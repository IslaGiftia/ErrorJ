# Error酱阿里云部署日志

这份日志记录 Error酱 从本地项目到阿里云上线的关键操作、成功结果、故障处理和当前遗留事项。后续每次进行重大部署、迁移、备份或安全配置后，都应追加记录。

不要在日志中写入密码、私钥、Token 或完整的 `auth.json` 内容。

## 1. 当前状态

更新日期：

```text
2026-10-08
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

## 9. 2026-10-07 首页地图入口体验优化

完成内容：

- 游客地图入口接入浅色静态底图，暗色模式使用同一底图的滤镜和遮罩，位置不变。
- 首页地图入口悬停文案改为「足迹」。
- 登录后地图入口自动刷新为真实地图，不再需要强制刷新。
- README 和 Error酱动态同步更新。

验证结果：

```text
游客地图入口                   -> 无在线瓦片请求，浅色 / 暗色位置一致
登录后地图入口                 -> 自动刷新
PING 深色主题状态              -> 正常 / 警告 / 异常颜色正确
```

## 10. 2026-10-07 首页动态、留言文案与备案占位

完成内容：

- 全站用户可见的「留言板」统一改为「留言」。
- 首页字体说明下移，并新增备案占位信息。
- 首页左下角新增近 7 天公开内容动态滚动列表。
- 游客只显示「普通用户 / 管理员」署名，登录用户可看到普通用户的登录用户名。
- 管理员的新留言和待审附件提醒会高亮闪烁，阅读或处理后自动消失。

验证结果：

```text
公开动态接口                  -> 游客 / 管理员返回符合权限
首页动态列表                  -> 桌面端显示，移动端隐藏
管理员提醒                    -> 新留言和待审附件可闪烁，处理后消失
留言文案                      -> 首页、标题和标签页统一为「留言」
```

## 11. 2026-10-08 首页帧率与动态滚动优化

完成内容：

- 雨滴动画的落点检测从 20Hz 降到 5Hz，并在后台标签页暂停检测，减少布局计算。
- 首页动态滚动列表不再每帧读取 `scrollHeight` / `clientHeight`。
- HUD 在标签页切回时重置帧计数，避免把后台恢复后的第一秒误报成低帧率。

验证结果：

```text
首页平均帧率                   -> 59 / 60 FPS（屏幕刷新率上限）
雨滴开启 / 关闭的帧间隔       -> 稳定，无持续长帧
动态列表                      -> 正常滚动，暂停与恢复状态正常
```

## 12. 2026-10-08 首页动态、模块标题与 2K 布局细节

完成内容：

- 首页公开动态改为 7 条可视记录，时间戳使用 `「」` 包裹，时间戳和用户名取消加粗。
- 管理员未读留言、待审附件提醒正文改为 PING 同款绿色，取消闪烁，时间戳和用户名保持普通主题色，处理后消失。
- 公开动态来源覆盖留言、游戏、歌单、书架、动态和推荐，按最近 7 天倒序显示。
- 手机端不显示动态面板和 PING / FPS，PC 端保持显示；参考项目页同步更新。
- 仓库、书签、笔记、留言、游戏、歌单、动态和推荐模块页标题统一为首页入口文字。
- 优化 2K / 125% 缩放下的首页纵向布局：内容组整体略向上移动，并拉大标题、简介、主入口、次入口和参考链接之间的间距；页脚说明和备案信息固定在底部。

验证结果：

```text
首页主线程帧率              -> 约 60 FPS（测试环境）
动态列表                    -> 7 条可视记录，合成层滚动，上下渐隐
管理员提醒                  -> 绿色，不闪烁，处理后消失
手机端                      -> 不显示动态面板和 PING / FPS
模块标题                    -> 首页入口与模块页一致
2K / 125% 缩放              -> 内容组略上移，分组间距增大
移动端                      -> 不显示动态面板
```

## 13. 2026-10-08 游客书架、IP 属地与图片上传修复

完成内容：

- 书架游客视图只显示书名和作者，不显示阅读进度、文件大小和“最近阅读”排序；登录账号保持原视图。
- 留言和动态的 IP 属地增加海外兜底解析：国内显示省份，国外显示中文国家或地区。
- 首页左下角动态改为固定三列左对齐，两处列间距均统一为 `6px`。
- 修复手机相册图片扩展名与真实格式不一致导致的上传失败；服务端按文件头识别真实图片格式，并使用正确的存储扩展名和 MIME 类型。
- 继续拒绝伪装成图片的非图片文件，不影响原有附件安全校验。

验证结果：

```text
游客书架                    -> 只显示书名和作者，无进度和文件大小
登录书架                    -> 进度和文件大小保持显示
国内 IP 属地                -> 省份，例如「江苏」
海外 IP 属地                -> 国家 / 地区，例如「美国」
首页动态                    -> 三列左对齐，列间距均为 6px
JPEG 扩展名为 PNG           -> 可上传，内部按 image/jpeg 和 .jpg 保存
伪造图片                    -> 继续拒绝
自动化测试                  -> 15 / 15 通过
```

## 14. 2026-10-08 首页日志静态展示与提醒优化

完成内容：

- 首页左下角日志改为静态显示最多 9 条，统一按 `created_at` 时间倒序排列。
- 未读留言和待审附件提醒不再插队，严格按照自身时间参与排序；若提醒是最新记录，则自然显示在最上面。
- 时间戳、用户名和日志内容之间取消额外间距，三列间距改为 `0px`。
- 提醒正文保持 PING 同款绿色，并使用与「留言」「工作台」按钮相同的 `3.6s ease-in-out infinite` 呼吸动画。
- 移除滚动、轨道复制和上下渐隐效果。
- 双击日志区域可以在当前页面隐藏，刷新 Error酱首页后恢复显示。

验证结果：

```text
静态条数                    -> 最多 9 条
排序                        -> 严格按时间倒序，提醒不插队
字段间距                    -> 0px
提醒动画                    -> activityAlertPulse 3.6s ease-in-out
滚动 / 渐隐                 -> 已移除
双击隐藏                    -> 当前页面生效
刷新恢复                    -> 正常
自动化测试                  -> 15 / 15 通过
```

## 15. 2026-10-08 参考项目、限时分享与下载申请

完成内容：

- 新增参考项目数据库和管理员 CRUD；现有静态条目首次启动自动迁移，普通访客保持只读。
- 新增通用限时分享链接，覆盖电子书、本地上传歌曲、工作台资料和固件。
- 分享链接支持常用时长和自定义过期时间，服务端执行过期校验，并支持公开下载与 HTTP Range。
- 新增电子书和本地上传歌曲的逐账号下载申请；批准后仅申请账号永久可下载，管理员可以撤销。
- 外部歌曲链接和外部推荐链接不进入申请流程；推荐模块暂无本地文件上传，因此不增加推荐下载申请。
- 工作台严格仅管理员可访问，普通账户的旧工作台权限、工作台 API 和 `data/workbench/` 文件全部拒绝。
- 工作台新增独立「下载申请」页面和徽标；首页工作台入口汇总待审注册、附件和下载申请数量。
- 新增「新的下载申请」Webhook 开关；首页管理员提醒聚合为未读留言、待审核附件和下载申请。
- 参考项目、分享、申请、批准、拒绝、撤销和普通用户下载全部记录到工作台日志。

验证结果：

```text
参考项目 CRUD               -> 新增 / 编辑 / 删除正常
分享链接                    -> 公开下载正常，过期与撤销服务端校验
分享下载 Range              -> HTTP 206，文件名和下载头正确
普通账户申请                -> 按账号和文件独立保存
批准 / 撤销                 -> 永久授权与立即失效正常
工作台权限                  -> 普通账户和游客均拒绝
原始文件直链                -> 电子书与歌曲目录返回 403
首页聚合提醒                -> 未读留言 / 待审附件 / 下载申请
下载申请 Webhook            -> 独立事件开关
自动化测试                  -> 21 / 21 通过
```

## 16. 2026-10-08 歌曲页面操作按钮布局修复

完成内容：

- 修复歌曲页面管理员操作按钮向左溢出、遮挡歌曲时长的问题。
- 管理员操作区按四个按钮的实际宽度预留 `132px`，普通账号单按钮操作区预留 `36px`。
- 手机宽度下同步缩小按钮和预留列宽，避免分享、下载、编辑、删除按钮继续覆盖歌曲信息。

验证结果：

```text
1475px 宽度                  -> 时长与操作区无重叠
1000px 宽度                  -> 时长与操作区无重叠
720px 宽度                   -> 时长与操作区无重叠
560px 宽度                   -> 时长与操作区无重叠
管理员四按钮                 -> 完整显示在行内
```

## 17. 2026-10-08 用户名脱敏与移动端播放修复

完成内容：

- 游客视角下，首页动态和留言中的普通账号用户名只保留最后一个字符，其余替换为星号；管理员仍显示为「管理员」。
- 登录的普通账号和管理员仍可看到完整用户名。
- 首页左下角日志行间距缩小到 `2px`，鼠标悬停显示「双击隐藏」。
- 歌曲页面的分享、下载、编辑和删除按钮改为常驻显示。
- 下载申请弹窗精简为「向管理员申请下载『文件名』？」。
- 登录页注册入口文案改为「申请注册账号」。
- 音频流接口支持 HEAD 请求，并为旧记录自动回填时长；前端监听 `durationchange`，移动端不再持续显示 `0:00`。

验证结果：

```text
用户名脱敏                  -> 牛大能 / **能
游客动态与留言              -> 已登录用户显示完整用户名
首页日志间距                -> 2px
首页日志悬停                 -> 双击隐藏
歌曲操作按钮                -> 常驻显示
下载申请弹窗                -> 仅保留申请提示
移动端音频                  -> duration 228.7 秒，显示 3:48
音频 HEAD                   -> HTTP 200，包含长度与 Range 支持
自动化测试                  -> 24 / 24 通过
```

## 18. 2026-10-08 足迹动态与地图入口优化

完成内容：

- `map_place_create` 纳入首页公开动态，显示为「新增了一个足迹」，不泄露地点名称和地址。
- 地图新增、编辑、删除后写入本地刷新信号。
- 首页地图圆盘在页面恢复显示、标签页重新可见和跨标签刷新时自动重新请求地图数据。
- 删除首页地图入口的网格覆盖层和「N」标记，游客、普通账户和管理员统一生效。

验证结果：

```text
新增足迹动态                -> 管理员 / 普通用户名 + 新增了一个足迹
地点隐私                    -> 不公开名称与地址
地图圆盘刷新                -> pageshow / visibility / storage 均触发
网格线与 N                  -> 静态和 DOM 中均不存在
全身份模式                  -> 游客 / 普通账户 / 管理员统一
自动化测试                  -> 24 / 24 通过
```

## 19. 2026-10-08 工作台上传限制设置

完成内容：

- 工作台新增「上传限制」视图（仅管理员可见），按类别统一调整留言附件、动态图片、歌曲、电子书、照片墙、推荐封面、足迹照片、笔记图片、笔记导入文档、工作台源码 / 固件 / 文档 / 图片 / 其他文件和仓库元件图片的数量与大小上限，支持逐项恢复默认。
- 限制存进 `app_meta.upload_limits_v1`，修改写入内容事件和管理审计；新增公开只读接口 `/api/site/upload-limits`，工作台接口 `/api/admin/upload-limits` 仅管理员可访问。
- 后端所有上传路径（留言、动态、歌曲、电子书、照片墙、推荐封面、足迹照片、笔记图片与文档导入、工作台文件、元件图片）统一读取当前配置；单文件上限 1KB–60MB、数量 1–100，受 84MB 请求体上限约束。
- 前端新增 `static/site/upload-limits.js`，留言、动态、歌单、书架、足迹、笔记、推荐和工作台页面会读取配置更新提示文案与上传前校验，接口不可用时回退到内置默认值。
- 修复工作台限制面板引用未定义常量导致的渲染报错、事件未绑定，以及工作台文件上传写死 30MB 的问题；文档导入的内嵌图片超过当前上限时跳过该图而不是整篇失败；限制小于 1MB 时提示不再显示为 0MB。

验证结果：

```text
上传限制接口                -> /api/site/upload-limits 公开只读，/api/admin/upload-limits 仅管理员
默认值                      -> 15 类限制与原有硬编码一致
保存与恢复默认              -> 写入后公开接口同步生效，恢复默认可回落
超范围拒绝                  -> 超过 60MB / 100 个返回 400
页面提示联动                -> 留言、动态、歌单、足迹实测随设置更新
自动化测试                  -> 32 / 32 通过
```

## 20. 2026-10-09 注册申请提醒与足迹标题

完成内容：

- 首页左下角公开动态补充管理员提醒：存在待审核注册申请时显示「有 N 个待审核注册申请」，按最新一条申请的时间参与排序，审核（通过 / 拒绝 / 删除）后自动消失；提醒只有管理员看得到，游客和普通账号拿到的接口数据里没有管理员提醒项。
- 足迹页（`/map`）侧栏标题由「Error酱地图」改为「Error酱足迹」，与首页入口文字保持一致。
- 修正部署日志第 19 节与第 18 节的排列顺序。

验证结果：

```text
注册申请提醒                -> 管理员接口返回 alert 项，处理完自动消失
游客与普通账号              -> 接口不返回任何管理员提醒
足迹侧栏标题                -> 显示「Error酱足迹」
自动化测试                  -> 34 / 34 通过
```

## 21. 2026-10-09 留言与动态互动（点赞、评论、提醒）

完成内容：

- 新增 `content_likes` 表：留言（含回复）和动态都支持点赞，登录账号可以点赞 / 取消点赞，数量对所有访客可见，自己给自己点赞不会产生提醒；删除留言或动态时同步清理点赞记录。
- 新增 `moment_comments` 表：动态支持评论与一层回复，登录账号（含普通账号）可以评论和回复，评论作者和管理员可以删除评论，删除主评论会连带删除回复，评论不公开 IP 属地。
- 新增 `user_notifications` 表：普通账号会收到属于自己的互动提醒——管理员发布新动态、留言被点赞、留言被回复、动态评论被回复；首页左下角出现绿色呼吸提醒，「留言」「动态」入口同步呼吸并显示未读数，打开对应页面后自动清零。管理员不接收这类提醒。
- 留言 / 动态列表接口返回 `like_count`、`liked` 和评论数据；动态页新增点赞按钮、评论区、回复表单和删除入口，留言页新增点赞按钮。
- 管理员发布动态时，公开动态文案统一为「更新了一条动态」；管理员自己在左下角只看到这条普通记录，不带绿色闪烁和角标。

验证结果：

```text
点赞切换                    -> 计数 1 / 0 往返，重复点赞按主键去重
提醒写入                    -> 被点赞 / 被回复的普通账号收到未读提醒，自助点赞不提醒
新动态提醒                  -> 已批准普通账号收到，待审账号和站长不收到
已读清零                    -> 打开留言 / 动态页后提醒与角标消失
动态评论                    -> 评论、回复、删除均生效，删除主评论连带回复
浏览器实测                  -> 点赞计数 1、评论与回复渲染、普通账号首页呼吸 + 角标 + 绿色提醒，阅读后清零
自动化测试                  -> 40 / 40 通过
```

## 23. 2026-10-09 留言互动、通知文案与分享体验优化

完成内容：

- 留言和回复的点赞会在爱心旁边直接列出点赞人的用户名（多人时显示前三个人 + 等 N 人），游客视角沿用用户名脱敏规则。
- 回复支持楼中楼：每条回复下面都有「回复」按钮，回复某条回复时显示「回复 @某某」，通知发给被回复的人。
- 留言页和动态页新增卡片级提醒：收到新点赞 / 回复后对应卡片按首页按钮的 3.6 秒节奏呼吸闪烁，鼠标移入即标记已读并停止；提醒卡片在屏幕下方时右下角出现向下箭头，点击平滑跳转。
- 通知文案统一：直接回复留言提示「回复了你的留言」，回复回复提示「回复了你」，评论动态（含回复动态评论）提示「评论了你的动态」；新增「新的动态评论」Webhook 事件（默认开启，可在工作台关闭），站长自己的站内提醒通道同时打通。
- 「公开 IP 属地」复选框默认不勾选，需要用户主动勾选才会公开。
- 分享按钮的悬停提示从「生成限时分享链接」统一改成「分享」；三选一分享弹窗改为跟随浅色 / 暗色主题，并固定面板最小高度，切换选项时窗口不再忽大忽小。
- 笔记分享阅读页补上章节大纲：可展开的章节列表、随滚动更新的面包屑、点击章节跳转；阅读页改成整页滚动，sticky 大纲正常生效。
- 游客点击动态里的音乐分享卡片时提示「请登录后播放」，不再直接播放。

验证结果：

```text
点赞名单                    -> 爱心旁显示用户名，游客脱敏
楼中楼回复                  -> 分组正确，reply_to 显示「回复 @某某」，通知文案「回复了你」
卡片呼吸                    -> 悬停后 is-fresh 移除，对应提醒写 seen_at
跳转箭头                    -> 卡片在下方时出现，点击后滚动到位并自动隐藏
动态评论提醒                -> 站长收到「评论了你的动态」，未读目标可在动态页高亮
分享弹窗                    -> 三种模式高度均为 301px，暗色模式背景 rgb(38,38,38)
分享按钮提示                -> 书架 / 歌单 / 工作台均显示「分享」
笔记大纲                    -> 4 节大纲可展开，点击后路径更新为「标题 › H1 › H2 › H3」
游客音乐卡片                -> 提示「请登录后播放」，不进入播放态
自动化测试                  -> 52 / 52 通过
```

## 24. 2026-10-09 分享音乐卡片与笔记阅读页优化

完成内容：

- 动态里的音乐分享卡片恢复为游客也能直接播放：去掉「请登录后播放」的限制，点封面或播放按钮都会播放 / 暂停。
- 播放按钮从封面遮罩改成独立圆形按钮，放在专辑缩略图右侧的空白区域并垂直居中（`margin-left: auto` + `align-self: center`），播放时按钮变主题色实心并显示暂停图标。
- 分享出去的笔记阅读页（`/notes/read`）补上和笔记页一致的标题区自动收起：向下滚动时面包屑 + 标题区向上滑出，章节大纲条自动贴到屏幕顶部；向上滚动时标题区滑回；回到顶部始终显示；点章节跳转时先显示标题区并暂停自动收起 700ms。
- 面包屑和标题合并进同一个 sticky 容器，收起动画连续、正文不会跳动。

验证结果：

```text
游客播放                    -> 未登录点击播放按钮起播，按钮变暂停态，控制台无报错
播放按钮位置                -> 卡片中心 Y=782、按钮中心 Y=782；按钮右边缘 967、卡片右边缘 980
笔记标题收起                -> 滚到 700：is-hidden、位移 -108.65px、大纲 top=0
笔记标题展开                -> 上滚到 400：恢复显示、--nt-read-top-h=109px、大纲 top=109px
回到顶部                    -> 标题区始终显示
自动化测试                  -> 52 / 52 通过
```

## 25. 2026-10-09 目录导航吸顶与动态点赞优化

完成内容：

- 修复分享笔记阅读页的章节目录条不吸顶的问题：`.nt-read-outline` 的 `position: sticky` 被文件后面同权重的 `.nt-outline { position: relative }` 覆盖，改为 `.nt-outline.nt-read-outline` 提高权重；现在向下滚动只收起面包屑和标题区，目录条贴到屏幕最上方，向上滚动标题区滑回、目录条落到标题下方，始终常驻。
- 动态点赞补上点赞人用户名：`api_moments` 返回 `like_users`，前端在爱心右边显示最多三个人（更多人显示「等 N 人」），游客视角按全站规则脱敏，站长显示「管理员」。
- 动态评论支持点赞，排列顺序对齐留言板：昵称 + 时间 → 正文 → 爱心 + 数量 + 点赞人用户名 → 回复 / 删除 → 子回复。
- 评论被点赞时给评论作者发提醒「点赞了你的评论」（进「动态」入口的角标和卡片呼吸高亮）。

验证结果：

```text
目录条吸顶                  -> 顶部 top=145；下滚 600 时 top=0 仍可见；上滚 300 时 top=109
动态点赞名单                -> like_users 返回用户名，游客脱敏，站长显示管理员
评论点赞                    -> 点击后名单 memberx → 管理员、memberx，数量 1 → 2
评论点赞提醒                -> kind=comment_like，module=moments，指向所属动态
自动化测试                  -> 55 / 55 通过
```

## 26. 2026-10-09 首页页脚展示 ICP 备案号

完成内容：

- 首页页脚的占位文案（原「秦ICP备2333-1 备案中」）替换为工信部核发的正式编号「陕ICP备2026028018号-1」，与备案审核通知完全一致。
- 按备案要求把备案号放在网站首页底部，并超链接到工信部备案管理系统 `https://beian.miit.gov.cn/`（新标签页打开，带 `noopener noreferrer`）。
- 补充页脚链接样式：默认沿用页脚淡灰色、不抢眼，鼠标悬停变主题色并加下划线。

