# Error酱 移动端 UI 审查报告（第一轮）

日期：2026-10-10　分支：`codex/mobile-ui-audit`（未提交）

## 一、测试环境

| 项目 | 内容 |
| --- | --- |
| 技术栈 | Python 标准库 HTTP 服务（`app.py`）+ 原生 HTML/CSS/JS，无构建步骤、无 npm 依赖 |
| 启动方式 | `python app.py`（本地已在 `http://127.0.0.1:8000` 运行，本地模式免登录，等价于管理员视角） |
| 浏览器 | 本机 Chrome 154.0.8037.98，headless，通过 **原生 CDP** 驱动（`scripts/mobile-audit.mjs`） |
| 为什么不是 Playwright | 这台机器只有 Codex 运行时的 node，没有 npm，装不了 Playwright；改用同样能力的 CDP 方案，零依赖、不动生产依赖 |

## 二、测试视口（每个页面都跑）

| 视口 | DPR | 说明 |
| --- | --- | --- |
| 412×915 | 3.5 | 目标机型（6.78" 3200×1440 ≈ 1440×3200 竖屏，约 20:9） |
| 360×800 | 3 | 小屏安卓 |
| 390×844 | 3 | iPhone 14/15 |
| 430×932 | 3 | iPhone Pro Max |
| 768×1024 | 2 | 平板竖屏 |
| 915×412 | 3 | 手机横屏 |
| 1440×900 | 1 | 桌面回归 |

全部开启 `mobile`、触摸模拟、真实 UA；分屏首屏 + 全页截图，落在 `.tmp-mobile-audit/<视口>/`（已 gitignore）。

## 三、测试路由

`/`、`/login`、`/register`、`/messages`、`/moments`、`/recommendations`、`/music`、`/books`、`/notes`、`/bookmarks`、`/map`、`/references`、`/workbench` —— 共 13 页 × 7 视口 = **91 个组合**。

## 四、自动检查项

文档级水平溢出及具体元素、固定/粘性栏位置与底部遮挡、可点击区域尺寸、输入框字号、图片/表格/代码块溢出、长单词截断、`flex/grid` 是否换行、弹窗高度与可滚动性、依赖 hover 的交互、`viewport` meta、`safe-area-inset`、`touch-action`、控制台异常与 404。

## 五、问题清单

