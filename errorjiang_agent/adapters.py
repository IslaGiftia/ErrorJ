from __future__ import annotations

from typing import Any, Protocol

from .onebot import MessageEvent, parse_message_event
from .qqbot import parse_qqbot_event


class PlatformAdapter(Protocol):
    platform: str

    def parse(
        self,
        event_type: str,
        payload: dict[str, Any],
        self_id: str | int,
    ) -> MessageEvent | None:
        ...


class OneBotAdapter:
    platform = "qq"

    def parse(
        self,
        event_type: str,
        payload: dict[str, Any],
        self_id: str | int,
    ) -> MessageEvent | None:
        del event_type, self_id
        return parse_message_event(payload)


class QQBotAdapter:
    platform = "qqbot"

    def parse(
        self,
        event_type: str,
        payload: dict[str, Any],
        self_id: str | int,
    ) -> MessageEvent | None:
        return parse_qqbot_event(event_type, payload, self_id)


class AdapterRegistry:
    def __init__(self, adapters: list[PlatformAdapter] | None = None):
        self._adapters: dict[str, PlatformAdapter] = {}
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: PlatformAdapter) -> None:
        self._adapters[adapter.platform] = adapter

    def get(self, platform: str) -> PlatformAdapter:
        key = str(platform or "").strip().lower()
        adapter = self._adapters.get(key)
        if not adapter:
            raise KeyError(f"未注册平台适配器：{key}")
        return adapter

    def parse(
        self,
        platform: str,
        event_type: str,
        payload: dict[str, Any],
        self_id: str | int,
    ) -> MessageEvent | None:
        return self.get(platform).parse(event_type, payload, self_id)
