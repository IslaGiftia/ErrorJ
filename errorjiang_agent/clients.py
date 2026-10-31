from __future__ import annotations

from datetime import datetime
import json
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .errors import AgentError
from .onebot_ws import OneBotWebSocketClient


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
    }
    request_headers.update(headers or {})
    request = Request(
        url,
        data=body,
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
            message = data.get("error") or f"HTTP {exc.code}"
        except Exception:
            message = f"HTTP {exc.code}"
        raise AgentError(message) from exc
    except URLError as exc:
        raise AgentError(f"无法连接服务：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise AgentError("服务返回了无效 JSON。") from exc


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131 Safari/537.36"
        ),
    }
    request_headers.update(headers or {})
    request = Request(url, headers=request_headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            data = json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        raise AgentError(f"热搜接口返回 HTTP {exc.code}。") from exc
    except URLError as exc:
        raise AgentError(f"无法连接热搜接口：{exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentError("热搜接口返回了无效数据。") from exc
    return data if isinstance(data, dict) else {}


class ErrorJClient:
    def __init__(self, base_url: str, token: str, user_id: int):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.user_id = int(user_id)

    def tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return post_json(
            self.base_url + "/api/agent/tool",
            {"tool": name, "arguments": arguments},
            headers={
                "X-ErrorJ-Agent-Token": self.token,
                "X-ErrorJ-Agent-User": str(self.user_id),
            },
            timeout=40,
        )


class DeepSeekClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.name = "deepseek"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
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
            timeout=90,
        )
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0].get("message"), dict):
            raise AgentError("DeepSeek 没有返回有效消息。")
        return choices[0]["message"]

    def web_search(
        self,
        query: str,
        count: int = 5,
        original_question: str = "",
    ) -> dict[str, Any]:
        value = str(query or "").strip()[:128]
        if not value:
            raise AgentError("搜索词不能为空。")
        payload = {
            "query": value,
            "count": max(1, min(int(count), 10)),
            "need_content": False,
        }
        question = str(original_question or "").strip()[:128]
        if question:
            payload["ori_question"] = question
        data = post_json(
            self.base_url + "/tools/search",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=40,
        )
        results = []
        for item in (data.get("results") or [])[:10]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": str(item.get("title") or "")[:300],
                    "url": str(item.get("url") or "")[:2000],
                    "snippet": str(item.get("snippet") or "")[:800],
                    "summary": str(item.get("summary") or "")[:1600],
                    "site_name": str(item.get("site_name") or "")[:120],
                    "date": item.get("date"),
                    "authority": item.get("authority"),
                    "rerank_score": item.get("rerank_score"),
                }
            )
        return {
            "query": value,
            "untrusted": True,
            "results": results,
        }

    def web_fetch(self, url: str) -> dict[str, Any]:
        value = str(url or "").strip()[:8192]
        if not value.startswith(("http://", "https://")):
            raise AgentError("网页地址必须是 HTTP/HTTPS URL。")
        data = post_json(
            self.base_url + "/tools/fetch",
            {"url": value},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=50,
        )
        return {
            "url": value,
            "untrusted": True,
            "title": str(data.get("title") or "")[:500],
            "content": str(data.get("content") or "")[:20000],
        }


