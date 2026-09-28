"""把 HTML 或 Markdown 文档导入成一条学习笔记。

用法：
    python tools/import_doc_note.py <文件.html|文件.md> [--title 标题] [--tags 标签] [--slug 前缀]

正文按 Markdown 保存。HTML 里内嵌的 base64 图片、Markdown 里引用的本地图片，
都会复制到 data/note_images/，并以 /site-files/note_images/xxx 的形式写进正文。
同名笔记默认覆盖更新，不重复堆积。
"""

import argparse
import base64
import re
import sys
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402

DATA_IMAGE_RE = re.compile(r"^data:(image/[A-Za-z0-9.+-]+);base64,(.+)$", re.S)
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
SECTION_RE = re.compile(r"^[一二三四五六七八九十]+[、.．]")
MD_HEADING1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
SKIP_TAGS = {"style", "script", "head", "svg"}
HTML_SUFFIXES = {".html", ".htm"}
LOCAL_URL_PREFIXES = ("/site-files/", "http://", "https://", "//")


class HtmlDocParser(HTMLParser):
    """按出现顺序抽出标题、段落文字和图片。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.blocks = []
        self._skip_depth = 0
        self._buffer = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            self._buffer = []
            return
        if tag == "p":
            self._buffer = []
            return
        if tag == "br" and self._buffer is not None:
            self._buffer.append("\n")
            return
        if tag == "img":
            self._add_image(dict(attrs))

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            self._add_image(dict(attrs))

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title" and self._in_title:
            self.title = self._clean("".join(self._buffer or []))
            self._in_title = False
            self._buffer = None
            return
        if tag == "p" and self._buffer is not None:
            text = self._clean("".join(self._buffer))
            if text:
                self.blocks.append(("text", text))
            self._buffer = None

    def handle_data(self, data):
        if self._skip_depth and not self._in_title:
            return
        if self._buffer is not None:
            self._buffer.append(data)

    def _add_image(self, attrs):
        src = (attrs.get("src") or "").strip()
        alt = (attrs.get("alt") or "").strip()
        if src:
            self.blocks.append(("image", {"src": src, "alt": alt}))

    @staticmethod
    def _clean(text):
        lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line).strip()


def save_image(raw, alt, slug, index):
    """把图片写进 data/note_images/ 并登记数据库，返回 (相对路径, 字节数, 图片 id)。"""
    mime_type = app.detect_image_type(raw)
    if not mime_type:
        print(f"  跳过第 {index} 张图：类型无法识别")
        return None
    extension = app.NOTE_IMAGE_EXTENSIONS[mime_type]
    name = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}_{slug}-{index:02d}{extension}"
    relative = f"note_images/{name}"
    app.NOTE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    (app.DATA_DIR / relative).write_bytes(raw)
    image_id = app.execute(
        """INSERT INTO note_images (note_id, file_path, original_name, mime_type, size_bytes, created_at)
           VALUES (NULL, ?, ?, ?, ?, ?)""",
        (relative, alt or name, mime_type, len(raw), app.now_text()),
    )
    return relative, len(raw), image_id


def store_data_uri(src, alt, slug, index):
    match = DATA_IMAGE_RE.match(src)
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group(2), validate=False)
    except Exception:
        return None
    return save_image(raw, alt, slug, index)


def build_from_html(path, slug):
    parser = HtmlDocParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    if not parser.blocks:
        raise ValueError("这个 HTML 里没有抽到正文段落或图片。")
    parts = [f"> 导入自 {path.name} · {app.now_text()[:10]}"]
    image_ids = []
    total_bytes = 0
    image_count = 0
    for kind, payload in parser.blocks:
        if kind == "text":
            text = payload
            parts.append(f"### {text}" if SECTION_RE.match(text) and len(text) <= 40 else text)
            continue
        image_count += 1
        stored = store_data_uri(payload["src"], payload["alt"], slug, image_count)
        if not stored:
            continue
        relative, size, image_id = stored
        image_ids.append(image_id)
        total_bytes += size
        parts.append(f"![{payload['alt'] or f'图 {image_count}'}](/site-files/{relative})")
    return parser.title, "\n\n".join(parts) + "\n", image_count, total_bytes, image_ids


def build_from_markdown(path, slug):
    text = path.read_text(encoding="utf-8", errors="replace")
    title_match = MD_HEADING1_RE.search(text)
    title = title_match.group(1).strip() if title_match else path.stem
    if title_match:
        text = text[: title_match.start()] + text[title_match.end():]
    text = text.lstrip("\n")
    text = f"> 导入自 {path.name} · {app.now_text()[:10]}\n\n" + text

    image_ids = []
    total_bytes = 0
    counter = {"n": 0, "bytes": 0}

    def replace(match):
        alt, src = match.group(1), match.group(2)
        if src.startswith(LOCAL_URL_PREFIXES):
            return match.group(0)
        counter["n"] += 1
        stored = None
        if src.startswith("data:"):
            stored = store_data_uri(src, alt, slug, counter["n"])
        else:
            source = (path.parent / src).resolve()
            if source.is_file():
                stored = save_image(source.read_bytes(), alt, slug, counter["n"])
            else:
                print(f"  第 {counter['n']} 张图找不到：{src}")
        if not stored:
            return match.group(0)
        relative, size, image_id = stored
        image_ids.append(image_id)
        counter["bytes"] += size
        return f"![{alt}](/site-files/{relative})"

    text = MD_IMAGE_RE.sub(replace, text)
    return title, text, len(image_ids), counter["bytes"], image_ids


def main():
    parser = argparse.ArgumentParser(description="把 HTML / Markdown 文档导入成一条学习笔记")
    parser.add_argument("doc_file")
    parser.add_argument("--title", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--slug", default="import", help="图片文件名前缀")
    parser.add_argument("--new", action="store_true", help="同名笔记也新建，不覆盖")
    args = parser.parse_args()

    path = Path(args.doc_file).expanduser()
    if not path.is_file():
        print(f"找不到文件：{path}")
        return 1

    builder = build_from_html if path.suffix.lower() in HTML_SUFFIXES else build_from_markdown
    try:
        doc_title, content, image_count, total_bytes, image_ids = builder(path, args.slug)
    except ValueError as exc:
        print(exc)
        return 1

    title = (args.title or doc_title or path.stem).strip()[:120]
    app.init_db()

    existing = None
    if not args.new:
        existing = app.query_one("SELECT id FROM learning_notes WHERE title = ?", (title,))
    if existing:
        note_id = existing["id"]
        for row in app.query("SELECT id, file_path FROM note_images WHERE note_id = ?", (note_id,)):
            app.remove_data_file(row["file_path"])
            app.execute("DELETE FROM note_images WHERE id = ?", (row["id"],))
        app.execute(
            "UPDATE learning_notes SET content = ?, tags = ?, updated_at = ? WHERE id = ?",
            (content, args.tags or None, app.now_text(), note_id),
        )
        action = "已更新"
    else:
        stamp = app.now_text()
        note_id = app.execute(
            """INSERT INTO learning_notes (title, content, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (title, content, args.tags or None, stamp, stamp),
        )
        action = "已新建"

    for image_id in image_ids:
        app.execute("UPDATE note_images SET note_id = ? WHERE id = ?", (note_id, image_id))

    print(f"{action}笔记 #{note_id}：{title}")
    print(f"  正文 {len(content)} 字，图片 {image_count} 张（{total_bytes / 1024 / 1024:.1f} MB）")
    print("  http://127.0.0.1:8000/notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