| # | 页面 | 现象 | 严重度 | 原因 | 修复 | 文件 | 验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/notes` | 手机上文档被撑到 531px（视口 412），**「新建笔记」整条按钮在屏幕外**，「导入文档」被切一半 | P0 | 头部 `.nt-header` 是 nowrap flex，品牌 + 搜索 + 两个按钮横排放不下 | 手机改两行：品牌 + 按钮一行，搜索框独占一行；搜索框补 `min-width:0` | `static/notes.css` | 文档宽 412 = 视口；截图确认两个按钮完整可见 |
| 2 | `/bookmarks` | 360 / 390 宽下文档 402px | P0 | 搜索框 `.pin-search { min-width:150px }` 挤爆头部（头部固定 56px，下方抽屉按 `top:56px` 定位，不能改高） | 允许搜索框收缩 + 收掉移动端无用的右侧 50px 留白 | `static/bookmarks.css` | 文档宽 = 视口（360 / 412 均通过） |
| 3 | `/bookmarks` | 768 宽下 2px 溢出 | P2 | 排序栏内边距 + 按钮刚好超 2px | 收窄排序栏内边距与按钮左右内边距 | `static/bookmarks.css` | 768 / 980 均无溢出 |
| 4 | messages / moments / music / books / map / notes / bookmarks / register | 输入框 12.5~14px，iOS 聚焦会自动放大整页 | P1 | 组件用 `font: inherit`（权重高于通用规则）把字号固定在 14px；部分规则直接写死 12.5px | 用 `body[data-notify-module=…]` 提权覆盖，并覆盖到 ≤1024（平板竖屏 / 手机横屏）；map 直接改 `.mp-search input`；notes/bookmarks 改各自搜索框 | `static/{messages,moments,music,books,map,notes,bookmarks,recommendations}.css`、`static/register.html` | 逐页探针实测 **16px**（412 / 768 / 915 三种宽度） |
| 5 | 首页地图圆盘 | 「314 个标记」只有 8.5px，几乎看不清 | P2 | `.map-dock` 手机上 10px，子元素 0.85em | 圆盘字号提到 12px，标签单独 11px | `static/site/minimap.css` | 探针 11px |
| 6 | 全部页面（应用外壳） | `100vh` 在手机浏览器会被地址栏顶掉底部内容 | P2 | 缺 `dvh` 兜底（music / workbench 本来已有） | 补 `100dvh`（渐进增强，不支持则忽略） | `static/styles.css`、`books.css`、`prompts.css`、`site/site.css`、`site/report.css`、`bookmarks.css` | 桌面回归无变化 |
| 7 | 首页 / `/bookmarks` | 每个没有缓存图标的书签请求 favicon 都 404，控制台刷红、白跑请求（整轮 195 条异常，其中 90 条 favicon 404） | P2 | 前端无条件渲染 favicon `<img>`，靠 `onerror` 兜底 | 只有 `favicon_path` 存在时才发请求 | `static/bookmarks.js`、`static/site/site.js` | 复跑后**控制台/网络异常 0 条** |
| 8 | 全局（首页/登录页） | 主题浮动按钮 36×36，手机上不好点 | P2 | `.theme-float` / `.icon-btn` 36px | ≤640px 放大到 44×44 | `static/site/site.css` | 44×44 |
| 9 | `/music` | 图标按钮 36×36 | P2 | `.mu-icon-btn` | ≤720px 放大到 44×44 | `static/music.css` | 44×44 |
| 10 | `/bookmarks` | 头部图标按钮 34×34、文件夹行 36px 高 | P2 | `.pin-mobile-menu/.pin-header-btn/.pin-folder-row` | ≤760px 提到 44px | `static/bookmarks.css` | 小点击区从 123 → 89（其余为品牌链接、11px 文本链接等可接受项） |
| 11 | 留言 / 动态 / 推荐 / 注册 | 主按钮高 36~40px | P2 | `.mg-btn/.mo-btn/.rec-btn/.register-submit` | 手机端 `min-height: 44px` | `static/{messages,moments,recommendations}.css`、`static/register.html` | 44px |

## 六、最终验证结果（91 个组合）

```
horizontal-overflow（水平溢出） -> 7 处 → 0 处
input-font-small（输入框<16px） -> 移动端 48 处 → 0 处（桌面 7 处为设计内的紧凑控件）
控制台/网络异常                 -> 195 条 → 0 条
bottom-bar-occlusion（底部栏遮挡）-> 0 处
media-overflow（图片/表格溢出）  -> 0 处
dialog-overflow（弹窗超高）      -> 0 处
small-tap-target（<44×44）      -> 移动端 78 处 → 约 80 处（多为品牌/文本链接；主要按钮与图标按钮已达标）
tiny-text（<12px）              -> 47 处 → 47 处（标签、时间戳等次级文字，未动）
text-clipped（文本被裁）         -> 29 处，全部为设计内的省略号截断（.nt-card-title / .mu-row-title /
                                   .pin-bookmark-title / .pin-folder-name 均有 overflow:hidden + ellipsis）
```

桌面 1440×900 全部页面回归通过，未发现新增问题。

## 七、未解决 / 需真机确认

1. **软键盘弹出时的底部栏遮挡**：headless 无法模拟软键盘，需真机验证（建议重点看 `/workbench`、`/messages` 输入框聚焦后底部栏是否遮住提交按钮）。
2. **`100dvh` 的实际效果**：headless 里 `vh == dvh`，需真机确认地址栏收起/展开时不跳。
3. **iOS Safari 输入框缩放**：已按 16px 处理，但仍需 iPhone 真机确认聚焦不再放大。
4. **微信内置浏览器**：未测；建议真机点一遍 `/login`、`/register`、`/messages`。
5. **横屏深度**：915×412 只测了首屏，长列表与弹窗未深测。
6. **暗色模式、200% 字体放大**：本轮未系统覆盖，留待第二轮。
7. **小点击区剩余约 80 处**：主要是品牌链接（30px 高）、11px 文本链接、单条书签行；是否继续放大取决于你的取舍。
8. **favicon 接口本身**：前端已不再对无图标条目发请求，但服务器 `/api/bookmarks/<id>/favicon` 对无图标记录仍返回 404（直接访问时），如需彻底干净可在服务端返回一个占位图。