验证结果：

```text
编号文案        -> 陕ICP备2026028018号-1
链接地址        -> https://beian.miit.gov.cn/
打开方式        -> target=_blank + rel=noopener noreferrer
占位清理        -> 全站已无「备案中」残留
```

## 22. 2026-10-09 站内分享（动态卡片、站内资源推荐）

完成内容：

- 新增 `moment_shares` 表：一条动态最多挂一张分享卡片，卡片只记录资源类型和 ID，展示时实时查询原内容，资源被删除后卡片自动显示「内容已失效」。
- 分享按钮改为三选一：分享到动态、分享到推荐页、生成外部下载链接；电子书、歌曲、学习笔记三个类型支持前两项，资料和固件保持原来的限时链接。
- 「分享到动态」会新发一条动态（可附文字，可留空），并走普通的新动态提醒；「分享到推荐」在 `recommendations` 表新增 `resource` 类型，进入推荐页新的「站内资源」分类，旧的推荐编辑器不会生成这类卡片。
- 新增只读阅读页：`/notes/read?id=` 复用笔记的 Markdown 渲染和样式，带「首页 / 笔记 / 标题」面包屑，不带列表、标签和编辑按钮；`/books/shared?id=` 复用书架阅读器，目录、搜索、书签、批注、阅读设置和进度记忆与书架一致，两者都要求登录（游客只看得到卡片）。
- 动态里的音乐卡片是朋友圈风格的小卡片：点击封面播放、再点暂停，同一时间只播一首，游客也能播放。
- 新增接口：`POST /api/admin/share-content`（管理员）、`GET /api/shared/notes/<id>`、`GET /api/shared/books/<id>`、`GET /api/shared/books/<id>/content`；共享阅读接口只在资源确实被分享过（动态卡片或站内资源推荐）时才放行。

