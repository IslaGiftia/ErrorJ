// Error酱 移动端 UI 自动审查脚本（零依赖，直接驱动本机 Chrome 的 CDP）
//
// 用法：
//   node scripts/mobile-audit.mjs                  # 全部页面 × 全部视口
//   node scripts/mobile-audit.mjs --pages=home,music --viewports=412x915
//   AUDIT_BASE=http://127.0.0.1:8000 node scripts/mobile-audit.mjs
//
// 产物：
//   .tmp-mobile-audit/<viewport>/<page>.png   首屏截图
//   .tmp-mobile-audit/<viewport>/<page>-full.png  全页截图
//   .tmp-mobile-audit/report.json             机器可读报告
//   stdout 打印每条问题（含元素、尺寸、原因）

import { spawn } from "node:child_process";
import { mkdir, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const CHROME =
  process.env.AUDIT_CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = process.env.AUDIT_BASE || "http://127.0.0.1:8000";
const OUT_DIR = process.env.AUDIT_OUT || ".tmp-mobile-audit";
const PORT = Number(process.env.AUDIT_PORT || 9333);
const MOBILE_UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36";

const PAGES = [
  { name: "home", path: "/" },
  { name: "inventory", path: "/inventory" },
  { name: "login", path: "/login" },
  { name: "register", path: "/register" },
  { name: "messages", path: "/messages" },
  { name: "moments", path: "/moments" },
  { name: "recommendations", path: "/recommendations" },
  { name: "music", path: "/music" },
  { name: "books", path: "/books" },
  { name: "notes", path: "/notes" },
  { name: "notes-detail", path: "/notes", click: ".nt-card" },
  { name: "bookmarks", path: "/bookmarks" },
  { name: "map", path: "/map" },
  // 手机端标记清单是要手动展开的，单独跑一遍带展开状态的组合，
  // 免得「展开后才出现的横向溢出」被漏掉
  { name: "map-panel", path: "/map", click: "#mapActionsToggle" },
  { name: "references", path: "/references" },
  { name: "workbench", path: "/workbench" },
];

const VIEWPORTS = [
  { name: "412x915", width: 412, height: 915, dpr: 3.5, mobile: true },
  { name: "360x800", width: 360, height: 800, dpr: 3, mobile: true },
  { name: "390x844", width: 390, height: 844, dpr: 3, mobile: true },
  { name: "430x932", width: 430, height: 932, dpr: 3, mobile: true },
  { name: "768x1024", width: 768, height: 1024, dpr: 2, mobile: true },
  { name: "915x412", width: 915, height: 412, dpr: 3, mobile: true, landscape: true },
  { name: "1440x900", width: 1440, height: 900, dpr: 1, mobile: false },
];

const args = Object.fromEntries(
  process.argv.slice(2).map((item) => {
    const [key, value] = item.replace(/^--/, "").split("=");
    return [key, value ?? true];
  })
);
const onlyPages = args.pages ? String(args.pages).split(",") : null;
const onlyViewports = args.viewports ? String(args.viewports).split(",") : null;
const pagesToRun = PAGES.filter((p) => !onlyPages || onlyPages.includes(p.name));
const viewportsToRun = VIEWPORTS.filter(
  (v) => !onlyViewports || onlyViewports.includes(v.name)
);

// ---------------------------------------------------------------- 页内审查脚本
const AUDIT_SCRIPT = String.raw`(() => {
  const out = { issues: [], stats: {} };
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const de = document.documentElement;

  const label = (el) => {
    if (!el || !el.tagName) return "?";
    const id = el.id ? "#" + el.id : "";
    let cls = "";
    if (typeof el.className === "string" && el.className.trim()) {
      cls = "." + el.className.trim().split(/\s+/).slice(0, 3).join(".");
    }
    const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 24);
    return el.tagName.toLowerCase() + id + cls + (text ? " «" + text + "»" : "");
  };
  const visible = (el, rect) => {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0)
      return false;
    if (!rect || rect.width < 1 || rect.height < 1) return false;
    // 完全在视口外的元素（例如收起来的抽屉）不算「可见」，否则会把它们算进点击区统计
    if (rect.right <= 0 || rect.left >= window.innerWidth) return false;
    if (rect.bottom <= 0 && rect.top < 0) return false;
    return true;
  };
  const inViewportList = [];
  const all = Array.from(document.body.querySelectorAll("*"));

  // 1) 水平溢出
  out.stats.docScrollWidth = de.scrollWidth;
  out.stats.docClientWidth = de.clientWidth;
  out.stats.horizontalOverflow = de.scrollWidth - de.clientWidth;
  if (de.scrollWidth > de.clientWidth + 1) {
    const offenders = [];
    for (const el of all) {
      const rect = el.getBoundingClientRect();
      if (!visible(el, rect)) continue;
      const right = rect.right + window.scrollX;
      const left = rect.left + window.scrollX;
      if (right > vw + 1 || left < -1) {
        // 只报告"自己就超出视口"的元素，父级容器溢出会另算
        const style = getComputedStyle(el);
        const scrollableX = /auto|scroll/.test(style.overflowX);
        offenders.push({
          el: label(el),
          left: Math.round(left),
          right: Math.round(right),
          width: Math.round(rect.width),
          scrollableX,
        });
      }
    }
    offenders.sort((a, b) => b.right - a.right);
    out.issues.push({
      kind: "horizontal-overflow",
      severity: "P0",
      detail: "文档宽 " + de.scrollWidth + " > 视口 " + de.clientWidth,
      items: offenders.slice(0, 12),
      extraCount: Math.max(0, offenders.length - 12),
    });
  }

  // 2) 固定/粘性栏位置 + 遮挡
  const fixedBars = [];
  for (const el of all) {
    const style = getComputedStyle(el);
    if (style.position !== "fixed" && style.position !== "sticky") continue;
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    fixedBars.push({
      el: label(el),
      position: style.position,
      top: Math.round(rect.top),
      bottom: Math.round(rect.bottom),
      height: Math.round(rect.height),
      zIndex: style.zIndex,
    });
  }
  out.stats.fixedBars = fixedBars.slice(0, 12);

  const bottomBars = fixedBars.filter(
    (b) => b.position === "fixed" && b.bottom > vh - 4 && b.height > 24 && b.height < vh * 0.6
  );
  const topBars = fixedBars.filter((b) => b.position === "fixed" && b.top <= 2 && b.height > 24);
  out.stats.bottomBars = bottomBars;
  out.stats.topBars = topBars;

  // 底部固定栏是否压住最后一段可滚动内容（滚动到最底后仍有内容被挡）
  if (bottomBars.length) {
    const maxBottom = Math.max(...bottomBars.map((b) => b.height));
    const probe = [];
    for (const el of all) {
      if (el.closest("script,style,svg")) continue;
      const rect = el.getBoundingClientRect();
      if (!visible(el, rect)) continue;
      if (!el.textContent || !el.textContent.trim()) continue;
      if (el.children.length > 0) continue;
      const hidden = rect.top < vh - maxBottom + 1 && rect.bottom > vh - maxBottom - 1;
      if (hidden) probe.push({ el: label(el), top: Math.round(rect.top), bottom: Math.round(rect.bottom) });
    }
    if (probe.length) {
      out.issues.push({
        kind: "bottom-bar-occlusion",
        severity: "P1",
        detail: "底部固定栏高约 " + maxBottom + "px，压住了 " + probe.length + " 处文本节点",
        items: probe.slice(0, 8),
      });
    }
  }

  // 3) 可点击区域尺寸
  const clickableSel =
    'a[href], button, [role="button"], input[type="checkbox"], input[type="radio"], select, [onclick], summary, .btn, .chip';
  const smallTargets = [];
  for (const el of document.body.querySelectorAll(clickableSel)) {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    if (el.closest("[hidden]")) continue;
    const w = Math.round(rect.width);
    const h = Math.round(rect.height);
    if (w < 44 || h < 44) smallTargets.push({ el: label(el), w, h });
  }
  if (smallTargets.length) {
    out.issues.push({
      kind: "small-tap-target",
      severity: "P2",
      detail: smallTargets.length + " 个可点击元素小于 44×44",
      items: smallTargets.slice(0, 10),
    });
  }

  // 4) 输入框字号（iOS 会自动放大 <16px 的输入框）
  const smallInputs = [];
  const textInputSel =
    'input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]):not([type="submit"]):not([type="button"]), textarea, select';
  for (const el of document.body.querySelectorAll(textInputSel)) {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 16) smallInputs.push({ el: label(el), fontSize: fs });
  }
  if (smallInputs.length) {
    out.issues.push({
      kind: "input-font-small",
      severity: "P1",
      detail: smallInputs.length + " 个输入控件字号 <16px（手机上聚焦会被放大）",
      items: smallInputs.slice(0, 8),
    });
  }

  // 5) 图片/视频/表格/代码块溢出
  const mediaOverflow = [];
  for (const el of document.body.querySelectorAll("img, video, canvas, table, pre, iframe")) {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    if (rect.width > vw + 1) {
      const style = getComputedStyle(el);
      mediaOverflow.push({
        el: label(el),
        width: Math.round(rect.width),
        parentOverflowX: el.parentElement
          ? getComputedStyle(el.parentElement).overflowX
          : "",
        ownOverflowX: style.overflowX,
      });
    }
  }
  if (mediaOverflow.length) {
    out.issues.push({
      kind: "media-overflow",
      severity: "P1",
      detail: mediaOverflow.length + " 个图片/表格/代码块宽于视口",
      items: mediaOverflow.slice(0, 8),
    });
  }

  // 6) 长单词 / URL 撑破容器
  const longWord = [];
  for (const el of document.body.querySelectorAll("p, li, td, div, span, h1, h2, h3, a")) {
    if (el.children.length) continue;
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const style = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 2 && !/auto|scroll/.test(style.overflowX)) {
      longWord.push({ el: label(el), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
    }
  }
  if (longWord.length) {
    out.issues.push({
      kind: "text-clipped",
      severity: "P1",
      detail: longWord.length + " 处文本被容器裁掉（长单词/URL 未换行）",
      items: longWord.slice(0, 8),
    });
  }

  // 7) 打开着的弹窗 / 抽屉
  const dialogs = [];
  for (const el of document.body.querySelectorAll(
    '[role="dialog"], .modal, .dialog, .drawer, .sheet, [class*="modal"], [class*="dialog"]'
  )) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    if (el.hidden || rect.height < 10) continue;
    const inner = el.firstElementChild ? el.firstElementChild.getBoundingClientRect() : rect;
    dialogs.push({
      el: label(el),
      height: Math.round(rect.height),
      top: Math.round(rect.top),
      bottom: Math.round(rect.bottom),
      innerHeight: Math.round(inner.height),
      overflowY: style.overflowY,
      tallerThanViewport: rect.height > vh + 1,
    });
  }
  if (dialogs.length) {
    out.stats.dialogs = dialogs;
    const bad = dialogs.filter((d) => d.tallerThanViewport && !/auto|scroll/.test(d.overflowY));
    if (bad.length) {
      out.issues.push({
        kind: "dialog-overflow",
        severity: "P1",
        detail: bad.length + " 个弹窗高于视口且自身不可滚动",
        items: bad,
      });
    }
  }

  // 8) 横向滚动容器（表格等允许横滑的地方）
  const scrollers = [];
  for (const el of all) {
    const style = getComputedStyle(el);
    if (!/auto|scroll/.test(style.overflowX)) continue;
    if (el.scrollWidth > el.clientWidth + 2) {
      scrollers.push({ el: label(el), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
    }
  }
  out.stats.horizontalScrollers = scrollers.slice(0, 10);

  // 9) 太小正文字号
  const tinyText = [];
  for (const el of document.body.querySelectorAll("p, li, span, td, label, div")) {
    if (el.children.length) continue;
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const text = (el.textContent || "").trim();
    if (text.length < 4) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 12) tinyText.push({ el: label(el), fontSize: fs });
  }
  if (tinyText.length) {
    out.issues.push({
      kind: "tiny-text",
      severity: "P2",
      detail: tinyText.length + " 处正文小于 12px",
      items: tinyText.slice(0, 8),
    });
  }

  // 9.5) 文字竖排 / 换行过多：短文字被挤成好几行（手机上很常见，肉眼一看就是"乱"）
  const wrapped = [];
  for (const el of document.body.querySelectorAll(
    "button, a, h1, h2, h3, .chip, [class*='tag'], [class*='label'], [class*='title']"
  )) {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const text = (el.textContent || "").trim().replace(/\s+/g, "");
    if (!text || text.length > 14) continue;
    if (el.children.length > 1) continue;
    const style = getComputedStyle(el);
    const fontSize = parseFloat(style.fontSize) || 0;
    if (fontSize <= 0) continue; // font-size:0 的元素（用 ::before 画图标）不算文字
    if (style.whiteSpace === "nowrap" && !/pre/.test(style.whiteSpace)) {
      // nowrap 也可能被 overflow 裁掉，另外单独检查
      if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) {
        wrapped.push({ el: label(el), kind: "nowrap-clipped", width: Math.round(rect.width), text });
      }
      continue;
    }
    // 用 Range 实测文字行数：按 height/line-height 估算会把「固定高度 + 单行文字」的
    // 按钮（例如 44px 高的提交按钮）误判成多行；只看有实际文字的文本节点，
    // 纯空白文本节点和图标元素都会产生无意义的行框。
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const lineTops = [];
    let textNode = walker.nextNode();
    while (textNode) {
      if (textNode.textContent.trim()) {
        const range = document.createRange();
        range.selectNodeContents(textNode);
        for (const r of range.getClientRects()) {
          if (r.width < 0.5 || r.height < 0.5) continue;
          if (!lineTops.some((top) => Math.abs(top - r.top) <= 4)) lineTops.push(r.top);
        }
      }
      textNode = walker.nextNode();
    }
    const lines = Math.max(1, lineTops.length);
    if (lines >= 3 || (lines >= 2 && rect.height > 44 && text.length <= 6)) {
      wrapped.push({
        el: label(el),
        kind: "text-wrapped",
        lines,
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        text,
      });
    }
  }
  if (wrapped.length) {
    out.issues.push({
      kind: "text-wrapped",
      severity: "P1",
      detail: wrapped.length + " 处短文字被挤成多行/竖排",
      items: wrapped.slice(0, 10),
    });
  }

  // 10) 依赖 hover 的交互（桌面才有的 affordance）
  let hoverOnly = 0;
  for (const sheet of document.styleSheets) {
    let rules;
    try {
      rules = sheet.cssRules;
    } catch (err) {
      continue;
    }
    if (!rules) continue;
    for (const rule of rules) {
      if (rule.selectorText && /:hover/.test(rule.selectorText)) hoverOnly += 1;
    }
  }
  out.stats.hoverRules = hoverOnly;

  out.stats.viewportMeta = (() => {
    const m = document.querySelector('meta[name="viewport"]');
    return m ? m.getAttribute("content") : null;
  })();
  out.stats.scroll = {
    y: Math.round(window.scrollY),
    scrollHeight: de.scrollHeight,
    clientHeight: de.clientHeight,
  };
  out.stats.touchActionNone = all.filter((el) => {
    const style = getComputedStyle(el);
    return style.touchAction === "none";
  }).length;
  return out;
})()`;

// ---------------------------------------------------------------- CDP 客户端
class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.listeners = [];
    ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      } else if (msg.method) {
        for (const fn of this.listeners) fn(msg);
      }
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error("CDP 超时: " + method));
        }
      }, 30000);
    });
  }
  on(fn) {
    this.listeners.push(fn);
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForDevtools(port, tries = 40) {
  for (let i = 0; i < tries; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return await res.json();
    } catch (err) {
      /* 继续等 */
    }
    await sleep(250);
  }
  throw new Error("Chrome DevTools 没起来");
}

