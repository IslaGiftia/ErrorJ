from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)


MAX_SHARED_LINKS = 2
MAX_FETCH_BYTES = 512 * 1024
FETCH_TIMEOUT_SECONDS = 6

PLATFORM_LABELS = {
    "bilibili": "B站",
    "douyin": "抖音",
    "weibo": "微博",
    "netease": "网易云音乐",
    "xiaohongshu": "小红书",
}

PLATFORM_HOSTS = {
    "bilibili": ("bilibili.com", "b23.tv"),
    "douyin": ("douyin.com", "iesdouyin.com"),
    "weibo": ("weibo.com", "weibo.cn", "t.cn"),
    "netease": ("music.163.com", "163cn.tv", "y.music.163.com"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
}

URL_RE = re.compile(r"https?://[^\s<>'\"\\]+", re.IGNORECASE)
HINT_KEYS = (
    "title",
    "desc",
    "description",
    "summary",
    "content",
    "tag",
    "source",
    "name",
    "nickname",
)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        if not safe_public_url(newurl):
            return None
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


_OPENER = build_opener(
    _SafeRedirectHandler(),
    HTTPSHandler(context=ssl.create_default_context()),
)


def _normalized_host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def platform_for_url(url: str) -> str:
    host = _normalized_host(url)
    if not host:
        return ""
    for platform, suffixes in PLATFORM_HOSTS.items():
        if any(host == item or host.endswith("." + item) for item in suffixes):
            return platform
    return ""


def safe_public_url(url: str) -> bool:
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return False
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return False
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return False
    for item in addresses:
        try:
            address = ipaddress.ip_address(item[4][0])
        except ValueError:
            return False
        if not address.is_global:
            return False
    return bool(addresses)


def _clean_url(value: str) -> str:
    text = unescape(str(value or "")).strip()
    text = text.rstrip(".,，。!?！？、;；:：)]}】》")
    return text[:1200]


def _iter_payload_strings(value: Any, depth: int = 0):
    if depth > 8:
        return
    if isinstance(value, str):
        yield value
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                yield from _iter_payload_strings(json.loads(stripped), depth + 1)
            except (json.JSONDecodeError, TypeError):
                pass
        if "%3a" in value.lower() or "%2f" in value.lower():
            yield unquote(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_payload_strings(item, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_payload_strings(item, depth + 1)


def _payload_hints(payload: dict[str, Any] | None) -> list[str]:
    hints = []
    if not isinstance(payload, dict):
        return hints

    def visit(value: Any, depth: int = 0):
        if depth > 7:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    str(key).lower() in HINT_KEYS
                    and isinstance(item, str)
                ):
                    text = _plain_text(item)[:300]
                    if (
                        text
                        and not text.startswith(("http://", "https://"))
                        and text not in hints
                    ):
                        hints.append(text)
                visit(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    visit(json.loads(stripped), depth + 1)
                except (json.JSONDecodeError, TypeError):
                    pass

    visit(payload)
    return hints[:12]


def extract_shared_media(
    text: str = "",
    payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates = []
    strings = [str(text or "")]
    strings.extend(_iter_payload_strings(payload))
    for value in strings:
        normalized = unquote(unescape(str(value or "")))
        for match in URL_RE.findall(normalized):
            url = _clean_url(match)
            platform = platform_for_url(url)
            if not platform or url in [item["url"] for item in candidates]:
                continue
            candidates.append({"url": url, "platform": platform})
            if len(candidates) >= MAX_SHARED_LINKS:
                break
        if len(candidates) >= MAX_SHARED_LINKS:
            break
    hints = _payload_hints(payload)
    for index, item in enumerate(candidates):
        title_index = 0 if index == 0 else min(len(hints) - 1, index * 2)
        if hints:
            item["title_hint"] = hints[title_index]
        if len(hints) > 1:
            item["description_hint"] = hints[
                min(len(hints) - 1, title_index + 1)
            ]
    return candidates


def _plain_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


class _MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self._json_buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            key = (
                values.get("property")
                or values.get("name")
                or values.get("itemprop")
                or ""
            ).lower()
            content = values.get("content") or ""
            if key and content:
                self.meta[key] = content
        if (
            tag.lower() == "script"
            and values.get("type", "").lower() == "application/ld+json"
        ):
            self._in_json_ld = True
            self._json_buffer = []

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._json_buffer))
            self._in_json_ld = False
            self._json_buffer = []

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_json_ld:
            self._json_buffer.append(data)


def _first_json_ld_value(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            found = _first_json_ld_value(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _first_json_ld_value(item, keys)
            if found:
                return found
    return ""


def _html_metadata(body: bytes, final_url: str) -> dict[str, str]:
    parser = _MetadataParser()
    parser.feed(body.decode("utf-8", errors="ignore"))
    title = (
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or parser.title
    )
    description = (
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or parser.meta.get("twitter:description")
        or ""
    )
    author = (
        parser.meta.get("author")
        or parser.meta.get("article:author")
        or ""
    )
    image = (
        parser.meta.get("og:image")
        or parser.meta.get("twitter:image")
        or ""
    )
    for raw in parser.json_ld:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        title = title or _first_json_ld_value(
            data,
            ("headline", "name", "title"),
        )
        description = description or _first_json_ld_value(
            data,
            ("description", "articleBody", "text"),
        )
        author = author or _first_json_ld_value(
            data,
            ("author", "creator"),
        )
        image = image or _first_json_ld_value(data, ("image", "thumbnailUrl"))
        if title or description:
            break
    script_text = body.decode("utf-8", errors="ignore")
    if not description:
        match = re.search(
            r'"(?:desc|description)"\s*:\s*"((?:\\.|[^"\\]){1,800})"',
            script_text,
        )
        if match:
            try:
                description = json.loads('"' + match.group(1) + '"')
            except json.JSONDecodeError:
                description = match.group(1)
    if not author:
        match = re.search(
            r'"(?:nickname|screen_name|author)"\s*:\s*"'
            r'((?:\\.|[^"\\]){1,120})"',
            script_text,
        )
        if match:
            try:
                author = json.loads('"' + match.group(1) + '"')
            except json.JSONDecodeError:
                author = match.group(1)
    return {
        "title": _plain_text(title)[:180],
        "author": _plain_text(author)[:80],
        "description": _plain_text(description)[:900],
        "cover_url": urljoin(final_url, image) if image else "",
    }


def _fetch_url(
    url: str,
    *,
    accept: str = "text/html,application/json;q=0.9,*/*;q=0.8",
) -> tuple[str, bytes]:
    if not safe_public_url(url):
        raise ValueError("链接地址不安全或无法访问。")
    request = Request(
        url,
        headers={
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13) "
                "AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36"
            ),
        },
    )
    try:
        with _OPENER.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_FETCH_BYTES + 1)
            final_url = response.geturl()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise ValueError(str(exc)[:180]) from exc
    if len(body) > MAX_FETCH_BYTES:
        raise ValueError("分享页面体积过大。")
    if not safe_public_url(final_url):
        raise ValueError("分享页面跳转到了不安全地址。")
    return final_url, body


def _json_body(body: bytes) -> dict[str, Any]:
    data = json.loads(body.decode("utf-8-sig", errors="ignore"))
    return data if isinstance(data, dict) else {}


def _https_cover(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        return "https:" + text
    if text.startswith("http://"):
        return "https://" + text[7:]
    return text


def _duration_text(seconds: int) -> str:
    if seconds <= 0:
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


def _bilibili_metadata(
    final_url: str,
    html_body: bytes,
) -> dict[str, Any]:
    match = re.search(r"(BV[0-9A-Za-z]{8,})", final_url)
    if match:
        api = (
            "https://api.bilibili.com/x/web-interface/view?"
            + urlencode({"bvid": match.group(1)})
        )
    else:
        aid = re.search(r"/av(\d+)", final_url, re.IGNORECASE)
        if not aid:
            return _html_metadata(html_body, final_url)
        api = (
            "https://api.bilibili.com/x/web-interface/view?"
            + urlencode({"aid": aid.group(1)})
        )
    _, raw = _fetch_url(api, accept="application/json")
    data = _json_body(raw)
    video = data.get("data") if isinstance(data.get("data"), dict) else {}
    if not video:
        return _html_metadata(html_body, final_url)
    stat = video.get("stat") or {}
    duration = int(video.get("duration") or 0)
    return {
        "title": str(video.get("title") or "")[:180],
        "author": str((video.get("owner") or {}).get("name") or "")[:80],
        "description": str(video.get("desc") or "")[:900],
        "cover_url": _https_cover(str(video.get("pic") or "")),
        "extra": " · ".join(
            item
            for item in (
                f"播放 {int(stat.get('view') or 0)}" if stat.get("view") else "",
                f"时长 {_duration_text(duration)}" if duration else "",
            )
            if item
        ),
    }


def _netease_metadata(final_url: str) -> dict[str, Any]:
    parsed = urlsplit(final_url)
    query = parse_qs(parsed.query)
    item_id = str((query.get("id") or [""])[0]).strip()
    if not item_id.isdigit():
        return {}
    path = parsed.path.lower()
    if "/album" in path:
        _, raw = _fetch_url(
            f"https://music.163.com/api/album/{item_id}",
            accept="application/json",
        )
        album = _json_body(raw).get("album") or {}
        return {
            "title": str(album.get("name") or "")[:180],
            "author": str((album.get("artist") or {}).get("name") or "")[:80],
            "description": str(album.get("description") or "")[:900],
            "cover_url": _https_cover(str(album.get("picUrl") or "")),
            "extra": f"专辑 · {int(album.get('size') or 0)} 首",
        }
    if "/playlist" in path or "/discover/toplist" in path:
        _, raw = _fetch_url(
            f"https://music.163.com/api/playlist/detail?id={item_id}",
            accept="application/json",
        )
        playlist = _json_body(raw).get("result") or {}
        return {
            "title": str(playlist.get("name") or "")[:180],
            "author": str((playlist.get("creator") or {}).get("nickname") or "")[
                :80
            ],
            "description": str(playlist.get("description") or "")[:900],
            "cover_url": _https_cover(str(playlist.get("coverImgUrl") or "")),
            "extra": f"歌单 · {int(playlist.get('trackCount') or 0)} 首",
        }
    api = (
        "https://music.163.com/api/song/detail/?"
        + urlencode({"id": item_id, "ids": f"[{item_id}]"})
    )
    _, raw = _fetch_url(api, accept="application/json")
    songs = _json_body(raw).get("songs") or []
    song = songs[0] if songs and isinstance(songs[0], dict) else {}
    if not song:
        return {}
    artists = " / ".join(
        str(item.get("name") or "")
        for item in song.get("artists") or []
        if isinstance(item, dict) and item.get("name")
    )
    album = song.get("album") or {}
    duration_ms = int(song.get("duration") or 0)
    duration = round(duration_ms / 1000) if duration_ms else 0
    return {
        "title": str(song.get("name") or "")[:180],
        "author": artists[:80],
        "description": str(album.get("name") or "")[:900],
        "cover_url": _https_cover(str(album.get("picUrl") or "")),
        "extra": f"时长 {_duration_text(duration)}" if duration else "",
    }


def _weibo_metadata(
    final_url: str,
    html_body: bytes,
) -> dict[str, Any]:
    match = (
        re.search(r"/(?:detail|status)/([A-Za-z0-9]+)", final_url)
        or re.search(r"[?&]id=([A-Za-z0-9]+)", final_url)
    )
    if match:
        api = (
            "https://m.weibo.cn/statuses/show?"
            + urlencode({"id": match.group(1)})
        )
        try:
            _, raw = _fetch_url(api, accept="application/json")
            data = _json_body(raw)
            row = data.get("data") if isinstance(data.get("data"), dict) else data
            if isinstance(row, dict) and row.get("text"):
                user = row.get("user") or {}
                return {
                    "title": _plain_text(str(row.get("text") or ""))[:120],
                    "author": str(user.get("screen_name") or "")[:80],
                    "description": _plain_text(str(row.get("text") or ""))[:900],
                    "cover_url": _https_cover(
                        str(
                            (
                                (row.get("page_info") or {}).get("page_pic")
                                or {}
                            ).get("url")
                            or ""
                        )
                    ),
                    "extra": "微博",
                }
        except ValueError:
            pass
    return _html_metadata(html_body, final_url)


def parse_shared_media(
    media: list[dict[str, Any]],
    limit: int = MAX_SHARED_LINKS,
) -> list[dict[str, Any]]:
    results = []
    for item in media[: max(1, min(int(limit), MAX_SHARED_LINKS))]:
        source_url = str(item.get("url") or "").strip()
        if not source_url:
            continue
        platform = str(item.get("platform") or platform_for_url(source_url))
        candidate = {
            "platform": platform,
            "platform_label": PLATFORM_LABELS.get(platform, "分享内容"),
            "url": source_url,
            "title": str(item.get("title_hint") or "")[:180],
            "author": "",
            "description": str(item.get("description_hint") or "")[:900],
            "cover_url": "",
            "extra": "",
            "note": "",
        }
        try:
            final_url, body = _fetch_url(source_url)
            resolved_platform = platform_for_url(final_url) or platform
            candidate["platform"] = resolved_platform
            candidate["platform_label"] = PLATFORM_LABELS.get(
                resolved_platform,
                "分享内容",
            )
            candidate["url"] = final_url
            if resolved_platform == "bilibili":
                metadata = _bilibili_metadata(final_url, body)
            elif resolved_platform == "netease":
                metadata = _netease_metadata(final_url)
            elif resolved_platform == "weibo":
                metadata = _weibo_metadata(final_url, body)
            elif resolved_platform in ("douyin", "xiaohongshu"):
                metadata = _html_metadata(body, final_url)
            else:
                metadata = {}
            for key in ("title", "author", "description", "cover_url", "extra"):
                value = str(metadata.get(key) or "").strip()
                if value:
                    candidate[key] = value
        except (ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
            candidate["note"] = f"只读取到分享卡片信息（{str(exc)[:80]}）"
        if not candidate["title"] and candidate["description"]:
            candidate["title"] = candidate["description"][:80]
        results.append(candidate)
    return results


def format_shared_media_context(media: list[dict[str, Any]]) -> str:
    if not media:
        return ""
    blocks = []
    for item in media[:MAX_SHARED_LINKS]:
        lines = [f"平台：{item.get('platform_label') or '分享内容'}"]
        for label, key in (
            ("标题", "title"),
            ("作者", "author"),
            ("摘要", "description"),
            ("补充", "extra"),
        ):
            value = re.sub(r"\s+", " ", str(item.get(key) or "")).strip()
            if value:
                lines.append(f"{label}：{value[:600]}")
        if item.get("note"):
            lines.append(f"说明：{item['note']}")
        if item.get("url"):
            lines.append(f"链接：{item['url']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)[:2400]
