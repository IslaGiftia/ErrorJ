#!/usr/bin/env python3
"""把 config/changelog-seed.json 里的每日更新日志写入 moments 表。

每条日志写成一条动态，created_at 使用日志日期（默认 20:00:00），
这样动态页面显示的时间就是 Error酱 实际更新的日期。

用法：
    python tools/import_changelog_moments.py --dry-run   # 只预览
    python tools/import_changelog_moments.py             # 写入缺失的日期
    python tools/import_changelog_moments.py --force     # 覆盖同日期内容
    python tools/import_changelog_moments.py --delete    # 删除全部“更新日志”动态
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "inventory.db"
DEFAULT_SEED = BASE_DIR / "config" / "changelog-seed.json"
DEFAULT_TAG = "更新日志"
DEFAULT_TIME = "20:00:00"
MAX_CONTENT_CHARS = 2000


def normalize_time(value, fallback):
    """把 hh:mm 或 hh:mm:ss 规范化成 hh:mm:ss。"""
    text = str(value or "").strip() or str(fallback or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not match:
        raise ValueError(f"时间格式不正确：{text or '(空)'}")
    hour = int(match.group(1))
    if hour > 23 or int(match.group(2)) > 59 or int(match.group(3) or 0) > 59:
        raise ValueError(f"时间超出范围：{text}")
    return f"{hour:02d}:{match.group(2)}:{match.group(3) or '00'}"


def build_content(entry, tag):
    lines = [f"【{tag}】{entry['date']}　{entry['title']}", ""]
    for item in entry.get("items", []):
        lines.append(f"· {item}")
    text = "\n".join(lines).strip()
    if len(text) > MAX_CONTENT_CHARS:
        raise ValueError(
            f"{entry['date']} 的日志有 {len(text)} 字，超过了动态上限 {MAX_CONTENT_CHARS} 字。"
        )
    return text


def parse_args():
    parser = argparse.ArgumentParser(description="导入 Error酱 每日更新日志到动态")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="inventory.db 路径")
    parser.add_argument("--seed", default=str(DEFAULT_SEED), help="更新日志 JSON 路径")
    parser.add_argument("--time", default=DEFAULT_TIME, help="每天写入的时间，默认 20:00:00")
    parser.add_argument("--date", default="", help="只处理指定日期，格式 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的操作")
    parser.add_argument("--force", action="store_true", help="同一天已存在时覆盖内容")
    parser.add_argument("--delete", action="store_true", help="删除所有“更新日志”动态后退出")
    return parser.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)
    seed_path = Path(args.seed)
    if not db_path.is_file():
        print(f"数据库不存在：{db_path}", file=sys.stderr)
        return 1
    if not seed_path.is_file():
        print(f"日志文件不存在：{seed_path}", file=sys.stderr)
        return 1

    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    tag = str(seed.get("tag") or DEFAULT_TAG)
    entries = seed.get("entries") or []
    if args.date:
        entries = [entry for entry in entries if str(entry.get("date") or "") == args.date]
    if not entries:
        print("没有匹配的日志条目。", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        like = f"%{tag}%"
        existing = {
            row["day"]: row["id"]
            for row in conn.execute(
                """SELECT id, substr(created_at, 1, 10) AS day
                   FROM moments WHERE tags LIKE ?""",
                (like,),
            )
        }

        if args.delete:
            targets = list(existing.items())
            if args.dry_run:
                for day, row_id in sorted(targets):
                    print(f"[dry-run] 删除 {day}（id={row_id}）")
                print(f"共会删除 {len(targets)} 条。")
                return 0
            for _day, row_id in targets:
                conn.execute("DELETE FROM moments WHERE id = ?", (row_id,))
            conn.commit()
            print(f"已删除 {len(targets)} 条“{tag}”动态。")
            return 0

        inserted = 0
        updated = 0
        skipped = 0
        for entry in entries:
            day = str(entry.get("date") or "").strip()
            if not day:
                print("有一条日志缺少 date，已跳过。", file=sys.stderr)
                skipped += 1
                continue
            content = build_content(entry, tag)
            stamp = f"{day} {normalize_time(entry.get('time'), args.time)}"
            if day in existing:
                if not args.force:
                    print(f"[跳过] {day} 已存在（id={existing[day]}）")
                    skipped += 1
                    continue
                if args.dry_run:
                    print(f"[dry-run] 覆盖 {day}（id={existing[day]}）")
                    updated += 1
                    continue
                conn.execute(
                    "UPDATE moments SET content = ?, tags = ?, created_at = ? WHERE id = ?",
                    (content, tag, stamp, existing[day]),
                )
                updated += 1
                continue
            if args.dry_run:
                print(f"[dry-run] 新增 {day}：{entry.get('title') or ''}")
                inserted += 1
                continue
            conn.execute(
                """INSERT INTO moments
                       (content, tags, pinned, ip, ip_region, show_region, created_at)
                   VALUES (?, ?, 0, '', '', 0, ?)""",
                (content, tag, stamp),
            )
            inserted += 1

        if not args.dry_run:
            conn.commit()
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}完成：新增 {inserted} 条，覆盖 {updated} 条，跳过 {skipped} 条。")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
