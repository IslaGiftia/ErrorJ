import base64
import json
import os
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import app


class MessageDeletePermissionTests(unittest.TestCase):
    def test_required_permission_allows_signed_in_message_delete(self):
        # 删除的细分权限（管理员可删任意 / 普通账号只能删自己的）在处理器里判，
        # 权限映射层对登录账号放行；游客仍会被 guard 拦下。
        self.assertEqual(
            app.required_permission("/api/site/messages/12", "DELETE"), ""
        )

    def test_message_delete_handler_rejects_other_users_message(self):
        handler = object.__new__(app.InventoryHandler)
        handler.is_admin = lambda: False
        handler.session_identity = lambda: {
            "kind": "member",
            "user_id": 7,
            "username": "tester",
        }

        with patch.object(
            app,
            "query_one",
            return_value={"id": 12, "content": "别人的留言", "user_id": 9},
        ):
            with patch.object(app, "api_error") as api_error:
                handler.api_site_message_delete("/api/site/messages/12")

        api_error.assert_called_once_with(handler, 403, "只能删除自己的留言。")

    def test_message_delete_handler_allows_own_message(self):
        handler = object.__new__(app.InventoryHandler)
        handler.is_admin = lambda: False
        handler.session_identity = lambda: {
            "kind": "member",
            "user_id": 7,
            "username": "tester",
        }
        handler.log_activity = lambda *args, **kwargs: None
        handler.notification_actor_name = lambda identity: "tester"
        sent = []
        handler.send_json = lambda status, payload: sent.append((status, payload))

        with patch.object(
            app,
            "query_one",
            return_value={"id": 12, "content": "自己的留言", "user_id": 7},
        ), patch.object(app, "query", return_value=[]), patch.object(
            app, "execute"
        ) as execute, patch.object(
            app, "notify_async"
        ), patch.object(
            app, "remove_data_file"
        ), patch.object(
            app, "api_error"
        ) as api_error:
            handler.api_site_message_delete("/api/site/messages/12")

        api_error.assert_not_called()
        self.assertEqual(sent, [(200, {"ok": True})])
        delete_calls = [
            call
            for call in execute.call_args_list
            if call.args and call.args[0] == "DELETE FROM site_messages WHERE id = ?"
        ]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0].args[1], (12,))

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

    def test_download_endpoints_are_open_to_members(self):
        self.assertEqual(app.required_permission("/api/site/music/1/download", "GET"), "")
        self.assertEqual(app.required_permission("/api/books/1/download", "GET"), "")

    def test_download_request_flow_is_gone(self):
        """下载申请 / 审批整体下线：接口、处理器与通知事件都不再存在。"""
        self.assertFalse(hasattr(app.InventoryHandler, "api_download_request_create"))
        self.assertFalse(hasattr(app.InventoryHandler, "api_admin_download_requests"))
        self.assertFalse(hasattr(app.InventoryHandler, "api_admin_download_request_action"))
        self.assertFalse(hasattr(app.InventoryHandler, "download_state"))
        self.assertNotIn(
            "download_request", {item["key"] for item in app.NOTIFY_EVENTS}
        )


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
    def test_member_downloads_directly_without_approval(self):
        """下载不再需要申请与审批：登录账号直接拿文件，也不再写申请记录。"""
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
                music_id = app.execute(
                    """INSERT INTO site_music
                           (title, source_type, source_id, sort_order, created_at)
                       VALUES (?, 'file', ?, 0, ?)""",
                    ("测试歌曲", "site_music_files/tone.mp3", stamp),
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
                sent = []
                handler.send_data_file = lambda *args, **kwargs: sent.append(args)

                handler.api_book_download(book_id)
                handler.api_site_music_download(music_id)

                # 没有任何 401 / 403，两个文件都直接送出
                self.assertEqual(responses, [])
                self.assertEqual(
                    [Path(str(call[0])).name for call in sent],
                    ["test.txt", "tone.mp3"],
                )
                # 也不再写申请记录
                self.assertEqual(
                    app.query_one("SELECT COUNT(*) AS n FROM download_requests")["n"], 0
                )

                # 游客仍然拿不到文件（登录要求没被一起放开）
                guest = object.__new__(app.InventoryHandler)
                guest.session_identity = lambda: None
                guest.is_admin = lambda: False
                guest_responses = []
                guest.send_json = lambda status, payload: guest_responses.append(
                    (status, payload)
                )
                guest.send_data_file = lambda *args, **kwargs: None
                guest.api_book_download(book_id)
                self.assertEqual(guest_responses[-1][0], 401)


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

    def test_notification_unread_api_is_public(self):
        self.assertIn("/api/site/notifications/unread", app.ALWAYS_PUBLIC_APIS)

    def test_public_activity_uses_generic_content_labels(self):
        self.assertEqual(app.PUBLIC_ACTIVITY_LABELS["message_create"], "发表了留言")
        self.assertEqual(app.PUBLIC_ACTIVITY_LABELS["book_upload"], "上架了一本电子书")
        self.assertEqual(app.PUBLIC_ACTIVITY_LABELS["map_place_create"], "新增了一个足迹")

    def test_game_module_is_gone(self):
        """游戏模块整体下线：页面、接口、权限点与公开动态事件都不再存在。"""
        self.assertFalse((app.STATIC_DIR / "games").exists())
        self.assertFalse((app.STATIC_DIR / "site" / "game-activity.js").exists())
        self.assertFalse(hasattr(app.InventoryHandler, "api_site_game_play"))
        self.assertNotIn("/api/site/game-play", app.ALWAYS_PUBLIC_APIS)
        self.assertNotIn("game_play", app.PUBLIC_ACTIVITY_LABELS)
        self.assertNotIn("game", app.REPORT_TARGET_TYPES)
        keys = {item["key"] for item in app.GUEST_PAGE_PERMISSIONS}
        self.assertNotIn("guest:page:games", keys)

    def test_recommend_page_collects_four_subpages(self):
        """「推荐」页把歌曲 / 书籍 / 网页 / 站内资源四个子页并进一个页面，首页只留一个入口。"""
        home = (app.STATIC_DIR / "site" / "site.html").read_text(encoding="utf-8")
        self.assertIn('href="/downloads"', home)
        self.assertIn('id="downloadsEntry"', home)
        self.assertIn('id="downloadsPending"', home)
        self.assertIn("推荐", home)
        for gone in ('href="/music"', 'href="/books"', 'href="/recommendations"'):
            self.assertNotIn(gone, home)
        self.assertNotIn("游戏", home)

        page = (app.STATIC_DIR / "downloads.html").read_text(encoding="utf-8")
        for key in ("music", "books", "web", "resource"):
            self.assertIn('data-tab="%s"' % key, page)
            self.assertIn('data-panel="%s"' % key, page)
        # 四个子页面一开始就全部加载好，切换只翻转显隐
        for src in (
            "/music?embed=1",
            "/books?embed=1",
            "/recommendations?embed=1&view=web",
            "/recommendations?embed=1&view=resource",
        ):
            self.assertIn(src, page)
        self.assertIn('id="dlAction"', page)

        self.assertEqual(app.GUEST_PAGE_RULES.get("/downloads"), "guest:page:downloads")
        labels = {item["key"]: item["label"] for item in app.GUEST_PAGE_PERMISSIONS}
        self.assertEqual(labels["guest:page:downloads"], "推荐")
        for name in ("music.html", "books.html", "recommendations.html"):
            text = (app.STATIC_DIR / name).read_text(encoding="utf-8")
            self.assertIn("/static/site/embed.css", text)
            self.assertIn("/static/site/embed.js", text)

    def test_legacy_subpages_redirect_into_recommend_page(self):
        """歌曲 / 书籍的独立地址只剩 iframe 落点这一个用途，直接打开就送回推荐页。"""
        to_urls = app.legacy_subpage_redirect
        self.assertEqual(to_urls("/books", {}), "/downloads?tab=books")
        self.assertEqual(to_urls("/music", {}), "/downloads?tab=music")
        # 侧栏更新日志带过来的 focus 定位参数要一起带走
        self.assertEqual(
            to_urls("/books", {"focus": ["3"]}), "/downloads?tab=books&focus=3"
        )
        # iframe 内嵌（?embed=1）照常出页面，不能跳走
        for path in ("/books", "/music"):
            self.assertEqual(to_urls(path, {"embed": ["1"]}), "")
        # 其它地址一概不管
        for path in ("/downloads", "/recommendations", "/", "/inventory"):
            self.assertEqual(to_urls(path, {}), "")

    def test_recommend_module_has_no_report_entry(self):
        """举报入口从推荐模块整体退场，只保留单条内容卡片上的举报。"""
        for name in ("books.html", "music.html", "recommendations.html"):
            text = (app.STATIC_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn('href="/reporting"', text)
        embed = (app.STATIC_DIR / "site" / "embed.css").read_text(encoding="utf-8")
        self.assertNotIn('a[href="/reporting"]', embed)

    def test_messages_permission_label_is_renamed(self):
        labels = {item["key"]: item["label"] for item in app.GUEST_PAGE_PERMISSIONS}
        self.assertEqual(labels["guest:page:messages"], "留言")

    def test_module_permission_labels_match_home_entries(self):
        labels = {item["key"]: item["label"] for item in app.GUEST_PAGE_PERMISSIONS}
        self.assertEqual(labels["guest:page:moments"], "动态")
        self.assertEqual(labels["guest:page:recommendations"], "推荐内容")

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
        app.RATE_LIMITS.clear()
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

    def test_shared_book_resource_offers_download_not_reader(self):
        """书籍阅读器已整体下线：站内分享的电子书卡片指向下载，而不是阅读页。"""
        self.assertFalse((app.STATIC_DIR / "reader.html").exists())
        handler, responses = self.make_handler(0)
        handler.api_admin_share_content(
            {
                "target": "recommendation",
                "resource_type": "book",
                "resource_id": self.book_id,
            }
        )
        self.assertEqual(responses[-1][0], 200)
        handler.api_recommendations({})
        items = responses[-1][1]["items"]
        card = [item for item in items if item["kind"] == "resource"][0]
        self.assertEqual(
            card["resource"]["page_url"], f"/api/books/{self.book_id}/download"
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
        app.RATE_LIMITS.clear()
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
        handler.headers = {"User-Agent": "test", "Host": "example.test"}
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

    def test_nested_reply_does_not_push_webhook(self):
        """楼中楼（回复某条回复）只在站内提醒，不推 Webhook；回复顶层留言照常推。"""
        stamp = app.now_text()
        root_id = app.execute(
            """INSERT INTO site_messages
                   (nickname, content, user_id, status, created_at)
               VALUES (?, ?, ?, 'approved', ?)""",
            ("作者甲", "顶层留言", self.author_id, stamp),
        )

        reply_handler, reply_responses = self.make_handler(
            self.other_id, username="other1"
        )
        with patch.object(app, "rate_allow", return_value=True), patch.object(
            app, "notify_async"
        ) as pushed:
            reply_handler.api_site_message_create(
                {"content": "回复顶层留言", "parent_id": root_id}
            )
        self.assertEqual(reply_responses[-1][0], 200)
        self.assertEqual(pushed.call_count, 1)
        self.assertEqual(pushed.call_args[0][0], "message")
        self.assertIn("新的回复", pushed.call_args[0][1])
        reply_id = reply_responses[-1][1]["id"]

        nested_handler, nested_responses = self.make_handler(
            self.author_id, username="author1"
        )
        with patch.object(app, "rate_allow", return_value=True), patch.object(
            app, "notify_async"
        ) as nested_pushed:
            nested_handler.api_site_message_create(
                {"content": "回复那条回复", "parent_id": reply_id}
            )
        self.assertEqual(nested_responses[-1][0], 200)
        nested_pushed.assert_not_called()
        # 站内提醒仍然要有：只是不再推 Webhook
        self.assertEqual(
            app.query_one(
                """SELECT COUNT(*) AS n FROM user_notifications
                   WHERE user_id = ? AND kind = 'message_reply'""",
                (self.other_id,),
            )["n"],
            1,
        )

    def test_top_level_message_still_pushes_webhook(self):
        """顶层留言（含先审后发）照常推送，没被楼中楼那条规则误伤。"""
        handler, responses = self.make_handler(self.author_id, username="author1")
        with patch.object(app, "rate_allow", return_value=True), patch.object(
            app, "notify_async"
        ) as pushed:
            handler.api_site_message_create({"content": "新留言"})
        self.assertEqual(responses[-1][0], 200)
        self.assertEqual(pushed.call_count, 1)
        self.assertIn("新的留言", pushed.call_args[0][1])

    def test_deleting_message_does_not_push_webhook(self):
        """删除留言不推 Webhook（和「删除标记不推送」同一条规则），只留内容事件。"""
        handler, responses = self.make_handler(self.author_id, username="author1")
        handler.command = "DELETE"
        with patch.object(app, "notify_async") as pushed:
            handler.api_site_message_delete(f"/api/site/messages/{self.message_id}")
        self.assertEqual(responses[-1][0], 200)
        pushed.assert_not_called()
        self.assertIsNone(
            app.query_one(
                "SELECT id FROM site_messages WHERE id = ?", (self.message_id,)
            )
        )

    def test_nested_moment_reply_does_not_push_webhook(self):
        """动态的楼中楼回复同理：站内提醒保留，Webhook 不推。"""
        moment_id = app.execute(
            "INSERT INTO moments (content, kind, created_at) VALUES (?, 'post', ?)",
            ("动态内容", app.now_text()),
        )
        handler, responses = self.make_handler(self.other_id, username="other1")
        with patch.object(app, "notify_async") as first:
            handler.api_moment_comment_create(moment_id, {"content": "评论一条"})
        self.assertEqual(responses[-1][0], 200)
        self.assertEqual(first.call_count, 1)
        self.assertEqual(first.call_args[0][0], "moment_comment")
        comment_id = responses[-1][1]["id"]

        with patch.object(app, "notify_async") as second:
            handler.api_moment_comment_create(
                moment_id, {"content": "回复那条评论", "parent_id": comment_id}
            )
        self.assertEqual(responses[-1][0], 200)
        # 回复顶层评论属于「评论了动态」，仍然推
        self.assertEqual(second.call_count, 1)
        reply_id = responses[-1][1]["id"]

        with patch.object(app, "notify_async") as nested:
            handler.api_moment_comment_create(
                moment_id, {"content": "回复那条回复", "parent_id": reply_id}
            )
        self.assertEqual(responses[-1][0], 200)
        nested.assert_not_called()

    def test_sidebar_log_hides_entries_whose_target_is_gone(self):
        """更新日志：内容被删掉的条目整条不显示，让位给更早的记录。"""
        stamp = app.now_text()
        app.execute(
            """INSERT INTO activity_log
                   (created_at, actor_kind, user_id, action, summary, target_type, target_id)
               VALUES (?, 'owner', 0, 'music_upload', ?, 'music', ?)""",
            (stamp, "上传歌曲：已经被删掉的歌", 999999),
        )
        items = app.sidebar_activities()
        self.assertEqual([item for item in items if item["action"] == "music_upload"], [])

        # 目标还在的时候照常带名称
        music_id = app.execute(
            """INSERT INTO site_music
                   (title, artist, source_type, source_id, sort_order, created_at)
               VALUES (?, ?, 'url', ?, 0, ?)""",
            ("还在的歌", "歌手", "https://example.com/x.mp3", stamp),
        )
        app.execute(
            """INSERT INTO activity_log
                   (created_at, actor_kind, user_id, action, summary, target_type, target_id)
               VALUES (?, 'owner', 0, 'music_upload', ?, 'music', ?)""",
            (stamp, "上传歌曲：还在的歌", music_id),
        )
        items = app.sidebar_activities()
        row = [item for item in items if item["target"] == "还在的歌"]
        self.assertEqual(len(row), 1)

    def test_sidebar_log_urls_point_back_to_the_recommend_page(self):
        """更新日志里歌曲 / 书籍 / 网页 / 站内资源都指回推荐页，不再指向独立子页。

        站长要求删掉「点日志新开标签页打开那四个独立模块」这套逻辑，所以接口算出来的
        地址必须落在 /downloads 上；前端也据此在留言 / 动态页只提示「请在推荐页查看」。
        """
        stamp = app.now_text()
        music_id = app.execute(
            """INSERT INTO site_music
                   (title, artist, source_type, source_id, sort_order, created_at)
               VALUES (?, ?, 'url', ?, 0, ?)""",
            ("指回推荐页的歌", "歌手", "https://example.com/z.mp3", stamp),
        )
        app.execute(
            """INSERT INTO activity_log
                   (created_at, actor_kind, user_id, action, summary, target_type, target_id)
               VALUES (?, 'owner', 0, 'music_upload', ?, 'music', ?)""",
            (stamp, "上传歌曲：指回推荐页的歌", music_id),
        )
        items = app.sidebar_activities()
        row = [item for item in items if item["target"] == "指回推荐页的歌"]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["tab"], "music")
        self.assertEqual(row[0]["href"], "/downloads?tab=music")
        self.assertEqual(row[0]["url"], f"/downloads?tab=music&focus={music_id}")

    def test_sidebar_user_card_prefers_recent_activity_over_password_login(self):
        """左下「注册账户」显示最近活跃，而不是只看输密码那一刻的登录时间。

        `users.last_login_at` 只在真的输密码登录时写，靠记住的会话继续浏览不会更新，所以
        一直挂着的账号会显示成很多天前登录；接口另外回一次 `access_log` 里最新的页面访问，
        没有访问记录（访问日志没开 / 记录已被清理）时留空，前端退回原来的「…前登录」。
        """
        login_stamp = "2026-01-01 08:00:00"
        view_stamp = "2026-10-14 09:05:00"
        app.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (login_stamp, self.author_id),
        )
        app.execute(
            """INSERT INTO access_log
                   (created_at, actor_kind, path, status, user_id, actor_name)
               VALUES (?, 'member', '/messages', 200, ?, '作者甲')""",
            (view_stamp, self.author_id),
        )
        # 「注册 N 天 · X 前活跃」只有管理员看得到
        admin_view = app.sidebar_users(self.author_id, viewer_is_admin=True)
        rows = {item["id"]: item for item in admin_view["items"]}
        self.assertEqual(rows[self.author_id]["last_login_at"], login_stamp)
        self.assertEqual(rows[self.author_id]["last_view_at"], view_stamp)
        self.assertEqual(rows[self.other_id]["last_view_at"], "")
        # 普通账号视角不下发这几个字段（连自己那行也没有）
        member_view = app.sidebar_users(self.author_id)
        for item in member_view["items"]:
            self.assertNotIn("last_view_at", item)
            self.assertNotIn("last_login_at", item)
            self.assertNotIn("registered_days", item)

    def test_status_invisible_suffix_and_owner_custom_text(self):
        """状态：只有「隐身」会被记住；它和自定义文案都只在人还在活跃窗口内时才显示。"""
        self.assertEqual(app.owner_status()["label"], "离线")
        self.assertEqual(app.owner_status()["tone"], "offline")

        # 站长可以写自定义文案
        owner, owner_responses = self.make_handler(0, kind="owner", username="管理员")
        owner.api_site_user_status_save({"mode": "auto", "suffix": "", "text": "摸鱼中"})
        self.assertEqual(owner_responses[-1][0], 200)
        self.assertEqual(app.owner_status()["text"], "摸鱼中")
        # 没有访问记录 = 人不在：文案也不显示，就是「离线」
        self.assertEqual(app.owner_status()["label"], "离线")

        # 有访问记录 -> 在线，文案才显示出来
        app.execute(
            """INSERT INTO access_log
                   (created_at, actor_kind, path, status, user_id, actor_name)
               VALUES (?, 'owner', '/messages', 200, 0, '管理员')""",
            (app.now_text(),),
        )
        self.assertEqual(app.owner_status()["label"], "摸鱼中")
        self.assertEqual(app.owner_status()["tone"], "online")

        # 选当前设备后缀，胶囊里就只显示设备名
        owner.api_site_user_status_save(
            {"mode": "auto", "suffix": "Win", "text": ""}
        )
        self.assertEqual(app.owner_status()["label"], "Win")
        self.assertEqual(app.owner_status()["tone"], "online")

        # 隐身盖住在线（人在活跃窗口内才成立）
        owner.api_site_user_status_save({"mode": "invisible", "suffix": ""})
        self.assertEqual(app.owner_status()["label"], "隐身")
        self.assertEqual(app.owner_status()["tone"], "invisible")

        # 点「在线」只是取消隐身；没有后缀就只显示「在线」
        owner.api_site_user_status_save({"mode": "auto", "suffix": "", "text": ""})
        self.assertEqual(app.owner_status()["label"], "在线")

        # 隐身但到点没操作 = 真的离线，不会一直挂着隐身
        owner.api_site_user_status_save({"mode": "invisible", "suffix": ""})
        stale = (app.datetime.now() - app.timedelta(minutes=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.assertEqual(app.member_status(0, stale)["label"], "离线")
        self.assertEqual(app.member_status(0, stale)["tone"], "offline")
        # 重新登录后回到默认的「在线」
        app.reset_status_on_login(0)
        self.assertEqual(app.user_status_row(0)["mode"], "auto")
        self.assertEqual(app.member_status(0, app.now_text())["label"], "在线")

    def test_status_suffix_only_for_the_detected_device_and_expires_to_offline(self):
        """后缀只认当前设备那一项；「在线」不是手动固定，过了活跃窗口就自动变「离线」。"""
        self.assertEqual(
            app.device_suffix("Windows desktop", "Mozilla/5.0 (Windows NT 10.0)"), "Win"
        )
        self.assertEqual(app.device_suffix("macOS desktop", ""), "Mac")
        self.assertEqual(
            app.device_suffix("", "Mozilla/5.0 (X11; Linux x86_64) Firefox/120"), "Linux"
        )
        # 安卓 UA 里带 linux、iOS UA 里带 mac os x，都要认对
        self.assertEqual(
            app.device_suffix("", "Mozilla/5.0 (Linux; Android 14; Pixel 7) Mobile Safari"),
            "Android",
        )
        self.assertEqual(
            app.device_suffix("", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"),
            "iOS",
        )
        self.assertEqual(app.device_suffix("", "curl/8.0"), "")

        # 后缀只接受设备名（大小写不敏感），旧的 WIFI / 5G 认不出就当没选
        self.assertEqual(app.user_status_save(self.author_id, "auto", "win")["suffix"], "Win")
        self.assertEqual(app.user_status_save(self.author_id, "auto", "WIFI")["suffix"], "")
        self.assertEqual(app.user_status_save(self.author_id, "auto", "5G")["suffix"], "")
        app.user_status_save(self.author_id, "auto", "Win")

        # 窗口内活跃 -> 胶囊里显示设备名
        self.assertEqual(
            app.member_status(self.author_id, app.now_text())["label"], "Win"
        )
        # 超过窗口没有活跃 -> 自动变离线，不需要本人再点一次
        stale = (app.datetime.now() - app.timedelta(minutes=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.assertEqual(app.member_status(self.author_id, stale)["label"], "离线")

    def test_member_status_is_self_only_and_guests_see_masked_users(self):
        """普通账号只能改自己的状态、写不了自定义文案；游客看到的是脱敏列表且没有状态。"""
        # 先在站内有访问记录（人确实在线），隐身才成立
        app.execute(
            """INSERT INTO access_log
                   (created_at, actor_kind, path, status, user_id, actor_name)
               VALUES (?, 'member', '/messages', 200, ?, '作者甲')""",
            (app.now_text(), self.author_id),
        )
        member, responses = self.make_handler(self.author_id, username="author1")
        member.api_site_user_status_save(
            {"mode": "invisible", "suffix": "Android", "text": "偷偷摸鱼"}
        )
        self.assertEqual(responses[-1][0], 200)
        self.assertEqual(responses[-1][1]["presence"]["label"], "隐身")
        # 普通账号没有自定义权限，提交的文案被忽略
        self.assertEqual(app.user_status_row(self.author_id)["text"], "")

        users = app.sidebar_users(self.author_id)
        rows = {item["id"]: item for item in users["items"]}
        self.assertTrue(rows[self.author_id]["self"])
        self.assertFalse(rows[self.other_id]["self"])
        self.assertEqual(rows[self.author_id]["presence"]["label"], "隐身")
        self.assertEqual(rows[self.other_id]["presence"]["label"], "离线")

        # 隐身给本人和管理员看，普通账号看到的一律是「离线」，接口里也翻不出隐身
        others = app.sidebar_users(self.other_id)
        other_rows = {item["id"]: item for item in others["items"]}
        invisible_row = other_rows[self.author_id]["presence"]
        self.assertEqual(invisible_row["label"], "离线")
        self.assertEqual(invisible_row["tone"], "offline")
        self.assertEqual(invisible_row["mode"], "auto")
        # 管理员看得到别人真实的橘色「隐身」
        admin_rows = {
            item["id"]: item
            for item in app.sidebar_users(viewer_is_admin=True)["items"]
        }
        self.assertEqual(admin_rows[self.author_id]["presence"]["label"], "隐身")
        self.assertEqual(admin_rows[self.author_id]["presence"]["tone"], "invisible")
        # 站长设隐身时（且在活跃窗口内），访客看到的 Error酱 也是「离线」，
        # 站长自己看才是「隐身」；站长离开活跃窗口后对谁都是「离线」
        app.execute(
            """INSERT INTO access_log
                   (created_at, actor_kind, path, status, user_id, actor_name)
               VALUES (?, 'owner', '/messages', 200, 0, '管理员')""",
            (app.now_text(),),
        )
        app.user_status_save(0, "invisible", "", None)
        self.assertEqual(app.owner_status_for(True)["label"], "隐身")
        self.assertEqual(app.owner_status_for(False)["label"], "离线")
        app.execute("DELETE FROM access_log WHERE actor_kind = 'owner'")
        self.assertEqual(app.owner_status_for(True)["label"], "离线")
        app.user_status_save(0, "auto", "", None)

        # 游客：用户名脱敏、只给脱敏名字，不下发任何人的状态、也不给注册 / 活跃时间
        guests = app.sidebar_users(masked=True)
        self.assertEqual(guests["scope"], "masked")
        self.assertTrue(guests["items"])
        for item in guests["items"]:
            self.assertTrue(item["masked"])
            self.assertNotIn("presence", item)
            self.assertNotIn("registered_days", item)
            self.assertNotIn("last_view_at", item)
            self.assertTrue(item["name"].startswith("*"))

        # 未通过审核的账号不进这张卡
        stamp = app.now_text()
        pending_id = app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', 'member', ?, ?)""",
            ("pending9", "待审核的", "hash", stamp, stamp),
        )
        after = app.sidebar_users(masked=True)
        self.assertNotIn(pending_id, [item.get("id") for item in after["items"]])
        admin_after = app.sidebar_users(viewer_is_admin=True)
        self.assertNotIn(pending_id, [item["id"] for item in admin_after["items"]])

        # 游客不能设置状态
        guest = object.__new__(app.InventoryHandler)
        guest.session_identity = lambda: None
        guest_responses = []
        guest.send_json = lambda status, payload: guest_responses.append((status, payload))
        guest.api_site_user_status_save({"mode": "auto"})
        self.assertEqual(guest_responses[-1][0], 401)

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
        expected = app.PUBLIC_ACTIVITY_LABELS["moment_create"]
        matching = [item for item in items if item.get("text") == expected]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["alert"])
        self.assertFalse(any(item.get("id") == "notify-moments" for item in items))

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
        # 提醒落在「新回复」这条评论上（带着评论 id 才能精确高亮 / 定位）
        self.assertEqual(
            int(notifications[0]["target_id"]), int(responses[-1][1]["id"])
        )

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

    def test_guest_sees_moments_comments_with_masked_names(self):
        """游客能看动态正文和评论 / 回复，但普通账号的名字只保留最后一个字。"""
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        comment_id = app.execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, NULL, ?, ?, ?, ?)""",
            (moment_id, self.other_id, "评论乙", "给游客看的评论", stamp),
        )
        app.execute(
            """INSERT INTO moment_comments
                   (moment_id, parent_id, user_id, actor, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (moment_id, comment_id, self.author_id, "作者甲", "给游客看的回复", stamp),
        )
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "moment", "target_id": moment_id}
        )
        guest = object.__new__(app.InventoryHandler)
        guest.session_identity = lambda: None
        guest.is_admin = lambda: False
        responses = []
        guest.send_json = lambda status, payload: responses.append((status, payload))
        guest.api_moments({})
        payload = responses[-1][1]
        self.assertIsInstance(payload, list)
        target = [row for row in payload if int(row["id"]) == moment_id][0]
        self.assertEqual(target["content"], "动态内容")
        # 点赞者名字只保留最后一个字
        self.assertEqual(target["like_users"], [app.mask_username("other1")])
        self.assertEqual(target["comment_count"], 2)
        comments = {int(row["id"]): row for row in target["comments"]}
        self.assertEqual(comments[comment_id]["content"], "给游客看的评论")
        self.assertEqual(comments[comment_id]["actor"], app.mask_username("评论乙"))
        reply = [row for row in target["comments"] if int(row["id"]) != comment_id][0]
        self.assertEqual(reply["content"], "给游客看的回复")
        # 脱敏后的名字不能再从响应里还原出原文
        self.assertEqual(reply["actor"], app.mask_username("作者甲"))
        self.assertNotIn("评论乙", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("作者甲", json.dumps(payload, ensure_ascii=False))

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

        author_handler, author_responses = self.make_handler(
            self.author_id, username="author1"
        )
        author_handler.api_moment_comment_create(
            moment_id, {"content": "回复这条评论", "parent_id": parent_id}
        )
        reply_id = int(author_responses[-1][1]["id"])
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
        # 两条提醒分别指向两条评论；target_kinds 用来区分「动态本体」和「评论」
        self.assertEqual(payload["targets"], [parent_id, reply_id])
        self.assertEqual(
            payload["target_kinds"],
            {str(parent_id): "moment_comment", str(reply_id): "moment_comment"},
        )

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

    def test_guest_sees_message_replies_with_masked_names(self):
        """游客能看留言正文和回复，但普通账号的名字只保留最后一个字。"""
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        reply_handler, _ = self.make_handler(self.author_id, username="author1")
        reply_handler.api_site_message_create(
            {"content": "给游客看的回复", "parent_id": self.message_id, "files": []}
        )
        guest = object.__new__(app.InventoryHandler)
        guest.session_identity = lambda: None
        guest.is_admin = lambda: False
        responses = []
        guest.send_json = lambda status, payload: responses.append((status, payload))
        guest.api_site_messages({})
        roots = responses[-1][1]
        target = [row for row in roots if int(row["id"]) == self.message_id][0]
        self.assertEqual(target["content"], "测试留言")
        self.assertEqual(target["nickname"], app.mask_username("author1"))
        self.assertEqual(target["like_users"], [app.mask_username("other1")])
        self.assertEqual(len(target["replies"]), 1)
        self.assertEqual(target["replies"][0]["content"], "给游客看的回复")
        self.assertEqual(
            target["replies"][0]["nickname"], app.mask_username("author1")
        )
        # 脱敏后的名字不能再从响应里还原出原文
        self.assertNotIn("author1", json.dumps(roots, ensure_ascii=False))

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

    def test_map_interaction_feature_is_offline(self):
        """标记点的点赞 / 打卡整体下线：接口与互动字段都不再存在。"""
        self.assertFalse(hasattr(app.InventoryHandler, "api_map_place_interact"))
        self.assertNotIn(
            "map_interaction", {item["key"] for item in app.NOTIFY_EVENTS}
        )

    def test_map_api_hides_interaction_state(self):
        """历史互动行与未读提醒留在库里，但接口不再下发互动字段。"""
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
        for field in ("like_count", "checkin_count", "liked", "checked_in"):
            self.assertNotIn(field, target)
        self.assertTrue(target["fresh"])
        self.assertEqual(payload["notify_targets"], [place_id])

        owner_handler, owner_responses = self.make_handler(0, kind="owner")
        owner_handler.api_map_mark_seen({"notify_targets": [place_id]})
        owner_handler.api_site_activity()
        items = owner_responses[-1][1]["items"]
        self.assertFalse(
            any(item.get("id") == "notify-map" for item in items)
        )

    def test_admin_map_place_create_skips_webhook(self):
        """站长在足迹页新增标记不推 Webhook；普通账号（默认有 map:write）新增照旧推。"""
        payload = {
            "name": "站长加的标记",
            "lat": 34.34,
            "lng": 108.94,
            "address": "测试路 1 号",
        }
        calls = []
        owner, owner_responses = self.make_handler(0, kind="owner", username="owner")
        member, member_responses = self.make_handler(self.author_id, username="author1")
        with patch.object(app, "notify_async", lambda *args, **kwargs: calls.append(args)):
            owner.api_map_place_create(dict(payload))
            self.assertEqual(owner_responses[-1][0], 201)
            self.assertEqual(calls, [])

            member.api_map_place_create(dict(payload, name="普通账号加的标记"))
            self.assertEqual(member_responses[-1][0], 201)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "place")

    def test_deleting_place_cleans_interactions_and_notifications(self):
        stamp = app.now_text()
        place_id = app.execute(
            """INSERT INTO map_places
                   (name, lat, lng, created_by, created_at, updated_at)
               VALUES (?, ?, ?, 0, ?, ?)""",
            ("待删除标记", 34.34, 108.94, stamp, stamp),
        )
        app.execute(
            """INSERT INTO map_place_interactions (place_id, user_id, kind, created_at)
               VALUES (?, ?, 'like', ?)""",
            (place_id, self.author_id, stamp),
        )
        app.add_user_notification(
            0, "place_like", "map", place_id, "作者甲", "作者甲 点赞了你的标记点"
        )
        handler, responses = self.make_handler(0, kind="owner", username="owner")
        handler.command = "DELETE"
        handler.api_map_place_item(f"/api/map/places/{place_id}")
        self.assertTrue(responses[-1][1]["ok"])
        self.assertEqual(
            app.query_one(
                "SELECT COUNT(*) AS n FROM map_place_interactions WHERE place_id = ?",
                (place_id,),
            )["n"],
            0,
        )
        self.assertEqual(
            app.query_one(
                """SELECT COUNT(*) AS n FROM user_notifications
                   WHERE module = 'map' AND target_id = ?""",
                (place_id,),
            )["n"],
            0,
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

    def test_moment_notification_reuses_public_activity_row(self):
        stamp = app.now_text()
        moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("通知去重测试", stamp),
        )
        app.write_activity(
            {"kind": "owner", "user_id": 0, "username": "管理员"},
            "moment_create",
            "发布动态：通知去重测试",
            target_type="moment",
            target_id=moment_id,
        )
        app.add_user_notification(
            self.author_id,
            "moment_new",
            "moments",
            moment_id,
            "管理员",
            "更新了动态",
        )
        handler, responses = self.make_handler(self.author_id, username="author1")
        handler.api_site_activity()
        items = responses[-1][1]["items"]
        matching = [item for item in items if item.get("text") == "更新了一条动态"]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["alert"])
        self.assertEqual(
            len([item for item in items if item.get("alert")]),
            1,
        )

        app.mark_notifications_seen(self.author_id, "moments")
        handler.api_site_activity()
        items = responses[-1][1]["items"]
        matching = [item for item in items if item.get("text") == "更新了一条动态"]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0]["alert"])
        self.assertFalse(any(item.get("alert") for item in items))

    def test_message_reply_notification_reuses_public_activity_row(self):
        handler, responses = self.make_handler(self.other_id, username="other1")
        handler.api_site_message_create(
            {"content": "回复内容", "parent_id": self.message_id, "files": []}
        )
        reply_id = responses[-1][1]["id"]
        app.write_activity(
            {"kind": "member", "user_id": self.other_id, "username": "other1"},
            "message_reply",
            "回复留言：回复内容",
            target_type="message",
            target_id=reply_id,
        )
        notification = app.query_one(
            """SELECT target_id FROM user_notifications
               WHERE user_id = ? AND kind = 'message_reply'""",
            (self.author_id,),
        )
        self.assertEqual(int(notification["target_id"]), int(reply_id))

        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_activity()
        items = member_responses[-1][1]["items"]
        matching = [
            item
            for item in items
            if item.get("text") == app.PUBLIC_ACTIVITY_LABELS["message_reply"]
        ]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["alert"])
        self.assertFalse(any(item.get("id") == "notify-messages" for item in items))

        app.mark_notifications_seen(self.author_id, "messages")
        member_handler.api_site_activity()
        items = member_responses[-1][1]["items"]
        matching = [
            item
            for item in items
            if item.get("text") == app.PUBLIC_ACTIVITY_LABELS["message_reply"]
        ]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0]["alert"])

    def test_message_like_does_not_mark_public_message_row(self):
        app.write_activity(
            {"kind": "member", "user_id": self.author_id, "username": "author1"},
            "message_create",
            "发布留言：测试留言",
            target_type="message",
            target_id=self.message_id,
        )
        handler, _ = self.make_handler(self.other_id, username="other1")
        handler.api_site_like_toggle(
            {"target_type": "message", "target_id": self.message_id}
        )
        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_activity()
        items = member_responses[-1][1]["items"]
        public_rows = [
            item
            for item in items
            if item.get("text") == app.PUBLIC_ACTIVITY_LABELS["message_create"]
        ]
        self.assertEqual(len(public_rows), 1)
        self.assertFalse(public_rows[0]["alert"])
        alerts = [item for item in items if item.get("id") == "notify-messages"]
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["alert"])

    def test_new_content_notifies_members_and_clears_summary(self):
        handler, responses = self.make_handler(0, kind="owner", username="owner")
        handler.api_site_music_upload(
            {
                "title": "测试歌曲",
                "artist": "测试歌手",
                "file_name": "test.mp3",
                "data_base64": base64.b64encode(b"ID3" + b"\x00" * 64).decode(
                    "ascii"
                ),
            }
        )
        music_id = responses[-1][1]["id"]
        handler.api_book_upload(
            {
                "title": "测试书籍",
                "author": "测试作者",
                "file_name": "test.txt",
                "data_base64": base64.b64encode(b"test book content").decode(
                    "ascii"
                ),
            }
        )
        book_id = responses[-1][1]["id"]
        handler.api_recommendation_create(
            {"kind": "movie", "title": "测试推荐"}
        )
        recommendation_id = responses[-1][1]["id"]

        rows = app.query(
            """SELECT user_id, kind, module, target_id
               FROM user_notifications
               WHERE kind IN ('music_new', 'book_new', 'recommendation_new')
               ORDER BY user_id, kind"""
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {
                (
                    int(row["user_id"]),
                    str(row["kind"]),
                    str(row["module"]),
                    int(row["target_id"]),
                )
                for row in rows
            },
            {
                (self.author_id, "music_new", "music", music_id),
                (self.other_id, "music_new", "music", music_id),
                (self.author_id, "book_new", "books", book_id),
                (self.other_id, "book_new", "books", book_id),
                (
                    self.author_id,
                    "recommendation_new",
                    "recommendations",
                    recommendation_id,
                ),
                (
                    self.other_id,
                    "recommendation_new",
                    "recommendations",
                    recommendation_id,
                ),
            },
        )

        member_handler, member_responses = self.make_handler(
            self.author_id, username="author1"
        )
        member_handler.api_site_notification_summary()
        summary = member_responses[-1][1]
        self.assertEqual(summary["music"], 1)
        self.assertEqual(summary["books"], 1)
        self.assertEqual(summary["recommendations"], 1)

        member_handler.api_site_notification_unread({"module": ["music"]})
        self.assertEqual(member_responses[-1][1]["targets"], [music_id])
        member_handler.api_site_notification_unread({"module": ["books"]})
        self.assertEqual(member_responses[-1][1]["targets"], [book_id])
        member_handler.api_site_notification_unread(
            {"module": ["recommendations"]}
        )
        self.assertEqual(
            member_responses[-1][1]["targets"], [recommendation_id]
        )

        member_handler.api_site_notifications_seen({"module": "music"})
        member_handler.api_site_notification_summary()
        summary = member_responses[-1][1]
        self.assertEqual(summary["music"], 0)
        self.assertEqual(summary["books"], 1)
        self.assertEqual(summary["recommendations"], 1)

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

    def test_guest_activity_is_not_returned(self):
        """游客看不到首页左下角动态区：接口直接返回空，不泄露任何动态。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                app.write_activity(
                    {"kind": "owner", "user_id": 0, "username": "管理员"},
                    "moment_create",
                    "发布动态：不应公开的正文",
                    target_type="moment",
                    target_id=1,
                )
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: None
                handler.is_admin = lambda: False
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.api_site_activity()
                payload = responses[0][1]
                self.assertEqual(payload["items"], [])
                self.assertFalse(payload["signed_in"])
                self.assertFalse(payload["admin"])

    def test_member_activity_reports_signed_in(self):
        """登录账号的接口带上身份标记，前端据此决定默认只看未读提醒。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: {
                    "kind": "member",
                    "user_id": 1,
                    "username": "member1",
                    "nickname": "member1",
                }
                handler.is_admin = lambda: False
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.api_site_activity()
                payload = responses[-1][1]
                self.assertTrue(payload["signed_in"])
                self.assertFalse(payload["admin"])

    def test_map_alert_survives_log_truncation(self):
        """公开动态超过 60 条时，历史遗留的地图提醒也必须返回给本人。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                for _ in range(70):
                    app.write_activity(
                        {"kind": "owner", "user_id": 0, "username": "管理员"},
                        "music_upload",
                        "上传了一首歌",
                        target_type="music",
                    )
                app.add_user_notification(
                    2, "place_like", "map", 999, "牛大能", "牛大能 点赞了你的标记点"
                )
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: {
                    "kind": "member",
                    "user_id": 2,
                    "username": "member2",
                    "nickname": "member2",
                }
                handler.is_admin = lambda: False
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.api_site_activity()
                payload = responses[-1][1]
                self.assertLessEqual(len(payload["items"]), 60)
                alerts = [item for item in payload["items"] if item.get("alert")]
                self.assertTrue(any(item.get("id") == "notify-map" for item in alerts))
                matching = [
                    item
                    for item in alerts
                    if item.get("text") == "牛大能 点赞了你的标记点"
                ]
                self.assertEqual(len(matching), 1)

    def test_admin_alert_survives_log_truncation(self):
        """管理员的待办提醒同样不能被日志截断。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                for _ in range(70):
                    app.write_activity(
                        {"kind": "owner", "user_id": 0, "username": "管理员"},
                        "music_upload",
                        "上传了一首歌",
                        target_type="music",
                    )
                stamp = app.now_text()
                app.execute(
                    """INSERT INTO users
                           (username, nickname, password_hash, status, role,
                            created_at, updated_at)
                       VALUES (?, ?, ?, 'pending', 'member', ?, ?)""",
                    ("pending9", "待审", "hash", stamp, stamp),
                )
                handler = object.__new__(app.InventoryHandler)
                handler.session_identity = lambda: {
                    "kind": "owner",
                    "user_id": 0,
                    "username": "owner",
                    "nickname": "owner",
                }
                handler.is_admin = lambda: True
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.api_site_activity()
                payload = responses[-1][1]
                self.assertLessEqual(len(payload["items"]), 60)
                self.assertTrue(
                    any(
                        item.get("id") == "pending-user-alert"
                        for item in payload["items"]
                    )
                )


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


class ComplianceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self._db_patch = patch.object(
            app, "DB_PATH", Path(self._temp.name) / "inventory.db"
        )
        self._db_patch.start()
        app.RATE_LIMITS.clear()
        app.init_db()
        stamp = app.now_text()
        self.member_id = app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role,
                    created_at, updated_at)
               VALUES (?, ?, ?, 'approved', 'member', ?, ?)""",
            ("member1", "用户甲", "hash", stamp, stamp),
        )
        self.other_id = app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role,
                    created_at, updated_at)
               VALUES (?, ?, ?, 'approved', 'member', ?, ?)""",
            ("member2", "用户乙", "hash", stamp, stamp),
        )
        self.message_id = app.execute(
            """INSERT INTO site_messages
                   (nickname, content, user_id, status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            ("用户甲", "待审核留言", self.member_id, stamp),
        )
        self.moment_id = app.execute(
            "INSERT INTO moments (content, created_at) VALUES (?, ?)",
            ("动态内容", stamp),
        )
        self.music_id = app.execute(
            """INSERT INTO site_music
                   (title, artist, source_type, source_id, sort_order, created_at)
               VALUES (?, ?, 'url', ?, 0, ?)""",
            ("测试歌曲", "歌手", "https://example.com/test.mp3", stamp),
        )
        self.book_id = app.execute(
            """INSERT INTO books
                   (title, author, format, file_path, sort_order, created_at, updated_at)
               VALUES (?, ?, 'txt', ?, 0, ?, ?)""",
            ("测试书", "作者", "book_files/test.txt", stamp, stamp),
        )
        self.recommendation_id = app.execute(
            """INSERT INTO recommendations
                   (kind, title, url, created_at, updated_at)
               VALUES ('site', ?, ?, ?, ?)""",
            ("测试推荐", "https://example.com/tool", stamp, stamp),
        )

    def tearDown(self):
        self._db_patch.stop()
        self._temp.cleanup()

    def make_handler(self, identity, admin=False, method="GET"):
        handler = object.__new__(app.InventoryHandler)
        handler.command = method
        handler.headers = {"User-Agent": "test", "Host": "example.test"}
        handler.client_address = ("127.0.0.1", 12345)
        handler.session_identity = lambda: identity
        handler.is_admin = lambda: admin
        handler.client_ip = lambda: "127.0.0.1"
        handler.client_port = lambda: 12345
        handler.target_endpoint = lambda: ("example.test", 443)
        handler.client_platform = lambda: "test"
        handler.responses = []
        handler.send_json = lambda status, payload: handler.responses.append(
            (status, payload)
        )
        handler.log_activity = lambda *args, **kwargs: None
        return handler

    def member(self, user_id):
        return {
            "kind": "member",
            "user_id": user_id,
            "username": f"member{user_id}",
            "nickname": f"用户{user_id}",
        }

    def test_message_review_controls_visibility_and_keeps_publish_time(self):
        author = self.make_handler(self.member(self.member_id))
        author.api_site_messages({})
        author_rows = author.responses[-1][1]
        self.assertEqual(len(author_rows), 1)
        published_at = author_rows[0]["created_at"]
        self.assertTrue(author_rows[0]["pending_review"])

        other = self.make_handler(self.member(self.other_id))
        other.api_site_messages({})
        self.assertEqual(other.responses[-1][1], [])

        guest = self.make_handler(None)
        guest.api_site_messages({})
        # 待审的留言对游客也一样不显示
        self.assertEqual(guest.responses[-1][1], [])

        admin = self.make_handler(
            {"kind": "owner", "user_id": 0, "nickname": "管理员"},
            admin=True,
            method="POST",
        )
        admin.api_admin_review_action(
            f"/api/admin/review/{self.message_id}", {"action": "approve"}
        )
        self.assertEqual(admin.responses[-1][1]["status"], "approved")
        other.api_site_messages({})
        visible = other.responses[-1][1]
        self.assertEqual(visible[0]["id"], self.message_id)
        self.assertEqual(visible[0]["created_at"], published_at)
        self.assertFalse(visible[0]["pending_review"])
        self.assertNotIn("reviewed_at", visible[0])

    def test_guest_content_endpoints_hide_actionable_data(self):
        guest = self.make_handler(None)
        guest.api_site_music({})
        music = guest.responses[-1][1][0]
        self.assertEqual(music["url"], "")
        self.assertTrue(music["requires_login"])

        guest.api_books({})
        book = guest.responses[-1][1][0]
        self.assertNotIn("file_url", book)
        self.assertTrue(book["requires_login"])

        guest.api_recommendations({})
        recommendation = guest.responses[-1][1]["items"][0]
        # 网页 / 工具对游客开放点击访问，所以地址照常返回
        self.assertEqual(recommendation["url"], "https://example.com/tool")
        self.assertTrue(recommendation["requires_login"])

        guest.api_moments({})
        moments = guest.responses[-1][1]
        # 动态对游客整体开放：正文、评论 / 回复都照常返回（名字脱敏）
        self.assertIsInstance(moments, list)
        moment = [row for row in moments if int(row["id"]) == self.moment_id][0]
        self.assertEqual(moment["content"], "动态内容")

        guest.api_site_music_stream(self.music_id)
        self.assertEqual(guest.responses[-1][0], 401)
        self.assertFalse(guest.guest_request_allowed("/games/2048", "GET", None))

    def test_reports_are_open_to_guests_for_every_public_content_type(self):
        """留言 / 动态 / 歌曲 / 书籍 / 推荐内容的举报都对游客开放，不再要求登录。"""
        approved_message_id = app.execute(
            """INSERT INTO site_messages
                   (nickname, content, status, created_at)
               VALUES ('游客', '公开留言', 'approved', ?)""",
            (app.now_text(),),
        )
        guest = self.make_handler(None, method="POST")
        with patch.object(app, "notify_async", return_value=False):
            for target_type, target_key, reason in (
                ("book", self.book_id, "侵权或隐私"),
                ("recommendation", self.recommendation_id, "诈骗广告"),
                ("music", self.music_id, "侵权或隐私"),
                ("moment", self.moment_id, "违法违规"),
                ("message", approved_message_id, "违法违规"),
            ):
                guest.api_site_report_create(
                    {
                        "target_type": target_type,
                        "target_key": str(target_key),
                        "reason": reason,
                    }
                )
        statuses = [guest.responses[-offset][0] for offset in range(5, 0, -1)]
        self.assertEqual(statuses, [200] * 5)
        self.assertEqual(
            app.query_one("SELECT COUNT(*) AS n FROM content_reports")["n"], 5
        )
        # 待审留言依然不能举报：这是「对象不合法」，和登不登录无关
        guest.api_site_report_create(
            {
                "target_type": "message",
                "target_key": str(self.message_id),
                "reason": "违法违规",
            }
        )
        self.assertEqual(guest.responses[-1][0], 400)

    def test_log_retention_default_is_six_months(self):
        self.assertEqual(app.LOG_RETENTION_DAYS, 180)

    def test_device_info_label_and_normalize(self):
        """UA 自动识别只认系统：鸿蒙 / Android / iOS 优先，其次 ChromeOS / Windows / macOS / Linux。"""
        windows = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"
        android = "Mozilla/5.0 (Linux; Android 14; Pixel 7) Mobile Safari/537.36"
        iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
        ipad_new = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
        )
        mac = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
        )
        linux = "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0"
        chromeos = (
            "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        )
        # 鸿蒙 4.x 及以下的 UA 里同时带 Android，必须优先判成鸿蒙
        harmony4 = (
            "Mozilla/5.0 (Linux; Android 12; HarmonyOS; ALN-AL80; HMSCore 6.12.0.302) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.88 "
            "HuaweiBrowser/14.0.5.302 Mobile Safari/537.36"
        )
        open_harmony = (
            "Mozilla/5.0 (Phone; OpenHarmony 5.0) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36 ArkWeb/4.1.6.1 Mobile"
        )
        self.assertEqual(app.device_info_label(windows), "来自 Windows")
        self.assertEqual(app.device_info_label(android), "来自 Android")
        self.assertEqual(app.device_info_label(iphone), "来自 iOS")
        self.assertEqual(app.device_info_label(ipad_new), "来自 iOS")
        self.assertEqual(app.device_info_label(mac), "来自 macOS")
        self.assertEqual(app.device_info_label(linux), "来自 Linux")
        self.assertEqual(app.device_info_label(chromeos), "来自 ChromeOS")
        self.assertEqual(app.device_info_label(harmony4), "来自 鸿蒙")
        self.assertEqual(app.device_info_label(open_harmony), "来自 鸿蒙")
        self.assertEqual(app.device_info_label("harmonyos"), "来自 鸿蒙")
        self.assertEqual(app.device_info_label(""), "来自 Web")

        # 管理员自定义：补「来自 」前缀、压掉换行与多余空格、超长截断
        self.assertEqual(app.normalize_device_info("iQOO 12 Pro"), "来自 iQOO 12 Pro")
        self.assertEqual(app.normalize_device_info("  来自 iOS\n"), "来自 iOS")
        self.assertEqual(app.normalize_device_info("iPad\nPro"), "来自 iPad Pro")
        self.assertEqual(app.normalize_device_info(""), "")
        self.assertEqual(
            len(app.normalize_device_info("X" * 80)), app.DEVICE_INFO_MAX_CHARS
        )

    @patch.object(app, "rate_allow", return_value=True)
    def test_message_device_info_auto_for_members_and_custom_for_admin(self, _rate):
        """
        留言的设备平台：默认不公开（落空串），勾了 show_device 才按 UA 自动识别；
        普通账号伪造 device_info 会被忽略，只有管理员能用自定义名称。
        """
        auto = self.make_handler(self.member(self.member_id), method="POST")
        with patch.object(app, "notify_async", return_value=False):
            # 没勾「设备平台」→ 不公开，落空串
            auto.api_site_message_create({"content": "会员未公开", "files": []})
            # 勾了「设备平台」→ 按 UA 自动识别（测试里的 UA 是 test → 来自 Web）
            auto.api_site_message_create(
                {"content": "会员留言", "files": [], "show_device": True}
            )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM site_messages WHERE content = ?",
                ("会员未公开",),
            )["device_info"],
            "",
        )
        row = app.query_one(
            "SELECT device_info FROM site_messages WHERE content = ?", ("会员留言",)
        )
        self.assertEqual(row["device_info"], "来自 Web")

        forged = self.make_handler(self.member(self.other_id), method="POST")
        with patch.object(app, "notify_async", return_value=False):
            forged.api_site_message_create(
                {
                    "content": "伪造设备",
                    "files": [],
                    "show_device": True,
                    "device_info": "iQOO 12 Pro",
                }
            )
        row = app.query_one(
            "SELECT device_info FROM site_messages WHERE content = ?", ("伪造设备",)
        )
        self.assertEqual(row["device_info"], "来自 Web")

        admin_identity = {"kind": "owner", "user_id": 0, "nickname": "管理员"}
        admin = self.make_handler(admin_identity, admin=True, method="POST")
        with patch.object(app, "notify_async", return_value=False):
            admin.api_site_message_create(
                {
                    "content": "管理员留言",
                    "files": [],
                    "show_device": True,
                    "device_info": "iQOO 12 Pro",
                }
            )
            # 填了自定义名称但只有空格 → 退回自动识别
            admin.api_site_message_create(
                {
                    "content": "管理员留空",
                    "files": [],
                    "show_device": True,
                    "device_info": "   ",
                }
            )
            # 没勾「设备平台」：自定义名称也不公开
            admin.api_site_message_create(
                {
                    "content": "管理员未公开",
                    "files": [],
                    "device_info": "iQOO 12 Pro",
                }
            )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM site_messages WHERE content = ?",
                ("管理员留言",),
            )["device_info"],
            "来自 iQOO 12 Pro",
        )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM site_messages WHERE content = ?",
                ("管理员留空",),
            )["device_info"],
            "来自 Web",
        )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM site_messages WHERE content = ?",
                ("管理员未公开",),
            )["device_info"],
            "",
        )

        # 列表接口把设备信息一起下发给前端
        board = self.make_handler(admin_identity, admin=True)
        board.api_site_messages({})
        rows = board.responses[-1][1]
        target = [row for row in rows if row["content"] == "管理员留言"][0]
        self.assertEqual(target["device_info"], "来自 iQOO 12 Pro")
        auto_row = [row for row in rows if row["content"] == "伪造设备"][0]
        self.assertEqual(auto_row["device_info"], "来自 Web")

    @patch.object(app, "rate_allow", return_value=True)
    def test_custom_device_name_permission_can_be_granted(self, _rate):
        """「自定义设备平台名称」是账号权限里的一项：开了就能填，没开只能用自动识别。"""
        self.assertIn("site:device_name", app.PERMISSION_LABELS)
        self.assertIn("site:device_name", app.GRANTABLE_PERMISSIONS)
        # 可以整批授予「普通账户」这个角色，但默认不发给任何人
        self.assertIn("site:device_name", app.MEMBER_ROLE_PERMISSIONS)
        self.assertNotIn("site:device_name", app.DEFAULT_MEMBER_PERMISSIONS)

        without = self.make_handler(self.member(self.member_id), method="POST")
        with patch.object(app, "notify_async", return_value=False):
            without.api_site_message_create(
                {
                    "content": "没权限",
                    "files": [],
                    "show_device": True,
                    "device_info": "iQOO 12 Pro",
                }
            )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM site_messages WHERE content = ?",
                ("没权限",),
            )["device_info"],
            "来自 Web",
        )

        # 单独给这个账号开放权限
        app.execute(
            """INSERT INTO user_permissions (user_id, permission, mode, granted_by, granted_at)
               VALUES (?, ?, 'allow', 'owner', ?)""",
            (self.other_id, "site:device_name", app.now_text()),
        )
        granted = self.make_handler(self.member(self.other_id), method="POST")
        with patch.object(app, "notify_async", return_value=False):
            granted.api_site_message_create(
                {
                    "content": "有权限",
                    "files": [],
                    "show_device": True,
                    "device_info": "iQOO 12 Pro",
                }
            )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM site_messages WHERE content = ?",
                ("有权限",),
            )["device_info"],
            "来自 iQOO 12 Pro",
        )

    def test_moment_device_info_requires_admin_and_survives_other_edits(self):
        """
        动态的设备平台：默认不公开；public 开关 + 管理员自定义名称；不带这两个字段的编辑
        （例如置顶）不会覆盖原值。
        """
        admin_identity = {"kind": "owner", "user_id": 0, "nickname": "管理员"}
        member = self.make_handler(self.member(self.member_id), method="POST")
        with patch.object(app, "notify_async", return_value=False):
            member.api_moment_create(
                {
                    "content": "会员动态",
                    "images": [],
                    "show_device": True,
                    "device_info": "iQOO 12 Pro",
                }
            )
            member.api_moment_create({"content": "会员未公开", "images": []})
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM moments WHERE content = ?", ("会员动态",)
            )["device_info"],
            "来自 Web",
        )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM moments WHERE content = ?", ("会员未公开",)
            )["device_info"],
            "",
        )

        admin = self.make_handler(admin_identity, admin=True, method="POST")
        with patch.object(app, "notify_async", return_value=False):
            admin.api_moment_create(
                {
                    "content": "管理员动态",
                    "images": [],
                    "show_device": True,
                    "device_info": "iQOO 12 Pro",
                }
            )
        moment_id = int(
            app.query_one(
                "SELECT id FROM moments WHERE content = ?", ("管理员动态",)
            )["id"]
        )
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM moments WHERE id = ?", (moment_id,)
            )["device_info"],
            "来自 iQOO 12 Pro",
        )

        def patch_moment(payload):
            editor = self.make_handler(admin_identity, admin=True, method="PATCH")
            with patch.object(app, "get_payload", return_value=payload):
                editor.api_moment_item(f"/api/moments/{moment_id}")
            self.assertEqual(editor.responses[-1][0], 200)

        # 只改置顶：payload 里没有 device_info，自定义名称保持不变
        patch_moment({"content": "管理员动态", "pinned": True})
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM moments WHERE id = ?", (moment_id,)
            )["device_info"],
            "来自 iQOO 12 Pro",
        )
        # 编辑表单明确留空自定义名称 → 回到自动识别
        patch_moment({"content": "管理员动态", "show_device": True, "device_info": ""})
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM moments WHERE id = ?", (moment_id,)
            )["device_info"],
            "来自 Web",
        )
        # 关掉「设备平台」→ 不再公开（落空串）
        patch_moment({"content": "管理员动态", "show_device": False})
        self.assertEqual(
            app.query_one(
                "SELECT device_info FROM moments WHERE id = ?", (moment_id,)
            )["device_info"],
            "",
        )

        board = self.make_handler(self.member(self.member_id))
        board.api_moments({})
        rows = board.responses[-1][1]
        target = [row for row in rows if int(row["id"]) == moment_id][0]
        self.assertEqual(target["device_info"], "")

    def test_recommendation_badges_split_between_web_and_resource(self):
        """推荐提醒按内容拆开：站内分享只算「站内」那一栏，点开一栏只清一栏。"""
        stamp = app.now_text()
        resource_recommendation_id = app.execute(
            """INSERT INTO recommendations
                   (kind, title, resource_type, resource_id, created_at, updated_at)
               VALUES ('resource', '分享的笔记', 'note', 1, ?, ?)""",
            (stamp, stamp),
        )
        app.add_user_notification(
            self.member_id,
            "recommendation_new",
            "recommendations",
            self.recommendation_id,
            "管理员",
            "新增了一条推荐",
        )
        app.add_user_notification(
            self.member_id,
            "recommendation_new",
            "recommendations",
            resource_recommendation_id,
            "管理员",
            "新增了一条推荐",
        )
        handler = self.make_handler(self.member(self.member_id))
        summary = handler.notification_summary()
        # 总数保持不变（首页「推荐」入口用的是它），另外两栏各算各的
        self.assertEqual(summary["recommendations"], 2)
        self.assertEqual(summary["recommendation_web"], 1)
        self.assertEqual(summary["recommendation_resource"], 1)

        # 点开「站内」：只清站内那一半，网页的角标留着
        handler.api_site_notifications_seen(
            {"module": "recommendations", "scope": "resource"}
        )
        self.assertEqual(handler.responses[-1][0], 200)
        summary = handler.notification_summary()
        self.assertEqual(summary["recommendation_resource"], 0)
        self.assertEqual(summary["recommendation_web"], 1)
        self.assertEqual(summary["recommendations"], 1)

        # 点开「网页」：清掉另一半
        handler.api_site_notifications_seen(
            {"module": "recommendations", "scope": "web"}
        )
        summary = handler.notification_summary()
        self.assertEqual(summary["recommendation_web"], 0)
        self.assertEqual(summary["recommendations"], 0)
        self.assertEqual(
            app.query_one(
                """SELECT COUNT(*) AS n FROM user_notifications
                   WHERE user_id = ? AND seen_at IS NULL""",
                (self.member_id,),
            )["n"],
            0,
        )

    def test_back_to_top_is_loaded_on_content_pages(self):
        pages = (
            "messages.html",
            "moments.html",
            "music.html",
            "books.html",
            "recommendations.html",
        )
        for page in pages:
            text = (app.STATIC_DIR / page).read_text(encoding="utf-8")
            self.assertIn("/static/site/back-to-top.js", text)
        script = (app.STATIC_DIR / "site" / "back-to-top.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("errorjumpvisibilitychange", script)
        self.assertIn(".site-back-top[hidden]", script)
        # 各页的全局 [hidden]{display:none !important} 会让按钮在隐藏时真的
        # display:none，Chrome 对 display:none 的元素不跑过渡，淡入淡出就没了
        self.assertIn("display:inline-flex!important", script)

    def test_fresh_notifications_use_visible_three_pulse_read_timing(self):
        pages = (
            "messages.html",
            "moments.html",
            "music.html",
            "books.html",
            "recommendations.html",
        )
        for page in pages:
            text = (app.STATIC_DIR / page).read_text(encoding="utf-8")
            self.assertIn("/static/site/fresh-visibility.js", text)
            self.assertNotIn("/static/site/notify-seen.js", text)
        script = (app.STATIC_DIR / "site" / "fresh-visibility.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("READ_PULSES = 3", script)
        self.assertIn("PULSE_MS = 3600", script)
        self.assertIn("errorj-recommend-visibility", script)

    def test_button_effect_layers_do_not_capture_label_text(self):
        script = (app.STATIC_DIR / "site" / "button-effects.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('layer = document.createElement("i")', script)
        self.assertIn('ripple = document.createElement("i")', script)
        css = (app.STATIC_DIR / "site" / "button-effects.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            ".fx-liquid-host > :not(.fx-liquid-layer):not(.fx-state-mark)",
            css,
        )
        page = (app.STATIC_DIR / "bookmarks.html").read_text(encoding="utf-8")
        self.assertIn('id="checkLinksLabel"', page)

    def test_report_modal_has_explicit_hidden_rule(self):
        css = (app.STATIC_DIR / "site" / "report.css").read_text(encoding="utf-8")
        self.assertIn(".er-report-overlay[hidden]", css)

    def test_routed_pages_do_not_use_native_dialogs(self):
        files = (
            "messages.js",
            "moments.js",
            "prompts.js",
            "references.js",
            "recommendations.js",
            "workbench.js",
            "site/report.js",
            "site/share.js",
        )
        native = ("window.alert(", "window.confirm(", "window.prompt(")
        for relative in files:
            text = (app.STATIC_DIR / relative).read_text(encoding="utf-8")
            for marker in native:
                self.assertNotIn(marker, text, relative)

    def test_error_dialog_is_loaded_on_interactive_pages(self):
        files = (
            "messages.html",
            "moments.html",
            "music.html",
            "books.html",
            "notes.html",
            "recommendations.html",
            "references.html",
            "workbench.html",
        )
        for relative in files:
            text = (app.STATIC_DIR / relative).read_text(encoding="utf-8")
            self.assertIn("/static/site/dialog.js", text, relative)

    def test_home_footer_only_keeps_icp_record(self):
        html = (app.STATIC_DIR / "site" / "site.html").read_text(encoding="utf-8")
        self.assertIn("陕ICP备2026028018号-1", html)
        self.assertNotIn("举报邮箱：2873523107@qq.com", html)
        self.assertNotIn("时光流转，愿你与珍爱之人，能够再次重逢。", html)
        self.assertNotIn("网页字体为 vivo Sans", html)
        css = (app.STATIC_DIR / "site" / "site.css").read_text(encoding="utf-8")
        self.assertIn(".landing-three .landing-credit-block", css)
        self.assertIn("bottom: var(--dock-bottom)", css)

    def test_notification_summary_includes_all_admin_queues(self):
        stamp = app.now_text()
        app.execute(
            """INSERT INTO users
                   (username, nickname, password_hash, status, role, created_at, updated_at)
               VALUES ('pending1', '待审用户', 'hash', 'pending', 'member', ?, ?)""",
            (stamp, stamp),
        )
        app.execute(
            """INSERT INTO site_messages
                   (nickname, content, user_id, status, created_at)
               VALUES ('用户甲', '第二条待审留言', ?, 'pending', ?)""",
            (self.member_id, stamp),
        )
        app.execute(
            """INSERT INTO content_reports
                   (target_type, target_key, target_title, reason, status, created_at)
               VALUES ('recommendation', '1', '测试推荐', '违法违规', 'pending', ?)""",
            (stamp,),
        )
        handler = self.make_handler(
            {"kind": "owner", "user_id": 0, "nickname": "管理员"}, admin=True
        )
        summary = handler.notification_summary()
        self.assertTrue(summary["admin"])
        self.assertEqual(summary["pending_users"], 1)
        self.assertEqual(summary["pending_reviews"], 2)
        self.assertEqual(summary["pending_reports"], 1)
        self.assertEqual(summary["workbench"], 4)

    def test_notification_summary_tracks_member_interactions(self):
        app.add_user_notification(
            self.member_id, "message_reply", "messages", self.message_id, "用户乙", "回复了你"
        )
        app.add_user_notification(
            self.member_id, "moment_comment", "moments", self.moment_id, "用户乙", "评论了你的动态"
        )
        handler = self.make_handler(self.member(self.member_id))
        summary = handler.notification_summary()
        self.assertFalse(summary["admin"])
        self.assertEqual(summary["messages"], 1)
        self.assertEqual(summary["moments"], 1)
        self.assertEqual(summary["workbench"], 0)

    def test_ip_region_visibility_defaults_to_private(self):
        handler = self.make_handler(self.member(self.member_id), method="POST")
        with patch.object(app, "notify_async", return_value=False):
            handler.api_site_message_create(
                {"content": "属地默认测试", "files": []}
            )
        row = app.query_one(
            "SELECT show_region FROM site_messages WHERE content = ?",
            ("属地默认测试",),
        )
        self.assertEqual(int(row["show_region"]), 0)

        with patch.object(app, "notify_async", return_value=False):
            handler.api_site_message_create(
                {"content": "属地主动公开测试", "files": [], "show_region": True}
            )
        row = app.query_one(
            "SELECT show_region FROM site_messages WHERE content = ?",
            ("属地主动公开测试",),
        )
        self.assertEqual(int(row["show_region"]), 1)

    def test_ip_region_checkboxes_default_unchecked(self):
        messages_html = (app.STATIC_DIR / "messages.html").read_text(encoding="utf-8")
        moments_html = (app.STATIC_DIR / "moments.html").read_text(encoding="utf-8")
        self.assertNotIn('id="msgShowRegion" checked', messages_html)
        self.assertNotIn('id="momentShowRegion" checked', moments_html)
        for filename in ("messages.js", "moments.js"):
            text = (app.STATIC_DIR / filename).read_text(encoding="utf-8")
            self.assertNotIn("errorShowRegion", text)

    def test_reference_project_name_and_wording(self):
        home = (app.STATIC_DIR / "site" / "site.html").read_text(encoding="utf-8")
        references = (app.STATIC_DIR / "references.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(">参考项目</a>", home)
        self.assertIn("<h1>Error酱参考项目</h1>", references)
        self.assertNotIn("搬运", references)

    def test_changelog_importer_uses_full_timestamp(self):
        script = (app.BASE_DIR / "tools" / "import_changelog_moments.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("key = stamp", script)
        self.assertNotIn("stamp[11:13]", script)
        self.assertIn("force_dates", script)
        self.assertIn("DELETE FROM moments", script)

    def test_moments_mobile_comment_layout_is_scoped(self):
        css = (app.STATIC_DIR / "moments.css").read_text(encoding="utf-8")
        script = (app.STATIC_DIR / "moments.js").read_text(encoding="utf-8")
        self.assertIn(".mo-composer-foot .mo-btn-primary", css)
        self.assertIn(".mo-comment-submit", css)
        self.assertIn("scrollIntoView", script)


class RegistrationLimitTests(unittest.TestCase):
    def test_rate_allow_survives_large_key_space(self):
        """大量不同 key 出现时不能把别人的限速计数一起清掉。"""
        saved = {key: list(value) for key, value in app.RATE_LIMITS.items()}
        try:
            app.RATE_LIMITS.clear()
            now = time.time()
            for index in range(6000):
                app.RATE_LIMITS[f"bulk:{index}"] = [now]
            results = [app.rate_allow("register", "203.0.113.77", 3, 3600) for _ in range(4)]
        finally:
            app.RATE_LIMITS.clear()
            app.RATE_LIMITS.update(saved)
        self.assertEqual(results, [True, True, True, False])

    def test_registration_block_reason_reports_daily_limit(self):
        with patch.object(
            app, "query_one", return_value={"n": app.REGISTRATION_LIMIT_PER_WINDOW}
        ):
            reason = app.registration_block_reason("203.0.113.9")
        self.assertIn("24 小时", reason)

    def test_registration_block_reason_reports_pending_request(self):
        with patch.object(app, "query_one", side_effect=[{"n": 0}, {"n": 1}]):
            reason = app.registration_block_reason("203.0.113.9")
        self.assertIn("等待审核", reason)

    def test_registration_block_reason_allows_when_clean(self):
        with patch.object(app, "query_one", return_value={"n": 0}):
            self.assertEqual("", app.registration_block_reason("203.0.113.9"))

    def test_register_handler_returns_429_when_quota_reached(self):
        handler = object.__new__(app.InventoryHandler)
        handler.client_ip = lambda: "203.0.113.9"
        message = "同一个网络 24 小时内最多提交 3 次注册申请，请明天再试。"
        with patch.object(app, "rate_allow", return_value=True), patch.object(
            app, "registration_block_reason", return_value=message
        ), patch.object(app.InventoryHandler, "log_activity"), patch.object(
            app, "api_error"
        ) as api_error:
            handler.api_register({"username": "someone", "password": "abcdefgh"})
        api_error.assert_called_once_with(handler, 429, message)


class AdminSessionIpBindingTests(unittest.TestCase):
    """管理员会话绑定登录来源 IP：换网络就要求重新登录。"""

    def _handler(self, ip):
        handler = object.__new__(app.InventoryHandler)
        handler.client_ip = lambda: ip
        handler.cookies = lambda: {app.AUTH_COOKIE: "token"}
        return handler

    def _session(self, sid, kind, user_id, ip):
        return {
            "sid": sid,
            "kind": kind,
            "user_id": user_id,
            "expires_at": time.time() + 600,
            "ip": ip,
        }

    def test_owner_session_dropped_when_source_ip_changes(self):
        handler = self._handler("10.9.9.9")
        with patch.dict(app.AUTH_STATE, {"enabled": True}), patch.object(
            app,
            "verify_session_token",
            return_value={"kind": "owner", "user_id": 0, "sid": "s1"},
        ), patch.object(
            app, "session_row", return_value=self._session("s1", "owner", 0, "1.2.3.4")
        ), patch.object(app, "delete_session") as delete_session, patch.object(
            app.InventoryHandler, "log_activity"
        ):
            self.assertIsNone(handler.session_identity())
        delete_session.assert_called_once_with("s1")

    def test_owner_session_kept_when_source_ip_matches(self):
        handler = self._handler("1.2.3.4")
        with patch.dict(app.AUTH_STATE, {"enabled": True}), patch.object(
            app,
            "verify_session_token",
            return_value={"kind": "owner", "user_id": 0, "sid": "s1"},
        ), patch.object(
            app, "session_row", return_value=self._session("s1", "owner", 0, "1.2.3.4")
        ), patch.object(app, "delete_session") as delete_session:
            identity = handler.session_identity()
        self.assertEqual(identity["kind"], "owner")
        delete_session.assert_not_called()

    def test_owner_session_without_recorded_ip_still_works(self):
        handler = self._handler("10.9.9.9")
        with patch.dict(app.AUTH_STATE, {"enabled": True}), patch.object(
            app,
            "verify_session_token",
            return_value={"kind": "owner", "user_id": 0, "sid": "s1"},
        ), patch.object(
            app, "session_row", return_value=self._session("s1", "owner", 0, None)
        ), patch.object(app, "delete_session") as delete_session:
            identity = handler.session_identity()
        self.assertEqual(identity["kind"], "owner")
        delete_session.assert_not_called()

    def test_member_user_with_admin_permission_is_ip_bound(self):
        handler = self._handler("10.9.9.9")
        with patch.dict(app.AUTH_STATE, {"enabled": True}), patch.object(
            app,
            "verify_session_token",
            return_value={"kind": "member", "user_id": 7, "sid": "s2"},
        ), patch.object(
            app, "session_row", return_value=self._session("s2", "member", 7, "1.2.3.4")
        ), patch.object(
            app,
            "query_one",
            return_value={"id": 7, "username": "helper", "nickname": None, "status": "approved"},
        ), patch.object(
            app, "user_has_permission", return_value=True
        ), patch.object(app, "delete_session") as delete_session, patch.object(
            app.InventoryHandler, "log_activity"
        ):
            self.assertIsNone(handler.session_identity())
        delete_session.assert_called_once_with("s2")

    def test_plain_member_session_is_not_ip_bound(self):
        handler = self._handler("10.9.9.9")
        with patch.dict(app.AUTH_STATE, {"enabled": True}), patch.object(
            app,
            "verify_session_token",
            return_value={"kind": "member", "user_id": 8, "sid": "s3"},
        ), patch.object(
            app, "session_row", return_value=self._session("s3", "member", 8, "1.2.3.4")
        ), patch.object(
            app,
            "query_one",
            return_value={"id": 8, "username": "guest1", "nickname": None, "status": "approved"},
        ), patch.object(
            app, "user_has_permission", return_value=False
        ), patch.object(app, "delete_session") as delete_session:
            identity = handler.session_identity()
        self.assertEqual(identity["kind"], "member")
        delete_session.assert_not_called()


class AuthSecretStorageTests(unittest.TestCase):
    """会话签名密钥要能稳定持久化，否则每次重启都会把所有人踢下线。"""

    def test_secret_is_generated_and_saved_to_database(self):
        saved = []
        with patch.object(app, "query_one", return_value=None), patch.object(
            app, "execute", side_effect=lambda sql, params=(): saved.append(params)
        ):
            secret = app.stored_auth_secret()
        self.assertEqual(len(secret), 64)
        self.assertEqual(saved, [(app.AUTH_SECRET_KEY, secret)])

    def test_saved_secret_is_reused(self):
        with patch.object(app, "query_one", return_value={"value": "saved-secret"}), patch.object(
            app, "execute"
        ) as execute:
            self.assertEqual(app.stored_auth_secret(), "saved-secret")
        execute.assert_not_called()

    def test_authoritative_secret_is_mirrored_into_database(self):
        saved = []
        with patch.object(app, "query_one", return_value={"value": "old"}), patch.object(
            app, "execute", side_effect=lambda sql, params=(): saved.append(params)
        ):
            secret = app.stored_auth_secret("from-file")
        self.assertEqual(secret, "from-file")
        self.assertEqual(saved, [(app.AUTH_SECRET_KEY, "from-file")])

    def test_database_failure_still_returns_usable_secret(self):
        with patch.object(app, "query_one", side_effect=app.sqlite3.Error("boom")):
            self.assertEqual(len(app.stored_auth_secret("env-secret")), len("env-secret"))


class AdminPasswordChangeTests(unittest.TestCase):
    """站内改管理员密码：写进 auth.json、立即生效、只允许站长操作。"""

    def _handler(self):
        handler = object.__new__(app.InventoryHandler)
        handler.client_ip = lambda: "111.19.28.219"
        handler.cookies = lambda: {}
        return handler

    def test_save_auth_password_writes_hash_and_updates_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auth.json"
            with patch.object(app, "AUTH_PATH", path), patch.dict(
                app.AUTH_STATE, {"enabled": False, "password_hash": "", "secret": ""}
            ):
                app.save_auth_password("brand-new-pass")
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(
                    app.verify_password_hash("brand-new-pass", saved["password_hash"])
                )
                self.assertTrue(app.AUTH_STATE["enabled"])
                self.assertEqual(app.AUTH_STATE["password_hash"], saved["password_hash"])
                self.assertEqual(len(saved.get("secret") or ""), 64)

    def test_auth_json_password_wins_over_env_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auth.json"
            path.write_text(
                json.dumps(
                    {"password_hash": app.hash_password("from-file"), "secret": "x" * 64},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(app, "AUTH_PATH", path), patch.dict(
                app.AUTH_STATE, {}, clear=True
            ), patch.dict(os.environ, {"INVENTORY_PASSWORD": "from-env"}, clear=False), patch.object(
                app, "stored_auth_secret", side_effect=lambda existing="": existing or "x" * 64
            ):
                state = dict(app.load_auth_state())
        self.assertTrue(app.verify_password_hash("from-file", state["password_hash"]))
        self.assertFalse(app.verify_password_hash("from-env", state["password_hash"]))

    def test_env_password_is_used_when_auth_json_has_no_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auth.json"
            path.write_text(json.dumps({"secret": "x" * 64}), encoding="utf-8")
            with patch.object(app, "AUTH_PATH", path), patch.dict(
                app.AUTH_STATE, {}, clear=True
            ), patch.dict(os.environ, {"INVENTORY_PASSWORD": "bootstrap-pass"}, clear=False), patch.object(
                app, "stored_auth_secret", side_effect=lambda existing="": existing or "x" * 64
            ):
                state = dict(app.load_auth_state())
        self.assertTrue(app.verify_password_hash("bootstrap-pass", state["password_hash"]))

    def test_password_change_rejects_non_owner(self):
        handler = self._handler()
        with patch.object(handler, "is_owner", return_value=False), patch.object(
            app, "api_error"
        ) as api_error:
            handler.api_admin_password({"current_password": "a", "new_password": "bbbbbbbb"})
        api_error.assert_called_once_with(handler, 403, "只有站长账号可以修改管理员登录密码。")

    def test_password_change_rejects_wrong_current_password(self):
        handler = self._handler()
        with patch.object(handler, "is_owner", return_value=True), patch.object(
            app, "verify_password", return_value=False
        ), patch.object(app, "save_auth_password") as save, patch.object(
            app.InventoryHandler, "log_activity"
        ), patch.object(app, "api_error") as api_error:
            handler.api_admin_password({"current_password": "bad", "new_password": "bbbbbbbb"})
        api_error.assert_called_once_with(handler, 401, "当前密码不正确。")
        save.assert_not_called()

    def test_password_change_rejects_short_password(self):
        handler = self._handler()
        with patch.object(handler, "is_owner", return_value=True), patch.object(
            app, "verify_password", return_value=True
        ), patch.object(app, "save_auth_password") as save, patch.object(
            app, "api_error"
        ) as api_error:
            handler.api_admin_password({"current_password": "old", "new_password": "1234567"})
        api_error.assert_called_once_with(handler, 400, "新密码长度需为 8-128 位。")
        save.assert_not_called()

    def test_password_change_saves_and_kicks_other_owner_sessions(self):
        handler = self._handler()
        with patch.object(handler, "is_owner", return_value=True), patch.object(
            app, "verify_password", return_value=True
        ), patch.object(app, "save_auth_password") as save, patch.object(
            app,
            "verify_session_token",
            return_value={"sid": "keep-me", "kind": "owner", "user_id": 0},
        ), patch.object(app, "execute") as execute, patch.object(
            app, "write_audit"
        ), patch.object(app.InventoryHandler, "log_activity"), patch.object(
            app.InventoryHandler, "send_json"
        ) as send_json:
            handler.api_admin_password(
                {"current_password": "old", "new_password": "brand-new-pass"}
            )
        save.assert_called_once_with("brand-new-pass")
        execute.assert_called_once_with(
            "DELETE FROM sessions WHERE kind = 'owner' AND sid <> ?", ("keep-me",)
        )
        send_json.assert_called_once_with(200, {"ok": True})


class FiniteNumberTests(unittest.TestCase):
    """库存类数量必须先过 finite_number，NaN / 无穷大不能当成合法数字。"""

    def test_rejects_nan_and_infinity(self):
        for bad in ("nan", "NaN", "inf", "-inf", "Infinity", "-Infinity"):
            with self.assertRaises(ValueError, msg=bad):
                app.finite_number(bad)

    def test_rejects_non_numeric_text(self):
        with self.assertRaises(ValueError):
            app.finite_number("abc")

    def test_keeps_normal_values(self):
        self.assertEqual(app.finite_number("3.5"), 3.5)
        self.assertEqual(app.finite_number(7), 7.0)
        self.assertEqual(app.finite_number(None), 0.0)
        self.assertEqual(app.finite_number(""), 0.0)


class AuthFailClosedTests(unittest.TestCase):
    """密码文件存在但读不出来时，绝不能静默降级成整站免密。"""

    def setUp(self):
        self._auth_path = app.AUTH_PATH
        self._state = dict(app.AUTH_STATE)

    def tearDown(self):
        app.AUTH_PATH = self._auth_path
        app.AUTH_STATE.clear()
        app.AUTH_STATE.update(self._state)

    def test_broken_auth_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "auth.json"
            path.write_text("{ this is not json", encoding="utf-8")
            app.AUTH_PATH = path
            with patch.dict(os.environ, {"INVENTORY_PASSWORD": ""}, clear=False):
                state = app.load_auth_state()
        self.assertFalse(state["enabled"])
        self.assertTrue(state.get("config_broken"))

    def test_missing_auth_file_stays_local_mode(self):
        # 文件根本不存在 = 没设过访问密码，是正常的本地模式，不该被当成损坏
        with tempfile.TemporaryDirectory() as temp_dir:
            app.AUTH_PATH = Path(temp_dir) / "auth.json"
            with patch.dict(os.environ, {"INVENTORY_PASSWORD": ""}, clear=False):
                state = app.load_auth_state()
        self.assertFalse(state["enabled"])
        self.assertFalse(state.get("config_broken"))


class BookDeleteRouteTests(unittest.TestCase):
    """do_DELETE 曾经漏了 /api/books/<id>，前端删书永远 404。"""

    def test_delete_request_reaches_book_handler_and_removes_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(app, "DB_PATH", Path(temp_dir) / "inventory.db"):
                app.init_db()
                stamp = app.now_text()
                book_id = app.execute(
                    """INSERT INTO books
                           (title, author, format, file_path, file_size, sort_order,
                            created_at, updated_at)
                       VALUES (?, ?, 'txt', ?, 1, 0, ?, ?)""",
                    ("待删的书", "作者", "book_files/not-there.txt", stamp, stamp),
                )
                handler = object.__new__(app.InventoryHandler)
                handler.path = f"/api/books/{book_id}"
                handler.command = "DELETE"
                handler.guard_request = lambda path, method: True
                responses = []
                handler.send_json = lambda status, payload: responses.append(
                    (status, payload)
                )
                handler.log_activity = lambda *args, **kwargs: None

                handler.do_DELETE()

                self.assertEqual(responses[-1], (200, {"ok": True}))
                self.assertIsNone(
                    app.query_one("SELECT id FROM books WHERE id = ?", (book_id,))
                )

    def test_unknown_delete_path_still_404s(self):
        handler = object.__new__(app.InventoryHandler)
        handler.path = "/api/books/not-a-number"
        handler.command = "DELETE"
        handler.guard_request = lambda path, method: True
        responses = []
        handler.send_json = lambda status, payload: responses.append((status, payload))
        handler.do_DELETE()
        self.assertEqual(responses[-1][0], 404)


class StockQuantityGuardTests(unittest.TestCase):
    """出入库：非数字 / NaN 走 400，库存不足也走 400（不再是 500 + 内部信息）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patcher = patch.object(
            app, "DB_PATH", Path(self._tmp.name) / "inventory.db"
        )
        self._patcher.start()
        app.init_db()
        stamp = app.now_text()
        self.part_id = app.execute(
            "INSERT INTO parts (part_number, min_stock, created_at, updated_at)"
            " VALUES (?, 0, ?, ?)",
            ("TEST-PART", stamp, stamp),
        )
        self.location_id = app.execute(
            "INSERT INTO locations (code, name, created_at) VALUES (?, ?, ?)",
            ("A1", "A1", stamp),
        )
        app.execute(
            """INSERT INTO batches
                   (part_id, location_id, quantity, received_quantity, purchase_date, created_at)
               VALUES (?, ?, 1, 1, ?, ?)""",
            (self.part_id, self.location_id, stamp, stamp),
        )

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def _handler(self):
        handler = object.__new__(app.InventoryHandler)
        handler.command = "POST"
        responses = []
        handler.send_json = lambda status, payload: responses.append((status, payload))
        handler.log_activity = lambda *args, **kwargs: None
        return handler, responses

    def test_non_finite_quantity_is_rejected(self):
        handler, responses = self._handler()
        for bad in ("nan", "inf", "-inf"):
            handler.api_stock_inbound(
                {
                    "part_id": self.part_id,
                    "location_id": self.location_id,
                    "quantity": bad,
                }
            )
        self.assertEqual([status for status, _ in responses], [400, 400, 400])
        # 库存没被动过：仍然是那 1 个
        self.assertEqual(
            app.query_one("SELECT SUM(quantity) AS n FROM batches")["n"], 1
        )

    def test_shortage_returns_400_with_readable_message(self):
        handler, responses = self._handler()
        handler.api_stock_outbound({"part_id": self.part_id, "quantity": 5})
        status, payload = responses[-1]
        self.assertEqual(status, 400)
        self.assertIn("可用库存不足", payload["error"])


if __name__ == "__main__":
    unittest.main()
