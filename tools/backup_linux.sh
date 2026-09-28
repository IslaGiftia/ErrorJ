#!/usr/bin/env bash
# Error酱 数据备份（Linux / 阿里云 ECS）
#
# 用法：
#   bash tools/backup_linux.sh                 # 备份到 ../errorjiang-backup
#   bash tools/backup_linux.sh /data/backup    # 指定备份目录
#
# 说明：
#   - SQLite 用官方 backup API 做一致性快照（服务运行中也能安全备份）
#   - 上传文件（site_message_files / note_images / workbench 等）直接打包
#   - 默认保留最近 14 份，超过的自动删除
#   - 想同步到 OSS：装好 ossutil 后在脚本末尾加
#       ossutil cp -rf "$BACKUP_DIR" oss://你的bucket/errorjiang/ --update
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$APP_DIR/data"
BACKUP_DIR="${1:-$(dirname "$APP_DIR")/errorjiang-backup}"
KEEP=14
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/$STAMP"
PYTHON="$(command -v python3 || command -v python || true)"

if [ -z "$PYTHON" ]; then
  echo "找不到 python3 / python，请先安装 Python 3。" >&2
  exit 1
fi

mkdir -p "$TARGET"

echo "[1/2] 备份数据库（一致性快照）"
"$PYTHON" - "$DATA_DIR/inventory.db" "$TARGET/inventory.db" <<'PY'
import sqlite3
import sys
from pathlib import Path

source, target = sys.argv[1], sys.argv[2]
if not Path(source).is_file():
    raise SystemExit(f"找不到数据库：{source}")

src = sqlite3.connect(source)
try:
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
finally:
    src.close()
print(f"  -> {target}")
PY

echo "[2/2] 打包上传文件（不含数据库和缓存）"
if [ -d "$DATA_DIR" ]; then
  tar -czf "$TARGET/files.tar.gz" -C "$DATA_DIR" \
    --exclude="inventory.db*" \
    --exclude="__pycache__" \
    .
  echo "  -> $TARGET/files.tar.gz"
fi

echo "清理旧备份（保留最近 $KEEP 份）"
ls -1dt "$BACKUP_DIR"/*/ 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -rf -- "$old"
  echo "  删除 $old"
done

echo "完成：$TARGET"
du -sh "$TARGET" 2>/dev/null || true
