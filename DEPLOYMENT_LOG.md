# Error酱阿里云部署日志

这份日志记录 Error酱 从本地项目到阿里云上线的关键操作、成功结果、故障处理和当前遗留事项。后续每次进行重大部署、迁移、备份或安全配置后，都应追加记录。

不要在日志中写入密码、私钥、Token 或完整的 `auth.json` 内容。

## 1. 当前状态

更新日期：

```text
2026-10-07
```

公网访问：

```text
http://<服务器公网IP>
```

当前架构：

```text
浏览器
  -> 阿里云安全组 80
  -> Nginx
  -> 127.0.0.1:8000
  -> errorjiang.service
  -> /opt/errorjiang/app.py
  -> /opt/errorjiang/data
```

当前关键信息：

```text
系统：Ubuntu 26.04.1 LTS
应用目录：/opt/errorjiang
数据目录：/opt/errorjiang/data
服务名称：errorjiang.service
运行用户：errorjiang
Web 服务：Nginx 1.28.3
Python：3.14.4
Git 仓库：git@github.com:IslaGiftia/ErrorJ.git
当前提交：57ff940
Nginx 上传上限：client_max_body_size 84m
公网端口：80 已开放
HTTPS：未配置，443 未开放
自动备份：尚未确认安装
本地数据上传：尚未完成
```

当前验证结果：

```text
systemctl is-active errorjiang
active

curl -i http://127.0.0.1:8000/api/health
HTTP/1.1 200 OK
{"ok": true}

浏览器 http://<服务器公网IP>
正常显示 Error酱 登录页
```

## 2. 2026-09-28 至 2026-09-29 时间线

### 2.1 本地项目初始化

完成内容：

- 将本地 `<项目目录>` 初始化为 Git 仓库，默认分支为 `main`。
- 添加 `.gitignore`、`.dockerignore` 和 `.gitattributes`。
- 排除运行数据、密码、证书、缓存、日志和备份。
- 确认 Git 中只有 `data/.gitkeep`，没有提交真实数据库和上传文件。

本地源代码没有第三方 Python 依赖，主要运行环境是 Python 标准库和 SQLite。

### 2.2 阿里云 ECS 基础环境

服务器实际情况：

```text
Ubuntu 26.04.1 LTS
2 CPU
约 1.7GiB 内存
约 39GB 系统盘
VPC 内网 IP：<内网IP>
公网出口地址：<服务器公网IP>
```

完成内容：

- 安装并更新基础系统软件。
- 安装 Git、curl、wget、nano、unzip、Nginx 和 Docker。
- 配置服务器到 GitHub 的 SSH 密钥。
- 设置中国时区。
- 开放公网 80 端口。

### 2.3 Docker 部署尝试

最初尝试在 `/opt/ErrorJ` 使用 Docker Compose：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

遇到的第一个问题：

```text
required variable INVENTORY_PASSWORD is missing a value
```

处理：

```bash
echo "INVENTORY_PASSWORD=..." > .env
```

后来确认这个密码没有承接实际网站流量。

遇到的第二个问题：

```text
failed to resolve source metadata for docker.io/library/python:3.12-slim
i/o timeout
```

原因是国内服务器连接 Docker Hub 超时。

处理：

- 配置 Docker 镜像加速器。
- 镜像最终构建成功。

随后发现：

```text
127.0.0.1:8000 address already in use
```

原因是 systemd 服务已经占用 `8000`。

最终结论：

- Docker 容器没有端口映射。
- Docker 容器后来被删除。
- 网站流量由 systemd 提供，不是 Docker。

### 2.4 systemd 原生部署

活动部署目录：

```text
/opt/errorjiang
```

使用项目自带服务：

```text
deploy/errorjiang.service
```

启动：

```bash
systemctl enable --now errorjiang
```

遇到的权限问题：

```text
Failed at step CHDIR spawning /usr/bin/python3
status=200/CHDIR
```

原因是运行用户无法进入 `/opt/errorjiang`。

