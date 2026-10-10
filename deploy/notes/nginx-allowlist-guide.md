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

前提是手机上有一套能用的 SSH 客户端 + 一把专门的私钥（下面第六节有喂饭步骤，
密钥已经生成好了，放在电脑桌面 `Error酱-VPN\手机SSH\phone_termius`）。

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

**办法 B+（去网吧 / 借别人电脑专用）**：临时全部放开，到点自动收回

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh open 2h
```

意思是"这 2 小时谁都能访问后台登录页，2 小时后自动切回 `strict`"，
不用惦记着回来手动关。适合人在网吧、又不想在别人电脑上装东西的场景。
⚠️ 这段时间后台登录页对全网开放，所以密码要够长；
如果你刚把密码改短了，就用下面的 `add` 只放行网吧那台机器的 IP，更稳。

**办法 B++（网吧最稳）**：在网吧电脑上打开「我的 IP」查到出口 IP，
然后用手机执行：

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh add 123.45.67.89 2h
```

只放行那一台机器的 IP，2 小时后自动移除。

**办法 C**：重新挂一次 VPN，回到上面「首选办法」。

**不建议**：做成"网页上一键把自己 IP 加进白名单"的救援链接 —— 那等于给后台再开一个后门，
谁拿到链接谁就能把自己放进来。

**白名单到底管哪些东西（最容易误会的地方）**

- **管**：`/api/login`（提交登录）、`/logout`、`/workbench`、`/api/workbench`、
  `/api/prompts`、`/api/admin`。
- **不管**：浏览网页、普通账号登录和注册。普通账号的会话不绑 IP，
  在手机流量和家里 WiFi 之间来回切都不会被踢下线。
- **额外一层**：**管理员会话绑定登录时的来源 IP**（2026-10-10 起）。
  换了网络，下一次请求就会被判失效、要求重新登录；而重新登录要过白名单，
  所以出门在外要么先连 VPN，要么按上一节的办法临时放行自己的 IP。
  （这条对站长和拥有「管理员」权限的账号生效，普通账号不受影响。）

**管理员密码怎么改**

工作台 →「账号权限」→「登录密码」标签页，填当前密码 + 新密码（8-128 位）→ 修改密码。
改完立即生效，不用重启服务；同一账号在其它设备上的登录会被下线。
这个页面只有站长能打开（普通管理员看不到改密码的权限）。

---

## 六、手机 SSH（Termius）：喂饭版设置

这一节做一次，之后出门在外就能用手机改白名单。

**为什么单独给手机一把密钥**

电脑上那把 `C:\Users\Administrator\.ssh\id_ed25519` 是主钥匙，不要往手机里搬。
已经给手机单独生成了一把（`phone_termius`），公钥装在服务器上，
万一手机丢了，把服务器上这一行删掉就废掉它，电脑那把不受影响。

手机上的密钥文件在电脑桌面：`Error酱-VPN\手机SSH\phone_termius`

**第一步：把密钥传到手机（三种选一种）**

- **最好：USB 数据线**（不经过任何第三方）。手机插上电脑 → 解锁 → 下拉通知选「传输文件 / MTP」→
  把 `phone_termius` 这个文件复制到手机的「下载 / Download」文件夹。
- 或者：**在同一个 WiFi 下走局域网**（需要我在这边临时开个下载服务，联网前跟我说一声）。
- 或者：用微信「文件传输助手」发给自己（方便，但文件会经过腾讯服务器，能不用尽量不用）。

**第二步：手机装 Termius**

应用商店搜 **Termius**（黑色图标，官方那个），装好打开。

**第三步：把密钥导进 Termius**

1. 底部导航点「**Keychain**」（钥匙串）
2. 右上角「**+**」→ 选「**Import key**」/「导入密钥」
3. 选「**File**」→ 找到刚才放进手机「下载」里的 `phone_termius` 文件
4. 名字随便填（比如 `手机钥匙`），保存

**第四步：新建一台主机**

1. 底部导航点「**Hosts**」→ 右上角「**+**」
2. 按这个填：
   - Label / 名称：`Error酱服务器`
   - Address / 地址：`47.108.86.201`
   - Port / 端口：`22`
   - Username / 用户名：`root`
   - Key / 密钥：选第三步导入的那把
3. 保存，回到列表点它
4. 第一次连接会弹「未知主机 / 指纹」，点 **Trust / 信任并继续**，然后把指纹填进去确认：
   `SHA256:+8qQb1+V61fYvBlhBGE+O8oFTW3mK0DcYylWr51VUr8`

连上后看到 `root@iZxxxxx:~#` 就成了。

**第五步：记住四条短命令（免费版也能用）**

**Termius 免费版够用**：SSH、SFTP、本地密钥库、端口转发都免费（免费版叫 Starter）。
收费的是 Pro（US$10/月），主要是跨设备同步、会话日志和 **Snippets 自动化**——
所以下面这套不需要花钱，直接在终端里手打几个字母就行。

服务器上已经装好一条短命令 `allow`，手机上只需要敲：

```bash
allow                 # 看当前状态和名单（等于 list）
allow open 2h         # 临时全放开 2 小时，到期自动收回（网吧用这个）
allow strict          # 立刻收回白名单
allow add 1.2.3.4 2h  # 只放行某个 IP 2 小时
```

命令都很短，手打不费劲。如果嫌记不住，把它们抄在手机备忘录里，
或者直接打开站内笔记 #21 复制（`/` 后面接 `notes` 那个页面，登录后能看到）。

⚠️ 时长只认「数字 + `s`/`m`/`h`/`d`」（例如 `2h`、`30m`、`1d`）。
写错了脚本会直接拒绝执行、**不会改动白名单**，所以手滑多打一个字也不会出意外。

（如果你以后自己开了 Termius Pro，也可以把它们存成 Snippets 一键执行，
命令内容就是上面这四条，或者把 `allow` 换成完整路径
`bash /usr/local/bin/nginx-allow-ip.sh` 一样能用。）

**安全提醒**

- 手机上一定要设锁屏密码 / 指纹，密钥就存在手机里。
- 手机丢了或换手机：让服务器执行下面这句就能作废这把钥匙（电脑上的主钥匙不受影响），
  或者微信/QQ 上找我帮你弄：
  ```bash
  sed -i '/phone-termius/d' /root/.ssh/authorized_keys
  ```

---

## 七、常用命令（复制就能用）

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

## 八、改坏了怎么办

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

## 九、三个容易踩的坑

1. **白名单关着的时候，往名单里加 IP 是没用的** —— 必须先 `strict` 才会生效。
2. **游客注册申请不受白名单影响**（2026-10-10 起已解耦）：`/api/register`、
   `/api/member/login` 和浏览网页一样对任意网络开放，只受接口限速约束。
   注册申请另有额度：同一 IP 24 小时最多 3 次，并且同一 IP 同时只能有
   1 条待审核申请，额度用完会提示"明天再试"。
3. **白名单只是额外一层**，管理员密码校验和登录限速一直都在，
   别把它当成"有了白名单就可以用简单密码"。

---

## 十、记不住？就记这三条

```bash
sudo bash /usr/local/bin/nginx-allow-ip.sh list     # 看现在什么状态
sudo bash /usr/local/bin/nginx-allow-ip.sh strict   # 只让我进（先 add 自己的 IP）
sudo bash /usr/local/bin/nginx-allow-ip.sh open     # 谁都能进（出门在外用）
```

更完整的服务器运维说明见笔记《Error酱服务器维护手册：小白版》的 10.5 节。