验证结果：

```text
分享接口                    -> 笔记/歌曲分享到动态、电子书分享到推荐均返回成功
动态卡片                    -> 笔记卡片显示「阅读」，歌曲卡片显示播放按钮，点击播放/暂停正常
笔记阅读页                  -> 面包屑 + Markdown 正文渲染正确，无控制台报错
电子书分享阅读              -> 复用书架阅读器，目录能解析出章节，进度条 100%
推荐页                      -> 新增「站内资源」分类与统计，资源卡片带去歌单 / 阅读入口
失效处理                    -> 删除原笔记后卡片 available=false（单元测试覆盖）
自动化测试                  -> 46 / 46 通过
```

## 27. 2026-10-09 管理员入口 IP 白名单（方案 A）

完成内容：

- 新增 `/etc/nginx/conf.d/errorjiang-admin-allow.conf`（仓库模板 `deploy/nginx-errorjiang-admin-allow.conf`）：用 `geo` 定义管理员白名单变量 `$errorjiang_admin_ok`，用 `map` 从 `X-Forwarded-For` 提取真实客户端 IP 到 `$errorjiang_real_ip`。
- 站点对公网继续开放（首页、留言、动态、推荐、音乐、书架、参考项目以及游客模式不变），但管理员相关入口只允许白名单 IP 访问，非白名单来源返回 403：`/api/login`、`/api/register`、`/logout`、`/workbench`、`/api/workbench`、`/api/prompts`、`/api/admin`。
- 移除 80 端口的 `default_server`（公网 IP 直连入口），只保留域名访问的 80 → 443 跳转，避免用服务器 IP 绕过域名白名单。
- 反向代理统一改用 `$errorjiang_real_ip`，应用侧活动日志和限流记录到真实客户端 IP，不再记录成代理地址。
- 白名单当前放行管理员公网出口 `111.18.134.33` 和本机 `127.0.0.1`；公网 IP 变化后修改该文件并 `nginx -t && systemctl reload nginx` 即可。

