# Error酱阿里云部署日志

这份日志记录 Error酱 从本地项目到阿里云上线的关键操作、成功结果、故障处理和当前遗留事项。后续每次进行重大部署、迁移、备份或安全配置后，都应追加记录。

不要在日志中写入密码、私钥、Token 或完整的 `auth.json` 内容。

## 1. 当前状态

更新日期：

```text
2026-09-29
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
当前提交：e3dd260
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

- 将本地 `C:\lX.NeT` 初始化为 Git 仓库，默认分支为 `main`。
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

本地 `C:\lX.NeT\data` 比服务器当前数据库更大，尚未上传到服务器。

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
C:\lX.NeT\data
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
