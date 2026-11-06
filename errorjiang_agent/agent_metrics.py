from __future__ import annotations

import time
from typing import Any, Callable

from .errors import AgentError


MetricCallback = Callable[[str, bool, int], None]


class MeteredProvider:
    def __init__(self, provider: Any, record: MetricCallback):
        self.provider = provider
        self.record = record
        self.name = str(getattr(provider, "name", "provider"))

    def _call(self, kind: str, method: Callable, *args, **kwargs):
        started = time.monotonic()
        success = False
        try:
            result = method(*args, **kwargs)
            success = True
            return result
        finally:
            elapsed = int((time.monotonic() - started) * 1000)
            try:
                self.record(kind, success, elapsed)
            except Exception:
                pass

    def chat(self, messages, tools):
        return self._call("llm", self.provider.chat, messages, tools)

    def web_search(self, query, count=5, original_question=""):
        method = getattr(self.provider, "web_search", None)
        if not callable(method):
            self.record("search", False, 0)
            raise AgentError("当前模型 Provider 不支持网页搜索。")
        return self._call(
            "search",
            method,
            query,
            count,
            original_question,
        )

    def web_fetch(self, url):
        method = getattr(self.provider, "web_fetch", None)
        if not callable(method):
            self.record("fetch", False, 0)
            raise AgentError("当前模型 Provider 不支持网页抓取。")
        return self._call("fetch", method, url)

    def __getattr__(self, name):
        return getattr(self.provider, name)


class MeteredHotSearch:
    def __init__(self, client: Any, record: MetricCallback):
        self.client = client
        self.record = record

    def fetch(self, source="all", limit=10):
        started = time.monotonic()
        success = False
        try:
            result = self.client.fetch(source, limit)
            success = True
            return result
        finally:
            elapsed = int((time.monotonic() - started) * 1000)
            try:
                self.record("hot_search", success, elapsed)
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.client, name)
