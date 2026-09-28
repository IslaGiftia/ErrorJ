"""设置或清除 Error酱 的访问密码。

用法：
    python tools/set_password.py                # 交互式输入新密码
    python tools/set_password.py --password xxx # 直接指定（注意 shell 历史）
    python tools/set_password.py --clear        # 关闭访问密码

密码以 PBKDF2-SHA256 哈希写在 data/auth.json，不会保存明文。
设置后重启 app.py 生效：未登录访问会跳转到 /login。
也可以用环境变量 INVENTORY_PASSWORD 临时覆盖（优先级高于本文件）。
"""

import argparse
import getpass
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as errorjiang  # noqa: E402


def load_config():
    if errorjiang.AUTH_PATH.is_file():
        try:
            return json.loads(errorjiang.AUTH_PATH.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_config(config):
    errorjiang.AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    errorjiang.AUTH_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        errorjiang.AUTH_PATH.chmod(0o600)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="设置 Error酱 访问密码")
    parser.add_argument("--password", help="直接指定密码（不推荐，会留在命令历史里）")
    parser.add_argument("--clear", action="store_true", help="清除密码，恢复免登录")
    args = parser.parse_args()

    config = load_config()
    config.setdefault("secret", secrets.token_hex(32))

    if args.clear:
        config.pop("password_hash", None)
        save_config(config)
        print("已清除访问密码，重启 app.py 后恢复免登录访问。")
        return

    password = args.password or ""
    if not password:
        password = getpass.getpass("新密码：")
        confirm = getpass.getpass("再输一次：")
        if password != confirm:
            print("两次输入不一致，已取消。")
            return
    if len(password) < 6:
        print("密码至少 6 位。")
        return

    config["password_hash"] = errorjiang.hash_password(password)
    save_config(config)
    print(f"已写入 {errorjiang.AUTH_PATH}")
    print("重启 app.py 后用新密码登录（环境变量 INVENTORY_PASSWORD 会覆盖它）。")


if __name__ == "__main__":
    main()
