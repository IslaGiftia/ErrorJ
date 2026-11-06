import base64
import io
import json
import http.client
import os
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

import app
from errorjiang_agent import group_learning, media_links, memory_policy
from errorjiang_agent.adapters import (
    AdapterRegistry,
    OneBotAdapter,
    QQBotAdapter,
)
from errorjiang_agent.agent_metrics import MeteredProvider
from errorjiang_agent.brain import TOOLS, AgentBrain
from errorjiang_agent.clients import DeepSeekClient, HotSearchClient
from errorjiang_agent.config import Config
from errorjiang_agent.context import ContextWindow
from errorjiang_agent.errors import AgentError
from errorjiang_agent.onebot import (
    MessageEvent,
    event_key,
    extract_location_event,
    parse_message_event,
)
from errorjiang_agent.onebot_ws import _masked_frame, _read_frame
from errorjiang_agent.persona import compose_persona_prompt
from errorjiang_agent.qqbot import QQBotClient, parse_qqbot_event
from errorjiang_agent.providers import (
    FallbackLLMProvider,
    OpenAICompatibleProvider,
    ProviderRegistry,
)
from errorjiang_agent.routing import (
    EventState,
    GroupConversationPolicy,
    build_group_event_pipeline,
)
from errorjiang_agent.research import WebResearchEngine
from errorjiang_agent.search_routing import route_search_intent
from errorjiang_agent.search_evidence import assess_search_evidence
from errorjiang_agent.service import AgentHttpServer, AgentService
from errorjiang_agent.settings_schema import normalize_settings_update
from errorjiang_agent.store import AgentStore
from errorjiang_agent.tools import ToolRegistry


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
        defaults = self.store.get_settings("qq", "10001")
        self.assertTrue(defaults["memory_immediate_extraction_enabled"])
        self.assertEqual(
            defaults["memory_immediate_extraction_daily_limit"],
            12,
        )
        self.assertEqual(defaults["private_history_retention_days"], 90)
        self.assertEqual(defaults["group_history_retention_days"], 30)
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

    def test_settings_schema_normalizes_types_bounds_and_choices(self):
        current = self.store.get_settings("qqbot", "admin-openid")
        normalized = normalize_settings_update(
            current,
            {
                "memory_enabled": "false",
                "web_search_count": "99",
                "group_idle_trigger_minutes": 1,
                "group_activity_level": "invalid",
                "quiet_start": "25:99",
                "unknown_key": "ignored",
            },
        )
        self.assertFalse(normalized["memory_enabled"])
        self.assertEqual(normalized["web_search_count"], 10)
        self.assertEqual(normalized["group_idle_trigger_minutes"], 15)
        self.assertNotIn("group_activity_level", normalized)
        self.assertNotIn("quiet_start", normalized)
        self.assertNotIn("unknown_key", normalized)
        updated = self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "memory_enabled": "false",
                "web_search_count": 999,
                "group_activity_level": "active",
            },
        )
        self.assertFalse(updated["memory_enabled"])
        self.assertEqual(updated["web_search_count"], 10)
        self.assertEqual(updated["group_activity_level"], "active")

    def test_history_retention_prunes_once_per_day(self):
        now = 200 * 86400
        with patch(
            "errorjiang_agent.store.time.time",
            side_effect=[
                now - 100 * 86400,
                now - 1 * 86400,
                now - 100 * 86400,
                now - 50 * 86400,
                now - 1 * 86400,
            ],
        ):
            self.store.add_message("qq", "10001", "user", "旧私聊")
            self.store.add_message("qq", "10001", "user", "新私聊")
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                "member-a",
                "小明",
                "user",
                "旧群聊",
                "old-group",
            )
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                "member-a",
                "小明",
                "user",
                "中间群聊",
                "middle-group",
            )
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                "member-b",
                "小红",
                "user",
                "新群聊",
                "new-group",
            )
        result = self.store.prune_history(
            "2026-11-06",
            private_days=30,
            group_days=60,
            now=now,
        )
        self.assertTrue(result["ran"])
        self.assertEqual(result["private_deleted"], 1)
        self.assertEqual(result["group_deleted"], 1)
        self.assertEqual(
            [row["content"] for row in self.store.get_messages("qq", "10001", 10)],
            ["新私聊"],
        )
        self.assertEqual(
            [
                row["content"]
                for row in self.store.get_group_messages(
                    "qqbot",
                    "group-openid",
                    10,
                )
            ],
            ["中间群聊", "新群聊"],
        )
        again = self.store.prune_history(
            "2026-11-06",
            private_days=30,
            group_days=60,
            now=now,
        )
        self.assertFalse(again["ran"])

    def test_group_quiet_scope_and_metric_aggregation(self):
        now = int(time.time())
        self.store.set_group_quiet(
            "qqbot",
            "group-openid",
            "member-a",
            now + 600,
            "personal",
        )
        self.assertIsNotNone(
            self.store.group_quiet_active(
                "qqbot",
                "group-openid",
                "member-a",
                now,
            )
        )
        self.assertIsNone(
            self.store.group_quiet_active(
                "qqbot",
                "group-openid",
                "member-b",
                now,
            )
        )
        self.store.set_group_quiet(
            "qqbot",
            "group-openid",
            "*",
            now + 600,
            "group",
        )
        self.assertEqual(
            self.store.group_quiet_active(
                "qqbot",
                "group-openid",
                "member-b",
                now,
            )["member_id"],
            "*",
        )
        self.store.record_agent_metric("search", True, 120)
        self.store.record_agent_metric("search", False, 300)
        self.store.record_agent_metric("llm", True, 200)
        summary = self.store.agent_metric_summary()
        self.assertEqual(summary["today"]["search"]["success"], 1)
        self.assertEqual(summary["today"]["search"]["failure"], 1)
        self.assertEqual(summary["total_calls"], 3)
        self.assertEqual(summary["failed_calls"], 1)

    def test_persona_and_web_search_settings_persist(self):
        settings = self.store.save_settings(
            "qq",
            "10001",
            {
                "persona_preset": "温柔",
                "persona_custom_prompt": "少用感叹号，偶尔先说嗯。",
                "web_search_enabled": False,
                "web_search_count": 8,
                "web_domain_routing_enabled": False,
            },
        )
        self.assertEqual(settings["persona_preset"], "温柔")
        self.assertEqual(settings["web_search_count"], 8)
        self.assertFalse(settings["web_search_enabled"])
        self.assertFalse(settings["web_domain_routing_enabled"])
        prompt = AgentService.persona_prompt(settings)
        self.assertIn("温柔", prompt)
        self.assertIn("少用感叹号", prompt)

    def test_long_persona_prompt_preserves_format_and_trigger_words(self):
        custom = (
            "# 身份\n"
            "你是「鲸鲸」，一条住在 QQ 里的蓝色鲸鱼娘。\n"
            "别人叫你“大肥鱼”你会炸毛反驳“才不是大肥鱼！”。\n\n"
            "# 说话\n"
            + "- 日常短句，遇到明显转折时才拆成两条。\n" * 80
        )
        self.assertGreater(len(custom), 1000)
        settings = self.store.save_settings(
            "qqbot",
            "admin-openid",
            {"persona_custom_prompt": custom},
        )
        self.assertEqual(settings["persona_custom_prompt"], custom)
        prompt = compose_persona_prompt(settings)
        self.assertIn("# 身份\n", prompt)
        self.assertIn("别人叫你“大肥鱼”", prompt)
        self.assertIn("遇到明显转折时才拆成两条", prompt)

    def test_chat_human_delay_defaults_true_and_persists(self):
        settings = self.store.get_settings("qqbot", "admin-openid")
        self.assertTrue(settings["chat_human_delay"])
        updated = self.store.save_settings(
            "qqbot",
            "admin-openid",
            {"chat_human_delay": False},
        )
        self.assertFalse(updated["chat_human_delay"])

    def test_group_reply_control_defaults_and_persist(self):
        settings = self.store.get_settings("qqbot", "admin-openid")
        self.assertTrue(settings["group_reply_control_enabled"])
        self.assertEqual(settings["group_activity_level"], "balanced")
        self.assertTrue(settings["group_jargon_enabled"])
        self.assertEqual(settings["group_reply_max_per_10m"], 6)
        self.assertEqual(settings["group_reply_fatigue_rounds"], 3)
        self.assertEqual(settings["group_message_merge_seconds"], 4)
        updated = self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_reply_control_enabled": False,
                "group_activity_level": "active",
                "group_jargon_enabled": False,
                "group_reply_max_per_10m": 8,
                "group_reply_fatigue_rounds": 4,
                "group_message_merge_seconds": 2,
            },
        )
        self.assertFalse(updated["group_reply_control_enabled"])
        self.assertEqual(updated["group_activity_level"], "active")
        self.assertFalse(updated["group_jargon_enabled"])
        self.assertEqual(updated["group_reply_max_per_10m"], 8)
        self.assertEqual(updated["group_reply_fatigue_rounds"], 4)
        self.assertEqual(updated["group_message_merge_seconds"], 2)

    def test_bot_global_settings_merge_agent_page_platforms(self):
        self.store.save_settings(
            "web",
            "0",
            {"persona_custom_prompt": "被叫大肥鱼会炸毛"},
        )
        self.store.save_settings(
            "qq",
            "0",
            {"chat_human_delay": False},
        )
        service = object.__new__(AgentService)
        service.store = self.store
        resolved = service.bot_global_settings(
            "qqbot",
            {
                "chat_human_delay": True,
                "persona_custom_prompt": "",
            },
        )
        self.assertFalse(resolved["chat_human_delay"])
        self.assertIn("大肥鱼", resolved["persona_custom_prompt"])

    def test_legacy_persona_identity_is_migrated_to_jingjing(self):
        legacy = (
            "你是「大肥鱼」，一条蓝色鲸鱼娘。"
            "别人叫你“大肥鱼”你会炸毛反驳“才不是大肥鱼！”。"
            "折兮颜和小颜是旧名字。"
        )
        self.store.save_settings(
            "qqbot",
            "10001",
            {"persona_custom_prompt": legacy},
        )
        settings = self.store.get_settings("qqbot", "10001")
        custom = settings["persona_custom_prompt"]
        self.assertIn("你是「鲸鲸」", custom)
        self.assertIn("鲸鲸", custom)
        self.assertIn("大肥鱼", custom)
        self.assertNotIn("胖鲸", custom)
        for legacy_name in ("折兮颜", "小颜"):
            self.assertNotIn(legacy_name, custom)
        conn = sqlite3.connect(self.store.path)
        try:
            row = conn.execute(
                "SELECT value_json FROM settings "
                "WHERE platform = ? AND owner_id = ?",
                ("qqbot", "10001"),
            ).fetchone()
        finally:
            conn.close()
        saved = json.loads(row[0])["persona_custom_prompt"]
        self.assertEqual(saved, custom)

    def test_legacy_assistant_display_name_is_migrated_to_jingjing(self):
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "bot-openid",
            "折兮颜",
            "assistant",
            "旧消息",
            "legacy-assistant-name",
        )
        migrated = AgentStore(self.store.path)
        rows = migrated.get_group_messages(
            "qqbot",
            "group-openid",
            5,
        )
        self.assertEqual(rows[0]["display_name"], "鲸鲸")

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
        self.assertEqual(sticker["caption"], "")
        self.assertEqual(sticker["keywords"], "")
        self.assertEqual(sticker["mood"], "")
        self.assertEqual(sticker["use_count"], 0)
        self.assertIsNone(sticker["last_used_at"])
        self.assertEqual(sticker["library_id"], "default")
        self.assertEqual(sticker["source_name"], "")
        self.assertEqual(sticker["tags"], "旧标签")
        libraries = migrated.list_sticker_libraries()
        self.assertEqual(libraries[0]["id"], "default")
        self.assertEqual(libraries[0]["sticker_count"], 1)

    def test_member_sticker_packs_migrate_to_global_library(self):
        self.store.add_sticker(
            "member-openid",
            "image",
            "member-sticker.png",
            category="笑哭",
        )
        self.store.ensure_sticker_category("member-openid", "专属")
        migrated = AgentStore(self.store.path)
        stickers = migrated.list_stickers("0")
        self.assertEqual(
            [sticker["ref"] for sticker in stickers],
            ["member-sticker.png"],
        )
        self.assertEqual(migrated.list_stickers("member-openid"), [])
        self.assertIn("专属", migrated.list_sticker_categories("0"))

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
        self.assertEqual(stickers[0]["mood"], "sad")
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

    def test_sticker_libraries_and_selection_rule_priority(self):
        work = self.store.create_sticker_library("工作日常")
        life = self.store.create_sticker_library("生活")
        with self.assertRaises(ValueError):
            self.store.create_sticker_library("生活")
        default_sticker = self.store.add_sticker(
            "0",
            "image",
            "default.png",
            source_name="默认.png",
        )
        work_sticker = self.store.add_sticker(
            "0",
            "image",
            "work.png",
            source_name="工作.png",
            library_id=work["id"],
        )
        life_sticker = self.store.add_sticker(
            "0",
            "image",
            "life.png",
            source_name="生活.png",
            library_id=life["id"],
        )
        self.assertEqual(
            self.store.move_stickers_to_library(
                "0",
                [default_sticker],
                life["id"],
            ),
            1,
        )
        self.store.set_sticker_rule(
            "default",
            "",
            [life["id"]],
        )
        self.store.set_sticker_rule(
            "persona",
            "冷脸萌",
            [work["id"]],
        )
        self.store.set_sticker_rule(
            "group",
            "qqbot:group-openid",
            [life["id"]],
        )
        self.assertEqual(
            self.store.resolve_sticker_library_ids(
                "qqbot",
                "group",
                "group-openid",
                "冷脸萌",
            ),
            [life["id"]],
        )
        self.assertEqual(
            self.store.resolve_sticker_library_ids(
                "qqbot",
                "private",
                "member-openid",
                "冷脸萌",
            ),
            [work["id"]],
        )
        self.assertEqual(
            self.store.resolve_sticker_library_ids(
                "qqbot",
                "private",
                "member-openid",
                "温柔",
            ),
            [life["id"]],
        )
        self.store.update_sticker_library(life["id"], enabled=False)
        self.assertEqual(
            self.store.resolve_sticker_library_ids(
                "qqbot",
                "group",
                "group-openid",
                "冷脸萌",
            ),
            [work["id"]],
        )
        stickers = {
            sticker["id"]: sticker
            for sticker in self.store.list_stickers("0")
        }
        self.assertEqual(stickers[default_sticker]["library_id"], life["id"])
        self.assertEqual(stickers[work_sticker]["library_id"], work["id"])
        self.assertEqual(stickers[life_sticker]["library_id"], life["id"])

    def test_sticker_candidates_stay_pending_until_review(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.sticker_dir = Path(self.temp.name) / "stickers"
        service.sticker_dir.mkdir()
        work = self.store.create_sticker_library("待审核目标")
        raw = b"\x89PNG\r\n\x1a\ncandidate-image"
        self.assertTrue(
            service.save_sticker_candidate_image(
                raw,
                "猫猫笑哭.png",
                work["id"],
                "qqbot",
                "group-openid",
                "member-openid",
            )
        )
        self.assertEqual(self.store.list_stickers("0"), [])
        candidates = self.store.list_sticker_candidates("0")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["library_id"], work["id"])
        self.assertFalse(
            service.save_sticker_candidate_image(
                raw,
                "重复.png",
                work["id"],
                "qqbot",
                "group-openid",
                "member-openid",
            )
        )
        result = service.review_sticker_candidate(
            candidates[0]["id"],
            "accept",
            category="笑哭",
            caption="猫猫笑哭",
            keywords="猫猫 笑哭",
            mood="happy",
        )
        self.assertEqual(result["action"], "accepted")
        sticker = self.store.list_stickers("0")[0]
        self.assertEqual(sticker["library_id"], work["id"])
        self.assertEqual(sticker["category"], "笑哭")
        self.assertEqual(self.store.list_sticker_candidates("0"), [])

        second_raw = b"\x89PNG\r\n\x1a\nsecond-candidate"
        self.assertTrue(
            service.save_sticker_candidate_image(
                second_raw,
                "不要.png",
                "default",
                "qqbot",
                "group-openid",
                "member-openid",
            )
        )
        second = self.store.list_sticker_candidates("0")[0]
        service.review_sticker_candidate(second["id"], "discard")
        self.assertEqual(self.store.list_sticker_candidates("0"), [])
        self.assertFalse((service.sticker_dir / second["ref"]).exists())

    def test_sticker_selection_uses_group_and_persona_rules(self):
        service = object.__new__(AgentService)
        service.store = self.store
        work = self.store.create_sticker_library("工作")
        life = self.store.create_sticker_library("生活")
        self.store.add_sticker(
            "0",
            "image",
            "default.png",
            source_name="默认.png",
        )
        self.store.add_sticker(
            "0",
            "image",
            "work.png",
            source_name="工作.png",
            library_id=work["id"],
        )
        self.store.add_sticker(
            "0",
            "image",
            "life.png",
            source_name="生活.png",
            library_id=life["id"],
        )
        self.store.set_sticker_rule(
            "group",
            "qqbot:group-openid",
            [life["id"]],
        )
        self.store.set_sticker_rule(
            "persona",
            "冷脸萌",
            [work["id"]],
        )
        group_rows = service.sticker_candidates(
            "0",
            "qqbot",
            {
                "platform": "qqbot",
                "chat_type": "group",
                "chat_id": "group-openid",
                "persona_preset": "冷脸萌",
            },
        )
        self.assertEqual([row["ref"] for row in group_rows], ["life.png"])
        persona_rows = service.sticker_candidates(
            "0",
            "qqbot",
            {
                "platform": "qqbot",
                "chat_type": "private",
                "chat_id": "member-openid",
                "persona_preset": "冷脸萌",
            },
        )
        self.assertEqual([row["ref"] for row in persona_rows], ["work.png"])

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

    def test_member_sticker_picker_falls_back_to_global_pack(self):
        service = object.__new__(AgentService)
        service.store = self.store
        self.store.add_sticker("0", "image", "global-cry.png", category="泪目")
        context = {
            "platform": "qqbot",
            "owner_id": "member-openid",
            "is_admin": "0",
            "sticker_enabled": "1",
        }
        result = service.prepare_sticker({"emotion": "泪目"}, context)
        self.assertEqual(result["status"], "selected")
        sticker = service.selected_sticker(context)
        self.assertEqual(sticker["ref"], "global-cry.png")

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

    def test_sticker_layered_search_and_metadata_tools(self):
        service = object.__new__(AgentService)
        service.store = self.store
        self.store.add_sticker(
            "0",
            "image",
            "filename.png",
            category="日常",
            source_name="猫猫比心.png",
            caption="普通描述",
            keywords="普通",
            mood="daily",
        )
        self.store.add_sticker(
            "0",
            "image",
            "caption.png",
            category="开心",
            source_name="random.png",
            caption="猫猫比心",
            keywords="猫 比心",
            mood="happy",
        )
        self.store.add_sticker(
            "0",
            "image",
            "angry-cat.png",
            category="生气",
            source_name="random2.png",
            caption="气鼓鼓的猫",
            keywords="生气 猫 暴躁",
            mood="angry",
        )
        self.store.add_sticker(
            "0",
            "image",
            "sad.png",
            category="泪目",
            source_name="random3.png",
            caption="眼泪止不住",
            keywords="泪目 哭",
            mood="sad",
        )
        selected = AgentService.choose_sticker_for_query(
            self.store.list_stickers("0"),
            "猫猫比心",
            allow_random=False,
        )
        self.assertEqual(selected["ref"], "filename.png")
        selected = AgentService.choose_sticker_for_query(
            self.store.list_stickers("0"),
            "生气猫",
            allow_random=False,
        )
        self.assertEqual(selected["ref"], "angry-cat.png")
        selected = AgentService.choose_sticker_for_query(
            self.store.list_stickers("0"),
            "泪目",
            allow_random=False,
        )
        self.assertEqual(selected["ref"], "sad.png")

        listed = service.sticker_list_tool(
            {"query": "生气 猫", "limit": 10},
            {"platform": "qqbot", "sticker_enabled": "1"},
        )
        self.assertEqual(listed["count"], 1)
        sticker_id = listed["stickers"][0]["id"]
        updated = service.sticker_update_tool(
            {
                "ids": [sticker_id],
                "caption": "气到冒烟的猫",
                "keywords": "生气 猫 冒烟",
                "mood": "angry",
            },
            {"platform": "qqbot", "sticker_enabled": "1"},
        )
        self.assertEqual(updated["status"], "updated")
        sticker = next(
            item
            for item in self.store.list_stickers("0")
            if item["id"] == sticker_id
        )
        self.assertEqual(sticker["caption"], "气到冒烟的猫")
        self.assertEqual(sticker["keywords"], "生气 猫 冒烟")
        self.assertEqual(sticker["mood"], "angry")

    def test_sticker_picker_returns_real_stats_on_miss(self):
        service = object.__new__(AgentService)
        service.store = self.store
        self.store.add_sticker(
            "0",
            "image",
            "one.png",
            category="泪目",
            source_name="cry.png",
            caption="眼泪止不住",
            keywords="哭 泪目",
            mood="sad",
        )
        self.store.add_sticker(
            "0",
            "image",
            "two.png",
            category="开心",
            source_name="happy.png",
            mood="happy",
        )
        context = {
            "platform": "qqbot",
            "owner_id": "admin-openid",
            "is_admin": "1",
            "sticker_enabled": "1",
        }
        result = service.prepare_sticker(
            {"emotion": "完全不存在的画面"},
            context,
        )
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(
            {item["name"] for item in result["categories"]},
            {"泪目", "开心"},
        )
        self.assertEqual(
            {item["name"] for item in result["moods"]},
            {"难过", "开心"},
        )
        selected = service.prepare_sticker(
            {"emotion": "泪目", "query": "眼泪"},
            context,
        )
        self.assertEqual(selected["status"], "selected", selected)
        self.assertEqual(service.selected_sticker(context)["ref"], "one.png")

    def test_sticker_usage_tracks_recent_and_avoids_repeat(self):
        service = object.__new__(AgentService)
        service.store = self.store
        first = self.store.add_sticker(
            "0",
            "image",
            "first.png",
            category="开心",
            source_name="开心一号.png",
            caption="开心到飞起",
            keywords="开心 飞起",
            mood="happy",
        )
        second = self.store.add_sticker(
            "0",
            "image",
            "second.png",
            category="开心",
            source_name="开心二号.png",
            caption="开心转圈",
            keywords="开心 转圈",
            mood="happy",
        )
        used_at = int(time.time())
        with patch("errorjiang_agent.store.time.time", return_value=used_at):
            self.assertTrue(
                self.store.record_sticker_use(
                    "0",
                    first,
                    "qqbot",
                    "chat-openid",
                    "开心",
                    "metadata",
                )
            )
        stickers = self.store.list_stickers("0")
        used = next(item for item in stickers if item["id"] == first)
        self.assertEqual(used["use_count"], 1)
        self.assertEqual(used["last_used_at"], used_at)
        recent = self.store.recent_sticker_ids(
            "0",
            "qqbot",
            "chat-openid",
            used_at - 60,
            5,
        )
        self.assertEqual(recent, [first])
        selected = AgentService.choose_sticker_for_query(
            stickers,
            "开心",
            exclude_ids={first},
            allow_random=False,
        )
        self.assertEqual(selected["id"], second)
        context = {
            "platform": "qqbot",
            "chat_id": "chat-openid",
            "sticker_enabled": "1",
        }
        result = service.prepare_sticker({"emotion": "开心"}, context)
        self.assertEqual(result["status"], "selected")
        self.assertEqual(service.selected_sticker(context)["id"], second)

    def test_sticker_pack_export_import_and_deduplication(self):
        source_temp = tempfile.TemporaryDirectory()
        target_temp = tempfile.TemporaryDirectory()
        self.addCleanup(source_temp.cleanup)
        self.addCleanup(target_temp.cleanup)
        source = object.__new__(AgentService)
        source.store = AgentStore(Path(source_temp.name) / "source.db")
        source.sticker_dir = Path(source_temp.name) / "stickers"
        source.sticker_dir.mkdir()
        source.save_sticker_upload(
            "0",
            b"\x89PNG\r\n\x1a\npack-image",
            "晚安_鲸鱼睡大觉.png",
            "晚安",
            caption="鲸鱼盖着被子睡大觉",
            keywords="晚安 鲸鱼 睡大觉",
            mood="daily",
        )
        archive = source.export_sticker_pack("0")
        self.assertTrue(archive.startswith(b"PK"))

        target = object.__new__(AgentService)
        target.store = AgentStore(Path(target_temp.name) / "target.db")
        target.sticker_dir = Path(target_temp.name) / "stickers"
        target.sticker_dir.mkdir()
        result = target.import_sticker_pack(archive, "0")
        self.assertEqual(result["imported"], 1)
        sticker = target.store.list_stickers("0")[0]
        self.assertEqual(sticker["source_name"], "晚安_鲸鱼睡大觉.png")
        self.assertEqual(sticker["caption"], "鲸鱼盖着被子睡大觉")
        self.assertEqual(sticker["keywords"], "晚安 鲸鱼 睡大觉")
        self.assertEqual(sticker["mood"], "daily")
        self.assertTrue((target.sticker_dir / sticker["ref"]).is_file())
        repeated = target.import_sticker_pack(archive, "0")
        self.assertEqual(repeated["duplicates"], 1)

    def test_sticker_pack_rejects_unsafe_archive(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        service = object.__new__(AgentService)
        service.store = AgentStore(Path(temp.name) / "agent.db")
        service.sticker_dir = Path(temp.name) / "stickers"
        service.sticker_dir.mkdir()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps({"version": 1, "stickers": []}),
            )
            archive.writestr("../evil.png", b"bad")
        with self.assertRaises(AgentError):
            service.import_sticker_pack(buffer.getvalue(), "0")

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
            "0",
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

    def test_group_idle_proactive_schedules_then_sends_once(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_idle_proactive_enabled": True,
                "group_idle_trigger_minutes": 90,
                "group_idle_random_min_minutes": 15,
                "group_idle_random_max_minutes": 45,
                "group_idle_max_per_day": 1,
                "group_idle_max_unanswered": 2,
                "quiet_start": "23:30",
                "quiet_end": "08:00",
            },
        )
        now = datetime(2026, 11, 4, 15, 0)
        activity_at = now - timedelta(minutes=100)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=activity_at.timestamp(),
        ):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "周末有人去吃火锅吗",
                "group-idle-message-1",
            )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        class FakeDeepSeek:
            def chat(self, messages, tools):
                self.last_messages = messages
                return {"content": "火锅先记着，周六谁先到谁占座？"}

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace(
            tool=lambda *args, **kwargs: {"casts": []}
        )
        service.deepseek = FakeDeepSeek()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )

        with patch(
            "errorjiang_agent.service.random.randint",
            return_value=20 * 60,
        ):
            service._group_idle_proactive_tick(now)
        self.assertEqual(service.qqbot.sent, [])
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(
            state["next_proactive_at"],
            int(now.timestamp()) + 20 * 60,
        )

        due = datetime.fromtimestamp(state["next_proactive_at"]) + timedelta(
            seconds=1
        )
        service._group_idle_proactive_tick(due)
        self.assertEqual(len(service.qqbot.sent), 1)
        message_type, group_id, text = service.qqbot.sent[0]
        self.assertEqual((message_type, group_id), ("group", "group-openid"))
        self.assertIn("火锅", text)
        self.assertIn("最近群聊流水", service.deepseek.last_messages[1]["content"])
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["unanswered_count"], 1)
        self.assertIsNone(state["next_proactive_at"])
        self.assertEqual(
            self.store.proactive_count(
                due.strftime("%Y-%m-%d"),
                "qqbot-group-idle:group-openid",
            ),
            1,
        )
        status = service.group_idle_status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["groups"][0]["unanswered_count"], 1)
        self.assertEqual(status["groups"][0]["group_tail"], "group-openid"[-8:])
        self.assertEqual(
            self.store.get_group_messages("qqbot", "group-openid")[-1][
                "content"
            ],
            text,
        )

        service._group_idle_proactive_tick(
            due + timedelta(minutes=30)
        )
        self.assertEqual(len(service.qqbot.sent), 1)

    def test_group_idle_discards_generation_when_group_becomes_active(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_idle_proactive_enabled": True,
                "group_idle_trigger_minutes": 90,
                "group_idle_random_min_minutes": 15,
                "group_idle_random_max_minutes": 45,
            },
        )
        now = datetime(2026, 11, 4, 16, 0)
        activity_at = now - timedelta(minutes=120)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=activity_at.timestamp(),
        ):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "晚上一起打游戏吗",
                "race-message-1",
            )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        store = self.store

        class ActiveGroupDeepSeek:
            def chat(self, messages, tools):
                with patch(
                    "errorjiang_agent.store.time.time",
                    return_value=(now + timedelta(minutes=3)).timestamp(),
                ):
                    store.record_group_activity(
                        "qqbot",
                        "group-openid",
                        "member-2",
                        "小红",
                        "来了来了",
                        "race-message-2",
                    )
                return {"content": "那就晚上八点？"}

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace(
            tool=lambda *args, **kwargs: {"casts": []}
        )
        service.deepseek = ActiveGroupDeepSeek()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        with patch(
            "errorjiang_agent.service.random.randint",
            return_value=15 * 60,
        ):
            service._group_idle_proactive_tick(now)
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        due = datetime.fromtimestamp(state["next_proactive_at"]) + timedelta(
            seconds=1
        )
        service._group_idle_proactive_tick(due)
        self.assertEqual(service.qqbot.sent, [])
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertIsNone(state["next_proactive_at"])
        self.assertEqual(state["unanswered_count"], 0)

    def test_group_idle_reschedules_stale_task_without_generating(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_idle_proactive_enabled": True,
                "group_idle_trigger_minutes": 90,
                "group_idle_random_min_minutes": 15,
                "group_idle_random_max_minutes": 45,
            },
        )
        now = datetime(2026, 11, 4, 17, 0)
        activity_at = now - timedelta(hours=5)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=activity_at.timestamp(),
        ):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "下午有人出去吗",
                "stale-message-1",
            )
        self.store.schedule_group_proactive(
            "qqbot",
            "group-openid",
            int(now.timestamp()) - 3 * 3600,
        )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        class NoGeneration:
            def chat(self, messages, tools):
                raise AssertionError("stale task must not call the model")

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace()
        service.deepseek = NoGeneration()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        with patch(
            "errorjiang_agent.service.random.randint",
            return_value=20 * 60,
        ):
            service._group_idle_proactive_tick(now)
        self.assertEqual(service.qqbot.sent, [])
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(
            state["next_proactive_at"],
            int(now.timestamp()) + 20 * 60,
        )

    def test_group_idle_stops_after_unanswered_limit(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_idle_proactive_enabled": True,
                "group_idle_trigger_minutes": 15,
                "group_idle_max_unanswered": 2,
            },
        )
        now = datetime(2026, 11, 4, 18, 0)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=(now - timedelta(hours=2)).timestamp(),
        ):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "晚上吃什么",
                "unanswered-message-1",
            )
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=(now - timedelta(minutes=90)).timestamp(),
        ):
            self.store.mark_group_proactive_sent(
                "qqbot",
                "group-openid",
                int((now - timedelta(minutes=90)).timestamp()),
            )
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=(now - timedelta(minutes=30)).timestamp(),
        ):
            self.store.mark_group_proactive_sent(
                "qqbot",
                "group-openid",
                int((now - timedelta(minutes=30)).timestamp()),
            )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        class NoGeneration:
            def chat(self, messages, tools):
                raise AssertionError("unanswered limit must stop generation")

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace()
        service.deepseek = NoGeneration()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        service._group_idle_proactive_tick(now)
        self.assertEqual(service.qqbot.sent, [])
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["unanswered_count"], 2)
        self.assertIsNone(state["next_proactive_at"])

    def test_group_idle_skip_uses_long_backoff(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_idle_proactive_enabled": True,
                "group_idle_trigger_minutes": 90,
            },
        )
        now = datetime(2026, 11, 4, 19, 0)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=(now - timedelta(hours=2)).timestamp(),
        ):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "今天好安静",
                "skip-message-1",
            )
        self.store.schedule_group_proactive(
            "qqbot",
            "group-openid",
            int(now.timestamp()),
        )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        class SkipDeepSeek:
            def chat(self, messages, tools):
                return {"content": "SKIP"}

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace()
        service.deepseek = SkipDeepSeek()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        service._group_idle_proactive_tick(now)
        self.assertEqual(service.qqbot.sent, [])
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(
            state["next_proactive_at"],
            int(now.timestamp()) + 6 * 3600,
        )

    def test_group_idle_threshold_adapts_to_group_cadence(self):
        now_ts = int(datetime(2026, 11, 4, 20, 0).timestamp())
        for index in range(24):
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "user",
                f"普通消息 {index}",
                f"cadence-{index}",
            )
        with self.store._connection() as conn:
            for index in range(24):
                conn.execute(
                    """UPDATE group_messages SET created_at = ?
                       WHERE source_message_id = ?""",
                    (
                        now_ts - 24 * 3600 + index * 3600,
                        f"cadence-{index}",
                    ),
                )
        service = object.__new__(AgentService)
        service.store = self.store
        adaptive = service.group_idle_threshold(
            "qqbot",
            "group-openid",
            90,
            now_ts,
        )
        self.assertFalse(adaptive["sparse"])
        self.assertEqual(adaptive["minutes"], 150)
        self.assertEqual(adaptive["median_gap_seconds"], 3600)

    def test_group_idle_only_effective_reply_resets_unanswered(self):
        self.store.bind_admin("qqbot", "admin-openid")
        base = int(datetime(2026, 11, 4, 16, 0).timestamp())
        with patch("errorjiang_agent.store.time.time", return_value=base):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "周六去吃火锅吗",
                "reply-base",
            )
        run_id = self.store.create_group_proactive_run(
            "qqbot",
            "group-openid",
            "接续最近群聊",
        )
        message_id = self.store.add_group_message(
            "qqbot",
            "group-openid",
            "assistant",
            "鲸鲸",
            "assistant",
            "火锅可以，周六谁先到？",
            "idle-sent",
        )
        self.store.mark_group_proactive_sent(
            "qqbot",
            "group-openid",
            base + 100,
            message_id=message_id or 0,
            text="火锅可以，周六谁先到？",
            run_id=run_id,
        )
        self.store.update_group_proactive_run(
            run_id,
            status="sent",
            generated_text="火锅可以，周六谁先到？",
        )

        service = object.__new__(AgentService)
        service.store = self.store

        def event(text, message_id):
            return MessageEvent(
                self_id="bot",
                user_id="member-2",
                message_type="group",
                chat_id="group-openid",
                message_id=message_id,
                text=text,
                to_me=False,
                platform="qqbot",
                group_full=True,
                display_name="小红",
            )

        with patch(
            "errorjiang_agent.service.time.time",
            return_value=base + 180,
        ), patch(
            "errorjiang_agent.store.time.time",
            return_value=base + 180,
        ):
            self.assertTrue(
                service._observe_group_activity(
                    event("今天风好大", "unrelated-reply")
                )
            )
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["unanswered_count"], 1)
        run = self.store.list_group_proactive_runs(
            "qqbot",
            limit=1,
        )[0]
        self.assertEqual(run["status"], "sent")

        with patch(
            "errorjiang_agent.service.time.time",
            return_value=base + 240,
        ), patch(
            "errorjiang_agent.store.time.time",
            return_value=base + 240,
        ):
            self.assertTrue(
                service._observe_group_activity(
                    event("火锅我也去", "effective-reply")
                )
            )
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["unanswered_count"], 0)
        self.assertIsNone(state["awaiting_reply_until"])
        run = self.store.list_group_proactive_runs(
            "qqbot",
            limit=1,
        )[0]
        self.assertEqual(run["status"], "replied")
        self.assertEqual(run["reply_member_id"], "member-2")

    def test_group_idle_scheduler_expires_reply_window(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {"group_idle_proactive_enabled": True},
        )
        base = int(datetime(2026, 11, 4, 16, 0).timestamp())
        with patch("errorjiang_agent.store.time.time", return_value=base):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "有人去吃火锅吗",
                "expire-base",
            )
        run_id = self.store.create_group_proactive_run(
            "qqbot",
            "group-openid",
            "接续最近群聊",
        )
        self.store.mark_group_proactive_sent(
            "qqbot",
            "group-openid",
            base,
            text="火锅可以，谁去？",
            run_id=run_id,
        )
        self.store.update_group_proactive_run(
            run_id,
            status="sent",
            generated_text="火锅可以，谁去？",
        )
        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = SimpleNamespace()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace()
        service.deepseek = SimpleNamespace()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        now = datetime.fromtimestamp(base + 16 * 60)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=base + 16 * 60,
        ):
            service._group_idle_proactive_tick(now)
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertIsNone(state["awaiting_reply_until"])
        self.assertEqual(state["unanswered_count"], 1)
        run = self.store.list_group_proactive_runs("qqbot", limit=1)[0]
        self.assertEqual(run["status"], "expired")

    def test_group_idle_manual_preview_send_and_pause(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {"group_idle_proactive_enabled": True},
        )
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "member-openid",
            "小明",
            "user",
            "最近有人去看展吗",
            "manual-context",
        )

        class FakeQQBot:
            def __init__(self):
                self.sent = []

            def send_active_message(self, message_type, chat_id, text):
                self.sent.append((message_type, chat_id, text))

        class FakeDeepSeek:
            def chat(self, messages, tools):
                return {"content": "最近那个展好像快结束了，有人想去吗？"}

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = FakeQQBot()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace()
        service.deepseek = FakeDeepSeek()
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )

        preview = service.group_idle_action("preview", "group-openid")
        self.assertTrue(preview["ok"])
        self.assertEqual(service.qqbot.sent, [])
        self.assertEqual(
            self.store.list_group_proactive_runs("qqbot", limit=1)[0][
                "status"
            ],
            "preview",
        )

        configured = service.group_idle_action(
            "configure",
            "group-openid",
            idle_trigger_minutes=180,
            max_per_day=2,
        )
        self.assertTrue(configured["ok"])
        override = self.store.get_group_proactive_override(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(override["idle_trigger_minutes"], 180)
        self.assertEqual(override["max_per_day"], 2)

        sent = service.group_idle_action("send", "group-openid")
        self.assertTrue(sent["ok"])
        self.assertEqual(len(service.qqbot.sent), 1)
        self.assertEqual(service.qqbot.sent[0][0], "group")
        self.assertEqual(
            self.store.list_group_proactive_runs("qqbot", limit=1)[0][
                "status"
            ],
            "sent",
        )

        paused = service.group_idle_action("pause", "group-openid")
        self.assertTrue(paused["ok"])
        override = self.store.get_group_proactive_override(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(override["enabled"], 0)

    def test_group_idle_respects_group_pause_and_sparse_weekly_limit(self):
        self.store.bind_admin("qqbot", "admin-openid")
        self.store.save_settings(
            "qqbot",
            "admin-openid",
            {
                "group_idle_proactive_enabled": True,
                "group_idle_trigger_minutes": 15,
            },
        )
        now = datetime(2026, 11, 4, 20, 0)
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=(now - timedelta(hours=2)).timestamp(),
        ):
            self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "小明",
                "有人吗",
                "pause-context",
            )
        self.store.set_group_proactive_enabled(
            "qqbot",
            "group-openid",
            False,
        )

        class NoQQBotSend:
            def send_active_message(self, message_type, chat_id, text):
                raise AssertionError("paused group must not send")

        service = object.__new__(AgentService)
        service.store = self.store
        service.qqbot = NoQQBotSend()
        service.onebot = SimpleNamespace()
        service.errorjiang = SimpleNamespace()
        service.deepseek = SimpleNamespace(
            chat=lambda *args, **kwargs: {"content": "不该生成"}
        )
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        service._group_idle_proactive_tick(now)

        self.store.set_group_proactive_enabled(
            "qqbot",
            "group-openid",
            True,
        )
        for index in range(3):
            self.store.claim_proactive_slot(
                now.strftime("%Y-%m-%d"),
                f"sparse-{index}",
                "qqbot-group-idle:group-openid",
            )
        service._group_idle_proactive_tick(now)
        self.assertEqual(
            self.store.list_group_proactive_runs("qqbot", limit=10),
            [],
        )

    def test_full_group_messages_are_observed_before_reply_gate(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            qqbot_group_ids=frozenset({"group-openid"})
        )
        service.group_policy = GroupConversationPolicy(self.store)
        service.event_pipeline = build_group_event_pipeline(
            service.group_policy,
            service.config,
        )
        submitted = []
        service.executor = SimpleNamespace(
            submit=lambda *args: submitted.append(args)
        )
        event = MessageEvent(
            self_id="bot-openid",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="ordinary-group-message",
            text="今天食堂排队也太长了",
            to_me=False,
            platform="qqbot",
            group_full=True,
            display_name="小明",
        )
        service.schedule_qqbot_event(event)
        self.assertEqual(submitted, [])
        history = self.store.get_group_messages("qqbot", "group-openid")
        self.assertEqual(history[-1]["content"], "今天食堂排队也太长了")
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertGreater(state["last_user_at"], 0)

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

    def test_group_auto_reply_requires_name_or_recent_conversation(self):
        service = object.__new__(AgentService)
        service.store = self.store

        def event(
            text,
            referenced=False,
            mentions_other=False,
            user_id="member-openid",
        ):
            return MessageEvent(
                self_id="bot",
                user_id=user_id,
                message_type="group",
                chat_id="group-openid",
                message_id=f"message-{abs(hash((text, referenced)))}",
                text=text,
                to_me=False,
                platform="qqbot",
                group_full=True,
                referenced=referenced,
                mentions_other=mentions_other,
            )

        self.assertTrue(
            service.group_message_wants_reply(
                event("鲸鲸，帮我查一下千阳县美食")
            )
        )
        self.assertFalse(
            service.group_message_wants_reply(
                event("今天中午大家准备吃什么")
            )
        )
        self.assertTrue(
            service.group_message_wants_reply(
                event("设置天气城市 西安")
            )
        )
        self.assertTrue(
            service.group_message_wants_reply(
                event("添加刚才的标记点")
            )
        )
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "member-openid",
            "星星",
            "user",
            "帮我查千阳县。",
            "group-auto-user-1",
        )
        self.store.add_group_message(
            "qqbot",
            "group-openid",
            "assistant",
            "鲸鲸",
            "assistant",
            "我刚才查了千阳县。",
            "group-auto-assistant-1",
        )
        self.assertTrue(
            service.group_message_wants_reply(
                event("那附近还有别的吗？")
            )
        )
        self.assertTrue(
            service.group_message_wants_reply(
                event("接着说", referenced=True)
            )
        )
        for index in range(24):
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                f"other-{index % 3}",
                f"群友{index % 3}",
                "user",
                f"普通闲聊 {index}",
                f"group-auto-extra-{index}",
            )
        self.assertTrue(
            service.group_message_wants_reply(
                event("还有呢", user_id="member-openid")
            )
        )
        self.assertFalse(
            service.group_message_wants_reply(event("哈哈哈哈"))
        )
        self.assertFalse(
            service.group_message_wants_reply(
                event("你在说啥", user_id="other-member")
            )
        )
        self.assertFalse(
            service.group_message_wants_reply(
                event("你帮我看下这个", mentions_other=True)
            )
        )

        submitted = []

        class FakeFuture:
            def add_done_callback(self, callback):
                return None

        service.executor = SimpleNamespace(
            submit=lambda fn, *args: submitted.append((fn, args))
            or FakeFuture()
        )
        service._event_done = lambda future: None
        service.schedule_qqbot_event(
            event("鲸鲸，在吗")
        )
        self.assertEqual(len(submitted), 1)
        self.assertTrue(submitted[0][1][0].to_me)
        service.schedule_qqbot_event(event("今天食堂排队好长"))
        self.assertEqual(len(submitted), 1)

    def test_group_ambient_reply_density_and_fatigue(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service._group_ambient_lock = threading.Lock()
        service._group_ambient_state = {}
        service._group_runtime_settings = lambda _event: {
            "group_reply_control_enabled": True,
            "group_reply_max_per_10m": 6,
            "group_reply_fatigue_rounds": 3,
        }
        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="ambient-reply",
            text="那这个还有吗？",
            to_me=True,
            platform="qqbot",
            group_full=True,
        )
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=1000,
        ):
            for index in range(3):
                self.store.add_group_message(
                    "qqbot",
                    "group-openid",
                    "assistant",
                    "鲸鲸",
                    "assistant",
                    f"回复 {index}",
                    f"assistant-density-{index}",
                )
        with patch(
            "errorjiang_agent.service.time.time",
            return_value=1010,
        ):
            self.assertEqual(
                service._group_auto_reply_suppression_reason(
                    event,
                    "group_conversation",
                ),
                "",
            )
            service._group_ambient_state["qqbot:group-openid"] = {
                "last_member": "member-openid",
                "last_at": 1000,
                "streak": 3,
            }
            self.assertEqual(
                service._group_auto_reply_suppression_reason(
                    event,
                    "group_conversation",
                ),
                "conversation_fatigue",
            )
            service._note_group_human_activity(
                replace(event, text="鲸鲸，换个话题")
            )
            self.assertEqual(
                service._group_ambient_state["qqbot:group-openid"]["streak"],
                0,
            )
            service._group_ambient_state["qqbot:group-openid"] = {
                "last_member": "member-openid",
                "last_at": 1000,
                "streak": 3,
            }
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=1000,
        ):
            for index in range(3, 6):
                self.store.add_group_message(
                    "qqbot",
                    "group-openid",
                    "assistant",
                    "鲸鲸",
                    "assistant",
                    f"回复 {index}",
                    f"assistant-density-{index}",
                )
        with patch(
            "errorjiang_agent.service.time.time",
            return_value=1400,
        ):
            self.assertEqual(
                service._group_auto_reply_suppression_reason(
                    event,
                    "group_conversation",
                ),
                "reply_density",
            )
        self.assertEqual(
            service._group_auto_reply_suppression_reason(
                replace(event, text="鲸鲸，在吗"),
                "group_conversation",
            ),
            "",
        )
        self.assertEqual(
            service._group_auto_reply_suppression_reason(
                replace(event, text="设置天气城市 西安"),
                "group_conversation",
            ),
            "",
        )
        self.assertEqual(
            service._group_auto_reply_suppression_reason(
                replace(event, text="添加刚才的标记点"),
                "group_conversation",
            ),
            "",
        )
        self.assertEqual(
            service._group_auto_reply_suppression_reason(
                replace(
                    event,
                    shared_media=(
                        {
                            "url": "https://b23.tv/example",
                            "platform": "bilibili",
                        },
                    ),
                ),
                "shared_media",
            ),
            "",
        )
        service._group_runtime_settings = lambda _event: {
            "group_reply_control_enabled": False,
        }
        self.assertEqual(
            service._group_auto_reply_suppression_reason(
                event,
                "group_conversation",
            ),
            "",
        )

    def test_ambient_group_messages_merge_for_a_short_window(self):
        timers = []

        class FakeTimer:
            def __init__(self, delay, callback, args):
                self.delay = delay
                self.callback = callback
                self.args = args
                self.daemon = False
                self.cancelled = False
                timers.append(self)

            def start(self):
                return None

            def cancel(self):
                self.cancelled = True

            def fire(self):
                self.callback(*self.args)

        class FakeFuture:
            def add_done_callback(self, callback):
                return None

        submitted = []
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset({"group-openid"}),
        )
        service._group_ambient_lock = threading.Lock()
        service._group_ambient_state = {}
        service._group_merge_lock = threading.Lock()
        service._group_merge_timers = {}
        service._group_merge_pending = {}
        service._observe_group_activity = lambda _event: True
        service._group_runtime_settings = lambda _event: {
            "group_message_merge_seconds": 4,
        }
        service.event_pipeline = SimpleNamespace(
            run=lambda event, state=None: (
                replace(event, to_me=True),
                EventState(auto_reply=True, reason="group_conversation"),
            )
        )
        service.executor = SimpleNamespace(
            submit=lambda fn, *args: submitted.append((fn, args))
            or FakeFuture()
        )
        first = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="merge-1",
            text="那这个还有吗？",
            to_me=False,
            platform="qqbot",
            group_full=True,
        )
        second = replace(
            first,
            message_id="merge-2",
            text="然后呢？",
        )
        with patch(
            "errorjiang_agent.service.threading.Timer",
            FakeTimer,
        ):
            service.schedule_qqbot_event(first)
            service.schedule_qqbot_event(second)
            self.assertEqual(len(timers), 2)
            self.assertTrue(timers[0].cancelled)
            self.assertEqual(submitted, [])
            timers[1].fire()
            self.assertEqual(len(submitted), 1)
            self.assertEqual(submitted[0][1][0].message_id, "merge-2")
            self.assertEqual(submitted[0][1][4], "group_conversation")

            service.schedule_qqbot_event(
                replace(
                    first,
                    message_id="merge-3",
                    text="还有呢？",
                )
            )
            service.schedule_qqbot_event(
                replace(
                    first,
                    message_id="explicit-1",
                    text="鲸鲸，在吗",
                )
            )
        self.assertEqual(len(submitted), 2)
        self.assertEqual(submitted[1][1][0].message_id, "explicit-1")
        self.assertTrue(timers[2].cancelled)
        self.assertEqual(service._group_merge_pending, {})
        timers[2].fire()
        self.assertEqual(len(submitted), 2)

    def test_amap_share_url_resolves_to_coordinates(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def geturl(self):
                nested = (
                    "androidamap?action=shorturl&p=B0HG3CD2JX,"
                    "34.644625,107.110015,千阳县位置,测试路"
                )
                return "https://m.amap.com/callAPP?" + urlencode(
                    {"android": nested}
                )

            def read(self, limit):
                return b""

        service = object.__new__(AgentService)
        with patch(
            "errorjiang_agent.service.urlopen",
            return_value=FakeResponse(),
        ):
            location = service.resolve_amap_share_location(
                {
                    "title": "千阳县位置",
                    "jump_url": "https://surl.amap.com/example",
                }
            )
        self.assertAlmostEqual(location["lat"], 34.644625)
        self.assertAlmostEqual(location["lng"], 107.110015)

    def test_unbound_group_location_is_cached_and_explains_binding(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset(),
        )
        replies = []
        service.send_reply = lambda event, text: replies.append(text)
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
        self.assertIn("还没有绑定", replies[0])
        cached = self.store.consume_shared_location(
            "qqbot",
            "group-openid",
            "member-openid",
        )
        self.assertEqual(cached["title"], "春发芽葫芦头")

    def test_admin_group_location_is_added_automatically(self):
        self.store.bind_admin("qqbot", "admin-openid")
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset(),
            admin_qqs=frozenset(),
        )
        replies = []
        service.send_reply = lambda event, text: replies.append(text)
        added = []

        def add_location(event, target_user_id):
            added.append((event.location["title"], target_user_id))
            return {
                "status": "added",
                "place": {
                    "name": event.location["title"],
                    "category_name": "美食",
                    "url": "https://example.com/map?place=99",
                },
            }

        service.add_shared_location = add_location
        event = MessageEvent(
            self_id="bot",
            user_id="admin-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="location-share-admin",
            text="",
            to_me=False,
            platform="qqbot",
            group_full=True,
            location={
                "lat": 34.3416,
                "lng": 108.9398,
                "title": "春发芽葫芦头",
                "address": "测试路",
                "coord": "gcj02",
            },
        )
        service._handle_message_event(event)
        self.assertEqual(added, [("春发芽葫芦头", 0)])
        self.assertIn("已从位置卡片添加足迹", replies[0])
        self.assertIsNone(
            self.store.get_shared_location(
                "qqbot",
                "group-openid",
                "admin-openid",
            )
        )

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

    def test_legacy_memories_migrate_lifecycle_fields_and_events(self):
        path = Path(self.temp.name) / "legacy-memory.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                """CREATE TABLE memories (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       platform TEXT NOT NULL,
                       owner_id TEXT NOT NULL,
                       kind TEXT NOT NULL DEFAULT 'fact',
                       content TEXT NOT NULL,
                       importance INTEGER NOT NULL DEFAULT 5,
                       confidence INTEGER NOT NULL DEFAULT 5,
                       source TEXT NOT NULL DEFAULT 'chat',
                       access_count INTEGER NOT NULL DEFAULT 0,
                       created_at INTEGER NOT NULL,
                       updated_at INTEGER NOT NULL,
                       last_used_at INTEGER,
                       UNIQUE(platform, owner_id, content)
                   )"""
            )
            connection.execute(
                """INSERT INTO memories(
                       platform, owner_id, content, created_at, updated_at
                   ) VALUES ('qq', '10001', '旧记忆', 1, 1)"""
            )
            connection.commit()
        finally:
            connection.close()

        migrated = AgentStore(path)
        memory = migrated.list_memories("qq", "10001")[0]
        self.assertEqual(memory["strength"], 1.0)
        self.assertEqual(memory["pinned"], 0)
        self.assertIsNone(memory["archived_at"])
        self.assertEqual(memory["evidence"], "")
        self.assertEqual(memory["source_ref"], "")
        connection = sqlite3.connect(path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            connection.close()
        self.assertIn("memory_events", tables)
        self.assertIn("memory_decay_runs", tables)

    def test_memory_evidence_merges_and_is_searchable(self):
        memory_id = self.store.add_memory(
            "qq",
            "10001",
            "星星喜欢安静的咖啡馆",
            "preference",
            7,
            8,
            evidence="原话：想找安静一点的地方",
        )
        repeated_id = self.store.add_memory(
            "qq",
            "10001",
            "星星喜欢安静的咖啡馆",
            "preference",
            8,
            9,
            evidence="补充：最好有插座",
        )
        self.assertEqual(memory_id, repeated_id)
        memory = self.store.list_memories("qq", "10001")[0]
        self.assertIn("原话", memory["evidence"])
        self.assertIn("插座", memory["evidence"])
        self.assertEqual(
            len(self.store.list_memories("qq", "10001", "插座")),
            1,
        )
        actions = [
            event["action"]
            for event in self.store.list_memory_events(
                "qq",
                "10001",
                memory_id,
            )
        ]
        self.assertEqual(actions.count("remember"), 2)
        self.assertTrue(
            self.store.delete_memory("qq", "10001", memory_id)
        )
        self.assertEqual(
            self.store.list_memory_events("qq", "10001", memory_id),
            [],
        )

    def test_memory_context_skips_unrelated_and_reinforces_matches(self):
        memory_id = self.store.add_memory(
            "qq",
            "10001",
            "星星怕打雷",
            "fact",
            2,
            2,
        )
        before = self.store.list_memories("qq", "10001")[0]
        self.assertEqual(
            self.store.memory_context("qq", "10001", "咖啡", 5),
            [],
        )
        unchanged = self.store.list_memories("qq", "10001")[0]
        self.assertEqual(unchanged["access_count"], 0)
        self.assertEqual(unchanged["strength"], before["strength"])

        recalled = self.store.memory_context("qq", "10001", "打雷", 5)
        self.assertEqual(recalled, ["星星怕打雷"])
        reinforced = self.store.list_memories("qq", "10001")[0]
        self.assertEqual(reinforced["id"], memory_id)
        self.assertEqual(reinforced["access_count"], 1)
        self.assertGreater(reinforced["strength"], before["strength"])

    def test_memory_archive_restore_and_daily_decay_are_reversible(self):
        now = int(time.time())
        low_id = self.store.add_memory(
            "qq",
            "10001",
            "不太重要的旧事件",
            "event",
            2,
            2,
        )
        high_id = self.store.add_memory(
            "qq",
            "10001",
            "非常重要的长期约定",
            "promise",
            9,
            8,
        )
        connection = sqlite3.connect(self.store.path)
        try:
            connection.execute(
                """UPDATE memories
                   SET strength = 0.16, updated_at = ?, last_used_at = NULL
                   WHERE id IN (?, ?)""",
                (now - 86400, low_id, high_id),
            )
            connection.commit()
        finally:
            connection.close()

        self.assertTrue(self.store.claim_memory_decay("2026-11-04"))
        self.assertFalse(self.store.claim_memory_decay("2026-11-04"))
        result = self.store.decay_memories(now)
        self.assertEqual(result, {"decayed": 2, "archived": 1})
        active_ids = {
            memory["id"]
            for memory in self.store.list_memories("qq", "10001")
        }
        self.assertNotIn(low_id, active_ids)
        self.assertIn(high_id, active_ids)
        archived = self.store.list_memories(
            "qq",
            "10001",
            include_archived=True,
        )
        low = next(memory for memory in archived if memory["id"] == low_id)
        self.assertIsNotNone(low["archived_at"])
        self.assertTrue(
            self.store.set_memory_archived(
                "qq",
                "10001",
                low_id,
                False,
            )
        )
        restored_ids = {
            memory["id"]
            for memory in self.store.list_memories("qq", "10001")
        }
        self.assertIn(low_id, restored_ids)
        actions = [
            event["action"]
            for event in self.store.list_memory_events(
                "qq",
                "10001",
                low_id,
            )
        ]
        self.assertIn("decay_archive", actions)
        self.assertIn("restore", actions)

    def test_memory_tools_respect_scope_permissions_and_secrets(self):
        service = object.__new__(AgentService)
        service.store = self.store
        private_context = {
            "platform": "qq",
            "owner_id": "10001",
            "chat_id": "10001",
            "chat_type": "private",
            "message_id": "message-1",
            "memory_enabled": "1",
            "is_admin": "0",
        }
        remembered = service.memorize_memory_tool(
            {
                "content": "星星偏爱安静的咖啡馆",
                "kind": "preference",
                "importance": 8,
                "confidence": 9,
                "evidence": "原话：想找安静的地方",
            },
            private_context,
        )
        self.assertEqual(remembered["status"], "remembered")
        recalled = service.recall_memory_tool(
            {"query": "安静 咖啡"},
            private_context,
        )
        self.assertEqual(recalled["status"], "ok")
        self.assertEqual(recalled["count"], 1)
        self.assertIn("咖啡馆", recalled["memories"][0]["content"])
        self.assertGreater(recalled["memories"][0]["strength"], 0.35)
        missing = service.recall_memory_tool(
            {"query": "滑雪"},
            private_context,
        )
        self.assertEqual(missing["status"], "not_found")
        self.assertEqual(missing["memories"], [])
        rejected = service.memorize_memory_tool(
            {"content": "网站密码是 secret123"},
            private_context,
        )
        self.assertEqual(rejected["status"], "rejected")

        member_context = {
            "platform": "qqbot",
            "owner_id": "member-openid",
            "chat_id": "group-openid",
            "chat_type": "group",
            "memory_enabled": "1",
            "is_admin": "0",
        }
        forbidden = service.memorize_memory_tool(
            {
                "content": "群活动改到周日",
                "scope": "group",
            },
            member_context,
        )
        self.assertEqual(forbidden["status"], "forbidden")
        admin_context = dict(member_context, is_admin="1")
        group_saved = service.memorize_memory_tool(
            {
                "content": "群活动改到周日",
                "scope": "group",
                "kind": "event",
            },
            admin_context,
        )
        self.assertEqual(group_saved["status"], "remembered")
        group_recalled = service.recall_memory_tool(
            {"query": "周日", "scope": "group"},
            member_context,
        )
        self.assertEqual(group_recalled["status"], "ok")
        self.assertEqual(group_recalled["memories"][0]["scope"], "group")
        forbidden_archive = service.forget_memory_tool(
            {
                "ids": [group_saved["memory_id"]],
                "scope": "group",
            },
            member_context,
        )
        self.assertEqual(forbidden_archive["status"], "forbidden")
        archived = service.forget_memory_tool(
            {
                "ids": [group_saved["memory_id"]],
                "scope": "group",
            },
            admin_context,
        )
        self.assertEqual(archived["status"], "archived")

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
            "鲸鲸",
            "assistant",
            "可以，鲸鲸记下了",
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

    def test_group_activity_resets_idle_state_and_deduplicates(self):
        with patch("errorjiang_agent.store.time.time", return_value=100):
            inserted = self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "星星",
                "周末去吃火锅吗",
                "message-1",
            )
        self.assertTrue(inserted)
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["last_user_at"], 100)
        self.assertGreater(state["last_user_message_id"], 0)
        self.assertEqual(state["unanswered_count"], 0)
        self.assertEqual(
            self.store.get_group_member(
                "qqbot",
                "group-openid",
                "member-openid",
            )["message_count"],
            1,
        )

        self.store.schedule_group_proactive(
            "qqbot",
            "group-openid",
            200,
        )
        with patch("errorjiang_agent.store.time.time", return_value=300):
            self.store.mark_group_proactive_sent(
                "qqbot",
                "group-openid",
                300,
            )
        with patch("errorjiang_agent.store.time.time", return_value=400):
            duplicate = self.store.record_group_activity(
                "qqbot",
                "group-openid",
                "member-openid",
                "星星",
                "周末去吃火锅吗",
                "message-1",
            )
        self.assertFalse(duplicate)
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["last_user_at"], 100)
        self.assertEqual(state["unanswered_count"], 1)

        with patch("errorjiang_agent.store.time.time", return_value=500):
            self.assertTrue(
                self.store.record_group_activity(
                    "qqbot",
                    "group-openid",
                    "member-openid",
                    "星星",
                    "那就周六",
                    "message-2",
                )
            )
        state = self.store.get_group_proactive_state(
            "qqbot",
            "group-openid",
        )
        self.assertEqual(state["last_user_at"], 500)
        self.assertIsNone(state["next_proactive_at"])
        self.assertEqual(state["unanswered_count"], 0)
        self.assertEqual(
            self.store.get_group_member(
                "qqbot",
                "group-openid",
                "member-openid",
            )["message_count"],
            2,
        )

    def test_group_proactive_state_migrates_v2_columns(self):
        path = Path(self.temp.name) / "legacy-proactive.db"
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """CREATE TABLE group_proactive_state (
                       platform TEXT NOT NULL,
                       group_id TEXT NOT NULL,
                       last_user_at INTEGER NOT NULL DEFAULT 0,
                       last_user_message_id INTEGER NOT NULL DEFAULT 0,
                       next_proactive_at INTEGER,
                       last_proactive_at INTEGER,
                       unanswered_count INTEGER NOT NULL DEFAULT 0,
                       last_error TEXT NOT NULL DEFAULT '',
                       updated_at INTEGER NOT NULL,
                       PRIMARY KEY (platform, group_id)
                   )"""
            )
            conn.commit()
        finally:
            conn.close()
        migrated = AgentStore(path)
        conn = sqlite3.connect(path)
        try:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(group_proactive_state)"
                ).fetchall()
            }
        finally:
            conn.close()
        self.assertIn("awaiting_reply_until", columns)
        self.assertIn("last_proactive_message_id", columns)
        self.assertIn("last_proactive_run_id", columns)
        self.assertIn("last_effective_reply_at", columns)
        self.assertTrue(
            migrated.get_group_proactive_override(
                "qqbot",
                "group-openid",
            )
            is None
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

    def test_memory_policy_selects_stable_information_only(self):
        explicit = memory_policy.extract_explicit_memory(
            "记住：我对花生过敏"
        )
        self.assertEqual(explicit["content"], "我对花生过敏")
        self.assertEqual(explicit["kind"], "preference")
        self.assertIsNone(
            memory_policy.extract_explicit_memory(
                "记住：我的密码是 secret123"
            )
        )
        self.assertTrue(
            memory_policy.should_extract_memory_now(
                "以后请叫我阿星"
            )[0]
        )
        self.assertTrue(
            memory_policy.should_extract_memory_now(
                "周六一起整理书架吧"
            )[0]
        )
        self.assertFalse(
            memory_policy.should_extract_memory_now(
                "今天中午吃什么"
            )[0]
        )

    def test_remember_exchange_skips_chat_and_limits_immediate_calls(self):
        class Extractor:
            def __init__(self):
                self.calls = 0

            def chat(self, messages, tools):
                self.calls += 1
                return {"content": '{"memories":[],"events":[]}'}

        service = object.__new__(AgentService)
        service.store = self.store
        service.deepseek = Extractor()
        service.remember_exchange(
            "qq",
            "10001",
            "今天中午吃什么",
            "还没想好",
        )
        self.assertEqual(service.deepseek.calls, 0)
        service.store.save_settings(
            "qq",
            "10001",
            {"memory_immediate_extraction_daily_limit": 1},
        )
        service.remember_exchange(
            "qq",
            "10001",
            "以后请叫我阿星",
            "知道啦",
        )
        service.remember_exchange(
            "qq",
            "10001",
            "我喜欢喝美式咖啡",
            "记住啦",
        )
        self.assertEqual(service.deepseek.calls, 1)
        service.remember_exchange(
            "qq",
            "10001",
            "记住：我不吃香菜",
            "好",
        )
        self.assertEqual(service.deepseek.calls, 1)
        memories = self.store.list_memories("qq", "10001")
        self.assertTrue(
            any("不吃香菜" in item["content"] for item in memories)
        )
        self.assertTrue(
            any(item["source"] == "explicit_chat" for item in memories)
        )

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
            "嗯，鲸鲸记下了。",
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
        self.assertEqual(
            AgentService.chat_bubbles("emmm 等我吃完这口 || 好啦发来"),
            ["emmm 等我吃完这口", "好啦发来"],
        )
        self.assertEqual(
            AgentService.chat_bubbles("```js\nconst next = a || b;\n```"),
            ["```js\nconst next = a || b;\n```"],
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

    def test_empty_mention_uses_natural_reply(self):
        from errorjiang_agent.service import (
            EMPTY_MENTION_REPLIES,
            EMPTY_STICKER_REPLIES,
        )

        service = object.__new__(AgentService)
        replies = []
        service.send_reply = lambda event, text: replies.append(text)
        event = MessageEvent(
            self_id="bot",
            user_id="member-openid",
            message_type="group",
            chat_id="group-openid",
            message_id="empty-mention",
            text="",
            to_me=True,
            platform="qqbot",
        )
        service._process_event(event)
        self.assertIn(replies[-1], EMPTY_MENTION_REPLIES)
        self.assertTrue(
            all(
                "请直接告诉我" not in reply
                for reply in EMPTY_MENTION_REPLIES
            )
        )
        service._process_event(event, saved_stickers=1)
        self.assertIn(replies[-1], EMPTY_STICKER_REPLIES)

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

    def test_chat_reply_delay_is_casual_only_and_occasionally_slower(self):
        settings = {"chat_human_delay": True}
        self.assertTrue(AgentService.should_humanize_chat_delay(settings, []))
        self.assertFalse(
            AgentService.should_humanize_chat_delay(
                settings,
                ["errorjiang_footprints_search"],
            )
        )
        self.assertFalse(
            AgentService.should_humanize_chat_delay(
                {"chat_human_delay": False},
                [],
            )
        )
        with patch("errorjiang_agent.service.random.uniform", return_value=0.2), patch(
            "errorjiang_agent.service.random.random",
            return_value=0.99,
        ):
            normal = AgentService.chat_typing_delay("今天有点累，不太想说话。")
        with patch("errorjiang_agent.service.random.uniform", return_value=0.2), patch(
            "errorjiang_agent.service.random.random",
            return_value=0.01,
        ):
            occasional = AgentService.chat_typing_delay("今天有点累，不太想说话。")
        self.assertGreaterEqual(normal, 0.7)
        self.assertLessEqual(normal, 3.55)
        self.assertGreater(occasional, normal)
        self.assertLessEqual(occasional, 6.2)
        with patch("errorjiang_agent.service.random.random", return_value=0.1):
            self.assertTrue(AgentService.should_send_casual_sticker([]))
        with patch("errorjiang_agent.service.random.random", return_value=0.1):
            self.assertFalse(
                AgentService.should_send_casual_sticker(
                    ["errorjiang_footprints_search"],
                )
            )

    def test_send_reply_only_sleeps_for_human_delay(self):
        sent = []
        service = object.__new__(AgentService)
        service.qqbot = SimpleNamespace(
            send_message=lambda *args: sent.append(args),
        )
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
        with patch("errorjiang_agent.service.time.sleep") as sleep:
            service.send_reply(event, "即时回复")
        sleep.assert_not_called()
        with patch.object(
            service,
            "chat_typing_delay",
            return_value=1.25,
        ) as typing_delay, patch("errorjiang_agent.service.time.sleep") as sleep:
            service.send_reply(event, "闲聊回复", human_delay=True)
        typing_delay.assert_called_once_with("闲聊回复")
        sleep.assert_called_once_with(1.25)
        self.assertEqual(len(sent), 2)

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
        stickers = self.store.list_stickers("0")
        self.assertEqual(len(stickers), 1)
        self.assertEqual(stickers[0]["kind"], "image")
        self.assertTrue(
            (service.sticker_dir / stickers[0]["ref"]).is_file()
        )

    def test_unmentioned_group_image_is_collected_to_pending_only(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"\x89PNG\r\n\x1a\npending-image"

        service = object.__new__(AgentService)
        service.store = self.store
        service.sticker_dir = Path(self.temp.name) / "stickers"
        service.sticker_dir.mkdir()
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
            message_id="pending-auto-collect",
            text="",
            to_me=False,
            platform="qqbot",
            attachments=(
                {
                    "content_type": "image/png",
                    "filename": "候选项.png",
                    "url": "https://example.com/pending.png",
                },
            ),
        )
        with patch(
            "errorjiang_agent.service.urlopen",
            return_value=FakeResponse(),
        ):
            service._handle_message_event(event, activity_observed=True)
        self.assertEqual(self.store.list_stickers("0"), [])
        candidates = self.store.list_sticker_candidates("0")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_name"], "候选项.png")

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

    def test_llm_provider_and_fallback_config_are_loaded(self):
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai-compatible",
                "LLM_BASE_URL": "https://llm.example/v1",
                "LLM_API_KEY": "primary-key",
                "LLM_MODEL": "primary-model",
                "LLM_FALLBACK_PROVIDER": "deepseek",
                "LLM_FALLBACK_BASE_URL": "https://api.deepseek.com",
                "LLM_FALLBACK_API_KEY": "fallback-key",
                "LLM_FALLBACK_MODEL": "deepseek-chat",
                "ERRORJIANG_AGENT_CONTEXT_CHAR_LIMIT": "24000",
            },
            clear=False,
        ):
            config = Config.load(Path(self.temp.name))
        self.assertEqual(config.llm_provider, "openai-compatible")
        self.assertEqual(config.llm_api_key, "primary-key")
        self.assertEqual(config.llm_model, "primary-model")
        self.assertEqual(config.llm_fallback_provider, "deepseek")
        self.assertEqual(config.llm_fallback_api_key, "fallback-key")
        self.assertEqual(config.context_char_limit, 24000)

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

    def test_onebot_json_card_extracts_supported_media_without_mention(self):
        card = json.dumps(
            {
                "meta": {
                    "detail_1": {
                        "title": "测试视频",
                        "desc": "这是卡片摘要",
                        "qqdocurl": (
                            "https://www.bilibili.com/video/BV1xx411c7mD"
                        ),
                    }
                }
            },
            ensure_ascii=False,
        )
        event = parse_message_event(
            {
                "post_type": "message",
                "message_type": "group",
                "self_id": 20000,
                "user_id": 10001,
                "group_id": 30001,
                "message_id": 15,
                "message": [
                    {"type": "json", "data": {"data": card}},
                ],
            }
        )
        self.assertIsNotNone(event)
        self.assertFalse(event.to_me)
        self.assertEqual(
            event.shared_media[0]["platform"],
            "bilibili",
        )
        self.assertEqual(event.shared_media[0]["title_hint"], "测试视频")

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
                        "username": "鲸鲸",
                        "bot": True,
                    }
                ],
                "message_scene": {
                    "source": "default",
                    "ext": ["ref_msg_idx=REFIDX-1"],
                },
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertTrue(event.to_me)
        self.assertTrue(event.group_full)
        self.assertTrue(event.referenced)
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

    def test_qqbot_tuwen_amap_card_is_parsed_as_location(self):
        event = parse_qqbot_event(
            "GROUP_MESSAGE_CREATE",
            {
                "id": "message-amap-tuwen",
                "content": " ",
                "group_openid": "group-openid",
                "author": {
                    "member_openid": "member-openid",
                    "username": "星星",
                },
                "message_type": 3,
                "ark_data": {
                    "ark_type": "tuwen",
                    "ark_name": "高德地图",
                    "fields": {
                        "title": "千阳县人民政府",
                        "desc": "陕西省宝鸡市千阳县",
                        "jump_url": (
                            "https://uri.amap.com/marker?"
                            "position=107.110015,34.644625"
                        ),
                    },
                },
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertTrue(event.group_full)
        self.assertEqual(event.location["title"], "千阳县人民政府")
        self.assertAlmostEqual(event.location["lat"], 34.644625)
        self.assertAlmostEqual(event.location["lng"], 107.110015)

    def test_qqbot_full_group_media_card_is_parsed_without_mention(self):
        event = parse_qqbot_event(
            "GROUP_MESSAGE_CREATE",
            {
                "id": "message-douyin-card",
                "content": " ",
                "group_openid": "group-openid",
                "author": {
                    "member_openid": "member-openid",
                    "username": "星星",
                },
                "ark_data": {
                    "ark_type": "news",
                    "fields": {
                        "title": "一条抖音视频",
                        "desc": "卡片自带的视频简介",
                        "jump_url": "https://v.douyin.com/abc123/",
                    },
                },
            },
            "bot-qq",
        )
        self.assertIsNotNone(event)
        self.assertFalse(event.to_me)
        self.assertEqual(event.shared_media[0]["platform"], "douyin")
        self.assertEqual(
            event.shared_media[0]["title_hint"],
            "一条抖音视频",
        )

    def test_amap_callapp_nested_payload_is_parsed(self):
        nested = (
            "androidamap?action=shorturl&p=B0HG3CD2JX,"
            "34.25213848901167,108.95823955535886,"
            "朱秀英梆梆肉葫芦头(下马陵店),下马陵六号"
        )
        final_url = "https://m.amap.com/callAPP?" + urlencode(
            {"android": nested}
        )
        location = extract_location_event(
            {
                "ark_data": {
                    "ark_type": "tuwen",
                    "ark_name": "图文H5",
                    "fields": {"jump_url": final_url},
                }
            }
        )
        self.assertIsNotNone(location)
        self.assertEqual(location["title"], "朱秀英梆梆肉葫芦头(下马陵店)")
        self.assertEqual(location["address"], "下马陵六号")
        self.assertAlmostEqual(location["lat"], 34.25213848901167)
        self.assertAlmostEqual(location["lng"], 108.95823955535886)

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


class MediaLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AgentStore(Path(self.temp.name) / "agent.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_extracts_only_supported_links_and_caps_at_two(self):
        text = (
            "看看 https://b23.tv/first "
            "https://www.douyin.com/video/123 "
            "https://www.xiaohongshu.com/explore/abc "
            "https://example.com/not-supported"
        )
        media = media_links.extract_shared_media(text)
        self.assertEqual(
            [item["platform"] for item in media],
            ["bilibili", "douyin"],
        )

    def test_extracts_nested_card_url_and_title_hint(self):
        card = json.dumps(
            {
                "meta": {
                    "detail_1": {
                        "title": "微博卡片标题",
                        "desc": "卡片摘要",
                        "qqdocurl": "https://m.weibo.cn/detail/123456",
                    }
                }
            },
            ensure_ascii=False,
        )
        media = media_links.extract_shared_media("", {"card": card})
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]["platform"], "weibo")
        self.assertEqual(media[0]["title_hint"], "微博卡片标题")
        self.assertEqual(media[0]["description_hint"], "卡片摘要")

    def test_platform_host_matching_is_exact(self):
        cases = {
            "https://www.bilibili.com/video/BV1xx411c7mD": "bilibili",
            "https://v.douyin.com/abc": "douyin",
            "https://m.weibo.cn/detail/1": "weibo",
            "https://music.163.com/song?id=1": "netease",
            "https://www.xiaohongshu.com/explore/1": "xiaohongshu",
            "https://notbilibili.com/video/1": "",
            "https://example.com/www.bilibili.com": "",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(media_links.platform_for_url(url), expected)

    def test_private_and_local_addresses_are_rejected(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ]
        with patch(
            "errorjiang_agent.media_links.socket.getaddrinfo",
            return_value=addresses,
        ):
            self.assertFalse(
                media_links.safe_public_url("https://www.bilibili.com/video/x")
            )
        addresses = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ]
        with patch(
            "errorjiang_agent.media_links.socket.getaddrinfo",
            return_value=addresses,
        ):
            self.assertTrue(
                media_links.safe_public_url("https://www.bilibili.com/video/x")
            )

    def test_bilibili_api_returns_metadata_without_media_download(self):
        source = "https://www.bilibili.com/video/BV1xx411c7mD"
        page = b"<html><title>fallback</title></html>"
        payload = {
            "data": {
                "title": "B站测试视频",
                "desc": "视频简介",
                "duration": 125,
                "pic": "//i.example/cover.jpg",
                "owner": {"name": "测试UP主"},
                "stat": {"view": 1234},
            }
        }
        requested = []

        def fetch(url, **_kwargs):
            requested.append(url)
            if url == source:
                return source, page
            return url, json.dumps(payload, ensure_ascii=False).encode()

        with patch.object(media_links, "_fetch_url", side_effect=fetch):
            parsed = media_links.parse_shared_media(
                [{"url": source, "platform": "bilibili"}]
            )
        self.assertEqual(parsed[0]["title"], "B站测试视频")
        self.assertEqual(parsed[0]["author"], "测试UP主")
        self.assertEqual(parsed[0]["description"], "视频简介")
        self.assertIn("播放 1234", parsed[0]["extra"])
        self.assertEqual(len(requested), 2)
        self.assertTrue(requested[1].startswith("https://api.bilibili.com/"))

    def test_netease_song_album_and_playlist_metadata(self):
        cases = [
            (
                "https://music.163.com/song?id=11",
                {
                    "songs": [
                        {
                            "name": "测试歌曲",
                            "duration": 61000,
                            "artists": [{"name": "歌手甲"}],
                            "album": {"name": "专辑甲"},
                        }
                    ]
                },
                "测试歌曲",
                "歌手甲",
            ),
            (
                "https://music.163.com/album?id=22",
                {
                    "album": {
                        "name": "测试专辑",
                        "artist": {"name": "歌手乙"},
                        "size": 8,
                    }
                },
                "测试专辑",
                "歌手乙",
            ),
            (
                "https://music.163.com/playlist?id=33",
                {
                    "result": {
                        "name": "测试歌单",
                        "creator": {"nickname": "收藏者"},
                        "trackCount": 12,
                    }
                },
                "测试歌单",
                "收藏者",
            ),
        ]
        for url, payload, title, author in cases:
            with self.subTest(url=url):
                def fetch(api, **_kwargs):
                    if api == url:
                        return url, b""
                    return api, json.dumps(payload).encode()

                with patch.object(media_links, "_fetch_url", side_effect=fetch):
                    parsed = media_links.parse_shared_media(
                        [{"url": url, "platform": "netease"}]
                    )
                self.assertEqual(parsed[0]["title"], title)
                self.assertEqual(parsed[0]["author"], author)

    def test_weibo_api_metadata_and_html_fallback(self):
        source = "https://m.weibo.cn/detail/123456"
        html = (
            '<meta property="og:title" content="微博网页标题">'
            '<meta name="description" content="网页摘要">'
        ).encode()
        payload = {
            "data": {
                "text": "<p>微博正文</p>",
                "user": {"screen_name": "博主"},
            }
        }
        with patch.object(
            media_links,
            "_fetch_url",
            side_effect=[
                (source, html),
                ("api", json.dumps(payload).encode()),
            ],
        ):
            parsed = media_links.parse_shared_media(
                [{"url": source, "platform": "weibo"}]
            )
        self.assertEqual(parsed[0]["title"], "微博正文")
        self.assertEqual(parsed[0]["author"], "博主")

        with patch.object(
            media_links,
            "_fetch_url",
            side_effect=[
                (source, html),
                ValueError("api blocked"),
            ],
        ):
            parsed = media_links.parse_shared_media(
                [{"url": source, "platform": "weibo"}]
            )
        self.assertEqual(parsed[0]["title"], "微博网页标题")
        self.assertEqual(parsed[0]["description"], "网页摘要")

    def test_douyin_and_xhs_keep_card_hints_when_page_fetch_fails(self):
        cases = [
            ("https://v.douyin.com/abc/", "douyin", "抖音卡片"),
            ("https://xhslink.com/a/abc", "xiaohongshu", "小红书卡片"),
        ]
        for url, platform, title in cases:
            with self.subTest(platform=platform):
                media = media_links.extract_shared_media(
                    "",
                    {
                        "ark_data": {
                            "fields": {
                                "title": title,
                                "desc": "卡片摘要",
                                "jump_url": url,
                            }
                        }
                    },
                )
                with patch.object(
                    media_links,
                    "_fetch_url",
                    side_effect=ValueError("blocked"),
                ):
                    parsed = media_links.parse_shared_media(media)
                self.assertEqual(parsed[0]["platform"], platform)
                self.assertEqual(parsed[0]["title"], title)
                self.assertEqual(parsed[0]["description"], "卡片摘要")
                self.assertIn("分享卡片信息", parsed[0]["note"])

    def test_group_media_card_bypasses_mention_gate(self):
        class EmptyStore:
            @staticmethod
            def get_group_messages(platform, chat_id, limit):
                return []

        config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset(),
        )
        pipeline = build_group_event_pipeline(
            GroupConversationPolicy(EmptyStore()),
            config,
        )
        event = MessageEvent(
            self_id="bot",
            user_id="member",
            message_type="group",
            chat_id="group",
            message_id="media-card",
            text="",
            to_me=False,
            platform="qqbot",
            group_full=True,
            shared_media=(
                {
                    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                    "platform": "bilibili",
                },
            ),
        )
        routed, state = pipeline.run(event)
        self.assertIsNotNone(routed)
        self.assertTrue(routed.to_me)
        self.assertTrue(state.auto_reply)
        self.assertEqual(state.reason, "shared_media")

        unsupported = replace(
            event,
            text="https://example.com/ordinary-link",
            shared_media=(),
        )
        routed, _ = pipeline.run(unsupported, EventState())
        self.assertIsNone(routed)

    def test_service_passes_untrusted_media_metadata_to_model(self):
        captured = {}

        class FakeBrain:
            last_used_tools = []

            def reply(
                self,
                user_text,
                history,
                tool_context,
                memories=None,
            ):
                captured["user_text"] = user_text
                captured["memories"] = list(memories or [])
                return "看懂啦"

        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            context_messages=8,
            errorjiang_base_url="http://127.0.0.1:8000",
            errorjiang_token="test-token",
        )
        service.relationship_context = lambda *_args: {}
        service.timeline_context = lambda *_args: []
        service.relationship_prompt = lambda *_args: ""
        service.persona_prompt = lambda *_args: ""
        service.shared_media_context = lambda _event: (
            "平台：B站\n标题：一条测试视频\n作者：测试UP主"
        )
        service.should_humanize_chat_delay = lambda *_args: False
        service.should_send_casual_sticker = lambda *_args: False
        service.selected_sticker = lambda *_args: None
        service.send_reply = lambda *_args, **_kwargs: None
        service.update_relationship_after_exchange = lambda *_args: None
        service.remember_exchange = lambda *_args: None
        service.executor = SimpleNamespace(
            submit=lambda *_args, **_kwargs: None
        )
        service.build_brain = lambda _client: FakeBrain()
        event = MessageEvent(
            self_id="bot",
            user_id="admin-openid",
            message_type="private",
            chat_id="admin-openid",
            message_id="media-service",
            text="",
            to_me=True,
            platform="qqbot",
            shared_media=(
                {
                    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                    "platform": "bilibili",
                },
            ),
        )
        service._process_event(
            event,
            target_user_id=0,
            is_admin=True,
        )
        self.assertEqual(captured["user_text"], "分享了一个内容卡片")
        self.assertTrue(
            any(
                "不可信文本" in item
                and "一条测试视频" in item
                for item in captured["memories"]
            )
        )


class GroupLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AgentStore(Path(self.temp.name) / "agent.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_extracts_repeated_group_terms_without_raw_messages(self):
        messages = [
            {
                "role": "user",
                "member_id": "member-a",
                "content": "这波操作真是绝绝子",
            },
            {
                "role": "user",
                "member_id": "member-b",
                "content": "绝绝子，确实厉害",
            },
            {
                "role": "user",
                "member_id": "member-a",
                "content": "这个梗 yyds",
            },
            {
                "role": "user",
                "member_id": "member-b",
                "content": "yyds 我先笑为敬",
            },
            {
                "role": "user",
                "member_id": "member-a",
                "content": "今天中午吃什么",
            },
            {
                "role": "user",
                "member_id": "member-a",
                "content": "验证码 abcdef",
            },
            {
                "role": "user",
                "member_id": "member-b",
                "content": "验证码 ghijkl",
            },
        ]
        candidates = group_learning.extract_jargon_candidates(messages)
        terms = {item["term"] for item in candidates}
        self.assertIn("yyds", terms)
        self.assertTrue(any("绝绝子" in term for term in terms))
        self.assertNotIn("什么", terms)
        self.assertNotIn("验证码", terms)
        self.assertTrue(
            all(set(item) == {
                "term",
                "occurrences",
                "member_count",
                "score",
            } for item in candidates)
        )

    def test_jargon_review_approval_and_context_match(self):
        saved = self.store.upsert_group_jargon_candidates(
            "qqbot",
            "group-openid",
            [
                {
                    "term": "绝绝子",
                    "occurrences": 4,
                    "member_count": 2,
                },
                {
                    "term": "yyds",
                    "occurrences": 3,
                    "member_count": 2,
                },
            ],
        )
        self.assertEqual(saved, 2)
        pending = self.store.list_group_jargon()
        self.assertEqual(len(pending), 2)
        approved = self.store.update_group_jargon(
            pending[0]["id"],
            status="approved",
            meaning="表示非常喜欢或厉害",
            example="这波操作绝绝子",
        )
        self.assertEqual(approved["status"], "approved")
        matched = self.store.approved_group_jargon(
            "qqbot",
            "group-openid",
            "这操作绝绝子",
        )
        self.assertEqual(matched[0]["term"], "绝绝子")
        self.assertEqual(
            self.store.approved_group_jargon(
                "qqbot",
                "other-group",
                "这操作绝绝子",
            ),
            [],
        )
        self.assertTrue(self.store.delete_group_jargon(approved["id"]))

    def test_service_scans_and_injects_only_approved_group_jargon(self):
        first_messages = [
            "今天这个操作真是绝绝子",
            "绝绝子，这个也太好吃了",
            "这波发挥真的绝绝子",
            "不愧是你们，绝绝子",
        ]
        for index in range(12):
            member = f"member-{index % 2}"
            content = (
                first_messages[index]
                if index < 4
                else f"普通聊天内容 {index}"
            )
            self.store.add_group_message(
                "qqbot",
                "group-openid",
                member,
                member,
                "user",
                content,
                f"jargon-scan-{index}",
            )
        service = object.__new__(AgentService)
        service.store = self.store
        service._group_jargon_lock = threading.Lock()
        service._group_jargon_last_scan = {}
        event = MessageEvent(
            self_id="bot",
            user_id="member-0",
            message_type="group",
            chat_id="group-openid",
            message_id="jargon-scan",
            text="今天这个操作绝绝子",
            to_me=False,
            platform="qqbot",
            group_full=True,
        )
        with patch(
            "errorjiang_agent.service.time.time",
            return_value=int(time.time()),
        ):
            self.assertGreater(service._maybe_scan_group_jargon(event), 0)
        candidates = self.store.list_group_jargon()
        self.assertTrue(any("绝绝子" in item["term"] for item in candidates))
        item = next(
            item for item in candidates if "绝绝子" in item["term"]
        )
        self.store.update_group_jargon(
            item["id"],
            status="approved",
            meaning="表示非常厉害或喜欢",
        )
        self.assertIn(
            "表示非常厉害或喜欢",
            service.group_jargon_context(
                "qqbot",
                "group-openid",
                "这操作绝绝子",
            ),
        )
        self.assertEqual(
            service.group_jargon_context(
                "qqbot",
                "other-group",
                "这操作绝绝子",
            ),
            "",
        )
        self.store.save_settings(
            "qqbot",
            "0",
            {"group_jargon_enabled": False},
        )
        service._group_jargon_last_scan = {}
        with patch(
            "errorjiang_agent.service.time.time",
            return_value=int(time.time()) + 700,
        ):
            self.assertEqual(service._maybe_scan_group_jargon(event), 0)

    def test_active_activity_level_can_join_lively_group_question(self):
        with patch(
            "errorjiang_agent.store.time.time",
            return_value=1000,
        ):
            for index, member in enumerate(
                ("member-a", "member-b", "member-a"),
            ):
                self.store.add_group_message(
                    "qqbot",
                    "group-openid",
                    member,
                    member,
                    "user",
                    f"正在聊天 {index}",
                    f"active-chat-{index}",
                )
        levels = {"value": "active"}
        policy = GroupConversationPolicy(
            self.store,
            lambda _event: {
                "group_activity_level": levels["value"],
            },
        )
        event = MessageEvent(
            self_id="bot",
            user_id="member-c",
            message_type="group",
            chat_id="group-openid",
            message_id="active-question",
            text="有人推荐附近好吃的吗？",
            to_me=False,
            platform="qqbot",
            group_full=True,
        )
        with patch(
            "errorjiang_agent.routing.time.time",
            return_value=1010,
        ), patch(
            "errorjiang_agent.routing.random.random",
            return_value=0.1,
        ):
            self.assertTrue(policy.wants_reply(event))
            routed, state = build_group_event_pipeline(
                policy,
                SimpleNamespace(
                    group_enabled=True,
                    group_ids=frozenset(),
                    qqbot_group_ids=frozenset(),
                ),
            ).run(event)
            self.assertIsNotNone(routed)
            self.assertTrue(routed.to_me)
            self.assertEqual(state.reason, "group_conversation")
            topic_event = replace(
                event,
                message_id="active-topic",
                text="这个新游戏看起来挺有意思",
            )
            self.assertTrue(policy.wants_reply(topic_event))
        levels["value"] = "balanced"
        with patch(
            "errorjiang_agent.routing.time.time",
            return_value=1010,
        ):
            self.assertFalse(policy.wants_reply(event))


class AgentOperationalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AgentStore(Path(self.temp.name) / "agent.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_group_quiet_commands_and_ambient_suppression(self):
        service = object.__new__(AgentService)
        service.store = self.store
        service.config = SimpleNamespace(
            admin_qqs=frozenset({"admin"}),
        )
        replies = []
        service.send_reply = lambda _event, text: replies.append(text)
        personal = MessageEvent(
            self_id="bot",
            user_id="member-a",
            message_type="group",
            chat_id="group-openid",
            message_id="quiet-personal",
            text="安静 5 分钟",
            to_me=True,
            platform="qq",
        )
        self.assertTrue(service.handle_group_quiet_command(personal))
        self.assertIsNotNone(
            self.store.group_quiet_active(
                "qq",
                "group-openid",
                "member-a",
            )
        )
        self.assertTrue(
            service.handle_group_quiet_command(
                replace(personal, message_id="resume", text="恢复")
            )
        )
        self.assertIsNone(
            self.store.group_quiet_active(
                "qq",
                "group-openid",
                "member-a",
            )
        )
        admin_group = replace(
            personal,
            user_id="admin",
            message_id="quiet-group",
            text="群里安静 1 小时",
        )
        self.assertTrue(service.handle_group_quiet_command(admin_group))
        state = self.store.group_quiet_active(
            "qq",
            "group-openid",
            "member-b",
        )
        self.assertEqual(state["member_id"], "*")
        non_admin = replace(
            admin_group,
            user_id="member-a",
            message_id="quiet-group-denied",
        )
        self.assertTrue(service.handle_group_quiet_command(non_admin))
        self.assertIn("只有管理员", replies[-1])

        service._group_ambient_lock = threading.Lock()
        service._group_ambient_state = {}
        service._group_runtime_settings = lambda _event: {
            "group_reply_control_enabled": True,
            "group_reply_max_per_10m": 6,
        }
        ambient = replace(
            personal,
            message_id="quiet-ambient",
            text="那这个还有吗？",
        )
        self.assertEqual(
            service._group_auto_reply_suppression_reason(
                ambient,
                "group_conversation",
            ),
            "quiet",
        )

    def test_metered_provider_and_diagnostics_payload(self):
        class Provider:
            name = "test"

            def chat(self, messages, tools):
                return {"content": "ok"}

            def web_search(self, query, count=5, original_question=""):
                return {"results": [{"title": "ok"}]}

            def web_fetch(self, url):
                return {"content": "page"}

        metered = MeteredProvider(
            Provider(),
            self.store.record_agent_metric,
        )
        self.assertEqual(metered.chat([], []), {"content": "ok"})
        self.assertEqual(metered.web_search("测试", 1), {"results": [{"title": "ok"}]})
        service = object.__new__(AgentService)
        service.store = self.store
        service.deepseek = metered
        service.started_at = int(time.time())
        service.qqbot = SimpleNamespace(
            status=lambda: {"enabled": True, "connected": True}
        )
        for attribute in (
            "_proactive_thread",
            "_reminder_thread",
            "_memory_consolidation_thread",
        ):
            setattr(
                service,
                attribute,
                SimpleNamespace(is_alive=lambda: True),
            )
        service._qqbot_thread = SimpleNamespace(is_alive=lambda: True)
        payload = service.diagnostics_payload("search_check")
        self.assertTrue(payload["search_check"]["ok"])
        self.assertTrue(payload["threads"]["proactive"]["alive"])
        self.assertGreaterEqual(payload["metrics"]["total_calls"], 3)
        self.assertGreater(payload["database"]["size_bytes"], 0)

    def test_quiet_command_is_auto_accepted_by_group_pipeline(self):
        policy = GroupConversationPolicy(self.store)
        event = MessageEvent(
            self_id="bot",
            user_id="member",
            message_type="group",
            chat_id="group",
            message_id="quiet-route",
            text="安静一会儿",
            to_me=False,
            platform="qqbot",
            group_full=True,
        )
        routed, state = build_group_event_pipeline(
            policy,
            SimpleNamespace(
                group_enabled=True,
                group_ids=frozenset(),
                qqbot_group_ids=frozenset(),
            ),
        ).run(event)
        self.assertIsNotNone(routed)
        self.assertTrue(routed.to_me)
        self.assertEqual(state.reason, "group_conversation")


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


class AgentInfrastructureTests(unittest.TestCase):
    def test_adapter_registry_parses_onebot_and_qqbot(self):
        registry = AdapterRegistry([OneBotAdapter(), QQBotAdapter()])
        onebot = registry.parse(
            "qq",
            "message",
            {
                "post_type": "message",
                "message_type": "private",
                "self_id": 1,
                "user_id": 2,
                "message_id": 3,
                "raw_message": "你好",
            },
            "1",
        )
        self.assertIsNotNone(onebot)
        self.assertEqual(onebot.platform, "qq")
        self.assertEqual(onebot.text, "你好")

        qqbot = registry.parse(
            "qqbot",
            "C2C_MESSAGE_CREATE",
            {
                "id": "qq-message",
                "content": "在吗",
                "author": {
                    "user_openid": "user-openid",
                    "username": "星星",
                },
            },
            "bot",
        )
        self.assertIsNotNone(qqbot)
        self.assertEqual(qqbot.platform, "qqbot")
        self.assertEqual(qqbot.user_id, "user-openid")

    def test_provider_registry_and_fallback_chain(self):
        class FailingProvider:
            name = "primary"

            def chat(self, messages, tools):
                raise AgentError("primary unavailable")

        class WorkingProvider:
            name = "backup"

            def chat(self, messages, tools):
                return {"role": "assistant", "content": "backup reply"}

            def web_search(self, query, count=5, original_question=""):
                return {"query": query, "untrusted": True, "results": []}

        chain = FallbackLLMProvider(
            [FailingProvider(), WorkingProvider()]
        )
        self.assertEqual(
            chain.chat([], [])["content"],
            "backup reply",
        )
        self.assertEqual(chain.web_search("test")["query"], "test")

        registry = ProviderRegistry()
        registry.register(
            "fake",
            lambda base_url, api_key, model: WorkingProvider(),
        )
        provider = registry.create("fake", "", "", "")
        self.assertEqual(provider.name, "backup")

    def test_openai_compatible_provider_uses_standard_chat_payload(self):
        provider = OpenAICompatibleProvider(
            "https://llm.example/v1/",
            "token",
            "model-a",
        )
        with patch(
            "errorjiang_agent.providers.post_json",
            return_value={
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}}
                ]
            },
        ) as post:
            result = provider.chat(
                [{"role": "user", "content": "hi"}],
                [],
            )
        self.assertEqual(result["content"], "ok")
        self.assertEqual(
            post.call_args.args[0],
            "https://llm.example/v1/chat/completions",
        )
        self.assertEqual(post.call_args.args[1]["model"], "model-a")

    def test_context_window_is_budgeted_and_keeps_latest_messages(self):
        history = [
            {"role": "user", "content": "old message"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "newest message"},
        ]
        compacted = ContextWindow(
            max_messages=2,
            max_chars=8,
            max_message_chars=20,
        ).compact(history)
        self.assertEqual(len(compacted), 1)
        self.assertTrue(compacted[-1]["content"].endswith("message"))
        self.assertNotIn("old message", [item["content"] for item in compacted])

    def test_tool_registry_filters_search_admin_and_disabled_tools(self):
        definitions = [
            {"type": "function", "function": {"name": "normal"}},
            {"type": "function", "function": {"name": "web"}},
            {"type": "function", "function": {"name": "admin"}},
        ]
        registry = ToolRegistry(definitions)
        registry.register(
            "normal",
            lambda arguments, context, text: {"ok": True},
        )
        registry.register(
            "web",
            lambda arguments, context, text: {"ok": True},
            requires_web_search=True,
        )
        registry.register(
            "admin",
            lambda arguments, context, text: {"ok": True},
            admin_only=True,
        )
        names = [
            item["function"]["name"]
            for item in registry.available(
                {
                    "tools_enabled": "1",
                    "web_search_enabled": "0",
                    "is_admin": "0",
                }
            )
        ]
        self.assertEqual(names, ["normal"])
        self.assertEqual(
            registry.available({"tools_enabled": "0"}),
            [],
        )
        with self.assertRaises(AgentError):
            registry.execute(
                "admin",
                {},
                {"is_admin": "0"},
                "",
            )

    def test_every_model_tool_has_a_registered_handler(self):
        brain = AgentBrain(
            object(),
            object(),
            lambda arguments, context: {},
        )
        defined = {
            item["function"]["name"]
            for item in TOOLS
        }
        self.assertEqual(set(brain.tool_registry.names()), defined)

    def test_group_event_pipeline_auto_mentions_and_bypasses_for_location(self):
        class EmptyStore:
            @staticmethod
            def get_group_messages(platform, chat_id, limit):
                return []

        policy = GroupConversationPolicy(EmptyStore())
        config = SimpleNamespace(
            group_enabled=True,
            group_ids=frozenset(),
            qqbot_group_ids=frozenset(),
        )
        pipeline = build_group_event_pipeline(policy, config)
        event = MessageEvent(
            self_id="bot",
            user_id="member",
            message_type="group",
            chat_id="group",
            message_id="message",
            text="鲸鲸，在吗",
            to_me=False,
            platform="qqbot",
            group_full=True,
        )
        routed, state = pipeline.run(event)
        self.assertIsNotNone(routed)
        self.assertTrue(routed.to_me)
        self.assertTrue(state.auto_reply)

        location_event = replace(
            event,
            text="",
            location={"title": "测试地点"},
        )
        routed_location, _ = pipeline.run(location_event, EventState())
        self.assertIsNotNone(routed_location)
        self.assertFalse(routed_location.to_me)

        unrelated = replace(event, text="今天中午吃什么")
        routed_unrelated, _ = pipeline.run(unrelated, EventState())
        self.assertIsNone(routed_unrelated)

    def test_persona_prompt_composes_preset_and_custom_preference(self):
        prompt = compose_persona_prompt(
            {
                "persona_preset": "理性",
                "persona_custom_prompt": "少用感叹号",
            }
        )
        self.assertIn("理性", prompt)
        self.assertIn("少用感叹号", prompt)

    def test_service_brain_factory_keeps_hot_search_connected(self):
        service = object.__new__(AgentService)
        service.config = SimpleNamespace(
            max_tool_rounds=4,
            context_messages=8,
            context_char_limit=16000,
        )
        service.deepseek = object()
        service.hot_search = object()
        service.prepare_review = lambda arguments, context: {}
        service.prepare_sticker = lambda arguments, context: {}
        service.prepare_reminder = lambda arguments, context: {}
        service.prepare_content_send = lambda arguments, context: {}
        service.prepare_footprint = lambda arguments, context: {}
        brain = service.build_brain(FakeErrorJ())
        self.assertIs(brain.hot_search, service.hot_search)


class WebResearchTests(unittest.TestCase):
    def test_search_evidence_flags_official_dates_and_syndication(self):
        payload = assess_search_evidence(
            {
                "results": [
                    {
                        "title": "官方公告",
                        "url": "https://www.gov.cn/notice",
                        "date": "2026-11-01",
                        "authority": 9,
                    },
                    {
                        "title": "官方公告",
                        "url": "https://example.com/repost",
                        "snippet": "转载内容",
                        "authority": 3,
                    },
                ]
            },
            now=datetime(2026, 11, 6, tzinfo=timezone.utc),
        )
        first, second = payload["results"]
        self.assertTrue(first["official_source"])
        self.assertEqual(first["published_date"], "2026-11-01")
        self.assertEqual(first["freshness_days"], 5)
        self.assertGreater(first["source_quality"], second["source_quality"])
        self.assertTrue(second["possible_syndication"])
        self.assertEqual(payload["evidence"]["official_sources"], 1)
        self.assertEqual(payload["evidence"]["undated_sources"], 1)
        self.assertTrue(payload["evidence"]["warnings"])

    def test_search_router_detects_security_and_structured_identifiers(self):
        route = route_search_intent(
            "CVE-2026-12345",
            "这个漏洞会影响哪些版本？",
        )
        self.assertEqual(route.domains[0], "security")
        self.assertEqual(route.region, "intl")
        self.assertEqual(route.language, "en")
        self.assertIn("CVE-2026-12345", route.primary_query)
        self.assertIn("NVD", route.primary_query)
        self.assertGreater(route.confidence, 0.5)

    def test_search_router_builds_academic_and_code_queries(self):
        academic = route_search_intent(
            "10.48550/arXiv.2501.00001",
            "帮我找这篇论文的出处",
        )
        self.assertEqual(academic.domains[0], "academic")
        self.assertEqual(academic.language, "en")
        self.assertTrue(
            any("paper DOI" in query for query in academic.queries)
        )
        code = route_search_intent(
            "React useEffect 报错",
            "这个 traceback 怎么解决",
        )
        self.assertEqual(code.domains[0], "code")
        self.assertTrue(
            any(
                "official documentation" in query
                for query in code.queries
            )
        )

    def test_search_router_keeps_general_queries_small(self):
        route = route_search_intent("附近有什么好吃的")
        self.assertEqual(route.domains, ())
        self.assertEqual(route.queries, ("附近有什么好吃的",))
        self.assertEqual(route.label, "通用网页")

    def test_research_plans_searches_merges_and_fetches_pages(self):
        class Provider:
            name = "research"

            def __init__(self):
                self.search_calls = []
                self.fetch_calls = []

            def chat(self, messages, tools):
                self.assert_no_tools = tools == []
                return {
                    "content": json.dumps(
                        {
                            "queries": [
                                "量子计算 最新进展",
                                "量子计算 官方 回应",
                            ]
                        },
                        ensure_ascii=False,
                    )
                }

            def web_search(self, query, count=5, original_question=""):
                self.search_calls.append((query, count, original_question))
                if "官方" in query:
                    return {
                        "results": [
                            {
                                "title": "官方说明",
                                "url": "https://www.example.com/a?utm_source=x",
                                "authority": 9,
                            },
                            {
                                "title": "第二来源",
                                "url": "https://news.example.com/b",
                                "authority": 6,
                            },
                        ]
                    }
                return {
                    "results": [
                        {
                            "title": "官方说明",
                            "url": "https://example.com/a",
                            "authority": 8,
                            "summary": "同一篇网页的更长摘要。",
                        },
                        {
                            "title": "背景资料",
                            "url": "https://docs.example.com/c",
                            "authority": 5,
                        },
                    ]
                }

            def web_fetch(self, url):
                self.fetch_calls.append(url)
                return {
                    "title": "网页正文",
                    "content": "公开网页正文 " * 600,
                }

        provider = Provider()
        engine = WebResearchEngine(provider, max_fetches=2)
        result = engine.run(
            "量子计算",
            "量子计算最近有什么进展？",
            5,
        )
        self.assertEqual(len(result["queries"]), 3)
        self.assertEqual(len(provider.search_calls), 3)
        self.assertEqual(len(result["pages"]), 2)
        self.assertLessEqual(len(result["pages"][0]["content"]), 2400)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 14500)
        official = [
            item
            for item in result["results"]
            if item["title"] == "官方说明"
        ]
        self.assertEqual(len(official), 1)
        self.assertGreaterEqual(len(official[0]["matched_queries"]), 2)

    def test_research_falls_back_when_query_planning_fails(self):
        class Provider:
            def chat(self, messages, tools):
                raise AgentError("planner unavailable")

            def web_search(self, query, count=5, original_question=""):
                return {
                    "results": [
                        {
                            "title": query,
                            "url": "https://example.com/" + str(len(query)),
                        }
                    ]
                }

            def web_fetch(self, url):
                return {"content": "page"}

        engine = WebResearchEngine(Provider())
        result = engine.run("测试主题", "测试主题有什么新消息")
        self.assertGreaterEqual(len(result["queries"]), 2)
        self.assertEqual(result["results"][0]["title"], "测试主题")

    def test_research_uses_local_domain_queries_and_reports_route(self):
        class Provider:
            def __init__(self):
                self.queries = []

            def chat(self, messages, tools):
                return {"content": '{"queries":["漏洞影响范围"]}'}

            def web_search(self, query, count=5, original_question=""):
                self.queries.append(query)
                return {
                    "results": [
                        {
                            "title": query,
                            "url": "https://example.com/" + str(len(query)),
                        }
                    ]
                }

            def web_fetch(self, url):
                return {"content": "page"}

        provider = Provider()
        result = WebResearchEngine(provider).run(
            "CVE-2026-12345",
            "这个漏洞影响哪些版本？",
        )
        self.assertEqual(result["route"]["domains"][0], "security")
        self.assertTrue(
            any("NVD" in query for query in provider.queries)
        )
        self.assertGreaterEqual(
            len(
                [
                    item
                    for item in result["results"]
                    if item["title"] == "CVE-2026-12345 NVD official advisory"
                ]
            ),
            1,
        )

    def test_research_reports_when_every_search_fails(self):
        class Provider:
            def chat(self, messages, tools):
                return {"content": '{"queries":["测试 A","测试 B"]}'}

            def web_search(self, query, count=5, original_question=""):
                raise AgentError("search denied")

            def web_fetch(self, url):
                raise AgentError("fetch denied")

        with self.assertRaises(AgentError):
            WebResearchEngine(Provider()).run("测试")

    def test_brain_dispatches_deep_research_tool(self):
        calls = []

        class Research:
            def run(
                self,
                query,
                original_question,
                count,
                domain_routing_enabled=True,
            ):
                calls.append((query, original_question, count))
                return {"untrusted": True, "results": []}

        brain = AgentBrain(
            object(),
            FakeErrorJ(),
            lambda arguments, context: {},
            web_research=Research(),
        )
        result = brain.tool_registry.execute(
            "deepseek_web_research",
            {"query": "复杂事件", "count": 7},
            {
                "tools_enabled": "1",
                "web_search_enabled": "1",
            },
            "帮我查一下复杂事件的来龙去脉",
        )
        self.assertTrue(result["untrusted"])
        self.assertEqual(
            calls,
            [("复杂事件", "帮我查一下复杂事件的来龙去脉", 7)],
        )


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
        self.assertEqual(brain.last_used_tools, ["errorjiang_inventory_search"])

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

    def test_web_search_tool_applies_and_can_disable_domain_routing(self):
        deepseek = FakeSearchDeepSeek([])
        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
        )
        context = {
            "tools_enabled": "1",
            "web_search_enabled": "1",
            "web_search_count": "4",
        }
        result = brain.tool_registry.execute(
            "deepseek_web_search",
            {"query": "CVE-2026-12345"},
            context,
            "这个漏洞影响哪些版本？",
        )
        self.assertEqual(result["route"]["domains"], ["security"])
        self.assertIn("NVD", deepseek.search_calls[-1][0])

        context["web_domain_routing_enabled"] = "0"
        result = brain.tool_registry.execute(
            "deepseek_web_search",
            {"query": "CVE-2026-12345"},
            context,
            "这个漏洞影响哪些版本？",
        )
        self.assertEqual(result["route"]["domains"], [])
        self.assertEqual(
            deepseek.search_calls[-1][0],
            "CVE-2026-12345",
        )

    def test_custom_persona_template_reaches_agent_system_prompt(self):
        deepseek = FakeSearchDeepSeek(
            [
                {
                    "role": "assistant",
                    "content": "在呢。",
                }
            ]
        )
        custom = (
            "你是「鲸鲸」，一条住在 QQ 里的蓝色鲸鱼娘。"
            "语气懒散但任务要认真。"
            "开场示例末尾标记：鲸尾摆摆。"
        )
        persona_prompt = AgentService.persona_prompt(
            {
                "persona_preset": "冷脸萌",
                "persona_custom_prompt": custom,
            }
        )
        brain = AgentBrain(
            deepseek,
            FakeErrorJ(),
            lambda args, context: {},
        )
        self.assertEqual(
            brain.reply(
                "在吗",
                [],
                {
                    "tools_enabled": "1",
                    "persona_prompt": persona_prompt,
                },
            ),
            "在呢。",
        )
        system = deepseek.seen_systems[0]
        self.assertIn("蓝色鲸鱼娘", system)
        self.assertIn("鲸尾摆摆", system)
        self.assertIn("自称始终使用“鲸鲸”", system)

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
        self.assertNotIn("deepseek_web_research", deepseek.seen_tools[0])
        self.assertNotIn("deepseek_web_fetch", deepseek.seen_tools[0])
        self.assertNotIn("web_hot_search", deepseek.seen_tools[0])

    def test_search_tool_reports_provider_without_search_support(self):
        class ChatOnlyProvider:
            name = "chat-only"

            def __init__(self):
                self.calls = 0
                self.messages = []

            def chat(self, messages, tools):
                self.calls += 1
                self.messages = messages
                if self.calls == 1:
                    return {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-search",
                                "type": "function",
                                "function": {
                                    "name": "deepseek_web_search",
                                    "arguments": json.dumps(
                                        {"query": "测试"}
                                    ),
                                },
                            }
                        ],
                    }
                return {"role": "assistant", "content": "暂时不能搜索。"}

        provider = ChatOnlyProvider()
        brain = AgentBrain(
            provider,
            FakeErrorJ(),
            lambda arguments, context: {},
        )
        reply = brain.reply(
            "搜一下测试",
            [],
            {
                "tools_enabled": "1",
                "web_search_enabled": "1",
            },
        )
        self.assertEqual(reply, "暂时不能搜索。")
        tool_result = provider.messages[-1]["content"]
        self.assertIn("不支持网页搜索", tool_result)

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
            "username": "鲸鲸",
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

    def test_group_idle_action_forwards_admin_request(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            return_value={"ok": True, "message": "预览内容"},
        ) as request:
            handler.api_agent_web_group_idle_action(
                {"action": "preview", "group_id": "group-openid"}
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["message"], "预览内容")
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/group-idle-action")
        self.assertEqual(args[1]["action"], "preview")
        self.assertEqual(args[1]["group_id"], "group-openid")

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
                    "caption": "猫猫哭了",
                    "keywords": "猫猫 泪目 哭",
                    "mood": "sad",
                    "library_id": "lib-work",
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        self.assertEqual(captured["status"], 200)
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/sticker/upload")
        self.assertEqual(args[1]["owner_id"], "0")
        self.assertEqual(args[1]["category"], "泪目")
        self.assertEqual(args[1]["caption"], "猫猫哭了")
        self.assertEqual(args[1]["keywords"], "猫猫 泪目 哭")
        self.assertEqual(args[1]["mood"], "sad")
        self.assertEqual(args[1]["library_id"], "lib-work")

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

    def test_agent_sticker_metadata_update_forwards_batch(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            return_value={"ok": True, "updated": 2},
        ) as request:
            handler.api_agent_web_sticker_update(
                {
                    "ids": [1, "2", 2],
                    "caption": "猫猫睡大觉",
                    "keywords": "猫猫 晚安 睡大觉",
                    "mood": "daily",
                }
            )
        self.assertEqual(captured["status"], 200)
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/sticker/update")
        self.assertEqual(args[1]["ids"], [1, 2])
        self.assertEqual(args[1]["values"]["mood"], "daily")

    def test_agent_memory_list_forwards_archive_filter(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            return_value={
                "memories": [
                    {
                        "id": 4,
                        "pinned": 0,
                        "strength": 0.42,
                        "importance": 8,
                        "evidence": "原话",
                        "archived_at": None,
                    }
                ]
            },
        ) as request:
            handler.api_agent_web_memories(
                {"q": ["咖啡"], "include_archived": ["1"]}
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["memories"][0]["strength"], 0.42)
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertIn("include_archived=1", call.args[0])
            self.assertIn("q=%E5%92%96%E5%95%A1", call.args[0])

    def test_agent_memory_status_forwards_archive_action(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            return_value={"ok": True, "archived": True},
        ) as request:
            handler.api_agent_web_memory_status(
                {
                    "id": 9,
                    "platform": "qq",
                    "archived": True,
                }
            )
        self.assertEqual(captured["status"], 200)
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/memory/status")
        self.assertEqual(args[1]["id"], 9)
        self.assertEqual(args[1]["platform"], "qq")
        self.assertTrue(args[1]["archived"])

    def test_agent_group_jargon_proxy_forwards_review_action(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = []
        handler.send_json = lambda status, payload: captured.append(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            side_effect=[
                {"items": [], "pending_count": 0, "approved_count": 0},
                {
                    "items": [
                        {
                            "id": 3,
                            "term": "绝绝子",
                            "status": "approved",
                        }
                    ],
                    "pending_count": 0,
                    "approved_count": 1,
                },
            ],
        ) as request:
            handler.api_agent_web_group_jargon()
            handler.api_agent_web_group_jargon_action(
                {
                    "id": 3,
                    "action": "approve",
                    "meaning": "表示非常厉害",
                    "example": "这操作绝绝子",
                }
            )
        self.assertEqual([item["status"] for item in captured], [200, 200])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], "/internal/group-jargon")
        action_args = request.call_args_list[1].args
        self.assertEqual(action_args[0], "/internal/group-jargon")
        self.assertEqual(action_args[1]["action"], "approve")
        self.assertEqual(action_args[1]["meaning"], "表示非常厉害")

    def test_agent_diagnostics_proxy_forwards_health_actions(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = []
        handler.send_json = lambda status, payload: captured.append(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            side_effect=[
                {"ok": True, "threads": {}},
                {
                    "ok": True,
                    "search_check": {
                        "ok": True,
                        "results": 1,
                    },
                },
            ],
        ) as request:
            handler.api_agent_web_diagnostics()
            handler.api_agent_web_diagnostics_action(
                {"action": "search_check"}
            )
        self.assertEqual([item["status"] for item in captured], [200, 200])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            request.call_args_list[0].args[0],
            "/internal/diagnostics",
        )
        self.assertEqual(
            request.call_args_list[1].args[1]["action"],
            "search_check",
        )

    def test_agent_sticker_import_forwards_zip(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        raw = b"PK-test-sticker-pack"
        with patch.object(
            app,
            "agent_internal_request",
            return_value={"ok": True, "imported": 2, "duplicates": 1},
        ) as request:
            handler.api_agent_web_sticker_import(
                {
                    "library_id": "lib-life",
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["payload"]["imported"], 2)
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/sticker/import")
        self.assertEqual(args[1]["library_id"], "lib-life")
        self.assertEqual(
            base64.b64decode(args[1]["data_base64"]),
            raw,
        )

    def test_agent_sticker_library_and_rule_forwarding(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            side_effect=[
                {
                    "id": "lib-work",
                    "name": "工作",
                    "libraries": [{"id": "lib-work", "name": "工作"}],
                },
                {
                    "ok": True,
                    "scope_type": "group",
                    "scope_key": "qqbot:group-openid",
                    "library_ids": ["lib-work"],
                    "rules": [],
                },
            ],
        ) as request:
            handler.api_agent_web_sticker_library(
                {"action": "create", "name": "工作"}
            )
            handler.api_agent_web_sticker_rule(
                {
                    "scope_type": "group",
                    "scope_key": "qqbot:group-openid",
                    "library_ids": ["lib-work"],
                }
            )
        self.assertEqual(captured["status"], 200)
        self.assertEqual(request.call_count, 2)
        first = request.call_args_list[0]
        second = request.call_args_list[1]
        self.assertEqual(first.args[0], "/internal/sticker/library")
        self.assertEqual(first.args[1]["action"], "create")
        self.assertEqual(first.args[1]["name"], "工作")
        self.assertEqual(second.args[0], "/internal/sticker/rule")
        self.assertEqual(second.args[1]["library_ids"], ["lib-work"])

    def test_agent_sticker_candidate_review_forwarding(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        captured = {}
        handler.send_json = lambda status, payload: captured.update(
            {"status": status, "payload": payload}
        )
        with patch.object(
            app,
            "agent_internal_request",
            return_value={
                "ok": True,
                "action": "accepted",
                "candidates": [],
            },
        ) as request:
            handler.api_agent_web_sticker_candidate(
                {
                    "id": 9,
                    "action": "accept",
                    "category": "笑哭",
                    "caption": "猫猫笑哭",
                    "keywords": "猫猫 笑哭",
                    "mood": "happy",
                }
            )
        self.assertEqual(captured["status"], 200)
        args = request.call_args.args
        self.assertEqual(args[0], "/internal/sticker/candidate")
        self.assertEqual(args[1]["id"], 9)
        self.assertEqual(args[1]["action"], "accept")
        self.assertEqual(args[1]["category"], "笑哭")

    def test_agent_sticker_export_streams_zip(self):
        handler = self.make_handler({})
        handler.is_admin = lambda: True
        handler.wfile = io.BytesIO()
        response_meta = {}
        handler.send_response = lambda status: response_meta.update(
            {"status": status}
        )
        handler.send_header = lambda key, value: response_meta.update(
            {key: value}
        )
        handler.end_headers = lambda: None

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"PK-sticker-export"

        with patch.dict(
            os.environ,
            {"ERRORJIANG_AGENT_TOKEN": "test-token"},
        ), patch.object(app, "urlopen", return_value=FakeResponse()):
            handler.api_agent_web_sticker_export({})
        self.assertEqual(response_meta["status"], 200)
        self.assertEqual(response_meta["Content-Type"], "application/zip")
        self.assertEqual(handler.wfile.getvalue(), b"PK-sticker-export")

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

    def test_internal_group_jargon_can_be_listed_and_approved(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        service = object.__new__(AgentService)
        service.config = SimpleNamespace(errorjiang_token="internal-token")
        service.store = AgentStore(Path(temp.name) / "agent.db")
        service.store.upsert_group_jargon_candidates(
            "qqbot",
            "group-openid",
            [
                {
                    "term": "绝绝子",
                    "occurrences": 4,
                    "member_count": 2,
                }
            ],
        )
        server = AgentHttpServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(method, payload=None):
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                server.server_address[1],
                timeout=5,
            )
            body = (
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            )
            try:
                connection.request(
                    method,
                    "/internal/group-jargon",
                    body=body,
                    headers={
                        "X-ErrorJ-Agent-Token": "internal-token",
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                return response.status, json.loads(
                    response.read().decode("utf-8")
                )
            finally:
                connection.close()

        status, listed = request("GET")
        self.assertEqual(status, 200)
        self.assertEqual(listed["pending_count"], 1)
        item_id = listed["items"][0]["id"]
        status, approved = request(
            "POST",
            {
                "id": item_id,
                "action": "approve",
                "meaning": "表示非常厉害",
                "example": "这操作绝绝子",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(approved["approved_count"], 1)
        self.assertEqual(approved["items"][0]["meaning"], "表示非常厉害")

    def test_internal_diagnostics_supports_refresh_and_search_check(self):
        calls = []

        def diagnostics_payload(action=""):
            calls.append(action)
            return {
                "ok": True,
                "search_check": (
                    {"ok": True, "results": 1}
                    if action == "search_check"
                    else None
                ),
            }

        service = SimpleNamespace(
            config=SimpleNamespace(errorjiang_token="internal-token"),
            diagnostics_payload=diagnostics_payload,
            run_history_cleanup=lambda: {"ran": True},
        )
        server = AgentHttpServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(method, payload=None):
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                server.server_address[1],
                timeout=5,
            )
            body = (
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            )
            try:
                connection.request(
                    method,
                    "/internal/diagnostics",
                    body=body,
                    headers={
                        "X-ErrorJ-Agent-Token": "internal-token",
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                return response.status, json.loads(
                    response.read().decode("utf-8")
                )
            finally:
                connection.close()

        status, payload = request("GET")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, payload = request("POST", {"action": "search_check"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["search_check"]["ok"])
        self.assertEqual(calls, ["", "search_check"])

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
            "caption": "猫猫眼泪止不住",
            "keywords": "泪目 猫猫 哭",
            "mood": "sad",
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
        self.assertEqual(result["sticker"]["caption"], "猫猫眼泪止不住")
        self.assertEqual(result["sticker"]["keywords"], "泪目 猫猫 哭")
        self.assertEqual(result["sticker"]["mood"], "sad")
        self.assertEqual(result["sticker"]["tags"], "泪目")
        sticker = service.store.list_stickers("0")[0]
        self.assertEqual(sticker["category"], "泪目")
        self.assertEqual(sticker["source_name"], "泪目_猫猫.png")
        self.assertEqual(sticker["caption"], "猫猫眼泪止不住")
        self.assertEqual(sticker["keywords"], "泪目 猫猫 哭")
        self.assertEqual(sticker["mood"], "sad")
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
    def test_agent_sidebar_uses_consistent_compact_spacing(self):
        css = (app.STATIC_DIR / "agent.css").read_text(encoding="utf-8")
        self.assertIn(".agent-console-nav {\n  display: grid;\n  gap: 4px;", css)
        self.assertIn(
            "min-height: 44px;\n  align-items: center;\n  gap: 9px;\n  padding: 0 12px;",
            css,
        )
        self.assertIn("border-radius: var(--agent-radius);", css)
        self.assertIn("font-size: 12px;\n  line-height: 1.3;", css)
        self.assertIn("margin-top: 20px;\n  padding: 12px;", css)
        self.assertIn(
            "min-height: 42px;\n    padding: 0 12px;\n    font-size: 12px;",
            css,
        )
        self.assertIn("scroll-margin-top: 128px;", css)

    def test_agent_persona_prompt_allows_long_formatted_templates(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        self.assertIn(
            'id="settingPersonaCustomPrompt" rows="4" maxlength="6000"',
            html,
        )

    def test_agent_exposes_chat_human_delay_switch(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="settingChatHumanDelay"', html)
        self.assertIn("闲聊拟人延迟", html)
        self.assertIn(
            'settingValue("settingChatHumanDelay", settings.chat_human_delay)',
            script,
        )
        self.assertIn(
            'chat_human_delay: document.getElementById("settingChatHumanDelay").checked',
            script,
        )

    def test_agent_exposes_local_search_domain_routing_switch(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="settingWebDomainRoutingEnabled"', html)
        self.assertIn("智能领域检索", html)
        self.assertIn(
            "settingWebDomainRoutingEnabled",
            script,
        )
        self.assertIn("web_domain_routing_enabled:", script)

    def test_agent_exposes_group_reply_pacing_controls(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="settingGroupReplyControlEnabled"', html)
        self.assertIn('id="settingGroupActivityLevel"', html)
        self.assertIn('id="settingGroupReplyMax"', html)
        self.assertIn('id="settingGroupReplyFatigueRounds"', html)
        self.assertIn('id="settingGroupMessageMergeSeconds"', html)
        self.assertIn(
            'settingValue(\n          "settingGroupReplyControlEnabled",\n'
            "          settings.group_reply_control_enabled\n        );",
            script,
        )
        self.assertIn("group_reply_max_per_10m:", script)
        self.assertIn("group_activity_level:", script)
        self.assertIn("group_reply_fatigue_rounds:", script)
        self.assertIn("group_message_merge_seconds:", script)

    def test_agent_exposes_group_jargon_review_panel(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="settings-jargon"', html)
        self.assertIn('id="settingGroupJargonEnabled"', html)
        self.assertIn('id="agentJargonList"', html)
        self.assertIn('id="agentJargonStatusFilter"', html)
        self.assertIn("/api/agent/web/group-jargon", script)
        self.assertIn("function loadGroupJargon()", script)
        self.assertIn("function updateGroupJargon(item, action)", script)
        self.assertIn("批准并启用", script)

    def test_agent_memory_lifecycle_controls_are_wired(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="settingMemoryDecayEnabled"', html)
        self.assertIn("记忆衰减与归档", html)
        self.assertIn('id="agentMemoryArchived"', html)
        self.assertIn('id="agentMemoryCount"', html)
        self.assertIn(
            'settingValue(\n          "settingMemoryDecayEnabled",\n'
            "          settings.memory_decay_enabled\n        );",
            script,
        )
        self.assertIn("memory_decay_enabled:", script)
        self.assertIn("include_archived=1", script)
        self.assertIn("/api/agent/web/memory-status", script)
        self.assertIn("agent-memory-evidence", script)

    def test_agent_exposes_immediate_memory_cost_controls(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn(
            'id="settingMemoryImmediateExtractionEnabled"',
            html,
        )
        self.assertIn(
            'id="settingMemoryImmediateDailyLimit"',
            html,
        )
        self.assertIn("即时记忆提取", html)
        self.assertIn(
            "memory_immediate_extraction_enabled:",
            script,
        )
        self.assertIn(
            "memory_immediate_extraction_daily_limit:",
            script,
        )
        self.assertIn(
            'id="settingPrivateHistoryRetentionDays"',
            html,
        )
        self.assertIn(
            'id="settingGroupHistoryRetentionDays"',
            html,
        )

    def test_agent_exposes_runtime_diagnostics(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="settings-diagnostics"', html)
        self.assertIn('id="agentDiagnosticThreads"', html)
        self.assertIn('id="agentDiagnosticCounts"', html)
        self.assertIn('id="agentDiagnosticsSearch"', html)
        self.assertIn('id="agentDiagnosticsCleanup"', html)
        self.assertIn("/api/agent/web/diagnostics", script)
        self.assertIn("function renderDiagnostics(data)", script)

    def test_agent_settings_intro_has_no_eyebrow(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        self.assertIn("<h1>机器人设置</h1>", html)
        self.assertNotIn("<span>Error酱 / 鲸鲸</span>", html)

    def test_moment_log_toggle_has_stable_arrow_and_smaller_motion(self):
        css = (app.STATIC_DIR / "moments.css").read_text(encoding="utf-8")
        self.assertIn("transform-box: fill-box", css)
        self.assertIn("transform-origin: center", css)
        self.assertIn(".mo-log-head .mo-log-caret", css)
        self.assertIn("position: absolute", css)
        keyframes_start = css.index("@keyframes mo-log-open")
        keyframes_end = css.index("}", keyframes_start) + 1
        keyframes = css[keyframes_start:keyframes_end]
        self.assertIn("transform: translateY(-2px)", keyframes)
        self.assertNotIn("translateY(-4px)", keyframes)

    def test_agent_page_is_settings_console_without_chat(self):
        html = (app.STATIC_DIR / "agent.html").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "agent.js").read_text(encoding="utf-8")
        landing = (app.STATIC_DIR / "site" / "site.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("<title>鲸鲸 · 配置中心</title>", html)
        self.assertIn("<strong>鲸鲸</strong>", html)
        self.assertIn('title="鲸鲸"', landing)
        self.assertIn('aria-label="打开鲸鲸"', landing)
        self.assertNotIn("折兮颜", html + script + landing)
        self.assertNotIn("ErrorJ Agent", html + script + landing)
        self.assertIn('class="agent-console-shell"', html)
        self.assertIn('id="settings-stickers"', html)
        self.assertIn('id="agentStickerUploadCaption"', html)
        self.assertIn('id="agentStickerUploadKeywords"', html)
        self.assertIn('id="agentStickerUploadMood"', html)
        self.assertIn('id="agentStickerBulkUpdate"', html)
        self.assertIn('id="agentStickerSearch"', html)
        self.assertIn('id="agentStickerMoodFilter"', html)
        self.assertIn('id="agentStickerPendingOnly"', html)
        self.assertIn('id="agentStickerExport"', html)
        self.assertIn('id="agentStickerImportInput"', html)
        self.assertIn('id="agentStickerLibrary"', html)
        self.assertIn('id="agentStickerLibraryCreateForm"', html)
        self.assertIn('id="agentStickerRuleScope"', html)
        self.assertIn('id="agentStickerRuleLibraries"', html)
        self.assertIn('id="agentStickerCandidateList"', html)
        self.assertIn('id="settingStickerAutoCollectEnabled"', html)
        self.assertIn('id="settingStickerAutoCollectLibrary"', html)
        self.assertIn('id="agentStickerBulkLibraryMove"', html)
        self.assertIn('id="agentSettingsSave" disabled', html)
        self.assertIn('aria-label="筛选记忆"', html)
        self.assertIn('id="settings-persona"', html)
        self.assertIn('id="settings-web-search"', html)
        self.assertIn('id="settings-group-proactive"', html)
        self.assertIn("网页与热搜", html)
        self.assertIn('id="settingPersonaPreset"', html)
        self.assertIn('id="settingWebSearchEnabled"', html)
        self.assertIn('id="settingGroupProactiveEnabled"', html)
        self.assertIn('id="settingGroupIdleProactiveEnabled"', html)
        self.assertIn('id="settingGroupIdleTriggerMinutes"', html)
        self.assertIn('id="settingGroupIdleRandomMin"', html)
        self.assertIn('id="settingGroupIdleRandomMax"', html)
        self.assertIn('id="settingGroupIdleMaxPerDay"', html)
        self.assertIn('id="settingGroupIdleMaxUnanswered"', html)
        self.assertIn('id="agentGroupIdleStatus"', html)
        self.assertIn('id="agentGroupIdleGroups"', html)
        self.assertIn('id="agentGroupIdlePreview"', html)
        self.assertIn('id="agentGroupIdleRuns"', html)
        self.assertIn(
            "group_idle_proactive_enabled",
            script,
        )
        self.assertIn("renderGroupIdleStatus", script)
        self.assertIn("/api/agent/web/group-idle-action", script)
        self.assertIn("保存群参数", script)
        self.assertIn("agent-sticker-file-name", script)
        self.assertIn("agent-sticker-caption", script)
        self.assertIn("/api/agent/web/sticker-update", script)
        self.assertIn("/api/agent/web/sticker-export", script)
        self.assertIn("/api/agent/web/sticker-import", script)
        self.assertIn("/api/agent/web/sticker-library", script)
        self.assertIn("/api/agent/web/sticker-rule", script)
        self.assertIn("/api/agent/web/sticker-candidate", script)
        self.assertIn("sticker_auto_collect_enabled", script)
        self.assertEqual(html.count("data-console-section"), 11)
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
