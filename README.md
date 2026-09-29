# 元件库存

本地运行的电子元件库存管理系统，中文界面为主，保留 `MPN`、`Package`、`Datasheet`、`Purchase Order` 等英文专业术语。支持电脑浏览器和安卓手机通过局域网访问。

## 核心功能

- 元件资料：型号、LCSC 编号、品牌、分类、封装、温度范围、耐压、描述、数据手册链接、最低库存提醒。
- 元件图片：详情编辑页可上传或移除图片，元件列表和库存页面显示缩略图，鼠标悬停可放大预览；也可按 LCSC 编号从立创商城批量抓取商品图。
- 库存调整：元件详情编辑页可直接修改库存位置、总库存数量，并关联项目记录出库去向。
- 元件列表：直接显示每个元件的库存位置，可按位置筛选；搜索同时支持位置路径、位置代码和分类名称。
- 分类图标：没有商品图片的元件会按一级分类显示原理图风格图标；页面搜索栏支持吸顶，并提供一键回到顶部按钮。
- 分类树：默认预置电阻、电容、IC、PCB、OLED 显示模块、电感、二极管、晶体管、连接器、电源模块、传感器等；下拉选择按一级分类分组，二级及以下缩进显示。
- 库存筛选：库存页面左侧默认收起分类树和位置树，可按需逐级展开筛选，位置和分类可以组合使用。
- 存放位置：默认预置 `XP`、`XA` 两级，二级为 `A~Z`，三级以后可按 `A1`、`A2` 继续添加。
- 库存管理：按批次记录可用数量、已出库数量、购买日期、单价、渠道、订单号和备注。
- 出入库记录：可修改时间、备注和关联项目，也可删除记录并自动恢复或扣回库存；删除均有二次确认。
- 页面状态：打开仓库系统默认进入仪表盘；按 F5 刷新才回到上次停留的页面。首屏在 HTML 里就只放开目标页面，数据没回来时不会把各模块堆在一起（不再闪屏）。
- 外观主题：只在首页保留“浅色 / 暗色”切换按钮，选择存在浏览器里，全站所有页面共用；其它页面不再单独放切换按钮，已打开的页面会跟着一起变。
- 公开首页与游客模式：首页、留言板、游戏、Error酱动态、参考项目和 AI 提示词可公开访问；仓库、网页收藏、笔记和工作台需要登录，未登录时显示“登录后查看”。
- 源码入口：首页“Error酱源码”在新标签页直接打开 `https://github.com/IslaGiftia/ErrorJ`。
- 登录状态：首页右上角显示“游客 / 已登录”，点击可打开无头像登录弹窗；管理员解锁全部模块，普通账号只读解锁仓库和网页收藏。
- 普通账号：`/register` 提交注册申请，管理员在服务器批准后可登录。普通账号只能只读访问仓库和网页收藏，不能用笔记和工作台，也不能修改任何仓库或收藏数据。
- 项目追溯：出库时选择项目，可查看每个项目用了哪些元件、每种元件用了多少；新建项目时可选择 BOM 文件自动生成缺料对比。
- 待购入清单：记录想买但还没买的元件，可一键转为采购入库并自动创建或关联元件。
- LCSC 导入：支持立创商城导出的 `.xlsx`，自动识别字段并生成数据手册链接。
- 图片自动抓取：重新上传 LCSC 采购清单后，默认在后台自动补齐新元件的商品图片。
- BOM 缺料对比：导入 PCB 设计软件导出的 BOM（CSV / Excel），按 LCSC 编号或厂家型号匹配库存，生成缺料清单并支持导出 CSV。
- 工作台：集中管理项目源码包、固件、文档和图片，支持版本、目标芯片、开发板、在线烧录链接、项目关联和维修台账。
- 学习笔记：支持 Markdown 编辑、图片粘贴与导入 TXT、Markdown、HTML、Word、PDF；文档会自动转换为站内可阅读的 Markdown，Word 内嵌图片会保存到笔记图库，单篇笔记可导出为内嵌图片和源文的单文件 HTML。
- AI 提示词：`/prompts` 提供可管理的提示词库，游客可搜索、展开和复制，管理员可新增、编辑、删除和置顶，首页入口位于“Error酱动态”旁边。
- 游戏大厅：`/games` 收录五子棋、2048、扫雷、记忆翻牌，全部是纯前端小游戏，手机可直接玩（键盘方向键 / 滑动 / 长按插旗）。
- 日常：`/moments` 记录说说和日志，支持配图（可直接粘贴截图）、标签、置顶、编辑和删除。

## 本地运行（不需要 Docker）

环境要求：Windows / macOS / Linux，Python 3.10 或更高版本。

Windows：

```bat
start-inventory.bat
```

也可以使用 `run.bat`。关机或重启电脑后，需要再次运行这个脚本，库存数据不会丢失。

macOS / Linux：

```bash
chmod +x run.sh
./run.sh
```

也可以直接运行：

```bash
python -m pip install -r requirements.txt
python app.py
```

启动后访问：

```text
http://127.0.0.1:8000
```

服务默认监听 `0.0.0.0:8000`，可用环境变量修改：

```bash
set INVENTORY_PORT=8080
python app.py
```

## Docker 运行（可选）

如果已经安装 Docker Desktop，可在项目目录执行：

```bash
docker compose up -d --build
```

访问地址相同。数据保存在项目目录的 `data/` 文件夹中。

## 手机局域网访问

