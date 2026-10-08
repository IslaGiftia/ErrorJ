import base64
import json
import unittest
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
