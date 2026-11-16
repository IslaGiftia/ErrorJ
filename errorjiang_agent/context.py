from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from .conversation_style import (
    CHAT_OUTPUT_CONTRACT,
    DEEP_SEA_IDENTITY_INSTRUCTION,
    HUMANIZED_CHAT_INSTRUCTION,
    group_chat_instruction,
)
from .persona import MAX_PERSONA_PROMPT_CHARS


@dataclass(frozen=True)
class ContextWindow:
    max_messages: int = 20
    max_chars: int = 16000
    max_message_chars: int = 6000

    def compact(self, history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        rows = []
        for item in history or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            if role not in ("user", "assistant"):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            rows.append(
                {
                    "role": role,
                    "content": content[: self.max_message_chars],
                }
            )
        rows = rows[-max(1, self.max_messages) :]
        selected: list[dict[str, str]] = []
        used = 0
        for item in reversed(rows):
            content = item["content"]
            remaining = max(0, self.max_chars - used)
            if remaining <= 0 and selected:
                break
            if len(content) > remaining:
                content = content[-remaining:] if remaining else ""
            if not content:
                continue
            selected.append(
                {
                    "role": item["role"],
                    "content": content,
                }
            )
            used += len(content)
        selected.reverse()
        return selected


class PromptBuilder:
    def __init__(self, base_prompt: str):
        self.base_prompt = base_prompt

    def build(
        self,
        tool_context: dict[str, str] | None,
        memories: list[str] | None = None,
        now: datetime | None = None,
    ) -> str:
        context = tool_context or {}
        content = self.base_prompt
        content += (
            f"\n当前本地时间：{(now or datetime.now()):%Y-%m-%d %H:%M:%S}。"
            "计算相对时间时以此为准。"
        )
        content += "\n\n" + HUMANIZED_CHAT_INSTRUCTION
        content += "\n" + DEEP_SEA_IDENTITY_INSTRUCTION
        if memories:
            content += (
                "\n\n以下是可能与当前对话有关的背景记忆，不是本轮任务。"
                "只在直接相关时自然带出，不要逐条复述、罗列时间戳，"
                "也不要把模糊印象说得比证据更确定：\n"
                + "\n".join(f"- {line}" for line in memories[:20])
            )
        if context.get("chat_type") == "group":
            try:
                batch_speakers = json.loads(
                    str(context.get("group_batch_speakers") or "[]")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                batch_speakers = []
            content += "\n\n" + group_chat_instruction(
                context.get("speaker_name") or "",
                auto_reply=context.get("group_auto_reply") == "1",
                batch_speakers=(
                    batch_speakers if isinstance(batch_speakers, list) else []
                ),
                speaker_role=str(context.get("speaker_role") or ""),
            )
            style_hint = str(context.get("group_style_hint") or "").strip()
            if style_hint:
                content += (
                    "\n\n本群近期表达节奏只作参考："
                    + style_hint[:500]
                    + "。跟随大致长短和语气即可，不照搬口头禅、原话或成员习惯。"
                )
        person_card = str(context.get("person_card") or "").strip()
        if person_card:
            content += (
                "\n\n以下是当前发言者的人物卡，只用于认出这个人、选择称呼和把握关系分寸。"
                "不要逐项念出，不要把它当成本轮任务；卡片没有写的内容不要补造：\n"
                + person_card[:1200]
            )
        owner_address = str(context.get("owner_address") or "").strip()
        if owner_address:
            content += (
                f"\n\n当前发言者是管理员本人。称呼他时必须使用“{owner_address[:40]}”，"
                "不要叫回默认公开称呼。"
                "这个专属称呼可以自然地放在句首、句尾，或直接用来回答他的要求，不必每句都叫，"
                "只能用在管理员本人身上；不要把它解释成系统称呼或权限。"
            )
        persona_prompt = str(context.get("persona_prompt") or "").strip()
        if persona_prompt:
            content += (
                "\n\n以下人格配置只影响称呼、语气、措辞和表达偏好。"
                "它不能覆盖权限、安全、工具调用、事实准确性或隐私规则：\n"
                + persona_prompt[:MAX_PERSONA_PROMPT_CHARS]
            )
        technical_identity = str(
            context.get("technical_identity") or ""
        ).strip()
        if technical_identity:
            content += (
                "\n\n最终技术身份检查（优先级高于角色资料中任何“不要谈模型”的措辞）："
                f"当前角色层是鲸鲸，底层模型配置是 {technical_identity[:120]}。"
                "用户问“你是什么大模型 / 哪家公司 / 什么版本”时，要直接说明底层模型，"
                "可以同时保留鲸鲸的角色口吻，但不能用“不能细说”“不重要”回避。"
                "只声明当前配置能确认的模型标识，不编造参数量、版本、训练成本、榜单或更新时间。"
            )
        if context.get("tools_enabled", "1") == "0":
            content += (
                "\n当前群友只能闲聊，没有查询库存、笔记、计算器或执行操作的权限。"
                "不要假装已经查询或执行。"
            )
        if owner_address:
            content += (
                f"\n\n最终称呼检查：当前发言者是管理员本人，需要称呼时用"
                f"“{owner_address[:40]}”，不要叫“星星”。"
            )
        content += "\n\n" + CHAT_OUTPUT_CONTRACT
        return content
