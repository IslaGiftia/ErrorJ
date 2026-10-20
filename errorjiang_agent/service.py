from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from .brain import AgentBrain
from .clients import AgentError, DeepSeekClient, ErrorJClient, OneBotClient
from .config import Config
from .onebot import MessageEvent, event_key, parse_message_event
from .store import AgentStore


CONFIRM_RE = re.compile(r"^(?:确认|/confirm)\s+(\d{6})$", re.IGNORECASE)
BIND_RE = re.compile(r"^(?:绑定|/bind)\s+(\S+)$", re.IGNORECASE)
MAX_WEBHOOK_BYTES = 8 * 1024 * 1024


class RateLimiter:
    def __init__(self, limit: int = 20, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < now - self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


class AgentService:
    def __init__(self, config: Config):
        config.validate()
        self.config = config
        self.store = AgentStore(config.db_path)
        self.onebot = OneBotClient(
            config.onebot_api_base,
            config.onebot_access_token,
        )
        self.deepseek = DeepSeekClient(
            config.deepseek_base_url,
            config.deepseek_api_key,
            config.deepseek_model,
        )
        self.errorjiang = ErrorJClient(
            config.errorjiang_base_url,
            config.errorjiang_token,
            config.admin_user_id,
        )
        self.brain = AgentBrain(
            self.deepseek,
            self.errorjiang,
            self.prepare_review,
            max_tool_rounds=config.max_tool_rounds,
        )
        self.rate_limiter = RateLimiter()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")
        self._chat_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        for qq in config.admin_qqs:
            self.store.bind_admin("qq", str(qq))

    def prepare_review(
        self,
        arguments: dict[str, Any],
        tool_context: dict[str, str] | None,
    ) -> dict[str, Any]:
        if not tool_context:
            raise AgentError("审核上下文缺失。")
        if tool_context.get("is_admin") != "1":
            raise AgentError("当前会话没有审核权限。")
        kind = str(arguments.get("kind") or "").strip()
        action = str(arguments.get("action") or "").strip()
        note = str(arguments.get("note") or "").strip()[:500]
        try:
            item_id = int(arguments.get("id"))
        except (TypeError, ValueError):
            raise AgentError("审核记录编号不正确。") from None
        if kind not in ("user", "message", "report"):
            raise AgentError("审核类型不正确。")
        allowed_actions = {
            "user": {"approve", "reject"},
            "message": {"approve", "reject"},
            "report": {"resolve", "dismiss"},
        }
        if action not in allowed_actions[kind]:
            raise AgentError("审核动作不正确。")
        # The service only accepts admin QQ accounts, so this action is stored
        # under the bound ErrorJ admin identity.
        code, expires_at = self.store.create_pending(
            tool_context.get("platform") or "qq",
            tool_context.get("owner_id") or "",
            tool_context.get("chat_id") or "",
            {"kind": kind, "id": item_id, "action": action, "note": note},
        )
        return {
            "status": "pending_confirmation",
            "code": code,
            "expires_at": expires_at,
            "message": f"请回复“确认 {code}”，两分钟内有效。",
        }

    def send_reply(self, event: MessageEvent, text: str) -> None:
        text = text.strip()
        if not text:
            text = "这次没有生成有效回答。"
        if len(text) > 3500:
            text = text[:3500] + "\n（内容较长，已截断）"
        if event.message_type == "group":
            self.onebot.send_group(event.chat_id, text)
        else:
            self.onebot.send_private(event.user_id, text)

    def confirm_pending(self, event: MessageEvent, code: str) -> str | None:
        action = self.store.consume_pending(
            "qq",
            str(event.user_id),
            str(event.chat_id),
            code,
        )
        if not action:
            return None
        result = self.errorjiang.tool("reviews.decide", action)
        kind = action.get("kind")
        action_name = action.get("action")
        item_id = action.get("id")
        labels = {
            ("user", "approve"): "已通过用户",
            ("user", "reject"): "已驳回用户",
            ("message", "approve"): "已通过留言",
            ("message", "reject"): "已驳回留言",
            ("report", "resolve"): "已处理举报",
            ("report", "dismiss"): "已忽略举报",
        }
        return f"{labels.get((kind, action_name), '审核已完成')} #{item_id}。{result.get('ok') and ''}".strip()

    def handle_event(self, payload: dict[str, Any]) -> None:
        event = parse_message_event(payload)
        if not event:
            return
        if self.store.seen_event(event_key(event)):
            return
        if event.message_type == "group" and not self.config.group_enabled:
            return
        if event.message_type == "group" and not event.to_me:
            return
        bind_match = BIND_RE.fullmatch(event.text.strip())
        if (
            bind_match
            and event.message_type == "private"
            and self.config.bind_code
            and not self.store.has_admins()
            and hmac.compare_digest(bind_match.group(1), self.config.bind_code)
        ):
            self.store.bind_admin("qq", str(event.user_id))
            self.send_reply(
                event,
                "主 QQ 已绑定为 ErrorJ Agent 管理员。现在可以查询库存、链接、笔记和审核队列。",
            )
            return
        if event.user_id not in self.config.admin_qqs and not self.store.is_admin(
            "qq", str(event.user_id)
        ):
            if event.message_type == "private":
                hint = (
                    f"当前 QQ 尚未绑定。请发送：绑定 {self.config.bind_code}"
                    if self.config.bind_code and not self.store.has_admins()
                    else "当前 QQ 尚未绑定 Error酱管理员身份。"
                )
                self.send_reply(event, hint)
            return
        if not self.rate_limiter.allow(str(event.user_id)):
            self.send_reply(event, "请求太频繁，请稍后再试。")
            return
        chat_lock = self._chat_locks[event.owner_id]
        with chat_lock:
            self._process_event(event)

    def _process_event(self, event: MessageEvent) -> None:
        text = event.text.strip()
        if not text:
            self.send_reply(event, "请直接告诉我你想查询什么。")
            return
        if text.lower() in ("/reset", "重置对话", "清空上下文"):
            self.store.clear_messages("qq", str(event.user_id))
            self.send_reply(event, "对话上下文已清空。")
            return
        if text.lower() in ("/help", "帮助"):
            self.send_reply(
                event,
                "可以问我：元件库存、收藏网站链接、笔记内容、待审核列表。"
                "审核操作需要回复“确认 123456”。发送“重置对话”可清空上下文。",
            )
            return
        confirm_match = CONFIRM_RE.fullmatch(text)
        if confirm_match:
            try:
                reply = self.confirm_pending(event, confirm_match.group(1))
            except AgentError as exc:
                self.send_reply(event, f"审核执行失败：{exc}")
                return
            self.send_reply(
                event,
                reply or "确认码无效、已过期或不属于当前聊天。",
            )
            return
        history = self.store.get_messages(
            "qq",
            str(event.user_id),
            self.config.context_messages,
        )
        self.store.add_message("qq", str(event.user_id), "user", text)
        try:
            reply = self.brain.reply(
                text,
                history,
                {
                    "platform": "qq",
                    "owner_id": str(event.user_id),
                    "chat_id": str(event.chat_id),
                    "is_admin": "1",
                },
            )
        except AgentError as exc:
            self.send_reply(event, f"查询失败：{exc}")
            return
        except Exception:
            self.send_reply(event, "处理消息时发生内部错误，请稍后重试。")
            return
        self.store.add_message("qq", str(event.user_id), "assistant", reply)
        self.send_reply(event, reply)

    def schedule_event(self, payload: dict[str, Any]) -> None:
        self.executor.submit(self.handle_event, payload)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


class AgentHttpHandler(BaseHTTPRequestHandler):
    server_version = "ErrorJAgent/1.0"

    @property
    def service(self) -> AgentService:
        return self.server.agent_service

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_json(200, {"ok": True})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        prefix = "/onebot/event/"
        if not parsed.path.startswith(prefix):
            self.send_json(404, {"error": "not found"})
            return
        supplied = parsed.path[len(prefix) :]
        expected = self.service.config.onebot_webhook_secret
        if not supplied or not hmac.compare_digest(supplied, expected):
            self.send_json(403, {"error": "forbidden"})
            return
        transfer_encoding = str(
            self.headers.get("Transfer-Encoding") or ""
        ).lower()
        try:
            if "chunked" in transfer_encoding:
                chunks = []
                total = 0
                while True:
                    line = self.rfile.readline(128).strip()
                    if not line:
                        continue
                    size = int(line.split(b";", 1)[0], 16)
                    if size == 0:
                        self.rfile.readline(8192)
                        break
                    total += size
                    if total > MAX_WEBHOOK_BYTES:
                        self.send_json(413, {"error": "invalid body size"})
                        return
                    chunks.append(self.rfile.read(size))
                    self.rfile.read(2)
                raw = b"".join(chunks)
            else:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_WEBHOOK_BYTES:
                    self.send_json(413, {"error": "invalid body size"})
                    return
                raw = self.rfile.read(length)
        except (ValueError, OSError):
            self.send_json(400, {"error": "invalid request body"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "invalid json"})
            return
        if not isinstance(payload, dict):
            self.send_json(400, {"error": "invalid event"})
            return
        self.service.schedule_event(payload)
        self.send_json(200, {"ok": True})


class AgentHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: AgentService):
        super().__init__(address, AgentHttpHandler)
        self.agent_service = service


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    try:
        config = Config.load(base_dir)
        service = AgentService(config)
    except Exception as exc:
        print(f"ErrorJ Agent 启动失败：{exc}", file=sys.stderr)
        return 1
    server = AgentHttpServer((config.host, config.port), service)
    print(
        f"ErrorJ Agent 已启动：http://{config.host}:{config.port} "
        f"(model={config.deepseek_model})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
