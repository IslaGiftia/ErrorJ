from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
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
