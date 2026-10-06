# Error酱

Error酱 是一个自托管的个人工作与学习站点。最开始它只是想做一个电子元件库存管理系统，后来慢慢长成了一个网站：仓库、网页收藏、学习笔记、工作台、AI 提示词、留言板、动态、推荐和小游戏，都放在同一个站里。

- 技术栈很朴素：Python 标准库 HTTP 服务 + SQLite + 原生 HTML / CSS / JavaScript，没有前端框架，也没有构建步骤。
- 数据全部保存在自己的机器上（`data/` 目录），不依赖第三方服务。
- 手机浏览器可以直接使用，适合局域网自用，也可以放到云服务器上通过 Nginx 反代公网访问。
- 界面使用 vivo Sans SC 字体，相关说明见文末「字体」一节。

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

### 地图

- 首页左下角有一枚圆形小地图入口（PUBG 风格），实时显示最近浏览区域和标记点，点开进入 `/map`。
- 标记支持名称、别名、地址、招牌推荐、标签、备注、经纬度、打卡状态（想去 / 去过）、推荐度（1~5 星）和照片（每个标记最多 9 张、单张不超过 8MB），按分类着色并用一个字做图标。
- 分类是两级结构：一级分类（例如美食、景点、酒店）下面可以挂二级分类，管理员可以新增、改名、换色换字、删除一级或二级分类；删除一级分类时它的下级分类会一并删除，原来的标记会变成未分类。
- 管理员可以编辑和管理所有标记；普通账号可以新增标记，并编辑、移动、删除自己新增的标记和照片，不能改动别人的和管理员添加的内容。
- 支持关键字搜索、一级 / 二级分类筛选、标签筛选、聚合显示、定位、全览，以及高德 / 百度导航链接。
- 底图可在右上角切换：高德矢量、高德卫星、Esri 深色、Esri 卫星和 OSM 标准；高德底图会自动做 WGS84 与 GCJ-02 坐标换算，保证标记不偏移。
- 底图按主题分别记忆：浅色模式默认高德矢量、深色模式默认 Esri 深色，在每个主题下手动换过底图后，下次进入该主题仍是你的选择；重新进入站点时会按 Error酱当前的全局主题取对应底图。深色底图额外叠加地名注记，并限制到瓦片原生缩放级别，避免放大后发虚。
- 底图瓦片由访客浏览器直接向高德 / OpenStreetMap / Esri 获取，不经过 Error酱 服务器；服务器只提供页面、标记数据和照片，所以浏览地图不会增加服务器带宽压力。
- 导入支持 GeoJSON、KML、GPX、CSV（名称,经度,纬度）和 MapBridge 插件导出的高德收藏（`format: mapbridge`）。普通文件可以在导入时选择坐标来源：WGS-84（OSM / Google / 本站导出）、GCJ-02（高德 / 腾讯网页导出）或 BD-09（百度），系统会自动换算成 WGS-84 后再保存；MapBridge 文件的坐标本来就是 WGS-84，会自动识别处理。导入需要登录：目标分类留空时按文件里的分类路径自动归类（管理员会创建缺失的分类），选择具体分类则全部归入该分类；同名同坐标的标记会自动跳过，可以放心重复导入。
- 导出 GeoJSON 仅管理员可用。
- 全新安装时地图是空的，不含任何内置示例标记；迁移数据可以用页面上的导出 / 导入，或用 `tools/map_transfer.py` 在两台机器之间整体迁移（带分类树、打卡状态、评分和照片）。
- 瓦片来自高德、OpenStreetMap、Esri 的在线服务，标记数据始终只保存在自己的 `data/` 里；如果地图内容是私密的，设置 `INVENTORY_MAP_PUBLIC=0` 后地图只对管理员可见。

### 工作台

- 概览、资料、固件、维修台账、提示词、账号权限、内容审核七个视图；原来的 AI 提示词模块已经并进这里，成为工作台的一个标签页。
- 上传项目源码包、固件、文档和图片，记录版本、目标芯片、目标开发板、在线烧录链接和项目关联。
- 维修台账记录设备、故障现象、诊断过程和处理结果，支持搜索。
- 文件统一保存在 `data/workbench/`。

### AI 提示词（工作台内）

- 工作台的「提示词」标签，管理员可见，支持搜索、分类筛选、展开、复制、新增、编辑、删除和置顶。
- 卡片采用扁宽等高布局，长内容在独立弹窗中预览，不会撑开列表。
- 初始提示词来自 `config/prompts-seed.json`，首次初始化数据库时导入。

### 歌单（听 Error酱的歌单）

- 首页模块入口，页面 `/music`，所有访客都能听。
- 管理员可以上传歌曲源文件，支持 mp3、wav、flac、m4a、aac、ogg、opus，单个文件最大 60MB；上传后自动读取文件内的歌名、歌手、专辑，并提取内嵌封面（MP3 的 ID3 APIC、FLAC 的 PICTURE、M4A 的 covr）。
- 播放器支持播放 / 暂停、上一首 / 下一首、进度拖动、音量与静音、随机播放、列表循环 / 单曲循环，并接入了系统媒体控制（Media Session），手机锁屏和耳机按键也能控制。
- 音频文件保存在 `data/site_music_files/`，封面保存在 `data/music_covers/`；文件接口支持 HTTP Range，拖动进度不会重新下载整首歌。

### 个人站点

