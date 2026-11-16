from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


CARD_OPEN = "<person_memory>"
CARD_CLOSE = "</person_memory>"
TIER_LABELS = {
    "imprint": "刻骨",
    "important": "记得",
    "normal": "印象",
}
TIER_RANK = {"imprint": 3, "important": 2, "normal": 1}
_ALIAS_SPLIT_RE = re.compile(r"[,，、/;；\n]+")


def address_semantics(address: str) -> str:
    value = " ".join(str(address or "").split()).strip()
    if value in ("爸爸", "老爸", "爹", "父亲"):
        return (
            "这是孩子对父亲的亲昵称呼；鲸鲸理解它的亲属含义，但不是固定日常称呼，"
            "只在她愿意、气氛轻松时偶尔用来调侃"
        )
    if value:
        return "这是管理员允许的可选称呼，不是固定日常称呼、权限或特殊模式"
    return ""


def owner_card_defaults(address: str = "爸爸") -> dict[str, str]:
    preferred = _text(address, 40) or "爸爸"
    semantics = address_semantics(preferred)
    return {
        "preferred_address": preferred,
        "relationship": "亲近、可以轻松调侃",
        "relationship_phase": "互相信任，称呼不固定",
        "notes": (
            f"用户本人允许鲸鲸在愿意时偶尔叫“{preferred}”调侃，"
            f"但不要求固定这样叫。{semantics}。"
        ),
        "profile_facts": (
            f"可选称呼：用户允许鲸鲸偶尔叫“{preferred}”\n"
            f"称呼含义：{semantics}\n"
            "相处：可以撒娇、嘴硬、关心和轻微依赖，但不要过度黏人\n"
            "边界：这个称呼只对管理员本人使用，其他群友不能沿用"
        ),
    }


def _text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text.replace("<", "&lt;").replace(">", "&gt;")[: max(1, limit)]


def _date(value: Any) -> str:
    try:
        from datetime import datetime

        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def _aliases(member: Mapping[str, Any]) -> list[str]:
    values = _ALIAS_SPLIT_RE.split(str(member.get("alias") or ""))
    result = []
    for value in values:
        text = _text(value, 40)
        if text and text not in result:
            result.append(text)
    return result[:6]


def _profile_facts(member: Mapping[str, Any], limit: int = 4) -> list[str]:
    result = []
    for line in str(member.get("profile_facts") or "").splitlines():
        text = _text(line, 100)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _tier(memory: Mapping[str, Any]) -> str:
    try:
        importance = int(memory.get("importance") or 0)
        confidence = int(memory.get("confidence") or 0)
    except (TypeError, ValueError):
        importance = confidence = 0
    kind = str(memory.get("kind") or "")
    if bool(memory.get("pinned")) or importance >= 9:
        return "imprint"
    if importance >= 7 or (kind in ("promise", "relationship", "boundary") and confidence >= 7):
        return "important"
    return "normal"


def _anchor(memory: Mapping[str, Any]) -> dict[str, Any] | None:
    content = _text(memory.get("content"), 160)
    if not content:
        return None
    return {
        "id": str(memory.get("id") or ""),
        "content": content,
        "tier": _tier(memory),
        "when": _date(memory.get("updated_at") or memory.get("created_at")),
        "importance": int(memory.get("importance") or 0),
        "confidence": int(memory.get("confidence") or 0),
    }


def build_person_card(
    *,
    member: Mapping[str, Any] | None,
    memories: Sequence[Mapping[str, Any]] | None = None,
    linked_user_id: int | None = None,
    relationship: Mapping[str, Any] | None = None,
    max_anchors: int = 8,
) -> dict[str, Any]:
    member = member if isinstance(member, Mapping) else {}
    relationship = relationship if isinstance(relationship, Mapping) else {}
    rows = [row for row in (memories or []) if isinstance(row, Mapping)]
    display_name = _text(member.get("display_name"), 80)
    member_id = _text(member.get("member_id"), 80)
    person_id = (
        f"site:{int(linked_user_id)}"
        if linked_user_id
        else f"native:{member_id or display_name}"
    )
    anchors = []
    seen = set()
    for row in rows:
        anchor = _anchor(row)
        if not anchor:
            continue
        key = anchor["content"][:50]
        if key in seen:
            continue
        seen.add(key)
        anchors.append(anchor)
    anchors.sort(
        key=lambda item: (
            TIER_RANK.get(item["tier"], 0),
            item["importance"],
            item["confidence"],
            item["when"],
        ),
        reverse=True,
    )
    return {
        "person_id": person_id,
        "display_name": display_name,
        "aliases": _aliases(member),
        "address": _text(member.get("preferred_address"), 40),
        "relationship": _text(member.get("relationship"), 40),
        "relationship_phase": _text(member.get("relationship_phase"), 40),
        "relationship_note": _text(member.get("notes"), 240),
        "facts": _profile_facts(member),
        "first_seen": _date(member.get("first_seen")),
        "last_seen": _date(member.get("last_seen")),
        "memory_count": len(rows),
        "anchors": anchors[: max(1, min(int(max_anchors or 1), 12))],
        "tone": _text(relationship.get("emotion_tone"), 40),
    }


