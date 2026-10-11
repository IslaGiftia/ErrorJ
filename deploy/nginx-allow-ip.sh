#!/usr/bin/env bash
# Error酱：管理员入口 IP 白名单管理
#   list / open [时长] / strict / add <IP|网段> [时长] / remove <IP|网段>
# 每次改动都会先备份、再 nginx -t，失败自动回滚并 reload。
set -euo pipefail

CONF="${ERRORJIANG_ALLOW_CONF:-/etc/nginx/conf.d/errorjiang-admin-allow.conf}"
BACKUP_ROOT="${ERRORJIANG_ALLOW_BACKUP:-/data/errorjiang-backup}"
BEGIN_MARK="# errorjiang-allow-begin"
END_MARK="# errorjiang-allow-end"
# systemd-run 起的定时任务是脱离当前 shell 跑的，$0 可能是相对路径（./nginx-allow-ip.sh），
# 到点执行时找不到脚本，所以这里先定成绝对路径。
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

usage() {
  cat <<'EOF'
用法：nginx-allow-ip.sh <命令> [参数]

  list                      查看当前模式与白名单
  open [时长]               关闭白名单（任意网络都能访问管理员入口）；
                            带时长则到期自动恢复成 strict，适合临时去网吧等场景
  strict                    开启白名单（只允许名单内的 IP / 网段）
  add <IP|网段> [时长]      加白名单；带时长则到期自动移除
  remove <IP|网段>          从白名单移除，并取消它的自动移除任务

时长写法：数字 + s（秒）/ m（分钟）/ h（小时）/ d（天），例如 30m、2h、1d
EOF
}

die() { echo "错误：$*" >&2; exit 1; }

# 只接受 IPv4 / IPv4 掩码 / IPv6 / IPv6 掩码，避免把奇怪的字符串写进 nginx 配置
valid_ttl() {
  # 时长只认「数字 + s/m/h/d」。防手滑：写成 open --help 这类参数时直接拒绝，
  # 否则会被当成"带时长的 open"而先把白名单打开、再因定时器失败而报错。
  [[ "$1" =~ ^[0-9]+[smhd]$ ]]
}

valid_entry() {
  local value="$1" base mask octet
  if [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?$ ]]; then
    base="${value%%/*}"
    IFS='.' read -r -a octets <<<"$base"
    for octet in "${octets[@]}"; do
      (( octet <= 255 )) || return 1
    done
    if [[ "$value" == */* ]]; then
      mask="${value##*/}"
      (( mask <= 32 )) || return 1
    fi
    return 0
  fi
  if [[ "$value" == *:* && "$value" =~ ^[0-9A-Fa-f:]{2,45}(/[0-9]{1,3})?$ ]]; then
    if [[ "$value" == */* ]]; then
      mask="${value##*/}"
      (( mask <= 128 )) || return 1
    fi
    return 0
  fi
  return 1
}

backup_conf() {
  local stamp dir
  # 带上 pid：同一秒里跑两次（比如脚本调用脚本）不会撞进同一个备份目录互相覆盖
  stamp="$(date +%Y%m%d-%H%M%S)-$$"
  dir="$BACKUP_ROOT/allow-$stamp"
  mkdir -p "$dir"
  cp -a "$CONF" "$dir/errorjiang-admin-allow.conf"
  echo "$dir"
}

reload_nginx() {
  local backup="$1"
  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx
    echo "nginx 已 reload"
    return 0
  fi
  echo "nginx 配置检查失败，正在回滚…" >&2
  cp -a "$backup/errorjiang-admin-allow.conf" "$CONF"
  nginx -t >/dev/null 2>&1 || true
  die "已回滚到备份：$backup"
}

unit_name() {
  echo "errorjiang-allow-$(echo "$1" | tr -c 'A-Za-z0-9' '-')"
}

cmd_list() {
  local mode
  # 末尾 || true：set -e 下如果配置里没有 default 行，grep 非零退出会让整个脚本中断，
  # 原本该打印的「未知」就走不到了
  mode="$(grep -E '^[[:space:]]*default[[:space:]]+' "$CONF" 2>/dev/null | head -n1 | awk '{print $2}' | tr -d ';' || true)"
  echo "配置文件：$CONF"
  case "$mode" in
    1) echo "当前模式：白名单关闭（default 1，任意 IP 都能访问管理员入口）" ;;
    0) echo "当前模式：白名单开启（default 0，只允许下列 IP / 网段）" ;;
    *) echo "当前模式：未知（default=$mode）" ;;
  esac
  echo "白名单条目："
  sed -n "/$BEGIN_MARK/,/$END_MARK/p" "$CONF" |
    grep -v "$BEGIN_MARK" | grep -v "$END_MARK" | sed 's/^[[:space:]]*/  /'
}

