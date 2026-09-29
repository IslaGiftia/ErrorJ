#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
if ! python3 -c "import anydoc" >/dev/null 2>&1; then
  echo "正在安装 Word/PDF 转换依赖..."
  if ! python3 -m pip install -r requirements.txt; then
    echo "依赖安装失败，Word/PDF 导入暂不可用。"
  fi
fi
exec python3 app.py