class HotSearchClient:
    SOURCE_LABELS = {
        "weibo": "微博热搜",
        "bilibili": "B站热搜",
        "douyin": "抖音热搜",
    }
    SOURCE_URLS = {
        "weibo": "https://weibo.com/ajax/side/hotSearch",
        "bilibili": (
            "https://api.bilibili.com/x/web-interface/search/square?limit=10"
        ),
        "douyin": (
            "https://www.douyin.com/aweme/v1/web/hot/search/list/?"
            "device_platform=webapp&aid=6383&channel=channel_pc_web"
            "&detail_list=1"
        ),
    }

    def __init__(self, cache_seconds: int = 120):
        self.cache_seconds = max(30, int(cache_seconds))
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def fetch(
        self,
        source: str = "all",
        limit: int = 10,
    ) -> dict[str, Any]:
        value = str(source or "all").strip().lower()
        sources = (
            list(self.SOURCE_LABELS)
            if value == "all"
            else [value]
        )
        if any(item not in self.SOURCE_LABELS for item in sources):
            raise AgentError("热搜来源只支持微博、B站、抖音或全部。")
        count = max(1, min(int(limit), 10))
        lists: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for item in sources:
            try:
                lists[item] = self._fetch_source(item, count)
            except AgentError as exc:
                errors[item] = str(exc)
        if not any(lists.values()):
            detail = "；".join(errors.values()) or "没有取得热搜内容。"
            raise AgentError(f"热搜查询失败：{detail}")
        return {
            "source": value,
            "untrusted": True,
            "fetched_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "lists": [
                {
                    "source": item,
                    "label": self.SOURCE_LABELS[item],
                    "items": lists.get(item) or [],
                }
                for item in sources
                if lists.get(item)
            ],
            "errors": [
                {"source": item, "message": message}
                for item, message in errors.items()
            ],
        }

    def _fetch_source(
        self,
        source: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        cache_key = f"{source}:{limit}"
        now = time.time()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < self.cache_seconds:
                return list(cached[1])
        headers = {
            "Referer": (
                "https://weibo.com/"
                if source == "weibo"
                else (
                    "https://www.bilibili.com/"
                    if source == "bilibili"
                    else "https://www.douyin.com/"
                )
            )
        }
        data = get_json(self.SOURCE_URLS[source], headers=headers)
        if source == "weibo":
            rows = (
                (data.get("data") or {}).get("realtime")
                if isinstance(data.get("data"), dict)
                else []
            ) or []
            items = self._weibo_items(rows, limit)
        elif source == "bilibili":
            payload = data.get("data") or {}
            trending = (
                payload.get("trending") or {}
                if isinstance(payload, dict)
                else {}
            )
            rows = trending.get("list") if isinstance(trending, dict) else []
            items = self._bilibili_items(rows or [], limit)
        else:
            payload = data.get("data") or {}
            rows = payload.get("word_list") if isinstance(payload, dict) else []
            items = self._douyin_items(rows or [], limit)
        if not items:
            raise AgentError(f"{self.SOURCE_LABELS[source]}没有返回可用内容。")
        with self._lock:
            self._cache[cache_key] = (now, items)
        return items

    @staticmethod
    def _weibo_items(rows: list[Any], limit: int) -> list[dict[str, Any]]:
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("word") or row.get("note") or "").strip()
            if not title:
                continue
            query = str(row.get("word_scheme") or f"#{title}#")
            items.append(
                {
                    "rank": int(row.get("realpos") or len(items) + 1),
                    "title": title[:120],
                    "heat": row.get("num"),
                    "label": str(row.get("label_name") or "")[:20],
                    "url": (
                        "https://s.weibo.com/weibo?q="
                        + quote_plus(query)
                    ),
                }
            )
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _bilibili_items(rows: list[Any], limit: int) -> list[dict[str, Any]]:
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(
                row.get("keyword") or row.get("show_name") or ""
            ).strip()
            if not title:
                continue
            items.append(
                {
                    "rank": len(items) + 1,
                    "title": title[:120],
                    "heat": row.get("heat_score"),
                    "url": (
                        "https://search.bilibili.com/all?keyword="
                        + quote_plus(title)
                    ),
                }
            )
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _douyin_items(rows: list[Any], limit: int) -> list[dict[str, Any]]:
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("word") or "").strip()
            if not title:
                continue
            items.append(
                {
                    "rank": int(row.get("position") or len(items) + 1),
                    "title": title[:120],
                    "heat": row.get("hot_value"),
                    "url": (
                        "https://www.douyin.com/search/"
                        + quote_plus(title)
                    ),
                }
            )
            if len(items) >= limit:
                break
        return items


class OneBotClient:
    def __init__(self, api_base: str, ws_url: str, access_token: str = ""):
        self.api_base = api_base.rstrip("/")
        self.ws_url = ws_url
        self.access_token = access_token
        self.ws = OneBotWebSocketClient(ws_url, access_token)

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    def send_private(self, user_id: int, message: str | list[dict[str, Any]]) -> None:
        self.ws.call("send_private_msg", {"user_id": int(user_id), "message": message})

    def send_group(self, group_id: int, message: str | list[dict[str, Any]]) -> None:
        self.ws.call("send_group_msg", {"group_id": int(group_id), "message": message})
