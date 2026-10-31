from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .errors import AgentError


ToolHandler = Callable[
    [dict[str, Any], dict[str, str] | None, str],
    dict[str, Any],
]


@dataclass(frozen=True)
class ToolSpec:
    definition: dict[str, Any]
    handler: ToolHandler
    requires_web_search: bool = False
    admin_only: bool = False

    @property
    def name(self) -> str:
        return str(self.definition.get("function", {}).get("name") or "")


class ToolRegistry:
    def __init__(self, definitions: list[dict[str, Any]]):
        self._definitions = {
            str(item.get("function", {}).get("name") or ""): item
            for item in definitions
            if isinstance(item, dict)
        }
        self._specs: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        requires_web_search: bool = False,
        admin_only: bool = False,
    ) -> None:
        definition = self._definitions.get(name)
        if not definition:
            raise ValueError(f"未定义的模型工具：{name}")
        self._specs[name] = ToolSpec(
            definition=definition,
            handler=handler,
            requires_web_search=requires_web_search,
            admin_only=admin_only,
        )

    def available(
        self,
        tool_context: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        context = tool_context or {}
        if context.get("tools_enabled", "1") == "0":
            return []
        search_allowed = context.get("web_search_enabled", "1") == "1"
        is_admin = context.get("is_admin", "1") == "1"
        result = []
        for name, spec in self._specs.items():
            if spec.requires_web_search and not search_allowed:
                continue
            if spec.admin_only and not is_admin:
                continue
            result.append(self._definitions[name])
        return result

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_context: dict[str, str] | None,
        user_text: str,
    ) -> dict[str, Any]:
        spec = self._specs.get(name)
        if not spec:
            raise AgentError("模型请求了未知工具。")
        context = tool_context or {}
        if context.get("tools_enabled", "1") == "0":
            raise AgentError("当前会话没有工具权限。")
        if spec.requires_web_search and (
            context.get("web_search_enabled", "1") != "1"
        ):
            return {"error": "网页搜索未启用。", "untrusted": True}
        if spec.admin_only and context.get("is_admin", "1") != "1":
            raise AgentError("当前会话没有该工具权限。")
        return spec.handler(arguments, tool_context, user_text)

    def names(self) -> list[str]:
        return list(self._specs)
