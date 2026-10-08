import "/static/vendor/foliate/view.js";
import { createTOCView } from "/static/vendor/foliate/ui/tree.js";
import { Overlayer } from "/static/vendor/foliate/overlayer.js";
import { textWalker } from "/static/vendor/foliate/text-walker.js";
import { searchMatcher } from "/static/vendor/foliate/search.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const bookId = Number(params.get("id") || 0);
const sharedMode = location.pathname === "/books/shared" || params.get("shared") === "1";
const SETTINGS_KEY = "errorReaderSettings";
const LOCAL_PROGRESS_KEY = "errorBookProgress";
const LOCAL_BOOKMARKS_KEY = "errorBookBookmarks";
const LOCAL_ANNOTATIONS_KEY = "errorBookAnnotations";
const SEARCH_LIMIT = 80;
const SAVE_INTERVAL = 800;

const THEME_CSS = {
  light: { paper: "#ffffff", ink: "#1b1f27", link: "#4f46e5" },
  sepia: { paper: "#f7f1e3", ink: "#3b342a", link: "#8a6a2f" },
  dark: { paper: "#1f1f24", ink: "#e8e8ea", link: "#a78bfa" },
};

const state = {
  book: null,
  view: null,
  tocView: null,
  tocFlat: [],
  canSync: false,
  signedIn: false,
  location: "",
  percent: 0,
  tocLabel: "",
  annotations: new Map(),
  annotationByValue: new Map(),
  bookmarks: [],
  pendingSelection: null,
  lastSave: 0,
  progressReady: false,
  settings: {
    theme: "light",
    flow: "paginated",
    fontSize: 100,
    lineHeight: 1.7,
    fontFamily: "",
  },
};

function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : fallback;
  } catch (err) {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {}
}

function toast(message) {
  const el = $("rdToast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    el.hidden = true;
  }, 2600);
}

function api(path, options) {
  return fetch(path, options).then((response) =>
    response
      .json()
      .catch(() => ({}))
      .then((data) => {
        if (!response.ok) throw new Error((data && data.error) || "请求失败：" + response.status);
        return data;
      })
  );
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

// 中文 TXT 常见 GB18030 / Big5 编码，优先看 BOM，再逐个试解码
function decodeTextBytes(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return new TextDecoder("utf-8").decode(bytes.subarray(3));
  }
  if (bytes[0] === 0xff && bytes[1] === 0xfe) {
    return new TextDecoder("utf-16le").decode(bytes.subarray(2));
  }
  if (bytes[0] === 0xfe && bytes[1] === 0xff) {
    return new TextDecoder("utf-16be").decode(bytes.subarray(2));
  }
  for (const encoding of ["utf-8", "gb18030", "big5"]) {
    try {
      return new TextDecoder(encoding, { fatal: true }).decode(bytes);
    } catch (err) {}
  }
  return new TextDecoder("gb18030").decode(bytes);
}

// ---------- 设置与样式 ----------

function loadSettings() {
  const saved = readJSON(SETTINGS_KEY, null);
  if (saved) Object.assign(state.settings, saved);
  const siteTheme = (() => {
    try {
      return localStorage.getItem("errorSiteTheme") || "auto";
    } catch (err) {
      return "auto";
    }
  })();
  if (!saved) {
    state.settings.theme =
      siteTheme === "dark" ||
      (siteTheme === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches)
        ? "dark"
        : "light";
  }
}

function saveSettings() {
  writeJSON(SETTINGS_KEY, state.settings);
}

function bookCSS() {
  const theme = THEME_CSS[state.settings.theme] || THEME_CSS.light;
  return `
    @namespace epub "http://www.idpf.org/2007/ops";
    html {
      color-scheme: ${state.settings.theme === "dark" ? "dark" : "light"};
      background: ${theme.paper};
      color: ${theme.ink};
    }
    body {
      color: ${theme.ink};
      background: ${theme.paper};
      font-size: ${state.settings.fontSize}%;
      ${state.settings.fontFamily ? `font-family: ${state.settings.fontFamily};` : ""}
    }
    a:link { color: ${theme.link}; }
    p, li, blockquote, dd {
      line-height: ${state.settings.lineHeight};
      text-align: justify;
      hanging-punctuation: allow-end last;
      widows: 2;
    }
    [align="left"] { text-align: left; }
    [align="right"] { text-align: right; }
    [align="center"] { text-align: center; }
    [align="justify"] { text-align: justify; }
    pre { white-space: pre-wrap !important; }
    img { max-width: 100%; }
    aside[epub|type~="endnote"],
    aside[epub|type~="footnote"],
    aside[epub|type~="note"],
    aside[epub|type~="rearnote"] { display: none; }
  `;
}

