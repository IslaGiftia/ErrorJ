# Error酱服务器维护手册：小白版

这份手册只针对当前这套已经上线的 Error酱 服务器，目标是让你在不了解 Linux 的情况下，也能完成日常检查、改密码、重启、备份、恢复和上传本地数据。

## 0. 先记住这些信息

当前公网访问地址：

```text
http://<服务器公网IP>
```

当前服务器：

```text
系统：Ubuntu 26.04
应用目录：/opt/errorjiang
数据目录：/opt/errorjiang/data
代码仓库：git@github.com:IslaGiftia/ErrorJ.git
当前提交：e3dd260
启动方式：systemd
服务名称：errorjiang
监听端口：127.0.0.1:8000
网页入口：Nginx 的 80 端口
密码文件：/etc/errorjiang.env
备份目录：/data/errorjiang-backup
```

当前真正运行网站的是：

```text
/usr/bin/python3 /opt/errorjiang/app.py
```

`/opt/errorjiang` 只是历史目录名。这个目录原先来自已经删除的 `ErrorJiang` 仓库，但在 2026-09-29 已经把 Git remote 改成当前的 `ErrorJ` 仓库，并快进拉取了最新提交。

`/opt/ErrorJ` 是另一份单独克隆的目录，当前没有运行，也没有端口映射。它里面的 `data` 不是当前网站的数据。除非以后明确切回 Docker，否则维护时只操作 `/opt/errorjiang`。

## 1. 最重要的安全规则

### 1.1 不要把密码发出去

不要在聊天、GitHub、截图或公开网页中显示下面文件的内容：

```text
/etc/errorjiang.env
```

不要对下面命令的输出截图：

```bash
cat /etc/errorjiang.env

tr '\0' '\n' < /proc/$(systemctl show errorjiang -p MainPID --value)/environ \
  | grep '^INVENTORY_PASSWORD='
```

如果真的需要查看密码，看完后清除屏幕。

### 1.2 不要在普通 shell 里直接粘贴 cron 行

这一行不是普通命令：

```cron
0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

它必须通过 `crontab -e` 或本文后面给出的 `crontab` 安装命令保存，不能直接粘到 `root@...#` 后面执行。

### 1.3 看到 `(END)` 时按 q

Linux 的 `less` 分页器会显示：

```text
(END)
```

这时不要输入后续命令。按键盘：

```text
q
```

退出分页器后，才会重新出现：

```text
root@...#
```

如果看到的是 `LESS COMMANDS` 帮助页，也按 `q` 退出。

## 2. 怎么连接服务器

### 方法 A：阿里云 Workbench

1. 登录阿里云控制台。
2. 进入“云服务器 ECS”。
3. 找到当前实例。
4. 点击“远程连接”。
5. 选择 Workbench。
6. 登录后看到类似下面的提示符：

```text
root@<服务器主机名>:~#
```

### 方法 B：从 Windows 使用 SSH

打开 Windows PowerShell，执行：

```powershell
ssh root@<服务器公网IP>
```

输入服务器 SSH 密码后进入服务器。

注意：这里的 SSH 密码和 Error酱 网页登录密码不是一回事。

### 2.1 确认自己在哪里

在服务器执行：

```bash
whoami
hostname
pwd
date
```

应该看到：

```text
root
<服务器主机名>
...
```

`pwd` 显示的路径会随着你执行 `cd` 变化，不影响 systemd 服务。

## 3. 一眼检查网站是否正常

一次只执行一条命令，等结果出来再执行下一条。

### 3.1 检查 Error酱 应用

```bash
systemctl is-active errorjiang
```

正常结果：

```text
active
```

### 3.2 查看应用详细状态

```bash
systemctl status errorjiang --no-pager
```

重点看：

```text
Active: active (running)
Main PID: ...
```

### 3.3 检查应用是否监听 8000

```bash
ss -lntp | grep ':8000'
```

正常结果类似：

```text
LISTEN 0 5 127.0.0.1:8000 0.0.0.0:* users:(("python3",pid=...,fd=...))
```

如果没有输出，说明 Error酱 没有监听端口。

### 3.4 检查应用健康接口

```bash
curl -i http://127.0.0.1:8000/api/health
```

