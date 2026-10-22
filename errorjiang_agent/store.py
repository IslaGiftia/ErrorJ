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

                CREATE TABLE IF NOT EXISTS identity_bind_codes (
                    code TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    used_at INTEGER,
                    used_openid TEXT
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
                    confidence INTEGER NOT NULL DEFAULT 5,
                    source TEXT NOT NULL DEFAULT 'chat',
                    access_count INTEGER NOT NULL DEFAULT 0,
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

                CREATE TABLE IF NOT EXISTS identities (
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS group_members (
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    alias TEXT NOT NULL DEFAULT '',
                    relationship TEXT NOT NULL DEFAULT '群友',
                    allow_chat INTEGER NOT NULL DEFAULT 1,
                    allow_tools INTEGER NOT NULL DEFAULT 1,
                    memory_enabled INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    last_topic TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (platform, group_id, member_id)
                );

                CREATE TABLE IF NOT EXISTS group_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_message_id TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    UNIQUE(platform, group_id, source_message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_group_messages_group
                    ON group_messages(platform, group_id, id);

                CREATE TABLE IF NOT EXISTS memory_consolidation_runs (
                    day TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (day, platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    chat_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    due_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    sent_at INTEGER,
                    cancelled_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS relationship_state (
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    mood TEXT NOT NULL DEFAULT '平静',
                    energy INTEGER NOT NULL DEFAULT 7,
                    care INTEGER NOT NULL DEFAULT 6,
                    jealousy INTEGER NOT NULL DEFAULT 1,
                    last_topic TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS timeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    event_type TEXT NOT NULL DEFAULT 'event',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    event_at INTEGER NOT NULL,
                    follow_up_at INTEGER,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at INTEGER NOT NULL,
                    last_used_at INTEGER,
                    UNIQUE(platform, owner_id, content)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_timeline_owner
                    ON timeline_events(
                        platform, owner_id, status, follow_up_at, last_used_at
                    );
                """
            )
            memory_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memories)").fetchall()
            }
            for name, definition in (
                ("confidence", "INTEGER NOT NULL DEFAULT 5"),
                ("source", "TEXT NOT NULL DEFAULT 'chat'"),
                ("access_count", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if name not in memory_columns:
                    conn.execute(
                        f"ALTER TABLE memories ADD COLUMN {name} {definition}"
                    )
            member_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(group_members)"
                ).fetchall()
            }
            for name, definition in (
                ("alias", "TEXT NOT NULL DEFAULT ''"),
                ("relationship", "TEXT NOT NULL DEFAULT '群友'"),
                ("allow_chat", "INTEGER NOT NULL DEFAULT 1"),
                ("allow_tools", "INTEGER NOT NULL DEFAULT 1"),
                ("memory_enabled", "INTEGER NOT NULL DEFAULT 1"),
                ("notes", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in member_columns:
                    conn.execute(
                        f"ALTER TABLE group_members ADD COLUMN {name} {definition}"
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
        confidence: int = 5,
        source: str = "chat",
    ) -> None:
        text = " ".join(str(content or "").split()).strip()[:1000]
        if not text:
            return
        now = int(time.time())
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO memories
                   (platform, owner_id, kind, content, importance, confidence,
                    source, access_count, created_at, updated_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)
                   ON CONFLICT(platform, owner_id, content) DO UPDATE SET
                       importance = MAX(memories.importance, excluded.importance),
                       confidence = MAX(memories.confidence, excluded.confidence),
                       source = excluded.source,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    owner_id,
                    str(kind or "fact")[:30],
                    text,
                    max(1, min(int(importance or 5), 10)),
                    max(1, min(int(confidence or 5), 10)),
                    str(source or "chat")[:30],
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
        sql = """SELECT id, kind, content, importance, confidence, source,
                        access_count, created_at, updated_at, last_used_at
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
            word.lower()
            for word in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)
            if len(word) <= 20
        ][:6]
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT id, kind, content, importance, confidence,
                          access_count, updated_at, last_used_at
                   FROM memories
                   WHERE platform = ? AND owner_id = ?
                   ORDER BY updated_at DESC LIMIT 200""",
                (platform, owner_id),
            ).fetchall()
            now = int(time.time())
            kind_weights = {
                "boundary": 2.2,
                "preference": 1.7,
                "relationship": 1.7,
                "promise": 1.5,
                "habit": 1.2,
                "event": 1.0,
                "fact": 0.8,
            }

            def score(row: sqlite3.Row) -> float:
                content = str(row["content"] or "").lower()
                relevance = sum(
                    1.0 for word in words if word and word in content
                )
                age_days = max(
                    0.0,
                    (now - int(row["updated_at"] or now)) / 86400,
                )
                recency = max(0.0, 2.5 - age_days * 0.18)
                return (
                    relevance * 8.0
                    + int(row["importance"] or 5) * 0.72
                    + int(row["confidence"] or 5) * 0.48
                    + kind_weights.get(str(row["kind"] or "fact"), 0.8)
                    + recency
                    + min(5, int(row["access_count"] or 0)) * 0.22
                )

            ranked = sorted(rows, key=score, reverse=True)[
                : max(1, min(int(limit), 50))
            ]
            if rows:
                ids = [row["id"] for row in ranked]
                conn.executemany(
                    """UPDATE memories
                       SET last_used_at = ?, access_count = access_count + 1
                       WHERE id = ?""",
                    [(now, item_id) for item_id in ids],
                )
        return [str(row["content"]) for row in ranked]

    def delete_memory(self, platform: str, owner_id: str, memory_id: int) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE id = ? AND platform = ? AND owner_id = ?",
                (int(memory_id), platform, owner_id),
            )
        return cursor.rowcount > 0

    def mark_memory_used(self, platform: str, owner_id: str, memory_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE memories SET last_used_at = ?
                       , access_count = access_count + 1
                   WHERE id = ? AND platform = ? AND owner_id = ?""",
                (int(time.time()), int(memory_id), platform, owner_id),
            )

    def remember_group_member(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        display_name: str,
        topic: str = "",
    ) -> dict:
        now = int(time.time())
        name = " ".join(str(display_name or "").split()).strip()[:80]
        recent_topic = " ".join(str(topic or "").split()).strip()[:200]
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO group_members
                   (platform, group_id, member_id, display_name, first_seen,
                    last_seen, message_count, last_topic)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(platform, group_id, member_id) DO UPDATE SET
                       display_name = CASE
                           WHEN excluded.display_name != ''
                           THEN excluded.display_name
                           ELSE group_members.display_name
                       END,
                       last_seen = excluded.last_seen,
                       message_count = group_members.message_count + 1,
                       last_topic = CASE
                           WHEN excluded.last_topic != ''
                           THEN excluded.last_topic
                           ELSE group_members.last_topic
                       END""",
                (
                    platform,
                    str(group_id),
                    str(member_id),
                    name,
                    now,
                    now,
                    recent_topic,
                ),
            )
            row = conn.execute(
                """SELECT * FROM group_members
                   WHERE platform = ? AND group_id = ? AND member_id = ?""",
                (platform, str(group_id), str(member_id)),
            ).fetchone()
        return dict(row) if row else {}

    def get_group_member(
        self,
        platform: str,
        group_id: str,
        member_id: str,
    ) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT * FROM group_members
                   WHERE platform = ? AND group_id = ? AND member_id = ?""",
                (platform, str(group_id), str(member_id)),
            ).fetchone()
        return dict(row) if row else None

    def list_group_members(self, limit: int = 100) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT m.*, i.user_id
                   FROM group_members m
                   LEFT JOIN identities i
                     ON i.platform = m.platform AND i.owner_id = m.member_id
                   ORDER BY m.last_seen DESC LIMIT ?""",
                (max(1, min(int(limit), 300)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def group_member_display_name(
        self,
        platform: str,
        member_id: str,
    ) -> str:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT display_name FROM group_members
                   WHERE platform = ? AND member_id = ?
                   ORDER BY last_seen DESC LIMIT 1""",
                (platform, str(member_id)),
            ).fetchone()
        return str(row["display_name"] or "") if row else ""

    def update_group_member_profile(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        values: dict,
    ) -> dict | None:
        current = self.get_group_member(platform, group_id, member_id)
        if not current:
            return None
        allowed = {
            "alias",
            "relationship",
            "allow_chat",
            "allow_tools",
            "memory_enabled",
            "notes",
        }
        updates = {}
        for key in allowed:
            if key not in values:
                continue
            if key in ("allow_chat", "allow_tools", "memory_enabled"):
                updates[key] = 1 if bool(values[key]) else 0
            else:
                updates[key] = " ".join(
                    str(values[key] or "").split()
                ).strip()[:300]
        if not updates:
            return current
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._lock, self._connection() as conn:
            conn.execute(
                f"""UPDATE group_members SET {assignments}
                    WHERE platform = ? AND group_id = ? AND member_id = ?""",
                (
                    *updates.values(),
                    platform,
                    str(group_id),
                    str(member_id),
                ),
            )
        return self.get_group_member(platform, group_id, member_id)

    def add_group_message(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        display_name: str,
        role: str,
        content: str,
        source_message_id: str = "",
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO group_messages
                   (platform, group_id, member_id, display_name, role,
                    content, source_message_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    platform,
                    str(group_id),
                    str(member_id),
                    str(display_name or "")[:80],
                    str(role or "user"),
                    str(content or "")[:4000],
                    str(source_message_id or ""),
                    int(time.time()),
                ),
            )

    def get_group_messages(
        self,
        platform: str,
        group_id: str,
        limit: int = 20,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT member_id, display_name, role, content, created_at
                   FROM group_messages
                   WHERE platform = ? AND group_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (
                    platform,
                    str(group_id),
                    max(1, min(int(limit), 100)),
                ),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_group_messages(
        self,
        platform: str,
        group_id: str,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """DELETE FROM group_messages
                   WHERE platform = ? AND group_id = ?""",
                (platform, str(group_id)),
            )

    def recent_group_chats(
        self,
        since: int,
        minimum_messages: int = 4,
        limit: int = 20,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT platform, group_id, COUNT(*) AS message_count
                   FROM group_messages
                   WHERE role = 'user' AND created_at >= ?
                   GROUP BY platform, group_id
                   HAVING COUNT(*) >= ?
                   ORDER BY MAX(created_at) DESC LIMIT ?""",
                (
                    int(since),
                    max(1, int(minimum_messages)),
                    max(1, min(int(limit), 100)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_messages_since(
        self,
        platform: str,
        owner_id: str,
        since: int,
        limit: int = 80,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT role, content, created_at FROM messages
                   WHERE platform = ? AND owner_id = ? AND created_at >= ?
                   ORDER BY id DESC LIMIT ?""",
                (
                    platform,
                    owner_id,
                    int(since),
                    max(1, min(int(limit), 200)),
                ),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def recent_message_owners(
        self,
        since: int,
        minimum_messages: int = 4,
        limit: int = 50,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT platform, owner_id, COUNT(*) AS message_count
                   FROM messages
                   WHERE role = 'user' AND created_at >= ?
                   GROUP BY platform, owner_id
                   HAVING COUNT(*) >= ?
                   ORDER BY MAX(created_at) DESC LIMIT ?""",
                (
                    int(since),
                    max(1, int(minimum_messages)),
                    max(1, min(int(limit), 200)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_memory_consolidation(
        self,
        day: str,
        platform: str,
        owner_id: str,
        message_count: int,
    ) -> bool:
        with self._lock, self._connection() as conn:
            try:
                conn.execute(
                    """INSERT INTO memory_consolidation_runs
                       (day, platform, owner_id, message_count, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        day,
                        platform,
                        owner_id,
                        int(message_count),
                        int(time.time()),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

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
            "memory_consolidation_enabled": True,
            "memory_consolidation_time": "03:30",
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

    def last_proactive_at(self, owner_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT MAX(sent_at) AS sent_at FROM proactive_log
                   WHERE owner_id = ?""",
                (owner_id,),
            ).fetchone()
        return int(row["sent_at"] or 0)

    def bind_user(self, platform: str, owner_id: str, user_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO identities(platform, owner_id, user_id, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(platform, owner_id) DO UPDATE SET
                       user_id = excluded.user_id,
                       created_at = excluded.created_at""",
                (platform, owner_id, int(user_id), int(time.time())),
            )

    def unbind_user(self, platform: str, owner_id: str) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM identities WHERE platform = ? AND owner_id = ?",
                (platform, owner_id),
            )
        return cursor.rowcount > 0

    def linked_user_id(self, platform: str, owner_id: str) -> int | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT user_id FROM identities WHERE platform = ? AND owner_id = ?",
                (platform, owner_id),
            ).fetchone()
        return int(row["user_id"]) if row else None

    def list_identities(self, platform: str = "qq") -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT owner_id, user_id, created_at FROM identities
                   WHERE platform = ? ORDER BY created_at, owner_id""",
                (platform,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_reminder(
        self,
        platform: str,
        owner_id: str,
        chat_id: str,
        chat_type: str,
        text: str,
        due_at: int,
    ) -> int:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """INSERT INTO reminders
                   (platform, owner_id, chat_id, chat_type, text, due_at,
                    created_at, sent_at, cancelled_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)""",
                (
                    platform,
                    owner_id,
                    chat_id,
                    chat_type,
                    str(text or "")[:500],
                    int(due_at),
                    int(time.time()),
                ),
            )
        return int(cursor.lastrowid)

    def due_reminders(self, now: int, limit: int = 20) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT * FROM reminders
                   WHERE sent_at IS NULL AND cancelled_at IS NULL AND due_at <= ?
                   ORDER BY due_at, id LIMIT ?""",
                (int(now), max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_reminder_sent(self, reminder_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE reminders SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
                (int(time.time()), int(reminder_id)),
            )

    def list_reminders(self, platform: str, owner_id: str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT id, text, due_at, chat_type FROM reminders
                   WHERE platform = ? AND owner_id = ?
                     AND sent_at IS NULL AND cancelled_at IS NULL
                   ORDER BY due_at, id LIMIT 50""",
                (platform, owner_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def cancel_reminder(self, platform: str, owner_id: str, reminder_id: int) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """UPDATE reminders SET cancelled_at = ?
                   WHERE id = ? AND platform = ? AND owner_id = ?
                     AND sent_at IS NULL AND cancelled_at IS NULL""",
                (int(time.time()), int(reminder_id), platform, owner_id),
            )
        return cursor.rowcount > 0

    def get_relationship_state(self, platform: str, owner_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT * FROM relationship_state
                   WHERE platform = ? AND owner_id = ?""",
                (platform, owner_id),
            ).fetchone()
            last_user = conn.execute(
                """SELECT MAX(created_at) AS ts FROM messages
                   WHERE platform = ? AND owner_id = ? AND role = 'user'""",
                (platform, owner_id),
            ).fetchone()
        state = dict(row) if row else {
            "mood": "平静",
            "energy": 7,
            "care": 6,
            "jealousy": 1,
            "last_topic": "",
            "updated_at": int(time.time()),
        }
        state["last_user_at"] = (
            int(last_user["ts"]) if last_user and last_user["ts"] else 0
        )
        return state

    def update_relationship_state(
        self,
        platform: str,
        owner_id: str,
        values: dict,
    ) -> dict:
        current = self.get_relationship_state(platform, owner_id)
        mood = str(values.get("mood") or current.get("mood") or "平静")[:20]
        energy = max(0, min(int(values.get("energy", current.get("energy", 7))), 10))
        care = max(0, min(int(values.get("care", current.get("care", 6))), 10))
        jealousy = max(0, min(int(values.get("jealousy", current.get("jealousy", 1))), 3))
        topic = str(values.get("last_topic", current.get("last_topic", "")) or "")[:120]
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO relationship_state
                   (platform, owner_id, mood, energy, care, jealousy, last_topic, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(platform, owner_id) DO UPDATE SET
                       mood = excluded.mood,
                       energy = excluded.energy,
                       care = excluded.care,
                       jealousy = excluded.jealousy,
                       last_topic = excluded.last_topic,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    owner_id,
                    mood,
                    energy,
                    care,
                    jealousy,
                    topic,
                    int(time.time()),
                ),
            )
        return self.get_relationship_state(platform, owner_id)

    def last_user_topic(self, platform: str, owner_id: str) -> str:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT content FROM messages
                   WHERE platform = ? AND owner_id = ? AND role = 'user'
                   ORDER BY id DESC LIMIT 1""",
                (platform, owner_id),
            ).fetchone()
        return str(row["content"])[:120] if row else ""

    def add_timeline_event(
        self,
        platform: str,
        owner_id: str,
        event_type: str,
        title: str,
        content: str,
        event_at: int | None = None,
        follow_up_at: int | None = None,
    ) -> int:
        title_text = " ".join(str(title or "").split()).strip()[:120]
        content_text = " ".join(str(content or "").split()).strip()[:1000]
        if not content_text:
            content_text = title_text
        if not title_text:
            title_text = content_text[:120]
        if not content_text:
            return 0
        now = int(time.time())
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO timeline_events
                   (platform, owner_id, event_type, title, content, event_at,
                    follow_up_at, status, created_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, NULL)
                   ON CONFLICT(platform, owner_id, content) DO UPDATE SET
                       event_type = excluded.event_type,
                       title = excluded.title,
                       event_at = excluded.event_at,
                       follow_up_at = COALESCE(
                           excluded.follow_up_at,
                           timeline_events.follow_up_at
                       )""",
                (
                    platform,
                    owner_id,
                    str(event_type or "event")[:30],
                    title_text,
                    content_text,
                    int(event_at) if event_at is not None else now,
                    int(follow_up_at) if follow_up_at else None,
                    now,
                ),
            )
            row = conn.execute(
                """SELECT id FROM timeline_events
                   WHERE platform = ? AND owner_id = ? AND content = ?""",
                (platform, owner_id, content_text),
            ).fetchone()
        return int(row["id"]) if row else 0

    def list_timeline_events(
        self,
        platform: str,
        owner_id: str,
        limit: int = 100,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT * FROM timeline_events
                   WHERE platform = ? AND owner_id = ?
                   ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,
                            COALESCE(follow_up_at, event_at) DESC, id DESC
                   LIMIT ?""",
                (platform, owner_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [dict(row) for row in rows]

    def due_timeline_events(
        self,
        now: int,
        limit: int = 20,
        platform: str | None = None,
        owner_id: str | None = None,
    ) -> list[dict]:
        clauses = [
            "status = 'open'",
            "follow_up_at IS NOT NULL",
            "follow_up_at <= ?",
            "last_used_at IS NULL",
        ]
        params: list = [int(now)]
        if platform is not None:
            clauses.append("platform = ?")
            params.append(platform)
        if owner_id is not None:
            clauses.append("owner_id = ?")
            params.append(owner_id)
        params.append(max(1, min(int(limit), 100)))
        with self._connection() as conn:
            rows = conn.execute(
                f"""SELECT * FROM timeline_events
                    WHERE {" AND ".join(clauses)}
                    ORDER BY follow_up_at, id LIMIT ?""",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_timeline_used(self, event_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE timeline_events SET last_used_at = ? WHERE id = ?",
                (int(time.time()), int(event_id)),
            )

    def set_timeline_status(
        self,
        platform: str,
        owner_id: str,
        event_id: int,
        status: str,
    ) -> bool:
        if status not in ("open", "done"):
            return False
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """UPDATE timeline_events
                   SET status = ?,
                       last_used_at = CASE
                           WHEN ? = 'open' THEN NULL
                           ELSE last_used_at
                       END
                   WHERE id = ? AND platform = ? AND owner_id = ?""",
                (status, status, int(event_id), platform, owner_id),
            )
        return cursor.rowcount > 0

    def delete_timeline_event(
        self, platform: str, owner_id: str, event_id: int
    ) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """DELETE FROM timeline_events
                   WHERE id = ? AND platform = ? AND owner_id = ?""",
                (int(event_id), platform, owner_id),
            )
        return cursor.rowcount > 0

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

    def create_identity_bind_code(
        self,
        platform: str,
        target_user_id: int,
        ttl_seconds: int = 600,
    ) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + max(60, min(int(ttl_seconds), 3600))
        with self._lock, self._connection() as conn:
            conn.execute(
                "DELETE FROM identity_bind_codes "
                "WHERE expires_at < ? OR used_at IS NOT NULL",
                (now,),
            )
            for _ in range(12):
                code = f"{secrets.randbelow(1_000_000):06d}"
                try:
                    conn.execute(
                        """INSERT INTO identity_bind_codes
                           (code, platform, target_user_id, created_at,
                            expires_at, used_at, used_openid)
                           VALUES (?, ?, ?, ?, ?, NULL, NULL)""",
                        (
                            code,
                            platform,
                            int(target_user_id),
                            now,
                            expires_at,
                        ),
                    )
                    return code, expires_at
                except sqlite3.IntegrityError:
                    continue
        raise RuntimeError("无法生成绑定码，请稍后重试。")

    def consume_identity_bind_code(
        self,
        platform: str,
        code: str,
        openid: str,
    ) -> int | None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """SELECT target_user_id FROM identity_bind_codes
                   WHERE code = ? AND platform = ? AND used_at IS NULL
                     AND expires_at >= ?""",
                (str(code), platform, now),
            ).fetchone()
            if not row:
                return None
            cursor = conn.execute(
                """UPDATE identity_bind_codes
                   SET used_at = ?, used_openid = ?
                   WHERE code = ? AND platform = ? AND used_at IS NULL""",
                (now, openid, str(code), platform),
            )
            if cursor.rowcount <= 0:
                return None
            return int(row["target_user_id"])

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
