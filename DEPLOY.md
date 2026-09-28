# 部署到阿里云（公网）指南

Error酱 原本是按“可信局域网自用”设计的：默认**没有登录、没有限流、服务监听 0.0.0.0**。
放到公网之前，请按本文档把这几件事补上；否则任何能访问到的人都可以读改删你的数据。

---

## 1. 快速开始（Docker，推荐）

```bash
# 服务器上：装好 Docker 与 compose 插件
git clone <你的仓库> /opt/errorjiang && cd /opt/errorjiang

# 设置访问密码后启动（只监听 127.0.0.1，公网由 Nginx 转发）
INVENTORY_PASSWORD='换成一个复杂密码' docker compose -f docker-compose.prod.yml up -d --build

docker compose -f docker-compose.prod.yml logs -f   # 看日志
```

数据都在 `./data`，升级时 `git pull` 后重新 `up -d --build` 即可，数据不会丢。

---

## 2. 访问密码（登录保护）

**方式 A：环境变量**（适合 Docker / systemd）

```bash
INVENTORY_PASSWORD='你的密码' python app.py
```

**方式 B：写进数据库目录**（适合裸机运行，密码只存哈希）

```bash
python tools/set_password.py          # 交互式输入
python tools/set_password.py --clear  # 取消密码，恢复免登录
```

启用后：

- 未登录访问任何页面都会跳到 `/login`
- 未登录调用 `/api/*` 返回 `401 {"error": "请先登录。"}`
- 退出登录：访问 `/logout`
- 输错 5 次锁定 5 分钟（按 IP）
- 会话 Cookie 是 HttpOnly + SameSite=Lax；走 HTTPS 时自动加 `Secure`（Nginx 传 `X-Forwarded-Proto`）

> 没有设置密码时，服务照旧免登录运行（局域网自用不受影响），启动日志里会打印提醒。

---

## 3. Nginx + HTTPS

示例配置见 [`deploy/nginx-errorjiang.conf`](deploy/nginx-errorjiang.conf)：反向代理 + 安全响应头 + 登录接口限流 + 上传体积上限。

```bash
sudo cp deploy/nginx-errorjiang.conf /etc/nginx/conf.d/errorjiang.conf
sudo nginx -t && sudo systemctl reload nginx

# 证书：certbot（Let's Encrypt）
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d errorjiang.example.com
```

要点：

- 应用只监听 `127.0.0.1:8000`，**阿里云安全组只放行 80 / 443**，8000 不对外
- 大陆服务器用域名要备案；只用 IP 访问可以免备案，但没有 HTTPS，浏览器会提示不安全
- 反代时给应用加 `INVENTORY_TRUST_PROXY=1`，这样限流和日志拿到的是真实客户端 IP

---

## 4. 不用 Docker（systemd）

```bash
sudo useradd -r -s /bin/bash errorjiang
sudo mkdir -p /opt/errorjiang && sudo chown errorjiang:errorjiang /opt/errorjiang
# 把代码放进 /opt/errorjiang，然后：
echo 'INVENTORY_PASSWORD=你的密码' | sudo tee /etc/errorjiang.env >/dev/null
sudo chmod 600 /etc/errorjiang.env
sudo cp deploy/errorjiang.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now errorjiang
sudo journalctl -u errorjiang -f
```

---

## 5. 备份

```bash
bash tools/backup_linux.sh                 # 默认备份到 ../errorjiang-backup，保留 14 份
bash tools/backup_linux.sh /data/backup    # 指定目录
crontab -e                                 # 每天 3 点备份
# 0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh >> /var/log/errorjiang-backup.log 2>&1
```

脚本用 SQLite 官方 backup API 做一致性快照（服务运行中也能安全备份），再把上传文件打包。
想再稳妥一层：`ossutil cp -rf` 同步到 OSS，并给 ECS 磁盘开自动快照。

---

## 6. 环境变量清单

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `INVENTORY_HOST` | `0.0.0.0` | 监听地址，公网部署建议 `127.0.0.1` |
| `INVENTORY_PORT` | `8000` | 监听端口 |
| `INVENTORY_PASSWORD` | 空 | 设置后启用登录保护（优先于 auth.json） |
| `INVENTORY_SECRET` | 自动生成 | 会话签名密钥，多实例部署时必须一致 |
| `INVENTORY_TRUST_PROXY` | 关 | 置 1 时读取 `X-Forwarded-For` / `X-Forwarded-Proto` |
| `INVENTORY_SECURE_COOKIES` | 关 | 强制 Cookie 带 `Secure`（HTTPS） |
| `INVENTORY_ACCESS_LOG` | 关 | 置 1 输出访问日志到 stdout |
| `TZ` | 容器内 UTC | 设成 `Asia/Shanghai`，否则留言/笔记时间会差 8 小时 |

---

## 7. 部署后这些功能会变样

- **日常（说说）**：纯站内内容，云上运行没有影响；配图和留言附件一样存在 `data/` 里，注意云盘容量和备份。
- **浏览器串口 / ESP 在线烧录**：需要 HTTPS + 桌面版 Chrome/Edge，且 USB 设备要插在你当前这台电脑上，云端部署不适用。
- **Firefox 书签导入**：读取的是 `%APPDATA%`（Windows 路径），Linux 服务器上没有。
- **`start-inventory.bat` / `autostart.vbs` / `backup.ps1`**：Windows 专用，服务器上改用 systemd + `tools/backup_linux.sh`。
- **LCSC 图片抓取脚本**：依赖浏览器环境，云上无头运行要先装 Playwright 依赖，或者干脆手动传图。

---

## 8. 常见问题

**时间差 8 小时**
容器里默认 UTC。`docker-compose.prod.yml` 已经带了 `TZ=Asia/Shanghai`，裸机用 systemd 时在 unit 里加 `Environment=TZ=Asia/Shanghai`。

**`database is locked`**
已默认开启 WAL + `busy_timeout=5000`。如果磁盘在 NFS 上，SQLite 会不稳定，请把 `data/` 放在本地盘。

**图标还是旧的**
浏览器会缓存 favicon：`Ctrl+F5`，或者清掉该站点的缓存。全站图标现在统一是 `/static/site/error-chan-favicon.png`。

**忘记密码**
`python tools/set_password.py --clear` 清掉密码，或者删掉 `data/auth.json` 后重启。

---

## 9. 迁移检查清单

1. 服务器安装 Docker + compose
2. 安全组：只开 22 / 80 / 443
3. 传代码 + 拷 `data/`（先在副本上演练一遍）
4. 设置 `INVENTORY_PASSWORD`
5. 起服务，确认 `curl -I http://127.0.0.1:8000/api/health` 正常
6. 配 Nginx + HTTPS + `INVENTORY_TRUST_PROXY=1`
7. 配 systemd 自启或 compose `restart: unless-stopped`
8. 配 `tools/backup_linux.sh` 定时任务 + OSS/快照
9. 浏览器访问域名，确认登录、留言、日常都正常
