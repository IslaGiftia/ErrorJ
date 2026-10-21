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
from .qqbot import QQBotClient
from .store import AgentStore


CONFIRM_RE = re.compile(r"^(?:确认|/confirm)\s+(\d{6})$", re.IGNORECASE)
BIND_RE = re.compile(r"^(?:绑定|/bind)\s+(\S+)$", re.IGNORECASE)
BIND_USER_RE = re.compile(r"^绑定用户\s+(\d{5,12})\s+(.+)$")
UNBIND_USER_RE = re.compile(r"^解绑用户\s+(\d{5,12})$")
BIND_USER_ANY_RE = re.compile(r"^绑定用户\s+(\S{5,128})\s+(.+)$")
UNBIND_USER_ANY_RE = re.compile(r"^解绑用户\s+(\S{5,128})$")
MAX_WEBHOOK_BYTES = 8 * 1024 * 1024
PROACTIVE_GREETING_WINDOW_MINUTES = 25
PROACTIVE_MIN_GAP_SECONDS = 90 * 60
PROACTIVE_MEMORY_COOLDOWN_SECONDS = 3 * 86400
CHAT_SPLIT_RE = re.compile(r"\s*\[\[split\]\]\s*", re.IGNORECASE)


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
            self.prepare_reminder,
            max_tool_rounds=config.max_tool_rounds,
        )
        self.rate_limiter = RateLimiter()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")
        self.qqbot = (
            QQBotClient(
                config.qqbot_app_id,
                config.qqbot_app_secret,
                config.qqbot_bot_qq,
                self.schedule_qqbot_event,
            )
            if config.qqbot_enabled
            else None
        )
        self._chat_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.sticker_dir = config.db_path.parent / "stickers"
        self.sticker_dir.mkdir(parents=True, exist_ok=True)
        self._proactive_stop = threading.Event()
        self._proactive_thread = threading.Thread(
            target=self._proactive_loop,
            daemon=True,
            name="agent-proactive",
        )
        self._reminder_stop = threading.Event()
        self._reminder_thread = threading.Thread(
            target=self._reminder_loop,
            daemon=True,
            name="agent-reminders",
        )
        self._qqbot_thread = None
        if self.qqbot:
            self._qqbot_thread = threading.Thread(
                target=self.qqbot.run,
                daemon=True,
                name="agent-qqbot",
            )
        for qq in config.admin_qqs:
            self.store.bind_admin("qq", str(qq))
        for openid in config.qqbot_admin_openids:
            self.store.bind_admin("qqbot", openid)
        self._proactive_thread.start()
        self._reminder_thread.start()
        if self._qqbot_thread:
            self._qqbot_thread.start()

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

    def prepare_reminder(
        self,
        arguments: dict[str, Any],
        tool_context: dict[str, str] | None,
    ) -> dict[str, Any]:
        if not tool_context:
            raise AgentError("提醒上下文缺失。")
        text = str(arguments.get("text") or "").strip()[:300]
        if not text:
            raise AgentError("提醒内容不能为空。")
        try:
            delay_minutes = float(arguments.get("delay_minutes"))
        except (TypeError, ValueError):
            raise AgentError("提醒时间不正确。") from None
        if delay_minutes < 0.1 or delay_minutes > 7 * 24 * 60:
            raise AgentError("提醒时间需在 6 秒到 7 天之间。")
        due_at = int(time.time() + delay_minutes * 60)
        reminder_id = self.store.add_reminder(
            tool_context.get("platform") or "qq",
            tool_context.get("owner_id") or "",
            tool_context.get("chat_id") or "",
            tool_context.get("chat_type") or "private",
            text,
            due_at,
        )
        return {
            "status": "scheduled",
            "reminder_id": reminder_id,
            "due_at": due_at,
            "message": f"已安排在 {datetime.fromtimestamp(due_at):%H:%M} 提醒。",
        }

    def _reminder_loop(self) -> None:
        while not self._reminder_stop.wait(10):
            for reminder in self.store.due_reminders(int(time.time())):
                try:
                    text = self.reminder_delivery_text(reminder)
                    if reminder.get("chat_type") == "group":
                        message = [
                            {
                                "type": "at",
                                "data": {"qq": str(reminder["owner_id"])},
                            },
                            {"type": "text", "data": {"text": " " + text}},
                        ]
                        self.onebot.send_group(int(reminder["chat_id"]), message)
                    else:
                        self.onebot.send_private(int(reminder["owner_id"]), text)
                    self.store.mark_reminder_sent(int(reminder["id"]))
                except Exception:
                    traceback.print_exc()

    @staticmethod
    def reminder_delivery_text(reminder: dict[str, Any]) -> str:
        return str(reminder.get("text") or "").strip()

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
                            '"importance":1}],'
                            '"events":[{"title":"...","content":"...",'
                            '"event_type":"plan|promise|milestone|relationship|event",'
                            '"event_at":"YYYY-MM-DD HH:MM:SS or null",'
                            '"follow_up_at":"YYYY-MM-DD HH:MM:SS or null"}]}'
                            f"\n当前时间：{datetime.now():%Y-%m-%d %H:%M:%S}"
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
            for item in (data.get("events") or [])[:6]:
                if not isinstance(item, dict):
                    continue
                event_at = None
                follow_up_at = None
                try:
                    if item.get("event_at"):
                        event_at = int(
                            datetime.strptime(
                                str(item["event_at"]), "%Y-%m-%d %H:%M:%S"
                            ).timestamp()
                        )
                    if item.get("follow_up_at"):
                        follow_up_at = int(
                            datetime.strptime(
                                str(item["follow_up_at"]), "%Y-%m-%d %H:%M:%S"
                            ).timestamp()
                        )
                except ValueError:
                    pass
                title = " ".join(
                    str(item.get("title") or item.get("content") or "").split()
                ).strip()
                content = " ".join(
                    str(item.get("content") or title).split()
                ).strip()
                if not content:
                    continue
                self.store.add_timeline_event(
                    platform,
                    owner_id,
                    str(item.get("event_type") or "event"),
                    title or content,
                    content,
                    event_at,
                    follow_up_at,
                )
        except Exception:
            traceback.print_exc()

    def relationship_context(self, platform: str, owner_id: str) -> dict:
        state = self.store.get_relationship_state(platform, owner_id)
        last_user_at = int(state.get("last_user_at") or 0)
        idle_hours = (
            max(0.0, (time.time() - last_user_at) / 3600)
            if last_user_at
            else 0.0
        )
        longing = max(0, min(10, int(idle_hours / 6) + (1 if idle_hours >= 3 else 0)))
        return {
            **state,
            "idle_hours": round(idle_hours, 1),
            "longing": longing,
            "last_topic": self.store.last_user_topic(platform, owner_id),
        }

    def update_relationship_after_exchange(
        self,
        platform: str,
        owner_id: str,
        user_text: str,
    ) -> dict:
        state = self.relationship_context(platform, owner_id)
        text = str(user_text or "")
        jealousy = max(0, int(state.get("jealousy") or 0) - 1)
        if re.search(r"别的\s*(?:AI|ai|女生|女孩|机器人)|找别人|前任|不理你", text):
            jealousy = min(3, jealousy + 2)
        care = min(10, int(state.get("care") or 6) + 1)
        hour = datetime.now().hour
        energy = 9 if 8 <= hour < 23 else 4
        if jealousy >= 2:
            mood = "有点吃醋"
        elif hour >= 22:
            mood = "有点困但还在"
        elif re.search(r"想你|喜欢你|晚安|抱抱|亲亲", text):
            mood = "嘴硬但开心"
        else:
            mood = "平静"
        return self.store.update_relationship_state(
            platform,
            owner_id,
            {
                "mood": mood,
                "energy": energy,
                "care": care,
                "jealousy": jealousy,
                "last_topic": text[:120],
            },
        )

    def timeline_context(self, platform: str, owner_id: str) -> list[str]:
        rows = self.store.list_timeline_events(platform, owner_id, 20)
        lines = []
        for row in rows:
            if row.get("status") != "open":
                continue
            when = ""
            if row.get("follow_up_at"):
                when = f"（跟进时间 {datetime.fromtimestamp(row['follow_up_at']):%m-%d %H:%M}）"
            lines.append(f"{row.get('title')}{when}：{row.get('content')}")
            if len(lines) >= 8:
                break
        return lines

    @staticmethod
    def relationship_prompt(state: dict) -> str:
        mood = state.get("mood") or "平静"
        longing = int(state.get("longing") or 0)
        care = int(state.get("care") or 0)
        jealousy = int(state.get("jealousy") or 0)
        return (
            f"当前关系状态：心情{mood}，想念{longing}/10，在意{care}/10，"
            f"轻微吃醋{jealousy}/3，已 {state.get('idle_hours', 0)} 小时没联系。"
            "可以自然表达一点点想念或在意，但不要冷暴力、指责、索要关注或用情绪操纵星星。"
        )

    @staticmethod
    def proactive_time_near(now: datetime, target: str) -> bool:
        try:
            target_time = datetime.strptime(str(target), "%H:%M").time()
        except (TypeError, ValueError):
            return False
        current_minutes = now.hour * 60 + now.minute
        target_minutes = target_time.hour * 60 + target_time.minute
        distance = abs(current_minutes - target_minutes)
        distance = min(distance, 24 * 60 - distance)
        return distance <= PROACTIVE_GREETING_WINDOW_MINUTES

    @classmethod
    def proactive_candidates(
        cls,
        now: datetime,
        settings: dict,
        state: dict,
        due_events: list[dict],
        memories: list[dict],
    ) -> list[dict]:
        candidates = []
        for event in due_events[:5]:
            title = str(event.get("title") or "那件事").strip()
            content = str(event.get("content") or "").strip()
            topic = title if not content or content == title else f"{title}：{content}"
            candidates.append(
                {
                    "priority": 100,
                    "slot": f"timeline:{int(event['id'])}",
                    "kind": "timeline",
                    "reason": "时间线里有一件已经到期的约定或事件，先自然问问进展",
                    "topic": topic[:500],
                    "event_id": int(event["id"]),
                    "event_platform": str(event.get("platform") or "qq"),
                }
            )
        if cls.proactive_time_near(
            now, str(settings.get("morning_time") or "09:00")
        ):
            candidates.append(
                {
                    "priority": 80,
                    "slot": "morning",
                    "kind": "morning",
                    "reason": "早上这个时间很自然，可以随口问候星星",
                }
            )
        if cls.proactive_time_near(
            now, str(settings.get("night_time") or "21:30")
        ):
            candidates.append(
                {
                    "priority": 82,
                    "slot": "night",
                    "kind": "night",
                    "reason": "晚上这个时间很自然，可以问问星星今天怎么样",
                }
            )

        idle_hours = float(state.get("idle_hours") or 0)
        last_topic = " ".join(str(state.get("last_topic") or "").split()).strip()
        reusable_topic = bool(
            len(last_topic) >= 2
            and not re.match(r"^(?:/|绑定|解绑|确认|帮助|重置)", last_topic)
        )
        if reusable_topic and idle_hours >= 6:
            candidates.append(
                {
                    "priority": 72,
                    "slot": "missing",
                    "kind": "missing",
                    "reason": "已经有一段时间没联系，可以自然地提一下最近聊过的事",
                    "topic": last_topic[:300],
                }
            )
        elif reusable_topic and idle_hours >= 3:
            candidates.append(
                {
                    "priority": 48,
                    "slot": "reopen",
                    "kind": "reopen",
                    "reason": "隔了几个小时，可以顺着最近的话题自然接着聊",
                    "topic": last_topic[:300],
                }
            )

        if now.hour >= 17:
            cutoff = int(now.timestamp()) - PROACTIVE_MEMORY_COOLDOWN_SECONDS
            for memory in memories[:12]:
                if str(memory.get("kind") or "") not in ("promise", "event"):
                    continue
                last_used_at = int(memory.get("last_used_at") or 0)
                if last_used_at and last_used_at > cutoff:
                    continue
                content = str(memory.get("content") or "").strip()
                if not content:
                    continue
                candidates.append(
                    {
                        "priority": 60,
                        "slot": f"memory:{int(memory['id'])}",
                        "kind": "memory",
                        "reason": "晚上适合跟进以前记住的约定或事件",
                        "topic": content[:300],
                        "memory_id": int(memory["id"]),
                        "memory_platform": str(
                            memory.get("platform") or "qq"
                        ),
                    }
                )
        return candidates

    @staticmethod
    def choose_proactive_candidate(candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        highest = max(int(item.get("priority") or 0) for item in candidates)
        shortlist = [
            item
            for item in candidates
            if int(item.get("priority") or 0) == highest
        ]
        return random.choice(shortlist)

    def proactive_message(
        self,
        owner_id: str,
        reason: str,
        state: dict,
        topic: str = "",
        memories: list[str] | None = None,
    ) -> str:
        memory_lines = (
            list(memories or [])
            if memories is not None
            else self.store.memory_context("qq", owner_id, "", 8)
        )
        prompt = (
            "你是折兮颜，称呼用户为星星。请主动发一条简短自然的消息。"
            "冷脸萌、轻微傲娇，关心但不过度黏人。只发一到两句，"
            "不要分点、不要空行、闲聊句末通常不加句号，"
            "问号和感叹号按语气保留，不要提这是系统定时任务。"
            "不要假装刚看到消息，也不要用质问或冷暴力的语气。"
            f"\n主动原因：{reason}。"
            f"\n{self.relationship_prompt(state)}"
        )
        if topic:
            prompt += f"\n可以自然带到的话题：{topic}。"
        last_topic = str(state.get("last_topic") or "").strip()
        if last_topic and last_topic != topic:
            prompt += f"\n最近一次聊到：{last_topic[:200]}。"
        if memory_lines:
            prompt += "\n你记得：" + "；".join(memory_lines[:8])
        message = self.deepseek.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "主动说一句话。"},
            ],
            [],
        )
        return " ".join(
            self.chat_bubbles(str(message.get("content") or ""))
        )[:500]

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
            now_timestamp = int(now.timestamp())
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
                last_sent_at = self.store.last_proactive_at(owner_id)
                if (
                    last_sent_at
                    and now_timestamp - last_sent_at < PROACTIVE_MIN_GAP_SECONDS
                ):
                    continue
                state = self.relationship_context("qq", owner_id)
                qq_due_events = self.store.due_timeline_events(
                    now_timestamp,
                    limit=5,
                    platform="qq",
                    owner_id=owner_id,
                )
                web_due_events = self.store.due_timeline_events(
                    now_timestamp,
                    limit=5,
                    platform="web",
                    owner_id="0",
                )
                due_events = []
                seen_events = set()
                for item in qq_due_events + web_due_events:
                    key = (
                        str(item.get("title") or ""),
                        str(item.get("content") or ""),
                    )
                    if key in seen_events:
                        continue
                    seen_events.add(key)
                    due_events.append(item)
                memory_rows = []
                seen_memories = set()
                for item in (
                    self.store.list_memories("qq", owner_id, limit=20)
                    + self.store.list_memories("web", "0", limit=20)
                ):
                    content = str(item.get("content") or "")
                    if not content or content in seen_memories:
                        continue
                    seen_memories.add(content)
                    memory_rows.append(item)
                candidates = self.proactive_candidates(
                    now,
                    settings,
                    state,
                    due_events,
                    memory_rows,
                )
                candidate = self.choose_proactive_candidate(candidates)
                if not candidate or not self.store.claim_proactive_slot(
                    day, str(candidate["slot"]), owner_id
                ):
                    continue
                try:
                    text = self.proactive_message(
                        owner_id,
                        str(candidate["reason"]),
                        state,
                        topic=str(candidate.get("topic") or ""),
                        memories=[
                            str(item.get("content") or "")
                            for item in memory_rows[:8]
                            if item.get("content")
                        ],
                    )
                    if text:
                        self.onebot.send_private(int(owner_id), text)
                        self.store.add_message("qq", owner_id, "assistant", text)
                        if candidate.get("event_id"):
                            self.store.mark_timeline_used(
                                int(candidate["event_id"])
                            )
                        if candidate.get("memory_id"):
                            self.store.mark_memory_used(
                                str(candidate.get("memory_platform") or "qq"),
                                owner_id
                                if candidate.get("memory_platform") != "web"
                                else "0",
                                int(candidate["memory_id"]),
                            )
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

    @staticmethod
    def humanize_text(text: str, strip_terminal_period: bool = False) -> str:
        value = str(text or "").replace("**", "").replace("__", "")
        value = re.sub(r"^#{1,6}\s*", "", value, flags=re.MULTILINE)
        value = re.sub(r"\n{2,}", "\n", value).strip()
        structured = bool(
            re.search(
                r"(^|\n)\s*(?:[-*]|\d+[.、])\s+|https?://|```",
                value,
                flags=re.MULTILINE,
            )
        )
        if not structured:
            value = re.sub(r"\s*\n\s*", " ", value)
            value = re.sub(r"[ \t]{2,}", " ", value)
            if strip_terminal_period:
                value = re.sub(r"[。｡]([”’」』】）)]*)$", r"\1", value)
        return value.strip()

    @classmethod
    def chat_bubbles(cls, text: str) -> list[str]:
        parts = CHAT_SPLIT_RE.split(str(text or ""))
        bubbles = []
        for part in parts:
            value = cls.humanize_text(
                part,
                strip_terminal_period=True,
            )[:500]
            if value:
                bubbles.append(value)
        if len(bubbles) > 3:
            bubbles = bubbles[:2] + [" ".join(bubbles[2:])[:500]]
        return bubbles or [""]

    def send_reply(
        self,
        event: MessageEvent,
        text: str,
        sticker: dict[str, Any] | None = None,
        bubbles: list[str] | None = None,
    ) -> None:
        chunks = bubbles if bubbles is not None else [text]
        chunks = [chunk for chunk in chunks if chunk]
        if not chunks:
            chunks = ["这次没有生成有效回答。"]
        for index, chunk in enumerate(chunks):
            if not bubbles:
                chunk = self.humanize_text(chunk)
            if len(chunk) > 3500:
                chunk = chunk[:3500] + "\n（内容较长，已截断）"
            segment = self.sticker_segment(sticker) if index == len(chunks) - 1 else None
            message = chunk
            if segment:
                message = [
                    {"type": "text", "data": {"text": chunk}},
                    segment,
                ]
            delay = min(1.8, max(0.45, len(chunk) * 0.018))
            time.sleep(delay + random.uniform(0, 0.35))
            if event.platform == "qqbot" and self.qqbot:
                self.qqbot.send_message(
                    event.message_type,
                    str(event.chat_id),
                    str(event.message_id),
                    chunk,
                )
            elif event.message_type == "group":
                self.onebot.send_group(event.chat_id, message)
            else:
                self.onebot.send_private(event.user_id, message)
            if index < len(chunks) - 1:
                time.sleep(random.uniform(0.35, 0.8))

    def confirm_pending(self, event: MessageEvent, code: str) -> str | None:
        action = self.store.consume_pending(
            event.platform,
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
        self._handle_message_event(event, payload)

    def schedule_qqbot_event(self, event: MessageEvent) -> None:
        print(
            f"[QQBot] 接收 {event.message_type} "
            f"user={event.user_id} chat={event.chat_id}",
            flush=True,
        )
        future = self.executor.submit(self._handle_message_event, event, None, 0)
        future.add_done_callback(self._event_done)

    def _handle_message_event(
        self,
        event: MessageEvent,
        payload: dict[str, Any] | None = None,
        saved_stickers: int = 0,
    ) -> None:
        platform = event.platform
        if self.store.seen_event(event_key(event)):
            return
        if event.message_type == "group":
            if platform == "qq" and not self.config.group_enabled:
                return
            if (
                platform == "qq"
                and event.chat_id not in self.config.group_ids
            ):
                return
            if (
                platform == "qqbot"
                and self.config.qqbot_group_ids
                and str(event.chat_id) not in self.config.qqbot_group_ids
            ):
                return
        if event.message_type == "group" and not event.to_me:
            return
        if (
            platform == "qqbot"
            and event.message_type == "private"
            and self.config.qqbot_auto_bind_first_admin
            and not self.store.has_admins("qqbot")
        ):
            self.store.bind_admin("qqbot", str(event.user_id))
            self.send_reply(
                event,
                "主账号已绑定为折兮颜管理员。现在可以直接聊天",
            )
            return
        bind_match = BIND_RE.fullmatch(event.text.strip())
        if (
            bind_match
            and event.message_type == "private"
            and self.config.bind_code
            and not self.store.has_admins(platform)
            and hmac.compare_digest(bind_match.group(1), self.config.bind_code)
        ):
            self.store.bind_admin(platform, str(event.user_id))
            self.send_reply(
                event,
                "主账号已绑定为 ErrorJ Agent 管理员。现在可以查询库存、链接、笔记和审核队列。",
            )
            return
        is_admin = (
            platform == "qq" and event.user_id in self.config.admin_qqs
        ) or self.store.is_admin(
            platform, str(event.user_id)
        )
        if is_admin:
            bind_user_match = (
                BIND_USER_ANY_RE
                if platform == "qqbot"
                else BIND_USER_RE
            ).fullmatch(event.text.strip())
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
                self.store.bind_user(platform, qq_id, site_user_id)
                self.send_reply(
                    event,
                    f"已将账号 {qq_id} 绑定到 {site_name}（#{site_user_id}）。",
                )
                return
            unbind_user_match = (
                UNBIND_USER_ANY_RE
                if platform == "qqbot"
                else UNBIND_USER_RE
            ).fullmatch(event.text.strip())
            if unbind_user_match:
                qq_id = unbind_user_match.group(1)
                removed = self.store.unbind_user(platform, qq_id)
                self.send_reply(
                    event,
                    f"已解绑账号 {qq_id}。"
                    if removed
                    else "这个账号尚未绑定。",
                )
                return
            if event.text.strip() in ("绑定列表", "/bindings"):
                links = self.store.list_identities(platform)
                if not links:
                    self.send_reply(event, "目前没有普通用户绑定。")
                else:
                    self.send_reply(
                        event,
                        "普通用户绑定：\n"
                        + "\n".join(
                            f"{item['owner_id']} → 用户 #{item['user_id']}"
                            for item in links
                        ),
                    )
                return
        linked_user_id = self.store.linked_user_id(
            platform, str(event.user_id)
        )
        if not is_admin and linked_user_id is None:
            hint = (
                f"当前账号尚未绑定。请让管理员发送：绑定用户 {event.user_id} 用户编号"
                if event.message_type == "private"
                else "这个账号尚未绑定 Error酱账号。"
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
        if platform == "qq" and payload:
            saved_stickers = self.save_message_stickers(event, payload)
        chat_lock = self._chat_locks[f"{platform}:{event.owner_id}"]
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
        platform = event.platform
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
            self.store.clear_messages(platform, str(event.user_id))
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
            platform,
            str(event.user_id),
            self.config.context_messages,
        )
        settings = self.store.get_settings(platform, str(event.user_id))
        memories = (
            self.store.memory_context(platform, str(event.user_id), text, 10)
            if settings.get("memory_enabled", True)
            else []
        )
        relationship = self.relationship_context(platform, str(event.user_id))
        memories = (
            list(memories)
            + self.timeline_context(platform, str(event.user_id))
            + [self.relationship_prompt(relationship)]
        )
        self.store.add_message(platform, str(event.user_id), "user", text)
        context = {
            "platform": platform,
            "owner_id": str(event.user_id),
            "chat_id": str(event.chat_id),
            "chat_type": event.message_type,
            "is_admin": "1" if is_admin else "0",
            "sticker_enabled": (
                "1"
                if platform == "qq" and settings.get("sticker_enabled", True)
                else "0"
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
            self.prepare_reminder,
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
        bubbles = self.chat_bubbles(reply)
        reply = "\n".join(bubbles)
        self.store.add_message(platform, str(event.user_id), "assistant", reply)
        self.send_reply(
            event,
            reply,
            self.selected_sticker(context),
            bubbles=bubbles,
        )
        self.update_relationship_after_exchange(
            platform, str(event.user_id), text
        )
        self.executor.submit(
            self.remember_exchange,
            platform,
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
        relationship = self.relationship_context("web", str(user_id))
        memories = (
            list(memories)
            + self.timeline_context("web", str(user_id))
            + [self.relationship_prompt(relationship)]
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
            self.prepare_reminder,
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
        bubbles = self.chat_bubbles(reply)
        reply = "\n".join(bubbles)
        self.store.add_message("web", owner, "assistant", reply)
        self.update_relationship_after_exchange("web", str(user_id), text)
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
        self._reminder_stop.set()
        if self.qqbot:
            self.qqbot.close()
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
            admin_ids = self.service.store.admin_ids("qq")
            relationship_owner = admin_ids[0] if admin_ids else "0"
            self.send_json(
                200,
                {
                    "ok": True,
                    "model": self.service.config.deepseek_model,
                    "group_enabled": self.service.config.group_enabled,
                    "group_ids": sorted(self.service.config.group_ids),
                    "bound_admins": len(admin_ids),
                    "qqbot": (
                        self.service.qqbot.status()
                        if self.service.qqbot
                        else {"enabled": False, "connected": False}
                    ),
                    "relationship": self.service.relationship_context(
                        "qq", relationship_owner
                    ),
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
        if path == "/internal/timeline":
            if not self.internal_authorized():
                self.send_json(403, {"error": "forbidden"})
                return
            query = parse_qs(parsed.query)
            platform = str((query.get("platform") or ["web"])[0])
            owner_id = str((query.get("owner_id") or ["0"])[0])
            status = str((query.get("status") or ["all"])[0])
            rows = self.service.store.list_timeline_events(
                platform, owner_id, 200
            )
            if status in ("open", "done"):
                rows = [
                    item for item in rows if item.get("status") == status
                ]
            self.send_json(200, {"events": rows})
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
            "/internal/timeline/create",
            "/internal/timeline/status",
            "/internal/timeline/delete",
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
            if parsed.path == "/internal/timeline/create":
                platform = str(payload.get("platform") or "web")
                owner_id = str(payload.get("owner_id") or "0")
                title = str(payload.get("title") or "").strip()
                content = str(payload.get("content") or "").strip()
                if not title and not content:
                    self.send_json(400, {"error": "event content required"})
                    return
                try:
                    event_at = (
                        int(payload["event_at"])
                        if payload.get("event_at") is not None
                        else None
                    )
                    follow_up_at = (
                        int(payload["follow_up_at"])
                        if payload.get("follow_up_at") is not None
                        else None
                    )
                except (TypeError, ValueError):
                    self.send_json(400, {"error": "invalid event time"})
                    return
                event_id = self.service.store.add_timeline_event(
                    platform,
                    owner_id,
                    str(payload.get("event_type") or "event"),
                    title,
                    content,
                    event_at,
                    follow_up_at,
                )
                if not event_id:
                    self.send_json(400, {"error": "event content required"})
                    return
                self.send_json(200, {"ok": True, "id": event_id})
                return
            if parsed.path in (
                "/internal/timeline/status",
                "/internal/timeline/delete",
            ):
                platform = str(payload.get("platform") or "web")
                owner_id = str(payload.get("owner_id") or "0")
                try:
                    event_id = int(payload.get("id"))
                except (TypeError, ValueError):
                    self.send_json(400, {"error": "invalid event id"})
                    return
                if parsed.path == "/internal/timeline/delete":
                    deleted = self.service.store.delete_timeline_event(
                        platform, owner_id, event_id
                    )
                    self.send_json(200, {"ok": deleted})
                    return
                status = str(payload.get("status") or "")
                if status not in ("open", "done"):
                    self.send_json(400, {"error": "invalid event status"})
                    return
                updated = self.service.store.set_timeline_status(
                    platform, owner_id, event_id, status
                )
                self.send_json(200, {"ok": updated})
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
