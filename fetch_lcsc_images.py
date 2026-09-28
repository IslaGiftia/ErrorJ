#!/usr/bin/env python3
"""Fetch part images from LCSC product pages and save them into the local system."""

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "inventory.db"
IMAGE_DIR = BASE_DIR / "data" / "part_images"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def fetch_text(url, timeout=25):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def extract_image_url(html, code):
    for match in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    ):
        try:
            data = json.loads(match.group(1))
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        images = data.get("image")
        if isinstance(images, str):
            images = [images]
        if isinstance(images, list) and images:
            return str(images[0])
    match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def fetch_one(part, force=False):
    part_id, code = part["id"], part["lcsc_code"]
    try:
        page_url = f"https://www.lcsc.com/product-detail/{code}.html"
        html = fetch_text(page_url).decode("utf-8", errors="replace")
        image_url = extract_image_url(html, code)
        if not image_url:
            return part_id, code, False, "页面里没有找到图片"
        image_data = fetch_text(image_url, timeout=40)
        if len(image_data) < 1024:
            return part_id, code, False, "图片内容为空或过小"

        suffix = Path(urllib.parse.urlparse(image_url).path).suffix.lower()
        if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            suffix = ".jpg"
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        image_path = IMAGE_DIR / f"{part_id}{suffix}"

        conn = sqlite3.connect(DB_PATH)
        try:
            old = conn.execute(
                "SELECT image_path FROM parts WHERE id = ?", (part_id,)
            ).fetchone()
            if old and old[0] and not force:
                return part_id, code, False, "已有图片，跳过"
            if old and old[0]:
                old_full = BASE_DIR / old[0]
                try:
                    old_full.relative_to(BASE_DIR)
                    if old_full.is_file():
                        old_full.unlink()
                except ValueError:
                    pass
            image_path.write_bytes(image_data)
            conn.execute(
                "UPDATE parts SET image_path = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (f"part_images/{image_path.name}", part_id),
            )
            conn.commit()
        finally:
            conn.close()
        return part_id, code, True, image_path.name
    except urllib.error.HTTPError as exc:
        return part_id, code, False, f"HTTP {exc.code}"
    except Exception as exc:
        return part_id, code, False, str(exc)[:120]


def main():
    parser = argparse.ArgumentParser(description="从立创商城按 LCSC 编码批量抓取元件图片")
    parser.add_argument("--force", action="store_true", help="覆盖已有图片")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not DB_PATH.is_file():
        print(f"未找到数据库：{DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, lcsc_code
            FROM parts
            WHERE lcsc_code IS NOT NULL AND lcsc_code <> ''
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()

    if args.limit:
        rows = rows[: args.limit]

    print(f"共找到 {len(rows)} 个有 LCSC 编码的元件，开始抓取图片...")
    ok = skipped = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(fetch_one, part, args.force): part
            for part in rows
        }
        for index, future in enumerate(as_completed(futures), start=1):
            part_id, code, success, message = future.result()
            if success:
                ok += 1
                print(f"[{index}/{len(rows)}] OK  {code} -> {message}")
            elif message == "已有图片，跳过":
                skipped += 1
                print(f"[{index}/{len(rows)}] --  {code} {message}")
            else:
                failed += 1
                print(f"[{index}/{len(rows)}] ERR {code} {message}")

    print(f"完成：新增 {ok} 张，跳过 {skipped} 张，失败 {failed} 张")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
