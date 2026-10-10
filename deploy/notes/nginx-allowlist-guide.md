# Error酱管理员入口白名单：喂饭版操作笔记

这篇只讲一件事：**怎么让"只有我的 IP 能进管理员后台"，以及怎么临时放行一个 IP。**
跟着做就行，每条命令都能直接复制；改坏了网站也不会挂，脚本会自动回滚。

> 先记住一句话：白名单**默认是关着的**（谁都能在登录页输密码试试），
> 只有执行了下面「收紧」那一步，白名单才真正开始拦人。

---

## 一、先连上服务器

电脑上打开 PowerShell（Windows）或终端（Mac），整行复制：

```bash
ssh root@47.108.86.201
```

看到提示符变成 `root@iZxxxx:~#` 就说明连上了。**后面所有命令都在这个窗口里执行**。

---

## 二、看一眼现在是什么状态

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh list
```

会出现两种结果之一：

- `当前模式：白名单关闭（default 1，任意 IP 都能访问管理员入口）` → 现在谁都能登录
- `当前模式：白名单开启（default 0，只允许下列 IP / 网段）` → 现在只有名单里的 IP 能登录

下面会接着列出名单里所有的 IP。

---

## 三、查我自己的公网 IP

用手机或电脑浏览器搜索 **"我的 IP"**（或者打开 `https://www.ip138.com`），
页面最上面那个 IP 就是。

⚠️ 手机流量、家里 WiFi、公司网络，出来的 IP 是不一样的，
**要按你当前正在用的那个网络去查**。

---

## 四、加白名单 + 收紧（推荐流程）

假设你查到的 IP 是 `123.45.67.89`（替换成你自己的，别照抄）：

```bash
# 第一步：把自己这个 IP 加进白名单
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.89

# 第二步：开启白名单（从这一刻起，只有名单里的 IP 能进后台）
sudo bash /usr/local/bin/nginx-allow-ip.sh strict

# 第三步：确认一下改对了
sudo bash /usr/local/bin/nginx-allow-ip.sh list
```

**怎么知道成功了？**
打开浏览器访问 `https://zhexiyan.cc/login`，输入管理员密码登录：

- **能登录** → 说明你现在的 IP 已经在名单里了 ✓
- **页面显示「管理员入口仅限受信任的 IP 访问。」** → 说明当前网络的 IP 不在名单里，
  回到第三步，把**当前网络**的 IP 再加一次。

---

## 五、我出门了，要用手机管后台

两个办法，随便挑一个：

**办法 1（最省事）**：直接把白名单关掉，谁都能登录

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh open
```

**办法 2（更安全）**：用手机查一下当前 IP，临时放行 8 小时

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.89 8h
```

意思是"这个 IP 放行 8 小时，到点自动删掉"，不用你记着回来手动删。

---

## 六、常用命令（复制就能用）

看当前状态和名单：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh list
```

关闭白名单（谁都拦，出门在外用这个）：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh open
```

开启白名单（只放行名单里的 IP，先确保自己已经在名单里）：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh strict
```

加一个固定 IP：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.89
```

加一整个网段（比如公司或学校出口）：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.0/24
```

临时加 2 小时（到期自动移除）：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.89 2h
```

删掉某个 IP（同时会取消它的自动移除任务）：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh remove 123.45.67.89
```

时长怎么写：`30m` 半小时、`2h` 两小时、`1d` 一天。

---

## 七、改坏了怎么办

**1）先自己检查一遍配置：**

```bash
nginx -t
```

看到 `configuration file /etc/nginx/nginx.conf test is successful` 就是没问题。

**2）脚本改坏会自动回滚，不用慌。**
每次改动前都会备份到 `/data/errorjiang-backup/allow-<时间戳>/`，
`nginx -t` 检查不过就自动把备份拷回去，网站不会中断。

**3）真要手动回滚：**

```bash
ls -t /data/errorjiang-backup/ | head          # 看最近几个备份目录
cp /data/errorjiang-backup/allow-xxxxxxxx-xxxxxx/errorjiang-admin-allow.conf \
   /etc/nginx/conf.d/errorjiang-admin-allow.conf
nginx -t && systemctl reload nginx
```

---

## 八、三个容易踩的坑

1. **白名单关着的时候，往名单里加 IP 是没用的** —— 必须先 `strict` 才会生效。
2. **开启白名单后，普通账号的注册申请（`/api/register`）也会一起被挡**：
   不在名单里的网络提交注册申请会收到 403。
   如果你希望陌生人随时能提交注册申请，就保持"关闭"状态。
3. **白名单只是额外一层**，管理员密码校验和登录限速一直都在，
   别把它当成"有了白名单就可以用简单密码"。

---

## 九、记不住？就记这三条

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh list     # 看现在什么状态
sudo bash /usr/local/bin/nginx-allow-ip.sh strict   # 只让我进（先 add 自己的 IP）
sudo bash /usr/local/bin/nginx-allow-ip.sh open     # 谁都能进（出门在外用）
```

更完整的服务器运维说明见笔记《Error酱服务器维护手册：小白版》的 10.5 节。