function applySettings() {
  document.body.dataset.readerTheme = state.settings.theme;
  $("rdTheme").value = state.settings.theme;
  $("rdFontSize").value = String(state.settings.fontSize);
  $("rdLineHeight").value = String(state.settings.lineHeight);
  $("rdFontFamily").value = state.settings.fontFamily;
  $("rdFlowBtn").textContent = state.settings.flow === "paginated" ? "翻页" : "滚动";
  if (state.view?.renderer) {
    state.view.renderer.setStyles?.(bookCSS());
    state.view.renderer.setAttribute("flow", state.settings.flow);
  }
  saveSettings();
}

// ---------- TXT / Markdown 转成内存里的 EPUB ----------

function crc32(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    let byte = (crc ^ bytes[i]) & 0xff;
    for (let j = 0; j < 8; j += 1) {
      byte = byte & 1 ? (byte >>> 1) ^ 0xedb88320 : byte >>> 1;
    }
    crc = (crc >>> 8) ^ byte;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function buildZip(files) {
  const encoder = new TextEncoder();
  const parts = [];
  const central = [];
  let offset = 0;
  files.forEach((file) => {
    const nameBytes = encoder.encode(file.name);
    const data = file.data;
    const crc = crc32(data);
    const local = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(local.buffer);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0x0800, true);
    localView.setUint32(14, crc, true);
    localView.setUint32(18, data.length, true);
    localView.setUint32(22, data.length, true);
    localView.setUint16(26, nameBytes.length, true);
    local.set(nameBytes, 30);
    parts.push(local, data);

    const dir = new Uint8Array(46 + nameBytes.length);
    const dirView = new DataView(dir.buffer);
    dirView.setUint32(0, 0x02014b50, true);
    dirView.setUint16(4, 20, true);
    dirView.setUint16(6, 20, true);
    dirView.setUint16(8, 0x0800, true);
    dirView.setUint32(16, crc, true);
    dirView.setUint32(20, data.length, true);
    dirView.setUint32(24, data.length, true);
    dirView.setUint16(28, nameBytes.length, true);
    dirView.setUint32(42, offset, true);
    dir.set(nameBytes, 46);
    central.push(dir);
    offset += local.length + data.length;
  });
  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, files.length, true);
  endView.setUint16(10, files.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  return new Blob([...parts, ...central, end], { type: "application/epub+zip" });
}

function splitChapters(text) {
  const lines = text.split(/\r?\n/);
  const chapters = [];
  let current = { title: "正文", lines: [] };
  const pattern =
    /^\s*(第\s*[0-9零一二三四五六七八九十百千两]+\s*[章节回卷]|Chapter\s+\d+|序章|楔子|尾声)/;
  lines.forEach((line) => {
    if (pattern.test(line) && current.lines.length > 20) {
      chapters.push(current);
      current = { title: line.trim().slice(0, 60), lines: [line] };
      return;
    }
    current.lines.push(line);
  });
  chapters.push(current);
  if (chapters.length === 1) {
    const size = 200000;
    const plain = chapters[0].lines;
    const chunks = [];
    for (let i = 0; i < plain.length; i += 2000) {
      chunks.push({ title: `第 ${Math.floor(i / 2000) + 1} 节`, lines: plain.slice(i, i + 2000) });
    }
    return chunks.length ? chunks : [{ title: "正文", lines: plain }];
  }
  return chapters;
}

function textToXhtml(title, paragraphs) {
  const body = paragraphs
    .map((line) => (line.trim() ? `<p>${escapeHtml(line)}</p>` : "<p>&#160;</p>"))
    .join("");
  return `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>${escapeHtml(title)}</title></head>
<body>${body}</body></html>`;
}

