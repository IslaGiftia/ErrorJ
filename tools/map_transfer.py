"""地图模块整体迁移：在本机导出，在服务器导入。

比页面上的 GeoJSON 导入导出更完整：带分类树、打卡状态、推荐度和照片。

用法：
    # 本机导出（生成一个包含照片的 JSON 文件）
    python tools/map_transfer.py export -o map-export.json

    # 服务器上先演练一遍，确认会写入多少数据
    python tools/map_transfer.py import map-export.json --dry-run

    # 正式导入（默认合并：已存在的跳过，缺失的补齐）
    python tools/map_transfer.py import map-export.json

    # 清空服务器现有地图数据后完整覆盖（需要 --yes 确认）
    python tools/map_transfer.py import map-export.json --mode replace --yes

    # 只清空地图数据（分类、标记、标记照片），不动其它模块
    python tools/map_transfer.py wipe --yes
"""

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402

SCHEMA_VERSION = 1
DATA_ROOT = app.DATA_DIR.resolve()


def export_map(output_path, include_photos=True):
    categories = app.query(
        """SELECT id, parent_id, name, glyph, color, note, sort_order, created_at
           FROM map_categories
           ORDER BY COALESCE(parent_id, id), parent_id IS NOT NULL, sort_order, id"""
    )
    places = app.query(
        """SELECT id, category_id, name, subtitle, address, note, signature, tags,
                  lat, lng, status, rating, created_by, created_at, updated_at
           FROM map_places ORDER BY id"""
    )
    photos = []
    if include_photos:
        rows = app.query(
            """SELECT id, place_id, file_path, original_name, mime_type, size_bytes,
                      created_by, created_at
               FROM map_place_photos ORDER BY id"""
        )
        for row in rows:
            full = (app.DATA_DIR / (row["file_path"] or "")).resolve()
            try:
                full.relative_to(DATA_ROOT)
            except ValueError:
                continue
            if not full.is_file():
                continue
            raw = full.read_bytes()
            photos.append(
                {
                    "place_id": row["place_id"],
                    "file_path": row["file_path"],
                    "original_name": row["original_name"],
                    "mime_type": row["mime_type"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
    bundle = {
        "format": "errorjiang-map",
        "version": SCHEMA_VERSION,
        "exported_at": app.now_text(),
        "categories": categories,
        "places": places,
        "photos": photos,
    }
    target = Path(output_path)
    target.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    size_mb = target.stat().st_size / (1024 * 1024)
    print(
        f"已导出：{len(categories)} 个分类、{len(places)} 个标记、{len(photos)} 张照片 "
        f"→ {target}（{size_mb:.1f} MB）"
    )


def save_photo_file(relative, raw):
    """把导出的照片写进 data/ 目录，返回实际使用的相对路径。"""
    relative = str(relative or "").replace("\\", "/").lstrip("/")
    name = os.path.basename(relative) or f"photo-{uuid.uuid4().hex[:6]}.jpg"
    if not relative.startswith("map_images/"):
        relative = "map_images/" + name
    full = (app.DATA_DIR / relative).resolve()
    try:
        full.relative_to(DATA_ROOT)
    except ValueError:
        relative = f"map_images/{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}_{name}"
        full = app.DATA_DIR / relative
    if full.is_file():
        if full.read_bytes() == raw:
            return relative
        stem, suffix = os.path.splitext(relative)
        relative = f"{stem}_{uuid.uuid4().hex[:4]}{suffix}"
        full = app.DATA_DIR / relative
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(raw)
    return relative


def parse_bundle(input_path):
    bundle = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if not isinstance(bundle, dict) or bundle.get("format") != "errorjiang-map":
        raise SystemExit("这不是 map_transfer.py 导出的文件。")
    return bundle


def import_map(input_path, dry_run=False, keep_created_by=False):
    bundle = parse_bundle(input_path)
    categories = bundle.get("categories") or []
    places = bundle.get("places") or []
    photos = bundle.get("photos") or []
    conn = app.get_conn()
    stats = {
        "categories_added": 0,
        "categories_matched": 0,
        "places_added": 0,
        "places_skipped": 0,
        "photos_added": 0,
        "photos_skipped": 0,
    }
    try:
        cursor = conn.cursor()

        def find_category(name, parent_id):
            if parent_id:
                row = cursor.execute(
                    "SELECT id FROM map_categories WHERE name = ? AND parent_id = ?",
                    (name, parent_id),
                ).fetchone()
            else:
                row = cursor.execute(
                    "SELECT id FROM map_categories WHERE name = ? AND parent_id IS NULL",
                    (name,),
                ).fetchone()
            return row["id"] if row else None

        category_map = {}
        tops = [row for row in categories if not row.get("parent_id")]
        children = [row for row in categories if row.get("parent_id")]
        for row in tops + children:
            parent_id = (
                category_map.get(row.get("parent_id")) if row.get("parent_id") else None
            )
            if row.get("parent_id") and parent_id is None:
                continue
            found = find_category(row.get("name") or "", parent_id)
            if found:
                category_map[row["id"]] = found
                stats["categories_matched"] += 1
                continue
            if dry_run:
                category_map[row["id"]] = -(len(category_map) + 1)
                stats["categories_added"] += 1
                continue
            cursor.execute(
                """INSERT INTO map_categories
                       (parent_id, name, glyph, color, note, sort_order, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    parent_id,
                    row.get("name"),
                    row.get("glyph") or "·",
                    row.get("color") or "#7b68ee",
                    row.get("note"),
                    int(row.get("sort_order") or 0),
                    row.get("created_at") or app.now_text(),
                ),
            )
            category_map[row["id"]] = cursor.lastrowid
            stats["categories_added"] += 1

        place_map = {}
        for row in places:
            try:
                lat = float(row.get("lat"))
                lng = float(row.get("lng"))
            except (TypeError, ValueError):
                stats["places_skipped"] += 1
                continue
            found = cursor.execute(
                """SELECT id FROM map_places
                   WHERE name = ? AND ROUND(lat, 5) = ROUND(?, 5)
                     AND ROUND(lng, 5) = ROUND(?, 5)""",
                (row.get("name"), lat, lng),
            ).fetchone()
            if found:
                place_map[row["id"]] = found["id"]
                stats["places_skipped"] += 1
                continue
            if dry_run:
                place_map[row["id"]] = -(len(place_map) + 1)
                stats["places_added"] += 1
                continue
            created_by = 0 if not keep_created_by else int(row.get("created_by") or 0)
            cursor.execute(
                """INSERT INTO map_places
                       (category_id, name, subtitle, address, note, signature, tags,
                        lat, lng, status, rating, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    category_map.get(row.get("category_id")),
                    row.get("name"),
                    row.get("subtitle"),
                    row.get("address"),
                    row.get("note"),
                    row.get("signature"),
                    row.get("tags"),
                    lat,
                    lng,
                    row.get("status"),
                    int(row.get("rating") or 0),
                    created_by,
                    row.get("created_at") or app.now_text(),
                    row.get("updated_at") or app.now_text(),
                ),
            )
            place_map[row["id"]] = cursor.lastrowid
            stats["places_added"] += 1

        hash_cache = {}
        for photo in photos:
            place_id = place_map.get(photo.get("place_id"))
            if not place_id or place_id < 0:
                continue
            try:
                raw = base64.b64decode(photo.get("data_base64") or "", validate=True)
            except Exception:
                stats["photos_skipped"] += 1
                continue
            digest = photo.get("sha256") or hashlib.sha256(raw).hexdigest()
            if place_id not in hash_cache:
                known = set()
                for existing in cursor.execute(
                    "SELECT file_path FROM map_place_photos WHERE place_id = ?",
                    (place_id,),
                ).fetchall():
                    full = (app.DATA_DIR / (existing["file_path"] or "")).resolve()
                    try:
                        full.relative_to(DATA_ROOT)
                    except ValueError:
                        continue
                    if full.is_file():
                        known.add(hashlib.sha256(full.read_bytes()).hexdigest())
                hash_cache[place_id] = known
            if digest in hash_cache[place_id]:
                stats["photos_skipped"] += 1
                continue
            if dry_run:
                stats["photos_added"] += 1
                continue
            relative = save_photo_file(photo.get("file_path"), raw)
            cursor.execute(
                """INSERT INTO map_place_photos
                       (place_id, file_path, original_name, mime_type, size_bytes,
                        created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    place_id,
                    relative,
                    photo.get("original_name"),
                    photo.get("mime_type"),
                    len(raw),
                    0,
                    photo.get("created_at") or app.now_text(),
                ),
            )
            hash_cache[place_id].add(digest)
            stats["photos_added"] += 1
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()
    label = "（演练，未写入）" if dry_run else ""
    print(
        f"导入完成{label}：分类新增 {stats['categories_added']} / 匹配 {stats['categories_matched']}；"
        f"标记新增 {stats['places_added']} / 跳过 {stats['places_skipped']}；"
        f"照片新增 {stats['photos_added']} / 跳过 {stats['photos_skipped']}"
    )


def wipe_map():
    conn = app.get_conn()
    try:
        rows = conn.execute("SELECT file_path FROM map_place_photos").fetchall()
        conn.execute("DELETE FROM map_places")
        conn.execute("DELETE FROM map_categories")
        conn.commit()
    finally:
        conn.close()
    for row in rows:
        app.remove_data_file(row["file_path"])


def main():
    parser = argparse.ArgumentParser(description="Error酱地图模块迁移工具")
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser("export", help="导出地图数据到 JSON")
    export_parser.add_argument("-o", "--output", default="map-export.json")
    export_parser.add_argument(
        "--no-photos", action="store_true", help="不包含照片（文件会小很多）"
    )

    import_parser = sub.add_parser("import", help="从 JSON 导入地图数据")
    import_parser.add_argument("input")
    import_parser.add_argument(
        "--mode",
        choices=("merge", "replace"),
        default="merge",
        help="merge=合并去重（默认），replace=先清空再导入",
    )
    import_parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    import_parser.add_argument(
        "--keep-created-by",
        action="store_true",
        help="保留原创建人 ID（默认统一归到管理员）",
    )
    import_parser.add_argument(
        "--yes", action="store_true", help="replace 模式的确认开关"
    )

    wipe_parser = sub.add_parser("wipe", help="清空全部地图数据（分类、标记和照片）")
    wipe_parser.add_argument("--yes", action="store_true", help="确认执行")

    args = parser.parse_args()
    if args.command == "export":
        export_map(args.output, include_photos=not args.no_photos)
        return
    if args.command == "wipe":
        if not args.yes:
            raise SystemExit("wipe 会清空所有地图分类和标记，确认后请再加 --yes。")
        wipe_map()
        print("已清空全部地图数据（分类、标记和照片）。")
        return
    if args.mode == "replace" and not args.dry_run:
        if not args.yes:
            raise SystemExit("replace 会清空现有地图数据，确认后请再加 --yes。")
        wipe_map()
        print("已清空现有地图数据。")
    import_map(
        args.input,
        dry_run=args.dry_run,
        keep_created_by=args.keep_created_by,
    )


if __name__ == "__main__":
    main()
