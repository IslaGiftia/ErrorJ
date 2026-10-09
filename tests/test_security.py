import base64
import json
import tempfile
import unittest
import wave
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


class UsernameMaskTests(unittest.TestCase):
    def test_guest_username_mask_keeps_only_last_character(self):
        self.assertEqual(app.mask_username("牛大能"), "**能")
        self.assertEqual(app.mask_username("A"), "A")

    def test_message_display_name_uses_full_username_for_signed_in_user(self):
        handler = object.__new__(app.InventoryHandler)
        row = {"user_id": 7, "nickname": "旧昵称"}
        authors = {7: {"username": "牛大能", "nickname": "牛牛"}}
        self.assertEqual(
            handler.message_display_name(row, authors, False),
            "**能",
        )
        self.assertEqual(
            handler.message_display_name(row, authors, True),
            "牛大能",
        )


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


class MusicDurationTests(unittest.TestCase):
    def test_missing_duration_is_backfilled_from_local_audio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(app, "DB_PATH", root / "inventory.db"), patch.object(
                app, "DATA_DIR", root
            ):
                app.init_db()
                audio_dir = root / "site_music_files"
                audio_dir.mkdir(parents=True, exist_ok=True)
                audio_path = audio_dir / "tone.wav"
                with wave.open(str(audio_path), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(1)
                    handle.setframerate(8000)
                    handle.writeframes(b"\x80" * 8000)
                stamp = app.now_text()
                item_id = app.execute(
                    """INSERT INTO site_music
                           (title, source_type, source_id, sort_order, created_at)
                       VALUES (?, 'file', ?, 0, ?)""",
                    ("测试音频", "site_music_files/tone.wav", stamp),
                )
                app.MUSIC_DURATION_BACKFILLED.clear()
                row = app.query_one("SELECT * FROM site_music WHERE id = ?", (item_id,))
                duration = app.ensure_music_duration(row)
                self.assertAlmostEqual(duration, 1.0, places=2)
                stored = app.query_one(
                    "SELECT duration FROM site_music WHERE id = ?", (item_id,)
                )
                self.assertAlmostEqual(stored["duration"], 1.0, places=2)


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
        self.assertEqual(app.PUBLIC_ACTIVITY_LABELS["map_place_create"], "新增了一个足迹")

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


class ContentShareTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self._db_patch = patch.object(
            app, "DB_PATH", Path(self._temp.name) / "inventory.db"
        )
        self._db_patch.start()
        app.init_db()
        stamp = app.now_text()
        self.member_id = app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role,
                    created_at, updated_at)
               VALUES (?, ?, ?, 'approved', 'member', ?, ?)""",
            ("reader1", "读者", "hash", stamp, stamp),
        )
        self.note_id = app.execute(
            """INSERT INTO learning_notes (title, content, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            ("电源笔记", "# 标题\n\n正文内容", stamp, stamp),
        )
        self.book_id = app.execute(
            """INSERT INTO books
                   (title, author, format, file_path, sort_order, created_at, updated_at)
               VALUES (?, ?, 'txt', ?, 0, ?, ?)""",
            ("测试书", "作者", "book_files/test.txt", stamp, stamp),
        )
        self.music_id = app.execute(
            """INSERT INTO site_music
                   (title, artist, source_type, source_id, sort_order, created_at)
               VALUES (?, ?, 'url', ?, 0, ?)""",
            ("测试歌", "歌手", "https://example.com/a.mp3", stamp),
        )

    def tearDown(self):
        self._db_patch.stop()
        self._temp.cleanup()

    def make_handler(self, user_id, kind="owner", username="owner"):
        handler = object.__new__(app.InventoryHandler)
        handler.session_identity = lambda: {
            "kind": kind,
            "user_id": user_id,
            "username": username,
            "nickname": username,
        }
        handler.is_admin = lambda: kind in ("owner", "admin")
        handler.client_ip = lambda: "127.0.0.1"
        responses = []
        handler.send_json = lambda status, payload: responses.append(
            (status, payload)
        )
        handler.log_activity = lambda *args, **kwargs: None
        return handler, responses

    def test_share_content_rejects_non_admin(self):
        handler, responses = self.make_handler(
            self.member_id, kind="member", username="reader1"
        )
        handler.api_admin_share_content(
            {"target": "moment", "resource_type": "note", "resource_id": self.note_id}
        )
        self.assertIn("error", responses[-1][1])
        self.assertEqual(
            app.query_one("SELECT COUNT(*) AS n FROM moment_shares")["n"], 0
        )

    def test_share_note_to_moment_creates_card(self):
        handler, responses = self.make_handler(0)
        handler.api_admin_share_content(
            {
                "target": "moment",
                "resource_type": "note",
                "resource_id": self.note_id,
                "content": "分享一篇笔记",
            }
        )
        moment_id = responses[-1][1]["moment_id"]
        self.assertTrue(moment_id > 0)
        share_row = app.query_one(
            "SELECT resource_type, resource_id FROM moment_shares WHERE moment_id = ?",
            (moment_id,),
        )
        self.assertEqual(share_row["resource_type"], "note")
        self.assertEqual(int(share_row["resource_id"]), self.note_id)

        moments = query_handler_moments(
            self.make_handler(self.member_id, kind="member", username="reader1")[0]
        )
        card = [item for item in moments if int(item["id"]) == moment_id][0]["share"]
        self.assertTrue(card["available"])
        self.assertEqual(card["title"], "电源笔记")
        self.assertEqual(card["url"], f"/notes/read?id={self.note_id}")

        notifications = app.query(
            "SELECT user_id FROM user_notifications WHERE kind = 'moment_new'"
        )
        self.assertEqual([int(row["user_id"]) for row in notifications], [self.member_id])

    def test_share_music_to_recommendation(self):
        handler, responses = self.make_handler(0)
        handler.api_admin_share_content(
            {
                "target": "recommendation",
                "resource_type": "music",
                "resource_id": self.music_id,
            }
        )
        recommendation_id = responses[-1][1]["recommendation_id"]
        row = app.query_one(
            "SELECT kind, title, resource_type, resource_id FROM recommendations WHERE id = ?",
            (recommendation_id,),
        )
        self.assertEqual(row["kind"], "resource")
        self.assertEqual(row["resource_type"], "music")
        self.assertEqual(int(row["resource_id"]), self.music_id)
        self.assertEqual(row["title"], "测试歌")

    def test_shared_note_requires_share(self):
        member_handler, member_responses = self.make_handler(
            self.member_id, kind="member", username="reader1"
        )
        try:
            member_handler.api_shared_note(self.note_id)
        except Exception as exc:  # pragma: no cover - api_error 不会抛异常
            self.fail(f"不应该抛异常：{exc}")
        self.assertIn("error", member_responses[-1][1])

        admin_handler, admin_responses = self.make_handler(0)
        admin_handler.api_admin_share_content(
            {"target": "moment", "resource_type": "note", "resource_id": self.note_id}
        )
        member_handler.api_shared_note(self.note_id)
        self.assertEqual(member_responses[-1][1]["title"], "电源笔记")

    def test_shared_book_content_requires_share(self):
        member_handler, member_responses = self.make_handler(
            self.member_id, kind="member", username="reader1"
        )
        member_handler.api_shared_book(self.book_id)
        self.assertIn("error", member_responses[-1][1])

        admin_handler, _ = self.make_handler(0)
        admin_handler.api_admin_share_content(
            {
                "target": "recommendation",
                "resource_type": "book",
                "resource_id": self.book_id,
            }
        )
        member_handler.api_shared_book(self.book_id)
        payload = member_responses[-1][1]
        self.assertEqual(payload["title"], "测试书")
        self.assertEqual(
            payload["file_url"], f"/api/shared/books/{self.book_id}/content"
        )

    def test_deleted_resource_marks_card_missing(self):
        handler, responses = self.make_handler(0)
        handler.api_admin_share_content(
            {
                "target": "moment",
                "resource_type": "note",
                "resource_id": self.note_id,
            }
        )
        moment_id = responses[-1][1]["moment_id"]
        app.execute("DELETE FROM learning_notes WHERE id = ?", (self.note_id,))
        moments = query_handler_moments(
            self.make_handler(self.member_id, kind="member", username="reader1")[0]
        )
        card = [item for item in moments if int(item["id"]) == moment_id][0]["share"]
        self.assertFalse(card["available"])