async function collectPageMetrics(cdp, sessionId) {
  const { result } = await cdp.send(
    "Runtime.evaluate",
    { expression: AUDIT_SCRIPT, returnByValue: true, awaitPromise: false },
    sessionId
  );
  return result.value || { issues: [], stats: {} };
}

async function capture(cdp, sessionId, file, full) {
  const params = { format: "png", captureBeyondViewport: Boolean(full) };
  const shot = await cdp.send("Page.captureScreenshot", params, sessionId);
  await writeFile(file, Buffer.from(shot.data, "base64"));
}

async function run() {
  await rm(OUT_DIR, { recursive: true, force: true });
  await mkdir(OUT_DIR, { recursive: true });
  const profile = path.join(OUT_DIR, "chrome-profile");
  await mkdir(profile, { recursive: true });

  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--disable-background-networking",
      "--disable-features=Translate,OptimizationHints",
      "--mute-audio",
      ...(process.env.AUDIT_FONT_BOOST
        ? ["--blink-settings=textAutosizingEnabled=true"]
        : []),
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  const report = { base: BASE, startedAt: new Date().toISOString(), runs: [] };
  let browserVersion;
  try {
    browserVersion = await waitForDevtools(PORT);
    report.browser = browserVersion.Browser;

    const ws = new WebSocket(browserVersion.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve, { once: true });
      ws.addEventListener("error", reject, { once: true });
    });
    const cdp = new Cdp(ws);
    await cdp.send("Target.setDiscoverTargets", { discover: true });
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });

    await cdp.send("Page.enable", {}, sessionId);
    await cdp.send("Runtime.enable", {}, sessionId);
    await cdp.send("Network.enable", {}, sessionId);
    await cdp.send("Log.enable", {}, sessionId);

    let events = [];
    cdp.on((msg) => {
      if (msg.sessionId !== sessionId) return;
      if (msg.method === "Runtime.exceptionThrown") {
        events.push({
          type: "exception",
          text: msg.params.exceptionDetails?.exception?.description
            || msg.params.exceptionDetails?.text,
        });
      } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
        events.push({
          type: "console-error",
          text: (msg.params.args || []).map((a) => a.value ?? a.description).join(" "),
        });
      } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
        events.push({ type: "log-error", text: msg.params.entry.text });
      } else if (msg.method === "Network.loadingFailed") {
        events.push({
          type: "request-failed",
          text: `${msg.params.type} ${msg.params.errorText}`,
        });
      } else if (msg.method === "Network.responseReceived") {
        const status = msg.params.response.status;
        if (status >= 400) {
          events.push({ type: "http-error", text: `${status} ${msg.params.response.url}` });
        }
      }
    });

    for (const viewport of viewportsToRun) {
      const dir = path.join(OUT_DIR, viewport.name);
      await mkdir(dir, { recursive: true });
      await cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {
          width: viewport.width,
          height: viewport.height,
          deviceScaleFactor: viewport.dpr,
          mobile: viewport.mobile,
          screenWidth: viewport.width,
          screenHeight: viewport.height,
        },
        sessionId
      );
      await cdp.send(
        "Emulation.setTouchEmulationEnabled",
        { enabled: viewport.mobile, maxTouchPoints: viewport.mobile ? 5 : 1 },
        sessionId
      );
      await cdp.send(
        "Emulation.setUserAgentOverride",
        {
          userAgent: viewport.mobile
            ? MOBILE_UA
            : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
          platform: viewport.mobile ? "Android" : "Win32",
        },
        sessionId
      );

      for (const page of pagesToRun) {
        events = [];
        const url = BASE + page.path;
        await cdp.send("Page.navigate", { url }, sessionId);
        await sleep(1400);
        if (page.click) {
          await cdp.send(
            "Runtime.evaluate",
            {
              expression: `(() => {
                const el = document.querySelector(${JSON.stringify(page.click)});
                if (el) el.click();
                return Boolean(el);
              })()`,
              returnByValue: true,
            },
            sessionId
          );
          await sleep(900);
        }
        const metrics = await collectPageMetrics(cdp, sessionId);
        const name = `${viewport.name}/${page.name}`;
        await capture(cdp, sessionId, path.join(OUT_DIR, viewport.name, `${page.name}.png`), false);
        await capture(
          cdp,
          sessionId,
          path.join(OUT_DIR, viewport.name, `${page.name}-full.png`),
          true
        );
        report.runs.push({
          viewport: viewport.name,
          page: page.name,
          url,
          metrics,
          events: events.slice(0, 20),
        });
        const issueKinds = metrics.issues.map((i) => i.kind).join(",");
        console.log(
          `[${name}] overflow=${metrics.stats.horizontalOverflow || 0}px` +
            (issueKinds ? ` issues=${issueKinds}` : " issues=-") +
            (events.length ? ` events=${events.length}` : "")
        );
      }
    }
    await writeFile(path.join(OUT_DIR, "report.json"), JSON.stringify(report, null, 2));
    ws.close();
  } finally {
    chrome.kill();
  }

  // ---- 汇总 ----
  console.log("\n================ 汇总 ================");
  const byKind = new Map();
  for (const run of report.runs) {
    for (const issue of run.metrics.issues) {
      const key = issue.kind;
      if (!byKind.has(key)) byKind.set(key, []);
      byKind.get(key).push({ where: `${run.viewport}/${run.page}`, ...issue });
    }
  }
  for (const [kind, items] of [...byKind.entries()].sort()) {
    console.log(`\n### ${kind}  (${items.length} 处)`);
    for (const item of items.slice(0, 8)) {
      console.log(`  - ${item.where} [${item.severity}] ${item.detail}`);
      const first = (item.items || [])[0];
      if (first) console.log(`      ↳ ${JSON.stringify(first)}`);
    }
    if (items.length > 8) console.log(`  ... 其余 ${items.length - 8} 处见 report.json`);
  }
  const eventCount = report.runs.reduce((sum, r) => sum + r.events.length, 0);
  console.log(`\n控制台/网络异常共 ${eventCount} 条`);
  for (const run of report.runs) {
    for (const ev of run.events.slice(0, 3)) {
      console.log(`  - ${run.viewport}/${run.page}: ${ev.type} ${String(ev.text).slice(0, 120)}`);
    }
  }
  console.log(`\n报告：${path.join(OUT_DIR, "report.json")}`);
  process.exit(0);
}

run().catch((err) => {
  console.error("审查失败:", err);
  process.exit(1);
});
