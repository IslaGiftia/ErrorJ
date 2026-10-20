from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time


class AgentStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_messages_owner
                    ON messages(platform, owner_id, id);

                CREATE TABLE IF NOT EXISTS pending_actions (
                    code TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    used_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS seen_events (
                    event_key TEXT PRIMARY KEY,
                    seen_at INTEGER NOT NULL
                );
                """
            )

    def seen_event(self, event_key: str) -> bool:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO seen_events(event_key, seen_at) VALUES (?, ?)",
                    (event_key, now),
                )
            except sqlite3.IntegrityError:
                return True
            conn.execute(
                "DELETE FROM seen_events WHERE seen_at < ?",
                (now - 3 * 86400,),
            )
            return False

    def add_message(self, platform: str, owner_id: str, role: str, content: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO messages(platform, owner_id, role, content, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (platform, owner_id, role, content, int(time.time())),
            )

    def get_messages(self, platform: str, owner_id: str, limit: int) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT role, content FROM messages
                   WHERE platform = ? AND owner_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (platform, owner_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_messages(self, platform: str, owner_id: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "DELETE FROM messages WHERE platform = ? AND owner_id = ?",
                (platform, owner_id),
            )

    def create_pending(
        self,
        platform: str,
        owner_id: str,
        chat_id: str,
        action: dict,
        ttl_seconds: int = 120,
    ) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + ttl_seconds
        with self._lock, self._connection() as conn:
            conn.execute(
                "DELETE FROM pending_actions WHERE expires_at < ? OR used_at IS NOT NULL",
                (now,),
            )
            for _ in range(12):
                code = f"{secrets.randbelow(1_000_000):06d}"
                try:
                    conn.execute(
                        """INSERT INTO pending_actions
                           (code, platform, owner_id, chat_id, action_json,
                            created_at, expires_at, used_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                        (
                            code,
                            platform,
                            owner_id,
                            chat_id,
                            json.dumps(action, ensure_ascii=False),
                            now,
                            expires_at,
                        ),
                    )
                    return code, expires_at
                except sqlite3.IntegrityError:
                    continue
        raise RuntimeError("无法生成审核确认码，请稍后重试。")

    def consume_pending(
        self, platform: str, owner_id: str, chat_id: str, code: str
    ) -> dict | None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """SELECT * FROM pending_actions
                   WHERE code = ? AND platform = ? AND owner_id = ? AND chat_id = ?
                     AND used_at IS NULL AND expires_at >= ?""",
                (code, platform, owner_id, chat_id, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE pending_actions SET used_at = ? WHERE code = ?",
                (now, code),
            )
        try:
            action = json.loads(row["action_json"])
        except json.JSONDecodeError:
            return None
        return action if isinstance(action, dict) else None
