from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from .persona import normalize_persona_custom_prompt
from .settings_schema import normalize_settings_update


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
                    strength REAL NOT NULL DEFAULT 1.0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived_at INTEGER,
                    evidence TEXT NOT NULL DEFAULT '',
                    source_ref TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_used_at INTEGER,
                    UNIQUE(platform, owner_id, content)
                );

                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_events_memory
                    ON memory_events(memory_id, id DESC);

                CREATE TABLE IF NOT EXISTS memory_decay_runs (
                    day TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_extraction_runs (
                    day TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (day, platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS history_cleanup_runs (
                    day TEXT PRIMARY KEY,
                    private_deleted INTEGER NOT NULL DEFAULT 0,
                    group_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_call_metrics (
                    day TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    call_count INTEGER NOT NULL DEFAULT 0,
                    total_ms INTEGER NOT NULL DEFAULT 0,
                    last_at INTEGER NOT NULL,
                    PRIMARY KEY (day, kind, success)
                );

                CREATE TABLE IF NOT EXISTS group_quiet_state (
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    quiet_until INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, group_id, member_id)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    platform TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, owner_id)
                );

                CREATE TABLE IF NOT EXISTS sticker_libraries (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stickers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    ref TEXT NOT NULL,
                    library_id TEXT NOT NULL DEFAULT 'default',
                    category TEXT NOT NULL DEFAULT '未分类',
                    source_name TEXT NOT NULL DEFAULT '',
                    caption TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '',
                    mood TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at INTEGER,
                    created_at INTEGER NOT NULL,
                    UNIQUE(owner_id, kind, ref)
                );

                CREATE TABLE IF NOT EXISTS sticker_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    sticker_id INTEGER NOT NULL,
                    platform TEXT NOT NULL DEFAULT '',
                    chat_id TEXT NOT NULL DEFAULT '',
                    query TEXT NOT NULL DEFAULT '',
                    matched_by TEXT NOT NULL DEFAULT '',
                    used_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sticker_usage_chat
                    ON sticker_usage(
                        owner_id, platform, chat_id, used_at DESC
                    );

                CREATE TABLE IF NOT EXISTS sticker_categories (
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (owner_id, name)
                );

                CREATE TABLE IF NOT EXISTS sticker_selection_rules (
                    scope_type TEXT NOT NULL,
                    scope_key TEXT NOT NULL DEFAULT '',
                    library_ids TEXT NOT NULL DEFAULT '[]',
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (scope_type, scope_key)
                );

                CREATE TABLE IF NOT EXISTS sticker_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL DEFAULT '0',
                    library_id TEXT NOT NULL DEFAULT 'default',
                    ref TEXT NOT NULL,
                    source_name TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT '',
                    chat_id TEXT NOT NULL DEFAULT '',
                    sender_id TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    UNIQUE(owner_id, ref)
                );
                CREATE INDEX IF NOT EXISTS idx_sticker_candidates_created
                    ON sticker_candidates(created_at DESC);

                CREATE TABLE IF NOT EXISTS shared_locations (
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, group_id, member_id)
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
                CREATE INDEX IF NOT EXISTS idx_group_messages_activity
                    ON group_messages(
                        platform, group_id, role, created_at
                    );

                CREATE TABLE IF NOT EXISTS group_jargon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    term TEXT NOT NULL,
                    meaning TEXT NOT NULL DEFAULT '',
                    example TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    member_count INTEGER NOT NULL DEFAULT 1,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(platform, group_id, term)
                );
                CREATE INDEX IF NOT EXISTS idx_group_jargon_status
                    ON group_jargon(status, updated_at);

                CREATE TABLE IF NOT EXISTS group_proactive_state (
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    last_user_at INTEGER NOT NULL DEFAULT 0,
                    last_user_message_id INTEGER NOT NULL DEFAULT 0,
                    next_proactive_at INTEGER,
                    last_proactive_at INTEGER,
                    unanswered_count INTEGER NOT NULL DEFAULT 0,
                    awaiting_reply_until INTEGER,
                    last_proactive_message_id INTEGER NOT NULL DEFAULT 0,
                    last_proactive_text TEXT NOT NULL DEFAULT '',
                    last_proactive_run_id INTEGER,
                    last_effective_reply_at INTEGER,
                    last_error TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, group_id)
                );
                CREATE INDEX IF NOT EXISTS idx_group_proactive_next
                    ON group_proactive_state(
                        platform, next_proactive_at, unanswered_count
                    );

                CREATE TABLE IF NOT EXISTS group_proactive_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    generated_text TEXT NOT NULL DEFAULT '',
                    context_chars INTEGER NOT NULL DEFAULT 0,
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    sent_message_id INTEGER NOT NULL DEFAULT 0,
                    reply_at INTEGER,
                    reply_member_id TEXT NOT NULL DEFAULT '',
                    reply_text TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_group_proactive_runs_group
                    ON group_proactive_runs(
                        platform, group_id, id DESC
                    );

                CREATE TABLE IF NOT EXISTS group_proactive_overrides (
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    enabled INTEGER,
                    idle_trigger_minutes INTEGER,
                    max_per_day INTEGER,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, group_id)
                );

                CREATE TABLE IF NOT EXISTS group_weather_locations (
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    city TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (platform, group_id, member_id)
                );

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
                    cancelled_at INTEGER,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at INTEGER,
                    last_error TEXT NOT NULL DEFAULT '',
                    failed_at INTEGER
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
            conn.execute(
                """INSERT OR IGNORE INTO sticker_libraries
                       (id, name, enabled, sort_order, created_at, updated_at)
                   VALUES ('default', '默认图库', 1, 0, ?, ?)""",
                (int(time.time()), int(time.time())),
            )
            conn.execute(
                """UPDATE group_messages SET display_name = ?
                   WHERE role = 'assistant'
                     AND display_name IN ('折兮颜', '小颜', '大肥鱼',
                                          'ErrorJ Agent')""",
                ("鲸鲸",),
            )
            settings_rows = conn.execute(
                "SELECT platform, owner_id, value_json FROM settings"
            ).fetchall()
            for settings_row in settings_rows:
                try:
                    saved = json.loads(settings_row["value_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(saved, dict):
                    continue
                original = str(saved.get("persona_custom_prompt") or "")
                normalized = normalize_persona_custom_prompt(original)
                if normalized == original:
                    continue
                saved["persona_custom_prompt"] = normalized
                conn.execute(
                    """UPDATE settings SET value_json = ?, updated_at = ?
                       WHERE platform = ? AND owner_id = ?""",
                    (
                        json.dumps(saved, ensure_ascii=False),
                        int(time.time()),
                        settings_row["platform"],
                        settings_row["owner_id"],
                    ),
                )
            proactive_state_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(group_proactive_state)"
                ).fetchall()
            }
            for name, definition in (
                ("awaiting_reply_until", "INTEGER"),
                (
                    "last_proactive_message_id",
                    "INTEGER NOT NULL DEFAULT 0",
                ),
                ("last_proactive_text", "TEXT NOT NULL DEFAULT ''"),
                ("last_proactive_run_id", "INTEGER"),
                ("last_effective_reply_at", "INTEGER"),
            ):
                if name not in proactive_state_columns:
                    conn.execute(
                        "ALTER TABLE group_proactive_state "
                        f"ADD COLUMN {name} {definition}"
                    )
            memory_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memories)").fetchall()
            }
            for name, definition in (
                ("confidence", "INTEGER NOT NULL DEFAULT 5"),
                ("source", "TEXT NOT NULL DEFAULT 'chat'"),
                ("access_count", "INTEGER NOT NULL DEFAULT 0"),
                ("strength", "REAL NOT NULL DEFAULT 1.0"),
                ("pinned", "INTEGER NOT NULL DEFAULT 0"),
                ("archived_at", "INTEGER"),
                ("evidence", "TEXT NOT NULL DEFAULT ''"),
                ("source_ref", "TEXT NOT NULL DEFAULT ''"),
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
            sticker_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(stickers)").fetchall()
            }
            if "category" not in sticker_columns:
                conn.execute(
                    "ALTER TABLE stickers "
                    "ADD COLUMN category TEXT NOT NULL DEFAULT '未分类'"
                )
            if "source_name" not in sticker_columns:
                conn.execute(
                    "ALTER TABLE stickers "
                    "ADD COLUMN source_name TEXT NOT NULL DEFAULT ''"
                )
            for name in ("caption", "keywords", "mood"):
                if name not in sticker_columns:
                    conn.execute(
                        "ALTER TABLE stickers "
                        f"ADD COLUMN {name} TEXT NOT NULL DEFAULT ''"
                    )
            if "use_count" not in sticker_columns:
                conn.execute(
                    "ALTER TABLE stickers "
                    "ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0"
                )
            if "last_used_at" not in sticker_columns:
                conn.execute(
                    "ALTER TABLE stickers ADD COLUMN last_used_at INTEGER"
                )
            if "library_id" not in sticker_columns:
                conn.execute(
                    "ALTER TABLE stickers "
                    "ADD COLUMN library_id TEXT NOT NULL DEFAULT 'default'"
                )
            reminder_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(reminders)").fetchall()
            }
            for name, definition in (
                ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_attempt_at", "INTEGER"),
                ("last_error", "TEXT NOT NULL DEFAULT ''"),
                ("failed_at", "INTEGER"),
            ):
                if name not in reminder_columns:
                    conn.execute(
                        f"ALTER TABLE reminders ADD COLUMN {name} {definition}"
                    )
            conn.execute(
                "UPDATE stickers SET category = '未分类' "
                "WHERE TRIM(category) = ''"
            )
            conn.execute(
                "UPDATE stickers SET library_id = 'default' "
                "WHERE TRIM(COALESCE(library_id, '')) = ''"
            )
            conn.execute(
                """INSERT OR IGNORE INTO stickers(
                       owner_id, kind, ref, category, source_name, tags, created_at
                   )
                   SELECT '0', kind, ref, category, source_name, tags, created_at
                   FROM stickers WHERE owner_id <> '0'"""
            )
            conn.execute("DELETE FROM stickers WHERE owner_id <> '0'")
            conn.execute(
                """INSERT OR IGNORE INTO sticker_categories(
                       owner_id, name, created_at
                   )
                   SELECT '0', name, created_at
                   FROM sticker_categories WHERE owner_id <> '0'"""
            )
            conn.execute(
                "DELETE FROM sticker_categories WHERE owner_id <> '0'"
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
        evidence: str = "",
        source_ref: str = "",
        pinned: bool = False,
    ) -> int | None:
        text = " ".join(str(content or "").split()).strip()[:1000]
        if not text:
            return None
        now = int(time.time())
        bounded_importance = max(1, min(int(importance or 5), 10))
        bounded_confidence = max(1, min(int(confidence or 5), 10))
        strength = min(
            1.0,
            0.35 + bounded_importance * 0.04 + bounded_confidence * 0.03,
        )
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO memories
                   (platform, owner_id, kind, content, importance, confidence,
                    source, access_count, strength, pinned, evidence,
                    source_ref, created_at, updated_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(platform, owner_id, content) DO UPDATE SET
                       importance = MAX(memories.importance, excluded.importance),
                       confidence = MAX(memories.confidence, excluded.confidence),
                       source = excluded.source,
                       strength = MAX(memories.strength, excluded.strength),
                       pinned = MAX(memories.pinned, excluded.pinned),
                       archived_at = NULL,
                       evidence = CASE
                           WHEN excluded.evidence = ''
                           THEN memories.evidence
                           WHEN memories.evidence = ''
                           THEN excluded.evidence
                           WHEN instr(memories.evidence, excluded.evidence) > 0
                           THEN memories.evidence
                           ELSE substr(
                               memories.evidence || char(10) ||
                               excluded.evidence,
                               -600
                           )
                       END,
                       source_ref = CASE
                           WHEN excluded.source_ref <> ''
                           THEN excluded.source_ref
                           ELSE memories.source_ref
                       END,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    owner_id,
                    str(kind or "fact")[:30],
                    text,
                    bounded_importance,
                    bounded_confidence,
                    str(source or "chat")[:30],
                    strength,
                    1 if pinned else 0,
                    " ".join(str(evidence or "").split()).strip()[:600],
                    str(source_ref or "").strip()[:200],
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """SELECT id FROM memories
                   WHERE platform = ? AND owner_id = ? AND content = ?""",
                (platform, owner_id, text),
            ).fetchone()
            if row:
                memory_id = int(row["id"])
                conn.execute(
                    """INSERT INTO memory_events
                       (memory_id, platform, owner_id, action, detail, created_at)
                       VALUES (?, ?, ?, 'remember', ?, ?)""",
                    (
                        memory_id,
                        platform,
                        owner_id,
                        text[:300],
                        now,
                    ),
                )
                return memory_id
        return None

    def list_memories(
        self,
        platform: str,
        owner_id: str,
        query: str = "",
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[dict]:
        sql = """SELECT id, kind, content, importance, confidence, source,
                        access_count, strength, pinned, archived_at, evidence,
                        source_ref, created_at, updated_at, last_used_at
                 FROM memories WHERE platform = ? AND owner_id = ?"""
        params: list = [platform, owner_id]
        if not include_archived:
            sql += " AND archived_at IS NULL"
        if query.strip():
            sql += " AND (content LIKE ? OR evidence LIKE ?)"
            pattern = f"%{query.strip()[:100]}%"
            params.extend((pattern, pattern))
        sql += """ ORDER BY pinned DESC, strength DESC, importance DESC,
                         updated_at DESC, id DESC LIMIT ?"""
        params.append(max(1, min(int(limit), 500)))
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
        normalized_query = " ".join(str(query or "").lower().split()).strip()
        words = []
        for word in re.findall(r"[\w\u4e00-\u9fff]{2,}", normalized_query):
            if len(word) <= 20 and word not in words:
                words.append(word)
            if re.search(r"[\u4e00-\u9fff]", word) and len(word) >= 3:
                for index in range(len(word) - 1):
                    gram = word[index : index + 2]
                    if gram not in words:
                        words.append(gram)
        words = words[:20]

        def match_parts(content: str) -> tuple[int, int]:
            phrase = int(
                bool(normalized_query and normalized_query in content)
            )
            relevance = sum(
                1 for word in words if word and word in content
            )
            return phrase, relevance

        with self._connection() as conn:
            rows = conn.execute(
                """SELECT id, kind, content, importance, confidence,
                          access_count, strength, updated_at, last_used_at
                   FROM memories
                   WHERE platform = ? AND owner_id = ? AND archived_at IS NULL
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
                phrase, relevance = match_parts(content)
                age_days = max(
                    0.0,
                    (now - int(row["updated_at"] or now)) / 86400,
                )
                recency = max(0.0, 2.5 - age_days * 0.18)
                return (
                    phrase * 18.0
                    + relevance * 5.0
                    + int(row["importance"] or 5) * 0.72
                    + int(row["confidence"] or 5) * 0.48
                    + kind_weights.get(str(row["kind"] or "fact"), 0.8)
                    + recency
                    + min(5, int(row["access_count"] or 0)) * 0.22
                    + float(row["strength"] or 1.0) * 2.0
                )

            candidates = []
            for row in rows:
                if not normalized_query:
                    candidates.append(row)
                    continue
                phrase, relevance = match_parts(
                    str(row["content"] or "").lower()
                )
                if phrase or relevance:
                    candidates.append(row)
            ranked = sorted(candidates, key=score, reverse=True)[
                : max(1, min(int(limit), 50))
            ]
            if ranked:
                ids = [row["id"] for row in ranked]
                conn.executemany(
                    """UPDATE memories
                       SET last_used_at = ?,
                           access_count = access_count + 1,
                           strength = MIN(1.0, strength + 0.08)
                       WHERE id = ?""",
                    [(now, item_id) for item_id in ids],
                )
        return [str(row["content"]) for row in ranked]

    def delete_memory(self, platform: str, owner_id: str, memory_id: int) -> bool:
        with self._lock, self._connection() as conn:
            conn.execute(
                """DELETE FROM memory_events
                   WHERE memory_id = ? AND platform = ? AND owner_id = ?""",
                (int(memory_id), platform, owner_id),
            )
            cursor = conn.execute(
                "DELETE FROM memories WHERE id = ? AND platform = ? AND owner_id = ?",
                (int(memory_id), platform, owner_id),
            )
        return cursor.rowcount > 0

    def mark_memory_used(self, platform: str, owner_id: str, memory_id: int) -> None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """UPDATE memories SET last_used_at = ?,
                       access_count = access_count + 1,
                       strength = MIN(1.0, strength + 0.12),
                       archived_at = NULL
                   WHERE id = ? AND platform = ? AND owner_id = ?""",
                (now, int(memory_id), platform, owner_id),
            )
            if cursor.rowcount:
                conn.execute(
                    """INSERT INTO memory_events
                       (memory_id, platform, owner_id, action, detail, created_at)
                       VALUES (?, ?, ?, 'recall', '', ?)""",
                    (int(memory_id), platform, owner_id, now),
                )

    def set_memory_archived(
        self,
        platform: str,
        owner_id: str,
        memory_id: int,
        archived: bool,
    ) -> bool:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """UPDATE memories
                   SET archived_at = ?, updated_at = ?,
                       strength = CASE WHEN ? THEN strength
                                       ELSE MAX(strength, 0.35) END
                   WHERE id = ? AND platform = ? AND owner_id = ?""",
                (
                    now if archived else None,
                    now,
                    0 if archived else 1,
                    int(memory_id),
                    platform,
                    owner_id,
                ),
            )
            if cursor.rowcount:
                conn.execute(
                    """INSERT INTO memory_events
                       (memory_id, platform, owner_id, action, detail, created_at)
                       VALUES (?, ?, ?, ?, '', ?)""",
                    (
                        int(memory_id),
                        platform,
                        owner_id,
                        "archive" if archived else "restore",
                        now,
                    ),
                )
        return cursor.rowcount > 0

    def claim_memory_decay(self, day: str) -> bool:
        with self._lock, self._connection() as conn:
            try:
                conn.execute(
                    """INSERT INTO memory_decay_runs(day, created_at)
                       VALUES (?, ?)""",
                    (day, int(time.time())),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def decay_memories(self, now: int | None = None) -> dict[str, int]:
        current = int(now or time.time())
        decayed = 0
        archived = 0
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """SELECT id, platform, owner_id, importance, confidence,
                          strength, created_at, updated_at, last_used_at
                   FROM memories
                   WHERE archived_at IS NULL AND pinned = 0
                   ORDER BY COALESCE(last_used_at, updated_at, created_at)
                   LIMIT 2000"""
            ).fetchall()
            for row in rows:
                anchor = int(
                    row["last_used_at"]
                    or row["updated_at"]
                    or row["created_at"]
                    or current
                )
                age_days = max(0.0, (current - anchor) / 86400)
                if age_days < 1:
                    continue
                importance = int(row["importance"] or 5)
                confidence = int(row["confidence"] or 5)
                loss = min(
                    0.08,
                    0.008 * age_days
                    + max(0, 6 - importance) * 0.004
                    + max(0, 5 - confidence) * 0.003,
                )
                next_strength = max(
                    0.0,
                    float(row["strength"] or 1.0) - loss,
                )
                should_archive = (
                    next_strength <= 0.15
                    and importance < 9
                )
                conn.execute(
                    """UPDATE memories
                       SET strength = ?, archived_at = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        next_strength,
                        current if should_archive else None,
                        current,
                        int(row["id"]),
                    ),
                )
                decayed += 1
                if should_archive:
                    archived += 1
                    conn.execute(
                        """INSERT INTO memory_events
                           (memory_id, platform, owner_id, action, detail,
                            created_at)
                           VALUES (?, ?, ?, 'decay_archive', ?, ?)""",
                        (
                            int(row["id"]),
                            str(row["platform"]),
                            str(row["owner_id"]),
                            f"strength={next_strength:.3f}",
                            current,
                        ),
                    )
        return {"decayed": decayed, "archived": archived}

    def list_memory_events(
        self,
        platform: str,
        owner_id: str,
        memory_id: int,
        limit: int = 20,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT action, detail, created_at
                   FROM memory_events
                   WHERE memory_id = ? AND platform = ? AND owner_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (
                    int(memory_id),
                    platform,
                    owner_id,
                    max(1, min(int(limit), 100)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

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
    ) -> int | None:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
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
        return int(cursor.lastrowid) if cursor.rowcount > 0 else None

    def record_group_activity(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        display_name: str,
        content: str,
        source_message_id: str = "",
        *,
        reset_unanswered: bool = True,
        effective_reply: bool = False,
    ) -> bool:
        """Store a human group message and reset that group's idle state."""
        now = int(time.time())
        name = " ".join(str(display_name or "").split()).strip()[:80]
        topic = " ".join(str(content or "").split()).strip()[:4000]
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO group_messages
                   (platform, group_id, member_id, display_name, role,
                    content, source_message_id, created_at)
                   VALUES (?, ?, ?, ?, 'user', ?, ?, ?)""",
                (
                    platform,
                    str(group_id),
                    str(member_id),
                    name,
                    topic,
                    str(source_message_id or ""),
                    now,
                ),
            )
            if cursor.rowcount <= 0:
                return False
            message_id = int(cursor.lastrowid or 0)
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
                    topic[:200],
                ),
            )
            conn.execute(
                """INSERT INTO group_proactive_state
                   (platform, group_id, last_user_at, last_user_message_id,
                    next_proactive_at, unanswered_count, updated_at)
                   VALUES (?, ?, ?, ?, NULL, 0, ?)
                   ON CONFLICT(platform, group_id) DO UPDATE SET
                       last_user_at = excluded.last_user_at,
                       last_user_message_id = excluded.last_user_message_id,
                       next_proactive_at = NULL,
                       unanswered_count = CASE
                           WHEN ? THEN 0
                           ELSE unanswered_count
                       END,
                       awaiting_reply_until = CASE
                           WHEN ? THEN NULL
                           ELSE awaiting_reply_until
                       END,
                       last_effective_reply_at = CASE
                           WHEN ? THEN ?
                           ELSE last_effective_reply_at
                       END,
                       last_error = '',
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    str(group_id),
                    now,
                    message_id,
                    now,
                    1 if reset_unanswered else 0,
                    1 if reset_unanswered else 0,
                    1 if effective_reply else 0,
                    now,
                ),
            )
        return True

    def ensure_group_proactive_state(
        self,
        platform: str,
        group_id: str,
        now: int,
    ) -> dict:
        """Create a group state without making an already-quiet group fire immediately."""
        current = self.get_group_proactive_state(platform, group_id)
        if current:
            return current
        with self._lock, self._connection() as conn:
            latest = conn.execute(
                """SELECT id, created_at
                   FROM group_messages
                   WHERE platform = ? AND group_id = ? AND role = 'user'
                   ORDER BY id DESC LIMIT 1""",
                (platform, str(group_id)),
            ).fetchone()
            last_user_at = (
                int(latest["created_at"])
                if latest and int(latest["created_at"] or 0) > 0
                else int(now)
            )
            last_message_id = (
                int(latest["id"]) if latest and int(latest["id"] or 0) > 0 else 0
            )
            conn.execute(
                """INSERT OR IGNORE INTO group_proactive_state
                   (platform, group_id, last_user_at, last_user_message_id,
                    next_proactive_at, unanswered_count, updated_at)
                   VALUES (?, ?, ?, ?, NULL, 0, ?)""",
                (
                    platform,
                    str(group_id),
                    last_user_at,
                    last_message_id,
                    int(now),
                ),
            )
        return self.get_group_proactive_state(platform, group_id)

    def get_group_proactive_state(
        self,
        platform: str,
        group_id: str,
    ) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT *
                   FROM group_proactive_state
                   WHERE platform = ? AND group_id = ?""",
                (platform, str(group_id)),
            ).fetchone()
        return dict(row) if row else None

    def list_group_proactive_states(
        self,
        platform: str,
        limit: int = 20,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT *
                   FROM group_proactive_state
                   WHERE platform = ?
                   ORDER BY
                       CASE WHEN next_proactive_at IS NULL THEN 1 ELSE 0 END,
                       next_proactive_at,
                       updated_at DESC
                   LIMIT ?""",
                (
                    platform,
                    max(1, min(int(limit), 100)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def schedule_group_proactive(
        self,
        platform: str,
        group_id: str,
        next_at: int,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE group_proactive_state
                   SET next_proactive_at = ?, last_error = '', updated_at = ?
                   WHERE platform = ? AND group_id = ?""",
                (
                    int(next_at),
                    int(time.time()),
                    platform,
                    str(group_id),
                ),
            )

    def record_group_proactive_failure(
        self,
        platform: str,
        group_id: str,
        next_at: int,
        error: str,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE group_proactive_state
                   SET next_proactive_at = ?, last_error = ?, updated_at = ?
                   WHERE platform = ? AND group_id = ?""",
                (
                    int(next_at),
                    " ".join(str(error or "").split()).strip()[:500],
                    int(time.time()),
                    platform,
                    str(group_id),
                ),
            )

    def mark_group_proactive_sent(
        self,
        platform: str,
        group_id: str,
        sent_at: int,
        *,
        message_id: int = 0,
        text: str = "",
        run_id: int | None = None,
        reply_window_seconds: int = 15 * 60,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE group_proactive_state
                   SET next_proactive_at = NULL,
                       last_proactive_at = ?,
                       unanswered_count = unanswered_count + 1,
                       awaiting_reply_until = ?,
                       last_proactive_message_id = ?,
                       last_proactive_text = ?,
                       last_proactive_run_id = ?,
                       last_error = '',
                       updated_at = ?
                   WHERE platform = ? AND group_id = ?""",
                (
                    int(sent_at),
                    int(sent_at) + max(60, int(reply_window_seconds)),
                    int(message_id),
                    " ".join(str(text or "").split()).strip()[:1200],
                    int(run_id) if run_id is not None else None,
                    int(sent_at),
                    platform,
                    str(group_id),
                ),
            )

    def expire_group_proactive_awaiting(
        self,
        platform: str,
        group_id: str,
        now: int,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE group_proactive_state
                   SET awaiting_reply_until = NULL, updated_at = ?
                   WHERE platform = ? AND group_id = ?
                     AND awaiting_reply_until IS NOT NULL""",
                (
                    int(now),
                    platform,
                    str(group_id),
                ),
            )

    def create_group_proactive_run(
        self,
        platform: str,
        group_id: str,
        trigger_reason: str,
        *,
        status: str = "running",
        context_chars: int = 0,
    ) -> int:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """INSERT INTO group_proactive_runs
                   (platform, group_id, trigger_reason, status,
                    context_chars, started_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    platform,
                    str(group_id),
                    " ".join(str(trigger_reason or "").split()).strip()[:300],
                    status,
                    max(0, int(context_chars)),
                    now,
                ),
            )
        return int(cursor.lastrowid)

    def update_group_proactive_run(
        self,
        run_id: int,
        *,
        status: str,
        detail: str | None = None,
        generated_text: str | None = None,
        context_chars: int | None = None,
        sent_message_id: int | None = None,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE group_proactive_runs
                   SET status = ?,
                       detail = COALESCE(?, detail),
                       generated_text = COALESCE(?, generated_text),
                       context_chars = COALESCE(?, context_chars),
                       sent_message_id = COALESCE(?, sent_message_id),
                       finished_at = ?
                   WHERE id = ?""",
                (
                    status,
                    (
                        " ".join(str(detail or "").split()).strip()[:500]
                        if detail is not None
                        else None
                    ),
                    (
                        str(generated_text or "")[:1200]
                        if generated_text is not None
                        else None
                    ),
                    (
                        max(0, int(context_chars))
                        if context_chars is not None
                        else None
                    ),
                    (
                        int(sent_message_id)
                        if sent_message_id is not None
                        else None
                    ),
                    int(time.time()),
                    int(run_id),
                ),
            )

    def mark_group_proactive_run_replied(
        self,
        run_id: int,
        reply_at: int,
        member_id: str,
        reply_text: str,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """UPDATE group_proactive_runs
                   SET status = 'replied',
                       reply_at = ?,
                       reply_member_id = ?,
                       reply_text = ?,
                       finished_at = COALESCE(finished_at, ?)
                   WHERE id = ?""",
                (
                    int(reply_at),
                    str(member_id),
                    " ".join(str(reply_text or "").split()).strip()[:500],
                    int(reply_at),
                    int(run_id),
                ),
            )

    def list_group_proactive_runs(
        self,
        platform: str,
        limit: int = 20,
        group_id: str = "",
    ) -> list[dict]:
        where = "platform = ?"
        values: list[object] = [platform]
        if group_id:
            where += " AND group_id = ?"
            values.append(str(group_id))
        values.append(max(1, min(int(limit), 100)))
        with self._connection() as conn:
            rows = conn.execute(
                f"""SELECT *
                    FROM group_proactive_runs
                    WHERE {where}
                    ORDER BY id DESC LIMIT ?""",
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_group_proactive_override(
        self,
        platform: str,
        group_id: str,
    ) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT *
                   FROM group_proactive_overrides
                   WHERE platform = ? AND group_id = ?""",
                (platform, str(group_id)),
            ).fetchone()
        return dict(row) if row else None

    def set_group_proactive_enabled(
        self,
        platform: str,
        group_id: str,
        enabled: bool,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO group_proactive_overrides
                   (platform, group_id, enabled, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(platform, group_id) DO UPDATE SET
                       enabled = excluded.enabled,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    str(group_id),
                    1 if enabled else 0,
                    int(time.time()),
                ),
            )

    def set_group_proactive_limits(
        self,
        platform: str,
        group_id: str,
        idle_trigger_minutes: int,
        max_per_day: int,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO group_proactive_overrides
                   (platform, group_id, idle_trigger_minutes, max_per_day,
                    updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(platform, group_id) DO UPDATE SET
                       idle_trigger_minutes = excluded.idle_trigger_minutes,
                       max_per_day = excluded.max_per_day,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    str(group_id),
                    int(idle_trigger_minutes),
                    int(max_per_day),
                    int(time.time()),
                ),
            )

    def group_activity_timestamps(
        self,
        platform: str,
        group_id: str,
        since: int,
    ) -> list[int]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT created_at
                   FROM group_messages
                   WHERE platform = ? AND group_id = ?
                     AND role = 'user' AND created_at >= ?
                   ORDER BY created_at, id""",
                (
                    platform,
                    str(group_id),
                    int(since),
                ),
            ).fetchall()
        return [int(row["created_at"]) for row in rows]

    def proactive_count_since(self, owner_id: str, since: int) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS n
                   FROM proactive_log
                   WHERE owner_id = ? AND sent_at >= ?""",
                (owner_id, int(since)),
            ).fetchone()
        return int(row["n"] or 0) if row else 0

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

    def get_group_reply_stats(
        self,
        platform: str,
        group_id: str,
        since: int,
    ) -> dict[str, int]:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS reply_count,
                          COALESCE(MAX(created_at), 0) AS last_reply_at
                   FROM group_messages
                   WHERE platform = ? AND group_id = ?
                     AND role = 'assistant' AND created_at >= ?""",
                (
                    platform,
                    str(group_id),
                    int(since),
                ),
            ).fetchone()
        return {
            "reply_count": int(row["reply_count"] or 0) if row else 0,
            "last_reply_at": int(row["last_reply_at"] or 0) if row else 0,
        }

    def upsert_group_jargon_candidates(
        self,
        platform: str,
        group_id: str,
        candidates: list[dict[str, Any]],
    ) -> int:
        now = int(time.time())
        saved = 0
        with self._lock, self._connection() as conn:
            for item in candidates[:20]:
                term = " ".join(str(item.get("term") or "").split()).strip()[:24]
                if len(term) < 2:
                    continue
                occurrences = max(1, int(item.get("occurrences") or 1))
                member_count = max(1, int(item.get("member_count") or 1))
                conn.execute(
                    """INSERT INTO group_jargon
                       (platform, group_id, term, status, occurrences,
                        member_count, first_seen, last_seen, created_at,
                        updated_at)
                       VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(platform, group_id, term) DO UPDATE SET
                           occurrences = MAX(
                               group_jargon.occurrences,
                               excluded.occurrences
                           ),
                           member_count = MAX(
                               group_jargon.member_count,
                               excluded.member_count
                           ),
                           last_seen = excluded.last_seen,
                           updated_at = excluded.updated_at""",
                    (
                        platform,
                        str(group_id),
                        term,
                        occurrences,
                        member_count,
                        now,
                        now,
                        now,
                        now,
                    ),
                )
                saved += 1
        return saved

    def list_group_jargon(
        self,
        *,
        include_rejected: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        where = "" if include_rejected else "WHERE status != 'rejected'"
        with self._connection() as conn:
            rows = conn.execute(
                f"""SELECT id, platform, group_id, term, meaning, example,
                           status, occurrences, member_count, first_seen,
                           last_seen, created_at, updated_at
                    FROM group_jargon
                    {where}
                    ORDER BY CASE status
                                 WHEN 'pending' THEN 0
                                 WHEN 'approved' THEN 1
                                 ELSE 2
                             END,
                             occurrences DESC, updated_at DESC
                    LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_group_jargon(
        self,
        jargon_id: int,
        *,
        status: str | None = None,
        meaning: str | None = None,
        example: str | None = None,
    ) -> dict | None:
        updates: dict[str, Any] = {}
        if status is not None:
            if status not in ("pending", "approved", "rejected"):
                raise ValueError("无效的黑话状态。")
            updates["status"] = status
        if meaning is not None:
            updates["meaning"] = " ".join(str(meaning).split()).strip()[:500]
        if example is not None:
            updates["example"] = " ".join(str(example).split()).strip()[:500]
        if not updates:
            return None
        updates["updated_at"] = int(time.time())
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                f"""UPDATE group_jargon SET {assignments} WHERE id = ?""",
                (*updates.values(), int(jargon_id)),
            )
            if cursor.rowcount <= 0:
                return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM group_jargon WHERE id = ?",
                (int(jargon_id),),
            ).fetchone()
        return dict(row) if row else None

    def delete_group_jargon(self, jargon_id: int) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM group_jargon WHERE id = ?",
                (int(jargon_id),),
            )
        return cursor.rowcount > 0

    def approved_group_jargon(
        self,
        platform: str,
        group_id: str,
        text: str,
        limit: int = 6,
    ) -> list[dict]:
        value = str(text or "")[:4000]
        if not value:
            return []
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT id, term, meaning, example, occurrences
                   FROM group_jargon
                   WHERE platform = ? AND group_id = ?
                     AND status = 'approved' AND meaning != ''
                     AND instr(?, term) > 0
                   ORDER BY LENGTH(term) DESC, occurrences DESC
                   LIMIT ?""",
                (
                    platform,
                    str(group_id),
                    value,
                    max(1, min(int(limit), 12)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

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

    def list_known_group_ids(self, platform: str = "qqbot") -> list[str]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT group_id FROM group_members WHERE platform = ?
                   UNION
                   SELECT group_id FROM group_messages WHERE platform = ?
                   UNION
                   SELECT group_id FROM group_weather_locations
                   WHERE platform = ?
                   ORDER BY group_id""",
                (platform, platform, platform),
            ).fetchall()
        return [str(row["group_id"]) for row in rows if row["group_id"]]

    def set_group_weather_city(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        city: str,
    ) -> str:
        value = re.sub(r"\s+", " ", str(city or "")).strip()[:40]
        if not value:
            raise ValueError("天气城市不能为空。")
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO group_weather_locations
                       (platform, group_id, member_id, city, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(platform, group_id, member_id) DO UPDATE SET
                       city = excluded.city,
                       updated_at = excluded.updated_at""",
                (
                    platform,
                    str(group_id),
                    str(member_id),
                    value,
                    int(time.time()),
                ),
            )
        return value

    def clear_group_weather_city(
        self,
        platform: str,
        group_id: str,
        member_id: str,
    ) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """DELETE FROM group_weather_locations
                   WHERE platform = ? AND group_id = ? AND member_id = ?""",
                (platform, str(group_id), str(member_id)),
            )
        return cursor.rowcount > 0

    def list_group_weather_cities(
        self,
        platform: str,
        group_id: str,
        limit: int = 12,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT member_id, city, updated_at
                   FROM group_weather_locations
                   WHERE platform = ? AND group_id = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (
                    platform,
                    str(group_id),
                    max(1, min(int(limit), 50)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

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

    def claim_memory_extraction(
        self,
        day: str,
        platform: str,
        owner_id: str,
        limit: int,
    ) -> bool:
        maximum = max(1, min(int(limit), 100))
        now = int(time.time())
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """SELECT attempts FROM memory_extraction_runs
                   WHERE day = ? AND platform = ? AND owner_id = ?""",
                (day, platform, str(owner_id)),
            ).fetchone()
            attempts = int(row["attempts"] or 0) if row else 0
            if attempts >= maximum:
                return False
            conn.execute(
                """INSERT INTO memory_extraction_runs
                       (day, platform, owner_id, attempts, updated_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(day, platform, owner_id) DO UPDATE SET
                       attempts = memory_extraction_runs.attempts + 1,
                       updated_at = excluded.updated_at""",
                (day, platform, str(owner_id), now),
            )
            conn.execute(
                "DELETE FROM memory_extraction_runs WHERE day < ?",
                ((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),),
            )
        return True

    def record_agent_metric(
        self,
        kind: str,
        success: bool,
        latency_ms: int = 0,
    ) -> None:
        day = datetime.now().strftime("%Y-%m-%d")
        now = int(time.time())
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO agent_call_metrics
                       (day, kind, success, call_count, total_ms, last_at)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT(day, kind, success) DO UPDATE SET
                       call_count = agent_call_metrics.call_count + 1,
                       total_ms = agent_call_metrics.total_ms + excluded.total_ms,
                       last_at = excluded.last_at""",
                (
                    day,
                    str(kind or "other")[:40],
                    1 if success else 0,
                    max(0, int(latency_ms)),
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM agent_call_metrics WHERE day < ?",
                (
                    (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                ),
            )

    def agent_metric_summary(self, days: int = 7) -> dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        since = (
            datetime.now() - timedelta(days=max(1, min(int(days), 30)) - 1)
        ).strftime("%Y-%m-%d")
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT day, kind, success, call_count, total_ms, last_at
                   FROM agent_call_metrics
                   WHERE day >= ?
                   ORDER BY day, kind, success""",
                (since,),
            ).fetchall()
        by_day: dict[str, dict[str, dict[str, int]]] = {}
        total_calls = 0
        failed_calls = 0
        for row in rows:
            day = str(row["day"])
            kind = str(row["kind"])
            count = int(row["call_count"] or 0)
            item = by_day.setdefault(day, {}).setdefault(
                kind,
                {
                    "success": 0,
                    "failure": 0,
                    "total_ms": 0,
                    "last_at": 0,
                },
            )
            item["success" if int(row["success"]) else "failure"] += count
            item["total_ms"] += int(row["total_ms"] or 0)
            item["last_at"] = max(item["last_at"], int(row["last_at"] or 0))
            total_calls += count
            if not int(row["success"]):
                failed_calls += count
        return {
            "today": by_day.get(today, {}),
            "by_day": by_day,
            "total_calls": total_calls,
            "failed_calls": failed_calls,
        }

    def prune_history(
        self,
        day: str,
        private_days: int,
        group_days: int,
        now: int | None = None,
    ) -> dict[str, int | bool]:
        current = int(now or time.time())
        with self._lock, self._connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM history_cleanup_runs WHERE day = ?",
                (day,),
            ).fetchone()
            if existing:
                return {
                    "ran": False,
                    "private_deleted": 0,
                    "group_deleted": 0,
                }
            private_deleted = 0
            group_deleted = 0
            if int(private_days) > 0:
                cursor = conn.execute(
                    "DELETE FROM messages WHERE created_at < ?",
                    (current - int(private_days) * 86400,),
                )
                private_deleted = max(0, int(cursor.rowcount))
            if int(group_days) > 0:
                cursor = conn.execute(
                    "DELETE FROM group_messages WHERE created_at < ?",
                    (current - int(group_days) * 86400,),
                )
                group_deleted = max(0, int(cursor.rowcount))
            conn.execute(
                """INSERT INTO history_cleanup_runs
                   (day, private_deleted, group_deleted, created_at)
                   VALUES (?, ?, ?, ?)""",
                (day, private_deleted, group_deleted, current),
            )
        return {
            "ran": True,
            "private_deleted": private_deleted,
            "group_deleted": group_deleted,
        }

    def set_group_quiet(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        quiet_until: int,
        reason: str = "",
    ) -> None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT INTO group_quiet_state
                       (platform, group_id, member_id, quiet_until,
                        reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(platform, group_id, member_id) DO UPDATE SET
                       quiet_until = excluded.quiet_until,
                       reason = excluded.reason,
                       created_at = excluded.created_at""",
                (
                    platform,
                    str(group_id),
                    str(member_id),
                    int(quiet_until),
                    str(reason or "")[:200],
                    now,
                ),
            )

    def clear_group_quiet(
        self,
        platform: str,
        group_id: str,
        member_id: str,
    ) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """DELETE FROM group_quiet_state
                   WHERE platform = ? AND group_id = ? AND member_id = ?""",
                (platform, str(group_id), str(member_id)),
            )
        return cursor.rowcount > 0

    def group_quiet_active(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        now: int | None = None,
    ) -> dict | None:
        current = int(now or time.time())
        with self._connection() as conn:
            row = conn.execute(
                """SELECT platform, group_id, member_id, quiet_until, reason
                   FROM group_quiet_state
                   WHERE platform = ? AND group_id = ?
                     AND member_id IN (?, '*') AND quiet_until > ?
                   ORDER BY CASE member_id WHEN '*' THEN 1 ELSE 0 END
                   LIMIT 1""",
                (
                    platform,
                    str(group_id),
                    str(member_id),
                    current,
                ),
            ).fetchone()
        return dict(row) if row else None

    def list_active_group_quiet(self, now: int | None = None) -> list[dict]:
        current = int(now or time.time())
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT platform, group_id, member_id, quiet_until, reason
                   FROM group_quiet_state
                   WHERE quiet_until > ?
                   ORDER BY quiet_until""",
                (current,),
            ).fetchall()
        return [dict(row) for row in rows]

    def diagnostic_counts(self) -> dict[str, int]:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT
                       (SELECT COUNT(*) FROM messages) AS messages,
                       (SELECT COUNT(*) FROM group_messages) AS group_messages,
                       (SELECT COUNT(*) FROM memories) AS memories,
                       (SELECT COUNT(*) FROM group_jargon) AS group_jargon,
                       (SELECT COUNT(*) FROM reminders
                        WHERE sent_at IS NULL AND cancelled_at IS NULL)
                           AS pending_reminders,
                       (SELECT COUNT(*) FROM group_proactive_state)
                           AS proactive_groups"""
            ).fetchone()
        return {
            key: int(row[key] or 0)
            for key in (
                "messages",
                "group_messages",
                "memories",
                "group_jargon",
                "pending_reminders",
                "proactive_groups",
            )
        }

    def last_history_cleanup(self) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT day, private_deleted, group_deleted, created_at
                   FROM history_cleanup_runs
                   ORDER BY day DESC LIMIT 1"""
            ).fetchone()
        return dict(row) if row else None

    def get_settings(self, platform: str, owner_id: str) -> dict:
        defaults = {
            "memory_enabled": True,
            "memory_immediate_extraction_enabled": True,
            "memory_immediate_extraction_daily_limit": 12,
            "private_history_retention_days": 90,
            "group_history_retention_days": 30,
            "proactive_enabled": True,
            "proactive_max_per_day": 2,
            "quiet_start": "23:30",
            "quiet_end": "08:00",
            "morning_time": "09:00",
            "night_time": "21:30",
            "sticker_enabled": True,
            "sticker_auto_collect_enabled": True,
            "sticker_auto_collect_library": "default",
            "chat_human_delay": True,
            "persona_preset": "冷脸萌",
            "persona_custom_prompt": "",
            "web_search_enabled": True,
            "web_search_count": 5,
            "web_domain_routing_enabled": True,
            "group_proactive_enabled": False,
            "group_weather_enabled": True,
            "group_holiday_enabled": True,
            "group_weather_city": "",
            "group_proactive_time": "08:30",
            "group_idle_proactive_enabled": False,
            "group_idle_trigger_minutes": 90,
            "group_idle_random_min_minutes": 15,
            "group_idle_random_max_minutes": 45,
            "group_idle_max_unanswered": 2,
            "group_idle_max_per_day": 1,
            "group_reply_control_enabled": True,
            "group_activity_level": "balanced",
            "group_jargon_enabled": True,
            "group_reply_max_per_10m": 6,
            "group_reply_fatigue_rounds": 3,
            "group_message_merge_seconds": 4,
            "voice_enabled": False,
            "memory_consolidation_enabled": True,
            "memory_consolidation_time": "03:30",
            "memory_decay_enabled": True,
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
                    defaults.update(
                        normalize_settings_update(defaults, saved)
                    )
            except json.JSONDecodeError:
                pass
        original_custom = str(
            defaults.get("persona_custom_prompt") or ""
        )
        normalized_custom = normalize_persona_custom_prompt(original_custom)
        if normalized_custom != original_custom:
            defaults["persona_custom_prompt"] = normalized_custom
            if row:
                try:
                    saved = json.loads(row["value_json"])
                except json.JSONDecodeError:
                    saved = None
                if isinstance(saved, dict):
                    saved["persona_custom_prompt"] = normalized_custom
                    with self._lock, self._connection() as conn:
                        conn.execute(
                            """UPDATE settings SET value_json = ?, updated_at = ?
                               WHERE platform = ? AND owner_id = ?""",
                            (
                                json.dumps(saved, ensure_ascii=False),
                                int(time.time()),
                                platform,
                                owner_id,
                            ),
                        )
        return defaults

    def get_saved_settings(self, platform: str, owner_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM settings WHERE platform = ? AND owner_id = ?",
                (platform, owner_id),
            ).fetchone()
        if not row:
            return {}
        try:
            saved = json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return saved if isinstance(saved, dict) else {}

    def save_settings(self, platform: str, owner_id: str, values: dict) -> dict:
        current = self.get_settings(platform, owner_id)
        current.update(normalize_settings_update(current, values))
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
        category: str = "未分类",
        source_name: str = "",
        caption: str = "",
        keywords: str = "",
        mood: str = "",
        library_id: str = "default",
    ) -> int:
        category = str(category or "未分类").strip()[:40] or "未分类"
        library_id = str(library_id or "default").strip()[:60] or "default"
        with self._lock, self._connection() as conn:
            library = conn.execute(
                "SELECT id FROM sticker_libraries WHERE id = ?",
                (library_id,),
            ).fetchone()
            if not library:
                library_id = "default"
            conn.execute(
                """INSERT OR IGNORE INTO sticker_categories(
                       owner_id, name, created_at
                   ) VALUES (?, ?, ?)""",
                (owner_id, category, int(time.time())),
            )
            conn.execute(
                """INSERT INTO stickers(
                       owner_id, kind, ref, library_id, category, source_name,
                       caption, keywords, mood, tags, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(owner_id, kind, ref) DO UPDATE SET
                       library_id = excluded.library_id,
                       category = excluded.category,
                       source_name = CASE
                           WHEN excluded.source_name <> ''
                           THEN excluded.source_name
                           ELSE stickers.source_name
                       END,
                       caption = CASE
                           WHEN excluded.caption <> ''
                           THEN excluded.caption
                           ELSE stickers.caption
                       END,
                       keywords = CASE
                           WHEN excluded.keywords <> ''
                           THEN excluded.keywords
                           ELSE stickers.keywords
                       END,
                       mood = CASE
                           WHEN excluded.mood <> ''
                           THEN excluded.mood
                           ELSE stickers.mood
                       END,
                       tags = excluded.tags""",
                (
                    owner_id,
                    kind,
                    ref,
                    library_id,
                    category,
                    str(source_name or "").strip()[:180],
                    str(caption or "").strip()[:200],
                    str(keywords or "").strip()[:300],
                    str(mood or "").strip()[:20],
                    tags[:300],
                    int(time.time()),
                ),
            )
            row = conn.execute(
                "SELECT id FROM stickers WHERE owner_id = ? AND kind = ? AND ref = ?",
                (owner_id, kind, ref),
            ).fetchone()
        return int(row["id"])

    def list_stickers(
        self,
        owner_id: str,
        limit: int = 100,
        library_id: str | None = None,
    ) -> list[dict]:
        sql = """SELECT id, kind, ref, library_id, category, source_name,
                        caption, keywords, mood, tags, use_count,
                        last_used_at, created_at
                 FROM stickers WHERE owner_id = ?"""
        params: list = [owner_id]
        if library_id:
            sql += " AND library_id = ?"
            params.append(str(library_id))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self._connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def list_sticker_libraries(
        self,
        include_disabled: bool = True,
    ) -> list[dict]:
        sql = """SELECT l.id, l.name, l.enabled, l.sort_order, l.created_at,
                        l.updated_at, COUNT(s.id) AS sticker_count
                 FROM sticker_libraries l
                 LEFT JOIN stickers s
                   ON s.library_id = l.id AND s.owner_id = '0'"""
        if not include_disabled:
            sql += " WHERE l.enabled = 1"
        sql += """ GROUP BY l.id, l.name, l.enabled, l.sort_order,
                          l.created_at, l.updated_at
                   ORDER BY l.sort_order, l.created_at, l.name"""
        with self._connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def create_sticker_library(self, name: str) -> dict:
        value = " ".join(str(name or "").split()).strip()[:40]
        if not value:
            raise ValueError("图库名称不能为空。")
        now = int(time.time())
        with self._lock, self._connection() as conn:
            if conn.execute(
                "SELECT 1 FROM sticker_libraries WHERE name = ?",
                (value,),
            ).fetchone():
                raise ValueError("已经存在同名图库。")
            library_id = ""
            for _attempt in range(20):
                candidate = "lib-" + secrets.token_hex(4)
                if not conn.execute(
                    "SELECT 1 FROM sticker_libraries WHERE id = ?",
                    (candidate,),
                ).fetchone():
                    library_id = candidate
                    break
            if not library_id:
                raise ValueError("图库编号生成失败，请重试。")
            sort_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next "
                "FROM sticker_libraries"
            ).fetchone()["next"]
            conn.execute(
                """INSERT INTO sticker_libraries
                       (id, name, enabled, sort_order, created_at, updated_at)
                   VALUES (?, ?, 1, ?, ?, ?)""",
                (library_id, value, int(sort_order), now, now),
            )
            row = conn.execute(
                "SELECT * FROM sticker_libraries WHERE id = ?",
                (library_id,),
            ).fetchone()
        result = dict(row)
        result["sticker_count"] = 0
        return result

    def update_sticker_library(
        self,
        library_id: str,
        *,
        name: str | None = None,
        enabled: bool | None = None,
    ) -> dict | None:
        library_id = str(library_id or "").strip()
        if not library_id:
            return None
        changes = []
        params: list = []
        if name is not None:
            value = " ".join(str(name or "").split()).strip()[:40]
            if not value:
                raise ValueError("图库名称不能为空。")
            changes.append("name = ?")
            params.append(value)
        if enabled is not None:
            changes.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not changes:
            return None
        changes.append("updated_at = ?")
        params.append(int(time.time()))
        params.append(library_id)
        try:
            with self._lock, self._connection() as conn:
                cursor = conn.execute(
                    f"""UPDATE sticker_libraries SET {", ".join(changes)}
                        WHERE id = ?""",
                    tuple(params),
                )
                if not cursor.rowcount:
                    return None
                row = conn.execute(
                    """SELECT l.id, l.name, l.enabled, l.sort_order,
                              l.created_at, l.updated_at,
                              COUNT(s.id) AS sticker_count
                       FROM sticker_libraries l
                       LEFT JOIN stickers s
                         ON s.library_id = l.id AND s.owner_id = '0'
                       WHERE l.id = ?
                       GROUP BY l.id""",
                    (library_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("已经存在同名图库。") from exc
        return dict(row) if row else None

    def move_stickers_to_library(
        self,
        owner_id: str,
        sticker_ids: list[int],
        library_id: str,
    ) -> int:
        library_id = str(library_id or "").strip()
        unique_ids = []
        for sticker_id in sticker_ids[:200]:
            try:
                value = int(sticker_id)
            except (TypeError, ValueError):
                continue
            if value not in unique_ids:
                unique_ids.append(value)
        if not unique_ids or not library_id:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        with self._lock, self._connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sticker_libraries WHERE id = ?",
                (library_id,),
            ).fetchone():
                return 0
            cursor = conn.execute(
                f"""UPDATE stickers SET library_id = ?
                    WHERE owner_id = ? AND id IN ({placeholders})""",
                (library_id, owner_id, *unique_ids),
            )
        return int(cursor.rowcount or 0)

    def list_sticker_rules(self) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT scope_type, scope_key, library_ids, updated_at
                   FROM sticker_selection_rules
                   ORDER BY scope_type, scope_key"""
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                value = json.loads(str(item.get("library_ids") or "[]"))
            except json.JSONDecodeError:
                value = []
            item["library_ids"] = [
                str(library_id)
                for library_id in (value if isinstance(value, list) else [])
                if str(library_id).strip()
            ]
            result.append(item)
        return result

    def set_sticker_rule(
        self,
        scope_type: str,
        scope_key: str,
        library_ids: list[str],
    ) -> list[str]:
        if scope_type not in ("default", "group", "persona"):
            raise ValueError("不支持的选图规则范围。")
        normalized_key = (
            ""
            if scope_type == "default"
            else " ".join(str(scope_key or "").split()).strip()[:200]
        )
        if scope_type != "default" and not normalized_key:
            raise ValueError("请选择规则对象。")
        with self._lock, self._connection() as conn:
            available = {
                str(row["id"])
                for row in conn.execute(
                    "SELECT id FROM sticker_libraries"
                ).fetchall()
            }
            selected = []
            for value in library_ids[:50]:
                library_id = str(value or "").strip()
                if (
                    library_id in available
                    and library_id not in selected
                ):
                    selected.append(library_id)
            if not selected:
                conn.execute(
                    """DELETE FROM sticker_selection_rules
                       WHERE scope_type = ? AND scope_key = ?""",
                    (scope_type, normalized_key),
                )
                return []
            conn.execute(
                """INSERT INTO sticker_selection_rules
                       (scope_type, scope_key, library_ids, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(scope_type, scope_key) DO UPDATE SET
                       library_ids = excluded.library_ids,
                       updated_at = excluded.updated_at""",
                (
                    scope_type,
                    normalized_key,
                    json.dumps(selected, ensure_ascii=False),
                    int(time.time()),
                ),
            )
        return selected

    def resolve_sticker_library_ids(
        self,
        platform: str,
        chat_type: str,
        chat_id: str,
        persona_preset: str,
    ) -> list[str]:
        with self._connection() as conn:
            enabled = [
                str(row["id"])
                for row in conn.execute(
                    """SELECT id FROM sticker_libraries
                       WHERE enabled = 1
                       ORDER BY sort_order, created_at, name"""
                ).fetchall()
            ]
            enabled_set = set(enabled)
            rows = conn.execute(
                """SELECT scope_type, scope_key, library_ids
                   FROM sticker_selection_rules"""
            ).fetchall()
        rules = {}
        for row in rows:
            try:
                value = json.loads(str(row["library_ids"] or "[]"))
            except json.JSONDecodeError:
                value = []
            rules[(str(row["scope_type"]), str(row["scope_key"]))] = [
                str(library_id)
                for library_id in (value if isinstance(value, list) else [])
                if str(library_id) in enabled_set
            ]
        candidates = []
        if str(chat_type or "") == "group" and chat_id:
            candidates.append(
                ("group", f"{platform}:{chat_id}")
            )
        persona = " ".join(str(persona_preset or "").split()).strip()[:200]
        if persona:
            candidates.append(("persona", persona))
        candidates.append(("default", ""))
        for key in candidates:
            selected = rules.get(key) or []
            if selected:
                return selected
        return enabled

    def add_sticker_candidate(
        self,
        owner_id: str,
        ref: str,
        library_id: str,
        source_name: str = "",
        platform: str = "",
        chat_id: str = "",
        sender_id: str = "",
    ) -> int | None:
        ref = Path(str(ref or "")).name
        if not ref:
            return None
        library_id = str(library_id or "default").strip()[:60] or "default"
        with self._lock, self._connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sticker_libraries WHERE id = ?",
                (library_id,),
            ).fetchone():
                library_id = "default"
            if conn.execute(
                """SELECT 1 FROM stickers
                   WHERE owner_id = ? AND kind = 'image' AND ref = ?""",
                (owner_id, ref),
            ).fetchone():
                return None
            cursor = conn.execute(
                """INSERT OR IGNORE INTO sticker_candidates
                       (owner_id, library_id, ref, source_name, platform,
                        chat_id, sender_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    owner_id,
                    library_id,
                    ref,
                    Path(str(source_name or "")).name[:180],
                    str(platform or "")[:30],
                    str(chat_id or "")[:200],
                    str(sender_id or "")[:200],
                    int(time.time()),
                ),
            )
            if not cursor.rowcount:
                return None
            candidate_id = int(cursor.lastrowid)
        return candidate_id

    def list_sticker_candidates(
        self,
        owner_id: str = "0",
        limit: int = 100,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT c.id, c.owner_id, c.library_id, c.ref,
                          c.source_name, c.platform, c.chat_id,
                          c.sender_id, c.created_at,
                          COALESCE(l.name, c.library_id) AS library_name
                   FROM sticker_candidates c
                   LEFT JOIN sticker_libraries l ON l.id = c.library_id
                   WHERE c.owner_id = ?
                   ORDER BY c.id DESC LIMIT ?""",
                (
                    owner_id,
                    max(1, min(int(limit), 200)),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_sticker_candidate(self, candidate_id: int) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT id, owner_id, library_id, ref, source_name,
                          platform, chat_id, sender_id, created_at
                   FROM sticker_candidates WHERE id = ?""",
                (int(candidate_id),),
            ).fetchone()
        return dict(row) if row else None

    def delete_sticker_candidate(self, candidate_id: int) -> dict | None:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """SELECT id, owner_id, library_id, ref, source_name,
                          platform, chat_id, sender_id, created_at
                   FROM sticker_candidates WHERE id = ?""",
                (int(candidate_id),),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "DELETE FROM sticker_candidates WHERE id = ?",
                (int(candidate_id),),
            )
        return dict(row)

    def list_sticker_categories(self, owner_id: str) -> list[str]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT name FROM sticker_categories
                   WHERE owner_id = ? ORDER BY created_at, name""",
                (owner_id,),
            ).fetchall()
        categories = ["未分类"]
        for row in rows:
            name = str(row["name"] or "").strip()
            if name and name not in categories:
                categories.append(name)
        return categories

    def ensure_sticker_category(self, owner_id: str, name: str) -> str:
        category = str(name or "未分类").strip()[:40] or "未分类"
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO sticker_categories(
                       owner_id, name, created_at
                   ) VALUES (?, ?, ?)""",
                (owner_id, category, int(time.time())),
            )
        return category

    def move_stickers(
        self,
        owner_id: str,
        sticker_ids: list[int],
        category: str,
    ) -> int:
        category = str(category or "未分类").strip()[:40] or "未分类"
        unique_ids = []
        for sticker_id in sticker_ids[:200]:
            try:
                value = int(sticker_id)
            except (TypeError, ValueError):
                continue
            if value not in unique_ids:
                unique_ids.append(value)
        if not unique_ids:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        with self._lock, self._connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO sticker_categories(
                       owner_id, name, created_at
                   ) VALUES (?, ?, ?)""",
                (owner_id, category, int(time.time())),
            )
            cursor = conn.execute(
                f"""UPDATE stickers SET category = ?
                    WHERE owner_id = ? AND id IN ({placeholders})""",
                (category, owner_id, *unique_ids),
            )
        return int(cursor.rowcount or 0)

    def update_stickers_metadata(
        self,
        owner_id: str,
        sticker_ids: list[int],
        values: dict,
    ) -> int:
        unique_ids = []
        for sticker_id in sticker_ids[:200]:
            try:
                value = int(sticker_id)
            except (TypeError, ValueError):
                continue
            if value not in unique_ids:
                unique_ids.append(value)
        if not unique_ids:
            return 0
        allowed = {"category", "caption", "keywords", "mood", "tags"}
        updates = {}
        for key in allowed:
            if key not in values or values[key] is None:
                continue
            limit = 40 if key == "category" else 300
            if key == "caption":
                limit = 200
            elif key == "mood":
                limit = 20
            value = " ".join(str(values[key] or "").split()).strip()[:limit]
            if key == "category" and not value:
                value = "未分类"
            updates[key] = value
        if not updates:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._lock, self._connection() as conn:
            if "category" in updates:
                conn.execute(
                    """INSERT OR IGNORE INTO sticker_categories(
                           owner_id, name, created_at
                       ) VALUES (?, ?, ?)""",
                    (owner_id, updates["category"], int(time.time())),
                )
            cursor = conn.execute(
                f"""UPDATE stickers SET {assignments}
                    WHERE owner_id = ? AND id IN ({placeholders})""",
                (*updates.values(), owner_id, *unique_ids),
            )
        return int(cursor.rowcount or 0)

    def record_sticker_use(
        self,
        owner_id: str,
        sticker_id: int,
        platform: str,
        chat_id: str,
        query: str,
        matched_by: str = "",
    ) -> bool:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """UPDATE stickers
                   SET use_count = use_count + 1, last_used_at = ?
                   WHERE id = ? AND owner_id = ?""",
                (now, int(sticker_id), owner_id),
            )
            if not cursor.rowcount:
                return False
            conn.execute(
                """INSERT INTO sticker_usage
                   (owner_id, sticker_id, platform, chat_id, query,
                    matched_by, used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    owner_id,
                    int(sticker_id),
                    str(platform or ""),
                    str(chat_id or ""),
                    " ".join(str(query or "").split()).strip()[:300],
                    str(matched_by or "")[:80],
                    now,
                ),
            )
        return True

    def recent_sticker_ids(
        self,
        owner_id: str,
        platform: str,
        chat_id: str,
        since: int,
        limit: int = 10,
    ) -> list[int]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT sticker_id
                   FROM sticker_usage
                   WHERE owner_id = ? AND platform = ? AND chat_id = ?
                     AND used_at >= ?
                   ORDER BY used_at DESC, id DESC
                   LIMIT ?""",
                (
                    owner_id,
                    str(platform or ""),
                    str(chat_id or ""),
                    int(since),
                    max(1, min(int(limit), 100)),
                ),
            ).fetchall()
        ids = []
        for row in rows:
            sticker_id = int(row["sticker_id"])
            if sticker_id not in ids:
                ids.append(sticker_id)
        return ids

    def sticker_usage_summary(
        self,
        owner_id: str,
        limit: int = 20,
    ) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT s.id, s.source_name, s.category, s.mood,
                          s.use_count, s.last_used_at
                   FROM stickers s
                   WHERE s.owner_id = ?
                   ORDER BY s.use_count DESC, s.last_used_at DESC,
                            s.id DESC
                   LIMIT ?""",
                (owner_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_shared_location(
        self,
        platform: str,
        group_id: str,
        member_id: str,
        location: dict,
        ttl_seconds: int = 600,
    ) -> None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM shared_locations WHERE expires_at < ?", (now,))
            conn.execute(
                """INSERT INTO shared_locations
                       (platform, group_id, member_id, data_json, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(platform, group_id, member_id) DO UPDATE SET
                       data_json = excluded.data_json,
                       created_at = excluded.created_at,
                       expires_at = excluded.expires_at""",
                (
                    platform,
                    group_id,
                    member_id,
                    json.dumps(location, ensure_ascii=False),
                    now,
                    now + max(60, min(int(ttl_seconds), 3600)),
                ),
            )

    def get_shared_location(
        self,
        platform: str,
        group_id: str,
        member_id: str,
    ) -> dict | None:
        now = int(time.time())
        with self._connection() as conn:
            row = conn.execute(
                """SELECT data_json FROM shared_locations
                   WHERE platform = ? AND group_id = ? AND member_id = ?
                     AND expires_at >= ?""",
                (platform, group_id, member_id, now),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["data_json"])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def consume_shared_location(
        self,
        platform: str,
        group_id: str,
        member_id: str,
    ) -> dict | None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """SELECT data_json FROM shared_locations
                   WHERE platform = ? AND group_id = ? AND member_id = ?
                     AND expires_at >= ?""",
                (platform, group_id, member_id, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """DELETE FROM shared_locations
                   WHERE platform = ? AND group_id = ? AND member_id = ?""",
                (platform, group_id, member_id),
            )
        try:
            data = json.loads(row["data_json"])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

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
                   WHERE sent_at IS NULL AND cancelled_at IS NULL
                     AND failed_at IS NULL AND due_at <= ?
                   ORDER BY due_at, id LIMIT ?""",
                (int(now), max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def expire_stale_reminders(
        self,
        now: int,
        max_age_seconds: int,
        reason: str,
    ) -> list[dict]:
        cutoff = int(now) - max(60, int(max_age_seconds))
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """SELECT * FROM reminders
                   WHERE sent_at IS NULL AND cancelled_at IS NULL
                     AND failed_at IS NULL AND due_at <= ?
                   ORDER BY due_at, id""",
                (cutoff,),
            ).fetchall()
            if rows:
                conn.execute(
                    """UPDATE reminders
                       SET failed_at = ?, last_error = ?
                       WHERE sent_at IS NULL AND cancelled_at IS NULL
                         AND failed_at IS NULL AND due_at <= ?""",
                    (int(now), str(reason or "")[:1000], cutoff),
                )
        return [dict(row) for row in rows]

    def mark_reminder_sent(self, reminder_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE reminders SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
                (int(time.time()), int(reminder_id)),
            )

    def record_reminder_failure(
        self,
        reminder_id: int,
        error: str,
        max_attempts: int = 5,
    ) -> dict | None:
        now = int(time.time())
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """SELECT attempt_count FROM reminders
                   WHERE id = ? AND sent_at IS NULL AND cancelled_at IS NULL""",
                (int(reminder_id),),
            ).fetchone()
            if not row:
                return None
            attempts = int(row["attempt_count"] or 0) + 1
            failed_at = (
                now if attempts >= max(1, int(max_attempts)) else None
            )
            conn.execute(
                """UPDATE reminders
                   SET attempt_count = ?, last_attempt_at = ?,
                       last_error = ?, failed_at = ?
                   WHERE id = ?""",
                (
                    attempts,
                    now,
                    str(error or "")[:1000],
                    failed_at,
                    int(reminder_id),
                ),
            )
        return {
            "attempt_count": attempts,
            "last_attempt_at": now,
            "failed_at": failed_at,
        }

    def list_reminders(self, platform: str, owner_id: str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT id, text, due_at, chat_type FROM reminders
                   WHERE platform = ? AND owner_id = ?
                     AND sent_at IS NULL AND cancelled_at IS NULL
                     AND failed_at IS NULL
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
