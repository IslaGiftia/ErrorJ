# Error酱

![Error酱](static/site/error-chan.jpg)

Error酱 是一个自托管的个人工作与学习站点。最开始它只是想做一个电子元件库存管理系统，后来慢慢长成了一个网站：仓库、网页收藏、学习笔记、工作台、AI 提示词、留言板、动态、推荐和小游戏，都放在同一个站里。

- 技术栈很朴素：Python 标准库 HTTP 服务 + SQLite + 原生 HTML / CSS / JavaScript，没有前端框架，也没有构建步骤。
- 数据全部保存在自己的机器上（`data/` 目录），不依赖第三方服务。
- 手机浏览器可以直接使用，适合局域网自用，也可以放到云服务器上通过 Nginx 反代公网访问。
- 界面使用 vivo Sans SC 字体，相关说明见文末「字体」一节。

在线示例：<http://<服务器公网IP>>

源码仓库：<https://github.com/IslaGiftia/ErrorJ>

## 功能

### 仓库（电子元件库存）

- 元件档案：型号、LCSC 编号、品牌、分类、封装、温度范围、耐压、描述、数据手册链接、最低库存提醒和图片。
- 分类树与存放位置树：默认预置电阻、电容、IC、连接器等分类，以及 `XP`、`XA`、`A~Z` 等位置，可继续扩展层级；分类和位置可以组合筛选。
- 搜索同时支持型号、LCSC 编号、位置路径、位置代码、分类名称和描述。
- 批次库存：按批次记录可用数量、已出库数量、购买日期、单价、渠道、订单号和备注；支持快速入库、快速出库。
- 出入库记录可以修改时间和备注，删除后会自动回补库存；所有删除都有二次确认。
- 项目追溯：出库时可关联项目，随时查看每个项目用了哪些元件、各用了多少。
- 待购入清单：记录想买但还没买的元件，可一键转为采购入库。
- LCSC 导入：支持立创商城导出的 `.xlsx`，自动识别字段，并可在后台按 LCSC 编号批量抓取商品图片。
- BOM 缺料对比：导入 PCB 设计软件导出的 BOM（`.csv` / `.tsv` / `.txt` / `.xlsx` / `.xls`），自动识别位号、型号、封装、数量等字段，按 LCSC 或 MPN 匹配库存，生成缺料清单并导出 CSV。
- BOM 文件夹监控：指定本机目录后，服务会定期扫描新放入的 BOM 文件并自动生成报告；同一文件内容不变时不会重复处理。
- 新建项目时可以直接选择 BOM，保存项目后自动完成对比并把报告关联到项目。
- 分类图标、图片悬停放大、搜索栏吸顶、回到顶部等细节都已处理。

### 网页收藏

- 导航模式和列表模式两种视图，支持文件夹归类和多选批量操作。
- 手动拖动排序，也可以按最近添加、最早添加、标题或文件夹排序。
- 内置失效链接检查，可以只查看失效项并批量清理。
- 支持从 Firefox 导入收藏。
- 每个收藏可以保存说明和备注，图标会缓存到本地。
- 推荐模块可以直接引用网页收藏，收藏改名后推荐卡片会自动同步。

### 学习笔记

- Markdown 源文编辑 + 实时预览，支持标题、列表、引用、代码块、表格和链接。
- 顶部固定大纲与面包屑，实时解析 H1/H2/H3，滚动时自动高亮当前小节。
- 图片可以上传、粘贴或拖拽进编辑器，上传前自动缩放到最长边 2000px。
- 笔记列表支持搜索标题、正文和标签，可按标签筛选、按更新时间或标题排序。
- 支持导入 TXT、Markdown、HTML、Word（DOC / DOCX）和 PDF，自动转换为站内 Markdown；Word 内嵌图片会提取到图库，扫描版 PDF 暂不支持 OCR。
- 单篇笔记可以导出为单文件 HTML：图片以 data URI 内嵌，正文保留 Markdown 源文，可离线打开。

### 工作台

- 概览、资料、固件、维修台账四个视图。
- 上传项目源码包、固件、文档和图片，记录版本、目标芯片、目标开发板、在线烧录链接和项目关联。
- 维修台账记录设备、故障现象、诊断过程和处理结果，支持搜索。
- 文件统一保存在 `data/workbench/`。

