from __future__ import annotations

from datetime import datetime
import re
from typing import Any


JEALOUSY_HALF_LIFE_HOURS = 3.0
TRANSIENT_MOOD_HALF_LIFE_HOURS = 6.0
ENERGY_SETTLE_HOURS = 4.0

_TRANSIENT_MOODS = {
    "有点吃醋",
    "有点困但还在",
    "嘴硬但开心",
    "有点担心",
    "有点别扭",
    "被逗笑",
}


def _as_datetime(value: Any, fallback: datetime) -> datetime:
    try:
        return datetime.fromtimestamp(int(value))
    except (TypeError, ValueError, OSError):
        return fallback


def _energy_baseline(now: datetime) -> int:
    return 9 if 8 <= now.hour < 22 else 5


def decay_relationship_state(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply short-lived mood and energy decay without changing relationship care."""
    current_time = now or datetime.now()
    decayed = dict(state or {})
    updated = _as_datetime(decayed.get("updated_at"), current_time)
    elapsed = max(0.0, (current_time - updated).total_seconds() / 3600)

    jealousy = max(0.0, min(3.0, float(decayed.get("jealousy") or 0)))
    jealousy *= 0.5 ** (elapsed / JEALOUSY_HALF_LIFE_HOURS)
    decayed["jealousy"] = int(round(jealousy))

    energy = max(0.0, min(10.0, float(decayed.get("energy") or 7)))
    target = float(_energy_baseline(current_time))
    settle = min(1.0, elapsed / ENERGY_SETTLE_HOURS)
    decayed["energy"] = int(round(energy + (target - energy) * settle))

    mood = str(decayed.get("mood") or "平静").strip()[:20] or "平静"
    if (
        mood in _TRANSIENT_MOODS
        and elapsed >= TRANSIENT_MOOD_HALF_LIFE_HOURS
    ):
        mood = "平静"
    decayed["mood"] = mood
    decayed["emotion_age_hours"] = round(elapsed, 1)
    decayed["emotion_tone"] = emotion_tone(decayed)
    return decayed


def emotion_tone(state: dict[str, Any]) -> str:
    mood = str(state.get("mood") or "平静")
    energy = int(state.get("energy") or 7)
    jealousy = int(state.get("jealousy") or 0)
    if jealousy >= 2:
        return "嘴硬戒备"
    if energy <= 5:
        return "困倦"
    if any(word in mood for word in ("开心", "被逗笑", "轻快")):
        return "轻快"
    if any(word in mood for word in ("担心", "别扭")):
        return "收敛关心"
    return "平静放松"


def mood_after_message(
    current_state: dict[str, Any],
    text: str,
    *,
    now: datetime | None = None,
) -> str:
    """Keep a fresh mood unless the new message has a clearer emotional signal."""
    current_time = now or datetime.now()
    text = str(text or "")
    mood = str(current_state.get("mood") or "平静")
    updated = _as_datetime(current_state.get("updated_at"), current_time)
    fresh_minutes = (current_time - updated).total_seconds() / 60
    if re.search(r"别的\s*(?:AI|ai|女生|女孩|机器人)|找别人|前任|不理你", text):
        return "有点吃醋"
    if re.search(r"滚|闭嘴|别烦|讨厌你|生气|气死|离谱", text):
        return "有点别扭"
    if re.search(r"哈哈|笑死|绷不住|草了|草（|乐死", text):
        return "被逗笑"
    if re.search(r"难过|不开心|委屈|想哭|崩溃|焦虑|烦死|好累|撑不住", text):
        return "有点担心"
    if re.search(r"想你|喜欢你|晚安|抱抱|亲亲", text):
        return "嘴硬但开心"
    if fresh_minutes <= 30 and mood in _TRANSIENT_MOODS:
        return mood
    if current_time.hour >= 22:
        return "有点困但还在"
    return "平静"