修复：

```bash
chown root:errorjiang /opt/errorjiang
chmod 750 /opt/errorjiang
chown -R errorjiang:errorjiang /opt/errorjiang/data
systemctl restart errorjiang
```

服务恢复正常：

```text
Active: active (running)
HTTP/1.1 200 OK
{"ok": true}
```

### 2.5 Nginx 反向代理

完成内容：

- Nginx 监听公网 80。
- 请求反向代理到 `127.0.0.1:8000`。
- 配置 `client_max_body_size 40m`。
- 配置真实客户端 IP 转发。
- `nginx -t` 检查成功。

已验证：

```bash
curl -i http://127.0.0.1/api/health
```

返回：

```text
HTTP/1.1 200 OK
{"ok": true}
```

公网访问：

```text
http://<服务器公网IP>
```

可以正常进入 Error酱 登录页。

### 2.6 数据检查

活动数据目录：

```text
/opt/errorjiang/data
```

历史 Docker 数据目录：

```text
/opt/ErrorJ/data
```

两边数据库的记录数相同，都是接近空库的默认状态：

```text
categories: 12
locations: 54
projects: 1
warehouse_types: 1
```

两个数据库文件哈希不同，但业务内容接近。当前网站固定使用 `/opt/errorjiang/data`。

本地 `<项目目录>\data` 比服务器当前数据库更大，尚未上传到服务器。

### 2.7 备份检查

手动备份成功：

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

已生成的备份：

```text
/data/errorjiang-backup/20260929-010426
/data/errorjiang-backup/20260929-094323
```

备份内容：

```text
inventory.db
files.tar.gz
```

当时服务器数据较小，因此备份约为 `256K`。

已确认：

- Docker 容器已经没有运行。
- `crontab -l` 曾显示 `no crontab for root`。
- 每天自动备份任务还没有确认安装。

### 2.8 GitHub 仓库切换

活动目录 `/opt/errorjiang` 最初的 remote：

```text
https://github.com/IslaGiftia/ErrorJiang.git
```

该仓库后来从 GitHub 删除。

服务器中仍然保留着当时的本地代码，因此删除远程仓库不会立刻导致网站停止。

为了改用当前仓库，执行：

```bash
cd /opt/errorjiang
git remote set-url origin git@github.com:IslaGiftia/ErrorJ.git
git fetch origin
git pull --ff-only
```

更新过程：

```text
08f62f2..e3dd260  main -> origin/main
Fast-forward
```

更新内容：

```text
.gitignore
DEPLOY.md
```

更新后的激活代码没有变化，服务正常重启：

```text
systemctl restart errorjiang
active
HTTP/1.1 200 OK
{"ok": true}
```

结论：

- `/opt/errorjiang` 仍然是活动目录。
- 目录名中的 `errorjiang` 只是历史名称。
- 当前代码来源已经切换为 `ErrorJ`。
- `ErrorJiang` 删除后不再影响服务器维护。
- `/opt/ErrorJ` 是另一份未运行的克隆目录。

### 2.9 游客访问与私有模块权限重构

完成内容：

- 首页改为公开访问，不再首先跳转登录页。
- 仓库、网页收藏、笔记、工作台四个模块继续要求管理员登录。
- 首页右上角新增“游客 / 已登录 / 本地模式”状态。
- 无权限模块入口保持普通外观，游客或普通账号点击后只提示“该模块仅管理员可以访问”。
- 游客访问私有模块时页面显示“登录后查看”，不再显示硬编码的“已入库 80 种元件”。
- 留言板、日常、游戏、参考项目、源码允许公开访问。
- 游客可以浏览和发布留言，但不能删除留言。
- 游客可以浏览日常，但发布、编辑、置顶和删除仅管理员可用。
- 笔记图片、元件图片、书签图标、工作台文件和 BOM 报告继续要求登录。
- 留言附件、日常配图、照片墙和音乐文件可通过 `/site-files/` 公开访问。

验证结果：

