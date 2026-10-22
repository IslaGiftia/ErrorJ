import json
import http.client
import os
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from errorjiang_agent.brain import AgentBrain
from errorjiang_agent.config import Config
from errorjiang_agent.onebot import MessageEvent, event_key, parse_message_event
from errorjiang_agent.onebot_ws import _masked_frame, _read_frame
from errorjiang_agent.qqbot import QQBotClient, parse_qqbot_event
from errorjiang_agent.service import AgentHttpServer, AgentService
from errorjiang_agent.store import AgentStore


class AgentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AgentStore(Path(self.temp.name) / "agent.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_seen_event_is_deduplicated(self):
        self.assertFalse(self.store.seen_event("event-1"))
        self.assertTrue(self.store.seen_event("event-1"))

    def test_pending_action_requires_same_owner_and_chat(self):
        code, _ = self.store.create_pending(
            "qq",
            "10001",
            "10001",
            {"kind": "user", "id": 3, "action": "approve"},
        )
        self.assertIsNone(
            self.store.consume_pending("qq", "10002", "10001", code)
        )
        action = self.store.consume_pending("qq", "10001", "10001", code)
        self.assertEqual(action["id"], 3)
        self.assertIsNone(
            self.store.consume_pending("qq", "10001", "10001", code)
        )

    def test_pending_action_expires(self):
        with patch("errorjiang_agent.store.time.time", return_value=100):
            code, _ = self.store.create_pending(
                "qq",
                "10001",
                "10001",
                {"kind": "message", "id": 8, "action": "reject"},
                ttl_seconds=1,
            )
        with patch("errorjiang_agent.store.time.time", return_value=102):
            self.assertIsNone(
                self.store.consume_pending("qq", "10001", "10001", code)
            )

    def test_admin_binding_is_persistent(self):
        self.assertFalse(self.store.has_admins())
        self.store.bind_admin("qq", "10001")
        self.assertTrue(self.store.has_admins())
        self.assertTrue(self.store.is_admin("qq", "10001"))
        self.assertFalse(self.store.is_admin("qq", "10002"))

    def test_qq_user_can_be_linked_to_site_account(self):
        self.store.bind_user("qq", "10003", 42)
        self.assertEqual(self.store.linked_user_id("qq", "10003"), 42)
        self.assertEqual(self.store.list_identities("qq")[0]["user_id"], 42)
        self.assertTrue(self.store.unbind_user("qq", "10003"))
        self.assertIsNone(self.store.linked_user_id("qq", "10003"))

    def test_memory_settings_and_stickers(self):
        self.store.add_memory("qq", "10001", "星星喜欢安静", "preference", 8)
        self.store.add_memory("qq", "10001", "星星喜欢安静", "preference", 9)
        memories = self.store.list_memories("qq", "10001")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["importance"], 9)
        self.assertIn("安静", self.store.memory_context("qq", "10001", "安静")[0])

        settings = self.store.save_settings(
            "qq", "10001", {"proactive_max_per_day": 3}
        )
        self.assertEqual(settings["proactive_max_per_day"], 3)

        sticker_id = self.store.add_sticker(
            "10001", "face", "178", "开心"
        )
        self.assertEqual(self.store.list_stickers("10001")[0]["id"], sticker_id)
        self.assertIsNotNone(self.store.delete_sticker("10001", sticker_id))

    def test_memory_context_uses_relevance_and_confidence(self):
        self.store.add_memory(
            "qq",
            "10001",
            "星星喜欢安静的咖啡馆",
            "preference",
            6,
            8,
        )
        self.store.add_memory(
            "qq",
            "10001",
            "星星上周去了图书馆",
            "event",
            5,
            3,
        )
        self.store.add_memory(
            "qq",
            "10001",
            "星星不喜欢太吵的地方",
            "preference",
            9,
            9,
        )
        relevant = self.store.memory_context(
            "qq",
            "10001",
            "图书馆",
            2,
        )
        self.assertIn("图书馆", relevant[0])
        confident = self.store.memory_context("qq", "10001", "", 2)
        self.assertIn("不喜欢太吵", confident[0])
        memory = self.store.list_memories("qq", "10001")[0]
        self.assertIn("confidence", memory)
        self.assertIn("source", memory)

    def test_group_member_directory_survives_and_links_site_account(self):
        first = self.store.remember_group_member(
            "qqbot",
            "group-openid",
            "member-openid",
            "小明",
            "今天去吃饭",
        )
        self.assertEqual(first["message_count"], 1)
        second = self.store.remember_group_member(
            "qqbot",
            "group-openid",
            "member-openid",
            "小明改名",
            "下次还去",
        )
        self.assertEqual(second["message_count"], 2)
        self.assertEqual(second["display_name"], "小明改名")
        self.store.bind_user("qqbot", "member-openid", 7)
        members = self.store.list_group_members()
        self.assertEqual(members[0]["user_id"], 7)
        self.assertEqual(members[0]["last_topic"], "下次还去")
        self.assertEqual(
            self.store.group_member_display_name(
                "qqbot",
                "member-openid",
            ),
            "小明改名",
        )
        updated = self.store.update_group_member_profile(
            "qqbot",
            "group-openid",
            "member-openid",
            {
                "alias": "明明",
                "relationship": "朋友",
                "allow_chat": False,
                "allow_tools": False,
                "memory_enabled": False,
                "notes": "不喜欢被叫全名",
            },
        )
        self.assertEqual(updated["alias"], "明明")
        self.assertEqual(updated["relationship"], "朋友")
        self.assertEqual(updated["allow_chat"], 0)
        self.assertEqual(updated["allow_tools"], 0)
        self.assertEqual(updated["memory_enabled"], 0)

    def test_group_chat_history_keeps_speakers_and_deduplicates(self):
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "member-a",
            "小明",
            "user",
            "周六去吃火锅",
            "message-1",
        )
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "member-a",
            "小明",
            "user",
            "周六去吃火锅",
            "message-1",
        )
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "assistant",
            "折兮颜",
            "assistant",
            "可以，折兮颜记下了",
            "assistant:message-1",
        )
        history = self.store.get_group_messages(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["display_name"], "小明")
        self.assertEqual(history[1]["role"], "assistant")
        self.store.clear_group_messages("qqbot", "group-openid")
        self.assertEqual(
            self.store.get_group_messages("qqbot", "group-openid"),
            [],
        )

    def test_idle_memory_consolidation_is_daily_and_structured(self):
        class Consolidator:
            def chat(self, messages, tools):
                return {
                    "content": json.dumps(
                        {
                            "summary": "记住偏好",
                            "memories": [
                                {
                                    "content": "星星更喜欢安静的聊天环境",
                                    "kind": "preference",
                                    "importance": 8,
                                    "confidence": 9,
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        for index in range(8):
            self.store.add_message(
                "qqbot",
                "member-openid",
                "user" if index % 2 == 0 else "assistant",
                f"消息 {index}",
            )
        service = object.__new__(AgentService)
        service.store = self.store
        service.deepseek = Consolidator()
        self.assertEqual(
            service.consolidate_memories(
                "2026-10-22",
                datetime(2026, 10, 22, 3, 30),
            ),
            1,
        )
        memories = self.store.list_memories("qqbot", "member-openid")
        self.assertEqual(memories[0]["source"], "consolidation")
        self.assertEqual(memories[0]["confidence"], 9)
        self.assertEqual(
            service.consolidate_memories(
                "2026-10-22",
                datetime(2026, 10, 22, 3, 31),
            ),
            0,
        )

    def test_group_chat_consolidates_shared_memories_separately(self):
        class Consolidator:
            def chat(self, messages, tools):
                return {
                    "content": json.dumps(
                        {
                            "summary": "群活动",
                            "memories": [
                                {
                                    "content": "大家约好周六一起吃火锅",
                                    "kind": "event",
                                    "importance": 8,
                                    "confidence": 9,
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        for index in range(8):
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                f"member-{index % 3}",
                f"群友{index % 3}",
                "user" if index % 2 == 0 else "assistant",
                f"群消息 {index}",
                f"group-message-{index}",
            )
        service = object.__new__(AgentService)
        service.store = self.store
        service.deepseek = Consolidator()
        self.assertEqual(
            service.consolidate_memories(
                "2026-10-22",
                datetime(2026, 10, 22, 3, 30),
            ),
            1,
        )
        group_memories = self.store.list_memories(
            "qqbot-group",
            "group-openid",
        )
        self.assertEqual(
            group_memories[0]["source"],
            "group_consolidation",
        )
        self.assertIn("火锅", group_memories[0]["content"])

    def test_timeline_events_are_deduplicated_and_used_once(self):
        event_id = self.store.add_timeline_event(
            "qq",
            "10001",
            "promise",
            "周末整理房间",
            "周六一起整理书架",
            100,
            200,
        )
        self.assertGreater(event_id, 0)
        self.assertEqual(
            self.store.add_timeline_event(
                "qq",
                "10001",
                "plan",
                "周末整理书架",
                "周六一起整理书架",
                100,
                200,
            ),
            event_id,
        )
        self.assertEqual(len(self.store.list_timeline_events("qq", "10001")), 1)
        self.assertEqual(self.store.due_timeline_events(199), [])
        due = self.store.due_timeline_events(
            200, platform="qq", owner_id="10001"
        )
        self.assertEqual([item["id"] for item in due], [event_id])

        self.store.mark_timeline_used(event_id)
        self.assertEqual(self.store.due_timeline_events(200), [])
        self.assertTrue(
            self.store.set_timeline_status("qq", "10001", event_id, "open")
        )
        self.assertEqual(len(self.store.due_timeline_events(200)), 1)
        self.assertTrue(
            self.store.set_timeline_status("qq", "10001", event_id, "done")
        )
        self.assertEqual(self.store.due_timeline_events(200), [])
        self.assertTrue(
            self.store.delete_timeline_event("qq", "10001", event_id)
        )
        self.assertEqual(self.store.list_timeline_events("qq", "10001"), [])

    def test_remember_exchange_extracts_timeline_events(self):
        class Extractor:
            def chat(self, messages, tools):
                return {
                    "content": json.dumps(
                        {
                            "memories": [],
                            "events": [
                                {
                                    "title": "周末整理房间",
                                    "content": "星星约好周六一起整理书架",
                                    "event_type": "promise",
                                    "event_at": "2026-10-24 10:00:00",
                                    "follow_up_at": "2026-10-23 20:00:00",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        service = object.__new__(AgentService)
        service.store = self.store
        service.deepseek = Extractor()
        service.remember_exchange(
            "qq",
            "10001",
            "周六一起整理书架吧",
            "嗯，折兮颜记下了。",
        )
        events = self.store.list_timeline_events("qq", "10001")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "promise")
        self.assertEqual(events[0]["title"], "周末整理房间")
        self.assertIsNotNone(events[0]["follow_up_at"])

    def test_relationship_state_is_persistent_and_bounded(self):
        state = self.store.update_relationship_state(
            "qq",
            "10001",
            {
                "mood": "有点吃醋",
                "energy": 20,
                "care": 8,
                "jealousy": 9,
                "last_topic": "星星提到了别的 AI",
            },
        )
        self.assertEqual(state["energy"], 10)
        self.assertEqual(state["jealousy"], 3)
        self.assertEqual(state["mood"], "有点吃醋")

    def test_service_prepares_action_for_current_chat(self):
        service = object.__new__(AgentService)
        service.store = self.store
        prepared = service.prepare_review(
            {"kind": "user", "id": 9, "action": "approve"},
            {
                "platform": "qq",
                "owner_id": "10001",
                "chat_id": "10001",
                "is_admin": "1",
            },
        )
        action = self.store.consume_pending(
            "qq", "10001", "10001", prepared["code"]
        )
        self.assertEqual(action["kind"], "user")
        self.assertEqual(action["id"], 9)
        self.assertEqual(action["action"], "approve")

    def test_reminder_is_scheduled(self):
        service = object.__new__(AgentService)
        service.store = self.store
        prepared = service.prepare_reminder(
            {"delay_minutes": 10, "text": "提醒星星睡觉"},
            {"platform": "qq", "owner_id": "10001", "chat_id": "10001", "chat_type": "private"},
        )
        self.assertEqual(prepared["status"], "scheduled")
        reminders = self.store.list_reminders("qq", "10001")
        self.assertEqual(reminders[0]["text"], "提醒星星睡觉")
        self.assertEqual(
            AgentService.reminder_delivery_text(reminders[0]),
            "提醒星星睡觉",
        )

    def test_humanize_collapses_chat_blank_lines(self):
        text = "嗯，就一个句号。\n\n我收好了，你还想说什么？"
        self.assertEqual(
            AgentService.humanize_text(text),
            "嗯，就一个句号。 我收好了，你还想说什么？",
        )
        self.assertEqual(
            AgentService.humanize_text(
                "知道啦。今天也辛苦了。",
                strip_terminal_period=True,
            ),
            "知道啦。今天也辛苦了",
        )
        self.assertEqual(
            AgentService.humanize_text(
                "“晚安。”",
                strip_terminal_period=True,
            ),
            "“晚安”",
        )
        self.assertEqual(
            AgentService.humanize_text(
                "- 库存 3 条。",
                strip_terminal_period=True,
            ),
            "- 库存 3 条。",
        )

    def test_chat_bubbles_only_split_when_model_requests_it(self):
        self.assertEqual(
            AgentService.chat_bubbles("嗯，知道啦"),
            ["嗯，知道啦"],
        )
        self.assertEqual(
            AgentService.chat_bubbles(
                "嗯。知道啦。\n[[split]]\n那你早点睡。"
            ),
            ["嗯。知道啦", "那你早点睡"],
        )
        self.assertEqual(
            AgentService.chat_bubbles(
                "一[[split]]二[[split]]三[[split]]四"
            ),
            ["一", "二", "三 四"],
        )

    def test_explicit_sticker_requests_are_detected(self):
        from errorjiang_agent.service import STICKER_REQUEST_RE

        for text in (
            "发个表情包",
            "来一个无语的表情",
            "整张晚安表情包",
        ):
            self.assertIsNotNone(STICKER_REQUEST_RE.search(text))
        self.assertIsNone(STICKER_REQUEST_RE.search("这个表情包是什么"))

    def test_qqbot_reply_uses_openapi_messages_per_bubble(self):
        class FakeQQBot:
            def __init__(self):
                self.messages = []

            def send_message(self, message_type, chat_id, message_id, content):
                self.messages.append(
                    (message_type, chat_id, message_id, content)
                )

        service = object.__new__(AgentService)
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.sticker_segment = lambda sticker: None
        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="message-id",
            text="你好",
            to_me=True,
            platform="qqbot",
        )
        with patch("errorjiang_agent.service.time.sleep"), patch(
            "errorjiang_agent.service.random.uniform",
            return_value=0,
        ):
            service.send_reply(
                event,
                "嗯\n早点睡",
                bubbles=["嗯", "早点睡"],
            )
        self.assertEqual(
            service.qqbot.messages,
            [
                ("group", "group-openid", "message-id", "嗯"),
                ("group", "group-openid", "message-id", "早点睡"),
            ],
        )

    def test_qqbot_image_upload_uses_file_info_and_media_message(self):
        client = QQBotClient("app", "secret", "bot", lambda event: None)
        client._auth_headers = lambda: {"Authorization": "test"}
        calls = []

        def fake_http(url, payload=None, headers=None):
            calls.append((url, payload, headers))
            if url.endswith("/files"):
                return {"file_info": "file-info"}
            return {"id": "sent"}

        client._http_json = fake_http
        client.send_image(
            "group",
            "group-openid",
            "message-id",
            "sticker.png",
            b"png-data",
        )
        self.assertTrue(calls[0][0].endswith("/groups/group-openid/files"))
        self.assertEqual(calls[0][1]["file_type"], 1)
        self.assertEqual(calls[0][1]["file_name"], "sticker.png")
        self.assertEqual(calls[1][1]["msg_type"], 7)
        self.assertEqual(
            calls[1][1]["media"],
            {"file_info": "file-info"},
        )

    def test_qqbot_image_attachment_is_saved_as_sticker(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return b"\x89PNG\r\n\x1a\n" + b"sticker-data"

        service = object.__new__(AgentService)
        service.store = self.store
        service.sticker_dir = Path(self.temp.name) / "stickers"
        service.sticker_dir.mkdir()
        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="message-id",
            text="",
            to_me=True,
            platform="qqbot",
            attachments=(
                {
                    "content_type": "image/png",
                    "filename": "sticker.png",
                    "url": "https://example.com/sticker.png",
                },
            ),
        )
        with patch(
            "errorjiang_agent.service.urlopen",
            return_value=FakeResponse(),
        ):
            saved = service.save_qqbot_attachments(event)
        self.assertEqual(saved, 1)
        stickers = self.store.list_stickers("member-openid")
        self.assertEqual(len(stickers), 1)
        self.assertEqual(stickers[0]["kind"], "image")
        self.assertTrue(
            (service.sticker_dir / stickers[0]["ref"]).is_file()
        )

    def test_qqbot_config_is_loaded_when_enabled(self):
        with patch.dict(
            os.environ,
            {
                "QQBOT_ENABLED": "true",
                "QQBOT_APP_ID": "10001",
                "QQBOT_APP_SECRET": "secret",
                "QQBOT_BOT_QQ": "20002",
                "QQBOT_GROUP_IDS": "group-a,group-b",
                "QQBOT_ADMIN_OPENIDS": "admin-openid",
                "QQBOT_AUTO_BIND_FIRST_ADMIN": "true",
            },
            clear=False,
        ):
            config = Config.load(Path(self.temp.name))
        self.assertTrue(config.qqbot_enabled)
        self.assertEqual(config.qqbot_app_id, "10001")
        self.assertEqual(config.qqbot_bot_qq, "20002")
        self.assertEqual(
            config.qqbot_group_ids,
            frozenset({"group-a", "group-b"}),
        )
        self.assertEqual(
            config.qqbot_admin_openids,
            frozenset({"admin-openid"}),
        )
        self.assertTrue(config.qqbot_auto_bind_first_admin)

    def test_qqbot_identity_bind_code_is_one_time(self):
        code, expires_at = self.store.create_identity_bind_code(
            "qqbot",
            12,
        )
        self.assertGreater(expires_at, int(time.time()))
        self.assertEqual(
            self.store.consume_identity_bind_code(
                "qqbot",
                code,
                "group-member-openid",
            ),
            12,
        )
        self.assertIsNone(
            self.store.consume_identity_bind_code(
                "qqbot",
                code,
                "group-member-openid",
            )
        )

    def test_due_timeline_event_is_the_first_proactive_topic(self):
        now = datetime(2026, 10, 20, 9, 10)
        candidates = AgentService.proactive_candidates(
            now,
            {
                "morning_time": "09:00",
                "night_time": "21:30",
            },
            {"idle_hours": 8, "last_topic": "昨天说到的那本书"},
            [
                {
                    "id": 7,
                    "title": "周末整理房间",
                    "content": "星星说周六一起整理书架",
                }
            ],
            [
                {
                    "id": 9,
                    "kind": "promise",
                    "content": "晚上提醒星星早点睡",
                    "last_used_at": None,
                }
            ],
        )
        chosen = AgentService.choose_proactive_candidate(candidates)
        self.assertEqual(chosen["kind"], "timeline")
        self.assertEqual(chosen["event_id"], 7)
        self.assertIn("整理书架", chosen["topic"])

    def test_proactive_time_uses_a_window_and_skips_recent_memories(self):
        self.assertTrue(
            AgentService.proactive_time_near(
                datetime(2026, 10, 20, 9, 24), "09:00"
            )
        )
        self.assertFalse(
            AgentService.proactive_time_near(
                datetime(2026, 10, 20, 9, 26), "09:00"
            )
        )
        now = datetime(2026, 10, 20, 20, 0)
        recent = int(now.timestamp()) - 60
        old = int(now.timestamp()) - 4 * 86400
        candidates = AgentService.proactive_candidates(
            now,
            {"morning_time": "09:00", "night_time": "21:30"},
            {"idle_hours": 0, "last_topic": ""},
            [],
            [
                {
                    "id": 1,
                    "kind": "promise",
                    "content": "刚聊过的约定",
                    "last_used_at": recent,
                },
                {
                    "id": 2,
                    "kind": "event",
                    "content": "几天前提到的约定",
                    "last_used_at": old,
                },
            ],
        )
        memory_topics = [
            item["topic"] for item in candidates if item["kind"] == "memory"
        ]
        self.assertEqual(memory_topics, ["几天前提到的约定"])


class OneBotParserTests(unittest.TestCase):
    def test_private_message_parser(self):
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "private",
                "self_id": 20000,
                "user_id": 10001,
                "message_id": 9,
                "raw_message": "你好",
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.text, "你好")
        self.assertEqual(event.chat_id, 10001)

    def test_group_message_strips_mention_and_detects_to_me(self):
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "group",
                "self_id": 20000,
                "user_id": 10001,
                "group_id": 30001,
                "message_id": 10,
                "raw_message": "[CQ:at,qq=20000] 查库存",
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.text, "查库存")
        self.assertEqual(event.chat_id, 30001)
        self.assertTrue(event.to_me)
        self.assertIn("30001", event_key(event))

    def test_websocket_frame_round_trip(self):
        left, right = socket.socketpair()
        try:
            payload = "发送测试".encode("utf-8")
            left.sendall(_masked_frame(payload))
            opcode, fin, decoded = _read_frame(right)
            self.assertEqual(opcode, 1)
            self.assertTrue(fin)
            self.assertEqual(decoded, payload)
        finally:
            left.close()
            right.close()

    def test_qqbot_group_at_event_maps_openids(self):
        event = parse_qqbot_event(
            "GROUP_AT_MESSAGE_CREATE",
            {
                "id": "message-1",
                "content": "查一下库存",
                "group_openid": "group-openid",
                "author": {
                    "member_openid": "member-openid",
                    "username": "星星",
                },
                "attachments": [
                    {
                        "content_type": "image/png",
                        "url": "https://example.com/sticker.png",
                    }
                ],
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.platform, "qqbot")
        self.assertEqual(event.message_type, "group")
        self.assertEqual(event.user_id, "member-openid")
        self.assertEqual(event.chat_id, "group-openid")
        self.assertEqual(event.message_id, "message-1")
        self.assertEqual(event.display_name, "星星")
        self.assertEqual(
            event.attachments[0]["content_type"],
            "image/png",
        )

    def test_qqbot_c2c_event_maps_user_openid(self):
        event = parse_qqbot_event(
            "C2C_MESSAGE_CREATE",
            {
                "id": "message-2",
                "content": "在吗",
                "author": {
                    "user_openid": "user-openid",
                    "username": "星星",
                },
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.message_type, "private")
        self.assertEqual(event.user_id, "user-openid")
        self.assertEqual(event.chat_id, "user-openid")


class FakeDeepSeek:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, tools):
        return self.replies.pop(0)


class FakeErrorJ:
    def __init__(self):
        self.calls = []

    def tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"count": 1, "results": [{"part_number": "STM32F103C8T6"}]}


class AgentBrainTests(unittest.TestCase):
    def test_tool_call_then_final_reply(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_inventory_search",
                                "arguments": json.dumps(
                                    {"query": "STM32F103C8T6"}
                                ),
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "库存里有 1 条记录。"},
            ]
        )
        errorjiang = FakeErrorJ()
        brain = AgentBrain(deepseek, errorjiang, lambda args, context: {})
        reply = brain.reply("有 STM32F103C8T6 吗？", [])
        self.assertEqual(reply, "库存里有 1 条记录。")
        self.assertEqual(
            errorjiang.calls,
            [("inventory.search", {"query": "STM32F103C8T6"})],
        )

    def test_calculator_tool_mapping(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-aa",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_aa_events_list",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "账目列表如下。"},
            ]
        )
        errorjiang = FakeErrorJ()
        brain = AgentBrain(deepseek, errorjiang, lambda args, context: {})
        self.assertEqual(brain.reply("有哪些账目？", []), "账目列表如下。")
        self.assertEqual(errorjiang.calls, [("aa.events.list", {})])

    def test_review_prepare_receives_current_chat_context(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_review_prepare",
                                "arguments": json.dumps(
                                    {"kind": "user", "id": 3, "action": "approve"}
                                ),
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "请确认。"},
            ]
        )
        captured = {}

        def prepare(arguments, context):
            captured["arguments"] = arguments
            captured["context"] = context
            return {"status": "pending_confirmation", "code": "123456"}

        brain = AgentBrain(deepseek, FakeErrorJ(), prepare)
        reply = brain.reply(
            "通过用户 3",
            [],
            {"platform": "qq", "owner_id": "10001", "chat_id": "10001"},
        )
        self.assertEqual(reply, "请确认。")
        self.assertEqual(captured["arguments"]["id"], 3)
        self.assertEqual(captured["context"]["owner_id"], "10001")

    def test_group_member_can_be_limited_to_chat_without_tools(self):
        class CaptureDeepSeek:
            def __init__(self):
                self.tools = None

            def chat(self, messages, tools):
                self.tools = tools
                return {"role": "assistant", "content": "好"}

        deepseek = CaptureDeepSeek()
        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
        )
        self.assertEqual(
            brain.reply(
                "小明：你好",
                [],
                {
                    "platform": "qqbot",
                    "owner_id": "member-openid",
                    "is_admin": "0",
                    "speaker_name": "小明",
                    "tools_enabled": "0",
                },
            ),
            "好",
        )
        self.assertEqual(deepseek.tools, [])


class AgentInternalAuthTests(unittest.TestCase):
    def make_handler(self, headers, ip="127.0.0.1"):
        handler = object.__new__(app.InventoryHandler)
        handler.headers = headers
        handler.client_ip = lambda: ip
        handler.client_address = (ip, 12345)
        return handler

    def test_agent_token_and_loopback_are_required(self):
        token = "test-agent-token"
        with patch.dict(os.environ, {"ERRORJIANG_AGENT_TOKEN": token}):
            valid = self.make_handler(
                {
                    "X-ErrorJ-Agent-Token": token,
                    "X-ErrorJ-Agent-User": "0",
                }
            )
            self.assertEqual(valid.agent_request_identity()["kind"], "owner")

            remote = self.make_handler(
                {
                    "X-ErrorJ-Agent-Token": token,
                    "X-ErrorJ-Agent-User": "0",
                },
                ip="203.0.113.5",
            )
            self.assertIsNone(remote.agent_request_identity())

            bad = self.make_handler(
                {
                    "X-ErrorJ-Agent-Token": "wrong",
                    "X-ErrorJ-Agent-User": "0",
                }
            )
            self.assertIsNone(bad.agent_request_identity())

    def test_notes_tool_rejects_member_without_permission(self):
        handler = self.make_handler({})
        handler.send_json = lambda *args: None
        identity = {"kind": "member", "user_id": 7, "nickname": "test"}
        with patch.object(app, "user_has_permission", return_value=False), patch.object(
            app, "api_error"
        ) as api_error:
            handler.agent_tool_note_search(identity, {"query": "ESP32"})
        api_error.assert_called_once_with(
            handler, 403, "当前账号没有笔记查看权限。"
        )

    def test_review_decision_approves_pending_user(self):
        handler = self.make_handler({})
        handler.send_json = lambda *args: None
        handler.log_activity = lambda *args, **kwargs: None
        identity = {
            "kind": "owner",
            "user_id": 0,
            "username": "ErrorJ Agent",
            "nickname": "管理员",
            "role": "owner",
        }
        with patch.object(
            app,
            "query_one",
            return_value={
                "id": 9,
                "username": "new-user",
                "nickname": "新人",
                "status": "pending",
            },
        ), patch.object(app, "execute") as execute, patch.object(
            app, "write_audit"
        ) as write_audit:
            handler.agent_tool_reviews_decide(
                identity,
                {"kind": "user", "id": 9, "action": "approve", "note": "资料完整"},
            )
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[0][:20], "UPDATE users SET sta")
        write_audit.assert_called_once()

    def test_agent_web_page_is_admin_only(self):
        self.assertIsNone(app.required_permission("/agent", "GET"))
        self.assertIsNone(app.required_permission("/api/agent/web/chat", "POST"))

    def test_binding_command_accepts_username(self):
        from errorjiang_agent.service import (
            BIND_USER_RE,
            REDEEM_IDENTITY_BIND_CODE_RE,
        )

        match = BIND_USER_RE.fullmatch("绑定用户 123456789 星星")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "123456789")
        self.assertEqual(match.group(2).strip(), "星星")
        for text in (
            "绑定账号 748876",
            "绑定码：748876",
            "绑定 748876",
        ):
            match = REDEEM_IDENTITY_BIND_CODE_RE.fullmatch(text)
            self.assertIsNotNone(match)
            self.assertEqual(match.group(1), "748876")

    def test_agent_web_api_does_not_require_internal_token(self):
        handler = self.make_handler({})
        handler.session_identity = lambda: {
            "kind": "owner",
            "user_id": 0,
            "username": "管理员",
            "role": "owner",
        }
        with patch.dict(app.AUTH_STATE, {"enabled": True}, clear=False):
            self.assertTrue(
                handler.guard_request_inner("/api/agent/web/status", "GET")
            )


class AgentWebhookTests(unittest.TestCase):
    def test_chunked_onebot_event_is_accepted(self):
        received = []
        fake_service = SimpleNamespace(
            config=SimpleNamespace(onebot_webhook_secret="hook-secret"),
            schedule_event=received.append,
        )
        server = AgentHttpServer(("127.0.0.1", 0), fake_service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = json.dumps(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 10001,
                "message_id": 2,
                "raw_message": "绑定 123456",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=5
        )
        try:
            connection.request(
                "POST",
                "/onebot/event/hook-secret",
                body=[payload],
                headers={"Content-Type": "application/json"},
                encode_chunked=True,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
        self.assertEqual(received[0]["raw_message"], "绑定 123456")

    def test_internal_web_chat_uses_service_rate_limiter(self):
        class Limiter:
            def __init__(self):
                self.keys = []

            def allow(self, key):
                self.keys.append(key)
                return True

        limiter = Limiter()
        fake_service = SimpleNamespace(
            config=SimpleNamespace(errorjiang_token="internal-token"),
            rate_limiter=limiter,
            web_chat=lambda user_id, text: f"reply:{user_id}:{text}",
        )
        server = AgentHttpServer(("127.0.0.1", 0), fake_service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=5
        )
        try:
            body = json.dumps({"user_id": 0, "message": "你好"}).encode("utf-8")
            connection.request(
                "POST",
                "/internal/web-chat",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "X-ErrorJ-Agent-Token": "internal-token",
                },
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["reply"], "reply:0:你好")
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
        self.assertEqual(limiter.keys, ["web:0"])


class AgentTimelineApiTests(unittest.TestCase):
    def test_internal_timeline_can_be_created_listed_and_completed(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = AgentStore(Path(temp.name) / "agent.db")
        fake_service = SimpleNamespace(
            config=SimpleNamespace(errorjiang_token="internal-token"),
            store=store,
        )
        server = AgentHttpServer(("127.0.0.1", 0), fake_service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(method, path, payload=None):
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            body = (
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            )
            headers = {
                "X-ErrorJ-Agent-Token": "internal-token",
                "Content-Type": "application/json",
            }
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                data = json.loads(response.read().decode("utf-8"))
                return response.status, data
            finally:
                connection.close()

        status, created = request(
            "POST",
            "/internal/timeline/create",
            {
                "platform": "web",
                "owner_id": "0",
                "event_type": "plan",
                "title": "周末整理房间",
                "content": "周六一起整理书架",
                "event_at": 100,
                "follow_up_at": 200,
            },
        )
        self.assertEqual(status, 200)
        self.assertGreater(created["id"], 0)
        status, listed = request(
            "GET", "/internal/timeline?platform=web&owner_id=0&status=open"
        )
        self.assertEqual(status, 200)
        self.assertEqual(listed["events"][0]["title"], "周末整理房间")
        status, completed = request(
            "POST",
            "/internal/timeline/status",
            {
                "platform": "web",
                "owner_id": "0",
                "id": created["id"],
                "status": "done",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(completed["ok"])


class AgentNotificationTests(unittest.TestCase):
    def make_service(self):
        service = object.__new__(AgentService)
        service.config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset({1128878349}),
        )
        service.store = SimpleNamespace(admin_ids=lambda platform="qq": ["2873523107"])
        service.onebot = SimpleNamespace(
            group_messages=[],
            private_messages=[],
        )
        service.onebot.send_group = lambda group_id, text: service.onebot.group_messages.append(
            (group_id, text)
        )
        service.onebot.send_private = lambda user_id, text: service.onebot.private_messages.append(
            (user_id, text)
        )
        return service

    def test_public_activity_is_sent_to_whitelisted_group(self):
        service = self.make_service()
        service.send_notification(
            {
                "event": "place",
                "title": "Error酱：有新的标记点",
                "body": "用户A 新增了标记点「测试」",
                "link": "https://zhexiyan.cc/map",
            }
        )
        self.assertEqual(len(service.onebot.group_messages), 1)
        self.assertEqual(service.onebot.group_messages[0][0], 1128878349)
        self.assertIn("用户A", service.onebot.group_messages[0][1])
        self.assertEqual(len(service.onebot.private_messages), 1)

    def test_admin_review_event_is_sent_privately(self):
        service = self.make_service()
        service.send_notification(
            {
                "event": "register",
                "title": "Error酱：新的注册申请",
                "body": "新用户提交了申请",
            }
        )
        self.assertEqual(service.onebot.group_messages, [])
        self.assertEqual(len(service.onebot.private_messages), 1)
        self.assertEqual(service.onebot.private_messages[0][0], 2873523107)

    def test_proactive_quiet_hours_cross_midnight(self):
        self.assertTrue(
            AgentService.in_quiet_hours(
                datetime(2026, 10, 20, 23, 45), "23:30", "08:00"
            )
        )
        self.assertTrue(
            AgentService.in_quiet_hours(
                datetime(2026, 10, 20, 7, 30), "23:30", "08:00"
            )
        )
        self.assertFalse(
            AgentService.in_quiet_hours(
                datetime(2026, 10, 20, 12, 0), "23:30", "08:00"
            )
        )

if __name__ == "__main__":
    unittest.main()
