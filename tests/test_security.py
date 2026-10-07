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


if __name__ == "__main__":
    unittest.main()
