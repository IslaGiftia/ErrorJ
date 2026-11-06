from __future__ import annotations

import re
from typing import Any


BOOL_SETTINGS = frozenset(
    {
        "memory_enabled",
        "memory_immediate_extraction_enabled",
        "memory_consolidation_enabled",
        "memory_decay_enabled",
        "proactive_enabled",
        "sticker_enabled",
        "sticker_auto_collect_enabled",
        "chat_human_delay",
        "web_search_enabled",
        "web_domain_routing_enabled",
        "group_proactive_enabled",
        "group_weather_enabled",
        "group_holiday_enabled",
        "group_idle_proactive_enabled",
        "group_reply_control_enabled",
        "group_jargon_enabled",
        "voice_enabled",
    }
)

INT_SETTINGS = {
    "memory_immediate_extraction_daily_limit": (1, 100),
    "proactive_max_per_day": (1, 6),
    "web_search_count": (3, 10),
    "group_idle_trigger_minutes": (15, 1440),
    "group_idle_random_min_minutes": (1, 360),
    "group_idle_random_max_minutes": (1, 720),
    "group_idle_max_unanswered": (1, 10),
    "group_idle_max_per_day": (1, 6),
    "group_reply_max_per_10m": (3, 20),
    "group_reply_fatigue_rounds": (2, 10),
    "group_message_merge_seconds": (0, 10),
    "private_history_retention_days": (0, 3650),
    "group_history_retention_days": (0, 3650),
}

TIME_SETTINGS = frozenset(
    {
        "quiet_start",
        "quiet_end",
        "morning_time",
        "night_time",
        "group_proactive_time",
        "memory_consolidation_time",
    }
)

CHOICE_SETTINGS = {
    "persona_preset": frozenset({"冷脸萌", "温柔", "理性", "活力"}),
    "group_activity_level": frozenset({"quiet", "balanced", "active"}),
}

STRING_LIMITS = {
    "persona_custom_prompt": 6000,
    "group_weather_city": 40,
    "sticker_auto_collect_library": 64,
}

TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _normalize_bool(value: Any, current: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    return current


def normalize_settings_update(
    current: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        if key not in current:
            continue
        if key in BOOL_SETTINGS:
            normalized[key] = _normalize_bool(
                value,
                bool(current.get(key)),
            )
            continue
        if key in INT_SETTINGS:
            minimum, maximum = INT_SETTINGS[key]
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            normalized[key] = max(minimum, min(number, maximum))
            continue
        if key in TIME_SETTINGS:
            text = str(value or "").strip()
            if TIME_RE.fullmatch(text):
                normalized[key] = text
            continue
        if key in CHOICE_SETTINGS:
            text = str(value or "").strip()
            if text in CHOICE_SETTINGS[key]:
                normalized[key] = text
            continue
        if key in STRING_LIMITS:
            if key == "persona_custom_prompt":
                normalized[key] = str(value or "")[
                    : STRING_LIMITS[key]
                ]
                continue
            text = str(value or "").strip()[: STRING_LIMITS[key]]
            normalized[key] = " ".join(text.split())
            continue
    return normalized