1. 手机和电脑连接同一个 WiFi。
2. 启动服务后查看启动提示，或运行 `ipconfig`（Windows）/ `ifconfig`（macOS/Linux）找到电脑的局域网 IP，例如 `192.168.1.10`。
3. 手机浏览器打开 `http://192.168.1.10:8000`。

Windows 首次访问时，如果防火墙拦截，需要允许 TCP 8000 端口：

```text
netsh advfirewall firewall add rule name="Component Inventory 8000" dir=in action=allow protocol=TCP localport=8000
```

当前版本支持游客公开浏览、普通账号申请制注册和管理员审批。普通账号只读访问仓库与网页收藏，笔记、工作台和全部修改操作仍仅限管理员。

## 开机自启

Windows 登录后会自动在后台启动元件库存服务，不显示黑色命令行窗口。

需要关闭自启时，删除启动目录中的 `元件库存自动启动.lnk` 即可。

## LCSC 导入

在“导入”页面选择立创商城导出的 `.xlsx` 文件，选择默认分类和默认位置后开始导入。

导入时会识别以下字段：

- 商品编号 -> LCSC 编号
- 品牌
- 厂家型号 -> MPN
- 封装
- 商品名称 -> 描述
- 订购数量（修改后）
- 商品单价

“是否不发批货”和“毛重”不会被导入。已存在元件时会更新品牌、封装、描述并追加库存批次；也可以在导入页面关闭该选项，遇到已存在元件时跳过。

## 从立创商城批量抓取元件图片

如果元件资料里已经填写了 LCSC 编号，可以运行：

```bash
python fetch_lcsc_images.py
```

脚本会打开每个 LCSC 商品页并下载商品正面图，保存到 `data/part_images/`，随后元件列表和库存页面会自动显示缩略图。已有图片默认跳过，不重复下载；用 `--force` 可覆盖已有图片。抓不到的页面会记录并跳过，不影响其他元件。

## BOM 缺料对比

在“BOM 缺料”页面选择 PCB 设计软件导出的文件，支持 `.csv`、`.tsv`、`.txt`、`.xlsx` 和旧版 `.xls`（旧版 `.xls` 需要本机已安装 `xlrd`）。常见导出模板会自动识别：

- 位号 / Designator / Reference Designator
- 型号 / Comment / Manufacturer Part / Value
- 封装 / Footprint
- 数量 / Quantity
- LCSC / Supplier Part / JLC Code

匹配规则默认“自动”：先按 BOM 中的 LCSC 编号匹配，没有 LCSC 或匹配不到时再按厂家型号 MPN 精确匹配，最后才尝试按描述包含匹配。也可以在页面手动改为只按 LCSC、只按型号或只按描述。

对比结果会显示每个元件的需求数量、当前可用库存、缺口、匹配到的库存元件和匹配方式，并可一键导出 CSV。每次对比会保留在“最近对比记录”中，手机浏览器同样可以查看和下载。

“文件夹自动监控”可以填写一个本机文件夹路径，服务会定期扫描新放入的 BOM 文件并自动生成缺料报告；同一文件内容不变时不会重复处理。

新建项目时也会出现“选择 BOM（可选）”入口：上传 BOM 后保存项目，系统会自动完成对比并把报告关联到该项目；不选 BOM 则只创建项目，不产生对比记录。项目详情里可以直接查看该项目关联的 BOM 缺料清单。

## 数据备份

全部数据保存在 `data/inventory.db`，BOM 对比记录保存在 `data/bom_reports/`，工作台文件保存在 `data/workbench/`。备份脚本会把整个系统目录（代码、界面、数据库、BOM 报告和工作台文件）一起压缩到 D 盘：

```powershell
powershell -ExecutionPolicy Bypass -File backup.ps1
```

脚本默认保存到 `D:\InventoryBackups`，文件名包含日期时间，例如 `inventory_backup_20260830_023136.zip`，并自动清理 30 天前的旧备份。数据库会使用 SQLite 在线备份方式生成一致副本，不会因为备份时正在写入而损坏。

本机已经注册了计划任务 `ComponentInventoryBackup`，每天 12:00 整自动执行。也可以在 Windows 任务计划程序中手动查看或修改这个任务。

恢复时把最新压缩包解压，把 `app.py`、`static/`、`data/` 等文件放回 `C:\lX.NeT`，再启动服务即可。

## 项目结构

```text
app.py                 Python 后端、数据库、LCSC 导入和 BOM 对比
requirements.txt       Python 运行依赖（Word / PDF 文档转换）
backup.ps1             整个系统自动备份到 D 盘的 PowerShell 脚本
fetch_lcsc_images.py   按 LCSC 编号从立创商城批量抓取元件图片
static/index.html      中文响应式界面
static/app.js          页面交互逻辑
static/styles.css      界面样式
static/prompts.html    AI 提示词页面
static/prompts.css     AI 提示词样式
static/prompts.js      AI 提示词交互与管理员操作
static/prompts-seed.json 首次初始化时导入的默认提示词
static/register.html   普通账号注册申请页
static/site/role-mode.js 普通账号只读界面控制
data/inventory.db      运行时自动创建的数据库
Dockerfile             可选 Docker 镜像
docker-compose.yml     可选 Docker 部署配置
docker-compose.prod.yml 公网部署配置（只监听 127.0.0.1 + 密码 + 时区）
deploy/                 Nginx 反代示例与 systemd 单元
tools/                  设置密码、Linux 备份、文档导入等脚本
tools/manage_users.py  审批、创建、停用和重置普通用户账号
```

## 后续扩展方向

- PostgreSQL 数据库
- 更多供应商导入模板
- 条码扫码入库/出库