### AI 提示词

- 管理员专属页面，支持搜索、分类筛选、展开、复制、新增、编辑、删除和置顶。
- 卡片采用扁宽等高布局，长内容在独立弹窗中预览，不会撑开列表。
- 初始提示词来自 `config/prompts-seed.json`，首次初始化数据库时导入。

### 个人站点

- 留言板：游客可以直接留言，昵称会被浏览器记住；每条留言最多 3 个附件，单个不超过 5MB、合计不超过 15MB，图片显示缩略图，其它文件提供下载；支持回复和删除。
- Error酱动态：记录说说和日志，支持最多 9 张配图（可直接粘贴截图）、标签、置顶、编辑和删除；游客可浏览，管理员可发布。
- Error酱推荐：分网站与工具、电影、动漫三类展示；支持封面、评分、年份、观看状态和标签；网站类型可直接关联网页收藏。
- 参考项目：列出参考过的开源项目。
- 小屋里还留着一版照片墙 / 音乐原型（`static/hub.html`），目前没有接到主站导航。

### 游戏大厅

- 五子棋、2048、扫雷、记忆翻牌四个小游戏，全部是纯前端实现，不产生后端请求。
- 电脑端支持键盘操作，手机端支持滑动和长按插旗。
- 得分和最好成绩保存在浏览器本地。

## 账号与权限

默认不设置密码时是免登录模式，局域网内直接使用。设置 `INVENTORY_PASSWORD`（或运行 `python tools/set_password.py`）后会启用登录：

| 身份 | 可访问内容 |
| --- | --- |
| 游客 | 首页、留言板、Error酱动态、Error酱推荐、游戏大厅、参考项目 |
| 普通账号 | 公开页面；仓库、网页收藏、笔记、工作台、AI 提示词仍仅管理员可访问 |
| 管理员 | 全部模块 |

- 普通账号通过 `/register` 提交申请，管理员用 `python tools/manage_users.py` 在服务器上批准、停用或重置密码。
- 密码只保存 PBKDF2-SHA256 哈希；会话使用 HMAC 签名 Cookie（HttpOnly + SameSite=Lax，默认 7 天，勾选“记住我”为 30 天）。
- 登录失败 5 次会锁定 5 分钟；停用账号后已有会话立即失效。
- 写接口按 IP 限速，游客留言限制为每 IP 每分钟 5 条。

## 快速开始

环境要求：Windows / macOS / Linux，Python 3.10 或更高版本。

Windows：

```bat
start-inventory.bat
```

也可以使用 `run.bat`。启动脚本会在需要时自动安装 Word / PDF 文档转换依赖。

macOS / Linux：

```bash
chmod +x run.sh
./run.sh
```

或者直接运行：

```bash
python -m pip install -r requirements.txt
python app.py
```

启动后访问 <http://127.0.0.1:8000>。

### Docker（可选）

```bash
docker compose up -d --build
```

数据仍然保存在项目目录的 `data/` 文件夹中。

### 手机局域网访问

1. 手机和电脑连接同一个 WiFi。
2. 启动服务后查看启动提示，或用 `ipconfig`（Windows）/ `ifconfig`（macOS / Linux）找到电脑的局域网 IP。
3. 手机浏览器打开 `http://电脑IP:8000`。

Windows 首次访问如果被防火墙拦截，需要放行 TCP 8000：

```text
netsh advfirewall firewall add rule name="Errorjiang 8000" dir=in action=allow protocol=TCP localport=8000
```

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `INVENTORY_HOST` | `0.0.0.0` | 监听地址 |
| `INVENTORY_PORT` | `8000` | 监听端口 |
| `INVENTORY_PASSWORD` | 空 | 设置后启用登录 |
| `INVENTORY_SECRET` | 自动生成 | 会话签名密钥，保存在 `data/auth.json` |
| `INVENTORY_TRUST_PROXY` | 关闭 | 走 Nginx 反代时读取 `X-Forwarded-For` / `X-Forwarded-Proto` |
| `INVENTORY_SECURE_COOKIES` | 关闭 | 强制使用 Secure Cookie（HTTPS 环境） |
| `INVENTORY_ACCESS_LOG` | 关闭 | 打开访问日志 |

