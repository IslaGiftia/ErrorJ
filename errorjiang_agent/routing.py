from __future__ import annotations

from dataclasses import dataclass, replace
import random
import re
import time
from typing import Any, Callable

from .onebot import MessageEvent


GROUP_BOT_ALIASES = ("鲸鲸",)
GROUP_FOLLOWUP_START_RE = re.compile(
    r"^(?:那|所以|然后|还有|继续|刚才|刚刚|这个|那个|"
    r"帮我|请问|查一下|查询|搜索|添加|提醒|记住)"
)
GROUP_DIRECT_COMMAND_RE = re.compile(
    r"^(?:/|帮助$|重置对话$|群友档案$|绑定账号\s+|解绑用户\s+|"
    r"设置天气城市\s+|清除天气城市$|删除天气城市$|确认\s+\d{6}$|"
    r"保存(?:一个|一张)?(?:表情包?|图片)|添加(?:一个|一张)?(?:表情包?|图片))"
)
GROUP_QUIET_COMMAND_RE = re.compile(
    r"^\s*(?:(?:群里|全群)\s*)?(?:鲸鲸\s*)?(?:"
    r"安静(?:一下|一会儿)?|别插话(?:了)?|别说了?|闭嘴|禁言鲸鲸|"
    r"恢复|解除安静|恢复说话|可以说话了)"
    r"(?:\s*\d{1,3}\s*(?:分钟|小时))?\s*$"
)


class GroupConversationPolicy:
    ACTIVE_QUESTION_PROBABILITY = 0.45
    ACTIVE_TOPIC_PROBABILITY = 0.18
    ACTIVE_QUESTION_RE = re.compile(
        r"(?:什么|怎么|为什么|咋|如何|有没有|有人|大家|推荐|求问|"
        r"哪家|哪里|哪个|能不能|可不可以)"
    )

    def __init__(
        self,
        store: Any,
        settings_provider: Callable[[MessageEvent], dict[str, Any]] | None = None,
    ):
        self.store = store
        self.settings_provider = settings_provider

    @staticmethod
    def location_add_requested(text: str) -> bool:
        value = str(text or "").strip().lower()
        if not value:
            return False
        return (
            any(word in value for word in ("添加", "加进", "保存", "存进"))
            and any(
                word in value
                for word in ("刚才", "刚刚", "上一个", "这个")
            )
            and any(word in value for word in ("位置", "地点", "标记", "足迹"))
        )

    def recent_assistant_member(self, event: MessageEvent) -> str:
        rows = self.store.get_group_messages(
            event.platform,
            str(event.chat_id),
            40,
        )
        cutoff = int(time.time()) - 10 * 60
        for index in range(len(rows) - 1, -1, -1):
            row = rows[index]
            if row.get("role") != "assistant":
                continue
            try:
                if int(row.get("created_at") or 0) < cutoff:
                    return ""
            except (TypeError, ValueError):
                return ""
            for previous in reversed(rows[:index]):
                if previous.get("role") == "user":
                    return str(previous.get("member_id") or "")
            return ""
        return ""

    def group_activity_level(self, event: MessageEvent) -> str:
        if not self.settings_provider:
            return "balanced"
        try:
            settings = self.settings_provider(event) or {}
        except Exception:
            return "balanced"
        level = str(settings.get("group_activity_level") or "balanced").strip()
        return level if level in ("quiet", "balanced", "active") else "balanced"

    def active_join_candidate(self, event: MessageEvent) -> bool:
        if self.group_activity_level(event) != "active":
            return False
        text = " ".join(event.text.split()).strip()
        if (
            len(text) < 4
            or "http://" in text.lower()
            or "https://" in text.lower()
        ):
            return False
        question_like = bool(
            text.endswith(("?", "？", "吗", "呢", "么"))
            or self.ACTIVE_QUESTION_RE.search(text)
        )
        if not question_like and len(text) < 6:
            return False
        rows = self.store.get_group_messages(
            event.platform,
            str(event.chat_id),
            40,
        )
        cutoff = int(time.time()) - 5 * 60
        recent_members = {
            str(row.get("member_id") or "")
            for row in rows
            if row.get("role") == "user"
            and int(row.get("created_at") or 0) >= cutoff
            and row.get("member_id")
        }
        recent_count = sum(
            1
            for row in rows
            if row.get("role") == "user"
            and int(row.get("created_at") or 0) >= cutoff
        )
        return (
            recent_count >= 3
            and len(recent_members) >= 2
            and random.random()
            < (
                self.ACTIVE_QUESTION_PROBABILITY
                if question_like
                else self.ACTIVE_TOPIC_PROBABILITY
            )
        )

    def wants_reply(self, event: MessageEvent) -> bool:
        if event.shared_media:
            return True
        text = " ".join(event.text.split()).strip()
        if not text:
            return False
        lowered = text.lower()
        if any(alias in lowered for alias in GROUP_BOT_ALIASES):
            return True
        if event.mentions_other:
            return False
        if GROUP_QUIET_COMMAND_RE.match(text):
            return True
        if (
            GROUP_DIRECT_COMMAND_RE.match(text)
            or self.location_add_requested(text)
        ):
            return True
        if self.active_join_candidate(event):
            return True
        recent_member = self.recent_assistant_member(event)
        if event.referenced and recent_member:
            return True
        if not recent_member or len(text) < 3:
            return False
        if recent_member != str(event.user_id):
            return False
        if "你" in text:
            return True
        if GROUP_FOLLOWUP_START_RE.match(text):
            return True
        return text.endswith(("?", "？", "吗", "呢", "么"))


@dataclass
class EventState:
    auto_reply: bool = False
    reason: str = ""


EventStage = Callable[
    [MessageEvent, EventState],
    MessageEvent | None,
]


class EventPipeline:
    def __init__(self, stages: list[EventStage]):
        self.stages = list(stages)

    def run(
        self,
        event: MessageEvent,
        state: EventState | None = None,
    ) -> tuple[MessageEvent | None, EventState]:
        current = event
        current_state = state or EventState()
        for stage in self.stages:
            current = stage(current, current_state)
            if current is None:
                break
        return current, current_state


def build_group_event_pipeline(
    policy: GroupConversationPolicy,
    config: Any,
) -> EventPipeline:
    def auto_mention(
        event: MessageEvent,
        state: EventState,
    ) -> MessageEvent | None:
        if event.message_type != "group" or event.to_me:
            return event
        if event.location:
            return event
        if event.shared_media:
            state.auto_reply = True
            state.reason = "shared_media"
            return replace(event, to_me=True)
        if (
            event.platform == "qqbot"
            and event.group_full
            and policy.wants_reply(event)
        ):
            state.auto_reply = True
            state.reason = "group_conversation"
            return replace(event, to_me=True)
        return event

    def scope(
        event: MessageEvent,
        state: EventState,
    ) -> MessageEvent | None:
        del state
        if event.message_type != "group":
            return event
        if event.platform == "qq":
            if not config.group_enabled:
                return None
            if event.chat_id not in config.group_ids:
                return None
        elif event.platform == "qqbot":
            if (
                config.qqbot_group_ids
                and str(event.chat_id) not in config.qqbot_group_ids
            ):
                return None
        return event

    def mention_gate(
        event: MessageEvent,
        state: EventState,
    ) -> MessageEvent | None:
        del state
        if (
            event.message_type == "group"
            and not event.to_me
            and not event.location
            and not event.shared_media
        ):
            return None
        return event

    return EventPipeline([auto_mention, scope, mention_gate])
