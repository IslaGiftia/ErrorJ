import base64
import concurrent.futures
import configparser
import csv
import gzip
import hashlib
from html import escape as html_escape, unescape as html_unescape
from html.parser import HTMLParser
import hmac
import ipaddress
import io
import json
import mimetypes
import os
import posixpath
import queue
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
AGENT_BASE_URL = os.environ.get(
    "ERRORJIANG_AGENT_URL", "http://172.17.0.1:8011"
).rstrip("/")
PUBLIC_SITE_URL = os.environ.get(
    "ERRORJIANG_PUBLIC_URL", "https://zhexiyan.cc"
).rstrip("/")
MAP_PUBLIC = os.environ.get("INVENTORY_MAP_PUBLIC", "1").strip().lower() not in (
    "0",
    "false",
    "off",
    "no",
)
AMAP_WEB_KEY = os.environ.get("INVENTORY_AMAP_KEY", "").strip()
AMAP_POI_CACHE_TTL = 600
AMAP_POI_CACHE_LIMIT = 200
AMAP_POI_CACHE = {}
AMAP_POI_CACHE_LOCK = threading.Lock()
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
BOM_REPORT_DIR = DATA_DIR / "bom_reports"
BOM_WATCH_STATE_PATH = DATA_DIR / "bom_watch_state.json"
PART_IMAGE_DIR = DATA_DIR / "part_images"
BOOKMARK_FAVICON_DIR = DATA_DIR / "bookmark_favicons"
NOTE_IMAGE_DIR = DATA_DIR / "note_images"
RECOMMEND_IMAGE_DIR = DATA_DIR / "recommend_images"
MAP_IMAGE_DIR = DATA_DIR / "map_images"
MUSIC_COVER_DIR = DATA_DIR / "music_covers"
BOOK_DIR = DATA_DIR / "book_files"
BOOK_COVER_DIR = DATA_DIR / "book_covers"
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
# 上传走 JSON + base64，体积约为原文件的 1.37 倍：60MB 的音乐大约 80MB 请求体，
# 30MB 的固件大约 41MB，所以这里要留出足够余量（nginx 的 client_max_body_size 同步为 84m）。
MAX_REQUEST_BYTES = 84 * 1024 * 1024
AUTH_PATH = DATA_DIR / "auth.json"
AUTH_COOKIE = "errorjiang_session"
# 会话签名密钥在数据库里的存放键（见 stored_auth_secret）
AUTH_SECRET_KEY = "auth_secret"
AUTH_SESSION_DAYS = 7
AUTH_SESSION_DAYS_REMEMBER = 30
AUTH_PBKDF2_ITERATIONS = 200_000
AUTH_STATE = {"enabled": False, "password_hash": "", "secret": ""}
# 游客角色可以控制的公开页面（对应「全部权限 → 游客」里的开关）
GUEST_PAGE_RULES = {
    "/messages": "guest:page:messages",
    "/moments": "guest:page:moments",
    "/downloads": "guest:page:downloads",
    "/recommendations": "guest:page:recommendations",
    "/music": "guest:page:music",
    "/books": "guest:page:books",
    "/references": "guest:page:references",
}
GUEST_PAGE_PREFIX_RULES = ()
GUEST_API_RULES = {
    "/api/site/messages": "guest:page:messages",
    "/api/moments": "guest:page:moments",
    "/api/recommendations": "guest:page:recommendations",
    "/api/site/music": "guest:page:music",
    "/api/books": "guest:page:books",
    "/api/references": "guest:page:references",
}
GUEST_DATA_RULES = (
    ("moment_images/", "guest:page:moments"),
    ("music_covers/", "guest:page:music"),
    ("book_covers/", "guest:page:books"),
    ("recommend_images/", "guest:page:recommendations"),
)
# 永远公开的基础页：首页、登录、注册、举报说明、静态资源和登录相关接口
ALWAYS_PUBLIC_PAGES = {
    "/",
    "/index.html",
    "/login",
    "/register",
    "/reporting",
    "/favicon.ico",
}
ALWAYS_PUBLIC_APIS = {
    "/api/health",
    "/api/site/activity",
    "/api/site/sidebar",
    "/api/site/reports",
    "/api/site/upload-limits",
    "/api/site/notifications/unread",
    "/api/auth/status",
    "/api/login",
    "/api/member/login",
    "/api/register",
    "/api/logout",
}
# 登录账号（普通账户）可以访问的公开站点模块，不受游客开关影响
SITE_MEMBER_PAGES = {
    "/messages",
    "/moments",
    "/recommendations",
    "/music",
    "/books",
    "/references",
}
SITE_MEMBER_APIS = {
    "/api/site/messages",
    "/api/moments",
    "/api/recommendations",
    "/api/site/music",
    "/api/books",
    "/api/site/photos",
    "/api/site/links",
    "/api/references",
}
SITE_MEMBER_DATA_PREFIXES = (
    "moment_images/",
    "site_photos/",
    "music_covers/",
    "book_covers/",
    "recommend_images/",
)
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
AA_PERMISSION = "aa:view"

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
        "label": "书签",
        "items": (
            {"key": "bookmarks:view", "label": "查看书签"},
            {"key": "bookmarks:write", "label": "增删改收藏、导入 Firefox、检查链接"},
        ),
    },
    {
        "key": "notes",
        "label": "笔记",
        "items": (
            {"key": "notes:view", "label": "查看笔记"},
            {"key": "notes:write", "label": "新增、编辑、导入导出笔记"},
        ),
    },
    {
        "key": "aa",
        "label": "计算器",
        "items": (
            {
                "key": "aa:view",
                "label": "使用计算器（查看、创建账目、录入费用）",
            },
        ),
    },
    {
        "key": "map",
        "label": "地图",
        "items": (
            {"key": "map:write", "label": "添加标记、管理自己添加的标记与照片"},
            {"key": "map:write_all", "label": "编辑和删除所有标记"},
            {"key": "map:manage_categories", "label": "管理地图分类"},
        ),
    },
    {
        "key": "site",
        "label": "站点内容",
        "items": (
            {"key": "music:write", "label": "上传、编辑歌单"},
            {"key": "books:write", "label": "上传、编辑、删除书架电子书"},
            {"key": "links:write", "label": "管理宝藏网站链接"},
            {"key": "photos:write", "label": "管理照片墙"},
            {
                "key": "site:device_name",
                "label": "自定义「设备平台」名称（留言 / 动态）",
            },
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
DEFAULT_MEMBER_PERMISSIONS = ("map:write",)
GRANTABLE_PERMISSIONS = tuple(
    item["key"]
    for group in PERMISSION_GROUPS
    for item in group["items"]
)

ROLE_GUEST = "guest"
ROLE_MEMBER = "member"
ROLE_ADMIN = "admin"
ROLE_LABELS = {"guest": "游客", "member": "普通账户", "admin": "管理员"}
GUEST_PAGE_PERMISSIONS = (
    {"key": "guest:page:messages", "label": "留言"},
    {"key": "guest:page:moments", "label": "动态"},
    {"key": "guest:page:downloads", "label": "推荐"},
    {"key": "guest:page:recommendations", "label": "推荐内容"},
    {"key": "guest:page:music", "label": "歌单"},
    {"key": "guest:page:books", "label": "书架"},
    {"key": "guest:page:references", "label": "参考项目"},
)
GUEST_PAGE_PERMISSION_KEYS = tuple(item["key"] for item in GUEST_PAGE_PERMISSIONS)
GUEST_PAGE_LABELS = {item["key"]: item["label"] for item in GUEST_PAGE_PERMISSIONS}
MEMBER_ROLE_PERMISSIONS = tuple(
    key
    for key in GRANTABLE_PERMISSIONS
    if key != ADMIN_PERMISSION and not key.endswith(":view")
)
MEMBER_ROLE_LABELS = {key: PERMISSION_LABELS.get(key, key) for key in MEMBER_ROLE_PERMISSIONS}

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
    "/finance": ("aa:view",),
    "/aa": ("aa:view",),
}
if MAP_PUBLIC:
    # 地图不再对游客开放；登录账号需要至少一个地图权限才能查看
    PAGE_PERMISSIONS["/map"] = (
        "map:write",
        "map:write_all",
        "map:manage_categories",
    )

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
    {"key": "attachment", "label": "新的待审核留言", "default": True},
    {"key": "report", "label": "新的内容举报", "default": True},
    {"key": "message", "label": "新的留言", "default": True},
    {"key": "moment_comment", "label": "新的动态评论", "default": True},
    {"key": "place", "label": "新的标记点", "default": True},
    {"key": "security", "label": "安全提醒（登录失败 / 敏感词拦截）", "default": True},
)
NOTIFY_DEFAULT_EVENTS = tuple(
    item["key"] for item in NOTIFY_EVENTS if item.get("default")
)
LOGIN_FAILURES = {}
LOGIN_ALERT_SENT = {}
LOGIN_ALERT_THRESHOLD = 5
LOGIN_ALERT_WINDOW_SECONDS = 300
LOGIN_ALERT_COOLDOWN_SECONDS = 1800
SENSITIVE_ALERT_SENT = {}
SENSITIVE_ALERT_COOLDOWN_SECONDS = 600
RATE_LIMITS = {}
RATE_LOCK = threading.Lock()
# 一个限速 key 最长多久没动静就认为过期（所有调用点的窗口都不超过 1 小时）
RATE_KEY_TTL_SECONDS = 3600
# 注册申请：同一 IP 24 小时最多 3 次，且同时只能有 1 条待审核申请
REGISTRATION_WINDOW_SECONDS = 24 * 3600
REGISTRATION_LIMIT_PER_WINDOW = 3
REGISTRATION_PENDING_LIMIT = 1
# 额外的短时突发保护，避免同一秒内反复提交
REGISTRATION_BURST_LIMIT = 5
REGISTRATION_BURST_WINDOW_SECONDS = 600
TRUST_PROXY = os.environ.get("INVENTORY_TRUST_PROXY", "") not in ("", "0", "false")
FORCE_SECURE_COOKIES = os.environ.get("INVENTORY_SECURE_COOKIES", "") not in ("", "0", "false")
ACCESS_LOG = os.environ.get("INVENTORY_ACCESS_LOG", "") not in ("", "0", "false")
try:
    LOG_RETENTION_DAYS = max(1, int(os.environ.get("INVENTORY_LOG_DAYS", "180") or 180))
except (TypeError, ValueError):
    LOG_RETENTION_DAYS = 180
LOG_CLEANUP_INTERVAL_SECONDS = 24 * 3600
REPORT_REMINDER_INTERVAL_SECONDS = 30 * 60
ACCESS_LOG_QUEUE = queue.Queue(maxsize=2000)
PAGE_VIEW_PATHS = {
    "/",
    "/index.html",
    "/login",
    "/register",
    "/inventory",
    "/bookmarks",
    "/notes",
    "/finance",
    "/aa",
    "/messages",
    "/workbench",
    "/references",
    "/moments",
    "/map",
    "/downloads",
    "/recommendations",
    "/music",
    "/books",
    "/reporting",
}
PUBLIC_ACTIVITY_LABELS = {
    "message_create": "发表了留言",
    "message_reply": "回复了留言",
    "moment_create": "更新了一条动态",
    "moment_update": "更新了动态",
    "book_upload": "上架了一本电子书",
    "music_upload": "上传了一首歌",
    "recommendation_create": "新增了一条推荐",
    "recommendation_update": "更新了一条推荐",
    "music_download": "下载了一首歌",
    "book_download": "下载了一本电子书",
    "map_place_create": "新增了一个足迹",
}
REFERENCE_ITEM_RE = re.compile(
    r'<article class="reference-item">\s*'
    r'<a href="([^"]+)"[^>]*>(.*?)</a>\s*'
    r'<p>(.*?)</p>\s*</article>',
    re.DOTALL,
)
SHARE_RESOURCE_TYPES = {"book", "music", "workbench_asset"}
DOWNLOAD_RESOURCE_TYPES = {"book", "music"}
MESSAGE_FILE_MAX_BYTES = 5 * 1024 * 1024
MESSAGE_FILE_TOTAL_MAX_BYTES = 15 * 1024 * 1024
MESSAGE_FILE_MAX_COUNT = 3
MESSAGE_DAILY_LIMIT = 9
DEVICE_INFO_MAX_CHARS = 40
REPORT_TARGET_TYPES = ("message", "moment", "book", "recommendation", "music")
REPORT_TARGET_LABELS = {
    "message": "留言",
    "moment": "动态",
    "book": "电子书",
    "recommendation": "推荐",
    "music": "歌曲",
}
REPORT_REASONS = (
    "违法违规",
    "色情低俗",
    "暴力恐怖",
    "诈骗广告",
    "侵权或隐私",
    "其他",
)
REPORT_SLA_HOURS = 24
MOMENT_CONTENT_MAX_CHARS = 2000
MOMENT_COMMENT_MAX_CHARS = 500
MOMENT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
MAP_PHOTO_MAX_BYTES = 8 * 1024 * 1024
MAP_PHOTO_MAX_COUNT = 9
MUSIC_MAX_BYTES = 60 * 1024 * 1024
MUSIC_COVER_MAX_BYTES = 5 * 1024 * 1024
MUSIC_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus"}
MUSIC_DURATION_BACKFILLED = set()
MUSIC_DURATION_BACKFILL_LOCK = threading.Lock()
BOOK_MAX_BYTES = 60 * 1024 * 1024
BOOK_COVER_MAX_BYTES = 5 * 1024 * 1024
BOOK_EXTENSIONS = {
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".fb2",
    ".cbz",
    ".pdf",
    ".txt",
    ".md",
    ".markdown",
}
MOMENT_IMAGE_TOTAL_MAX_BYTES = 15 * 1024 * 1024
MOMENT_IMAGE_MAX_COUNT = 9
UPLOAD_LIMIT_HARD_MAX_BYTES = 60 * 1024 * 1024
UPLOAD_LIMIT_HARD_MAX_COUNT = 100
UPLOAD_LIMIT_SCHEMA = (
    {
        "key": "message_file",
        "label": "留言附件",
        "description": "单条留言允许上传的附件数量、单个大小和合计大小。",
        "count": True,
        "total": True,
        "max_count": MESSAGE_FILE_MAX_COUNT,
        "max_file_bytes": MESSAGE_FILE_MAX_BYTES,
        "max_total_bytes": MESSAGE_FILE_TOTAL_MAX_BYTES,
    },
    {
        "key": "moment_image",
        "label": "动态图片",
        "description": "单条动态允许上传的图片数量、单张大小和合计大小。",
        "count": True,
        "total": True,
        "max_count": MOMENT_IMAGE_MAX_COUNT,
        "max_file_bytes": MOMENT_IMAGE_MAX_BYTES,
        "max_total_bytes": MOMENT_IMAGE_TOTAL_MAX_BYTES,
    },
    {
        "key": "music_file",
        "label": "歌曲音频",
        "description": "本地上传歌曲的单个文件大小和单次选择数量。",
        "count": True,
        "total": False,
        "max_count": 20,
        "max_file_bytes": MUSIC_MAX_BYTES,
    },
    {
        "key": "book_file",
        "label": "电子书",
        "description": "电子书原文件的单个大小和单次选择数量。",
        "count": True,
        "total": False,
        "max_count": 20,
        "max_file_bytes": BOOK_MAX_BYTES,
    },
    {
        "key": "site_photo",
        "label": "照片墙图片",
        "description": "照片墙上传图片的单个大小和单次数量。",
        "count": True,
        "total": False,
        "max_count": 20,
        "max_file_bytes": 15 * 1024 * 1024,
    },
    {
        "key": "recommend_image",
        "label": "推荐封面",
        "description": "推荐模块封面上传大小。",
        "count": False,
        "total": False,
        "max_file_bytes": RECOMMEND_IMAGE_MAX_BYTES,
    },
    {
        "key": "map_photo",
        "label": "足迹照片",
        "description": "单个足迹最多照片数量和单张大小。",
        "count": True,
        "total": False,
        "max_count": MAP_PHOTO_MAX_COUNT,
        "max_file_bytes": MAP_PHOTO_MAX_BYTES,
    },
    {
        "key": "note_image",
        "label": "笔记图片",
        "description": "笔记正文图片的单个大小和单次数量。",
        "count": True,
        "total": False,
        "max_count": 20,
        "max_file_bytes": NOTE_IMAGE_MAX_BYTES,
    },
    {
        "key": "note_import",
        "label": "笔记文档导入",
        "description": "Word / PDF 导入文档的单个大小。",
        "count": False,
        "total": False,
        "max_file_bytes": NOTE_IMPORT_MAX_BYTES,
    },
    {
        "key": "workbench_source",
        "label": "工作台源码 / 工程",
        "description": "源码、工程包等资料的单文件大小。",
        "count": False,
        "total": False,
        "max_file_bytes": WORKBENCH_FILE_MAX_BYTES,
    },
    {
        "key": "workbench_firmware",
        "label": "工作台固件",
        "description": "HEX / BIN / ELF 等固件的单文件大小。",
        "count": False,
        "total": False,
        "max_file_bytes": WORKBENCH_FILE_MAX_BYTES,
    },
    {
        "key": "workbench_document",
        "label": "工作台文档",
        "description": "PDF、原理图、说明文档等的单文件大小。",
        "count": False,
        "total": False,
        "max_file_bytes": WORKBENCH_FILE_MAX_BYTES,
    },
    {
        "key": "workbench_image",
        "label": "工作台图片",
        "description": "工作台图片文件的单文件大小。",
        "count": False,
        "total": False,
        "max_file_bytes": WORKBENCH_FILE_MAX_BYTES,
    },
    {
        "key": "workbench_other",
        "label": "工作台其他文件",
        "description": "其他工作台文件的单文件大小。",
        "count": False,
        "total": False,
        "max_file_bytes": WORKBENCH_FILE_MAX_BYTES,
    },
    {
        "key": "part_image",
        "label": "仓库元件图片",
        "description": "电子元件图片的单文件大小。",
        "count": False,
        "total": False,
        "max_file_bytes": 5 * 1024 * 1024,
    },
)
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
RECOMMEND_KINDS = {"site", "tool", "movie", "anime", "resource"}
SHARE_CONTENT_TYPES = {"note", "book", "music"}
SHARE_CONTENT_LABELS = {"note": "笔记", "book": "电子书", "music": "歌曲"}
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


def reference_seed_rows():
    """从静态参考项目页提取首次迁移数据。"""
    path = STATIC_DIR / "references.html"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for index, match in enumerate(REFERENCE_ITEM_RE.finditer(text)):
        url = html_unescape(match.group(1).strip())
        title = re.sub(r"<[^>]+>", "", match.group(2))
        description = re.sub(r"<[^>]+>", "", match.group(3))
        title = re.sub(r"\s+", " ", html_unescape(title)).strip()
        description = re.sub(r"\s+", " ", html_unescape(description)).strip()
        if not title or not url.startswith(("http://", "https://")):
            continue
        rows.append((title[:200], url[:1000], description[:2000], index))
    return rows


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    BOOKMARK_FAVICON_DIR.mkdir(exist_ok=True)
    NOTE_IMAGE_DIR.mkdir(exist_ok=True)
    MAP_IMAGE_DIR.mkdir(exist_ok=True)
    MUSIC_COVER_DIR.mkdir(exist_ok=True)
    BOOK_DIR.mkdir(exist_ok=True)
    BOOK_COVER_DIR.mkdir(exist_ok=True)
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
                user_id INTEGER,
                ip TEXT,
                ip_region TEXT,
                show_region INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'approved',
                reviewed_by TEXT,
                reviewed_at TEXT,
                review_note TEXT,
                device_info TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS map_place_views (
                user_id INTEGER PRIMARY KEY,
                last_seen_id INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS map_place_interactions (
                place_id INTEGER NOT NULL REFERENCES map_places(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (place_id, user_id, kind)
            );

            CREATE INDEX IF NOT EXISTS idx_map_place_interactions_user
                ON map_place_interactions (user_id, kind);

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
                ip TEXT,
                ip_region TEXT,
                show_region INTEGER NOT NULL DEFAULT 0,
                -- post = 手动发布的动态；log = 更新日志（由导入脚本写入）
                kind TEXT NOT NULL DEFAULT 'post',
                device_info TEXT,
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

            CREATE TABLE IF NOT EXISTS reference_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS share_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                resource_type TEXT NOT NULL,
                resource_id INTEGER NOT NULL,
                created_by TEXT,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                download_count INTEGER NOT NULL DEFAULT 0,
                last_download_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS download_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT,
                UNIQUE(user_id, resource_type, resource_id)
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
                message_daily_limit INTEGER,
                last_login_at TEXT,
                register_ip TEXT
            );

            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                permission TEXT NOT NULL,
                granted_by TEXT,
                granted_at TEXT NOT NULL,
                PRIMARY KEY (user_id, permission)
            );

            CREATE TABLE IF NOT EXISTS role_permissions (
                role TEXT NOT NULL,
                permission TEXT NOT NULL,
                granted_by TEXT,
                granted_at TEXT NOT NULL,
                PRIMARY KEY (role, permission)
            );

            CREATE TABLE IF NOT EXISTS aa_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                owner_user_id INTEGER NOT NULL DEFAULT 0,
                qr_path TEXT,
                qr_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS aa_members (
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (event_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS aa_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_aa_members_user
                ON aa_members(user_id, event_id);

            CREATE INDEX IF NOT EXISTS idx_aa_expenses_event
                ON aa_expenses(event_id, id);

            CREATE TABLE IF NOT EXISTS aa_expense_splits (
                expense_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (expense_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_aa_expense_splits_user
                ON aa_expense_splits(user_id, expense_id);

            CREATE TABLE IF NOT EXISTS aa_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                qr_path TEXT NOT NULL,
                qr_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(event_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_aa_receipts_event
                ON aa_receipts(event_id, user_id);

            CREATE TABLE IF NOT EXISTS sessions (
                sid TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                device TEXT NOT NULL DEFAULT 'desktop',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                ip TEXT
            );

            -- 每个账号在侧栏卡片上自己选的展示状态：user_id = 0 表示站长（Error酱）。
            -- 「在线 / 在线-<设备> / 离线」都由活跃时间自动判定，只有 mode = 'invisible'
            -- 会被记住；suffix 是本人手选的当前设备后缀（Win / Mac / Linux / Android / iOS），
            -- text 只有站长能写。
            CREATE TABLE IF NOT EXISTS user_status (
                user_id INTEGER PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'auto',
                suffix TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS message_views (
                user_id INTEGER PRIMARY KEY,
                last_seen_id INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS content_likes (
                target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (target_type, target_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS moment_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moment_id INTEGER NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
                parent_id INTEGER,
                user_id INTEGER NOT NULL DEFAULT 0,
                actor TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS content_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_key TEXT NOT NULL,
                target_title TEXT,
                target_snapshot TEXT,
                reporter_user_id INTEGER NOT NULL DEFAULT 0,
                reporter_name TEXT,
                reason TEXT NOT NULL,
                detail TEXT,
                contact TEXT,
                ip TEXT,
                ip_region TEXT,
                user_agent TEXT,
                client_platform TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                handled_by TEXT,
                handled_at TEXT,
                resolution TEXT,
                reminded_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_content_reports_status
                ON content_reports (status, created_at);

            CREATE INDEX IF NOT EXISTS idx_content_reports_target
                ON content_reports (target_type, target_key, created_at);

            CREATE TABLE IF NOT EXISTS moment_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moment_id INTEGER NOT NULL UNIQUE REFERENCES moments(id) ON DELETE CASCADE,
                resource_type TEXT NOT NULL,
                resource_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                module TEXT NOT NULL,
                target_id INTEGER,
                actor TEXT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                seen_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_content_likes_target
                ON content_likes (target_type, target_id);
            CREATE INDEX IF NOT EXISTS idx_moment_comments_moment
                ON moment_comments (moment_id, id);
            CREATE INDEX IF NOT EXISTS idx_user_notifications_user
                ON user_notifications (user_id, seen_at, id);
            CREATE INDEX IF NOT EXISTS idx_moment_shares_resource
                ON moment_shares (resource_type, resource_id);

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

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor_kind TEXT NOT NULL DEFAULT 'guest',
                user_id INTEGER NOT NULL DEFAULT 0,
                actor_name TEXT,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                summary TEXT,
                ip TEXT,
                ip_region TEXT,
                source_path TEXT,
                method TEXT,
                source_port INTEGER,
                target_host TEXT,
                target_port INTEGER,
                user_agent TEXT,
                client_platform TEXT
            );

            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor_kind TEXT NOT NULL DEFAULT 'guest',
                ip TEXT,
                ip_region TEXT,
                path TEXT NOT NULL,
                status INTEGER NOT NULL DEFAULT 200,
                user_id INTEGER NOT NULL DEFAULT 0,
                actor_name TEXT,
                referer TEXT,
                user_agent TEXT,
                device TEXT,
                method TEXT,
                source_port INTEGER,
                target_host TEXT,
                target_port INTEGER,
                client_platform TEXT
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
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                tags TEXT,
                description TEXT,
                format TEXT NOT NULL,
                file_path TEXT NOT NULL,
                cover_path TEXT,
                file_size INTEGER,
                mime_type TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS book_progress (
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                location TEXT,
                percent REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, book_id)
            );

            CREATE TABLE IF NOT EXISTS book_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                location TEXT NOT NULL,
                label TEXT,
                percent REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS book_annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                location TEXT NOT NULL,
                text TEXT,
                note TEXT,
                color TEXT,
                percent REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_parts_lcsc ON parts(lcsc_code);
            CREATE INDEX IF NOT EXISTS idx_book_progress_user ON book_progress(user_id);
            CREATE INDEX IF NOT EXISTS idx_book_bookmarks_book ON book_bookmarks(book_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_book_annotations_book ON book_annotations(book_id, user_id);
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
            CREATE INDEX IF NOT EXISTS idx_reference_projects_order ON reference_projects(sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token);
            CREATE INDEX IF NOT EXISTS idx_share_links_resource ON share_links(resource_type, resource_id);
            CREATE INDEX IF NOT EXISTS idx_download_requests_user ON download_requests(user_id, resource_type, resource_id);
            CREATE INDEX IF NOT EXISTS idx_download_requests_status ON download_requests(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_bookmark_folders_parent ON bookmark_folders(parent_id);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_folder ON bookmarks(folder_id);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON bookmarks(created_at);
            CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_activity_log_action ON activity_log(action);
            CREATE INDEX IF NOT EXISTS idx_activity_log_user ON activity_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_activity_log_ip ON activity_log(ip);
            CREATE INDEX IF NOT EXISTS idx_access_log_created ON access_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_access_log_path ON access_log(path);
            CREATE INDEX IF NOT EXISTS idx_access_log_ip ON access_log(ip);
            CREATE INDEX IF NOT EXISTS idx_access_log_user ON access_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_access_log_actor ON access_log(actor_kind, created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(kind, user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
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
        user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "register_ip" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN register_ip TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_register_ip ON users(register_ip)")
        moment_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(moments)").fetchall()
        ]
        if "kind" not in moment_columns:
            conn.execute("ALTER TABLE moments ADD COLUMN kind TEXT NOT NULL DEFAULT 'post'")
            # 老数据里更新日志是靠内容前缀写进去的，这里只回填这一次；
            # 之后新导入的日志由 tools/import_changelog_moments.py 自己写 kind='log'。
            conn.execute("UPDATE moments SET kind = 'log' WHERE content LIKE '【更新日志】%'")
        session_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        ]
        if "ip" not in session_columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN ip TEXT")
            # 升级前签发的会话没有记录来源 IP，无法套用「管理员会话绑定 IP」的新规则，
            # 统一作废掉，让人重新登录一次；普通账号的会话不受影响。
            conn.execute(
                "DELETE FROM sessions WHERE kind = 'owner' OR user_id IN "
                "(SELECT user_id FROM user_permissions WHERE permission = ?)",
                (ADMIN_PERMISSION,),
            )
        recommendation_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(recommendations)").fetchall()
        ]
        if "bookmark_id" not in recommendation_columns:
            conn.execute(
                "ALTER TABLE recommendations ADD COLUMN bookmark_id INTEGER "
                "REFERENCES bookmarks(id) ON DELETE SET NULL"
            )
        for column in ("resource_type", "resource_id"):
            if column not in recommendation_columns:
                definition = "TEXT" if column == "resource_type" else "INTEGER"
                conn.execute(
                    f"ALTER TABLE recommendations ADD COLUMN {column} {definition}"
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
        interaction_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(map_place_interactions)").fetchall()
        }
        if "active" not in interaction_columns:
            conn.execute(
                "ALTER TABLE map_place_interactions ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )
        # 清理历史遗留：标记点删除后留下的互动记录和已失效提醒
        conn.execute(
            """DELETE FROM map_place_interactions
               WHERE place_id NOT IN (SELECT id FROM map_places)"""
        )
        conn.execute(
            """DELETE FROM user_notifications
               WHERE module = 'map' AND target_id NOT IN (SELECT id FROM map_places)"""
        )
        # 游戏模块已下线：清掉历史公开动态、相关举报和残留权限（重复执行无副作用）
        conn.execute("DELETE FROM activity_log WHERE action = 'game_play'")
        conn.execute("DELETE FROM content_reports WHERE target_type = 'game'")
        conn.execute("DELETE FROM role_permissions WHERE permission = 'guest:page:games'")
        conn.execute("DELETE FROM user_permissions WHERE permission = 'guest:page:games'")
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
        # 「设备信息」：留言和动态都记录一条「来自 <系统>」或管理员自定义的名称
        for table in ("site_messages", "moments"):
            table_columns = {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "device_info" not in table_columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN device_info TEXT")
        user_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        for column, ddl in (
            ("nickname", "ALTER TABLE users ADD COLUMN nickname TEXT"),
            ("nickname_updated_at", "ALTER TABLE users ADD COLUMN nickname_updated_at TEXT"),
            ("silenced_until", "ALTER TABLE users ADD COLUMN silenced_until TEXT"),
            ("message_daily_limit", "ALTER TABLE users ADD COLUMN message_daily_limit INTEGER"),
        ):
            if column not in user_columns:
                conn.execute(ddl)
        permission_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(user_permissions)").fetchall()
        }
        if "mode" not in permission_columns:
            conn.execute(
                "ALTER TABLE user_permissions ADD COLUMN mode TEXT NOT NULL DEFAULT 'allow'"
            )
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
        message_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(site_messages)").fetchall()
        }
        for column, ddl in (
            ("user_id", "ALTER TABLE site_messages ADD COLUMN user_id INTEGER"),
            ("ip", "ALTER TABLE site_messages ADD COLUMN ip TEXT"),
            ("ip_region", "ALTER TABLE site_messages ADD COLUMN ip_region TEXT"),
            (
                "show_region",
                "ALTER TABLE site_messages ADD COLUMN show_region INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "status",
                "ALTER TABLE site_messages ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'",
            ),
            ("reviewed_by", "ALTER TABLE site_messages ADD COLUMN reviewed_by TEXT"),
            ("reviewed_at", "ALTER TABLE site_messages ADD COLUMN reviewed_at TEXT"),
            ("review_note", "ALTER TABLE site_messages ADD COLUMN review_note TEXT"),
        ):
            if column not in message_columns:
                conn.execute(ddl)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_messages_status "
            "ON site_messages(status, created_at)"
        )
        moment_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(moments)").fetchall()
        }
        for column, ddl in (
            ("ip", "ALTER TABLE moments ADD COLUMN ip TEXT"),
            ("ip_region", "ALTER TABLE moments ADD COLUMN ip_region TEXT"),
            (
                "show_region",
                "ALTER TABLE moments ADD COLUMN show_region INTEGER NOT NULL DEFAULT 0",
            ),
        ):
            if column not in moment_columns:
                conn.execute(ddl)
        activity_log_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(activity_log)").fetchall()
        }
        for column, ddl in (
            ("method", "ALTER TABLE activity_log ADD COLUMN method TEXT"),
            ("source_port", "ALTER TABLE activity_log ADD COLUMN source_port INTEGER"),
            ("target_host", "ALTER TABLE activity_log ADD COLUMN target_host TEXT"),
            ("target_port", "ALTER TABLE activity_log ADD COLUMN target_port INTEGER"),
            ("user_agent", "ALTER TABLE activity_log ADD COLUMN user_agent TEXT"),
            ("client_platform", "ALTER TABLE activity_log ADD COLUMN client_platform TEXT"),
        ):
            if column not in activity_log_columns:
                conn.execute(ddl)
        access_log_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(access_log)").fetchall()
        }
        for column, ddl in (
            ("method", "ALTER TABLE access_log ADD COLUMN method TEXT"),
            ("source_port", "ALTER TABLE access_log ADD COLUMN source_port INTEGER"),
            ("target_host", "ALTER TABLE access_log ADD COLUMN target_host TEXT"),
            ("target_port", "ALTER TABLE access_log ADD COLUMN target_port INTEGER"),
            ("client_platform", "ALTER TABLE access_log ADD COLUMN client_platform TEXT"),
        ):
            if column not in access_log_columns:
                conn.execute(ddl)
        report_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(content_reports)").fetchall()
        }
        if "client_platform" not in report_columns:
            conn.execute("ALTER TABLE content_reports ADD COLUMN client_platform TEXT")
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
        # 一次性修复历史数据：早期「新增分类」会先建一个图标为占位「新」的分类，
        # 改名时图标没跟着走，于是留下「酒店 + 新」这种不一致。名字首字已经变了、
        # 图标还停在占位「新」的，按名字首字补齐；自定义过图标的分类不受影响。
        glyph_fix = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'map_glyph_follow_fix_v1'"
        ).fetchone()
        if not glyph_fix:
            conn.execute(
                """UPDATE map_categories
                      SET glyph = substr(trim(name), 1, 1)
                    WHERE glyph = '新'
                      AND trim(name) <> ''
                      AND substr(trim(name), 1, 1) <> '新'"""
            )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('map_glyph_follow_fix_v1', ?)",
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
        role_seed = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'role_permissions_v1'"
        ).fetchone()
        if not role_seed:
            stamp = now_text()
            for key in GUEST_PAGE_PERMISSION_KEYS:
                conn.execute(
                    """INSERT OR IGNORE INTO role_permissions
                           (role, permission, granted_by, granted_at)
                       VALUES (?, ?, ?, ?)""",
                    (ROLE_GUEST, key, "系统初始化", stamp),
                )
            for key in DEFAULT_MEMBER_PERMISSIONS:
                conn.execute(
                    """INSERT OR IGNORE INTO role_permissions
                           (role, permission, granted_by, granted_at)
                       VALUES (?, ?, ?, ?)""",
                    (ROLE_MEMBER, key, "系统初始化", stamp),
                )
            # 旧版批准账号时自动写入的 map:write 默认值，改为跟随「普通账户」角色
            conn.execute(
                """DELETE FROM user_permissions
                   WHERE permission = 'map:write' AND mode = 'allow'
                     AND user_id IN (
                         SELECT user_id FROM user_permissions
                         GROUP BY user_id HAVING COUNT(*) = 1
                     )"""
            )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('role_permissions_v1', ?)",
                (stamp,),
            )
        # 旧费用没有分摊明细时，按当时活动成员全员平均分摊回填。
        conn.execute(
            """INSERT OR IGNORE INTO aa_expense_splits (expense_id, user_id)
               SELECT e.id, m.user_id
               FROM aa_expenses e
               JOIN aa_members m ON m.event_id = e.event_id
               WHERE NOT EXISTS (
                   SELECT 1 FROM aa_expense_splits s WHERE s.expense_id = e.id
               )"""
        )
        # 旧版活动只有一张发起人收款码，迁移为每位成员各自一张的收款码表。
        receipt_migration = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'finance_receipts_migrated_v1'"
        ).fetchone()
        if not receipt_migration:
            conn.execute(
                """INSERT OR IGNORE INTO aa_receipts
                       (event_id, user_id, qr_path, qr_name, created_at, updated_at)
                   SELECT id, owner_user_id, qr_path, qr_name, created_at, updated_at
                   FROM aa_events
                   WHERE qr_path IS NOT NULL AND qr_path <> ''"""
            )
            conn.execute(
                "UPDATE aa_events SET qr_path = NULL, qr_name = NULL"
            )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('finance_receipts_migrated_v1', ?)",
                (now_text(),),
            )
        guest_books = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'books_guest_page_v1'"
        ).fetchone()
        if not guest_books:
            conn.execute(
                """INSERT OR IGNORE INTO role_permissions
                       (role, permission, granted_by, granted_at)
                   VALUES (?, ?, ?, ?)""",
                (ROLE_GUEST, "guest:page:books", "系统初始化", now_text()),
            )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('books_guest_page_v1', ?)",
                (now_text(),),
            )
        guest_downloads = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'downloads_guest_page_v1'"
        ).fetchone()
        if not guest_downloads:
            conn.execute(
                """INSERT OR IGNORE INTO role_permissions
                       (role, permission, granted_by, granted_at)
                   VALUES (?, ?, ?, ?)""",
                (ROLE_GUEST, "guest:page:downloads", "系统初始化", now_text()),
            )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('downloads_guest_page_v1', ?)",
                (now_text(),),
            )
        reference_seeded = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'reference_projects_seeded_v1'"
        ).fetchone()
        if not reference_seeded:
            seed_rows = reference_seed_rows()
            if seed_rows:
                stamp = now_text()
                conn.executemany(
                    """INSERT INTO reference_projects
                           (title, url, description, sort_order, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [(*row, stamp, stamp) for row in seed_rows],
                )
                conn.execute(
                    "INSERT INTO app_meta (key, value) VALUES ('reference_projects_seeded_v1', ?)",
                    (stamp,),
                )
        reference_pruned = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'reference_projects_pruned_v2'"
        ).fetchone()
        if not reference_pruned:
            # 2026-10 的几轮重构删掉了小游戏模块与站内电子书阅读器，参考项目清单跟着收敛一次：
            # 以 static/references.html 为准，删掉已经不在清单里的条目、更新其余条目的文案与顺序。
            # 只跑一次（带标记），之后页面内新增 / 编辑的条目不会再被动过。
            seed_rows = reference_seed_rows()
            keep_titles = {row[0] for row in seed_rows}
            existing_ids = {
                row["title"]: row["id"]
                for row in conn.execute(
                    "SELECT id, title FROM reference_projects"
                ).fetchall()
            }
            for title, item_id in existing_ids.items():
                if title not in keep_titles:
                    conn.execute(
                        "DELETE FROM reference_projects WHERE id = ?", (item_id,)
                    )
            stamp = now_text()
            for title, url, description, sort_order in seed_rows:
                item_id = existing_ids.get(title)
                if item_id:
                    conn.execute(
                        """UPDATE reference_projects
                           SET url = ?, description = ?, sort_order = ?, updated_at = ?
                           WHERE id = ?""",
                        (url, description, sort_order, stamp, item_id),
                    )
                else:
                    conn.execute(
                        """INSERT INTO reference_projects
                               (title, url, description, sort_order, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (title, url, description, sort_order, stamp, stamp),
                    )
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('reference_projects_pruned_v2', ?)",
                (stamp,),
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


def finite_number(value, label="数量"):
    """把用户提交的数量转成有限的浮点数。

    float() 会接受 "nan" / "inf"，而 NaN 参与比较恒为 False，
    `value <= 0` 这类校验会直接放行；NaN 还会被 SQLite 存成 NULL，
    之后 sum()/min() 抛 TypeError，那个元件的库存就再也动不了了。
    """
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        raise ValueError(f"{label}必须是数字。")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label}不合法。")
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


def save_part_image(part_id, data_base64, file_name, max_bytes=5 * 1024 * 1024):
    try:
        data = base64.b64decode(data_base64)
    except Exception as exc:
        raise ValueError("图片内容无法解码。") from exc
    if not data:
        raise ValueError("图片内容为空。")
    if len(data) > max_bytes:
        raise ValueError(f"图片不能超过 {format_upload_limit_bytes(max_bytes)}。")
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


def normalized_data_relative(relative):
    """Return a canonical DATA_DIR-relative path, or "" if it escapes DATA_DIR."""
    text = str(relative or "").replace("\\", "/")
    if (
        not text
        or text.startswith("/")
        or re.match(r"^[A-Za-z]:/", text)
        or any(part == ".." for part in text.split("/"))
    ):
        return ""
    try:
        full = (DATA_DIR / text).resolve()
        full.relative_to(DATA_DIR.resolve())
        return full.relative_to(DATA_DIR.resolve()).as_posix()
    except (OSError, ValueError):
        return ""


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


def ensure_music_duration(row):
    """返回本地歌曲时长；旧记录缺失时读取文件补一次。"""
    try:
        duration = float(row.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration > 0:
        return duration
    if row.get("source_type") != "file":
        return None
    item_id = int(row.get("id") or 0)
    with MUSIC_DURATION_BACKFILL_LOCK:
        if item_id in MUSIC_DURATION_BACKFILLED:
            return None
        MUSIC_DURATION_BACKFILLED.add(item_id)
    source_id = row.get("source_id") or ""
    path = DATA_DIR / source_id
    try:
        if not path.is_file() or path.stat().st_size > MUSIC_MAX_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    metadata = parse_audio_metadata(raw, os.path.basename(source_id))
    try:
        duration = float(metadata.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration > 0:
        execute("UPDATE site_music SET duration = ? WHERE id = ?", (duration, item_id))
        return duration
    return None


CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))


def _has_cjk(text):
    return any(
        any(start <= ord(char) <= end for start, end in CJK_RANGES)
        for char in str(text or "")
    )


def guess_title_and_artist(stem):
    """文件里没有标签时，从文件名猜标题和作者（歌名/歌手、书名/作者通用）。

    - 「作者 - 标题」这种带空格的写法按标准解析；
    - 中文常见的「标题-作者」只在两边都含中文时才拆，避免误伤英文文件名。
    """
    text = str(stem or "").strip()
    if not text:
        return "", ""
    for separator in (" - ", " – ", " — "):
        if separator in text:
            left, _, right = text.rpartition(separator)
            left, right = left.strip(), right.strip()
            if left and right:
                return right[:120], left[:120]
    if "-" in text:
        left, _, right = text.rpartition("-")
        left, right = left.strip(), right.strip()
        if left and right and _has_cjk(left) and _has_cjk(right) and len(right) <= 16:
            return left[:120], right[:120]
    return text[:120], ""


def parse_epub_metadata(raw):
    """从 EPUB（zip 容器）里读标题、作者、简介和封面。"""
    info = {"title": "", "author": "", "description": "", "cover": None}
    ns_container = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    ns_opf = {"o": "http://www.idpf.org/2007/opf"}
    ns_dc = {"d": "http://purl.org/dc/elements/1.1/"}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = set(archive.namelist())
            if "META-INF/container.xml" not in names:
                return info
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(".//c:rootfile", ns_container)
            if rootfile is None:
                return info
            opf_path = (rootfile.get("full-path") or "").strip()
            if opf_path not in names:
                lowered = {name.lower(): name for name in names}
                opf_path = lowered.get(opf_path.lower(), "")
            if not opf_path:
                return info
            opf = ET.fromstring(archive.read(opf_path))
            base = posixpath.dirname(opf_path)

            def dc_text(tag):
                node = opf.find(f".//d:{tag}", ns_dc)
                return (node.text or "").strip() if node is not None else ""

            info["title"] = dc_text("title")[:200]
            info["author"] = "、".join(
                (node.text or "").strip()
                for node in opf.findall(".//d:creator", ns_dc)
                if (node.text or "").strip()
            )[:200]
            info["description"] = dc_text("description")[:1000]

            manifest = {}
            for item in opf.findall(".//o:manifest/o:item", ns_opf):
                item_id = item.get("id")
                if item_id:
                    manifest[item_id] = item
            cover_item = None
            for meta in opf.findall(".//o:metadata/o:meta", ns_opf):
                if (meta.get("name") or "").lower() == "cover" and meta.get("content"):
                    cover_item = manifest.get(meta.get("content"))
                    if cover_item is not None:
                        break
            if cover_item is None:
                for item in manifest.values():
                    if "cover-image" in (item.get("properties") or ""):
                        cover_item = item
                        break
            if cover_item is not None:
                href = unquote(cover_item.get("href") or "")
                path = posixpath.normpath(posixpath.join(base, href)) if base else href
                if path in names:
                    data = archive.read(path)
                    if data and len(data) <= BOOK_COVER_MAX_BYTES:
                        extension = _image_ext_from_magic(data) or os.path.splitext(path)[1].lower()
                        info["cover"] = (data, extension or ".jpg")
    except Exception:
        return info
    return info


def parse_mobi_metadata(raw):
    """尽力从 MOBI / AZW3 的 EXTH 记录里读标题、作者和封面。"""
    info = {"title": "", "author": "", "description": "", "cover": None}
    try:
        if len(raw) < 132 or raw[60:68] != b"BOOKMOBI":
            return info
        record_count = int.from_bytes(raw[76:78], "big")
        if record_count < 1:
            return info
        offsets = []
        cursor = 78
        for _ in range(record_count):
            if cursor + 8 > len(raw):
                return info
            offsets.append(int.from_bytes(raw[cursor : cursor + 4], "big"))
            cursor += 8

        def record(index):
            start = offsets[index]
            end = offsets[index + 1] if index + 1 < len(offsets) else len(raw)
            return raw[start:end]

        header = record(0)
        if header[16:20] != b"MOBI":
            return info
        header_len = int.from_bytes(header[20:24], "big")
        mobi = header[16:]
        first_image = int.from_bytes(mobi[0x5C:0x60], "big") if len(mobi) >= 0x60 else 0
        exth_flags = int.from_bytes(mobi[0x70:0x74], "big") if len(mobi) >= 0x74 else 0
        title = ""
        author = ""
        cover_offset = -1
        if exth_flags & 0x40 and header_len:
            start = 16 + header_len
            if header[start : start + 4] == b"EXTH":
                count = int.from_bytes(header[start + 8 : start + 12], "big")
                pos = start + 12
                for _ in range(min(count, 512)):
                    if pos + 8 > len(header):
                        break
                    record_type = int.from_bytes(header[pos : pos + 4], "big")
                    record_len = int.from_bytes(header[pos + 4 : pos + 8], "big")
                    if record_len < 8:
                        break
                    data = header[pos + 8 : pos + record_len]
                    pos += record_len
                    if record_type == 100 and not author:
                        author = data.decode("utf-8", "ignore").strip()
                    elif record_type == 503 and not title:
                        title = data.decode("utf-8", "ignore").strip()
                    elif record_type in (201, 202) and len(data) >= 4 and cover_offset < 0:
                        cover_offset = int.from_bytes(data[:4], "big")
        if not title:
            title = raw[:32].split(b"\x00")[0].decode("utf-8", "ignore").strip()
        info["title"] = title[:200]
        info["author"] = author[:200]
        if cover_offset >= 0 and first_image:
            index = first_image + cover_offset
            if 0 <= index < len(offsets):
                data = record(index)
                extension = _image_ext_from_magic(data)
                if extension and len(data) <= BOOK_COVER_MAX_BYTES:
                    info["cover"] = (data, extension)
    except Exception:
        return info
    return info


def parse_pdf_metadata(raw):
    """PDF 只做尽力而为的标题/作者解析（正文与封面交给前端 PDF.js）。"""
    info = {"title": "", "author": "", "description": "", "cover": None}
    if not raw.startswith(b"%PDF"):
        return info
    head = raw[: 512 * 1024]

    def pdf_string(key):
        pattern = re.compile(
            rb"/" + key.encode("ascii") + rb"\s*(\(((?:\\.|[^()\\]){0,300})\)|<([0-9A-Fa-f\s]{4,600})>)"
        )
        match = pattern.search(head)
        if not match:
            return ""
        if match.group(2) is not None:
            data = _pdf_unescape(match.group(2))
        else:
            try:
                data = bytes.fromhex(re.sub(rb"\s+", b"", match.group(3)).decode("ascii"))
            except ValueError:
                return ""
        if data.startswith(b"\xfe\xff"):
            return data[2:].decode("utf-16-be", "ignore").strip()
        try:
            return data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return data.decode("latin-1", "ignore").strip()

    info["title"] = pdf_string("Title")[:200]
    info["author"] = pdf_string("Author")[:200]
    return info


def _pdf_unescape(data):
    """还原 PDF 字面量字符串里的转义（包括 \\ddd 八进制）。"""
    out = bytearray()
    index = 0
    simple = {
        0x6E: 10,
        0x72: 13,
        0x74: 9,
        0x62: 8,
        0x66: 12,
        0x28: 40,
        0x29: 41,
        0x5C: 92,
    }
    while index < len(data):
        char = data[index]
        if char != 0x5C or index + 1 >= len(data):
            out.append(char)
            index += 1
            continue
        nxt = data[index + 1]
        if nxt in simple:
            out.append(simple[nxt])
            index += 2
            continue
        if 0x30 <= nxt <= 0x37:
            digits = b""
            cursor = index + 1
            while cursor < len(data) and len(digits) < 3 and 0x30 <= data[cursor] <= 0x37:
                digits += bytes([data[cursor]])
                cursor += 1
            out.append(int(digits, 8) & 0xFF)
            index = cursor
            continue
        index += 2
    return bytes(out)


def parse_book_metadata(raw, filename):
    """按扩展名解析电子书元数据（标题、作者、简介、封面）。"""
    extension = os.path.splitext(filename or "")[1].lower()
    info = {"title": "", "author": "", "description": "", "cover": None}
    try:
        if extension == ".epub":
            info.update(parse_epub_metadata(raw))
        elif extension in (".mobi", ".azw", ".azw3"):
            info.update(parse_mobi_metadata(raw))
        elif extension == ".pdf":
            info.update(parse_pdf_metadata(raw))
    except Exception:
        return info
    return info


def guess_book_name(stem):
    """文件名兜底：优先认《书名》/作者：某某，其次按「标题-作者」拆。"""
    text = str(stem or "").strip()
    title = ""
    author = ""
    match = re.search(r"[《【]([^》】]{1,80})[》】]", text)
    if match:
        title = match.group(1).strip()
    match = re.search(r"作者[:：]\s*([^\s（(]{1,40})", text)
    if match:
        author = match.group(1).strip()
    if not title:
        guess_title, guess_author = guess_title_and_artist(text)
        title = guess_title
        if not author:
            author = guess_author
    return title[:200], author[:200]


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


# ---------- IP 属地（国内到省级，国外到国家 / 地区） ----------

IP_REGION_CACHE = {}
IP_REGION_CACHE_TTL = 7 * 86400
IP_REGION_CACHE_FAIL_TTL = 600
IP_REGION_CACHE_LIMIT = 2000
IP_REGION_CACHE_LOCK = threading.Lock()
REGION_SUFFIXES = (
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "特别行政区",
    "自治区",
    "省",
    "市",
)


def is_private_ip(address):
    """内网 / 回环 / 非法地址返回 True，这些地址不做属地解析。"""
    text = str(address or "").strip()
    if not text or text == "unknown":
        return True
    if ":" in text:
        lowered = text.lower()
        if lowered == "::1":
            return True
        return lowered.startswith(("fc", "fd", "fe80", "::ffff:127."))
    parts = text.split(".")
    if len(parts) != 4:
        return True
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        return True
    if any(octet < 0 or octet > 255 for octet in octets):
        return True
    if octets[0] in (0, 10, 127):
        return True
    if octets[0] == 192 and octets[1] == 168:
        return True
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    if octets[0] == 169 and octets[1] == 254:
        return True
    return False


def normalize_region(name):
    text = str(name or "").strip()
    if not text or text in ("[]", "未知", "局域网"):
        return ""
    for suffix in REGION_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text[:20]


def mask_username(value):
    """游客视角只保留用户名最后一个字符。"""
    text = str(value or "").strip()
    if not text:
        return "普通用户"
    if len(text) == 1:
        return text
    return "*" * (len(text) - 1) + text[-1]


def is_recent_time(value, seconds):
    """某个「YYYY-MM-DD HH:MM:SS」时间戳是否落在最近 N 秒内（解析不了算「不在」）。"""
    text = str(value or "").strip()
    if not text:
        return False
    try:
        moment = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return datetime.now() - moment <= timedelta(seconds=seconds)


def is_recent_place(created_at, hours=24):
    """标记点是否在最近 N 小时内创建（用于首次没记录时的提醒基线）。"""
    return is_recent_time(created_at, hours * 3600)


# ---------- 留言 / 动态页的左右侧栏 ----------

# 侧栏「更新日志」只收这几种管理员更新动作，并按动作落到对应页面
SIDEBAR_ACTIVITY_HREFS = {
    "moment_create": "/moments",
    "music_upload": "/music",
    "book_upload": "/books",
    "recommendation_create": "/downloads?tab=web",
    "map_place_create": "/map",
}
# 目标属于「推荐页四个标签里的哪一个」：前端据此判断「内容就在当前页」时原地切标签
SIDEBAR_ACTIVITY_TABS = {
    "music_upload": "music",
    "book_upload": "books",
    "recommendation_create": "web",
}
# 点击日志后，目标页用哪个查询参数定位到这一条（地图页本来就是 place）
SIDEBAR_FOCUS_PARAM = {
    "map_place_create": "place",
}
# 每条日志的文案前缀 + 目标类型（用来查「更新了哪一条」的名称）
SIDEBAR_ACTIVITY_META = {
    "moment_create": ("更新动态", "moment"),
    "music_upload": ("上传歌曲", "music"),
    "book_upload": ("上传书籍", "book"),
    "recommendation_create": ("推荐网页", "recommendation"),
    "map_place_create": ("新增足迹", "map_place"),
}
SIDEBAR_ACTIVITY_LIMIT = 11
# 动态正文取多少个字进日志
SIDEBAR_MOMENT_SNIPPET = 24
# 先按动作过滤再截断，所以多取一些原始行再筛
SIDEBAR_ACTIVITY_SCAN = 60
SIDEBAR_COVER_LIMIT = 10
SIDEBAR_USER_LIMIT = 200
SITE_START_CACHE = {"at": 0.0, "value": ""}
SITE_START_CACHE_TTL = 5.0


def days_since(text):
    """某个时间点到现在经过的天数（含当天，最少 1 天）；解析不了返回 0。"""
    value = str(text or "").strip()
    if len(value) < 10:
        return 0
    try:
        start = datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return 0
    return max(1, (date.today() - start).days + 1)


def site_started_at():
    """建站起点：取站内最早的一条内容时间（用户 / 动态 / 留言 / 歌曲 / 书籍）。"""
    now = time.time()
    cached = SITE_START_CACHE
    if cached["value"] and now - cached["at"] < SITE_START_CACHE_TTL:
        return cached["value"]
    row = query_one(
        """SELECT MIN(created_at) AS at FROM (
               SELECT created_at FROM users
               UNION ALL SELECT created_at FROM moments
               UNION ALL SELECT created_at FROM site_messages
               UNION ALL SELECT created_at FROM site_music
               UNION ALL SELECT created_at FROM books
           )"""
    )
    value = str((row or {}).get("at") or "")
    cached["at"] = now
    cached["value"] = value
    return value


def sidebar_stats():
    """左上基础信息卡片用的站点统计。"""
    approved = query_one(
        "SELECT COUNT(*) AS n FROM users WHERE status = 'approved'"
    )["n"]
    pending = query_one("SELECT COUNT(*) AS n FROM users WHERE status = 'pending'")["n"]
    messages = query_one(
        """SELECT COUNT(*) AS n FROM site_messages
           WHERE parent_id IS NULL AND status = 'approved'"""
    )["n"]
    moments = query_one(
        "SELECT COUNT(*) AS n FROM moments WHERE IFNULL(kind, 'post') <> 'log'"
    )["n"]
    return {
        "user_total": int(approved),
        "user_pending": int(pending),
        "message_total": int(messages),
        "moment_total": int(moments),
        "site_days": days_since(site_started_at()) or 1,
    }


def cover_file_ok(relative):
    """封面文件真的存在才拿去轮播：老数据里可能有指向已删文件的路径。"""
    value = str(relative or "").strip()
    if not value:
        return False
    try:
        full = (DATA_DIR / value).resolve()
        full.relative_to(DATA_DIR.resolve())
    except (ValueError, OSError):
        return False
    return full.is_file()


def sidebar_covers(limit=SIDEBAR_COVER_LIMIT):
    """右上封面轮播：歌曲与电子书的封面混排，按时间倒序取最新的若干条。

    没有封面（或封面文件已经不在）的条目直接跳过，不占轮播的位置。
    """
    items = []
    for row in query(
        """SELECT title, artist, album, cover_path, created_at FROM site_music
           WHERE cover_path IS NOT NULL AND cover_path <> ''
           ORDER BY id DESC LIMIT ?""",
        (limit * 4,),
    ):
        if not cover_file_ok(row.get("cover_path")):
            continue
        items.append(
            {
                "type": "music",
                "title": str(row.get("title") or "未命名歌曲"),
                "subtitle": str(row.get("artist") or row.get("album") or "歌曲"),
                "cover_url": "/site-files/" + str(row.get("cover_path") or ""),
                "href": "/downloads?tab=music",
                "created_at": str(row.get("created_at") or ""),
            }
        )
    for row in query(
        """SELECT title, author, cover_path, created_at FROM books
           WHERE cover_path IS NOT NULL AND cover_path <> ''
           ORDER BY id DESC LIMIT ?""",
        (limit * 4,),
    ):
        if not cover_file_ok(row.get("cover_path")):
            continue
        items.append(
            {
                "type": "book",
                "title": str(row.get("title") or "未命名书籍"),
                "subtitle": str(row.get("author") or "电子书"),
                "cover_url": "/site-files/" + str(row.get("cover_path") or ""),
                "href": "/downloads?tab=books",
                "created_at": str(row.get("created_at") or ""),
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def sidebar_users(viewer_id=0, masked=False, viewer_is_admin=False):
    """左下「注册账户」卡片：只放**已通过审核**的账号，最多 5 行。

    - 管理员和普通账号看到同一份前 5 个账号、每行都带状态胶囊，但「注册 N 天 · X 前活跃」
      那一行**只有管理员看得到**（普通账号连自己那行也不显示）。
    - **游客也看得到这张卡**，但用户名脱敏（只保留最后一个字），不显示注册 / 活跃时间，
      也不下发任何人的状态 —— 游客只能看到左上「Error酱」那一枚状态胶囊。
    - 普通账号如果不在前 5 里，会把自己那行补在最前面，否则他没地方点自己的状态胶囊。
      站长（viewer_id = 0）不在 users 表里，本来就不会也不需要出现在这张卡上。
    """
    rows = query(
        """SELECT id, username, nickname, created_at, last_login_at
           FROM users WHERE status = 'approved'
           ORDER BY id DESC
           LIMIT ?""",
        (SIDEBAR_USER_LIMIT,),
    )
    if viewer_id:
        if int(viewer_id) not in [int(row["id"]) for row in rows]:
            mine = query_one(
                """SELECT id, username, nickname, created_at, last_login_at
                   FROM users WHERE id = ? AND status = 'approved'""",
                (int(viewer_id),),
            )
            if mine:
                rows = [mine] + rows[: max(0, SIDEBAR_USER_CARD_LIMIT - 1)]
    rows = rows[:SIDEBAR_USER_CARD_LIMIT]
    if masked:
        # 游客：只给脱敏用户名，不给任何时间信息、不给状态
        return {
            "scope": "masked",
            "total": len(rows),
            "items": [
                {
                    "name": mask_username(row.get("nickname") or row.get("username")),
                    "masked": True,
                }
                for row in rows
            ],
        }
    items = []
    last_views = sidebar_last_views([row["id"] for row in rows])
    for row in rows:
        user_id = int(row["id"])
        last_view = last_views.get(user_id, "")
        is_self = bool(viewer_id) and user_id == int(viewer_id)
        item = {
            "id": user_id,
            "name": str(row.get("nickname") or row.get("username") or "普通用户"),
            # 隐身只给本人和管理员看：普通账号、访客看到的一律是「离线」
            "presence": member_status(
                user_id, last_view, is_self or viewer_is_admin
            ),
            "self": is_self,
        }
        if viewer_is_admin:
            # 「注册 N 天 · X 前活跃」只有管理员看得到
            item["registered_days"] = days_since(row.get("created_at"))
            item["last_login_at"] = str(row.get("last_login_at") or "")
            item["last_view_at"] = last_view
        items.append(item)
    return {"scope": "all", "total": len(items), "items": items}


# ---------- 侧栏卡片上的展示状态 ----------

# 「在线 / 在线-<设备> / 离线」都由活跃时间自动判定，只有「隐身」是手动记下来的
USER_STATUS_MODES = ("auto", "invisible")
# 本人手选的设备后缀（只列出当前设备那一个）；空字符串 = 只显示「在线」
USER_STATUS_SUFFIXES = ("", "Win", "Mac", "Linux", "Android", "iOS")
_USER_STATUS_SUFFIX_LOOKUP = {value.lower(): value for value in USER_STATUS_SUFFIXES if value}


def normalize_status_suffix(value):
    """把前端传来的设备后缀归一到标准写法（大小写不敏感，认不出就当没选）。"""
    return _USER_STATUS_SUFFIX_LOOKUP.get(str(value or "").strip().lower(), "")


def device_suffix(hint="", user_agent=""):
    """把浏览器上报的平台 / UA 映射成状态后缀：Win / Mac / Linux / Android / iOS。

    先看 Sec-CH-UA-Platform，没有再退回 UA；每一份来源里都先判 Windows 与 iOS / Android
    再判 Mac / Linux —— 安卓的 UA 里带 linux、iOS 的 UA 里带 mac os x，顺序错了会认错。
    """
    for source in (str(hint or "").lower(), str(user_agent or "").lower()):
        if not source:
            continue
        if "windows" in source:
            return "Win"
        if any(token in source for token in ("iphone", "ipad", "ipod", "ios")):
            return "iOS"
        if "android" in source:
            return "Android"
        if "mac" in source or "darwin" in source:
            return "Mac"
        if "linux" in source or "x11" in source:
            return "Linux"
    return ""
# 站长自定义文案最多几个字（只有站长能用）
USER_STATUS_MAX_LEN = 12
# 多久之内有过一次真实页面访问就算「在线」
ONLINE_WINDOW_MINUTES = 10
# 左下「注册账户」卡片最多显示几行
SIDEBAR_USER_CARD_LIMIT = 5


def user_status_row(user_id):
    """读某个账号自己选的状态（没有就返回默认的「自动」）。"""
    row = query_one(
        "SELECT mode, suffix, text, updated_at FROM user_status WHERE user_id = ?",
        (int(user_id or 0),),
    )
    mode = str((row or {}).get("mode") or "auto")
    return {
        "mode": mode if mode in USER_STATUS_MODES else "auto",
        "suffix": normalize_status_suffix((row or {}).get("suffix")),
        "text": str((row or {}).get("text") or "")[:USER_STATUS_MAX_LEN],
        "updated_at": str((row or {}).get("updated_at") or ""),
    }


def user_status_save(user_id, mode, suffix, text=None):
    """写某个账号的状态；`text` 传 None 表示这一栏不动（普通账号只能改 mode / suffix）。"""
    entry = user_status_row(user_id)
    mode = str(mode or "").strip().lower()
    mode = mode if mode in USER_STATUS_MODES else "auto"
    suffix = normalize_status_suffix(suffix)
    if text is not None:
        entry["text"] = str(text or "").strip()[:USER_STATUS_MAX_LEN]
    execute(
        """INSERT INTO user_status (user_id, mode, suffix, text, updated_at)
               VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               mode = excluded.mode,
               suffix = excluded.suffix,
               text = excluded.text,
               updated_at = excluded.updated_at""",
        (int(user_id or 0), mode, suffix, entry["text"], now_text()),
    )
    return user_status_row(user_id)


def presence_payload(entry, online, last_active):
    """把「自己选的状态 + 是否最近活跃」拼成前端直接画的状态对象。

    「隐身」只在人还在活跃窗口内时才成立 —— 到点没操作就是真的离线了，直接显示「离线」，
    不会一直挂着隐身。显示优先级：离线 > 隐身（在线时）> 站长自定义文案 > 在线[-设备名]。
    自定义文案在的时候，圆点仍然表示真实的在线 / 离线。
    """
    if not online:
        tone, label = "offline", "离线"
    elif entry["mode"] == "invisible":
        tone, label = "invisible", "隐身"
    elif entry["text"]:
        tone = "online"
        label = entry["text"]
    else:
        tone = "online"
        # 有设备后缀时胶囊里只显示设备名（Win / Mac / Linux / Android / iOS），仍然是绿色的「在线」
        label = entry["suffix"] or "在线"
    return {
        "tone": tone,
        "label": label,
        "mode": entry["mode"],
        "suffix": entry["suffix"],
        "text": entry["text"],
        "online": bool(online),
        "last_active_at": str(last_active or ""),
        "updated_at": entry["updated_at"],
    }


def presence_for_viewer(presence, revealed):
    """隐身只给「本人」和「管理员」看：普通账号与访客看到的一律是灰色的「离线」。

    不可见时把 mode / suffix / text 一起抹掉，免得接口里还能翻出「他其实在隐身」。
    """
    if revealed or presence.get("mode") != "invisible":
        return presence
    masked = dict(presence)
    masked.update({"tone": "offline", "label": "离线", "mode": "auto", "suffix": "", "text": ""})
    return masked


def reset_status_on_login(user_id):
    """重新登录之后状态回到默认：清掉「隐身」和手选的设备后缀（站长自定义文案保留）。"""
    entry = user_status_row(user_id)
    user_status_save(user_id, "auto", "", entry["text"])


def owner_last_active():
    """站长最近一次真实页面访问（走 idx_access_log_actor）。"""
    row = query_one(
        """SELECT created_at FROM access_log
           WHERE actor_kind = 'owner'
           ORDER BY created_at DESC LIMIT 1"""
    )
    return str((row or {}).get("created_at") or "")


def owner_status():
    """右上「Error酱」卡片的状态（站长本人视角）。"""
    return owner_status_for(True)


def owner_status_for(revealed):
    """右上「Error酱」卡片的状态；`revealed` = 看的人能不能看到隐身的真实状态。"""
    last_active = owner_last_active()
    entry = user_status_row(0)
    return presence_for_viewer(
        presence_payload(
            entry, is_recent_time(last_active, ONLINE_WINDOW_MINUTES * 60), last_active
        ),
        revealed,
    )


def member_status(user_id, last_view="", revealed=True):
    """某个注册账号的状态（`last_view` 由调用方批量查好后传进来）。"""
    entry = user_status_row(user_id)
    return presence_for_viewer(
        presence_payload(
            entry, is_recent_time(last_view, ONLINE_WINDOW_MINUTES * 60), last_view
        ),
        revealed,
    )


def member_last_view(user_id):
    """单个注册账号最近一次真实页面访问（走 idx_access_log_user）。"""
    row = query_one(
        """SELECT created_at FROM access_log
           WHERE user_id = ?
           ORDER BY created_at DESC LIMIT 1""",
        (int(user_id or 0),),
    )
    return str((row or {}).get("created_at") or "")


def sidebar_last_views(user_ids):
    """每个账号最近一次真实页面访问（`access_log`），一次查回这几个账号的新时间。

    `users.last_login_at` 只在**真的输密码登录**那一刻写，靠记住的会话继续浏览不会更新，
    所以长期挂着的账号会一直显示成「很多天前登录」。侧栏卡片要回答的是「这个人最近来过吗」，
    所以另外取 `access_log` 里每个账号最新的一条页面访问；访问日志没开或已被清理时返回空，
    前端会自动退回原来的「…前登录」。
    """
    ids = sorted({int(value) for value in user_ids if int(value or 0) > 0})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = query(
        f"""SELECT user_id, MAX(created_at) AS at FROM access_log
            WHERE user_id IN ({placeholders})
            GROUP BY user_id""",
        tuple(ids),
    )
    return {int(row["user_id"]): str(row.get("at") or "") for row in rows}


def sidebar_activities():
    """右下更新日志卡片：只要管理员的上传 / 发布类更新，最新的若干条。

    目标内容已经被删掉的条目直接不显示（站长要求「删了就是删了」），
    所以这里按「目标还查得到名称」过滤，并继续往下取到够 11 条为止。
    """
    actions = tuple(SIDEBAR_ACTIVITY_HREFS)
    placeholders = ",".join("?" for _ in actions)
    rows = query(
        f"""SELECT a.id, a.action, a.actor_kind, a.created_at, a.target_type, a.target_id
            FROM activity_log a
            WHERE a.action IN ({placeholders})
            ORDER BY a.id DESC
            LIMIT ?""",
        (*actions, SIDEBAR_ACTIVITY_SCAN),
    )
    # 只留管理员的动作，并且目标还在（下面的名称解析会告诉我们哪个目标已经不在了）
    candidates = [
        row
        for row in rows
        if str(row.get("actor_kind") or "guest") in ("owner", "admin")
    ]
    ids_by_type = {}
    for row in candidates:
        target_type = str(row.get("target_type") or "")
        target_id = int(row.get("target_id") or 0)
        if target_type and target_id:
            ids_by_type.setdefault(target_type, set()).add(target_id)
    names = sidebar_target_names(ids_by_type)

    items = []
    for row in candidates:
        action = str(row.get("action") or "")
        label, target_type = SIDEBAR_ACTIVITY_META.get(action, ("更新", ""))
        target_id = int(row.get("target_id") or 0)
        hit = names.get((target_type, target_id)) or {}
        target = str(hit.get("name") or "")
        # 内容已被删除的条目整条不显示，让位给更早的那些
        if not target:
            continue
        # 推荐的两类共用一条动作，靠目标自己的 kind 决定落在「网页」还是「站内」栏
        tab = SIDEBAR_ACTIVITY_TABS.get(action, "")
        if action == "recommendation_create":
            tab = "resource" if str(hit.get("kind") or "") == "resource" else "web"
        base = SIDEBAR_ACTIVITY_HREFS.get(action, "")
        # 歌曲 / 书籍 / 网页 / 站内资源只活在推荐页里（没有独立入口），日志的地址统一
        # 指回推荐页对应的那一栏，不再指向 /music、/books 这些独立子页
        if tab:
            base = f"/downloads?tab={tab}"
        focus_param = SIDEBAR_FOCUS_PARAM.get(action, "focus")
        url = base
        if base:
            separator = "&" if "?" in base else "?"
            url = f"{base}{separator}{focus_param}={target_id}"
        items.append(
            {
                "id": int(row["id"]),
                "action": action,
                "created_at": str(row.get("created_at") or ""),
                "label": label,
                "target": target,
                "href": base,
                "url": url,
                "tab": tab,
                "target_id": target_id,
            }
        )
        if len(items) >= SIDEBAR_ACTIVITY_LIMIT:
            break
    return items


def sidebar_target_names(ids_by_type):
    """按 (目标类型, 目标 id) 批量取名称：歌曲 / 书名、动态正文片段、足迹名称、推荐标题。

    返回 {(type, id): {"name": 名称, "kind": 推荐内容属于哪一栏（web / resource）}}。
    """
    getters = {
        "music": ("site_music", "title", ""),
        "book": ("books", "title", ""),
        "recommendation": ("recommendations", "title", "kind"),
        "map_place": ("map_places", "name", ""),
        "moment": ("moments", "content", ""),
    }
    found = {}
    for target_type, ids in ids_by_type.items():
        source = getters.get(target_type)
        if not source or not ids:
            continue
        table, column, extra = source
        id_list = sorted(ids)
        placeholders = ",".join("?" for _ in id_list)
        selected = f"id, {column} AS value" + (f", {extra} AS extra" if extra else "")
        for row in query(
            f"SELECT {selected} FROM {table} WHERE id IN ({placeholders})",
            tuple(id_list),
        ):
            value = " ".join(str(row.get("value") or "").split())
            if target_type == "moment":
                # 动态正文只取前一小段，够认出来就行
                value = value[:SIDEBAR_MOMENT_SNIPPET]
            kind = str(row.get("extra") or "") if extra else ""
            found[(target_type, int(row["id"]))] = {"name": value, "kind": kind}
    return found


def amap_ip_region(text):
    """高德 IP 定位；未配置 Key 或没返回省份时返回空串。"""
    if not AMAP_WEB_KEY:
        return ""
    try:
        request = Request(
            "https://restapi.amap.com/v3/ip?"
            + urlencode({"key": AMAP_WEB_KEY, "ip": text}),
            headers={"User-Agent": "ErrorJiang/1.0"},
        )
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8", "replace") or "{}")
    except (URLError, socket.timeout, OSError, json.JSONDecodeError):
        return ""
    if str(payload.get("status")) == "1":
        return normalize_region(payload.get("province"))
    return ""


def pconline_ip_region(text):
    """高德对部分运营商 IP 返回空省份，再用太平洋电脑网的库兜底。"""
    try:
        request = Request(
            "https://whois.pconline.com.cn/ipJson.jsp?"
            + urlencode({"ip": text, "json": "true"}),
            headers={
                "User-Agent": "ErrorJiang/1.0",
                "Referer": "https://whois.pconline.com.cn/",
            },
        )
        with urlopen(request, timeout=3) as response:
            raw = response.read()
    except (URLError, socket.timeout, OSError):
        return ""
    payload = {}
    for encoding in ("utf-8", "gbk"):
        try:
            payload = json.loads(raw.decode(encoding).strip() or "{}")
            break
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
    if not isinstance(payload, dict):
        return ""
    return normalize_region(payload.get("pro") or payload.get("province") or "")


def ipwhois_ip_region(text):
    """海外 IP 兜底：返回中文国家 / 地区；中国 IP 尽量返回省级。"""
    try:
        request = Request(
            "https://ipwho.is/"
            + quote(text, safe="")
            + "?"
            + urlencode({"lang": "zh-CN"}),
            headers={"User-Agent": "ErrorJiang/1.0"},
        )
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8", "replace") or "{}")
    except (URLError, socket.timeout, OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return ""
    country = normalize_region(payload.get("country"))
    if country in ("中国", "中國"):
        return normalize_region(payload.get("region")) or country
    return country


def lookup_ip_region(address):
    """把公网 IP 解析到省级或国家 / 地区；解析失败时返回空串。"""
    text = str(address or "").strip()
    if is_private_ip(text):
        return ""
    now = time.time()
    with IP_REGION_CACHE_LOCK:
        cached = IP_REGION_CACHE.get(text)
        if cached:
            ttl = IP_REGION_CACHE_TTL if cached[1] else IP_REGION_CACHE_FAIL_TTL
            if now - cached[0] < ttl:
                return cached[1]
    region = amap_ip_region(text) or pconline_ip_region(text) or ipwhois_ip_region(text)
    with IP_REGION_CACHE_LOCK:
        if len(IP_REGION_CACHE) >= IP_REGION_CACHE_LIMIT:
            IP_REGION_CACHE.clear()
        IP_REGION_CACHE[text] = (now, region)
    return region


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


def role_permission_set(role):
    rows = query("SELECT permission FROM role_permissions WHERE role = ?", (role,))
    return {row["permission"] for row in rows}


GUEST_PERMISSION_CACHE = {"at": 0.0, "value": None}


def guest_permission_set():
    """游客角色权限；2 秒缓存，避免每个请求都查库。"""
    now = time.time()
    cached = GUEST_PERMISSION_CACHE
    if cached["value"] is not None and now - cached["at"] < 2:
        return set(cached["value"])
    value = role_permission_set(ROLE_GUEST)
    cached["at"] = now
    cached["value"] = value
    return set(value)


def guest_has_permission(permission):
    return permission in guest_permission_set()


def invalidate_guest_permission_cache():
    GUEST_PERMISSION_CACHE["at"] = 0.0
    GUEST_PERMISSION_CACHE["value"] = None


def user_permission_overrides(user_id):
    if not user_id:
        return {}
    rows = query("SELECT permission, mode FROM user_permissions WHERE user_id = ?", (user_id,))
    return {row["permission"]: (row["mode"] or "allow") for row in rows}


def user_permission_set(user_id):
    """账号有效权限 = 普通账户角色默认 + 单账户允许 - 单账户禁止。"""
    if not user_id:
        return set()
    permissions = role_permission_set(ROLE_MEMBER)
    for permission, mode in user_permission_overrides(user_id).items():
        if mode == "deny":
            permissions.discard(permission)
        else:
            permissions.add(permission)
    return permissions


def user_has_permission(user_id, permission):
    if not user_id:
        return False
    overrides = user_permission_overrides(user_id)
    if permission == ADMIN_PERMISSION:
        return overrides.get(ADMIN_PERMISSION) == "allow"
    if overrides.get(ADMIN_PERMISSION) == "allow":
        return True
    permissions = role_permission_set(ROLE_MEMBER)
    for key, mode in overrides.items():
        if mode == "deny":
            permissions.discard(key)
        else:
            permissions.add(key)
    return permission in permissions


def required_permission(path, method):
    """把请求映射到权限点；返回 None 表示仍按"仅管理员"处理。"""
    if path == "/workbench" or path.startswith("/workbench/"):
        return None
    if path == "/agent" or path.startswith("/api/agent/web"):
        return None
    if path.startswith("/agent-stickers/"):
        return None
    if path.startswith("/api/workbench") or path.startswith("/api/prompts"):
        return None
    # 计算器是独立的授权模块：一个权限点同时控制页面和全部业务接口，
    # 默认不进入普通账号角色，只能在「工作台 → 账号权限」里按账号授予。
    if path in ("/aa", "/finance") or path == "/api/aa" or path.startswith("/api/aa/"):
        return AA_PERMISSION
    if path == "/api/account/nickname":
        return ""
    if path == "/api/site/messages/quota" and method == "GET":
        return ""
    if path == "/api/site/reports" and method == "POST":
        return ""
    if path == "/api/site/reports" and method == "GET":
        return ""
    if path == "/api/references":
        return "" if method == "GET" else None
    if re.fullmatch(r"/api/references/\d+", path):
        return None
    if path == "/api/map/seen" and method == "POST":
        # 记录「已看到标记」是读状态，任何登录账号都可以
        return ""
    if path == "/api/site/user-status" and method == "POST":
        # 设置自己的展示状态：任何登录账号都可以（处理器里再判身份，游客 401）
        return ""
    # 公开站点模块：游客能否访问由游客角色权限控制；登录账号一律可以浏览
    if path in SITE_MEMBER_PAGES:
        return ""
    if path == "/api/site/messages" or path.startswith("/api/site/messages/"):
        # 留言：游客只能浏览；登录账号可以发表留言。
        # 删除先放行到处理器，那里再判「管理员可删任意 / 普通账号只能删自己的」。
        if method == "POST":
            return ""
        return ""
    if path.startswith("/api/site/message-files/"):
        # 附件接口：游客只能看图片，非图片附件在处理器里再拦一次
        return ""
    if path == "/api/site/likes" and method == "POST":
        # 点赞：登录账号可用，处理器里再校验身份
        return ""
    if path == "/api/site/notifications/seen" and method == "POST":
        return ""
    if path == "/api/site/notifications/unread" and method == "GET":
        return ""
    if path == "/api/site/notifications/summary" and method == "GET":
        return ""
    if path == "/api/site/moments/unread" and method == "GET":
        return ""
    if re.fullmatch(r"/api/moments/\d+/comments", path) and method == "POST":
        # 动态评论：登录账号可用，发布动态本身仍仅管理员
        return ""
    if re.fullmatch(r"/api/site/moment-comments/\d+", path) and method == "DELETE":
        return ""
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
    if path == "/api/site/photos" or path.startswith("/api/site/photos/"):
        return "photos:write" if method in ("POST", "PATCH", "DELETE") else ""
    if path == "/api/site/links" or path.startswith("/api/site/links/"):
        return "links:write" if method in ("POST", "PATCH", "DELETE") else ""
    if re.fullmatch(r"/api/site/music/\d+/(stream|download)", path):
        return ""
    if path == "/api/site/music" or path.startswith("/api/site/music/"):
        return "music:write" if method in ("POST", "PATCH", "DELETE") else ""
    if path == "/api/books" or path.startswith("/api/books/"):
        # 书架：游客和普通账号只能看；上传、编辑、删除仅管理员。
        if re.fullmatch(r"/api/books/\d+/download", path):
            return ""
        if path == "/api/books/upload" or re.fullmatch(r"/api/books/\d+", path):
            return "books:write"
        if path == "/api/books" and method == "GET":
            return ""
        return None
    if path == "/notes/read":
        # 站内分享的笔记：登录账号都能读，处理器里再校验是否真的被分享
        return ""
    if re.fullmatch(r"/api/shared/notes/\d+", path):
        return ""
    if path.startswith("/api/admin"):
        return None
    if path.startswith("/api/map/categories"):
        if not MAP_PUBLIC:
            return None
        return "map:manage_categories"
    if path.startswith("/api/map/import"):
        # 导入标记仅管理员可用（不再作为可授予权限点）
        return None
    if path.startswith("/api/map"):
        if not MAP_PUBLIC:
            return None
        if method in ("POST", "PATCH", "DELETE"):
            return "map:write"
        return ("map:write", "map:write_all", "map:manage_categories")
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


MAP_VIEW_PERMISSIONS = (
    "map:write",
    "map:write_all",
    "map:manage_categories",
)
# 私有模块数据目录：登录账号需要对应权限
DATA_PERMISSION_RULES = (
    ("note_images/", ("notes:view", "notes:write")),
    ("part_images/", ("inventory:view", "inventory:write")),
    ("bom_reports/", ("inventory:view", "inventory:write")),
    ("aa_qr/", (AA_PERMISSION,)),
)
# 游客可见模块的接口 / 子路径前缀
GUEST_RULE_PREFIXES = (
    ("/api/site/messages/", "guest:page:messages"),
    ("/api/moments/", "guest:page:moments"),
    ("/api/recommendations/", "guest:page:recommendations"),
    ("/api/site/music/", "guest:page:music"),
)


def guest_page_permission_for_path(path):
    """返回路径对应的游客页面权限点；None 表示不受游客角色控制。"""
    if path in GUEST_PAGE_RULES:
        return GUEST_PAGE_RULES[path]
    if path in GUEST_API_RULES:
        return GUEST_API_RULES[path]
    if path.startswith("/api/site/message-files/"):
        return "guest:page:messages"
    for prefix, rule in GUEST_RULE_PREFIXES:
        if path.startswith(prefix):
            return rule
    return None


AA_EVENT_TITLE_MAX_CHARS = 80
AA_EVENT_MEMBER_MAX = 30
AA_EXPENSE_NOTE_MAX_CHARS = 120
AA_EXPENSE_MAX_CENTS = 100_000_000
AA_QR_MAX_BYTES = 5 * 1024 * 1024


def aa_amount_cents(value):
    """把前端提交的整分金额校验成整数；不接收带小数的浮点值。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return None
    if cents <= 0 or cents > AA_EXPENSE_MAX_CENTS:
        return None
    return cents


def aa_settlement(members, expenses):
    """
    每笔费用只在它选择的分摊成员之间平均分，并把除不尽的 1 分依次分给
    活动成员顺序靠前的分摊人。
    返回每个成员的应付 / 已付 / 净额，以及尽量少的转账组合。
    """
    member_rows = [dict(item) for item in members]
    if not member_rows:
        return {"total_cents": 0, "members": [], "transfers": []}
    member_order = {
        int(item["user_id"]): index for index, item in enumerate(member_rows)
    }
    paid_by_user = {int(item["user_id"]): 0 for item in member_rows}
    share_by_user = {int(item["user_id"]): 0 for item in member_rows}
    total_cents = 0
    for expense in expenses:
        user_id = int(expense.get("user_id") or 0)
        amount = int(expense.get("amount_cents") or 0)
        if user_id in paid_by_user and amount > 0:
            paid_by_user[user_id] += amount
            total_cents += amount
            split_ids = expense.get("split_user_ids")
            if not split_ids:
                split_ids = list(member_order)
            split_ids = sorted(
                {
                    int(split_id)
                    for split_id in split_ids
                    if int(split_id) in member_order
                },
                key=lambda split_id: member_order[split_id],
            )
            if not split_ids:
                split_ids = list(member_order)
            base_share, remainder = divmod(amount, len(split_ids))
            for index, split_id in enumerate(split_ids):
                share_by_user[split_id] += base_share + (
                    1 if index < remainder else 0
                )
    balances = []
    for member in member_rows:
        user_id = int(member["user_id"])
        share_cents = share_by_user[user_id]
        paid_cents = paid_by_user[user_id]
        item = dict(member)
        item.update(
            {
                "paid_cents": paid_cents,
                "share_cents": share_cents,
                "balance_cents": paid_cents - share_cents,
            }
        )
        balances.append(item)

    debtors = [
        {"user_id": item["user_id"], "name": item["name"], "cents": -item["balance_cents"]}
        for item in balances
        if item["balance_cents"] < 0
    ]
    creditors = [
        {"user_id": item["user_id"], "name": item["name"], "cents": item["balance_cents"]}
        for item in balances
        if item["balance_cents"] > 0
    ]
    debtors.sort(key=lambda item: (-item["cents"], int(item["user_id"])))
    creditors.sort(key=lambda item: (-item["cents"], int(item["user_id"])))
    transfers = []
    debtor_index = 0
    creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor = debtors[debtor_index]
        creditor = creditors[creditor_index]
        amount = min(debtor["cents"], creditor["cents"])
        if amount > 0:
            transfers.append(
                {
                    "from_user_id": debtor["user_id"],
                    "from_name": debtor["name"],
                    "to_user_id": creditor["user_id"],
                    "to_name": creditor["name"],
                    "amount_cents": amount,
                }
            )
        debtor["cents"] -= amount
        creditor["cents"] -= amount
        if debtor["cents"] <= 0:
            debtor_index += 1
        if creditor["cents"] <= 0:
            creditor_index += 1
    return {
        "total_cents": total_cents,
        "members": balances,
        "transfers": transfers,
    }


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


# ---------- 站点日志（内容事件 / 页面访问） ----------

def describe_user_agent(user_agent):
    """把 User-Agent 压成「设备 · 浏览器」的短标签。"""
    text = str(user_agent or "").lower()
    if not text:
        return ""
    if "ipad" in text or ("tablet" in text and "mobile" not in text):
        device = "平板"
    elif (
        "iphone" in text
        or "ipod" in text
        or "windows phone" in text
        or "mobile" in text
        or ("android" in text and "mobile" in text)
    ):
        device = "手机"
    else:
        device = "桌面"
    if "micromessenger" in text:
        browser = "微信"
    elif "edg" in text or "edga" in text or "edgios" in text:
        browser = "Edge"
    elif "firefox" in text or "fxios" in text:
        browser = "Firefox"
    elif "chrome" in text or "crios" in text:
        browser = "Chrome"
    elif "safari" in text:
        browser = "Safari"
    else:
        browser = "其他"
    return f"{device} · {browser}"


def device_info_label(user_agent):
    """
    留言 / 动态卡片上展示的「设备信息」自动识别结果：只认系统，不认浏览器。
    判断顺序有讲究：
      鸿蒙（OpenHarmony / HarmonyOS，鸿蒙 4.x 及以下的 UA 同时带 Android，必须先判；卡片上写「鸿蒙」）→
      Android（它的 UA 里同时带 Linux）→ iOS（iPhone / iPad / iPod）→
      iPadOS 13+ 的新 UA 会把自己报成 Macintosh，靠同一个 UA 里的 Mobile 认出来（先于 macOS）→
      ChromeOS（带 CrOS）→ Windows → macOS → Linux →
      认不出来（含空 UA）就记「来自 Web」。
    """
    text = str(user_agent or "")
    if re.search(r"OpenHarmony|HarmonyOS", text, re.I):
        return "来自 鸿蒙"
    if re.search(r"Android", text, re.I):
        return "来自 Android"
    if re.search(r"iPhone|iPad|iPod", text, re.I):
        return "来自 iOS"
    if re.search(r"Macintosh", text, re.I) and re.search(r"Mobile", text, re.I):
        return "来自 iOS"
    if re.search(r"CrOS", text):
        return "来自 ChromeOS"
    if re.search(r"Windows", text, re.I):
        return "来自 Windows"
    if re.search(r"Macintosh|Mac OS X", text, re.I):
        return "来自 macOS"
    if re.search(r"Linux", text, re.I):
        return "来自 Linux"
    return "来自 Web"


def normalize_device_info(value):
    """
    管理员自定义的设备名称：压掉换行与多余空格、限长，并补上「来自 」前缀，
    保证和自动识别出来的文案是同一个形状。空值返回空串（表示退回自动识别）。
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()[:DEVICE_INFO_MAX_CHARS]
    if not text:
        return ""
    if not text.startswith("来自"):
        text = "来自 " + text
    return text[:DEVICE_INFO_MAX_CHARS]


def write_activity(
    actor,
    action,
    summary="",
    target_type="",
    target_id=None,
    ip="",
    ip_region="",
    source_path="",
    method="",
    source_port=None,
    target_host="",
    target_port=None,
    user_agent="",
    client_platform="",
):
    """写入一条内容事件日志；失败只提示，不影响主流程。"""
    actor = actor or {}
    try:
        execute(
            """INSERT INTO activity_log
                   (created_at, actor_kind, user_id, actor_name, action,
                    target_type, target_id, summary, ip, ip_region, source_path,
                    method, source_port, target_host, target_port, user_agent,
                    client_platform)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now_text(),
                actor.get("kind") or "guest",
                int(actor.get("user_id") or 0),
                str(actor.get("nickname") or actor.get("username") or "")[:80],
                str(action or "")[:80],
                str(target_type or "")[:40] or None,
                int(target_id) if target_id not in (None, "") else None,
                str(summary or "")[:500],
                str(ip or "")[:80],
                str(ip_region or "")[:40],
                str(source_path or "")[:200],
                str(method or "")[:12],
                int(source_port) if source_port not in (None, "") else None,
                str(target_host or "")[:200],
                int(target_port) if target_port not in (None, "") else None,
                str(user_agent or "")[:300],
                str(client_platform or "")[:120],
            ),
        )
    except Exception as exc:
        print(f"[activity] 写入失败: {exc}", file=sys.stderr)


def enqueue_access_log(
    path,
    ip,
    status=200,
    actor_kind="guest",
    user_id=0,
    actor_name="",
    referer="",
    user_agent="",
    method="GET",
    source_port=None,
    target_host="",
    target_port=None,
    client_platform="",
):
    """把页面访问丢进队列，由后台线程落库并补齐属地。"""
    try:
        ACCESS_LOG_QUEUE.put_nowait(
            {
                "created_at": now_text(),
                "path": str(path or "")[:300],
                "status": int(status or 200),
                "actor_kind": str(actor_kind or "guest")[:20],
                "ip": str(ip or "")[:80],
                "user_id": int(user_id or 0),
                "actor_name": str(actor_name or "")[:80],
                "referer": str(referer or "")[:300],
                "user_agent": str(user_agent or "")[:300],
                "device": describe_user_agent(user_agent),
                "method": str(method or "GET")[:12],
                "source_port": int(source_port) if source_port not in (None, "") else None,
                "target_host": str(target_host or "")[:200],
                "target_port": int(target_port) if target_port not in (None, "") else None,
                "client_platform": str(client_platform or "")[:120],
            }
        )
    except queue.Full:
        pass
    except Exception as exc:
        print(f"[access] 入队失败: {exc}", file=sys.stderr)


def access_log_worker():
    while True:
        item = ACCESS_LOG_QUEUE.get()
        try:
            ip = item.get("ip") or ""
            region = lookup_ip_region(ip) if ip else ""
            execute(
                """INSERT INTO access_log
                       (created_at, actor_kind, ip, ip_region, path, status, user_id,
                        actor_name, referer, user_agent, device, method, source_port,
                        target_host, target_port, client_platform)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["created_at"],
                    item["actor_kind"],
                    ip,
                    region,
                    item["path"],
                    item["status"],
                    item["user_id"],
                    item["actor_name"],
                    item["referer"],
                    item["user_agent"],
                    item["device"],
                    item["method"],
                    item["source_port"],
                    item["target_host"],
                    item["target_port"],
                    item["client_platform"],
                ),
            )
        except Exception as exc:
            print(f"[access] 写入失败: {exc}", file=sys.stderr)
        finally:
            ACCESS_LOG_QUEUE.task_done()


def start_access_log_worker():
    thread = threading.Thread(target=access_log_worker, name="access-log-worker", daemon=True)
    thread.start()
    return thread


def cleanup_logs():
    """删除超过保留期的内容事件与访问明细，返回删除条数。"""
    cutoff = (datetime.now() - timedelta(days=LOG_RETENTION_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    removed = 0
    for table in ("activity_log", "access_log"):
        row = query_one(f"SELECT COUNT(*) AS n FROM {table} WHERE created_at < ?", (cutoff,))
        removed += int((row or {}).get("n") or 0)
        execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
    return removed


def logs_maintenance_loop():
    while True:
        try:
            purge_expired_sessions()
            removed = cleanup_logs()
            if removed:
                print(
                    f"已清理 {removed} 条超过 {LOG_RETENTION_DAYS} 天的日志明细。",
                    flush=True,
                )
        except Exception as exc:
            print(f"[logs] 清理失败: {exc}", file=sys.stderr)
        time.sleep(LOG_CLEANUP_INTERVAL_SECONDS)


def report_reminder_loop():
    """对超过 24 小时未处理的举报补发一次 Webhook 提醒。"""
    while True:
        try:
            cutoff = (
                datetime.now() - timedelta(hours=REPORT_SLA_HOURS)
            ).strftime("%Y-%m-%d %H:%M:%S")
            rows = query(
                """SELECT id, target_title FROM content_reports
                   WHERE status = 'pending' AND reminded_at IS NULL
                     AND created_at <= ?
                   ORDER BY id LIMIT 50""",
                (cutoff,),
            )
            for row in rows:
                notify_async(
                    "report",
                    "Error酱：举报处理已超过 24 小时",
                    f"举报 #{row['id']}「{row.get('target_title') or ''}」仍未处理，"
                    "请到工作台「举报处理」完成核实。",
                    "/workbench?view=reports",
                )
                execute(
                    "UPDATE content_reports SET reminded_at = ? WHERE id = ? AND reminded_at IS NULL",
                    (now_text(), row["id"]),
                )
        except Exception as exc:
            print(f"[reports] 超时提醒失败: {exc}", file=sys.stderr)
        time.sleep(REPORT_REMINDER_INTERVAL_SECONDS)


# ---------- 站长通知（Webhook 推送） ----------

def app_meta_get(key, default=""):
    row = query_one("SELECT value FROM app_meta WHERE key = ?", (key,))
    return row["value"] if row else default


def app_meta_set(key, value):
    execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, str(value))
    )


UPLOAD_LIMIT_META_KEY = "upload_limits_v1"


def upload_limit_defaults():
    defaults = {}
    for item in UPLOAD_LIMIT_SCHEMA:
        limits = {
            "max_count": int(item.get("max_count") or 1),
            "max_file_bytes": int(item["max_file_bytes"]),
        }
        if item.get("total"):
            limits["max_total_bytes"] = int(item.get("max_total_bytes") or 0)
        defaults[item["key"]] = limits
    return defaults


def upload_limits():
    limits = upload_limit_defaults()
    raw = app_meta_get(UPLOAD_LIMIT_META_KEY, "")
    if not raw:
        return limits
    try:
        saved = json.loads(raw)
    except json.JSONDecodeError:
        return limits
    if not isinstance(saved, dict):
        return limits
    for item in UPLOAD_LIMIT_SCHEMA:
        key = item["key"]
        current = limits[key]
        value = saved.get(key)
        if not isinstance(value, dict):
            continue
        try:
            current["max_file_bytes"] = max(
                1024,
                min(
                    UPLOAD_LIMIT_HARD_MAX_BYTES,
                    int(value.get("max_file_bytes") or current["max_file_bytes"]),
                ),
            )
            current["max_count"] = max(
                1,
                min(
                    UPLOAD_LIMIT_HARD_MAX_COUNT,
                    int(value.get("max_count") or current["max_count"]),
                ),
            )
            if item.get("total"):
                current["max_total_bytes"] = max(
                    current["max_file_bytes"],
                    min(
                        UPLOAD_LIMIT_HARD_MAX_BYTES,
                        int(
                            value.get("max_total_bytes")
                            or current.get("max_total_bytes")
                            or current["max_file_bytes"]
                        ),
                    ),
                )
        except (TypeError, ValueError):
            continue
    return limits


def upload_limit(key):
    return upload_limits().get(key) or upload_limit_defaults()[key]


def format_upload_limit_bytes(value):
    """把字节上限转成便于提示的文案，兼容不足 1MB 的小限制。"""
    size = max(0, int(value or 0))
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))}KB"
    megabytes = size / (1024 * 1024)
    if abs(megabytes - round(megabytes)) < 0.05:
        return f"{int(round(megabytes))}MB"
    return f"{megabytes:.1f}MB"


def normalize_upload_limit_payload(payload):
    raw_limits = payload.get("limits") if isinstance(payload, dict) else None
    if not isinstance(raw_limits, dict):
        raise ValueError("上传限制格式不正确。")
    normalized = {}
    for item in UPLOAD_LIMIT_SCHEMA:
        key = item["key"]
        current = upload_limit_defaults()[key]
        value = raw_limits.get(key)
        if not isinstance(value, dict):
            value = {}
        try:
            file_bytes = int(value.get("max_file_bytes") or current["max_file_bytes"])
            count = int(value.get("max_count") or current["max_count"])
        except (TypeError, ValueError):
            raise ValueError(f"{item['label']}的大小或数量不是整数。")
        if not 1024 <= file_bytes <= UPLOAD_LIMIT_HARD_MAX_BYTES:
            raise ValueError(
                f"{item['label']}单个文件必须在 1KB 到 "
                f"{UPLOAD_LIMIT_HARD_MAX_BYTES // (1024 * 1024)}MB 之间。"
            )
        if not 1 <= count <= UPLOAD_LIMIT_HARD_MAX_COUNT:
            raise ValueError(
                f"{item['label']}数量必须在 1 到 {UPLOAD_LIMIT_HARD_MAX_COUNT} 之间。"
            )
        normalized[key] = {
            "max_count": count,
            "max_file_bytes": file_bytes,
        }
        if item.get("total"):
            try:
                total_bytes = int(
                    value.get("max_total_bytes")
                    or current.get("max_total_bytes")
                    or file_bytes
                )
            except (TypeError, ValueError):
                raise ValueError(f"{item['label']}合计大小不是整数。")
            if not file_bytes <= total_bytes <= UPLOAD_LIMIT_HARD_MAX_BYTES:
                raise ValueError(
                    f"{item['label']}合计大小需不小于单个文件，且不超过 "
                    f"{UPLOAD_LIMIT_HARD_MAX_BYTES // (1024 * 1024)}MB。"
                )
            normalized[key]["max_total_bytes"] = total_bytes
    return normalized


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
                # 新版本加入的默认事件（如「新的标记点」）一次性补进已有配置
                if app_meta_get("notify_events_migrated_v2", "") != "1":
                    for item in NOTIFY_EVENTS:
                        if item.get("default") and item["key"] not in events:
                            events.append(item["key"])
                    app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
                    app_meta_set("notify_events_migrated_v2", "1")
                # v3：加入「安全提醒」等后续新增的默认事件
                if app_meta_get("notify_events_migrated_v3", "") != "1":
                    for item in NOTIFY_EVENTS:
                        if item.get("default") and item["key"] not in events:
                            events.append(item["key"])
                    app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
                    app_meta_set("notify_events_migrated_v3", "1")
                if app_meta_get("notify_events_migrated_v4", "") != "1":
                    for item in NOTIFY_EVENTS:
                        if item.get("default") and item["key"] not in events:
                            events.append(item["key"])
                    app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
                    app_meta_set("notify_events_migrated_v4", "1")
                # v5：加入「新的动态评论」等后续新增的默认事件
                if app_meta_get("notify_events_migrated_v5", "") != "1":
                    for item in NOTIFY_EVENTS:
                        if item.get("default") and item["key"] not in events:
                            events.append(item["key"])
                    app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
                    app_meta_set("notify_events_migrated_v5", "1")
                # v6：内容举报
                if app_meta_get("notify_events_migrated_v6", "") != "1":
                    for item in NOTIFY_EVENTS:
                        if item.get("default") and item["key"] not in events:
                            events.append(item["key"])
                    app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
                    app_meta_set("notify_events_migrated_v6", "1")
                # v7：留言审核改为真正的先审后发后，新留言通知默认开启
                if app_meta_get("notify_events_migrated_v7", "") != "1":
                    for item in NOTIFY_EVENTS:
                        if item.get("default") and item["key"] not in events:
                            events.append(item["key"])
                    app_meta_set("notify_events", json.dumps(events, ensure_ascii=False))
                    app_meta_set("notify_events_migrated_v7", "1")
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


def deliver_notification(channel, url, title, body, event, link="/workbench"):
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
                    "url": link,
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


def agent_internal_request(path, payload=None, timeout=15):
    token = os.environ.get("ERRORJIANG_AGENT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("ErrorJ Agent 尚未配置内部令牌。")
    headers = {
        "Accept": "application/json",
        "X-ErrorJ-Agent-Token": token,
        "User-Agent": "ErrorJ-Agent-Bridge/1.0",
    }
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
        method = "POST"
    request = Request(
        AGENT_BASE_URL + path,
        data=data,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def notify_agent_async(event, title, body, link="/workbench"):
    token = os.environ.get("ERRORJIANG_AGENT_TOKEN", "").strip()
    if not token:
        return False
    absolute_link = str(link or "")
    if absolute_link.startswith("/"):
        absolute_link = PUBLIC_SITE_URL + absolute_link

    def worker():
        try:
            agent_internal_request(
                "/internal/notify",
                {
                    "event": str(event or ""),
                    "title": str(title or ""),
                    "body": str(body or ""),
                    "link": absolute_link,
                },
                timeout=10,
            )
            notify_log_write(event, title, body, "agent", "ok", "HTTP 200")
        except HTTPError as exc:
            notify_log_write(
                event, title, body, "agent", "fail", f"HTTP {exc.code}"
            )
        except (
            URLError,
            ValueError,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as exc:
            notify_log_write(
                event,
                title,
                body,
                "agent",
                "fail",
                str(exc)[:200],
            )

    threading.Thread(target=worker, daemon=True).start()
    return True


def notify_async(event, title, body, link="/workbench"):
    """事件触发时异步推送，不阻塞请求。"""
    notify_agent_async(event, title, body, link)
    settings = notify_settings()
    if (
        not settings["enabled"]
        or not settings["url"]
        or event not in settings["events"]
    ):
        return False
    channel, url = settings["channel"], settings["url"]

    def worker():
        ok, detail = deliver_notification(channel, url, title, body, event, link)
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


def stored_auth_secret(existing=""):
    """会话签名密钥的稳定存放点（数据库 app_meta）。

    密钥原先只存在 data/auth.json。如果那个文件被别的用户（例如用 sudo 跑
    tools/set_password.py）改成只有 root 能读，应用读不到就会在每次启动时
    重新随机生成密钥，于是所有会话（含「记住我 30 天」）一重启就全部失效。
    这里改成以数据库为准：应用自己写得进去，重启后密钥稳定。

    existing 非空时表示从环境变量或 auth.json 拿到了权威值，把它镜像进数据库。
    """
    try:
        row = query_one("SELECT value FROM app_meta WHERE key = ?", (AUTH_SECRET_KEY,))
        saved = str((row or {}).get("value") or "").strip()
        if existing:
            if saved != existing:
                execute(
                    "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
                    (AUTH_SECRET_KEY, existing),
                )
            return existing
        if saved:
            return saved
        fresh = secrets.token_hex(32)
        execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            (AUTH_SECRET_KEY, fresh),
        )
        return fresh
    except sqlite3.Error:
        return existing or secrets.token_hex(32)


def save_auth_password(password):
    """把新的管理员密码写进 data/auth.json，并立刻在内存里生效（不用重启服务）。

    环境变量 INVENTORY_PASSWORD 只在 auth.json 还没有密码哈希时当引导值，
    所以这里写下的密码会真正接管登录校验（见 load_auth_state 的优先级说明）。
    """
    config = {}
    if AUTH_PATH.is_file():
        try:
            config = json.loads(AUTH_PATH.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            config = {}
    config["password_hash"] = hash_password(password)
    config.setdefault("secret", str(AUTH_STATE.get("secret") or "") or secrets.token_hex(32))
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(AUTH_PATH, 0o600)
    except OSError:
        pass
    AUTH_STATE["enabled"] = True
    AUTH_STATE["password_hash"] = config["password_hash"]
    if config.get("secret"):
        AUTH_STATE["secret"] = config["secret"]


def load_auth_state():
    """密码来自环境变量 INVENTORY_PASSWORD，或 data/auth.json（tools/set_password.py 生成）。"""
    config = {}
    config_broken = ""
    if AUTH_PATH.is_file():
        try:
            config = json.loads(AUTH_PATH.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError) as exc:
            # 文件存在却读不出来时绝不能静默降级成免密开放模式
            # （那等于全站敞开，连 /workbench 和 /api/admin 都不用密码），
            # 这里只做记录，由 main() 决定拒绝启动。
            config = {}
            config_broken = f"{AUTH_PATH} 无法读取或解析：{exc}"
    password_hash = str(config.get("password_hash") or "")
    env_password = os.environ.get("INVENTORY_PASSWORD") or ""
    # auth.json 里有密码哈希就优先用它：站内「修改管理员密码」写的就是这里，
    # 这样改完立即生效、不需要重启服务。环境变量只在还没设置过密码时当引导值。
    if not password_hash and env_password:
        password_hash = hash_password(env_password)
    secret = os.environ.get("INVENTORY_SECRET") or str(config.get("secret") or "")
    if password_hash:
        secret = stored_auth_secret(secret)
    if password_hash and not config.get("secret"):
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
            "config_broken": config_broken,
        }
    )
    return AUTH_STATE


SESSION_DEVICE_DESKTOP = "desktop"
SESSION_DEVICE_MOBILE = "mobile"


def session_device_class(user_agent):
    """按 User-Agent 粗分设备：平板算手机端，其它算电脑端。"""
    label = describe_user_agent(user_agent)
    if "手机" in label or "平板" in label:
        return SESSION_DEVICE_MOBILE
    return SESSION_DEVICE_DESKTOP


def session_row(sid):
    if not sid:
        return None
    return query_one("SELECT * FROM sessions WHERE sid = ?", (sid,))


def delete_session(sid):
    if sid:
        execute("DELETE FROM sessions WHERE sid = ?", (sid,))


def delete_user_sessions(kind, user_id):
    execute("DELETE FROM sessions WHERE kind = ? AND user_id = ?", (kind, int(user_id or 0)))


def delete_sessions_for_user(user_id):
    execute("DELETE FROM sessions WHERE user_id = ?", (int(user_id or 0),))


def clear_device_sessions(kind, user_id, device):
    """同一账号同一设备类型只保留一个会话：新登录生效，旧会话被踢下线。"""
    execute(
        "DELETE FROM sessions WHERE kind = ? AND user_id = ? AND device = ?",
        (kind, int(user_id or 0), device),
    )


def purge_expired_sessions():
    execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))


def newest_message_id():
    row = query_one("SELECT COALESCE(MAX(id), 0) AS n FROM site_messages")
    return int((row or {}).get("n") or 0)


def message_last_seen(user_id):
    row = query_one(
        "SELECT last_seen_id FROM message_views WHERE user_id = ?",
        (int(user_id or 0),),
    )
    return int(row["last_seen_id"] or 0) if row else 0


def mark_messages_seen(user_id):
    user_id = int(user_id or 0)
    seen = max(message_last_seen(user_id), newest_message_id())
    execute(
        """INSERT INTO message_views (user_id, last_seen_id, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               last_seen_id = excluded.last_seen_id,
               updated_at = excluded.updated_at""",
        (user_id, seen, now_text()),
    )
    return seen


LIKE_TARGET_TYPES = {"message", "moment", "comment"}
NOTIFICATION_MODULES = {"messages", "moments", "map", "music", "books", "recommendations"}
NOTIFICATION_ACTIVITY_ACTIONS = {
    "moment_new": {"moment_create"},
    "message_reply": {"message_reply"},
    "music_new": {"music_upload"},
    "book_new": {"book_upload"},
    "recommendation_new": {"recommendation_create"},
}
NOTIFICATION_TARGET_TABLES = {
    "messages": "site_messages",
    # 动态模块的提醒有两种落点：动态本身（新动态）和具体评论（新评论 / 回复 / 点赞）
    "moments": ("moments", "moment_comments"),
    "map": "map_places",
    "music": "site_music",
    "books": "books",
    "recommendations": "recommendations",
}


def like_counts(target_type, target_ids):
    ids = [int(value) for value in target_ids if int(value or 0) > 0]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = query(
        f"""SELECT target_id, COUNT(*) AS n FROM content_likes
            WHERE target_type = ? AND target_id IN ({placeholders})
            GROUP BY target_id""",
        (target_type, *ids),
    )
    return {int(row["target_id"]): int(row["n"]) for row in rows}


def liked_target_ids(viewer_id, target_type, target_ids):
    """viewer_id 为 None 表示未登录；0 表示站长本人。"""
    if viewer_id is None:
        return set()
    user_id = int(viewer_id)
    ids = [int(value) for value in target_ids if int(value or 0) > 0]
    if not ids:
        return set()
    placeholders = ",".join("?" for _ in ids)
    rows = query(
        f"""SELECT target_id FROM content_likes
            WHERE target_type = ? AND user_id = ? AND target_id IN ({placeholders})""",
        (target_type, user_id, *ids),
    )
    return {int(row["target_id"]) for row in rows}


def add_user_notification(user_id, kind, module, target_id, actor, text):
    """给单个账号写一条站内提醒；user_id 为 0 表示站长本人。"""
    if user_id is None:
        return None
    user_id = int(user_id)
    if user_id < 0 or module not in NOTIFICATION_MODULES:
        return None
    return execute(
        """INSERT INTO user_notifications
               (user_id, kind, module, target_id, actor, text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            str(kind or "")[:40],
            module,
            int(target_id or 0),
            str(actor or "")[:64],
            str(text or "")[:200],
            now_text(),
        ),
    )


def member_user_ids():
    """所有已批准、非管理员的普通账号。"""
    rows = query(
        """SELECT id FROM users
           WHERE status = 'approved' AND role = 'member'
             AND id NOT IN (
                 SELECT user_id FROM user_permissions
                 WHERE permission = ? AND mode = 'allow'
             )""",
        (ADMIN_PERMISSION,),
    )
    return [int(row["id"]) for row in rows]


def unseen_notifications(user_id):
    """按模块汇总该账号的未读提醒。"""
    if user_id is None:
        return {}
    user_id = int(user_id)
    rows = query(
        """SELECT module, COUNT(*) AS n, MAX(created_at) AS last_at,
                  MAX(id) AS last_id
           FROM user_notifications
           WHERE user_id = ? AND seen_at IS NULL
           GROUP BY module""",
        (user_id,),
    )
    result = {}
    for row in rows:
        latest = query_one(
            "SELECT text, kind, actor FROM user_notifications WHERE id = ?",
            (int(row["last_id"] or 0),),
        )
        result[str(row["module"])] = {
            "count": int(row["n"] or 0),
            "created_at": str(row["last_at"] or ""),
            "text": str((latest or {}).get("text") or ""),
            "kind": str((latest or {}).get("kind") or ""),
            "actor": str((latest or {}).get("actor") or ""),
        }
    return result


def unseen_notification_targets(user_id, module):
    """未读提醒对应到具体卡片的目标 ID，用于页面里的呼吸高亮。"""
    if user_id is None:
        return []
    user_id = int(user_id)
    if user_id < 0 or module not in NOTIFICATION_MODULES:
        return []
    rows = query(
        """SELECT DISTINCT target_id FROM user_notifications
           WHERE user_id = ? AND module = ? AND seen_at IS NULL
             AND target_id > 0""",
        (user_id, module),
    )
    return sorted(int(row["target_id"]) for row in rows)


def unseen_notification_target_kinds(user_id, module):
    """未读提醒的 target_id → kind。

    动态模块里「动态 id」和「评论 id」来自两张自增表，可能撞号；前端要靠 kind
    判断这个目标指向的是动态本体还是某条评论。评论类 kind 优先。
    """
    if user_id is None:
        return {}
    user_id = int(user_id)
    if user_id < 0 or module not in NOTIFICATION_MODULES:
        return {}
    comment_kinds = {"moment_comment", "comment_reply", "comment_like"}
    result = {}
    for row in query(
        """SELECT target_id, kind FROM user_notifications
           WHERE user_id = ? AND module = ? AND seen_at IS NULL
             AND target_id > 0
           ORDER BY id""",
        (user_id, module),
    ):
        target = int(row["target_id"])
        kind = str(row.get("kind") or "")
        if result.get(target) in comment_kinds:
            continue
        result[target] = kind
    return result


def unseen_notification_rows(user_id):
    """返回未读提醒的明细，供首页把公开动态和站内提醒合并展示。"""
    if user_id is None:
        return []
    user_id = int(user_id)
    if user_id < 0:
        return []
    return query(
        """SELECT id, kind, module, target_id, actor, text, created_at
           FROM user_notifications
           WHERE user_id = ? AND seen_at IS NULL
           ORDER BY id""",
        (user_id,),
    )


def mark_notifications_seen(user_id, module, target_id=None, scope=""):
    """
    把某个模块的未读提醒标记为已读。

    scope 只对推荐模块有意义：「网页」和「站内资源」两栏共用 recommendations 模块，
    scope="web" / "resource" 时只清掉对应那部分，另一栏的角标留着。
    """
    if user_id is None:
        return 0
    user_id = int(user_id)
    if user_id < 0 or module not in NOTIFICATION_MODULES:
        return 0
    if target_id:
        execute(
            """UPDATE user_notifications SET seen_at = ?
               WHERE user_id = ? AND module = ? AND target_id = ?
                 AND seen_at IS NULL""",
            (now_text(), user_id, module, int(target_id)),
        )
        return 1
    if scope == "resource":
        execute(
            """UPDATE user_notifications SET seen_at = ?
               WHERE user_id = ? AND module = ? AND seen_at IS NULL
                 AND target_id IN (
                     SELECT id FROM recommendations WHERE kind = 'resource'
                 )""",
            (now_text(), user_id, module),
        )
        return 1
    if scope == "web":
        execute(
            """UPDATE user_notifications SET seen_at = ?
               WHERE user_id = ? AND module = ? AND seen_at IS NULL
                 AND target_id NOT IN (
                     SELECT id FROM recommendations WHERE kind = 'resource'
                 )""",
            (now_text(), user_id, module),
        )
        return 1
    execute(
        """UPDATE user_notifications SET seen_at = ?
           WHERE user_id = ? AND module = ? AND seen_at IS NULL""",
        (now_text(), user_id, module),
    )
    return 1


def clear_notification_target(module, target_id):
    """内容被删除后，清理所有账号指向该内容的未读提醒。"""
    if module not in NOTIFICATION_MODULES:
        return
    execute(
        """UPDATE user_notifications SET seen_at = ?
           WHERE module = ? AND target_id = ? AND seen_at IS NULL""",
        (now_text(), module, int(target_id or 0)),
    )


def prune_notification_targets(user_id, module, table):
    """指向已删除内容的提醒直接标记已读，返回仍然存在的目标。"""
    targets = unseen_notification_targets(user_id, module)
    if not targets:
        return []
    placeholders = ",".join("?" for _ in targets)
    # table 可以是单个表名，也可以是多张表的元组（例如动态 = moments + moment_comments）
    tables = (table,) if isinstance(table, str) else tuple(table)
    existing = set()
    for name in tables:
        for row in query(
            f"SELECT id FROM {name} WHERE id IN ({placeholders})", tuple(targets)
        ):
            existing.add(int(row["id"]))
    for target in targets:
        if target not in existing:
            mark_notifications_seen(user_id, module, target)
    return [target for target in targets if target in existing]


def notification_alert_text(module, info):
    """把未读提醒汇总成首页左下角的一行提示。"""
    count = max(1, int((info or {}).get("count") or 0))
    kind = str((info or {}).get("kind") or "")
    if module == "map":
        # 标记点的点赞 / 打卡已下线，这条分支只用来展示历史遗留的未读提醒
        return str((info or {}).get("text") or "标记点有未读提醒")
    if module == "music":
        return "上传了一首歌" if count == 1 else f"上传了 {count} 首歌"
    if module == "books":
        return "上架了一本电子书" if count == 1 else f"上架了 {count} 本电子书"
    if module == "recommendations":
        return "新增了一条推荐" if count == 1 else f"新增了 {count} 条推荐"
    if module == "moments":
        if kind == "comment_reply":
            return "回复了你的评论" if count == 1 else f"有 {count} 条新回复（你的评论）"
        if kind == "comment_like":
            return "点赞了你的评论" if count == 1 else f"有 {count} 个新点赞（你的评论）"
        if kind == "moment_comment":
            return "评论了你的动态" if count == 1 else f"有 {count} 条新评论（你的动态）"
        return "更新了动态" if count == 1 else f"更新了 {count} 条动态"
    if kind == "message_reply":
        if count == 1:
            return str((info or {}).get("text") or "回复了你的留言")
        return f"有 {count} 条新回复"
    return "点赞了你的留言" if count == 1 else f"有 {count} 个新点赞（你的留言）"


def shared_resource_info(resource_type, resource_id):
    """分享卡片和站内推荐共用的资源信息；资源不存在时 available=False。"""
    resource_type = str(resource_type or "")
    resource_id = int(resource_id or 0)
    info = {
        "type": resource_type,
        "id": resource_id,
        "label": SHARE_CONTENT_LABELS.get(resource_type, "内容"),
        "title": "",
        "subtitle": "",
        "cover_url": "",
        "url": "",
        "page_url": "",
        "available": False,
    }
    if resource_id <= 0:
        return info
    if resource_type == "note":
        row = query_one(
            """SELECT id, title, created_at, updated_at
               FROM learning_notes WHERE id = ?""",
            (resource_id,),
        )
        if row:
            info.update(
                {
                    "title": row.get("title") or "未命名笔记",
                    "subtitle": "笔记",
                    "url": f"/notes/read?id={resource_id}",
                    "page_url": f"/notes/read?id={resource_id}",
                    "available": True,
                }
            )
    elif resource_type == "book":
        row = query_one(
            """SELECT id, title, author, format, cover_path
               FROM books WHERE id = ?""",
            (resource_id,),
        )
        if row:
            info.update(
                {
                    "title": row.get("title") or "未命名电子书",
                    "subtitle": str(row.get("author") or "").strip()
                    or str(row.get("format") or "").upper(),
                    "cover_url": (
                        f"/site-files/{row['cover_path']}"
                        if row.get("cover_path")
                        else ""
                    ),
                    "url": f"/api/books/{resource_id}/download",
                    "page_url": f"/api/books/{resource_id}/download",
                    "available": True,
                }
            )
    elif resource_type == "music":
        row = query_one(
            """SELECT id, title, artist, cover_path
               FROM site_music WHERE id = ?""",
            (resource_id,),
        )
        if row:
            info.update(
                {
                    "title": row.get("title") or "未命名歌曲",
                    "subtitle": str(row.get("artist") or "").strip(),
                    "cover_url": (
                        f"/site-files/{row['cover_path']}"
                        if row.get("cover_path")
                        else ""
                    ),
                    "url": f"/api/site/music/{resource_id}/stream",
                    "page_url": "/music",
                    "available": True,
                }
            )
    return info


def resource_is_shared(resource_type, resource_id):
    """这个资源是否被分享到了动态或推荐页（决定登录账号能否阅读）。"""
    resource_type = str(resource_type or "")
    if resource_type not in SHARE_CONTENT_TYPES:
        return False
    resource_id = int(resource_id or 0)
    if resource_id <= 0:
        return False
    if query_one(
        """SELECT 1 AS ok FROM moment_shares
           WHERE resource_type = ? AND resource_id = ? LIMIT 1""",
        (resource_type, resource_id),
    ):
        return True
    return bool(
        query_one(
            """SELECT 1 AS ok FROM recommendations
               WHERE kind = 'resource' AND resource_type = ? AND resource_id = ?
               LIMIT 1""",
            (resource_type, resource_id),
        )
    )


def issue_session_token(days, identity, device=SESSION_DEVICE_DESKTOP, client_ip=""):
    expires = int(time.time()) + int(days) * 86400
    kind = str(identity.get("kind") or "owner")
    if kind not in ("owner", "member"):
        kind = "owner"
    user_id = int(identity.get("user_id") or 0)
    if device not in (SESSION_DEVICE_DESKTOP, SESSION_DEVICE_MOBILE):
        device = SESSION_DEVICE_DESKTOP
    sid = secrets.token_hex(16)
    stamp = now_text()
    execute(
        """INSERT INTO sessions
               (sid, kind, user_id, device, created_at, last_seen_at, expires_at, ip)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, kind, user_id, device, stamp, stamp, expires, (client_ip or "").strip() or None),
    )
    payload = f"v2|{kind}|{user_id}|{sid}|{expires}"
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
    if len(parts) != 6:
        return None
    version, kind, user_id_text, sid, expires_text, signature = parts
    if version != "v2" or kind not in ("owner", "member") or not sid:
        return None
    payload = "|".join(parts[:5])
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
    return {"kind": kind, "user_id": user_id, "expires": expires, "sid": sid}


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
            # 只回收过期计数。以前这里直接 clear()，攻击者用大量不同 key 打一轮
            # 就能把所有限速（含登录失败计数）一次性清空，等于绕过限速。
            stale = [
                item
                for item, values in RATE_LIMITS.items()
                if not values or now - values[-1] >= RATE_KEY_TTL_SECONDS
            ]
            for item in stale:
                RATE_LIMITS.pop(item, None)
            if len(RATE_LIMITS) > 20000:
                # 全是新鲜 key 的极端情况：丢掉最久没动的一批，保证内存有上限
                oldest = sorted(RATE_LIMITS, key=lambda item: RATE_LIMITS[item][-1])[:10000]
                for item in oldest:
                    RATE_LIMITS.pop(item, None)
        return True


def registration_block_reason(client_ip):
    """注册申请的持久化限额：返回空串表示放行，否则返回给用户看的原因。

    计数写在 users 表里（配合 register_ip 列），进程重启不会清零；
    应用内存里的 rate_allow 只用来挡同一秒内的连点。
    """
    if not client_ip:
        return ""
    cutoff = (datetime.now() - timedelta(seconds=REGISTRATION_WINDOW_SECONDS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    recent = query_one(
        "SELECT COUNT(*) AS n FROM users WHERE register_ip = ? AND created_at >= ?",
        (client_ip, cutoff),
    )
    if recent and int(recent.get("n") or 0) >= REGISTRATION_LIMIT_PER_WINDOW:
        return (
            f"同一个网络 {REGISTRATION_WINDOW_SECONDS // 3600} 小时内最多提交 "
            f"{REGISTRATION_LIMIT_PER_WINDOW} 次注册申请，请明天再试。"
        )
    pending = query_one(
        "SELECT COUNT(*) AS n FROM users WHERE register_ip = ? AND status = 'pending'",
        (client_ip,),
    )
    if pending and int(pending.get("n") or 0) >= REGISTRATION_PENDING_LIMIT:
        return "这个网络下已经有注册申请在等待审核，请等管理员处理后再提交。"
    return ""


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


def maybe_alert_login_failures(identifier):
    """同一 IP 5 分钟内失败达到阈值时推送一次，30 分钟内不重复提醒。"""
    now = time.time()
    with RATE_LOCK:
        count = len(
            [
                item
                for item in LOGIN_FAILURES.get(identifier, [])
                if now - item < LOGIN_ALERT_WINDOW_SECONDS
            ]
        )
        last_sent = LOGIN_ALERT_SENT.get(identifier, 0)
        if count < LOGIN_ALERT_THRESHOLD or now - last_sent < LOGIN_ALERT_COOLDOWN_SECONDS:
            return False
        LOGIN_ALERT_SENT[identifier] = now

    def worker():
        region = lookup_ip_region(identifier)
        where = identifier + (f"（{region}）" if region else "")
        notify_async(
            "security",
            "Error酱：登录失败提醒",
            f"IP {where} 在 5 分钟内登录失败 {count} 次，已触发登录限流。",
            "/workbench?view=logs",
        )

    threading.Thread(target=worker, daemon=True).start()
    return True


def maybe_alert_sensitive(scene, sample="", actor=""):
    """敏感词拦截提醒：同一场景 10 分钟内最多推送一次。"""
    now = time.time()
    if now - SENSITIVE_ALERT_SENT.get(scene, 0) < SENSITIVE_ALERT_COOLDOWN_SECONDS:
        return False
    SENSITIVE_ALERT_SENT[scene] = now
    text = str(sample or "").strip().replace("\n", " ")[:60]
    who = f"{str(actor).strip()[:40]} " if str(actor or "").strip() else ""
    notify_async(
        "security",
        "Error酱：敏感词拦截",
        f"{who}在{scene}中触发敏感词" + (f"：{text}" if text else "。"),
        "/workbench?view=logs",
    )
    return True


def safe_next_path(value):
    """只允许站内跳转，挡掉 //evil.com 这类开放重定向。"""
    text = str(value or "")
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return "/"
    return text


# 歌曲 / 书籍这两个地址只是推荐页 iframe 的落点，本身不再是一个能停留的页面
# （顶栏、举报入口都已从它们身上退场）。手输地址或翻旧书签进来的，送回推荐页对应那一栏。
LEGACY_SUBPAGE_TABS = {"/music": "music", "/books": "books"}


def legacy_subpage_redirect(path, query):
    """给独立子页地址算出该跳去哪儿；不该跳（iframe 内嵌、或不是子页）时返回空串。"""
    tab = LEGACY_SUBPAGE_TABS.get(path)
    if not tab:
        return ""
    if (query.get("embed") or [""])[0] == "1":
        return ""
    # 其余查询参数照搬，侧栏更新日志的 focus 定位还能用
    carried = [
        (key, value)
        for key, values in query.items()
        for value in values
        if key != "embed"
    ]
    return "/downloads?" + urlencode([("tab", tab), *carried])


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
        session = session_row(claims.get("sid"))
        if (
            not session
            or session.get("kind") != claims.get("kind")
            or int(session.get("user_id") or 0) != int(claims.get("user_id") or 0)
            or int(session.get("expires_at") or 0) <= time.time()
        ):
            return None
        if claims["kind"] == "owner":
            if not self.session_ip_matches(session):
                return None
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
        if is_admin_user and not self.session_ip_matches(session):
            return None
        return {
            "kind": "admin" if is_admin_user else "member",
            "user_id": row["id"],
            "username": row["username"],
            "nickname": row.get("nickname") or row["username"],
            "role": "admin" if is_admin_user else "member",
        }

    def session_ip_matches(self, session):
        """管理员会话绑定登录时的来源 IP：换了网络就必须重新登录。

        普通账号不受影响（会员在手机 / 家里网络之间切换不会被踢下线）。
        升级前签发的旧会话没有记录 IP，按「不拦」处理，下次登录时自动绑定。
        """
        bound = str((session or {}).get("ip") or "").strip()
        current = self.client_ip()
        if not bound or bound == current:
            return True
        delete_session((session or {}).get("sid"))
        self.log_activity(
            "session_ip_mismatch",
            f"管理员会话因来源网络变化被下线（登录时 {bound}，当前 {current}）",
            actor={"kind": "guest", "username": "管理员"},
        )
        return False

    def session_valid(self):
        return self.session_identity() is not None

    def is_owner(self):
        identity = self.session_identity()
        return bool(identity and identity.get("kind") == "owner")

    def is_admin(self):
        identity = self.session_identity()
        return bool(identity and identity.get("kind") in ("owner", "admin"))

    def agent_request_identity(self):
        """校验 errorjiang-agent 的内部请求，并还原它声明的网站用户身份。"""
        expected = os.environ.get("ERRORJIANG_AGENT_TOKEN", "").strip()
        supplied = str(self.headers.get("X-ErrorJ-Agent-Token") or "").strip()
        if not expected:
            return None
        if not supplied or not hmac.compare_digest(supplied, expected):
            return None
        try:
            source_ip = ipaddress.ip_address(self.client_ip())
        except ValueError:
            return None
        if not source_ip.is_loopback:
            return None
        try:
            user_id = int(self.headers.get("X-ErrorJ-Agent-User") or "")
        except (TypeError, ValueError):
            return None
        if user_id < 0:
            return None
        if user_id == 0:
            return {
                "kind": "owner",
                "user_id": 0,
                "username": "ErrorJ Agent",
                "nickname": "管理员",
                "role": "owner",
            }
        user = query_one(
            "SELECT id, username, nickname, status FROM users WHERE id = ?",
            (user_id,),
        )
        if not user or user.get("status") != "approved":
            return None
        is_admin_user = user_has_permission(user_id, ADMIN_PERMISSION)
        return {
            "kind": "admin" if is_admin_user else "member",
            "user_id": user_id,
            "username": user.get("username") or "",
            "nickname": user.get("nickname") or user.get("username") or "",
            "role": "admin" if is_admin_user else "member",
        }

    def guard_agent_request(self):
        expected = os.environ.get("ERRORJIANG_AGENT_TOKEN", "").strip()
        if not expected:
            api_error(self, 503, "ErrorJ Agent 内部接口未启用。")
            return False
        if not self.agent_request_identity():
            api_error(self, 401, "ErrorJ Agent 鉴权失败。")
            return False
        return True

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
            real_ip = (self.headers.get("X-Real-IP") or "").strip()
            if real_ip:
                try:
                    return str(ipaddress.ip_address(real_ip))
                except ValueError:
                    pass
            forwarded = self.headers.get("X-Forwarded-For") or ""
            # Nginx appends the real peer to $proxy_add_x_forwarded_for. The
            # left-most value is client-controlled, so only trust the right-most
            # address and only when it is a valid IP.
            for candidate in reversed(forwarded.split(",")):
                candidate = candidate.strip()
                if not candidate:
                    continue
                try:
                    return str(ipaddress.ip_address(candidate))
                except ValueError:
                    continue
        return self.client_address[0] if self.client_address else "unknown"

    def client_port(self):
        try:
            return int(self.client_address[1])
        except (IndexError, TypeError, ValueError):
            return None

    def target_endpoint(self):
        host_header = (self.headers.get("Host") or "").strip()
        proto = (
            "https"
            if FORCE_SECURE_COOKIES
            or (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"
            else "http"
        )
        parsed = urlsplit(f"//{host_header}" if host_header else "")
        host = parsed.hostname or host_header or HOST
        port = parsed.port or (443 if proto == "https" else PORT)
        return host, int(port)

    def client_platform(self):
        platform_hint = (self.headers.get("Sec-CH-UA-Platform") or "").strip().strip('"')
        mobile_hint = (self.headers.get("Sec-CH-UA-Mobile") or "").strip().strip('"')
        if mobile_hint == "?1":
            mobile_hint = "mobile"
        elif mobile_hint == "?0":
            mobile_hint = "desktop"
        parts = [part for part in (platform_hint, mobile_hint) if part]
        return " · ".join(parts)

    def log_activity(
        self,
        action,
        summary="",
        target_type="",
        target_id=None,
        actor=None,
        ip=None,
        ip_region=None,
        source_path="",
    ):
        """记录内容事件；自动补当前 IP 和省属地，失败不影响主流程。"""
        try:
            if ip is None:
                ip = self.client_ip()
            if ip_region is None:
                ip_region = lookup_ip_region(ip) if ip else ""
            identity = actor if actor is not None else self.session_identity()
            target_host, target_port = self.target_endpoint()
            write_activity(
                identity,
                action,
                summary=summary,
                target_type=target_type,
                target_id=target_id,
                ip=ip,
                ip_region=ip_region,
                source_path=source_path,
                method=self.command,
                source_port=self.client_port(),
                target_host=target_host,
                target_port=target_port,
                user_agent=self.headers.get("User-Agent") or "",
                client_platform=self.client_platform(),
            )
        except Exception as exc:
            print(f"[activity] {exc}", file=sys.stderr)

    def log_page_view(self, path, status=200):
        """记录一次页面访问（只记录真实页面，不记静态资源和接口）。"""
        try:
            identity = self.session_identity()
            actor_kind = "guest"
            user_id = 0
            name = "游客"
            if identity:
                actor_kind = identity.get("kind") or "member"
                if identity.get("kind") == "owner":
                    name = identity.get("username") or "管理员"
                else:
                    user_id = int(identity.get("user_id") or 0)
                    name = identity.get("nickname") or identity.get("username") or ""
            target_host, target_port = self.target_endpoint()
            enqueue_access_log(
                path=path,
                ip=self.client_ip(),
                status=status,
                actor_kind=actor_kind,
                user_id=user_id,
                actor_name=name,
                referer=self.headers.get("Referer") or "",
                user_agent=self.headers.get("User-Agent") or "",
                method=self.command,
                source_port=self.client_port(),
                target_host=target_host,
                target_port=target_port,
                client_platform=self.client_platform(),
            )
        except Exception as exc:
            print(f"[access] {exc}", file=sys.stderr)

    def request_base_url(self):
        """按当前请求拼出站点根地址，用于通知里的可点击链接。"""
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return ""
        proto = (
            "https"
            if FORCE_SECURE_COOKIES
            or (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"
            else "http"
        )
        return f"{proto}://{host}"

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

    def base_public_allowed(self, path, method):
        """永远公开的基础请求：首页、登录注册、静态资源和登录相关接口。"""
        if path.startswith("/static/"):
            return True
        if path in ALWAYS_PUBLIC_PAGES or path in ALWAYS_PUBLIC_APIS:
            return True
        if method == "GET" and path == "/favicon.ico":
            return True
        return False

    def data_file_allowed(self, relative, identity):
        """site-files 数据的访问控制。"""
        relative = normalized_data_relative(relative)
        if not relative or relative == ".":
            return False
        if relative.startswith("workbench/"):
            return bool(
                identity and identity.get("kind") in ("owner", "admin")
            )
        for prefix, permissions in DATA_PERMISSION_RULES:
            if relative.startswith(prefix):
                if identity is None:
                    return False
                if identity.get("kind") in ("owner", "admin"):
                    return True
                return any(
                    user_has_permission(identity.get("user_id"), key)
                    for key in permissions
                )
        if relative.startswith("map_images/"):
            if identity is None:
                return False
            if identity.get("kind") in ("owner", "admin"):
                return True
            return self.map_view_allowed(identity)
        for prefix, rule in GUEST_DATA_RULES:
            if relative.startswith(prefix):
                if guest_has_permission(rule):
                    return True
                return identity is not None
        if relative.startswith(SITE_MEMBER_DATA_PREFIXES):
            return identity is not None
        return False

    def map_view_allowed(self, identity=None):
        """当前账号有没有地图查看权限（管理员恒有）。"""
        if not MAP_PUBLIC:
            return False
        identity = identity if identity is not None else self.session_identity()
        if not identity:
            return False
        if identity.get("kind") in ("owner", "admin"):
            return True
        return any(
            user_has_permission(identity.get("user_id"), key)
            for key in MAP_VIEW_PERMISSIONS
        )

    def map_dock_allowed(self, identity=None):
        """/api/map 这次请求有没有可能成功（首页圆盘据此决定要不要发请求）。"""
        identity = identity if identity is not None else self.session_identity()
        if not identity:
            # 游客没有身份，can() 恒为 False，请求必然 401
            return False
        if identity.get("kind") in ("owner", "admin"):
            return True
        if not MAP_PUBLIC:
            # 地图整体关掉时 /api/map 变成管理员专属
            return False
        return any(
            user_has_permission(identity.get("user_id"), key)
            for key in MAP_VIEW_PERMISSIONS
        )

    def guest_request_allowed(self, path, method, identity):
        """游客（以及未登录请求）能访问的页面、接口和数据文件。"""
        if self.base_public_allowed(path, method):
            return True
        if path.startswith("/site-files/"):
            relative = unquote(path[len("/site-files/") :])
            return self.data_file_allowed(relative, identity)
        if method != "GET":
            return False
        rule = guest_page_permission_for_path(path)
        if rule:
            return guest_has_permission(rule)
        return False

    def guard_request(self, path, method):
        """返回 True 表示请求可以继续处理；被拒时先把请求体读干净再放行返回。"""
        allowed = self.guard_request_inner(path, method)
        if not allowed:
            # 拒绝的请求不会再走 get_payload()，请求体留在 socket 上会把 keep-alive 连接搞乱：
            # 下一个请求行会被拼成「{"module":"messages"}GET /static/moments.css」这种畸形请求，
            # 结果就是紧随其后的静态资源拿到 501。读掉残余字节即可。
            self.drain_request_body()
        return allowed

    def drain_request_body(self):
        """把当前请求的请求体读掉，保证 keep-alive 连接的下一个请求不被污染。"""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return
        remaining = max(0, length)
        if not remaining:
            return
        # 只读合理范围内的字节；超过就干脆断开连接，免得卡在一个巨大的 body 上
        budget = min(remaining, MAX_REQUEST_BYTES + 1024)
        while budget > 0:
            chunk = self.rfile.read(min(65536, budget))
            if not chunk:
                break
            budget -= len(chunk)
        if budget > 0 or remaining > MAX_REQUEST_BYTES + 1024:
            self.close_connection = True

    def guard_request_inner(self, path, method):
        """真正的权限 / 来源判断。"""
        if path == "/api/agent/tool":
            return self.guard_agent_request()
        if method in ("POST", "PATCH", "DELETE") and path not in ("/api/login", "/api/member/login"):
            if AUTH_STATE.get("enabled") and not self.origin_allowed():
                api_error(self, 403, "请求来源不合法。")
                return False
            if not rate_allow("write", self.client_ip(), 120, 60):
                api_error(self, 429, "操作过于频繁，请稍后再试。")
                return False
        identity = self.session_identity()
        if path.startswith("/site-files/"):
            relative = unquote(path[len("/site-files/") :])
            if relative and self.data_file_allowed(relative, identity):
                return True
            if identity is None:
                api_error(self, 401, "请登录后操作")
            else:
                api_error(self, 403, "当前账号没有访问权限。")
            return False
        if not AUTH_STATE.get("enabled"):
            return True
        if identity and identity.get("kind") in ("owner", "admin"):
            return True
        if self.guest_request_allowed(path, method, identity):
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
            api_error(self, 401, "请登录后操作")
        else:
            target = path if path.startswith("/") else "/"
            self.redirect(f"/login?next={quote(target)}")
        return False

    def api_site_upload_limits(self):
        self.send_json(200, {"limits": upload_limits()})

    def api_site_user_status_save(self, payload):
        """本人设置自己的展示状态：在线 / 在线-<设备> / 隐身。

        「在线 / 离线」都只是回到自动判断（按活跃时间），只有「隐身」会被记住 —— 而且隐身
        只在人还在活跃窗口内时成立，到点没操作就显示「离线」（见 presence_payload）；
        站长多一个自定义文案。任何人都只能改自己的状态 —— 别人的胶囊是只读的。
        """
        identity = self.session_identity()
        if identity is None:
            api_error(self, 401, "请登录后操作")
            return
        is_owner = identity.get("kind") in ("owner", "admin")
        user_id = 0 if is_owner else int(identity.get("user_id") or 0)
        if not is_owner and not user_id:
            api_error(self, 403, "当前账号不能设置状态。")
            return
        data = payload or {}
        # 自定义文案只有站长能写，普通账号带了也忽略
        text = str(data.get("text") or "").strip() if (is_owner and "text" in data) else None
        user_status_save(user_id, data.get("mode"), data.get("suffix"), text)
        presence = (
            owner_status() if is_owner else member_status(user_id, member_last_view(user_id))
        )
        self.log_activity("user_status_update", f"把展示状态改成「{presence['label']}」")
        self.send_json(200, {"ok": True, "presence": presence})

    def api_admin_upload_limits(self):
        self.send_json(
            200,
            {
                "limits": upload_limits(),
                "defaults": upload_limit_defaults(),
                "schema": UPLOAD_LIMIT_SCHEMA,
                "hard_max_bytes": UPLOAD_LIMIT_HARD_MAX_BYTES,
                "hard_max_count": UPLOAD_LIMIT_HARD_MAX_COUNT,
            },
        )

    def api_admin_upload_limits_save(self, payload):
        try:
            normalized = normalize_upload_limit_payload(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        app_meta_set(
            UPLOAD_LIMIT_META_KEY,
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
        )
        self.log_activity("upload_limits_update", "修改上传大小与数量限制")
        write_audit(
            self.session_identity(),
            "upload_limits_update",
            "修改上传大小与数量限制",
            normalized,
        )
        self.send_json(200, {"ok": True, "limits": normalized})

    def api_auth_status(self):
        enabled = bool(AUTH_STATE.get("enabled"))
        identity = self.session_identity()
        permissions = []
        pending_users = 0
        pending_attachments = 0
        pending_reports = 0
        if identity and identity.get("kind") != "owner":
            permissions = sorted(user_permission_set(identity.get("user_id")))
        if identity and identity.get("kind") in ("owner", "admin"):
            pending_users = query_one(
                "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'"
            )["n"]
            pending_messages = query_one(
                """SELECT COUNT(*) AS n FROM site_messages
                   WHERE parent_id IS NULL AND status = 'pending'"""
            )["n"]
            pending_legacy_files = query_one(
                """SELECT COUNT(*) AS n FROM site_message_files f
                   JOIN site_messages m ON m.id = f.message_id
                   WHERE f.status = 'pending' AND m.parent_id IS NULL
                     AND m.status = 'approved'"""
            )["n"]
            pending_attachments = int(pending_messages) + int(pending_legacy_files)
            pending_reports = query_one(
                "SELECT COUNT(*) AS n FROM content_reports WHERE status = 'pending'"
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
                "guest_pages": [] if identity else sorted(guest_permission_set()),
                "map_allowed": self.map_view_allowed(identity) if identity else False,
                # 首页左下角的圆形小地图入口会无条件请求一次 /api/map?dock=1；
                # 地图接口要地图类权限，游客和没有权限的账号必然 401。
                # 先把结果告诉前端，让它别白跑这次注定失败的请求（浏览器会在控制台留红字）。
                "map_dock_allowed": self.map_dock_allowed(identity),
                "pending_users": pending_users,
                "pending_attachments": pending_attachments,
                "pending_reports": pending_reports,
            },
        )

    def api_login(self, payload, member_only=False):
        identifier = self.client_ip()
        if login_blocked(identifier):
            self.log_activity(
                "login_blocked",
                f"登录尝试被限流：{str(payload.get('username') or '').strip() or '管理员'}",
                actor={
                    "kind": "guest",
                    "username": str(payload.get("username") or "").strip() or "管理员",
                },
            )
            maybe_alert_login_failures(identifier)
            api_error(self, 429, "密码错误次数过多，请 5 分钟后再试。")
            return
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if member_only and not username:
            api_error(self, 400, "请输入用户名和密码。")
            return
        if username:
            user = query_one(
                "SELECT id, username, password_hash, status FROM users WHERE username = ?",
                (username,),
            )
            if not user:
                login_failed(identifier)
                self.log_activity(
                    "login_fail",
                    f"用户名不存在：{username}",
                    actor={"kind": "guest", "username": username},
                )
                maybe_alert_login_failures(identifier)
                api_error(self, 401, "用户名或密码不正确。")
                return
            if user.get("status") != "approved":
                status_text = {
                    "pending": "账号正在等待管理员审核。",
                    "rejected": "账号申请未通过。",
                    "disabled": "账号已被停用。",
                }.get(user.get("status"), "账号当前不可用。")
                self.log_activity(
                    "login_fail",
                    f"账号状态不可用（{user.get('status')}）：{username}",
                    actor={"kind": "guest", "username": username},
                    target_type="user",
                    target_id=user["id"],
                )
                api_error(self, 403, status_text)
                return
            if not verify_password_hash(password, user.get("password_hash")):
                login_failed(identifier)
                self.log_activity(
                    "login_fail",
                    f"密码不正确：{username}",
                    actor={"kind": "guest", "username": username},
                    target_type="user",
                    target_id=user["id"],
                )
                maybe_alert_login_failures(identifier)
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
            # 重新登录后状态回到默认的「在线」（清掉隐身 / 设备后缀）
            reset_status_on_login(user["id"])
            self.log_activity(
                "login", "登录成功", target_type="user", target_id=user["id"], actor=identity
            )
        else:
            if not verify_password(password):
                login_failed(identifier)
                self.log_activity(
                    "login_fail",
                    "管理员密码不正确",
                    actor={"kind": "guest", "username": "管理员"},
                )
                maybe_alert_login_failures(identifier)
                api_error(self, 401, "管理员密码不正确。")
                return
            identity = {
                "kind": "owner",
                "user_id": 0,
                "username": "管理员",
                "role": "owner",
            }
            # 重新登录后状态回到默认的「在线」（清掉隐身 / 设备后缀）
            reset_status_on_login(0)
            self.log_activity("login", "管理员登录成功", actor=identity)
        login_succeeded(identifier)
        days = AUTH_SESSION_DAYS_REMEMBER if payload.get("remember") else AUTH_SESSION_DAYS
        device = session_device_class(self.headers.get("User-Agent"))
        # 同一账号同一设备类型只保留一个会话：新登录生效，旧设备被踢下线
        clear_device_sessions(identity.get("kind") or "owner", identity.get("user_id") or 0, device)
        token = issue_session_token(days, identity, device, self.client_ip())
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
        client_ip = self.client_ip()
        if not rate_allow(
            "register",
            client_ip,
            REGISTRATION_BURST_LIMIT,
            REGISTRATION_BURST_WINDOW_SECONDS,
        ):
            api_error(self, 429, "注册请求太频繁，请稍后再试。")
            return
        blocked = registration_block_reason(client_ip)
        if blocked:
            self.log_activity(
                "register_blocked",
                f"注册申请被限额拦截：{blocked}",
                actor={"kind": "guest", "username": str(payload.get("username") or "").strip()},
            )
            api_error(self, 429, blocked)
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
                maybe_alert_sensitive("注册昵称", nickname, username)
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
                (username, nickname, password_hash, status, role, created_at, updated_at,
                 register_ip)
            VALUES (?, ?, ?, 'pending', 'member', ?, ?, ?)
            """,
            (username, nickname, hash_password(password), stamp, stamp, client_ip or None),
        )
        write_audit(
            None,
            "register",
            f"新注册申请：{username}" + (f"（{nickname}）" if nickname else ""),
            {"username": username, "nickname": nickname or ""},
        )
        self.log_activity(
            "register",
            f"提交注册申请：{username}" + (f"（{nickname}）" if nickname else ""),
            actor={"kind": "guest", "username": username},
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
            api_error(self, 401, "请登录后操作")
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
            maybe_alert_sensitive(
                "修改昵称", nickname, identity.get("nickname") or identity.get("username") or ""
            )
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
        self.log_activity(
            "nickname_change",
            f"昵称改为「{nickname}」",
            target_type="user",
            target_id=user_id,
            actor=identity,
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
                        approved_at, last_login_at, nickname_updated_at, silenced_until,
                        message_daily_limit
                 FROM users"""
        values = ()
        if status_filter in ("pending", "approved", "rejected", "disabled"):
            sql += " WHERE status = ?"
            values = (status_filter,)
        sql += """ ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1
                   ELSE 2 END, id DESC"""
        users = query(sql, values)
        permission_rows = query(
            "SELECT user_id, permission, mode FROM user_permissions ORDER BY permission"
        )
        grouped = {}
        for row in permission_rows:
            grouped.setdefault(row["user_id"], {})[row["permission"]] = (
                row["mode"] or "allow"
            )
        for user in users:
            overrides = grouped.get(user["id"], {})
            user["permission_overrides"] = overrides
            user["permissions"] = sorted(user_permission_set(user["id"]))
            user["is_admin"] = overrides.get(ADMIN_PERMISSION) == "allow"
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
                "role_defaults": sorted(role_permission_set(ROLE_MEMBER)),
                "default_message_limit": MESSAGE_DAILY_LIMIT,
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
        if status in ("disabled", "rejected"):
            # 停用 / 拒绝后立刻踢掉该账号的全部会话
            delete_sessions_for_user(user_id)
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
        mode = str(payload.get("mode") or "").strip().lower()
        if mode not in ("allow", "deny", "inherit"):
            mode = "allow" if bool(payload.get("granted")) else "inherit"
        if permission == ADMIN_PERMISSION:
            # 「授予管理员」只有两种状态：允许 / 继承（不授予）
            mode = "allow" if mode == "allow" else "inherit"
        granted = mode == "allow"
        stamp = now_text()
        if mode == "inherit":
            execute(
                "DELETE FROM user_permissions WHERE user_id = ? AND permission = ?",
                (user_id, permission),
            )
        else:
            execute(
                """INSERT OR REPLACE INTO user_permissions
                       (user_id, permission, granted_by, granted_at, mode)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    user_id,
                    permission,
                    self.session_identity().get("nickname") or "管理员",
                    stamp,
                    mode,
                ),
            )
        audit_action = "grant" if mode == "allow" else ("deny" if mode == "deny" else "revoke")
        write_audit(
            self.session_identity(),
            audit_action,
            f"{PERMISSION_LABELS.get(permission, permission)}（{permission}）"
            + ("（禁止）" if mode == "deny" else ""),
            target,
        )
        self.send_json(
            200,
            {
                "ok": True,
                "mode": mode,
                "overrides": user_permission_overrides(user_id),
                "permissions": sorted(user_permission_set(user_id)),
            },
        )

    def api_admin_user_message_limit(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以调整留言次数。")
            return
        user_id = int(path.split("/")[4])
        target = self.admin_target_user(user_id)
        if not target:
            api_error(self, 404, "账号不存在。")
            return
        if not self.admin_can_touch(target):
            return
        raw = payload.get("limit")
        if raw is None or raw == "":
            new_limit = None
        else:
            try:
                new_limit = int(raw)
            except (TypeError, ValueError):
                api_error(self, 400, "留言次数需为 0-999 之间的整数。")
                return
            if new_limit < 0 or new_limit > 999:
                api_error(self, 400, "留言次数需为 0-999 之间的整数。")
                return
        execute(
            "UPDATE users SET message_daily_limit = ?, updated_at = ? WHERE id = ?",
            (new_limit, now_text(), user_id),
        )
        shown = MESSAGE_DAILY_LIMIT if new_limit is None else new_limit
        write_audit(
            self.session_identity(),
            "set_message_limit",
            f"每日留言上限改为 {shown} 条" + ("（默认）" if new_limit is None else ""),
            target,
        )
        self.send_json(
            200,
            {
                "ok": True,
                "limit": shown,
                "custom": new_limit is not None,
            },
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
            actor = self.session_identity() or {}
            maybe_alert_sensitive(
                "管理员修改昵称",
                nickname,
                actor.get("nickname") or actor.get("username") or "",
            )
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
        delete_sessions_for_user(user_id)
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
        delete_sessions_for_user(user_id)
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

    def role_permission_payload(self):
        member_groups = []
        for group in PERMISSION_GROUPS:
            items = [
                {"key": item["key"], "label": item["label"]}
                for item in group["items"]
                if item["key"] in MEMBER_ROLE_PERMISSIONS
            ]
            if items:
                member_groups.append(
                    {"key": group["key"], "label": group["label"], "items": items}
                )
        admin_items = [
            {"key": item["key"], "label": item["label"]}
            for group in PERMISSION_GROUPS
            for item in group["items"]
            if item["key"] != ADMIN_PERMISSION
        ]
        return {
            "guest_options": list(GUEST_PAGE_PERMISSIONS),
            "guest": sorted(role_permission_set(ROLE_GUEST)),
            "member_groups": member_groups,
            "member": sorted(role_permission_set(ROLE_MEMBER)),
            "member_defaults": list(DEFAULT_MEMBER_PERMISSIONS),
            "admin_permissions": admin_items,
        }

    def api_admin_role_permissions(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看角色权限。")
            return
        self.send_json(200, self.role_permission_payload())

    def api_admin_role_permission_set(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以修改角色权限。")
            return
        role = str(payload.get("role") or "").strip()
        permission = str(payload.get("permission") or "").strip()
        if role == ROLE_GUEST:
            allowed = set(GUEST_PAGE_PERMISSION_KEYS)
            labels = GUEST_PAGE_LABELS
        elif role == ROLE_MEMBER:
            allowed = set(MEMBER_ROLE_PERMISSIONS)
            labels = MEMBER_ROLE_LABELS
        else:
            api_error(self, 400, "未知角色。")
            return
        if permission not in allowed:
            api_error(self, 400, "这个权限不能分配给该角色。")
            return
        granted = bool(payload.get("granted"))
        stamp = now_text()
        identity = self.session_identity()
        actor = identity.get("nickname") or identity.get("username") or "管理员"
        if granted:
            execute(
                """INSERT OR REPLACE INTO role_permissions
                       (role, permission, granted_by, granted_at)
                   VALUES (?, ?, ?, ?)""",
                (role, permission, actor, stamp),
            )
        else:
            execute(
                "DELETE FROM role_permissions WHERE role = ? AND permission = ?",
                (role, permission),
            )
        invalidate_guest_permission_cache()
        write_audit(
            identity,
            "role_grant" if granted else "role_revoke",
            f"{ROLE_LABELS.get(role, role)} · {labels.get(permission, permission)}（{permission}）",
            {"id": None, "username": ROLE_LABELS.get(role, role)},
        )
        self.send_json(200, {"ok": True, **self.role_permission_payload()})

    def api_admin_audit(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看审计日志。")
            return
        conditions = []
        values = []
        action = self.log_param(params, "action")
        if action:
            conditions.append("action = ?")
            values.append(action)
        keyword = self.log_param(params, "q")
        if keyword:
            like = f"%{keyword}%"
            conditions.append("(actor_name LIKE ? OR target_name LIKE ? OR detail LIKE ?)")
            values.extend([like, like, like])
        date_from = self.log_param(params, "date_from")
        date_to = self.log_param(params, "date_to")
        if date_from:
            conditions.append("created_at >= ?")
            values.append(date_from + " 00:00:00")
        if date_to:
            conditions.append("created_at <= ?")
            values.append(date_to + " 23:59:59")
        where = self.where_clause(conditions)
        if "page" in params:
            page, page_limit = self.log_pagination(params)
            total = query_one(
                f"SELECT COUNT(*) AS n FROM permission_audit{where}", tuple(values)
            )["n"]
            rows = query(
                f"""SELECT id, actor_kind, actor_name, target_id, target_name,
                           action, detail, created_at
                    FROM permission_audit{where}
                    ORDER BY id DESC LIMIT ? OFFSET ?""",
                tuple(values) + (page_limit, (page - 1) * page_limit),
            )
            actions = query(
                """SELECT action, COUNT(*) AS count FROM permission_audit
                   GROUP BY action ORDER BY count DESC, action"""
            )
            self.send_json(
                200,
                {
                    "items": rows,
                    "total": total,
                    "page": page,
                    "limit": page_limit,
                    "actions": actions,
                },
            )
            return
        try:
            limit = int((params.get("limit") or ["100"])[0])
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 500))
        rows = query(
            f"""SELECT id, actor_kind, actor_name, target_id, target_name,
                       action, detail, created_at
                FROM permission_audit{where} ORDER BY id DESC LIMIT ?""",
            tuple(values) + (limit,),
        )
        self.send_json(200, rows)

    @staticmethod
    def log_param(params, key, default=""):
        return str((params.get(key) or [default])[0] or "").strip()

    def log_date_filters(self, params, include_ip=True):
        conditions = []
        values = []
        date_from = self.log_param(params, "date_from")
        date_to = self.log_param(params, "date_to")
        if date_from:
            conditions.append("created_at >= ?")
            values.append(date_from + " 00:00:00")
        if date_to:
            conditions.append("created_at <= ?")
            values.append(date_to + " 23:59:59")
        ip = self.log_param(params, "ip")
        if include_ip and ip:
            conditions.append("ip LIKE ?")
            values.append(f"%{ip}%")
        return conditions, values

    def log_pagination(self, params):
        try:
            page = max(1, int(self.log_param(params, "page", "1") or 1))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = int(self.log_param(params, "limit", "50") or 50)
        except (TypeError, ValueError):
            limit = 50
        return page, max(1, min(limit, 200))

    @staticmethod
    def where_clause(conditions):
        return (" WHERE " + " AND ".join(conditions)) if conditions else ""

    def activity_log_filters(self, params):
        conditions, values = self.log_date_filters(params)
        action = self.log_param(params, "action")
        if action:
            conditions.append("action = ?")
            values.append(action)
        user = self.log_param(params, "user")
        if user == "guest":
            conditions.append("actor_kind = 'guest'")
        elif user == "admin":
            conditions.append("actor_kind IN ('owner', 'admin')")
        elif user.isdigit():
            conditions.append("user_id = ?")
            values.append(int(user))
        keyword = self.log_param(params, "q")
        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                "(summary LIKE ? OR actor_name LIKE ? OR source_path LIKE ?)"
            )
            values.extend([like, like, like])
        return conditions, values

    def access_log_filters(self, params):
        conditions, values = self.log_date_filters(params)
        path_keyword = self.log_param(params, "path")
        if path_keyword:
            conditions.append("path LIKE ?")
            values.append(f"%{path_keyword}%")
        visitor = self.log_param(params, "visitor")
        if visitor == "guest":
            conditions.append("actor_kind = 'guest'")
        elif visitor == "user":
            conditions.append("actor_kind != 'guest'")
        return conditions, values

    def api_admin_logs_activity(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看日志。")
            return
        conditions, values = self.activity_log_filters(params)
        where = self.where_clause(conditions)
        page, limit = self.log_pagination(params)
        total = query_one(
            f"SELECT COUNT(*) AS n FROM activity_log{where}", tuple(values)
        )["n"]
        rows = query(
            f"""SELECT id, created_at, actor_kind, user_id, actor_name, action,
                       target_type, target_id, summary, ip, ip_region, source_path,
                       method, source_port, target_host, target_port, user_agent,
                       client_platform
                FROM activity_log{where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            tuple(values) + (limit, (page - 1) * limit),
        )
        actions = query(
            """SELECT action, COUNT(*) AS count FROM activity_log
               GROUP BY action ORDER BY count DESC, action"""
        )
        users = query(
            """SELECT user_id, actor_name, COUNT(*) AS count FROM activity_log
               WHERE user_id > 0 GROUP BY user_id
               ORDER BY count DESC, user_id LIMIT 100"""
        )
        self.send_json(
            200,
            {
                "items": rows,
                "total": total,
                "page": page,
                "limit": limit,
                "actions": actions,
                "users": users,
            },
        )

    def api_admin_logs_access(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看日志。")
            return
        conditions, values = self.access_log_filters(params)
        where = self.where_clause(conditions)
        page, limit = self.log_pagination(params)
        total = query_one(
            f"SELECT COUNT(*) AS n FROM access_log{where}", tuple(values)
        )["n"]
        rows = query(
            f"""SELECT id, created_at, actor_kind, user_id, actor_name, ip, ip_region,
                       path, status, referer, device, user_agent, method, source_port,
                       target_host, target_port, client_platform
                FROM access_log{where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            tuple(values) + (limit, (page - 1) * limit),
        )
        self.send_json(
            200, {"items": rows, "total": total, "page": page, "limit": limit}
        )

    def api_admin_logs_stats(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看日志。")
            return
        try:
            days = int(self.log_param(params, "days", "7") or 7)
        except (TypeError, ValueError):
            days = 7
        days = max(1, min(days, 30))
        today = date.today()
        today_like = today.isoformat() + "%"
        start = (today - timedelta(days=days - 1)).isoformat() + " 00:00:00"
        today_pv = query_one(
            "SELECT COUNT(*) AS n FROM access_log WHERE created_at LIKE ?",
            (today_like,),
        )["n"]
        today_uv = query_one(
            "SELECT COUNT(DISTINCT ip) AS n FROM access_log WHERE created_at LIKE ?",
            (today_like,),
        )["n"]
        today_messages = query_one(
            """SELECT COUNT(*) AS n FROM activity_log WHERE created_at LIKE ?
               AND action IN ('message_create', 'message_reply')""",
            (today_like,),
        )["n"]
        today_login_fail = query_one(
            """SELECT COUNT(*) AS n FROM activity_log
               WHERE created_at LIKE ? AND action = 'login_fail'""",
            (today_like,),
        )["n"]
        rows = query(
            """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS pv,
                      COUNT(DISTINCT ip) AS uv
               FROM access_log WHERE created_at >= ?
               GROUP BY day ORDER BY day""",
            (start,),
        )
        by_day = {row["day"]: row for row in rows}
        series = []
        for offset in range(days):
            day = (today - timedelta(days=days - 1 - offset)).isoformat()
            item = by_day.get(day) or {}
            series.append(
                {
                    "date": day,
                    "pv": int(item.get("pv") or 0),
                    "uv": int(item.get("uv") or 0),
                }
            )
        top_paths = query(
            """SELECT path, COUNT(*) AS count FROM access_log
               WHERE created_at >= ? GROUP BY path
               ORDER BY count DESC, path LIMIT 10""",
            (start,),
        )
        top_ips = query(
            """SELECT ip, ip_region, COUNT(*) AS count FROM access_log
               WHERE created_at >= ? AND ip IS NOT NULL AND ip != ''
               GROUP BY ip ORDER BY count DESC, ip LIMIT 10""",
            (start,),
        )
        self.send_json(
            200,
            {
                "today": {
                    "pv": today_pv,
                    "uv": today_uv,
                    "messages": today_messages,
                    "login_failed": today_login_fail,
                },
                "series": series,
                "top_paths": top_paths,
                "top_ips": top_ips,
                "retention_days": LOG_RETENTION_DAYS,
            },
        )

    def api_admin_logs_export(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以导出日志。")
            return
        kind = self.log_param(params, "kind", "activity") or "activity"
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        if kind == "access":
            conditions, values = self.access_log_filters(params)
            where = self.where_clause(conditions)
            rows = query(
                f"""SELECT created_at, actor_kind, actor_name, ip, ip_region, path,
                           status, referer, device, user_agent, method, source_port,
                           target_host, target_port, client_platform
                    FROM access_log{where} ORDER BY id DESC LIMIT 5000""",
                tuple(values),
            )
            writer.writerow(
                ["时间", "访客类型", "账号", "IP", "属地", "路径", "状态码", "来源页", "设备", "User-Agent", "方法", "源端口", "目标主机", "目标端口", "客户端平台"]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["created_at"],
                        "登录" if row["actor_kind"] != "guest" else "游客",
                        row["actor_name"] or "",
                        row["ip"] or "",
                        row["ip_region"] or "",
                        row["path"] or "",
                        row["status"],
                        row["referer"] or "",
                        row["device"] or "",
                        row["user_agent"] or "",
                        row["method"] or "",
                        row["source_port"] if row["source_port"] is not None else "",
                        row["target_host"] or "",
                        row["target_port"] if row["target_port"] is not None else "",
                        row["client_platform"] or "",
                    ]
                )
            download_name = f"errorjiang-访问日志-{today_text()}.csv"
        else:
            conditions, values = self.activity_log_filters(params)
            where = self.where_clause(conditions)
            rows = query(
                f"""SELECT created_at, actor_kind, actor_name, action, target_type,
                           target_id, summary, ip, ip_region, source_path, method,
                           source_port, target_host, target_port, user_agent,
                           client_platform
                    FROM activity_log{where} ORDER BY id DESC LIMIT 5000""",
                tuple(values),
            )
            writer.writerow(
                ["时间", "操作者类型", "操作者", "动作", "对象类型", "对象 ID", "摘要", "IP", "属地", "来源页面", "方法", "源端口", "目标主机", "目标端口", "User-Agent", "客户端平台"]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["created_at"],
                        row["actor_kind"] or "",
                        row["actor_name"] or "",
                        row["action"] or "",
                        row["target_type"] or "",
                        row["target_id"] if row["target_id"] is not None else "",
                        row["summary"] or "",
                        row["ip"] or "",
                        row["ip_region"] or "",
                        row["source_path"] or "",
                        row["method"] or "",
                        row["source_port"] if row["source_port"] is not None else "",
                        row["target_host"] or "",
                        row["target_port"] if row["target_port"] is not None else "",
                        row["user_agent"] or "",
                        row["client_platform"] or "",
                    ]
                )
            download_name = f"errorjiang-内容事件-{today_text()}.csv"
        self.send_csv(200, "\ufeff" + buffer.getvalue(), download_name)

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

    # ---------- 管理员登录密码（仅站长） ----------
    def api_admin_password(self, payload):
        if not self.is_owner():
            api_error(self, 403, "只有站长账号可以修改管理员登录密码。")
            return
        current = str(payload.get("current_password") or "")
        new_password = str(payload.get("new_password") or "")
        if not verify_password(current):
            self.log_activity(
                "password_change_fail",
                "修改管理员密码：当前密码不正确",
                actor={"kind": "guest", "username": "管理员"},
            )
            api_error(self, 401, "当前密码不正确。")
            return
        if len(new_password) < 8 or len(new_password) > 128:
            api_error(self, 400, "新密码长度需为 8-128 位。")
            return
        if new_password == current:
            api_error(self, 400, "新密码不能和当前密码相同。")
            return
        save_auth_password(new_password)
        # 同一账号其它设备上的管理员会话作废，当前这台继续用
        claims = verify_session_token(self.cookies().get(AUTH_COOKIE, "")) or {}
        execute(
            "DELETE FROM sessions WHERE kind = 'owner' AND sid <> ?",
            (str(claims.get("sid") or ""),),
        )
        write_audit(
            {"kind": "owner", "user_id": 0, "username": "管理员"},
            "password_change",
            f"管理员登录密码已修改（来源 {self.client_ip()}）",
        )
        self.log_activity(
            "password_change",
            "管理员登录密码已修改",
            actor={"kind": "owner", "username": "管理员"},
        )
        self.send_json(200, {"ok": True})

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
        claims = verify_session_token(self.cookies().get(AUTH_COOKIE, ""))
        if claims:
            delete_session(claims.get("sid"))
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
        if path.startswith("/s/"):
            self.serve_share_link(path[len("/s/") :].strip())
            return
        if path == "/login":
            if not AUTH_STATE.get("enabled") or self.session_valid():
                self.redirect(safe_next_path((query.get("next") or ["/"])[0]))
                return
            self.log_page_view(path)
            self.send_file("login.html")
            return
        if path == "/register":
            self.log_page_view(path)
            self.send_file("register.html")
            return
        if path == "/reporting":
            self.log_page_view(path)
            self.send_file("reporting.html")
            return
        if path == "/prompts":
            self.send_response(302)
            self.send_header("Location", "/workbench?view=prompts")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        legacy_redirect = legacy_subpage_redirect(path, query)
        if legacy_redirect:
            self.redirect(legacy_redirect)
            return
        if path == "/logout":
            claims = verify_session_token(self.cookies().get(AUTH_COOKIE, ""))
            if claims:
                delete_session(claims.get("sid"))
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", self.session_cookie_value("", 0))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not self.guard_request(path, "GET"):
            return
        try:
            if path.startswith("/agent-stickers/"):
                self.api_agent_sticker_file(path)
                return
            if path in PAGE_VIEW_PATHS:
                self.log_page_view(path)
            if path in ("/", "/index.html"):
                self.send_site("home")
            elif path == "/inventory":
                self.send_file("index.html")
            elif path == "/bookmarks":
                self.send_file("bookmarks.html")
            elif path == "/notes":
                self.send_file("notes.html")
            elif path == "/notes/read":
                self.send_file("note-read.html")
            elif path == "/finance":
                self.send_file("finance.html")
            elif path == "/aa":
                target = "/finance"
                if parsed.query:
                    target += "?" + parsed.query
                self.redirect(target)
                return
            elif path == "/messages":
                self.send_file("messages.html")
            elif path == "/workbench":
                self.send_file("workbench.html")
            elif path == "/agent":
                self.send_file("agent.html")
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
            elif path == "/books":
                self.send_file("books.html")
            elif path == "/downloads":
                self.send_file("downloads.html")
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
            elif path == "/api/site/upload-limits":
                self.api_site_upload_limits()
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
            elif path == "/api/site/messages/unread":
                self.api_site_messages_unread()
            elif path == "/api/site/messages/quota":
                self.api_site_message_quota()
            elif path == "/api/site/activity":
                self.api_site_activity()
            elif path == "/api/site/sidebar":
                self.api_site_sidebar()
            elif re.fullmatch(r"/api/site/message-files/\d+", path):
                self.api_site_message_file(path)
            elif path == "/api/moments":
                self.api_moments(query)
            elif path == "/api/site/moments/unread":
                self.api_site_moments_unread()
            elif path == "/api/site/notifications/summary":
                self.api_site_notification_summary()
            elif path == "/api/site/notifications/unread":
                self.api_site_notification_unread(query)
            elif path == "/api/recommendations":
                self.api_recommendations(query)
            elif path == "/api/map/poi-search":
                self.api_map_poi_search(query)
            elif path == "/api/map":
                self.api_map(query)
            elif path == "/api/admin/users":
                self.api_admin_users(query)
            elif path == "/api/admin/permissions":
                self.api_admin_permissions()
            elif path == "/api/admin/role-permissions":
                self.api_admin_role_permissions(query)
            elif path == "/api/admin/audit":
                self.api_admin_audit(query)
            elif path == "/api/admin/logs/activity":
                self.api_admin_logs_activity(query)
            elif path == "/api/admin/logs/access":
                self.api_admin_logs_access(query)
            elif path == "/api/admin/logs/stats":
                self.api_admin_logs_stats(query)
            elif path == "/api/admin/logs/export":
                self.api_admin_logs_export(query)
            elif path == "/api/admin/sensitive-words":
                self.api_admin_sensitive_words(query)
            elif path == "/api/admin/review":
                self.api_admin_review(query)
            elif path == "/api/agent/web/status":
                self.api_agent_web_status()
            elif path == "/api/agent/web/settings":
                self.api_agent_web_settings()
            elif path == "/api/agent/web/memories":
                self.api_agent_web_memories(query)
            elif path == "/api/agent/web/stickers":
                self.api_agent_web_stickers(query)
            elif path == "/api/admin/reports":
                self.api_admin_reports(query)
            elif path == "/api/admin/notify":
                self.api_admin_notify(query)
            elif path == "/api/admin/upload-limits":
                self.api_admin_upload_limits()
            elif path == "/api/references":
                self.api_reference_projects()
            elif re.fullmatch(r"/api/recommendations/\d+/icon", path):
                self.api_recommendation_icon(path)
            elif path == "/api/site/photos":
                self.api_site_photos(query)
            elif path == "/api/site/music":
                self.api_site_music(query)
            elif re.fullmatch(r"/api/site/music/\d+/stream", path):
                self.api_site_music_stream(int(path.split("/")[4]))
            elif re.fullmatch(r"/api/site/music/\d+/download", path):
                self.api_site_music_download(int(path.split("/")[4]))
            elif path == "/api/books":
                self.api_books(query)
            elif re.fullmatch(r"/api/books/\d+/download", path):
                self.api_book_download(int(path.split("/")[3]))
            elif path == "/api/site/links":
                self.api_site_links(query)
            elif path == "/api/prompts":
                self.api_prompts(query)
            elif path == "/api/notes":
                self.api_notes(query)
            elif path == "/api/aa/events":
                self.api_aa_events()
            elif path == "/api/aa/candidates":
                self.api_aa_candidates()
            elif re.fullmatch(r"/api/aa/events/\d+", path):
                self.api_aa_event_detail(int(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/api/notes/\d+/export\.html", path):
                self.api_note_export(path)
            elif re.fullmatch(r"/api/shared/notes/\d+", path):
                self.api_shared_note(int(path.split("/")[4]))
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

    def do_HEAD(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if not self.guard_request(path, "GET"):
            return
        try:
            if re.fullmatch(r"/api/site/music/\d+/stream", path):
                self.api_site_music_stream(int(path.split("/")[4]), head_only=True)
                return
            self.send_error(404)
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
            if path == "/api/agent/tool":
                self.api_agent_tool(payload, self.agent_request_identity())
            elif path == "/api/agent/web/chat":
                self.api_agent_web_chat(payload)
            elif path == "/api/agent/web/settings":
                self.api_agent_web_settings_save(payload)
            elif path == "/api/agent/web/memory-delete":
                self.api_agent_web_memory_delete(payload)
            elif path == "/api/agent/web/sticker-delete":
                self.api_agent_web_sticker_delete(payload)
            elif path == "/api/login":
                self.api_login(payload)
            elif path == "/api/member/login":
                self.api_login(payload, member_only=True)
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
            elif path == "/api/site/reports":
                self.api_site_report_create(payload)
            elif path == "/api/site/messages/seen":
                self.api_site_message_mark_seen()
            elif path == "/api/site/likes":
                self.api_site_like_toggle(payload)
            elif path == "/api/site/notifications/seen":
                self.api_site_notifications_seen(payload)
            elif path == "/api/moments":
                self.api_moment_create(payload)
            elif re.fullmatch(r"/api/moments/\d+/comments", path):
                self.api_moment_comment_create(
                    int(path.split("/")[3]), payload
                )
            elif path == "/api/map/categories":
                self.api_map_category_create(payload)
            elif path == "/api/map/places":
                self.api_map_place_create(payload)
            elif path == "/api/map/seen":
                self.api_map_mark_seen(payload)
            elif re.fullmatch(r"/api/map/places/\d+/photos", path):
                self.api_map_place_photo_upload(path, payload)
            elif path == "/api/map/import":
                self.api_map_import(payload)
            elif path == "/api/account/nickname":
                self.api_account_nickname(payload)
            elif path == "/api/admin/sensitive-words":
                self.api_admin_sensitive_word_add(payload)
            elif path == "/api/admin/role-permissions":
                self.api_admin_role_permission_set(payload)
            elif path == "/api/admin/sensitive-words/test":
                self.api_admin_sensitive_test(payload)
            elif path == "/api/admin/notify":
                self.api_admin_notify_save(payload)
            elif path == "/api/admin/password":
                self.api_admin_password(payload)
            elif path == "/api/admin/upload-limits":
                self.api_admin_upload_limits_save(payload)
            elif path == "/api/site/user-status":
                self.api_site_user_status_save(payload)
            elif path == "/api/admin/notify/test":
                self.api_admin_notify_test(payload)
            elif path == "/api/admin/share-links":
                self.api_admin_share_link_create(payload)
            elif path == "/api/admin/share-content":
                self.api_admin_share_content(payload)
            elif path == "/api/admin/review/approve-all":
                self.api_admin_review_all(payload)
            elif re.fullmatch(r"/api/admin/review/\d+", path):
                self.api_admin_review_action(path, payload)
            elif re.fullmatch(r"/api/admin/review-files/\d+", path):
                self.api_admin_review_file_action(path, payload)
            elif re.fullmatch(r"/api/admin/reports/\d+", path):
                self.api_admin_report_action(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/status", path):
                self.api_admin_user_status(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/permissions", path):
                self.api_admin_user_permission(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/message-limit", path):
                self.api_admin_user_message_limit(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/nickname", path):
                self.api_admin_user_nickname(path, payload)
            elif re.fullmatch(r"/api/admin/users/\d+/password", path):
                self.api_admin_user_password(path, payload)
            elif path == "/api/recommendations":
                self.api_recommendation_create(payload)
            elif path == "/api/references":
                self.api_reference_create(payload)
            elif path == "/api/recommendations/images":
                self.api_recommendation_image_upload(payload)
            elif path == "/api/site/photos":
                self.api_site_photo_upload(payload)
            elif path == "/api/site/music":
                self.api_site_music_create(payload)
            elif path == "/api/site/music/upload":
                self.api_site_music_upload(payload)
            elif path == "/api/books/upload":
                self.api_book_upload(payload)
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
            elif path == "/api/aa/events":
                self.api_aa_event_create(payload)
            elif re.fullmatch(r"/api/aa/events/\d+/expenses", path):
                self.api_aa_expense_create(
                    int(path.split("/")[4]), payload
                )
            elif re.fullmatch(r"/api/aa/events/\d+/receipts", path):
                self.api_aa_receipt_upload(
                    int(path.split("/")[4]), payload
                )
            elif re.fullmatch(r"/api/aa/events/\d+/qr", path):
                self.api_aa_receipt_upload(
                    int(path.split("/")[4]), payload
                )
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
            elif re.fullmatch(r"/api/aa/events/\d+", path):
                self.api_aa_event_update(int(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/api/aa/expenses/\d+", path):
                self.api_aa_expense_update(int(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/api/books/\d+", path):
                self.api_book_item(path)
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
            elif re.fullmatch(r"/api/references/\d+", path):
                self.api_reference_item(path)
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
            elif re.fullmatch(r"/api/site/moment-comments/\d+", path):
                self.api_moment_comment_delete(int(path.rsplit("/", 1)[1]))
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
            elif re.fullmatch(r"/api/references/\d+", path):
                self.api_reference_item(path)
            elif re.fullmatch(r"/api/site/links/\d+", path):
                self.api_site_link_delete(path)
            elif re.fullmatch(r"/api/prompts/\d+", path):
                self.api_prompt_item(path)
            elif re.fullmatch(r"/api/books/\d+", path):
                self.api_book_item(path)
            elif re.fullmatch(r"/api/notes/images/\d+", path):
                self.api_note_image_delete(path)
            elif re.fullmatch(r"/api/notes/\d+", path):
                self.api_note_item(path)
            elif re.fullmatch(r"/api/aa/events/\d+/receipts/\d+", path):
                parts = path.split("/")
                self.api_aa_receipt_delete(int(parts[4]), int(parts[6]))
            elif re.fullmatch(r"/api/aa/events/\d+/qr", path):
                self.api_aa_receipt_delete(int(path.split("/")[4]), None)
            elif re.fullmatch(r"/api/aa/events/\d+", path):
                self.api_aa_event_delete(int(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/api/aa/expenses/\d+", path):
                self.api_aa_expense_delete(int(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/api/workbench/assets/\d+", path):
                self.api_workbench_asset_item(path)
            elif re.fullmatch(r"/api/workbench/repairs/\d+", path):
                self.api_workbench_repair_item(path)
            else:
                api_error(self, 404, "接口不存在。")
        except Exception as exc:
            api_error(self, 500, f"服务器错误：{exc}")

    def aa_identity_user_id(self, identity):
        return int((identity or {}).get("user_id") or 0)

    def aa_identity_is_admin(self, identity):
        return bool(identity and identity.get("kind") in ("owner", "admin"))

    def aa_user_has_access(self, user_id):
        return user_has_permission(user_id, ADMIN_PERMISSION) or user_has_permission(
            user_id, AA_PERMISSION
        )

    def aa_event_member_ids(self, event_id):
        return {
            int(row["user_id"])
            for row in query(
                "SELECT user_id FROM aa_members WHERE event_id = ?", (event_id,)
            )
        }

    def aa_event_members(self, event_id):
        rows = query(
            """SELECT user_id, joined_at FROM aa_members
               WHERE event_id = ? ORDER BY joined_at, user_id""",
            (event_id,),
        )
        user_ids = [int(row["user_id"]) for row in rows if int(row["user_id"]) != 0]
        users = {}
        if user_ids:
            placeholders = ",".join("?" for _ in user_ids)
            users = {
                int(row["id"]): row
                for row in query(
                    f"""SELECT id, username, nickname FROM users
                        WHERE id IN ({placeholders})""",
                    tuple(user_ids),
                )
            }
        result = []
        for row in rows:
            user_id = int(row["user_id"])
            user = users.get(user_id) or {}
            name = (
                "管理员"
                if user_id == 0
                else str(user.get("nickname") or user.get("username") or f"用户 {user_id}")
            )
            result.append(
                {
                    "user_id": user_id,
                    "username": str(user.get("username") or ""),
                    "name": name,
                    "joined_at": row["joined_at"],
                }
            )
        return result

    def aa_event_payload(self, event_id, identity, include_expenses=True):
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (event_id,))
        if not event:
            return None
        current_user_id = self.aa_identity_user_id(identity)
        is_admin = self.aa_identity_is_admin(identity)
        member_ids = self.aa_event_member_ids(event_id)
        if not is_admin and current_user_id not in member_ids:
            return None
        members = self.aa_event_members(event_id)
        expense_rows = query(
            """SELECT id, user_id, amount_cents, note, created_at, updated_at
               FROM aa_expenses WHERE event_id = ? ORDER BY id DESC""",
            (event_id,),
        )
        split_rows = query(
            """SELECT s.expense_id, s.user_id
               FROM aa_expense_splits s
               JOIN aa_expenses e ON e.id = s.expense_id
               WHERE e.event_id = ?
               ORDER BY s.expense_id, s.user_id""",
            (event_id,),
        )
        splits_by_expense = {}
        for split in split_rows:
            splits_by_expense.setdefault(int(split["expense_id"]), []).append(
                int(split["user_id"])
            )
        names = {int(item["user_id"]): item["name"] for item in members}
        for expense in expense_rows:
            expense_id = int(expense["id"])
            split_user_ids = splits_by_expense.get(expense_id) or list(member_ids)
            expense["split_user_ids"] = sorted(
                split_user_ids,
                key=lambda user_id: (
                    next(
                        (
                            index
                            for index, member in enumerate(members)
                            if int(member["user_id"]) == int(user_id)
                        ),
                        len(members),
                    )
                ),
            )
            expense["split_names"] = [
                names.get(int(user_id), f"用户 {user_id}")
                for user_id in expense["split_user_ids"]
            ]
        expenses = []
        if include_expenses:
            expenses = expense_rows
            can_manage = is_admin or int(event["owner_user_id"]) == current_user_id
            for expense in expenses:
                user_id = int(expense["user_id"])
                expense["user_name"] = names.get(user_id, f"用户 {user_id}")
                expense["can_edit"] = bool(
                    can_manage or user_id == current_user_id
                )
        receipts_by_user = {
            int(row["user_id"]): row
            for row in query(
                """SELECT user_id, qr_path, qr_name, updated_at
                   FROM aa_receipts WHERE event_id = ?""",
                (event_id,),
            )
        }
        receipts = []
        for member in members:
            user_id = int(member["user_id"])
            receipt = receipts_by_user.get(user_id) or {}
            receipts.append(
                {
                    "user_id": user_id,
                    "name": member["name"],
                    "url": (
                        "/site-files/" + str(receipt["qr_path"])
                        if receipt.get("qr_path")
                        else ""
                    ),
                    "file_name": receipt.get("qr_name") or "",
                    "updated_at": receipt.get("updated_at") or "",
                    "can_edit": bool(is_admin or user_id == current_user_id),
                    "is_self": user_id == current_user_id,
                }
            )
        settlement = aa_settlement(members, expense_rows)
        owner_user_id = int(event["owner_user_id"])
        owner_name = next(
            (
                item["name"]
                for item in members
                if int(item["user_id"]) == owner_user_id
            ),
            "管理员" if owner_user_id == 0 else f"用户 {owner_user_id}",
        )
        my_balance = next(
            (
                int(item["balance_cents"])
                for item in settlement["members"]
                if int(item["user_id"]) == current_user_id
            ),
            0,
        )
        return {
            "id": int(event["id"]),
            "title": event["title"],
            "owner_user_id": owner_user_id,
            "owner_name": owner_name,
            "created_at": event["created_at"],
            "updated_at": event["updated_at"],
            "member_count": len(members),
            "members": settlement["members"],
            "expenses": expenses,
            "transfers": settlement["transfers"],
            "total_cents": settlement["total_cents"],
            "my_balance_cents": my_balance,
            "current_user_id": current_user_id,
            "is_admin": is_admin,
            "can_manage": bool(is_admin or owner_user_id == current_user_id),
            "can_add_expense": current_user_id in member_ids,
            "receipts": receipts,
        }

    def api_aa_events(self):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        current_user_id = self.aa_identity_user_id(identity)
        if self.aa_identity_is_admin(identity):
            rows = query(
                """SELECT id FROM aa_events
                   ORDER BY updated_at DESC, id DESC"""
            )
        else:
            rows = query(
                """SELECT e.id FROM aa_events e
                   JOIN aa_members m ON m.event_id = e.id
                   WHERE m.user_id = ?
                   ORDER BY e.updated_at DESC, e.id DESC""",
                (current_user_id,),
            )
        events = []
        for row in rows:
            payload = self.aa_event_payload(int(row["id"]), identity, False)
            if not payload:
                continue
            events.append(
                {
                    "id": payload["id"],
                    "title": payload["title"],
                    "owner_name": payload["owner_name"],
                    "updated_at": payload["updated_at"],
                    "member_count": payload["member_count"],
                    "total_cents": payload["total_cents"],
                    "my_balance_cents": payload["my_balance_cents"],
                    "can_manage": payload["can_manage"],
                }
            )
        self.send_json(
            200,
            {
                "events": events,
                "current_user_id": current_user_id,
                "is_admin": self.aa_identity_is_admin(identity),
            },
        )

    def api_aa_candidates(self):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        candidates = [
            {"id": 0, "username": "admin", "name": "管理员"},
        ]
        for row in query(
            """SELECT id, username, nickname FROM users
               WHERE status = 'approved'
               ORDER BY COALESCE(NULLIF(nickname, ''), username) COLLATE NOCASE"""
        ):
            if not self.aa_user_has_access(int(row["id"])):
                continue
            candidates.append(
                {
                    "id": int(row["id"]),
                    "username": row["username"],
                    "name": row.get("nickname") or row["username"],
                }
            )
        self.send_json(
            200,
            {
                "users": candidates,
                "current_user_id": self.aa_identity_user_id(identity),
            },
        )

    def aa_validated_title(self, payload):
        title = str((payload or {}).get("title") or "").strip()
        if not title:
            api_error(self, 400, "请填写账目名称。")
            return ""
        if len(title) > AA_EVENT_TITLE_MAX_CHARS:
            api_error(
                self,
                400,
                f"账目名称不能超过 {AA_EVENT_TITLE_MAX_CHARS} 字。",
            )
            return ""
        return title

    def aa_validated_member_ids(self, identity, raw_member_ids, event_id=None):
        if not isinstance(raw_member_ids, list):
            api_error(self, 400, "参与人格式不正确。")
            return None
        ids = set()
        for raw in raw_member_ids:
            if isinstance(raw, bool):
                api_error(self, 400, "参与人格式不正确。")
                return None
            try:
                user_id = int(raw)
            except (TypeError, ValueError):
                api_error(self, 400, "参与人格式不正确。")
                return None
            if user_id != 0:
                user = query_one(
                    "SELECT id, status FROM users WHERE id = ?", (user_id,)
                )
                if not user or user.get("status") != "approved":
                    api_error(self, 400, "有参与人账号不存在或未通过审核。")
                    return None
                if not self.aa_user_has_access(user_id):
                    api_error(self, 400, "有参与人还没有被授予计算器权限。")
                    return None
            ids.add(user_id)
        if event_id is None:
            ids.add(self.aa_identity_user_id(identity))
        else:
            event = query_one("SELECT owner_user_id FROM aa_events WHERE id = ?", (event_id,))
            if event:
                ids.add(int(event["owner_user_id"]))
        if len(ids) < 2:
            api_error(self, 400, "至少需要两位参与人。")
            return None
        if len(ids) > AA_EVENT_MEMBER_MAX:
            api_error(self, 400, f"一次最多 {AA_EVENT_MEMBER_MAX} 位参与人。")
            return None
        return sorted(ids)

    def api_aa_event_create(self, payload):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        title = self.aa_validated_title(payload)
        if not title:
            return
        member_ids = self.aa_validated_member_ids(
            identity, (payload or {}).get("member_ids")
        )
        if member_ids is None:
            return
        stamp = now_text()

        def create(conn):
            cursor = conn.execute(
                """INSERT INTO aa_events
                       (title, owner_user_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (title, self.aa_identity_user_id(identity), stamp, stamp),
            )
            event_id = int(cursor.lastrowid)
            conn.executemany(
                """INSERT INTO aa_members (event_id, user_id, joined_at)
                   VALUES (?, ?, ?)""",
                [(event_id, user_id, stamp) for user_id in member_ids],
            )
            return event_id

        event_id = transaction(create)
        self.log_activity(
            "aa_event_create",
            f"创建计算器账目：{title}",
            target_type="aa_event",
            target_id=event_id,
        )
        self.send_json(
            200, {"ok": True, "event": self.aa_event_payload(event_id, identity)}
        )

    def api_aa_event_detail(self, event_id):
        identity = self.session_identity()
        payload = self.aa_event_payload(event_id, identity)
        if not payload:
            api_error(self, 404, "账目不存在或你没有访问权限。")
            return
        self.send_json(200, payload)

    def api_aa_event_update(self, event_id):
        identity = self.session_identity()
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (event_id,))
        if not event:
            api_error(self, 404, "账目不存在。")
            return
        current_user_id = self.aa_identity_user_id(identity)
        if not (
            self.aa_identity_is_admin(identity)
            or int(event["owner_user_id"]) == current_user_id
        ):
            api_error(self, 403, "只有发起人可以修改参与人。")
            return
        payload = get_payload(self)
        if payload is None:
            return
        title = self.aa_validated_title(payload)
        if not title:
            return
        raw_member_ids = payload.get("member_ids")
        member_ids = self.aa_validated_member_ids(
            identity, raw_member_ids, event_id=event_id
        )
        if member_ids is None:
            return
        existing_ids = self.aa_event_member_ids(event_id)
        removed_ids = existing_ids - set(member_ids)
        for user_id in removed_ids:
            count = query_one(
                """SELECT COUNT(*) AS n
                   FROM aa_expenses e
                   WHERE e.event_id = ?
                     AND (
                         e.user_id = ?
                         OR EXISTS (
                             SELECT 1 FROM aa_expense_splits s
                             WHERE s.expense_id = e.id AND s.user_id = ?
                         )
                     )""",
                (event_id, user_id, user_id),
            )["n"]
            if count:
                api_error(self, 400, "已有费用记录的参与人不能移除。")
                return
        stamp = now_text()

        def update(conn):
            conn.execute(
                "UPDATE aa_events SET title = ?, updated_at = ? WHERE id = ?",
                (title, stamp, event_id),
            )
            conn.execute("DELETE FROM aa_members WHERE event_id = ?", (event_id,))
            conn.executemany(
                """INSERT INTO aa_members (event_id, user_id, joined_at)
                   VALUES (?, ?, ?)""",
                [(event_id, user_id, stamp) for user_id in member_ids],
            )

        transaction(update)
        self.log_activity(
            "aa_event_update",
            f"修改计算器账目：{title}",
            target_type="aa_event",
            target_id=event_id,
        )
        self.send_json(
            200, {"ok": True, "event": self.aa_event_payload(event_id, identity)}
        )

    def api_aa_event_delete(self, event_id):
        identity = self.session_identity()
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (event_id,))
        if not event:
            api_error(self, 404, "账目不存在。")
            return
        current_user_id = self.aa_identity_user_id(identity)
        if not (
            self.aa_identity_is_admin(identity)
            or int(event["owner_user_id"]) == current_user_id
        ):
            api_error(self, 403, "只有发起人可以删除这个账目。")
            return
        receipt_paths = [
            row["qr_path"]
            for row in query(
                "SELECT qr_path FROM aa_receipts WHERE event_id = ?",
                (event_id,),
            )
            if row.get("qr_path")
        ]
        if event.get("qr_path"):
            receipt_paths.append(event["qr_path"])

        def remove(conn):
            conn.execute(
                """DELETE FROM aa_expense_splits
                   WHERE expense_id IN (
                       SELECT id FROM aa_expenses WHERE event_id = ?
                   )""",
                (event_id,),
            )
            conn.execute("DELETE FROM aa_receipts WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM aa_expenses WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM aa_members WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM aa_events WHERE id = ?", (event_id,))

        transaction(remove)
        for receipt_path in set(receipt_paths):
            remove_data_file(receipt_path)
        self.log_activity(
            "aa_event_delete",
            f"删除计算器账目：{event['title']}",
            target_type="aa_event",
            target_id=event_id,
        )
        self.send_json(200, {"ok": True})

    def aa_member_event(self, event_id):
        identity = self.session_identity()
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (event_id,))
        if not event:
            api_error(self, 404, "账目不存在。")
            return None, None
        member_ids = self.aa_event_member_ids(event_id)
        current_user_id = self.aa_identity_user_id(identity)
        if current_user_id not in member_ids:
            api_error(self, 403, "只有账目成员可以录入费用。")
            return None, None
        return event, identity

    def aa_validated_split_ids(self, event_id, raw_split_ids):
        member_ids = self.aa_event_member_ids(event_id)
        if raw_split_ids is None:
            return sorted(member_ids)
        if not isinstance(raw_split_ids, list):
            api_error(self, 400, "分摊人格式不正确。")
            return None
        split_ids = set()
        for raw in raw_split_ids:
            if isinstance(raw, bool):
                api_error(self, 400, "分摊人格式不正确。")
                return None
            try:
                user_id = int(raw)
            except (TypeError, ValueError):
                api_error(self, 400, "分摊人格式不正确。")
                return None
            if user_id not in member_ids:
                api_error(self, 400, "分摊人必须是当前账目成员。")
                return None
            split_ids.add(user_id)
        if not split_ids:
            api_error(self, 400, "请至少选择一位分摊人。")
            return None
        return sorted(split_ids)

    def api_aa_expense_create(self, event_id, payload):
        event, identity = self.aa_member_event(event_id)
        if not event:
            return
        amount_cents = aa_amount_cents((payload or {}).get("amount_cents"))
        if amount_cents is None:
            api_error(self, 400, "金额需大于 0，且不超过 1,000,000 元。")
            return
        note = str((payload or {}).get("note") or "").strip()
        if len(note) > AA_EXPENSE_NOTE_MAX_CHARS:
            api_error(
                self,
                400,
                f"备注不能超过 {AA_EXPENSE_NOTE_MAX_CHARS} 字。",
            )
            return
        split_user_ids = self.aa_validated_split_ids(
            event_id, (payload or {}).get("split_user_ids")
        )
        if split_user_ids is None:
            return
        stamp = now_text()

        def create(conn):
            cursor = conn.execute(
                """INSERT INTO aa_expenses
                       (event_id, user_id, amount_cents, note, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    self.aa_identity_user_id(identity),
                    amount_cents,
                    note,
                    stamp,
                    stamp,
                ),
            )
            expense_id = int(cursor.lastrowid)
            conn.executemany(
                """INSERT INTO aa_expense_splits (expense_id, user_id)
                   VALUES (?, ?)""",
                [(expense_id, user_id) for user_id in split_user_ids],
            )
            return expense_id

        expense_id = transaction(create)
        execute(
            "UPDATE aa_events SET updated_at = ? WHERE id = ?", (stamp, event_id)
        )
        self.log_activity(
            "aa_expense_create",
            f"在计算器账目「{event['title']}」录入费用",
            target_type="aa_event",
            target_id=event_id,
        )
        self.send_json(
            200,
            {
                "ok": True,
                "expense_id": expense_id,
                "event": self.aa_event_payload(event_id, identity),
            },
        )

    def api_aa_expense_update(self, expense_id):
        identity = self.session_identity()
        expense = query_one("SELECT * FROM aa_expenses WHERE id = ?", (expense_id,))
        if not expense:
            api_error(self, 404, "费用记录不存在。")
            return
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (expense["event_id"],))
        current_user_id = self.aa_identity_user_id(identity)
        if not (
            self.aa_identity_is_admin(identity)
            or int(event["owner_user_id"]) == current_user_id
            or int(expense["user_id"]) == current_user_id
        ):
            api_error(self, 403, "只能修改自己的费用记录。")
            return
        payload = get_payload(self)
        if payload is None:
            return
        amount_cents = aa_amount_cents(payload.get("amount_cents"))
        if amount_cents is None:
            api_error(self, 400, "金额需大于 0，且不超过 1,000,000 元。")
            return
        note = str(payload.get("note") or "").strip()
        if len(note) > AA_EXPENSE_NOTE_MAX_CHARS:
            api_error(
                self,
                400,
                f"备注不能超过 {AA_EXPENSE_NOTE_MAX_CHARS} 字。",
            )
            return
        split_user_ids = self.aa_validated_split_ids(
            expense["event_id"], payload.get("split_user_ids")
        )
        if split_user_ids is None:
            return
        stamp = now_text()

        def update(conn):
            conn.execute(
                """UPDATE aa_expenses
                   SET amount_cents = ?, note = ?, updated_at = ?
                   WHERE id = ?""",
                (amount_cents, note, stamp, expense_id),
            )
            conn.execute(
                "DELETE FROM aa_expense_splits WHERE expense_id = ?",
                (expense_id,),
            )
            conn.executemany(
                """INSERT INTO aa_expense_splits (expense_id, user_id)
                   VALUES (?, ?)""",
                [(expense_id, user_id) for user_id in split_user_ids],
            )

        transaction(update)
        execute(
            "UPDATE aa_events SET updated_at = ? WHERE id = ?",
            (stamp, expense["event_id"]),
        )
        self.send_json(
            200,
            {
                "ok": True,
                "event": self.aa_event_payload(expense["event_id"], identity),
            },
        )

    def api_aa_expense_delete(self, expense_id):
        identity = self.session_identity()
        expense = query_one("SELECT * FROM aa_expenses WHERE id = ?", (expense_id,))
        if not expense:
            api_error(self, 404, "费用记录不存在。")
            return
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (expense["event_id"],))
        current_user_id = self.aa_identity_user_id(identity)
        if not (
            self.aa_identity_is_admin(identity)
            or int(event["owner_user_id"]) == current_user_id
            or int(expense["user_id"]) == current_user_id
        ):
            api_error(self, 403, "只能删除自己的费用记录。")
            return
        stamp = now_text()

        def remove(conn):
            conn.execute(
                "DELETE FROM aa_expense_splits WHERE expense_id = ?",
                (expense_id,),
            )
            conn.execute("DELETE FROM aa_expenses WHERE id = ?", (expense_id,))

        transaction(remove)
        execute(
            "UPDATE aa_events SET updated_at = ? WHERE id = ?",
            (stamp, expense["event_id"]),
        )
        self.send_json(
            200,
            {
                "ok": True,
                "event": self.aa_event_payload(expense["event_id"], identity),
            },
        )

    def aa_receipt_target_user_id(self, event_id, identity, raw_user_id):
        current_user_id = self.aa_identity_user_id(identity)
        member_ids = self.aa_event_member_ids(event_id)
        if raw_user_id in (None, ""):
            target_user_id = current_user_id
        else:
            try:
                target_user_id = int(raw_user_id)
            except (TypeError, ValueError):
                api_error(self, 400, "收款码所属账号不正确。")
                return None
        if target_user_id not in member_ids:
            api_error(self, 400, "收款码只能添加到当前账目成员。")
            return None
        if target_user_id != current_user_id and not self.aa_identity_is_admin(identity):
            api_error(self, 403, "只能管理自己的收款码。")
            return None
        return target_user_id

    def api_aa_receipt_upload(self, event_id, payload):
        identity = self.session_identity()
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (event_id,))
        if not event:
            api_error(self, 404, "账目不存在。")
            return
        target_user_id = self.aa_receipt_target_user_id(
            event_id, identity, (payload or {}).get("user_id")
        )
        if target_user_id is None:
            return
        name = os.path.basename(str((payload or {}).get("name") or "receipt.png"))
        extension = os.path.splitext(name)[1].lower()
        if extension not in MESSAGE_IMAGE_EXTENSIONS:
            api_error(self, 400, "只支持 png、jpg、jpeg、gif、webp、bmp 图片。")
            return
        try:
            raw = base64.b64decode(
                str((payload or {}).get("data_base64") or ""), validate=True
            )
        except Exception:
            api_error(self, 400, "图片数据无效。")
            return
        if not raw:
            api_error(self, 400, "图片内容为空。")
            return
        if len(raw) > AA_QR_MAX_BYTES:
            api_error(self, 400, "收款码图片不能超过 5MB。")
            return
        try:
            relative = self.save_data_file(
                raw, name, "aa_qr", max_bytes=AA_QR_MAX_BYTES
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        existing = query_one(
            """SELECT qr_path FROM aa_receipts
               WHERE event_id = ? AND user_id = ?""",
            (event_id, target_user_id),
        )
        stamp = now_text()
        execute(
            """INSERT INTO aa_receipts
                   (event_id, user_id, qr_path, qr_name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id, user_id) DO UPDATE SET
                   qr_path = excluded.qr_path,
                   qr_name = excluded.qr_name,
                   updated_at = excluded.updated_at""",
            (event_id, target_user_id, relative, name, stamp, stamp),
        )
        execute(
            "UPDATE aa_events SET updated_at = ? WHERE id = ?",
            (stamp, event_id),
        )
        if existing and existing.get("qr_path"):
            remove_data_file(existing["qr_path"])
        self.send_json(
            200,
            {
                "ok": True,
                "url": "/site-files/" + relative,
                "event": self.aa_event_payload(event_id, identity),
            },
        )

    def api_aa_receipt_delete(self, event_id, target_user_id):
        identity = self.session_identity()
        event = query_one("SELECT * FROM aa_events WHERE id = ?", (event_id,))
        if not event:
            api_error(self, 404, "账目不存在。")
            return
        target_user_id = self.aa_receipt_target_user_id(
            event_id, identity, target_user_id
        )
        if target_user_id is None:
            return
        receipt = query_one(
            """SELECT qr_path FROM aa_receipts
               WHERE event_id = ? AND user_id = ?""",
            (event_id, target_user_id),
        )
        if not receipt:
            api_error(self, 404, "还没有设置收款码。")
            return
        execute(
            "DELETE FROM aa_receipts WHERE event_id = ? AND user_id = ?",
            (event_id, target_user_id),
        )
        execute(
            "UPDATE aa_events SET updated_at = ? WHERE id = ?",
            (now_text(), event_id),
        )
        remove_data_file(receipt.get("qr_path"))
        self.send_json(
            200,
            {
                "ok": True,
                "event": self.aa_event_payload(event_id, identity),
            },
        )

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
        self.log_activity(
            "project_create",
            f"新建项目：{name}",
            target_type="project",
            target_id=new_id,
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
            current = query_one("SELECT name FROM projects WHERE id = ?", (item_id,))
            execute("DELETE FROM projects WHERE id = ?", (item_id,))
            self.log_activity(
                "project_delete",
                f"删除项目：{(current or {}).get('name') or item_id}",
                target_type="project",
                target_id=item_id,
            )
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
        self.log_activity(
            "project_update",
            f"编辑项目：{name}",
            target_type="project",
            target_id=item_id,
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
                stock_quantity = finite_number(payload["stock_quantity"], "库存数量")
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
            min_stock_value = finite_number(payload.get("min_stock") or 0, "最低库存")
        except ValueError as exc:
            api_error(self, 400, str(exc))
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
                    min_stock_value,
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
                new_stock = finite_number(payload["stock_quantity"], "库存数量")
            except (TypeError, ValueError):
                api_error(self, 400, "库存数量格式不正确。")
                return
            if new_stock < 0:
                api_error(self, 400, "库存数量不能小于 0。")
                return
        try:
            min_stock_value = finite_number(payload.get("min_stock") or 0, "最低库存")
        except ValueError as exc:
            api_error(self, 400, str(exc))
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
                    min_stock_value,
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
                upload_limit("part_image")["max_file_bytes"],
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        self.send_json(200, {"image_path": relative})

    def send_data_file(
        self,
        relative,
        download_name=None,
        allow_range=False,
        head_only=False,
    ):
        relative = normalized_data_relative(relative)
        if not relative or relative == ".":
            api_error(self, 404, "文件不存在。")
            return
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
        if range_header.startswith("bytes=") and (allow_range or not download_name):
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
                body = b""
                if not head_only:
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
                if download_name:
                    encoded_name = quote(os.path.basename(download_name))
                    self.send_header(
                        "Content-Disposition",
                        f"attachment; filename*=UTF-8''{encoded_name}",
                    )
                self.send_header(
                    "Content-Length",
                    str(length if head_only else len(body)),
                )
                self.send_header("Cache-Control", cache_control)
                self.send_header("ETag", etag)
                self.end_headers()
                if not head_only:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except OSError:
                api_error(self, 404, "文件不存在。")
            return
        if head_only:
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
            self.send_header("Content-Length", str(total_size))
            self.send_header("Cache-Control", cache_control)
            self.send_header("ETag", etag)
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
            raise ValueError(f"文件不能超过 {format_upload_limit_bytes(max_bytes)}。")
        name = os.path.basename(file_name or "file")
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        if not name:
            name = "file.bin"
        target_dir = DATA_DIR / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        relative = f"{folder}/{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}_{name}"
        (DATA_DIR / relative).write_bytes(raw)
        return relative

    def save_site_file(self, data_base64, file_name, folder, max_bytes=20 * 1024 * 1024):
        if not data_base64:
            raise ValueError("没有文件数据。")
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception:
            raise ValueError("文件数据不是有效的 base64。")
        return self.save_data_file(raw, file_name, folder, max_bytes=max_bytes)

    def site_message_files_map(self, message_ids):
        """
        按留言 ID 分组返回附件，供列表接口一次性取回。
        游客也能看到留言里的图片，非图片附件只给一个「登录后可查看」的锁定占位。
        """
        if not message_ids:
            return {}
        identity = self.session_identity()
        viewer_signed_in = identity is not None
        viewer_id = None
        if identity:
            viewer_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        placeholders = ",".join("?" for _ in message_ids)
        rows = query(
            f"""SELECT f.id, f.message_id, f.file_name, f.file_path, f.file_size,
                       f.mime_type, f.status, f.uploaded_by,
                       m.status AS message_status, m.user_id AS message_user_id
                FROM site_message_files f
                LEFT JOIN site_messages m ON m.id = f.message_id
                WHERE f.message_id IN ({placeholders})
                ORDER BY f.id""",
            tuple(message_ids),
        )
        is_admin = self.is_admin()
        grouped = {}
        for row in rows:
            extension = os.path.splitext(row.get("file_name") or "")[1].lower()
            file_status = row.get("status") or "approved"
            message_status = row.get("message_status") or "approved"
            approved = file_status == "approved" and message_status == "approved"
            owned = (
                viewer_id is not None
                and (
                    row.get("uploaded_by") == viewer_id
                    or row.get("message_user_id") == viewer_id
                )
            )
            visible = approved or is_admin or owned
            is_image = extension in MESSAGE_IMAGE_EXTENSIONS
            entry = {
                "id": row["id"],
                "status": file_status,
                "message_status": message_status,
                "is_image": is_image,
                "visible": visible,
                "can_save": bool(is_admin or owned),
                "locked": False,
            }
            if visible and (viewer_signed_in or is_image):
                entry.update(
                    {
                        "file_name": row["file_name"],
                        "file_size": row["file_size"],
                        "mime_type": row["mime_type"],
                        "url": f"/api/site/message-files/{row['id']}",
                        "pending": not approved,
                    }
                )
            elif visible:
                # 游客：图片之外的附件只给占位，想看内容要登录
                entry.update(
                    {
                        "file_name": row["file_name"],
                        "file_size": row["file_size"],
                        "mime_type": row["mime_type"],
                        "locked": True,
                    }
                )
            grouped.setdefault(row["message_id"], []).append(entry)
        return grouped

    def message_display_name(self, row, authors, viewer_signed_in):
        """留言展示名：游客只看到脱敏用户名。"""
        user_id = row.get("user_id")
        if user_id is None:
            return str(row.get("nickname") or "匿名")[:30]
        if user_id == 0:
            return "管理员"
        user = authors.get(user_id)
        username = str((user or {}).get("username") or "").strip()
        if username:
            return username[:32] if viewer_signed_in else mask_username(username)
        return str(row.get("nickname") or "").strip()[:16] or "普通用户"

    def message_daily_used(self, user_id):
        """统计该账号今天（服务器本地日期）已发布的留言和回复数量。"""
        start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        row = query_one(
            "SELECT COUNT(*) AS n FROM site_messages WHERE user_id = ? AND created_at >= ?",
            (user_id, start),
        )
        return int(row["n"] if row else 0)

    def message_limit_for_user(self, user_id):
        """该账号每天的留言上限；没单独设置时用全局默认 9 条。"""
        if user_id in (None, 0):
            return MESSAGE_DAILY_LIMIT
        row = query_one(
            "SELECT message_daily_limit FROM users WHERE id = ?", (user_id,)
        )
        value = row.get("message_daily_limit") if row else None
        if value is None:
            return MESSAGE_DAILY_LIMIT
        try:
            return max(0, min(999, int(value)))
        except (TypeError, ValueError):
            return MESSAGE_DAILY_LIMIT

    def api_site_message_quota(self):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        user_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        used = self.message_daily_used(user_id)
        limit = self.message_limit_for_user(user_id)
        self.send_json(
            200,
            {
                "limit": limit,
                "used": used,
                "remaining": max(0, limit - used),
            },
        )

    def api_site_messages_unread(self):
        identity = self.session_identity()
        if not identity:
            self.send_json(
                200,
                {
                    "admin": False,
                    "unread": 0,
                    "newest_id": 0,
                    "last_seen_id": 0,
                    "targets": [],
                },
            )
            return
        if identity.get("kind") not in ("owner", "admin"):
            # 普通账号：未读的点赞 / 回复提醒
            user_id = int(identity.get("user_id") or 0)
            targets = prune_notification_targets(
                user_id, "messages", "site_messages"
            )
            info = unseen_notifications(user_id).get("messages") or {}
            self.send_json(
                200,
                {
                    "admin": False,
                    "unread": int(info.get("count") or 0),
                    "newest_id": 0,
                    "last_seen_id": 0,
                    "targets": targets,
                },
            )
            return
        user_id = 0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        last_seen = message_last_seen(user_id)
        newest = newest_message_id()
        unread = query_one(
            "SELECT COUNT(*) AS n FROM site_messages WHERE id > ?", (last_seen,)
        )["n"]
        self.send_json(
            200,
            {
                "admin": True,
                "unread": int(unread),
                "newest_id": newest,
                "last_seen_id": last_seen,
                "targets": prune_notification_targets(
                    user_id, "messages", "site_messages"
                ),
            },
        )

    def api_site_message_mark_seen(self):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以更新留言已读状态。")
            return
        identity = self.session_identity() or {}
        user_id = 0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        seen = mark_messages_seen(user_id)
        self.send_json(200, {"ok": True, "last_seen_id": seen})

    def notification_actor_name(self, identity):
        """写入提醒时用的展示名：管理员统一显示管理员，普通账号用用户名。"""
        identity = identity or {}
        if identity.get("kind") in ("owner", "admin"):
            return "管理员"
        return str(
            identity.get("username")
            or identity.get("nickname")
            or "普通用户"
        )[:32]

    def api_site_notifications_seen(self, payload):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        payload = payload or {}
        module = str(payload.get("module") or "").strip()
        if module not in NOTIFICATION_MODULES:
            api_error(self, 400, "提醒类型不正确。")
            return
        raw_target = payload.get("target_id")
        target_id = int(raw_target) if str(raw_target or "").isdigit() else None
        # 推荐模块的提醒分「网页」和「站内资源」两栏：点开哪一栏只清哪一栏
        scope = str(payload.get("scope") or "").strip()
        if scope not in ("", "web", "resource"):
            scope = ""
        mark_notifications_seen(
            int(identity.get("user_id") or 0), module, target_id, scope
        )
        self.send_json(200, {"ok": True, "cleared": 1})

    def notification_summary(self, identity=None):
        identity = identity if identity is not None else self.session_identity()
        summary = {
            "authenticated": identity is not None,
            "admin": False,
            "messages": 0,
            "moments": 0,
            "music": 0,
            "books": 0,
            "recommendations": 0,
            "recommendation_web": 0,
            "recommendation_resource": 0,
            "workbench": 0,
            "pending_users": 0,
            "pending_reviews": 0,
            "pending_reports": 0,
        }
        if not identity:
            return summary
        user_id = (
            0
            if identity.get("kind") == "owner"
            else int(identity.get("user_id") or 0)
        )
        unseen = unseen_notifications(user_id)
        for module in ("messages", "moments", "music", "books", "recommendations"):
            summary[module] = int((unseen.get(module) or {}).get("count") or 0)
        # 推荐条数按内容类型拆开：分享出来的站内资源只算「站内」那一栏
        summary["recommendation_web"] = summary["recommendations"]
        if summary["recommendations"]:
            resource_unread = int(
                query_one(
                    """SELECT COUNT(*) AS n
                       FROM user_notifications un
                       JOIN recommendations r ON r.id = un.target_id
                       WHERE un.user_id = ? AND un.module = 'recommendations'
                         AND un.seen_at IS NULL AND r.kind = 'resource'""",
                    (user_id,),
                )["n"]
            )
            summary["recommendation_resource"] = resource_unread
            summary["recommendation_web"] = max(
                0, summary["recommendations"] - resource_unread
            )
        if identity.get("kind") in ("owner", "admin"):
            summary["admin"] = True
            last_seen = message_last_seen(user_id)
            summary["messages"] = int(
                query_one(
                    "SELECT COUNT(*) AS n FROM site_messages WHERE id > ?",
                    (last_seen,),
                )["n"]
            )
            summary["pending_users"] = int(
                query_one(
                    "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'"
                )["n"]
            )
            pending_messages = int(
                query_one(
                    """SELECT COUNT(*) AS n FROM site_messages
                       WHERE parent_id IS NULL AND status = 'pending'"""
                )["n"]
            )
            pending_legacy = int(
                query_one(
                    """SELECT COUNT(*) AS n FROM site_message_files f
                       JOIN site_messages m ON m.id = f.message_id
                       WHERE f.status = 'pending' AND m.parent_id IS NULL
                         AND m.status = 'approved'"""
                )["n"]
            )
            summary["pending_reviews"] = pending_messages + pending_legacy
            summary["pending_reports"] = int(
                query_one(
                    "SELECT COUNT(*) AS n FROM content_reports WHERE status = 'pending'"
                )["n"]
            )
            summary["workbench"] = (
                summary["pending_users"]
                + summary["pending_reviews"]
                + summary["pending_reports"]
            )
        else:
            summary["messages"] = int(
                (unseen.get("messages") or {}).get("count") or 0
            )
        return summary

    def api_site_notification_summary(self):
        self.send_json(200, self.notification_summary())

    def api_site_notification_unread(self, params):
        identity = self.session_identity()
        if not identity:
            self.send_json(200, {"unread": 0, "targets": []})
            return
        module = self.log_param(params, "module")
        table = NOTIFICATION_TARGET_TABLES.get(module)
        if not table:
            api_error(self, 400, "提醒类型不正确")
            return
        user_id = (
            0
            if identity.get("kind") == "owner"
            else int(identity.get("user_id") or 0)
        )
        targets = prune_notification_targets(user_id, module, table)
        info = unseen_notifications(user_id).get(module) or {}
        self.send_json(
            200,
            {
                "unread": int(info.get("count") or 0),
                "targets": targets,
            },
        )

    def api_site_moments_unread(self):
        identity = self.session_identity()
        if not identity:
            self.send_json(200, {"unread": 0, "text": "", "targets": []})
            return
        user_id = 0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        targets = prune_notification_targets(
            user_id, "moments", NOTIFICATION_TARGET_TABLES["moments"]
        )
        info = unseen_notifications(user_id).get("moments") or {}
        kinds = unseen_notification_target_kinds(user_id, "moments")
        self.send_json(
            200,
            {
                "unread": int(info.get("count") or 0),
                "text": str(info.get("kind") or ""),
                "targets": targets,
                "target_kinds": {
                    str(target): kinds.get(target, "") for target in targets
                },
            },
        )

    def api_site_like_toggle(self, payload):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        if not rate_allow("like", self.client_ip(), 60, 60):
            api_error(self, 429, "操作太频繁，请稍后再试。")
            return
        target_type = str((payload or {}).get("target_type") or "").strip()
        raw_id = (payload or {}).get("target_id")
        target_id = int(raw_id) if str(raw_id or "").isdigit() else 0
        if target_type not in LIKE_TARGET_TYPES or target_id <= 0:
            api_error(self, 400, "点赞对象不正确。")
            return
        if target_type == "message":
            row = query_one(
                "SELECT id, user_id, status FROM site_messages WHERE id = ?", (target_id,)
            )
        elif target_type == "moment":
            row = query_one("SELECT id FROM moments WHERE id = ?", (target_id,))
        else:
            row = query_one(
                """SELECT id, user_id, moment_id
                   FROM moment_comments WHERE id = ?""",
                (target_id,),
            )
        if not row:
            api_error(self, 404, "要点赞的内容不存在。")
            return
        if target_type == "message" and row.get("status") != "approved" and not self.is_admin():
            api_error(self, 403, "这条留言尚未通过审核。")
            return
        user_id = 0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        existing = query_one(
            """SELECT 1 AS ok FROM content_likes
               WHERE target_type = ? AND target_id = ? AND user_id = ?""",
            (target_type, target_id, user_id),
        )
        if existing:
            execute(
                """DELETE FROM content_likes
                   WHERE target_type = ? AND target_id = ? AND user_id = ?""",
                (target_type, target_id, user_id),
            )
            liked = False
        else:
            execute(
                """INSERT OR IGNORE INTO content_likes
                       (target_type, target_id, user_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (target_type, target_id, user_id, now_text()),
            )
            liked = True
            if target_type == "message":
                author_id = int(row.get("user_id") or 0)
                if author_id and author_id != user_id:
                    add_user_notification(
                        author_id,
                        "message_like",
                        "messages",
                        target_id,
                        self.notification_actor_name(identity),
                        "点赞了你的留言",
                    )
            elif target_type == "comment":
                author_id = int(row.get("user_id") or 0)
                if author_id and author_id != user_id:
                    add_user_notification(
                        author_id,
                        "comment_like",
                        "moments",
                        int(row.get("id") or 0),
                        self.notification_actor_name(identity),
                        "点赞了你的评论",
                    )
        count = query_one(
            """SELECT COUNT(*) AS n FROM content_likes
               WHERE target_type = ? AND target_id = ?""",
            (target_type, target_id),
        )["n"]
        self.send_json(200, {"liked": liked, "count": int(count)})

    def api_site_messages(self, params):
        """
        留言板：游客也能看全部留言，但普通账号的名字只保留最后一个字，
        回复区照常下发（同样脱敏），发布 / 回复 / 点赞 / 删除按钮由前端对游客隐藏。
        """
        identity = self.session_identity()
        viewer_signed_in = identity is not None
        viewer_id = None
        if identity:
            viewer_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        is_admin = self.is_admin()
        all_rows = query(
            """SELECT id, nickname, content, parent_id, user_id, ip, ip_region,
                      show_region, status, reviewed_by, reviewed_at, review_note,
                      device_info, created_at
               FROM site_messages
               ORDER BY COALESCE(parent_id, id) DESC, id ASC"""
        )
        by_id_all = {int(row["id"]): row for row in all_rows}

        def visible_root(row):
            current = row
            guard = 0
            while current and current.get("parent_id") and guard < 50:
                guard += 1
                current = by_id_all.get(int(current["parent_id"]))
            return current

        if is_admin:
            rows = all_rows
        else:
            rows = []
            for row in all_rows:
                root = visible_root(row)
                if not root:
                    continue
                mine = (
                    viewer_id is not None
                    and int(row.get("user_id") or 0) == int(viewer_id)
                )
                if int(root["id"]) == int(row["id"]):
                    if row.get("status") == "approved" or mine:
                        rows.append(row)
                elif root.get("status") == "approved" or mine:
                    rows.append(row)
        my_ids = {
            int(row["id"])
            for row in rows
            if viewer_id is not None
            and int(row.get("user_id") or 0) == int(viewer_id)
        }
        liked_ids = liked_target_ids(viewer_id, "message", [row["id"] for row in rows])
        user_ids = sorted(
            {row["user_id"] for row in rows if row.get("user_id") not in (None, 0)}
        )
        authors = {}
        if user_ids:
            placeholders = ",".join("?" for _ in user_ids)
            for user in query(
                f"SELECT id, username, nickname FROM users WHERE id IN ({placeholders})",
                tuple(user_ids),
            ):
                authors[user["id"]] = user
        files = self.site_message_files_map([row["id"] for row in rows])
        message_ids = [int(row["id"]) for row in rows]
        like_count_map = like_counts("message", message_ids)
        liked_set = liked_target_ids(viewer_id, "message", message_ids)
        like_user_map = {}
        if message_ids:
            placeholders = ",".join("?" for _ in message_ids)
            for like in query(
                f"""SELECT l.target_id, l.user_id, u.username
                    FROM content_likes l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE l.target_type = 'message'
                      AND l.target_id IN ({placeholders})
                    ORDER BY l.created_at, l.user_id""",
                tuple(message_ids),
            ):
                like_user = int(like["user_id"] or 0)
                if like_user == 0:
                    name = "管理员"
                else:
                    username = str(like.get("username") or "").strip() or "普通用户"
                    name = username[:32] if viewer_signed_in else mask_username(username)
                like_user_map.setdefault(int(like["target_id"]), []).append(name)
        display_names = {}
        for row in rows:
            display_names[int(row["id"])] = self.message_display_name(
                row, authors, viewer_signed_in
            )
        # 之前没解析出属地的留言，打开页面时自动补一次（最多 3 条/次）
        for row in [
            item
            for item in rows
            if item.get("show_region") and not item.get("ip_region") and item.get("ip")
        ][:3]:
            region = lookup_ip_region(row.get("ip"))
            if region:
                execute(
                    "UPDATE site_messages SET ip_region = ? WHERE id = ?",
                    (region, row["id"]),
                )
                row["ip_region"] = region
        for row in rows:
            # 管理员可删任意留言；普通账号只能删自己发的（user_id 匹配）
            owner_match = (
                viewer_id not in (None, 0)
                and int(row.get("user_id") or 0) == int(viewer_id)
            )
            can_delete_row = bool(is_admin or owner_match)
            row["files"] = files.get(row["id"], [])
            row["like_count"] = like_count_map.get(int(row["id"]), 0)
            row["liked"] = int(row["id"]) in liked_set
            row["like_users"] = like_user_map.get(int(row["id"]), [])[:12]
            row["can_delete"] = can_delete_row
            row["can_review"] = is_admin
            row["nickname"] = display_names.get(int(row["id"]), "匿名")
            reply_to = row.get("parent_id")
            row["reply_to"] = (
                display_names.get(int(reply_to), "") if reply_to else ""
            )
            row["can_save"] = can_delete_row
            row["region"] = (
                normalize_region(row.get("ip_region")) if row.get("show_region") else ""
            )
            # 设备信息是公开展示字段：老数据没有就返回空串，前端不渲染
            row["device_info"] = str(row.get("device_info") or "")
            row["pending_review"] = row.get("status") == "pending"
            row["rejected"] = row.get("status") == "rejected"
            row["can_reply"] = bool(
                is_admin or row.get("status") == "approved" or int(row["id"]) in my_ids
            )
            if not is_admin:
                row.pop("review_note", None)
                row.pop("reviewed_by", None)
                row.pop("reviewed_at", None)
            row.pop("ip", None)
            row.pop("user_id", None)
            row.pop("ip_region", None)
            row.pop("show_region", None)
        roots = [row for row in rows if not row.get("parent_id")]
        replies = [row for row in rows if row.get("parent_id")]
        by_id = {int(row["id"]): row for row in rows}

        def thread_root(row):
            current = row
            guard = 0
            while current and current.get("parent_id") and guard < 50:
                guard += 1
                current = by_id.get(int(current["parent_id"]))
            return current

        for root in roots:
            root["replies"] = []
            root["mine"] = int(root["id"]) in my_ids
            root["liked_by_me"] = int(root["id"]) in liked_ids
            root["replied_by_me"] = False
        for reply in replies:
            root = thread_root(reply)
            if root and int(root.get("id") or 0) != int(reply.get("id") or 0):
                root.setdefault("replies", []).append(reply)
                if int(reply["id"]) in liked_ids:
                    root["liked_by_me"] = True
                if int(reply["id"]) in my_ids:
                    root["replied_by_me"] = True
            reply["mine"] = int(reply["id"]) in my_ids
        for root in roots:
            root["replies"] = sorted(
                root.get("replies") or [], key=lambda item: int(item["id"])
            )
        self.send_json(200, roots)

    def message_attachments(self, payload):
        """校验并解出附件，返回 (展示名、内容、MIME、存储名) 列表和错误信息。"""
        limits = upload_limit("message_file")
        max_count = limits["max_count"]
        max_file_bytes = limits["max_file_bytes"]
        max_total_bytes = limits["max_total_bytes"]
        raw_files = payload.get("files") or []
        if not isinstance(raw_files, list):
            return None, "附件格式不正确。"
        if len(raw_files) > max_count:
            return None, f"每条留言最多上传 {max_count} 个附件。"
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
            mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            stored_name = name
            if extension in MESSAGE_IMAGE_EXTENSIONS:
                detected_mime = detect_image_type(raw)
                if not detected_mime:
                    return None, f"图片内容无法识别：{name}"
                mime_type = detected_mime
                stored_name = (
                    os.path.splitext(name)[0] + NOTE_IMAGE_EXTENSIONS[detected_mime]
                )
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
            if len(raw) > max_file_bytes:
                limit_text = format_upload_limit_bytes(max_file_bytes)
                return None, f"单个附件不能超过 {limit_text}：{name}"
            total_bytes += len(raw)
            if total_bytes > max_total_bytes:
                limit_text = format_upload_limit_bytes(max_total_bytes)
                return None, f"附件总大小不能超过 {limit_text}。"
            prepared.append((name, raw, mime_type, stored_name))
        return prepared, ""

    def device_info_for(self, payload):
        """
        留言 / 动态要落库的「设备信息」：
        要不要公开由提交时的 show_device 开关决定（和「IP属地」一样是可选项，默认不公开，
        不公开时落空串、卡片上不显示）；文案一律由服务端按 User-Agent 自动识别
        （来自 Windows / macOS / Linux / 鸿蒙 / Android / iOS / ChromeOS，认不出记「来自 Web」）；
        只有具备 `site:device_name` 权限的账号
        （管理员天然具备，也可以在「工作台 → 账号权限」里单独开放给普通账号）
        能用 payload 里的 device_info 覆盖成自定义名称，其他人传了也一律忽略，
        防止普通账号或游客伪造设备名称。
        """
        payload = payload or {}
        if payload.get("show_device") is not True:
            return ""
        auto = device_info_label(self.headers.get("User-Agent"))
        if not self.can("site:device_name"):
            return auto
        return normalize_device_info(payload.get("device_info")) or auto

    def api_site_message_create(self, payload):
        """
        发布留言 / 回复。设备平台要不要公开由 show_device 决定（默认不公开），
        文案按 User-Agent 自动识别，只有管理员能用 device_info 自定义（其他人传了也会被丢掉）。
        """
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        if not rate_allow("message", self.client_ip(), 5, 60):
            api_error(self, 429, "留言太频繁，请稍后再试。")
            return
        user_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        daily_used = self.message_daily_used(user_id)
        daily_limit = self.message_limit_for_user(user_id)
        if daily_used >= daily_limit:
            api_error(
                self,
                429,
                f"今天的留言额度已用完（每天最多 {daily_limit} 条），明天 0 点恢复。",
            )
            return
        author = (
            query_one("SELECT nickname, username FROM users WHERE id = ?", (user_id,))
            if user_id
            else None
        )
        if identity.get("kind") == "owner":
            nickname = "管理员"
        elif author:
            nickname = (author.get("nickname") or "").strip()[:16]
        else:
            nickname = ""
        content = str(payload.get("content") or "").strip()
        parent_id = payload.get("parent_id")
        if content and sensitive_contains(content):
            maybe_alert_sensitive("留言内容", content, nickname)
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
            parent = query_one(
                """SELECT id, user_id AS author_id, parent_id, status
                   FROM site_messages WHERE id = ?""",
                (parent_id,),
            )
            if not parent:
                api_error(self, 400, "要回复的留言不存在。")
                return
            if prepared:
                api_error(self, 400, "回复暂不支持附件。")
                return
            if (
                parent.get("status") != "approved"
                and int(parent.get("author_id") or 0) != int(user_id)
                and not self.is_admin()
            ):
                api_error(self, 403, "这条留言还在审核中，暂时不能回复。")
                return
        created_at = now_text()
        client_ip = self.client_ip()
        show_region = 1 if payload.get("show_region") is True else 0
        ip_region = lookup_ip_region(client_ip) if show_region else ""
        device_info = self.device_info_for(payload)
        saved = []
        storage_limit = upload_limit("message_file")["max_file_bytes"]
        try:
            for name, raw, _mime_type, stored_name in prepared:
                relative = self.save_data_file(
                    raw,
                    stored_name,
                    "site_message_files",
                    max_bytes=storage_limit,
                )
                saved.append((name, relative, len(raw), _mime_type))
        except ValueError as exc:
            for _name, relative, _size, _mime_type in saved:
                remove_data_file(relative)
            api_error(self, 400, str(exc))
            return
        uploader_id = user_id
        message_status = "approved" if parent_id else "pending"
        file_status = "approved" if parent_id else "pending"

        def write(conn):
            cursor = conn.execute(
                """INSERT INTO site_messages
                       (nickname, content, parent_id, user_id, ip, ip_region,
                        show_region, status, device_info, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    nickname,
                    content,
                    parent_id or None,
                    user_id,
                    client_ip,
                    ip_region,
                    show_region,
                    message_status,
                    device_info,
                    created_at,
                ),
            )
            message_id = cursor.lastrowid
            for name, relative, size, mime_type in saved:
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
                        mime_type,
                        file_status,
                        uploader_id,
                        created_at,
                    ),
                )
            return message_id

        try:
            row_id = transaction(write)
        except Exception:
            for _name, relative, _size, _mime_type in saved:
                remove_data_file(relative)
            raise
        self.log_activity(
            "message_reply" if parent_id else "message_create",
            f"{'回复' if parent_id else '发布'}留言：{(content[:60] if content else '（仅附件）')}",
            target_type="message",
            target_id=row_id,
            actor=identity,
            ip=client_ip,
            ip_region=ip_region,
        )
        if parent_id:
            target_user = int((parent or {}).get("author_id") or 0)
            if target_user and target_user != user_id:
                add_user_notification(
                    target_user,
                    "message_reply",
                    "messages",
                    row_id,
                    self.notification_actor_name(identity),
                    "回复了你" if (parent or {}).get("parent_id") else "回复了你的留言",
                )
        if parent_id:
            nested_reply = bool((parent or {}).get("parent_id"))
            # 楼中楼（回复某条回复）只在站内提醒，不再往 Webhook 推 —— 那是两个人之间的对话，
            # 推到微信只会变成噪音；回复顶层留言照常推送。
            if not nested_reply:
                parent_author = int((parent or {}).get("author_id") or 0)
                if parent_author:
                    author_row = query_one(
                        "SELECT username FROM users WHERE id = ?", (parent_author,)
                    )
                    parent_name = str(
                        (author_row or {}).get("username") or "普通用户"
                    )
                else:
                    parent_name = "管理员"
                notify_async(
                    "message",
                    "Error酱：新的回复",
                    f"{nickname} 回复了「{parent_name}」的留言"
                    f"：{(content[:60] if content else '（仅附件）')}",
                )
        else:
            notify_async(
                "message",
                "Error酱：新的留言",
                f"{nickname}：{(content[:60] if content else '（仅附件）')}，请到工作台「留言审核」处理。",
            )
        self.send_json(
            200,
            {
                "id": row_id,
                "files": len(saved),
                "pending_review": message_status == "pending",
                "daily_limit": daily_limit,
                "daily_used": daily_used + 1,
                "daily_remaining": max(0, daily_limit - daily_used - 1),
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

    def moment_comments_map(self, moment_ids, viewer_id, can_manage, viewer_signed_in):
        """按动态分组返回评论，并标出每一条能不能删。"""
        if not moment_ids:
            return {}, set()
        placeholders = ",".join("?" for _ in moment_ids)
        rows = query(
            f"""SELECT id, moment_id, parent_id, user_id, actor, content, created_at
                FROM moment_comments
                WHERE moment_id IN ({placeholders})
                ORDER BY id""",
            tuple(moment_ids),
        )
        comment_ids = [int(row["id"]) for row in rows]
        like_count_map = like_counts("comment", comment_ids)
        liked_set = liked_target_ids(viewer_id, "comment", comment_ids)
        viewer_commented_ids = (
            set(
                int(row["moment_id"])
                for row in rows
                if viewer_id is not None
                and int(row.get("user_id") or 0) == int(viewer_id)
            )
            if viewer_id is not None
            else set()
        )
        like_user_map = {}
        if comment_ids:
            like_placeholders = ",".join("?" for _ in comment_ids)
            for like in query(
                f"""SELECT l.target_id, l.user_id, u.username
                    FROM content_likes l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE l.target_type = 'comment'
                      AND l.target_id IN ({like_placeholders})
                    ORDER BY l.created_at, l.user_id""",
                tuple(comment_ids),
            ):
                like_user = int(like["user_id"] or 0)
                if like_user == 0:
                    name = "管理员"
                else:
                    username = str(like.get("username") or "").strip() or "普通用户"
                    name = username[:32] if viewer_signed_in else mask_username(username)
                like_user_map.setdefault(int(like["target_id"]), []).append(name)
        grouped = {}
        for row in rows:
            can_delete = bool(
                can_manage
                or (viewer_id is not None and int(row.get("user_id") or 0) == int(viewer_id))
            )
            grouped.setdefault(row["moment_id"], []).append(
                {
                    "id": row["id"],
                    "parent_id": row["parent_id"],
                    # 游客视角：管理员照常显示「管理员」，普通账号只保留最后一个字
                    "actor": (
                        row["actor"]
                        if viewer_signed_in
                        else (
                            "管理员"
                            if int(row.get("user_id") or 0) == 0
                            else mask_username(row["actor"])
                        )
                    ),
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "can_delete": can_delete,
                    "mine": bool(
                        viewer_id is not None
                        and int(row.get("user_id") or 0) == int(viewer_id)
                    ),
                    "like_count": like_count_map.get(int(row["id"]), 0),
                    "liked": int(row["id"]) in liked_set,
                    "like_users": like_user_map.get(int(row["id"]), [])[:12],
                }
            )
        return grouped, viewer_commented_ids

    def api_moments(self, params):
        """
        动态：游客也能看全部动态（正文、图片、属地），但普通账号的名字只保留最后一个字，
        评论 / 回复区照常下发（评论人同样脱敏），点赞、评论输入和分享卡的操作按钮由前端对游客隐藏。
        """
        identity = self.session_identity()
        viewer_signed_in = identity is not None
        rows = query(
            """SELECT id, content, tags, pinned, ip, ip_region, show_region, kind,
                      device_info, created_at
               FROM moments
               ORDER BY pinned DESC, created_at DESC, id DESC"""
        )
        can_manage = self.is_admin()
        viewer_id = None
        if identity:
            viewer_id = 0 if identity.get("kind") == "owner" else int(
                identity.get("user_id") or 0
            )
        files = self.moment_files_map([row["id"] for row in rows])
        moment_ids = [int(row["id"]) for row in rows]
        comments, comment_moment_ids = self.moment_comments_map(
            moment_ids, viewer_id, can_manage, viewer_signed_in
        )
        share_ids = {}
        if moment_ids:
            placeholders = ",".join("?" for _ in moment_ids)
            for share in query(
                f"""SELECT moment_id, resource_type, resource_id
                    FROM moment_shares WHERE moment_id IN ({placeholders})""",
                tuple(moment_ids),
            ):
                share_ids[int(share["moment_id"])] = (
                    share["resource_type"],
                    share["resource_id"],
                )
        like_count_map = like_counts("moment", moment_ids)
        liked_set = liked_target_ids(viewer_id, "moment", moment_ids)
        like_user_map = {}
        if moment_ids:
            placeholders = ",".join("?" for _ in moment_ids)
            for like in query(
                f"""SELECT l.target_id, l.user_id, u.username
                    FROM content_likes l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE l.target_type = 'moment'
                      AND l.target_id IN ({placeholders})
                    ORDER BY l.created_at, l.user_id""",
                tuple(moment_ids),
            ):
                like_user = int(like["user_id"] or 0)
                if like_user == 0:
                    name = "管理员"
                else:
                    username = str(like.get("username") or "").strip() or "普通用户"
                    name = username[:32] if viewer_signed_in else mask_username(username)
                like_user_map.setdefault(int(like["target_id"]), []).append(name)
        if viewer_signed_in:
            # 属地补解析会写库 / 打外部接口，只在登录账号浏览时顺带做
            for row in [
                item
                for item in rows
                if item.get("show_region") and not item.get("ip_region") and item.get("ip")
            ][:3]:
                region = lookup_ip_region(row.get("ip"))
                if region:
                    execute(
                        "UPDATE moments SET ip_region = ? WHERE id = ?",
                        (region, row["id"]),
                    )
                    row["ip_region"] = region
        comment_counts = {
            moment_id: len(items) for moment_id, items in comments.items()
        }
        for row in rows:
            row["files"] = files.get(row["id"], [])
            row["comments"] = comments.get(row["id"], [])
            row["comment_count"] = comment_counts.get(int(row["id"]), 0)
            share = share_ids.get(int(row["id"]))
            share_info = shared_resource_info(share[0], share[1]) if share else None
            if share_info and not viewer_signed_in:
                # 分享卡对游客只留标题 / 封面，进去看内容要登录
                share_info = dict(share_info)
                share_info["locked"] = True
                for key in ("url", "file_url", "page_url"):
                    share_info.pop(key, None)
            row["share"] = share_info
            row["like_count"] = like_count_map.get(int(row["id"]), 0)
            row["liked"] = int(row["id"]) in liked_set
            row["liked_by_me"] = row["liked"] or any(
                comment.get("liked") for comment in row["comments"]
            )
            row["commented_by_me"] = int(row["id"]) in comment_moment_ids
            # 「评论 / 点赞」两个筛选看的是「有没有任何用户（含管理员）动过」，
            # 不再只看自己——所以这里直接给出行级的布尔标记。
            row["has_comments"] = bool(row["comments"])
            row["has_likes"] = int(row["like_count"] or 0) > 0
            row["like_users"] = like_user_map.get(int(row["id"]), [])[:12]
            row["pinned"] = bool(row["pinned"])
            # post = 手动发布的动态，log = 更新日志；前端按这个字段分流成两个标签页
            row["kind"] = row.get("kind") or "post"
            row["can_manage"] = can_manage
            row["can_save"] = can_manage
            row["region"] = (
                normalize_region(row.get("ip_region")) if row.get("show_region") else ""
            )
            row["device_info"] = str(row.get("device_info") or "")
            row.pop("ip", None)
            row.pop("ip_region", None)
            row.pop("show_region", None)
        self.send_json(200, rows)

    def api_moment_comment_create(self, moment_id, payload):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        if not rate_allow("moment_comment", self.client_ip(), 10, 60):
            api_error(self, 429, "评论太频繁，请稍后再试。")
            return
        content = str((payload or {}).get("content") or "").strip()
        if not content:
            api_error(self, 400, "评论内容不能为空。")
            return
        if len(content) > MOMENT_COMMENT_MAX_CHARS:
            api_error(self, 400, f"评论不能超过 {MOMENT_COMMENT_MAX_CHARS} 字。")
            return
        actor = self.notification_actor_name(identity)
        if sensitive_contains(content):
            maybe_alert_sensitive("动态评论", content, actor)
            api_error(self, 400, "评论内容包含不允许的词汇，请修改后再发。")
            return
        if not query_one("SELECT id FROM moments WHERE id = ?", (moment_id,)):
            api_error(self, 404, "动态不存在。")
            return
        raw_parent = (payload or {}).get("parent_id")
        parent_id = int(raw_parent) if str(raw_parent or "").isdigit() else None
        parent = None
        if parent_id:
            parent = query_one(
                """SELECT id, user_id, parent_id FROM moment_comments
                   WHERE id = ? AND moment_id = ?""",
                (parent_id, moment_id),
            )
            if not parent:
                api_error(self, 400, "要回复的评论不存在。")
                return
        user_id = 0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        comment_id = execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (moment_id, parent_id, user_id, actor, content, now_text()),
        )
        if parent:
            target_user = int(parent.get("user_id") or 0)
            if target_user and target_user != user_id:
                add_user_notification(
                    target_user,
                    "comment_reply",
                    "moments",
                    comment_id,
                    actor,
                    "回复了你的评论",
                )
        if identity.get("kind") != "owner":
            # 动态都是管理员发的，评论提醒统一收敛到站长账号
            add_user_notification(
                0,
                "moment_comment",
                "moments",
                comment_id,
                actor,
                "评论了你的动态",
            )
            # 和留言同一条规则：楼中楼（回复某条回复）只在站内提醒，不再推 Webhook
            if not (parent and parent.get("parent_id")):
                notify_async(
                    "moment_comment",
                    "Error酱：新的动态评论",
                    f"{actor} 评论了你的动态：{content[:60]}",
                    "/moments",
                )
        self.log_activity(
            "moment_comment",
            f"评论了动态：{content[:40]}",
            target_type="moment",
            target_id=moment_id,
        )
        self.send_json(200, {"id": comment_id})

    def api_moment_comment_delete(self, comment_id):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        row = query_one(
            "SELECT id, moment_id, user_id FROM moment_comments WHERE id = ?",
            (comment_id,),
        )
        if not row:
            api_error(self, 404, "评论不存在。")
            return
        user_id = 0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        if not self.is_admin() and int(row.get("user_id") or 0) != user_id:
            api_error(self, 403, "只能删除自己的评论。")
            return
        execute(
            "DELETE FROM moment_comments WHERE id = ? OR parent_id = ?",
            (comment_id, comment_id),
        )
        self.send_json(200, {"ok": True})

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
        limits = upload_limit("moment_image")
        max_count = limits["max_count"]
        max_file_bytes = limits["max_file_bytes"]
        max_total_bytes = limits["max_total_bytes"]
        raw_files = payload.get("images") or []
        if not isinstance(raw_files, list):
            return None, "图片格式不正确。"
        if len(raw_files) > max_count:
            return None, f"一条说说最多 {max_count} 张图片。"
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
            if len(raw) > max_file_bytes:
                limit_text = format_upload_limit_bytes(max_file_bytes)
                return None, f"单张图片不能超过 {limit_text}：{name}"
            total_bytes += len(raw)
            if total_bytes > max_total_bytes:
                limit_text = format_upload_limit_bytes(max_total_bytes)
                return None, f"图片总大小不能超过 {limit_text}。"
            prepared.append((name, raw))
        return prepared, ""

    def api_moment_create(self, payload):
        """发布动态。设备平台同留言：要不要公开看 show_device，文案自动识别，只有管理员能自定义。"""
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
        client_ip = self.client_ip()
        show_region = 1 if payload.get("show_region") is True else 0
        ip_region = lookup_ip_region(client_ip) if show_region else ""
        device_info = self.device_info_for(payload)
        saved = []
        storage_limit = upload_limit("moment_image")["max_file_bytes"]
        try:
            for name, raw in prepared:
                relative = self.save_data_file(
                    raw, name, "moment_images", max_bytes=storage_limit
                )
                saved.append((name, relative, len(raw)))
        except ValueError as exc:
            for _name, relative, _size in saved:
                remove_data_file(relative)
            api_error(self, 400, str(exc))
            return

        def write(conn):
            cursor = conn.execute(
                """INSERT INTO moments
                       (content, tags, pinned, ip, ip_region, show_region, kind,
                        device_info, created_at)
                   VALUES (?, ?, 0, ?, ?, ?, 'post', ?, ?)""",
                (content, tags, client_ip, ip_region, show_region, device_info, created_at),
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
        self.log_activity(
            "moment_create",
            f"发布动态：{(content[:60] if content else '（仅配图）')}",
            target_type="moment",
            target_id=row_id,
            ip=client_ip,
            ip_region=ip_region,
        )
        self.notify_members_new_moment(row_id)
        notify_async(
            "moment",
            "Error酱：管理员发布了新动态",
            f"{(content[:100] if content else '（仅配图）')}",
            f"/moments?moment={row_id}",
        )
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
            execute(
                "DELETE FROM content_likes WHERE target_type = 'moment' AND target_id = ?",
                (moment_id,),
            )
            for row in rows:
                remove_data_file(row.get("file_path"))
            self.log_activity(
                "moment_delete",
                f"删除动态 #{moment_id}",
                target_type="moment",
                target_id=moment_id,
            )
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
            # 「有内容」不只是文字：带配图，或者「分享到动态」生成的卡片
            # （歌曲 / 笔记 / 电子书等，正文本来就允许为空）同样算有内容，
            # 这样这些动态才能正常置顶 / 编辑，不会被「说说内容不能为空」挡住。
            has_extra = query_one(
                "SELECT id FROM moment_files WHERE moment_id = ? LIMIT 1", (moment_id,)
            ) or query_one(
                "SELECT id FROM moment_shares WHERE moment_id = ? LIMIT 1", (moment_id,)
            )
            if not has_extra:
                api_error(self, 400, "说说内容不能为空。")
                return
        pinned = 1 if payload.get("pinned", current.get("pinned")) else 0
        # 设备信息：编辑表单提交时按「填了就自定义、留空回自动识别」处理；
        # 公开开关（show_device）也在这里一起处理；
        # 只发置顶之类的请求不会带这两个字段，原值保持不变。
        device_info = current.get("device_info")
        if "show_device" in payload or "device_info" in payload:
            device_info = self.device_info_for(payload)
        execute(
            """UPDATE moments SET content = ?, tags = ?, pinned = ?, device_info = ?
               WHERE id = ?""",
            (content, tags, pinned, device_info, moment_id),
        )
        self.log_activity(
            "moment_update",
            f"编辑动态：{(content[:60] if content else '（仅配图）')}"
            + ("（置顶）" if pinned else ""),
            target_type="moment",
            target_id=moment_id,
        )
        self.send_json(200, {"id": moment_id})

    # ---------- 参考项目 ----------

    def reference_payload(self, payload, current=None):
        current = current or {}
        title = str(payload.get("title", current.get("title", "")) or "").strip()[:200]
        url = str(payload.get("url", current.get("url", "")) or "").strip()[:1000]
        description = str(
            payload.get("description", current.get("description", "")) or ""
        ).strip()[:2000]
        if not title:
            raise ValueError("项目名称不能为空。")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("项目链接必须是有效的 http:// 或 https:// 地址。")
        try:
            sort_order = int(payload.get("sort_order", current.get("sort_order", 0)) or 0)
        except (TypeError, ValueError):
            raise ValueError("排序值必须是整数。")
        return title, url, description, sort_order

    def api_reference_projects(self):
        self.send_json(
            200,
            query(
                """SELECT id, title, url, description, sort_order,
                          created_at, updated_at
                   FROM reference_projects
                   ORDER BY sort_order, id"""
            ),
        )

    def api_reference_create(self, payload):
        try:
            title, url, description, sort_order = self.reference_payload(payload)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        stamp = now_text()
        item_id = execute(
            """INSERT INTO reference_projects
                   (title, url, description, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, url, description, sort_order, stamp, stamp),
        )
        self.log_activity(
            "reference_create",
            f"新增参考项目：{title}",
            target_type="reference",
            target_id=item_id,
        )
        self.send_json(200, {"id": item_id})

    def api_reference_item(self, path):
        item_id = int(path.rsplit("/", 1)[1])
        current = query_one("SELECT * FROM reference_projects WHERE id = ?", (item_id,))
        if not current:
            api_error(self, 404, "参考项目不存在。")
            return
        if self.command == "DELETE":
            execute("DELETE FROM reference_projects WHERE id = ?", (item_id,))
            self.log_activity(
                "reference_delete",
                f"删除参考项目：{current.get('title') or item_id}",
                target_type="reference",
                target_id=item_id,
            )
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        try:
            title, url, description, sort_order = self.reference_payload(payload, current)
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        execute(
            """UPDATE reference_projects
               SET title = ?, url = ?, description = ?, sort_order = ?, updated_at = ?
               WHERE id = ?""",
            (title, url, description, sort_order, now_text(), item_id),
        )
        self.log_activity(
            "reference_update",
            f"编辑参考项目：{title}",
            target_type="reference",
            target_id=item_id,
        )
        self.send_json(200, {"id": item_id})

    # ---------- 限时分享 ----------

    def share_resource(self, resource_type, resource_id):
        if resource_type not in SHARE_RESOURCE_TYPES:
            return None
        if resource_type == "book":
            row = query_one(
                "SELECT title, format, file_path FROM books WHERE id = ?",
                (resource_id,),
            )
            if not row:
                return None
            extension = "." + str(row.get("format") or "bin").lstrip(".")
            return {
                "title": row.get("title") or "电子书",
                "file_path": row.get("file_path") or "",
                "download_name": (row.get("title") or "book") + extension,
            }
        if resource_type == "music":
            row = query_one(
                """SELECT title, source_type, source_id
                   FROM site_music WHERE id = ?""",
                (resource_id,),
            )
            if not row or row.get("source_type") != "file":
                return None
            source_id = row.get("source_id") or ""
            extension = os.path.splitext(source_id)[1] or ".mp3"
            return {
                "title": row.get("title") or "歌曲",
                "file_path": source_id,
                "download_name": (row.get("title") or "music") + extension,
            }
        row = query_one(
            """SELECT title, original_name, file_path
               FROM workbench_assets WHERE id = ?""",
            (resource_id,),
        )
        if not row:
            return None
        return {
            "title": row.get("title") or row.get("original_name") or "资料",
            "file_path": row.get("file_path") or "",
            "download_name": row.get("original_name") or "download.bin",
        }

    def download_resource(self, resource_type, resource_id):
        if resource_type not in DOWNLOAD_RESOURCE_TYPES:
            return None
        if resource_type == "book":
            row = query_one(
                "SELECT title, format, file_path FROM books WHERE id = ?",
                (resource_id,),
            )
            if not row:
                return None
            return {
                "title": row.get("title") or "电子书",
                "file_path": row.get("file_path") or "",
                "download_name": (row.get("title") or "book")
                + "."
                + str(row.get("format") or "bin").lstrip("."),
            }
        row = query_one(
            """SELECT title, source_type, source_id
               FROM site_music WHERE id = ?""",
            (resource_id,),
        )
        if not row or row.get("source_type") != "file":
            return None
        source_id = row.get("source_id") or ""
        return {
            "title": row.get("title") or "歌曲",
            "file_path": source_id,
            "download_name": (row.get("title") or "music")
            + (os.path.splitext(source_id)[1] or ".mp3"),
        }

    def notify_members_new_content(self, kind, module, target_id, actor, text):
        """给所有已批准普通账号写一条新内容提醒。"""
        for member_id in member_user_ids():
            add_user_notification(
                member_id,
                kind,
                module,
                target_id,
                actor,
                text,
            )

    def notify_members_new_moment(self, moment_id):
        """给所有已批准普通账号写一条新动态提醒。"""
        self.notify_members_new_content(
            "moment_new", "moments", moment_id, "管理员", "更新了动态"
        )

    def api_admin_share_content(self, payload):
        """把笔记 / 电子书 / 歌曲分享到动态或推荐页。"""
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以分享内容。")
            return
        target = str((payload or {}).get("target") or "").strip()
        resource_type = str((payload or {}).get("resource_type") or "").strip()
        raw_id = (payload or {}).get("resource_id")
        resource_id = int(raw_id) if str(raw_id or "").isdigit() else 0
        if target not in ("moment", "recommendation"):
            api_error(self, 400, "分享目标不正确。")
            return
        if resource_type not in SHARE_CONTENT_TYPES:
            api_error(self, 400, "这种内容暂时不能分享到站内。")
            return
        info = shared_resource_info(resource_type, resource_id)
        if not info.get("available"):
            api_error(self, 404, "要分享的内容不存在。")
            return
        stamp = now_text()
        if target == "moment":
            content = str((payload or {}).get("content") or "").strip()
            if len(content) > MOMENT_CONTENT_MAX_CHARS:
                api_error(
                    self, 400, f"说说内容不能超过 {MOMENT_CONTENT_MAX_CHARS} 字。"
                )
                return
            moment_id = execute(
                """INSERT INTO moments
                       (content, tags, pinned, ip, ip_region, show_region, kind, created_at)
                   VALUES (?, NULL, 0, '', '', 0, 'post', ?)""",
                (content, stamp),
            )
            execute(
                """INSERT INTO moment_shares
                       (moment_id, resource_type, resource_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (moment_id, resource_type, resource_id, stamp),
            )
            self.log_activity(
                "moment_share",
                f"分享{info['label']}到动态：{info['title']}",
                target_type=resource_type,
                target_id=resource_id,
            )
            self.notify_members_new_moment(moment_id)
            self.send_json(
                200, {"ok": True, "moment_id": moment_id, "url": "/moments"}
            )
            return
        cover_path = (
            info["cover_url"].replace("/site-files/", "", 1)
            if info.get("cover_url")
            else None
        )
        recommendation_id = execute(
            """INSERT INTO recommendations
                   (kind, title, subtitle, cover_path, resource_type, resource_id,
                    sort_order, created_at, updated_at)
               VALUES ('resource', ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                info["title"],
                info.get("subtitle") or None,
                cover_path,
                resource_type,
                resource_id,
                stamp,
                stamp,
            ),
        )
        self.log_activity(
            "recommendation_share",
            f"分享{info['label']}到推荐：{info['title']}",
            target_type=resource_type,
            target_id=resource_id,
        )
        self.notify_members_new_content(
            "recommendation_new",
            "recommendations",
            recommendation_id,
            "管理员",
            "新增了一条推荐",
        )
        self.send_json(
            200,
            {
                "ok": True,
                "recommendation_id": recommendation_id,
                "url": "/downloads?tab=resource",
            },
        )

    def api_shared_note(self, note_id):
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        if not self.is_admin() and not resource_is_shared("note", note_id):
            api_error(self, 403, "这篇笔记没有在站内分享。")
            return
        row = query_one(
            """SELECT id, title, content, tags, created_at, updated_at
               FROM learning_notes WHERE id = ?""",
            (note_id,),
        )
        if not row:
            api_error(self, 404, "笔记不存在。")
            return
        self.send_json(200, row)

    def api_admin_share_link_create(self, payload):
        resource_type = str(payload.get("resource_type") or "").strip()
        try:
            resource_id = int(payload.get("resource_id") or 0)
        except (TypeError, ValueError):
            resource_id = 0
        resource = self.share_resource(resource_type, resource_id)
        if not resource:
            api_error(self, 400, "这个文件不支持分享。")
            return
        expires_text = str(payload.get("expires_at") or "").strip()
        now = datetime.now()
        if expires_text:
            try:
                expires = datetime.fromisoformat(expires_text.replace("Z", "+00:00")).replace(
                    tzinfo=None
                )
            except ValueError:
                api_error(self, 400, "自定义过期时间格式不正确。")
                return
        else:
            try:
                hours = int(payload.get("expires_hours") or 24)
            except (TypeError, ValueError):
                hours = 24
            hours = max(1, min(720, hours))
            expires = now + timedelta(hours=hours)
        if expires <= now + timedelta(minutes=1):
            api_error(self, 400, "过期时间至少要比现在晚 1 分钟。")
            return
        if expires > now + timedelta(days=30):
            api_error(self, 400, "分享链接最长有效期不能超过 30 天。")
            return
        token = secrets.token_urlsafe(24)
        stamp = now_text()
        link_id = execute(
            """INSERT INTO share_links
                   (token, resource_type, resource_id, created_by, expires_at,
                    created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                token,
                resource_type,
                resource_id,
                (self.session_identity() or {}).get("nickname") or "管理员",
                expires.strftime("%Y-%m-%d %H:%M:%S"),
                stamp,
            ),
        )
        self.log_activity(
            "share_create",
            f"生成限时分享：{resource['title']}（至 {expires.strftime('%Y-%m-%d %H:%M')}）",
            target_type=resource_type,
            target_id=resource_id,
        )
        self.send_json(
            200,
            {
                "id": link_id,
                "url": self.request_base_url() + "/s/" + token,
                "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    def serve_share_link(self, token):
        row = query_one(
            "SELECT * FROM share_links WHERE token = ?",
            (token,),
        )
        now = now_text()
        if not row or row.get("revoked_at") or str(row.get("expires_at") or "") <= now:
            api_error(self, 410, "分享链接已过期或已失效。")
            return
        resource = self.share_resource(row["resource_type"], row["resource_id"])
        if not resource:
            api_error(self, 404, "分享的文件不存在。")
            return
        execute(
            """UPDATE share_links
               SET download_count = download_count + 1, last_download_at = ?
               WHERE id = ?""",
            (now, row["id"]),
        )
        self.log_activity(
            "share_download",
            f"通过分享链接下载：{resource['title']}",
            target_type=row["resource_type"],
            target_id=row["resource_id"],
        )
        self.send_data_file(
            resource["file_path"],
            resource["download_name"],
            allow_range=True,
        )

    def recommendation_rows(self, params=None):
        params = params or {}
        is_guest = self.session_identity() is None
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
                       r.resource_type, r.resource_id,
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
            if row.get("kind") == "resource":
                row["resource"] = shared_resource_info(
                    row.get("resource_type"), row.get("resource_id")
                )
            row["requires_login"] = is_guest
            if is_guest:
                # 网页 / 工具对游客开放点击访问；其它类型（电影 / 动漫）的详情地址仍然不返回
                if row.get("kind") not in ("site", "tool"):
                    row["url"] = ""
                row["download_url"] = ""
                row.pop("resource", None)
                row.pop("resource_type", None)
                row.pop("resource_id", None)
        return rows

    def api_recommendations(self, params):
        self.send_json(
            200,
            {
                "items": self.recommendation_rows(params),
                "can_manage": self.is_admin(),
                "requires_login": self.session_identity() is None,
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
        if kind == "resource":
            raise ValueError("站内资源卡片请用分享按钮生成。")
        bookmark_id_value = payload.get("bookmark_id", current.get("bookmark_id"))
        bookmark = None
        if bookmark_id_value not in (None, "", 0, "0"):
            try:
                bookmark_id = int(bookmark_id_value)
            except (TypeError, ValueError):
                raise ValueError("书签关联不正确。")
            if kind != "site":
                raise ValueError("只有网站类型可以关联书签。")
            bookmark = query_one(
                "SELECT id, title, url, description, favicon_updated_at FROM bookmarks WHERE id = ?",
                (bookmark_id,),
            )
            if not bookmark:
                raise ValueError("关联的书签不存在。")
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
        self.log_activity(
            "recommendation_create",
            f"新增推荐：{values[2]}",
            target_type="recommendation",
            target_id=recommendation_id,
        )
        self.notify_members_new_content(
            "recommendation_new",
            "recommendations",
            recommendation_id,
            "管理员",
            "新增了一条推荐",
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
            self.log_activity(
                "recommendation_delete",
                f"删除推荐：{current.get('title') or recommendation_id}",
                target_type="recommendation",
                target_id=recommendation_id,
            )
            clear_notification_target("recommendations", recommendation_id)
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
        self.log_activity(
            "recommendation_update",
            f"更新推荐：{values[2]}",
            target_type="recommendation",
            target_id=recommendation_id,
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
        max_file_bytes = upload_limit("recommend_image")["max_file_bytes"]
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                f"封面图片不能超过 {format_upload_limit_bytes(max_file_bytes)}。",
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
                max_file_bytes,
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
                upload_limit("site_photo")["max_file_bytes"],
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
        identity = self.session_identity()
        is_admin = self.is_admin()
        for row in rows:
            if row.get("source_type") == "file":
                duration = ensure_music_duration(row)
                if duration:
                    row["duration"] = duration
                row["url"] = (
                    f"/api/site/music/{row['id']}/stream" if identity else ""
                )
            else:
                row["url"] = (row.get("source_id") or "") if identity else ""
            row["cover_url"] = (
                "/site-files/" + row["cover_path"] if row.get("cover_path") else ""
            )
            row["requires_login"] = identity is None
            if not is_admin:
                row.pop("source_id", None)
        self.send_json(200, rows)

    def api_site_music_stream(self, item_id, head_only=False):
        if self.session_identity() is None:
            api_error(self, 401, "请登录后操作")
            return
        row = query_one(
            """SELECT title, source_type, source_id
               FROM site_music WHERE id = ?""",
            (item_id,),
        )
        if not row or row.get("source_type") != "file":
            api_error(self, 404, "歌曲不存在或不是本地上传文件。")
            return
        source_id = row.get("source_id") or ""
        self.send_data_file(source_id, allow_range=True, head_only=head_only)

    def api_site_music_download(self, item_id):
        resource = self.download_resource("music", item_id)
        if not resource:
            api_error(self, 404, "歌曲不存在或不是本地上传文件。")
            return
        # 登录后直接下载，不再需要申请与审核
        if self.session_identity() is None:
            api_error(self, 401, "请登录后操作")
            return
        self.log_activity(
            "music_download",
            f"下载歌曲：{resource['title']}",
            target_type="music",
            target_id=item_id,
        )
        self.send_data_file(
            resource["file_path"],
            resource["download_name"],
            allow_range=True,
        )

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
        max_file_bytes = upload_limit("music_file")["max_file_bytes"]
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                "单个音频文件不能超过 "
                f"{format_upload_limit_bytes(max_file_bytes)}。",
            )
            return
        metadata = parse_audio_metadata(raw, file_name)
        try:
            relative = self.save_data_file(
                raw, file_name, "site_music_files", max_bytes=max_file_bytes
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
        if not title or not artist:
            # 文件里没有标签时，退而求其次从文件名猜（例如「茶汤-郁可唯」）
            guess_title, guess_artist = guess_title_and_artist(os.path.splitext(file_name)[0])
            if not title:
                title = metadata.get("title") or guess_title
            if not artist:
                artist = metadata.get("artist") or guess_artist
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
        self.log_activity(
            "music_upload",
            f"上传歌曲：{title or file_name}",
            target_type="music",
            target_id=row_id,
        )
        self.notify_members_new_content(
            "music_new", "music", row_id, "管理员", "上传了一首歌"
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
            execute(
                # 下载申请功能已下线，这里只清理历史行，避免删歌后留下孤儿记录
                "DELETE FROM download_requests WHERE resource_type = 'music' AND resource_id = ?",
                (item_id,),
            )
            clear_notification_target("music", item_id)
            execute(
                """UPDATE share_links SET revoked_at = ?
                   WHERE resource_type = 'music' AND resource_id = ? AND revoked_at IS NULL""",
                (now_text(), item_id),
            )
            self.log_activity(
                "music_delete",
                f"删除歌曲：{current.get('title') or item_id}",
                target_type="music",
                target_id=item_id,
            )
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

    # ---------- 书架 ----------

    def book_payload(self, row):
        item = dict(row)
        item["cover_url"] = "/site-files/" + item["cover_path"] if item.get("cover_path") else ""
        # 阅读器已下线，书架只提供下载；游客拿不到文件，标记出来让前端提示登录。
        item["requires_login"] = self.session_identity() is None
        return item

    def api_books(self, params):
        rows = query("SELECT * FROM books ORDER BY sort_order, id")
        is_admin = self.is_admin()
        items = []
        for row in rows:
            item = self.book_payload(row)
            if not is_admin:
                item.pop("file_path", None)
            items.append(item)
        self.send_json(200, items)

    def api_book_upload(self, payload):
        file_name = os.path.basename(str(payload.get("file_name") or "book.epub"))
        extension = os.path.splitext(file_name)[1].lower()
        if extension not in BOOK_EXTENSIONS:
            api_error(self, 400, "支持 EPUB、MOBI、AZW3、FB2、CBZ、PDF、TXT 和 Markdown。")
            return
        try:
            raw = base64.b64decode(str(payload.get("data_base64") or ""), validate=True)
        except Exception:
            api_error(self, 400, "电子书数据不是有效的 base64。")
            return
        if not raw:
            api_error(self, 400, "电子书内容为空。")
            return
        max_file_bytes = upload_limit("book_file")["max_file_bytes"]
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                f"单个电子书不能超过 {format_upload_limit_bytes(max_file_bytes)}。",
            )
            return
        metadata = parse_book_metadata(raw, file_name)
        guess_title, guess_author = guess_book_name(os.path.splitext(file_name)[0])
        title = (
            str(payload.get("title") or "").strip()[:200]
            or metadata.get("title")
            or guess_title
        )
        author = (
            str(payload.get("author") or "").strip()[:200]
            or metadata.get("author")
            or guess_author
        )
        description = (
            str(payload.get("description") or "").strip()[:1000]
            or metadata.get("description")
            or ""
        )
        tags = str(payload.get("tags") or "").strip()[:200]
        try:
            relative = self.save_data_file(
                raw, file_name, "book_files", max_bytes=max_file_bytes
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
                    "book_covers",
                    max_bytes=BOOK_COVER_MAX_BYTES,
                )
            except ValueError:
                cover_path = None
        sort_order = query_one("SELECT COALESCE(MAX(sort_order), -1) + 1 AS value FROM books")["value"]
        stamp = now_text()
        row_id = execute(
            """INSERT INTO books
                   (title, author, tags, description, format, file_path, cover_path,
                    file_size, mime_type, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title or "未命名电子书",
                author or None,
                tags or None,
                description or None,
                extension.lstrip("."),
                relative,
                cover_path,
                len(raw),
                mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                sort_order,
                stamp,
                stamp,
            ),
        )
        row = query_one("SELECT * FROM books WHERE id = ?", (row_id,))
        self.log_activity(
            "book_upload",
            f"上架电子书：{title or '未命名电子书'}",
            target_type="book",
            target_id=row_id,
        )
        self.notify_members_new_content(
            "book_new", "books", row_id, "管理员", "上架了一本电子书"
        )
        self.send_json(200, self.book_payload(row))

    def api_book_download(self, book_id):
        resource = self.download_resource("book", book_id)
        if not resource:
            api_error(self, 404, "电子书不存在。")
            return
        # 登录后直接下载，不再需要申请与审核
        if self.session_identity() is None:
            api_error(self, 401, "请登录后操作")
            return
        self.log_activity(
            "book_download",
            f"下载电子书：{resource['title']}",
            target_type="book",
            target_id=book_id,
        )
        self.send_data_file(
            resource["file_path"],
            resource["download_name"],
            allow_range=True,
        )

    def api_book_item(self, path):
        item_id = int(path.rstrip("/").rsplit("/", 1)[-1])
        current = query_one("SELECT * FROM books WHERE id = ?", (item_id,))
        if not current:
            api_error(self, 404, "电子书不存在。")
            return
        if self.command == "DELETE":
            self.log_activity(
                "book_delete",
                f"删除电子书：{current.get('title') or item_id}",
                target_type="book",
                target_id=item_id,
            )
            if current.get("file_path"):
                remove_data_file(current["file_path"])
            if current.get("cover_path"):
                remove_data_file(current["cover_path"])
            execute("DELETE FROM books WHERE id = ?", (item_id,))
            execute(
                # 下载申请功能已下线，这里只清理历史行，避免删书后留下孤儿记录
                "DELETE FROM download_requests WHERE resource_type = 'book' AND resource_id = ?",
                (item_id,),
            )
            clear_notification_target("books", item_id)
            execute(
                """UPDATE share_links SET revoked_at = ?
                   WHERE resource_type = 'book' AND resource_id = ? AND revoked_at IS NULL""",
                (now_text(), item_id),
            )
            self.send_json(200, {"ok": True})
            return
        payload = get_payload(self)
        if payload is None:
            return
        title = str(payload.get("title", current.get("title", "")) or "").strip()[:200]
        if not title:
            api_error(self, 400, "书名不能为空。")
            return
        author = str(payload.get("author", current.get("author", "")) or "").strip()[:200]
        tags = str(payload.get("tags", current.get("tags", "")) or "").strip()[:200]
        description = str(
            payload.get("description", current.get("description", "")) or ""
        ).strip()[:1000]
        try:
            sort_order = int(payload.get("sort_order", current.get("sort_order", 0)) or 0)
        except (TypeError, ValueError):
            api_error(self, 400, "排序值必须是整数。")
            return
        execute(
            """UPDATE books SET title = ?, author = ?, tags = ?, description = ?,
                   sort_order = ?, updated_at = ? WHERE id = ?""",
            (title, author or None, tags or None, description or None, sort_order, now_text(), item_id),
        )
        self.log_activity(
            "book_update",
            f"编辑电子书：{title}",
            target_type="book",
            target_id=item_id,
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

    def map_creator_name(self, user_id):
        if user_id in (None, 0):
            return "管理员"
        row = query_one("SELECT nickname, username FROM users WHERE id = ?", (user_id,))
        if not row:
            return "某位用户"
        return str(row.get("nickname") or row.get("username") or "某位用户")[:32]

    def map_created_by_label(self, creator_id, creators, viewer_signed_in):
        """地图上的「添加者」展示名：游客看不到普通账号的用户名。"""
        if creator_id in (None, 0):
            return "管理员"
        user = creators.get(creator_id)
        if not user:
            return "未知用户"
        nickname = str(user.get("nickname") or "").strip()
        if nickname:
            return nickname[:16]
        if viewer_signed_in:
            return str(user.get("username") or "普通用户")[:32]
        return "普通用户"

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

    def api_map(self, params=None):
        params = params or {}
        dock_mode = str((params.get("dock") or [""])[0] or "") == "1"
        identity = self.session_identity()
        is_admin = self.is_admin()
        user_id = self.map_identity_user_id()
        places = self.map_place_rows()
        photos = self.map_photos_map([row["id"] for row in places])
        notify_targets = []
        if identity:
            live_ids = {int(row["id"]) for row in places}
            notify_targets = [
                target_id
                for target_id in unseen_notification_targets(user_id, "map")
                if target_id in live_ids
            ]
        creator_ids = sorted(
            {row["created_by"] for row in places if row.get("created_by") not in (None, 0)}
        )
        creators = {}
        if creator_ids:
            placeholders = ",".join("?" for _ in creator_ids)
            for user in query(
                f"SELECT id, username, nickname FROM users WHERE id IN ({placeholders})",
                tuple(creator_ids),
            ):
                creators[user["id"]] = user
        viewer_signed_in = identity is not None
        unseen_ids = []
        if identity:
            view_row = query_one(
                "SELECT last_seen_id FROM map_place_views WHERE user_id = ?",
                (user_id if user_id is not None else 0,),
            )
            if view_row:
                seen_id = int(view_row["last_seen_id"] or 0)
                unseen_ids = [
                    int(place["id"]) for place in places if int(place["id"]) > seen_id
                ]
            else:
                unseen_ids = [
                    int(place["id"])
                    for place in places
                    if is_recent_place(place.get("created_at"))
                ]
        for row in places:
            row["photos"] = photos.get(row["id"], [])
            row["fresh"] = bool(identity and int(row["id"]) in notify_targets)
            row["created_by_name"] = self.map_created_by_label(
                row.get("created_by"), creators, viewer_signed_in
            )
            row["can_edit"] = bool(
                identity
                and (
                    is_admin
                    or (user_id is not None and row.get("created_by") == user_id)
                )
            )
        categories = self.map_category_rows()
        if dock_mode:
            # 首页/悬浮圆盘只需要坐标和分类颜色，去掉备注、照片等大字段
            places = [
                {
                    "id": row["id"],
                    "lat": row["lat"],
                    "lng": row["lng"],
                    "category_id": row["category_id"],
                    "created_at": row["created_at"],
                }
                for row in places
            ]
            categories = [
                {"id": cat["id"], "color": cat.get("color")} for cat in categories
            ]
        self.send_json(
            200,
            {
                "categories": categories,
                "places": places,
                "can_manage": is_admin,
                "can_add": self.can("map:write"),
                "can_import": is_admin,
                "can_manage_categories": self.can("map:manage_categories"),
                # 只有管理员能按「添加者」挑人；普通账户只能看「全部」或「只看自己添加的」
                "can_filter_owner": is_admin,
                "user_id": user_id,
                "signed_in": identity is not None,
                "map_public": MAP_PUBLIC,
                "unseen_count": len(unseen_ids),
                "newest_unseen_id": max(unseen_ids) if unseen_ids else 0,
                "notify_targets": notify_targets,
                "notify_count": len(notify_targets),
            },
        )

    def amap_poi_search(self, keywords, city=""):
        """调用高德 Web 服务 POI 搜索；带内存缓存，避免重复消耗月配额。"""
        params = {
            "key": AMAP_WEB_KEY,
            "keywords": keywords,
            "offset": 20,
            "page": 1,
            "extensions": "base",
        }
        if city:
            params["city"] = city
            params["citylimit"] = "true"
        cache_key = json.dumps(params, sort_keys=True, ensure_ascii=False)
        now = time.time()
        with AMAP_POI_CACHE_LOCK:
            cached = AMAP_POI_CACHE.get(cache_key)
            if cached and now - cached[0] < AMAP_POI_CACHE_TTL:
                return cached[1]
        url = "https://restapi.amap.com/v3/place/text?" + urlencode(params)
        request = Request(url, headers={"User-Agent": "ErrorJiang/1.0"})
        try:
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8", "replace") or "{}")
        except (URLError, socket.timeout, OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"高德接口请求失败：{exc}") from exc
        if str(payload.get("status")) != "1":
            info = str(payload.get("info") or "未知错误")
            infocode = str(payload.get("infocode") or "")
            raise ValueError(f"高德接口返回错误：{info}（{infocode}）")
        pois = []
        for item in payload.get("pois") or []:
            location = str(item.get("location") or "")
            lng_text, _, lat_text = location.partition(",")
            try:
                lng_value = float(lng_text)
                lat_value = float(lat_text)
            except ValueError:
                continue
            telephone = item.get("tel")
            if isinstance(telephone, list):
                telephone = " / ".join(str(value) for value in telephone if value)
            pois.append(
                {
                    "id": item.get("id") or "",
                    "name": item.get("name") or "",
                    "type": item.get("type") or "",
                    "typecode": item.get("typecode") or "",
                    "address": item.get("address") or "",
                    "tel": telephone or "",
                    "lng": lng_value,
                    "lat": lat_value,
                }
            )
        result = {
            "count": int(payload.get("count") or 0),
            "pois": pois,
            "coord": "gcj02",
        }
        with AMAP_POI_CACHE_LOCK:
            if len(AMAP_POI_CACHE) >= AMAP_POI_CACHE_LIMIT:
                AMAP_POI_CACHE.clear()
            AMAP_POI_CACHE[cache_key] = (now, result)
        return result

    def api_map_poi_search(self, params):
        """按关键字搜索高德 POI，供「添加标记」弹窗直接选用。"""
        if not self.can("map:write"):
            api_error(self, 403, "当前账号没有添加标记的权限。")
            return
        if not AMAP_WEB_KEY:
            api_error(self, 503, "还没有配置高德 Key，请联系管理员在服务器设置 INVENTORY_AMAP_KEY。")
            return
        keywords = str((params.get("keywords") or [""])[0] or "").strip()[:80]
        city = str((params.get("city") or [""])[0] or "").strip()[:40]
        if not keywords:
            api_error(self, 400, "请输入要搜索的地点名称。")
            return
        if not rate_allow("amap_search", self.client_ip(), 60, 60):
            api_error(self, 429, "搜索太频繁，请稍后再试。")
            return
        try:
            data = self.amap_poi_search(keywords, city)
        except ValueError as exc:
            api_error(self, 502, str(exc))
            return
        self.send_json(200, data)

    def api_map_mark_seen(self, payload=None):
        """更新「已看到标记」；如带 notify_targets 则同时把地图提醒标记已读。"""
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        user_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        payload = payload or {}
        raw_targets = payload.get("notify_targets")
        cleared = 0
        if isinstance(raw_targets, list):
            seen = set()
            for value in raw_targets:
                if not str(value).isdigit():
                    continue
                target_id = int(value)
                if target_id <= 0 or target_id in seen:
                    continue
                seen.add(target_id)
                mark_notifications_seen(user_id, "map", target_id)
                cleared += 1
        row = query_one("SELECT COALESCE(MAX(id), 0) AS value FROM map_places")
        newest = int(row["value"] if row else 0)
        execute(
            """INSERT INTO map_place_views (user_id, last_seen_id, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   last_seen_id = excluded.last_seen_id,
                   updated_at = excluded.updated_at""",
            (user_id, newest, now_text()),
        )
        self.send_json(200, {"last_seen_id": newest, "cleared": cleared})

    def map_category_payload(self, payload, current=None, category_id=None):
        current = current or {}
        name = str(payload.get("name", current.get("name", "")) or "").strip()[:60]
        if not name:
            raise ValueError("分类名称不能为空。")
        glyph = str(payload.get("glyph", current.get("glyph", "·")) or "·").strip()[:2] or "·"
        old_name = str(current.get("name") or "").strip()
        # 自动图标（旧名字首字，或还没设置时的占位「·」）跟随改名更新，自定义图标保留
        if old_name and name != old_name and glyph in (old_name[:1], "·"):
            glyph = name[:1] or "·"
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
            api_error(self, 401, "请登录后操作")
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
        name = values[1] or "未命名地点"
        address = values[3] or ""
        author = self.map_creator_name(user_id)
        link = self.request_base_url() + f"/map?place={row_id}"
        detail = f"{author} 新增了标记点「{name}」"
        if address:
            detail += f"（{address}）"
        # 站长自己在足迹页新增标记不推 Webhook（自己的操作不用推给自己）；
        # 普通账号（默认有 map:write）新增时照旧推送
        if not self.is_admin():
            notify_async(
                "place",
                "Error酱：有新的标记点",
                f"{detail}\n查看位置：{link}",
                link,
            )
        self.log_activity(
            "map_place_create",
            f"新增标记「{name}」" + (f"（{address}）" if address else ""),
            target_type="map_place",
            target_id=row_id,
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
            execute(
                "DELETE FROM map_place_interactions WHERE place_id = ?", (place_id,)
            )
            execute(
                """DELETE FROM user_notifications
                   WHERE module = 'map' AND target_id = ?""",
                (place_id,),
            )
            execute("DELETE FROM map_places WHERE id = ?", (place_id,))
            for photo in photos:
                remove_data_file(photo.get("file_path"))
            self.log_activity(
                "map_place_delete",
                f"删除标记「{current.get('name') or place_id}」",
                target_type="map_place",
                target_id=place_id,
            )
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
        self.log_activity(
            "map_place_update",
            f"编辑标记「{values[1] or current.get('name') or place_id}」",
            target_type="map_place",
            target_id=place_id,
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
        limits = upload_limit("map_photo")
        max_count = limits["max_count"]
        max_file_bytes = limits["max_file_bytes"]
        if count >= max_count:
            api_error(self, 400, f"每个标记最多 {max_count} 张照片。")
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
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                f"单张照片不能超过 {format_upload_limit_bytes(max_file_bytes)}。",
            )
            return
        try:
            relative = self.save_data_file(
                raw, name, "map_images", max_bytes=max_file_bytes
            )
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
        self.log_activity(
            "map_photo_upload",
            f"给标记「{place.get('name') or place_id}」上传照片",
            target_type="map_place",
            target_id=place_id,
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
        self.log_activity(
            "map_photo_delete",
            f"删除标记「{(place or {}).get('name') or photo['place_id']}」的照片",
            target_type="map_place",
            target_id=photo["place_id"],
        )
        self.send_json(200, {"ok": True})

    def api_map_import(self, payload):
        user_id = self.map_identity_user_id()
        if user_id is None:
            api_error(self, 401, "请登录后操作")
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
                        # 导入文件里没带图标时，用分类名首字，别留一个没有意义的「·」
                        glyph = (
                            str(properties.get("category_glyph") or "").strip()[:2]
                            or (top_name[:1] or "·")
                        )
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
                                glyph = (
                                    str(properties.get("category_glyph") or "").strip()[:2]
                                    or (child_name[:1] or "·")
                                )
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
        self.log_activity(
            "prompt_create",
            f"新增提示词：{title}",
            target_type="prompt",
            target_id=prompt_id,
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
            self.log_activity(
                "prompt_delete",
                f"删除提示词：{current.get('title') or prompt_id}",
                target_type="prompt",
                target_id=prompt_id,
            )
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
        self.log_activity(
            "prompt_update",
            f"编辑提示词：{title}" + ("（置顶）" if pinned else ""),
            target_type="prompt",
            target_id=prompt_id,
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
        identity = self.session_identity()
        if not identity:
            api_error(self, 401, "请登录后操作")
            return
        item_id = int(path.split("/")[4])
        target = query_one(
            "SELECT id, content, user_id FROM site_messages WHERE id = ?",
            (item_id,),
        )
        if not target:
            api_error(self, 404, "留言不存在。")
            return
        # 管理员可删任意留言；普通账号只能删自己发的
        viewer_id = (
            0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        )
        if not self.is_admin() and (
            viewer_id == 0 or int(target.get("user_id") or 0) != viewer_id
        ):
            api_error(self, 403, "只能删除自己的留言。")
            return
        rows = query(
            """SELECT file_path FROM site_message_files
               WHERE message_id = ?
                  OR message_id IN (SELECT id FROM site_messages WHERE parent_id = ?)""",
            (item_id, item_id),
        )
        like_ids = [item_id] + [
            int(row["id"])
            for row in query(
                "SELECT id FROM site_messages WHERE parent_id = ?", (item_id,)
            )
        ]
        placeholders = ",".join("?" for _ in like_ids)
        execute(
            f"""DELETE FROM content_likes
                WHERE target_type = 'message' AND target_id IN ({placeholders})""",
            tuple(like_ids),
        )
        execute("DELETE FROM site_messages WHERE id = ?", (item_id,))
        for row in rows:
            remove_data_file(row.get("file_path"))
        excerpt = (target.get("content") or "（仅附件）")[:40]
        self.log_activity(
            "message_delete",
            f"删除留言 #{item_id}：{excerpt}",
            target_type="message",
            target_id=item_id,
            actor=identity,
        )
        # 删除类操作不推 Webhook（和「删除标记不推送」同一条规则），只在内容事件里留记录
        self.send_json(200, {"ok": True})

    def api_site_message_file(self, path):
        """
        留言附件：已通过的留言附件都能看；游客额外只放行图片，
        非图片附件（PDF / 文本等）仍然要求登录；待审附件只有作者和管理员看得到。
        """
        file_id = int(path.rsplit("/", 1)[1])
        row = query_one(
            """SELECT f.*, m.status AS message_status, m.user_id AS message_user_id
               FROM site_message_files f
               LEFT JOIN site_messages m ON m.id = f.message_id
               WHERE f.id = ?""",
            (file_id,),
        )
        if not row:
            api_error(self, 404, "附件不存在。")
            return
        identity = self.session_identity()
        is_admin = self.is_admin()
        viewer_id = None
        if identity:
            viewer_id = 0 if identity.get("kind") == "owner" else identity.get("user_id")
        owned = bool(
            viewer_id is not None
            and (
                row.get("uploaded_by") == viewer_id
                or row.get("message_user_id") == viewer_id
            )
        )
        approved = (
            (row.get("status") or "approved") == "approved"
            and (row.get("message_status") or "approved") == "approved"
        )
        if not approved and not is_admin:
            if not owned:
                api_error(self, 403, "附件正在审核中。")
                return
        if identity is None:
            extension = os.path.splitext(row.get("file_name") or "")[1].lower()
            if extension not in MESSAGE_IMAGE_EXTENSIONS:
                api_error(self, 401, "请登录后操作")
                return
        self.send_data_file(row["file_path"])

    # ---------- 首页公开动态 ----------
    def api_site_activity(self):
        identity = self.session_identity()
        if identity is None:
            # 游客不显示首页左下角动态区，也不返回任何动态数据
            self.send_json(200, {"items": [], "admin": False, "signed_in": False})
            return
        viewer_signed_in = True
        is_admin = self.is_admin()
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        actions = tuple(PUBLIC_ACTIVITY_LABELS)
        placeholders = ",".join("?" for _ in actions)
        rows = query(
            f"""SELECT a.id, a.action, a.actor_kind, a.user_id, a.created_at, a.summary,
                       a.target_type, a.target_id,
                       u.username AS member_username
                FROM activity_log a
                LEFT JOIN users u ON u.id = a.user_id
                WHERE a.created_at >= ? AND a.action IN ({placeholders})
                ORDER BY a.id DESC
                LIMIT 200""",
            (cutoff, *actions),
        )
        items = []
        # 提醒单独收集：公开动态可能有上百条，提醒必须保证不被截断
        alerts = []
        for row in rows:
            kind = str(row.get("actor_kind") or "guest")
            user_id = int(row.get("user_id") or 0)
            if kind not in ("owner", "admin", "member") or (kind == "member" and user_id <= 0):
                continue
            if kind in ("owner", "admin"):
                actor = "管理员"
            elif viewer_signed_in:
                actor = str(row.get("member_username") or "普通用户")[:32]
            else:
                actor = mask_username(row.get("member_username"))
            items.append(
                {
                    "id": f"activity-{row['id']}",
                    "created_at": row["created_at"],
                    "actor": actor,
                    "text": PUBLIC_ACTIVITY_LABELS[row["action"]],
                    "alert": False,
                    "_action": str(row.get("action") or ""),
                    "_target_type": row.get("target_type") or "",
                    "_target_id": int(row.get("target_id") or 0),
                }
            )

        def grouped_unseen_notifications(account_id):
            grouped = {}
            for notification in unseen_notification_rows(account_id):
                module = str(notification.get("module") or "")
                grouped.setdefault(module, []).append(notification)
            return grouped

        def mark_activity_alerts(module_rows):
            matched_ids = set()
            for notification in module_rows:
                target_id = int(notification.get("target_id") or 0)
                actions = NOTIFICATION_ACTIVITY_ACTIONS.get(
                    str(notification.get("kind") or "")
                )
                if target_id <= 0 or not actions:
                    continue
                for item in items:
                    if (
                        item.get("_target_id") == target_id
                        and item.get("_action") in actions
                    ):
                        item["alert"] = True
                        matched_ids.add(int(notification.get("id") or 0))
                        break
            return matched_ids

        def notification_info(module_rows):
            latest = module_rows[-1]
            return {
                "count": len(module_rows),
                "kind": str(latest.get("kind") or ""),
                "text": str(latest.get("text") or ""),
                "actor": str(latest.get("actor") or ""),
                "created_at": str(latest.get("created_at") or ""),
            }

        def strip_internal_fields():
            for item in items:
                item.pop("_action", None)
                item.pop("_target_type", None)
                item.pop("_target_id", None)

        if is_admin:
            admin_user_id = (
                0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
            )
            last_seen = message_last_seen(admin_user_id)
            newest_message = query_one(
                "SELECT created_at FROM site_messages WHERE id > ? ORDER BY id DESC LIMIT 1",
                (last_seen,),
            )
            unread_message_items = [
                item
                for item in items
                if item.get("_target_type") == "message"
                and item.get("_target_id", 0) > last_seen
            ]
            if newest_message and unread_message_items:
                unread = query_one(
                    "SELECT COUNT(*) AS n FROM site_messages WHERE id > ?",
                    (last_seen,),
                )["n"]
                newest_item = max(
                    unread_message_items, key=lambda item: int(item.get("_target_id") or 0)
                )
                newest_item.update(
                    {
                        "created_at": newest_message["created_at"],
                        "actor": "管理员",
                        "text": f"有 {int(unread)} 条未读留言",
                        "alert": True,
                    }
                )
            elif newest_message:
                unread = query_one(
                    "SELECT COUNT(*) AS n FROM site_messages WHERE id > ?",
                    (last_seen,),
                )["n"]
                alerts.append(
                    {
                        "id": "message-alert",
                        "created_at": newest_message["created_at"],
                        "actor": "管理员",
                        "text": f"有 {int(unread)} 条未读留言",
                        "alert": True,
                    }
                )
            pending_users = query_one(
                "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'"
            )["n"]
            if pending_users:
                newest_user = query_one(
                    """SELECT created_at FROM users
                       WHERE status = 'pending' ORDER BY id DESC LIMIT 1"""
                )
                alerts.append(
                    {
                        "id": "pending-user-alert",
                        "created_at": (newest_user or {}).get("created_at") or now_text(),
                        "actor": "管理员",
                        "text": f"有 {int(pending_users)} 个待审核注册申请",
                        "alert": True,
                    },
                )
            pending_messages = query_one(
                """SELECT COUNT(*) AS n FROM site_messages
                   WHERE parent_id IS NULL AND status = 'pending'"""
            )["n"]
            pending_legacy = query_one(
                """SELECT COUNT(*) AS n FROM site_message_files f
                   JOIN site_messages m ON m.id = f.message_id
                   WHERE f.status = 'pending' AND m.parent_id IS NULL
                     AND m.status = 'approved'"""
            )["n"]
            pending_reviews = int(pending_messages) + int(pending_legacy)
            if pending_reviews:
                newest_pending = query_one(
                    """SELECT created_at FROM site_messages
                       WHERE parent_id IS NULL AND status = 'pending'
                       ORDER BY id DESC LIMIT 1"""
                )
                alerts.append(
                    {
                        "id": "message-review-alert",
                        "created_at": (newest_pending or {}).get("created_at") or now_text(),
                        "actor": "管理员",
                        "text": f"有 {pending_reviews} 条留言待审核",
                        "alert": True,
                    },
                )
            pending_reports = query_one(
                "SELECT COUNT(*) AS n FROM content_reports WHERE status = 'pending'"
            )["n"]
            if pending_reports:
                newest_report = query_one(
                    """SELECT created_at FROM content_reports
                       WHERE status = 'pending' ORDER BY id DESC LIMIT 1"""
                )
                alerts.append(
                    {
                        "id": "report-alert",
                        "created_at": (newest_report or {}).get("created_at") or now_text(),
                        "actor": "管理员",
                        "text": f"有 {int(pending_reports)} 个待处理举报",
                        "alert": True,
                    }
                )
            # 站长自己收到的新动态评论、留言点赞 / 回复
            for module, module_rows in grouped_unseen_notifications(
                admin_user_id
            ).items():
                matched_ids = mark_activity_alerts(module_rows)
                remaining = [
                    notification
                    for notification in module_rows
                    if int(notification.get("id") or 0) not in matched_ids
                ]
                if not remaining:
                    continue
                info = notification_info(remaining)
                alert_actor = "提醒" if module == "map" else info.get("actor") or "提醒"
                alerts.append(
                    {
                        "id": f"notify-{module}",
                        "created_at": info.get("created_at") or now_text(),
                        "actor": alert_actor,
                        "text": notification_alert_text(module, info),
                        "alert": True,
                    }
                )
        elif identity:
            # 普通账号：新动态、被点赞、被回复的提醒
            user_id = int(identity.get("user_id") or 0)
            for module, module_rows in grouped_unseen_notifications(user_id).items():
                matched_ids = mark_activity_alerts(module_rows)
                remaining = [
                    notification
                    for notification in module_rows
                    if int(notification.get("id") or 0) not in matched_ids
                ]
                if not remaining:
                    continue
                info = notification_info(remaining)
                alerts.append(
                    {
                        "id": f"notify-{module}",
                        "created_at": info.get("created_at") or now_text(),
                        "actor": info.get("actor") or "提醒",
                        "text": notification_alert_text(module, info),
                        "alert": True,
                    }
                )
        strip_internal_fields()
        budget = max(0, 60 - len(alerts))
        self.send_json(
            200,
            {
                "items": alerts + items[:budget],
                "admin": is_admin,
                "signed_in": True,
            },
        )

    def api_site_sidebar(self):
        """留言 / 动态页左右侧栏的数据。

        四张卡片游客也照常展示：统计、封面、更新日志都不脱敏下发；只有「注册账户」
        列表是登录后才给的（游客那边前端只摆一位并提示登录）。
        """
        identity = self.session_identity()
        # 当前这台设备读出来是什么（Windows / macOS / Linux / Android / iOS），
        # 前端只拿它多出一个「在线-Win」这类选项，不多不少
        viewer_device = device_suffix(
            self.client_platform(), self.headers.get("User-Agent") or ""
        )
        if identity is None:
            self.send_json(
                200,
                {
                    "viewer": {
                        "signed_in": False,
                        "name": "游客",
                        "role": "guest",
                        "device": viewer_device,
                    },
                    "stats": sidebar_stats(),
                    "covers": sidebar_covers(),
                    "users": sidebar_users(masked=True),
                    "activities": sidebar_activities(),
                    # 游客不是站长本人：站长设了隐身的话，游客看到的是「离线」
                    "presence": owner_status_for(False),
                },
            )
            return
        is_admin = self.is_admin()
        viewer_id = (
            0 if identity.get("kind") == "owner" else int(identity.get("user_id") or 0)
        )
        viewer_name = str(
            identity.get("nickname") or identity.get("username") or "已登录"
        )
        # 站长没有 users 行，就用建站天数当「注册天数」，避免卡片上出现 0
        viewer_row = (
            query_one("SELECT created_at FROM users WHERE id = ?", (viewer_id,))
            if viewer_id
            else None
        )
        registered_days = days_since((viewer_row or {}).get("created_at")) or days_since(
            site_started_at()
        )
        self.send_json(
            200,
            {
                "viewer": {
                    "signed_in": True,
                    "name": viewer_name,
                    "role": str(identity.get("role") or "member"),
                    "admin": bool(is_admin),
                    "registered_days": registered_days,
                    "device": viewer_device,
                },
                "stats": sidebar_stats(),
                "covers": sidebar_covers(),
                "users": sidebar_users(
                    viewer_id, viewer_is_admin=is_admin
                ),
                "activities": sidebar_activities(),
                "presence": owner_status_for(
                    identity.get("kind") in ("owner", "admin")
                ),
            },
        )

    def report_target(self, target_type, target_key):
        """校验举报对象并返回可长期保存的内容快照。所有公开内容游客也能举报。"""
        target_type = str(target_type or "").strip()
        target_key = str(target_key or "").strip()[:80]
        if target_type not in REPORT_TARGET_TYPES or not target_key:
            raise ValueError("举报对象不正确。")

        if target_type == "message":
            if not target_key.isdigit():
                raise ValueError("举报对象不正确。")
            row = query_one(
                """SELECT id, nickname, content, status, created_at
                   FROM site_messages WHERE id = ?""",
                (int(target_key),),
            )
            if not row:
                raise LookupError("留言不存在。")
            if row.get("status") != "approved":
                raise ValueError("只能举报已经审核通过的留言。")
            return (
                f"留言 #{row['id']}",
                {
                    "id": row["id"],
                    "nickname": row.get("nickname") or "",
                    "content": str(row.get("content") or "")[:1000],
                    "created_at": row.get("created_at") or "",
                    "status": row.get("status") or "",
                },
            )

        if target_type == "moment":
            if not target_key.isdigit():
                raise ValueError("举报对象不正确。")
            row = query_one(
                "SELECT id, content, tags, created_at FROM moments WHERE id = ?",
                (int(target_key),),
            )
            if not row:
                raise LookupError("动态不存在。")
            return (
                f"动态 #{row['id']}",
                {
                    "id": row["id"],
                    "content": str(row.get("content") or "")[:2000],
                    "tags": row.get("tags") or "",
                    "created_at": row.get("created_at") or "",
                },
            )

        if target_type == "book":
            if not target_key.isdigit():
                raise ValueError("举报对象不正确。")
            row = query_one(
                """SELECT id, title, author, description, format, created_at
                   FROM books WHERE id = ?""",
                (int(target_key),),
            )
            if not row:
                raise LookupError("电子书不存在。")
            return (
                str(row.get("title") or f"电子书 #{row['id']}")[:160],
                {
                    "id": row["id"],
                    "title": row.get("title") or "",
                    "author": row.get("author") or "",
                    "description": str(row.get("description") or "")[:1000],
                    "format": row.get("format") or "",
                    "created_at": row.get("created_at") or "",
                },
            )

        if target_type == "recommendation":
            if not target_key.isdigit():
                raise ValueError("举报对象不正确。")
            row = query_one(
                """SELECT id, kind, title, subtitle, description, created_at
                   FROM recommendations WHERE id = ?""",
                (int(target_key),),
            )
            if not row:
                raise LookupError("推荐内容不存在。")
            return (
                str(row.get("title") or f"推荐 #{row['id']}")[:160],
                {
                    "id": row["id"],
                    "kind": row.get("kind") or "",
                    "title": row.get("title") or "",
                    "subtitle": row.get("subtitle") or "",
                    "description": str(row.get("description") or "")[:1000],
                    "created_at": row.get("created_at") or "",
                },
            )

        if target_type == "music":
            if not target_key.isdigit():
                raise ValueError("举报对象不正确。")
            row = query_one(
                """SELECT id, title, artist, album, created_at
                   FROM site_music WHERE id = ?""",
                (int(target_key),),
            )
            if not row:
                raise LookupError("歌曲不存在。")
            return (
                str(row.get("title") or f"歌曲 #{row['id']}")[:160],
                {
                    "id": row["id"],
                    "title": row.get("title") or "",
                    "artist": row.get("artist") or "",
                    "album": row.get("album") or "",
                    "created_at": row.get("created_at") or "",
                },
            )
        raise ValueError("举报对象不正确。")

    def api_site_report_create(self, payload):
        if not rate_allow("site_report", self.client_ip(), 10, 3600):
            api_error(self, 429, "举报提交过于频繁，请稍后再试。")
            return
        identity = self.session_identity()
        target_type = str(payload.get("target_type") or "").strip()
        target_key = str(payload.get("target_key") or payload.get("target_id") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        detail = str(payload.get("detail") or "").strip()[:1000]
        contact = str(payload.get("contact") or "").strip()[:200]
        if reason not in REPORT_REASONS:
            api_error(self, 400, "请选择举报理由。")
            return
        try:
            target_title, snapshot = self.report_target(target_type, target_key)
        except PermissionError as exc:
            api_error(self, 401, str(exc))
            return
        except LookupError as exc:
            api_error(self, 404, str(exc))
            return
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        reporter_user_id = (
            0
            if identity and identity.get("kind") == "owner"
            else int((identity or {}).get("user_id") or 0)
        )
        if identity:
            reporter_name = self.notification_actor_name(identity)
        else:
            reporter_name = "游客"
        cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        if reporter_user_id:
            duplicate = query_one(
                """SELECT id FROM content_reports
                   WHERE target_type = ? AND target_key = ?
                     AND reporter_user_id = ? AND created_at >= ?""",
                (target_type, target_key, reporter_user_id, cutoff),
            )
        else:
            duplicate = query_one(
                """SELECT id FROM content_reports
                   WHERE target_type = ? AND target_key = ?
                     AND ip = ? AND created_at >= ?""",
                (target_type, target_key, self.client_ip(), cutoff),
            )
        if duplicate:
            api_error(self, 429, "同一内容 24 小时内无需重复举报。")
            return
        client_ip = self.client_ip()
        region = lookup_ip_region(client_ip) if client_ip else ""
        report_id = execute(
            """INSERT INTO content_reports
                   (target_type, target_key, target_title, target_snapshot,
                    reporter_user_id, reporter_name, reason, detail, contact,
                    ip, ip_region, user_agent, client_platform, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                target_type,
                target_key,
                target_title,
                json.dumps(snapshot, ensure_ascii=False),
                reporter_user_id,
                reporter_name,
                reason,
                detail or None,
                contact or None,
                client_ip,
                region,
                self.headers.get("User-Agent") or "",
                self.client_platform(),
                now_text(),
            ),
        )
        self.log_activity(
            "report_create",
            f"举报{REPORT_TARGET_LABELS.get(target_type, target_type)}：{target_title}",
            target_type=f"report_{target_type}",
            target_id=report_id,
            actor=identity,
            ip=client_ip,
            ip_region=region,
        )
        notify_async(
            "report",
            "Error酱：收到新的内容举报",
            f"{reporter_name} 举报了{REPORT_TARGET_LABELS.get(target_type, target_type)}「{target_title}」，"
            "请到工作台「举报处理」查看。",
            "/workbench?view=reports",
        )
        self.send_json(200, {"id": report_id, "status": "pending"})

    def admin_report_payload(self, row):
        item = dict(row)
        try:
            item["target_snapshot_data"] = json.loads(item.get("target_snapshot") or "{}")
        except json.JSONDecodeError:
            item["target_snapshot_data"] = {}
        created = str(item.get("created_at") or "")
        item["overdue"] = bool(
            item.get("status") == "pending"
            and created
            and created
            <= (datetime.now() - timedelta(hours=REPORT_SLA_HOURS)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        item["sla_hours"] = REPORT_SLA_HOURS
        return item

    def api_admin_reports(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以处理举报。")
            return
        status_filter = str((params.get("status") or ["pending"])[0] or "pending").strip()
        if status_filter not in ("pending", "resolved", "dismissed", "all"):
            status_filter = "pending"
        where = ""
        values = ()
        if status_filter != "all":
            where = "WHERE status = ?"
            values = (status_filter,)
        rows = query(
            f"""SELECT * FROM content_reports
                {where}
                ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                         created_at DESC, id DESC
                LIMIT 300""",
            values,
        )
        counts = {
            row["status"]: int(row["n"])
            for row in query(
                "SELECT status, COUNT(*) AS n FROM content_reports GROUP BY status"
            )
        }
        self.send_json(
            200,
            {
                "reports": [self.admin_report_payload(row) for row in rows],
                "counts": counts,
                "pending": int(counts.get("pending") or 0),
                "status": status_filter,
            },
        )

    def api_admin_report_action(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以处理举报。")
            return
        report_id = int(path.rstrip("/").rsplit("/", 1)[-1])
        row = query_one("SELECT * FROM content_reports WHERE id = ?", (report_id,))
        if not row:
            api_error(self, 404, "举报记录不存在。")
            return
        action = str(payload.get("action") or "").strip()
        if action not in ("resolve", "dismiss", "reopen"):
            api_error(self, 400, "未知处理操作。")
            return
        identity = self.session_identity()
        reviewer = (identity or {}).get("nickname") or "管理员"
        status = {
            "resolve": "resolved",
            "dismiss": "dismissed",
            "reopen": "pending",
        }[action]
        resolution = str(payload.get("resolution") or "").strip()[:1000]
        execute(
            """UPDATE content_reports
               SET status = ?, handled_by = ?, handled_at = ?, resolution = ?,
                   reminded_at = CASE WHEN ? = 'pending' THEN NULL ELSE reminded_at END
               WHERE id = ?""",
            (
                status,
                reviewer if status != "pending" else None,
                now_text() if status != "pending" else None,
                resolution or None,
                status,
                report_id,
            ),
        )
        write_audit(
            identity,
            f"report_{status}",
            resolution or row.get("target_title") or "",
            {"id": report_id, "nickname": row.get("target_title") or ""},
        )
        self.log_activity(
            f"report_{status}",
            f"处理举报 #{report_id}：{row.get('target_title') or ''}",
            target_type="report",
            target_id=report_id,
        )
        self.send_json(200, {"ok": True, "status": status})

    # ---------- ErrorJ Agent 内部工具接口 ----------
    @staticmethod
    def agent_limit(value, default=8, maximum=20):
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(1, min(number, maximum))

    def agent_has_permission(self, identity, permission):
        if not identity:
            return False
        if identity.get("kind") in ("owner", "admin"):
            return True
        return user_has_permission(identity.get("user_id"), permission)

    @staticmethod
    def agent_note_excerpt(content, limit=280):
        text = str(content or "")
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"[#>*_`~-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    def agent_tool_inventory_search(self, identity, args):
        if not self.agent_has_permission(identity, "inventory:view"):
            api_error(self, 403, "当前账号没有仓库查看权限。")
            return
        search = str(args.get("query") or "").strip()[:200]
        limit = self.agent_limit(args.get("limit"), 8, 12)
        where = ""
        params = []
        if search:
            like = f"%{search}%"
            where = """
                WHERE (p.part_number LIKE ? OR p.lcsc_code LIKE ? OR p.brand LIKE ?
                       OR p.description LIKE ? OR p.package LIKE ? OR p.notes LIKE ?)
            """
            params.extend([like] * 6)
        rows = query(
            part_summary_select()
            + where
            + " ORDER BY p.updated_at DESC, p.id DESC LIMIT ?",
            (*params, limit),
        )
        results = []
        for row in rows:
            batches = query(
                """SELECT b.quantity, b.received_quantity - b.quantity AS used_quantity,
                          l.code AS location_code, l.name AS location_name
                   FROM batches b JOIN locations l ON l.id = b.location_id
                   WHERE b.part_id = ? AND b.quantity > 0
                   ORDER BY l.code, b.id DESC""",
                (row["id"],),
            )
            results.append(
                {
                    "id": int(row["id"]),
                    "part_number": row.get("part_number") or "",
                    "lcsc_code": row.get("lcsc_code") or "",
                    "brand": row.get("brand") or "",
                    "package": row.get("package") or "",
                    "description": row.get("description") or "",
                    "notes": (row.get("notes") or "")[:1200],
                    "stock_quantity": row.get("stock_quantity") or 0,
                    "min_stock": row.get("min_stock") or 0,
                    "category": row.get("category_name") or "",
                    "datasheet_url": row.get("datasheet_url") or "",
                    "locations": [
                        {
                            "code": batch.get("location_code") or "",
                            "name": batch.get("location_name") or "",
                            "quantity": batch.get("quantity") or 0,
                        }
                        for batch in batches
                    ],
                }
            )
        self.send_json(200, {"query": search, "count": len(results), "results": results})

    def agent_tool_bookmark_search(self, identity, args):
        if not self.agent_has_permission(identity, "bookmarks:view"):
            api_error(self, 403, "当前账号没有书签查看权限。")
            return
        search = str(args.get("query") or "").strip()[:200]
        limit = self.agent_limit(args.get("limit"), 8, 15)
        where = ""
        params = []
        if search:
            like = f"%{search}%"
            where = """
                WHERE (b.title LIKE ? OR b.url LIKE ? OR b.description LIKE ?
                       OR f.name LIKE ?)
            """
            params.extend([like] * 4)
        rows = query(
            """SELECT b.id, b.title, b.url, b.description, b.link_status,
                      f.name AS folder_name
               FROM bookmarks b
               LEFT JOIN bookmark_folders f ON f.id = b.folder_id
            """
            + where
            + " ORDER BY b.updated_at DESC, b.id DESC LIMIT ?",
            (*params, limit),
        )
        results = [
            {
                "id": int(row["id"]),
                "title": row.get("title") or "",
                "url": row.get("url") or "",
                "description": (row.get("description") or "")[:600],
                "folder": row.get("folder_name") or "",
                "link_status": row.get("link_status") or "unknown",
            }
            for row in rows
        ]
        self.send_json(200, {"query": search, "count": len(results), "results": results})

    def agent_tool_note_search(self, identity, args):
        if not self.agent_has_permission(identity, "notes:view"):
            api_error(self, 403, "当前账号没有笔记查看权限。")
            return
        search = str(args.get("query") or "").strip()[:200]
        limit = self.agent_limit(args.get("limit"), 6, 10)
        where = ""
        params = []
        if search:
            like = f"%{search}%"
            where = "WHERE (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend([like, like, like])
        rows = query(
            """SELECT id, title, content, tags, created_at, updated_at
               FROM learning_notes
            """
            + where
            + " ORDER BY updated_at DESC, id DESC LIMIT ?",
            (*params, limit),
        )
        results = [
            {
                "id": int(row["id"]),
                "title": row.get("title") or "",
                "tags": row.get("tags") or "",
                "updated_at": row.get("updated_at") or "",
                "excerpt": self.agent_note_excerpt(row.get("content")),
            }
            for row in rows
        ]
        self.send_json(200, {"query": search, "count": len(results), "results": results})

    def agent_tool_note_read(self, identity, args):
        if not self.agent_has_permission(identity, "notes:view"):
            api_error(self, 403, "当前账号没有笔记查看权限。")
            return
        try:
            note_id = int(args.get("id"))
        except (TypeError, ValueError):
            api_error(self, 400, "笔记编号不正确。")
            return
        row = query_one(
            """SELECT id, title, content, tags, created_at, updated_at
               FROM learning_notes WHERE id = ?""",
            (note_id,),
        )
        if not row:
            api_error(self, 404, "笔记不存在。")
            return
        self.send_json(
            200,
            {
                "id": int(row["id"]),
                "title": row.get("title") or "",
                "tags": row.get("tags") or "",
                "created_at": row.get("created_at") or "",
                "updated_at": row.get("updated_at") or "",
                "content": (row.get("content") or "")[:12000],
                "truncated": len(row.get("content") or "") > 12000,
            },
        )

    def agent_tool_reviews_list(self, identity, args):
        if not self.agent_has_permission(identity, ADMIN_PERMISSION):
            api_error(self, 403, "只有管理员可以查看审核队列。")
            return
        limit = self.agent_limit(args.get("limit"), 8, 20)
        users = query(
            """SELECT id, username, nickname, created_at
               FROM users WHERE status = 'pending'
               ORDER BY created_at ASC, id ASC LIMIT ?""",
            (limit,),
        )
        messages = query(
            """SELECT id, nickname, content, created_at
               FROM site_messages
               WHERE parent_id IS NULL AND status = 'pending'
               ORDER BY created_at ASC, id ASC LIMIT ?""",
            (limit,),
        )
        reports = query(
            """SELECT id, target_type, target_title, reason, detail, created_at
               FROM content_reports WHERE status = 'pending'
               ORDER BY created_at ASC, id ASC LIMIT ?""",
            (limit,),
        )
        self.send_json(
            200,
            {
                "counts": {
                    "users": query_one(
                        "SELECT COUNT(*) AS n FROM users WHERE status = 'pending'"
                    )["n"],
                    "messages": query_one(
                        """SELECT COUNT(*) AS n FROM site_messages
                           WHERE parent_id IS NULL AND status = 'pending'"""
                    )["n"],
                    "reports": query_one(
                        "SELECT COUNT(*) AS n FROM content_reports WHERE status = 'pending'"
                    )["n"],
                },
                "users": users,
                "messages": messages,
                "reports": reports,
            },
        )

    def agent_tool_reviews_decide(self, identity, args):
        if not self.agent_has_permission(identity, ADMIN_PERMISSION):
            api_error(self, 403, "只有管理员可以执行审核。")
            return
        kind = str(args.get("kind") or "").strip()
        action = str(args.get("action") or "").strip()
        note = str(args.get("note") or "").strip()[:500]
        try:
            item_id = int(args.get("id"))
        except (TypeError, ValueError):
            api_error(self, 400, "审核记录编号不正确。")
            return
        if kind == "user":
            target = query_one("SELECT * FROM users WHERE id = ?", (item_id,))
            if not target:
                api_error(self, 404, "用户不存在。")
                return
            if target.get("status") != "pending":
                api_error(self, 409, "该注册申请已经处理过了。")
                return
            if action not in ("approve", "reject"):
                api_error(self, 400, "用户审核只支持通过或驳回。")
                return
            status = "approved" if action == "approve" else "rejected"
            stamp = now_text()
            execute(
                """UPDATE users SET status = ?, approved_at = ?, updated_at = ?
                   WHERE id = ?""",
                (status, stamp if status == "approved" else None, stamp, item_id),
            )
            if status == "rejected":
                delete_sessions_for_user(item_id)
            write_audit(
                identity,
                f"user_{action}",
                note or ("通过注册" if action == "approve" else "驳回注册"),
                target,
            )
        elif kind == "message":
            target = query_one(
                "SELECT * FROM site_messages WHERE id = ? AND parent_id IS NULL",
                (item_id,),
            )
            if not target:
                api_error(self, 404, "留言不存在。")
                return
            if target.get("status") != "pending":
                api_error(self, 409, "该留言已经处理过了。")
                return
            if action not in ("approve", "reject"):
                api_error(self, 400, "留言审核只支持通过或驳回。")
                return
            status = "approved" if action == "approve" else "rejected"
            execute(
                """UPDATE site_messages
                   SET status = ?, reviewed_by = ?, reviewed_at = ?, review_note = ?
                   WHERE id = ?""",
                (status, identity.get("nickname") or "管理员", now_text(), note or None, item_id),
            )
            execute(
                """UPDATE site_message_files
                   SET status = ?, reviewed_by = ?, reviewed_at = ?
                   WHERE message_id = ?""",
                (status, identity.get("nickname") or "管理员", now_text(), item_id),
            )
            write_audit(
                identity,
                f"{action}_message",
                note or str(target.get("content") or "")[:200],
                {"id": item_id, "nickname": target.get("nickname") or ""},
            )
        elif kind == "report":
            target = query_one("SELECT * FROM content_reports WHERE id = ?", (item_id,))
            if not target:
                api_error(self, 404, "举报记录不存在。")
                return
            if target.get("status") != "pending":
                api_error(self, 409, "该举报已经处理过了。")
                return
            if action not in ("resolve", "dismiss"):
                api_error(self, 400, "举报审核只支持处理或忽略。")
                return
            status = "resolved" if action == "resolve" else "dismissed"
            execute(
                """UPDATE content_reports
                   SET status = ?, handled_by = ?, handled_at = ?, resolution = ?
                   WHERE id = ?""",
                (
                    status,
                    identity.get("nickname") or "管理员",
                    now_text(),
                    note or None,
                    item_id,
                ),
            )
            write_audit(
                identity,
                f"report_{status}",
                note or target.get("target_title") or "",
                {"id": item_id, "nickname": target.get("target_title") or ""},
            )
        else:
            api_error(self, 400, "未知审核类型。")
            return
        self.log_activity(
            f"agent_review_{kind}_{action}",
            f"ErrorJ Agent 审核 {kind} #{item_id}：{action}",
            target_type=kind,
            target_id=item_id,
            actor=identity,
        )
        self.send_json(
            200,
            {"ok": True, "kind": kind, "id": item_id, "action": action},
        )

    def api_agent_tool(self, payload, identity):
        tool = str((payload or {}).get("tool") or "").strip()
        args = (payload or {}).get("arguments") or {}
        if not isinstance(args, dict):
            api_error(self, 400, "工具参数格式不正确。")
            return
        handlers = {
            "inventory.search": self.agent_tool_inventory_search,
            "bookmarks.search": self.agent_tool_bookmark_search,
            "notes.search": self.agent_tool_note_search,
            "notes.read": self.agent_tool_note_read,
            "reviews.list": self.agent_tool_reviews_list,
            "reviews.decide": self.agent_tool_reviews_decide,
        }
        handler = handlers.get(tool)
        if not handler:
            api_error(self, 400, "未知 ErrorJ Agent 工具。")
            return
        handler(identity, args)

    def api_agent_web_status(self):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看 ErrorJ Agent。")
            return
        try:
            status = agent_internal_request("/internal/status", timeout=5)
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            self.send_json(
                200,
                {"ok": False, "error": str(exc)[:200]},
            )
            return
        self.send_json(200, {"ok": True, "agent": status})

    def api_agent_web_chat(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以使用 ErrorJ Agent。")
            return
        message = str((payload or {}).get("message") or "").strip()
        if not message:
            api_error(self, 400, "请输入要发送的内容。")
            return
        if len(message) > 4000:
            api_error(self, 400, "单次消息不能超过 4000 字。")
            return
        try:
            data = agent_internal_request(
                "/internal/web-chat",
                {"user_id": 0, "message": message},
                timeout=110,
            )
        except HTTPError as exc:
            detail = "Agent 请求失败。"
            try:
                error_data = json.loads(exc.read().decode("utf-8"))
                detail = str(error_data.get("error") or detail)
            except Exception:
                pass
            api_error(self, 502, detail)
            return
        except (URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, {"reply": str(data.get("reply") or "").strip()})

    def api_agent_web_settings(self):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以管理 ErrorJ Agent。")
            return
        try:
            data = agent_internal_request(
                "/internal/settings?platform=web&owner_id=0", timeout=10
            )
            qq_data = agent_internal_request(
                "/internal/settings?platform=qq&owner_id=0", timeout=10
            )
            merged = dict(data.get("settings") or {})
            merged.update(qq_data.get("settings") or {})
            data["settings"] = merged
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, data)

    def api_agent_web_settings_save(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以管理 ErrorJ Agent。")
            return
        values = (payload or {}).get("settings")
        if not isinstance(values, dict):
            api_error(self, 400, "设置格式不正确。")
            return
        try:
            data = agent_internal_request(
                "/internal/settings",
                {
                    "platform": "web",
                    "owner_id": "0",
                    "settings": values,
                },
                timeout=10,
            )
            agent_internal_request(
                "/internal/settings",
                {
                    "platform": "qq",
                    "owner_id": "0",
                    "settings": values,
                },
                timeout=10,
            )
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, data)

    def api_agent_web_memories(self, query):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以管理 ErrorJ Agent 记忆。")
            return
        search = str((query.get("q") or [""])[0])
        try:
            data = agent_internal_request(
                "/internal/memories?platform=web&owner_id=0&q="
                + quote(search),
                timeout=10,
            )
            qq_data = agent_internal_request(
                "/internal/memories?platform=qq&owner_id=0&q="
                + quote(search),
                timeout=10,
            )
            memories = []
            for item in data.get("memories") or []:
                item = dict(item)
                item["platform"] = "web"
                memories.append(item)
            for item in qq_data.get("memories") or []:
                item = dict(item)
                item["platform"] = "qq"
                memories.append(item)
            memories.sort(
                key=lambda item: (int(item.get("importance") or 0), int(item.get("id") or 0)),
                reverse=True,
            )
            data["memories"] = memories
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, data)

    def api_agent_web_memory_delete(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以管理 ErrorJ Agent 记忆。")
            return
        try:
            memory_id = int((payload or {}).get("id"))
        except (TypeError, ValueError):
            api_error(self, 400, "记忆编号不正确。")
            return
        try:
            data = agent_internal_request(
                "/internal/memory/delete",
                {
                    "platform": str((payload or {}).get("platform") or "web"),
                    "owner_id": "0",
                    "id": memory_id,
                },
                timeout=10,
            )
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, data)

    def api_agent_web_stickers(self, query):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以管理表情包。")
            return
        try:
            data = agent_internal_request(
                "/internal/stickers?owner_id=0", timeout=10
            )
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, data)

    def api_agent_web_sticker_delete(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以管理表情包。")
            return
        try:
            sticker_id = int((payload or {}).get("id"))
        except (TypeError, ValueError):
            api_error(self, 400, "表情包编号不正确。")
            return
        try:
            data = agent_internal_request(
                "/internal/sticker/delete",
                {"owner_id": "0", "id": sticker_id},
                timeout=10,
            )
        except (HTTPError, URLError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            api_error(self, 502, str(exc)[:200])
            return
        self.send_json(200, data)

    def api_agent_sticker_file(self, path):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看表情包。")
            return
        filename = Path(path[len("/agent-stickers/") :]).name
        if not filename:
            api_error(self, 404, "表情包不存在。")
            return
        try:
            request = Request(
                AGENT_BASE_URL + "/stickers/" + quote(filename),
                headers={"User-Agent": "ErrorJ-Agent-Bridge/1.0"},
            )
            with urlopen(request, timeout=10) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type") or "application/octet-stream"
        except (HTTPError, URLError, OSError) as exc:
            api_error(self, 404, str(exc)[:120])
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    # ---------- 留言审核（管理员） ----------
    def api_admin_review(self, params):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以查看审核队列。")
            return
        status_filter = str((params.get("status") or ["pending"])[0] or "pending").strip()
        if status_filter not in ("pending", "approved", "rejected", "all"):
            status_filter = "pending"
        where = "WHERE m.parent_id IS NULL"
        values = ()
        if status_filter != "all":
            where += " AND m.status = ?"
            values = (status_filter,)
        rows = query(
            f"""SELECT m.id, m.nickname AS message_nickname, m.content AS message_content,
                       m.user_id AS message_user_id, m.status, m.created_at,
                       m.reviewed_by, m.reviewed_at, m.review_note
                FROM site_messages m
                {where}
                ORDER BY CASE WHEN m.status = 'pending' THEN 0 ELSE 1 END,
                         m.created_at DESC, m.id DESC
                LIMIT 200""",
            values,
        )
        author_ids = sorted(
            {
                row["message_user_id"]
                for row in rows
                if row.get("message_user_id") not in (None, 0)
            }
        )
        authors = {}
        if author_ids:
            placeholders = ",".join("?" for _ in author_ids)
            for user in query(
                f"SELECT id, username, nickname FROM users WHERE id IN ({placeholders})",
                tuple(author_ids),
            ):
                authors[user["id"]] = user
        files = self.site_message_files_map([row["id"] for row in rows])
        for row in rows:
            row["message_author"] = self.message_display_name(
                {
                    "user_id": row.get("message_user_id"),
                    "nickname": row.get("message_nickname"),
                },
                authors,
                True,
            )
            row["files"] = files.get(row["id"], [])
        legacy_rows = []
        if status_filter in ("pending", "all"):
            legacy_rows = query(
                """SELECT f.id, f.message_id, f.file_name, f.file_size, f.mime_type,
                          f.status, f.uploaded_by, f.created_at,
                          m.nickname AS message_nickname, m.content AS message_content,
                          m.created_at AS message_created_at, m.user_id AS message_user_id
                   FROM site_message_files f
                   JOIN site_messages m ON m.id = f.message_id
                   WHERE f.status = 'pending' AND m.parent_id IS NULL
                     AND m.status = 'approved'
                   ORDER BY f.id DESC
                   LIMIT 200"""
            )
        for row in legacy_rows:
            extension = os.path.splitext(row.get("file_name") or "")[1].lower()
            row["is_image"] = extension in MESSAGE_IMAGE_EXTENSIONS
            row["url"] = f"/api/site/message-files/{row['id']}"
            row["message_author"] = self.message_display_name(
                {
                    "user_id": row.get("message_user_id"),
                    "nickname": row.get("message_nickname"),
                },
                authors,
                True,
            )
        pending_messages = query_one(
            "SELECT COUNT(*) AS n FROM site_messages WHERE parent_id IS NULL AND status = 'pending'"
        )["n"]
        pending_legacy = query_one(
            """SELECT COUNT(*) AS n FROM site_message_files f
               JOIN site_messages m ON m.id = f.message_id
               WHERE f.status = 'pending' AND m.parent_id IS NULL
                 AND m.status = 'approved'"""
        )["n"]
        pending = int(pending_messages) + int(pending_legacy)
        self.send_json(
            200,
            {
                "messages": rows,
                "legacy_files": legacy_rows,
                "pending": pending,
            },
        )

    def api_admin_review_action(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以审核留言。")
            return
        message_id = int(path.split("/")[4])
        row = query_one(
            "SELECT * FROM site_messages WHERE id = ? AND parent_id IS NULL",
            (message_id,),
        )
        if not row:
            api_error(self, 404, "留言不存在。")
            return
        action = str(payload.get("action") or "").strip()
        identity = self.session_identity()
        reviewer = (identity or {}).get("nickname") or "管理员"
        review_note = str(payload.get("review_note") or "").strip()[:500]
        if action == "approve":
            execute(
                """UPDATE site_messages
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?,
                       review_note = NULL
                   WHERE id = ?""",
                (reviewer, now_text(), message_id),
            )
            execute(
                """UPDATE site_message_files
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?
                   WHERE message_id = ?""",
                (reviewer, now_text(), message_id),
            )
            write_audit(
                identity,
                "approve_message",
                str(row.get("content") or "")[:200],
                {"id": message_id, "nickname": row.get("nickname") or ""},
            )
            self.send_json(200, {"ok": True, "status": "approved"})
            return
        if action == "reject":
            execute(
                """UPDATE site_messages
                   SET status = 'rejected', reviewed_by = ?, reviewed_at = ?,
                       review_note = ?
                   WHERE id = ?""",
                (reviewer, now_text(), review_note or None, message_id),
            )
            execute(
                """UPDATE site_message_files
                   SET status = 'rejected', reviewed_by = ?, reviewed_at = ?
                   WHERE message_id = ?""",
                (reviewer, now_text(), message_id),
            )
            write_audit(
                identity,
                "reject_message",
                review_note or str(row.get("content") or "")[:200],
                {"id": message_id, "nickname": row.get("nickname") or ""},
            )
            self.send_json(200, {"ok": True, "status": "rejected"})
            return
        api_error(self, 400, "未知审核操作。")

    def api_admin_review_file_action(self, path, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以审核留言附件。")
            return
        file_id = int(path.rstrip("/").rsplit("/", 1)[-1])
        row = query_one("SELECT * FROM site_message_files WHERE id = ?", (file_id,))
        if not row:
            api_error(self, 404, "附件不存在。")
            return
        action = str(payload.get("action") or "").strip()
        identity = self.session_identity()
        reviewer = (identity or {}).get("nickname") or "管理员"
        if action not in ("approve", "reject"):
            api_error(self, 400, "未知审核操作。")
            return
        status = "approved" if action == "approve" else "rejected"
        execute(
            """UPDATE site_message_files
               SET status = ?, reviewed_by = ?, reviewed_at = ?
               WHERE id = ?""",
            (status, reviewer, now_text(), file_id),
        )
        write_audit(
            identity,
            f"{action}_legacy_attachment",
            row.get("file_name") or "",
            {"id": row.get("message_id"), "nickname": row.get("file_name") or ""},
        )
        self.send_json(200, {"ok": True, "status": status})

    def api_admin_review_all(self, payload):
        if not self.is_admin():
            api_error(self, 403, "只有管理员可以审核留言。")
            return
        identity = self.session_identity()
        reviewer = (identity or {}).get("nickname") or "管理员"
        stamp = now_text()
        message_rows = query(
            "SELECT id FROM site_messages WHERE parent_id IS NULL AND status = 'pending'"
        )
        for row in message_rows:
            execute(
                """UPDATE site_messages
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?,
                       review_note = NULL
                   WHERE id = ?""",
                (reviewer, stamp, row["id"]),
            )
            execute(
                """UPDATE site_message_files
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?
                   WHERE message_id = ?""",
                (reviewer, stamp, row["id"]),
            )
        legacy_rows = query(
            """SELECT f.id FROM site_message_files f
               JOIN site_messages m ON m.id = f.message_id
               WHERE f.status = 'pending' AND m.parent_id IS NULL
                 AND m.status = 'approved'"""
        )
        for row in legacy_rows:
            execute(
                """UPDATE site_message_files
                   SET status = 'approved', reviewed_by = ?, reviewed_at = ?
                   WHERE id = ?""",
                (reviewer, stamp, row["id"]),
            )
        total = len(message_rows) + len(legacy_rows)
        if total:
            write_audit(
                identity,
                "approve_message_batch",
                f"批量通过 {len(message_rows)} 条留言、{len(legacy_rows)} 个旧附件",
            )
        self.send_json(
            200,
            {
                "ok": True,
                "approved": total,
                "approved_messages": len(message_rows),
                "approved_legacy_files": len(legacy_rows),
            },
        )

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
        try:
            relative = self.save_data_file(
                raw,
                stored_name,
                "note_images",
                upload_limit("note_image")["max_file_bytes"],
            )
        except ValueError:
            # 文档里内嵌的图片超过当前上限时跳过，不影响整篇导入。
            return None
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
        max_file_bytes = upload_limit("note_import")["max_file_bytes"]
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                "导入文档不能超过 "
                f"{format_upload_limit_bytes(max_file_bytes)}。",
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
        max_file_bytes = upload_limit("note_image")["max_file_bytes"]
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                f"图片不能超过 {format_upload_limit_bytes(max_file_bytes)}。",
            )
            return
        mime_type = detect_image_type(raw)
        if not mime_type:
            api_error(self, 400, "只支持 PNG / JPEG / WebP / GIF / BMP 图片。")
            return
        base_name = os.path.splitext(original_name)[0] or "image"
        stored_name = f"{base_name}{NOTE_IMAGE_EXTENSIONS[mime_type]}"
        try:
            relative = self.save_data_file(
                raw, stored_name, "note_images", max_file_bytes
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
        extension = Path(original_name).suffix.lower()
        if extension not in WORKBENCH_EXTENSIONS:
            api_error(self, 400, "不支持这种文件类型。")
            return
        category = self.workbench_category_for_name(
            original_name,
            str(payload.get("category") or ""),
        )
        max_file_bytes = upload_limit(f"workbench_{category}")["max_file_bytes"]
        if len(raw) > max_file_bytes:
            api_error(
                self,
                400,
                "工作台文件不能超过 "
                f"{format_upload_limit_bytes(max_file_bytes)}。",
            )
            return
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
                max_file_bytes,
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
        self.log_activity(
            "asset_download",
            f"下载资料：{row.get('original_name') or ('#' + str(asset_id))}",
            target_type="asset",
            target_id=asset_id,
        )
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
            execute(
                """UPDATE share_links SET revoked_at = ?
                   WHERE resource_type = 'workbench_asset' AND resource_id = ?
                     AND revoked_at IS NULL""",
                (now_text(), asset_id),
            )
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
                cost = (
                    finite_number(payload.get("cost"), "费用")
                    if str(payload.get("cost") or "").strip()
                    else None
                )
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
        try:
            quantity = finite_number(payload.get("quantity"))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
        if not part_id or not location_id:
            api_error(self, 400, "请选择元件和存放位置。")
            return
        if quantity <= 0:
            api_error(self, 400, "入库数量必须大于 0。")
            return
        part = query_one("SELECT id, part_number FROM parts WHERE id = ?", (part_id,))
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
        self.log_activity(
            "stock_inbound",
            f"元件入库：{(part or {}).get('part_number') or part_id} × {quantity:g}",
            target_type="part",
            target_id=part_id,
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
        try:
            quantity = finite_number(payload.get("quantity"))
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
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

        try:
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
        except ValueError as exc:
            # 库存不足是正常的用户输入问题，不该变成 500 再把内部信息回给客户端
            api_error(self, 400, str(exc))
            return
        part_row = query_one("SELECT part_number FROM parts WHERE id = ?", (part_id,))
        project_row = (
            query_one("SELECT name FROM projects WHERE id = ?", (project_id,))
            if project_id
            else None
        )
        outbound_summary = (
            f"元件出库：{(part_row or {}).get('part_number') or part_id} × {quantity:g}"
        )
        if project_row:
            outbound_summary += f" → {project_row['name']}"
        self.log_activity(
            "stock_outbound",
            outbound_summary,
            target_type="part",
            target_id=part_id,
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
            self.log_activity(
                "movement_delete",
                f"删除出入库记录 #{movement_id}",
                target_type="movement",
                target_id=movement_id,
            )
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
        self.log_activity(
            "movement_update",
            f"修改出入库记录 #{movement_id}",
            target_type="movement",
            target_id=movement_id,
        )
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
        try:
            target_quantity = finite_number(payload.get("target_quantity") or 1, "目标数量")
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
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
        try:
            target_quantity = finite_number(payload.get("target_quantity") or 1, "目标数量")
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
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
        try:
            quantity = finite_number(
                payload.get("quantity") or item["target_quantity"] or 1
            )
        except ValueError as exc:
            api_error(self, 400, str(exc))
            return
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
    if AUTH_STATE.get("config_broken"):
        broken = AUTH_STATE["config_broken"]
        if os.environ.get("INVENTORY_ALLOW_OPEN") != "1":
            print(f"致命错误：{broken}", file=sys.stderr)
            print(
                "已拒绝启动：密码文件存在但读不出来时，继续运行会让全站变成免密开放模式。",
                file=sys.stderr,
            )
            print(
                "请修好文件权限或内容；确实要临时开放，设 INVENTORY_ALLOW_OPEN=1 再启动。",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"警告：{broken}", file=sys.stderr)
        print(
            "已按 INVENTORY_ALLOW_OPEN=1 强制启动：全站处于免密开放模式，仅限临时排查。",
            file=sys.stderr,
        )
    start_access_log_worker()
    threading.Thread(
        target=logs_maintenance_loop, name="logs-cleanup", daemon=True
    ).start()
    threading.Thread(
        target=report_reminder_loop, name="report-reminder", daemon=True
    ).start()
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
