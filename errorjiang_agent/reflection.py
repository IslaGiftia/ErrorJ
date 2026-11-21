from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Iterable


def _text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[: max(1, int(limit))]


def parse_reflection_payload(
    raw: str,
    day: str,
) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    agenda = []
    for item in data.get("agenda") or []:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"), 120)
        item_day = _text(item.get("date"), 10)
        item_time = _text(item.get("time"), 5)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item_day):
            item_day = day
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item_time):
            item_time = ""
        if not title or not item_time:
            continue
        agenda.append(
            {
                "date": item_day,
                "time": item_time,
                "title": title,
            }
        )
        if len(agenda) >= 8:
            break

    important_dates = []
    for item in data.get("important_dates") or []:
        if not isinstance(item, dict):
            continue
        month_day = _text(item.get("date") or item.get("month_day"), 5)
        title = _text(item.get("title"), 120)
        content = _text(item.get("content"), 240)
        if not re.fullmatch(r"(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])", month_day):
            continue
        if not title:
            continue
        important_dates.append(
            {
                "month_day": month_day,
                "title": title,
                "content": content or title,
            }
        )
        if len(important_dates) >= 12:
            break

    diary = _text(data.get("diary"), 1600)
    dream = _text(data.get("dream"), 1200)
    reflection = _text(data.get("reflection"), 1600)
    if not any((diary, dream, reflection, agenda, important_dates)):
        return None
    return {
        "day": day,
        "diary": diary,
        "dream": dream,
        "reflection": reflection,
        "agenda": agenda,
        "important_dates": important_dates,
    }


def fallback_reflection(
    day: str,
    transcript: Iterable[str],
    *,
    mood: str = "平静",
    energy: int = 7,
) -> dict[str, Any]:
    lines = [
        _text(line, 180)
        for line in transcript
        if _text(line, 180)
    ]
    topics = [line for line in lines if not line.startswith("鲸鲸：")][-5:]
    if topics:
        topic_text = "、".join(topic[:28] for topic in topics)
        diary = (
            f"今天聊到了{topic_text}。有些话当时只是随口一提，"
            "但回头看，已经能拼出这一天大概的样子。"
        )
    else:
        diary = "今天比较安静，没有发生太多需要专门记住的事。"

    if any(word in mood for word in ("开心", "轻快", "笑意", "被逗笑")):
        dream = "梦里像是一片很亮的海，水面一直有细碎的光，醒来时心情还算轻。"
    elif any(word in mood for word in ("困", "累")):
        dream = "梦里有很慢的潮声，像是醒着又像睡着了，后来连时间都变得模糊。"
    elif any(word in mood for word in ("别扭", "担心", "吃醋")):
        dream = "梦里有一段没说完的话，绕来绕去又回到原来的地方，最后只剩海风。"
    else:
        dream = "梦里没有明确的情节，只记得远处有海声，靠近时又安静下来。"

    energy_text = "精神还算够用" if int(energy) >= 6 else "有点累，想安静一会儿"
    reflection = (
        f"今天最值得留下的不是发生了什么大事，而是聊天时的语气和停顿。"
        f"现在{energy_text}；明天不用刻意表现得很热闹，能把话接住就好。"
    )
    return {
        "day": day,
        "diary": diary,
        "dream": dream,
        "reflection": reflection,
        "agenda": [],
        "important_dates": [],
    }


def agenda_items_for_day(
    reflection: dict[str, Any] | None,
    day: str,
) -> list[dict[str, str]]:
    if not isinstance(reflection, dict):
        return []
    return [
        {
            "date": str(item.get("date") or ""),
            "time": str(item.get("time") or ""),
            "title": str(item.get("title") or ""),
        }
        for item in reflection.get("agenda") or []
        if isinstance(item, dict)
        and str(item.get("date") or "") == day
        and str(item.get("title") or "").strip()
        and str(item.get("time") or "").strip()
    ]


def agenda_near(
    reflection: dict[str, Any] | None,
    now: datetime,
    *,
    minutes_before: int = 15,
    minutes_after: int = 120,
) -> dict[str, str] | None:
    current = now.hour * 60 + now.minute
    best = None
    for item in agenda_items_for_day(reflection, now.strftime("%Y-%m-%d")):
        try:
            hour, minute = [int(part) for part in item["time"].split(":", 1)]
        except (TypeError, ValueError):
            continue
        target = hour * 60 + minute
        distance = target - current
        if -minutes_before <= distance <= minutes_after:
            score = abs(distance)
            if best is None or score < best[0]:
                best = (score, item)
    return best[1] if best else None