```text
游客访问 /inventory /bookmarks /notes /workbench -> 302 到登录页
游客访问 /api/dashboard -> 401
游客访问首页、留言、日常、提示词 -> 200
管理员登录后访问四个私有模块 -> 200
游客发布留言 -> 200
游客发布日常 -> 401
游客删除留言 -> 401
```

### 2.10 AI 提示词第一版

完成内容：

- 首页“Error酱动态”旁边新增“AI 提示词”入口。
- 新增公开页面 `/prompts`。
- 提供编程、调试、测试、Git、运维、电子、写作和学习等内置分类。
- 支持关键词搜索、分类筛选、展开和复制。
- 第一版为静态只读提示词库。

随后升级为数据库版本：

- 新增 `ai_prompts` 表，初始内容由 `static/prompts-seed.json` 在首次启动时导入。
- `GET /api/prompts` 公开，游客可浏览、搜索、展开和复制。
- `POST /api/prompts`、`PATCH /api/prompts/<id>`、`DELETE /api/prompts/<id>` 仅管理员可用。
- 管理员可新增、编辑、删除和置顶提示词。
- `/prompts` 页面加入首页同款下雨特效，并移除顶部品牌栏和返回按钮。
- 首页模块入口由“看Error酱的日常”改名为“Error酱动态”。

### 2.11 普通账号注册与审批

完成内容：

- 新增 `users` 表，保存用户名、密码哈希、审批状态和最后登录时间。
- 新增公开注册页 `/register` 和注册接口 `/api/register`，新账号默认状态为 `pending`。
- 新增服务器管理脚本 `tools/manage_users.py`。
- 管理员密码登录与普通账号登录共用 `/api/login`；管理员用户名留空。
- 已批准普通账号可以只读访问仓库和网页收藏。
- 普通账号不能修改仓库或网页收藏，不能访问笔记、工作台及其文件。
- 普通账号无法编辑 Error酱动态或 AI 提示词，不能删除留言。
- 仓库和收藏页显示只读提示，并隐藏新增、导入、编辑、删除等入口。
- 网页收藏链接继续使用新标签页打开。

服务器审批命令：

```bash
python tools/manage_users.py pending
python tools/manage_users.py approve <用户名>
python tools/manage_users.py reject <用户名>
python tools/manage_users.py disable <用户名>
python tools/manage_users.py reset-password <用户名>
python tools/manage_users.py create <用户名>
```

### 2.12 管理员专属权限收口

完成内容：

- 仓库、网页收藏、笔记、工作台和 AI 提示词统一为管理员专属模块。
- 游客访问私有页面会跳转登录页，普通账号会跳回首页并看到“仅管理员”提示。
- 游客访问私有 API 返回 401，普通账号返回 403。
- 首页五类管理员入口不显示锁图标或特殊锁定样式，点击后统一提示仅管理员可访问；旧的普通账号只读界面控制 `role-mode` 已移除。
- 默认提示词从公开静态目录 `static/prompts-seed.json` 移到非公开的 `config/prompts-seed.json`。

验证结果：

```text
guest /inventory /bookmarks /prompts -> 302 /login?next=...
member /inventory /bookmarks /prompts -> 302 /?access=owner-only
guest private APIs -> 401
member private APIs -> 403
owner private pages and APIs -> 200
public messages/moments/references/games -> 200
```

### 2.13 Word / PDF 转换依赖部署

问题原因：

- 线上服务器已经更新到包含文档导入接口的版本，但 systemd 使用的 `/usr/bin/python3` 尚未安装 `firecrawl-anydoc`，因此导入 Word / PDF 时提示转换组件未安装。

处理结果：

- 线上服务器安装固定版本 `firecrawl-anydoc==0.2.4`，随后重启 `errorjiang.service`。
- Windows 的 `run.bat` / `start-inventory.bat` 和 Linux 的 `run.sh` 现在会自动检查并安装 `requirements.txt`。
- 服务器维护手册的代码更新步骤已加入依赖安装命令。

### 2.14 Error酱推荐