正常结果：

```text
HTTP/1.1 200 OK
{"ok": true}
```

### 3.5 检查 Nginx

```bash
systemctl is-active nginx
nginx -t
```

正常结果：

```text
active
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 3.6 检查通过 Nginx 访问应用

```bash
curl -i http://127.0.0.1/api/health
```

正常结果仍然是：

```text
HTTP/1.1 200 OK
{"ok": true}
```

然后浏览器访问：

```text
http://<服务器公网IP>
```

看到 Error酱 登录页，说明整条链路正常。

## 4. 启动、停止、重启和开机自启

### 4.1 重启 Error酱

修改密码或代码后，通常重启应用即可：

```bash
systemctl restart errorjiang
sleep 2
systemctl is-active errorjiang
curl -i http://127.0.0.1:8000/api/health
```

`systemctl restart` 返回后，应用还需要一点时间才能开始监听端口。刚重启后立刻执行 `curl` 可能显示：

```text
Connection refused
```

等待两秒再测试通常就正常。不要因为这个报错立刻反复重启。

### 4.2 停止 Error酱

```bash
systemctl stop errorjiang
```

停止后网页会显示 `502 Bad Gateway` 或无法访问。

### 4.3 启动 Error酱

```bash
systemctl start errorjiang
sleep 2
curl -i http://127.0.0.1:8000/api/health
```

### 4.4 设置开机自启

```bash
systemctl enable errorjiang
systemctl is-enabled errorjiang
```

正常结果：

```text
enabled
```

### 4.5 重启整台服务器

重启前先确认备份不是正在执行。

服务器重启：

```bash
reboot
```

SSH 或 Workbench 会断开，这是正常的。等待约 1 到 3 分钟后重新连接，然后检查：

```bash
systemctl is-active errorjiang
systemctl is-active nginx
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1/api/health
```

如果服务器没有自动恢复，再去阿里云控制台使用“重启”按钮。

### 4.6 不推荐使用 kill -9

不要用 `kill -9` 停止 Error酱。systemd 会自动管理服务：

```bash
systemctl restart errorjiang
```

`kill -9` 可能造成临时文件或数据库操作中断。

## 5. 修改 Error酱 网页登录密码

当前生效的密码文件是：

```text
/etc/errorjiang.env
```

不要修改 `data/auth.json` 来代替这一步。只要 systemd 环境变量里设置了 `INVENTORY_PASSWORD`，它就会覆盖 `auth.json` 里的密码。

### 5.1 正确修改密码

执行：

```bash
read -rsp '请输入新的登录密码: ' NEW_PW; echo
```

输入新密码后按回车。输入过程不会显示字符，这是正常的。

继续执行：

```bash
printf 'INVENTORY_PASSWORD=%s\nINVENTORY_SECRET=%s\n' \
  "$NEW_PW" "$(openssl rand -hex 32)" > /etc/errorjiang.env

chmod 600 /etc/errorjiang.env
systemctl restart errorjiang
unset NEW_PW
```

这里同时更换了 `INVENTORY_SECRET`，会让所有旧设备上的登录会话失效。所有人都必须用新密码重新登录。

### 5.2 验证密码已经生效

等待两秒：

```bash
sleep 2
systemctl is-active errorjiang
curl -i http://127.0.0.1:8000/api/health
```

浏览器先退出旧会话：

```text
http://<服务器公网IP>/logout
```

然后用新密码登录。

### 5.3 忘记密码怎么办

直接执行本节的密码修改步骤，设置一个新密码。旧密码不需要知道。

### 5.4 检查当前实际生效的密码

以下命令会显示明文密码。不要在公开场合运行或截图：

```bash
tr '\0' '\n' < /proc/$(systemctl show errorjiang -p MainPID --value)/environ \
  | grep '^INVENTORY_PASSWORD='