## 公网部署

推荐结构：

```text
浏览器
  -> Nginx（80 / 443）
  -> 127.0.0.1:8000
  -> systemd 服务 errorjiang
  -> /opt/errorjiang/app.py
  -> /opt/errorjiang/data
```

- 反向代理示例：`deploy/nginx-errorjiang.conf`
- systemd 单元：`deploy/errorjiang.service`
- 只监听回环的 Docker 方案：`docker-compose.prod.yml`

服务器上至少要做三件事：把 `INVENTORY_PASSWORD` 写进 `/etc/errorjiang.env`、让应用只监听 `127.0.0.1`、用 Nginx 转发并配置 HTTPS。完整的部署过程见 `DEPLOYMENT_LOG.md`，面向新手的服务器维护步骤见 `ERRORJIANG_MAINTENANCE.md`。

## 数据与备份

所有运行数据都在 `data/` 目录：

```text
data/inventory.db           SQLite 主数据库
data/auth.json              密码哈希与会话密钥（不要提交或外传）
data/bom_reports/           BOM 对比报告
data/workbench/             工作台文件与固件
data/note_images/           笔记图片
data/moment_images/         动态配图
data/site_message_files/    留言附件
data/recommend_images/      推荐封面
data/part_images/           元件图片
data/bookmark_favicons/     网页收藏图标
```

Windows 本地部署可以用 `backup.ps1` 把整个系统（代码、数据库、BOM 报告、工作台文件）打包到 `D:\InventoryBackups`，并自动清理 30 天前的旧备份：

```powershell
powershell -ExecutionPolicy Bypass -File backup.ps1
```

Linux 服务器可以用 `tools/backup_linux.sh`，配合 cron 定时执行：

```cron
0 3 * * * bash /opt/errorjiang/tools/backup_linux.sh /data/errorjiang-backup
```

恢复时把备份解压回项目目录，再启动服务即可。

## 项目结构

```text
app.py                  后端：HTTP 服务、数据库、权限、导入导出、BOM 对比
requirements.txt        Python 运行依赖（Word / PDF 文档转换）
static/                 前端页面与静态资源
  site/                 首页、主题、下雨动画、返回逻辑
  index.html / app.js / styles.css        仓库（元件库存）
  bookmarks.*           网页收藏
  notes.*               学习笔记
  workbench.*           工作台
  prompts.*             AI 提示词
  messages.*            留言板
  moments.*             Error酱动态
  recommendations.*     Error酱推荐
  games/                五子棋、2048、扫雷、记忆翻牌
  fonts/                vivo Sans 字体与许可协议
config/                 提示词初始数据等配置
data/                   运行时数据（数据库、上传文件、报告，已加入 .gitignore）
deploy/                 Nginx 反代示例与 systemd 单元
tools/                  设置密码、用户审批、文档导入、Linux 备份脚本
docker-compose.yml      本地 Docker 运行
docker-compose.prod.yml 公网 Docker 运行（只监听回环）
backup.ps1              Windows 整站备份脚本
fetch_lcsc_images.py    按 LCSC 编号批量抓取元件图片
```

## 字体

界面使用 vivo Sans SC 可变字体（vivo Sans 官方字体包，Version 1.05）。网页端使用由官方 TTF 无损转换的 WOFF2 副本，字形集合与字重轴均未改动；字体文件和《vivo Sans 字体知识产权许可协议》位于 `static/fonts/vivo-sans/`。

本应用使用了 vivo Sans 字体。

## 相关文档

- `PROJECT_SUMMARY.md`：完整的功能记录与需求演进。
- `DEPLOYMENT_LOG.md`：阿里云部署过程与故障处理记录。
- `ERRORJIANG_MAINTENANCE.md`：面向新手的服务器维护手册。

## 后续方向

- 迁移到 PostgreSQL，支持更大的数据量。
- 增加更多供应商的导入模板。
- 条码扫码入库 / 出库。
- 把小屋的照片墙和音乐模块接到主站。
- 继续打磨移动端体验和弱网下的加载速度。
