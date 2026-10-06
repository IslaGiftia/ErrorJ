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
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".opus")
mimetypes.add_type("audio/ogg", ".oga")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/aac", ".aac")


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
PROMPTS_SEED_PATH = BASE_DIR / "config" / "prompts-seed.json"
DB_PATH = DATA_DIR / "inventory.db"
HOST = os.environ.get("INVENTORY_HOST", "0.0.0.0")
PORT = int(os.environ.get("INVENTORY_PORT", "8000"))
MAP_PUBLIC = os.environ.get("INVENTORY_MAP_PUBLIC", "1").strip().lower() not in (
    "0",
    "false",
    "off",
    "no",
)
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
BOM_REPORT_DIR = DATA_DIR / "bom_reports"
BOM_WATCH_STATE_PATH = DATA_DIR / "bom_watch_state.json"
PART_IMAGE_DIR = DATA_DIR / "part_images"
BOOKMARK_FAVICON_DIR = DATA_DIR / "bookmark_favicons"
NOTE_IMAGE_DIR = DATA_DIR / "note_images"
RECOMMEND_IMAGE_DIR = DATA_DIR / "recommend_images"
MAP_IMAGE_DIR = DATA_DIR / "map_images"
MUSIC_COVER_DIR = DATA_DIR / "music_covers"
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
RECOMMEND_IMAGE_MAX_BYTES = 15 * 1024 * 1024
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
    "/recommendations",
    "/music",
    "/references",
    "/games",
    "/favicon.ico",
}
PUBLIC_GET_APIS = {
    "/api/health",
    "/api/auth/status",
    "/api/site/messages",
    "/api/moments",
    "/api/recommendations",
    "/api/site/photos",
    "/api/site/music",
    "/api/site/links",
}
PUBLIC_POST_APIS = {
    "/api/login",
    "/api/register",
    "/api/logout",
}
PUBLIC_DATA_PREFIXES = (
    "moment_images/",
    "site_photos/",
    "site_music_files/",
    "music_covers/",
    "recommend_images/",
)
if MAP_PUBLIC:
    PUBLIC_PAGES.add("/map")
    PUBLIC_GET_APIS.add("/api/map")
    PUBLIC_DATA_PREFIXES = PUBLIC_DATA_PREFIXES + ("map_images/",)
USERNAME_RE = re.compile(r"^[\w.-]{3,32}$", re.UNICODE)
RESERVED_USERNAMES = {"owner", "admin", "administrator", "root", "system"}
NICKNAME_RE = re.compile(r"^[\w\u4e00-\u9fff·．.\-_\u0020]{2,16}$", re.UNICODE)
RESERVED_NICKNAMES = {
    "管理员",
    "admin",
    "administrator",
    "owner",
    "root",
    "system",
    "error酱",
    "errorjiang",
    "系统",
    "官方",
}
NICKNAME_CHANGE_DAYS = 30
ADMIN_PERMISSION = "system:admin"

PERMISSION_GROUPS = (
    {
        "key": "inventory",
        "label": "仓库（电子元件）",
        "items": (
            {"key": "inventory:view", "label": "查看仓库、元件、出入库记录"},
            {"key": "inventory:write", "label": "增删改元件、出入库、BOM 对比"},
        ),
    },
    {
        "key": "bookmarks",
        "label": "网页收藏",
        "items": (
            {"key": "bookmarks:view", "label": "查看网页收藏"},
            {"key": "bookmarks:write", "label": "增删改收藏、导入 Firefox、检查链接"},
        ),
    },
    {
        "key": "notes",
        "label": "学习笔记",
        "items": (
            {"key": "notes:view", "label": "查看学习笔记"},
            {"key": "notes:write", "label": "新增、编辑、导入导出笔记"},
        ),
    },
    {
        "key": "workbench",
        "label": "工作台",
        "items": (
            {"key": "workbench:view", "label": "查看工作台资料与维修台账"},
            {"key": "workbench:write", "label": "上传资料、维护维修台账"},
            {"key": "prompts:view", "label": "查看 AI 提示词"},
            {"key": "prompts:write", "label": "增删改 AI 提示词"},
        ),
    },
    {
        "key": "map",
        "label": "地图",
        "items": (
            {"key": "map:write", "label": "添加标记、管理自己添加的标记与照片"},
            {"key": "map:write_all", "label": "编辑和删除所有标记"},
            {"key": "map:manage_categories", "label": "管理地图分类"},
            {"key": "map:import", "label": "导入标记数据"},
            {"key": "map:export", "label": "导出地图数据"},
        ),
    },
    {
        "key": "site",
        "label": "站点内容",
        "items": (
            {"key": "music:write", "label": "上传、编辑歌单"},
            {"key": "links:write", "label": "管理宝藏网站链接"},
            {"key": "photos:write", "label": "管理照片墙"},
            {"key": "messages:attach_auto", "label": "留言附件免审核（可信用户）"},
        ),
    },
    {
        "key": "system",
        "label": "系统",
        "items": (
            {
                "key": ADMIN_PERMISSION,
                "label": "授予管理员（拥有全部权限，除不能删除站长）",
                "admin_only": True,
            },
        ),
    },
)
PERMISSION_LABELS = {
    item["key"]: item["label"]
    for group in PERMISSION_GROUPS
    for item in group["items"]
}
DEFAULT_MEMBER_PERMISSIONS = ("map:write", "map:import")
GRANTABLE_PERMISSIONS = tuple(
    item["key"]
    for group in PERMISSION_GROUPS
    for item in group["items"]
)

PERMISSION_ROUTE_MODULES = (
    ("/api/parts", "inventory"),
    ("/api/categories", "inventory"),
    ("/api/locations", "inventory"),
    ("/api/projects", "inventory"),
    ("/api/inventory", "inventory"),
    ("/api/movements", "inventory"),
    ("/api/wishlist", "inventory"),
    ("/api/warehouse", "inventory"),
    ("/api/bom", "inventory"),
    ("/api/dashboard", "inventory"),
    ("/api/import/lcsc", "inventory"),
    ("/api/bookmarks", "bookmarks"),
    ("/api/bookmark-folders", "bookmarks"),
    ("/api/notes", "notes"),
    ("/api/workbench", "workbench"),
    ("/api/prompts", "prompts"),
    ("/api/moments", "moments"),
    ("/api/recommendations", "recommendations"),
    ("/api/site/music", "music"),
    ("/api/site/photos", "photos"),
    ("/api/site/links", "links"),
)
PAGE_PERMISSIONS = {
    "/inventory": ("inventory:view", "inventory:write"),
    "/bookmarks": ("bookmarks:view", "bookmarks:write"),
    "/notes": ("notes:view", "notes:write"),
    "/workbench": ("workbench:view", "workbench:write", "prompts:view", "prompts:write"),
}

SENSITIVE_SEED_WORDS = (
    ("共产党", "政治"),
    ("国民党", "政治"),
    ("杀人", "暴力"),
    ("砍死", "暴力"),
    ("砍人", "暴力"),
    ("自杀", "暴力"),
    ("爆炸", "暴力"),
    ("炸弹", "暴力"),
    ("枪支", "暴力"),
    ("毒品", "暴力"),
    ("傻逼", "辱骂"),
    ("脑残", "辱骂"),
    ("废物", "辱骂"),
    ("去死", "辱骂"),
    ("贱人", "辱骂"),
    ("色情", "色情"),
    ("嫖娼", "色情"),
    ("卖淫", "色情"),
    ("约炮", "色情"),
    ("成人影片", "色情"),
    ("加微信", "广告"),
    ("加QQ", "广告"),
    ("代购", "广告"),
    ("刷单", "广告"),
    ("博彩", "广告"),
    ("赌博", "广告"),
    ("网贷", "广告"),
    ("优惠券群", "广告"),
)
SENSITIVE_CATEGORIES = ("政治", "暴力", "辱骂", "色情", "广告", "自定义")

