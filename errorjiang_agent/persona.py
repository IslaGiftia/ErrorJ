from __future__ import annotations

import re
from typing import Any


AGENT_NAME = "鲸鲸"


PERSONA_PRESETS = {
    "冷脸萌": "保持冷脸萌和轻微傲娇，关心但不过度黏人，偶尔嘴硬，语气自然克制。",
    "温柔": "温柔、耐心、体贴，先理解对方感受再回应，不使用命令式或指责式表达。",
    "理性": "理性、清晰、直接，优先说明事实、判断依据和下一步，不刻意卖萌。",
    "活力": "活泼、轻快、有行动感，可以适度感叹，但不要刷屏、夸张或过度热情。",
}


def normalize_persona_custom_prompt(value: Any) -> str:
    text = str(value or "")
    replacements = (
        (
            "你是「大肥鱼」",
            f"你是「{AGENT_NAME}」",
        ),
        (
            "别人叫你“大肥鱼”你会炸毛反驳“才不是大肥鱼！”",
            "别人叫你“胖鲸”你会炸毛反驳“才不是胖鲸！”",
        ),
        ("被叫“大肥鱼”", "被叫“胖鲸”"),
        ("用户：你这条大肥鱼", "用户：你这条胖鲸"),
        ("你：才不是大肥鱼！", "你：才不是胖鲸！"),
        ("折兮颜", AGENT_NAME),
        ("小颜", AGENT_NAME),
        ("大肥鱼", AGENT_NAME),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def compose_persona_prompt(settings: dict[str, Any]) -> str:
    preset = str(settings.get("persona_preset") or "冷脸萌")
    base = PERSONA_PRESETS.get(preset, PERSONA_PRESETS["冷脸萌"])
    custom = normalize_persona_custom_prompt(
        settings.get("persona_custom_prompt")
    ).strip()
    custom = re.sub(r"\s+", " ", custom)[:1000]
    if custom:
        base += " 用户自定义表达偏好：" + custom
    return base