完成内容：

- 首页新增“Error酱推荐”入口，位于“Error酱动态”和“AI 提示词”之间。
- 新增公开页面 `/recommendations`，支持网站、工具、电影和动漫四类内容。
- 网站和工具使用 16:9 截图卡片；电影和动漫使用 2:3 海报卡片。
- 管理员支持封面上传、新增、编辑、删除和置顶。
- 推荐网站可直接关联网页收藏，推荐页实时读取收藏标题、网址和图标。
- 数据保存在 `recommendations` 表，封面保存在 `data/recommend_images/`。

验证结果：

```text
游客浏览推荐页和 GET API -> 200
游客写入推荐 -> 401
普通账号写入推荐 -> 403
管理员上传封面和 CRUD -> 200
桌面端 -> 3 列独立错位布局
移动端 -> 单列布局
```

## 3. 当前尚未完成

### 3.1 每日自动备份

需要确认：

```bash
crontab -l
```

没有任务时安装：

```bash
(
  crontab -l 2>/dev/null | grep -vF '/opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup'
  echo '0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup >> /var/log/errorjiang-backup.log 2>&1'
) | crontab -
```

### 3.2 本地数据上传

本地数据：

```text
<项目目录>\data
```

目标：

```text
/opt/errorjiang/data
```

必须按维护手册第 9 节执行，上传前先备份服务器数据和本地数据。

### 3.3 HTTPS

需要准备：

- 域名
- ICP 备案
- DNS A 记录
- SSL 证书
- 安全组 443
- Nginx HTTPS 配置

在 HTTPS 完成前，登录密码会通过 HTTP 明文传输，不适合长期在不可信网络中使用。

### 3.4 阿里云快照和 OSS

需要开启：

- 云盘自动快照
- 备份文件同步到 OSS
- 定期下载备份到本地电脑

## 4. 当前验证命令

```bash
systemctl is-active errorjiang
systemctl is-active nginx

git -C /opt/errorjiang status --short --branch
git -C /opt/errorjiang remote -v

ss -lntp | grep ':8000'
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1/api/health

ls -lah /data/errorjiang-backup
crontab -l
```

## 5. 后续日志记录模板

每次操作后追加：

```text
日期：
操作人：
操作目的：

操作前状态：

执行的命令：

结果：

遇到的问题：

处理方式：

验证结果：

后续待办：
```

不要记录密码、私钥、Token 或会话密钥。

## 6. 2026-10-07 部署记录：上传进度、歌单改版与图标修复

```text
日期：2026-10-07 17:46 – 17:50（服务器本地时间）
操作人：Codex（本地提交推送 + 服务器执行）
操作目的：发布「全站上传进度、歌单页改版、地图分类图标修复、首页入口与标签页文字统一、
          上传体积上限提升」，并更新线上 Error酱动态的更新日志。
```

操作前状态：

- `/opt/errorjiang` 停在 `bceab0b`，`errorjiang.service` 与 `nginx` 都是 active，`/api/health` 返回 200。
- Nginx `client_max_body_size 40m`，应用 `MAX_REQUEST_BYTES = 40MB`。

执行的命令：

```bash
# 1) 本地提交并推送（本机 C:\lX.NeT）
git commit -m "feat: upload progress, music player rework and UI polish"   # 57ff940
git push origin main

# 2) 服务器：先备份，再拉取代码
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup        # 20261007-174616（46M）
cd /opt/errorjiang && git pull --ff-only                                   # bceab0b..57ff940
/usr/bin/python3 -m pip install --break-system-packages -r requirements.txt
/usr/bin/python3 -m py_compile app.py

# 3) Nginx 上传上限 40m -> 84m
cp -a /etc/nginx/sites-available/errorjiang.conf \
      /etc/nginx/sites-available/errorjiang.conf.bak-<时间戳>
sed -i "s/client_max_body_size 40m;/client_max_body_size 84m;/" \
      /etc/nginx/sites-available/errorjiang.conf
nginx -t && systemctl reload nginx

# 4) 重启并检查
systemctl restart errorjiang && sleep 3
curl -s http://127.0.0.1:8000/api/health

# 5) 更新线上动态（更新日志）
scp config/changelog-seed.json <服务器>:/opt/errorjiang/config/changelog-seed.json
# 先用 sqlite3 备份数据库到 /data/errorjiang-backup/inventory-before-changelog-20261007-1748.db
python3 tools/import_changelog_moments.py --seed config/changelog-seed.json \
        --date 2026-10-07 --force --dry-run
python3 tools/import_changelog_moments.py --seed config/changelog-seed.json \
        --date 2026-10-07 --force
```

