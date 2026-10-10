// 针对单页单视口做深挖：谁把文档撑宽了
// 用法：node scripts/mobile-probe.mjs /notes 412x915
import { spawn } from "node:child_process";

const CHROME =
  process.env.AUDIT_CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = process.env.AUDIT_BASE || "http://127.0.0.1:8000";
const PORT = 9334;
const target = process.argv[2] || "/";
const size = (process.argv[3] || "412x915").split("x").map(Number);
const UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36";

const PROBE = String.raw`(() => {
  const vw = window.innerWidth;
  const de = document.documentElement;
  const rows = [];
  for (const el of document.body.querySelectorAll("*")) {
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const right = rect.right + window.scrollX;
    const left = rect.left + window.scrollX;
    const id = el.id ? "#" + el.id : "";
    const cls = typeof el.className === "string" && el.className.trim()
      ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
      : "";
    rows.push({
      el: el.tagName.toLowerCase() + id + cls,
      left: Math.round(left),
      right: Math.round(right),
      width: Math.round(rect.width),
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      position: style.position,
      overflowX: style.overflowX,
      minWidth: style.minWidth,
      display: style.display,
      extra: right - vw,
      text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 20),
    });
  }
  rows.sort((a, b) => b.right - a.right);
  return {
    vw,
    docScrollWidth: de.scrollWidth,
    docClientWidth: de.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    htmlOverflowX: getComputedStyle(de).overflowX,
    bodyOverflowX: getComputedStyle(document.body).overflowX,
    widestRight: rows.slice(0, 10),
    widestElement: [...rows].sort((a, b) => b.width - a.width).slice(0, 10),
    bigScrollWidth: rows
      .filter((r) => r.scrollWidth > r.clientWidth + 2)
      .sort((a, b) => b.scrollWidth - b.clientWidth - (a.scrollWidth - a.clientWidth))
      .slice(0, 10),
  };
})()`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    "--user-data-dir=.tmp-mobile-audit/probe-profile",
    "--no-first-run",
    "--disable-extensions",
    "about:blank",
  ],
  { stdio: "ignore" }
);

let version;
for (let i = 0; i < 40; i += 1) {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/json/version`);
    if (res.ok) {
      version = await res.json();
      break;
    }
  } catch {}
  await sleep(250);
}

const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  }
});
const send = (method, params = {}, sessionId) =>
  new Promise((resolve) => {
    const key = ++id;
    pending.set(key, resolve);
    ws.send(JSON.stringify({ id: key, method, params, ...(sessionId ? { sessionId } : {}) }));
  });

const { result: t } = await send("Target.createTarget", { url: "about:blank" });
const { result: attached } = await send("Target.attachToTarget", {
  targetId: t.targetId,
  flatten: true,
});
const sid = attached.sessionId;
await send("Page.enable", {}, sid);
await send("Runtime.enable", {}, sid);
await send(
  "Emulation.setDeviceMetricsOverride",
  {
    width: size[0],
    height: size[1],
    deviceScaleFactor: 3.5,
    mobile: true,
    screenWidth: size[0],
    screenHeight: size[1],
  },
  sid
);
await send("Emulation.setUserAgentOverride", { userAgent: UA, platform: "Android" }, sid);
await send("Page.navigate", { url: BASE + target }, sid);
await sleep(1600);
const evaluated = await send(
  "Runtime.evaluate",
  { expression: PROBE, returnByValue: true },
  sid
);
const selector = process.argv[4];
if (selector) {
  const styleProbe = await send(
    "Runtime.evaluate",
    {
      expression: `(() => {
        const el = document.querySelector(${JSON.stringify(selector)});
        if (!el) return { found: false };
        const s = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return {
          found: true,
          tag: el.tagName.toLowerCase(),
          id: el.id,
          cls: typeof el.className === "string" ? el.className : "",
          fontSize: s.fontSize,
          height: Math.round(rect.height),
          width: Math.round(rect.width),
          visible: rect.width > 0 && rect.height > 0,
          display: s.display,
          flexWrap: s.flexWrap,
          order: s.order,
          flex: s.flex,
          minWidth: s.minWidth,
          parentDisplay: el.parentElement
            ? getComputedStyle(el.parentElement).display + "/" + getComputedStyle(el.parentElement).flexWrap
            : null,
          parentWidth: el.parentElement
            ? Math.round(el.parentElement.getBoundingClientRect().width)
            : null,
        };
      })()`,
      returnByValue: true,
    },
    sid
  );
  console.log("选择器探针:", JSON.stringify(styleProbe.result.result.value));
}
if (!evaluated.result || evaluated.result.exceptionDetails) {
  console.log("求值失败:", JSON.stringify(evaluated, null, 1).slice(0, 1200));
} else {
  console.log(JSON.stringify(evaluated.result.result.value, null, 1));
}
ws.close();
chrome.kill();
process.exit(0);
