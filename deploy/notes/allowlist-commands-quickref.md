**一、Termius 里（连上服务器后直接粘，`allow` 后面加参数就行）**

```bash
allow                 # 看现在是什么状态、名单里有谁
allow open 2h         # 临时放开 2 小时，到点自动关回去（网吧就用这条）
allow strict          # 立刻关回去（只让名单里的 IP 进）
allow add 1.2.3.4 2h  # 只放行某个 IP 2 小时（把 1.2.3.4 换成网吧电脑的 IP）
allow remove 1.2.3.4  # 提前把这个 IP 撤掉，不等它到期
```

说明：`open` 不带时长就是一直放开，得自己记得关；带 `2h` 就自动收回，推荐后者。

**二、阿里云控制台里（不装任何软件，全中文，手机浏览器也能用）**

路径：阿里云控制台 → 云服务器 ECS → 实例 → 找到 `47.108.86.201` 这台 → 「远程命令 / 云助手」→ 发送命令 → 类型选 Shell → 把下面任意一条贴进去执行：

```bash
bash /usr/local/bin/nginx-allow-ip.sh list
bash /usr/local/bin/nginx-allow-ip.sh open 2h
bash /usr/local/bin/nginx-allow-ip.sh strict
bash /usr/local/bin/nginx-allow-ip.sh add 1.2.3.4 2h
```

云助手里写成 `allow open 2h` 一般也能用，但在那儿用完整路径最保险。

**三、只要记住三句**

- 查状态：`allow`
- 出门放开：`allow open 2h`
- 回来收回：`allow strict`

**两个提醒**

1. 时长只认「数字 + `s`/`m`/`h`/`d`」（`30m`、`2h`、`1d`）。写错了脚本会直接拒绝、**不会动白名单**，不会出意外。
2. 网吧想更稳就用 `allow add <网吧IP> 2h`：先在网吧电脑上打开 ip138 查出口 IP，只放行那一台机器，比全放开安全。

这几条在站内笔记 #21 的「七、常用命令」里也有，手机忘了就打开那篇复制。