function markdownToChapters(text) {
  const html = window.marked ? window.marked.parse(text) : `<p>${escapeHtml(text)}</p>`;
  const clean = window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
  const container = document.createElement("div");
  container.innerHTML = clean;
  const chapters = [];
  let current = { title: "正文", html: "" };
  Array.from(container.childNodes).forEach((node) => {
    const isHeading = node.nodeType === 1 && /^H[12]$/.test(node.tagName);
    if (isHeading && current.html.trim()) {
      chapters.push(current);
      current = { title: node.textContent.trim().slice(0, 60) || "正文", html: "" };
      return;
    }
    if (isHeading && !current.html.trim()) current.title = node.textContent.trim().slice(0, 60) || "正文";
    current.html += node.outerHTML || escapeHtml(node.textContent || "");
  });
  if (current.html.trim()) chapters.push(current);
  return chapters.length ? chapters : [{ title: "正文", html: `<p>${escapeHtml(text)}</p>` }];
}

async function makeEpubFromText(book, text) {
  const isMarkdown = /\.(md|markdown)$/i.test(book.file_url);
  const encoder = new TextEncoder();
  const chapters = isMarkdown
    ? markdownToChapters(text).map((chapter) => ({
        title: chapter.title,
        xhtml: `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>${escapeHtml(chapter.title)}</title></head>
<body>${chapter.html}</body></html>`,
      }))
    : splitChapters(text).map((chapter) => ({
        title: chapter.title,
        xhtml: textToXhtml(chapter.title, chapter.lines),
      }));
  const title = book.title || "未命名";
  const author = book.author || "";
  const files = [
    { name: "mimetype", data: encoder.encode("application/epub+zip") },
    {
      name: "META-INF/container.xml",
      data: encoder.encode(`<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>`),
    },
    {
      name: "OEBPS/content.opf",
      data: encoder.encode(`<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">errorjiang-${book.id}</dc:identifier>
    <dc:title>${escapeHtml(title)}</dc:title>
    <dc:creator>${escapeHtml(author || "未知作者")}</dc:creator>
    <dc:language>zh-CN</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
${chapters.map((chapter, index) => `    <item id="c${index}" href="c${index}.xhtml" media-type="application/xhtml+xml"/>`).join("\n")}
  </manifest>
  <spine>
${chapters.map((chapter, index) => `    <itemref idref="c${index}"/>`).join("\n")}
  </spine>
</package>`),
    },
    {
      name: "OEBPS/nav.xhtml",
      data: encoder.encode(`<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head>
<body><nav epub:type="toc" id="toc"><h1>目录</h1><ol>
${chapters.map((chapter, index) => `<li><a href="c${index}.xhtml">${escapeHtml(chapter.title)}</a></li>`).join("")}
</ol></nav></body></html>`),
    },
  ];
  chapters.forEach((chapter, index) => {
    files.push({ name: `OEBPS/c${index}.xhtml`, data: encoder.encode(chapter.xhtml) });
  });
  return new File([buildZip(files)], `${title}.epub`, { type: "application/epub+zip" });
}

// ---------- 进度 / 书签 / 批注 ----------

function localBookKey(map, bookIdValue) {
  return map[bookIdValue] || null;
}

function saveLocalProgress() {
  const all = readJSON(LOCAL_PROGRESS_KEY, {});
  all[bookId] = { location: state.location, percent: state.percent, updated_at: new Date().toISOString() };
  writeJSON(LOCAL_PROGRESS_KEY, all);
}