结果：

- 服务 active，`http://127.0.0.1:8000/api/health` 和 `http://127.0.0.1/api/health` 都返回 200 `{"ok": true}`。
- 标签页文字线上生效：`/messages` 留言板、`/games` 游戏、`/music` 歌单、`/moments` 动态、
  `/recommendations` 推荐、`/map` 足迹（地图对游客仍按权限 302 到登录页）。
- 地图分类图标的一次性修复已随启动执行：`app_meta` 里写入了 `map_glyph_follow_fix_v1`，
  服务器上的「酒店 + 新」「网吧 + 新」都换成了名字首字，剩余不一致的占位图标为 0。
- 线上动态 id=15 的 2026-10-07 更新日志覆盖为「工作台日志、上传进度与歌单改版」
  （903 字，17:43:00），公开接口能读到标题和新增条目。

遇到的问题：

- 生成数据备份时用 heredoc 拼接时间戳，被外层引号吃掉，产生了一个名字里带空格的备份文件。

处理方式：

- 删除那个文件，改由 Python 内部用 `datetime` 生成时间戳，重新生成
  `/data/errorjiang-backup/inventory-before-changelog-20261007-1748.db`。

验证结果：

```text
systemctl is-active errorjiang   -> active
curl /api/health（8000 / Nginx）  -> 200 {"ok": true}
/messages /games /music /moments /recommendations -> 留言板 / 游戏 / 歌单 / 动态 / 推荐
grep <title> static/map.html     -> 足迹
map_categories 残留占位图标       -> 0
moments id=15                    -> 2026-10-07 17:43:00，903 字
```

后续待办：

- 在浏览器里实际走一遍大文件上传（音乐 60MB、工作台固件 30MB、笔记 Word/PDF），确认进度、取消和
  服务器解析阶段的表现。
- `/etc/nginx/sites-available/errorjiang.conf.bak-*` 保留几天后可清理。

## 7. 2026-10-07 安全修复与部署加固

```text
日期：2026-10-07 21:20 – 21:40（服务器本地时间）
操作人：Codex
操作目的：根据服务器日志和代码安全检查结果，修复安全问题并完成部署加固。
```

完成内容：

- 修复了文件访问、账号操作和代理访问处理中的安全问题。
- 收紧了应用、Nginx、systemd、备份目录和数据目录的权限配置。
- 轮换了会话签名密钥，现有登录需要重新登录一次。
- 保留原有功能，补充了安全回归测试。

验证结果：

```text
errorjiang / nginx                     -> active
/api/health（Nginx）                   -> 200 {"ok": true}
关键权限访问路径                        -> 已按预期拒绝或放行
本地安全回归测试                        -> 6 tests OK
日志与历史备份抽查                      -> 未发现外部的成功异常访问痕迹
```

后续待办：

- 域名备案完成后配置 HTTPS，并强制跳转 HTTPS。

## 8. 2026-10-07 首页细节修复与更新日志补录

完成内容：

- 修复首页 HUD 的 PING 状态颜色显示。
- 游客地图入口改为网格预览，不展示地图地址信息。
- 补录本次安全加固和首页修复到 Error酱动态更新日志。

验证结果：

```text
首页 HUD 状态颜色              -> 正常
游客地图入口                   -> 仅网格预览
Error酱动态                    -> 已补录
```