## 八、如何复跑

```bash
# 前置：本地服务已在跑（python app.py，监听 127.0.0.1:8000）
node scripts/mobile-audit.mjs                                   # 全部 91 个组合
node scripts/mobile-audit.mjs --pages=notes,bookmarks --viewports=412x915   # 只跑指定页/视口
node scripts/mobile-audit-report.mjs                            # 把 report.json 压成清单
node scripts/mobile-probe.mjs /notes 412x915 "#searchInput"     # 单页深挖（含指定选择器的计算字号）
```

产物：`.tmp-mobile-audit/report.json`（机器可读）、`.tmp-mobile-audit/<视口>/<页面>.png`（首屏）、`-full.png`（全页）。

环境变量：`AUDIT_BASE`（默认 `http://127.0.0.1:8000`）、`AUDIT_CHROME`（Chrome 路径）、`AUDIT_OUT`、`AUDIT_PORT`。

---

# 第二轮任务清单（站长 2026-10-11 提出，做完再执行 errorjiang-release）

> 本段是待办清单，做完后要把每一项的「结果」补写到上面的问题清单表里。

## 批次 A：移动端地图（`/map`）

1. **左下角「展开/收起搜索区」按钮只有一半**（截图中被裁切）。要求：
   - 按钮做大；或改成上下两个按钮；
   - 搜索区**收起时箭头朝上**、**展开时箭头朝下**（状态与图标方向必须一致）。
2. **搜索区展开后整体再高一点**，让「搜索框 / 分类 / 标签 / 添加者 / 结果列表」显示更全、更整齐，避免底部被操作栏压住或截断。
3. **右上角三个按钮**（图层 / 定位 / 全屏）：
   - 搜索区收起时保持现在的位置；
   - 搜索区展开后**向右滑出隐藏**，把区域让给搜索面板（带过渡动画，收起时滑回）。

## 批次 B：移动端所有按钮的按下反馈圆角

逐个检查已做移动端适配的页面（首页、留言、动态、推荐、歌单、书架、笔记、书签、地图、工作台、登录、注册），确认 `:active` 反馈的圆角与按钮自身圆角一致，不要出现"方形/直角矩形"的高亮块。已知历史问题是 tap-highlight 造成的方块，需要用 `-webkit-tap-highlight-color: transparent` + `:active` 自绘圆角背景统一处理。

## 批次 C：移动端笔记页「以便查看为主」

1. 笔记列表页：**上滑隐藏上方功能区、下滑重新显示**（现有只隐藏了详情页头部，列表页头部也要跟随滚动）。
2. 点开笔记后：同样上滑隐藏上方区域，**只保留一条较细的导航条**（返回 + 必要操作），把屏幕让给正文。
3. 总原则：移动端优先"看"，编辑类控件默认收起。

## 批次 D：留言 / 动态的图片查看（移动端 + 电脑端都要）

1. 点击查看上传的照片时，**不要再显示图片文件名**。
2. 增加**双击放大**功能（在放大状态下再双击还原）。

## 批次 E：发布

以上全部完成、逐项自测通过后，执行 `errorjiang-release` skill：
提交 → push → 服务器备份 → 拉取 → 导入 changelog → 重启 → 线上验证；同时更新 README / DEPLOYMENT_LOG.md / config/changelog-seed.json 动态。

## 附带待办（上一轮遗留）