def query_handler_moments(handler):
    responses = []
    original = handler.send_json
    handler.send_json = lambda status, payload: responses.append((status, payload))
    try:
        handler.api_moments({})
    finally:
        handler.send_json = original
    return responses[-1][1]


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self._db_patch = patch.object(
            app, "DB_PATH", Path(self._temp.name) / "inventory.db"
        )
        self._db_patch.start()
        app.init_db()
        stamp = app.now_text()
        self.author_id = app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role,
                    created_at, updated_at)
               VALUES (?, ?, ?, 'approved', 'member', ?, ?)""",
            ("author1", "作者甲", "hash", stamp, stamp),
        )
        self.other_id = app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role,
                    created_at, updated_at)
               VALUES (?, ?, ?, 'approved', 'member', ?, ?)""",
            ("other1", "作者乙", "hash", stamp, stamp),
        )
        self.message_id = app.execute(
            """INSERT INTO site_messages
                   (nickname, content, user_id, created_at)
               VALUES (?, ?, ?, ?)""",
            ("作者甲", "测试留言", self.author_id, stamp),
        )

    def tearDown(self):
        self._db_patch.stop()
        self._temp.cleanup()

    def make_handler(self, user_id, kind="member", username="author1"):
        handler = object.__new__(app.InventoryHandler)
        handler.session_identity = lambda: {
            "kind": kind,
            "user_id": user_id,
            "username": username,
            "nickname": username,
        }
        handler.is_admin = lambda: kind in ("owner", "admin")
        handler.client_ip = lambda: "127.0.0.1"
        responses = []
        handler.send_json = lambda status, payload: responses.append(
            (status, payload)
        )
        handler.log_activity = lambda *args, **kwargs: None
        return handler, responses

    def test_like_toggle_counts_and_notifies_author(self):
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        self.assertEqual(responses[-1][1], {"liked": True, "count": 1})
        notifications = app.query(
            "SELECT kind, module FROM user_notifications WHERE user_id = ?",
            (self.author_id,),
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["kind"], "message_like")
        self.assertEqual(notifications[0]["module"], "messages")

        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        self.assertEqual(responses[-1][1], {"liked": False, "count": 0})
        self.assertEqual(
            app.query_one(
                "SELECT COUNT(*) AS n FROM content_likes WHERE target_id = ?",
                (self.message_id,),
            )["n"],
            0,
        )

    def test_self_like_does_not_notify(self):
        handler, responses = self.make_handler(self.author_id, username="author1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        self.assertTrue(responses[-1][1]["liked"])
        self.assertEqual(
            app.query_one(
                "SELECT COUNT(*) AS n FROM user_notifications WHERE user_id = ?",
                (self.author_id,),
            )["n"],
            0,
        )

    def test_new_moment_notifies_members_only(self):
        stamp = app.now_text()
        app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role,
                    created_at, updated_at)
               VALUES (?, ?, ?, 'pending', 'member', ?, ?)""",
            ("pending1", "待审", "hash", stamp, stamp),
        )
        handler, responses = self.make_handler(0, kind="owner", username="owner")
        handler.api_moment_create({"content": "今天的动态", "images": []})
        moment_id = responses[-1][1]["id"]
        app.execute(
            """INSERT INTO activity_log
                   (created_at, actor_kind, user_id, action, target_type,
                    target_id, summary)
               VALUES (?, 'owner', 0, 'moment_create', 'moment', ?, ?)""",
            (app.now_text(), moment_id, "发布动态：今天的动态"),
        )
        rows = app.query(
            """SELECT user_id, kind, module FROM user_notifications
               WHERE kind = 'moment_new' ORDER BY user_id"""
        )
        self.assertEqual(
            sorted(int(row["user_id"]) for row in rows),
            sorted([self.author_id, self.other_id]),
        )
        self.assertTrue(all(row["module"] == "moments" for row in rows))

        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_activity()
        items = member_responses[-1][1]["items"]
        alerts = [item for item in items if item.get("alert")]
        self.assertTrue(
            any(
                item.get("actor") == "管理员"
                and item.get("text") == "更新了动态"
                for item in alerts
            )
        )

        owner_handler, owner_responses = self.make_handler(
            0, kind="owner", username="owner"
        )
        owner_handler.api_site_activity()
        owner_items = owner_responses[-1][1]["items"]
        self.assertFalse(
            any(
                item.get("text") == "更新了动态"
                for item in owner_items
                if item.get("alert")
            )
        )
        self.assertTrue(
            any(
                item.get("text") == "更新了一条动态" and not item.get("alert")
                for item in owner_items
            )
        )

        app.mark_notifications_seen(self.author_id, "moments")
        member_handler.api_site_activity()
        items = member_responses[-1][1]["items"]
        self.assertFalse(
            any(
                item.get("text") == "更新了动态"
                for item in items
                if item.get("alert")
            )
        )
        self.assertTrue(moment_id > 0)

    def test_moment_comment_reply_notifies_parent_author(self):
        stamp = app.now_text()
        moment_id = app.execute(
            """INSERT INTO moments (content, created_at)
               VALUES (?, ?)""",
            ("动态内容", stamp),
        )
        parent_id = app.execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, NULL, ?, ?, ?, ?)""",
            (moment_id, self.author_id, "作者甲", "第一条评论", stamp),
        )
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_moment_comment_create(
            moment_id, {"content": "回复一下", "parent_id": parent_id}
        )
        self.assertTrue(responses[-1][1]["id"] > 0)
        notifications = app.query(
            """SELECT kind, module, target_id FROM user_notifications
               WHERE user_id = ? AND kind = 'comment_reply'""",
            (self.author_id,),
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["module"], "moments")
        self.assertEqual(int(notifications[0]["target_id"]), moment_id)

    def test_comment_like_notifies_author_and_shows_names(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        comment_id = app.execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, NULL, ?, ?, ?, ?)""",
            (moment_id, self.author_id, "作者甲", "我的评论", stamp),
        )
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "comment", "target_id": comment_id}
        )
        self.assertEqual(responses[-1][1], {"liked": True, "count": 1})
        notifications = app.query(
            """SELECT kind, module, target_id, text FROM user_notifications
               WHERE user_id = ? AND kind = 'comment_like'""",
            (self.author_id,),
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["module"], "moments")
        self.assertEqual(int(notifications[0]["target_id"]), moment_id)
        self.assertEqual(notifications[0]["text"], "点赞了你的评论")

        viewer_handler, viewer_responses = self.make_handler(
            self.author_id, username="author1"
        )
        viewer_handler.api_moments({})
        moments = viewer_responses[-1][1]
        target = [row for row in moments if int(row["id"]) == moment_id][0]
        self.assertEqual(target["like_users"], [])
        comment = target["comments"][0]
        self.assertEqual(comment["like_count"], 1)
        self.assertEqual(comment["like_users"], ["other1"])
        self.assertTrue(comment["liked"] is False)

    def test_comment_like_shows_masked_for_guest(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        comment_id = app.execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, NULL, ?, ?, ?, ?)""",
            (moment_id, self.author_id, "作者甲", "我的评论", stamp),
        )
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "comment", "target_id": comment_id}
        )
        guest = object.__new__(app.InventoryHandler)
        guest.session_identity = lambda: None
        guest.is_admin = lambda: False
        responses = []
        guest.send_json = lambda status, payload: responses.append((status, payload))
        guest.api_moments({})
        moments = responses[-1][1]
        target = [row for row in moments if int(row["id"]) == moment_id][0]
        self.assertEqual(
            target["comments"][0]["like_users"], [app.mask_username("other1")]
        )

    def test_moment_like_lists_usernames(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle({"target_type": "moment", "target_id": moment_id})
        viewer_handler, viewer_responses = self.make_handler(
            self.author_id, username="author1"
        )
        viewer_handler.api_moments({})
        moments = viewer_responses[-1][1]
        target = [row for row in moments if int(row["id"]) == moment_id][0]
        self.assertEqual(target["like_count"], 1)
        self.assertEqual(target["like_users"], ["other1"])

    def test_moment_comment_notifies_owner(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_moment_comment_create(moment_id, {"content": "来评论一下"})
        parent_id = responses[-1][1]["id"]
        owner_rows = app.query(
            """SELECT kind, text FROM user_notifications
               WHERE user_id = 0 AND module = 'moments'"""
        )
        self.assertEqual(len(owner_rows), 1)
        self.assertEqual(owner_rows[0]["kind"], "moment_comment")
        self.assertEqual(owner_rows[0]["text"], "评论了你的动态")

        author_handler, _ = self.make_handler(self.author_id, username="author1")
        author_handler.api_moment_comment_create(
            moment_id, {"content": "回复这条评论", "parent_id": parent_id}
        )
        self.assertEqual(
            app.query_one(
                """SELECT COUNT(*) AS n FROM user_notifications
                   WHERE user_id = 0 AND kind = 'moment_comment'"""
            )["n"],
            2,
        )
        parent_rows = app.query(
            """SELECT text FROM user_notifications
               WHERE user_id = ? AND kind = 'comment_reply'""",
            (self.other_id,),
        )
        self.assertEqual([row["text"] for row in parent_rows], ["回复了你的评论"])

        owner_handler, owner_responses = self.make_handler(0, kind="owner")
        owner_handler.api_site_moments_unread()
        payload = owner_responses[-1][1]
        self.assertEqual(payload["unread"], 2)
        self.assertEqual(payload["targets"], [moment_id])

        owner_handler.api_site_activity()
        items = owner_responses[-1][1]["items"]
        self.assertTrue(
            any(
                item.get("alert")
                and "动态" in str(item.get("text"))
                and "评论" in str(item.get("text"))
                for item in items
            )
        )

    def test_reply_to_message_notifies_author(self):
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_site_message_create(
            {
                "content": "回复内容",
                "parent_id": self.message_id,
                "files": [],
            }
        )
        reply_id = responses[-1][1]["id"]
        self.assertTrue(reply_id > 0)
        notifications = app.query(
            """SELECT kind, module FROM user_notifications
               WHERE user_id = ? AND kind = 'message_reply'""",
            (self.author_id,),
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["module"], "messages")

    def test_member_message_badge_reports_unread_likes(self):
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_messages_unread()
        self.assertEqual(member_responses[-1][1]["unread"], 1)
        app.mark_notifications_seen(self.author_id, "messages")
        member_handler.api_site_messages_unread()
        self.assertEqual(member_responses[-1][1]["unread"], 0)

    def test_message_list_reports_like_usernames(self):
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        admin_handler, admin_responses = self.make_handler(0, kind="owner")
        admin_handler.api_site_messages({})
        roots = admin_responses[-1][1]
        target = [row for row in roots if int(row["id"]) == self.message_id][0]
        self.assertEqual(target["like_users"], ["other1"])
        self.assertEqual(target["like_count"], 1)

    def test_guest_sees_masked_like_usernames(self):
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        guest = object.__new__(app.InventoryHandler)
        guest.session_identity = lambda: None
        guest.is_admin = lambda: False
        responses = []
        guest.send_json = lambda status, payload: responses.append((status, payload))
        guest.api_site_messages({})
        roots = responses[-1][1]
        target = [row for row in roots if int(row["id"]) == self.message_id][0]
        self.assertEqual(target["like_users"], [app.mask_username("other1")])

    def test_reply_to_reply_is_grouped_and_notifies(self):
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_site_message_create(
            {"content": "第一条回复", "parent_id": self.message_id, "files": []}
        )
        reply_id = responses[-1][1]["id"]
        author_handler, author_responses = self.make_handler(
            self.author_id, username="author1"
        )
        author_handler.api_site_message_create(
            {"content": "回复那条回复", "parent_id": reply_id, "files": []}
        )
        nested_id = author_responses[-1][1]["id"]
        notifications = app.query(
            """SELECT text FROM user_notifications
               WHERE user_id = ? AND kind = 'message_reply'""",
            (self.other_id,),
        )
        self.assertTrue(
            any(str(row["text"]) == "回复了你" for row in notifications)
        )

        admin_handler, admin_responses = self.make_handler(0, kind="owner")
        admin_handler.api_site_messages({})
        root = [
            row
            for row in admin_responses[-1][1]
            if int(row["id"]) == self.message_id
        ][0]
        reply_ids = [int(row["id"]) for row in root["replies"]]
        self.assertIn(reply_id, reply_ids)
        self.assertIn(nested_id, reply_ids)
        nested = [
            row for row in root["replies"] if int(row["id"]) == nested_id
        ][0]
        self.assertEqual(int(nested["parent_id"]), reply_id)
        self.assertEqual(nested["reply_to"], "other1")

    def test_unread_targets_clear_per_card(self):
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_messages_unread()
        self.assertEqual(member_responses[-1][1]["targets"], [self.message_id])
        member_handler.api_site_notifications_seen(
            {"module": "messages", "target_id": self.message_id}
        )
        member_handler.api_site_messages_unread()
        self.assertEqual(member_responses[-1][1]["targets"], [])
        self.assertEqual(member_responses[-1][1]["unread"], 0)

    def test_owner_mark_seen_clears_moment_comment_alert(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_moment_comment_create(moment_id, {"content": "评论一下"})
        owner_handler, owner_responses = self.make_handler(0, kind="owner")
        owner_handler.api_site_moments_unread()
        self.assertEqual(owner_responses[-1][1]["targets"], [moment_id])
        self.assertEqual(owner_responses[-1][1]["unread"], 1)

        owner_handler.api_site_notifications_seen(
            {"module": "moments", "target_id": moment_id}
        )
        owner_handler.api_site_moments_unread()
        self.assertEqual(owner_responses[-1][1]["targets"], [])
        self.assertEqual(owner_responses[-1][1]["unread"], 0)
        self.assertIsNotNone(
            app.query_one(
                """SELECT seen_at FROM user_notifications
                   WHERE user_id = 0 AND module = 'moments'"""
            )["seen_at"]
        )

    def test_map_place_interact_toggles_and_notifies_creator(self):
        stamp = app.now_text()
        place_id = app.execute(
            """INSERT INTO map_places
                   (name, lat, lng, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("测试地点", 34.34, 108.94, self.author_id, stamp, stamp),
        )
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.request_base_url = lambda: "https://zhexiyan.cc"
        handler.api_map_place_interact(
            f"/api/map/places/{place_id}/interact", {"kind": "like"}
        )
        self.assertEqual(
            responses[-1][1], {"active": True, "count": 1, "kind": "like"}
        )
        handler.api_map_place_interact(
            f"/api/map/places/{place_id}/interact", {"kind": "checkin"}
        )
        self.assertEqual(
            responses[-1][1], {"active": True, "count": 1, "kind": "checkin"}
        )
        rows = app.query(
            """SELECT kind, module, target_id, text FROM user_notifications
               WHERE user_id = ? AND module = 'map' ORDER BY id""",
            (self.author_id,),
        )
        self.assertEqual(
            [row["kind"] for row in rows], ["place_like", "place_checkin"]
        )
        self.assertEqual({int(row["target_id"]) for row in rows}, {place_id})
        self.assertTrue(rows[0]["text"].endswith("点赞了你的标记点"))
        self.assertTrue(rows[1]["text"].endswith("打卡了你的标记点"))

        handler.api_map_place_interact(
            f"/api/map/places/{place_id}/interact", {"kind": "like"}
        )
        self.assertEqual(
            responses[-1][1], {"active": False, "count": 0, "kind": "like"}
        )
        # 再点回来不会重复发提醒
        handler.api_map_place_interact(
            f"/api/map/places/{place_id}/interact", {"kind": "like"}
        )
        self.assertEqual(
            responses[-1][1], {"active": True, "count": 1, "kind": "like"}
        )
        self.assertEqual(
            app.query_one(
                "SELECT COUNT(*) AS n FROM user_notifications WHERE user_id = ? AND kind = 'place_like'",
                (self.author_id,),
            )["n"],
            1,
        )
        author_handler, _ = self.make_handler(self.author_id, username="author1")
        author_handler.api_map_mark_seen({"notify_targets": [place_id]})
        self.assertEqual(
            (app.unseen_notifications(self.author_id).get("map") or {}).get("count", 0),
            0,
        )
        self.assertEqual(
            app.query_one(
                "SELECT COUNT(*) AS n FROM map_place_interactions WHERE kind = 'checkin'"
            )["n"],
            1,
        )

    def test_map_api_exposes_interaction_state(self):
        stamp = app.now_text()
        place_id = app.execute(
            """INSERT INTO map_places
                   (name, lat, lng, created_by, created_at, updated_at)
               VALUES (?, ?, ?, 0, ?, ?)""",
            ("打卡点", 34.34, 108.94, stamp, stamp),
        )
        app.execute(
            """INSERT INTO map_place_interactions (place_id, user_id, kind, created_at)
               VALUES (?, ?, 'checkin', ?)""",
            (place_id, self.author_id, stamp),
        )
        app.add_user_notification(
            0, "place_checkin", "map", place_id, "作者甲", "作者甲 打卡了你的标记点"
        )
        handler, responses = self.make_handler(0, kind="owner", username="owner")
        handler.api_map()
        payload = responses[-1][1]
        target = [
            row for row in payload["places"] if int(row["id"]) == place_id
        ][0]
        self.assertEqual(target["checkin_count"], 1)
        self.assertFalse(target["checked_in"])
        self.assertTrue(target["fresh"])
        self.assertEqual(payload["notify_targets"], [place_id])

        owner_handler, owner_responses = self.make_handler(0, kind="owner")
        owner_handler.api_map_mark_seen({"notify_targets": [place_id]})
        owner_handler.api_site_activity()
        items = owner_responses[-1][1]["items"]
        self.assertFalse(
            any(item.get("id") == "notify-map" for item in items)
        )

    def test_message_filters_mark_like_and_reply_on_replies(self):
        stamp = app.now_text()
        reply_id = app.execute(
            """INSERT INTO site_messages
                   (nickname, content, parent_id, user_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("作者乙", "一条回复", self.message_id, self.other_id, stamp),
        )
        app.execute(
            """INSERT INTO content_likes (target_type, target_id, user_id, created_at)
               VALUES ('message', ?, ?, ?)""",
            (reply_id, self.author_id, stamp),
        )
        handler, responses = self.make_handler(self.author_id, username="author1")
        handler.api_site_messages({})
        root = [
            row for row in responses[-1][1] if int(row["id"]) == self.message_id
        ][0]
        self.assertTrue(root["mine"])
        self.assertTrue(root["liked_by_me"])
        self.assertFalse(root["replied_by_me"])
        self.assertFalse(root["replies"][0]["mine"])

        handler.api_site_message_create(
            {"content": "作者自己的回复", "parent_id": self.message_id, "files": []}
        )
        handler.api_site_messages({})
        root = [
            row for row in responses[-1][1] if int(row["id"]) == self.message_id
        ][0]
        self.assertTrue(root["replied_by_me"])
        self.assertTrue(
            any(reply.get("mine") for reply in root["replies"])
        )

        other_handler, other_responses = self.make_handler(
            self.other_id, username="other1"
        )
        other_handler.api_site_messages({})
        other_root = [
            row
            for row in other_responses[-1][1]
            if int(row["id"]) == self.message_id
        ][0]
        self.assertFalse(other_root["mine"])
        self.assertFalse(other_root["liked_by_me"])
        self.assertTrue(other_root["replied_by_me"])
        self.assertTrue(other_root["replies"][0]["mine"])

    def test_moment_filters_mark_likes_and_comments(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("筛选测试动态", stamp),
        )
        comment_id = app.execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, NULL, ?, ?, ?, ?)""",
            (moment_id, self.other_id, "作者乙", "评论一下", stamp),
        )
        app.execute(
            """INSERT INTO content_likes (target_type, target_id, user_id, created_at)
               VALUES ('comment', ?, ?, ?)""",
            (comment_id, self.author_id, stamp),
        )
        handler, responses = self.make_handler(self.author_id, username="author1")
        handler.api_moments({})
        row = [item for item in responses[-1][1] if int(item["id"]) == moment_id][0]
        self.assertTrue(row["liked_by_me"])
        self.assertFalse(row["commented_by_me"])

        other_handler, other_responses = self.make_handler(
            self.other_id, username="other1"
        )
        other_handler.api_moments({})
        other_row = [
            item for item in other_responses[-1][1] if int(item["id"]) == moment_id
        ][0]
        self.assertTrue(other_row["commented_by_me"])
        self.assertTrue(other_row["comments"][0]["mine"])

    def test_deleted_message_clears_notification(self):
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        app.execute("DELETE FROM site_messages WHERE id = ?", (self.message_id,))
        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_messages_unread()
        payload = member_responses[-1][1]
        self.assertEqual(payload["targets"], [])
        self.assertEqual(payload["unread"], 0)


class HomeActivityAlertTests(unittest.TestCase):
    def test_pending_registration_is_reported_to_admin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                stamp = app.now_text()
                app.execute(
                    """INSERT INTO users
                           (username, nickname, password_hash, status, role,
                            created_at, updated_at)
                       VALUES (?, ?, ?, 'pending', 'member', ?, ?)""",
                    ("newbie", "新用户", "hash", stamp, stamp),
                )
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: {"kind": "owner", "user_id": 0}
                handler.is_admin = lambda: True
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.api_site_activity()
                items = responses[0][1]["items"]
                alerts = [item for item in items if item.get("alert")]
                self.assertTrue(
                    any("待审核注册申请" in str(item.get("text")) for item in alerts)
                )

    def test_guest_activity_has_no_admin_alerts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: None
                handler.is_admin = lambda: False
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.api_site_activity()
                items = responses[0][1]["items"]
                self.assertFalse(any(item.get("alert") for item in items))


class UploadLimitTests(unittest.TestCase):
    def test_defaults_cover_every_schema_key(self):
        defaults = app.upload_limit_defaults()
        self.assertEqual(
            set(defaults),
            {item["key"] for item in app.UPLOAD_LIMIT_SCHEMA},
        )
        self.assertEqual(
            defaults["message_file"]["max_count"], app.MESSAGE_FILE_MAX_COUNT
        )
        self.assertEqual(
            defaults["message_file"]["max_file_bytes"], app.MESSAGE_FILE_MAX_BYTES
        )
        self.assertEqual(
            defaults["message_file"]["max_total_bytes"],
            app.MESSAGE_FILE_TOTAL_MAX_BYTES,
        )
        self.assertEqual(
            defaults["moment_image"]["max_total_bytes"],
            app.MOMENT_IMAGE_TOTAL_MAX_BYTES,
        )

    def test_normalize_rejects_values_beyond_hard_limits(self):
        with self.assertRaises(ValueError):
            app.normalize_upload_limit_payload(
                {
                    "limits": {
                        "message_file": {
                            "max_file_bytes": app.UPLOAD_LIMIT_HARD_MAX_BYTES + 1
                        }
                    }
                }
            )
        with self.assertRaises(ValueError):
            app.normalize_upload_limit_payload(
                {
                    "limits": {
                        "moment_image": {
                            "max_count": app.UPLOAD_LIMIT_HARD_MAX_COUNT + 1
                        }
                    }
                }
            )

    def test_normalize_rejects_total_smaller_than_single_file(self):
        with self.assertRaises(ValueError):
            app.normalize_upload_limit_payload(
                {
                    "limits": {
                        "message_file": {
                            "max_file_bytes": 5 * 1024 * 1024,
                            "max_total_bytes": 1024,
                        }
                    }
                }
            )

    def test_normalize_keeps_defaults_for_missing_keys(self):
        normalized = app.normalize_upload_limit_payload(
            {"limits": {"music_file": {"max_file_bytes": 12 * 1024 * 1024}}}
        )
        self.assertEqual(
            normalized["music_file"]["max_file_bytes"], 12 * 1024 * 1024
        )
        self.assertEqual(
            normalized["book_file"]["max_file_bytes"], app.BOOK_MAX_BYTES
        )

    def test_saved_limits_round_trip_and_clamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                app.app_meta_set(
                    app.UPLOAD_LIMIT_META_KEY,
                    json.dumps(
                        {
                            "message_file": {
                                "max_count": 8,
                                "max_file_bytes": 12 * 1024 * 1024,
                                "max_total_bytes": 40 * 1024 * 1024,
                            },
                            "music_file": {
                                "max_file_bytes": app.UPLOAD_LIMIT_HARD_MAX_BYTES
                                + 5 * 1024 * 1024
                            },
                        }
                    ),
                )
                limits = app.upload_limits()
                self.assertEqual(limits["message_file"]["max_count"], 8)
                self.assertEqual(
                    limits["message_file"]["max_file_bytes"], 12 * 1024 * 1024
                )
                self.assertEqual(
                    limits["message_file"]["max_total_bytes"], 40 * 1024 * 1024
                )
                self.assertEqual(
                    limits["music_file"]["max_file_bytes"],
                    app.UPLOAD_LIMIT_HARD_MAX_BYTES,
                )
                self.assertEqual(
                    limits["book_file"]["max_file_bytes"], app.BOOK_MAX_BYTES
                )

    def test_message_attachment_count_follows_saved_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                app.app_meta_set(
                    app.UPLOAD_LIMIT_META_KEY,
                    json.dumps(
                        {
                            "message_file": {
                                "max_count": 1,
                                "max_file_bytes": 1024,
                                "max_total_bytes": 1024,
                            }
                        }
                    ),
                )
                handler = object.__new__(app.InventoryHandler)
                payload = {
                    "files": [
                        {
                            "name": "a.txt",
                            "data_base64": base64.b64encode(b"hi").decode("ascii"),
                        },
                        {
                            "name": "b.txt",
                            "data_base64": base64.b64encode(b"ho").decode("ascii"),
                        },
                    ]
                }
                prepared, error = handler.message_attachments(payload)
                self.assertIsNone(prepared)
                self.assertIn("1", error)

    def test_upload_limits_endpoints_permissions(self):
        self.assertIn("/api/site/upload-limits", app.ALWAYS_PUBLIC_APIS)
        self.assertIsNone(
            app.required_permission("/api/admin/upload-limits", "GET")
        )
        self.assertIsNone(
            app.required_permission("/api/admin/upload-limits", "POST")
        )

    def test_upload_limit_labels_cover_small_sizes(self):
        self.assertEqual(app.format_upload_limit_bytes(512 * 1024), "512KB")
        self.assertEqual(app.format_upload_limit_bytes(2 * 1024 * 1024), "2MB")
        self.assertEqual(
            app.format_upload_limit_bytes(int(2.5 * 1024 * 1024)), "2.5MB"
        )


if __name__ == "__main__":
    unittest.main()