REVERT_UNIT="errorjiang-allow-revert"

# open / strict 都先取消上一个「到期自动收回」任务，避免互相打架
cancel_revert() {
  systemctl stop "${REVERT_UNIT}.timer" 2>/dev/null || true
}

cmd_mode() {
  local value="$1" label="$2" ttl="${3:-}" backup
  if [[ -n "$ttl" ]] && ! valid_ttl "$ttl"; then
    die "时长格式不对：$ttl（写法：数字 + s/m/h/d，例如 30m、2h、1d）"
  fi
  cancel_revert
  backup="$(backup_conf)"
  sed -i -E "s|^([[:space:]]*default[[:space:]]+)[0-9]+;|\1${value};|" "$CONF"
  # sed 找不到匹配时会「成功但什么也没改」，这里必须确认真的改了，
  # 否则会一边报「已切换」一边 reload 一份没变过的配置。
  if ! grep -qE "^[[:space:]]*default[[:space:]]+${value};" "$CONF"; then
    die "配置里没找到 default 指令，模式没有改动（备份在 $backup，请检查 $CONF）"
  fi
  echo "$label"
  reload_nginx "$backup"
  if [[ -n "$ttl" ]]; then
    local action
    if [[ "$value" == "1" ]]; then action="strict"; else action="open"; fi
    systemd-run --collect --on-active="$ttl" --unit="$REVERT_UNIT" \
      /usr/bin/env bash "$0" "$action" >/dev/null
    echo "已安排 $ttl 后自动切回「$action」（systemd 单元：$REVERT_UNIT）"
  fi
}

cmd_add() {
  local entry="${1:-}" ttl="${2:-}" backup escaped
  [[ -n "$entry" ]] || die "用法：add <IP|网段> [时长]"
  valid_entry "$entry" || die "IP / 网段格式不对：$entry"
  if [[ -n "$ttl" ]] && ! valid_ttl "$ttl"; then
    die "时长格式不对：$ttl（写法：数字 + s/m/h/d，例如 30m、2h、1d）"
  fi
  # 把 . 转义：IP 里的点如果按正则通配符解释，
  # 想删/查 2.3.4.5 会连带命中 12.3.4.5 这种条目
  escaped="${entry//./\\.}"
  if sed -n "/$BEGIN_MARK/,/$END_MARK/p" "$CONF" | grep -qE "^[[:space:]]*${escaped}[[:space:]]"; then
    echo "$entry 已经在白名单里"
  else
    backup="$(backup_conf)"
    sed -i "/$END_MARK/i\\    ${entry} 1;" "$CONF"
    echo "已加入白名单：$entry"
    reload_nginx "$backup"
  fi
  if [[ -n "$ttl" ]]; then
    local unit
    unit="$(unit_name "$entry")"
    systemd-run --collect --on-active="$ttl" --unit="$unit" \
      /usr/bin/env bash "$SELF" remove "$entry" >/dev/null
    echo "已安排 $ttl 后自动移除（systemd 单元：$unit）"
  fi
}

cmd_remove() {
  local entry="${1:-}" backup unit escaped
  [[ -n "$entry" ]] || die "用法：remove <IP|网段>"
  valid_entry "$entry" || die "IP / 网段格式不对：$entry"
  escaped="${entry//./\\.}"
  unit="$(unit_name "$entry")"
  systemctl stop "${unit}.timer" 2>/dev/null || true
  backup="$(backup_conf)"
  sed -i "\|^[[:space:]]*${escaped}[[:space:]]\+1;|d" "$CONF"
  echo "已从白名单移除：$entry"
  reload_nginx "$backup"
}

case "${1:-}" in
  list) cmd_list ;;
  open) shift; cmd_mode 1 "白名单已关闭：任意 IP 都能访问管理员入口" "${1:-}" ;;
  strict) cmd_mode 0 "白名单已开启：只允许名单内的 IP / 网段" ;;
  add) shift; cmd_add "${1:-}" "${2:-}" ;;
  remove) shift; cmd_remove "${1:-}" ;;
  *) usage; exit 1 ;;
esac