- 留言板：游客可以直接留言，昵称会被浏览器记住；每条留言最多 3 个附件，单个不超过 5MB、合计不超过 15MB，只允许图片（png/jpg/jpeg/gif/webp/bmp）和 pdf/txt/md；附件上传后会先进入审核队列，通过后游客和普通账户才能看到，待审核时只有上传者和管理员可见，工作台「内容审核」里可以通过、拒绝或批量通过；支持回复和删除。
- Error酱动态：记录说说和日志，支持最多 9 张配图（可直接粘贴截图）、标签、置顶、编辑和删除；游客可浏览，管理员可发布。
- Error酱推荐：分网站与工具、电影、动漫三类展示；支持封面、评分、年份、观看状态和标签；网站类型可直接关联网页收藏。
- 参考项目：列出参考过的开源项目。
- 小屋里还留着一版照片墙 / 音乐原型（`static/hub.html`），音乐部分已经由正式的「听 Error酱的歌单」接替。

### 游戏大厅

- 五子棋、2048、扫雷、记忆翻牌四个小游戏，全部是纯前端实现，不产生后端请求。
- 电脑端支持键盘操作，手机端支持滑动和长按插旗。
- 得分和最好成绩保存在浏览器本地。

## 账号与权限

默认不设置密码时是免登录模式，局域网内直接使用。设置 `INVENTORY_PASSWORD`（或运行 `python tools/set_password.py`）后会启用登录：

| 身份 | 可访问内容 |
| --- | --- |
| 游客 | 首页、地图、歌单、留言板、Error酱动态、Error酱推荐、游戏大厅、参考项目 |
| 普通账号 | 默认只有公开页面 + 地图贡献（新增标记、管理自己的标记和照片、导入标记）；其余权限由管理员在工作台逐个发放 |
| 管理员 | 全部模块；站长可以在工作台把「管理员」权限授予第二个账号 |

- 注册需要填写用户名、昵称和密码；昵称 2-16 位、支持中英文/数字/常见符号、全站唯一且会做敏感词检查，同一账号每 30 天可改一次昵称（首页账号菜单里修改）。
- 注册后进入待审核队列。站长/管理员在工作台「账号权限」页里同意、拒绝、停用、重置密码或删除账号，并可以按「模块 + 动作」的权限点逐个发放或收回；所有操作都会写入审计日志。
- 权限点覆盖仓库、网页收藏、笔记、工作台（含提示词）、地图（新增/改全部/管分类/导入/导出）、站点内容（动态、推荐、歌单、链接、照片、留言附件免审核）以及「管理员」；普通账号默认获得 `map:write`、`map:import`。
- 敏感词库在工作台里维护，内置政治（共产党、国民党）、暴力、辱骂、色情、广告几类基础词，可自行增删；匹配会忽略大小写、全角半角和空格/符号干扰，昵称命中直接拒绝注册，留言昵称或正文命中直接拒发，管理端有测试框。
- 有待审核注册时，首页工作台入口会显示紫色呼吸高亮和数量角标，审核完自动消失（不需要邮件系统）。
- 工作台「账号权限 → 通知设置」可以配置 Webhook 推送，把「新注册申请 / 新待审附件 / 新留言」推送到手机或群里：支持企业微信、钉钉、飞书群机器人、Bark（iOS）、Server酱（微信）和通用 JSON Webhook；可以发送测试通知，最近的推送成功/失败记录也会保留在页面里。没有配置时只有站内呼吸提醒，不影响使用。
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
| `INVENTORY_MAP_PUBLIC` | `1` | 设为 `0` 时地图和地图接口仅管理员可访问 |

## 公网部署

推荐结构：

```text
浏览器
  -> Nginx（80 / 443）
  -> 127.0.0.1:8000
  -> systemd 服务 errorjiang
  -> <应用目录>/app.py
  -> <应用目录>/data
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
0 3 * * * bash <应用目录>/tools/backup_linux.sh <备份目录>
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
  prompts.*             AI 提示词（由工作台的提示词标签页加载）
  music.*               歌单（播放器、上传、封面与标签解析）
  messages.*            留言板
  moments.*             Error酱动态
  recommendations.*     Error酱推荐
  map.*                 地图（标记、分类、GeoJSON 导入导出）
  games/                五子棋、2048、扫雷、记忆翻牌
  fonts/                vivo Sans 字体与许可协议
config/                 提示词初始数据等配置
data/                   运行时数据（数据库、上传文件、报告，已加入 .gitignore）
deploy/                 Nginx 反代示例与 systemd 单元
tools/                  设置密码、用户审批、文档导入、地图迁移、Linux 备份脚本
docker-compose.yml      本地 Docker 运行
docker-compose.prod.yml 公网 Docker 运行（只监听回环）
backup.ps1              Windows 整站备份脚本
fetch_lcsc_images.py    按 LCSC 编号批量抓取元件图片
```

## 界面约定

- 弹窗和编辑页统一采用「固定头尾」：标题行（含关闭按钮）在滚动时贴在弹窗顶部，底部操作行（删除 / 取消 / 保存）常驻贴底，只有中间的表单内容滚动。
- 实现方式参考 `static/workbench.css` 的 `.wb-modal-head` / `.wb-modal-actions`，以及 `static/map.css`、`static/music.css`、`static/prompts.css` 里对应的 sticky 规则；新增编辑弹窗时按同样方式处理（`position: sticky` + 负 margin 抵消弹窗内边距）。

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
