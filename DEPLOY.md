# 阿里云服务器部署指南：Error酱从零到上线

本文以 Ubuntu 22.04、24.04、26.04 和阿里云 ECS 为例，从购买服务器后的初始配置一直写到域名、HTTPS、备份和升级。

推荐使用 **systemd 原生部署**。Error酱只依赖 Python 标准库，不依赖数据库服务器，也不依赖前端构建工具。原生部署更简单，在国内服务器上还能避开 Docker Hub 连接超时。

Docker 部署仍然可用，放在本文最后作为可选方案。

> 当前生产部署记录，更新于 2026-09-29：
>
> - 公网地址：`http://<服务器公网IP>`
> - 活动代码目录：`/opt/errorjiang`
> - Git 仓库：`git@github.com:IslaGiftia/ErrorJ.git`
> - 当前提交：`e3dd260`
> - 数据目录：`/opt/errorjiang/data`
> - 运行方式：`errorjiang.service` + Nginx
> - `/opt/ErrorJ` 是另一份未运行的历史部署副本
> - 当前仍为 HTTP，HTTPS 和每日自动备份尚未完成

## 1. 最终架构

```text
浏览器
  |
  | 80 / 443
  v
阿里云安全组
  |
  v
Nginx
  |
  | 127.0.0.1:8000
  v
errorjiang.service
  |
  v
/opt/errorjiang/app.py
  |
  v
/opt/errorjiang/data
```

公网只开放 `22`、`80`、`443`。应用端口 `8000` 只监听服务器本机，不加入安全组。

## 2. 准备工作

需要准备：

- 一台阿里云 ECS，Ubuntu 22.04 或更高版本。
- ECS 公网 IP。
- 可选：已完成 ICP 备案的域名。
- 可选：阿里云免费 SSL 证书，或准备使用 Let's Encrypt。

建议配置：

- 个人使用：1 核 2GB 内存即可。
- 系统盘：至少 20GB。
- 地域：优先选择离主要访问者较近的地域。

## 3. 配置安全组

进入阿里云 ECS 控制台：

1. 打开“实例与镜像” > “实例”。
2. 选择 ECS 所在地域。
3. 点击实例 ID，打开“安全组”页签。
4. 点击“配置规则” > “入方向” > “手动添加”。
5. 按以下规则放行：

```text
SSH
协议：TCP
端口：22/22
授权对象：你的固定公网 IP/32
说明：只允许自己的电脑登录

HTTP
协议：TCP
端口：80/80
授权对象：0.0.0.0/0
说明：网页访问和证书签发

HTTPS
协议：TCP
端口：443/443
授权对象：0.0.0.0/0
说明：HTTPS 网页访问
```

不要放行 `8000`。

如果不知道自己的固定公网 IP，可以临时把 SSH 授权对象设为 `0.0.0.0/0`，上线后再收紧。

## 4. 连接服务器

Windows PowerShell：

```powershell
ssh root@你的ECS公网IP
```

推荐使用 SSH 密钥。密码登录容易受到公网爆破，长期运行时应关闭 root 密码登录。

登录后先确认系统版本：

```bash
cat /etc/os-release
python3 --version
```

本文命令默认在 root 终端执行。如果不是 root，请在命令前加 `sudo`。

## 5. 基础系统设置

更新系统并安装依赖：

```bash
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y
apt-get install -y git python3 nginx curl openssl ca-certificates
```

设置中国时区：

```bash
timedatectl set-timezone Asia/Shanghai
date
```

