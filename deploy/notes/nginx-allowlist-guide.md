# Error酱管理员入口白名单：喂饭版操作笔记

这篇只讲一件事：**怎么让"只有我的 IP 能进管理员后台"，以及怎么临时放行一个 IP。**
跟着做就行，每条命令都能直接复制；改坏了网站也不会挂，脚本会自动回滚。

> 先记住一句话：白名单**现在是开着的**（2026-10-10 起），
> 只有名单里的 IP / 网段能打开登录页和后台，其它网络会收到 403。
> 想临时放开，执行下面「出门在外」那一节的命令就行。
>
> 不受白名单影响的只有两件事：**游客浏览网页**和**普通账号注册申请 / 登录**。

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

**首选办法：连 VPN（服务器上已经装好了，2026-10-10 实测通过）**

服务器上装了 WireGuard。手机连上 VPN 之后，服务器看到你的来源就是 `10.66.0.2`，
这个网段早就在白名单里，所以走到哪都能直接开后台，**不用改任何配置**。

手机上一次性的设置（只做一次）：

1. 应用商店搜 **WireGuard**，装官方那个（开发者写的是 WireGuard Development Team）
2. 打开 App → 右上角「**+**」→ 选「**从二维码创建隧道**」
3. 在电脑上双击打开 `C:\Users\Administrator\Desktop\Error酱-VPN\phone.png`，
   把二维码显示在屏幕上，手机对着扫（别用微信扫，一定要在 WireGuard App 里扫）
4. 给隧道起个名字（比如 `Error酱`），保存
5. 打开开关，第一次会弹「允许添加 VPN 配置」，点允许

电脑端同理：装 WireGuard for Windows，导入同一个文件夹里的 `laptop.conf`。

连上之后直接开 `https://zhexiyan.cc/login` 就能登后台。平时在家不用挂 VPN
（家里的 IP 也在白名单里），出门再开。

⚠️ 万一连上 VPN 却打不开网站，按顺序查两件事：

1. 阿里云控制台 → 这台 ECS 的安全组 → **入方向** → 有没有一条「自定义 UDP、51820/51820」的规则。
   （这些 UDP 口默认是关的，加规则只能在控制台点，SSH 改不了）
2. 服务器上执行 `ip -4 addr show wg0`，除了 `10.66.0.1/24`，
   还应该看到 `47.108.86.201/32`。阿里云的公网 IP 是边缘做的一对一映射，
   服务器自己并不知道有这个名字；不认领这个地址的话，从隧道进来的包会被内核丢掉，
   表现就是**浏览器一直在转圈**（`wg show` 里能看到手机发来一堆字节、服务器几乎没回）。
   这个地址已经写进 `wg0.conf` 的 `PostUp`，正常情况下重启也会自动加上。

**保底办法：SSH 进服务器改白名单**

前提是手机上有一套能用的 SSH 客户端 + 服务器那把私钥。
推荐 Termius（iOS / Android），把电脑上的 `C:\Users\Administrator\.ssh\id_ed25519` 导进去。

为什么这条路一定通：**SSH 不走白名单**（白名单只管网页入口），
所以哪怕你被挡在登录页外面，手机 SSH 也永远进得去。

连上之后下面三种挑一个：

**办法 A（推荐）**：先查自己在当前网络下的 IP，临时放行 8 小时

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.89 8h
```

意思是"这个 IP 放行 8 小时，到点自动删掉"，不用你记着回来手动删。

**办法 B（最省事）**：直接把白名单关掉，谁都能登录

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh open
```

用完记得 `strict` 收回来。

**办法 C**：重新挂一次 VPN，回到上面「首选办法」。

**不建议**：做成"网页上一键把自己 IP 加进白名单"的救援链接 —— 那等于给后台再开一个后门，
谁拿到链接谁就能把自己放进来。

**白名单到底管哪些东西（最容易误会的地方）**

- **管**：`/api/login`（提交登录）、`/logout`、`/workbench`、`/api/workbench`、
  `/api/prompts`、`/api/admin`。
- **不管**：浏览网页、普通账号登录和注册，以及**你已经登录的管理员会话**。
  会话只认 Cookie、不绑 IP，所以在外面（哪怕 VPN 没连）刷新页面仍然显示登录状态、
  点「退出登录」也能正常退出，**只有「重新登录管理员」这一步会被挡成 403**。

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
2. **游客注册申请不受白名单影响**（2026-10-10 起已解耦）：`/api/register`、
   `/api/member/login` 和浏览网页一样对任意网络开放，只受接口限速约束。
   注册申请另有额度：同一 IP 24 小时最多 3 次，并且同一 IP 同时只能有
   1 条待审核申请，额度用完会提示"明天再试"。
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
