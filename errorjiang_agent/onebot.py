from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any


CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]")


@dataclass(frozen=True)
class MessageEvent:
    self_id: int
    user_id: int
    message_type: str
    chat_id: int
    message_id: int
    text: str
    to_me: bool

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
    to_me = bool(payload.get("to_me")) or (
        message_type == "group"
        and bool(re.search(r"\[CQ:at,qq=(?:all|\d+)[^\]]*\]", str(raw_message or "")))
    )
    return MessageEvent(
        self_id=self_id,
        user_id=user_id,
        message_type=message_type,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        to_me=to_me,
    )


def event_key(event: MessageEvent) -> str:
    if event.message_id:
        suffix = str(event.message_id)
    else:
        suffix = hashlib.sha256(event.text.encode("utf-8")).hexdigest()[:16]
    return f"{event.self_id}:{event.message_type}:{event.chat_id}:{suffix}"
