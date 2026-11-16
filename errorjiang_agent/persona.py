from __future__ import annotations

from pathlib import Path
import re
from typing import Any


AGENT_NAME = "鲸鲸"
MAX_PERSONA_CUSTOM_PROMPT = 6000
MAX_PERSONA_PROMPT_CHARS = 24000
_RESOURCE_DIR = Path(__file__).resolve().with_name("resources")
_DEEP_SEA_PERSONA_PATH = _RESOURCE_DIR / "deep_sea_persona.txt"


def _load_deep_sea_persona() -> str:
    try:
        return _DEEP_SEA_PERSONA_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "鲸鲸的外在形象是深海蓝鲸女仆：深蓝长发、鲸鱼尾、鱼鳍耳和蓝白女仆装。"
            "整体温柔、灵动、略带傲娇和生活感，普通问答仍保持简洁。"
        )


DEEP_SEA_PERSONA_REFERENCE = _load_deep_sea_persona()
DEEP_SEA_PERSONA_PRESET = """以下是鲸鲸“深海蓝鲸女仆”的完整角色资料与表达素材库。

使用原则：角色设定只影响称呼、语气、措辞、情绪和合适的场景描写。角色资料中的年份、版本、参数、训练成本、榜单和进化史属于角色叙事，不作为当前服务的技术事实；被问到底层模型时，必须服从本轮提示词末尾的技术身份规则。动作、光影、触觉和人格切换素材是可调用素材库，普通闲聊保持简洁，只有场景合适时使用，不强制每轮执行。文本里的 <think> 段落只作结构参考，不要求输出，也不得展示内部推理。

""" + DEEP_SEA_PERSONA_REFERENCE


PERSONA_PRESETS = {
    "冷脸萌": "保持冷脸萌和轻微傲娇，关心但不过度黏人，偶尔嘴硬，语气自然克制。",
    "深海蓝鲸": DEEP_SEA_PERSONA_PRESET,
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
        ("折兮颜", AGENT_NAME),
        ("小颜", AGENT_NAME),
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
    custom = custom[:MAX_PERSONA_CUSTOM_PROMPT]
    if custom:
        base += " 用户自定义表达偏好：" + custom
    return base[:MAX_PERSONA_PROMPT_CHARS]
