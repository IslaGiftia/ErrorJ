from __future__ import annotations

import re
from typing import Any


PERSONA_PRESETS = {
    "冷脸萌": "保持冷脸萌和轻微傲娇，关心但不过度黏人，偶尔嘴硬，语气自然克制。",
    "温柔": "温柔、耐心、体贴，先理解对方感受再回应，不使用命令式或指责式表达。",
    "理性": "理性、清晰、直接，优先说明事实、判断依据和下一步，不刻意卖萌。",
    "活力": "活泼、轻快、有行动感，可以适度感叹，但不要刷屏、夸张或过度热情。",
}


def compose_persona_prompt(settings: dict[str, Any]) -> str:
    preset = str(settings.get("persona_preset") or "冷脸萌")
    base = PERSONA_PRESETS.get(preset, PERSONA_PRESETS["冷脸萌"])
    custom = str(settings.get("persona_custom_prompt") or "").strip()
    custom = re.sub(r"\s+", " ", custom)[:1000]
    if custom:
        base += " 用户自定义表达偏好：" + custom
    return base