async function saveProgress(force) {
  if (!state.book || !state.progressReady) return;
  if (!force && Date.now() - state.lastSave < SAVE_INTERVAL) return;
  state.lastSave = Date.now();
  if (!state.signedIn) {
    saveLocalProgress();
    return;
  }
  try {
    await api(`/api/books/${bookId}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ location: state.location, percent: state.percent }),
    });
  } catch (err) {
    saveLocalProgress();
  }
}

async function restoreProgress() {
  let progress = null;
  if (state.signedIn) {
    try {
      progress = await api(`/api/books/${bookId}/progress`);
    } catch (err) {}
  }
  const local = localBookKey(readJSON(LOCAL_PROGRESS_KEY, {}), bookId);
  if (!progress || !progress.location) {
    if (local && local.location) progress = local;
  }
  return progress;
}

function localList(key) {
  const all = readJSON(key, {});
  const list = all[bookId];
  return Array.isArray(list) ? list : [];
}

function saveLocalList(key, list) {
  const all = readJSON(key, {});
  all[bookId] = list;
  writeJSON(key, all);
}

async function loadBookmarks() {
  if (state.signedIn) {
    try {
      state.bookmarks = await api(`/api/books/${bookId}/bookmarks`);
      return;
    } catch (err) {}
  }
  state.bookmarks = localList(LOCAL_BOOKMARKS_KEY);
}

async function addBookmark() {
  if (!state.location) {
    toast("先翻到要标记的位置");
    return;
  }
  const label = (state.tocLabel || state.book?.title || "书签") + " · " + Math.round(state.percent * 100) + "%";
  const payload = { location: state.location, label, percent: state.percent };
  if (state.signedIn) {
    try {
      const saved = await api(`/api/books/${bookId}/bookmarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      payload.id = saved.id;
    } catch (err) {
      toast(err.message);
      return;
    }
  } else {
    payload.id = Date.now();
    const list = localList(LOCAL_BOOKMARKS_KEY);
    list.push(payload);
    saveLocalList(LOCAL_BOOKMARKS_KEY, list);
  }
  state.bookmarks.push(payload);
  toast("已添加书签");
  openPanel("bookmarks");
}

async function removeBookmark(id) {
  if (state.signedIn) {
    try {
      await api(`/api/books/${bookId}/bookmarks/${id}`, { method: "DELETE" });
    } catch (err) {
      toast(err.message);
      return;
    }
  } else {
    const list = localList(LOCAL_BOOKMARKS_KEY).filter((item) => Number(item.id) !== Number(id));
    saveLocalList(LOCAL_BOOKMARKS_KEY, list);
  }
  state.bookmarks = state.bookmarks.filter((item) => Number(item.id) !== Number(id));
  openPanel("bookmarks");
}

async function loadAnnotations() {
  let list = [];
  if (state.signedIn) {
    try {
      list = await api(`/api/books/${bookId}/annotations`);
    } catch (err) {}
  } else {
    list = localList(LOCAL_ANNOTATIONS_KEY);
  }
  state.annotations.clear();
  state.annotationByValue.clear();
  list.forEach((item) => {
    const entry = {
      id: item.id,
      value: item.location,
      color: item.color || "yellow",
      note: item.note || "",
      text: item.text || "",
      percent: item.percent || 0,
    };
    let index = 0;
    try {
      index = state.view?.resolveCFI(item.location)?.index ?? 0;
    } catch (err) {}
    const bucket = state.annotations.get(index);
    if (bucket) bucket.push(entry);
    else state.annotations.set(index, [entry]);
    state.annotationByValue.set(entry.value, entry);
  });
}