如果你启用了 UFW，放行 SSH、HTTP 和 HTTPS：

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw status
```

阿里云安全组仍然是第一层防火墙。UFW 未启用时可以跳过。

## 6. 获取代码

项目仓库：

```text
https://github.com/IslaGiftia/ErrorJ.git
```

首次部署：

```bash
git clone https://github.com/IslaGiftia/ErrorJ.git /opt/errorjiang
```

如果目录已经存在：

```bash
cd /opt/errorjiang
git pull --ff-only
```

检查文件：

```bash
ls -la /opt/errorjiang
python3 -m py_compile /opt/errorjiang/app.py
```

`py_compile` 没有输出和报错，表示 Python 语法检查通过。

## 7. 创建运行用户和目录权限

不要直接用 root 运行网站进程。创建专用用户：

```bash
id -u errorjiang >/dev/null 2>&1 || useradd -r -s /bin/bash errorjiang
```

设置代码和运行数据权限：

```bash
chown -R root:root /opt/errorjiang
chown root:errorjiang /opt/errorjiang
chmod 750 /opt/errorjiang
chown -R errorjiang:errorjiang /opt/errorjiang/data
```

这里有一个容易踩的坑：

```text
chmod 750 /opt/errorjiang
```

表示只有所有者和 `errorjiang` 用户组可以进入目录。如果忘记把目录组改成 `errorjiang`，systemd 会报：

```text
Failed at step CHDIR spawning /usr/bin/python3
status=200/CHDIR
```

出现这个错误时执行：

```bash
chown root:errorjiang /opt/errorjiang
chmod 750 /opt/errorjiang
chown -R errorjiang:errorjiang /opt/errorjiang/data
systemctl restart errorjiang
```

## 8. 设置登录密码

Error酱默认没有访问密码。公网部署必须设置密码。

生成随机密码：

```bash
printf 'INVENTORY_PASSWORD=%s\n' "$(openssl rand -hex 24)" > /etc/errorjiang.env
chmod 600 /etc/errorjiang.env
cat /etc/errorjiang.env
```

立即复制并保存密码。不要把 `/etc/errorjiang.env` 或终端截图发到公开网络。

修改密码：

```bash
printf 'INVENTORY_PASSWORD=%s\n' "你的新密码" > /etc/errorjiang.env
chmod 600 /etc/errorjiang.env
systemctl restart errorjiang
```

密码中如果含有单引号、双引号、`$` 或反斜杠，建议改用随机十六进制密码，避免 shell 转义问题。

## 9. 安装 systemd 服务

项目已经提供 `deploy/errorjiang.service`：

```bash
cd /opt/errorjiang
cp deploy/errorjiang.service /etc/systemd/system/errorjiang.service
systemctl daemon-reload
systemctl enable --now errorjiang
```

检查状态：

```bash
systemctl status errorjiang --no-pager
```

正常状态：

```text
Active: active (running)
```

本机健康检查：

```bash
curl -i http://127.0.0.1:8000/api/health
```

正常结果：

```text
HTTP/1.1 200 OK
{"ok": true}
```

查看日志：

```bash
journalctl -u errorjiang -n 100 --no-pager
```

持续查看日志：

```bash
journalctl -u errorjiang -f
```

## 10. 配置 Nginx

先建立 HTTP 反向代理。没有域名时可以直接使用公网 IP 验证；有域名时把 `server_name _;` 改成你的域名。

创建配置：

```bash
cat > /etc/nginx/sites-available/errorjiang.conf <<'EOF'
limit_req_zone $binary_remote_addr zone=errorjiang_login:10m rate=6r/m;

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 40m;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location = /api/login {
        limit_req zone=errorjiang_login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF
```

启用配置：

```bash
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/errorjiang.conf /etc/nginx/sites-enabled/errorjiang.conf
nginx -t
systemctl enable --now nginx
systemctl reload nginx
```

验证：

```bash
ss -lntp | grep ':80'
curl -I http://127.0.0.1
curl -i http://127.0.0.1/api/health
```

浏览器访问：

```text
http://你的ECS公网IP
```

出现登录页表示部署成功。

HTTP 会明文传输登录密码，适合首次验证，不适合长期公开使用。准备好域名后应立即配置 HTTPS。

## 11. 域名和 ICP 备案

如果 ECS 位于中国大陆，域名用于网站访问前通常需要完成 ICP 备案。

配置域名解析：

1. 进入阿里云“云解析 DNS”。
2. 选择域名，点击“解析设置”。
3. 添加记录：

```text
记录类型：A
主机记录：@
记录值：ECS 公网 IP

记录类型：A
主机记录：www
记录值：ECS 公网 IP
```

验证解析：

```bash
dig +short 你的域名
curl -I http://你的域名
```

如果 `dig` 未安装：

```bash
apt-get install -y dnsutils
```

直接使用公网 IP 不需要备案，但没有域名就无法方便地申请受信任的 HTTPS 证书。

## 12. 配置 HTTPS

### 方案 A：阿里云免费证书

推荐阿里云 ECS 用户使用这个方案。

1. 进入阿里云“数字证书管理服务”。
2. 申请免费 SSL 证书，绑定你的域名。
3. 按控制台提示完成 DNS 验证。
4. 下载 Nginx 格式证书。
5. 上传证书文件到服务器。

建议目录：

```text
/etc/nginx/ssl/你的域名.pem
/etc/nginx/ssl/你的域名.key
```

项目提供了 HTTPS 配置模板：

```text
/opt/errorjiang/deploy/nginx-errorjiang.conf
```

复制并编辑：

```bash
mkdir -p /etc/nginx/ssl
cp /opt/errorjiang/deploy/nginx-errorjiang.conf /etc/nginx/sites-available/errorjiang-https.conf
nano /etc/nginx/sites-available/errorjiang-https.conf
```

需要替换：

```text
errorjiang.example.com
```

全部改成你的真实域名。

还需要替换证书路径：

```text
/etc/letsencrypt/live/errorjiang.example.com/fullchain.pem
/etc/letsencrypt/live/errorjiang.example.com/privkey.pem
```

改成：

```text
/etc/nginx/ssl/你的域名.pem
/etc/nginx/ssl/你的域名.key
```

启用 HTTPS 配置：

```bash
rm -f /etc/nginx/sites-enabled/errorjiang.conf
ln -sf /etc/nginx/sites-available/errorjiang-https.conf /etc/nginx/sites-enabled/errorjiang-https.conf
nginx -t
systemctl reload nginx
```

验证：

```bash
curl -I https://你的域名
```

### 方案 B：Let's Encrypt

使用 Let's Encrypt 前，域名必须已经解析到 ECS，并且公网可以访问 `80` 端口。

不要先启用带有不存在证书路径的 HTTPS 配置。先保留只监听 `80` 的 HTTP 配置，把 `server_name _;` 改为域名：

```nginx
server_name example.com www.example.com;
```

检查配置并重载：

```bash
nginx -t
systemctl reload nginx
```

安装 Certbot：

```bash
apt-get install -y certbot python3-certbot-nginx
```

申请证书：

```bash
certbot --nginx -d example.com -d www.example.com
```

Certbot 会自动修改 Nginx 配置并设置续期。检查：

```bash
systemctl list-timers | grep certbot
certbot renew --dry-run
```

如果 Nginx 因下面这种路径不存在而启动失败，说明证书还没有签发：

```text
/etc/letsencrypt/live/example.com/fullchain.pem
```

处理方法：先移除 HTTPS 配置，只保留 HTTP，完成证书签发后再启用。

## 13. 上线验收

按顺序检查：

```bash
systemctl is-active errorjiang
systemctl is-active nginx
curl -i http://127.0.0.1:8000/api/health
curl -I http://你的域名
curl -I https://你的域名
```

浏览器需要确认：

- 首页可以打开。
- 未登录访问会跳转到登录页。
- 正确密码可以登录。
- 错误密码多次后触发锁定。
- 元件、库存、项目、日常和笔记页面可以正常打开。
- 图片和附件上传正常。
- F5 刷新后页面状态正常。
- 手机浏览器可以访问。

## 13.1 把本指南导入 Error酱 笔记

在服务器上执行：

```bash
cd /opt/errorjiang

runuser -u errorjiang -- python3 tools/import_doc_note.py DEPLOY.md \
  --title "阿里云服务器部署指南：Error酱从零到上线" \
  --tags "部署,阿里云,Ubuntu,Error酱,Nginx,systemd" \
  --slug aliyun-deploy
```

不要用 root 直接导入，否则可能在 `data/` 中生成 root 所有的数据库文件。`runuser` 会让命令以 `errorjiang` 用户执行。

同一标题再次导入时会更新原笔记，不会重复创建。导入后访问：

```text
http://127.0.0.1:8000/notes
```

## 14. 配置备份

Error酱的数据都在：

```text
/opt/errorjiang/data
```

包括：

```text
inventory.db
auth.json
note_images/
part_images/
workbench/
bom_reports/
```

Linux 备份脚本：

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

脚本会：

- 使用 SQLite 官方 backup API 生成一致性数据库快照。
- 打包上传图片、附件和固件。
- 默认保留最近 14 份。

设置每天凌晨 3 点备份：

```bash
crontab -e
```

加入：

```cron
0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup >> /var/log/errorjiang-backup.log 2>&1
```

检查备份：

```bash
ls -lh /data/errorjiang-backup
tail -n 50 /var/log/errorjiang-backup.log
```

阿里云控制台还应开启云盘自动快照。备份和快照不是替代关系：

- 备份脚本用于快速恢复单个站点数据。
- 云盘快照用于整台服务器或系统故障恢复。

可选：把 `/data/errorjiang-backup` 同步到 OSS。

## 15. 升级和回滚

升级前先备份：

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

拉取新版本：

```bash
cd /opt/errorjiang
git pull --ff-only
python3 -m py_compile app.py
systemctl restart errorjiang
```

验证：

```bash
systemctl status errorjiang --no-pager
curl -i http://127.0.0.1:8000/api/health
journalctl -u errorjiang -n 100 --no-pager
```

查看历史版本：

```bash
git log --oneline --decorate -10
```

回滚前先停止服务并备份数据库。确认目标提交后，可以使用 Git 切换到旧版本进行恢复。不要在不了解影响的情况下使用破坏性 Git 命令。

## 16. 恢复备份

停止服务：

```bash
systemctl stop errorjiang
```

假设备份目录是：

```text
/data/errorjiang-backup/20260928-030000
```

恢复：

```bash
cp /data/errorjiang-backup/20260928-030000/inventory.db /opt/errorjiang/data/inventory.db
tar -xzf /data/errorjiang-backup/20260928-030000/files.tar.gz -C /opt/errorjiang/data
chown -R errorjiang:errorjiang /opt/errorjiang/data
systemctl start errorjiang
curl -i http://127.0.0.1:8000/api/health
```

恢复完成后检查登录、库存、笔记图片和上传附件。

## 17. 常见问题

### 17.1 `Failed to connect to 127.0.0.1 port 8000`

应用没有运行：

```bash
systemctl status errorjiang --no-pager
journalctl -u errorjiang -n 100 --no-pager
```

### 17.2 `status=200/CHDIR`

运行用户无法进入项目目录：

```bash
chown root:errorjiang /opt/errorjiang
chmod 750 /opt/errorjiang
chown -R errorjiang:errorjiang /opt/errorjiang/data
systemctl restart errorjiang
```

### 17.3 浏览器访问超时

依次检查：

```bash
systemctl status nginx --no-pager
ss -lntp | grep ':80'
curl -I http://127.0.0.1
```

再检查阿里云安全组是否放行 `80/443`，以及规则是否绑定到了正确实例。

### 17.4 `502 Bad Gateway`

Nginx 正常，但 Error酱 没运行：

```bash
systemctl status errorjiang --no-pager
journalctl -u errorjiang -n 100 --no-pager
curl -i http://127.0.0.1:8000/api/health
```

### 17.5 忘记密码

重新设置：

```bash
printf 'INVENTORY_PASSWORD=%s\n' "$(openssl rand -hex 24)" > /etc/errorjiang.env
chmod 600 /etc/errorjiang.env
systemctl restart errorjiang
cat /etc/errorjiang.env
```

### 17.6 时间差 8 小时

检查：

```bash
timedatectl
date
systemctl show errorjiang -p Environment
```

systemd 服务已经设置：

```text
TZ=Asia/Shanghai
```

### 17.7 `database is locked`

确认 `data/` 位于本地云盘，不要放在 NFS 或网络共享盘。Error酱已经启用 SQLite WAL 和 `busy_timeout=5000`。

### 17.8 Docker Hub 连接超时

错误示例：

```text
failed to resolve source metadata for docker.io/library/python:3.12-slim
dial tcp ...:443: i/o timeout
```

国内 ECS 访问 Docker Hub 经常超时。最简单的处理方式是使用本文的 systemd 部署，不下载 Docker 镜像。

如果必须使用 Docker，请到阿里云“容器镜像服务 ACR”获取当前账号专属的镜像加速器地址，然后在 `/etc/docker/daemon.json` 中配置：

```json
{
  "registry-mirrors": [
    "https://你的专属ID.mirror.aliyuncs.com"
  ]
}
```

重启 Docker：

```bash
systemctl daemon-reload
systemctl restart docker
docker info | grep -A 3 "Registry Mirrors"
```

不要随意使用来源不明的公共镜像加速地址。

## 18. 日常维护命令

查看应用：

```bash
systemctl status errorjiang --no-pager
```

重启应用：

```bash
systemctl restart errorjiang
```

查看应用日志：

```bash
journalctl -u errorjiang -f
```

查看 Nginx：

```bash
systemctl status nginx --no-pager
nginx -t
systemctl reload nginx
```

查看磁盘：

```bash
df -h
du -sh /opt/errorjiang/data
```

查看端口：

```bash
ss -lntp
```

查看监听端口时，应看到：

```text
127.0.0.1:8000
0.0.0.0:80
0.0.0.0:443
```

`8000` 不应监听在公网地址。

## 19. Docker 可选部署

只有在已经配置好 Docker Hub 镜像加速器时再使用。

文件：

```text
Dockerfile
docker-compose.prod.yml
```

生成密码：

```bash
cd /opt/errorjiang
printf 'INVENTORY_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env
chmod 600 .env
cat .env
```

启动：

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -i http://127.0.0.1:8000/api/health
```

注意：

- Docker 生产配置只映射 `127.0.0.1:8000`。
- Nginx 配置与 systemd 方案相同。
- systemd 服务和 Docker 容器不要同时占用 `8000`。
- 如果先启动了 systemd 服务，使用 Docker 前先执行 `systemctl stop errorjiang`。

## 20. 上线检查清单

- [ ] ECS 系统已更新。
- [ ] 安全组只放行 `22`、`80`、`443`。
- [ ] `8000` 未对公网开放。
- [ ] 代码位于 `/opt/errorjiang`。
- [ ] `/opt/errorjiang/data` 归 `errorjiang` 用户所有。
- [ ] `/etc/errorjiang.env` 已设置强密码，权限为 `600`。
- [ ] `errorjiang.service` 已设置开机自启。
- [ ] `/api/health` 返回 `200`。
- [ ] Nginx 配置通过 `nginx -t`。
- [ ] 域名 A 记录已生效。
- [ ] 中国大陆域名已完成 ICP 备案。
- [ ] HTTPS 证书有效，HTTP 自动跳转 HTTPS。
- [ ] 登录、上传、下载和手机访问均已验证。
- [ ] 每日备份任务已配置。
- [ ] 阿里云云盘自动快照已开启。
- [ ] 已实际演练一次恢复流程。

## 21. 一句话复盘

这套项目最稳的上线路线是：

```text
阿里云安全组
  -> Ubuntu
  -> Git 拉取代码
  -> systemd 运行 Error酱
  -> Nginx 反代
  -> 域名和 HTTPS
  -> 自动备份
```

Error酱没有复杂依赖，systemd 原生部署比 Docker 更少一层故障。Docker 适合已经配置镜像加速器、需要镜像打包或迁移到其他平台的场景。
