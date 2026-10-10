#!/usr/bin/env bash
# Error酱：白名单的「手机短命令」入口
# 安装位置：/usr/local/bin/allow
#   allow                等价于 nginx-allow-ip.sh list
#   allow open 2h        临时全放开 2 小时，到期自动收回
#   allow strict         立刻收回
#   allow add 1.2.3.4 2h 只放行某个 IP 2 小时
# 存在的意义：Termius 免费版没有 Snippets，手机上少打一大串路径。
set -euo pipefail

TARGET="/usr/local/bin/nginx-allow-ip.sh"

if [ ! -x "$TARGET" ]; then
  echo "找不到 $TARGET" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  exec bash "$TARGET" list
fi

exec bash "$TARGET" "$@"
