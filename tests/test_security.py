import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class MessageDeletePermissionTests(unittest.TestCase):
    def test_required_permission_marks_message_delete_admin_only(self):
        self.assertIsNone(app.required_permission("/api/site/messages/12", "DELETE"))

    def test_message_delete_handler_rejects_non_admin(self):
        handler = object.__new__(app.InventoryHandler)
        handler.is_admin = lambda: False

        with patch.object(app, "api_error") as api_error:
            handler.api_site_message_delete("/api/site/messages/12")

        api_error.assert_called_once_with(
            handler, 403, "只有管理员可以删除留言。"
        )

    def test_workbench_is_admin_only(self):
        self.assertIsNone(app.required_permission("/workbench", "GET"))
        self.assertIsNone(app.required_permission("/api/workbench/assets", "GET"))
        self.assertIsNone(app.required_permission("/api/prompts", "GET"))
        handler = object.__new__(app.InventoryHandler)
        self.assertFalse(
            handler.data_file_allowed(
                "workbench/firmware/test.bin",
                {"kind": "member", "user_id": 1},
            )
        )
        self.assertTrue(
            handler.data_file_allowed(
                "workbench/firmware/test.bin",
                {"kind": "admin", "user_id": 1},
            )
        )

    def test_download_request_is_available_to_members(self):
        self.assertEqual(app.required_permission("/api/download-requests", "POST"), "")
        self.assertEqual(app.required_permission("/api/site/music/1/download", "GET"), "")
        self.assertEqual(app.required_permission("/api/books/1/download", "GET"), "")


class ReferenceProjectTests(unittest.TestCase):
    def test_reference_api_is_public_for_reads(self):
        self.assertEqual(app.required_permission("/api/references", "GET"), "")
        self.assertIsNone(app.required_permission("/api/references", "POST"))

    def test_reference_seed_parser_finds_existing_projects(self):
        rows = app.reference_seed_rows()
        self.assertGreater(len(rows), 5)
        self.assertTrue(any(row[1] == "https://github.com/IslaGiftia/ErrorJ" for row in rows))


class DownloadWorkflowTests(unittest.TestCase):
    def test_member_request_can_be_approved_and_revoked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                stamp = app.now_text()
                user_id = app.execute(
                    """INSERT INTO users
                           (username, nickname, password_hash, status, role,
                            created_at, updated_at)
                       VALUES (?, ?, ?, 'approved', 'member', ?, ?)""",
                    ("member1", "普通用户", "hash", stamp, stamp),
                )
                book_id = app.execute(
                    """INSERT INTO books
                           (title, author, format, file_path, file_size, sort_order,
                            created_at, updated_at)
                       VALUES (?, ?, 'txt', ?, 1, 0, ?, ?)""",
                    ("测试书", "作者", "book_files/test.txt", stamp, stamp),
                )
                member = {
                    "kind": "member",
                    "user_id": user_id,
                    "username": "member1",
                    "nickname": "普通用户",
                }
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: member
                handler.is_admin = lambda: False
                responses = []
                handler.send_json = lambda status, payload: responses.append((status, payload))
                handler.log_activity = lambda *args, **kwargs: None

                with patch.object(app, "notify_async", return_value=False):
                    handler.api_download_request_create(
                        {"resource_type": "book", "resource_id": book_id}
                    )

                row = app.query_one(
                    """SELECT id, status FROM download_requests
                       WHERE user_id = ? AND resource_type = 'book' AND resource_id = ?""",
                    (user_id, book_id),
                )
                self.assertEqual(row["status"], "pending")
                self.assertEqual(handler.download_state(member, "book", book_id), "pending")

                admin_handler = object.__new__(app.InventoryHandler)
                admin_handler.session_identity = lambda: {
                    "kind": "owner",
                    "user_id": 0,
                    "nickname": "管理员",
                }
                admin_handler.is_admin = lambda: True
                admin_handler.log_activity = lambda *args, **kwargs: None
                admin_handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                admin_handler.api_admin_download_request_action(
                    f"/api/admin/download-requests/{row['id']}",
                    {"action": "approve"},
                )
                self.assertEqual(handler.download_state(member, "book", book_id), "approved")

                admin_handler.api_admin_download_request_action(
                    f"/api/admin/download-requests/{row['id']}",
                    {"action": "revoke"},
                )
                self.assertEqual(handler.download_state(member, "book", book_id), "revoked")


class ClientIpTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(app.InventoryHandler)
        self.handler.client_address = ("127.0.0.1", 12345)

    def test_real_ip_header_wins_over_spoofed_forwarded_for(self):
        self.handler.headers = {
            "X-Real-IP": "203.0.113.9",
            "X-Forwarded-For": "198.51.100.7, 203.0.113.9",
        }
        with patch.object(app, "TRUST_PROXY", True):
            self.assertEqual(self.handler.client_ip(), "203.0.113.9")

    def test_forwarded_for_falls_back_to_right_most_valid_address(self):
        self.handler.headers = {
            "X-Forwarded-For": "198.51.100.7, not-an-ip, 203.0.113.10",
        }
        with patch.object(app, "TRUST_PROXY", True):
            self.assertEqual(self.handler.client_ip(), "203.0.113.10")


class DataFilePathTests(unittest.TestCase):
    def test_traversal_is_rejected_before_permission_checks(self):
        self.assertEqual(app.normalized_data_relative("moment_images/../auth.json"), "")
        self.assertEqual(app.normalized_data_relative("moment_images\\..\\auth.json"), "")

    def test_data_file_permissions_reject_traversal(self):
        handler = object.__new__(app.InventoryHandler)
        self.assertFalse(
            handler.data_file_allowed("moment_images/../part_images/1.jpg", None)
        )


class HomeActivityTests(unittest.TestCase):
    def test_activity_api_is_public(self):
        self.assertIn("/api/site/activity", app.ALWAYS_PUBLIC_APIS)

    def test_game_activity_api_is_public(self):
        self.assertIn("/api/site/game-play", app.ALWAYS_PUBLIC_APIS)

    def test_public_activity_uses_generic_content_labels(self):
        self.assertEqual(app.PUBLIC_ACTIVITY_LABELS["message_create"], "发表了留言")
        self.assertEqual(app.PUBLIC_ACTIVITY_LABELS["book_upload"], "上架了一本电子书")

    def test_download_request_notification_event_exists(self):
        events = {item["key"]: item for item in app.NOTIFY_EVENTS}
        self.assertTrue(events["download_request"]["default"])

    def test_messages_permission_label_is_renamed(self):
        labels = {item["key"]: item["label"] for item in app.GUEST_PAGE_PERMISSIONS}
        self.assertEqual(labels["guest:page:messages"], "留言")

    def test_module_permission_labels_match_home_entries(self):
        labels = {item["key"]: item["label"] for item in app.GUEST_PAGE_PERMISSIONS}
        self.assertEqual(labels["guest:page:moments"], "动态")
        self.assertEqual(labels["guest:page:recommendations"], "推荐")
        self.assertEqual(labels["guest:page:games"], "游戏")

        groups = {group["key"]: group["label"] for group in app.PERMISSION_GROUPS}
        self.assertEqual(groups["bookmarks"], "书签")
        self.assertEqual(groups["notes"], "笔记")


class IpRegionTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def test_overseas_ip_falls_back_to_country(self):
        response = self.FakeResponse(
            {
                "success": True,
                "country": "美国",
                "region": "加利福尼亚州",
            }
        )
        with patch.object(app, "urlopen", return_value=response):
            self.assertEqual(app.ipwhois_ip_region("8.8.8.8"), "美国")

    def test_china_ip_falls_back_to_province(self):
        response = self.FakeResponse(
            {
                "success": True,
                "country": "中国",
                "region": "广东省",
            }
        )
        with patch.object(app, "urlopen", return_value=response):
            self.assertEqual(app.ipwhois_ip_region("1.2.3.4"), "广东")


class MessageAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(app.InventoryHandler)

    def test_jpeg_content_with_png_name_is_normalized(self):
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 24
        payload = {
            "files": [
                {
                    "name": "camera.png",
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                }
            ]
        }

        prepared, error = self.handler.message_attachments(payload)

        self.assertEqual(error, "")
        self.assertEqual(len(prepared), 1)
        display_name, content, mime_type, stored_name = prepared[0]
        self.assertEqual(display_name, "camera.png")
        self.assertEqual(content, raw)
        self.assertEqual(mime_type, "image/jpeg")
        self.assertEqual(stored_name, "camera.jpg")

    def test_invalid_image_content_is_rejected(self):
        payload = {
            "files": [
                {
                    "name": "fake.png",
                    "data_base64": base64.b64encode(b"not an image").decode("ascii"),
                }
            ]
        }

        prepared, error = self.handler.message_attachments(payload)

        self.assertIsNone(prepared)
        self.assertIn("图片内容无法识别", error)


if __name__ == "__main__":
    unittest.main()
