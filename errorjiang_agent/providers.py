from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .clients import DeepSeekClient, post_json
from .errors import AgentError


class LLMProvider(Protocol):
    name: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


class SearchProvider(Protocol):
    def web_search(
        self,
        query: str,
        count: int = 5,
        original_question: str = "",
    ) -> dict[str, Any]:
        ...

    def web_fetch(self, url: str) -> dict[str, Any]:
        ...


@dataclass
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    model: str
    name: str = "openai-compatible"
    timeout: int = 90

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        data = post_json(
            self.base_url + "/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0].get("message"), dict):
            raise AgentError(f"{self.name} 没有返回有效消息。")
        return choices[0]["message"]


class FallbackLLMProvider:
    name = "fallback-chain"

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("至少需要一个 LLM Provider")
        self.providers = providers

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        errors = []
        for provider in self.providers:
            try:
                return provider.chat(messages, tools)
            except AgentError as exc:
                errors.append(f"{provider.name}: {exc}")
        raise AgentError("模型服务暂时不可用：" + "；".join(errors))

    def web_search(
        self,
        query: str,
        count: int = 5,
        original_question: str = "",
    ) -> dict[str, Any]:
        errors = []
        for provider in self.providers:
            method = getattr(provider, "web_search", None)
            if not callable(method):
                continue
            try:
                return method(query, count, original_question)
            except AgentError as exc:
                errors.append(f"{provider.name}: {exc}")
        if errors:
            raise AgentError("网页搜索暂时不可用：" + "；".join(errors))
        raise AgentError("当前模型 Provider 不支持网页搜索。")

    def web_fetch(self, url: str) -> dict[str, Any]:
        errors = []
        for provider in self.providers:
            method = getattr(provider, "web_fetch", None)
            if not callable(method):
                continue
            try:
                return method(url)
            except AgentError as exc:
                errors.append(f"{provider.name}: {exc}")
        if errors:
            raise AgentError("网页抓取暂时不可用：" + "；".join(errors))
        raise AgentError("当前模型 Provider 不支持网页抓取。")


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Any] = {}

    def register(self, name: str, factory) -> None:
        key = str(name or "").strip().lower()
        if not key:
            raise ValueError("Provider 名称不能为空")
        self._factories[key] = factory

    def create(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
    ) -> LLMProvider:
        key = str(name or "").strip().lower()
        factory = self._factories.get(key)
        if not factory:
            raise AgentError(f"未知的模型 Provider：{key or '未配置'}")
        provider = factory(base_url, api_key, model)
        if not getattr(provider, "name", ""):
            provider.name = key
        return provider


def default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("deepseek", DeepSeekClient)
    registry.register(
        "openai-compatible",
        lambda base_url, api_key, model: OpenAICompatibleProvider(
            base_url,
            api_key,
            model,
            name="openai-compatible",
        ),
    )
    return registry
