import json
import http.client
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from errorjiang_agent.brain import AgentBrain
from errorjiang_agent.onebot import event_key, parse_message_event
from errorjiang_agent.onebot_ws import _masked_frame, _read_frame
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


if __name__ == "__main__":
    unittest.main()