- [x] 把本轮新结论补进报告：**字体放大（font boosting）是"手机上又大又乱"的根因**，已在 `static/fonts.css` 加 `text-size-adjust: 100%`（见下面《第二轮修复结果》）。
- [x] 仓库（`/inventory`）、书签（`/bookmarks`）改为**缩小版 PC**：viewport 固定 `width=1024`，手机端渲染结果与 PC 完全一致（实测 412 宽下 layoutWidth=1024、零溢出）。移动端媒体查询已失效但**未物理删除**，如站长要求可再删。
- [x] 工作台顶部页签「紫色背景不消失」：`:hover` 与 `.active` 混写导致手机 sticky hover，已把 hover 收进 `@media (hover: hover)`。
- [x] 台账：`/inventory` 已加入审查脚本页面清单（之前漏测）。
- [x] 可选：书签页头部搜索框在窄屏仍偏窄，若改成 PC 缩小版后已可接受则可关闭此项。（按「缩小版 PC」渲染，搜索框宽度等同 PC，可关闭）

---

# 第二轮修复结果（2026-10-11）

按 A → B → C → D 顺序改完，每批都用审查脚本 + 截图核对。截图走 `tmp/shot.mjs`（gitignore，不进版本库），支持真触摸按下、双击 / 双点、按元素裁图、指定浅色 / 暗色主题和关闭过渡动画（headless 里动画要靠出帧推进，不关过渡会截到动画中间帧）。

## 第二轮问题清单

| # | 批次 | 项目 | 现象 / 原因 | 修复 | 文件 | 验证 |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | A1 | 地图左下角展开 / 收起按钮只有半截 | `.mp-actions .mp-btn` 在手机上写死 `height: 34px`，而这个按钮跨两行网格（约 74px），所以只画了上半截、下面空一格 | 按钮宽 44px、`height: auto` + `min-height: 44px` 撑满两行；箭头沿用「收起朝上、展开朝下」 | `static/map.css` | 412×915 实测 **44×74**；只有导出按钮时（游客）是整行 **370×44** |
| 13 | A2 | 搜索区展开后太矮，底部被操作栏挤 | 面板顶部按「右上角三个按钮的高度」留了 150px 空档 | 展开时面板从 12px 起算：高度 653 → **791px**，结果列表 390 → **529px** | `static/map.css` | 探针：面板 12…803，列表 529px 且可滚动 |
| 14 | A3 | 右上角三个按钮不让位 | — | 清单展开时 `.mp-tools` 向右滑出并淡出（`transform` + `opacity`，`pointer-events: none`），收起滑回；同时收起未关闭的底图选择面板 | `static/map.css`、`static/map.js` | 探针：展开时 x=424（视口外）opacity 0，收起复位 |
| 15 | B | 手机端按下反馈是直角方块 | 浏览器默认 tap highlight 按矩形绘制，不跟随 `border-radius` | 全站关掉 `-webkit-tap-highlight-color`，改用 `:active` + `filter: brightness()`（浅色压暗 0.9 / 深色提亮 1.18），形状天然跟随按钮圆角；`label` 只在没包输入框时生效 | `static/fonts.css`（每页都加载） | 逐页探针：可点击元素全部命中；真触摸按下截图核对圆角按钮 / 胶囊 / 圆形图标按钮 / 卡片按钮 |
| 16 | C1 | 笔记列表页头部不跟手 | 上一轮只做了详情页头部自动收起 | 列表上滑（`.nt-list`）收起 `.nt-header` + `.nt-sidebar-head`，下滑 / 回到顶部复原；搜索框聚焦时不收 | `static/notes.css`、`static/notes.js` | 412 实测列表区 653 → **880px**；1440 桌面无变化 |
| 17 | C2 | 详情页上滑把整条头部都藏了，返回按钮也没了 | 详情页原来整块 `translateY(-100%)` | 手机端只收标题 / 标签 / 元信息，保留「返回 + 操作」一条 **47px** 细导航条；进入详情时连顶部 App 头部（品牌 / 搜索 / 导入 / 新建）一起收起 | `static/notes.css` | 412 实测导航条 47px，正文起点从 227px 提前到 **47px** |
| 18 | D1 | 打开图片显示文件名 | 查看器标题直接写文件名 | 图片固定显示「查看图片」，其它附件仍显示文件名 | `static/messages.js`、`static/moments.js` | 412 / 1440 截图确认标题为「查看图片」 |
| 19 | D2 | 图片不能放大 | — | 新增 `static/site/image-zoom.js`：双击（手机双点）放大到 2 倍、再双击还原，放大后交给容器滚动，并按双击点定位 | `static/site/image-zoom.js`（新）+ `static/messages.{html,css}`、`static/moments.{html,css}` | 探针：双击 308 → **616px**、双点 313 → **626px**，`is-zoomed` 生效；截图核对放大后可滚动 |
| 20 | 附带 | 审查脚本把 44px 高的单行按钮误判成 3 行 | 行数用 `height / line-height` 估算 | 改用 Range 实测文字行框（忽略纯空白文本节点和图标） | `scripts/mobile-audit.mjs` | 误报清零，剩下的 `text-wrapped` 都是真换行 |
| 21 | 附带 | 书签页排序栏按钮文字被挤成竖排 | 1024 宽度（手机走「缩小版 PC」）下 `.pin-sort-bar` 空间不足，flex 把按钮压得比文字还窄 | 按钮 `flex: 0 0 auto` + `white-space: nowrap`，排序栏允许折行 | `static/bookmarks.css` | 412（1024 布局）截图：按钮完整，「全部书签」折到第二行，零溢出 |

