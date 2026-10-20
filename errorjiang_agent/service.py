from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import mimetypes
from pathlib import Path
import random
import re
import sys
import threading
import time
import traceback
from typing import Any
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from .brain import AgentBrain
from .clients import DeepSeekClient, ErrorJClient, OneBotClient
from .config import Config
from .errors import AgentError
from .onebot import MessageEvent, event_key, parse_message_event
from .store import AgentStore


CONFIRM_RE = re.compile(r"^(?:确认|/confirm)\s+(\d{6})$", re.IGNORECASE)
BIND_RE = re.compile(r"^(?:绑定|/bind)\s+(\S+)$", re.IGNORECASE)
BIND_USER_RE = re.compile(r"^绑定用户\s+(\d{5,12})\s+(.+)$")
UNBIND_USER_RE = re.compile(r"^解绑用户\s+(\d{5,12})$")
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
            config.onebot_ws_url,
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
            self.prepare_sticker,
            max_tool_rounds=config.max_tool_rounds,
        )
        self.rate_limiter = RateLimiter()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")
        self._chat_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.sticker_dir = config.db_path.parent / "stickers"
        self.sticker_dir.mkdir(parents=True, exist_ok=True)
        self._proactive_stop = threading.Event()
        self._proactive_thread = threading.Thread(
            target=self._proactive_loop,
            daemon=True,
            name="agent-proactive",
        )
        for qq in config.admin_qqs:
            self.store.bind_admin("qq", str(qq))
        self._proactive_thread.start()

    def prepare_sticker(
        self,
        arguments: dict[str, Any],
        tool_context: dict[str, str] | None,
    ) -> dict[str, Any]:
        if not tool_context or tool_context.get("sticker_enabled") != "1":
            return {"status": "disabled"}
        owner_id = tool_context.get("owner_id") or ""
        settings = self.store.get_settings(tool_context.get("platform") or "qq", owner_id)
        if not settings.get("sticker_enabled", True):
            return {"status": "disabled"}
        emotion = str(arguments.get("emotion") or "").strip()[:30]
        stickers = self.store.list_stickers(owner_id, 200)
        matches = [
            item
            for item in stickers
            if emotion and emotion in str(item.get("tags") or "")
        ]
        candidates = matches or stickers
        if not candidates:
            return {"status": "empty"}
        sticker = random.choice(candidates)
        if tool_context is not None:
            tool_context["selected_sticker"] = str(sticker["id"])
        return {
            "status": "selected",
            "emotion": emotion,
            "message": "表情包会在文字回复后发送。",
        }

    def selected_sticker(self, tool_context: dict[str, str] | None):
        if not tool_context or not tool_context.get("selected_sticker"):
            return None
        try:
            sticker_id = int(tool_context["selected_sticker"])
        except (TypeError, ValueError):
            return None
        for sticker in self.store.list_stickers(
            tool_context.get("owner_id") or "", 200
        ):
            if int(sticker["id"]) == sticker_id:
                return sticker
        return None

    @staticmethod
    def sticker_segment(sticker: dict[str, Any] | None):
        if not sticker:
            return None
        if sticker.get("kind") == "face":
            return {
                "type": "face",
                "data": {"id": str(sticker.get("ref") or "")},
            }
        return {
            "type": "image",
            "data": {
                "file": (
                    "http://172.17.0.1:8011/stickers/"
                    + str(sticker.get("ref") or "")
                )
            },
        }

    def save_message_stickers(
        self,
        event: MessageEvent,
        payload: dict[str, Any],
    ) -> int:
        if event.message_type != "private":
            return 0
        if event.user_id not in self.config.admin_qqs and not self.store.is_admin(
            "qq", str(event.user_id)
        ):
            return 0
        saved = 0
        message = payload.get("message")
        if not isinstance(message, list):
            return 0
        for segment in message:
            if not isinstance(segment, dict):
                continue
            data = segment.get("data") or {}
            segment_type = segment.get("type")
            if segment_type == "face":
                face_id = str(data.get("id") or "").strip()
                if face_id.isdigit():
                    self.store.add_sticker(
                        str(event.user_id), "face", face_id, "qq表情"
                    )
                    saved += 1
                continue
            if segment_type != "image":
                continue
            source = str(data.get("url") or data.get("file") or "").strip()
            if not source.startswith(("http://", "https://")):
                continue
            try:
                request = Request(
                    source,
                    headers={"User-Agent": "ErrorJ-Agent-Sticker/1.0"},
                )
                with urlopen(request, timeout=20) as response:
                    raw = response.read(5 * 1024 * 1024 + 1)
            except Exception:
                continue
            if not raw or len(raw) > 5 * 1024 * 1024:
                continue
            mime = str(data.get("summary") or "")
            extension = mimetypes.guess_extension(mime or "") or ".gif"
            if raw[:6] in (b"GIF87a", b"GIF89a"):
                extension = ".gif"
            elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                extension = ".png"
            elif raw[:3] == b"\xff\xd8\xff":
                extension = ".jpg"
            else:
                continue
            digest = hashlib.sha256(raw).hexdigest()[:24]
            filename = digest + extension
            (self.sticker_dir / filename).write_bytes(raw)
            tags = "星星发送"
            summary = str(data.get("summary") or "").strip()
            if summary:
                tags += " " + summary[:100]
            self.store.add_sticker(str(event.user_id), "image", filename, tags)
            saved += 1
        return saved

    def remember_exchange(
        self,
        platform: str,
        owner_id: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        settings = self.store.get_settings(platform, owner_id)
        if not settings.get("memory_enabled", True):
            return
        try:
            message = self.deepseek.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "从一轮对话中提取值得长期记住的稳定信息。"
                            "只保留偏好、称呼、重要日期、长期项目、约定和关系事件。"
                            "不要保存临时查询、寒暄或无意义内容。"
                            "输出严格 JSON："
                            '{"memories":[{"content":"...","kind":"fact|preference|event|promise",'
                            '"importance":1}]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"星星：{user_text}\n折兮颜：{assistant_text}",
                    },
                ],
                [],
            )
            content = str(message.get("content") or "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
            data = json.loads(content)
            for item in (data.get("memories") or [])[:6]:
                if not isinstance(item, dict):
                    continue
                self.store.add_memory(
                    platform,
                    owner_id,
                    str(item.get("content") or ""),
                    str(item.get("kind") or "fact"),
                    int(item.get("importance") or 5),
                )
        except Exception:
            traceback.print_exc()

    def proactive_message(self, owner_id: str) -> str:
        memories = self.store.memory_context("qq", owner_id, "", 8)
        prompt = (
            "你是折兮颜，称呼用户为星星。请主动发一条简短自然的消息。"
            "冷脸萌、轻微傲娇，关心但不过度黏人。不要提这是系统定时任务。"
        )
        if memories:
            prompt += "\n你记得：" + "；".join(memories)
        message = self.deepseek.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "主动说一句话。"},
            ],
            [],
        )
        return str(message.get("content") or "").strip()[:500]

    @staticmethod
    def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
        try:
            start_time = datetime.strptime(start, "%H:%M").time()
            end_time = datetime.strptime(end, "%H:%M").time()
        except (TypeError, ValueError):
            return False
        current = now.time().replace(second=0, microsecond=0)
        if start_time <= end_time:
            return start_time <= current < end_time
        return current >= start_time or current < end_time

    def _proactive_loop(self) -> None:
        while not self._proactive_stop.wait(30):
            now = datetime.now()
            day = now.strftime("%Y-%m-%d")
            slot_time = now.strftime("%H:%M")
            owners = self.store.admin_ids("qq")
            for owner_id in owners:
                settings = self.store.get_settings("qq", owner_id)
                if not settings.get("proactive_enabled", True):
                    continue
                if self.in_quiet_hours(
                    now,
                    str(settings.get("quiet_start") or "23:30"),
                    str(settings.get("quiet_end") or "08:00"),
                ):
                    continue
                if self.store.proactive_count(day, owner_id) >= int(
                    settings.get("proactive_max_per_day", 2)
                ):
                    continue
                slot = None
                if slot_time == settings.get("morning_time"):
                    slot = "morning"
                elif slot_time == settings.get("night_time"):
                    slot = "night"
                if not slot:
                    continue
                if not self.store.claim_proactive_slot(day, slot, owner_id):
                    continue
                try:
                    text = self.proactive_message(owner_id)
                    if text:
                        self.onebot.send_private(int(owner_id), text)
                except Exception:
                    traceback.print_exc()

    def memory_settings(self, platform: str, owner_id: str) -> dict:
        return self.store.get_settings(platform, owner_id)

    def update_settings(
        self,
        platform: str,
        owner_id: str,
        values: dict[str, Any],
    ) -> dict:
        return self.store.save_settings(platform, owner_id, values)

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

    def send_reply(
        self,
        event: MessageEvent,
        text: str,
        sticker: dict[str, Any] | None = None,
    ) -> None:
        text = text.strip()
        if not text:
            text = "这次没有生成有效回答。"
        if len(text) > 3500:
            text = text[:3500] + "\n（内容较长，已截断）"
        segment = self.sticker_segment(sticker)
        message = text
        if segment:
            message = [
                {"type": "text", "data": {"text": text}},
                segment,
            ]
        if event.message_type == "group":
            self.onebot.send_group(event.chat_id, message)
        else:
            self.onebot.send_private(event.user_id, message)

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
        if event.message_type == "group" and event.chat_id not in self.config.group_ids:
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
        is_admin = event.user_id in self.config.admin_qqs or self.store.is_admin(
            "qq", str(event.user_id)
        )
        if is_admin:
            bind_user_match = BIND_USER_RE.fullmatch(event.text.strip())
            if bind_user_match:
                qq_id, site_ref = bind_user_match.groups()
                site_ref = site_ref.strip()
                if site_ref.isdigit():
                    site_user_id = int(site_ref)
                    site_name = f"用户 #{site_user_id}"
                else:
                    try:
                        resolved = self.errorjiang.tool(
                            "users.resolve", {"query": site_ref}
                        )
                    except AgentError as exc:
                        self.send_reply(event, f"账号解析失败：{exc}")
                        return
                    users = resolved.get("users") or []
                    if not users:
                        self.send_reply(event, f"没有找到已认证用户“{site_ref}”。")
                        return
                    if len(users) > 1:
                        names = [
                            f"#{item['id']} {item.get('nickname') or item['username']}"
                            for item in users
                        ]
                        self.send_reply(
                            event,
                            "找到多个同名账号，请改用用户编号：\n"
                            + "\n".join(names),
                        )
                        return
                    site_user_id = int(users[0]["id"])
                    site_name = (
                        users[0].get("nickname")
                        or users[0].get("username")
                        or f"用户 #{site_user_id}"
                    )
                self.store.bind_user("qq", qq_id, site_user_id)
                self.send_reply(
                    event,
                    f"已将 QQ {qq_id} 绑定到 {site_name}（#{site_user_id}）。",
                )
                return
            unbind_user_match = UNBIND_USER_RE.fullmatch(event.text.strip())
            if unbind_user_match:
                qq_id = unbind_user_match.group(1)
                removed = self.store.unbind_user("qq", qq_id)
                self.send_reply(
                    event,
                    f"已解绑 QQ {qq_id}。" if removed else "这个 QQ 尚未绑定。",
                )
                return
            if event.text.strip() in ("绑定列表", "/bindings"):
                links = self.store.list_identities("qq")
                if not links:
                    self.send_reply(event, "目前没有普通用户 QQ 绑定。")
                else:
                    self.send_reply(
                        event,
                        "普通用户绑定：\n"
                        + "\n".join(
                            f"QQ {item['owner_id']} → 用户 #{item['user_id']}"
                            for item in links
                        ),
                    )
                return
        linked_user_id = self.store.linked_user_id("qq", str(event.user_id))
        if not is_admin and linked_user_id is None:
            hint = (
                f"当前 QQ 尚未绑定。请让管理员发送：绑定用户 {event.user_id} 用户编号"
                if event.message_type == "private"
                else "这个 QQ 尚未绑定 Error酱账号。"
            )
            self.send_reply(event, hint)
            return
        if not is_admin and event.message_type == "private":
            self.send_reply(
                event,
                "普通用户请在授权群里 @折兮颜 使用。主 QQ 私聊仅限管理员。",
            )
            return
        target_user_id = 0 if is_admin else int(linked_user_id)
        if not self.rate_limiter.allow(str(event.user_id)):
            self.send_reply(event, "请求太频繁，请稍后再试。")
            return
        saved_stickers = self.save_message_stickers(event, payload)
        chat_lock = self._chat_locks[event.owner_id]
        with chat_lock:
            self._process_event(
                event,
                saved_stickers,
                target_user_id=target_user_id,
                is_admin=is_admin,
            )

    def _process_event(
        self,
        event: MessageEvent,
        saved_stickers: int = 0,
        target_user_id: int = 0,
        is_admin: bool = True,
    ) -> None:
        text = event.text.strip()
        if not text:
            self.send_reply(
                event,
                "表情我收下了。你直接说想问什么就行。"
                if saved_stickers
                else "请直接告诉我你想查询什么。",
            )
            return
        if text.lower() in ("/reset", "重置对话", "清空上下文"):
            self.store.clear_messages("qq", str(event.user_id))
            self.send_reply(event, "对话上下文已清空。")
            return
        if text.lower() in ("/help", "帮助"):
            self.send_reply(
                event,
                "可以问我：元件库存、收藏网站链接、笔记内容、待审核列表。"
                "也可以查询计算器账目和记录费用。"
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
        settings = self.store.get_settings("qq", str(event.user_id))
        memories = (
            self.store.memory_context("qq", str(event.user_id), text, 10)
            if settings.get("memory_enabled", True)
            else []
        )
        self.store.add_message("qq", str(event.user_id), "user", text)
        context = {
            "platform": "qq",
            "owner_id": str(event.user_id),
            "chat_id": str(event.chat_id),
            "is_admin": "1" if is_admin else "0",
            "sticker_enabled": (
                "1" if settings.get("sticker_enabled", True) else "0"
            ),
        }
        errorjiang = ErrorJClient(
            self.config.errorjiang_base_url,
            self.config.errorjiang_token,
            target_user_id,
        )
        brain = AgentBrain(
            self.deepseek,
            errorjiang,
            self.prepare_review,
            self.prepare_sticker,
            max_tool_rounds=self.config.max_tool_rounds,
        )
        try:
            reply = brain.reply(
                text,
                history,
                context,
                memories=memories,
            )
        except AgentError as exc:
            self.send_reply(event, f"查询失败：{exc}")
            return
        except Exception:
            self.send_reply(event, "处理消息时发生内部错误，请稍后重试。")
            return
        self.store.add_message("qq", str(event.user_id), "assistant", reply)
        self.send_reply(event, reply, self.selected_sticker(context))
        self.executor.submit(
            self.remember_exchange,
            "qq",
            str(event.user_id),
            text,
            reply,
        )

    def schedule_event(self, payload: dict[str, Any]) -> None:
        future = self.executor.submit(self.handle_event, payload)
        future.add_done_callback(self._event_done)

    @staticmethod
    def _event_done(future) -> None:
        error = future.exception()
        if error:
            traceback.print_exception(
                type(error),
                error,
                error.__traceback__,
                file=sys.stderr,
            )

    def send_notification(self, payload: dict[str, Any]) -> None:
        event = str(payload.get("event") or "").strip()
        title = str(payload.get("title") or "Error酱通知").strip()
        body = str(payload.get("body") or "").strip()
        link = str(payload.get("link") or "").strip()
        text = title + (f"\n{body}" if body else "")
        if link:
            text += f"\n{link}"
        group_events = {"message", "moment", "moment_comment", "place"}
        if event in group_events and self.config.group_enabled:
            for group_id in self.config.group_ids:
                self.onebot.send_group(group_id, text)
            return
        for owner_id in self.store.admin_ids("qq"):
            try:
                self.onebot.send_private(int(owner_id), text)
            except (ValueError, AgentError):
                continue

    def web_chat(self, user_id: int, text: str) -> str:
        owner = f"web:{int(user_id)}"
        history = self.store.get_messages(
            "web",
            owner,
            self.config.context_messages,
        )
        settings = self.store.get_settings("web", str(user_id))
        memories = (
            self.store.memory_context("web", str(user_id), text, 10)
            if settings.get("memory_enabled", True)
            else []
        )
        self.store.add_message("web", owner, "user", text)
        errorjiang = ErrorJClient(
            self.config.errorjiang_base_url,
            self.config.errorjiang_token,
            int(user_id),
        )
        brain = AgentBrain(
            self.deepseek,
            errorjiang,
            self.prepare_review,
            None,
            max_tool_rounds=self.config.max_tool_rounds,
        )
        context = {
            "platform": "web",
            "owner_id": str(user_id),
            "chat_id": str(user_id),
            "is_admin": "1" if int(user_id) == self.config.admin_user_id else "0",
            "sticker_enabled": "0",
        }
        reply = brain.reply(
            text,
            history,
            context,
            memories=memories,
        )
        self.store.add_message("web", owner, "assistant", reply)
        self.executor.submit(
            self.remember_exchange,
            "web",
            str(user_id),
            text,
            reply,
        )
        return reply

    def close(self) -> None:
        self._proactive_stop.set()
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
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/health":
            self.send_json(200, {"ok": True})
            return
        if path == "/internal/status":
            if not self.internal_authorized():
                self.send_json(403, {"error": "forbidden"})
                return
            self.send_json(
                200,
                {
                    "ok": True,
                    "model": self.service.config.deepseek_model,
                    "group_enabled": self.service.config.group_enabled,
                    "group_ids": sorted(self.service.config.group_ids),
                    "bound_admins": len(self.service.store.admin_ids("qq")),
                },
            )
            return
        if path == "/internal/settings":
            if not self.internal_authorized():
                self.send_json(403, {"error": "forbidden"})
                return
            query = parse_qs(parsed.query)
            platform = str((query.get("platform") or ["web"])[0])
            owner_id = str((query.get("owner_id") or ["0"])[0])
            self.send_json(
                200,
                {"settings": self.service.memory_settings(platform, owner_id)},
            )
            return
        if path == "/internal/memories":
            if not self.internal_authorized():
                self.send_json(403, {"error": "forbidden"})
                return
            query = parse_qs(parsed.query)
            platform = str((query.get("platform") or ["web"])[0])
            owner_id = str((query.get("owner_id") or ["0"])[0])
            search = str((query.get("q") or [""])[0])
            self.send_json(
                200,
                {
                    "memories": self.service.store.list_memories(
                        platform, owner_id, search, 100
                    )
                },
            )
            return
        if path == "/internal/stickers":
            if not self.internal_authorized():
                self.send_json(403, {"error": "forbidden"})
                return
            query = parse_qs(parsed.query)
            owner_id = str((query.get("owner_id") or ["0"])[0])
            self.send_json(
                200,
                {"stickers": self.service.store.list_stickers(owner_id, 200)},
            )
            return
        if path.startswith("/stickers/"):
            filename = Path(path[len("/stickers/") :]).name
            target = self.service.sticker_dir / filename
            if not target.is_file():
                self.send_json(404, {"error": "not found"})
                return
            body = target.read_bytes()
            content_type = (
                mimetypes.guess_type(target.name)[0]
                or "application/octet-stream"
            )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json(404, {"error": "not found"})

    def read_json_body(self) -> dict[str, Any] | None:
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
                        return None
                    chunks.append(self.rfile.read(size))
                    self.rfile.read(2)
                raw = b"".join(chunks)
            else:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_WEBHOOK_BYTES:
                    self.send_json(413, {"error": "invalid body size"})
                    return None
                raw = self.rfile.read(length)
        except (ValueError, OSError):
            self.send_json(400, {"error": "invalid request body"})
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "invalid json"})
            return None
        if not isinstance(payload, dict):
            self.send_json(400, {"error": "invalid event"})
            return None
        return payload

    def internal_authorized(self) -> bool:
        supplied = str(self.headers.get("X-ErrorJ-Agent-Token") or "")
        expected = self.service.config.errorjiang_token
        return bool(
            supplied
            and expected
            and hmac.compare_digest(supplied, expected)
        )

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in (
            "/internal/notify",
            "/internal/web-chat",
            "/internal/settings",
            "/internal/memory/delete",
            "/internal/sticker/delete",
        ):
            if not self.internal_authorized():
                self.send_json(403, {"error": "forbidden"})
                return
            payload = self.read_json_body()
            if payload is None:
                return
            if parsed.path == "/internal/notify":
                self.service.executor.submit(self.service.send_notification, payload)
                self.send_json(200, {"ok": True})
                return
            if parsed.path == "/internal/settings":
                platform = str(payload.get("platform") or "web")
                owner_id = str(payload.get("owner_id") or "0")
                values = payload.get("settings")
                if not isinstance(values, dict):
                    self.send_json(400, {"error": "invalid settings"})
                    return
                settings = self.service.update_settings(
                    platform, owner_id, values
                )
                self.send_json(200, {"settings": settings})
                return
            if parsed.path == "/internal/memory/delete":
                platform = str(payload.get("platform") or "web")
                owner_id = str(payload.get("owner_id") or "0")
                try:
                    memory_id = int(payload.get("id"))
                except (TypeError, ValueError):
                    self.send_json(400, {"error": "invalid memory"})
                    return
                deleted = self.service.store.delete_memory(
                    platform, owner_id, memory_id
                )
                self.send_json(200, {"ok": deleted})
                return
            if parsed.path == "/internal/sticker/delete":
                owner_id = str(payload.get("owner_id") or "0")
                try:
                    sticker_id = int(payload.get("id"))
                except (TypeError, ValueError):
                    self.send_json(400, {"error": "invalid sticker"})
                    return
                sticker = self.service.store.delete_sticker(owner_id, sticker_id)
                if sticker and sticker.get("kind") == "image":
                    try:
                        (self.service.sticker_dir / sticker["ref"]).unlink()
                    except OSError:
                        pass
                self.send_json(200, {"ok": bool(sticker)})
                return
            try:
                user_id = int(payload.get("user_id"))
            except (TypeError, ValueError):
                self.send_json(400, {"error": "invalid user"})
                return
            text = str(payload.get("message") or "").strip()
            if user_id < 0 or not text or len(text) > 4000:
                self.send_json(400, {"error": "invalid message"})
                return
            if not self.service.rate_limiter.allow(f"web:{user_id}"):
                self.send_json(429, {"error": "请求太频繁，请稍后再试。"})
                return
            try:
                reply = self.service.web_chat(user_id, text)
            except AgentError as exc:
                self.send_json(502, {"error": str(exc)})
                return
            except Exception:
                traceback.print_exc()
                self.send_json(500, {"error": "Agent 处理失败。"})
                return
            self.send_json(200, {"reply": reply})
            return
        prefix = "/onebot/event/"
        if not parsed.path.startswith(prefix):
            self.send_json(404, {"error": "not found"})
            return
        supplied = parsed.path[len(prefix) :]
        expected = self.service.config.onebot_webhook_secret
        if not supplied or not hmac.compare_digest(supplied, expected):
            self.send_json(403, {"error": "forbidden"})
            return
        payload = self.read_json_body()
        if payload is None:
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
