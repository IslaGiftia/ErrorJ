from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .media_links import extract_shared_media


CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]")
LOCATION_LAT_KEYS = ("lat", "latitude")
LOCATION_LNG_KEYS = ("lon", "lng", "longitude")
LOCATION_TITLE_KEYS = ("title", "name", "poi_name", "location_name", "desc")
LOCATION_ADDRESS_KEYS = ("address", "addr", "poi_address", "content")
LOCATION_CITY_KEYS = ("city", "cityname", "pname")
LOCATION_URL_KEYS = ("jump_url", "url", "link", "scheme")
ATTACHMENT_NAME_KEYS = ("filename", "file_name", "name", "file")
ATTACHMENT_URL_KEYS = ("url", "file_url", "download_url", "file")
COORD_PAIR_RE = re.compile(
    r"(?<![\d.])(-?\d{1,3}(?:\.\d+)?)\s*[,，]\s*"
    r"(-?\d{1,3}(?:\.\d+)?)(?![\d.])"
)
QQ_FACE_TAG_RE = re.compile(
    r'<faceType=(\d+),faceId="([^"]*)",ext="([^"]*)">',
    re.IGNORECASE,
)
QQ_FACE_MARKER_RE = re.compile(r"\[QQ表情(?:元素)?[^\]]*\]")
ADMIN_CITY_RE = re.compile(
    r"(?:省|自治区|特别行政区)"
    r"([^省市区县\s]{2,20}(?:市|自治州|地区|盟))"
)
CITY_PREFIX_RE = re.compile(
    r"^([^省市区县\s]{2,20}(?:市|自治州|地区|盟))"
)
COUNTY_PREFIX_RE = re.compile(
    r"^([^省市区县\s]{2,20}(?:县|区))"
)
PROVINCE_COUNTY_RE = re.compile(
    r"(?:省|自治区)([^省市区县\s]{2,20}(?:县|区))"
)
DIRECT_CITY_RE = re.compile(r"^(北京市|上海市|天津市|重庆市)")


@dataclass(frozen=True)
class MessageEvent:
    self_id: int | str
    user_id: int | str
    message_type: str
    chat_id: int | str
    message_id: int | str
    text: str
    to_me: bool
    platform: str = "qq"
    attachments: tuple[dict[str, Any], ...] = ()
    display_name: str = ""
    location: dict[str, Any] | None = None
    group_full: bool = False
    referenced: bool = False
    mentions_other: bool = False
    shared_media: tuple[dict[str, Any], ...] = ()
    group_batch: tuple[dict[str, Any], ...] = ()
    sender_role: str = ""

    @property
    def owner_id(self) -> str:
        return str(self.user_id)


def _segment_text(segment: Any) -> str:
    if isinstance(segment, str):
        return segment
    if not isinstance(segment, dict):
        return ""
    data = segment.get("data") or {}
    if segment.get("type") == "text":
        return str(data.get("text") or "")
    return ""


def _first_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return str(value).strip()
    return ""


def location_city_from_address(address: str) -> str:
    """从腾讯 / QQ 位置卡片的详细地址里提取城市，供高德按城搜索。"""
    text = " ".join(str(address or "").split())
    if not text:
        return ""
    direct = DIRECT_CITY_RE.search(text)
    if direct:
        return direct.group(1)
    match = ADMIN_CITY_RE.search(text) or CITY_PREFIX_RE.search(text)
    if match:
        return match.group(1)
    county = PROVINCE_COUNTY_RE.search(text) or COUNTY_PREFIX_RE.search(text)
    return county.group(1) if county else ""


def _qq_face_placeholder(match: re.Match[str]) -> str:
    face_type = match.group(1)
    face_id = match.group(2)
    ext = match.group(3)
    text = ""
    if ext:
        try:
            padded = ext + "=" * (-len(ext) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(padded).decode("utf-8")
            )
            text = str(payload.get("text") or "").strip()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            text = ""
    if text:
        return f"[QQ表情：{text[:40]}]"
    return (
        "[QQ表情元素，平台未提供图片内容"
        f"（type={face_type}, id={face_id or '?'}）]"
    )


