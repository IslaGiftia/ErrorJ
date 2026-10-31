from __future__ import annotations

from dataclasses import dataclass, replace
import re
import time
from typing import Any, Callable

from .onebot import MessageEvent


GROUP_BOT_ALIASES = ("折兮颜", "error酱", "错误酱", "小颜")
GROUP_FOLLOWUP_START_RE = re.compile(
    r"^(?:那|所以|然后|还有|继续|刚才|刚刚|这个|那个|"
    r"帮我|请问|查一下|查询|搜索|添加|提醒|记住)"
)
GROUP_DIRECT_COMMAND_RE = re.compile(
    r"^(?:/|帮助$|重置对话$|群友档案$|绑定账号\s+|解绑用户\s+|"
    r"设置天气城市\s+|清除天气城市$|删除天气城市$|确认\s+\d{6}$|"
    r"保存(?:一个|一张)?(?:表情包?|图片)|添加(?:一个|一张)?(?:表情包?|图片))"
)


class GroupConversationPolicy:
    def __init__(self, store: Any):
        self.store = store

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
            12,
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

    def wants_reply(self, event: MessageEvent) -> bool:
        text = " ".join(event.text.split()).strip()
        if not text:
            return False
        lowered = text.lower()
        if any(alias in lowered for alias in GROUP_BOT_ALIASES):
            return True
        if event.mentions_other:
            return False
        if (
            GROUP_DIRECT_COMMAND_RE.match(text)
            or self.location_add_requested(text)
        ):
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
        ):
            return None
        return event

    return EventPipeline([auto_mention, scope, mention_gate])