NOTIFY_CHANNELS = (
    {"key": "wecom", "label": "企业微信群机器人", "hint": "群机器人 Webhook 地址"},
    {"key": "dingtalk", "label": "钉钉群机器人", "hint": "机器人 Webhook 地址（安全设置建议用关键词，关键词填 Error酱）"},
    {"key": "feishu", "label": "飞书群机器人", "hint": "自定义机器人 Webhook 地址"},
    {"key": "bark", "label": "Bark（iOS）", "hint": "形如 https://api.day.app/你的Key"},
    {"key": "serverchan", "label": "Server酱（微信）", "hint": "形如 https://sctapi.ftqq.com/你的SendKey.send"},
    {"key": "json", "label": "通用 JSON Webhook", "hint": "会 POST {title, body, event, url, time} 到该地址"},
)
NOTIFY_EVENTS = (
    {"key": "register", "label": "新的注册申请", "default": True},
    {"key": "attachment", "label": "新的待审核附件", "default": True},
    {"key": "message", "label": "新的留言", "default": False},
)
NOTIFY_DEFAULT_EVENTS = tuple(
    item["key"] for item in NOTIFY_EVENTS if item.get("default")
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
MAP_PHOTO_MAX_BYTES = 8 * 1024 * 1024
MAP_PHOTO_MAX_COUNT = 9
MUSIC_MAX_BYTES = 60 * 1024 * 1024
MUSIC_COVER_MAX_BYTES = 5 * 1024 * 1024
MUSIC_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus"}
MOMENT_IMAGE_TOTAL_MAX_BYTES = 15 * 1024 * 1024
MOMENT_IMAGE_MAX_COUNT = 9
MESSAGE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MESSAGE_FILE_EXTENSIONS = MESSAGE_IMAGE_EXTENSIONS | {
    ".pdf",
    ".txt",
    ".md",
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
RECOMMEND_KINDS = {"site", "tool", "movie", "anime"}
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
    MAP_IMAGE_DIR.mkdir(exist_ok=True)
    MUSIC_COVER_DIR.mkdir(exist_ok=True)
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
                status TEXT NOT NULL DEFAULT 'pending',
                uploaded_by INTEGER,
                reviewed_by TEXT,
                reviewed_at TEXT,
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
                album TEXT,
                source_type TEXT NOT NULL DEFAULT 'url',
                source_id TEXT,
                cover_path TEXT,
                duration REAL,
                file_size INTEGER,
                mime_type TEXT,
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

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL DEFAULT 'site',
                bookmark_id INTEGER REFERENCES bookmarks(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                url TEXT,
                download_url TEXT,
                cover_path TEXT,
                icon_url TEXT,
                description TEXT,
                category TEXT,
                tags TEXT,
                rating REAL,
                release_year INTEGER,
                status TEXT,
                pinned INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS map_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER REFERENCES map_categories(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                glyph TEXT NOT NULL DEFAULT '·',
                color TEXT NOT NULL DEFAULT '#7b68ee',
                note TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS map_places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER REFERENCES map_categories(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                subtitle TEXT,
                address TEXT,
                note TEXT,
                signature TEXT,
                tags TEXT,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                status TEXT,
                rating INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_map_places_category
                ON map_places(category_id);

            CREATE TABLE IF NOT EXISTS map_place_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                place_id INTEGER NOT NULL REFERENCES map_places(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                original_name TEXT,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_map_place_photos_place
                ON map_place_photos(place_id);

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                nickname TEXT,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                nickname_updated_at TEXT,
                silenced_until TEXT,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                permission TEXT NOT NULL,
                granted_by TEXT,
                granted_at TEXT NOT NULL,
                PRIMARY KEY (user_id, permission)
            );

            CREATE TABLE IF NOT EXISTS permission_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_kind TEXT NOT NULL DEFAULT 'owner',
                actor_id INTEGER NOT NULL DEFAULT 0,
                actor_name TEXT,
                target_id INTEGER,
                target_name TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sensitive_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT '自定义',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notify_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                title TEXT,
                body TEXT,
                channel TEXT,
                status TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
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
            CREATE INDEX IF NOT EXISTS idx_recommendations_kind ON recommendations(kind);
            CREATE INDEX IF NOT EXISTS idx_recommendations_order ON recommendations(kind, pinned, sort_order, id);
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
        recommendation_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(recommendations)").fetchall()
        ]
        if "bookmark_id" not in recommendation_columns:
            conn.execute(
                "ALTER TABLE recommendations ADD COLUMN bookmark_id INTEGER "
                "REFERENCES bookmarks(id) ON DELETE SET NULL"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recommendations_bookmark "
            "ON recommendations(bookmark_id)"
        )
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
        map_place_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(map_places)").fetchall()
        }
        for column, ddl in (
            ("status", "ALTER TABLE map_places ADD COLUMN status TEXT"),
            ("rating", "ALTER TABLE map_places ADD COLUMN rating INTEGER NOT NULL DEFAULT 0"),
            ("created_by", "ALTER TABLE map_places ADD COLUMN created_by INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in map_place_columns:
                conn.execute(ddl)
        map_category_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(map_categories)").fetchall()
        }
        if "parent_id" not in map_category_columns:
            conn.execute(
                """ALTER TABLE map_categories
                   ADD COLUMN parent_id INTEGER REFERENCES map_categories(id) ON DELETE CASCADE"""
            )
        music_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(site_music)").fetchall()
        }
        for column, ddl in (
            ("album", "ALTER TABLE site_music ADD COLUMN album TEXT"),
            ("cover_path", "ALTER TABLE site_music ADD COLUMN cover_path TEXT"),
            ("duration", "ALTER TABLE site_music ADD COLUMN duration REAL"),
            ("file_size", "ALTER TABLE site_music ADD COLUMN file_size INTEGER"),
            ("mime_type", "ALTER TABLE site_music ADD COLUMN mime_type TEXT"),
        ):
            if column not in music_columns:
                conn.execute(ddl)
        user_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        for column, ddl in (
            ("nickname", "ALTER TABLE users ADD COLUMN nickname TEXT"),
            ("nickname_updated_at", "ALTER TABLE users ADD COLUMN nickname_updated_at TEXT"),
            ("silenced_until", "ALTER TABLE users ADD COLUMN silenced_until TEXT"),
        ):
            if column not in user_columns:
                conn.execute(ddl)
        message_file_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(site_message_files)").fetchall()
        }
        for column, ddl in (
            (
                "status",
                # 老数据本来就已公开显示，迁移时直接标记为已通过
                "ALTER TABLE site_message_files ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'",
            ),
            ("uploaded_by", "ALTER TABLE site_message_files ADD COLUMN uploaded_by INTEGER"),
            ("reviewed_by", "ALTER TABLE site_message_files ADD COLUMN reviewed_by TEXT"),
            ("reviewed_at", "ALTER TABLE site_message_files ADD COLUMN reviewed_at TEXT"),
        ):
            if column not in message_file_columns:
                conn.execute(ddl)
        migrated = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'map_categories_v2'"
        ).fetchone()
        if not migrated:
            total = conn.execute("SELECT COUNT(*) AS n FROM map_categories").fetchone()["n"]
            top_count = conn.execute(
                "SELECT COUNT(*) AS n FROM map_categories WHERE parent_id IS NULL"
            ).fetchone()["n"]
            if total > 0 and top_count == total:
                cursor = conn.execute(
                    """INSERT INTO map_categories
                           (parent_id, name, glyph, color, note, sort_order, created_at)
                       VALUES (NULL, ?, ?, ?, ?, ?, ?)""",
                    ("美食", "食", "#e0762e", "餐厅、小吃、饮品等", -1, now_text()),
                )
                parent_id = cursor.lastrowid
                conn.execute(
                    "UPDATE map_categories SET parent_id = ? WHERE id != ?",
                    (parent_id, parent_id),
                )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('map_categories_v2', ?)",
                (now_text(),),
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
            seed_path = PROMPTS_SEED_PATH
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

    count = conn.execute("SELECT COUNT(*) AS n FROM sensitive_words").fetchone()["n"]
    if count == 0:
        stamp = now_text()
        for word, category in SENSITIVE_SEED_WORDS:
            conn.execute(
                "INSERT OR IGNORE INTO sensitive_words (word, category, created_at) VALUES (?, ?, ?)",
                (word, category, stamp),
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


# ---------- 音频元数据（MP3 / FLAC / M4A / WAV） ----------

def _image_ext_from_magic(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _image_ext_from_mime(mime):
    mime = (mime or "").lower()
    if "png" in mime:
        return ".png"
    if "gif" in mime:
        return ".gif"
    if "webp" in mime:
        return ".webp"
    return ".jpg"


def _id3_decode_text(frame):
    if not frame:
        return ""
    encoding = frame[0]
    payload = frame[1:]
    try:
        if encoding == 0:
            text = payload.decode("latin-1", "ignore")
        elif encoding == 1:
            text = payload.decode("utf-16", "ignore")
        elif encoding == 2:
            text = payload.decode("utf-16-be", "ignore")
        else:
            text = payload.decode("utf-8", "ignore")
    except Exception:
        return ""
    return text.split("\x00")[0].strip()


def _id3_picture(frame, major):
    if not frame:
        return None
    encoding = frame[0]
    rest = frame[1:]
    if major == 2:
        mime = {
            "PNG": "image/png",
            "JPG": "image/jpeg",
        }.get(rest[:3].decode("latin-1", "ignore").upper(), "image/jpeg")
        rest = rest[3:]
    else:
        zero = rest.find(b"\x00")
        if zero < 0:
            return None
        mime = rest[:zero].decode("latin-1", "ignore")
        rest = rest[zero + 1 :]
    if not rest:
        return None
    rest = rest[1:]  # 图片类型
    if encoding in (1, 2):
        end = -1
        index = 0
        while index + 1 < len(rest):
            if rest[index] == 0 and rest[index + 1] == 0:
                end = index
                break
            index += 2
        rest = rest[end + 2 :] if end >= 0 else b""
    else:
        zero = rest.find(b"\x00")
        rest = rest[zero + 1 :] if zero >= 0 else b""
    if not rest:
        return None
    return rest, (_image_ext_from_magic(rest) or _image_ext_from_mime(mime))


def parse_id3v2(raw):
    """解析 ID3v2 标签，返回标题、歌手、专辑和内嵌封面。"""
    info = {"title": "", "artist": "", "album": "", "cover": None}
    if len(raw) < 10 or raw[:3] != b"ID3":
        return info
    major = raw[3]
    size = (
        ((raw[6] & 0x7F) << 21)
        | ((raw[7] & 0x7F) << 14)
        | ((raw[8] & 0x7F) << 7)
        | (raw[9] & 0x7F)
    )
    body = raw[10 : 10 + size]
    pos = 0
    while pos < len(body):
        if major == 2:
            frame_id = body[pos : pos + 3]
            header_size = 6
            if len(frame_id) < 3 or not frame_id.strip(b"\x00"):
                break
            frame_size = int.from_bytes(body[pos + 3 : pos + 6], "big")
        else:
            frame_id = body[pos : pos + 4]
            header_size = 10
            if len(frame_id) < 4 or not frame_id.strip(b"\x00"):
                break
            if major == 4:
                frame_size = (
                    ((body[pos + 4] & 0x7F) << 21)
                    | ((body[pos + 5] & 0x7F) << 14)
                    | ((body[pos + 6] & 0x7F) << 7)
                    | (body[pos + 7] & 0x7F)
                )
            else:
                frame_size = int.from_bytes(body[pos + 4 : pos + 8], "big")
        if frame_size <= 0 or pos + header_size + frame_size > len(body):
            break
        frame = body[pos + header_size : pos + header_size + frame_size]
        pos += header_size + frame_size
        key = frame_id.decode("latin-1", "ignore")
        if key in ("TIT2", "TT2"):
            info["title"] = _id3_decode_text(frame)
        elif key in ("TPE1", "TP1"):
            info["artist"] = _id3_decode_text(frame)
        elif key in ("TALB", "TAL"):
            info["album"] = _id3_decode_text(frame)
        elif key in ("APIC", "PIC"):
            picture = _id3_picture(frame, major)
            if picture:
                info["cover"] = picture
    return info


_MP3_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
_MP3_BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
_MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration(raw):
    """MP3 时长：优先读 Xing/Info 帧，否则按首帧码率估算。"""
    start = 0
    if raw[:3] == b"ID3" and len(raw) >= 10:
        size = (
            ((raw[6] & 0x7F) << 21)
            | ((raw[7] & 0x7F) << 14)
            | ((raw[8] & 0x7F) << 7)
            | (raw[9] & 0x7F)
        )
        start = 10 + size
        if raw[5] & 0x10:
            start += 10
    pos = start
    while pos + 4 <= len(raw):
        header = int.from_bytes(raw[pos : pos + 4], "big")
        if (header & 0xFFE00000) == 0xFFE00000:
            version = (header >> 19) & 3
            layer = (header >> 17) & 3
            bitrate_index = (header >> 12) & 0xF
            rate_index = (header >> 10) & 3
            if (
                version != 1
                and layer == 1
                and bitrate_index not in (0, 15)
                and rate_index != 3
            ):
                break
        pos += 1
    else:
        return None
    version = (header >> 19) & 3
    bitrate_index = (header >> 12) & 0xF
    rate_index = (header >> 10) & 3
    sample_rate = _MP3_RATES.get(version, _MP3_RATES[3])[rate_index]
    bitrate = (
        _MP3_BITRATES_V1_L3[bitrate_index]
        if version == 3
        else _MP3_BITRATES_V2_L3[bitrate_index]
    )
    side_info = 32 if version == 3 else 17
    xing_pos = pos + 4 + side_info
    if raw[xing_pos : xing_pos + 4] in (b"Xing", b"Info"):
        flags = (
            int.from_bytes(raw[xing_pos + 4 : xing_pos + 8], "big")
            if len(raw) >= xing_pos + 8
            else 0
        )
        if flags & 0x1 and len(raw) >= xing_pos + 12:
            frames = int.from_bytes(raw[xing_pos + 8 : xing_pos + 12], "big")
            samples_per_frame = 1152 if version == 3 else 576
            if frames > 0 and sample_rate:
                return frames * samples_per_frame / sample_rate
    if bitrate and sample_rate:
        audio_bytes = max(0, len(raw) - pos)
        return audio_bytes * 8 / (bitrate * 1000)
    return None


def parse_flac(raw):
    """解析 FLAC：STREAMINFO 时长、VORBIS 注释、PICTURE 封面。"""
    info = {"title": "", "artist": "", "album": "", "cover": None, "duration": None}
    if raw[:4] != b"fLaC":
        return info
    pos = 4
    while pos + 4 <= len(raw):
        block_header = raw[pos]
        block_type = block_header & 0x7F
        last = bool(block_header & 0x80)
        size = int.from_bytes(raw[pos + 1 : pos + 4], "big")
        block = raw[pos + 4 : pos + 4 + size]
        pos += 4 + size
        if block_type == 0 and len(block) >= 18:
            bits = int.from_bytes(block[10:18], "big")
            sample_rate = bits >> 44
            total_samples = bits & ((1 << 36) - 1)
            if sample_rate and total_samples:
                info["duration"] = total_samples / sample_rate
        elif block_type == 4 and len(block) >= 8:
            cursor = 0
            vendor_len = int.from_bytes(block[cursor : cursor + 4], "little")
            cursor += 4 + vendor_len
            if cursor + 4 <= len(block):
                count = int.from_bytes(block[cursor : cursor + 4], "little")
                cursor += 4
                for _ in range(min(count, 200)):
                    if cursor + 4 > len(block):
                        break
                    item_len = int.from_bytes(block[cursor : cursor + 4], "little")
                    cursor += 4
                    item = block[cursor : cursor + item_len]
                    cursor += item_len
                    if b"=" not in item:
                        continue
                    key, _, value = item.partition(b"=")
                    key = key.decode("utf-8", "ignore").upper()
                    value = value.decode("utf-8", "ignore").strip()
                    if key == "TITLE" and not info["title"]:
                        info["title"] = value
                    elif key == "ARTIST" and not info["artist"]:
                        info["artist"] = value
                    elif key == "ALBUM" and not info["album"]:
                        info["album"] = value
        elif block_type == 6 and len(block) >= 32:
            cursor = 4
            mime_len = int.from_bytes(block[cursor : cursor + 4], "big")
            cursor += 4
            mime = block[cursor : cursor + mime_len].decode("latin-1", "ignore")
            cursor += mime_len
            if cursor + 4 <= len(block):
                desc_len = int.from_bytes(block[cursor : cursor + 4], "big")
                cursor += 4 + desc_len + 16
                if cursor + 4 <= len(block):
                    data_len = int.from_bytes(block[cursor : cursor + 4], "big")
                    cursor += 4
                    data = block[cursor : cursor + data_len]
                    if data:
                        info["cover"] = (
                            data,
                            _image_ext_from_magic(data) or _image_ext_from_mime(mime),
                        )
        if last:
            break
    return info


def _mp4_children(raw, start, end):
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(raw[pos : pos + 4], "big")
        kind = raw[pos + 4 : pos + 8]
        header = 8
        if size == 1 and pos + 16 <= end:
            size = int.from_bytes(raw[pos + 8 : pos + 16], "big")
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            break
        yield kind, pos + header, pos + size
        pos += size


def parse_mp4(raw):
    """解析 M4A/MP4：mvhd 时长、ilst 标签与 covr 封面。"""
    info = {"title": "", "artist": "", "album": "", "cover": None, "duration": None}
    moov = None
    for kind, start, end in _mp4_children(raw, 0, len(raw)):
        if kind == b"moov":
            moov = (start, end)
            break
    if not moov:
        return info
    for kind, start, end in _mp4_children(raw, moov[0], moov[1]):
        if kind != b"mvhd":
            continue
        version = raw[start] if start < end else 0
        if version == 1 and start + 32 <= end:
            timescale = int.from_bytes(raw[start + 20 : start + 24], "big")
            duration = int.from_bytes(raw[start + 24 : start + 32], "big")
        elif start + 20 <= end:
            timescale = int.from_bytes(raw[start + 12 : start + 16], "big")
            duration = int.from_bytes(raw[start + 16 : start + 20], "big")
        else:
            timescale = duration = 0
        if timescale and duration:
            info["duration"] = duration / timescale
        break

    def walk(node_start, node_end):
        for kind, start, end in _mp4_children(raw, node_start, node_end):
            if kind == b"udta":
                walk(start, end)
            elif kind == b"meta":
                walk(start + 4, end)
            elif kind == b"ilst":
                for item_kind, item_start, item_end in _mp4_children(raw, start, end):
                    for data_kind, data_start, data_end in _mp4_children(
                        raw, item_start, item_end
                    ):
                        if data_kind != b"data" or data_start + 8 > data_end:
                            continue
                        data_type = (
                            int.from_bytes(raw[data_start : data_start + 4], "big")
                            & 0xFFFFFF
                        )
                        payload = raw[data_start + 8 : data_end]
                        if item_kind == b"\xa9nam" and data_type == 1:
                            info["title"] = payload.decode("utf-8", "ignore").strip()
                        elif item_kind == b"\xa9ART" and data_type == 1:
                            info["artist"] = payload.decode("utf-8", "ignore").strip()
                        elif item_kind == b"\xa9alb" and data_type == 1:
                            info["album"] = payload.decode("utf-8", "ignore").strip()
                        elif item_kind == b"covr" and payload:
                            ext = ".png" if data_type == 14 else ".jpg"
                            info["cover"] = (
                                payload,
                                _image_ext_from_magic(payload) or ext,
                            )
                    break

    walk(moov[0], moov[1])
    return info


def parse_wav(raw):
    info = {"duration": None}
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return info
    pos = 12
    byte_rate = 0
    data_size = 0
    while pos + 8 <= len(raw):
        kind = raw[pos : pos + 4]
        size = int.from_bytes(raw[pos + 4 : pos + 8], "little")
        if kind == b"fmt " and pos + 8 + 16 <= len(raw):
            byte_rate = int.from_bytes(raw[pos + 16 : pos + 20], "little")
        elif kind == b"data":
            data_size = size
        pos += 8 + size + (size % 2)
    if byte_rate and data_size:
        info["duration"] = data_size / byte_rate
    return info


def parse_audio_metadata(raw, filename):
    """按扩展名和文件头解析音频元数据。"""
    extension = os.path.splitext(filename or "")[1].lower()
    info = {"title": "", "artist": "", "album": "", "duration": None, "cover": None}
    try:
        if extension == ".mp3" or raw[:3] == b"ID3":
            info.update(parse_id3v2(raw))
            info["duration"] = mp3_duration(raw)
        elif extension == ".flac" or raw[:4] == b"fLaC":
            info.update(parse_flac(raw))
        elif extension in (".m4a", ".mp4", ".aac") or raw[4:8] == b"ftyp":
            info.update(parse_mp4(raw))
        elif extension == ".wav" or raw[:4] == b"RIFF":
            info.update(parse_wav(raw))
    except Exception:
        return info
    return info


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


# ---------- 敏感词过滤 ----------

_SENSITIVE_CACHE = {"key": None, "trie": None, "words": ()}
_ZERO_WIDTH = {ord(ch) for ch in "\u200b\u200c\u200d\ufeff"}


def _normalize_for_match(text):
    """归一化文本并记录每个字符在原串中的位置，便于回填掩码。"""
    chars = []
    indexes = []
    for index, char in enumerate(str(text or "")):
        if ord(char) in _ZERO_WIDTH:
            continue
        normalized = unicodedata.normalize("NFKC", char).casefold()
        for piece in normalized:
            if piece.isspace() or not piece.isalnum():
                # 标点和空白不参与连续匹配，用于挡住"共 产-党"这类插入干扰
                continue
            chars.append(piece)
            indexes.append(index)
    return "".join(chars), indexes


def _build_sensitive_trie(words):
    trie = {}
    for word in words:
        normalized, _ = _normalize_for_match(word)
        if not normalized:
            continue
        node = trie
        for char in normalized:
            node = node.setdefault(char, {})
        node["$"] = word
    return trie


def sensitive_word_rows():
    return query("SELECT id, word, category FROM sensitive_words ORDER BY category, word")


def sensitive_trie():
    rows = sensitive_word_rows()
    key = (len(rows), max((row["id"] for row in rows), default=0))
    if _SENSITIVE_CACHE["key"] != key:
        _SENSITIVE_CACHE["words"] = rows
        _SENSITIVE_CACHE["trie"] = _build_sensitive_trie(row["word"] for row in rows)
        _SENSITIVE_CACHE["key"] = key
    return _SENSITIVE_CACHE["trie"]


def sensitive_hits(text):
    """返回命中区间（原串下标）和命中的词，最长优先。"""
    normalized, indexes = _normalize_for_match(text)
    if not normalized:
        return []
    trie = sensitive_trie()
    hits = []
    for start in range(len(normalized)):
        node = trie
        for cursor in range(start, len(normalized)):
            node = node.get(normalized[cursor])
            if node is None:
                break
            if "$" in node:
                hits.append(
                    {
                        "word": node["$"],
                        "start": indexes[start],
                        "end": indexes[cursor] + 1,
                    }
                )
                break
    return hits


def sensitive_contains(text):
    return bool(sensitive_hits(text))


def mask_sensitive(text):
    hits = sensitive_hits(text)
    if not hits:
        return str(text or ""), 0
    chars = list(str(text or ""))
    for hit in hits:
        for index in range(hit["start"], min(hit["end"], len(chars))):
            chars[index] = "*"
    return "".join(chars), len(hits)


# ---------- 昵称与权限 ----------

def valid_nickname(value, exclude_user_id=None):
    nickname = str(value or "").strip()
    if not NICKNAME_RE.fullmatch(nickname):
        return ""
    if any(char.isalnum() for char in nickname) is False:
        return ""
    if nickname.casefold() in RESERVED_NICKNAMES:
        return ""
    if sensitive_contains(nickname):
        return ""
    row = query_one(
        "SELECT id FROM users WHERE nickname = ? COLLATE NOCASE", (nickname,)
    )
    if row and row["id"] != exclude_user_id:
        return ""
    return nickname


def user_permission_set(user_id):
    if not user_id:
        return set()
    rows = query("SELECT permission FROM user_permissions WHERE user_id = ?", (user_id,))
    return {row["permission"] for row in rows}


def user_has_permission(user_id, permission):
    if permission == ADMIN_PERMISSION:
        return bool(
            query_one(
                "SELECT permission FROM user_permissions WHERE user_id = ? AND permission = ?",
                (user_id, ADMIN_PERMISSION),
            )
        )
    permissions = user_permission_set(user_id)
    if ADMIN_PERMISSION in permissions:
        return True
    return permission in permissions


def required_permission(path, method):
    """把请求映射到权限点；返回 None 表示仍按"仅管理员"处理。"""
    if path == "/api/account/nickname":
        return ""
    if path == "/api/site/messages" or path.startswith("/api/site/messages/"):
        # 留言板：游客只能浏览；登录账号可以发表留言，删除仍仅管理员。
        if method == "POST":
            return ""
        return None
    if path == "/api/moments" or path.startswith("/api/moments/"):
        # 动态：游客和普通账号只能浏览，发布/编辑/置顶/删除仅管理员。
        if method in ("POST", "PATCH", "DELETE"):
            return None
        return ""
    if path == "/api/recommendations" or path.startswith("/api/recommendations/"):
        # 推荐：游客和普通账号只能浏览，管理仅管理员。
        if method in ("POST", "PATCH", "DELETE"):
            return None
        return ""
    if path.startswith("/api/admin"):
        return None
    if path.startswith("/api/map/export"):
        return "map:export"
    if path.startswith("/api/map/categories"):
        return "map:manage_categories"
    if path.startswith("/api/map/import"):
        return "map:import"
    if path.startswith("/api/map"):
        if method in ("POST", "PATCH", "DELETE"):
            return "map:write"
        return ""
    for prefix, module in PERMISSION_ROUTE_MODULES:
        if path.startswith(prefix):
            action = "write" if method in ("POST", "PATCH", "DELETE") else "view"
            return f"{module}:{action}"
    if path in PAGE_PERMISSIONS:
        return PAGE_PERMISSIONS[path]
    for page, permissions in PAGE_PERMISSIONS.items():
        if path.startswith(page + "/"):
            return permissions
    return None


def write_audit(actor, action, detail="", target=None):
    """记录一次敏感操作，actor 为 session_identity() 的结果。"""
    actor = actor or {}
    target = target or {}
    execute(
        """INSERT INTO permission_audit
               (actor_kind, actor_id, actor_name, target_id, target_name, action, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            actor.get("kind") or "system",
            int(actor.get("user_id") or 0),
            actor.get("nickname") or actor.get("username") or "",
            target.get("id"),
            target.get("nickname") or target.get("username") or "",
            action,
            str(detail or "")[:500],
            now_text(),
        ),
    )


# ---------- 站长通知（Webhook 推送） ----------

def app_meta_get(key, default=""):
    row = query_one("SELECT value FROM app_meta WHERE key = ?", (key,))
    return row["value"] if row else default


def app_meta_set(key, value):
    execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, str(value))
    )


def mask_notify_url(url):
    """只显示域名和末尾几位，避免把带密钥的地址回显给前端。"""
    text = str(url or "")
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        host = parsed.netloc or ""
        tail = parsed.path[-4:] if len(parsed.path) > 4 else parsed.path
        return f"{parsed.scheme}://{host}/...{tail}"
    except ValueError:
        return "已配置"


def notify_event_keys():
    return {item["key"] for item in NOTIFY_EVENTS}


def notify_settings():
    raw_events = app_meta_get("notify_events", "")
    events = list(NOTIFY_DEFAULT_EVENTS)
    if raw_events:
        try:
            parsed = json.loads(raw_events)
            if isinstance(parsed, list):
                events = [key for key in parsed if key in notify_event_keys()]
        except json.JSONDecodeError:
            events = list(NOTIFY_DEFAULT_EVENTS)
    channel = app_meta_get("notify_channel", "wecom")
    if channel not in {item["key"] for item in NOTIFY_CHANNELS}:
        channel = "wecom"
    return {
        "enabled": app_meta_get("notify_enabled", "0") == "1",
        "channel": channel,
        "url": app_meta_get("notify_url", ""),
        "events": events,
    }


def notify_log_write(event, title, body, channel, status, detail=""):
    execute(
        """INSERT INTO notify_log (event, title, body, channel, status, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event, title, body[:500], channel, status, str(detail)[:300], now_text()),
    )


def deliver_notification(channel, url, title, body, event):
    """按渠道组装请求并发送，返回 (是否成功, 说明)。"""
    text = f"{title}\n{body}"
    try:
        if channel in ("wecom", "dingtalk"):
            payload = json.dumps(
                {"msgtype": "text", "text": {"content": text}}, ensure_ascii=False
            ).encode("utf-8")
            content_type = "application/json"
        elif channel == "feishu":
            payload = json.dumps(
                {"msg_type": "text", "content": {"text": text}}, ensure_ascii=False
            ).encode("utf-8")
            content_type = "application/json"
        elif channel == "bark":
            payload = json.dumps({"title": title, "body": body}, ensure_ascii=False).encode(
                "utf-8"
            )
            content_type = "application/json"
        elif channel == "serverchan":
            payload = urlencode({"title": title, "desp": body}).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        else:
            payload = json.dumps(
                {
                    "title": title,
                    "body": body,
                    "event": event,
                    "url": "/workbench",
                    "time": now_text(),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            content_type = "application/json"
        request = Request(
            url,
            data=payload,
            headers={
                "Content-Type": content_type,
                "User-Agent": "ErrorJ-Notifier/1.0",
            },
            method="POST",
        )
        with urlopen(request, timeout=8) as response:
            return True, f"HTTP {response.status}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (URLError, ValueError, OSError) as exc:
        return False, str(exc)[:200]


def notify_async(event, title, body):
    """事件触发时异步推送，不阻塞请求。"""
    settings = notify_settings()
    if (
        not settings["enabled"]
        or not settings["url"]
        or event not in settings["events"]
    ):
        return False
    channel, url = settings["channel"], settings["url"]

    def worker():
        ok, detail = deliver_notification(channel, url, title, body, event)
        notify_log_write(event, title, body, channel, "ok" if ok else "fail", detail)

    threading.Thread(target=worker, daemon=True).start()
    return True


def notify_test(channel, url):
    ok, detail = deliver_notification(
        channel,
        url,
        "Error酱测试通知",
        "如果你看到这条消息，说明 Webhook 配置成功。",
        "test",
    )
    notify_log_write("test", "Error酱测试通知", "Webhook 测试", channel, "ok" if ok else "fail", detail)
    return ok, detail


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
            "SELECT id, username, nickname, status FROM users WHERE id = ?",
            (claims["user_id"],),
        )
        if not row or row.get("status") != "approved":
            return None
        is_admin_user = user_has_permission(row["id"], ADMIN_PERMISSION)
        return {
            "kind": "admin" if is_admin_user else "member",
            "user_id": row["id"],
            "username": row["username"],
            "nickname": row.get("nickname") or row["username"],
            "role": "admin" if is_admin_user else "member",
        }

    def session_valid(self):
        return self.session_identity() is not None

    def is_owner(self):
        identity = self.session_identity()
        return bool(identity and identity.get("kind") == "owner")

    def is_admin(self):
        identity = self.session_identity()
        return bool(identity and identity.get("kind") in ("owner", "admin"))

    def can(self, permission):
        """当前请求是否具备某个权限点（管理员直接通过）。"""
        identity = self.session_identity()
        if not identity:
            return False
        if identity.get("kind") in ("owner", "admin"):
            return True
        return user_has_permission(identity.get("user_id"), permission)

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
            if re.fullmatch(r"/api/recommendations/\d+/icon", path):
                return True
            if re.fullmatch(r"/api/site/message-files/\d+", path):
                # 附件接口公开，但会按审核状态在处理器里二次鉴权
                return True
            if path in PUBLIC_PAGES or path.startswith("/games/"):
                return True
            if path in PUBLIC_GET_APIS:
                return True
        if method == "POST" and path in PUBLIC_POST_APIS:
            return True
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
        if identity and identity.get("kind") in ("owner", "admin"):
            return True
        if identity:
            required = required_permission(path, method)
            if required == "":
                return True
            if isinstance(required, tuple):
                if any(
                    user_has_permission(identity.get("user_id"), permission)
                    for permission in required
                ):
                    return True
            elif required and user_has_permission(identity.get("user_id"), required):
                return True
            if path.startswith("/api/") or path.startswith("/site-files/"):
                api_error(self, 403, "当前账号没有访问权限。")
            else:
                self.redirect("/?access=denied")
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
        permissions = []
        pending_users = 0
        pending_attachments = 0
        if identity and identity.get("kind") != "owner":
            permissions = sorted(user_permission_set(identity.get("user_id")))
        if identity and identity.get("kind") in ("owner", "admin"):
            pending_users = query_one(
                "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'"
            )["n"]
            pending_attachments = query_one(
                "SELECT COUNT(*) AS n FROM site_message_files WHERE status = 'pending'"
            )["n"]
        self.send_json(
            200,
            {
                "enabled": enabled,
                "authenticated": identity is not None,
                "role": identity.get("role") if identity else "guest",
                "username": identity.get("username") if identity else "",
                "nickname": identity.get("nickname") if identity else "",
                "owner": bool(identity and identity.get("kind") == "owner"),
                "admin": bool(identity and identity.get("kind") in ("owner", "admin")),
                "permissions": permissions,
                "pending_users": pending_users,
                "pending_attachments": pending_attachments,
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
        nickname = str(payload.get("nickname") or "").strip()
        password = str(payload.get("password") or "")
        if not username:
            api_error(self, 400, "用户名需为 3-32 位，只能包含文字、字母、数字、点、下划线或短横线。")
            return
        if nickname:
            if not NICKNAME_RE.fullmatch(nickname):
                api_error(self, 400, "昵称需为 2-16 位，支持中英文、数字和常见符号。")
                return
            if nickname.casefold() in RESERVED_NICKNAMES:
                api_error(self, 400, "这个昵称不能使用，换一个吧。")
                return
            if sensitive_contains(nickname):
                api_error(self, 400, "昵称包含不允许的词汇，请修改后再注册。")
                return
            if query_one("SELECT id FROM users WHERE nickname = ? COLLATE NOCASE", (nickname,)):
                api_error(self, 409, "昵称已被使用。")
                return
        else:
            nickname = None
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
                (username, nickname, password_hash, status, role, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 'member', ?, ?)
            """,
            (username, nickname, hash_password(password), stamp, stamp),
        )
        write_audit(
            None,
            "register",
            f"新注册申请：{username}" + (f"（{nickname}）" if nickname else ""),
            {"username": username, "nickname": nickname or ""},
        )
        notify_async(
            "register",
            "Error酱：新的注册申请",
            f"{nickname or username}（用户名 {username}）提交了注册申请，请到工作台「账号权限」处理。",
        )
        self.send_json(201, {"ok": True, "status": "pending"})

    def api_account_nickname(self, payload):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请先登录。")
            return
        if identity.get("kind") == "owner":
            api_error(self, 400, "站长账号没有独立昵称。")
            return
        user_id = identity.get("user_id")
        row = query_one(
            "SELECT id, username, nickname, nickname_updated_at FROM users WHERE id = ?",
            (user_id,),
        )
        if not row:
            api_error(self, 404, "账号不存在。")
            return
        nickname = str(payload.get("nickname") or "").strip()
        if not NICKNAME_RE.fullmatch(nickname):
            api_error(self, 400, "昵称需为 2-16 位，支持中英文、数字和常见符号。")
            return
        if nickname.casefold() in RESERVED_NICKNAMES:
            api_error(self, 400, "这个昵称不能使用，换一个吧。")
            return
        if sensitive_contains(nickname):
            api_error(self, 400, "昵称包含不允许的词汇，请修改。")
            return
        if query_one(
            "SELECT id FROM users WHERE nickname = ? COLLATE NOCASE AND id != ?",
            (nickname, user_id),
        ):
            api_error(self, 409, "昵称已被使用。")
            return
        if row.get("nickname") == nickname:
            self.send_json(200, {"ok": True, "nickname": nickname, "changed": False})
            return
        updated_at = row.get("nickname_updated_at")
        if updated_at:
            try:
                last = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last = None
            if last and datetime.now() - last < timedelta(days=NICKNAME_CHANGE_DAYS):
                next_date = (last + timedelta(days=NICKNAME_CHANGE_DAYS)).strftime("%Y-%m-%d")
                api_error(self, 429, f"昵称每 {NICKNAME_CHANGE_DAYS} 天只能修改一次，下次可在 {next_date} 修改。")
                return
        stamp = now_text()
        execute(
            "UPDATE users SET nickname = ?, nickname_updated_at = ?, updated_at = ? WHERE id = ?",
            (nickname, stamp, stamp, user_id),
        )
        write_audit(
            identity,
            "nickname_change",
            f"{row.get('nickname') or row['username']} → {nickname}",
            {"id": user_id, "username": row["username"], "nickname": nickname},
        )
        self.send_json(200, {"ok": True, "nickname": nickname, "changed": True})

    # ---------- 账号与权限管理（管理员） ----------
    def admin_target_user(self, user_id):
        row = query_one(
            """SELECT id, username, nickname, status, role, created_at, updated_at,
                      approved_at, last_login_at, nickname_updated_at, silenced_until
               FROM users WHERE id = ?""",
            (user_id,),
        )
        return row

    def admin_can_touch(self, target):
        """普通管理员不能操作其他管理员，只有站长可以。"""
        if not target:
            return False
        if self.is_owner():
            return True
        if user_has_permission(target["id"], ADMIN_PERMISSION):
            api_error(self, 403, "只有站长可以管理其他管理员。")
            return False
        return True

    def api_admin_users(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看账号列表。")
            return
        status_filter = str((params.get("status") or [""])[0] or "").strip()
        sql = """SELECT id, username, nickname, status, role, created_at, updated_at,
                        approved_at, last_login_at, nickname_updated_at, silenced_until
                 FROM users"""
        values = ()
        if status_filter in ("pending", "approved", "rejected", "disabled"):
            sql += " WHERE status = ?"
            values = (status_filter,)
        sql += """ ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1
                   ELSE 2 END, id DESC"""
        users = query(sql, values)
        permission_rows = query(
            "SELECT user_id, permission FROM user_permissions ORDER BY permission"
        )
        grouped = {}
        for row in permission_rows:
            grouped.setdefault(row["user_id"], []).append(row["permission"])
        for user in users:
            user["permissions"] = sorted(grouped.get(user["id"], []))
            user["is_admin"] = ADMIN_PERMISSION in user["permissions"]
        pending = query_one(
            "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'"
        )["n"]
        self.send_json(
            200,
            {
                "users": users,
                "pending": pending,
                "total": len(users),
                "grantable": list(GRANTABLE_PERMISSIONS),
                "defaults": list(DEFAULT_MEMBER_PERMISSIONS),
            },
        )

    def api_admin_user_status(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以审批账号。")
            return
        user_id = int(path.split("/")[4])
        target = self.admin_target_user(user_id)
        if not target:
            api_error(self, 404, "账号不存在。")
            return
        if not self.admin_can_touch(target):
            return
        action = str(payload.get("action") or "").strip()
        mapping = {
            "approve": ("approved", "同意注册"),
            "reject": ("rejected", "拒绝注册"),
            "disable": ("disabled", "停用账号"),
            "enable": ("approved", "启用账号"),
        }
        if action not in mapping:
            api_error(self, 400, "未知操作。")
            return
        status, label = mapping[action]
        stamp = now_text()
        approved_at = stamp if status == "approved" else target.get("approved_at")
        execute(
            "UPDATE users SET status = ?, approved_at = ?, updated_at = ? WHERE id = ?",
            (status, approved_at, stamp, user_id),
        )
        if status == "approved":
            existing = user_permission_set(user_id)
            if not existing:
                for permission in DEFAULT_MEMBER_PERMISSIONS:
                    execute(
                        """INSERT OR IGNORE INTO user_permissions
                               (user_id, permission, granted_by, granted_at)
                           VALUES (?, ?, ?, ?)""",
                        (
                            user_id,
                            permission,
                            self.session_identity().get("nickname") or "管理员",
                            stamp,
                        ),
                    )
        write_audit(
            self.session_identity(),
            f"user_{action}",
            label + (f"：{payload.get('note')}" if payload.get("note") else ""),
            target,
        )
        self.send_json(200, {"ok": True, "status": status})

    def api_admin_user_permission(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以发放权限。")
            return
        user_id = int(path.split("/")[4])
        target = self.admin_target_user(user_id)
        if not target:
            api_error(self, 404, "账号不存在。")
            return
        permission = str(payload.get("permission") or "").strip()
        if permission not in GRANTABLE_PERMISSIONS:
            api_error(self, 400, "未知权限点。")
            return
        if permission == ADMIN_PERMISSION and not self.is_owner():
            api_error(self, 403, "只有站长可以授予或收回管理员。")
            return
        if not self.is_owner() and target["id"] != self.session_identity().get("user_id"):
            if user_has_permission(target["id"], ADMIN_PERMISSION):
                api_error(self, 403, "只有站长可以管理其他管理员。")
                return
        granted = bool(payload.get("granted"))
        stamp = now_text()
        if granted:
            execute(
                """INSERT OR REPLACE INTO user_permissions
                       (user_id, permission, granted_by, granted_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    user_id,
                    permission,
                    self.session_identity().get("nickname") or "管理员",
                    stamp,
                ),
            )
        else:
            execute(
                "DELETE FROM user_permissions WHERE user_id = ? AND permission = ?",
                (user_id, permission),
            )
        write_audit(
            self.session_identity(),
            "grant" if granted else "revoke",
            f"{PERMISSION_LABELS.get(permission, permission)}（{permission}）",
            target,
        )
        self.send_json(
            200,
            {"ok": True, "permissions": sorted(user_permission_set(user_id))},
        )

    def api_admin_user_nickname(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以修改昵称。")
            return
        user_id = int(path.split("/")[4])
        target = self.admin_target_user(user_id)
        if not target:
            api_error(self, 404, "账号不存在。")
            return
        nickname = str(payload.get("nickname") or "").strip()
        if not NICKNAME_RE.fullmatch(nickname):
            api_error(self, 400, "昵称需为 2-16 位，支持中英文、数字和常见符号。")
            return
        if nickname.casefold() in RESERVED_NICKNAMES:
            api_error(self, 400, "这个昵称不能使用。")
            return
        if sensitive_contains(nickname):
            api_error(self, 400, "昵称包含不允许的词汇。")
            return
        if query_one(
            "SELECT id FROM users WHERE nickname = ? COLLATE NOCASE AND id != ?",
            (nickname, user_id),
        ):
            api_error(self, 409, "昵称已被使用。")
            return
        execute(
            "UPDATE users SET nickname = ?, updated_at = ? WHERE id = ?",
            (nickname, now_text(), user_id),
        )
        write_audit(
            self.session_identity(),
            "set_nickname",
            f"{target.get('nickname') or target['username']} → {nickname}",
            target,
        )
        self.send_json(200, {"ok": True, "nickname": nickname})

    def api_admin_user_password(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以重置密码。")
            return
        user_id = int(path.split("/")[4])
        target = self.admin_target_user(user_id)
        if not target:
            api_error(self, 404, "账号不存在。")
            return
        if not self.admin_can_touch(target):
            return
        password = str(payload.get("password") or "")
        if len(password) < 8 or len(password) > 128:
            api_error(self, 400, "密码长度需为 8-128 位。")
            return
        execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(password), now_text(), user_id),
        )
        write_audit(self.session_identity(), "reset_password", "重置了登录密码", target)
        self.send_json(200, {"ok": True})

    def api_admin_user_delete(self, path):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以删除账号。")
            return
        user_id = int(path.rsplit("/", 1)[1])
        target = self.admin_target_user(user_id)
        if not target:
            api_error(self, 404, "账号不存在。")
            return
        if not self.admin_can_touch(target):
            return
        if target["id"] == (self.session_identity() or {}).get("user_id"):
            api_error(self, 400, "不能删除自己。")
            return
        execute("DELETE FROM users WHERE id = ?", (user_id,))
        write_audit(self.session_identity(), "delete_user", "删除了账号", target)
        self.send_json(200, {"ok": True})

    def api_admin_permissions(self):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看权限表。")
            return
        self.send_json(
            200,
            {
                "groups": PERMISSION_GROUPS,
                "defaults": list(DEFAULT_MEMBER_PERMISSIONS),
            },
        )

    def api_admin_audit(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看审计日志。")
            return
        try:
            limit = int((params.get("limit") or ["100"])[0])
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 500))
        rows = query(
            """SELECT id, actor_kind, actor_name, target_id, target_name,
                      action, detail, created_at
               FROM permission_audit ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
        self.send_json(200, rows)

    def api_admin_sensitive_words(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看敏感词。")
            return
        rows = sensitive_word_rows()
        grouped = {}
        for row in rows:
            grouped[row["category"]] = grouped.get(row["category"], 0) + 1
        self.send_json(
            200,
            {
                "words": rows,
                "categories": list(SENSITIVE_CATEGORIES),
                "counts": grouped,
            },
        )

    def api_admin_sensitive_word_add(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以维护敏感词。")
            return
        word = str(payload.get("word") or "").strip()
        category = str(payload.get("category") or "自定义").strip() or "自定义"
        if not 1 <= len(word) <= 20:
            api_error(self, 400, "敏感词长度需为 1-20 个字符。")
            return
        if category not in SENSITIVE_CATEGORIES:
            category = "自定义"
        if query_one("SELECT id FROM sensitive_words WHERE word = ?", (word,)):
            api_error(self, 409, "这个词已经在词库里了。")
            return
        word_id = execute(
            "INSERT INTO sensitive_words (word, category, created_at) VALUES (?, ?, ?)",
            (word, category, now_text()),
        )
        write_audit(
            self.session_identity(),
            "add_sensitive_word",
            f"{category}：{word}",
            {"id": word_id, "nickname": word},
        )
        self.send_json(200, {"id": word_id})

    def api_admin_sensitive_word_delete(self, path):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以维护敏感词。")
            return
        word_id = int(path.rsplit("/", 1)[1])
        row = query_one("SELECT id, word, category FROM sensitive_words WHERE id = ?", (word_id,))
        if not row:
            api_error(self, 404, "词条不存在。")
            return
        execute("DELETE FROM sensitive_words WHERE id = ?", (word_id,))
        write_audit(
            self.session_identity(),
            "remove_sensitive_word",
            f"{row['category']}：{row['word']}",
            {"id": word_id, "nickname": row["word"]},
        )
        self.send_json(200, {"ok": True})

    def api_admin_sensitive_test(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以测试敏感词。")
            return
        text = str(payload.get("text") or "")
        hits = sensitive_hits(text)
        masked, count = mask_sensitive(text)
        self.send_json(
            200,
            {
                "count": count,
                "words": sorted({hit["word"] for hit in hits}),
                "masked": masked,
            },
        )

    # ---------- 通知设置（管理员） ----------
    def api_admin_notify(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看通知设置。")
            return
        settings = notify_settings()
        logs = query(
            """SELECT id, event, title, body, channel, status, detail, created_at
               FROM notify_log ORDER BY id DESC LIMIT 30"""
        )
        self.send_json(
            200,
            {
                "enabled": settings["enabled"],
                "channel": settings["channel"],
                "url_set": bool(settings["url"]),
                "url_masked": mask_notify_url(settings["url"]),
                "events": settings["events"],
                "channels": NOTIFY_CHANNELS,
                "event_options": NOTIFY_EVENTS,
                "log": logs,
            },
        )

    def api_admin_notify_save(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以修改通知设置。")
            return
        channel = str(payload.get("channel") or "wecom")
        if channel not in {item["key"] for item in NOTIFY_CHANNELS}:
            api_error(self, 400, "未知的通知渠道。")
            return
        raw_events = payload.get("events")
        events = (
            [key for key in raw_events if key in notify_event_keys()]
            if isinstance(raw_events, list)
            else []
        )
        enabled = bool(payload.get("enabled"))
        current = notify_settings()
        url = str(payload.get("url") or "").strip()
        if payload.get("clear_url"):
            url = ""
        elif not url:
            url = current["url"]
        if url and not url.startswith(("http://", "https://")):
            api_error(self, 400, "Webhook 地址必须以 http:// 或 https:// 开头。")
            return
        if enabled and not url:
            api_error(self, 400, "开启通知前请先填写 Webhook 地址。")
            return
        app_meta_set("notify_enabled", "1" if enabled else "0")
        app_meta_set("notify_channel", channel)
        app_meta_set("notify_url", url)
        app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
        write_audit(
            self.session_identity(),
            "notify_settings",
            f"通知{'开启' if enabled else '关闭'}，渠道 {channel}，事件 {','.join(events) or '无'}",
        )
        self.send_json(200, {"ok": True, "url_masked": mask_notify_url(url)})

    def api_admin_notify_test(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以测试通知。")
            return
        current = notify_settings()
        channel = str(payload.get("channel") or current["channel"])
        if channel not in {item["key"] for item in NOTIFY_CHANNELS}:
            api_error(self, 400, "未知的通知渠道。")
            return
        url = str(payload.get("url") or "").strip() or current["url"]
        if not url:
            api_error(self, 400, "请先填写 Webhook 地址。")
            return
        if not url.startswith(("http://", "https://")):
            api_error(self, 400, "Webhook 地址必须以 http:// 或 https:// 开头。")
            return
        ok, detail = notify_test(channel, url)
        self.send_json(200 if ok else 502, {"ok": ok, "detail": detail})

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
        if path == "/prompts":
            self.send_response(302)
            self.send_header("Location", "/workbench?view=prompts")
            self.send_header("Content-Length", "0")
            self.end_headers()
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
            elif path == "/map":
                self.send_file("map.html")
            elif path == "/recommendations":
                self.send_file("recommendations.html")
            elif path == "/music":
                self.send_file("music.html")
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
            elif re.fullmatch(r"/api/site/message-files/\d+", path):
                self.api_site_message_file(path)
            elif path == "/api/moments":
                self.api_moments(query)
            elif path == "/api/recommendations":
                self.api_recommendations(query)
            elif path == "/api/map":
                self.api_map()
            elif path == "/api/admin/users":
                self.api_admin_users(query)
            elif path == "/api/admin/permissions":
                self.api_admin_permissions()
            elif path == "/api/admin/audit":
                self.api_admin_audit(query)
            elif path == "/api/admin/sensitive-words":
                self.api_admin_sensitive_words(query)
            elif path == "/api/admin/review":
                self.api_admin_review(query)
            elif path == "/api/admin/notify":
                self.api_admin_notify(query)
            elif path == "/api/map/export":
                self.api_map_export()
            elif re.fullmatch(r"/api/recommendations/\d+/icon", path):
                self.api_recommendation_icon(path)
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
            elif path == "/api/map/categories":
                self.api_map_category_create(payload)
            elif path == "/api/map/places":
                self.api_map_place_create(payload)
            elif re.fullmatch(r"/api/map/places/\d+/photos", path):
                self.api_map_place_photo_upload(path, payload)
            elif path == "/api/map/import":
                self.api_map_import(payload)
            elif path == "/api/account/nickname":
                self.api_account_nickname(payload)
            elif path == "/api/admin/sensitive-words":
                self.api_admin_sensitive_word_add(payload)
            elif path == "/api/admin/sensitive-words/test":
                self.api_admin_sensitive_test(payload)
            elif path == "/api/admin/notify":
                self.api_admin_notify_save(payload)
            elif path == "/api/admin/notify/test":
                self.api_admin_notify_test(payload)
            elif path == "/api/admin/review/approve-all":
                self.api_admin_review_all(payload)
            elif re.fullmatch(r"/api/admin/review/\d+", path):
                self.api_admin_review_action(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/status", path):
                self.api_admin_user_status(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/permissions", path):
                self.api_admin_user_permission(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/nickname", path):
                self.api_admin_user_nickname(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/password", path):
                self.api_admin_user_password(path, payload)
            elif path == "/api/recommendations":
                self.api_recommendation_create(payload)
            elif path == "/api/recommendations/images":
                self.api_recommendation_image_upload(payload)
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
            elif re.fullmatch(r"/api/map/categories/\d+", path):
                self.api_map_category_item(path)
            elif re.fullmatch(r"/api/map/places/\d+", path):
                self.api_map_place_item(path)
            elif re.fullmatch(r"/api/recommendations/\d+", path):
                self.api_recommendation_item(path)
            elif re.fullmatch(r"/api/workbench/assets/\d+", path):
                self.api_workbench_asset_item(path)
            elif re.fullmatch(r"/api/workbench/repairs/\d+", path):
                self.api_workbench_repair_item(path)
            elif re.fullmatch(r"/api/bookmark-folders/\d+", path):
                self.api_bookmark_folder_item(path)
            elif re.fullmatch(r"/api/prompts/\d+", path):
                self.api_prompt_item(path)
            elif re.fullmatch(r"/api/site/music/\d+", path):
                self.api_site_music_item(path)
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
            elif re.fullmatch(r"/api/map/categories/\d+", path):
                self.api_map_category_item(path)
            elif re.fullmatch(r"/api/map/places/\d+", path):
                self.api_map_place_item(path)
            elif re.fullmatch(r"/api/map/photos/\d+", path):
                self.api_map_photo_delete(path)
            elif re.fullmatch(r"/api/admin/users/\d+", path):
                self.api_admin_user_delete(path)
            elif re.fullmatch(r"/api/admin/sensitive-words/\d+", path):
                self.api_admin_sensitive_word_delete(path)
            elif re.fullmatch(r"/api/recommendations/\d+", path):
                self.api_recommendation_item(path)
            elif re.fullmatch(r"/api/site/photos/\d+", path):
                self.api_site_photo_delete(path)
            elif re.fullmatch(r"/api/site/music/\d+", path):
                self.api_site_music_item(path)
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
        total_size = stat_result.st_size
        range_header = (self.headers.get("Range") or "").strip()
        if range_header.startswith("bytes=") and not download_name:
            spec = range_header[len("bytes=") :].split(",")[0].strip()
            start_text, _, end_text = spec.partition("-")
            try:
                if start_text:
                    start = int(start_text)
                    end = int(end_text) if end_text else total_size - 1
                else:
                    start = max(0, total_size - int(end_text or 0))
                    end = total_size - 1
            except ValueError:
                start, end = 0, total_size - 1
            start = max(0, min(start, max(0, total_size - 1)))
            end = max(start, min(end, total_size - 1))
            length = max(0, end - start + 1)
            try:
                with full.open("rb") as handle:
                    handle.seek(start)
                    body = handle.read(length)
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header(
                    "Content-Range", f"bytes {start}-{end}/{total_size}"
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache_control)
                self.send_header("ETag", etag)
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except OSError:
                api_error(self, 404, "文件不存在。")
            return
        body = full.read_bytes()
        encoding = self.maybe_gzip(body, content_type)
        if encoding:
            body = encoding[1]
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Accept-Ranges", "bytes")
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
            f"""SELECT id, message_id, file_name, file_path, file_size, mime_type,
                       status, uploaded_by
                FROM site_message_files
                WHERE message_id IN ({placeholders})
                ORDER BY id""",
            tuple(message_ids),
        )
        identity = self.session_identity()
        viewer_id = None
        if identity:
            viewer_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        is_admin = self.is_admin()
        grouped = {}
        for row in rows:
            extension = os.path.splitext(row.get("file_name") or "")[1].lower()
            status = row.get("status") or "approved"
            approved = status == "approved"
            owned = (
                viewer_id is not None
                and row.get("uploaded_by") is not None
                and row["uploaded_by"] == viewer_id
            )
            visible = approved or is_admin or owned
            entry = {
                "id": row["id"],
                "status": status,
                "is_image": extension in MESSAGE_IMAGE_EXTENSIONS,
                "visible": visible,
            }
            if visible:
                entry.update(
                    {
                        "file_name": row["file_name"],
                        "file_size": row["file_size"],
                        "mime_type": row["mime_type"],
                        "url": f"/api/site/message-files/{row['id']}",
                        "pending": not approved,
                    }
                )
            grouped.setdefault(row["message_id"], []).append(entry)
        return grouped

    def api_site_messages(self, params):
        rows = query(
            """SELECT id, nickname, content, parent_id, created_at
               FROM site_messages
               ORDER BY COALESCE(parent_id, id) DESC, id ASC"""
        )
        can_delete = self.is_admin()
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
            if sensitive_contains(name):
                return None, f"附件名包含不允许的词汇：{name}"
            try:
                raw = base64.b64decode(str(item.get("data_base64") or ""), validate=True)
            except Exception:
                return None, f"附件数据无效：{name}"
            if not raw:
                return None, f"附件内容为空：{name}"
            if extension in MESSAGE_IMAGE_EXTENSIONS:
                detected = _image_ext_from_magic(raw)
                if not detected or detected not in (
                    {extension, ".jpg"} if extension in (".jpg", ".jpeg") else {extension}
                ):
                    return None, f"图片内容与扩展名不符：{name}"
            elif extension == ".pdf":
                if not raw.startswith(b"%PDF-"):
                    return None, f"不是有效的 PDF 文件：{name}"
            else:
                if b"\x00" in raw[:4096]:
                    return None, f"文本附件包含二进制内容：{name}"
                try:
                    raw[:4096].decode("utf-8")
                except UnicodeDecodeError:
                    return None, f"文本附件不是 UTF-8 编码：{name}"
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
        if sensitive_contains(nickname):
            api_error(self, 400, "昵称包含不允许的词汇，请修改后再留言。")
            return
        if content and sensitive_contains(content):
            api_error(self, 400, "留言内容包含不允许的词汇，请修改后再发。")
            return
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
        auto_approve = self.is_admin() or self.can("messages:attach_auto")
        identity = self.session_identity()
        uploader_id = None
        if identity:
            uploader_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")

        def write(conn):
            cursor = conn.execute(
                "INSERT INTO site_messages (nickname, content, parent_id, created_at) VALUES (?, ?, ?, ?)",
                (nickname, content, parent_id or None, created_at),
            )
            message_id = cursor.lastrowid
            for name, relative, size in saved:
                conn.execute(
                    """INSERT INTO site_message_files
                       (message_id, file_name, file_path, file_size, mime_type,
                        status, uploaded_by, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message_id,
                        name,
                        relative,
                        size,
                        mimetypes.guess_type(name)[0],
                        "approved" if auto_approve else "pending",
                        uploader_id,
                        created_at,
                    ),
                )
            return message_id

        try:
            row_id = transaction(write)
        except Exception:
            for _name, relative, _size in saved:
                remove_data_file(relative)
            raise
        if saved and not auto_approve:
            notify_async(
                "attachment",
                "Error酱：有新的待审附件",
                f"{nickname} 的留言附件等待审核，请到工作台「内容审核」处理。",
            )
        notify_async(
            "message",
            "Error酱：新的留言",
            f"{nickname}：{(content[:60] if content else '（仅附件）')}",
        )
        self.send_json(
            200,
            {
                "id": row_id,
                "files": len(saved),
                "pending_review": bool(saved) and not auto_approve,
            },
        )

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
        can_manage = self.is_admin()
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

    def recommendation_rows(self, params=None):
        params = params or {}
        conditions = []
        values = []
        kind = str((params.get("kind") or [""])[0] or "").strip().lower()
        keyword = str((params.get("q") or [""])[0] or "").strip()
        if kind in RECOMMEND_KINDS:
            conditions.append("r.kind = ?")
            values.append(kind)
        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                "(r.title LIKE ? OR r.subtitle LIKE ? OR r.description LIKE ? "
                "OR r.category LIKE ? OR r.tags LIKE ? "
                "OR b.title LIKE ? OR b.description LIKE ?)"
            )
            values.extend([like, like, like, like, like, like, like])
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = query(
            f"""SELECT r.id, r.kind, r.bookmark_id, r.title, r.subtitle, r.url,
                       r.download_url, r.cover_path, r.icon_url, r.description,
                       r.category, r.tags, r.rating, r.release_year, r.status,
                       r.pinned, r.sort_order, r.created_at, r.updated_at,
                       b.title AS bookmark_title, b.url AS bookmark_url,
                       b.description AS bookmark_description,
                       b.favicon_updated_at AS bookmark_favicon_updated_at
                FROM recommendations r
                LEFT JOIN bookmarks b ON b.id = r.bookmark_id
                {where}
                ORDER BY r.pinned DESC, r.sort_order, r.id DESC""",
            tuple(values),
        )
        for row in rows:
            if row.get("bookmark_id") and row.get("bookmark_title"):
                row["title"] = row["bookmark_title"]
                row["url"] = row["bookmark_url"]
                if not row.get("description"):
                    row["description"] = row.get("bookmark_description")
                row["icon_url"] = (
                    f"/api/recommendations/{row['id']}/icon"
                    f"?v={quote(str(row.get('bookmark_favicon_updated_at') or ''))}"
                )
            row.pop("bookmark_title", None)
            row.pop("bookmark_url", None)
            row.pop("bookmark_description", None)
            row.pop("bookmark_favicon_updated_at", None)
            row["pinned"] = bool(row["pinned"])
        return rows

    def api_recommendations(self, params):
        self.send_json(
            200,
            {
                "items": self.recommendation_rows(params),
                "can_manage": self.is_admin(),
            },
        )

    @staticmethod
    def recommendation_url(value, field_name, required=False):
        text = str(value or "").strip()[:1000]
        if not text:
            if required:
                raise ValueError(f"{field_name}不能为空。")
            return None
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{field_name}必须是 http 或 https 地址。")
        return text

    def recommendation_payload(self, payload, current=None):
        current = current or {}
        kind = str(payload.get("kind", current.get("kind", "site")) or "site").strip().lower()
        if kind not in RECOMMEND_KINDS:
            raise ValueError("推荐类型不正确。")
        bookmark_id_value = payload.get("bookmark_id", current.get("bookmark_id"))
        bookmark = None
        if bookmark_id_value not in (None, "", 0, "0"):
            try:
                bookmark_id = int(bookmark_id_value)
            except (TypeError, ValueError):
                raise ValueError("网页收藏关联不正确。")
            if kind != "site":
                raise ValueError("只有网站类型可以关联网页收藏。")
            bookmark = query_one(
                "SELECT id, title, url, description, favicon_updated_at FROM bookmarks WHERE id = ?",
                (bookmark_id,),
            )
            if not bookmark:
                raise ValueError("关联的网页收藏不存在。")
        title_source = payload.get("title", current.get("title", ""))
        if bookmark and not str(title_source or "").strip():
            title_source = bookmark["title"]
        title = str(title_source or "").strip()[:160]
        if not title:
            raise ValueError("推荐标题不能为空。")
        subtitle = str(payload.get("subtitle", current.get("subtitle", "")) or "").strip()[:200]
        url_source = payload.get("url", current.get("url", ""))
        if bookmark and not str(url_source or "").strip():
            url_source = bookmark["url"]
        url = self.recommendation_url(
            url_source,
            "详情或访问地址",
            required=kind in {"site", "tool"},
        )
        download_url = self.recommendation_url(
            payload.get("download_url", current.get("download_url", "")),
            "下载地址",
        )
        cover_path = str(payload.get("cover_path", current.get("cover_path", "")) or "").strip()
        if cover_path and not re.fullmatch(r"recommend_images/[A-Za-z0-9._-]+", cover_path):
            raise ValueError("封面路径不正确。")
        icon_url = self.recommendation_url(
            payload.get("icon_url", current.get("icon_url", "")),
            "图标地址",
        )
        description_source = payload.get("description", current.get("description", ""))
        if bookmark and not str(description_source or "").strip():
            description_source = bookmark.get("description") or ""
        description = str(description_source or "").strip()[:2000]
        category = str(payload.get("category", current.get("category", "")) or "").strip()[:40]
        tags = str(payload.get("tags", current.get("tags", "")) or "")
        tags = tags.replace("，", ",").replace("、", ",").strip()[:300]
        rating_value = payload.get("rating", current.get("rating"))
        rating = None
        if rating_value is not None and str(rating_value).strip():
            try:
                rating = float(rating_value)
            except (TypeError, ValueError):
                raise ValueError("评分必须是数字。")
            if rating < 0 or rating > 10:
                raise ValueError("评分需要在 0 到 10 之间。")
        year_value = payload.get("release_year", current.get("release_year"))
        release_year = None
        if year_value is not None and str(year_value).strip():
            try:
                release_year = int(year_value)
            except (TypeError, ValueError):
                raise ValueError("年份必须是整数。")
            if release_year < 1800 or release_year > 2200:
                raise ValueError("年份需要在 1800 到 2200 之间。")
        status = str(payload.get("status", current.get("status", "")) or "").strip()[:20]
        pinned = 1 if payload.get("pinned", current.get("pinned", False)) else 0
        sort_order_value = payload.get("sort_order", current.get("sort_order"))
        if sort_order_value in (None, ""):
            sort_order = None
        else:
            try:
                sort_order = int(sort_order_value)
            except (TypeError, ValueError):
                raise ValueError("排序值必须是整数。")
        return (
            kind,
            bookmark["id"] if bookmark else None,
            title,
            subtitle or None,
            url,
            download_url,
            cover_path or None,
            icon_url,
            description or None,
            category or None,
            tags or None,
            rating,
            release_year,
            status or None,
            pinned,
            sort_order,
        )

    def api_recommendation_create(self, payload):
        try:
            values = list(self.recommendation_payload(payload))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if values[-1] is None:
            row = query_one(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM recommendations"
            )
            values[-1] = int(row["value"] if row else 0)
        stamp = now_text()
        recommendation_id = execute(
            """INSERT INTO recommendations
               (kind, bookmark_id, title, subtitle, url, download_url, cover_path,
                icon_url, description, category, tags, rating, release_year,
                status, pinned, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(values) + (stamp, stamp),
        )
        self.send_json(200, {"id": recommendation_id})

    def remove_recommendation_cover_if_unused(self, relative):
        if not relative:
            return
        if query_one("SELECT id FROM recommendations WHERE cover_path = ? LIMIT 1", (relative,)):
            return
        remove_data_file(relative)

    def api_recommendation_item(self, path):
        recommendation_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM recommendations WHERE id = ?", (recommendation_id,))
        if not current:
            api_error(self, 404, "推荐内容不存在。")
            return
        if self.command == "DELETE":
            execute("DELETE FROM recommendations WHERE id = ?", (recommendation_id,))
            self.remove_recommendation_cover_if_unused(current.get("cover_path"))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            values = list(self.recommendation_payload(payload, current))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if values[-1] is None:
            values[-1] = int(current.get("sort_order") or 0)
        execute(
            """UPDATE recommendations
               SET kind = ?, bookmark_id = ?, title = ?, subtitle = ?, url = ?,
                   download_url = ?, cover_path = ?, icon_url = ?, description = ?,
                   category = ?, tags = ?, rating = ?, release_year = ?, status = ?,
                   pinned = ?, sort_order = ?, updated_at = ?
               WHERE id = ?""",
            tuple(values) + (now_text(), recommendation_id),
        )
        old_cover = current.get("cover_path")
        if old_cover and old_cover != values[6]:
            self.remove_recommendation_cover_if_unused(old_cover)
        self.send_json(200, {"id": recommendation_id})

    def api_recommendation_image_upload(self, payload):
        original_name = os.path.basename(str(payload.get("file_name") or "cover.png"))[:160]
        data_base64 = payload.get("data_base64") or ""
        if not data_base64:
            api_error(self, 400, "没有图片数据。")
            return
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception:
            api_error(self, 400, "图片数据不是有效的 base64。")
            return
        if not raw:
            api_error(self, 400, "图片内容为空。")
            return
        if len(raw) > RECOMMEND_IMAGE_MAX_BYTES:
            api_error(
                self,
                400,
                f"封面图片不能超过 {RECOMMEND_IMAGE_MAX_BYTES // (1024 * 1024)}MB。",
            )
            return
        mime_type = detect_image_type(raw)
        if not mime_type:
            api_error(self, 400, "只支持 PNG / JPEG / WebP / GIF / BMP 图片。")
            return
        base_name = os.path.splitext(original_name)[0] or "cover"
        stored_name = f"{base_name[:80]}{NOTE_IMAGE_EXTENSIONS[mime_type]}"
        try:
            relative = self.save_data_file(
                raw,
                stored_name,
                "recommend_images",
                RECOMMEND_IMAGE_MAX_BYTES,
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(
            200,
            {
                "path": relative,
                "url": f"/site-files/{relative}",
                "mime_type": mime_type,
                "size_bytes": len(raw),
            },
        )

    def api_recommendation_icon(self, path):
        recommendation_id = int(path.split("/")[3])
        row = query_one(
            "SELECT bookmark_id FROM recommendations WHERE id = ?",
            (recommendation_id,),
        )
        if not row or not row.get("bookmark_id"):
            self.send_error(404)
            return
        relative = refresh_bookmark_favicon(row["bookmark_id"])
        if not relative:
            self.send_error(404)
            return
        try:
            full_path = (DATA_DIR / relative).resolve()
            full_path.relative_to(DATA_DIR.resolve())
            body = full_path.read_bytes()
        except (ValueError, OSError):
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(full_path.name)[0] or "image/x-icon"
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

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
        for row in rows:
            if row.get("source_type") == "file":
                row["url"] = "/site-files/" + (row.get("source_id") or "")
            else:
                row["url"] = row.get("source_id") or ""
            row["cover_url"] = (
                "/site-files/" + row["cover_path"] if row.get("cover_path") else ""
            )
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
        album = str(payload.get("album") or "").strip()[:80]
        file_name = os.path.basename(str(payload.get("file_name") or "music.mp3"))
        extension = os.path.splitext(file_name)[1].lower()
        if extension not in MUSIC_EXTENSIONS:
            api_error(self, 400, "支持 mp3、wav、flac、m4a、aac、ogg、opus 格式。")
            return
        try:
            raw = base64.b64decode(str(payload.get("data_base64") or ""), validate=True)
        except Exception:
            api_error(self, 400, "音频数据不是有效的 base64。")
            return
        if not raw:
            api_error(self, 400, "音频内容为空。")
            return
        if len(raw) > MUSIC_MAX_BYTES:
            limit_mb = MUSIC_MAX_BYTES // (1024 * 1024)
            api_error(self, 400, f"单个音频文件不能超过 {limit_mb}MB。")
            return
        metadata = parse_audio_metadata(raw, file_name)
        try:
            relative = self.save_data_file(
                raw, file_name, "site_music_files", max_bytes=MUSIC_MAX_BYTES
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        cover_path = None
        cover = metadata.get("cover")
        if cover:
            try:
                cover_path = self.save_data_file(
                    cover[0],
                    "cover" + (cover[1] or ".jpg"),
                    "music_covers",
                    max_bytes=MUSIC_COVER_MAX_BYTES,
                )
            except ValueError:
                cover_path = None
        if not title:
            title = metadata.get("title") or os.path.splitext(file_name)[0]
        if not artist:
            artist = metadata.get("artist") or ""
        if not album:
            album = metadata.get("album") or ""
        sort_order = query_one(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM site_music"
        )["value"]
        row_id = execute(
            """INSERT INTO site_music
                   (title, artist, album, source_type, source_id, cover_path,
                    duration, file_size, mime_type, sort_order, created_at)
               VALUES (?, ?, ?, 'file', ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                artist or None,
                album or None,
                relative,
                cover_path,
                metadata.get("duration"),
                len(raw),
                mimetypes.guess_type(file_name)[0] or "audio/mpeg",
                sort_order,
                now_text(),
            ),
        )
        self.send_json(
            200,
            {
                "id": row_id,
                "source_id": relative,
                "cover_path": cover_path,
                "title": title,
                "artist": artist,
                "album": album,
                "duration": metadata.get("duration"),
            },
        )

    def api_site_music_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM site_music WHERE id = ?", (item_id,))
        if not current:
            api_error(self, 404, "歌曲不存在。")
            return
        if self.command == "DELETE":
            if current.get("source_type") == "file" and current.get("source_id"):
                remove_data_file(current["source_id"])
            if current.get("cover_path"):
                remove_data_file(current["cover_path"])
            execute("DELETE FROM site_music WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        title = str(payload.get("title", current.get("title", "")) or "").strip()[:80]
        if not title:
            api_error(self, 400, "歌名不能为空。")
            return
        artist = str(payload.get("artist", current.get("artist", "")) or "").strip()[:80]
        album = str(payload.get("album", current.get("album", "")) or "").strip()[:80]
        try:
            sort_order = int(
                payload.get("sort_order", current.get("sort_order", 0)) or 0
            )
        except (TypeError, ValueError):
            api_error(self, 400, "排序值必须是整数。")
            return
        execute(
            "UPDATE site_music SET title = ?, artist = ?, album = ?, sort_order = ? WHERE id = ?",
            (title, artist or None, album or None, sort_order, item_id),
        )
        self.send_json(200, {"id": item_id})

    def api_site_links(self, params):
        rows = query("SELECT * FROM site_links ORDER BY category, sort_order, id")
        self.send_json(200, rows)

    # ---------- 地图 ----------
    def map_category_rows(self):
        return query(
            """SELECT c.id, c.parent_id, c.name, c.glyph, c.color, c.note, c.sort_order,
                      c.created_at, COUNT(p.id) AS place_count
               FROM map_categories c
               LEFT JOIN map_places p ON p.category_id = c.id
               GROUP BY c.id
               ORDER BY COALESCE(c.parent_id, c.id), c.parent_id IS NOT NULL, c.sort_order, c.id"""
        )

    def map_place_rows(self):
        return query(
            """SELECT p.id, p.category_id, p.name, p.subtitle, p.address, p.note,
                      p.signature, p.tags, p.lat, p.lng, p.status, p.rating,
                      p.created_by, p.created_at, p.updated_at,
                      c.name AS category_name, c.glyph AS category_glyph,
                      c.color AS category_color,
                      CASE WHEN p.created_by = 0 THEN '管理员'
                           ELSE COALESCE(u.username, '未知用户') END AS created_by_name
               FROM map_places p
               LEFT JOIN map_categories c ON c.id = p.category_id
               LEFT JOIN users u ON u.id = p.created_by
               ORDER BY p.id"""
        )

    def map_photos_map(self, place_ids):
        if not place_ids:
            return {}
        placeholders = ",".join("?" for _ in place_ids)
        rows = query(
            f"""SELECT id, place_id, file_path, original_name, mime_type,
                       size_bytes, created_by, created_at
                FROM map_place_photos
                WHERE place_id IN ({placeholders})
                ORDER BY id""",
            tuple(place_ids),
        )
        grouped = {}
        for row in rows:
            row["url"] = "/site-files/" + row["file_path"]
            grouped.setdefault(row["place_id"], []).append(row)
        return grouped

    def map_identity_user_id(self):
        identity = self.session_identity()
        if not identity:
            return None
        if identity.get("kind") == "owner":
            return 0
        return identity.get("user_id")

    def map_admin(self):
        identity = self.session_identity()
        return bool(identity and identity.get("kind") == "owner")

    def map_place_can_edit(self, row):
        if not row:
            return False
        if self.is_admin():
            return True
        user_id = self.map_identity_user_id()
        if user_id is None:
            return False
        if user_has_permission(user_id, "map:write_all"):
            return True
        return row.get("created_by") == user_id

    def api_map(self):
        identity = self.session_identity()
        is_admin = self.is_admin()
        user_id = self.map_identity_user_id()
        places = self.map_place_rows()
        photos = self.map_photos_map([row["id"] for row in places])
        for row in places:
            row["photos"] = photos.get(row["id"], [])
            row["can_edit"] = bool(
                identity
                and (
                    is_admin
                    or (user_id is not None and row.get("created_by") == user_id)
                )
            )
        self.send_json(
            200,
            {
                "categories": self.map_category_rows(),
                "places": places,
                "can_manage": is_admin,
                "can_add": self.can("map:write"),
                "can_import": self.can("map:import"),
                "can_export": self.can("map:export"),
                "can_manage_categories": self.can("map:manage_categories"),
                "signed_in": identity is not None,
                "map_public": MAP_PUBLIC,
            },
        )

    def map_category_payload(self, payload, current=None, category_id=None):
        current = current or {}
        name = str(payload.get("name", current.get("name", "")) or "").strip()[:60]
        if not name:
            raise ValueError("分类名称不能为空。")
        glyph = str(payload.get("glyph", current.get("glyph", "·")) or "·").strip()[:2] or "·"
        color = str(payload.get("color", current.get("color", "#7b68ee")) or "#7b68ee").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("颜色需要是 #RRGGBB 格式。")
        note = str(payload.get("note", current.get("note", "")) or "").strip()[:500]
        try:
            sort_order = int(payload.get("sort_order", current.get("sort_order", 0)) or 0)
        except (TypeError, ValueError):
            raise ValueError("排序值必须是整数。")
        raw_parent = payload.get("parent_id", current.get("parent_id"))
        parent_id = None
        if raw_parent not in (None, "", 0, "0"):
            try:
                parent_id = int(raw_parent)
            except (TypeError, ValueError):
                raise ValueError("上级分类无效。")
            if category_id is not None and parent_id == category_id:
                raise ValueError("分类不能把自己设为上级。")
            parent = query_one(
                "SELECT id, parent_id FROM map_categories WHERE id = ?", (parent_id,)
            )
            if not parent:
                raise ValueError("上级分类不存在。")
            if parent.get("parent_id"):
                raise ValueError("最多支持两级分类。")
            if category_id is not None:
                children = query_one(
                    "SELECT COUNT(*) AS n FROM map_categories WHERE parent_id = ?",
                    (category_id,),
                )["n"]
                if children:
                    raise ValueError("该分类下已有子分类，不能再设为子分类。")
        return name, glyph, color.lower(), (note or None), sort_order, parent_id

    def api_map_category_create(self, payload):
        try:
            name, glyph, color, note, _sort_order, parent_id = self.map_category_payload(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if parent_id:
            sort_order = query_one(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM map_categories WHERE parent_id = ?",
                (parent_id,),
            )["value"]
        else:
            sort_order = query_one(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM map_categories WHERE parent_id IS NULL"
            )["value"]
        row_id = execute(
            """INSERT INTO map_categories
                   (parent_id, name, glyph, color, note, sort_order, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (parent_id, name, glyph, color, note, sort_order, now_text()),
        )
        self.send_json(201, {"id": row_id})

    def api_map_category_item(self, path):
        category_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM map_categories WHERE id = ?", (category_id,))
        if not current:
            api_error(self, 404, "分类不存在。")
            return
        if self.command == "DELETE":
            execute("DELETE FROM map_categories WHERE id = ?", (category_id,))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            name, glyph, color, note, sort_order, parent_id = self.map_category_payload(
                payload, current, category_id
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        execute(
            """UPDATE map_categories
               SET parent_id = ?, name = ?, glyph = ?, color = ?, note = ?, sort_order = ?
               WHERE id = ?""",
            (parent_id, name, glyph, color, note, sort_order, category_id),
        )
        self.send_json(200, {"id": category_id})

    def map_place_payload(self, payload, current=None):
        current = current or {}
        name = str(payload.get("name", current.get("name", "")) or "").strip()[:120]
        if not name:
            raise ValueError("地点名称不能为空。")
        try:
            lat = float(payload.get("lat", current.get("lat")))
            lng = float(payload.get("lng", current.get("lng")))
        except (TypeError, ValueError):
            raise ValueError("坐标无效。")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("坐标超出有效范围。")
        raw_category = payload.get("category_id", current.get("category_id"))
        category_id = None
        if raw_category not in (None, "", 0, "0"):
            try:
                category_id = int(raw_category)
            except (TypeError, ValueError):
                raise ValueError("分类无效。")
            if not query_one("SELECT id FROM map_categories WHERE id = ?", (category_id,)):
                raise ValueError("分类不存在。")
        subtitle = str(payload.get("subtitle", current.get("subtitle", "")) or "").strip()[:120]
        address = str(payload.get("address", current.get("address", "")) or "").strip()[:300]
        note = str(payload.get("note", current.get("note", "")) or "").strip()[:2000]
        signature = str(payload.get("signature", current.get("signature", "")) or "").strip()[:300]
        tags = str(payload.get("tags", current.get("tags", "")) or "")
        tags = tags.replace("，", ",").replace("、", ",").strip()[:200]
        status = str(payload.get("status", current.get("status", "")) or "").strip().lower()
        if status not in ("", "wish", "visited"):
            raise ValueError("打卡状态不正确。")
        try:
            rating = int(payload.get("rating", current.get("rating", 0)) or 0)
        except (TypeError, ValueError):
            raise ValueError("推荐度必须是整数。")
        if not 0 <= rating <= 5:
            raise ValueError("推荐度范围是 0 到 5。")
        return (
            category_id,
            name,
            subtitle or None,
            address or None,
            note or None,
            signature or None,
            tags or None,
            lat,
            lng,
            status or None,
            rating,
        )

    def api_map_place_create(self, payload):
        user_id = self.map_identity_user_id()
        if user_id is None:
            api_error(self, 401, "请先登录。")
            return
        try:
            values = self.map_place_payload(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        stamp = now_text()
        row_id = execute(
            """INSERT INTO map_places
                   (category_id, name, subtitle, address, note, signature,
                    tags, lat, lng, status, rating, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (*values, user_id, stamp, stamp),
        )
        self.send_json(201, {"id": row_id})

    def api_map_place_item(self, path):
        place_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM map_places WHERE id = ?", (place_id,))
        if not current:
            api_error(self, 404, "标记不存在。")
            return
        if not self.map_place_can_edit(current):
            api_error(self, 403, "只能修改自己添加的标记。")
            return
        if self.command == "DELETE":
            photos = query(
                "SELECT file_path FROM map_place_photos WHERE place_id = ?", (place_id,)
            )
            execute("DELETE FROM map_places WHERE id = ?", (place_id,))
            for photo in photos:
                remove_data_file(photo.get("file_path"))
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            values = self.map_place_payload(payload, current)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        execute(
            """UPDATE map_places
               SET category_id = ?, name = ?, subtitle = ?, address = ?, note = ?,
                   signature = ?, tags = ?, lat = ?, lng = ?, status = ?, rating = ?,
                   updated_at = ?
               WHERE id = ?""",
            (*values, now_text(), place_id),
        )
        self.send_json(200, {"id": place_id})

    def api_map_place_photo_upload(self, path, payload):
        place_id = int(path.split("/")[4])
        place = query_one("SELECT * FROM map_places WHERE id = ?", (place_id,))
        if not place:
            api_error(self, 404, "标记不存在。")
            return
        if not self.map_place_can_edit(place):
            api_error(self, 403, "只能给自己添加的标记上传照片。")
            return
        count = query_one(
            "SELECT COUNT(*) AS n FROM map_place_photos WHERE place_id = ?", (place_id,)
        )["n"]
        if count >= MAP_PHOTO_MAX_COUNT:
            api_error(self, 400, f"每个标记最多 {MAP_PHOTO_MAX_COUNT} 张照片。")
            return
        name = os.path.basename(str(payload.get("name") or "photo.jpg")).strip() or "photo.jpg"
        extension = os.path.splitext(name)[1].lower()
        if extension not in MESSAGE_IMAGE_EXTENSIONS:
            api_error(self, 400, "只支持 png、jpg、jpeg、gif、webp、bmp 图片。")
            return
        try:
            raw = base64.b64decode(str(payload.get("data_base64") or ""), validate=True)
        except Exception:
            api_error(self, 400, "图片数据无效。")
            return
        if not raw:
            api_error(self, 400, "图片内容为空。")
            return
        if len(raw) > MAP_PHOTO_MAX_BYTES:
            limit_mb = MAP_PHOTO_MAX_BYTES // (1024 * 1024)
            api_error(self, 400, f"单张照片不能超过 {limit_mb}MB。")
            return
        try:
            relative = self.save_data_file(raw, name, "map_images", max_bytes=MAP_PHOTO_MAX_BYTES)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        row_id = execute(
            """INSERT INTO map_place_photos
                   (place_id, file_path, original_name, mime_type, size_bytes,
                    created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                place_id,
                relative,
                name,
                mimetypes.guess_type(name)[0] or "image/*",
                len(raw),
                self.map_identity_user_id() or 0,
                now_text(),
            ),
        )
        self.send_json(200, {"id": row_id, "url": "/site-files/" + relative})

    def api_map_photo_delete(self, path):
        photo_id = int(path.rsplit("/", 1)[1])
        photo = query_one("SELECT * FROM map_place_photos WHERE id = ?", (photo_id,))
        if not photo:
            api_error(self, 404, "照片不存在。")
            return
        place = query_one("SELECT * FROM map_places WHERE id = ?", (photo["place_id"],))
        if not self.map_place_can_edit(place):
            api_error(self, 403, "只能删除自己标记下的照片。")
            return
        execute("DELETE FROM map_place_photos WHERE id = ?", (photo_id,))
        remove_data_file(photo.get("file_path"))
        self.send_json(200, {"ok": True})

    def api_map_export(self):
        if not self.can("map:export"):
            api_error(self, 403, "只有管理员可以导出地图数据。")
            return
        categories = {row["id"]: row for row in self.map_category_rows()}

        def category_path(category_id):
            category = categories.get(category_id)
            if not category:
                return ""
            if category.get("parent_id"):
                parent = categories.get(category["parent_id"])
                if parent:
                    return f"{parent['name']} / {category['name']}"
            return category["name"]

        features = []
        for row in self.map_place_rows():
            path = category_path(row.get("category_id"))
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [row["lng"], row["lat"]]},
                    "properties": {
                        "id": row["id"],
                        "name": row["name"],
                        "subtitle": row.get("subtitle") or "",
                        "address": row.get("address") or "",
                        "note": row.get("note") or "",
                        "signature": row.get("signature") or "",
                        "tags": row.get("tags") or "",
                        "status": row.get("status") or "",
                        "rating": row.get("rating") or 0,
                        "added_by": row.get("created_by_name") or "",
                        "category": row.get("category_name") or "",
                        "category_path": path,
                        "category_color": row.get("category_color") or "",
                        "category_glyph": row.get("category_glyph") or "",
                    },
                }
            )
        body = json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/geo+json; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            "attachment; filename*=UTF-8''"
            + quote(f"errorjiang-map-{today_text()}.geojson"),
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def api_map_import(self, payload):
        user_id = self.map_identity_user_id()
        if user_id is None:
            api_error(self, 401, "请先登录。")
            return
        is_admin = self.is_admin()
        if isinstance(payload, dict):
            features = payload.get("features")
        else:
            features = payload
        if not isinstance(features, list) or not features:
            api_error(self, 400, "没有找到可导入的 GeoJSON 要素。")
            return
        if len(features) > 2000:
            api_error(self, 400, "单次最多导入 2000 个标记。")
            return
        stamp = now_text()
        target_category_id = None
        raw_target = payload.get("category_id") if isinstance(payload, dict) else None
        if raw_target not in (None, "", 0, "0"):
            try:
                target_category_id = int(raw_target)
            except (TypeError, ValueError):
                api_error(self, 400, "目标分类无效。")
                return
            if not query_one("SELECT id FROM map_categories WHERE id = ?", (target_category_id,)):
                api_error(self, 400, "目标分类不存在。")
                return
        next_sort = query_one(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM map_categories WHERE parent_id IS NULL"
        )["value"]
        imported = 0
        skipped = 0
        for feature in features:
            if not isinstance(feature, dict):
                skipped += 1
                continue
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
            if (
                not isinstance(coordinates, (list, tuple))
                or len(coordinates) < 2
                or not isinstance(geometry, dict)
                or geometry.get("type") != "Point"
            ):
                skipped += 1
                continue
            try:
                lng = float(coordinates[0])
                lat = float(coordinates[1])
            except (TypeError, ValueError):
                skipped += 1
                continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                skipped += 1
                continue
            properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
            name = str(properties.get("name") or properties.get("title") or "").strip()[:120]
            if not name:
                skipped += 1
                continue
            existing = query_one(
                """SELECT id FROM map_places
                   WHERE name = ? AND ROUND(lat, 5) = ROUND(?, 5)
                     AND ROUND(lng, 5) = ROUND(?, 5)""",
                (name, lat, lng),
            )
            if existing:
                skipped += 1
                continue
            category_id = target_category_id
            if category_id is None:
                path_value = str(properties.get("category_path") or "").strip()[:200]
                category_name = str(properties.get("category") or "").strip()[:60]
                if path_value:
                    parts = [part.strip()[:60] for part in path_value.split("/") if part.strip()]
                elif category_name:
                    parts = [category_name]
                else:
                    parts = []
                if parts:
                    top_name = parts[0]
                    top = query_one(
                        "SELECT id FROM map_categories WHERE name = ? AND parent_id IS NULL",
                        (top_name,),
                    )
                    if not top and not is_admin:
                        fallback = query_one(
                            """SELECT id FROM map_categories WHERE name = ?
                               ORDER BY parent_id IS NOT NULL LIMIT 1""",
                            (top_name,),
                        )
                        if fallback:
                            top = fallback
                            parts = [top_name]
                    if not top and is_admin:
                        color = str(properties.get("category_color") or "").strip()
                        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                            color = "#7b68ee"
                        glyph = str(properties.get("category_glyph") or "·").strip()[:2] or "·"
                        top = {
                            "id": execute(
                                """INSERT INTO map_categories
                                       (parent_id, name, glyph, color, note, sort_order, created_at)
                                   VALUES (NULL, ?, ?, ?, NULL, ?, ?)""",
                                (top_name, glyph, color.lower(), next_sort, stamp),
                            )
                        }
                        next_sort += 1
                    if top:
                        category_id = top["id"]
                        if len(parts) >= 2:
                            child_name = parts[1]
                            child = query_one(
                                """SELECT id FROM map_categories
                                   WHERE name = ? AND parent_id = ?""",
                                (child_name, top["id"]),
                            )
                            if not child and is_admin:
                                child_sort = query_one(
                                    """SELECT COALESCE(MAX(sort_order), -1) + 1 AS value
                                       FROM map_categories WHERE parent_id = ?""",
                                    (top["id"],),
                                )["value"]
                                color = str(properties.get("category_color") or "").strip()
                                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                                    color = "#7b68ee"
                                glyph = str(properties.get("category_glyph") or "·").strip()[:2] or "·"
                                child = {
                                    "id": execute(
                                        """INSERT INTO map_categories
                                               (parent_id, name, glyph, color, note, sort_order, created_at)
                                           VALUES (?, ?, ?, ?, NULL, ?, ?)""",
                                        (top["id"], child_name, glyph, color.lower(), child_sort, stamp),
                                    )
                                }
                            if child:
                                category_id = child["id"]
            execute(
                """INSERT INTO map_places
                       (category_id, name, subtitle, address, note, signature,
                        tags, lat, lng, status, rating, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    category_id,
                    name,
                    str(properties.get("subtitle") or "").strip()[:120] or None,
                    str(properties.get("address") or "").strip()[:300] or None,
                    str(properties.get("note") or "").strip()[:2000] or None,
                    str(properties.get("signature") or "").strip()[:300] or None,
                    str(properties.get("tags") or "").strip()[:200] or None,
                    lat,
                    lng,
                    (
                        str(properties.get("status") or "").strip().lower()
                        if str(properties.get("status") or "").strip().lower()
                        in ("wish", "visited")
                        else None
                    ),
                    max(0, min(5, int(properties.get("rating") or 0)))
                    if str(properties.get("rating") or "0").lstrip("-").isdigit()
                    else 0,
                    user_id,
                    stamp,
                    stamp,
                ),
            )
            imported += 1
        self.send_json(200, {"imported": imported, "skipped": skipped})

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
                "can_manage": self.can("prompts:write"),
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

    def api_site_message_file(self, path):
        """留言附件：已通过的对所有人开放，待审核的只有上传者和管理员可见。"""
        file_id = int(path.rsplit("/", 1)[1])
        row = query_one(
            "SELECT * FROM site_message_files WHERE id = ?", (file_id,)
        )
        if not row:
            api_error(self, 404, "附件不存在。")
            return
        status = row.get("status") or "approved"
        if status != "approved" and not self.is_admin():
            identity = self.session_identity()
            viewer_id = None
            if identity:
                viewer_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
            if viewer_id is None or row.get("uploaded_by") is None or row["uploaded_by"] != viewer_id:
                api_error(self, 403, "附件正在审核中。")
                return
        self.send_data_file(row["file_path"])

    # ---------- 内容审核（管理员） ----------
    def api_admin_review(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看审核队列。")
            return
        status_filter = str((params.get("status") or ["pending"])[0] or "pending").strip()
        if status_filter not in ("pending", "approved"):
            status_filter = "pending"
        rows = query(
            """SELECT f.id, f.message_id, f.file_name, f.file_size, f.mime_type,
                      f.status, f.uploaded_by, f.created_at, f.reviewed_at, f.reviewed_by,
                      m.nickname AS message_nickname, m.content AS message_content,
                      m.created_at AS message_created_at
               FROM site_message_files f
               LEFT JOIN site_messages m ON m.id = f.message_id
               WHERE f.status = ?
               ORDER BY f.id DESC
               LIMIT 200""",
            (status_filter,),
        )
        for row in rows:
            extension = os.path.splitext(row.get("file_name") or "")[1].lower()
            row["is_image"] = extension in MESSAGE_IMAGE_EXTENSIONS
            row["url"] = f"/api/site/message-files/{row['id']}"
        pending = query_one(
            "SELECT COUNT(*) AS n FROM site_message_files WHERE status = 'pending'"
        )["n"]
        self.send_json(200, {"files": rows, "pending": pending})

    def api_admin_review_action(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以审核附件。")
            return
        file_id = int(path.split("/")[4])
        row = query_one("SELECT * FROM site_message_files WHERE id = ?", (file_id,))
        if not row:
            api_error(self, 404, "附件不存在。")
            return
        action = str(payload.get("action") or "").strip()
        identity = self.session_identity()
        reviewer = (identity or {}).get("nickname") or "管理员"
        if action == "approve":
            execute(
                """UPDATE site_message_files
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?
                   WHERE id = ?""",
                (reviewer, now_text(), file_id),
            )
            write_audit(
                identity,
                "approve_attachment",
                row.get("file_name") or "",
                {"id": row.get("message_id"), "nickname": row.get("file_name")},
            )
            self.send_json(200, {"ok": True, "status": "approved"})
            return
        if action == "reject":
            execute("DELETE FROM site_message_files WHERE id = ?", (file_id,))
            remove_data_file(row.get("file_path"))
            write_audit(
                identity,
                "reject_attachment",
                row.get("file_name") or "",
                {"id": row.get("message_id"), "nickname": row.get("file_name")},
            )
            self.send_json(200, {"ok": True, "status": "rejected"})
            return
        api_error(self, 400, "未知审核操作。")

    def api_admin_review_all(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以审核附件。")
            return
        identity = self.session_identity()
        reviewer = (identity or {}).get("nickname") or "管理员"
        rows = query("SELECT id FROM site_message_files WHERE status = 'pending'")
        if not rows:
            self.send_json(200, {"ok": True, "approved": 0})
            return
        stamp = now_text()
        for row in rows:
            execute(
                """UPDATE site_message_files
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?
                   WHERE id = ?""",
                (reviewer, stamp, row["id"]),
            )
        write_audit(identity, "approve_attachment_batch", f"批量通过 {len(rows)} 个附件")
        self.send_json(200, {"ok": True, "approved": len(rows)})

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
