import base64
import concurrent.futures
import configparser
import csv
import gzip
import hashlib
from html import escape as html_escape
from html.parser import HTMLParser
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "inventory.db"
HOST = os.environ.get("INVENTORY_HOST", "0.0.0.0")
PORT = int(os.environ.get("INVENTORY_PORT", "8000"))
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
BOM_REPORT_DIR = DATA_DIR / "bom_reports"
BOM_WATCH_STATE_PATH = DATA_DIR / "bom_watch_state.json"
PART_IMAGE_DIR = DATA_DIR / "part_images"
BOOKMARK_FAVICON_DIR = DATA_DIR / "bookmark_favicons"
NOTE_IMAGE_DIR = DATA_DIR / "note_images"
WORKBENCH_DIR = DATA_DIR / "workbench"
NOTE_CONTENT_MAX_CHARS = 2_000_000
NOTE_IMAGE_MAX_BYTES = 20 * 1024 * 1024
NOTE_IMPORT_MAX_BYTES = 20 * 1024 * 1024
NOTE_IMPORT_FORMATS = {
    "doc": "Word",
    "docx": "Word",
    "pdf": "PDF",
}
WORKBENCH_FILE_MAX_BYTES = 30 * 1024 * 1024
MAX_REQUEST_BYTES = 40 * 1024 * 1024
AUTH_PATH = DATA_DIR / "auth.json"
AUTH_COOKIE = "errorjiang_session"
AUTH_SESSION_DAYS = 7
AUTH_SESSION_DAYS_REMEMBER = 30
AUTH_PBKDF2_ITERATIONS = 200_000
AUTH_STATE = {"enabled": False, "password_hash": "", "secret": ""}
PUBLIC_PAGES = {
    "/",
    "/index.html",
    "/login",
    "/register",
    "/messages",
    "/moments",
    "/references",
    "/games",
    "/prompts",
    "/favicon.ico",
}
PUBLIC_GET_APIS = {
    "/api/health",
    "/api/auth/status",
    "/api/site/messages",
    "/api/moments",
    "/api/site/photos",
    "/api/site/music",
    "/api/site/links",
    "/api/prompts",
}
PUBLIC_POST_APIS = {
    "/api/login",
    "/api/register",
    "/api/logout",
    "/api/site/messages",
}
PUBLIC_DATA_PREFIXES = (
    "site_message_files/",
    "moment_images/",
    "site_photos/",
    "site_music_files/",
)
USERNAME_RE = re.compile(r"^[\w.-]{3,32}$", re.UNICODE)
RESERVED_USERNAMES = {"owner", "admin", "administrator", "root", "system"}
MEMBER_PAGE_PATHS = {"/inventory", "/bookmarks"}
MEMBER_GET_APIS = {
    "/api/dashboard",
    "/api/categories",
    "/api/locations",
    "/api/projects",
    "/api/parts",
    "/api/inventory",
    "/api/movements",
    "/api/wishlist",
    "/api/warehouse/types",
    "/api/bom/reports",
    "/api/bom/watch",
    "/api/bookmarks",
    "/api/bookmark-folders",
    "/api/bookmarks/check-links",
}
MEMBER_GET_PREFIXES = (
    "/api/parts/",
    "/api/bom/reports/",
    "/api/bookmarks/",
)
MEMBER_DATA_PREFIXES = (
    "part_images/",
    "bookmark_favicons/",
)
LOGIN_FAILURES = {}
RATE_LIMITS = {}
RATE_LOCK = threading.Lock()
TRUST_PROXY = os.environ.get("INVENTORY_TRUST_PROXY", "") not in ("", "0", "false")
FORCE_SECURE_COOKIES = os.environ.get("INVENTORY_SECURE_COOKIES", "") not in ("", "0", "false")
ACCESS_LOG = os.environ.get("INVENTORY_ACCESS_LOG", "") not in ("", "0", "false")
MESSAGE_FILE_MAX_BYTES = 5 * 1024 * 1024
MESSAGE_FILE_TOTAL_MAX_BYTES = 15 * 1024 * 1024
MESSAGE_FILE_MAX_COUNT = 3
MOMENT_CONTENT_MAX_CHARS = 2000
MOMENT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
MOMENT_IMAGE_TOTAL_MAX_BYTES = 15 * 1024 * 1024
MOMENT_IMAGE_MAX_COUNT = 9
MESSAGE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MESSAGE_FILE_EXTENSIONS = MESSAGE_IMAGE_EXTENSIONS | {
    ".7z",
    ".bin",
    ".csv",
    ".doc",
    ".docx",
    ".elf",
    ".gz",
    ".hex",
    ".json",
    ".log",
    ".md",
    ".pdf",
    ".rar",
    ".tar",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}
WORKBENCH_CATEGORIES = {"source", "firmware", "document", "image", "other"}
WORKBENCH_REPAIR_STATUSES = {"open", "repairing", "completed", "cancelled"}
WORKBENCH_EXTENSIONS = {
    ".7z",
    ".bin",
    ".brd",
    ".csv",
    ".elf",
    ".gif",
    ".gz",
    ".hex",
    ".jpeg",
    ".jpg",
    ".json",
    ".kicad_pcb",
    ".kicad_sch",
    ".md",
    ".pdf",
    ".pcb",
    ".png",
    ".rar",
    ".sch",
    ".tar",
    ".tgz",
    ".txt",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}