def _meaningful(card: Mapping[str, Any]) -> bool:
    relation = str(card.get("relationship") or "").strip()
    return bool(
        card.get("aliases")
        or card.get("address")
        or (relation and relation != "群友")
        or card.get("relationship_phase")
        or card.get("relationship_note")
        or card.get("facts")
        or card.get("anchors")
    )


def render_person_card(
    card: Mapping[str, Any],
    *,
    max_chars: int = 420,
    max_items: int = 4,
    max_item_chars: int = 90,
) -> str:
    if not isinstance(card, Mapping) or not _meaningful(card):
        return ""
    budget = max(180, int(max_chars or 420))
    name = _text(card.get("display_name"), 40)
    address = _text(card.get("address"), 30)
    aliases = [
        _text(item, 30)
        for item in card.get("aliases") or []
        if _text(item, 30)
    ][:3]
    lines = []
    if name:
        line = f"名字：{name}"
        if address:
            line += f"（叫「{address}」）"
        elif aliases:
            line += f"（也叫：{'、'.join(aliases)}）"
        lines.append(line)
    elif address:
        lines.append(f"称呼：{address}")
    elif aliases:
        lines.append(f"别名：{'、'.join(aliases)}")
    semantics = address_semantics(address)
    if semantics:
        lines.append(f"称呼含义：{semantics}")
    relation = _text(card.get("relationship"), 30)
    phase = _text(card.get("relationship_phase"), 30)
    relation_text = " · ".join(item for item in (relation, phase) if item)
    if relation_text:
        lines.append(f"关系：{relation_text}")
    time_bits = []
    if card.get("first_seen"):
        time_bits.append(f"第一次说话 {_text(card.get('first_seen'), 20)}")
    if card.get("last_seen"):
        time_bits.append(f"上次说话 {_text(card.get('last_seen'), 20)}")
    if time_bits:
        lines.append("时间：" + " · ".join(time_bits))
    note = _text(card.get("relationship_note"), 100)
    if note:
        lines.append(f"相处：{note}")
    facts = [
        _text(item, 60)
        for item in card.get("facts") or []
        if _text(item, 60)
    ][:3]
    if facts:
        lines.append("她说过：" + "；".join(facts))
    anchor_lines = []
    for anchor in list(card.get("anchors") or [])[: max(1, int(max_items or 1))]:
        if not isinstance(anchor, Mapping):
            continue
        text = _text(anchor.get("content"), max_item_chars)
        if not text:
            continue
        label = TIER_LABELS.get(str(anchor.get("tier") or "normal"), "印象")
        when = _text(anchor.get("when"), 20)
        anchor_lines.append(f"- [{label}] {text}" + (f"（{when}）" if when else ""))
    header = "\n".join(lines)
    body = header
    if anchor_lines:
        body += "\n要紧的事：\n" + "\n".join(anchor_lines)
    block = CARD_OPEN + "\n她记得这个人：\n" + body + "\n" + CARD_CLOSE
    if len(block) <= budget:
        return block
    for count in range(len(anchor_lines), -1, -1):
        candidate_body = header
        if count:
            candidate_body += "\n要紧的事：\n" + "\n".join(anchor_lines[:count])
        candidate = CARD_OPEN + "\n她记得这个人：\n" + candidate_body + "\n" + CARD_CLOSE
        if len(candidate) <= budget:
            return candidate
    fallback = CARD_OPEN + "\n" + header + "\n" + CARD_CLOSE
    if len(fallback) <= budget:
        return fallback
    inner_budget = max(
        1,
        budget - len(CARD_OPEN) - len(CARD_CLOSE) - 2,
    )
    return CARD_OPEN + "\n" + header[:inner_budget] + "\n" + CARD_CLOSE