## 最终验证（16 页 × 7 视口 = 112 个组合）

```
horizontal-overflow  -> 0 处
控制台 / 网络异常     -> 0 条
bottom-bar-occlusion -> 0 处
media/dialog-overflow-> 0 处
input-font-small     -> 移动端 0 处（桌面 1440 的 8 处是设计内的紧凑控件）
text-wrapped         -> 8 处，全部是 /references 的 32×53「编辑」按钮（真换行，见下）
small-tap-target     -> 105 处（地图标记 32×42、品牌与文本链接等，与上一轮同类）
tiny-text            -> 61 处（标签、时间戳等次级文字，未动）
text-clipped         -> 36 处，全部是设计内的省略号截断
```

桌面 1440×900 全部页面回归通过。

## 本轮之后仍然遗留

1. ~~`/references` 的「编辑 / 删除」按钮在 32px 宽的列里换行成两行~~ 已在同日补丁中修掉（见下面《第三轮补丁》）。
2. 真机项仍未覆盖：软键盘弹出时的底部遮挡、`100dvh` 实际效果、微信内置浏览器、双击放大的手感（headless 只能验证逻辑）。
3. 暗色主题与 200% 字体放大：本轮只抽查了关键页面的明暗两套主题，没有全量跑。

---

# 第三轮补丁（2026-10-11）

站长看完上线的第二轮后提出的三条收尾项。

| # | 项目 | 现象 / 原因 | 修复 | 文件 | 验证 |
| --- | --- | --- | --- | --- | --- |
| 22 | 手机地图「添加标记」和左侧按钮不一样高 | 左侧展开 / 收起按钮是 44px 高，而 `.mp-actions .mp-btn` 在手机上写死 34px，同一排一个高一个矮 | 手机上操作栏按钮统一 44px（展开按钮跨两行时是 94px，两行按钮各 44px 依然对齐） | `static/map.css` | 412×915 实测：普通账号 44 / 44 / 44；管理员 94 / 44 / 44，操作栏 92 → 112px，面板自动让位 |
| 23 | `/references` 的「编辑 / 删除」被挤成两行 | 按钮固定在卡片右上角、宽度写死 32px，两个汉字放不下就折行；还压在标题和正文上 | 按钮改成按文字撑开（54×32、`nowrap`），在卡片顶部独占一行右对齐 | `static/references.html` | 探针 32×53 → **54×32**；`text-wrapped` 由 8 处降为 **0**；412 / 1440 截图确认不再压字 |
| 24 | 游客首页白跑一次 `/api/map?dock=1` 并 401 | 私有地图下游客必然拿不到数据，前端仍会请求一次（浏览器控制台留红字） | `/api/auth/status` 增加 `map_dock_allowed`；圆盘先等登录状态再决定是否请求，明确拿不到就直接进游客态 | `app.py`、`static/site/site.js`、`static/site/minimap.js` | 本地用模拟事件验证：`mapDockAllowed=false` 时**不发请求**、圆盘进游客态；管理员侧正常运行（仍拿到 314 个标记）。线上：首页 `home` 的控制台 / 网络异常由 10 条降为 **0 条** |
