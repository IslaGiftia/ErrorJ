from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from urllib.parse import unquote


CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]")
LOCATION_LAT_KEYS = ("lat", "latitude")
LOCATION_LNG_KEYS = ("lon", "lng", "longitude")
LOCATION_TITLE_KEYS = ("title", "name", "poi_name", "location_name")
LOCATION_ADDRESS_KEYS = ("address", "addr", "poi_address", "content")
ATTACHMENT_NAME_KEYS = ("filename", "file_name", "name", "file")
ATTACHMENT_URL_KEYS = ("url", "file_url", "download_url", "file")


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
    if not title and not address:
        title = "QQ 位置分享"
    return {
        "lat": lat,
        "lng": lng,
        "title": title[:120],
        "address": address[:300],
        "coord": "gcj02",
    }


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


def extract_location_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("message", "raw_message", "attachments", "msg_elements"):
        location = _find_location(payload.get(key))
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