async function addAnnotation(kind, note) {
  const pending = state.pendingSelection;
  hideSelection();
  if (!pending) return;
  const cfi = state.view.getCFI(pending.index, pending.range);
  if (!cfi) {
    toast("这一处没法定位，换一段试试");
    return;
  }
  const payload = {
    location: cfi,
    text: pending.text.slice(0, 500),
    note: note || "",
    color: kind === "note" ? "violet" : "yellow",
    percent: state.percent,
  };
  if (state.signedIn) {
    try {
      const saved = await api(`/api/books/${bookId}/annotations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      payload.id = saved.id;
    } catch (err) {
      toast(err.message);
      return;
    }
  } else {
    payload.id = Date.now();
    const list = localList(LOCAL_ANNOTATIONS_KEY);
    list.push(payload);
    saveLocalList(LOCAL_ANNOTATIONS_KEY, list);
  }
  const entry = { id: payload.id, value: cfi, color: payload.color, note: payload.note, text: payload.text };
  const bucket = state.annotations.get(pending.index);
  if (bucket) bucket.push(entry);
  else state.annotations.set(pending.index, [entry]);
  state.annotationByValue.set(cfi, entry);
  state.view.addAnnotation(entry);
  toast(kind === "note" ? "批注已保存" : "已划线");
}

async function removeAnnotation(entry) {
  if (state.signedIn) {
    try {
      await api(`/api/books/${bookId}/annotations/${entry.id}`, { method: "DELETE" });
    } catch (err) {
      toast(err.message);
      return;
    }
  } else {
    const list = localList(LOCAL_ANNOTATIONS_KEY).filter((item) => Number(item.id) !== Number(entry.id));
    saveLocalList(LOCAL_ANNOTATIONS_KEY, list);
  }
  try {
    state.view.deleteAnnotation(entry);
  } catch (err) {}
  state.annotationByValue.delete(entry.value);
  for (const [index, list] of state.annotations) {
    const next = list.filter((item) => item.id !== entry.id);
    if (next.length) state.annotations.set(index, next);
    else state.annotations.delete(index);
  }
  toast("已删除");
  openPanel("annotations");
}

// ---------- 侧栏面板 ----------

let panelMode = "";

function openPanel(mode) {
  panelMode = mode;
  const panel = $("rdPanel");
  const body = $("rdPanelBody");
  const title = $("rdPanelTitle");
  $("rdSettings").hidden = true;
  panel.hidden = false;
  if (mode === "toc") {
    title.textContent = "目录";
    body.innerHTML = "";
    if (state.tocView) body.append(state.tocView.element);
    else body.innerHTML = '<p class="rd-empty">这本书没有目录。</p>';
    return;
  }
  if (mode === "search") {
    title.textContent = "全文搜索";
    body.innerHTML = `
      <div class="rd-search-box">
        <input id="rdSearchInput" type="search" placeholder="输入关键词后回车">
      </div>
      <div id="rdSearchResults"></div>`;
    const input = $("rdSearchInput");
    input.focus();
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runSearch(input.value.trim());
    });
    return;
  }
  if (mode === "bookmarks") {
    title.textContent = "书签";
    body.innerHTML = state.bookmarks.length
      ? state.bookmarks
          .map(
            (item) => `<button type="button" class="rd-item" data-bookmark="${item.id}" data-location="${escapeHtml(
              item.location
            )}"><span>${escapeHtml(item.label || "书签")}</span><small>${Math.round(
              (Number(item.percent) || 0) * 100
            )}%</small></button>`
          )
          .join("")
      : '<p class="rd-empty">还没有书签，读到想记住的地方点顶部「书签」。</p>';
    return;
  }
  if (mode === "annotations") {
    title.textContent = "划线批注";
    const items = [];
    state.annotations.forEach((list) => list.forEach((entry) => items.push(entry)));
    body.innerHTML = items.length
      ? items
          .map(
            (entry) => `<div class="rd-item" data-annotation="${entry.id}"><span>${escapeHtml(
              entry.text || "（划线）"
            )}</span>${entry.note ? `<small>${escapeHtml(entry.note)}</small>` : ""}<small>点这里删除</small></div>`
          )
          .join("")
      : '<p class="rd-empty">还没有划线或批注。选中正文文字试试。</p>';
  }
}

function closePanel() {
  $("rdPanel").hidden = true;
  panelMode = "";
}

function hasOverlayOpen() {
  return !$("rdPanel").hidden || !$("rdSettings").hidden;
}

function closeOverlays() {
  if (!$("rdPanel").hidden) closePanel();
  $("rdSettings").hidden = true;
}

async function runSearch(query) {
  const results = $("rdSearchResults");
  if (!query) {
    results.innerHTML = "";
    return;
  }
  results.innerHTML = '<p class="rd-empty">搜索中…</p>';
  const matcher = searchMatcher(textWalker, {
    matchCase: false,
    matchDiacritics: false,
    matchWholeWords: false,
    defaultLocale: "zh",
  });
  const found = [];
  const sections = state.view.book?.sections || [];
  for (let index = 0; index < sections.length && found.length < SEARCH_LIMIT; index += 1) {
    const section = sections[index];
    if (!section.createDocument) continue;
    let doc = null;
    try {
      doc = await section.createDocument();
    } catch (err) {
      continue;
    }
    if (!doc) continue;
    try {
      for (const result of matcher(doc, query)) {
        found.push({
          index,
          cfi: state.view.getCFI(index, result.range),
          pre: result.excerpt?.pre || "",
          match: result.excerpt?.match || query,
          post: result.excerpt?.post || "",
        });
        if (found.length >= SEARCH_LIMIT) break;
      }
    } catch (err) {}
  }
  results.innerHTML = found.length
    ? found
        .map(
          (item) => `<button type="button" class="rd-item" data-cfi="${escapeHtml(item.cfi)}">…${escapeHtml(
            item.pre
          )}<mark>${escapeHtml(item.match)}</mark>${escapeHtml(item.post)}…</button>`
        )
        .join("")
    : '<p class="rd-empty">没有找到匹配内容。</p>';
}

// ---------- 打开书籍 ----------

function hideSelection() {
  state.pendingSelection = null;
  $("rdSelection").hidden = true;
}

async function openBook() {
  if (sharedMode) {
    state.book = await api(`/api/shared/books/${bookId}`);
  } else {
    const books = await api("/api/books");
    state.book = (Array.isArray(books) ? books : []).find((item) => Number(item.id) === bookId) || null;
  }
  if (!state.book) {
    toast("找不到这本电子书");
    return;
  }
  document.title = state.book.title + (sharedMode ? " · 分享阅读" : " · 书架");
  $("rdTitle").textContent = state.book.title || "未命名";
  $("rdAuthor").textContent = state.book.author || "";

  const format = String(state.book.format || "").toLowerCase();

  let source = state.book.file_url;
  if (format === "txt" || format === "md" || format === "markdown") {
    try {
      const response = await fetch(source);
      const text = decodeTextBytes(await response.arrayBuffer());
      source = await makeEpubFromText(state.book, text);
    } catch (err) {
      toast("读取文本失败：" + err.message);
      return;
    }
  } else if (format === "pdf") {
    // npm 版 view.js 没有 PDF 分支，这里自己用 foliate 的 PDF 适配器造书对象
    try {
      const { makePDF } = await import("/static/vendor/foliate/pdf.js");
      const response = await fetch(source);
      if (!response.ok) throw new Error("文件读取失败（" + response.status + "）");
      const blob = await response.blob();
      const file = new File([blob], state.book.title + ".pdf", { type: "application/pdf" });
      source = await makePDF(file);
    } catch (err) {
      toast("PDF 组件加载失败：" + err.message);
      return;
    }
  }

  const view = document.createElement("foliate-view");
  $("rdHost").append(view);
  state.view = view;

  view.addEventListener("load", ({ detail }) => {
    const { doc, index } = detail;
    doc.addEventListener("mouseup", () => {
      const selection = doc.getSelection();
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        hideSelection();
        return;
      }
      state.pendingSelection = {
        index,
        range: selection.getRangeAt(0).cloneRange(),
        text: selection.toString().trim(),
      };
      $("rdSelection").hidden = false;
    });
    // 书页内部的点击不会冒泡到外层，这里单独接一份：左右翻页、中间切换上下栏
    doc.addEventListener("click", (event) => {
      if (doc.getSelection && String(doc.getSelection()).trim()) return;
      if (event.target.closest && event.target.closest("a")) return;
      // 一律用"整屏宽度"分三等分，避免正文列比窗口窄时把中间点成上一页
      const frame = doc.defaultView?.frameElement;
      const rect = frame?.getBoundingClientRect?.();
      const globalX = rect ? rect.left + event.clientX * (rect.width / (doc.defaultView.innerWidth || rect.width)) : event.clientX;
      zoneNavigate(globalX, window.innerWidth);
    });
    const list = state.annotations.get(index);
    if (list) list.forEach((annotation) => view.addAnnotation(annotation));
  });
  view.addEventListener("create-overlay", ({ detail }) => {
    const list = state.annotations.get(detail.index);
    if (list) list.forEach((annotation) => view.addAnnotation(annotation));
  });
  view.addEventListener("draw-annotation", ({ detail }) => {
    detail.draw(Overlayer.highlight, { color: detail.annotation.color || "yellow" });
  });
  view.addEventListener("relocate", ({ detail }) => {
    state.location = detail.location?.current || state.location;
    state.percent = Number(detail.fraction) || 0;
    state.tocLabel = detail.tocItem?.label || state.tocLabel;
    $("rdSlider").value = String(state.percent);
    // 页码：EPUB 是流式排版没有固定页码，书里带"印刷页码"就显示它；
    // PDF 是固定版式，直接显示第几页 / 共几页；都没有就显示百分比。
    const totalPages = (state.view?.book?.sections || []).length;
    let progressText = Math.round(state.percent * 100) + "%";
    if (detail.pageItem?.label) {
      progressText += " · 第 " + detail.pageItem.label + " 页";
    } else if (String(state.book?.format || "").toLowerCase() === "pdf" && totalPages) {
      progressText = "第 " + (Number(detail.index) + 1) + " / " + totalPages + " 页";
    } else if (state.tocFlat.length > 1 && detail.tocItem?.href) {
      // 流式书没有固定页码，用"第几章 / 共几章"代替
      const chapterIndex = state.tocFlat.findIndex((item) => item.href === detail.tocItem.href);
      if (chapterIndex >= 0) {
        progressText += " · 第 " + (chapterIndex + 1) + " / " + state.tocFlat.length + " 章";
      }
    }
    $("rdPercent").textContent = progressText;
    state.tocView?.setCurrentHref?.(detail.tocItem?.href || "");
    // 首次渲染出来的第一页会把进度覆盖掉，等恢复完再开始记录
    if (state.progressReady) saveProgress(false);
  });

  try {
    await view.open(source);
  } catch (err) {
    toast("这本书打不开：" + err.message);
    return;
  }
  view.renderer.setStyles?.(bookCSS());
  view.renderer.setAttribute("flow", state.settings.flow);
  // 上下栏改成覆盖式，正文用 margin 留出同样的高度，切换沉浸时就不会重排乱跳
  view.renderer.setAttribute("margin", "98px");
  // foliate 打开后要先渲染第一屏，否则画布是空的
  try {
    await Promise.race([
      view.renderer.next(),
      new Promise((_, reject) => setTimeout(() => reject(new Error("render timeout")), 7000)),
    ]);
  } catch (err) {
    showRenderFallback();
  }

  const toc = view.book?.toc;
  if (toc) {
    state.tocFlat = flattenToc(toc);
    state.tocView = createTOCView(toc, (href) => {
      view.goTo(href).catch(() => {});
      closePanel();
    });
  }
  const fractions = view.getSectionFractions?.() || [];
  const ticks = $("rdTicks");
  if (ticks) ticks.innerHTML = "";

  await loadBookmarks();
  await loadAnnotations();

  const progress = await restoreProgress();
  const savedPercent = Number(progress?.percent) || 0;
  if (progress?.location) {
    try {
      await view.goTo(progress.location);
    } catch (err) {}
  }
  // 百分比是主力：CFI 失效 / 为空时也能回到原来的位置
  if (savedPercent > 0.005 && Math.abs(state.percent - savedPercent) > 0.06) {
    try {
      await view.goToFraction(savedPercent);
    } catch (err) {}
  }
  state.progressReady = true;
  state.lastSave = 0;
  document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeOverlays();
    return;
  }
    if (event.target.matches("input, textarea, select")) return;
    if (event.key === "ArrowLeft") view.goLeft();
    else if (event.key === "ArrowRight") view.goRight();
  });
}

function flattenToc(items, out = []) {
  (items || []).forEach((item) => {
    if (item && item.href) out.push({ label: item.label, href: item.href });
    if (item && item.subitems) flattenToc(item.subitems, out);
  });
  return out;
}

// 少数浏览器（或内嵌浏览器）不允许 blob iframe，foliate 会一直等不到首屏
function showRenderFallback() {
  const host = $("rdHost");
  if (!host || host.dataset.fallback === "1") return;
  host.dataset.fallback = "1";
  const box = document.createElement("div");
  box.className = "rd-fallback";
  box.innerHTML =
    "<p>当前浏览器没能把这本书渲染出来。</p>" +
    '<p><a href="' +
    escapeHtml(state.book?.file_url || "#") +
    '" target="_blank" rel="noopener">直接打开原文件</a>，或换用最新版 Chrome / Firefox / Edge 阅读。</p>';
  host.append(box);
}

// ---------- 事件 ----------

loadSettings();
applySettings();

$("rdPrev").addEventListener("click", () => state.view?.goLeft());
$("rdNext").addEventListener("click", () => state.view?.goRight());
$("rdSlider").addEventListener("input", (event) => {
  state.view?.goToFraction(Number(event.target.value));
});
$("rdTocBtn").addEventListener("click", () => (panelMode === "toc" ? closePanel() : openPanel("toc")));
$("rdSearchBtn").addEventListener("click", () => (panelMode === "search" ? closePanel() : openPanel("search")));
$("rdNoteBtn").addEventListener("click", () => (panelMode === "annotations" ? closePanel() : openPanel("annotations")));
$("rdBookmarkBtn").addEventListener("click", addBookmark);
$("rdPanelClose").addEventListener("click", closePanel);
$("rdFlowBtn").addEventListener("click", () => {
  state.settings.flow = state.settings.flow === "paginated" ? "scrolled" : "paginated";
  applySettings();
});
$("rdSettingsBtn").addEventListener("click", () => {
  const box = $("rdSettings");
  if (box.hidden && !$("rdPanel").hidden) closePanel();
  box.hidden = !box.hidden;
});

// 沉浸阅读：隐藏顶部功能区与底部进度条，进入时顺便尝试全屏
// 点击分页：左侧 32% 上一页，右侧 32% 下一页，中间切换上下栏（滚动模式只切换上下栏）
function zoneNavigate(clientX, width) {
  if (!state.view || !width) return;
  // 侧栏 / 设置还开着的时候，先收起来再按分区动作
  if (hasOverlayOpen()) closeOverlays();
  const ratio = clientX / width;
  const scrolled = state.settings.flow !== "paginated";
  // 整屏三等分：左 1/3 上一页、右 1/3 下一页、中间 1/3 切换上下栏
  if (ratio < 1 / 3) {
    if (!scrolled) state.view.goLeft();
    return;
  }
  if (ratio > 2 / 3) {
    if (!scrolled) state.view.goRight();
    return;
  }
  // 中间 1/3：隐藏 / 显示上下功能区和进度条（排版区域不变，不会跳页）
  document.body.classList.toggle("is-ui-hidden");
}

document.querySelector(".rd-stage").addEventListener("click", (event) => {
  if (event.target.closest(".rd-fallback") || event.target.closest("a")) return;
  zoneNavigate(event.clientX, window.innerWidth);
});
$("rdTheme").addEventListener("change", (event) => {
  state.settings.theme = event.target.value;
  applySettings();
});
$("rdFontSize").addEventListener("input", (event) => {
  state.settings.fontSize = Number(event.target.value);
  applySettings();
});
$("rdLineHeight").addEventListener("input", (event) => {
  state.settings.lineHeight = Number(event.target.value);
  applySettings();
});
$("rdFontFamily").addEventListener("change", (event) => {
  state.settings.fontFamily = event.target.value;
  applySettings();
});
$("rdSelection").addEventListener("click", async (event) => {
  const action = event.target.closest("[data-act]")?.getAttribute("data-act");
  if (!action) return;
  if (action === "cancel") {
    hideSelection();
    return;
  }
  if (action === "note") {
    const note = window.prompt("写点什么（批注内容）", "");
    if (note === null) return;
    await addAnnotation("note", note.trim());
    return;
  }
  await addAnnotation("highlight");
});
$("rdPanelBody").addEventListener("click", (event) => {
  const bookmark = event.target.closest("[data-bookmark]");
  if (bookmark) {
    if (event.detail === 2 || event.altKey) {
      removeBookmark(bookmark.getAttribute("data-bookmark"));
      return;
    }
    state.view?.goTo(bookmark.getAttribute("data-location")).catch(() => {});
    closePanel();
    return;
  }
  const annotation = event.target.closest("[data-annotation]");
  if (annotation) {
    const entry = Array.from(state.annotationByValue.values()).find(
      (item) => Number(item.id) === Number(annotation.getAttribute("data-annotation"))
    );
    if (entry && window.confirm("删除这条划线 / 批注？")) removeAnnotation(entry);
    return;
  }
  const result = event.target.closest("[data-cfi]");
  if (result) {
    state.view?.goTo(result.getAttribute("data-cfi")).catch(() => {});
    closePanel();
  }
});

window.addEventListener("pagehide", () => saveProgress(true));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") saveProgress(true);
});

api("/api/auth/status")
  .then((status) => {
    state.signedIn = Boolean(status.authenticated);
  })
  .catch(() => {})
  .then(openBook)
  .catch((err) => toast(err.message));