```

### 5.5 管理注册用户

普通访客可以访问：

```text
http://<服务器公网IP>/register
```

提交后账号默认为 `pending`，不能立即登录。

查看待审核用户：

```bash
cd /opt/errorjiang
runuser -u errorjiang -- python3 tools/manage_users.py pending
```

批准账号：

```bash
runuser -u errorjiang -- python3 tools/manage_users.py approve 用户名
```

拒绝、停用和重新启用：

```bash
runuser -u errorjiang -- python3 tools/manage_users.py reject 用户名
runuser -u errorjiang -- python3 tools/manage_users.py disable 用户名
runuser -u errorjiang -- python3 tools/manage_users.py enable 用户名
```

直接创建已批准账号：

```bash
runuser -u errorjiang -- python3 tools/manage_users.py create 用户名
```

重置密码或删除账号：

```bash
runuser -u errorjiang -- python3 tools/manage_users.py reset-password 用户名
runuser -u errorjiang -- python3 tools/manage_users.py delete 用户名
```

已批准普通账号的权限：

```text
仓库：不可访问
网页收藏：不可访问
笔记：不可访问
工作台：不可访问
AI 提示词：不可访问
```

## 6. 数据在哪里

当前网站的数据目录：

```text
/opt/errorjiang/data
```

主要文件：

```text
inventory.db        主数据库
auth.json           会话密钥
note_images/        笔记图片
part_images/        元件图片
workbench/          工作台文件
bom_reports/        BOM 对比报告
site_photos/        照片墙图片
site_music_files/   音乐文件
```

查看大小：

```bash
du -sh /opt/errorjiang/data
ls -lah /opt/errorjiang/data
```

`/opt/ErrorJ/data` 不是当前网站的数据目录，除非以后明确切换回 Docker，否则不用备份它。

## 7. 手动备份

### 7.1 执行一次备份

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

脚本会创建类似目录：

```text
/data/errorjiang-backup/20260929-010426
```

里面包含：

```text
inventory.db
files.tar.gz
```

数据库使用 SQLite 官方 backup API，服务运行中也能安全备份。

### 7.2 查看备份结果

```bash
ls -lah /data/errorjiang-backup
du -sh /data/errorjiang-backup/*
```

查看最新一次备份：

```bash
find /data/errorjiang-backup \
  -maxdepth 2 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM %10s %p\n' | sort
```

### 7.3 设置每天自动备份

下面的整段命令会安装一个定时任务，并自动避免重复添加同一条：

```bash
(
  crontab -l 2>/dev/null | grep -vF '/opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup'
  echo '0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup >> /var/log/errorjiang-backup.log 2>&1'
) | crontab -
```

检查：

```bash
crontab -l
```

正常结果应该只有一条：

```text
0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup >> /var/log/errorjiang-backup.log 2>&1
```

如果看到多条备份命令，执行：

```bash
crontab -e
```

删除重复行，只保留一条，然后保存退出。

使用 nano 时：

```text
Ctrl+O
Enter
Ctrl+X
```

使用 vi 时：

```text
:wq
```

### 7.4 查看备份日志

```bash
tail -n 100 /var/log/errorjiang-backup.log
```

### 7.5 判断是否重复备份

```bash
crontab -l

find /data/errorjiang-backup /opt/errorjiang-backup \
  -maxdepth 2 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM %10s %p\n' 2>/dev/null | sort

sha256sum /data/errorjiang-backup/*/inventory.db \
  /opt/errorjiang-backup/*/inventory.db 2>/dev/null
```

判断方法：

- 只有一条 cron 任务：正常。
- 每天只有一个时间目录：正常。
- 同一时间出现两套不同来源的备份：重复配置。
- 哈希相同：内容完全相同的重复副本。
- 哈希不同：数据库内容不同，需要确认来源。

### 7.6 不要只依赖同一块云盘

如果备份文件仍保存在同一块云盘，只能防止误删，不能防止整块盘故障。

还应该在阿里云控制台：

1. 开启云盘自动快照。
2. 定期把备份同步到 OSS。
3. 偶尔下载一份备份到自己的电脑。

## 8. 恢复备份

恢复前先明确：这会覆盖服务器当前数据。

### 8.1 找到要恢复的备份

```bash
ls -lah /data/errorjiang-backup
```

假设备份目录是：

```text
/data/errorjiang-backup/20260929-010426
```

### 8.2 先备份当前数据

停止服务：

```bash
systemctl stop errorjiang
```

保存当前数据目录：

```bash
mv /opt/errorjiang/data \
  "/opt/errorjiang/data.before-restore-$(date +%F-%H%M%S)"
```

### 8.3 恢复数据库和上传文件

重新创建数据目录：

```bash
mkdir -p /opt/errorjiang/data
cp /data/errorjiang-backup/20260929-010426/inventory.db \
  /opt/errorjiang/data/inventory.db
tar -xzf /data/errorjiang-backup/20260929-010426/files.tar.gz \
  -C /opt/errorjiang/data
```

恢复权限：

```bash
chown -R errorjiang:errorjiang /opt/errorjiang/data
```

启动并检查：

```bash
systemctl start errorjiang
sleep 2
systemctl is-active errorjiang
curl -i http://127.0.0.1:8000/api/health
```

浏览器登录后检查库存、笔记、图片和附件。

## 9. 把本地数据上传到服务器

本地数据目录：

```text
C:\lX.NeT\data
```

服务器当前使用的数据目录：

```text
/opt/errorjiang/data
```

这是一次单向复制，不是自动同步。上传后，本地和服务器会各自独立修改。再次上传前要明确哪一边是最新数据。

### 9.1 先在本地停止 Error酱

打开 Windows PowerShell：

```powershell
$pid = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
Stop-Process -Id $pid
```

确认本地服务已经停止：

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

没有输出即已停止。

### 9.2 在本地打包数据

不复制本地会话密钥，避免把旧登录密钥带到服务器：

```powershell
tar --exclude=data/auth.json --exclude=*.log `
  -czf C:\errorjiang-data.tar.gz `
  -C C:\lX.NeT data
```

检查压缩包：

```powershell
Get-Item C:\errorjiang-data.tar.gz | Select-Object FullName,Length,LastWriteTime
```

### 9.3 在服务器先备份现有数据

```bash
df -h
systemctl stop errorjiang

mv /opt/errorjiang/data \
  "/opt/errorjiang/data.before-local-import-$(date +%F-%H%M%S)"
```

### 9.4 从 Windows 上传

```powershell
scp C:\errorjiang-data.tar.gz root@<服务器公网IP>:/tmp/
```

上传速度取决于你的家庭宽带上行速度。

### 9.5 在服务器解压

```bash
tar -xzf /tmp/errorjiang-data.tar.gz -C /opt/errorjiang
chown -R errorjiang:errorjiang /opt/errorjiang/data
```

确认目录：

```bash
ls -lah /opt/errorjiang/data
```

### 9.6 启动并检查

```bash
systemctl start errorjiang
sleep 2
systemctl is-active errorjiang
curl -i http://127.0.0.1:8000/api/health
```

浏览器登录后检查：

- 库存数量和位置
- 项目记录
- 笔记正文和图片
- 日常记录
- 留言和附件
- 工作台文件
- 书签

### 9.7 上传成功后立即备份

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
du -sh /data/errorjiang-backup/*
```

新备份应该明显大于上传前的 `256K`。

### 9.8 比较两个数据库的记录数

```bash
python3 - <<'PY'
import sqlite3

paths = [
    "/opt/errorjiang/data/inventory.db",
    "/opt/ErrorJ/data/inventory.db",
]

for path in paths:
    print(f"\n===== {path} =====")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = [
        row[0] for row in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    for table in tables:
        count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if count:
            print(f"{table}: {count}")
    con.close()
PY
```

## 10. Nginx 基础维护

### 10.1 检查配置

```bash
nginx -t
```

正常结果：

```text
configuration file /etc/nginx/nginx.conf test is successful
```

### 10.2 修改配置后重载

```bash
nginx -t
systemctl reload nginx
```

只有 `nginx -t` 成功后，才能执行 `reload`。

### 10.3 查看当前代理配置

```bash
nginx -T | grep -nE 'server_name|listen 80|listen 443|proxy_pass|client_max_body_size|X-Forwarded|limit_req'
```

至少要确认下面配置存在：

```nginx
client_max_body_size 40m;

proxy_pass http://127.0.0.1:8000;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

### 10.4 重启 Nginx

一般用 reload：

```bash
systemctl reload nginx
```

如果 reload 失败：

```bash
systemctl restart nginx
sleep 1
systemctl status nginx --no-pager
```

## 11. 安全组和公网访问

当前可访问地址：

```text
http://<服务器公网IP>
```

检查公网出口地址：

```bash
curl -4 -sS https://ipinfo.io/ip; echo
```

阿里云安全组建议：

```text
SSH 22：只允许自己的公网 IP
HTTP 80：允许所有 IPv4
HTTPS 443：配置证书后允许所有 IPv4
8000：不要开放
```

如果网页无法打开，依次检查：

```bash
systemctl is-active nginx
systemctl is-active errorjiang
ss -lntp | grep ':80'
ss -lntp | grep ':8000'
curl -i http://127.0.0.1/api/health
```

浏览器一直超时通常是安全组没有放行，或者规则绑定到了错误实例。

## 12. HTTP 和 HTTPS

当前只有：

```text
http://<服务器公网IP>
```

目前 `443` 端口没有开放，也没有域名证书。

HTTP 登录时，密码是明文传输。临时自己使用可以接受，但长期公网使用必须配置 HTTPS。

要配置 HTTPS，需要：

1. 一个域名。
2. 域名 A 记录指向 `<服务器公网IP>`。
3. 中国大陆 ECS 通常需要完成 ICP 备案。
4. 阿里云免费证书或 Let's Encrypt 证书。
5. 安全组放行 `443`。
6. Nginx 配置 HTTPS 和 HTTP 自动跳转。

配置完成后才使用：

```text
https://你的域名
```

## 13. 更新服务器代码

当前 systemd 使用的代码目录：

```text
/opt/errorjiang
```

正确仓库地址：

```text
git@github.com:IslaGiftia/ErrorJ.git
```

更新前先备份：

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

进入目录并检查：

```bash
cd /opt/errorjiang
git status
git remote -v
git log --oneline -5
```

如果工作区干净，可以拉取新版本：

```bash
git pull --ff-only
python3 -m py_compile app.py
systemctl restart errorjiang
sleep 2
curl -i http://127.0.0.1:8000/api/health
```

不要在不理解后果时执行：

```bash
git reset --hard
git clean -fd
```

这些命令会删除未提交的修改或未跟踪文件。

## 14. 服务器基础状态检查

### 14.1 磁盘空间

```bash
df -h
```

重点看 `/` 的 `Use%`。超过 85% 就应清理或扩容。

### 14.2 目录占用

```bash
du -sh /opt/errorjiang/data
du -sh /data/errorjiang-backup
du -sh /var/log
```

### 14.3 内存

```bash
free -h
```

### 14.4 系统负载和运行时间

```bash
uptime
```

### 14.5 最近应用日志

```bash
journalctl -u errorjiang -n 100 --no-pager
```

实时查看：

```bash
journalctl -u errorjiang -f
```

按 `Ctrl+C` 停止实时查看。

### 14.6 Nginx 日志

```bash
tail -n 100 /var/log/nginx/access.log
tail -n 100 /var/log/nginx/error.log
```

## 15. 常见问题处理

### 15.1 重启后立即 curl 提示 Connection refused

这是启动还没有完成。等待两秒：

```bash
sleep 2
ss -lntp | grep ':8000'
curl -i http://127.0.0.1:8000/api/health
```

### 15.2 网页显示 502 Bad Gateway

Nginx 正常，Error酱 没运行：

```bash
systemctl status errorjiang --no-pager
journalctl -u errorjiang -n 100 --no-pager
```

### 15.3 systemd 报 status=200/CHDIR

运行用户没有权限进入项目目录：

```bash
chown root:errorjiang /opt/errorjiang
chmod 750 /opt/errorjiang
chown -R errorjiang:errorjiang /opt/errorjiang/data
systemctl restart errorjiang
```

### 15.4 网页一直超时

检查：

```bash
systemctl is-active nginx
ss -lntp | grep ':80'
curl -I http://127.0.0.1
```

再检查阿里云安全组是否正确绑定实例。

### 15.5 上传图片或附件返回 413

Nginx 上传限制太小。检查：

```bash
nginx -T | grep client_max_body_size
```

应有：

```nginx
client_max_body_size 40m;
```

修改后：

```bash
nginx -t
systemctl reload nginx
```

### 15.6 数据库提示 database is locked

确认数据目录位于本地云盘，不要放在 NFS 或网络共享盘：

```bash
df -T /opt/errorjiang/data
```

Error酱已经启用 SQLite WAL 和重试等待。

### 15.7 看到 “no crontab for root”

表示还没设置定时任务。使用本文第 7.3 节的命令安装每日备份。

### 15.8 Docker Hub 连接超时

当前 systemd 部署不依赖 Docker Hub。不要把服务改回 Docker，除非已经配置好阿里云镜像加速器。

### 15.9 忘记公网 IP

```bash
curl -4 -sS https://ipinfo.io/ip; echo
```

当前地址是：

```text
<服务器公网IP>
```

## 16. 紧急操作卡片

### 16.1 网站打不开

```bash
systemctl is-active nginx
systemctl is-active errorjiang
ss -lntp | grep ':8000'
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1/api/health
journalctl -u errorjiang -n 80 --no-pager
```

### 16.2 需要马上重启网站

```bash
systemctl restart errorjiang
sleep 2
curl -i http://127.0.0.1:8000/api/health
```

### 16.3 需要修改密码

```bash
read -rsp '请输入新的登录密码: ' NEW_PW; echo
printf 'INVENTORY_PASSWORD=%s\nINVENTORY_SECRET=%s\n' \
  "$NEW_PW" "$(openssl rand -hex 32)" > /etc/errorjiang.env
chmod 600 /etc/errorjiang.env
systemctl restart errorjiang
unset NEW_PW
```

### 16.4 需要马上备份

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

### 16.5 需要重启服务器

```bash
reboot
```

等待 1 到 3 分钟，重新连接后再检查：

```bash
systemctl is-active errorjiang
systemctl is-active nginx
curl -i http://127.0.0.1:8000/api/health
```

## 17. 日常维护清单

### 每天

- 打开网站确认能登录。
- 检查自动备份最新时间。

```bash
ls -lah /data/errorjiang-backup | tail
```

### 每周

- 检查磁盘空间。
- 检查 Error酱 和 Nginx 状态。
- 查看是否有异常日志。

```bash
df -h
systemctl is-active errorjiang
systemctl is-active nginx
journalctl -u errorjiang --since '7 days ago' -p warning --no-pager
```

### 每月

- 手动执行一次备份。
- 确认阿里云快照和 OSS 同步正常。
- 检查和更新系统安全补丁。
- 确认只有一个 Error酱 运行方式。
- 确认备份中确实有数据库文件。

```bash
apt update
apt list --upgradable
```

更新系统前先备份。安装更新：

```bash
apt upgrade -y
```

如果更新了内核，按提示决定是否重启服务器。

## 18. 维护原则

遇到不熟悉的命令时，遵守下面规则：

1. 一次只执行一条命令。
2. 修改配置前先备份。
3. 不确定时先运行只读检查命令。
4. 不在聊天或截图里暴露密码、私钥和 `auth.json`。
5. 不直接删除 `data`、备份目录和 Git 目录。
6. 不用 `kill -9` 停止 systemd 服务。
7. 不让 systemd 和 Docker 同时占用 `8000`。
8. 修改 Nginx 后先运行 `nginx -t`。
9. 恢复备份前先把当前数据另存一份。
10. 本地数据和服务器数据不是自动同步关系。

## 19. 最常用命令速查

### 看网站状态

```bash
systemctl is-active errorjiang
systemctl is-active nginx
curl -i http://127.0.0.1:8000/api/health
```

### 重启网站

```bash
systemctl restart errorjiang
sleep 2
curl -i http://127.0.0.1:8000/api/health
```

### 看日志

```bash
journalctl -u errorjiang -n 100 --no-pager
```

### 备份

```bash
bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

### 看备份

```bash
ls -lah /data/errorjiang-backup
```

### 看磁盘

```bash
df -h
du -sh /opt/errorjiang/data
```

### 看端口

```bash
ss -lntp
```

### 看定时任务

```bash
crontab -l
```

### 测试 Nginx

```bash
nginx -t
```

### 重载 Nginx

```bash
systemctl reload nginx
```

### 重启服务器

```bash
reboot
```