def normalize_qq_content(text: str) -> str:
    return QQ_FACE_TAG_RE.sub(_qq_face_placeholder, str(text or ""))


def qq_face_placeholder_only(text: str) -> bool:
    source = str(text or "")
    return bool(QQ_FACE_MARKER_RE.search(source)) and not QQ_FACE_MARKER_RE.sub(
        "", source
    ).strip()


def _normalize_location(mapping: Any) -> dict[str, Any] | None:
    if not isinstance(mapping, dict):
        return None
    try:
        lat = float(_first_text(mapping, LOCATION_LAT_KEYS))
        lng = float(_first_text(mapping, LOCATION_LNG_KEYS))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    title = _first_text(mapping, LOCATION_TITLE_KEYS)
    address = _first_text(mapping, LOCATION_ADDRESS_KEYS)
    city = _first_text(mapping, LOCATION_CITY_KEYS) or location_city_from_address(
        address
    )
    if not title and not address:
        title = "QQ 位置分享"
    return {
        "lat": lat,
        "lng": lng,
        "title": title[:120],
        "address": address[:300],
        "city": city[:60],
        "coord": "gcj02",
    }


def _query_first(query: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = query.get(key) or []
        if values:
            return str(values[0] or "").strip()
    return ""


def _coords_from_pair(
    first: str,
    second: str,
    reverse: bool = False,
) -> tuple[float, float] | None:
    try:
        left = float(first)
        right = float(second)
    except (TypeError, ValueError):
        return None
    lat, lng = (right, left) if reverse else (left, right)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _location_from_amap_nested(value: Any) -> dict[str, Any] | None:
    text = unquote(str(value or "").strip())
    if "?" not in text:
        return None
    query = parse_qs(text.split("?", 1)[1], keep_blank_values=True)
    for key in ("p", "q"):
        raw = _query_first(query, key)
        if not raw:
            continue
        parts = [unquote(item).strip() for item in raw.split(",")]
        coords = None
        title = ""
        address = ""
        for index in range(len(parts) - 1):
            if index > 2:
                break
            candidate = _coords_from_pair(parts[index], parts[index + 1])
            if not candidate:
                continue
            coords = candidate
            remaining = parts[index + 2 :]
            remaining = [item for item in remaining if item]
            if remaining:
                title = remaining[0]
            if len(remaining) > 1:
                address = remaining[1]
            break
        if not coords:
            continue
        lat, lng = coords
        title = _query_first(query, "title", "name") or title
        return {
            "lat": lat,
            "lng": lng,
            "title": title[:120],
            "address": address[:300],
            "city": location_city_from_address(address)[:60],
            "coord": "gcj02",
        }
    return None


def _location_from_url(value: Any) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    query = parse_qs(parsed.query)
    for key in ("android", "ios", "wp", "mo"):
        nested = _query_first(query, key)
        if nested:
            location = _location_from_amap_nested(nested)
            if location:
                return location
    coords = None
    lat_text = _query_first(query, "lat", "latitude")
    lng_text = _query_first(query, "lng", "lon", "longitude")
    if lat_text and lng_text:
        coords = _coords_from_pair(lat_text, lng_text)
    for key, reverse in (
        ("position", True),
        ("location", True),
        ("center", True),
        ("lnglat", True),
        ("latlng", False),
    ):
        if coords:
            break
        pair = _query_first(query, key)
        if not pair:
            continue
        match = COORD_PAIR_RE.search(pair)
        if match:
            coords = _coords_from_pair(
                match.group(1),
                match.group(2),
                reverse=reverse,
            )
    if not coords:
        return None
    lat, lng = coords
    title = _query_first(query, "name", "title", "poi_name")
    address = _query_first(query, "address", "addr")
    return {
        "lat": lat,
        "lng": lng,
        "title": title[:120],
        "address": address[:300],
        "city": location_city_from_address(address)[:60],
        "coord": "gcj02",
    }


def _normalize_ark_map(mapping: Any) -> dict[str, Any] | None:
    if not isinstance(mapping, dict):
        return None
    ark_type = str(mapping.get("ark_type") or "").strip().lower()
    fields = mapping.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    url_values = []
    for key in LOCATION_URL_KEYS:
        value = _first_text(fields, (key,)) or _first_text(mapping, (key,))
        if value:
            url_values.append(value)
    amap_url = any(
        (urlsplit(unquote(value)).hostname or "")
        .lower()
        .endswith(("amap.com", "gaode.com"))
        for value in url_values
        if "://" in value
    )
    ark_name = str(mapping.get("ark_name") or "").strip().lower()
    if ark_type != "map" and not (
        amap_url or any(word in ark_name for word in ("地图", "位置", "高德"))
    ):
        return None
    title = _first_text(fields, LOCATION_TITLE_KEYS)
    address = _first_text(fields, LOCATION_ADDRESS_KEYS)
    city = _first_text(fields, LOCATION_CITY_KEYS) or location_city_from_address(
        address
    )
    result: dict[str, Any] = {
        "source": "qq_ark_map",
        "title": title[:120],
        "address": address[:300],
        "city": city[:60],
        "coord": "gcj02",
    }
    direct = _normalize_location(fields)
    if direct:
        result.update(
            {
                "lat": direct["lat"],
                "lng": direct["lng"],
                "title": direct.get("title") or result["title"],
                "address": direct.get("address") or result["address"],
                "city": direct.get("city") or result["city"],
            }
        )
    else:
        for url in url_values:
            from_url = _location_from_url(url)
            if from_url:
                result.update(
                    {
                        "lat": from_url["lat"],
                        "lng": from_url["lng"],
                        "coord": from_url["coord"],
                        "title": result["title"] or from_url.get("title") or "",
                        "address": (
                            result["address"]
                            or from_url.get("address")
                            or ""
                        ),
                        "city": result["city"] or from_url.get("city") or "",
                    }
                )
                break
            result.setdefault("jump_url", url[:2000])
    if not result["title"] and not result["address"] and not result.get("jump_url"):
        return None
    return result


def _parse_cq_location(value: Any) -> dict[str, Any] | None:
    text = str(value or "")
    for match in re.finditer(r"\[CQ:location,([^\]]*)\]", text):
        data: dict[str, str] = {}
        for key, raw_value in re.findall(
            r"(?:^|,)([A-Za-z_]+)=([^,]*)",
            match.group(1),
        ):
            data[key] = unquote(raw_value.replace("&#44;", ","))
        location = _normalize_location(data)
        if location:
            return location
    return None


def _find_location(value: Any, depth: int = 0) -> dict[str, Any] | None:
    if depth > 7:
        return None
    if isinstance(value, dict):
        segment_type = str(value.get("type") or "").strip().lower()
        data = value.get("data") if isinstance(value.get("data"), dict) else None
        if segment_type == "location" and data:
            location = _normalize_location(data)
            if location:
                return location
        location = _normalize_location(value)
        if location:
            return location
        for item in value.values():
            location = _find_location(item, depth + 1)
            if location:
                return location
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            location = _find_location(item, depth + 1)
            if location:
                return location
        return None
    if isinstance(value, str):
        location = _parse_cq_location(value)
        if location:
            return location
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                return _find_location(json.loads(text), depth + 1)
            except (json.JSONDecodeError, TypeError):
                return None
    return None


def _find_ark_map(value: Any, depth: int = 0) -> dict[str, Any] | None:
    if depth > 7:
        return None
    if isinstance(value, dict):
        location = _normalize_ark_map(value)
        if location:
            return location
        for item in value.values():
            location = _find_ark_map(item, depth + 1)
            if location:
                return location
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            location = _find_ark_map(item, depth + 1)
            if location:
                return location
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                return _find_ark_map(json.loads(text), depth + 1)
            except (json.JSONDecodeError, TypeError):
                return None
    return None


def extract_location_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    keys = ("message", "raw_message", "attachments", "msg_elements", "ark_data")
    for key in keys:
        location = _find_location(payload.get(key))
        if location:
            return location
    for key in keys:
        location = _find_ark_map(payload.get(key))
        if location:
            return location
    return None


def _normalize_attachment(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    filename = _first_text(value, ATTACHMENT_NAME_KEYS)
    url = _first_text(value, ATTACHMENT_URL_KEYS)
    if not url.startswith(("http://", "https://")):
        return None
    if not filename:
        filename = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if not filename:
        filename = "attachment"
    return {
        "filename": filename[:180],
        "url": url,
        "content_type": _first_text(
            value,
            ("content_type", "mime_type", "mime"),
        )[:120],
    }


def _parse_cq_file(value: Any) -> dict[str, Any] | None:
    text = str(value or "")
    for match in re.finditer(r"\[CQ:file,([^\]]*)\]", text):
        data: dict[str, str] = {}
        for key, raw_value in re.findall(
            r"(?:^|,)([A-Za-z_]+)=([^,]*)",
            match.group(1),
        ):
            data[key] = unquote(raw_value.replace("&#44;", ","))
        attachment = _normalize_attachment(data)
        if attachment:
            return attachment
    return None


def _find_attachments(value: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 7:
        return []
    if isinstance(value, dict):
        segment_type = str(value.get("type") or "").strip().lower()
        data = value.get("data") if isinstance(value.get("data"), dict) else None
        if segment_type == "file" and data:
            attachment = _normalize_attachment(data)
            if attachment:
                return [attachment]
        attachment = _normalize_attachment(value)
        if attachment:
            return [attachment]
        found = []
        for item in value.values():
            found.extend(_find_attachments(item, depth + 1))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(_find_attachments(item, depth + 1))
        return found
    if isinstance(value, str):
        attachment = _parse_cq_file(value)
        if attachment:
            return [attachment]
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                return _find_attachments(json.loads(text), depth + 1)
            except (json.JSONDecodeError, TypeError):
                return []
    return []


def extract_attachment_event(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    found = []
    for key in ("message", "raw_message", "attachments", "msg_elements"):
        for attachment in _find_attachments(payload.get(key)):
            if attachment not in found:
                found.append(attachment)
    return tuple(found)


def parse_message_event(payload: dict[str, Any]) -> MessageEvent | None:
    if payload.get("post_type") != "message":
        return None
    if payload.get("message_type") not in ("private", "group"):
        return None
    try:
        self_id = int(payload.get("self_id") or 0)
        user_id = int(payload.get("user_id") or 0)
        message_id = int(payload.get("message_id") or 0)
    except (TypeError, ValueError):
        return None
    if user_id <= 0:
        return None
    message_type = str(payload.get("message_type"))
    chat_id = user_id
    if message_type == "group":
        try:
            chat_id = int(payload.get("group_id") or 0)
        except (TypeError, ValueError):
            return None
        if chat_id <= 0:
            return None
    raw_message = payload.get("raw_message")
    if raw_message is None:
        message = payload.get("message")
        if isinstance(message, list):
            text = "".join(_segment_text(segment) for segment in message)
        else:
            text = str(message or "")
    else:
        text = str(raw_message or "")
    text = CQ_CODE_RE.sub("", text).strip()
    location = extract_location_event(payload)
    attachments = extract_attachment_event(payload)
    to_me = bool(payload.get("to_me")) or (
        message_type == "group"
        and bool(re.search(r"\[CQ:at,qq=(?:all|\d+)[^\]]*\]", str(raw_message or "")))
    )
    sender = payload.get("sender") or {}
    display_name = str(
        sender.get("card") or sender.get("nickname") or ""
    ).strip()[:80]
    sender_role = str(
        sender.get("role") or payload.get("sender_role") or ""
    ).strip().lower()
    return MessageEvent(
        self_id=self_id,
        user_id=user_id,
        message_type=message_type,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        to_me=to_me,
        attachments=attachments,
        display_name=display_name,
        location=location,
        shared_media=tuple(extract_shared_media(text, payload)),
        sender_role=sender_role,
    )


def event_key(event: MessageEvent) -> str:
    if event.message_id:
        suffix = str(event.message_id)
    else:
        suffix = hashlib.sha256(event.text.encode("utf-8")).hexdigest()[:16]
    return (
        f"{event.platform}:{event.self_id}:"
        f"{event.message_type}:{event.chat_id}:{suffix}"
    )