NOTE_IMAGE_PATH_RE = re.compile(r"/site-files/(note_images/[A-Za-z0-9._%+-]+)")
NOTE_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)
NOTE_IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}
BOOKMARK_CHECK_LOCK = threading.Lock()
BOOKMARK_FAVICON_SEMAPHORE = threading.BoundedSemaphore(4)
BOOKMARK_FAVICON_LOCKS = {}
BOOKMARK_FAVICON_LOCKS_GUARD = threading.Lock()
BOOKMARK_CHECK_STATE = {
    "running": False,
    "total": 0,
    "completed": 0,
    "valid": 0,
    "broken": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return date.today().isoformat()


def get_conn():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def query(sql, params=()):
    conn = get_conn()
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def query_one(sql, params=()):
    conn = get_conn()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def transaction(fn):
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        result = fn(conn)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def local_ips():
    ips = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    BOOKMARK_FAVICON_DIR.mkdir(exist_ok=True)
    NOTE_IMAGE_DIR.mkdir(exist_ok=True)
    WORKBENCH_DIR.mkdir(exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_number TEXT NOT NULL,
                lcsc_code TEXT UNIQUE,
                brand TEXT,
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                package TEXT,
                temperature_range TEXT,
                voltage_rating TEXT,
                description TEXT,
                datasheet_url TEXT,
                notes TEXT,
                min_stock REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT,
                parent_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS part_projects (
                part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (part_id, project_id)
            );

            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
                quantity REAL NOT NULL DEFAULT 0,
                received_quantity REAL NOT NULL DEFAULT 0,
                purchase_date TEXT,
                unit_price REAL,
                channel TEXT,
                order_number TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                movement_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                before_quantity REAL NOT NULL DEFAULT 0,
                after_quantity REAL NOT NULL DEFAULT 0,
                unit_price REAL,
                channel TEXT,
                order_number TEXT,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wishlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER REFERENCES parts(id) ON DELETE SET NULL,
                lcsc_code TEXT,
                brand TEXT,
                part_number TEXT,
                package TEXT,
                description TEXT,
                target_quantity REAL NOT NULL DEFAULT 1,
                unit_price REAL,
                priority TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL DEFAULT 'open',
                notes TEXT,
                created_at TEXT NOT NULL,
                purchased_at TEXT
            );

            CREATE TABLE IF NOT EXISTS warehouse_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT NOT NULL,
                content TEXT NOT NULL,
                parent_id INTEGER REFERENCES site_messages(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_message_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL REFERENCES site_messages(id) ON DELETE CASCADE,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                mime_type TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS moments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS moment_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moment_id INTEGER NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                mime_type TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                album TEXT,
                image_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_music (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist TEXT,
                source_type TEXT NOT NULL DEFAULT 'url',
                source_id TEXT,
                cover_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                category TEXT,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL DEFAULT '未分类',
                prompt TEXT NOT NULL,
                tags TEXT,
                pinned INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS learning_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS note_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER REFERENCES learning_notes(id) ON DELETE SET NULL,
                file_path TEXT NOT NULL,
                original_name TEXT,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS repair_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                device_name TEXT NOT NULL,
                serial_number TEXT,
                fault TEXT,
                diagnosis TEXT,
                action TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                cost REAL,
                started_at TEXT,
                finished_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workbench_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                repair_id INTEGER REFERENCES repair_records(id) ON DELETE SET NULL,
                category TEXT NOT NULL DEFAULT 'document',
                title TEXT NOT NULL,
                file_path TEXT NOT NULL,
                original_name TEXT,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT,
                version TEXT,
                target_chip TEXT,
                target_board TEXT,
                flash_url TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookmark_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER REFERENCES bookmark_folders(id) ON DELETE SET NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                source_key TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER REFERENCES bookmark_folders(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                source_key TEXT,
                link_status TEXT NOT NULL DEFAULT 'unknown',
                link_status_code INTEGER,
                link_checked_at TEXT,
                link_error TEXT,
                favicon_path TEXT,
                favicon_source_url TEXT,
                favicon_updated_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookmark_import_folders (
                source_key TEXT PRIMARY KEY,
                profile TEXT,
                name TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookmark_import_seen (
                source_key TEXT PRIMARY KEY,
                profile TEXT,
                url TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category_id);
            CREATE INDEX IF NOT EXISTS idx_parts_lcsc ON parts(lcsc_code);
            CREATE INDEX IF NOT EXISTS idx_batches_part ON batches(part_id);
            CREATE INDEX IF NOT EXISTS idx_batches_location ON batches(location_id);
            CREATE INDEX IF NOT EXISTS idx_movements_part ON movements(part_id);
            CREATE INDEX IF NOT EXISTS idx_movements_project ON movements(project_id);
CREATE INDEX IF NOT EXISTS idx_site_messages_parent ON site_messages(parent_id);
CREATE INDEX IF NOT EXISTS idx_site_message_files_message ON site_message_files(message_id);
CREATE INDEX IF NOT EXISTS idx_moments_created ON moments(created_at);
CREATE INDEX IF NOT EXISTS idx_moment_files_moment ON moment_files(moment_id);
            CREATE INDEX IF NOT EXISTS idx_site_photos_album ON site_photos(album);
            CREATE INDEX IF NOT EXISTS idx_site_links_category ON site_links(category);
            CREATE INDEX IF NOT EXISTS idx_ai_prompts_category ON ai_prompts(category);
            CREATE INDEX IF NOT EXISTS idx_ai_prompts_order ON ai_prompts(pinned, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
            CREATE INDEX IF NOT EXISTS idx_learning_notes_updated ON learning_notes(updated_at);
            CREATE INDEX IF NOT EXISTS idx_note_images_note ON note_images(note_id);
            CREATE INDEX IF NOT EXISTS idx_repair_records_project ON repair_records(project_id);
            CREATE INDEX IF NOT EXISTS idx_repair_records_status ON repair_records(status);
            CREATE INDEX IF NOT EXISTS idx_workbench_assets_project ON workbench_assets(project_id);
            CREATE INDEX IF NOT EXISTS idx_workbench_assets_repair ON workbench_assets(repair_id);
            CREATE INDEX IF NOT EXISTS idx_workbench_assets_category ON workbench_assets(category);
            CREATE INDEX IF NOT EXISTS idx_workbench_assets_created ON workbench_assets(created_at);
            CREATE INDEX IF NOT EXISTS idx_bookmark_folders_parent ON bookmark_folders(parent_id);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_folder ON bookmarks(folder_id);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON bookmarks(created_at);
            """
        )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(parts)").fetchall()]
        if "image_path" not in columns:
            conn.execute("ALTER TABLE parts ADD COLUMN image_path TEXT")
        if "warehouse_type_id" not in columns:
            conn.execute("ALTER TABLE parts ADD COLUMN warehouse_type_id INTEGER")
        folder_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(bookmark_folders)").fetchall()
        ]
        if "source_key" not in folder_columns:
            conn.execute("ALTER TABLE bookmark_folders ADD COLUMN source_key TEXT")
        bookmark_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(bookmarks)").fetchall()
        ]
        bookmark_migrations = {
            "source_key": "TEXT",
            "link_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "link_status_code": "INTEGER",
            "link_checked_at": "TEXT",
            "link_error": "TEXT",
            "favicon_path": "TEXT",
            "favicon_source_url": "TEXT",
            "favicon_updated_at": "TEXT",
        }
        for column, definition in bookmark_migrations.items():
            if column not in bookmark_columns:
                conn.execute(f"ALTER TABLE bookmarks ADD COLUMN {column} {definition}")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmark_folders_source
            ON bookmark_folders(source_key)
            WHERE source_key IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_source
            ON bookmarks(source_key)
            WHERE source_key IS NOT NULL
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_link_status ON bookmarks(link_status)"
        )
        import_timestamp = now_text()
        conn.execute(
            """
            INSERT OR IGNORE INTO bookmark_import_folders
                (source_key, profile, name, first_seen_at, last_seen_at)
            SELECT source_key, 'firefox', name, ?, ?
            FROM bookmark_folders
            WHERE source_key LIKE 'firefox:%'
            """,
            (import_timestamp, import_timestamp),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO bookmark_import_seen
                (source_key, profile, url, first_seen_at, last_seen_at)
            SELECT source_key, 'firefox', url,
                   COALESCE(created_at, ?), COALESCE(updated_at, ?)
            FROM bookmarks
            WHERE source_key LIKE 'firefox:%'
            """,
            (import_timestamp, import_timestamp),
        )
        seed_data(conn)
        conn.commit()
    finally:
        conn.close()


def seed_data(conn):
    count = conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
    if count == 0:
        categories = [
            "电阻 Resistor",
            "电容 Capacitor",
            "IC",
            "PCB",
            "OLED 显示模块",
            "电感 Inductor",
            "二极管 Diode",
            "晶体管 Transistor",
            "连接器 Connector",
            "电源模块 Power Module",
            "传感器 Sensor",
            "其他 Other",
        ]
        for i, name in enumerate(categories):
            conn.execute(
                "INSERT INTO categories (name, sort_order, created_at) VALUES (?, ?, ?)",
                (name, i, now_text()),
            )

    count = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
    if count == 0:
        ts = now_text()
        xp_id = conn.execute(
            "INSERT INTO locations (code, name, sort_order, created_at) VALUES (?, ?, 0, ?)",
            ("XP", "XP 柜", ts),
        ).lastrowid
        xa_id = conn.execute(
            "INSERT INTO locations (code, name, sort_order, created_at) VALUES (?, ?, 1, ?)",
            ("XA", "XA 柜", ts),
        ).lastrowid
        for i, code in enumerate([chr(ord("A") + i) for i in range(26)]):
            conn.execute(
                "INSERT INTO locations (code, name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
                (code, f"XP-{code}", xp_id, i, ts),
            )
            conn.execute(
                "INSERT INTO locations (code, name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
                (code, f"XA-{code}", xa_id, i, ts),
            )

    count = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
    if count == 0:
        conn.execute(
            "INSERT INTO projects (name, description, status, created_at) VALUES (?, ?, 'active', ?)",
            ("默认项目", "未指定项目的出库记录可归入这里。", now_text()),
        )

    count = conn.execute("SELECT COUNT(*) AS n FROM warehouse_types").fetchone()["n"]
    if count == 0:
        conn.execute(
            "INSERT INTO warehouse_types (name, description, sort_order, created_at) VALUES (?, ?, 0, ?)",
            ("电子元件", "电阻、电容、IC、PCB 等电子元器件。", now_text()),
        )

    seeded = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'ai_prompts_seeded'"
    ).fetchone()
    if not seeded:
        count = conn.execute("SELECT COUNT(*) AS n FROM ai_prompts").fetchone()["n"]
        if count == 0:
            seed_path = STATIC_DIR / "prompts-seed.json"
            try:
                default_prompts = json.loads(seed_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                default_prompts = []
            stamp = now_text()
            for index, item in enumerate(default_prompts):
                conn.execute(
                    """
                    INSERT INTO ai_prompts
                        (title, description, category, prompt, tags,
                         pinned, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        str(item.get("title") or "未命名提示词")[:120],
                        str(item.get("description") or "")[:300],
                        str(item.get("category") or "未分类")[:40],
                        str(item.get("prompt") or ""),
                        str(item.get("tags") or "")[:200],
                        index,
                        stamp,
                        stamp,
                    ),
                )
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES ('ai_prompts_seeded', ?)",
            (now_text(),),
        )


def path_text(table, row_id, code_field="name"):
    if not row_id:
        return ""
    rows = query(f"SELECT id, parent_id, {code_field} AS code FROM {table}")
    by_id = {row["id"]: row for row in rows}
    chain = []
    seen = set()
    current = by_id.get(row_id)
    while current and current["id"] not in seen:
        seen.add(current["id"])
        chain.append(current["code"])
        current = by_id.get(current["parent_id"])
    return "/".join(reversed(chain))


def normalize_bookmark_url(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("网址不能为空。")
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text):
        text = "https://" + text
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValueError("网址必须是以 http:// 或 https:// 开头的有效地址。")
    hostname = parsed.hostname or ""
    if not hostname or re.search(r"[\s/?#@]", hostname):
        raise ValueError("网址中的域名格式不正确。")
    return text[:1000]


def bookmark_folder_path_map():
    rows = query("SELECT id, name, parent_id FROM bookmark_folders")
    by_id = {row["id"]: row for row in rows}
    paths = {}
    for row in rows:
        chain = []
        seen = set()
        current = row
        while current and current["id"] not in seen:
            seen.add(current["id"])
            chain.append(current["name"])
            current = by_id.get(current["parent_id"])
        paths[row["id"]] = "/".join(reversed(chain))
    return paths


def bookmark_folder_cycle(parent_id, item_id):
    current_id = parent_id
    seen = set()
    while current_id and current_id not in seen:
        if current_id == item_id:
            return True
        seen.add(current_id)
        row = query_one("SELECT parent_id FROM bookmark_folders WHERE id = ?", (current_id,))
        current_id = row["parent_id"] if row else None
    return False


def firefox_profiles():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    firefox_root = Path(appdata) / "Mozilla" / "Firefox"
    ini_path = firefox_root / "profiles.ini"
    if not ini_path.is_file():
        return []

    parser = configparser.ConfigParser()
    try:
        parser.read(ini_path, encoding="utf-8")
    except (OSError, configparser.Error):
        return []

    default_paths = set()
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            default_paths.add(parser.get(section, "Default").strip().replace("\\", "/"))

    profiles = []
    seen_paths = set()
    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        path_value = parser.get(section, "Path", fallback="").strip()
        if not path_value:
            continue
        profile_path = Path(path_value)
        if parser.getboolean(section, "IsRelative", fallback=True):
            profile_path = firefox_root / profile_path
        if not profile_path.is_absolute():
            profile_path = profile_path.resolve()
        key = str(profile_path).replace("\\", "/").lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        places_path = profile_path / "places.sqlite"
        is_default = (
            parser.getboolean(section, "Default", fallback=False)
            or any(key.endswith(value.lower()) for value in default_paths)
        )
        profiles.append(
            {
                "id": section,
                "name": parser.get(section, "Name", fallback=section),
                "path": str(profile_path),
                "places_path": str(places_path),
                "available": places_path.is_file(),
                "default": is_default,
            }
        )

    profiles.sort(key=lambda item: (not item["default"], not item["available"], item["name"].lower()))
    return profiles


def select_firefox_profile(profile_key=None):
    profiles = firefox_profiles()
    if not profiles:
        raise ValueError("没有找到 Firefox 配置文件。")
    if profile_key:
        needle = str(profile_key).replace("\\", "/").lower()
        for profile in profiles:
            candidates = (
                str(profile["id"]).lower(),
                str(profile["name"]).lower(),
                str(profile["path"]).replace("\\", "/").lower(),
            )
            if needle == candidates[0] or needle == candidates[1] or needle == candidates[2]:
                if not profile["available"]:
                    raise ValueError("选择的 Firefox 配置中没有 places.sqlite。")
                return profile
        raise ValueError("选择的 Firefox 配置不存在。")
    for profile in profiles:
        if profile["default"] and profile["available"]:
            return profile
    for profile in profiles:
        if profile["available"]:
            return profile
    raise ValueError("Firefox 配置中找不到可读取的 places.sqlite。")


class FaviconLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []
        self.manifest = ""
        self.base_href = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "base" and not self.base_href:
            self.base_href = values.get("href", "").strip()
            return
        if tag != "link":
            return
        rel = values.get("rel", "").lower()
        href = values.get("href", "").strip()
        if not href:
            return
        rel_parts = set(rel.split())
        if "manifest" in rel_parts and not self.manifest:
            self.manifest = href
            return
        icon_rels = {"icon", "apple-touch-icon", "apple-touch-icon-precomposed", "mask-icon"}
        if not rel_parts.intersection(icon_rels):
            return
        score = 0
        if rel_parts.intersection({"apple-touch-icon", "apple-touch-icon-precomposed"}):
            score = 1
        if "mask-icon" in rel_parts:
            score = 2
        self.icons.append((score, href))


def fetch_remote_bytes(url, timeout=8, max_bytes=2 * 1024 * 1024, referer=None):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 ErrorChanFavicon/1.0"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("图标文件过大。")
        return body, response.geturl(), response.headers.get_content_type()


def favicon_candidates(page_url):
    candidates = []
    final_url = page_url
    try:
        body, final_url, _ = fetch_remote_bytes(
            page_url,
            timeout=7,
            max_bytes=512 * 1024,
        )
        parser = FaviconLinkParser()
        parser.feed(body.decode("utf-8", errors="ignore"))
        base_url = urljoin(final_url, parser.base_href) if parser.base_href else final_url
        for _, href in sorted(parser.icons):
            candidates.append(urljoin(base_url, href))
        if parser.manifest:
            manifest_url = urljoin(base_url, parser.manifest)
            try:
                manifest_body, _, _ = fetch_remote_bytes(
                    manifest_url,
                    timeout=5,
                    max_bytes=256 * 1024,
                )
                manifest = json.loads(manifest_body.decode("utf-8", errors="ignore"))
                if not isinstance(manifest, dict):
                    manifest = {}
                for icon in manifest.get("icons", []):
                    if not isinstance(icon, dict):
                        continue
                    src = str(icon.get("src") or "").strip()
                    if src:
                        candidates.append(urljoin(manifest_url, src))
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError):
                pass
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        pass
    parsed = urlsplit(final_url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        candidates.extend(
            [
                f"{origin}/favicon.ico",
                f"{origin}/favicon.png",
                f"{origin}/favicon.svg",
                f"{origin}/apple-touch-icon.png",
            ]
        )
    result = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result[:12]


def detect_favicon_extension(data, content_type, source_url):
    lower_type = (content_type or "").lower()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    if data.startswith(b"\x00\x00\x01\x00") or data.startswith(b"\x00\x00\x02\x00"):
        return ".ico", "image/x-icon"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif", "image/avif"
    sample = data[:1024].lstrip().lower()
    if sample.startswith(b"<svg") or (sample.startswith(b"<?xml") and b"<svg" in sample):
        return ".svg", "image/svg+xml"
    if lower_type in ("image/x-icon", "image/vnd.microsoft.icon", "image/ico"):
        return ".ico", "image/x-icon"
    if lower_type == "image/png":
        return ".png", "image/png"
    if lower_type == "image/jpeg":
        return ".jpg", "image/jpeg"
    if lower_type == "image/gif":
        return ".gif", "image/gif"
    if lower_type == "image/webp":
        return ".webp", "image/webp"
    if lower_type == "image/avif":
        return ".avif", "image/avif"
    if lower_type == "image/svg+xml":
        return ".svg", "image/svg+xml"
    path = urlsplit(source_url).path.lower()
    for extension, mime_type in (
        (".ico", "image/x-icon"),
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".gif", "image/gif"),
        (".webp", "image/webp"),
        (".svg", "image/svg+xml"),
    ):
        if path.endswith(extension):
            return extension, mime_type
    return None, None


def bookmark_favicon_lock(bookmark_id):
    with BOOKMARK_FAVICON_LOCKS_GUARD:
        lock = BOOKMARK_FAVICON_LOCKS.get(bookmark_id)
        if lock is None:
            lock = threading.Lock()
            BOOKMARK_FAVICON_LOCKS[bookmark_id] = lock
        return lock


def save_bookmark_favicon(bookmark_id, data, extension):
    for old_path in BOOKMARK_FAVICON_DIR.glob(f"{bookmark_id}.*"):
        try:
            old_path.unlink()
        except OSError:
            pass
    filename = f"{bookmark_id}{extension}"
    full_path = BOOKMARK_FAVICON_DIR / filename
    full_path.write_bytes(data)
    return f"bookmark_favicons/{filename}"


def refresh_bookmark_favicon(bookmark_id, force=False):
    bookmark = query_one("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,))
    if not bookmark:
        return None
    current_path = bookmark.get("favicon_path")
    if current_path and not force:
        full_path = (DATA_DIR / current_path).resolve()
        try:
            full_path.relative_to(DATA_DIR.resolve())
            if full_path.is_file():
                return current_path
        except (ValueError, OSError):
            pass
    checked_at = bookmark.get("favicon_updated_at")
    if checked_at and not force:
        try:
            checked_time = datetime.strptime(checked_at, "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - checked_time).total_seconds() < 24 * 60 * 60:
                return None
        except ValueError:
            pass

    lock = bookmark_favicon_lock(bookmark_id)
    with lock:
        bookmark = query_one("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,))
        if not bookmark:
            return None
        if bookmark.get("favicon_path") and not force:
            full_path = (DATA_DIR / bookmark["favicon_path"]).resolve()
            try:
                full_path.relative_to(DATA_DIR.resolve())
                if full_path.is_file():
                    return bookmark["favicon_path"]
            except (ValueError, OSError):
                pass
        with BOOKMARK_FAVICON_SEMAPHORE:
            for candidate in favicon_candidates(bookmark["url"]):
                try:
                    data, final_url, content_type = fetch_remote_bytes(
                        candidate,
                        timeout=7,
                        referer=bookmark["url"],
                    )
                    extension, _ = detect_favicon_extension(data, content_type, final_url)
                    if not extension or not data:
                        continue
                    relative_path = save_bookmark_favicon(bookmark_id, data, extension)
                    execute(
                        """
                        UPDATE bookmarks
                        SET favicon_path = ?, favicon_source_url = ?,
                            favicon_updated_at = ?
                        WHERE id = ?
                        """,
                        (relative_path, final_url, now_text(), bookmark_id),
                    )
                    return relative_path
                except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                    continue
        execute(
            """
            UPDATE bookmarks
            SET favicon_path = NULL, favicon_source_url = NULL,
                favicon_updated_at = ?
            WHERE id = ?
            """,
            (now_text(), bookmark_id),
        )
    return None


def import_firefox_bookmarks(profile_key=None):
    profile = select_firefox_profile(profile_key)
    places_path = Path(profile["places_path"])
    read_uri = places_path.as_uri() + "?mode=ro"
    try:
        source = sqlite3.connect(read_uri, uri=True, timeout=5)
        source.row_factory = sqlite3.Row
        rows = source.execute(
            """
            SELECT b.id, b.parent, b.title, b.type, b.position, b.dateAdded,
                   p.url
            FROM moz_bookmarks b
            LEFT JOIN moz_places p ON p.id = b.fk
            WHERE b.type IN (1, 2)
            ORDER BY b.parent, b.position, b.id
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"无法读取 Firefox 书签数据库：{exc}") from exc
    finally:
        try:
            source.close()
        except UnboundLocalError:
            pass

    children = {}
    for row in rows:
        item = dict(row)
        children.setdefault(item["parent"], []).append(item)

    def subtree_has_bookmark(node_id):
        for child in children.get(node_id, []):
            if child["type"] == 1 and child.get("url"):
                return True
            if child["type"] == 2 and subtree_has_bookmark(child["id"]):
                return True
        return False

    roots = []
    for child in children.get(1, []):
        if child["type"] != 2 or str(child.get("title") or "").lower() == "tags":
            continue
        if subtree_has_bookmark(child["id"]):
            roots.append(child)

    source_prefix = f"firefox:{profile['name']}"
    counters = {
        "imported": 0,
        "skipped_duplicates": 0,
        "skipped_invalid": 0,
        "profile": profile["name"],
    }

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        bookmark_history = {
            row["source_key"]
            for row in conn.execute(
                "SELECT source_key FROM bookmark_import_seen"
            ).fetchall()
        }
        existing_urls = {
            row["url"]
            for row in conn.execute("SELECT url FROM bookmarks").fetchall()
        }

        def remember_bookmark(source_key, url):
            timestamp = now_text()
            conn.execute(
                """
                INSERT INTO bookmark_import_seen
                    (source_key, profile, url, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    url = excluded.url,
                    last_seen_at = excluded.last_seen_at
                """,
                (source_key, profile["name"], url, timestamp, timestamp),
            )

        def collect_bookmarks(node_id):
            collected = []
            for child in children.get(node_id, []):
                if child["type"] == 2:
                    collected.extend(collect_bookmarks(child["id"]))
                elif child["type"] == 1:
                    collected.append(child)
            return collected

        candidates = []
        for root in roots:
            candidates.extend(collect_bookmarks(root["id"]))

        pending = []
        seen_urls = set(existing_urls)
        for child in candidates:
            source_key = f"{source_prefix}:bookmark:{child['id']}"
            if source_key in bookmark_history:
                remember_bookmark(source_key, child.get("url"))
                counters["skipped_duplicates"] += 1
                continue
            try:
                url = normalize_bookmark_url(child.get("url"))
            except ValueError:
                remember_bookmark(source_key, None)
                bookmark_history.add(source_key)
                counters["skipped_invalid"] += 1
                continue
            if url in seen_urls:
                remember_bookmark(source_key, url)
                bookmark_history.add(source_key)
                counters["skipped_duplicates"] += 1
                continue
            seen_urls.add(url)
            pending.append((child, url, source_key))

        if pending:
            minimum_order = conn.execute(
                """
                SELECT COALESCE(MIN(sort_order), 0) AS value
                FROM bookmarks
                WHERE folder_id IS NULL
                """
            ).fetchone()["value"]
            order_start = int(minimum_order or 0) - len(pending)
        else:
            order_start = 0

        for index, (child, url, source_key) in enumerate(pending):
            title = str(child.get("title") or "").strip()[:200]
            if not title:
                title = urlsplit(url).hostname or url
            date_added = child.get("dateAdded")
            created_at = now_text()
            if date_added:
                try:
                    created_at = datetime.fromtimestamp(
                        int(date_added) / 1_000_000
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except (OverflowError, OSError, ValueError):
                    pass
            conn.execute(
                """
                INSERT INTO bookmarks
                    (folder_id, title, url, description, sort_order, source_key,
                     link_status, created_at, updated_at)
                VALUES (NULL, ?, ?, NULL, ?, ?, 'unknown', ?, ?)
                """,
                (
                    title,
                    url,
                    order_start + index,
                    source_key,
                    created_at,
                    created_at,
                ),
            )
            remember_bookmark(source_key, url)
            bookmark_history.add(source_key)
            existing_urls.add(url)
            counters["imported"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    counters["profile_path"] = profile["path"]
    return counters


def check_bookmark_link(url, timeout=6):
    origin = urlsplit(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 ErrorChanBookmarkChecker/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if origin.scheme and origin.netloc:
        headers["Referer"] = f"{origin.scheme}://{origin.netloc}/"
    context = ssl.create_default_context()

    def request(method):
        req = Request(url, method=method, headers=headers)
        with urlopen(req, timeout=timeout, context=context) as response:
            return response.status

    try:
        try:
            code = request("HEAD")
            if code < 400:
                return "valid", code, None
        except HTTPError as exc:
            pass
        except (URLError, TimeoutError, OSError, ValueError):
            pass

        try:
            code = request("GET")
            if code < 400:
                return "valid", code, None
            if code in (401, 403, 405, 429):
                return "valid", code, None
            return "broken", code, f"HTTP {code}"
        except HTTPError as exc:
            if exc.code in (401, 403, 405, 429):
                return "valid", exc.code, None
            return "broken", exc.code, f"HTTP {exc.code}"
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            return "broken", None, str(getattr(exc, "reason", exc))[:200]
    except Exception as exc:
        return "broken", None, str(exc)[:200]


def bookmark_check_status():
    with BOOKMARK_CHECK_LOCK:
        return dict(BOOKMARK_CHECK_STATE)


def run_bookmark_link_check(rows):
    conn = get_conn()
    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(10, max(1, len(rows)))
        ) as executor:
            future_map = {
                executor.submit(check_bookmark_link, row["url"]): row
                for row in rows
            }
            for future in concurrent.futures.as_completed(future_map):
                row = future_map[future]
                try:
                    status, code, error = future.result()
                except Exception as exc:
                    status, code, error = "broken", None, str(exc)[:200]
                conn.execute(
                    """
                    UPDATE bookmarks
                    SET link_status = ?, link_status_code = ?,
                        link_checked_at = ?, link_error = ?
                    WHERE id = ?
                    """,
                    (status, code, now_text(), error, row["id"]),
                )
                conn.commit()
                with BOOKMARK_CHECK_LOCK:
                    BOOKMARK_CHECK_STATE["completed"] += 1
                    BOOKMARK_CHECK_STATE[status] += 1
        with BOOKMARK_CHECK_LOCK:
            BOOKMARK_CHECK_STATE["running"] = False
            BOOKMARK_CHECK_STATE["finished_at"] = now_text()
    except Exception as exc:
        with BOOKMARK_CHECK_LOCK:
            BOOKMARK_CHECK_STATE["running"] = False
            BOOKMARK_CHECK_STATE["error"] = str(exc)
            BOOKMARK_CHECK_STATE["finished_at"] = now_text()
    finally:
        conn.close()


def start_bookmark_link_check(ids=None, broken_only=False):
    with BOOKMARK_CHECK_LOCK:
        if BOOKMARK_CHECK_STATE["running"]:
            raise ValueError("链接检查正在进行中。")
        BOOKMARK_CHECK_STATE.update(
            {
                "running": True,
                "total": 0,
                "completed": 0,
                "valid": 0,
                "broken": 0,
                "started_at": now_text(),
                "finished_at": None,
                "error": None,
            }
        )

    if ids:
        clean_ids = []
        for item_id in ids[:500]:
            try:
                clean_ids.append(int(item_id))
            except (TypeError, ValueError):
                continue
        if not clean_ids:
            raise ValueError("没有可检查的书签。")
        placeholders = ",".join("?" for _ in clean_ids)
        rows = query(
            f"SELECT id, url FROM bookmarks WHERE id IN ({placeholders})",
            tuple(clean_ids),
        )
    elif broken_only:
        rows = query(
            "SELECT id, url FROM bookmarks WHERE link_status = 'broken'"
        )
    else:
        rows = query("SELECT id, url FROM bookmarks")

    if not rows:
        with BOOKMARK_CHECK_LOCK:
            BOOKMARK_CHECK_STATE["running"] = False
            BOOKMARK_CHECK_STATE["finished_at"] = now_text()
        raise ValueError("没有可检查的书签。")
    with BOOKMARK_CHECK_LOCK:
        BOOKMARK_CHECK_STATE["total"] = len(rows)
    thread = threading.Thread(
        target=run_bookmark_link_check,
        args=(rows,),
        daemon=True,
        name="bookmark-link-check",
    )
    thread.start()
    return bookmark_check_status()


def part_summary_select():
    return """
        SELECT
            p.*,
            c.name AS category_name,
            (SELECT pr.id FROM part_projects pp
             JOIN projects pr ON pr.id = pp.project_id
             WHERE pp.part_id = p.id
             ORDER BY pr.id LIMIT 1) AS linked_project_id,
            COALESCE((SELECT SUM(b.quantity) FROM batches b WHERE b.part_id = p.id), 0) AS stock_quantity,
            COALESCE((SELECT SUM(b.received_quantity - b.quantity) FROM batches b WHERE b.part_id = p.id), 0) AS used_quantity,
            (SELECT COUNT(*) FROM batches b WHERE b.part_id = p.id) AS batch_count
        FROM parts p
        LEFT JOIN categories c ON c.id = p.category_id
    """


def parse_number(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("￥", "").replace("¥", "").replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else 0.0


def parse_quantity(value):
    number = parse_number(value)
    if number <= 0:
        return 1.0
    return number


def col_index(ref):
    match = re.match(r"([A-Z]+)", ref or "")
    if not match:
        return 0
    result = 0
    for ch in match.group(1):
        result = result * 26 + (ord(ch.upper()) - 64)
    return result - 1


def parse_xlsx_rows(data):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("文件不是有效的 .xlsx 文件。") from exc

    names = archive.namelist()
    shared_strings = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for si in root.iter(f"{XLSX_NS}si"):
            shared_strings.append(
                "".join(t.text or "" for t in si.iter(f"{XLSX_NS}t"))
            )

    sheet_name = "xl/worksheets/sheet1.xml"
    if sheet_name not in names:
        candidates = [name for name in names if re.match(r"xl/worksheets/sheet\d+\.xml$", name)]
        if not candidates:
            raise ValueError("文件中没有找到可读取的工作表。")
        sheet_name = sorted(candidates)[0]

    root = ET.fromstring(archive.read(sheet_name))
    rows = []
    for row_el in root.iter(f"{XLSX_NS}row"):
        cells = {}
        for cell in row_el.findall(f"{XLSX_NS}c"):
            idx = col_index(cell.get("r", ""))
            cell_type = cell.get("t", "")
            value = ""
            value_el = cell.find(f"{XLSX_NS}v")
            if cell_type == "s" and value_el is not None:
                pos = int(float(value_el.text or 0))
                value = shared_strings[pos] if pos < len(shared_strings) else ""
            elif cell_type == "inlineStr":
                inline = cell.find(f"{XLSX_NS}is")
                if inline is not None:
                    value = "".join(t.text or "" for t in inline.iter(f"{XLSX_NS}t"))
            elif value_el is not None:
                value = value_el.text or ""
            cells[idx] = value
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    if not rows:
        raise ValueError("工作表中没有数据。")
    return rows


LCSC_COLUMN_ALIASES = {
    "lcsc_code": ["商品编号", "lcsc", "lcsc编号"],
    "brand": ["品牌", "制造商", "厂家"],
    "part_number": ["厂家型号", "型号", "制造商型号", "mpn"],
    "package": ["封装", "package"],
    "description": ["商品名称", "名称", "描述", "品名"],
    "quantity": ["订购数量", "数量", "库存数量"],
    "unit_price": ["商品单价", "单价"],
    "total_price": ["商品金额", "金额"],
}


def normalize_header(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def map_lcsc_columns(header):
    mapped = {}
    normalized = [normalize_header(value) for value in header]
    for field, aliases in LCSC_COLUMN_ALIASES.items():
        normalized_aliases = [normalize_header(alias) for alias in aliases]
        exact = next(
            (idx for idx, value in enumerate(normalized) if value in normalized_aliases),
            None,
        )
        if exact is not None:
            mapped[field] = exact
            continue
        for idx, value in enumerate(normalized):
            if any(alias and alias in value for alias in normalized_aliases):
                mapped[field] = idx
                break
    return mapped


def find_lcsc_header_row(rows):
    for idx, row in enumerate(rows):
        values = [str(v or "") for v in row]
        if any("商品编号" in v or "lcsc" in normalize_header(v) for v in values) and any(
            "型号" in v or "封装" in v or "品牌" in v for v in values
        ):
            return idx
    return None


def import_lcsc_data(payload):
    file_name = str(payload.get("file_name") or "LCSC.xlsx")
    data_base64 = payload.get("data_base64") or ""
    category_id = payload.get("category_id")
    location_id = payload.get("location_id")
    update_existing = bool(payload.get("update_existing", True))
    try:
        data = base64.b64decode(data_base64)
    except Exception as exc:
        raise ValueError("文件内容无法解码。") from exc
    rows = parse_xlsx_rows(data)
    header_idx = find_lcsc_header_row(rows)
    if header_idx is None:
        raise ValueError("没有识别到 LCSC 表头，请确认文件是立创商城导出的 .xlsx。")
    columns = map_lcsc_columns(rows[header_idx])
    missing = [field for field in ("lcsc_code", "part_number", "quantity") if field not in columns]
    if missing:
        raise ValueError("LCSC 文件缺少必要字段：" + "、".join(missing))

    if not location_id:
        first_location = query_one("SELECT id FROM locations ORDER BY id LIMIT 1")
        if not first_location:
            raise ValueError("请先创建存放位置。")
        location_id = first_location["id"]

    result = {"imported": 0, "updated": 0, "skipped": 0, "errors": []}
    order_number = Path(file_name).stem or f"LCSC-{today_text()}"

    def row_value(row, field):
        idx = columns.get(field)
        if idx is None or idx >= len(row):
            return ""
        return row[idx]

    for line_no, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        lcsc_code = str(row_value(row, "lcsc_code") or "").strip()
        part_number = str(row_value(row, "part_number") or "").strip()
        if not lcsc_code and not part_number:
            continue
        quantity = parse_quantity(row_value(row, "quantity"))
        unit_price = parse_number(row_value(row, "unit_price"))
        brand = str(row_value(row, "brand") or "").strip()
        package = str(row_value(row, "package") or "").strip()
        description = str(row_value(row, "description") or "").strip()

        def add_batch(conn, part_id):
            conn.execute(
                """INSERT INTO batches
                   (part_id, location_id, quantity, received_quantity, purchase_date,
                    unit_price, channel, order_number, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    part_id,
                    location_id,
                    quantity,
                    quantity,
                    today_text(),
                    unit_price if unit_price else None,
                    "LCSC",
                    order_number,
                    "LCSC Excel 导入",
                    now_text(),
                ),
            )
            batch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """INSERT INTO movements
                   (part_id, batch_id, project_id, movement_type, quantity,
                    before_quantity, after_quantity, unit_price, channel, order_number,
                    note, created_at)
                   VALUES (?, ?, NULL, 'in', ?, 0, ?, ?, 'LCSC', ?, ?, ?)""",
                (part_id, batch_id, quantity, quantity, unit_price if unit_price else None, order_number, "LCSC Excel 导入", now_text()),
            )

        try:
            def run(conn):
                existing = conn.execute(
                    """SELECT * FROM parts
                       WHERE (lcsc_code IS NOT NULL AND lcsc_code = ?)
                          OR (part_number <> '' AND part_number = ?)
                       ORDER BY id LIMIT 1""",
                    (lcsc_code, part_number),
                ).fetchone()
                if existing:
                    if not update_existing:
                        return "skip"
                    fields = []
                    values = []
                    if brand and existing["brand"] != brand:
                        fields.append("brand = ?")
                        values.append(brand)
                    if package and existing["package"] != package:
                        fields.append("package = ?")
                        values.append(package)
                    if description and existing["description"] != description:
                        fields.append("description = ?")
                        values.append(description)
                    if existing["datasheet_url"] is None and lcsc_code:
                        fields.append("datasheet_url = ?")
                        values.append(f"https://www.lcsc.com/product-detail/{lcsc_code}.html")
                    if fields:
                        values.append(now_text())
                        values.append(existing["id"])
                        conn.execute(
                            f"UPDATE parts SET {', '.join(fields)}, updated_at = ? WHERE id = ?",
                            values,
                        )
                    add_batch(conn, existing["id"])
                    return "updated"
                datasheet_url = (
                    f"https://www.lcsc.com/product-detail/{lcsc_code}.html" if lcsc_code else None
                )
                cursor = conn.execute(
                    """INSERT INTO parts
                       (part_number, lcsc_code, brand, category_id, package,
                        temperature_range, voltage_rating, description, datasheet_url,
                        notes, min_stock, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, '', '', ?, ?, '', 0, ?, ?)""",
                    (
                        part_number or lcsc_code,
                        lcsc_code or None,
                        brand or None,
                        category_id,
                        package or None,
                        description or None,
                        datasheet_url,
                        now_text(),
                        now_text(),
                    ),
                )
                add_batch(conn, cursor.lastrowid)
                return "imported"

            status = transaction(run)
            if status == "skip":
                result["skipped"] += 1
            elif status == "updated":
                result["updated"] += 1
            else:
                result["imported"] += 1
        except Exception as exc:
            result["errors"].append(f"第 {line_no} 行：{exc}")

    return result


BOM_FIELD_ALIASES = {
    "designators": [
        "位号",
        "designator",
        "designators",
        "reference designator",
        "reference_designator",
        "refdes",
        "ref",
        "元件编号",
    ],
    "mpn": [
        "型号",
        "规格",
        "厂家型号",
        "制造商型号",
        "元件型号",
        "mpn",
        "part number",
        "part_number",
        "part name",
        "part_name",
        "manufacturer part",
        "manufacturer_part",
        "comment",
        "value",
        "器件",
    ],
    "package": [
        "封装",
        "package",
        "footprint",
        "封装名称",
    ],
    "qty": [
        "数量",
        "用量",
        "数量/PCB",
        "qty",
        "quantity",
        "count",
        "amount",
    ],
    "description": [
        "描述",
        "description",
        "商品名称",
        "名称",
        "品名",
    ],
    "lcsc": [
        "lcsc",
        "lcsc编号",
        "lcsc code",
        "商品编号",
        "supplier part",
        "supplier_part",
        "jlc code",
        "立创编号",
    ],
    "brand": [
        "品牌",
        "制造商",
        "厂家",
        "manufacturer",
        "brand",
    ],
}

BOM_WATCH_LOCK = threading.Lock()
BOM_WATCH_STATE = {
    "thread": None,
    "stop": threading.Event(),
    "folder": "",
    "interval": 30,
    "last_run": None,
    "processed_count": 0,
    "last_error": None,
    "processed": {},
}


def normalize_bom_code(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


def decode_csv_bytes(data):
    raw = bytes(data)
    for encoding in ("utf-8-sig", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def detect_bom_columns(header):
    normalized = [normalize_header(value) for value in header]
    columns = {}
    for field, aliases in BOM_FIELD_ALIASES.items():
        normalized_aliases = [normalize_header(alias) for alias in aliases]
        exact = next(
            (idx for idx, value in enumerate(normalized) if value in normalized_aliases),
            None,
        )
        if exact is not None:
            columns[field] = exact
            continue
        for idx, value in enumerate(normalized):
            if any(alias and alias in value for alias in normalized_aliases):
                columns[field] = idx
                break
    return columns


def find_bom_header(rows):
    for idx, row in enumerate(rows[:40]):
        columns = detect_bom_columns(row)
        has_item = "mpn" in columns or "lcsc" in columns or "designators" in columns
        if has_item and ("qty" in columns or "designators" in columns):
            return idx, columns
    return None, None


def parse_bom_rows(data, file_name):
    suffix = Path(file_name).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return parse_xlsx_rows(data)
    if suffix == ".xls":
        try:
            import xlrd
        except ImportError:
            raise ValueError("旧版 .xls 需要先另存为 .xlsx 或 CSV。")
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".xls", delete=False) as handle:
            handle.write(data)
            temp_path = handle.name
        try:
            book = xlrd.open_workbook(temp_path)
            sheet = book.sheet_by_index(0)
            return [
                [str(sheet.cell_value(row_idx, col_idx)) for col_idx in range(sheet.ncols)]
                for row_idx in range(sheet.nrows)
            ]
        finally:
            os.unlink(temp_path)
    if suffix in (".csv", ".tsv", ".txt"):
        text = decode_csv_bytes(data)
        delimiter = "\t" if suffix == ".tsv" else None
        if delimiter is None:
            try:
                delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
            except csv.Error:
                delimiter = ","
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    raise ValueError(f"不支持的文件类型：{suffix}，请使用 CSV 或 Excel 文件。")


def bom_cell(row, columns, field):
    idx = columns.get(field)
    return str(row[idx]).strip() if idx is not None and idx < len(row) else ""


def extract_bom_items(rows):
    header_idx, columns = find_bom_header(rows)
    if header_idx is None:
        raise ValueError("没有识别到 BOM 表头，请确认包含 型号、数量、封装、位号 等字段。")

    items = {}
    for row in rows[header_idx + 1 :]:
        if not any(str(value or "").strip() for value in row):
            continue
        ref = bom_cell(row, columns, "designators")
        mpn = bom_cell(row, columns, "mpn")
        package = bom_cell(row, columns, "package")
        lcsc = bom_cell(row, columns, "lcsc")
        description = bom_cell(row, columns, "description")
        brand = bom_cell(row, columns, "brand")
        qty = parse_number(bom_cell(row, columns, "qty"))
        if qty <= 0:
            tokens = [token for token in re.split(r"[,;\s]+", ref) if token]
            qty = len(tokens) if tokens else 1.0
        if not mpn and not lcsc and not ref:
            continue

        key = (
            normalize_bom_code(mpn or lcsc or ref),
            normalize_bom_code(lcsc),
            normalize_bom_code(package),
        )
        if key not in items:
            items[key] = {
                "designators": [],
                "mpn": mpn,
                "package": package,
                "lcsc": lcsc,
                "description": description,
                "brand": brand,
                "qty": 0.0,
            }
        item = items[key]
        item["qty"] += qty
        for token in re.split(r"[,;\s]+", ref):
            if token and token not in item["designators"]:
                item["designators"].append(token)
        if not item["mpn"] and mpn:
            item["mpn"] = mpn
        if not item["lcsc"] and lcsc:
            item["lcsc"] = lcsc
        if not item["package"] and package:
            item["package"] = package
        if not item["description"] and description:
            item["description"] = description
        if not item["brand"] and brand:
            item["brand"] = brand

    result = list(items.values())
    for item in result:
        item["designators"] = ", ".join(item["designators"])
    return result


def choose_part_by_package(candidates, package_key):
    if package_key:
        exact = [
            part
            for part in candidates
            if normalize_bom_code(part.get("package")) == package_key
        ]
        if exact:
            return exact[0]
    return candidates[0]


def find_bom_part(item, parts, match_mode):
    lcsc_key = normalize_bom_code(item.get("lcsc"))
    mpn_key = normalize_bom_code(item.get("mpn"))
    package_key = normalize_bom_code(item.get("package"))

    if match_mode in ("auto", "lcsc_code") and lcsc_key:
        candidates = [
            part
            for part in parts
            if normalize_bom_code(part.get("lcsc_code")) == lcsc_key
        ]
        if candidates:
            return choose_part_by_package(candidates, package_key), "LCSC 编号"

    if match_mode in ("auto", "part_number") and mpn_key:
        candidates = [
            part
            for part in parts
            if normalize_bom_code(part.get("part_number")) == mpn_key
        ]
        if candidates:
            return choose_part_by_package(candidates, package_key), "厂家型号"

    if match_mode in ("auto", "description") and len(mpn_key) >= 4:
        candidates = [
            part
            for part in parts
            if mpn_key in normalize_bom_code(part.get("description") or "")
        ]
        if candidates:
            return choose_part_by_package(candidates, package_key), "描述"

    return None, ""


def compare_bom_items(items, match_mode="auto"):
    parts = query(
        "SELECT id, part_number, lcsc_code, brand, package, description FROM parts"
    )
    stock_rows = query(
        "SELECT part_id, COALESCE(SUM(quantity), 0) AS stock FROM batches GROUP BY part_id"
    )
    stock_map = {row["part_id"]: float(row["stock"] or 0) for row in stock_rows}

    report = []
    for item in items:
        part, matched_by = find_bom_part(item, parts, match_mode)
        row = dict(item)
        if part:
            stock = stock_map.get(part["id"], 0.0)
            shortage = max(0.0, item["qty"] - stock)
            row.update(
                {
                    "status": "充足" if shortage <= 0 else "缺料",
                    "stock": stock,
                    "shortage": shortage,
                    "matched_part_id": part["id"],
                    "matched_part_number": part["part_number"],
                    "matched_lcsc": part.get("lcsc_code") or "",
                    "matched_by": matched_by,
                }
            )
        else:
            row.update(
                {
                    "status": "未匹配",
                    "stock": 0.0,
                    "shortage": item["qty"],
                    "matched_part_id": None,
                    "matched_part_number": "",
                    "matched_lcsc": "",
                    "matched_by": "",
                }
            )
        report.append(row)

    report.sort(
        key=lambda row: (
            row["status"] == "充足",
            -row["shortage"],
            row["status"] != "缺料",
        )
    )
    return report


def bom_summary(report):
    return {
        "item_count": len(report),
        "ok": sum(1 for row in report if row["status"] == "充足"),
        "shortage": sum(1 for row in report if row["status"] == "缺料"),
        "unmatched": sum(1 for row in report if row["status"] == "未匹配"),
    }


def save_bom_report(
    file_name,
    source_path,
    report,
    match_mode,
    project_id=None,
    project_name=None,
):
    BOM_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    payload = {
        "id": report_id,
        "file_name": file_name,
        "source_path": source_path or "",
        "match_mode": match_mode,
        "project_id": project_id,
        "project_name": project_name or "",
        "created_at": now_text(),
        "summary": bom_summary(report),
        "items": report,
    }
    (BOM_REPORT_DIR / f"{report_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report_id, payload


def load_bom_report(report_id):
    path = BOM_REPORT_DIR / f"{report_id}.json"
    if not path.is_file():
        raise ValueError("对比记录不存在。")
    return json.loads(path.read_text(encoding="utf-8"))


def list_bom_reports():
    if not BOM_REPORT_DIR.is_dir():
        return []
    reports = []
    for path in BOM_REPORT_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            reports.append(
                {
                    "id": payload["id"],
                    "file_name": payload["file_name"],
                    "source_path": payload.get("source_path", ""),
                    "project_id": payload.get("project_id"),
                    "project_name": payload.get("project_name", ""),
                    "created_at": payload["created_at"],
                    "summary": payload["summary"],
                }
            )
        except (KeyError, json.JSONDecodeError):
            continue
    reports.sort(key=lambda row: row["created_at"], reverse=True)
    return reports[:50]


def report_csv_text(report):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "位号",
            "型号/规格",
            "封装",
            "LCSC",
            "需求数量",
            "库存可用",
            "缺口",
            "状态",
            "匹配元件ID",
            "匹配型号",
            "匹配LCSC",
            "匹配方式",
        ]
    )
    for row in report["items"]:
        writer.writerow(
            [
                row.get("designators", ""),
                row.get("mpn", ""),
                row.get("package", ""),
                row.get("lcsc", ""),
                f"{float(row.get('qty') or 0):g}",
                f"{float(row.get('stock') or 0):g}",
                f"{float(row.get('shortage') or 0):g}",
                row.get("status", ""),
                row.get("matched_part_id") or "",
                row.get("matched_part_number", ""),
                row.get("matched_lcsc", ""),
                row.get("matched_by", ""),
            ]
        )
    return "\ufeff" + output.getvalue()


def load_bom_watch_state():
    try:
        if BOM_WATCH_STATE_PATH.is_file():
            state = json.loads(BOM_WATCH_STATE_PATH.read_text(encoding="utf-8"))
            BOM_WATCH_STATE["processed"] = state.get("processed", {})
    except (ValueError, OSError):
        BOM_WATCH_STATE["processed"] = {}


def save_bom_watch_state():
    try:
        DATA_DIR.mkdir(exist_ok=True)
        BOM_WATCH_STATE_PATH.write_text(
            json.dumps(
                {"processed": BOM_WATCH_STATE.get("processed", {})},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def bom_watch_loop():
    while not BOM_WATCH_STATE["stop"].is_set():
        with BOM_WATCH_LOCK:
            folder = BOM_WATCH_STATE.get("folder", "")
            interval = max(5, int(BOM_WATCH_STATE.get("interval") or 30))
            processed = BOM_WATCH_STATE.setdefault("processed", {})
        try:
            if folder and Path(folder).is_dir():
                suffixes = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls")
                for path in sorted(Path(folder).iterdir()):
                    if path.suffix.lower() not in suffixes or not path.is_file():
                        continue
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if processed.get(str(path)) == digest:
                        continue
                    try:
                        rows = parse_bom_rows(path.read_bytes(), path.name)
                        items = extract_bom_items(rows)
                        report = compare_bom_items(items)
                        save_bom_report(path.name, str(path), report, "auto")
                        with BOM_WATCH_LOCK:
                            processed[str(path)] = digest
                            BOM_WATCH_STATE["processed_count"] = len(processed)
                            BOM_WATCH_STATE["last_error"] = None
                        save_bom_watch_state()
                    except Exception as exc:
                        with BOM_WATCH_LOCK:
                            processed[str(path)] = digest
                            BOM_WATCH_STATE["last_error"] = f"{path.name}: {exc}"
                        save_bom_watch_state()
        except Exception as exc:
            with BOM_WATCH_LOCK:
                BOM_WATCH_STATE["last_error"] = str(exc)
        with BOM_WATCH_LOCK:
            BOM_WATCH_STATE["last_run"] = now_text()
        BOM_WATCH_STATE["stop"].wait(interval)


def start_bom_watch(folder, interval=30):
    folder = str(folder or "").strip().strip('"')
    if not folder:
        raise ValueError("请填写本机文件夹路径。")
    if not Path(folder).is_dir():
        raise ValueError("文件夹不存在，请检查路径。")
    stop_bom_watch()
    load_bom_watch_state()
    with BOM_WATCH_LOCK:
        if BOM_WATCH_STATE.get("folder") != folder:
            BOM_WATCH_STATE["processed"] = {}
            BOM_WATCH_STATE["processed_count"] = 0
        BOM_WATCH_STATE["folder"] = folder
        BOM_WATCH_STATE["interval"] = max(5, int(interval or 30))
        BOM_WATCH_STATE["stop"] = threading.Event()
        BOM_WATCH_STATE["last_error"] = None
        BOM_WATCH_STATE["last_run"] = None
        thread = threading.Thread(target=bom_watch_loop, daemon=True)
        BOM_WATCH_STATE["thread"] = thread
        thread.start()
    return bom_watch_status()


def stop_bom_watch():
    with BOM_WATCH_LOCK:
        thread = BOM_WATCH_STATE.get("thread")
        stop_event = BOM_WATCH_STATE.get("stop")
        BOM_WATCH_STATE["thread"] = None
    if thread and thread.is_alive() and stop_event:
        stop_event.set()
        thread.join(timeout=3)
    return bom_watch_status()


def bom_watch_status():
    with BOM_WATCH_LOCK:
        thread = BOM_WATCH_STATE.get("thread")
        running = bool(thread and thread.is_alive())
        status = {
            "running": running,
            "folder": BOM_WATCH_STATE.get("folder", ""),
            "interval": BOM_WATCH_STATE.get("interval", 30),
            "last_run": BOM_WATCH_STATE.get("last_run"),
            "processed_count": BOM_WATCH_STATE.get("processed_count", 0),
            "last_error": BOM_WATCH_STATE.get("last_error"),
        }
    return status


ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def save_part_image(part_id, data_base64, file_name):
    try:
        data = base64.b64decode(data_base64)
    except Exception as exc:
        raise ValueError("图片内容无法解码。") from exc
    if not data:
        raise ValueError("图片内容为空。")
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("图片不能超过 5MB。")
    ext = Path(file_name or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        ext = ".png"

    part = query_one("SELECT image_path FROM parts WHERE id = ?", (part_id,))
    if not part:
        raise ValueError("元件不存在。")
    old_path = part.get("image_path") or ""
    if old_path:
        try:
            old_full = (DATA_DIR / old_path).resolve()
            old_full.relative_to(DATA_DIR.resolve())
            if old_full.is_file():
                old_full.unlink()
        except (ValueError, OSError):
            pass

    PART_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = f"{part_id}_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:4]}{ext}"
    image_path = PART_IMAGE_DIR / unique_name
    image_path.write_bytes(data)
    relative_path = f"part_images/{image_path.name}"
    execute(
        "UPDATE parts SET image_path = ?, updated_at = ? WHERE id = ?",
        (relative_path, now_text(), part_id),
    )
    return relative_path


def remove_part_image(part_id):
    part = query_one("SELECT image_path FROM parts WHERE id = ?", (part_id,))
    if not part:
        raise ValueError("元件不存在。")
    old_path = part.get("image_path") or ""
    if old_path:
        try:
            old_full = (DATA_DIR / old_path).resolve()
            old_full.relative_to(DATA_DIR.resolve())
            if old_full.is_file():
                old_full.unlink()
        except (ValueError, OSError):
            pass
    execute(
        "UPDATE parts SET image_path = NULL, updated_at = ? WHERE id = ?",
        (now_text(), part_id),
    )


def launch_lcsc_image_fetch():
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [
                sys.executable,
                str(BASE_DIR / "fetch_lcsc_images.py"),
                "--workers",
                "3",
            ],
            cwd=str(BASE_DIR),
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def markdown_escape_text(value):
    """转义普通文本里的 Markdown 控制字符，避免导入后改变原意。"""
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", str(value or ""))


def markdown_apply_style(value, style):
    text = str(value or "")
    if not text or style is None or not text.strip():
        return text
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    core = text.strip()
    if getattr(style, "code", False):
        core = f"`{core.replace('`', '``')}`"
    if getattr(style, "bold", False):
        core = f"**{core}**"
    if getattr(style, "italic", False):
        core = f"*{core}*"
    if getattr(style, "strike", False):
        core = f"~~{core}~~"
    return leading + core + trailing


def markdown_link_url(value):
    return (
        str(value or "")
        .replace(" ", "%20")
        .replace("(", "%28")
        .replace(")", "%29")
    )


def render_anydoc_inline(inline, asset_resolver):
    kind = getattr(inline, "kind", "")
    if kind == "text":
        return markdown_apply_style(
            markdown_escape_text(getattr(inline, "text", "")),
            getattr(inline, "style", None),
        )
    if kind == "link":
        label = render_anydoc_inlines(getattr(inline, "content", None), asset_resolver)
        target = getattr(inline, "target", None)
        if target is None:
            return label
        target_kind = getattr(target, "kind", "")
        href = str(getattr(target, "value", "") or "")
        if target_kind == "anchor":
            href = f"#{href}"
        href = markdown_link_url(href)
        if not href:
            return label
        return f"[{label or markdown_escape_text(href)}]({href})"
    if kind == "image":
        alt = markdown_escape_text(getattr(inline, "alt", "") or "图片")
        source = getattr(inline, "source", None)
        source_kind = getattr(source, "kind", "") if source is not None else ""
        if source_kind == "external":
            url = markdown_link_url(getattr(source, "url", ""))
            return f"![{alt}]({url})" if url else alt
        if source_kind == "asset":
            return asset_resolver(getattr(source, "asset_id", None), alt)
        return alt
    if kind == "anchor":
        return ""
    if kind == "note_ref":
        note_id = markdown_escape_text(getattr(inline, "note_id", ""))
        return f"[^{note_id}]" if note_id else ""
    if kind == "line_break":
        return "  \n"
    if kind == "math":
        value = str(getattr(inline, "text", "") or "").strip()
        return f"${value}$" if value else ""
    if kind == "checkbox":
        return "[x]" if getattr(inline, "checked", False) else "[ ]"
    content = getattr(inline, "content", None)
    if content:
        return render_anydoc_inlines(content, asset_resolver)
    return markdown_escape_text(getattr(inline, "text", ""))


def render_anydoc_inlines(inlines, asset_resolver):
    return "".join(render_anydoc_inline(item, asset_resolver) for item in (inlines or []))


def render_anydoc_table(table, asset_resolver):
    rows = []
    for grid_row in getattr(table, "grid", None) or []:
        cells = []
        for slot in grid_row:
            if getattr(slot, "kind", "") != "origin" or getattr(slot, "cell", None) is None:
                cells.append("")
                continue
            value = render_anydoc_blocks(
                getattr(slot.cell, "blocks", None) or [],
                asset_resolver,
            )
            value = value.replace("\n", "<br>").replace("|", "\\|").strip()
            cells.append(value)
        rows.append(cells)
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""
    columns = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (columns - len(row)))
    if getattr(table, "kind", "") == "layout":
        return "\n".join(" | ".join(cell for cell in row if cell).strip() for row in rows)
    header_rows = max(1, min(int(getattr(table, "header_rows", 0) or 1), len(rows)))
    header = rows[0]
    body = rows[1:]
    if header_rows > 1:
        header = [
            "<br>".join(rows[row_index][column] for row_index in range(header_rows))
            for column in range(columns)
        ]
        body = rows[header_rows:]
    return "\n".join(
        [
            f"| {' | '.join(header)} |",
            f"| {' | '.join('---' for _ in range(columns))} |",
            *[f"| {' | '.join(row)} |" for row in body],
        ]
    )


def markdown_alpha_number(value):
    number = max(1, int(value))
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("a") + remainder) + result
    return result


def markdown_roman_number(value):
    number = max(1, int(value))
    numerals = (
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    )
    result = []
    for amount, numeral in numerals:
        while number >= amount:
            result.append(numeral)
            number -= amount
    return "".join(result)


def render_anydoc_list(list_value, asset_resolver, depth):
    marker_family = getattr(list_value, "marker", "bullet")
    start = int(getattr(list_value, "start", 1) or 1)
    output = []
    for offset, item in enumerate(getattr(list_value, "items", None) or []):
        blocks = getattr(item, "blocks", None) or []
        if not blocks:
            continue
        marker = getattr(item, "marker_label", None)
        if not marker:
            number = start + offset
            if marker_family == "bullet":
                marker = "-"
            elif marker_family == "lower_alpha":
                marker = f"{markdown_alpha_number(number)}."
            elif marker_family == "upper_alpha":
                marker = f"{markdown_alpha_number(number).upper()}."
            elif marker_family == "lower_roman":
                marker = f"{markdown_roman_number(number)}."
            elif marker_family == "upper_roman":
                marker = f"{markdown_roman_number(number).upper()}."
            else:
                marker = f"{number}."
        first_block = blocks[0]
        first = render_anydoc_block(first_block, asset_resolver, depth + 1).strip()
        first_lines = first.splitlines() or [""]
        indent = "  " * depth
        continuation = indent + "  "
        lines = [f"{indent}{marker} {first_lines[0]}".rstrip()]
        lines.extend(f"{continuation}{line}".rstrip() for line in first_lines[1:])
        for block in blocks[1:]:
            rendered = render_anydoc_block(block, asset_resolver, depth + 1)
            lines.extend(f"{continuation}{line}".rstrip() for line in rendered.splitlines())
        output.append("\n".join(line for line in lines if line.strip()))
    return "\n".join(output)


def render_anydoc_block(block, asset_resolver, depth=0):
    kind = getattr(block, "kind", "")
    content = getattr(block, "content", None)
    if kind == "heading":
        level = max(1, min(int(getattr(block, "level", 1) or 1), 6))
        value = render_anydoc_inlines(content, asset_resolver).strip()
        return f"{'#' * level} {value}" if value else ""
    if kind == "paragraph":
        return render_anydoc_inlines(content, asset_resolver)
    if kind == "list":
        return render_anydoc_list(getattr(block, "list", None), asset_resolver, depth)
    if kind == "table":
        return render_anydoc_table(getattr(block, "table", None), asset_resolver)
    if kind == "block_quote":
        value = render_anydoc_blocks(getattr(block, "blocks", None) or [], asset_resolver, depth)
        return "\n".join(f"> {line}".rstrip() for line in value.splitlines())
    if kind == "code_block":
        value = str(getattr(block, "text", "") or "").rstrip()
        longest = max((len(match) for match in re.findall(r"`+", value)), default=0)
        fence = "`" * max(3, longest + 1)
        language = str(getattr(block, "lang", "") or "").strip()
        return f"{fence}{language}\n{value}\n{fence}"
    if kind == "rule":
        return "---"
    if kind == "math":
        value = str(getattr(block, "text", "") or "").strip()
        return f"$$\n{value}\n$$" if value else ""
    nested = getattr(block, "blocks", None)
    return render_anydoc_blocks(nested or [], asset_resolver, depth)


def render_anydoc_blocks(blocks, asset_resolver, depth=0):
    parts = []
    for block in blocks or []:
        rendered = render_anydoc_block(block, asset_resolver, depth).strip()
        if rendered:
            parts.append(rendered)
    return "\n\n".join(parts)


def render_anydoc_document(document, asset_resolver):
    parts = []
    body = render_anydoc_blocks(getattr(document, "blocks", None) or [], asset_resolver)
    if body:
        parts.append(body)
    for note in getattr(document, "notes", None) or []:
        note_id = markdown_escape_text(getattr(note, "id", ""))
        note_body = render_anydoc_blocks(getattr(note, "blocks", None) or [], asset_resolver)
        if note_id and note_body:
            parts.append(f"[^{note_id}]: {note_body.replace(chr(10), chr(10) + '    ')}")
    return "\n\n".join(parts).strip()


def note_image_paths(content):
    """按出现顺序返回笔记正文引用到的图片相对路径。"""
    paths = []
    for match in NOTE_IMAGE_PATH_RE.findall(content or ""):
        path = unquote(match)
        if path not in paths:
            paths.append(path)
    return paths


def note_export_json(value):
    """把值编码成可安全放进 HTML script 标签的 JSON。"""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def note_export_image_map(content):
    """把笔记引用的本地图片编码成 data URI，供导出的单文件 HTML 内嵌。"""
    images = {}
    data_root = DATA_DIR.resolve()
    for relative in note_image_paths(content):
        if relative in images:
            continue
        try:
            full = (DATA_DIR / relative).resolve()
            full.relative_to(data_root)
        except (ValueError, OSError):
            continue
        if not full.is_file():
            continue
        mime_type = mimetypes.guess_type(full.name)[0] or ""
        if not mime_type.startswith("image/"):
            continue
        try:
            raw = full.read_bytes()
        except OSError:
            continue
        images[relative] = f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"
    return images


def build_note_export_html(note, image_map):
    """生成可离线打开、也可在 VS Code 中阅读的单文件笔记 HTML。"""
    title = str(note.get("title") or "未命名笔记")
    content = str(note.get("content") or "")
    tags = [
        item.strip()
        for item in re.split(r"[,，、]", str(note.get("tags") or ""))
        if item.strip()
    ]
    tags_html = "".join(f"<span>{html_escape(tag)}</span>" for tag in tags)
    created_at = html_escape(str(note.get("created_at") or ""))
    updated_at = html_escape(str(note.get("updated_at") or ""))
    generated_at = html_escape(now_text())

    try:
        marked_script = (STATIC_DIR / "vendor" / "marked.min.js").read_text(encoding="utf-8")
        purify_script = (STATIC_DIR / "vendor" / "purify.min.js").read_text(encoding="utf-8")
    except OSError:
        marked_script = ""
        purify_script = ""

    css = """
    :root {
      color-scheme: light dark;
      --bg: #f6f7fb;
      --surface: #ffffff;
      --text: #1f2329;
      --muted: #667085;
      --border: #e4e7ec;
      --accent: #6d5ce7;
      --code-bg: #f3f4f6;
      --quote-bg: #f7f5ff;
      --shadow: 0 12px 36px rgba(24, 31, 45, 0.08);
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #111214;
        --surface: #1c1d21;
        --text: #f2f3f5;
        --muted: #a1a1aa;
        --border: #34363d;
        --accent: #a78bfa;
        --code-bg: #15161a;
        --quote-bg: #252134;
        --shadow: 0 14px 40px rgba(0, 0, 0, 0.32);
      }
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
      font-size: 16px;
      line-height: 1.75;
    }

    .note-shell {
      width: min(920px, 100%);
      min-height: 100vh;
      margin: 0 auto;
      padding: 44px 28px 80px;
    }

    .note-header {
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }

    .note-header h1 {
      margin: 0 0 10px;
      font-size: clamp(26px, 4vw, 38px);
      line-height: 1.25;
      overflow-wrap: anywhere;
    }

    .note-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .note-tags {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .note-tags span {
      padding: 1px 8px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--accent) 14%, transparent);
      color: var(--accent);
    }

    .markdown-body {
      padding: 30px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow-wrap: anywhere;
    }

    .markdown-body > :first-child {
      margin-top: 0;
    }

    .markdown-body > :last-child {
      margin-bottom: 0;
    }

    .markdown-body h1,
    .markdown-body h2,
    .markdown-body h3,
    .markdown-body h4,
    .markdown-body h5,
    .markdown-body h6 {
      margin: 1.6em 0 0.6em;
      line-height: 1.35;
      scroll-margin-top: 20px;
    }

    .markdown-body h1 {
      color: var(--accent);
    }

    .markdown-body h2,
    .markdown-body h3 {
      padding-bottom: 0.28em;
      border-bottom: 1px solid var(--border);
    }

    .markdown-body p,
    .markdown-body ul,
    .markdown-body ol,
    .markdown-body blockquote,
    .markdown-body table,
    .markdown-body pre {
      margin: 0 0 1em;
    }

    .markdown-body li + li {
      margin-top: 0.28em;
    }

    .markdown-body a {
      color: var(--accent);
      text-decoration: none;
    }

    .markdown-body a:hover {
      text-decoration: underline;
    }

    .markdown-body img {
      display: block;
      max-width: 100%;
      height: auto;
      margin: 1.1em auto;
      border-radius: 10px;
    }

    .markdown-body blockquote {
      padding: 10px 16px;
      border-left: 4px solid var(--accent);
      border-radius: 0 8px 8px 0;
      background: var(--quote-bg);
      color: var(--muted);
    }

    .markdown-body code {
      padding: 0.15em 0.4em;
      border-radius: 5px;
      background: var(--code-bg);
      font-family: Consolas, "Cascadia Code", "SFMono-Regular", monospace;
      font-size: 0.9em;
    }

    .markdown-body pre {
      overflow: auto;
      padding: 16px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--code-bg);
    }

    .markdown-body pre code {
      display: block;
      padding: 0;
      background: transparent;
      white-space: pre;
    }

    .markdown-body table {
      display: block;
      width: 100%;
      overflow-x: auto;
      border-collapse: collapse;
    }

    .markdown-body th,
    .markdown-body td {
      padding: 8px 10px;
      border: 1px solid var(--border);
      text-align: left;
    }

    .markdown-body th {
      background: var(--code-bg);
    }

    .source-panel {
      margin-top: 20px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--surface);
    }

    .source-panel summary {
      padding: 12px 16px;
      cursor: pointer;
      color: var(--muted);
      font-weight: 600;
    }

    .source-panel pre {
      margin: 0;
      padding: 16px;
      overflow: auto;
      border-top: 1px solid var(--border);
      background: var(--code-bg);
    }

    .source-panel code {
      font-family: Consolas, "Cascadia Code", "SFMono-Regular", monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    @media (max-width: 640px) {
      .note-shell {
        padding: 24px 14px 50px;
      }

      .markdown-body {
        padding: 20px 16px;
        border-radius: 10px;
      }
    }

    @media print {
      body {
        background: #fff;
        color: #111;
      }

      .note-shell {
        width: 100%;
        padding: 0;
      }

      .markdown-body,
      .source-panel {
        border: 0;
        box-shadow: none;
      }

      .source-panel {
        display: none;
      }
    }
    """

    source_json = note_export_json(content)
    images_json = note_export_json(image_map)
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{html_escape(title)} · Error酱</title>\n"
        f"  <style>{css}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <main class="note-shell">\n'
        '    <header class="note-header">\n'
        f"      <h1>{html_escape(title)}</h1>\n"
        '      <div class="note-meta">\n'
        f'        <span class="note-tags">{tags_html}</span>\n'
        f"        <span>创建：{created_at}</span>\n"
        f"        <span>更新：{updated_at}</span>\n"
        f"        <span>导出：{generated_at}</span>\n"
        "      </div>\n"
        "    </header>\n"
        '    <article class="markdown-body" id="rendered"></article>\n'
        '    <details class="source-panel">\n'
        "      <summary>Markdown 源文（可在 VS Code 中阅读）</summary>\n"
        f"      <pre><code>{html_escape(content)}</code></pre>\n"
        "    </details>\n"
        "  </main>\n"
        f'  <script id="note-source" type="application/json">{source_json}</script>\n'
        f'  <script id="note-images" type="application/json">{images_json}</script>\n'
        f"  <script>{marked_script}</script>\n"
        f"  <script>{purify_script}</script>\n"
        "  <script>\n"
        "    (function () {\n"
        '      var source = JSON.parse(document.getElementById("note-source").textContent || "\\\"\\\"");\n'
        '      var images = JSON.parse(document.getElementById("note-images").textContent || "{}");\n'
        "      var renderedSource = source.replace(/\\/site-files\\/(note_images\\/[A-Za-z0-9._%+-]+)/g, function (match, path) {\n"
        "        var image = images[path];\n"
        "        if (!image && path.indexOf(\"%\") >= 0) {\n"
        "          try { image = images[decodeURIComponent(path)]; } catch (err) {}\n"
        "        }\n"
        "        return image || match;\n"
        "      });\n"
        "      if (window.marked && window.DOMPurify) {\n"
        "        marked.setOptions({ gfm: true, breaks: true });\n"
        '        document.getElementById("rendered").innerHTML = DOMPurify.sanitize(marked.parse(renderedSource));\n'
        '        document.querySelectorAll("#rendered a[href]").forEach(function (link) {\n'
        '          link.setAttribute("target", "_blank");\n'
        '          link.setAttribute("rel", "noopener noreferrer");\n'
        "        });\n"
        "      } else {\n"
        '        document.getElementById("rendered").textContent = source;\n'
        "      }\n"
        "    })();\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


def detect_image_type(raw):
    for magic, mime_type in NOTE_IMAGE_MAGIC:
        if raw.startswith(magic):
            return mime_type
    if len(raw) > 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def remove_data_file(relative):
    if not relative:
        return False
    try:
        full = (DATA_DIR / relative).resolve()
        full.relative_to(DATA_DIR.resolve())
    except (ValueError, OSError):
        return False
    if not full.is_file():
        return False
    try:
        full.unlink()
        return True
    except OSError:
        return False


def api_error(handler, status, message):
    handler.send_json(status, {"error": message})


GZIP_MIN_BYTES = 1024
GZIP_TYPES = (
    "text/",
    "application/javascript",
    "application/json",
    "application/xml",
    "image/svg+xml",
)


def file_etag(stat_result):
    """用修改时间 + 大小做 ETag，文件没变就能走 304，省掉重复下载。"""
    return f'"{int(stat_result.st_mtime)}-{stat_result.st_size}"'


def gzip_type_allowed(content_type):
    return any(content_type.startswith(item) for item in GZIP_TYPES)


def get_payload(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    if length > MAX_REQUEST_BYTES:
        remaining = length
        while remaining > 0:
            chunk = handler.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        api_error(handler, 413, "请求体过大，请压缩文件后再上传。")
        return None
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        api_error(handler, 400, "请求数据不是有效的 JSON。")
        return None



def hash_password(password, salt=None, iterations=AUTH_PBKDF2_ITERATIONS):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password_hash(password, stored):
    if not stored or not password:
        return False
    try:
        algorithm, iterations_text, salt, digest_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations_text)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def verify_password(password):
    return verify_password_hash(password, AUTH_STATE.get("password_hash") or "")


def valid_username(value):
    username = str(value or "").strip()
    if not USERNAME_RE.fullmatch(username):
        return ""
    if username.casefold() in RESERVED_USERNAMES:
        return ""
    return username


def load_auth_state():
    """密码来自环境变量 INVENTORY_PASSWORD，或 data/auth.json（tools/set_password.py 生成）。"""
    config = {}
    if AUTH_PATH.is_file():
        try:
            config = json.loads(AUTH_PATH.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            config = {}
    password_hash = str(config.get("password_hash") or "")
    env_password = os.environ.get("INVENTORY_PASSWORD") or ""
    if env_password:
        password_hash = hash_password(env_password)
    secret = os.environ.get("INVENTORY_SECRET") or str(config.get("secret") or "")
    if password_hash and not secret:
        secret = secrets.token_hex(32)
        config["secret"] = secret
        try:
            AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
            AUTH_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            os.chmod(AUTH_PATH, 0o600)
        except OSError:
            pass
    AUTH_STATE.update(
        {
            "enabled": bool(password_hash),
            "password_hash": password_hash,
            "secret": secret,
        }
    )
    return AUTH_STATE


def issue_session_token(days, identity):
    expires = int(time.time()) + int(days) * 86400
    kind = str(identity.get("kind") or "owner")
    user_id = int(identity.get("user_id") or 0)
    payload = f"v1|{kind}|{user_id}|{expires}"
    signature = hmac.new(
        str(AUTH_STATE.get("secret") or "").encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}|{signature}"


def verify_session_token(token):
    secret = str(AUTH_STATE.get("secret") or "")
    if not token or "|" not in token or not secret:
        return None
    parts = token.split("|")
    if len(parts) != 5:
        return None
    version, kind, user_id_text, expires_text, signature = parts
    if version != "v1" or kind not in ("owner", "member"):
        return None
    payload = "|".join(parts[:4])
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        expires = int(expires_text)
        user_id = int(user_id_text)
    except ValueError:
        return None
    if expires <= time.time():
        return None
    if kind == "owner" and user_id != 0:
        return None
    if kind == "member" and user_id <= 0:
        return None
    return {"kind": kind, "user_id": user_id, "expires": expires}


def rate_allow(bucket, identifier, limit, window_seconds):
    now = time.time()
    key = f"{bucket}:{identifier}"
    with RATE_LOCK:
        stamps = [item for item in RATE_LIMITS.get(key, []) if now - item < window_seconds]
        if len(stamps) >= limit:
            RATE_LIMITS[key] = stamps
            return False
        stamps.append(now)
        RATE_LIMITS[key] = stamps
        if len(RATE_LIMITS) > 5000:
            RATE_LIMITS.clear()
        return True


def login_blocked(identifier):
    now = time.time()
    with RATE_LOCK:
        stamps = [item for item in LOGIN_FAILURES.get(identifier, []) if now - item < 300]
        LOGIN_FAILURES[identifier] = stamps
        return len(stamps) >= 5


def login_failed(identifier):
    with RATE_LOCK:
        LOGIN_FAILURES.setdefault(identifier, []).append(time.time())


def login_succeeded(identifier):
    with RATE_LOCK:
        LOGIN_FAILURES.pop(identifier, None)


def safe_next_path(value):
    """只允许站内跳转，挡掉 //evil.com 这类开放重定向。"""
    text = str(value or "")
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return "/"
    return text


class InventoryHandler(BaseHTTPRequestHandler):
    server_version = "ElectroStock/1.0"
    # 用 HTTP/1.1 才能复用连接：一个页面要拉十来个 css/js/图片，
    # HTTP/1.0 每次都要重新握手，带宽小或延迟高的链路上很吃亏。
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if ACCESS_LOG:
            print(f"[{now_text()}] {self.client_address[0]} {fmt % args}", flush=True)
        return

    # ---------- 登录态 ----------
    def cookies(self):
        jar = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                name, _, value = part.partition("=")
                jar[name.strip()] = value.strip()
        return jar

    def session_identity(self):
        if not AUTH_STATE.get("enabled"):
            return {
                "kind": "owner",
                "user_id": 0,
                "username": "本地模式",
                "role": "owner",
            }
        claims = verify_session_token(self.cookies().get(AUTH_COOKIE, ""))
        if not claims:
            return None
        if claims["kind"] == "owner":
            return {
                "kind": "owner",
                "user_id": 0,
                "username": "管理员",
                "role": "owner",
            }
        row = query_one(
            "SELECT id, username, status FROM users WHERE id = ?",
            (claims["user_id"],),
        )
        if not row or row.get("status") != "approved":
            return None
        return {
            "kind": "member",
            "user_id": row["id"],
            "username": row["username"],
            "role": "member",
        }

    def session_valid(self):
        return self.session_identity() is not None

    def is_owner(self):
        identity = self.session_identity()
        return bool(identity and identity.get("kind") == "owner")

    def client_ip(self):
        if TRUST_PROXY:
            forwarded = self.headers.get("X-Forwarded-For") or ""
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        return self.client_address[0] if self.client_address else "unknown"

    def redirect(self, location, status=302):
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def session_cookie_value(self, token, max_age):
        secure = FORCE_SECURE_COOKIES or (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"
        cookie = f"{AUTH_COOKIE}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax"
        if secure:
            cookie += "; Secure"
        return cookie

    def origin_allowed(self):
        """同源校验：带 Origin 的写请求必须和本站一致，防 CSRF。"""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host") or ""
        parsed = urlsplit(origin)
        return bool(parsed.netloc) and parsed.netloc == host

    def public_request_allowed(self, path, method):
        if path.startswith("/static/"):
            return True
        if path.startswith("/site-files/"):
            relative = unquote(path[len("/site-files/") :])
            if relative.startswith(PUBLIC_DATA_PREFIXES):
                return True
        if method == "GET":
            if path in PUBLIC_PAGES or path.startswith("/games/"):
                return True
            if path in PUBLIC_GET_APIS:
                return True
        if method == "POST" and path in PUBLIC_POST_APIS:
            return True
        return False

    def member_request_allowed(self, path, method):
        if method != "GET":
            return False
        if path in MEMBER_PAGE_PATHS or path in MEMBER_GET_APIS:
            return True
        if path.startswith(MEMBER_GET_PREFIXES):
            return not path.startswith("/api/bookmarks/firefox/")
        if path.startswith("/site-files/"):
            relative = unquote(path[len("/site-files/") :])
            return relative.startswith(MEMBER_DATA_PREFIXES)
        return False

    def guard_request(self, path, method):
        """返回 True 表示请求可以继续处理。"""
        if method in ("POST", "PATCH", "DELETE") and path != "/api/login":
            if AUTH_STATE.get("enabled") and not self.origin_allowed():
                api_error(self, 403, "请求来源不合法。")
                return False
            if not rate_allow("write", self.client_ip(), 120, 60):
                api_error(self, 429, "操作过于频繁，请稍后再试。")
                return False
        if not AUTH_STATE.get("enabled"):
            return True
        if self.public_request_allowed(path, method):
            return True
        identity = self.session_identity()
        if identity and identity.get("kind") == "owner":
            return True
        if identity and self.member_request_allowed(path, method):
            return True
        if identity:
            if path.startswith("/api/") or path.startswith("/site-files/"):
                api_error(self, 403, "当前账号没有访问权限。")
            else:
                self.redirect("/?access=owner-only")
            return False
        if path.startswith("/api/") or path.startswith("/site-files/"):
            api_error(self, 401, "请先登录。")
        else:
            target = path if path.startswith("/") else "/"
            self.redirect(f"/login?next={quote(target)}")
        return False

    def api_auth_status(self):
        enabled = bool(AUTH_STATE.get("enabled"))
        identity = self.session_identity()
        self.send_json(
            200,
            {
                "enabled": enabled,
                "authenticated": identity is not None,
                "role": identity.get("role") if identity else "guest",
                "username": identity.get("username") if identity else "",
                "owner": bool(identity and identity.get("kind") == "owner"),
            },
        )

    def api_login(self, payload):
        identifier = self.client_ip()
        if login_blocked(identifier):
            api_error(self, 429, "密码错误次数过多，请 5 分钟后再试。")
            return
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if username:
            user = query_one(
                "SELECT id, username, password_hash, status FROM users WHERE username = ?",
                (username,),
            )
            if not user:
                login_failed(identifier)
                api_error(self, 401, "用户名或密码不正确。")
                return
            if user.get("status") != "approved":
                status_text = {
                    "pending": "账号正在等待管理员审核。",
                    "rejected": "账号申请未通过。",
                    "disabled": "账号已被停用。",
                }.get(user.get("status"), "账号当前不可用。")
                api_error(self, 403, status_text)
                return
            if not verify_password_hash(password, user.get("password_hash")):
                login_failed(identifier)
                api_error(self, 401, "用户名或密码不正确。")
                return
            identity = {
                "kind": "member",
                "user_id": user["id"],
                "username": user["username"],
                "role": "member",
            }
            execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now_text(), now_text(), user["id"]),
            )
        else:
            if not verify_password(password):
                login_failed(identifier)
                api_error(self, 401, "管理员密码不正确。")
                return
            identity = {
                "kind": "owner",
                "user_id": 0,
                "username": "管理员",
                "role": "owner",
            }
        login_succeeded(identifier)
        days = AUTH_SESSION_DAYS_REMEMBER if payload.get("remember") else AUTH_SESSION_DAYS
        token = issue_session_token(days, identity)
        self.send_json(
            200,
            {
                "ok": True,
                "days": days,
                "role": identity["role"],
                "username": identity["username"],
            },
            headers=[("Set-Cookie", self.session_cookie_value(token, days * 86400))],
        )

    def api_register(self, payload):
        if not rate_allow("register", self.client_ip(), 5, 3600):
            api_error(self, 429, "注册请求太频繁，请稍后再试。")
            return
        username = valid_username(payload.get("username"))
        password = str(payload.get("password") or "")
        if not username:
            api_error(self, 400, "用户名需为 3-32 位，只能包含文字、字母、数字、点、下划线或短横线。")
            return
        if len(password) < 8 or len(password) > 128:
            api_error(self, 400, "密码长度需为 8-128 位。")
            return
        if query_one("SELECT id FROM users WHERE username = ?", (username,)):
            api_error(self, 409, "用户名已存在。")
            return
        stamp = now_text()
        execute(
            """
            INSERT INTO users
                (username, password_hash, status, role, created_at, updated_at)
            VALUES (?, ?, 'pending', 'member', ?, ?)
            """,
            (username, hash_password(password), stamp, stamp),
        )
        self.send_json(201, {"ok": True, "status": "pending"})

    def api_logout(self):
        self.send_json(
            200,
            {"ok": True},
            headers=[("Set-Cookie", self.session_cookie_value("", 0))],
        )

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in headers or []:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def send_file(self, path):
        if not STATIC_DIR.is_dir():
            self.send_error(404)
            return
        try:
            full = (STATIC_DIR / path).resolve()
            full.relative_to(STATIC_DIR.resolve())
        except (ValueError, OSError):
            self.send_error(403)
            return
        if not full.is_file():
            self.send_error(404)
            return
        try:
            stat_result = full.stat()
        except OSError:
            self.send_error(404)
            return
        etag = file_etag(stat_result)
        # 内容没变直接回 304：带宽小（比如 3Mbps 云服务器）时这是最划算的优化。
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        content_type = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
        body = full.read_bytes()
        encoding = self.maybe_gzip(body, content_type)
        if encoding:
            body = encoding[1]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", etag)
        if encoding:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

    def maybe_gzip(self, body, content_type):
        """文本类资源按需压缩，返回 (True, 压缩后字节) 或 None。"""
        if len(body) < GZIP_MIN_BYTES or not gzip_type_allowed(content_type):
            return None
        if "gzip" not in (self.headers.get("Accept-Encoding") or "").lower():
            return None
        compressed = gzip.compress(body, 6)
        if len(compressed) >= len(body):
            return None
        return True, compressed

    def send_site(self, page="home", desc="页面还没有建好，Error酱 正在努力搬砖，敬请期待。"):
        template = STATIC_DIR / "site" / "site.html"
        if not template.is_file():
            self.send_error(404)
            return
        html = template.read_text(encoding="utf-8")
        html = html.replace("</body>", f'<script>document.body.setAttribute("data-page", "{page}");</script></body>')
        html = html.replace('id="ucDesc">页面还没有建好，Error酱 正在努力搬砖，敬请期待。', f'id="ucDesc">{desc}')
        body = html.encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def send_csv(self, status, text, download_name):
        body = text.encode("utf-8")
        encoded_name = quote(download_name)
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if path == "/login":
            if not AUTH_STATE.get("enabled") or self.session_valid():
                self.redirect(safe_next_path((query.get("next") or ["/"])[0]))
                return
            self.send_file("login.html")
            return
        if path == "/register":
            self.send_file("register.html")
            return
        if path == "/logout":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", self.session_cookie_value("", 0))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not self.guard_request(path, "GET"):
            return
        try:
            if path in ("/", "/index.html"):
                self.send_site("home")
            elif path == "/inventory":
                self.send_file("index.html")
            elif path == "/bookmarks":
                self.send_file("bookmarks.html")
            elif path == "/notes":
                self.send_file("notes.html")
            elif path == "/messages":
                self.send_file("messages.html")
            elif path == "/workbench":
                self.send_file("workbench.html")
            elif path == "/references":
                self.send_file("references.html")
            elif path == "/moments":
                self.send_file("moments.html")
            elif path == "/prompts":
                self.send_file("prompts.html")
            elif path == "/games/gomoku":
                self.send_file("games/caro/index.html")
            elif path == "/games":
                self.send_file("games/index.html")
            elif path == "/games/2048":
                self.send_file("games/2048/index.html")
            elif path == "/games/minesweeper":
                self.send_file("games/minesweeper/index.html")
            elif path == "/games/memory":
                self.send_file("games/memory/index.html")
            elif path == "/favicon.ico":
                self.send_file("site/error-chan-favicon.png")
            elif path.startswith("/static/"):
                self.send_file(path[len("/static/") :])
            elif path.startswith("/site-files/"):
                self.send_data_file(path[len("/site-files/") :])
            elif path == "/api/health":
                self.send_json(200, {"ok": True})
            elif path == "/api/auth/status":
                self.api_auth_status()
            elif path == "/api/dashboard":
                self.api_dashboard()
            elif path == "/api/categories":
                self.api_categories()
            elif path == "/api/locations":
                self.api_locations()
            elif path == "/api/projects":
                self.api_projects()
            elif path == "/api/parts":
                self.api_parts(query)
            elif path == "/api/inventory":
                self.api_inventory(query)
            elif path == "/api/movements":
                self.api_movements(query)
            elif path == "/api/wishlist":
                self.api_wishlist()
            elif path == "/api/site/messages":
                self.api_site_messages(query)
            elif path == "/api/moments":
                self.api_moments(query)
            elif path == "/api/site/photos":
                self.api_site_photos(query)
            elif path == "/api/site/music":
                self.api_site_music(query)
            elif path == "/api/site/links":
                self.api_site_links(query)
            elif path == "/api/prompts":
                self.api_prompts(query)
            elif path == "/api/notes":
                self.api_notes(query)
            elif re.fullmatch(r"/api/notes/\d+/export\.html", path):
                self.api_note_export(path)
            elif path == "/api/workbench/summary":
                self.api_workbench_summary()
            elif path == "/api/workbench/assets":
                self.api_workbench_assets(query)
            elif path == "/api/workbench/repairs":
                self.api_workbench_repairs(query)
            elif path == "/api/bookmarks":
                self.api_bookmarks(query)
            elif path == "/api/bookmark-folders":
                self.api_bookmark_folders()
            elif path == "/api/bookmarks/firefox/profiles":
                self.api_firefox_bookmark_profiles()
            elif path == "/api/bookmarks/check-links":
                self.api_bookmark_check_status()
            elif path == "/api/warehouse/types":
                self.api_warehouse_types()
            elif path == "/api/bom/reports":
                self.api_bom_reports()
            elif path == "/api/bom/watch":
                self.api_bom_watch_status()
            elif re.fullmatch(r"/api/bom/reports/[A-Za-z0-9_]+/csv", path):
                self.api_bom_report_csv(path)
            elif re.fullmatch(r"/api/bom/reports/[A-Za-z0-9_]+", path):
                self.api_bom_report(path)
            elif re.fullmatch(r"/api/parts/\d+/image", path):
                self.api_part_image(path)
            elif re.fullmatch(r"/api/workbench/assets/\d+/download", path):
                self.api_workbench_asset_download(path)
            elif re.fullmatch(r"/api/bookmarks/\d+/favicon", path):
                self.api_bookmark_favicon(path)
            elif re.fullmatch(r"/api/parts/\d+", path):
                self.api_part_item(path)
            else:
                api_error(self, 404, "接口不存在。")
        except Exception as exc:
            api_error(self, 500, f"服务器错误：{exc}")

    def do_POST(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if not self.guard_request(path, "POST"):
            return
        try:
            payload = get_payload(self)
            if payload is None:
                return
            if path == "/api/login":
                self.api_login(payload)
            elif path == "/api/register":
                self.api_register(payload)
            elif path == "/api/logout":
                self.api_logout()
            elif path == "/api/categories":
                self.api_create_category(payload)
            elif path == "/api/locations":
                self.api_create_location(payload)
            elif path == "/api/projects":
                self.api_create_project(payload)
            elif path == "/api/parts":
                self.api_create_part(payload)
            elif path == "/api/stock/inbound":
                self.api_stock_inbound(payload)
            elif path == "/api/stock/outbound":
                self.api_stock_outbound(payload)
            elif path == "/api/wishlist":
                self.api_create_wishlist(payload)
            elif path == "/api/site/messages":
                self.api_site_message_create(payload)
            elif path == "/api/moments":
                self.api_moment_create(payload)
            elif path == "/api/site/photos":
                self.api_site_photo_upload(payload)
            elif path == "/api/site/music":
                self.api_site_music_create(payload)
            elif path == "/api/site/music/upload":
                self.api_site_music_upload(payload)
            elif path == "/api/site/links":
                self.api_site_link_create(payload)
            elif path == "/api/prompts":
                self.api_prompt_create(payload)
            elif path == "/api/notes":
                self.api_note_create(payload)
            elif path == "/api/notes/import":
                self.api_note_import(payload)
            elif path == "/api/notes/images":
                self.api_note_image_upload(payload)
            elif path == "/api/workbench/assets":
                self.api_workbench_asset_upload(payload)
            elif path == "/api/workbench/repairs":
                self.api_workbench_repair_create(payload)
            elif path == "/api/bookmarks":
                self.api_bookmark_create(payload)
            elif path == "/api/bookmarks/reorder":
                self.api_bookmark_reorder(payload)
            elif re.fullmatch(r"/api/bookmarks/\d+/mark-valid", path):
                self.api_bookmark_mark_valid(path)
            elif path == "/api/bookmark-folders":
                self.api_bookmark_folder_create(payload)
            elif path == "/api/bookmark-folders/reorder":
                self.api_bookmark_folder_reorder(payload)
            elif path == "/api/bookmarks/firefox/import":
                self.api_import_firefox_bookmarks(payload)
            elif path == "/api/bookmarks/check-links":
                self.api_start_bookmark_link_check(payload)
            elif re.fullmatch(r"/api/wishlist/\d+/convert", path):
                self.api_convert_wishlist(path, payload)
            elif re.fullmatch(r"/api/parts/\d+/image", path):
                self.api_part_image_upload(path, payload)
            elif path == "/api/import/lcsc":
                self.api_import_lcsc(payload)
            elif path == "/api/bom/compare":
                self.api_bom_compare(payload)
            elif path == "/api/bom/watch":
                self.api_bom_watch_start(payload)
            elif path == "/api/bom/watch/stop":
                self.api_bom_watch_stop()
            else:
                api_error(self, 404, "接口不存在。")
        except Exception as exc:
            api_error(self, 500, f"服务器错误：{exc}")

    def do_PATCH(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if not self.guard_request(path, "PATCH"):
            return
        try:
            if re.fullmatch(r"/api/categories/\d+", path):
                self.api_category_item(path)
            elif re.fullmatch(r"/api/locations/\d+", path):
                self.api_location_item(path)
            elif re.fullmatch(r"/api/projects/\d+", path):
                self.api_project_item(path)
            elif re.fullmatch(r"/api/parts/\d+", path):
                self.api_part_item(path)
            elif re.fullmatch(r"/api/wishlist/\d+", path):
                self.api_wishlist_item(path)
            elif re.fullmatch(r"/api/movements/\d+", path):
                self.api_movement_item(path)
            elif re.fullmatch(r"/api/bookmarks/\d+", path):
                self.api_bookmark_item(path)
            elif re.fullmatch(r"/api/notes/\d+", path):
                self.api_note_item(path)
            elif re.fullmatch(r"/api/moments/\d+", path):
                self.api_moment_item(path)
            elif re.fullmatch(r"/api/workbench/assets/\d+", path):
                self.api_workbench_asset_item(path)
            elif re.fullmatch(r"/api/workbench/repairs/\d+", path):
                self.api_workbench_repair_item(path)
            elif re.fullmatch(r"/api/bookmark-folders/\d+", path):
                self.api_bookmark_folder_item(path)
            elif re.fullmatch(r"/api/prompts/\d+", path):
                self.api_prompt_item(path)
            else:
                api_error(self, 404, "接口不存在。")
        except Exception as exc:
            api_error(self, 500, f"服务器错误：{exc}")

    def do_DELETE(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if not self.guard_request(path, "DELETE"):
            return
        try:
            if re.fullmatch(r"/api/categories/\d+", path):
                self.api_category_item(path)
            elif re.fullmatch(r"/api/locations/\d+", path):
                self.api_location_item(path)
            elif re.fullmatch(r"/api/projects/\d+", path):
                self.api_project_item(path)
            elif re.fullmatch(r"/api/parts/\d+/image", path):
                self.api_part_image_delete(path)
            elif re.fullmatch(r"/api/parts/\d+", path):
                self.api_part_item(path)
            elif re.fullmatch(r"/api/wishlist/\d+", path):
                self.api_wishlist_item(path)
            elif re.fullmatch(r"/api/movements/\d+", path):
                self.api_movement_item(path)
            elif re.fullmatch(r"/api/bookmarks/\d+", path):
                self.api_bookmark_item(path)
            elif re.fullmatch(r"/api/bookmark-folders/\d+", path):
                self.api_bookmark_folder_item(path)
            elif re.fullmatch(r"/api/site/messages/\d+", path):
                self.api_site_message_delete(path)
            elif re.fullmatch(r"/api/moments/\d+", path):
                self.api_moment_item(path)
            elif re.fullmatch(r"/api/site/photos/\d+", path):
                self.api_site_photo_delete(path)
            elif re.fullmatch(r"/api/site/music/\d+", path):
                self.api_site_music_delete(path)
            elif re.fullmatch(r"/api/site/links/\d+", path):
                self.api_site_link_delete(path)
            elif re.fullmatch(r"/api/prompts/\d+", path):
                self.api_prompt_item(path)
            elif re.fullmatch(r"/api/notes/images/\d+", path):
                self.api_note_image_delete(path)
            elif re.fullmatch(r"/api/notes/\d+", path):
                self.api_note_item(path)
            elif re.fullmatch(r"/api/workbench/assets/\d+", path):
                self.api_workbench_asset_item(path)
            elif re.fullmatch(r"/api/workbench/repairs/\d+", path):
                self.api_workbench_repair_item(path)
            else:
                api_error(self, 404, "接口不存在。")
        except Exception as exc:
            api_error(self, 500, f"服务器错误：{exc}")

    def api_dashboard(self):
        stats = {
            "part_count": query_one("SELECT COUNT(*) AS n FROM parts")["n"],
            "stock_quantity": query_one(
                "SELECT COALESCE(SUM(quantity), 0) AS n FROM batches"
            )["n"],
            "used_quantity": query_one(
                "SELECT COALESCE(SUM(received_quantity - quantity), 0) AS n FROM batches"
            )["n"],
            "wishlist_count": query_one(
                "SELECT COUNT(*) AS n FROM wishlist_items WHERE status = 'open'"
            )["n"],
            "project_count": query_one("SELECT COUNT(*) AS n FROM projects")["n"],
        }
        low_stock = query(
            """
            SELECT p.id, p.part_number, p.lcsc_code, p.package, p.min_stock,
                   COALESCE((SELECT SUM(b.quantity) FROM batches b WHERE b.part_id = p.id), 0) AS stock_quantity
            FROM parts p
            WHERE p.min_stock > 0
              AND COALESCE((SELECT SUM(b.quantity) FROM batches b WHERE b.part_id = p.id), 0) <= p.min_stock
            ORDER BY stock_quantity ASC, p.part_number ASC
            LIMIT 12
            """
        )
        recent = self.movement_rows(limit=8)
        self.send_json(
            200,
            {
                "stats": stats,
                "low_stock": low_stock,
                "recent_movements": recent,
            },
        )

    def api_categories(self):
        rows = query(
            """
            SELECT c.*,
                   (SELECT COUNT(*) FROM parts p WHERE p.category_id = c.id) AS part_count
            FROM categories c
            ORDER BY c.sort_order, c.id
            """
        )
        for row in rows:
            row["path"] = path_text("categories", row["id"])
        self.send_json(200, rows)

    def api_create_category(self, payload):
        name = str(payload.get("name") or "").strip()
        if not name:
            api_error(self, 400, "分类名称不能为空。")
            return
        parent_id = payload.get("parent_id")
        if parent_id is not None:
            parent = query_one("SELECT id FROM categories WHERE id = ?", (parent_id,))
            if not parent:
                api_error(self, 400, "父分类不存在。")
                return
        sort_order = int(payload.get("sort_order") or 0)
        new_id = execute(
            "INSERT INTO categories (name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (name, parent_id, sort_order, now_text()),
        )
        self.send_json(201, {"id": new_id})

    def api_category_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        if self.command == "DELETE":
            category = query_one("SELECT * FROM categories WHERE id = ?", (item_id,))
            if not category:
                api_error(self, 404, "分类不存在。")
                return
            execute("DELETE FROM categories WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        name = str(payload.get("name") or "").strip()
        if not name:
            api_error(self, 400, "分类名称不能为空。")
            return
        execute(
            "UPDATE categories SET name = ?, parent_id = ?, sort_order = ? WHERE id = ?",
            (name, payload.get("parent_id"), int(payload.get("sort_order") or 0), item_id),
        )
        self.send_json(200, {"ok": True})

    def api_locations(self):
        rows = query(
            """
            SELECT l.*,
                   (SELECT COUNT(*) FROM batches b WHERE b.location_id = l.id) AS batch_count
            FROM locations l
            ORDER BY l.sort_order, l.code, l.id
            """
        )
        for row in rows:
            row["path"] = path_text("locations", row["id"], "code")
        self.send_json(200, rows)

    def api_create_location(self, payload):
        code = str(payload.get("code") or "").strip().upper()
        if not code:
            api_error(self, 400, "位置代码不能为空。")
            return
        parent_id = payload.get("parent_id")
        sort_order = int(payload.get("sort_order") or 0)
        new_id = execute(
            "INSERT INTO locations (code, name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
            (code, payload.get("name") or code, parent_id, sort_order, now_text()),
        )
        self.send_json(201, {"id": new_id})

    def api_location_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        if self.command == "DELETE":
            location = query_one("SELECT * FROM locations WHERE id = ?", (item_id,))
            if not location:
                api_error(self, 404, "位置不存在。")
                return
            children = query_one(
                "SELECT COUNT(*) AS n FROM locations WHERE parent_id = ?", (item_id,)
            )["n"]
            batches = query_one(
                "SELECT COUNT(*) AS n FROM batches WHERE location_id = ?", (item_id,)
            )["n"]
            if children or batches:
                api_error(self, 400, "该位置下还有子位置或库存，不能删除。")
                return
            execute("DELETE FROM locations WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        code = str(payload.get("code") or "").strip().upper()
        if not code:
            api_error(self, 400, "位置代码不能为空。")
            return
        execute(
            "UPDATE locations SET code = ?, name = ?, parent_id = ?, sort_order = ? WHERE id = ?",
            (code, payload.get("name") or code, payload.get("parent_id"), int(payload.get("sort_order") or 0), item_id),
        )
        self.send_json(200, {"ok": True})

    def api_projects(self):
        rows = query(
            """
            SELECT pr.*,
                   (SELECT COALESCE(SUM(m.quantity), 0) FROM movements m
                    WHERE m.project_id = pr.id AND m.movement_type = 'out') AS used_quantity,
                   (SELECT COUNT(DISTINCT m.part_id) FROM movements m
                    WHERE m.project_id = pr.id AND m.movement_type = 'out') AS part_count
            FROM projects pr
            ORDER BY pr.status = 'active' DESC, pr.created_at DESC
            """
        )
        self.send_json(200, rows)

    def api_create_project(self, payload):
        name = str(payload.get("name") or "").strip()
        if not name:
            api_error(self, 400, "项目名称不能为空。")
            return
        bom_preview = None
        bom_data_base64 = payload.get("bom_data_base64") or ""
        if bom_data_base64:
            try:
                data = base64.b64decode(bom_data_base64)
            except Exception as exc:
                api_error(self, 400, "BOM 文件内容无法解码。")
                return
            try:
                file_name = str(payload.get("bom_file_name") or "BOM.csv")
                match_mode = str(payload.get("match_mode") or "auto")
                if match_mode not in ("auto", "part_number", "lcsc_code", "description"):
                    match_mode = "auto"
                rows = parse_bom_rows(data, file_name)
                items = extract_bom_items(rows)
                if not items:
                    raise ValueError("BOM 中没有可处理的数据行。")
                report = compare_bom_items(items, match_mode)
                bom_preview = (file_name, match_mode, report)
            except ValueError as exc:
                api_error(self, 400, str(exc))
                return
        new_id = execute(
            "INSERT INTO projects (name, description, status, created_at) VALUES (?, ?, ?, ?)",
            (name, payload.get("description") or "", payload.get("status") or "active", now_text()),
        )
        bom_report_info = None
        if bom_preview:
            file_name, match_mode, report = bom_preview
            report_id, saved = save_bom_report(
                file_name,
                "",
                report,
                match_mode,
                project_id=new_id,
                project_name=name,
            )
            bom_report_info = {
                "id": report_id,
                "file_name": file_name,
                "summary": saved["summary"],
            }
        self.send_json(201, {"id": new_id, "bom_report": bom_report_info})

    def api_project_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        if self.command == "DELETE":
            execute("DELETE FROM projects WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        name = str(payload.get("name") or "").strip()
        if not name:
            api_error(self, 400, "项目名称不能为空。")
            return
        execute(
            "UPDATE projects SET name = ?, description = ?, status = ? WHERE id = ?",
            (name, payload.get("description") or "", payload.get("status") or "active", item_id),
        )
        self.send_json(200, {"ok": True})

    def api_parts(self, query_params):
        search = str(query_params.get("search", [""])[0]).strip()
        category_id = query_params.get("category_id", [""])[0]
        conditions = []
        params = []
        if search:
            conditions.append(
                """(p.part_number LIKE ? OR p.lcsc_code LIKE ? OR p.brand LIKE ?
                    OR p.description LIKE ? OR p.package LIKE ?)"""
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like])
        if category_id:
            try:
                root_id = int(category_id)
            except ValueError:
                root_id = None
            if root_id:
                cat_ids = query(
                    """WITH RECURSIVE cat_tree(id) AS (
                           SELECT ? UNION ALL
                           SELECT c.id FROM categories c JOIN cat_tree t ON c.parent_id = t.id
                       )
                       SELECT id FROM cat_tree""",
                    (root_id,),
                )
                ids = [row["id"] for row in cat_ids]
                if ids:
                    conditions.append(f"p.category_id IN ({','.join('?' * len(ids))})")
                    params.extend(ids)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = query(
            part_summary_select() + f" {where} ORDER BY p.updated_at DESC, p.id DESC",
            params,
        )
        self.send_json(200, rows)

    def api_create_part(self, payload):
        part_number = str(payload.get("part_number") or "").strip()
        lcsc_code = str(payload.get("lcsc_code") or "").strip() or None
        if not part_number and not lcsc_code:
            api_error(self, 400, "至少填写厂家型号或 LCSC 编号。")
            return
        stock_quantity = None
        if payload.get("stock_quantity") not in (None, ""):
            try:
                stock_quantity = float(payload["stock_quantity"])
            except (TypeError, ValueError):
                api_error(self, 400, "库存数量格式不正确。")
                return
            if stock_quantity < 0:
                api_error(self, 400, "库存数量不能小于 0。")
                return
        location_id = payload.get("location_id")
        if stock_quantity and not location_id:
            api_error(self, 400, "填写库存数量后请选择库存位置。")
            return
        if location_id:
            location = query_one("SELECT id FROM locations WHERE id = ?", (location_id,))
            if not location:
                api_error(self, 400, "库存位置不存在。")
                return
        project_id = payload.get("project_id")
        if project_id:
            project = query_one("SELECT id FROM projects WHERE id = ?", (project_id,))
            if not project:
                api_error(self, 400, "关联项目不存在。")
                return
        try:
            new_id = execute(
                """INSERT INTO parts
                   (part_number, lcsc_code, brand, category_id, package, temperature_range,
                    voltage_rating, description, datasheet_url, notes, min_stock, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    part_number or lcsc_code,
                    lcsc_code,
                    payload.get("brand") or None,
                    payload.get("category_id"),
                    payload.get("package") or None,
                    payload.get("temperature_range") or "",
                    payload.get("voltage_rating") or "",
                    payload.get("description") or None,
                    payload.get("datasheet_url") or None,
                    payload.get("notes") or None,
                    float(payload.get("min_stock") or 0),
                    now_text(),
                    now_text(),
                ),
            )
        except sqlite3.IntegrityError:
            api_error(self, 400, "LCSC 编号已存在，请改用导入或编辑。")
            return
        if stock_quantity:
            transaction(
                lambda conn: self.insert_batch(
                    conn,
                    part_id=new_id,
                    location_id=location_id,
                    quantity=stock_quantity,
                    purchase_date=today_text(),
                    unit_price=None,
                    channel="",
                    order_number="",
                    notes="详情页初始化库存",
                )
            )
        if project_id:
            execute(
                "INSERT OR REPLACE INTO part_projects (part_id, project_id, created_at) VALUES (?, ?, ?)",
                (new_id, project_id, now_text()),
            )
        self.send_json(201, {"id": new_id})

    def api_part_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        if self.command == "DELETE":
            execute("DELETE FROM parts WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return
        if self.command == "GET":
            part = query_one(part_summary_select() + " WHERE p.id = ?", (item_id,))
            if not part:
                api_error(self, 404, "元件不存在。")
                return
            batches = query(
                """SELECT b.*, l.code AS location_code, l.name AS location_name
                   FROM batches b JOIN locations l ON l.id = b.location_id
                   WHERE b.part_id = ? ORDER BY b.created_at DESC, b.id DESC""",
                (item_id,),
            )
            usage = query(
                """SELECT pr.id, pr.name, pr.status,
                          COALESCE(SUM(m.quantity), 0) AS used_quantity,
                          COUNT(m.id) AS times
                   FROM movements m JOIN projects pr ON pr.id = m.project_id
                   WHERE m.part_id = ? AND m.movement_type = 'out'
                   GROUP BY pr.id, pr.name, pr.status
                   ORDER BY used_quantity DESC""",
                (item_id,),
            )
            linked_projects = query(
                """SELECT pr.id, pr.name, pr.status
                   FROM part_projects pp
                   JOIN projects pr ON pr.id = pp.project_id
                   WHERE pp.part_id = ?
                   ORDER BY pr.name""",
                (item_id,),
            )
            movements = self.movement_rows(part_id=item_id, limit=50)
            self.send_json(
                200,
                {
                    "part": part,
                    "batches": batches,
                    "project_usage": usage,
                    "linked_projects": linked_projects,
                    "movements": movements,
                },
            )
            return
        payload = get_payload(self)
        if payload is None:
            return
        part_number = str(payload.get("part_number") or "").strip()
        lcsc_code = str(payload.get("lcsc_code") or "").strip() or None
        if not part_number and not lcsc_code:
            api_error(self, 400, "至少填写厂家型号或 LCSC 编号。")
            return
        location_id = payload.get("location_id")
        if location_id:
            location = query_one("SELECT id FROM locations WHERE id = ?", (location_id,))
            if not location:
                api_error(self, 400, "库存位置不存在。")
                return
        project_id = payload.get("project_id")
        if project_id:
            project = query_one("SELECT id FROM projects WHERE id = ?", (project_id,))
            if not project:
                api_error(self, 400, "关联项目不存在。")
                return

        new_stock = None
        if payload.get("stock_quantity") not in (None, ""):
            try:
                new_stock = float(payload["stock_quantity"])
            except (TypeError, ValueError):
                api_error(self, 400, "库存数量格式不正确。")
                return
            if new_stock < 0:
                api_error(self, 400, "库存数量不能小于 0。")
                return

        def run(conn):
            conn.execute(
                """UPDATE parts SET
                   part_number = ?, lcsc_code = ?, brand = ?, category_id = ?, package = ?,
                   temperature_range = ?, voltage_rating = ?, description = ?, datasheet_url = ?,
                   notes = ?, min_stock = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    part_number or lcsc_code,
                    lcsc_code,
                    payload.get("brand") or None,
                    payload.get("category_id"),
                    payload.get("package") or None,
                    payload.get("temperature_range") or "",
                    payload.get("voltage_rating") or "",
                    payload.get("description") or None,
                    payload.get("datasheet_url") or None,
                    payload.get("notes") or None,
                    float(payload.get("min_stock") or 0),
                    now_text(),
                    item_id,
                ),
            )
            if location_id:
                conn.execute(
                    "UPDATE batches SET location_id = ? WHERE part_id = ?",
                    (location_id, item_id),
                )
            if "project_id" in payload:
                conn.execute("DELETE FROM part_projects WHERE part_id = ?", (item_id,))
                if project_id:
                    conn.execute(
                        "INSERT OR REPLACE INTO part_projects (part_id, project_id, created_at) VALUES (?, ?, ?)",
                        (item_id, project_id, now_text()),
                    )
            if new_stock is not None:
                current = conn.execute(
                    "SELECT COALESCE(SUM(quantity), 0) AS total FROM batches WHERE part_id = ?",
                    (item_id,),
                ).fetchone()["total"]
                delta = new_stock - float(current or 0)
                if delta > 0:
                    target_location = location_id
                    if not target_location:
                        row = conn.execute(
                            "SELECT location_id FROM batches WHERE part_id = ? ORDER BY id LIMIT 1",
                            (item_id,),
                        ).fetchone()
                        if not row:
                            raise ValueError("增加库存前请选择库存位置。")
                        target_location = row["location_id"]
                    self.insert_batch(
                        conn,
                        part_id=item_id,
                        location_id=target_location,
                        quantity=delta,
                        purchase_date=today_text(),
                        unit_price=None,
                        channel="",
                        order_number="",
                        notes="详情页库存调整",
                    )
                elif delta < 0:
                    self.consume_batches(
                        conn,
                        part_id=item_id,
                        batch_id=None,
                        quantity=-delta,
                        project_id=project_id,
                        note="详情页库存调整",
                    )

        try:
            transaction(run)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        except sqlite3.IntegrityError:
            api_error(self, 400, "LCSC 编号已存在。")
            return
        self.send_json(200, {"ok": True})

    def api_part_image(self, path):
        part_id = int(path.split("/")[3])
        part = query_one("SELECT image_path FROM parts WHERE id = ?", (part_id,))
        if not part or not part.get("image_path"):
            api_error(self, 404, "该元件还没有图片。")
            return
        try:
            full = (DATA_DIR / part["image_path"]).resolve()
            full.relative_to(DATA_DIR.resolve())
        except (ValueError, OSError):
            api_error(self, 404, "图片文件不存在。")
            return
        if not full.is_file():
            api_error(self, 404, "图片文件不存在。")
            return
        try:
            stat_result = full.stat()
        except OSError:
            api_error(self, 404, "图片文件不存在。")
            return
        etag = file_etag(stat_result)
        # 元件图片地址带 ?v=<路径> 版本号，换图必然换 URL，可以放心长期缓存
        cache_control = "private, max-age=604800"
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
        body = full.read_bytes()
        encoding = self.maybe_gzip(body, content_type)
        if encoding:
            body = encoding[1]
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("ETag", etag)
            if encoding:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def api_part_image_upload(self, path, payload):
        part_id = int(path.split("/")[3])
        try:
            relative = save_part_image(
                part_id,
                payload.get("data_base64") or "",
                payload.get("file_name") or "",
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(200, {"image_path": relative})

    def send_data_file(self, relative, download_name=None):
        try:
            full = (DATA_DIR / relative).resolve()
            full.relative_to(DATA_DIR.resolve())
        except (ValueError, OSError):
            api_error(self, 404, "文件不存在。")
            return
        if not full.is_file():
            api_error(self, 404, "文件不存在。")
            return
        content_type = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
        try:
            stat_result = full.stat()
        except OSError:
            api_error(self, 404, "文件不存在。")
            return
        etag = file_etag(stat_result)
        # 上传文件都是唯一文件名，可以放心让浏览器缓存一天。
        cache_control = "private, max-age=86400"
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            return
        body = full.read_bytes()
        encoding = self.maybe_gzip(body, content_type)
        if encoding:
            body = encoding[1]
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            if download_name:
                encoded_name = quote(os.path.basename(download_name))
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{encoded_name}",
                )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("ETag", etag)
            if encoding:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def save_data_file(self, raw, file_name, folder, max_bytes=20 * 1024 * 1024):
        if not raw:
            raise ValueError("没有文件数据。")
        if len(raw) > max_bytes:
            raise ValueError(f"文件不能超过 {max_bytes // (1024 * 1024)}MB。")
        name = os.path.basename(file_name or "file")
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        if not name:
            name = "file.bin"
        target_dir = DATA_DIR / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        relative = f"{folder}/{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}_{name}"
        (DATA_DIR / relative).write_bytes(raw)
        return relative

    def save_site_file(self, data_base64, file_name, folder):
        if not data_base64:
            raise ValueError("没有文件数据。")
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception:
            raise ValueError("文件数据不是有效的 base64。")
        return self.save_data_file(raw, file_name, folder)

    def site_message_files_map(self, message_ids):
        """按留言 ID 分组返回附件，供列表接口一次性取回。"""
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = query(
            f"""SELECT id, message_id, file_name, file_path, file_size, mime_type
                FROM site_message_files
                WHERE message_id IN ({placeholders})
                ORDER BY id""",
            tuple(message_ids),
        )
        grouped = {}
        for row in rows:
            extension = os.path.splitext(row.get("file_name") or "")[1].lower()
            grouped.setdefault(row["message_id"], []).append(
                {
                    "id": row["id"],
                    "file_name": row["file_name"],
                    "file_path": row["file_path"],
                    "file_size": row["file_size"],
                    "mime_type": row["mime_type"],
                    "is_image": extension in MESSAGE_IMAGE_EXTENSIONS,
                }
            )
        return grouped

    def api_site_messages(self, params):
        rows = query(
            """SELECT id, nickname, content, parent_id, created_at
               FROM site_messages
               ORDER BY COALESCE(parent_id, id) DESC, id ASC"""
        )
        can_delete = self.is_owner()
        files = self.site_message_files_map([row["id"] for row in rows])
        for row in rows:
            row["files"] = files.get(row["id"], [])
            row["can_delete"] = can_delete
        roots = [row for row in rows if not row.get("parent_id")]
        replies = [row for row in rows if row.get("parent_id")]
        for root in roots:
            root["replies"] = [row for row in replies if row["parent_id"] == root["id"]]
        self.send_json(200, roots)

    def message_attachments(self, payload):
        """校验并解出附件，返回 (准备写入的文件列表, 错误信息)。"""
        raw_files = payload.get("files") or []
        if not isinstance(raw_files, list):
            return None, "附件格式不正确。"
        if len(raw_files) > MESSAGE_FILE_MAX_COUNT:
            return None, f"每条留言最多上传 {MESSAGE_FILE_MAX_COUNT} 个附件。"
        prepared = []
        total_bytes = 0
        for item in raw_files:
            if not isinstance(item, dict):
                return None, "附件格式不正确。"
            name = os.path.basename(str(item.get("name") or "file")).strip()
            if not name:
                return None, "附件缺少文件名。"
            extension = os.path.splitext(name)[1].lower()
            if extension not in MESSAGE_FILE_EXTENSIONS:
                return None, f"不支持的附件类型：{name}"
            try:
                raw = base64.b64decode(str(item.get("data_base64") or ""), validate=True)
            except Exception:
                return None, f"附件数据无效：{name}"
            if not raw:
                return None, f"附件内容为空：{name}"
            if len(raw) > MESSAGE_FILE_MAX_BYTES:
                limit_mb = MESSAGE_FILE_MAX_BYTES // (1024 * 1024)
                return None, f"单个附件不能超过 {limit_mb}MB：{name}"
            total_bytes += len(raw)
            if total_bytes > MESSAGE_FILE_TOTAL_MAX_BYTES:
                limit_mb = MESSAGE_FILE_TOTAL_MAX_BYTES // (1024 * 1024)
                return None, f"附件总大小不能超过 {limit_mb}MB。"
            prepared.append((name, raw))
        return prepared, ""

    def api_site_message_create(self, payload):
        if not rate_allow("message", self.client_ip(), 5, 60):
            api_error(self, 429, "留言太频繁，请稍后再试。")
            return
        nickname = str(payload.get("nickname") or "匿名").strip()[:30] or "匿名"
        content = str(payload.get("content") or "").strip()
        parent_id = payload.get("parent_id")
        if len(content) > 1000:
            api_error(self, 400, "留言内容不能超过 1000 字。")
            return
        prepared, error = self.message_attachments(payload)
        if prepared is None:
            api_error(self, 400, error)
            return
        if not content and not prepared:
            api_error(self, 400, "留言内容和附件不能同时为空。")
            return
        if parent_id:
            parent = query_one("SELECT id FROM site_messages WHERE id = ?", (parent_id,))
            if not parent:
                api_error(self, 400, "要回复的留言不存在。")
                return
        created_at = now_text()
        saved = []
        try:
            for name, raw in prepared:
                relative = self.save_data_file(
                    raw, name, "site_message_files", max_bytes=MESSAGE_FILE_MAX_BYTES
                )
                saved.append((name, relative, len(raw)))
        except ValueError as exc:
            for _name, relative, _size in saved:
                remove_data_file(relative)
            api_error(self, 400, str(exc))
            return

        def write(conn):
            cursor = conn.execute(
                "INSERT INTO site_messages (nickname, content, parent_id, created_at) VALUES (?, ?, ?, ?)",
                (nickname, content, parent_id or None, created_at),
            )
            message_id = cursor.lastrowid
            for name, relative, size in saved:
                conn.execute(
                    """INSERT INTO site_message_files
                       (message_id, file_name, file_path, file_size, mime_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (message_id, name, relative, size, mimetypes.guess_type(name)[0], created_at),
                )
            return message_id

        try:
            row_id = transaction(write)
        except Exception:
            for _name, relative, _size in saved:
                remove_data_file(relative)
            raise
        self.send_json(200, {"id": row_id, "files": len(saved)})

    def api_site_photos(self, params):
        rows = query("SELECT * FROM site_photos ORDER BY album, sort_order, id DESC")
        self.send_json(200, rows)

    # ---------- 说说 / 日志 ----------
    def moment_files_map(self, moment_ids):
        if not moment_ids:
            return {}
        placeholders = ",".join("?" for _ in moment_ids)
        rows = query(
            f"""SELECT id, moment_id, file_name, file_path, file_size, mime_type
                FROM moment_files
                WHERE moment_id IN ({placeholders})
                ORDER BY id""",
            tuple(moment_ids),
        )
        grouped = {}
        for row in rows:
            grouped.setdefault(row["moment_id"], []).append(
                {
                    "id": row["id"],
                    "file_name": row["file_name"],
                    "file_path": row["file_path"],
                    "file_size": row["file_size"],
                    "mime_type": row["mime_type"],
                }
            )
        return grouped

    def api_moments(self, params):
        rows = query(
            """SELECT id, content, tags, pinned, created_at
               FROM moments
               ORDER BY pinned DESC, created_at DESC, id DESC"""
        )
        can_manage = self.is_owner()
        files = self.moment_files_map([row["id"] for row in rows])
        for row in rows:
            row["files"] = files.get(row["id"], [])
            row["pinned"] = bool(row["pinned"])
            row["can_manage"] = can_manage
        self.send_json(200, rows)

    def moment_payload(self, payload, current=None):
        current = current or {}
        content = str(payload.get("content", current.get("content", "")) or "").strip()
        tags = str(payload.get("tags", current.get("tags", "")) or "")
        tags = tags.replace("，", ",").replace("、", ",").strip()[:200]
        if len(content) > MOMENT_CONTENT_MAX_CHARS:
            raise ValueError(f"说说内容不能超过 {MOMENT_CONTENT_MAX_CHARS} 字。")
        return content, (tags or None)

    def moment_images(self, payload):
        """校验并解出说说配图，返回 (文件列表, 错误信息)。"""
        raw_files = payload.get("images") or []
        if not isinstance(raw_files, list):
            return None, "图片格式不正确。"
        if len(raw_files) > MOMENT_IMAGE_MAX_COUNT:
            return None, f"一条说说最多 {MOMENT_IMAGE_MAX_COUNT} 张图片。"
        prepared = []
        total_bytes = 0
        for item in raw_files:
            if not isinstance(item, dict):
                return None, "图片格式不正确。"
            name = os.path.basename(str(item.get("name") or "image.png")).strip() or "image.png"
            extension = os.path.splitext(name)[1].lower()
            if extension not in MESSAGE_IMAGE_EXTENSIONS:
                return None, f"只支持图片：{name}"
            try:
                raw = base64.b64decode(str(item.get("data_base64") or ""), validate=True)
            except Exception:
                return None, f"图片数据无效：{name}"
            if not raw:
                return None, f"图片内容为空：{name}"
            if len(raw) > MOMENT_IMAGE_MAX_BYTES:
                limit_mb = MOMENT_IMAGE_MAX_BYTES // (1024 * 1024)
                return None, f"单张图片不能超过 {limit_mb}MB：{name}"
            total_bytes += len(raw)
            if total_bytes > MOMENT_IMAGE_TOTAL_MAX_BYTES:
                limit_mb = MOMENT_IMAGE_TOTAL_MAX_BYTES // (1024 * 1024)
                return None, f"图片总大小不能超过 {limit_mb}MB。"
            prepared.append((name, raw))
        return prepared, ""

    def api_moment_create(self, payload):
        try:
            content, tags = self.moment_payload(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        prepared, error = self.moment_images(payload)
        if prepared is None:
            api_error(self, 400, error)
            return
        if not content and not prepared:
            api_error(self, 400, "写点什么，或者配张图吧。")
            return
        created_at = now_text()
        saved = []
        try:
            for name, raw in prepared:
                relative = self.save_data_file(
                    raw, name, "moment_images", max_bytes=MOMENT_IMAGE_MAX_BYTES
                )
                saved.append((name, relative, len(raw)))
        except ValueError as exc:
            for _name, relative, _size in saved:
                remove_data_file(relative)
            api_error(self, 400, str(exc))
            return

        def write(conn):
            cursor = conn.execute(
                "INSERT INTO moments (content, tags, pinned, created_at) VALUES (?, ?, 0, ?)",
                (content, tags, created_at),
            )
            moment_id = cursor.lastrowid
            for name, relative, size in saved:
                conn.execute(
                    """INSERT INTO moment_files
                       (moment_id, file_name, file_path, file_size, mime_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (moment_id, name, relative, size, mimetypes.guess_type(name)[0], created_at),
                )
            return moment_id

        try:
            row_id = transaction(write)
        except Exception:
            for _name, relative, _size in saved:
                remove_data_file(relative)
            raise
        self.send_json(200, {"id": row_id, "images": len(saved)})

    def api_moment_item(self, path):
        moment_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM moments WHERE id = ?", (moment_id,))
        if not current:
            api_error(self, 404, "这条说说不存在。")
            return
        if self.command == "DELETE":
            rows = query("SELECT file_path FROM moment_files WHERE moment_id = ?", (moment_id,))
            execute("DELETE FROM moments WHERE id = ?", (moment_id,))
            for row in rows:
                remove_data_file(row.get("file_path"))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            content, tags = self.moment_payload(payload, current)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if not content:
            has_image = query_one(
                "SELECT id FROM moment_files WHERE moment_id = ? LIMIT 1", (moment_id,)
            )
            if not has_image:
                api_error(self, 400, "说说内容不能为空。")
                return
        pinned = 1 if payload.get("pinned", current.get("pinned")) else 0
        execute(
            "UPDATE moments SET content = ?, tags = ?, pinned = ? WHERE id = ?",
            (content, tags, pinned, moment_id),
        )
        self.send_json(200, {"id": moment_id})


    def api_site_photo_upload(self, payload):
        title = str(payload.get("title") or "").strip()[:80]
        album = str(payload.get("album") or "").strip()[:40]
        try:
            relative = self.save_site_file(
                payload.get("data_base64") or "",
                payload.get("file_name") or "photo.jpg",
                "site_photos",
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        row_id = execute(
            "INSERT INTO site_photos (title, album, image_path, sort_order, created_at) VALUES (?, ?, ?, 0, ?)",
            (title or None, album or None, relative, now_text()),
        )
        self.send_json(200, {"id": row_id, "image_path": relative})

    def api_site_music(self, params):
        rows = query("SELECT * FROM site_music ORDER BY sort_order, id")
        self.send_json(200, rows)

    def api_site_music_create(self, payload):
        title = str(payload.get("title") or "").strip()[:80]
        artist = str(payload.get("artist") or "").strip()[:80]
        source_type = "file" if payload.get("source_type") == "file" else "url"
        source_id = str(payload.get("source_id") or "").strip()[:300]
        if not title or not source_id:
            api_error(self, 400, "歌名和歌曲链接/ID 不能为空。")
            return
        row_id = execute(
            "INSERT INTO site_music (title, artist, source_type, source_id, sort_order, created_at) VALUES (?, ?, ?, ?, 0, ?)",
            (title, artist or None, source_type, source_id, now_text()),
        )
        self.send_json(200, {"id": row_id})

    def api_site_music_upload(self, payload):
        title = str(payload.get("title") or "").strip()[:80]
        artist = str(payload.get("artist") or "").strip()[:80]
        try:
            relative = self.save_site_file(
                payload.get("data_base64") or "",
                payload.get("file_name") or "music.mp3",
                "site_music_files",
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if not title:
            title = os.path.basename(payload.get("file_name") or "未命名歌曲")
        row_id = execute(
            "INSERT INTO site_music (title, artist, source_type, source_id, sort_order, created_at) VALUES (?, ?, 'file', ?, 0, ?)",
            (title, artist or None, relative, now_text()),
        )
        self.send_json(200, {"id": row_id, "source_id": relative})

    def api_site_links(self, params):
        rows = query("SELECT * FROM site_links ORDER BY category, sort_order, id")
        self.send_json(200, rows)

    def api_prompts(self, params):
        rows = query(
            """
            SELECT id, title, description, category, prompt, tags,
                   pinned, sort_order, created_at, updated_at
            FROM ai_prompts
            ORDER BY pinned DESC, sort_order, id
            """
        )
        for row in rows:
            row["pinned"] = bool(row["pinned"])
        self.send_json(
            200,
            {
                "items": rows,
                "can_manage": self.is_owner(),
            },
        )

    def prompt_payload(self, payload, current=None):
        current = current or {}
        title = str(payload.get("title", current.get("title", "")) or "").strip()[:120]
        prompt_text = str(
            payload.get("prompt", current.get("prompt", "")) or ""
        ).strip()
        if not title:
            raise ValueError("提示词标题不能为空。")
        if not prompt_text:
            raise ValueError("提示词内容不能为空。")
        if len(prompt_text) > 12000:
            raise ValueError("提示词内容不能超过 12000 字。")
        description = str(
            payload.get("description", current.get("description", "")) or ""
        ).strip()[:300]
        category = str(
            payload.get("category", current.get("category", "未分类")) or "未分类"
        ).strip()[:40] or "未分类"
        tags = str(payload.get("tags", current.get("tags", "")) or "")
        tags = tags.replace("，", ",").replace("、", ",").strip()[:200]
        pinned = 1 if payload.get("pinned", current.get("pinned", False)) else 0
        try:
            sort_order = int(payload.get("sort_order", current.get("sort_order", 0)) or 0)
        except (TypeError, ValueError):
            raise ValueError("排序值必须是整数。")
        return title, description, category, prompt_text, (tags or None), pinned, sort_order

    def api_prompt_create(self, payload):
        try:
            title, description, category, prompt_text, tags, pinned, _sort_order = self.prompt_payload(
                payload
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        sort_order = query_one(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM ai_prompts"
        )["value"]
        stamp = now_text()
        prompt_id = execute(
            """
            INSERT INTO ai_prompts
                (title, description, category, prompt, tags,
                 pinned, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                description or None,
                category,
                prompt_text,
                tags,
                pinned,
                sort_order,
                stamp,
                stamp,
            ),
        )
        self.send_json(201, {"id": prompt_id})

    def api_prompt_item(self, path):
        prompt_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM ai_prompts WHERE id = ?", (prompt_id,))
        if not current:
            api_error(self, 404, "提示词不存在。")
            return
        if self.command == "DELETE":
            execute("DELETE FROM ai_prompts WHERE id = ?", (prompt_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            title, description, category, prompt_text, tags, pinned, sort_order = self.prompt_payload(
                payload, current
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        execute(
            """
            UPDATE ai_prompts
            SET title = ?, description = ?, category = ?, prompt = ?, tags = ?,
                pinned = ?, sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title,
                description or None,
                category,
                prompt_text,
                tags,
                pinned,
                sort_order,
                now_text(),
                prompt_id,
            ),
        )
        self.send_json(200, {"id": prompt_id})

    def api_site_link_create(self, payload):
        name = str(payload.get("name") or "").strip()[:80]
        url = str(payload.get("url") or "").strip()[:300]
        category = str(payload.get("category") or "").strip()[:40]
        description = str(payload.get("description") or "").strip()[:200]
        if not name or not url:
            api_error(self, 400, "名称和网址不能为空。")
            return
        if not url.startswith(("http://", "https://")):
            api_error(self, 400, "网址必须以 http:// 或 https:// 开头。")
            return
        row_id = execute(
            "INSERT INTO site_links (name, url, category, description, sort_order, created_at) VALUES (?, ?, ?, ?, 0, ?)",
            (name, url, category or None, description or None, now_text()),
        )
        self.send_json(200, {"id": row_id})

    def api_site_message_delete(self, path):
        item_id = int(path.split("/")[4])
        rows = query(
            """SELECT file_path FROM site_message_files
               WHERE message_id = ?
                  OR message_id IN (SELECT id FROM site_messages WHERE parent_id = ?)""",
            (item_id, item_id),
        )
        execute("DELETE FROM site_messages WHERE id = ?", (item_id,))
        for row in rows:
            remove_data_file(row.get("file_path"))
        self.send_json(200, {"ok": True})

    def api_site_photo_delete(self, path):
        item_id = int(path.split("/")[4])
        row = query_one("SELECT image_path FROM site_photos WHERE id = ?", (item_id,))
        if row and row.get("image_path"):
            try:
                full = (DATA_DIR / row["image_path"]).resolve()
                full.relative_to(DATA_DIR.resolve())
                if full.is_file():
                    full.unlink()
            except (ValueError, OSError):
                pass
        execute("DELETE FROM site_photos WHERE id = ?", (item_id,))
        self.send_json(200, {"ok": True})

    def api_site_music_delete(self, path):
        item_id = int(path.split("/")[4])
        row = query_one("SELECT source_type, source_id FROM site_music WHERE id = ?", (item_id,))
        if row and row.get("source_type") == "file" and row.get("source_id"):
            try:
                full = (DATA_DIR / row["source_id"]).resolve()
                full.relative_to(DATA_DIR.resolve())
                if full.is_file():
                    full.unlink()
            except (ValueError, OSError):
                pass
        execute("DELETE FROM site_music WHERE id = ?", (item_id,))
        self.send_json(200, {"ok": True})

    def api_site_link_delete(self, path):
        item_id = int(path.split("/")[4])
        execute("DELETE FROM site_links WHERE id = ?", (item_id,))
        self.send_json(200, {"ok": True})

    def note_rows(self, summary=False):
        rows = query(
            """SELECT id, title, content, tags, created_at, updated_at
               FROM learning_notes
               ORDER BY updated_at DESC, id DESC"""
        )
        for row in rows:
            paths = note_image_paths(row.get("content"))
            row["image_paths"] = paths
            row["image_count"] = len(paths)
            row["cover_path"] = paths[0] if paths else None
            # 首页只用到标题/标签/封面，正文（可能上百 KB 一篇）没必要传过去
            if summary:
                row["content_length"] = len(row.get("content") or "")
                row.pop("content", None)
        return rows

    def note_payload(self, payload, current=None):
        current = current or {}
        title = str(payload.get("title", current.get("title", "")) or "").strip()[:120]
        content = str(payload.get("content", current.get("content", "")) or "")
        tags = str(payload.get("tags", current.get("tags", "")) or "")
        tags = tags.replace("，", ",").replace("、", ",").strip()[:200]
        if len(content) > NOTE_CONTENT_MAX_CHARS:
            raise ValueError("笔记正文太长了，建议拆成多篇。")
        if not title:
            title = self.note_title_from_content(content)
        return title, content, (tags or None)

    @staticmethod
    def note_title_from_content(content):
        text = content or ""
        images = re.findall(r"!\[([^\]]*)\]\([^)]*\)", text)
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        for line in text.splitlines():
            cleaned = line.strip().lstrip("#>-* \t").strip().strip("`").strip()
            if cleaned:
                return cleaned[:40]
        for alt in images:
            if alt.strip():
                return alt.strip()[:40]
        if images:
            return "图片笔记"
        return "未命名笔记"

    def api_notes(self, params):
        summary = str((params or {}).get("summary", [""])[0]).lower() in ("1", "true", "yes")
        self.send_json(200, self.note_rows(summary=summary))

    def api_note_create(self, payload):
        try:
            title, content, tags = self.note_payload(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        stamp = now_text()
        note_id = execute(
            """INSERT INTO learning_notes (title, content, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (title, content, tags, stamp, stamp),
        )
        self.sync_note_images(note_id, content)
        self.send_json(200, {"id": note_id})

    def store_note_import_asset(self, raw, original_name, slug, index):
        mime_type = detect_image_type(raw)
        if not mime_type:
            return None
        extension = NOTE_IMAGE_EXTENSIONS[mime_type]
        base_name = os.path.splitext(os.path.basename(original_name or ""))[0]
        base_name = re.sub(r"[^A-Za-z0-9_-]+", "-", base_name).strip("-_") or f"image-{index:02d}"
        stored_name = f"{slug}-{index:02d}-{base_name[:60]}{extension}"
        relative = self.save_data_file(raw, stored_name, "note_images", NOTE_IMAGE_MAX_BYTES)
        try:
            image_id = execute(
                """INSERT INTO note_images
                   (note_id, file_path, original_name, mime_type, size_bytes, created_at)
                   VALUES (NULL, ?, ?, ?, ?, ?)""",
                (relative, original_name or stored_name, mime_type, len(raw), now_text()),
            )
        except Exception:
            remove_data_file(relative)
            raise
        return relative, image_id, len(raw)

    def api_note_import(self, payload):
        original_name = os.path.basename(str(payload.get("file_name") or "document"))[:180]
        data_base64 = payload.get("data_base64") or ""
        if not data_base64:
            api_error(self, 400, "没有文件数据。")
            return
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception:
            api_error(self, 400, "文件数据不是有效的 base64。")
            return
        if not raw:
            api_error(self, 400, "文件内容为空。")
            return
        if len(raw) > NOTE_IMPORT_MAX_BYTES:
            api_error(
                self,
                400,
                f"导入文档不能超过 {NOTE_IMPORT_MAX_BYTES // (1024 * 1024)}MB。",
            )
            return
        extension = Path(original_name).suffix.lower()
        if extension not in {".doc", ".docx", ".pdf"}:
            api_error(self, 400, "只支持导入 DOC、DOCX 和 PDF 文档。")
            return
        try:
            import anydoc
        except ImportError:
            api_error(
                self,
                503,
                "Word/PDF 转换组件未安装，请先执行 pip install -r requirements.txt。",
            )
            return
        try:
            doc_format = anydoc.format_from_bytes(raw)
        except Exception:
            doc_format = None
        if doc_format not in NOTE_IMPORT_FORMATS:
            api_error(self, 400, "文件内容不是支持的 Word 或 PDF 文档。")
            return

        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(original_name).stem).strip("-_")[:40]
        slug = slug or "import"
        image_ids = []
        image_count = 0
        image_bytes = 0
        asset_urls = {}
        assets = {}

        def cleanup_import_images():
            for image_id in image_ids:
                row = query_one("SELECT file_path FROM note_images WHERE id = ?", (image_id,))
                if row:
                    remove_data_file(row["file_path"])
                execute("DELETE FROM note_images WHERE id = ?", (image_id,))

        def asset_markdown(asset_id, alt):
            nonlocal image_count, image_bytes
            if asset_id in asset_urls:
                relative = asset_urls[asset_id]
                return f"![{alt}](/site-files/{relative})" if relative else alt
            asset = assets.get(asset_id)
            if asset is None:
                return alt
            asset_index = len(image_ids) + 1
            stored = self.store_note_import_asset(
                asset.data,
                getattr(asset, "origin_part", "") or f"image-{asset_index:02d}",
                slug,
                asset_index,
            )
            if not stored:
                asset_urls[asset_id] = None
                return alt
            relative, image_id, size_bytes = stored
            asset_urls[asset_id] = relative
            image_ids.append(image_id)
            image_count = len(image_ids)
            image_bytes += size_bytes
            return f"![{alt}](/site-files/{relative})"

        try:
            if doc_format == "pdf":
                content = anydoc.to_markdown_bytes(raw, doc_format)
            else:
                document = anydoc.to_document(raw, doc_format)
                assets = {
                    asset.id: asset
                    for asset in (getattr(document, "assets", None) or [])
                }
                content = render_anydoc_document(document, asset_markdown)
        except anydoc.NeedsOcrError as exc:
            pages = ", ".join(str(page) for page in (getattr(exc, "pages", None) or [])[:10])
            detail = f"（第 {pages} 页）" if pages else ""
            api_error(self, 400, f"这个 PDF 是扫描版，当前版本暂不支持 OCR{detail}。")
            return
        except anydoc.EncryptedError:
            api_error(self, 400, "文档已加密或设置了打开密码，暂时无法导入。")
            return
        except anydoc.ResourceLimitError:
            api_error(self, 400, "文档结构过于复杂，已超过安全解析限制。")
            return
        except anydoc.MalformedError:
            api_error(self, 400, "文档结构异常，无法转换。")
            return
        except anydoc.MissingPartError:
            api_error(self, 400, "文档缺少必要内容，无法转换。")
            return
        except anydoc.UnsupportedError:
            cleanup_import_images()
            api_error(self, 400, "暂不支持这种文档格式。")
            return
        except anydoc.ConvertError as exc:
            cleanup_import_images()
            api_error(self, 400, f"文档转换失败：{exc}")
            return
        except Exception as exc:
            cleanup_import_images()
            api_error(self, 500, f"文档转换失败：{exc}")
            return

        content = str(content or "").strip()
        if not content:
            cleanup_import_images()
            api_error(self, 400, "没有从文档中提取到可阅读的正文。")
            return
        content = (
            f"> 导入自 {markdown_escape_text(original_name)} · {today_text()}"
            f"\n\n{content}\n"
        )
        if len(content) > NOTE_CONTENT_MAX_CHARS:
            cleanup_import_images()
            api_error(self, 400, "转换后的正文太长了，建议拆分文档后再导入。")
            return
        title = Path(original_name).stem.strip()[:120] or f"{NOTE_IMPORT_FORMATS[doc_format]} 导入"
        tags = f"{NOTE_IMPORT_FORMATS[doc_format]}导入"
        stamp = now_text()
        try:
            def save_imported_note(conn):
                cursor = conn.execute(
                    """INSERT INTO learning_notes (title, content, tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (title, content, tags, stamp, stamp),
                )
                imported_note_id = cursor.lastrowid
                for image_id in image_ids:
                    conn.execute(
                        "UPDATE note_images SET note_id = ? WHERE id = ?",
                        (imported_note_id, image_id),
                    )
                return imported_note_id

            note_id = transaction(save_imported_note)
        except Exception as exc:
            cleanup_import_images()
            api_error(self, 500, f"保存导入笔记失败：{exc}")
            return
        self.send_json(
            200,
            {
                "id": note_id,
                "title": title,
                "format": doc_format,
                "content_length": len(content),
                "image_count": image_count,
                "image_bytes": image_bytes,
            },
        )

    def api_note_export(self, path):
        note_id = int(path.split("/")[3])
        note = query_one("SELECT * FROM learning_notes WHERE id = ?", (note_id,))
        if not note:
            api_error(self, 404, "笔记不存在。")
            return
        html = build_note_export_html(note, note_export_image_map(note.get("content") or ""))
        body = html.encode("utf-8")
        raw_name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", str(note.get("title") or "笔记")).strip(" .")
        file_name = f"{(raw_name or f'note-{note_id}')[:80]}.html"
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(file_name)}",
            )
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def api_note_item(self, path):
        note_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM learning_notes WHERE id = ?", (note_id,))
        if not current:
            api_error(self, 404, "笔记不存在。")
            return
        if self.command == "DELETE":
            self.delete_note(note_id)
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            title, content, tags = self.note_payload(payload, current)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        execute(
            """UPDATE learning_notes SET title = ?, content = ?, tags = ?, updated_at = ?
               WHERE id = ?""",
            (title, content, tags, now_text(), note_id),
        )
        self.sync_note_images(note_id, content)
        self.send_json(200, {"id": note_id})

    def sync_note_images(self, note_id, content):
        used = set(note_image_paths(content))
        for row in query("SELECT id, note_id, file_path FROM note_images"):
            if row["file_path"] in used:
                if row["note_id"] != note_id:
                    execute(
                        "UPDATE note_images SET note_id = ? WHERE id = ?",
                        (note_id, row["id"]),
                    )
            elif row["note_id"] == note_id:
                execute("UPDATE note_images SET note_id = NULL WHERE id = ?", (row["id"],))

    def delete_note(self, note_id):
        referenced = set()
        for row in query("SELECT content FROM learning_notes WHERE id != ?", (note_id,)):
            referenced.update(note_image_paths(row.get("content")))
        for row in query("SELECT id, file_path FROM note_images WHERE note_id = ?", (note_id,)):
            if row["file_path"] in referenced:
                execute("UPDATE note_images SET note_id = NULL WHERE id = ?", (row["id"],))
            else:
                remove_data_file(row["file_path"])
                execute("DELETE FROM note_images WHERE id = ?", (row["id"],))
        execute("DELETE FROM learning_notes WHERE id = ?", (note_id,))

    def api_note_image_upload(self, payload):
        original_name = os.path.basename(str(payload.get("file_name") or "image.png"))[:120]
        data_base64 = payload.get("data_base64") or ""
        if not data_base64:
            api_error(self, 400, "没有文件数据。")
            return
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception:
            api_error(self, 400, "文件数据不是有效的 base64。")
            return
        if not raw:
            api_error(self, 400, "图片内容为空。")
            return
        if len(raw) > NOTE_IMAGE_MAX_BYTES:
            api_error(self, 400, "图片不能超过 20MB。")
            return
        mime_type = detect_image_type(raw)
        if not mime_type:
            api_error(self, 400, "只支持 PNG / JPEG / WebP / GIF / BMP 图片。")
            return
        base_name = os.path.splitext(original_name)[0] or "image"
        stored_name = f"{base_name}{NOTE_IMAGE_EXTENSIONS[mime_type]}"
        try:
            relative = self.save_data_file(
                raw, stored_name, "note_images", NOTE_IMAGE_MAX_BYTES
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        image_id = execute(
            """INSERT INTO note_images (note_id, file_path, original_name, mime_type, size_bytes, created_at)
               VALUES (NULL, ?, ?, ?, ?, ?)""",
            (relative, original_name, mime_type, len(raw), now_text()),
        )
        self.send_json(
            200,
            {
                "id": image_id,
                "path": relative,
                "url": f"/site-files/{relative}",
                "mime_type": mime_type,
                "size_bytes": len(raw),
            },
        )

    def api_note_image_delete(self, path):
        image_id = int(path.rsplit("/", 1)[1])
        row = query_one("SELECT id, file_path FROM note_images WHERE id = ?", (image_id,))
        if not row:
            api_error(self, 404, "图片不存在。")
            return
        for note in query("SELECT content FROM learning_notes"):
            if row["file_path"] in note_image_paths(note.get("content")):
                api_error(self, 400, "这张图片还在笔记正文里被引用，请先删除正文中的图片。")
                return
        remove_data_file(row["file_path"])
        execute("DELETE FROM note_images WHERE id = ?", (image_id,))
        self.send_json(200, {"ok": True})

    def workbench_asset_rows(self, params=None):
        params = params or {}
        conditions = []
        values = []
        q = str((params.get("q") or [""])[0] or "").strip()
        category = str((params.get("category") or [""])[0] or "").strip()
        project_id = str((params.get("project_id") or [""])[0] or "").strip()
        repair_id = str((params.get("repair_id") or [""])[0] or "").strip()
        if q:
            conditions.append(
                """(
                    a.title LIKE ? OR a.original_name LIKE ? OR a.version LIKE ?
                    OR a.target_chip LIKE ? OR a.target_board LIKE ? OR a.notes LIKE ?
                )"""
            )
            like = f"%{q}%"
            values.extend([like] * 6)
        if category in WORKBENCH_CATEGORIES:
            conditions.append("a.category = ?")
            values.append(category)
        if project_id.isdigit():
            conditions.append("a.project_id = ?")
            values.append(int(project_id))
        if repair_id.isdigit():
            conditions.append("a.repair_id = ?")
            values.append(int(repair_id))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return query(
            f"""
            SELECT a.*, p.name AS project_name, r.device_name AS repair_device
            FROM workbench_assets a
            LEFT JOIN projects p ON p.id = a.project_id
            LEFT JOIN repair_records r ON r.id = a.repair_id
            {where}
            ORDER BY a.created_at DESC, a.id DESC
            """,
            tuple(values),
        )

    def workbench_repair_rows(self, params=None):
        params = params or {}
        conditions = []
        values = []
        q = str((params.get("q") or [""])[0] or "").strip()
        status = str((params.get("status") or [""])[0] or "").strip()
        project_id = str((params.get("project_id") or [""])[0] or "").strip()
        if q:
            conditions.append(
                """(
                    r.device_name LIKE ? OR r.serial_number LIKE ? OR r.fault LIKE ?
                    OR r.diagnosis LIKE ? OR r.action LIKE ? OR r.notes LIKE ?
                )"""
            )
            like = f"%{q}%"
            values.extend([like] * 6)
        if status in WORKBENCH_REPAIR_STATUSES:
            conditions.append("r.status = ?")
            values.append(status)
        if project_id.isdigit():
            conditions.append("r.project_id = ?")
            values.append(int(project_id))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return query(
            f"""
            SELECT r.*, p.name AS project_name,
                   (SELECT COUNT(*) FROM workbench_assets a WHERE a.repair_id = r.id)
                       AS asset_count
            FROM repair_records r
            LEFT JOIN projects p ON p.id = r.project_id
            {where}
            ORDER BY
                CASE r.status
                    WHEN 'repairing' THEN 0
                    WHEN 'open' THEN 1
                    ELSE 2
                END,
                r.updated_at DESC,
                r.id DESC
            """,
            tuple(values),
        )

    def api_workbench_summary(self):
        asset_counts = {row["category"]: row["n"] for row in query(
            "SELECT category, COUNT(*) AS n FROM workbench_assets GROUP BY category"
        )}
        repair_counts = {row["status"]: row["n"] for row in query(
            "SELECT status, COUNT(*) AS n FROM repair_records GROUP BY status"
        )}
        self.send_json(
            200,
            {
                "assets": {
                    "total": sum(asset_counts.values()),
                    "source": asset_counts.get("source", 0),
                    "firmware": asset_counts.get("firmware", 0),
                    "document": asset_counts.get("document", 0),
                    "image": asset_counts.get("image", 0),
                    "other": asset_counts.get("other", 0),
                },
                "repairs": {
                    "total": sum(repair_counts.values()),
                    "open": repair_counts.get("open", 0),
                    "repairing": repair_counts.get("repairing", 0),
                    "completed": repair_counts.get("completed", 0),
                    "cancelled": repair_counts.get("cancelled", 0),
                },
                "recent_assets": self.workbench_asset_rows()[:5],
                "recent_repairs": self.workbench_repair_rows()[:5],
            },
        )

    def api_workbench_assets(self, params):
        self.send_json(200, self.workbench_asset_rows(params))

    def api_workbench_repairs(self, params):
        self.send_json(200, self.workbench_repair_rows(params))

    @staticmethod
    def workbench_category_for_name(file_name, requested=""):
        if requested in WORKBENCH_CATEGORIES:
            return requested
        extension = Path(file_name).suffix.lower()
        if extension in {".hex", ".bin", ".elf"}:
            return "firmware"
        if extension in {
            ".zip", ".7z", ".rar", ".tar", ".gz", ".tgz",
            ".brd", ".pcb", ".sch", ".kicad_sch", ".kicad_pcb",
        }:
            return "source"
        if extension in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return "image"
        if extension in {".pdf", ".md", ".txt", ".csv", ".json", ".xls", ".xlsx"}:
            return "document"
        return "other"

    @staticmethod
    def workbench_external_url(value):
        url = str(value or "").strip()
        if not url:
            return None
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("烧录链接必须是 http 或 https 地址。")
        return url[:500]

    def api_workbench_asset_upload(self, payload):
        original_name = os.path.basename(str(payload.get("file_name") or "file"))[:180]
        data_base64 = payload.get("data_base64") or ""
        if not data_base64:
            api_error(self, 400, "没有文件数据。")
            return
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception:
            api_error(self, 400, "文件数据不是有效的 base64。")
            return
        if not raw:
            api_error(self, 400, "文件内容为空。")
            return
        if len(raw) > WORKBENCH_FILE_MAX_BYTES:
            api_error(self, 400, "工作台文件不能超过 30MB。")
            return
        extension = Path(original_name).suffix.lower()
        if extension not in WORKBENCH_EXTENSIONS:
            api_error(self, 400, "不支持这种文件类型。")
            return
        category = self.workbench_category_for_name(
            original_name,
            str(payload.get("category") or ""),
        )
        project_id = payload.get("project_id")
        project_id = int(project_id) if str(project_id or "").isdigit() else None
        if project_id and not query_one("SELECT id FROM projects WHERE id = ?", (project_id,)):
            api_error(self, 400, "关联项目不存在。")
            return
        repair_id = payload.get("repair_id")
        repair_id = int(repair_id) if str(repair_id or "").isdigit() else None
        if repair_id and not query_one("SELECT id FROM repair_records WHERE id = ?", (repair_id,)):
            api_error(self, 400, "关联维修记录不存在。")
            return
        try:
            flash_url = self.workbench_external_url(payload.get("flash_url"))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        try:
            relative = self.save_data_file(
                raw,
                original_name,
                f"workbench/{category}",
                WORKBENCH_FILE_MAX_BYTES,
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        title = str(payload.get("title") or Path(original_name).stem or original_name).strip()[:160]
        version = str(payload.get("version") or "").strip()[:80] or None
        target_chip = str(payload.get("target_chip") or "").strip()[:120] or None
        target_board = str(payload.get("target_board") or "").strip()[:120] or None
        notes = str(payload.get("notes") or "").strip()[:4000] or None
        stamp = now_text()
        digest = hashlib.sha256(raw).hexdigest()
        asset_id = execute(
            """
            INSERT INTO workbench_assets (
                project_id, repair_id, category, title, file_path, original_name,
                mime_type, size_bytes, sha256, version, target_chip, target_board,
                flash_url, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, repair_id, category, title or original_name, relative,
                original_name, mime_type, len(raw), digest, version, target_chip,
                target_board, flash_url, notes, stamp, stamp,
            ),
        )
        row = query_one("SELECT * FROM workbench_assets WHERE id = ?", (asset_id,))
        self.send_json(200, row)

    def api_workbench_asset_download(self, path):
        asset_id = int(path.split("/")[4])
        row = query_one(
            "SELECT file_path, original_name FROM workbench_assets WHERE id = ?",
            (asset_id,),
        )
        if not row:
            api_error(self, 404, "文件不存在。")
            return
        self.send_data_file(row["file_path"], row.get("original_name") or "download.bin")

    def api_workbench_asset_item(self, path):
        asset_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM workbench_assets WHERE id = ?", (asset_id,))
        if not current:
            api_error(self, 404, "文件不存在。")
            return
        if self.command == "DELETE":
            remove_data_file(current["file_path"])
            execute("DELETE FROM workbench_assets WHERE id = ?", (asset_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        fields = []
        values = []
        text_fields = {
            "title": 160,
            "version": 80,
            "target_chip": 120,
            "target_board": 120,
            "notes": 4000,
        }
        for key, limit in text_fields.items():
            if key in payload:
                fields.append(f"{key} = ?")
                values.append(str(payload.get(key) or "").strip()[:limit] or None)
        if "category" in payload and str(payload.get("category")) in WORKBENCH_CATEGORIES:
            fields.append("category = ?")
            values.append(str(payload.get("category")))
        for key in ("project_id", "repair_id"):
            if key in payload:
                value = payload.get(key)
                value = int(value) if str(value or "").isdigit() else None
                fields.append(f"{key} = ?")
                values.append(value)
        if "flash_url" in payload:
            try:
                fields.append("flash_url = ?")
                values.append(self.workbench_external_url(payload.get("flash_url")))
            except ValueError as exc:
                api_error(self, 400, str(exc))
                return
        if fields:
            fields.append("updated_at = ?")
            values.append(now_text())
            values.append(asset_id)
            execute(
                f"UPDATE workbench_assets SET {', '.join(fields)} WHERE id = ?",
                tuple(values),
            )
        self.send_json(200, query_one("SELECT * FROM workbench_assets WHERE id = ?", (asset_id,)))

    def api_workbench_repair_create(self, payload):
        device_name = str(payload.get("device_name") or "").strip()[:160]
        if not device_name:
            api_error(self, 400, "请填写设备或项目名称。")
            return
        status = str(payload.get("status") or "open")
        if status not in WORKBENCH_REPAIR_STATUSES:
            status = "open"
        project_id = payload.get("project_id")
        project_id = int(project_id) if str(project_id or "").isdigit() else None
        if project_id and not query_one("SELECT id FROM projects WHERE id = ?", (project_id,)):
            api_error(self, 400, "关联项目不存在。")
            return
        cost = payload.get("cost")
        try:
            cost = float(cost) if str(cost or "").strip() else None
        except (TypeError, ValueError):
            api_error(self, 400, "费用必须是数字。")
            return
        stamp = now_text()
        repair_id = execute(
            """
            INSERT INTO repair_records (
                project_id, device_name, serial_number, fault, diagnosis, action,
                status, cost, started_at, finished_at, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                device_name,
                str(payload.get("serial_number") or "").strip()[:120] or None,
                str(payload.get("fault") or "").strip()[:4000] or None,
                str(payload.get("diagnosis") or "").strip()[:4000] or None,
                str(payload.get("action") or "").strip()[:4000] or None,
                status,
                cost,
                str(payload.get("started_at") or "").strip()[:40] or None,
                str(payload.get("finished_at") or "").strip()[:40] or None,
                str(payload.get("notes") or "").strip()[:4000] or None,
                stamp,
                stamp,
            ),
        )
        self.send_json(200, query_one("SELECT * FROM repair_records WHERE id = ?", (repair_id,)))

    def api_workbench_repair_item(self, path):
        repair_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM repair_records WHERE id = ?", (repair_id,))
        if not current:
            api_error(self, 404, "维修记录不存在。")
            return
        if self.command == "DELETE":
            execute("DELETE FROM repair_records WHERE id = ?", (repair_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        text_fields = {
            "device_name": 160,
            "serial_number": 120,
            "fault": 4000,
            "diagnosis": 4000,
            "action": 4000,
            "started_at": 40,
            "finished_at": 40,
            "notes": 4000,
        }
        fields = []
        values = []
        for key, limit in text_fields.items():
            if key in payload:
                value = str(payload.get(key) or "").strip()[:limit] or None
                if key == "device_name" and not value:
                    api_error(self, 400, "请填写设备或项目名称。")
                    return
                fields.append(f"{key} = ?")
                values.append(value)
        if "status" in payload:
            status = str(payload.get("status") or "open")
            fields.append("status = ?")
            values.append(status if status in WORKBENCH_REPAIR_STATUSES else "open")
        if "project_id" in payload:
            value = payload.get("project_id")
            value = int(value) if str(value or "").isdigit() else None
            fields.append("project_id = ?")
            values.append(value)
        if "cost" in payload:
            try:
                cost = float(payload.get("cost")) if str(payload.get("cost") or "").strip() else None
            except (TypeError, ValueError):
                api_error(self, 400, "费用必须是数字。")
                return
            fields.append("cost = ?")
            values.append(cost)
        if fields:
            fields.append("updated_at = ?")
            values.append(now_text())
            values.append(repair_id)
            execute(
                f"UPDATE repair_records SET {', '.join(fields)} WHERE id = ?",
                tuple(values),
            )
        self.send_json(200, query_one("SELECT * FROM repair_records WHERE id = ?", (repair_id,)))

    def api_bookmarks(self, params):
        rows = query(
            """
            SELECT b.*, f.name AS folder_name
            FROM bookmarks b
            LEFT JOIN bookmark_folders f ON f.id = b.folder_id
            ORDER BY b.created_at DESC, b.id DESC
            """
        )
        paths = bookmark_folder_path_map()
        for row in rows:
            row["folder_path"] = paths.get(row["folder_id"], "")
        self.send_json(200, rows)

    def api_bookmark_favicon(self, path):
        bookmark_id = int(path.split("/")[3])
        relative_path = refresh_bookmark_favicon(bookmark_id)
        if not relative_path:
            self.send_error(404)
            return
        try:
            full_path = (DATA_DIR / relative_path).resolve()
            full_path.relative_to(DATA_DIR.resolve())
            body = full_path.read_bytes()
        except (ValueError, OSError):
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(full_path.name)[0] or "image/x-icon"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def api_firefox_bookmark_profiles(self):
        self.send_json(200, firefox_profiles())

    def api_import_firefox_bookmarks(self, payload):
        try:
            result = import_firefox_bookmarks(payload.get("profile"))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(200, result)

    def api_bookmark_check_status(self):
        self.send_json(200, bookmark_check_status())

    def api_start_bookmark_link_check(self, payload):
        try:
            result = start_bookmark_link_check(
                ids=payload.get("ids"),
                broken_only=bool(payload.get("broken_only")),
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(202, result)

    def api_bookmark_create(self, payload):
        try:
            url = normalize_bookmark_url(payload.get("url"))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return

        title = str(payload.get("title") or "").strip()[:200]
        if not title:
            title = urlsplit(url).hostname or url
            if title.lower().startswith("www."):
                title = title[4:]
        description = str(payload.get("description") or "").strip()[:500]
        folder_id = payload.get("folder_id")
        folder_id = int(folder_id) if folder_id not in (None, "") else None
        if folder_id is not None and not query_one(
            "SELECT id FROM bookmark_folders WHERE id = ?", (folder_id,)
        ):
            api_error(self, 400, "书签文件夹不存在。")
            return

        timestamp = now_text()
        sort_order = query_one(
            """
            SELECT COALESCE(MIN(sort_order), 0) AS value
            FROM bookmarks
            WHERE folder_id IS ?
            """,
            (folder_id,),
        )["value"] - 1
        row_id = execute(
            """
            INSERT INTO bookmarks
                (folder_id, title, url, description, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder_id,
                title,
                url,
                description or None,
                sort_order,
                timestamp,
                timestamp,
            ),
        )
        duplicate_count = query_one(
            "SELECT COUNT(*) AS n FROM bookmarks WHERE url = ?", (url,)
        )["n"]
        self.send_json(
            201,
            {
                "id": row_id,
                "title": title,
                "url": url,
                "duplicate_count": duplicate_count,
            },
        )

    def api_bookmark_reorder(self, payload):
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            api_error(self, 400, "排序列表不能为空。")
            return
        clean_ids = []
        for item_id in ids:
            try:
                clean_ids.append(int(item_id))
            except (TypeError, ValueError):
                api_error(self, 400, "排序列表包含无效的书签。")
                return
        if len(set(clean_ids)) != len(clean_ids):
            api_error(self, 400, "排序列表中存在重复书签。")
            return

        folder_value = payload.get("folder_id")
        folder_id = int(folder_value) if folder_value not in (None, "") else None
        if folder_id is not None and not query_one(
            "SELECT id FROM bookmark_folders WHERE id = ?", (folder_id,)
        ):
            api_error(self, 400, "书签文件夹不存在。")
            return

        placeholders = ",".join("?" for _ in clean_ids)
        existing = query(
            f"SELECT id, folder_id FROM bookmarks WHERE id IN ({placeholders})",
            tuple(clean_ids),
        )
        if len(existing) != len(clean_ids):
            api_error(self, 400, "排序列表中存在不存在的书签。")
            return
        if any(row["folder_id"] != folder_id for row in existing):
            api_error(self, 400, "只能调整同一分类中的书签顺序。")
            return

        def update_order(conn):
            for index, item_id in enumerate(clean_ids):
                conn.execute(
                    """
                    UPDATE bookmarks
                    SET sort_order = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (index, now_text(), item_id),
                )

        transaction(update_order)
        self.send_json(200, {"ok": True, "ids": clean_ids})

    def api_bookmark_mark_valid(self, path):
        item_id = int(path.split("/")[3])
        if not query_one("SELECT id FROM bookmarks WHERE id = ?", (item_id,)):
            api_error(self, 404, "书签不存在。")
            return
        checked_at = now_text()
        execute(
            """
            UPDATE bookmarks
            SET link_status = 'valid', link_status_code = NULL,
                link_error = NULL, link_checked_at = ?
            WHERE id = ?
            """,
            (checked_at, item_id),
        )
        self.send_json(
            200,
            {
                "id": item_id,
                "link_status": "valid",
                "link_status_code": None,
                "link_checked_at": checked_at,
            },
        )

    def api_bookmark_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM bookmarks WHERE id = ?", (item_id,))
        if not current:
            api_error(self, 404, "书签不存在。")
            return
        if self.command == "DELETE":
            execute("DELETE FROM bookmarks WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return

        payload = get_payload(self)
        if payload is None:
            return
        try:
            url = normalize_bookmark_url(payload.get("url", current["url"]))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return

        title = str(payload.get("title", current["title"]) or "").strip()[:200]
        if not title:
            title = urlsplit(url).hostname or url
            if title.lower().startswith("www."):
                title = title[4:]
        description = str(
            payload.get("description", current["description"]) or ""
        ).strip()[:500]
        folder_value = payload.get("folder_id", current["folder_id"])
        folder_id = int(folder_value) if folder_value not in (None, "") else None
        if folder_id is not None and not query_one(
            "SELECT id FROM bookmark_folders WHERE id = ?", (folder_id,)
        ):
            api_error(self, 400, "书签文件夹不存在。")
            return
        if "sort_order" in payload:
            sort_order = int(payload.get("sort_order") or 0)
        elif folder_id != current["folder_id"]:
            sort_order = query_one(
                """
                SELECT COALESCE(MAX(sort_order), -1) AS value
                FROM bookmarks
                WHERE folder_id IS ?
                """,
                (folder_id,),
            )["value"] + 1
        else:
            sort_order = int(current["sort_order"] or 0)
        execute(
            """
            UPDATE bookmarks
            SET folder_id = ?, title = ?, url = ?, description = ?,
                sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                folder_id,
                title,
                url,
                description or None,
                sort_order,
                now_text(),
                item_id,
            ),
        )
        self.send_json(200, {"id": item_id, "title": title, "url": url})

    def api_bookmark_folders(self):
        rows = query(
            """
            SELECT f.*,
                   (SELECT COUNT(*) FROM bookmarks b WHERE b.folder_id = f.id) AS bookmark_count
            FROM bookmark_folders f
            ORDER BY f.sort_order, f.name, f.id
            """
        )
        paths = bookmark_folder_path_map()
        for row in rows:
            row["path"] = paths.get(row["id"], row["name"])
        self.send_json(200, rows)

    def api_bookmark_folder_create(self, payload):
        name = str(payload.get("name") or "").strip()[:80]
        if not name:
            api_error(self, 400, "文件夹名称不能为空。")
            return
        parent_value = payload.get("parent_id")
        parent_id = int(parent_value) if parent_value not in (None, "") else None
        if parent_id is not None and not query_one(
            "SELECT id FROM bookmark_folders WHERE id = ?", (parent_id,)
        ):
            api_error(self, 400, "上级文件夹不存在。")
            return
        sort_order = int(payload.get("sort_order") or 0)
        row_id = execute(
            """
            INSERT INTO bookmark_folders (name, parent_id, sort_order, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, parent_id, sort_order, now_text()),
        )
        self.send_json(201, {"id": row_id})

    def api_bookmark_folder_reorder(self, payload):
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            api_error(self, 400, "排序列表不能为空。")
            return
        clean_ids = []
        for item_id in ids:
            try:
                clean_ids.append(int(item_id))
            except (TypeError, ValueError):
                api_error(self, 400, "排序列表包含无效的文件夹。")
                return
        if len(set(clean_ids)) != len(clean_ids):
            api_error(self, 400, "排序列表中存在重复文件夹。")
            return
        parent_value = payload.get("parent_id")
        parent_id = int(parent_value) if parent_value not in (None, "") else None
        if parent_id is not None and not query_one(
            "SELECT id FROM bookmark_folders WHERE id = ?", (parent_id,)
        ):
            api_error(self, 400, "上级文件夹不存在。")
            return
        placeholders = ",".join("?" for _ in clean_ids)
        existing = query(
            f"SELECT id FROM bookmark_folders WHERE id IN ({placeholders})",
            tuple(clean_ids),
        )
        if len(existing) != len(clean_ids):
            api_error(self, 400, "排序列表中存在不存在的文件夹。")
            return

        def update_order(conn):
            for index, item_id in enumerate(clean_ids):
                conn.execute(
                    """
                    UPDATE bookmark_folders
                    SET parent_id = ?, sort_order = ?
                    WHERE id = ?
                    """,
                    (parent_id, index, item_id),
                )

        transaction(update_order)
        self.send_json(200, {"ok": True, "ids": clean_ids})

    def api_bookmark_folder_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM bookmark_folders WHERE id = ?", (item_id,))
        if not current:
            api_error(self, 404, "文件夹不存在。")
            return
        if self.command == "DELETE":
            bookmark_count = query_one(
                "SELECT COUNT(*) AS n FROM bookmarks WHERE folder_id = ?", (item_id,)
            )["n"]
            child_count = query_one(
                "SELECT COUNT(*) AS n FROM bookmark_folders WHERE parent_id = ?", (item_id,)
            )["n"]
            execute("DELETE FROM bookmark_folders WHERE id = ?", (item_id,))
            self.send_json(
                200,
                {
                    "ok": True,
                    "bookmarks_moved": bookmark_count,
                    "children_moved": child_count,
                },
            )
            return

        payload = get_payload(self)
        if payload is None:
            return
        name = str(payload.get("name", current["name"]) or "").strip()[:80]
        if not name:
            api_error(self, 400, "文件夹名称不能为空。")
            return
        parent_value = payload.get("parent_id", current["parent_id"])
        parent_id = int(parent_value) if parent_value not in (None, "") else None
        if parent_id == item_id:
            api_error(self, 400, "文件夹不能移动到自身。")
            return
        if parent_id is not None:
            if not query_one(
                "SELECT id FROM bookmark_folders WHERE id = ?", (parent_id,)
            ):
                api_error(self, 400, "上级文件夹不存在。")
                return
            if bookmark_folder_cycle(parent_id, item_id):
                api_error(self, 400, "不能把文件夹移动到自己的子文件夹中。")
                return
        sort_order = int(payload.get("sort_order", current["sort_order"]) or 0)
        execute(
            """
            UPDATE bookmark_folders
            SET name = ?, parent_id = ?, sort_order = ?
            WHERE id = ?
            """,
            (name, parent_id, sort_order, item_id),
        )
        self.send_json(200, {"ok": True})

    def api_warehouse_types(self):
        rows = query("SELECT * FROM warehouse_types ORDER BY sort_order, id")
        self.send_json(200, rows)

    def api_part_image_delete(self, path):
        part_id = int(path.split("/")[3])
        try:
            remove_part_image(part_id)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(200, {"ok": True})

    def api_inventory(self, query_params):
        search = str(query_params.get("search", [""])[0]).strip()
        location_id = query_params.get("location_id", [""])[0]
        conditions = []
        params = []
        if search:
            conditions.append(
                """(p.part_number LIKE ? OR p.lcsc_code LIKE ? OR p.brand LIKE ?
                    OR p.package LIKE ? OR l.code LIKE ? OR l.name LIKE ?)"""
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like, like])
        if location_id:
            try:
                root_id = int(location_id)
            except ValueError:
                root_id = None
            if root_id:
                loc_ids = query(
                    """WITH RECURSIVE loc_tree(id) AS (
                           SELECT ? UNION ALL
                           SELECT l.id FROM locations l JOIN loc_tree t ON l.parent_id = t.id
                       )
                       SELECT id FROM loc_tree""",
                    (root_id,),
                )
                ids = [row["id"] for row in loc_ids]
                if ids:
                    conditions.append(f"b.location_id IN ({','.join('?' * len(ids))})")
                    params.extend(ids)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = query(
            f"""
            SELECT b.id AS batch_id, b.quantity, b.received_quantity,
                   b.received_quantity - b.quantity AS used_quantity,
                   b.purchase_date, b.unit_price, b.channel, b.order_number, b.notes AS batch_notes,
                   p.id AS part_id, p.part_number, p.lcsc_code, p.brand, p.package, p.image_path,
                   p.category_id, c.name AS category_name, p.min_stock,
                   l.id AS location_id, l.code AS location_code, l.name AS location_name
            FROM batches b
            JOIN parts p ON p.id = b.part_id
            LEFT JOIN categories c ON c.id = p.category_id
            JOIN locations l ON l.id = b.location_id
            {where}
            ORDER BY l.code, p.part_number, b.id DESC
            """,
            params,
        )
        for row in rows:
            row["location_path"] = path_text("locations", row["location_id"], "code")
        self.send_json(200, rows)

    def api_stock_inbound(self, payload):
        part_id = payload.get("part_id")
        location_id = payload.get("location_id")
        quantity = float(payload.get("quantity") or 0)
        if not part_id or not location_id:
            api_error(self, 400, "请选择元件和存放位置。")
            return
        if quantity <= 0:
            api_error(self, 400, "入库数量必须大于 0。")
            return
        part = query_one("SELECT id FROM parts WHERE id = ?", (part_id,))
        location = query_one("SELECT id FROM locations WHERE id = ?", (location_id,))
        if not part or not location:
            api_error(self, 400, "元件或位置不存在。")
            return
        batch_id = transaction(
            lambda conn: self.insert_batch(
                conn,
                part_id=part_id,
                location_id=location_id,
                quantity=quantity,
                purchase_date=payload.get("purchase_date") or today_text(),
                unit_price=payload.get("unit_price"),
                channel=payload.get("channel") or "",
                order_number=payload.get("order_number") or "",
                notes=payload.get("notes") or "",
            )
        )
        self.send_json(201, {"id": batch_id})

    def insert_batch(self, conn, part_id, location_id, quantity, purchase_date, unit_price, channel, order_number, notes):
        cursor = conn.execute(
            """INSERT INTO batches
               (part_id, location_id, quantity, received_quantity, purchase_date,
                unit_price, channel, order_number, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                part_id,
                location_id,
                quantity,
                quantity,
                purchase_date,
                unit_price if unit_price not in (None, "") else None,
                channel or None,
                order_number or None,
                notes or None,
                now_text(),
            ),
        )
        batch_id = cursor.lastrowid
        conn.execute(
            """INSERT INTO movements
               (part_id, batch_id, project_id, movement_type, quantity,
                before_quantity, after_quantity, unit_price, channel, order_number, note, created_at)
               VALUES (?, ?, NULL, 'in', ?, 0, ?, ?, ?, ?, ?, ?)""",
            (
                part_id,
                batch_id,
                quantity,
                quantity,
                unit_price if unit_price not in (None, "") else None,
                channel or None,
                order_number or None,
                notes or None,
                now_text(),
            ),
        )
        return batch_id

    def api_stock_outbound(self, payload):
        batch_id = payload.get("batch_id")
        part_id = payload.get("part_id")
        quantity = float(payload.get("quantity") or 0)
        project_id = payload.get("project_id")
        note = payload.get("note") or ""
        if quantity <= 0:
            api_error(self, 400, "出库数量必须大于 0。")
            return
        if project_id:
            project = query_one("SELECT id FROM projects WHERE id = ?", (project_id,))
            if not project:
                api_error(self, 400, "项目不存在。")
                return
        if batch_id:
            batch = query_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
            if not batch:
                api_error(self, 404, "库存批次不存在。")
                return
            part_id = batch["part_id"]
        elif part_id:
            part = query_one("SELECT id FROM parts WHERE id = ?", (part_id,))
            if not part:
                api_error(self, 400, "元件不存在。")
                return
        else:
            api_error(self, 400, "请选择要出库的批次或元件。")
            return

        result = transaction(
            lambda conn: self.consume_batches(
                conn,
                part_id=part_id,
                batch_id=batch_id,
                quantity=quantity,
                project_id=project_id,
                note=note,
            )
        )
        self.send_json(200, result)

    def consume_batches(self, conn, part_id, batch_id, quantity, project_id, note):
        remaining = quantity
        consumed = []
        if batch_id:
            rows = [
                conn.execute(
                    "SELECT * FROM batches WHERE id = ? AND part_id = ?",
                    (batch_id, part_id),
                ).fetchone()
            ]
        else:
            rows = conn.execute(
                """SELECT * FROM batches
                   WHERE part_id = ? AND quantity > 0
                   ORDER BY (purchase_date IS NULL), purchase_date, id""",
                (part_id,),
            ).fetchall()
        if not rows:
            raise ValueError("没有找到可用库存。")
        available = sum(row["quantity"] for row in rows)
        if available < quantity:
            raise ValueError(f"可用库存不足，当前只有 {available:g}。")
        for row in rows:
            if remaining <= 0:
                break
            take = min(remaining, row["quantity"])
            before = row["quantity"]
            after = before - take
            conn.execute(
                "UPDATE batches SET quantity = ? WHERE id = ?",
                (after, row["id"]),
            )
            conn.execute(
                """INSERT INTO movements
                   (part_id, batch_id, project_id, movement_type, quantity,
                    before_quantity, after_quantity, unit_price, channel, order_number, note, created_at)
                   VALUES (?, ?, ?, 'out', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    part_id,
                    row["id"],
                    project_id,
                    take,
                    before,
                    after,
                    row["unit_price"],
                    row["channel"],
                    row["order_number"],
                    note or None,
                    now_text(),
                ),
            )
            consumed.append({"batch_id": row["id"], "quantity": take})
            remaining -= take
        return {"consumed": consumed, "quantity": quantity}

    def movement_rows(self, part_id=None, project_id=None, limit=50):
        conditions = []
        params = []
        if part_id:
            conditions.append("m.part_id = ?")
            params.append(part_id)
        if project_id:
            conditions.append("m.project_id = ?")
            params.append(project_id)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)
        return query(
            f"""
            SELECT m.*, p.part_number, p.lcsc_code, p.package,
                   pr.name AS project_name, l.code AS location_code
            FROM movements m
            JOIN parts p ON p.id = m.part_id
            LEFT JOIN projects pr ON pr.id = m.project_id
            LEFT JOIN batches b ON b.id = m.batch_id
            LEFT JOIN locations l ON l.id = b.location_id
            {where}
            ORDER BY m.id DESC
            LIMIT ?
            """,
            params,
        )

    def api_movements(self, query_params):
        part_id = query_params.get("part_id", [""])[0]
        project_id = query_params.get("project_id", [""])[0]
        rows = self.movement_rows(
            part_id=int(part_id) if part_id else None,
            project_id=int(project_id) if project_id else None,
            limit=200,
        )
        self.send_json(200, rows)

    def api_movement_item(self, path):
        movement_id = int(path.rsplit("/", 1)[1])
        if self.command == "DELETE":
            try:
                transaction(lambda conn: self.delete_movement(conn, movement_id))
            except ValueError as exc:
                api_error(self, 400, str(exc))
                return
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            transaction(lambda conn: self.update_movement(conn, movement_id, payload))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(200, {"ok": True})

    def delete_movement(self, conn, movement_id):
        movement = conn.execute(
            "SELECT * FROM movements WHERE id = ?", (movement_id,)
        ).fetchone()
        if not movement:
            raise ValueError("出入库记录不存在。")
        if movement["movement_type"] == "out":
            if not movement["batch_id"]:
                raise ValueError("该出库记录没有关联库存批次，无法恢复库存。")
            batch = conn.execute(
                "SELECT id FROM batches WHERE id = ?", (movement["batch_id"],)
            ).fetchone()
            if not batch:
                raise ValueError("关联库存批次已不存在。")
            conn.execute(
                "UPDATE batches SET quantity = quantity + ? WHERE id = ?",
                (movement["quantity"], movement["batch_id"]),
            )
            conn.execute("DELETE FROM movements WHERE id = ?", (movement_id,))
        elif movement["movement_type"] == "in":
            batch_id = movement["batch_id"]
            if batch_id:
                out_count = conn.execute(
                    """SELECT COUNT(*) AS n FROM movements
                       WHERE batch_id = ? AND movement_type = 'out' AND id <> ?""",
                    (batch_id, movement_id),
                ).fetchone()["n"]
                if out_count:
                    raise ValueError("该入库记录已经被出库使用，请先删除对应出库记录。")
                conn.execute("DELETE FROM movements WHERE id = ?", (movement_id,))
                conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
            else:
                conn.execute("DELETE FROM movements WHERE id = ?", (movement_id,))
        else:
            conn.execute("DELETE FROM movements WHERE id = ?", (movement_id,))

    def update_movement(self, conn, movement_id, payload):
        movement = conn.execute(
            "SELECT * FROM movements WHERE id = ?", (movement_id,)
        ).fetchone()
        if not movement:
            raise ValueError("出入库记录不存在。")
        fields = []
        values = []
        if "note" in payload:
            fields.append("note = ?")
            values.append(payload.get("note") or None)
        if "project_id" in payload:
            if movement["movement_type"] != "out":
                raise ValueError("入库记录不能关联项目。")
            project_id = payload.get("project_id")
            if project_id:
                project = conn.execute(
                    "SELECT id FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                if not project:
                    raise ValueError("关联项目不存在。")
            fields.append("project_id = ?")
            values.append(project_id)
        if payload.get("created_at"):
            created_at = str(payload["created_at"]).replace("T", " ")
            fields.append("created_at = ?")
            values.append(created_at)
        if fields:
            conn.execute(
                f"UPDATE movements SET {', '.join(fields)} WHERE id = ?",
                values + [movement_id],
            )

    def api_wishlist(self):
        rows = query(
            """
            SELECT w.*, p.part_number AS linked_part_number, p.lcsc_code AS linked_lcsc,
                   COALESCE((SELECT SUM(b.quantity) FROM batches b WHERE b.part_id = p.id), 0) AS linked_stock
            FROM wishlist_items w
            LEFT JOIN parts p ON p.id = w.part_id
            ORDER BY CASE w.status WHEN 'open' THEN 0 ELSE 1 END, w.created_at DESC, w.id DESC
            """
        )
        self.send_json(200, rows)

    def api_create_wishlist(self, payload):
        part_id = payload.get("part_id")
        target_quantity = float(payload.get("target_quantity") or 1)
        if target_quantity <= 0:
            api_error(self, 400, "目标数量必须大于 0。")
            return
        new_id = execute(
            """INSERT INTO wishlist_items
               (part_id, lcsc_code, brand, part_number, package, description,
                target_quantity, unit_price, priority, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (
                part_id,
                payload.get("lcsc_code") or None,
                payload.get("brand") or None,
                payload.get("part_number") or None,
                payload.get("package") or None,
                payload.get("description") or None,
                target_quantity,
                payload.get("unit_price"),
                payload.get("priority") or "normal",
                payload.get("notes") or None,
                now_text(),
            ),
        )
        self.send_json(201, {"id": new_id})

    def api_wishlist_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        if self.command == "DELETE":
            execute("DELETE FROM wishlist_items WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        target_quantity = float(payload.get("target_quantity") or 1)
        if target_quantity <= 0:
            api_error(self, 400, "目标数量必须大于 0。")
            return
        execute(
            """UPDATE wishlist_items SET
               part_id = ?, lcsc_code = ?, brand = ?, part_number = ?, package = ?,
               description = ?, target_quantity = ?, unit_price = ?, priority = ?,
               status = ?, notes = ?
               WHERE id = ?""",
            (
                payload.get("part_id"),
                payload.get("lcsc_code") or None,
                payload.get("brand") or None,
                payload.get("part_number") or None,
                payload.get("package") or None,
                payload.get("description") or None,
                target_quantity,
                payload.get("unit_price"),
                payload.get("priority") or "normal",
                payload.get("status") or "open",
                payload.get("notes") or None,
                item_id,
            ),
        )
        self.send_json(200, {"ok": True})

    def api_convert_wishlist(self, path, payload):
        item_id = int(path.split("/")[3])
        item = query_one("SELECT * FROM wishlist_items WHERE id = ?", (item_id,))
        if not item:
            api_error(self, 404, "待购入条目不存在。")
            return
        location_id = payload.get("location_id")
        category_id = payload.get("category_id")
        quantity = float(payload.get("quantity") or item["target_quantity"] or 1)
        part_id = payload.get("part_id") or item["part_id"]
        if quantity <= 0:
            api_error(self, 400, "数量必须大于 0。")
            return
        if not location_id:
            api_error(self, 400, "请选择入库位置。")
            return

        def run(conn):
            nonlocal part_id
            if not part_id:
                existing = conn.execute(
                    """SELECT * FROM parts
                       WHERE (lcsc_code IS NOT NULL AND lcsc_code = ?)
                          OR (part_number <> '' AND part_number = ?)
                       ORDER BY id LIMIT 1""",
                    (item["lcsc_code"], item["part_number"]),
                ).fetchone()
                if existing:
                    part_id = existing["id"]
                else:
                    lcsc_code = item["lcsc_code"] or None
                    cursor = conn.execute(
                        """INSERT INTO parts
                           (part_number, lcsc_code, brand, category_id, package,
                            temperature_range, voltage_rating, description, datasheet_url,
                            notes, min_stock, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, '', '', ?, ?, '', 0, ?, ?)""",
                        (
                            item["part_number"] or item["lcsc_code"] or "未命名元件",
                            lcsc_code,
                            item["brand"],
                            category_id,
                            item["package"],
                            item["description"],
                            f"https://www.lcsc.com/product-detail/{lcsc_code}.html" if lcsc_code else None,
                            now_text(),
                            now_text(),
                        ),
                    )
                    part_id = cursor.lastrowid
            batch_id = self.insert_batch(
                conn,
                part_id=part_id,
                location_id=location_id,
                quantity=quantity,
                purchase_date=payload.get("purchase_date") or today_text(),
                unit_price=payload.get("unit_price") if payload.get("unit_price") not in (None, "") else item["unit_price"],
                channel=payload.get("channel") or "",
                order_number=payload.get("order_number") or "",
                notes=payload.get("notes") or "待购入转为入库",
            )
            conn.execute(
                "UPDATE wishlist_items SET status = 'purchased', purchased_at = ?, part_id = ? WHERE id = ?",
                (now_text(), part_id, item_id),
            )
            return {"batch_id": batch_id, "part_id": part_id}

        result = transaction(run)
        self.send_json(200, result)

    def api_import_lcsc(self, payload):
        try:
            result = import_lcsc_data(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if payload.get("auto_fetch_images", True):
            threading.Thread(target=launch_lcsc_image_fetch, daemon=True).start()
        self.send_json(200, result)

    def api_bom_compare(self, payload):
        try:
            file_name = str(payload.get("file_name") or "BOM.csv")
            data_base64 = payload.get("data_base64") or ""
            match_mode = str(payload.get("match_mode") or "auto")
            if match_mode not in ("auto", "part_number", "lcsc_code", "description"):
                match_mode = "auto"
            try:
                data = base64.b64decode(data_base64)
            except Exception as exc:
                raise ValueError("文件内容无法解码。") from exc
            rows = parse_bom_rows(data, file_name)
            items = extract_bom_items(rows)
            if not items:
                raise ValueError("BOM 中没有可处理的数据行。")
            report = compare_bom_items(items, match_mode)
            report_id, saved = save_bom_report(file_name, "", report, match_mode)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        except Exception as exc:
            api_error(self, 500, f"BOM 对比失败：{exc}")
            return
        self.send_json(200, {"id": report_id, "report": saved})

    def api_bom_reports(self):
        self.send_json(200, list_bom_reports())

    def api_bom_report(self, path):
        report_id = path.rsplit("/", 1)[1]
        try:
            payload = load_bom_report(report_id)
        except ValueError as exc:
            api_error(self, 404, str(exc))
            return
        self.send_json(200, payload)

    def api_bom_report_csv(self, path):
        report_id = path.rsplit("/", 2)[1]
        try:
            payload = load_bom_report(report_id)
        except ValueError as exc:
            api_error(self, 404, str(exc))
            return
        self.send_csv(200, report_csv_text(payload), f"{payload['file_name']}_缺料清单.csv")

    def api_bom_watch_status(self):
        self.send_json(200, bom_watch_status())

    def api_bom_watch_start(self, payload):
        try:
            status = start_bom_watch(
                payload.get("folder"),
                int(payload.get("interval") or 30),
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(200, status)

    def api_bom_watch_stop(self):
        self.send_json(200, stop_bom_watch())


def main():
    init_db()
    load_auth_state()
    server = ThreadingHTTPServer((HOST, PORT), InventoryHandler)
    print(f"电子元件库存系统已启动：http://127.0.0.1:{PORT}")
    for ip in local_ips():
        if ip != "127.0.0.1":
            print(f"手机局域网访问：http://{ip}:{PORT}")
    if AUTH_STATE.get("enabled"):
        print("已开启访问密码：未登录访问会跳转到 /login，退出登录访问 /logout。")
    else:
        print("提示：当前没有设置访问密码，同网络内任何人都能读写数据。")
        print("      要放到公网，请先设置 INVENTORY_PASSWORD 环境变量，或运行 python tools/set_password.py。")
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
