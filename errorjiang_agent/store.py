from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
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

                CREATE TABLE IF NOT EXISTS admins (
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'fact',
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 5,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_used_at INTEGER,
                    UNIQUE(platform, owner_id, content)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS stickers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    ref TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    UNIQUE(owner_id, kind, ref)
                );

                CREATE TABLE IF NOT EXISTS proactive_log (
                    day TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    sent_at INTEGER NOT NULL,
                    PRIMARY KEY (day, slot, owner_id)
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

    def bind_admin(self, platform: str, owner_id: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO admins(platform, owner_id, created_at)
                   VALUES (?, ?, ?)""",
                (platform, owner_id, int(time.time())),
            )

    def is_admin(self, platform: str, owner_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM admins WHERE platform = ? AND owner_id = ?",
                (platform, owner_id),
            ).fetchone()
        return row is not None

    def has_admins(self, platform: str = "qq") -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM admins WHERE platform = ? LIMIT 1",
                (platform,),
            ).fetchone()
        return row is not None

    def admin_ids(self, platform: str = "qq") -> list[str]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT owner_id FROM admins
                   WHERE platform = ? ORDER BY created_at, owner_id""",
                (platform,),
            ).fetchall()
        return [str(row["owner_id"]) for row in rows]

    def add_memory(
        self,
        platform: str,
        owner_id: str,
        content: str,
        kind: str = "fact",
        importance: int = 5,
    ) -> None:
        text = " ".join(str(content or "").split()).strip()[:1000]
        if not text:
            return
        now = int(time.time())
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO memories
                   (platform, owner_id, kind, content, importance,
                    created_at, updated_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(platform, owner_id, content) DO UPDATE SET
                       importance = MAX(memories.importance, excluded.importance),
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    owner_id,
                    str(kind or "fact")[:30],
                    text,
                    max(1, min(int(importance or 5), 10)),
                    now,
                    now,
                ),
            )

    def list_memories(
        self,
        platform: str,
        owner_id: str,
        query: str = "",
        limit: int = 50,
    ) -> list[dict]:
        sql = """SELECT id, kind, content, importance, created_at, updated_at
                 FROM memories WHERE platform = ? AND owner_id = ?"""
        params: list = [platform, owner_id]
        if query.strip():
            sql += " AND content LIKE ?"
            params.append(f"%{query.strip()[:100]}%")
        sql += " ORDER BY importance DESC, updated_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def memory_context(
        self,
        platform: str,
        owner_id: str,
        query: str,
        limit: int = 10,
    ) -> list[str]:
        words = [
            word
            for word in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)
            if len(word) <= 20
        ][:6]
        with self._connection() as conn:
            if words:
                clauses = " OR ".join("content LIKE ?" for _ in words)
                rows = conn.execute(
                    f"""SELECT id, content FROM memories
                        WHERE platform = ? AND owner_id = ? AND ({clauses})
                        ORDER BY importance DESC, updated_at DESC LIMIT ?""",
                    (platform, owner_id, *[f"%{word}%" for word in words], limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, content FROM memories
                       WHERE platform = ? AND owner_id = ?
                       ORDER BY importance DESC, updated_at DESC LIMIT ?""",
                    (platform, owner_id, limit),
                ).fetchall()
            if rows:
                now = int(time.time())
                ids = [row["id"] for row in rows]
                conn.executemany(
                    "UPDATE memories SET last_used_at = ? WHERE id = ?",
                    [(now, item_id) for item_id in ids],
                )
        return [str(row["content"]) for row in rows]

    def delete_memory(self, platform: str, owner_id: str, memory_id: int) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE id = ? AND platform = ? AND owner_id = ?",
                (int(memory_id), platform, owner_id),
            )
        return cursor.rowcount > 0

    def get_settings(self, platform: str, owner_id: str) -> dict:
        defaults = {
            "memory_enabled": True,
            "proactive_enabled": True,
            "proactive_max_per_day": 2,
            "quiet_start": "23:30",
            "quiet_end": "08:00",
            "morning_time": "09:00",
            "night_time": "21:30",
            "sticker_enabled": True,
            "voice_enabled": False,
        }
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM settings WHERE platform = ? AND owner_id = ?",
                (platform, owner_id),
            ).fetchone()
        if row:
            try:
                saved = json.loads(row["value_json"])
                if isinstance(saved, dict):
                    defaults.update(saved)
            except json.JSONDecodeError:
                pass
        return defaults

    def save_settings(self, platform: str, owner_id: str, values: dict) -> dict:
        current = self.get_settings(platform, owner_id)
        for key in current:
            if key in values:
                current[key] = values[key]
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO settings(platform, owner_id, value_json, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(platform, owner_id) DO UPDATE SET
                       value_json = excluded.value_json,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    owner_id,
                    json.dumps(current, ensure_ascii=False),
                    int(time.time()),
                ),
            )
        return current

    def add_sticker(
        self,
        owner_id: str,
        kind: str,
        ref: str,
        tags: str = "",
    ) -> int:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO stickers(owner_id, kind, ref, tags, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (owner_id, kind, ref, tags[:300], int(time.time())),
            )
            row = conn.execute(
                "SELECT id FROM stickers WHERE owner_id = ? AND kind = ? AND ref = ?",
                (owner_id, kind, ref),
            ).fetchone()
        return int(row["id"])

    def list_stickers(self, owner_id: str, limit: int = 100) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT id, kind, ref, tags, created_at FROM stickers
                   WHERE owner_id = ? ORDER BY id DESC LIMIT ?""",
                (owner_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_sticker(self, owner_id: str, sticker_id: int) -> dict | None:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM stickers WHERE id = ? AND owner_id = ?",
                (int(sticker_id), owner_id),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM stickers WHERE id = ?", (int(sticker_id),))
        return dict(row)

    def claim_proactive_slot(self, day: str, slot: str, owner_id: str) -> bool:
        with self._lock, self._connection() as conn:
            try:
                conn.execute(
                    """INSERT INTO proactive_log(day, slot, owner_id, sent_at)
                       VALUES (?, ?, ?, ?)""",
                    (day, slot, owner_id, int(time.time())),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def proactive_count(self, day: str, owner_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS n FROM proactive_log
                   WHERE day = ? AND owner_id = ?""",
                (day, owner_id),
            ).fetchone()
        return int(row["n"])

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
