"""管理 Error酱 普通用户账号。

用法：
    python tools/manage_users.py list
    python tools/manage_users.py pending
    python tools/manage_users.py approve <用户名>
    python tools/manage_users.py reject <用户名>
    python tools/manage_users.py disable <用户名>
    python tools/manage_users.py enable <用户名>
    python tools/manage_users.py delete <用户名>
    python tools/manage_users.py reset-password <用户名>
    python tools/manage_users.py create <用户名>
"""

import argparse
import getpass
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402


def find_user(username):
    return app.query_one(
        """
        SELECT id, username, status, role, created_at, updated_at,
               approved_at, last_login_at
        FROM users
        WHERE username = ?
        """,
        (username,),
    )


def require_user(username):
    user = find_user(username)
    if not user:
        raise SystemExit(f"找不到账号：{username}")
    return user


def set_status(username, status):
    user = require_user(username)
    stamp = app.now_text()
    approved_at = stamp if status == "approved" else user.get("approved_at")
    app.execute(
        """
        UPDATE users
        SET status = ?, approved_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, approved_at, stamp, user["id"]),
    )
    print(f"账号 {user['username']} 状态已更新为 {status}")


def prompt_password(label="密码"):
    password = getpass.getpass(f"{label}：")
    confirm = getpass.getpass(f"再次输入{label}：")
    if password != confirm:
        raise SystemExit("两次输入的密码不一致。")
    if len(password) < 8 or len(password) > 128:
        raise SystemExit("密码长度需为 8-128 位。")
    return password


def create_user(username_text, password=None, approved=True):
    username = app.valid_username(username_text)
    if not username:
        raise SystemExit("用户名需为 3-32 位，只能包含文字、字母、数字、点、下划线或短横线。")
    if find_user(username):
        raise SystemExit(f"用户名已存在：{username}")
    password = password or prompt_password()
    stamp = app.now_text()
    user_id = app.execute(
        """
        INSERT INTO users
            (username, password_hash, status, role, created_at, updated_at, approved_at)
        VALUES (?, ?, ?, 'member', ?, ?, ?)
        """,
        (
            username,
            app.hash_password(password),
            "approved" if approved else "pending",
            stamp,
            stamp,
            stamp if approved else None,
        ),
    )
    print(f"已创建账号 #{user_id}：{username}")


def list_users(pending_only=False):
    where = "WHERE status = 'pending'" if pending_only else ""
    rows = app.query(
        f"""
        SELECT id, username, status, role, created_at, approved_at, last_login_at
        FROM users
        {where}
        ORDER BY
            CASE status
                WHEN 'pending' THEN 0
                WHEN 'approved' THEN 1
                WHEN 'disabled' THEN 2
                ELSE 3
            END,
            created_at,
            id
        """
    )
    if not rows:
        print("没有匹配账号。")
        return
    print(f"{'ID':<5} {'用户名':<20} {'状态':<10} {'创建时间':<20} {'最后登录'}")
    print("-" * 88)
    for row in rows:
        print(
            f"{row['id']:<5} {row['username']:<20} {row['status']:<10} "
            f"{row['created_at']:<20} {row.get('last_login_at') or '-'}"
        )


def main():
    parser = argparse.ArgumentParser(description="管理 Error酱 普通用户账号")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出全部账号")
    sub.add_parser("pending", help="只列出待审核账号")

    for name, help_text in [
        ("approve", "批准账号"),
        ("reject", "拒绝账号"),
        ("disable", "停用账号"),
        ("enable", "重新启用账号"),
        ("delete", "删除账号"),
        ("reset-password", "重置密码"),
    ]:
        item = sub.add_parser(name, help=help_text)
        item.add_argument("username")

    create = sub.add_parser("create", help="直接创建已批准账号")
    create.add_argument("username")
    create.add_argument("--password", default="")

    args = parser.parse_args()
    app.init_db()

    if args.command == "list":
        list_users()
    elif args.command == "pending":
        list_users(pending_only=True)
    elif args.command in ("approve", "enable"):
        set_status(args.username, "approved")
    elif args.command == "reject":
        set_status(args.username, "rejected")
    elif args.command == "disable":
        set_status(args.username, "disabled")
    elif args.command == "delete":
        user = require_user(args.username)
        app.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        print(f"已删除账号：{user['username']}")
    elif args.command == "reset-password":
        user = require_user(args.username)
        password = prompt_password("新密码")
        app.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (app.hash_password(password), app.now_text(), user["id"]),
        )
        print(f"已重置账号密码：{user['username']}")
    elif args.command == "create":
        create_user(args.username, args.password or None)


if __name__ == "__main__":
    main()
