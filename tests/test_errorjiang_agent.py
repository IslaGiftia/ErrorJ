import base64
import json
import http.client
import os
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from errorjiang_agent.brain import AgentBrain
from errorjiang_agent.clients import DeepSeekClient, HotSearchClient
from errorjiang_agent.config import Config
from errorjiang_agent.errors import AgentError
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

    def test_persona_and_web_search_settings_persist(self):
        settings = self.store.save_settings(
            "qq",
            "10001",
            {
                "persona_preset": "温柔",
                "persona_custom_prompt": "少用感叹号，偶尔先说嗯。",
                "web_search_enabled": False,
                "web_search_count": 8,
            },
        )
        self.assertEqual(settings["persona_preset"], "温柔")
        self.assertEqual(settings["web_search_count"], 8)
        self.assertFalse(settings["web_search_enabled"])
        prompt = AgentService.persona_prompt(settings)
        self.assertIn("温柔", prompt)
        self.assertIn("少用感叹号", prompt)

    def test_group_weather_city_is_member_scoped_and_clearable(self):
        self.store.set_group_weather_city(
            "qqbot",
            "group-openid",
            "member-a",
            "西安",
        )
        self.store.set_group_weather_city(
            "qqbot",
            "group-openid",
            "member-b",
            "成都",
        )
        cities = self.store.list_group_weather_cities(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(
            {item["member_id"]: item["city"] for item in cities},
            {"member-a": "西安", "member-b": "成都"},
        )
        self.assertTrue(
            self.store.clear_group_weather_city(
                "qqbot",
                "group-openid",
                "member-a",
            )
        )
        cities = self.store.list_group_weather_cities(
            "qqbot",
            "group-openid",
        )
        self.assertEqual([item["member_id"] for item in cities], ["member-b"])

    def test_group_weather_command_uses_member_and_group_scope(self):
        service = object.__new__(AgentService)
        service.store = self.store
        replies = []
        service.send_reply = lambda event, text: replies.append(text)
        event = MessageEvent(
            self_id="bot",
            user_id="member-a",
            message_type="group",
            chat_id="group-openid",
            message_id="message-1",
            text="设置天气城市 西安",
            to_me=True,
            platform="qqbot",
        )
        self.assertTrue(service.handle_group_weather_command(event))
        cities = self.store.list_group_weather_cities(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(cities[0]["member_id"], "member-a")
        self.assertEqual(cities[0]["city"], "西安")
        self.assertIn("不会保存精确位置", replies[0])

        clear_event = replace(event, text="清除天气城市", message_id="message-2")
        self.assertTrue(service.handle_group_weather_command(clear_event))
        self.assertEqual(
            self.store.list_group_weather_cities("qqbot", "group-openid"),
            [],
        )
        self.assertEqual(replies[-1], "已清除你的天气城市。")

    def test_sticker_usage_updates_for_duplicate_file(self):
        first = self.store.add_sticker("0", "image", "same.png", "QQ图片")
        second = self.store.add_sticker(
            "0",
            "image",
            "same.png",
            "笑哭, 开心",
            source_name="晚安_猫猫.png",
        )
        self.assertEqual(first, second)
        sticker = self.store.list_stickers("0")[0]
        self.assertEqual(sticker["tags"], "笑哭, 开心")
        self.assertEqual(sticker["source_name"], "晚安_猫猫.png")

    def test_existing_sticker_table_migrates_to_category(self):
        path = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(path)
        connection.execute(
            """CREATE TABLE stickers (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   owner_id TEXT NOT NULL,
                   kind TEXT NOT NULL,
                   ref TEXT NOT NULL,
                   tags TEXT NOT NULL DEFAULT '',
                   created_at INTEGER NOT NULL,
                   UNIQUE(owner_id, kind, ref)
               )"""
        )
        connection.execute(
            """INSERT INTO stickers(owner_id, kind, ref, tags, created_at)
               VALUES ('0', 'image', 'legacy.png', '旧标签', 1)"""
        )
        connection.commit()
        connection.close()

        migrated = AgentStore(path)
        sticker = migrated.list_stickers("0")[0]
        self.assertEqual(sticker["category"], "未分类")
        self.assertEqual(sticker["source_name"], "")
        self.assertEqual(sticker["tags"], "旧标签")

    def test_legacy_reminder_table_migrates_retry_fields(self):
        path = Path(self.temp.name) / "legacy-reminders.db"
        connection = sqlite3.connect(path)
        connection.execute(
            """CREATE TABLE reminders (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   platform TEXT NOT NULL,
                   owner_id TEXT NOT NULL,
                   chat_id TEXT NOT NULL,
                   chat_type TEXT NOT NULL,
                   text TEXT NOT NULL,
                   due_at INTEGER NOT NULL,
                   created_at INTEGER NOT NULL,
                   sent_at INTEGER,
                   cancelled_at INTEGER
               )"""
        )
        connection.execute(
            """INSERT INTO reminders(
                   platform, owner_id, chat_id, chat_type, text,
                   due_at, created_at
               ) VALUES ('qqbot', 'owner-openid', 'group-openid', 'group',
                         '旧提醒', 1, 1)"""
        )
        connection.commit()
        connection.close()

        migrated = AgentStore(path)
        reminder = migrated.due_reminders(2)[0]
        self.assertEqual(reminder["attempt_count"], 0)
        self.assertIsNone(reminder["last_attempt_at"])
        self.assertIsNone(reminder["failed_at"])
        self.assertEqual(reminder["last_error"], "")

    def test_custom_sticker_upload_uses_selected_category(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.sticker_dir = Path(self.temp.name) / "stickers"
        service.sticker_dir.mkdir()
        raw = b"\x89PNG\r\n\x1a\n" + b"sticker-data"
        stored = service.save_sticker_upload("0", raw, "cry.png", "泪目")
        self.assertEqual(stored["category"], "泪目")
        self.assertEqual(stored["source_name"], "cry.png")
        self.assertEqual(stored["tags"], "泪目")
        self.assertTrue((service.sticker_dir / stored["ref"]).is_file())
        stickers = self.store.list_stickers("0")
        self.assertEqual(stickers[0]["category"], "泪目")
        self.assertEqual(stickers[0]["source_name"], "cry.png")
        self.assertIn("泪目", self.store.list_sticker_categories("0"))

    def test_sticker_categories_support_bulk_move(self):
        first = self.store.add_sticker(
            "0", "image", "laugh.png", category="笑哭"
        )
        second = self.store.add_sticker(
            "0", "image", "cry.png", category="泪目"
        )
        categories = self.store.list_sticker_categories("0")
        self.assertEqual(categories[0], "未分类")
        self.assertEqual(set(categories), {"未分类", "笑哭", "泪目"})
        moved = self.store.move_stickers("0", [first], "常用")
        self.assertEqual(moved, 1)
        stickers = {
            sticker["id"]: sticker
            for sticker in self.store.list_stickers("0")
        }
        self.assertEqual(stickers[first]["category"], "常用")
        self.assertEqual(stickers[second]["category"], "泪目")
        self.assertIn("常用", self.store.list_sticker_categories("0"))

    def test_admin_sticker_picker_uses_global_pack(self):
        service = object.__new__(AgentService)
        service.store = self.store
        self.store.add_sticker(
            "0", "image", "cry.png", category="泪目"
        )
        context = {
            "platform": "qqbot",
            "owner_id": "admin-openid",
            "is_admin": "1",
            "sticker_enabled": "1",
        }
        result = service.prepare_sticker({"emotion": "泪目"}, context)
        self.assertEqual(result["status"], "selected")
        sticker = service.selected_sticker(context)
        self.assertEqual(sticker["ref"], "cry.png")

    def test_sticker_filename_keywords_ignore_generic_names(self):
        self.assertEqual(
            AgentService.sticker_filename_keywords(
                "晚安_猫猫睡大觉.gif"
            ),
            ["晚安 猫猫睡大觉", "晚安", "猫猫睡大觉"],
        )
        self.assertEqual(
            AgentService.sticker_filename_keywords("微信图片_20261026.png"),
            [],
        )

    def test_sticker_picker_matches_filename_keyword(self):
        service = object.__new__(AgentService)
        service.store = self.store
        self.store.add_sticker(
            "0",
            "image",
            "sleep.png",
            category="未分类",
            source_name="晚安_猫猫睡大觉.png",
        )
        self.store.add_sticker(
            "0",
            "image",
            "laugh.png",
            category="未分类",
            source_name="笑哭_猫猫.png",
        )
        self.store.add_sticker(
            "0",
            "image",
            "category-only.png",
            category="睡大觉",
            source_name="笑哭_猫猫.png",
        )
        context = {
            "platform": "qqbot",
            "owner_id": "admin-openid",
            "is_admin": "1",
            "sticker_enabled": "1",
        }
        result = service.prepare_sticker({"emotion": "睡大觉"}, context)
        self.assertEqual(result["status"], "selected")
        sticker = service.selected_sticker(context)
        self.assertEqual(sticker["ref"], "sleep.png")
        explicit = AgentService.choose_sticker_for_query(
            self.store.list_stickers("0"),
            "来个睡大觉的表情",
        )
        self.assertEqual(explicit["ref"], "sleep.png")

    def test_proactive_target_prefers_qqbot_admin(self):
        self.store.bind_admin("qq", "10001")
        self.store.bind_admin("qqbot", "admin-openid")
        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = SimpleNamespace()
        platform, owners = service.proactive_target()
        self.assertEqual(platform, "qqbot")
        self.assertEqual(owners, ["admin-openid"])

    def test_proactive_failure_does_not_claim_daily_slot(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.proactive_message = lambda *args, **kwargs: "晚上好"

        class FailingQQBot:
            def send_active_message(self, message_type, chat_id, text):
                raise AgentError("send failed")

        service.qqbot = FailingQQBot()
        candidate = {"reason": "晚上问候", "slot": "night"}
        with self.assertRaises(AgentError):
            service.deliver_proactive_candidate(
                "2026-10-26",
                "qqbot",
                "admin-openid",
                {},
                candidate,
                [],
            )
        self.assertEqual(
            self.store.proactive_count("2026-10-26", "admin-openid"),
            0,
        )

    def test_proactive_success_records_slot_and_message(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.proactive_message = lambda *args, **kwargs: "晚上好"

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        service.qqbot = FakeQQBot()
        delivered = service.deliver_proactive_candidate(
            "2026-10-26",
            "qqbot",
            "admin-openid",
            {},
            {"reason": "晚上问候", "slot": "night"},
            [],
        )
        self.assertTrue(delivered)
        self.assertEqual(
            service.qqbot.sent,
            [("private", "admin-openid", "晚上好")],
        )
        self.assertEqual(
            self.store.proactive_count("2026-10-26", "admin-openid"),
            1,
        )

    def test_group_proactive_sends_city_weather_brief(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_proactive_enabled": True,
                "group_weather_enabled": True,
                "group_holiday_enabled": True,
                "group_weather_city": "成都",
                "group_proactive_time": "08:30",
            },
        )
        self.store.set_group_weather_city(
            "qqbot",
            "group-openid",
            "member-openid",
            "西安",
        )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        class FakeErrorJ:
            def tool(self, name, arguments):
                self.last = (name, arguments)
                return {
                    "city": arguments["city"],
                    "casts": [
                        {
                            "date": "2026-10-28",
                            "day_weather": "晴",
                            "night_temp": "10",
                            "day_temp": "20",
                        }
                    ],
                }

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = FakeErrorJ()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        now = datetime(2026, 10, 28, 8, 30)
        service._group_proactive_tick(now)
        self.assertEqual(len(service.qqbot.sent), 1)
        message_type, group_id, text = service.qqbot.sent[0]
        self.assertEqual((message_type, group_id), ("group", "group-openid"))
        self.assertIn("早安", text)
        self.assertIn("西安", text)
        self.assertIn("成都", text)
        self.assertIn("晴", text)
        self.assertEqual(
            self.store.proactive_count(
                "2026-10-28",
                "qqbot-group:group-openid",
            ),
            1,
        )
        self.assertEqual(
            self.store.get_group_messages("qqbot", "group-openid")[-1][
                "content"
            ],
            text,
        )
        service._group_proactive_tick(now)
        self.assertEqual(len(service.qqbot.sent), 1)

    def test_group_proactive_falls_back_to_admin_private(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_proactive_enabled": True,
                "group_weather_enabled": True,
                "group_holiday_enabled": True,
                "group_weather_city": "成都",
                "group_proactive_time": "08:30",
            },
        )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                if message_type == "group":
                    raise AgentError("group denied")
                self.sent.append((message_type, chat_id, text))

        class FakeErrorJ:
            def tool(self, name, arguments):
                return {
                    "city": arguments["city"],
                    "casts": [
                        {
                            "day_weather": "多云",
                            "night_temp": "12",
                            "day_temp": "21",
                        }
                    ],
                }

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = FakeErrorJ()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        service._group_proactive_tick(datetime(2026, 10, 28, 8, 30))
        self.assertEqual(len(service.qqbot.sent), 1)
        message_type, owner_id, text = service.qqbot.sent[0]
        self.assertEqual(
            (message_type, owner_id),
            ("private", "admin-openid"),
        )
        self.assertIn("成都", text)
        self.assertEqual(
            self.store.proactive_count(
                "2026-10-28",
                "qqbot-group:group-openid",
            ),
            1,
        )
        self.assertEqual(
            self.store.get_group_messages("qqbot", "group-openid"),
            [],
        )
        private_messages = self.store.get_messages(
            "qqbot",
            "admin-openid",
            10,
        )
        self.assertEqual(private_messages[-1]["content"], text)

    def test_group_proactive_failure_does_not_claim_slot(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_proactive_enabled": True,
                "group_weather_enabled": True,
                "group_holiday_enabled": True,
                "group_weather_city": "成都",
                "group_proactive_time": "08:30",
            },
        )

        class FakeQQBot:
            def __init__(self):
                self.attempts = []

            def send_active_message(self, message_type, chat_id, text):
                self.attempts.append((message_type, chat_id))
                raise AgentError(f"{message_type} denied")

        class FakeErrorJ:
            def tool(self, name, arguments):
                return {
                    "city": arguments["city"],
                    "casts": [
                        {
                            "day_weather": "晴",
                            "night_temp": "10",
                            "day_temp": "20",
                        }
                    ],
                }

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = FakeErrorJ()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        service._group_proactive_tick(datetime(2026, 10, 28, 8, 30))
        self.assertEqual(
            service.qqbot.attempts,
            [
                ("group", "group-openid"),
                ("private", "admin-openid"),
            ],
        )
        self.assertEqual(
            self.store.proactive_count(
                "2026-10-28",
                "qqbot-group:group-openid",
            ),
            0,
        )
        self.assertEqual(
            self.store.get_group_messages("qqbot", "group-openid"),
            [],
        )

    def test_group_holiday_notice_weekend_and_holiday_eve(self):
        self.assertEqual(
            AgentService.group_holiday_notice(
                datetime(2026, 10, 30, 8, 30)
            ),
            "明天就是周末。",
        )
        self.assertEqual(
            AgentService.group_holiday_notice(
                datetime(2026, 9, 24, 8, 30)
            ),
            "明天开始中秋节假期。",
        )

    def test_group_location_cache_is_member_scoped_and_one_time(self):
        location = {
            "lat": 34.3416,
            "lng": 108.9398,
            "title": "春发芽葫芦头",
            "address": "测试路",
            "coord": "gcj02",
        }
        self.store.save_shared_location(
            "qqbot",
            "group-openid",
            "member-openid",
            location,
        )
        self.assertIsNone(
            self.store.consume_shared_location(
                "qqbot",
                "group-openid",
                "other-member",
            )
        )
        self.assertEqual(
            self.store.consume_shared_location(
                "qqbot",
                "group-openid",
                "member-openid",
            )["title"],
            "春发芽葫芦头",
        )
        self.assertIsNone(
            self.store.consume_shared_location(
                "qqbot",
                "group-openid",
                "member-openid",
            )
        )

    def test_group_location_add_request_detection(self):
        self.assertTrue(
            AgentService.group_location_add_requested("添加刚才的标记点")
        )
        self.assertTrue(
            AgentService.group_location_add_requested("把刚刚的位置存进足迹")
        )
        self.assertFalse(
            AgentService.group_location_add_requested("刚才那个地方好玩吗")
        )

    def test_unmentioned_group_location_is_cached_silently(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset(),
        )
        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="location-share",
            text="",
            to_me=False,
            platform="qqbot",
            location={
                "lat": 34.3416,
                "lng": 108.9398,
                "title": "春发芽葫芦头",
                "address": "测试路",
                "coord": "gcj02",
            },
        )
        service._handle_message_event(event)
        cached = self.store.consume_shared_location(
            "qqbot",
            "group-openid",
            "member-openid",
        )
        self.assertEqual(cached["title"], "春发芽葫芦头")

    def test_location_card_without_coordinates_falls_back_to_amap_search(self):
        calls = []

        class FakeClient:
            def __init__(self, base_url, token, user_id):
                calls.append(("init", base_url, token, user_id))

            def tool(self, name, arguments):
                calls.append(("tool", name, arguments))
                return {
                    "status": "added",
                    "place": {"name": arguments["keywords"]},
                }

        service = object.__new__(AgentService)
        service.config = SimpleNamespace(
            errorjiang_base_url="https://example.com",
            errorjiang_token="token",
        )
        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="location-search",
            text="",
            to_me=True,
            platform="qqbot",
            location={
                "title": "山里的咖啡店",
                "address": "西安市长安区测试路",
                "city": "西安",
                "coord": "gcj02",
            },
        )
        with patch(
            "errorjiang_agent.service.ErrorJClient",
            FakeClient,
        ):
            result = service.add_shared_location(event, 7)
        self.assertEqual(result["status"], "added")
        self.assertEqual(
            calls[-1],
            (
                "tool",
                "footprints.add",
                {
                    "keywords": "山里的咖啡店",
                    "city": "西安",
                },
            ),
        )

    def test_group_at_message_can_consume_cached_location(self):
        self.store.bind_admin("qqbot", "admin-openid")
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            admin_qqs=frozenset(),
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset(),
        )
        service.rate_limiter = SimpleNamespace(allow=lambda _key: True)
        service._chat_locks = defaultdict(threading.Lock)
        captured = {}

        def capture(event, *args, **kwargs):
            captured["event"] = event

        service._process_event = capture
        self.store.save_shared_location(
            "qqbot",
            "group-openid",
            "admin-openid",
            {
                "lat": 34.3416,
                "lng": 108.9398,
                "title": "春发芽葫芦头",
                "address": "测试路",
                "coord": "gcj02",
            },
        )
        event = MessageEvent(
            self_id="bot",
            user_id="admin-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="at-add-location",
            text="添加刚才的标记点",
            to_me=True,
            platform="qqbot",
        )
        service._handle_message_event(event)
        self.assertEqual(
            captured["event"].location["title"],
            "春发芽葫芦头",
        )
        self.assertIsNone(
            self.store.get_shared_location(
                "qqbot",
                "group-openid",
                "admin-openid",
            )
        )

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

    def test_footprint_prepare_uses_bound_site_user_and_confirmation(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            errorjiang_base_url="http://agent.test",
            errorjiang_token="token",
        )

        class FakeClient:
            def __init__(self, base_url, token, user_id):
                self.user_id = user_id

            def tool(self, name, arguments):
                self.name = name
                return {
                    "status": "ready",
                    "place": {
                        "name": "山里的咖啡馆",
                        "address": "测试山路",
                        "status": "wish",
                        "category_name": "",
                    },
                    "possible_duplicates": [],
                }

        with patch("errorjiang_agent.service.ErrorJClient", FakeClient):
            prepared = service.prepare_footprint(
                {
                    "selection_ref": "signed-candidate",
                    "status": "wish",
                    "note": "周末去",
                },
                {
                    "platform": "qqbot",
                    "owner_id": "member-openid",
                    "chat_id": "group-openid",
                    "target_user_id": "7",
                    "tools_enabled": "1",
                },
            )
        self.assertEqual(prepared["status"], "pending_confirmation")
        self.assertIn("山里的咖啡馆", prepared["message"])
        action = self.store.consume_pending(
            "qqbot",
            "member-openid",
            "group-openid",
            prepared["code"],
        )
        self.assertEqual(action["operation"], "footprint_create")
        self.assertEqual(action["target_user_id"], 7)
        self.assertEqual(action["arguments"]["selection_ref"], "signed-candidate")
        self.assertEqual(action["arguments"]["note"], "周末去")

    def test_footprint_confirmation_creates_as_bound_site_user(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            errorjiang_base_url="http://agent.test",
            errorjiang_token="token",
        )
        code, _ = self.store.create_pending(
            "qqbot",
            "member-openid",
            "group-openid",
            {
                "operation": "footprint_create",
                "target_user_id": 7,
                "arguments": {
                    "selection_ref": "signed-candidate",
                    "status": "wish",
                },
            },
        )
        captured = {}

        class FakeClient:
            def __init__(self, base_url, token, user_id):
                captured["user_id"] = user_id

            def tool(self, name, arguments):
                captured["tool"] = name
                captured["arguments"] = arguments
                return {
                    "ok": True,
                    "name": "测试地点",
                    "url": "https://example.com/map?place=42",
                }

        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="message-1",
            text=f"确认 {code}",
            to_me=True,
            platform="qqbot",
        )
        with patch("errorjiang_agent.service.ErrorJClient", FakeClient):
            reply = service.confirm_pending(event, code)
        self.assertIn("已添加足迹「测试地点」", reply)
        self.assertEqual(captured["user_id"], 7)
        self.assertEqual(captured["tool"], "footprints.create")
        self.assertEqual(captured["arguments"]["selection_ref"], "signed-candidate")
        self.assertIsNone(
            self.store.consume_pending(
                "qqbot",
                "member-openid",
                "group-openid",
                code,
            )
        )

    def test_web_chat_can_confirm_footprint_action(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            errorjiang_base_url="http://agent.test",
            errorjiang_token="token",
        )
        code, _ = self.store.create_pending(
            "web",
            "7",
            "7",
            {
                "operation": "footprint_create",
                "target_user_id": 7,
                "arguments": {"selection_ref": "signed-candidate"},
            },
        )

        class FakeClient:
            def __init__(self, base_url, token, user_id):
                pass

            def tool(self, name, arguments):
                return {"ok": True, "name": "网页测试地点"}

        with patch("errorjiang_agent.service.ErrorJClient", FakeClient):
            reply = service.web_chat(7, f"确认 {code}")
        self.assertIn("已添加足迹「网页测试地点」", reply)
        messages = self.store.get_messages("web", "web:7", 10)
        self.assertEqual(messages[-1]["role"], "assistant")

    def test_location_card_is_added_before_ai_reply(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            errorjiang_base_url="http://agent.test",
            errorjiang_token="token",
        )
        sent = []
        service.send_reply = lambda event, text: sent.append(text)
        captured = {}

        class FakeClient:
            def __init__(self, base_url, token, user_id):
                captured["user_id"] = user_id

            def tool(self, name, arguments):
                captured["name"] = name
                captured["arguments"] = arguments
                return {
                    "status": "added",
                    "place": {
                        "name": "春发芽葫芦头",
                        "category_name": "美食",
                        "url": "https://example.com/map?place=88",
                    },
                }

        event = MessageEvent(
            self_id="bot",
            user_id="member",
            message_type="private",
            chat_id="member",
            message_id="message-location",
            text="",
            to_me=True,
            platform="qq",
            location={
                "lat": 34.3416,
                "lng": 108.9398,
                "title": "春发芽葫芦头",
                "address": "测试路",
                "coord": "gcj02",
            },
        )
        with patch("errorjiang_agent.service.ErrorJClient", FakeClient):
            service._process_event(
                event,
                target_user_id=7,
                is_admin=False,
            )
        self.assertEqual(captured["user_id"], 7)
        self.assertEqual(captured["name"], "footprints.location_add")
        self.assertEqual(captured["arguments"]["title"], "春发芽葫芦头")
        self.assertIn("已从位置卡片添加足迹", sent[0])
        self.assertIn("美食", sent[0])

    def test_note_attachments_are_imported_and_replied_with_links(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            errorjiang_base_url="http://agent.test",
            errorjiang_token="token",
        )
        sent = []
        service.send_reply = lambda event, text: sent.append(text)
        service.download_note_attachment = lambda attachment, allow_private=False: (
            b"# note"
        )
        calls = []

        class FakeClient:
            def __init__(self, base_url, token, user_id):
                calls.append(("client", user_id))

            def tool(self, name, arguments):
                calls.append((name, arguments["file_name"]))
                return {
                    "id": 9,
                    "title": arguments["file_name"].rsplit(".", 1)[0],
                    "url": "https://example.com/notes?note=9",
                }

        event = MessageEvent(
            self_id="bot",
            user_id="member",
            message_type="private",
            chat_id="member",
            message_id="message-note",
            text="",
            to_me=True,
            platform="qq",
            attachments=(
                {
                    "filename": "会议记录.md",
                    "url": "https://example.com/meeting.md",
                    "content_type": "text/markdown",
                },
                {
                    "filename": "学习资料.txt",
                    "url": "https://example.com/study.txt",
                    "content_type": "text/plain",
                },
            ),
        )
        with patch("errorjiang_agent.service.ErrorJClient", FakeClient):
            handled = service.import_note_attachments(event, target_user_id=7)
        self.assertTrue(handled)
        self.assertIn(("notes.import", "会议记录.md"), calls)
        self.assertIn(("notes.import", "学习资料.txt"), calls)
        self.assertIn("已导入 2 篇笔记", sent[0])
        self.assertIn("https://example.com/notes?note=9", sent[0])

    def test_note_attachment_name_uses_mime_when_extension_missing(self):
        self.assertEqual(
            AgentService.note_attachment_name(
                {"filename": "会议记录", "content_type": "text/plain"}
            ),
            "会议记录.txt",
        )
        self.assertIsNone(
            AgentService.note_attachment_name(
                {"filename": "图片.png", "content_type": "image/png"}
            )
        )

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

    def test_qqbot_group_reminder_uses_active_group_message(self):
        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, chat_type, chat_id, text):
                self.sent.append((chat_type, chat_id, text))

        service = object.__new__(AgentService)
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        channel = service.send_reminder_delivery(
            {
                "platform": "qqbot",
                "owner_id": "member-openid",
                "chat_id": "group-openid",
                "chat_type": "group",
                "text": "该喝水了",
            }
        )
        self.assertEqual(channel, "group")
        self.assertEqual(
            service.qqbot.sent,
            [("group", "group-openid", "该喝水了")],
        )

    def test_qqbot_group_reminder_falls_back_to_private(self):
        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, chat_type, chat_id, text):
                if chat_type == "group":
                    raise AgentError("group denied")
                self.sent.append((chat_type, chat_id, text))

        service = object.__new__(AgentService)
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        channel = service.send_reminder_delivery(
            {
                "platform": "qqbot",
                "owner_id": "member-openid",
                "chat_id": "group-openid",
                "chat_type": "group",
                "text": "该喝水了",
            }
        )
        self.assertEqual(channel, "private_fallback")
        self.assertEqual(
            service.qqbot.sent,
            [("private", "member-openid", "该喝水了")],
        )

    def test_reminder_failure_backoff_and_terminal_state(self):
        now = int(time.time())
        self.assertFalse(
            AgentService.reminder_retry_ready(
                {
                    "attempt_count": 1,
                    "last_attempt_at": now - 10,
                    "failed_at": None,
                },
                now,
            )
        )
        self.assertTrue(
            AgentService.reminder_retry_ready(
                {
                    "attempt_count": 1,
                    "last_attempt_at": now - 31,
                    "failed_at": None,
                },
                now,
            )
        )
        reminder_id = self.store.add_reminder(
            "qqbot",
            "member-openid",
            "group-openid",
            "group",
            "测试提醒",
            now - 1,
        )
        first = self.store.record_reminder_failure(
            reminder_id,
            "first failure",
            max_attempts=2,
        )
        self.assertEqual(first["attempt_count"], 1)
        self.assertIsNone(first["failed_at"])
        self.assertEqual(
            [item["id"] for item in self.store.due_reminders(now)],
            [reminder_id],
        )
        second = self.store.record_reminder_failure(
            reminder_id,
            "second failure",
            max_attempts=2,
        )
        self.assertEqual(second["attempt_count"], 2)
        self.assertIsNotNone(second["failed_at"])
        self.assertEqual(self.store.due_reminders(now), [])
        self.assertEqual(
            self.store.list_reminders("qqbot", "member-openid"),
            [],
        )

    def test_stale_reminder_is_cancelled_instead_of_delivered_late(self):
        now = int(time.time())
        reminder_id = self.store.add_reminder(
            "qqbot",
            "member-openid",
            "group-openid",
            "group",
            "旧提醒",
            now - 3 * 3600,
        )
        stale = self.store.expire_stale_reminders(
            now,
            2 * 3600,
            "超过补发时限",
        )
        self.assertEqual([item["id"] for item in stale], [reminder_id])
        self.assertEqual(self.store.due_reminders(now), [])
        self.assertEqual(
            self.store.list_reminders("qqbot", "member-openid"),
            [],
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

    def test_qqbot_active_message_has_no_reply_reference(self):
        client = QQBotClient("app", "secret", "bot", lambda event: None)
        client._auth_headers = lambda: {"Authorization": "test"}
        calls = []
        client._http_json = lambda url, payload=None, headers=None: calls.append(
            (url, payload, headers)
        )
        client.send_active_message(
            "private",
            "admin-openid",
            "晚上好",
        )
        self.assertEqual(len(calls), 1)
        self.assertTrue(
            calls[0][0].endswith("/v2/users/admin-openid/messages")
        )
        self.assertEqual(calls[0][1], {"content": "晚上好", "msg_type": 0})

    def test_deepseek_web_search_and_fetch_payloads(self):
        client = DeepSeekClient(
            "https://api.deepseek.com",
            "test-key",
            "deepseek-chat",
        )
        with patch(
            "errorjiang_agent.clients.post_json",
            side_effect=[
                {
                    "results": [
                        {
                            "title": "热梗来源",
                            "url": "https://example.com/meme",
                            "summary": "近期热梗摘要",
                            "date": "2026-10-25T00:00:00Z",
                        }
                    ]
                },
                {
                    "title": "完整文章",
                    "content": "# 正文\n热梗来源说明",
                },
            ],
        ) as request:
            search = client.web_search("最近热梗", 3, "最近有什么热梗")
            fetched = client.web_fetch("https://example.com/meme")
        self.assertTrue(search["untrusted"])
        self.assertEqual(search["results"][0]["title"], "热梗来源")
        self.assertEqual(fetched["title"], "完整文章")
        search_call, fetch_call = request.call_args_list
        self.assertTrue(search_call.args[0].endswith("/tools/search"))
        self.assertEqual(search_call.args[1]["query"], "最近热梗")
        self.assertEqual(search_call.args[1]["count"], 3)
        self.assertEqual(
            search_call.args[1]["ori_question"],
            "最近有什么热梗",
        )
        self.assertTrue(fetch_call.args[0].endswith("/tools/fetch"))
        self.assertEqual(
            fetch_call.args[1]["url"],
            "https://example.com/meme",
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

    def test_qqbot_file_url_upload_sends_media_message(self):
        client = QQBotClient("app", "secret", "bot", lambda event: None)
        client._auth_headers = lambda: {"Authorization": "test"}
        calls = []

        class FakeDownload:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return b"book-data"

        def fake_http(url, payload=None, headers=None):
            calls.append((url, payload, headers))
            if url.endswith("/files"):
                return {"file_info": "file-info"}
            return {"id": "sent"}

        client._http_json = fake_http
        with patch(
            "errorjiang_agent.qqbot.urlopen",
            return_value=FakeDownload(),
        ):
            client.send_file_from_url(
                "private",
                "user-openid",
                "message-id",
                "book.epub",
                "https://zhexiyan.cc/signed",
            )
        self.assertTrue(calls[0][0].endswith("/users/user-openid/files"))
        self.assertEqual(calls[0][1]["file_type"], 4)
        self.assertEqual(calls[0][1]["file_name"], "book.epub")
        self.assertIn("file_data", calls[0][1])
        self.assertEqual(calls[1][1]["msg_type"], 7)

    def test_qqbot_large_file_uses_chunked_upload(self):
        client = QQBotClient("app", "secret", "bot", lambda event: None)
        client._auth_headers = lambda: {"Authorization": "test"}
        calls = []
        raw = b"x" * (4 * 1024 * 1024)

        def fake_http(url, payload=None, headers=None):
            calls.append((url, payload, headers))
            if url.endswith("/upload_prepare"):
                return {
                    "upload_id": "upload-1",
                    "block_size": str(len(raw)),
                    "parts": [
                        {
                            "index": 1,
                            "presigned_url": "https://upload.example/part",
                            "block_size": str(len(raw)),
                        }
                    ],
                }
            if url.endswith("/upload_part_finish"):
                return {}
            return {"file_info": "file-info"}

        class FakeDownload:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return raw

        class FakePut:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        client._http_json = fake_http
        with patch(
            "errorjiang_agent.qqbot.urlopen",
            side_effect=[FakeDownload(), FakePut()],
        ):
            file_info = client.upload_file_from_url(
                "group",
                "group-openid",
                "large.mp3",
                "https://zhexiyan.cc/signed",
            )
        self.assertEqual(file_info, "file-info")
        self.assertTrue(
            any(url.endswith("/upload_prepare") for url, _, _ in calls)
        )
        merged = [
            payload
            for url, payload, _ in calls
            if url.endswith("/files")
        ][0]
        self.assertEqual(merged["upload_id"], "upload-1")

    def test_content_send_callback_records_selected_file(self):
        class ContentClient:
            def __init__(self, *args):
                pass

            def tool(self, name, arguments):
                self.name = name
                return {
                    "status": "file",
                    "kind": "book",
                    "id": 3,
                    "file_name": "book.epub",
                    "url": "https://zhexiyan.cc/signed",
                }

        service = object.__new__(AgentService)
        service.config = SimpleNamespace(
            errorjiang_base_url="http://127.0.0.1:8000",
            errorjiang_token="token",
        )
        context = {
            "platform": "qqbot",
            "owner_id": "member-openid",
            "target_user_id": "3",
        }
        with patch("errorjiang_agent.service.ErrorJClient", ContentClient):
            result = service.prepare_content_send(
                {"kind": "book", "id": 3},
                context,
            )
        self.assertEqual(result["status"], "file")
        selected = json.loads(context["selected_content"])
        self.assertEqual(selected["file_name"], "book.epub")

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

    def test_qqbot_image_without_mime_uses_magic_and_usage(self):
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
            user_id="admin-openid",
            message_type="private",
            chat_id="admin-openid",
            message_id="message-id",
            text="保存表情 笑哭",
            to_me=True,
            platform="qqbot",
            attachments=(
                {
                    "filename": "laugh.png",
                    "url": "https://example.com/laugh.png",
                },
            ),
        )
        with patch(
            "errorjiang_agent.service.urlopen",
            return_value=FakeResponse(),
        ):
            saved = service.save_qqbot_attachments(event, "0")
        self.assertEqual(saved, 1)
        sticker = self.store.list_stickers("0")[0]
        self.assertIn("笑哭", sticker["tags"])
        self.assertTrue(
            (service.sticker_dir / sticker["ref"]).is_file()
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

    def test_onebot_location_cq_code_is_parsed(self):
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "private",
                "self_id": 20000,
                "user_id": 10001,
                "message_id": 11,
                "raw_message": (
                    "[CQ:location,lat=34.3416,lon=108.9398,"
                    "title=%E6%98%A5%E5%8F%91%E8%8A%BD%E8%91%AB%E8%8A%A6%E5%A4%B4,"
                    "content=%E8%A5%BF%E5%AE%89%E5%B8%82%E6%B5%8B%E8%AF%95%E8%B7%AF]"
                ),
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.location["lat"], 34.3416)
        self.assertEqual(event.location["lng"], 108.9398)
        self.assertEqual(event.location["title"], "春发芽葫芦头")
        self.assertEqual(event.location["address"], "西安市测试路")

    def test_onebot_json_location_card_is_parsed(self):
        card = json.dumps(
            {
                "meta": {
                    "location": {
                        "lat": "34.2",
                        "lng": "108.8",
                        "title": "JSON 位置",
                        "address": "测试地址",
                    }
                }
            },
            ensure_ascii=False,
        )
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "private",
                "self_id": 20000,
                "user_id": 10001,
                "message_id": 12,
                "message": [
                    {"type": "json", "data": {"data": card}},
                ],
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.location["title"], "JSON 位置")

    def test_onebot_file_segment_is_parsed(self):
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "private",
                "self_id": 20000,
                "user_id": 10001,
                "message_id": 13,
                "message": [
                    {
                        "type": "file",
                        "data": {
                            "name": "测试笔记.md",
                            "url": "https://example.com/files/note.md",
                        },
                    }
                ],
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.attachments[0]["filename"], "测试笔记.md")
        self.assertEqual(
            event.attachments[0]["url"],
            "https://example.com/files/note.md",
        )

    def test_onebot_cq_file_is_parsed(self):
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "private",
                "self_id": 20000,
                "user_id": 10001,
                "message_id": 14,
                "raw_message": (
                    "[CQ:file,name=%E6%B5%8B%E8%AF%95.docx,"
                    "url=https%3A%2F%2Fexample.com%2Ffiles%2Ftest.docx]"
                ),
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.attachments[0]["filename"], "测试.docx")

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

    def test_qqbot_location_element_is_parsed(self):
        event = parse_qqbot_event(
            "C2C_MESSAGE_CREATE",
            {
                "id": "message-location",
                "content": "",
                "author": {
                    "user_openid": "user-openid",
                    "username": "星星",
                },
                "msg_elements": [
                    {
                        "type": "location",
                        "data": {
                            "lat": 34.1,
                            "lng": 108.9,
                            "title": "QQ 位置",
                            "address": "位置地址",
                        },
                    }
                ],
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.location["title"], "QQ 位置")
        self.assertEqual(event.location["coord"], "gcj02")

    def test_qqbot_full_group_map_ark_card_is_parsed(self):
        event = parse_qqbot_event(
            "GROUP_MESSAGE_CREATE",
            {
                "id": "message-map-ark",
                "content": " ",
                "group_openid": "group-openid",
                "author": {
                    "member_openid": "member-openid",
                    "username": "星星",
                },
                "ark_data": {
                    "ark_type": "map",
                    "fields": {
                        "title": "春发芽葫芦头",
                        "address": "西安市雁塔区测试路",
                        "jump_url": (
                            "https://uri.amap.com/marker?"
                            "position=108.9398,34.3416&name=test"
                        ),
                    },
                },
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertFalse(event.to_me)
        self.assertEqual(event.message_type, "group")
        self.assertEqual(event.location["title"], "春发芽葫芦头")
        self.assertAlmostEqual(event.location["lat"], 34.3416)
        self.assertAlmostEqual(event.location["lng"], 108.9398)

    def test_qqbot_full_group_message_detects_bot_mention(self):
        event = parse_qqbot_event(
            "GROUP_MESSAGE_CREATE",
            {
                "id": "message-full-at",
                "content": "<@bot-openid> 添加刚才的标记点",
                "group_openid": "group-openid",
                "author": {
                    "member_openid": "member-openid",
                    "username": "星星",
                },
                "mentions": [
                    {
                        "id": "bot-openid",
                        "member_openid": "bot-openid",
                        "username": "折兮颜",
                        "bot": True,
                    }
                ],
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertTrue(event.to_me)
        self.assertEqual(event.message_type, "group")
        self.assertEqual(event.text, "添加刚才的标记点")

    def test_qqbot_map_ark_without_coordinates_keeps_search_fields(self):
        event = parse_qqbot_event(
            "GROUP_MESSAGE_CREATE",
            {
                "id": "message-map-search",
                "content": " ",
                "group_openid": "group-openid",
                "author": {
                    "member_openid": "member-openid",
                    "username": "星星",
                },
                "ark_data": {
                    "ark_type": "map",
                    "fields": {
                        "title": "山里的咖啡店",
                        "address": "西安市长安区测试路",
                        "jump_url": "https://surl.amap.com/abc123",
                    },
                },
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.location["title"], "山里的咖啡店")
        self.assertEqual(event.location["address"], "西安市长安区测试路")
        self.assertNotIn("lat", event.location)

    def test_qqbot_file_attachment_is_parsed(self):
        event = parse_qqbot_event(
            "C2C_MESSAGE_CREATE",
            {
                "id": "message-file",
                "content": "",
                "author": {
                    "user_openid": "user-openid",
                    "username": "星星",
                },
                "attachments": [
                    {
                        "filename": "会议记录.txt",
                        "content_type": "text/plain",
                        "url": "https://example.com/files/meeting.txt",
                    }
                ],
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.attachments[0]["filename"], "会议记录.txt")
        self.assertEqual(event.attachments[0]["content_type"], "text/plain")


class HotSearchClientTests(unittest.TestCase):
    def test_fetches_weibo_bilibili_and_douyin_lists(self):
        responses = [
            {
                "ok": 1,
                "data": {
                    "realtime": [
                        {
                            "word": "微博测试",
                            "word_scheme": "#微博测试#",
                            "num": 123,
                            "realpos": 1,
                        }
                    ]
                },
            },
            {
                "code": 0,
                "data": {
                    "trending": {
                        "list": [
                            {
                                "keyword": "B站测试",
                                "heat_score": 456,
                            }
                        ]
                    }
                },
            },
            {
                "data": {
                    "word_list": [
                        {
                            "word": "抖音测试",
                            "hot_value": 789,
                            "position": 1,
                        }
                    ]
                }
            },
        ]
        client = HotSearchClient()
        with patch(
            "errorjiang_agent.clients.get_json",
            side_effect=responses,
        ) as get_json:
            result = client.fetch("all", 2)
        self.assertTrue(result["untrusted"])
        self.assertEqual(
            [item["label"] for item in result["lists"]],
            ["微博热搜", "B站热搜", "抖音热搜"],
        )
        self.assertEqual(
            [item["items"][0]["title"] for item in result["lists"]],
            ["微博测试", "B站测试", "抖音测试"],
        )
        self.assertEqual(get_json.call_count, 3)

    def test_weibo_item_has_search_link_and_heat(self):
        client = HotSearchClient()
        with patch(
            "errorjiang_agent.clients.get_json",
            return_value={
                "ok": 1,
                "data": {
                    "realtime": [
                        {
                            "word": "测试热搜",
                            "word_scheme": "#测试热搜#",
                            "num": 999,
                        }
                    ]
                },
            },
        ):
            result = client.fetch("weibo", 1)
        item = result["lists"][0]["items"][0]
        self.assertEqual(item["heat"], 999)
        self.assertIn("s.weibo.com", item["url"])


class FakeDeepSeek:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, tools):
        return self.replies.pop(0)


class FakeSearchDeepSeek(FakeDeepSeek):
    def __init__(self, replies):
        super().__init__(replies)
        self.search_calls = []
        self.seen_systems = []
        self.seen_tools = []

    def chat(self, messages, tools):
        self.seen_systems.append(str(messages[0].get("content") or ""))
        self.seen_tools.append(
            {
                str(tool.get("function", {}).get("name") or "")
                for tool in tools
            }
        )
        return super().chat(messages, tools)

    def web_search(self, query, count=5, original_question=""):
        self.search_calls.append((query, count, original_question))
        return {
            "query": query,
            "untrusted": True,
            "results": [
                {
                    "title": "热梗来源",
                    "url": "https://example.com/meme",
                }
            ],
        }


class FakeErrorJ:
    def __init__(self):
        self.calls = []

    def tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"count": 1, "results": [{"part_number": "STM32F103C8T6"}]}


class FakeHotSearch:
    def __init__(self):
        self.calls = []

    def fetch(self, source="all", limit=10):
        self.calls.append((source, limit))
        return {
            "source": source,
            "untrusted": True,
            "lists": [
                {
                    "source": "weibo",
                    "label": "微博热搜",
                    "items": [{"rank": 1, "title": "测试热搜"}],
                }
            ],
        }


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

    def test_weather_tool_mapping(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-weather",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_weather_forecast",
                                "arguments": json.dumps({"city": "西安"}),
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "西安今天晴。"},
            ]
        )
        errorjiang = FakeErrorJ()
        brain = AgentBrain(deepseek, errorjiang, lambda args, context: {})
        self.assertEqual(
            brain.reply("西安天气怎么样？", [], {"tools_enabled": "1"}),
            "西安今天晴。",
        )
        self.assertEqual(
            errorjiang.calls,
            [("weather.forecast", {"city": "西安"})],
        )

    def test_hot_search_tool_mapping(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-hot",
                            "type": "function",
                            "function": {
                                "name": "web_hot_search",
                                "arguments": json.dumps(
                                    {"source": "weibo", "limit": 3}
                                ),
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "微博热搜第一是测试热搜。"},
            ]
        )
        hot_search = FakeHotSearch()
        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
            hot_search=hot_search,
        )
        reply = brain.reply(
            "微博热搜是什么？",
            [],
            {
                "tools_enabled": "1",
                "web_search_enabled": "1",
            },
        )
        self.assertIn("测试热搜", reply)
        self.assertEqual(hot_search.calls, [("weibo", 3)])

    def test_web_search_tool_and_persona_context(self):
        deepseek = FakeSearchDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-search",
                            "type": "function",
                            "function": {
                                "name": "deepseek_web_search",
                                "arguments": json.dumps(
                                    {
                                        "query": "最近热梗",
                                        "count": 2,
                                    }
                                ),
                            },
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "最近热梗来源：https://example.com/meme",
                },
            ]
        )
        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
        )
        reply = brain.reply(
            "最近有什么热梗？",
            [],
            {
                "tools_enabled": "1",
                "web_search_enabled": "1",
                "web_search_count": "5",
                "persona_prompt": "温柔，少用感叹号。",
            },
        )
        self.assertIn("example.com/meme", reply)
        self.assertEqual(
            deepseek.search_calls,
            [("最近热梗", 2, "最近有什么热梗？")],
        )
        self.assertIn("温柔，少用感叹号", deepseek.seen_systems[0])
        self.assertIn("deepseek_web_search", deepseek.seen_tools[0])

    def test_web_search_disabled_is_hidden_from_model(self):
        deepseek = FakeSearchDeepSeek(
            [{"role": "assistant", "content": "普通回复"}]
        )
        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
        )
        reply = brain.reply(
            "最近有什么热梗？",
            [],
            {
                "tools_enabled": "1",
                "web_search_enabled": "0",
            },
        )
        self.assertEqual(reply, "普通回复")
        self.assertNotIn("deepseek_web_search", deepseek.seen_tools[0])
        self.assertNotIn("deepseek_web_fetch", deepseek.seen_tools[0])
        self.assertNotIn("web_hot_search", deepseek.seen_tools[0])

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

    def test_footprint_tools_are_mapped_to_internal_api(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-footprints-search",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_footprints_search",
                                "arguments": json.dumps(
                                    {
                                        "province": "陕西省",
                                        "city": "宝鸡市",
                                        "district": "千阳县",
                                        "category": "美食",
                                        "status": "visited",
                                    }
                                ),
                            },
                        },
                        {
                            "id": "call-footprints-poi",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_footprints_poi_search",
                                "arguments": json.dumps(
                                    {"keywords": "西湖咖啡馆", "city": "杭州"}
                                ),
                            },
                        },
                        {
                            "id": "call-footprints-add",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_footprints_add",
                                "arguments": json.dumps(
                                    {"keywords": "春发芽葫芦头", "city": "西安"}
                                ),
                            },
                        },
                    ],
                },
                {"role": "assistant", "content": "查到了。"},
            ]
        )
        errorjiang = FakeErrorJ()
        brain = AgentBrain(deepseek, errorjiang, lambda args, context: {})
        self.assertEqual(brain.reply("找一下足迹，再搜一个新地点", []), "查到了。")
        self.assertEqual(
            errorjiang.calls,
            [
                (
                    "footprints.search",
                    {
                        "province": "陕西省",
                        "city": "宝鸡市",
                        "district": "千阳县",
                        "category": "美食",
                        "status": "visited",
                    },
                ),
                (
                    "footprints.poi_search",
                    {"keywords": "西湖咖啡馆", "city": "杭州"},
                ),
                (
                    "footprints.add",
                    {"keywords": "春发芽葫芦头", "city": "西安"},
                ),
            ],
        )

    def test_footprint_prepare_receives_current_chat_context(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-footprint-prepare",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_footprints_prepare",
                                "arguments": json.dumps(
                                    {"selection_ref": "candidate-1", "status": "wish"}
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

        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
            prepare_footprint=prepare,
        )
        reply = brain.reply(
            "添加第一个",
            [],
            {
                "platform": "qq",
                "owner_id": "10001",
                "chat_id": "10001",
                "target_user_id": "7",
            },
        )
        self.assertEqual(reply, "请确认。")
        self.assertEqual(captured["arguments"]["selection_ref"], "candidate-1")
        self.assertEqual(captured["context"]["target_user_id"], "7")

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

    def test_content_search_and_send_tools_are_dispatched(self):
        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-search",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_content_search",
                                "arguments": json.dumps(
                                    {
                                        "kind": "book",
                                        "query": "STM32",
                                    }
                                ),
                            },
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "找到一本书。",
                },
            ]
        )
        errorjiang = FakeErrorJ()
        brain = AgentBrain(
            deepseek,
            errorjiang,
            lambda args, context: {},
        )
        self.assertEqual(
            brain.reply("找一本 STM32 的书", []),
            "找到一本书。",
        )
        self.assertEqual(
            errorjiang.calls,
            [
                (
                    "content.search",
                    {"kind": "book", "query": "STM32"},
                )
            ],
        )

        deepseek = FakeDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-send",
                            "type": "function",
                            "function": {
                                "name": "errorjiang_content_send",
                                "arguments": json.dumps(
                                    {"kind": "book", "id": 3}
                                ),
                            },
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "正在发。",
                },
            ]
        )
        captured = {}

        def prepare_content(arguments, context):
            captured["arguments"] = arguments
            return {"status": "file"}

        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
            prepare_content_send=prepare_content,
        )
        self.assertEqual(
            brain.reply(
                "把第三本书发我",
                [],
                {"tools_enabled": "1"},
            ),
            "正在发。",
        )
        self.assertEqual(captured["arguments"], {"kind": "book", "id": 3})


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

    def test_footprint_candidate_signature_rejects_tampering(self):
        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "agent-test-token"},
            clear=False,
        ):
            reference = app.encode_footprint_candidate(
                {
                    "source": "amap",
                    "name": "测试地点",
                    "address": "测试地址",
                    "lat": 30.123456,
                    "lng": 120.654321,
                }
            )
            candidate = app.decode_footprint_candidate(reference)
            self.assertEqual(candidate["name"], "测试地点")
            with self.assertRaises(ValueError):
                app.decode_footprint_candidate(reference[:-2] + "AA")

    def test_amap_gcj_coordinate_is_converted_for_storage(self):
        lat, lng = app.gcj02_to_wgs84(30.280001, 120.155001)
        self.assertNotEqual((lat, lng), (30.280001, 120.155001))
        self.assertAlmostEqual(lat, 30.280001, delta=0.01)
        self.assertAlmostEqual(lng, 120.155001, delta=0.01)
        self.assertEqual(app.gcj02_to_wgs84(51.5, -0.12), (51.5, -0.12))

    def test_amap_weather_uses_city_adcode_and_returns_forecast(self):
        class FakeResponse:
            def __init__(self, payload):
                self.raw = json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return self.raw

        handler = self.make_handler({})
        responses = [
            FakeResponse(
                {
                    "status": "1",
                    "geocodes": [
                        {"city": "西安市", "adcode": "610100"}
                    ],
                }
            ),
            FakeResponse(
                {
                    "status": "1",
                    "forecasts": [
                        {
                            "city": "西安市",
                            "casts": [
                                {
                                    "date": "2026-10-28",
                                    "week": "3",
                                    "dayweather": "晴",
                                    "nightweather": "多云",
                                    "daytemp": "20",
                                    "nighttemp": "10",
                                    "daywind": "东北",
                                    "daypower": "1-3",
                                }
                            ],
                        }
                    ],
                }
            ),
        ]
        with patch.object(app, "AMAP_WEB_KEY", "test-key"), patch.object(
            app,
            "AMAP_POI_CACHE",
            {},
        ), patch.object(app, "urlopen", side_effect=responses):
            result = handler.amap_weather_forecast("西安")
        self.assertEqual(result["city"], "西安市")
        self.assertEqual(result["adcode"], "610100")
        self.assertEqual(result["casts"][0]["day_weather"], "晴")
        self.assertEqual(result["casts"][0]["night_temp"], "10")

    def test_weather_tool_is_owner_only_and_returns_city_forecast(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        handler.amap_weather_forecast = lambda city: {
            "city": city,
            "adcode": "610100",
            "casts": [{"day_weather": "晴"}],
        }
        handler.agent_tool_weather_forecast(
            {"kind": "owner", "user_id": 0},
            {"city": "西安"},
        )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["city"], "西安")

        with patch.object(app, "api_error") as api_error:
            handler.agent_tool_weather_forecast(
                {"kind": "member", "user_id": 7},
                {"city": "西安"},
            )
        api_error.assert_called_once_with(
            handler,
            403,
            "当前账号没有天气查询权限。",
        )

    def test_footprint_search_returns_existing_places(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        identity = {"kind": "owner", "user_id": 0}
        rows = [
            {
                "id": 8,
                "name": "西湖咖啡馆",
                "address": "湖边",
                "status": "visited",
                "rating": 5,
                "lat": 30.2,
                "lng": 120.1,
                "created_by": 0,
                "created_by_name": None,
            }
        ]
        with patch.object(app, "query", return_value=rows):
            handler.agent_tool_footprints_search(
                identity,
                {"query": "咖啡馆", "status": "visited"},
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["count"], 1)
        self.assertEqual(captured["payload"]["results"][0]["name"], "西湖咖啡馆")
        self.assertTrue(
            captured["payload"]["results"][0]["url"].endswith("/map?place=8")
        )

    def test_footprint_area_terms_remove_generic_suffixes(self):
        handler = self.make_handler({})
        self.assertEqual(
            handler.agent_footprint_area_terms("西安市区"),
            ["西安市区", "西安"],
        )
        self.assertEqual(
            handler.agent_footprint_area_terms("雁塔区"),
            ["雁塔区", "雁塔"],
        )
        self.assertEqual(
            handler.agent_footprint_area_terms("西安市"),
            ["西安市", "西安"],
        )
        self.assertEqual(
            handler.agent_footprint_area_terms("陕西省"),
            ["陕西省", "陕西"],
        )
        region = handler.agent_footprint_region("陕西省宝鸡市千阳县")
        self.assertEqual(region["province"], "陕西省")
        self.assertEqual(region["city"], "宝鸡市")
        self.assertEqual(region["district"], "千阳县")

    def test_footprint_search_matches_county_by_anchor_and_category(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        candidates = [
            {
                "id": 9,
                "name": "千阳小馆",
                "address": None,
                "category_name": "美食",
                "parent_category_name": None,
                "status": "",
                "rating": 0,
                "lat": 34.641,
                "lng": 107.391,
                "created_by": 0,
                "created_by_name": None,
            }
        ]
        anchors = [{"lat": 34.640, "lng": 107.390}]
        with patch.object(
            app,
            "query",
            side_effect=[candidates, anchors],
        ) as query_mock:
            handler.agent_tool_footprints_search(
                {"kind": "owner", "user_id": 0},
                {
                    "province": "陕西省",
                    "city": "宝鸡市",
                    "district": "千阳县",
                    "category": "美食",
                    "limit": 8,
                },
            )
        candidate_sql, candidate_params = query_mock.call_args_list[0].args
        anchor_sql, anchor_params = query_mock.call_args_list[1].args
        self.assertIn("c.name LIKE ?", candidate_sql)
        self.assertIn("%美食%", candidate_params)
        self.assertIn("%串串%", candidate_params)
        self.assertIn("%特色小吃%", candidate_params)
        self.assertIn("%千阳县%", anchor_params)
        self.assertIn("%千阳%", anchor_params)
        self.assertIn("p.address LIKE ?", anchor_sql)
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["province"], "陕西省")
        self.assertEqual(captured["payload"]["city"], "宝鸡市")
        self.assertEqual(captured["payload"]["district"], "千阳县")
        self.assertEqual(captured["payload"]["region_level"], "district")
        self.assertEqual(captured["payload"]["region_radius_km"], 20.0)
        self.assertEqual(captured["payload"]["count"], 1)
        self.assertIsNotNone(
            captured["payload"]["results"][0]["distance_meters"]
        )

    def test_private_map_blocks_member_footprint_tools(self):
        handler = self.make_handler({})
        identity = {"kind": "member", "user_id": 7}
        with patch.object(app, "MAP_PUBLIC", False), patch.object(
            app, "user_has_permission", return_value=True
        ), patch.object(app, "api_error") as api_error:
            handler.agent_tool_footprints_search(identity, {"query": "咖啡馆"})
        api_error.assert_called_once_with(
            handler, 403, "当前账号没有查看足迹的权限。"
        )

    def test_footprint_poi_search_returns_signed_wgs_candidate(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        identity = {"kind": "owner", "user_id": 0}
        amap_result = {
            "pois": [
                {
                    "id": "poi-1",
                    "name": "西湖咖啡馆",
                    "address": "湖边",
                    "type": "餐饮",
                    "lat": 30.280001,
                    "lng": 120.155001,
                }
            ]
        }
        categories = [{"id": 2, "name": "咖啡馆", "parent_id": None}]
        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "agent-test-token"},
            clear=False,
        ), patch.object(app, "AMAP_WEB_KEY", "test-key"), patch.object(
            handler, "amap_poi_search", return_value=amap_result
        ), patch.object(app, "rate_allow", return_value=True), patch.object(
            app, "query", return_value=categories
        ):
            handler.agent_tool_footprints_poi_search(
                identity,
                {"keywords": "西湖咖啡馆", "city": "杭州"},
            )
            result = captured["payload"]["results"][0]
            candidate = app.decode_footprint_candidate(result["selection_ref"])
        self.assertEqual(captured["status"], 200)
        self.assertEqual(candidate["name"], "西湖咖啡馆")
        self.assertNotEqual(candidate["lat"], 30.280001)
        self.assertAlmostEqual(candidate["lat"], 30.280001, delta=0.01)
        self.assertEqual(captured["payload"]["categories"][0]["id"], 2)

    def test_footprint_category_strong_name_filter(self):
        handler = self.make_handler({})
        with patch.object(
            app, "query_one", return_value={"id": 14}
        ):
            category_id = handler.agent_footprint_category_id(
                "春发芽葫芦头",
                "",
            )
        with patch.object(app, "query_one") as query_one:
            self.assertIsNone(
                handler.agent_footprint_category_id("普通地点", "")
            )
        self.assertEqual(category_id, 14)
        query_one.assert_not_called()

    def test_footprint_auto_add_selects_best_amap_result(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        handler.amap_poi_search = lambda keywords, city="": {
            "pois": [
                {
                    "name": "春发芽葫芦头（测试店）",
                    "address": "测试路 1 号",
                    "type": "餐饮服务;中餐厅",
                    "lat": 34.3416,
                    "lng": 108.9398,
                }
            ]
        }
        stored = {}

        def store(identity, candidate, metadata, source):
            stored.update(
                {
                    "candidate": candidate,
                    "metadata": metadata,
                    "source": source,
                }
            )
            return {
                "id": 91,
                "name": candidate["name"],
                "category_name": "美食",
                "url": "https://example.com/map?place=91",
            }

        with patch.object(app, "AMAP_WEB_KEY", "test-key"), patch.object(
            app, "rate_allow", return_value=True
        ), patch.object(
            handler, "agent_footprint_duplicate", return_value=None
        ), patch.object(
            handler, "agent_store_footprint", side_effect=store
        ):
            handler.agent_tool_footprints_add(
                {"kind": "owner", "user_id": 0},
                {"keywords": "春发芽葫芦头", "city": "西安"},
            )
        self.assertEqual(captured["status"], 201)
        self.assertEqual(captured["payload"]["status"], "added")
        self.assertEqual(stored["candidate"]["name"], "春发芽葫芦头（测试店）")
        self.assertEqual(stored["metadata"]["status"], "")
        self.assertIn("高德自动搜索", stored["source"])

    def test_footprint_auto_add_returns_selection_link_when_not_found(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        handler.amap_poi_search = lambda keywords, city="": {"pois": []}
        with patch.object(app, "AMAP_WEB_KEY", "test-key"), patch.object(
            app, "rate_allow", return_value=True
        ):
            handler.agent_tool_footprints_add(
                {"kind": "owner", "user_id": 0},
                {"keywords": "山里的小店", "city": "西安"},
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["status"], "not_found")
        self.assertIn("/map?add=1", captured["payload"]["fallback_url"])

    def test_location_card_uses_gcj_coordinates_and_category(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        stored = {}

        def store(identity, candidate, metadata, source):
            stored["candidate"] = candidate
            stored["source"] = source
            return {
                "id": 92,
                "name": candidate["name"],
                "category_name": "美食",
                "url": "https://example.com/map?place=92",
            }

        with patch.object(
            handler, "agent_footprint_duplicate", return_value=None
        ), patch.object(
            handler, "agent_store_footprint", side_effect=store
        ):
            handler.agent_tool_footprints_location_add(
                {"kind": "owner", "user_id": 0},
                {
                    "lat": 34.3416,
                    "lng": 108.9398,
                    "title": "春发芽葫芦头",
                    "address": "测试路",
                    "coord": "gcj02",
                },
            )
        self.assertEqual(captured["status"], 201)
        self.assertNotEqual(stored["candidate"]["lat"], 34.3416)
        self.assertEqual(stored["candidate"]["name"], "春发芽葫芦头")
        self.assertIn("位置卡片", stored["source"])

    def test_footprint_create_requires_confirmed_signed_candidate(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        handler.log_activity = lambda *args, **kwargs: None
        identity = {
            "kind": "member",
            "user_id": 7,
            "username": "member",
            "nickname": "成员",
        }
        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "agent-test-token"},
            clear=False,
        ):
            reference = app.encode_footprint_candidate(
                {
                    "source": "amap",
                    "name": "测试地点",
                    "address": "测试地址",
                    "lat": 30.2,
                    "lng": 120.1,
                }
            )
            with patch.object(
                app, "user_has_permission", return_value=True
            ), patch.object(
                app, "query_one", return_value={"nickname": "成员", "username": "member"}
            ), patch.object(
                app, "execute", return_value=42
            ) as execute, patch.object(
                app, "notify_async"
            ) as notify_async:
                handler.agent_tool_footprints_create(
                    identity,
                    {
                        "selection_ref": reference,
                        "status": "wish",
                        "note": "周末去",
                    },
                )
        self.assertEqual(captured["status"], 201)
        self.assertEqual(captured["payload"]["id"], 42)
        self.assertEqual(captured["payload"]["name"], "测试地点")
        self.assertIn("INSERT INTO map_places", execute.call_args.args[0])
        notify_async.assert_called_once()

    def test_footprint_map_link_encodes_fallback_fields(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        handler.agent_tool_footprints_map_link(
            {"kind": "owner", "user_id": 0},
            {"name": "山里的店", "address": "测试山路", "note": "没有门牌"},
        )
        self.assertEqual(captured["status"], 200)
        url = captured["payload"]["url"]
        self.assertIn("/map?add=1", url)
        self.assertIn("%E5%B1%B1%E9%87%8C%E7%9A%84%E5%BA%97", url)

    def test_map_poi_around_returns_merchant_layer_data(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        handler.amap_poi_around = lambda lat, lng, radius: {
            "count": 1,
            "radius": radius,
            "coord": "gcj02",
            "pois": [
                {
                    "id": "merchant-1",
                    "name": "测试咖啡馆",
                    "type": "餐饮服务;咖啡厅",
                    "lat": 34.34,
                    "lng": 108.94,
                }
            ],
        }
        with patch.object(app, "AMAP_WEB_KEY", "test-key"), patch.object(
            app, "rate_allow", return_value=True
        ):
            handler.api_map_poi_around(
                {
                    "lat": ["34.3416"],
                    "lng": ["108.9398"],
                    "radius": ["1200"],
                }
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["pois"][0]["name"], "测试咖啡馆")
        self.assertEqual(captured["payload"]["radius"], 1200)

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

    def test_agent_sticker_upload_forwards_category_to_global_pack(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        raw = b"\x89PNG\r\n\x1a\nsticker"
        with patch.object(
            app,
            "agent_internal_request",
            return_value={"ok": True, "sticker": {"id": 1}},
        ) as request:
            handler.api_agent_web_sticker_upload(
                {
                    "file_name": "cry.png",
                    "category": "泪目",
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        self.assertEqual(captured["status"], 200)
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/sticker/upload")
        self.assertEqual(args[1]["owner_id"], "0")
        self.assertEqual(args[1]["category"], "泪目")

    def test_agent_sticker_category_create_and_move_forward(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        responses = []
        handler.send_json = lambda status, payload: responses.append(
            (status, payload)
        )
        with patch.object(
            app,
            "agent_internal_request",
            side_effect=[
                {
                    "ok": True,
                    "category": "常用",
                    "categories": ["未分类", "常用"],
                },
                {
                    "ok": True,
                    "moved": 2,
                    "category": "常用",
                    "categories": ["未分类", "常用"],
                },
            ],
        ) as request:
            handler.api_agent_web_sticker_category_create({"name": "常用"})
            handler.api_agent_web_sticker_move(
                {"ids": [1, "2", 2], "category": "常用"}
            )
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(responses[1][0], 200)
        create_args = request.call_args_list[0].args
        move_args = request.call_args_list[1].args
        self.assertEqual(create_args[0], "/internal/sticker/category-create")
        self.assertEqual(create_args[1]["name"], "常用")
        self.assertEqual(move_args[0], "/internal/sticker/move")
        self.assertEqual(move_args[1]["ids"], [1, 2])
        self.assertEqual(move_args[1]["category"], "常用")

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

    def test_signed_agent_media_can_be_fetched_without_session(self):
        handler = self.make_handler({})
        handler.session_identity = lambda: None
        with patch.dict(app.AUTH_STATE, {"enabled": True}, clear=False):
            self.assertTrue(
                handler.guard_request_inner(
                    "/api/agent/media/book/3",
                    "GET",
                )
            )

    def test_agent_content_search_returns_music_metadata(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        identity = {
            "kind": "member",
            "user_id": 7,
            "username": "test",
            "nickname": "test",
        }
        rows = [
            {
                "id": 2,
                "title": "测试歌曲",
                "artist": "歌手",
                "album": "专辑",
                "duration": 120,
                "file_size": 1024,
                "source_type": "file",
            }
        ]
        with patch.object(app, "query", return_value=rows):
            handler.agent_tool_content_search(
                identity,
                {"kind": "music", "query": "测试"},
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(
            captured["payload"]["results"][0]["title"],
            "测试歌曲",
        )

    def test_agent_content_send_returns_signed_file_url(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        target = Path(temp.name) / "book_files" / "book.epub"
        target.parent.mkdir()
        target.write_bytes(b"book-data")
        identity = {
            "kind": "member",
            "user_id": 7,
            "username": "test",
            "nickname": "test",
            "role": "member",
        }
        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "agent-test-token"},
            clear=False,
        ), patch.object(app, "DATA_DIR", Path(temp.name)), patch.object(
            handler,
            "download_resource",
            return_value={
                "title": "测试书",
                "file_path": "book_files/book.epub",
                "download_name": "测试书.epub",
            },
        ):
            handler.agent_tool_content_send(
                identity,
                {"kind": "book", "id": 3},
            )
        self.assertEqual(captured["status"], 200)
        payload = captured["payload"]
        self.assertEqual(payload["status"], "file")
        self.assertIn("/api/agent/media/book/3?", payload["url"])
        self.assertEqual(payload["file_size"], len(b"book-data"))

    def test_note_markdown_and_text_export_preserve_readable_content(self):
        note = {
            "id": 5,
            "title": "测试笔记",
            "content": (
                "# 一级标题\n\n**重点**\n\n"
                "![图](/site-files/note_images/demo.png)\n\n"
                "- 列表项"
            ),
            "tags": "测试,导出",
            "updated_at": "2026-10-25 10:00:00",
        }
        markdown = app.build_note_export_markdown(note)
        self.assertIn("# 测试笔记", markdown)
        self.assertIn("标签：测试,导出", markdown)
        self.assertIn(
            app.PUBLIC_SITE_URL + "/site-files/note_images/demo.png",
            markdown,
        )
        body, file_name, mime_type, export_format = app.build_note_export_file(
            note,
            "txt",
        )
        text = body.decode("utf-8")
        self.assertIn("重点", text)
        self.assertNotIn("**", text)
        self.assertNotIn("![", text)
        self.assertEqual(file_name, "测试笔记.txt")
        self.assertTrue(mime_type.startswith("text/plain"))
        self.assertEqual(export_format, "txt")

    def test_agent_note_export_returns_signed_markdown_file(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        note = {
            "id": 5,
            "title": "测试笔记",
            "content": "# 正文\n\n内容",
            "tags": "导出",
            "created_at": "2026-10-24 10:00:00",
            "updated_at": "2026-10-25 10:00:00",
        }
        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "agent-test-token"},
            clear=False,
        ), patch.object(app, "query_one", return_value=note):
            handler.agent_tool_content_send(
                {"kind": "owner", "user_id": 0},
                {"kind": "note", "id": 5, "format": "markdown"},
            )
        self.assertEqual(captured["status"], 200)
        payload = captured["payload"]
        self.assertEqual(payload["status"], "file")
        self.assertEqual(payload["kind"], "note")
        self.assertEqual(payload["file_name"], "测试笔记.md")
        self.assertIn("/api/agent/media/note_markdown/5?", payload["url"])
        self.assertGreater(payload["file_size"], 0)

    def test_note_export_media_url_returns_generated_file(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_download_bytes = lambda body, name, mime: captured.update(
            {"body": body, "name": name, "mime": mime}
        )
        note = {
            "id": 9,
            "title": "媒体导出",
            "content": "# 标题\n\n正文",
            "tags": "",
            "created_at": "",
            "updated_at": "",
        }
        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "agent-test-token"},
            clear=False,
        ):
            expires = int(time.time()) + 60
            signature = app.agent_media_signature(
                "note_markdown",
                9,
                expires,
            )
            with patch.object(app, "query_one", return_value=note):
                handler.api_agent_media(
                    "/api/agent/media/note_markdown/9",
                    {
                        "expires": [str(expires)],
                        "sig": [signature],
                    },
                )
        self.assertEqual(captured["name"], "媒体导出.md")
        self.assertTrue(captured["mime"].startswith("text/markdown"))
        self.assertIn("正文".encode("utf-8"), captured["body"])

    def test_agent_note_import_accepts_markdown_attachment(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        content = "# 会议记录\n\n- 事项一\n- 事项二"
        with patch.object(
            app,
            "upload_limit",
            return_value={"max_file_bytes": 20 * 1024 * 1024},
        ), patch.object(app, "execute", return_value=44) as execute:
            handler.agent_tool_notes_import(
                {"kind": "owner", "user_id": 0},
                {
                    "file_name": "会议记录.md",
                    "data_base64": base64.b64encode(
                        content.encode("utf-8")
                    ).decode("ascii"),
                },
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["id"], 44)
        self.assertEqual(captured["payload"]["format"], "markdown")
        self.assertIn("/notes?note=44", captured["payload"]["url"])
        self.assertEqual(execute.call_args.args[1][0], "会议记录")
        self.assertIn("# 会议记录", execute.call_args.args[1][1])

    def test_agent_note_import_roughly_formats_txt(self):
        handler = self.make_handler({})
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        content = "第一章 准备工作\n• 第一项\n• 第二项"
        with patch.object(
            app,
            "upload_limit",
            return_value={"max_file_bytes": 20 * 1024 * 1024},
        ), patch.object(app, "execute", return_value=45) as execute:
            handler.agent_tool_notes_import(
                {"kind": "owner", "user_id": 0},
                {
                    "file_name": "工作清单.txt",
                    "data_base64": base64.b64encode(
                        content.encode("utf-8")
                    ).decode("ascii"),
                },
            )
        self.assertEqual(captured["status"], 200)
        saved_content = execute.call_args.args[1][1]
        self.assertIn("## 第一章 准备工作", saved_content)
        self.assertIn("- 第一项", saved_content)
        self.assertIn("- 第二项", saved_content)


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

    def test_internal_sticker_upload_writes_tagged_global_sticker(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        service = object.__new__(AgentService)
        service.config = SimpleNamespace(errorjiang_token="internal-token")
        service.store = AgentStore(Path(temp.name) / "agent.db")
        service.sticker_dir = Path(temp.name) / "stickers"
        service.sticker_dir.mkdir()
        server = AgentHttpServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        raw = b"\x89PNG\r\n\x1a\n" + b"upload-data"
        payload = {
            "owner_id": "0",
            "file_name": "泪目_猫猫.png",
            "category": "泪目",
            "data_base64": base64.b64encode(raw).decode("ascii"),
        }
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
            timeout=5,
        )
        try:
            connection.request(
                "POST",
                "/internal/sticker/upload",
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "X-ErrorJ-Agent-Token": "internal-token",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            result = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(result["sticker"]["category"], "泪目")
        self.assertEqual(result["sticker"]["source_name"], "泪目_猫猫.png")
        self.assertEqual(result["sticker"]["tags"], "泪目")
        sticker = service.store.list_stickers("0")[0]
        self.assertEqual(sticker["category"], "泪目")
        self.assertEqual(sticker["source_name"], "泪目_猫猫.png")
        self.assertEqual(sticker["tags"], "泪目")
        self.assertTrue((service.sticker_dir / sticker["ref"]).is_file())
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
            timeout=5,
        )
        try:
            connection.request(
                "GET",
                "/internal/stickers?owner_id=0",
                headers={"X-ErrorJ-Agent-Token": "internal-token"},
            )
            listing_response = connection.getresponse()
            listing = json.loads(
                listing_response.read().decode("utf-8")
            )
        finally:
            connection.close()
        self.assertEqual(listing_response.status, 200)
        self.assertIn("泪目", listing["categories"])
        self.assertEqual(listing["stickers"][0]["category"], "泪目")


class AgentConsoleUiTests(unittest.TestCase):
    def test_agent_page_is_settings_console_without_chat(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('class="agent-console-shell"', html)
        self.assertIn('id="settings-stickers"', html)
        self.assertIn('id="agentSettingsSave" disabled', html)
        self.assertIn('aria-label="筛选记忆"', html)
        self.assertIn('id="settings-persona"', html)
        self.assertIn('id="settings-web-search"', html)
        self.assertIn('id="settings-group-proactive"', html)
        self.assertIn("网页与热搜", html)
        self.assertIn('id="settingPersonaPreset"', html)
        self.assertIn('id="settingWebSearchEnabled"', html)
        self.assertIn('id="settingGroupProactiveEnabled"', html)
        self.assertIn("agent-sticker-file-name", script)
        self.assertEqual(html.count("data-console-section"), 9)
        self.assertNotIn('id="agentMessages"', html)
        self.assertNotIn('id="agentForm"', html)
        self.assertNotIn('id="agentSettingsDialog"', html)
        self.assertNotIn("/api/agent/web/chat", script)
        self.assertIn('aria-current", "location"', script)


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