验证结果：

```text
nginx -t                     -> syntax is ok / test is successful
非白名单来源 api/login         -> 403
非白名单来源 api/register      -> 403
非白名单来源 /workbench        -> 403
非白名单来源 api/admin/*       -> 403
非白名单来源 api/workbench/*   -> 403
非白名单来源 api/prompts       -> 403
非白名单来源 公开页面          -> 200（首页 / 留言 / 动态 / 注册页 / 登录页 / 公开接口）
管理员 IP api/login           -> 401（到达应用，密码校验正常）
管理员 IP /workbench          -> 302（跳转登录页）
重启后服务                     -> errorjiang active、nginx active
```

## 28. 2026-10-09 普通账号登录与管理员入口分离

完成内容：

- 新增 `POST /api/member/login`：只接受"用户名 + 密码"的普通账号登录，任何来源都能访问，仍受 nginx 6 次/分钟和应用 5 次/5 分钟的登录限流。
- `/api/login` 只保留给管理员登录（表单用户名留空）和白名单来源，非白名单 IP 继续 403；`/workbench`、`/api/workbench`、`/api/prompts`、`/api/admin` 的保护不变。
- 首页登录弹窗和 `/login` 页面根据用户名是否填写自动选择接口，普通账号不再被 IP 白名单误伤。
- 站点配置模板、白名单文件说明同步更新。

验证结果：

```text
非白名单 /api/login          -> 403（管理员入口保护生效）
非白名单 /api/member/login   -> 401（到达应用，密码校验正常）
模拟非白名单 首页             -> 200
白名单 /api/login            -> 401（管理员登录正常）
自动化测试                    -> 55 / 55 通过
```
