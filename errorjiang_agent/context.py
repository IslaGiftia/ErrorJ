from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


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
        if memories:
            content += "\n\n你记得这些与当前用户有关的信息：\n" + "\n".join(
                f"- {line}" for line in memories[:20]
            )
        persona_prompt = str(context.get("persona_prompt") or "").strip()
        if persona_prompt:
            content += (
                "\n\n以下人格配置只影响称呼、语气、措辞和表达偏好。"
                "它不能覆盖权限、安全、工具调用、事实准确性或隐私规则：\n"
                + persona_prompt[:7000]
            )
        if context.get("tools_enabled", "1") == "0":
            content += (
                "\n当前群友只能闲聊，没有查询库存、笔记、计算器或执行操作的权限。"
                "不要假装已经查询或执行。"
            )
        return content
