(function () {
  const state = {
    notes: [],
    activeId: null,
    mode: "read",
    search: "",
    sort: "updated",
    tag: "",
    tagsExpanded: false,
    baseline: { title: "", content: "", tags: "" },
    uploading: 0,
    outline: [],
    outlineActive: -1,
    outlineOpen: false,
    outlineFrame: null,
    lastScrollTop: 0,
    suppressAutoHide: false,
  };

  const $ = (id) => document.getElementById(id);
  const MAX_UPLOAD_SIDE = 2000;
  const MAX_NOTE_CONTENT_CHARS = 2000000;

  const noteLimits = {
    importBytes: 20 * 1024 * 1024,
    imageBytes: 20 * 1024 * 1024,
    imageCount: 20,
  };

  function noteLimitLabel(bytes) {
    return window.ErrorUploadLimits ? window.ErrorUploadLimits.label(bytes) : "20MB";
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    const importLimit = window.ErrorUploadLimits.get("note_import");
    const imageLimit = window.ErrorUploadLimits.get("note_image");
    noteLimits.importBytes = Number(importLimit.max_file_bytes) || noteLimits.importBytes;
    noteLimits.imageBytes = Number(imageLimit.max_file_bytes) || noteLimits.imageBytes;
    noteLimits.imageCount = Number(imageLimit.max_count) || noteLimits.imageCount;
  }

  let themePreference = "auto";
  try {
    themePreference = localStorage.getItem("errorSiteTheme") || "auto";
  } catch (err) {}

  if (window.marked) {
    marked.setOptions({ gfm: true, breaks: true });
  }

  /* ---------- helpers ---------- */

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function parseTime(value) {
    if (!value) return null;
    const parsed = new Date(String(value).replace(" ", "T"));
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function formatTime(value) {
    const parsed = parseTime(value);
    if (!parsed) return "";
    const diff = Date.now() - parsed.getTime();
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diff < minute) return "刚刚";
    if (diff < hour) return Math.floor(diff / minute) + " 分钟前";
    if (diff < day) return Math.floor(diff / hour) + " 小时前";
    if (diff < 7 * day) return Math.floor(diff / day) + " 天前";
    const pad = (n) => String(n).padStart(2, "0");
    return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`;
  }

  function stripMarkdown(text) {
    return String(text || "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`([^`]*)`/g, "$1")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/^\s{0,3}#{1,6}\s*/gm, "")
      .replace(/^\s{0,3}>\s?/gm, "")
      .replace(/^\s{0,3}[-*+]\s+/gm, "")
      .replace(/^\s{0,3}\d+\.\s+/gm, "")
      .replace(/[*_~]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function noteTags(note) {
    return String(note.tags || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }

  function excerptOf(note, length = 120) {
    const text = stripMarkdown(note.content);
    if (!text && note.image_count) return "（图片笔记）";
    return text.length > length ? text.slice(0, length) + "…" : text;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (err) {
      payload = null;
    }
    if (!response.ok) {
      throw new Error((payload && payload.error) || `请求失败（${response.status}）`);
    }
    return payload;
  }

  let toastTimer = null;
  function toast(message) {
    const el = $("toast");
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 2600);
  }

  let confirmAction = null;
  function askConfirm(title, text, okText, onOk) {
    $("confirmTitle").textContent = title;
    $("confirmText").textContent = text;
    $("confirmOk").textContent = okText;
    confirmAction = onOk;
    $("confirmOverlay").hidden = false;
  }

  function closeConfirm() {
    $("confirmOverlay").hidden = true;
    confirmAction = null;
  }

  /* ---------- theme ---------- */

  function applyTheme(preference, save) {
    themePreference = preference;
    const dark =
      preference === "dark" ||
      (preference === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    const glyph = $("themeGlyph");
    if (glyph) glyph.textContent = dark ? "☾" : "☀";
    if (save) {
      try {
        localStorage.setItem("errorSiteTheme", preference);
      } catch (err) {}
    }
  }

  /* ---------- markdown ---------- */

  function normalizeMarkdown(value) {
    return String(value || "")
      .replace(/\r\n?/g, "\n")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  /* ---------- 智能排版 ---------- */
  // 粘贴时做一次初步排版：剪贴板有 HTML 就先转 Markdown（选区优先，整页用 Readability
  // 剥掉导航 / 广告 / 页脚），只有纯文本时走规则排版（统一列表符号、识别标题、
  // 接回被硬换行切断的段落、中英文之间补空格）。不修改任何文字内容，排完可以手动再改。

  const SMART_BULLET_RE = /^(?:[-*+•·▪◦‣●○]|[－—–])\s+/;
  const SMART_ORDER_RE = /^\d{1,3}\s*[.、)）]\s+/;
  const SMART_INDEX_RE = /^(?:第)?[一二三四五六七八九十百]{1,4}\s*[、.．)）]/;
  const SMART_BLOCK_RE = /^(?:#{1,6}\s|>|\||```|<|\[\^)/;
  const SMART_END_RE = /[。！？；：!?;:.…、,，]$/;
  const SMART_PARTICLE_RE = /[啊吧呢吗哦呀嘛哈嗯]$/;
  const SMART_OPENER_RE = /^(?:然后|接着|其次|另外|此外|因此|所以|但是|不过|最后|还有|以及|比如|例如|总之|另外)/;
  const SMART_HEADING_MAX = 42;
  const SMART_HEADING_WIDTH = 30;
  // 折行的行宽阈值（按显示宽度算，一个汉字算 2）：够宽才认为是排版折行，
  // 聊天那种一行一句话的短行不合并
  const SMART_WRAP_WIDTH = 56;

  function isCjkChar(ch) {
    return /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(ch);
  }

  function isWordChar(ch) {
    return /[A-Za-z0-9]/.test(ch);
  }

  function smartWidth(text) {
    let width = 0;
    for (const ch of String(text || "")) {
      width += isCjkChar(ch) ? 2 : 1;
    }
    return width;
  }

  // 盘古之白：中文和英文 / 数字之间补空格，行内代码与链接保持原样
  function panguSpacing(text) {
    return String(text || "")
      .split(/(`[^`\n]*`)/g)
      .map((part, index) => (index % 2 ? part : panguSegment(part)))
      .join("");
  }

  function panguSegment(segment) {
    return String(segment || "")
      .split(/(https?:\/\/[^\s)】」>）]+)/g)
      .map((part, index) => (index % 2 ? part : panguPlain(part)))
      .join("");
  }

  function panguPlain(text) {
    let out = "";
    for (const ch of String(text || "")) {
      const prev = out.slice(-1);
      if (
        prev &&
        ch !== "\n" &&
        prev !== "\n" &&
        ((isCjkChar(prev) && isWordChar(ch)) || (isWordChar(prev) && isCjkChar(ch)))
      ) {
        out += " ";
      }
      out += ch;
    }
    return out;
  }

  function smartJoinLines(left, right) {
    const tail = left.slice(-1);
    const head = right.slice(0, 1);
    const glue = isCjkChar(tail) && isCjkChar(head) ? "" : " ";
    return left + glue + right;
  }

  function smartOrderMarker(match) {
    const number = String(match).trim().replace(/[、)）]$/, ".");
    return /\.$/.test(number) ? number + " " : number + ". ";
  }

  function smartHeadingCandidate(block) {
    const text = String(block || "").trim();
    if (!text || text.includes("\n")) return false;
    if (text.length > SMART_HEADING_MAX) return false;
    if (smartWidth(text) > SMART_HEADING_WIDTH) return false;
    if (SMART_END_RE.test(text)) return false;
    // 「兄弟们这个板子怎么烧录啊」这种口语句子不算标题
    if (SMART_PARTICLE_RE.test(text)) return false;
    if (SMART_OPENER_RE.test(text)) return false;
    if (text.includes("，")) return false;
    if (/^https?:/i.test(text)) return false;
    if (!/[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]/.test(text)) return false;
    return true;
  }

  function smartFormatText(raw, options) {
    const opts = options || {};
    const source = String(raw || "").replace(/\r\n?/g, "\n").replace(/\t/g, "  ");
    const lines = source.split("\n");
    const blocks = [];
    let paragraph = "";
    let lastWidth = 0;
    let inFence = false;
    let fence = [];

    const flush = () => {
      if (paragraph) {
        blocks.push(paragraph);
        paragraph = "";
        lastWidth = 0;
      }
    };

    for (const rawLine of lines) {
      const line = rawLine.replace(/[ \t]+$/, "");
      const trimmed = line.trim();

      if (/^```/.test(trimmed)) {
        flush();
        fence.push(trimmed);
        inFence = !inFence;
        if (!inFence) {
          blocks.push(fence.join("\n"));
          fence = [];
        }
        continue;
      }
      if (inFence) {
        fence.push(line);
        continue;
      }
      if (!trimmed) {
        flush();
        continue;
      }
      if (SMART_BLOCK_RE.test(trimmed)) {
        flush();
        blocks.push(trimmed);
        continue;
      }
      const bullet = trimmed.match(SMART_BULLET_RE);
      if (bullet) {
        flush();
        blocks.push("- " + trimmed.replace(SMART_BULLET_RE, "").trim());
        continue;
      }
      const order = trimmed.match(SMART_ORDER_RE);
      if (order) {
        flush();
        blocks.push(smartOrderMarker(order[0]) + trimmed.slice(order[0].length).trim());
        continue;
      }
      // 缩进（中文文档常用全角空格）、上一段已经收尾、上一行还不够长（聊天那种一行一句），
      // 都算新段落；只有“长行且没有句末标点”才认为是折行，接回同一段
      const indented = /^[ \u3000]{2,}/.test(line) || /^\u3000/.test(line);
      const wrapped = lastWidth >= SMART_WRAP_WIDTH && !SMART_END_RE.test(paragraph);
      if (paragraph && (indented || !wrapped)) flush();
      paragraph = paragraph ? smartJoinLines(paragraph, trimmed) : trimmed;
      lastWidth = smartWidth(trimmed);
    }
    flush();

    const rendered = blocks
      .map((block, index) => {
        if (/^```/.test(block) || SMART_BLOCK_RE.test(block)) return block;
        if (SMART_BULLET_RE.test(block) || SMART_ORDER_RE.test(block)) return block;
        if (blocks.length < 2) return block;
        if (SMART_INDEX_RE.test(block) && block.length <= SMART_HEADING_MAX + 8) {
          return "### " + block;
        }
        if (!smartHeadingCandidate(block)) return block;
        return (index === 0 && opts.titleForFirst ? "# " : "## ") + block;
      })
      .filter(Boolean);

    // 连续的列表项之间不插空行，避免变成松散列表
    let output = "";
    let previousWasList = false;
    rendered.forEach((block, index) => {
      const isList = SMART_BULLET_RE.test(block) || SMART_ORDER_RE.test(block);
      if (index === 0) {
        output = block;
      } else {
        output += (isList && previousWasList ? "\n" : "\n\n") + block;
      }
      previousWasList = isList;
    });

    return normalizeMarkdown(panguSpacing(output));
  }

  function smartLooksLikeHtml(html) {
    const source = String(html || "");
    if (source.length < 40) return false;
    return /<(p|div|h[1-6]|ul|ol|li|table|blockquote|pre|article|section)\b/i.test(source);
  }

  // 浏览器复制整页时会在注释里标出真正的选区
  function smartClipFragment(doc) {
    const root = doc.body || doc.documentElement;
    if (!root) return null;
    const walker = doc.createTreeWalker(root, NodeFilter.SHOW_COMMENT);
    let start = null;
    let node;
    while ((node = walker.nextNode())) {
      const value = String(node.nodeValue || "");
      if (/^StartFragment/i.test(value)) {
        start = node;
        break;
      }
    }
    if (!start) return null;
    const holder = doc.createElement("div");
    let current = start.nextSibling;
    while (current) {
      if (current.nodeType === Node.COMMENT_NODE && /^EndFragment/i.test(String(current.nodeValue || ""))) {
        break;
      }
      const next = current.nextSibling;
      holder.appendChild(current.cloneNode(true));
      current = next;
    }
    return holder.childNodes.length ? holder : null;
  }

  function smartHtmlToMarkdown(html) {
    const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
    return normalizeMarkdown(htmlChildrenBlock(doc.body || doc.documentElement));
  }

  // 整页复制：交给 Mozilla Readability 剥掉导航 / 广告 / 页脚
  function smartReadableMarkdown(doc) {
    if (typeof window.Readability !== "function") return "";
    let article = null;
    try {
      article = new window.Readability(doc.cloneNode(true), {
        charThreshold: 120,
        keepClasses: false,
      }).parse();
    } catch (err) {
      return "";
    }
    if (!article || !article.content) return "";
    let markdown = smartHtmlToMarkdown(article.content);
    if (!markdown) return "";
    const title = String(article.title || "").trim();
    if (title && !/^#{1,2}\s/.test(markdown)) {
      markdown = `# ${title}\n\n${markdown}`;
    }
    return normalizeMarkdown(markdown);
  }

  function smartHtmlClipboardToMarkdown(html) {
    const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
    const fragment = smartClipFragment(doc);
    if (fragment) return normalizeMarkdown(htmlChildrenBlock(fragment));
    const readable = smartReadableMarkdown(doc);
    if (readable) return readable;
    return normalizeMarkdown(htmlChildrenBlock(doc.body || doc.documentElement));
  }

  function smartReplaceSelection(text) {
    const input = $("editorInput");
    if (!input) return;
    input.focus();
    let inserted = false;
    try {
      inserted = document.execCommand("insertText", false, text);
    } catch (err) {
      inserted = false;
    }
    if (!inserted) {
      input.setRangeText(text, input.selectionStart, input.selectionEnd, "end");
    }
    renderPreview();
    scheduleOutlineUpdate();
  }

  function smartCaretInFence() {
    const input = $("editorInput");
    if (!input) return false;
    const before = input.value.slice(0, input.selectionStart || 0);
    const fences = before.match(/^```/gm);
    return Boolean(fences && fences.length % 2 === 1);
  }

  // 太短的内容（一个词、一条链接）不排版，免得帮倒忙
  function smartWorthFormatting(text) {
    const value = String(text || "");
    return value.length >= 24 || value.includes("\n");
  }

  function smartPasteMarkdown(clipboard) {
    if (!clipboard || smartCaretInFence()) return "";
    const html = String(clipboard.getData("text/html") || "");
    const text = String(clipboard.getData("text/plain") || "");
    const input = $("editorInput");
    if (html && smartLooksLikeHtml(html)) {
      const markdown = smartHtmlClipboardToMarkdown(html);
      if (markdown && smartWorthFormatting(markdown)) return markdown;
    }
    if (!text.trim()) return "";
    const formatted = smartFormatText(text, {
      titleForFirst: Boolean(input && !input.value.trim()),
    });
    if (!formatted || !smartWorthFormatting(formatted)) return "";
    // 纯文本本来就已经是排好的 Markdown，就别插一遍
    if (formatted === normalizeMarkdown(text)) return "";
    return formatted;
  }

  function smartFormatSelection() {
    const input = $("editorInput");
    if (!input) return;
    const selection = input.value.slice(input.selectionStart, input.selectionEnd);
    const wholeNote = !selection.trim();
    const source = wholeNote ? input.value : selection;
    if (!source.trim()) {
      toast("先写点内容再排版");
      return;
    }
    const formatted = smartFormatText(source, { titleForFirst: wholeNote });
    if (!formatted.trim() || formatted === source) {
      toast(wholeNote ? "整篇看起来已经排好了" : "这段看起来已经排好了");
      return;
    }
    if (wholeNote) input.setSelectionRange(0, input.value.length);
    smartReplaceSelection(formatted);
    toast("已排版，Ctrl+Z 可撤销");
  }

  function safeHtmlUrl(value, image) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (raw.startsWith("#")) return raw;
    try {
      const url = new URL(raw, window.location.origin);
      if (image) {
        if (!/^(https?:)?\/\//i.test(raw) && !raw.startsWith("data:image/")) return "";
        return ["http:", "https:", "data:"].includes(url.protocol) ? url.href : "";
      }
      if (!/^(https?:|mailto:|tel:)/i.test(raw)) return "";
      if (["http:", "https:", "mailto:", "tel:"].includes(url.protocol)) {
        return url.href;
      }
    } catch (err) {}
    return "";
  }

  function htmlInlineMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return String(node.nodeValue || "").replace(/\s+/g, " ");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    if (["script", "style", "noscript", "template", "iframe", "object", "embed", "svg", "canvas"].includes(tag)) {
      return "";
    }
    if (tag === "br") return "  \n";
    if (tag === "img") {
      const src = safeHtmlUrl(node.getAttribute("src"), true);
      const alt = String(node.getAttribute("alt") || "").trim();
      return src ? `![${alt}](${src})` : alt;
    }
    if (tag === "a") {
      const href = safeHtmlUrl(node.getAttribute("href"), false);
      const text = htmlChildrenInline(node).trim();
      return href && text ? `[${text}](${href})` : text;
    }
    const content = htmlChildrenInline(node);
    if (tag === "strong" || tag === "b") return content ? `**${content}**` : "";
    if (tag === "em" || tag === "i") return content ? `*${content}*` : "";
    if (tag === "del" || tag === "s" || tag === "strike") return content ? `~~${content}~~` : "";
    if (tag === "code") return content ? `\`${content.replace(/`/g, "\\`")}\`` : "";
    return content;
  }

  function htmlChildrenInline(node) {
    return Array.from(node.childNodes || []).map(htmlInlineMarkdown).join("");
  }

  function htmlListMarkdown(list, depth) {
    const ordered = list.tagName.toLowerCase() === "ol";
    let index = Number(list.getAttribute("start") || 1);
    const lines = [];
    Array.from(list.children || []).forEach((item) => {
      if (item.tagName.toLowerCase() !== "li") return;
      const nested = [];
      const parts = [];
      Array.from(item.childNodes || []).forEach((child) => {
        if (child.nodeType === Node.ELEMENT_NODE && ["ul", "ol"].includes(child.tagName.toLowerCase())) {
          nested.push(htmlListMarkdown(child, depth + 1));
        } else {
          parts.push(htmlBlockMarkdown(child, depth + 1));
        }
      });
      const text = normalizeMarkdown(parts.join(" ")).replace(/\n+/g, " ").trim();
      const indent = "  ".repeat(depth);
      const marker = ordered ? `${index}. ` : "- ";
      lines.push(`${indent}${marker}${text}`);
      if (nested.length) lines.push(...nested);
      index += 1;
    });
    return lines.join("\n");
  }

  function htmlTableMarkdown(table) {
    const rows = Array.from(table.querySelectorAll("tr")).map((row) =>
      Array.from(row.querySelectorAll(":scope > th, :scope > td")).map((cell) =>
        htmlChildrenInline(cell).replace(/\|/g, "\\|").replace(/\s+/g, " ").trim()
      )
    ).filter((row) => row.length);
    if (!rows.length) return "";
    const columns = Math.max(...rows.map((row) => row.length));
    rows.forEach((row) => {
      while (row.length < columns) row.push("");
    });
    const header = rows[0];
    const body = rows.slice(1);
    return [
      `| ${header.join(" | ")} |`,
      `| ${header.map(() => "---").join(" | ")} |`,
      ...body.map((row) => `| ${row.join(" | ")} |`),
    ].join("\n");
  }

  function htmlBlockMarkdown(node, depth = 0) {
    if (node.nodeType === Node.TEXT_NODE) {
      return String(node.nodeValue || "").replace(/\s+/g, " ");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    if (["script", "style", "noscript", "template", "iframe", "object", "embed", "svg", "canvas", "form"].includes(tag)) {
      return "";
    }
    if (/^h[1-6]$/.test(tag)) {
      const level = Number(tag.slice(1));
      const text = htmlChildrenInline(node).trim();
      return text ? `\n\n${"#".repeat(level)} ${text}\n\n` : "";
    }
    if (tag === "p") {
      const text = htmlChildrenInline(node).trim();
      return text ? `\n\n${text}\n\n` : "";
    }
    if (tag === "br") return "  \n";
    if (tag === "hr") return "\n\n---\n\n";
    if (tag === "pre") {
      const code = String(node.textContent || "").replace(/\n$/, "");
      const className = node.querySelector("code")?.className || node.className || "";
      const language = String(className).match(/(?:language-|lang-)([A-Za-z0-9_+-]+)/)?.[1] || "";
      return code ? `\n\n\`\`\`${language}\n${code}\n\`\`\`\n\n` : "";
    }
    if (tag === "blockquote") {
      const text = normalizeMarkdown(htmlChildrenBlock(node, depth));
      return text
        ? `\n\n${text.split("\n").map((line) => `> ${line}`).join("\n")}\n\n`
        : "";
    }
    if (tag === "ul" || tag === "ol") {
      const text = htmlListMarkdown(node, depth);
      return text ? `\n\n${text}\n\n` : "";
    }
    if (tag === "table") {
      const text = htmlTableMarkdown(node);
      return text ? `\n\n${text}\n\n` : "";
    }
    if (tag === "img") {
      const text = htmlInlineMarkdown(node);
      return text ? `\n\n${text}\n\n` : "";
    }
    if (["div", "section", "article", "main", "header", "footer", "nav", "aside", "figure", "figcaption", "details", "summary"].includes(tag)) {
      return htmlChildrenBlock(node, depth);
    }
    return htmlChildrenInline(node);
  }

  function htmlChildrenBlock(node, depth = 0) {
    return Array.from(node.childNodes || []).map((child) => htmlBlockMarkdown(child, depth)).join("");
  }

  function embeddedCorpusFromHtml(html) {
    const parsed = new DOMParser().parseFromString(String(html || ""), "text/html");
    for (const script of parsed.querySelectorAll("script")) {
      const source = String(script.textContent || "");
      const marker = source.indexOf("window.__CORPUS__");
      if (marker < 0) continue;
      const start = source.indexOf("{", marker);
      const end = source.lastIndexOf("}");
      if (start < 0 || end <= start) continue;
      try {
        const corpus = JSON.parse(source.slice(start, end + 1));
        if (corpus && corpus.parts && typeof corpus.parts === "object") {
          return corpus;
        }
      } catch (err) {}
    }
    return null;
  }

  function importHtmlDocument(html, fallbackName) {
    const documentNode = new DOMParser().parseFromString(String(html || ""), "text/html");
    const title =
      String(documentNode.querySelector("title")?.textContent || "").trim() ||
      String(documentNode.querySelector("h1")?.textContent || "").trim() ||
      String(fallbackName || "").replace(/\.[^.]+$/, "") ||
      "HTML 导入笔记";
    const corpus = embeddedCorpusFromHtml(html);
    if (corpus) {
      const sections = [];
      if (typeof corpus.readme === "string" && corpus.readme.trim()) {
        const readmeDocument = new DOMParser().parseFromString(corpus.readme, "text/html");
        const readme = normalizeMarkdown(htmlChildrenBlock(readmeDocument.body || readmeDocument.documentElement));
        if (readme) sections.push(`# 目录与说明\n\n${readme}`);
      }
      Object.entries(corpus.parts)
        .sort(([left], [right]) => left.localeCompare(right, "zh-Hans-CN", { numeric: true }))
        .forEach(([name, content]) => {
          const markdown = normalizeMarkdown(content);
          if (markdown) sections.push(`<!-- ${name} -->\n\n${markdown}`);
        });
      return {
        title: title.slice(0, 120),
        content: normalizeMarkdown(sections.join("\n\n---\n\n")),
      };
    }
    const body = documentNode.body || documentNode.documentElement;
    return {
      title: title.slice(0, 120),
      content: normalizeMarkdown(htmlChildrenBlock(body)),
    };
  }

  function renderMarkdown(text) {
    const source = String(text || "");
    if (!source.trim()) {
      return '<p class="nt-markdown-empty">还没有内容，点右上角「编辑」开始写。</p>';
    }
    if (!window.marked || !window.DOMPurify) {
      return `<p class="nt-markdown-empty">${escapeHtml(source)}</p>`;
    }
    const html = marked.parse(source);
    return DOMPurify.sanitize(html, { ADD_ATTR: ["target", "rel"] });
  }

  function decoratePreview(container) {
    container.querySelectorAll("a[href]").forEach((link) => {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
  }

  function renderPreview() {
    const pane = $("previewPane");
    pane.innerHTML = renderMarkdown($("editorInput").value);
    decoratePreview(pane);
    buildOutline();
  }

  /* ---------- 大纲 / 面包屑 ---------- */

  function outlineItems() {
    return Array.from($("previewPane").querySelectorAll("h1, h2, h3")).map((el) => ({
      el,
      level: Number(el.tagName.slice(1)),
      text: (el.textContent || "").trim(),
    }));
  }

  function chainFor(index) {
    const items = state.outline;
    if (index < 0 || !items[index]) return [];
    const chain = [items[index]];
    let level = items[index].level;
    for (let i = index - 1; i >= 0 && level > 1; i -= 1) {
      if (items[i].level < level) {
        chain.unshift(items[i]);
        level = items[i].level;
      }
    }
    return chain;
  }

  function setOutlineOpen(open) {
    state.outlineOpen = Boolean(open) && state.outline.length > 0;
    $("outlinePanel").hidden = !state.outlineOpen;
    $("outlineToggle").setAttribute("aria-expanded", state.outlineOpen ? "true" : "false");
  }

  function buildOutline() {
    state.outline = outlineItems();
    const bar = $("outlineBar");
    const path = $("outlinePath");
    const panel = $("outlinePanel");
    path.innerHTML = "";
    panel.innerHTML = "";
    if (!state.outline.length) {
      bar.hidden = true;
      state.outlineActive = -1;
      setOutlineOpen(false);
      return;
    }
    bar.hidden = false;
    $("outlineCount").textContent = `${state.outline.length} 节`;
    state.outline.forEach((item, index) => {
      const entry = document.createElement("button");
      entry.type = "button";
      entry.className = `nt-outline-item nt-lvl-${item.level}`;
      entry.dataset.index = String(index);
      entry.style.paddingLeft = `${8 + (item.level - 1) * 14}px`;
      const level = document.createElement("span");
      level.className = "nt-ol-level";
      level.textContent = `H${item.level}`;
      const text = document.createElement("span");
      text.className = "nt-ol-text";
      text.textContent = item.text || "（空标题）";
      entry.append(level, text);
      panel.appendChild(entry);
    });
    if (state.outlineActive >= state.outline.length) {
      state.outlineActive = state.outline.length - 1;
    }
    paintOutline();
    updateActiveHeading();
  }

  function paintOutline() {
    const path = $("outlinePath");
    const index = state.outlineActive;
    const chain = chainFor(index);
    path.innerHTML = "";
    if (!chain.length) {
      const hint = document.createElement("span");
      hint.className = "nt-outline-seg";
      hint.textContent = state.baseline.title || "开头";
      path.appendChild(hint);
    } else {
      chain.forEach((item, position) => {
        const isLast = position === chain.length - 1;
        if (position) {
          const sep = document.createElement("span");
          sep.className = "nt-outline-sep";
          sep.textContent = "›";
          path.appendChild(sep);
        }
        const seg = document.createElement("button");
        seg.type = "button";
        seg.className = `nt-outline-seg nt-lvl-${item.level}${isLast ? " active" : ""}`;
        seg.textContent = item.text || "（空标题）";
        seg.title = item.text || "";
        seg.addEventListener("click", () => scrollToHeading(state.outline.indexOf(item)));
        path.appendChild(seg);
      });
      const active = path.querySelector(".nt-outline-seg.active");
      if (active) path.scrollLeft = Math.max(0, active.offsetLeft - 72);
    }
    $("outlinePanel")
      .querySelectorAll(".nt-outline-item")
      .forEach((el) => el.classList.toggle("active", Number(el.dataset.index) === index));
  }

  function updateActiveHeading() {
    state.outlineFrame = null;
    const items = state.outline;
    if (!items.length) return;
    const pane = $("paneRead");
    if (!pane || !pane.clientHeight || pane.offsetParent === null) return;
    const paneTop = pane.getBoundingClientRect().top;
    let index = -1;
    items.forEach((item, i) => {
      if (item.el.getBoundingClientRect().top - paneTop <= 14) index = i;
    });
    if (pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 4) {
      index = items.length - 1;
    }
    if (index !== state.outlineActive) {
      state.outlineActive = index;
      paintOutline();
    }
  }

  function scheduleOutlineUpdate() {
    if (state.outlineFrame) return;
    state.outlineFrame = requestAnimationFrame(updateActiveHeading);
  }

  function scrollToHeading(index) {
    const item = state.outline[index];
    const pane = $("paneRead");
    if (!item || !pane) return;
    const paneRect = pane.getBoundingClientRect();
    const target = pane.scrollTop + (item.el.getBoundingClientRect().top - paneRect.top) - 12;
    state.suppressAutoHide = true;
    setHeadHidden(false);
    clearTimeout(state.autoHideTimer);
    state.autoHideTimer = setTimeout(() => {
      state.suppressAutoHide = false;
    }, 700);
    pane.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    state.outlineActive = index;
    paintOutline();
    setOutlineOpen(false);
  }

  /* ---------- 向下滚动时收起标题区 ---------- */

  const HEAD_HIDE_OFFSET = 48;

  function syncHeadHeight() {
    const head = document.querySelector(".nt-doc-head");
    if (!head) return;
    document.documentElement.style.setProperty("--nt-head-h", `${head.offsetHeight}px`);
  }

  function setHeadHidden(hidden) {
    $("docPane").classList.toggle("nt-head-hidden", Boolean(hidden));
  }

  function handlePaneScroll() {
    const pane = $("paneRead");
    if (!pane) return;
    const top = pane.scrollTop;
    const delta = top - state.lastScrollTop;
    state.lastScrollTop = top;
    if (state.mode !== "read") {
      setHeadHidden(false);
      return;
    }
    if (state.suppressAutoHide) return;
    if (top <= 4) {
      setHeadHidden(false);
      return;
    }
    if (delta > 2 && top > HEAD_HIDE_OFFSET) {
      setHeadHidden(true);
    } else if (delta < -2) {
      setHeadHidden(false);
    }
  }

  /* ---------- list ---------- */

  function visibleNotes() {
    const keyword = state.search.trim().toLowerCase();
    let rows = state.notes.slice();
    if (state.tag) {
      rows = rows.filter((note) => noteTags(note).includes(state.tag));
    }
    if (keyword) {
      rows = rows.filter((note) => {
        const haystack = [note.title, note.content, note.tags]
          .map((value) => String(value || "").toLowerCase())
          .join("\n");
        return haystack.includes(keyword);
      });
    }
    rows.sort((a, b) => {
      if (state.sort === "title") {
        return String(a.title).localeCompare(String(b.title), "zh-Hans-CN");
      }
      const field = state.sort === "created" ? "created_at" : "updated_at";
      return String(b[field] || "").localeCompare(String(a[field] || ""));
    });
    return rows;
  }

  function renderList() {
    const list = $("noteList");
    const rows = visibleNotes();
    list.innerHTML = "";
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "nt-empty-list";
      empty.textContent = state.notes.length ? "没有匹配的笔记" : "还没有笔记，点右上角新建一篇。";
      list.appendChild(empty);
    }
    rows.forEach((note) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "nt-card" + (note.id === state.activeId ? " active" : "");
      card.dataset.id = note.id;
      const tags = noteTags(note)
        .slice(0, 2)
        .map((tag) => `<span class="nt-card-tag">${escapeHtml(tag)}</span>`)
        .join("");
      const images = note.image_count
        ? `<span>${note.image_count} 张图</span>`
        : "";
      card.innerHTML = `
        <div class="nt-card-title">${escapeHtml(note.title || "未命名笔记")}</div>
        <div class="nt-card-excerpt">${escapeHtml(excerptOf(note) || "（空笔记）")}</div>
        <div class="nt-card-meta">
          <span class="nt-card-tags">${tags}</span>
          <span>${escapeHtml(formatTime(note.updated_at))}</span>
          ${images}
        </div>`;
      card.addEventListener("click", () => openNote(note.id));
      list.appendChild(card);
    });
    $("noteCount").textContent = `${state.notes.length} 篇`;
    $("listStatus").textContent = state.notes.length
      ? `显示 ${rows.length} / ${state.notes.length} 篇`
      : "共 0 篇";
  }

  function updateTagToggle() {
    const wrap = $("tagFilter");
    const toggle = $("tagToggle");
    if (!wrap || !toggle) return;
    const expanded = state.tagsExpanded;
    wrap.classList.remove("is-expanded");
    const canToggle = wrap.scrollHeight > wrap.clientHeight + 2;
    wrap.classList.toggle("is-expanded", expanded && canToggle);
    toggle.hidden = !canToggle;
    toggle.textContent = expanded ? "收起标签" : "展开标签";
  }

  function renderTagFilter() {
    const wrap = $("tagFilter");
    const counts = new Map();
    state.notes.forEach((note) => {
      noteTags(note).forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1));
    });
    const tags = Array.from(counts.keys()).sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
    wrap.innerHTML = "";
    wrap.classList.toggle("is-expanded", state.tagsExpanded);
    if (!tags.length) {
      $("tagToggle").hidden = true;
      return;
    }
    const all = document.createElement("button");
    all.type = "button";
    all.className = "nt-tag-chip" + (state.tag ? "" : " active");
    all.textContent = "全部";
    all.addEventListener("click", () => {
      state.tag = "";
      renderTagFilter();
      renderList();
    });
    wrap.appendChild(all);
    tags.forEach((tag) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "nt-tag-chip" + (state.tag === tag ? " active" : "");
      chip.textContent = `${tag} ${counts.get(tag)}`;
      chip.addEventListener("click", () => {
        state.tag = state.tag === tag ? "" : tag;
        renderTagFilter();
        renderList();
      });
      wrap.appendChild(chip);
    });
    updateTagToggle();
  }

  async function loadNotes(options = {}) {
    const notes = await api("/api/notes");
    state.notes = Array.isArray(notes) ? notes : [];
    if (state.activeId && !state.notes.some((note) => note.id === state.activeId)) {
      closeNote();
    }
    renderTagFilter();
    renderList();
    if (options.reopen) {
      openNote(options.reopen, { mode: options.mode || "read", force: true });
    }
  }

  /* ---------- document ---------- */

  function currentValues() {
    return {
      title: $("titleInput").value.trim(),
      content: $("editorInput").value,
      tags: $("tagsInput").value.trim(),
    };
  }

  function isDirty() {
    if (state.mode !== "edit") return false;
    const now = currentValues();
    return (
      now.title !== state.baseline.title ||
      now.content !== state.baseline.content ||
      now.tags !== state.baseline.tags
    );
  }

  function setMode(mode) {
    state.mode = mode;
    const doc = $("docPane");
    doc.dataset.mode = mode;
    const editing = mode === "edit";
    doc.classList.toggle("nt-editing", editing);
    document.body.classList.toggle("nt-detail-open", true);
    $("titleText").hidden = editing;
    $("titleInput").hidden = !editing;
    $("tagsInput").hidden = !editing;
    $("readActions").hidden = editing;
    $("editActions").hidden = !editing;
    $("toolbar").hidden = !editing;
    if (editing) {
      setHeadHidden(false);
      renderPreview();
      $("editorInput").focus();
    }
    state.lastScrollTop = $("paneRead").scrollTop;
    syncHeadHeight();
    scheduleOutlineUpdate();
  }

  function renderDocMeta(note) {
    const meta = $("docMeta");
    if (!note) {
      meta.innerHTML = `<span>${state.mode === "edit" ? "未保存的新笔记" : ""}</span>`;
      return;
    }
    const tags = noteTags(note)
      .map((tag) => `<span class="nt-meta-tag">${escapeHtml(tag)}</span>`)
      .join("");
    meta.innerHTML = `
      ${tags}
      <span>创建 ${escapeHtml(String(note.created_at || "").slice(0, 10))}</span>
      <span>更新 ${escapeHtml(formatTime(note.updated_at))}</span>
      ${note.image_count ? `<span>${note.image_count} 张图片</span>` : ""}`;
  }

  function activeNote() {
    return state.notes.find((note) => note.id === state.activeId) || null;
  }

  function openNote(id, options = {}) {
    if (!options.force && isDirty() && id !== state.activeId) {
      askConfirm("放弃未保存的修改？", "当前笔记有改动还没保存，切换后会丢失。", "放弃修改", () => {
        closeConfirm();
        openNote(id, { force: true });
      });
      return;
    }
    const note = state.notes.find((item) => item.id === id);
    if (!note) return;
    const sameNote = state.activeId === id;
    state.activeId = id;
    state.baseline = {
      title: String(note.title || ""),
      content: String(note.content || ""),
      tags: String(note.tags || ""),
    };
    $("titleInput").value = state.baseline.title;
    $("titleText").textContent = state.baseline.title || "未命名笔记";
    $("tagsInput").value = state.baseline.tags;
    $("editorInput").value = state.baseline.content;
    $("welcomePane").hidden = true;
    $("docPane").hidden = false;
    if (!sameNote) {
      state.outlineActive = -1;
      state.lastScrollTop = 0;
      setHeadHidden(false);
      $("paneRead").scrollTop = 0;
      $("editorInput").scrollTop = 0;
    }
    renderPreview();
    setMode(options.mode || "read");
    syncHeadHeight();
    renderDocMeta(note);
    document.body.classList.add("nt-detail-open");
    renderList();
  }

  function closeNote() {
    state.activeId = null;
    state.mode = "read";
    state.baseline = { title: "", content: "", tags: "" };
    state.outline = [];
    state.outlineActive = -1;
    $("docPane").dataset.mode = "read";
    $("titleInput").value = "";
    $("tagsInput").value = "";
    $("titleText").textContent = "";
    $("editorInput").value = "";
    $("previewPane").innerHTML = "";
    $("docPane").hidden = true;
    $("welcomePane").hidden = false;
    document.body.classList.remove("nt-detail-open");
    renderList();
  }

  function newNote() {
    if (isDirty()) {
      askConfirm("放弃未保存的修改？", "当前笔记有改动还没保存，新建后会丢失。", "放弃修改", () => {
        closeConfirm();
        openDraft();
      });
      return;
    }
    openDraft();
  }

  function openDraft() {
    state.activeId = null;
    state.baseline = { title: "", content: "", tags: "" };
    $("titleInput").value = "";
    $("titleText").textContent = "";
    $("tagsInput").value = "";
    $("editorInput").value = "";
    $("welcomePane").hidden = true;
    $("docPane").hidden = false;
    setMode("edit");
    renderDocMeta(null);
    renderList();
    toast("新笔记还没保存");
  }

  async function saveNote() {
    const values = currentValues();
    if (!values.title && !values.content.trim()) {
      toast("写点内容再保存吧");
      return;
    }
    const saveBtn = $("saveBtn");
    saveBtn.disabled = true;
    try {
      const path = state.activeId ? `/api/notes/${state.activeId}` : "/api/notes";
      const method = state.activeId ? "PATCH" : "POST";
      const result = await api(path, { method, body: JSON.stringify(values) });
      const noteId = result && result.id ? result.id : state.activeId;
      state.activeId = null;
      state.baseline = { title: "", content: "", tags: "" };
      await loadNotes();
      if (noteId) {
        openNote(noteId, { mode: "read", force: true });
      }
      toast("已保存");
    } catch (err) {
      toast(err.message || "保存失败");
    } finally {
      saveBtn.disabled = false;
    }
  }

  function deleteNote() {
    const note = activeNote();
    if (!note) return;
    const images = note.image_count ? `这篇笔记的 ${note.image_count} 张图片也会一起删除。` : "";
    askConfirm("删除这篇笔记？", `「${note.title}」将被删除，${images}此操作无法撤销。`, "删除", async () => {
      closeConfirm();
      try {
        await api(`/api/notes/${note.id}`, { method: "DELETE" });
        state.activeId = null;
        state.baseline = { title: "", content: "", tags: "" };
        closeNote();
        await loadNotes();
        toast("已删除");
      } catch (err) {
        toast(err.message || "删除失败");
      }
    });
  }

  function exportNote() {
    const note = activeNote();
    if (!note) return;
    window.location.href = `/api/notes/${encodeURIComponent(note.id)}/export.html`;
  }

  /* ---------- editing helpers ---------- */

  function insertText(before, after = "", placeholder = "") {
    const input = $("editorInput");
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const selected = input.value.slice(start, end) || placeholder;
    const text = before + selected + after;
    input.setRangeText(text, start, end, "end");
    if (!selected && !placeholder) return;
    input.focus();
    const cursor = start + before.length + selected.length;
    input.setSelectionRange(start + before.length, cursor);
    renderPreview();
  }

  function prefixLines(prefix, numbered) {
    const input = $("editorInput");
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const lineStart = input.value.lastIndexOf("\n", start - 1) + 1;
    let lineEnd = input.value.indexOf("\n", end);
    if (lineEnd === -1) lineEnd = input.value.length;
    const lines = input.value.slice(lineStart, lineEnd).split("\n");
    const matches = (line) => (numbered ? /^\d+\.\s/.test(line) : line.startsWith(prefix));
    const already = lines.every(matches);
    const next = lines
      .map((line, index) => {
        if (already) return numbered ? line.replace(/^\d+\.\s/, "") : line.slice(prefix.length);
        return (numbered ? `${index + 1}. ` : prefix) + line;
      })
      .join("\n");
    input.setRangeText(next, lineStart, lineEnd, "end");
    input.focus();
    renderPreview();
  }

  function applyToolbar(action) {
    switch (action) {
      case "bold":
        insertText("**", "**", "加粗文字");
        break;
      case "italic":
        insertText("*", "*", "斜体文字");
        break;
      case "heading":
        prefixLines("## ", false);
        break;
      case "ul":
        prefixLines("- ", false);
        break;
      case "ol":
        prefixLines("- ", true);
        break;
      case "quote":
        prefixLines("> ", false);
        break;
      case "code":
        insertText("\n```\n", "\n```\n", "代码");
        break;
      case "link":
        insertText("[", "](https://)", "链接文字");
        break;
      case "image":
        $("imageInput").click();
        break;
      case "smart":
        smartFormatSelection();
        break;
      default:
        break;
    }
  }

  /* ---------- image upload ---------- */

  function readAsBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        resolve(result.slice(result.indexOf(",") + 1));
      };
      reader.onerror = () => reject(new Error("读取文件失败"));
      reader.readAsDataURL(blob);
    });
  }

  function shrinkImage(file) {
    return new Promise((resolve) => {
      if (!file.type.startsWith("image/") || file.type === "image/gif") {
        resolve({ blob: file, name: file.name || "image.png" });
        return;
      }
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => {
        const longest = Math.max(image.width, image.height);
        const scale = Math.min(1, MAX_UPLOAD_SIDE / longest);
        if (scale === 1 && file.size <= 2.5 * 1024 * 1024) {
          URL.revokeObjectURL(url);
          resolve({ blob: file, name: file.name || "image.png" });
          return;
        }
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(image.width * scale));
        canvas.height = Math.max(1, Math.round(image.height * scale));
        canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
        const keepPng = file.type === "image/png" && scale === 1;
        canvas.toBlob(
          (blob) => {
            URL.revokeObjectURL(url);
            if (!blob) {
              resolve({ blob: file, name: file.name || "image.png" });
              return;
            }
            const extension = blob.type === "image/webp" ? "webp" : "jpg";
            const base = (file.name || "image").replace(/\.[^.]+$/, "");
            resolve({ blob, name: `${base}.${extension}` });
          },
          keepPng ? "image/png" : "image/webp",
          0.92
        );
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        resolve({ blob: file, name: file.name || "image.png" });
      };
      image.src = url;
    });
  }

  function insertAtCursor(text) {
    const input = $("editorInput");
    const start = input.selectionStart;
    const end = input.selectionEnd;
    input.setRangeText(text, start, end, "end");
    input.focus();
    renderPreview();
  }

  async function uploadImages(files) {
    let images = Array.from(files || []).filter((file) => file.type.startsWith("image/"));
    if (!images.length) return;
    if (images.length > noteLimits.imageCount) {
      toast("一次最多上传 " + noteLimits.imageCount + " 张图片");
      images = images.slice(0, noteLimits.imageCount);
    }
    state.uploading += images.length;
    $("toolbarHint").textContent = "正在上传图片…";
    for (const file of images) {
      try {
        const prepared = await shrinkImage(file);
        if (prepared.blob.size > noteLimits.imageBytes) {
          throw new Error(
            "图片不能超过 " + noteLimitLabel(noteLimits.imageBytes) + "：" + file.name
          );
        }
        const dataBase64 = await readAsBase64(prepared.blob);
        const result = await api("/api/notes/images", {
          method: "POST",
          body: JSON.stringify({ file_name: prepared.name, data_base64: dataBase64 }),
        });
        const alt = String(prepared.name || "image").replace(/\.[^.]+$/, "");
        insertAtCursor(`\n\n![${alt}](${result.url})\n\n`);
      } catch (err) {
        toast(err.message || "图片上传失败");
      } finally {
        state.uploading -= 1;
      }
    }
    if (state.uploading <= 0) {
      state.uploading = 0;
      $("toolbarHint").textContent = "";
    } else {
      $("toolbarHint").textContent = `正在上传 ${state.uploading} 张…`;
    }
  }

  function bindShareButton() {
    const button = $("shareBtn");
    if (!button) return;
    button.addEventListener("click", function () {
      const note = state.notes.find(
        (item) => Number(item.id) === Number(state.activeId)
      );
      if (!note) return;
      if (window.ErrorShare) {
        window.ErrorShare.open("note", note.id, note.title || "笔记");
      }
    });
    fetch("/api/auth/status", { cache: "no-store" })
      .then((response) => response.json())
      .then((status) => {
        button.hidden = !(status.admin || status.owner);
      })
      .catch(() => {
        button.hidden = true;
      });
  }

  function importDateText() {
    const date = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  function importFileStem(fileName) {
    return String(fileName || "")
      .replace(/\.[^.]+$/, "")
      .replace(/[\r\n<>]/g, " ")
      .trim()
      .slice(0, 120) || "导入文档";
  }

  function importFileLabel(fileName) {
    return String(fileName || "document")
      .replace(/[\r\n<>]/g, " ")
      .trim()
      .slice(0, 180) || "document";
  }

  function documentImportKind(file) {
    const extension = String(file.name || "").toLowerCase().match(/\.[^.]+$/)?.[0] || "";
    if ([".html", ".htm"].includes(extension)) return "html";
    if ([".md", ".markdown"].includes(extension)) return "markdown";
    if (extension === ".txt" || file.type === "text/plain") return "text";
    if ([".doc", ".docx", ".pdf"].includes(extension)) return "binary";
    return "";
  }

  async function decodeTextDocument(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const encodings = [];
    if (bytes[0] === 0xff && bytes[1] === 0xfe) encodings.push("utf-16le");
    if (bytes[0] === 0xfe && bytes[1] === 0xff) encodings.push("utf-16be");
    encodings.push("utf-8", "gb18030", "utf-16le");
    for (const encoding of encodings) {
      try {
        const text = new TextDecoder(encoding, { fatal: true }).decode(bytes);
        return text.replace(/^\uFEFF/, "");
      } catch (err) {}
    }
    return new TextDecoder("utf-8").decode(bytes).replace(/^\uFEFF/, "");
  }

  function prepareTextDocument(text, file, kind) {
    let content = normalizeMarkdown(text);
    if (!content) throw new Error("文件中没有可导入的正文内容");
    let title = importFileStem(file.name);
    if (kind === "markdown") {
      const heading = content.match(/^#\s+(.+?)\s*$/m);
      if (heading) {
        title = heading[1].trim() || title;
        content = normalizeMarkdown(
          content.slice(0, heading.index) + content.slice(heading.index + heading[0].length)
        );
      }
    }
    content = `> 导入自 ${importFileLabel(file.name)} · ${importDateText()}\n\n${content}`;
    if (content.length > MAX_NOTE_CONTENT_CHARS) {
      throw new Error("转换后的正文太长了，建议拆分文档后再导入");
    }
    return { title: title.slice(0, 120), content };
  }

  // Word / PDF 导入：按钮内显示上传进度，服务端解析阶段用流动条纹表示。
  let importBusy = { active: false, canceled: false, abort: null, fill: null };

  function documentImportFill() {
    if (!importBusy.fill) {
      importBusy.fill = ErrorProgress.button($("documentImportBtn"), {
        onCancel: () => {
          importBusy.canceled = true;
          if (importBusy.abort) importBusy.abort();
        },
      });
    }
    return importBusy.fill;
  }

  async function importDocumentFile(file) {
    if (!file) return;
    if (isDirty()) {
      askConfirm("放弃未保存的修改？", "当前笔记有改动还没保存，导入文档后会切换到新笔记。", "继续导入", () => {
        closeConfirm();
        importDocumentFile(file);
      });
      return;
    }
    const kind = documentImportKind(file);
    if (!kind) {
      toast("只支持 TXT、Markdown、HTML、Word 和 PDF 文档");
      return;
    }
    if (file.size > noteLimits.importBytes) {
      toast("导入文档不能超过 " + noteLimitLabel(noteLimits.importBytes));
      return;
    }
    state.uploading += 1;
    const extension = String(file.name || "").toLowerCase().match(/\.[^.]+$/)?.[0] || "文档";
    $("toolbarHint").textContent = `正在导入 ${extension.replace(".", "").toUpperCase()}…`;
    let usedProgress = false;
    try {
      if (kind === "binary") {
        const formatLabel = extension.replace(".", "").toUpperCase() || "文档";
        const fill = documentImportFill();
        usedProgress = true;
        importBusy.active = true;
        importBusy.canceled = false;
        importBusy.abort = null;
        fill.busy("读取文档…");
        const dataBase64 = await readAsBase64(file);
        if (importBusy.canceled) throw new Error("已取消导入");
        const task = ErrorProgress.upload("/api/notes/import", {
          payload: { file_name: file.name || "document", data_base64: dataBase64 },
          onProgress: (ratio) => {
            fill.set(ratio, `上传 ${ErrorProgress.percentText(ratio)}`);
            $("toolbarHint").textContent = `上传 ${formatLabel} ${ErrorProgress.percentText(ratio)}`;
          },
          onUploaded: () => {
            fill.busy("解析文档中…");
            $("toolbarHint").textContent = `解析 ${formatLabel} 中…`;
          },
        });
        importBusy.abort = task.abort;
        const result = await task.promise;
        await loadNotes();
        if (result && result.id) {
          openNote(result.id, { mode: "read", force: true });
        }
        toast(`${result && result.format === "pdf" ? "PDF" : "Word"} 文档已导入为笔记`);
        return;
      }
      const text = await decodeTextDocument(file);
      const imported =
        kind === "html"
          ? importHtmlDocument(text, file.name)
          : prepareTextDocument(text, file, kind);
      if (!imported.content) {
        throw new Error("文件中没有可导入的正文内容");
      }
      if (imported.content.length > MAX_NOTE_CONTENT_CHARS) {
        throw new Error("转换后的正文太长了，建议拆分文档后再导入");
      }
      const tags = kind === "html" ? "HTML导入" : kind === "markdown" ? "Markdown导入" : "TXT导入";
      const result = await api("/api/notes", {
        method: "POST",
        body: JSON.stringify({
          title: imported.title,
          content: imported.content,
          tags,
        }),
      });
      await loadNotes();
      if (result && result.id) {
        openNote(result.id, { mode: "read", force: true });
      }
      toast(`${kind === "html" ? "HTML" : kind === "markdown" ? "Markdown" : "TXT"} 已导入为笔记`);
    } catch (err) {
      if (importBusy.canceled || ErrorProgress.isAborted(err)) {
        toast("已取消导入，文件还在，可以直接重试");
        return;
      }
      toast(err.message || "文档导入失败");
    } finally {
      state.uploading -= 1;
      if (state.uploading <= 0) {
        state.uploading = 0;
        $("toolbarHint").textContent = "";
      }
      if (usedProgress) {
        importBusy.active = false;
        importBusy.abort = null;
        importBusy.fill.reset();
      }
    }
  }

  /* ---------- events ---------- */

  function bindEvents() {
    $("newNoteBtn").addEventListener("click", newNote);
    $("documentImportBtn").addEventListener("click", () => $("documentInput").click());
    $("exportBtn").addEventListener("click", exportNote);
    $("editBtn").addEventListener("click", () => setMode("edit"));
    $("saveBtn").addEventListener("click", saveNote);
    $("deleteBtn").addEventListener("click", deleteNote);
    $("backBtn").addEventListener("click", () => {
      if (isDirty()) {
        askConfirm("放弃未保存的修改？", "当前笔记有改动还没保存，返回后会丢失。", "放弃修改", () => {
          closeConfirm();
          closeNote();
        });
        return;
      }
      closeNote();
    });
    $("cancelBtn").addEventListener("click", () => {
      if (state.activeId) {
        openNote(state.activeId, { mode: "read", force: true });
      } else {
        closeNote();
      }
    });

    $("searchInput").addEventListener("input", (event) => {
      state.search = event.target.value;
      renderList();
    });

    $("sortBar").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-sort]");
      if (!button) return;
      state.sort = button.dataset.sort;
      $("sortBar").querySelectorAll("button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderList();
    });

    $("tagToggle").addEventListener("click", () => {
      state.tagsExpanded = !state.tagsExpanded;
      updateTagToggle();
    });

    $("toolbar").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (button) applyToolbar(button.dataset.action);
    });

    $("outlineToggle").addEventListener("click", () => setOutlineOpen(!state.outlineOpen));

    $("outlinePanel").addEventListener("click", (event) => {
      const item = event.target.closest(".nt-outline-item");
      if (item) scrollToHeading(Number(item.dataset.index));
    });

    $("paneRead").addEventListener("scroll", scheduleOutlineUpdate, { passive: true });
    $("paneRead").addEventListener("scroll", handlePaneScroll, { passive: true });

    document.addEventListener("click", (event) => {
      if (!state.outlineOpen) return;
      if (!event.target.closest("#outlineBar")) setOutlineOpen(false);
    });

    window.addEventListener("resize", () => {
      updateTagToggle();
      syncHeadHeight();
      scheduleOutlineUpdate();
    });

    $("editorInput").addEventListener("input", renderPreview);

    $("editorInput").addEventListener("paste", (event) => {
      const files = Array.from(event.clipboardData?.files || []);
      if (files.some((file) => file.type.startsWith("image/"))) {
        event.preventDefault();
        uploadImages(files);
        return;
      }
      const smart = smartPasteMarkdown(event.clipboardData);
      if (!smart) return;
      event.preventDefault();
      smartReplaceSelection(smart);
      toast("已自动排版，Ctrl+Z 可撤销");
    });

    $("editorInput").addEventListener("dragover", (event) => {
      if (Array.from(event.dataTransfer?.items || []).some((item) => item.kind === "file")) {
        event.preventDefault();
      }
    });

    $("editorInput").addEventListener("drop", (event) => {
      const files = Array.from(event.dataTransfer?.files || []);
      if (!files.length) return;
      event.preventDefault();
      if (files.length === 1 && documentImportKind(files[0])) {
        importDocumentFile(files[0]);
        return;
      }
      uploadImages(files);
    });

    $("imageInput").addEventListener("change", (event) => {
      uploadImages(event.target.files);
      event.target.value = "";
    });

    $("documentInput").addEventListener("change", (event) => {
      importDocumentFile(event.target.files[0]);
      event.target.value = "";
    });

    $("previewPane").addEventListener("click", (event) => {
      const image = event.target.closest("img");
      if (!image) return;
      $("lightboxImage").src = image.src;
      $("lightbox").hidden = false;
    });

    $("lightbox").addEventListener("click", () => {
      $("lightbox").hidden = true;
      $("lightboxImage").src = "";
    });

    $("confirmCancel").addEventListener("click", closeConfirm);
    $("confirmOk").addEventListener("click", () => {
      const action = confirmAction;
      if (action) action();
      else closeConfirm();
    });
    $("confirmOverlay").addEventListener("click", (event) => {
      if (event.target === $("confirmOverlay")) closeConfirm();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeConfirm();
        setOutlineOpen(false);
        $("lightbox").hidden = true;
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        if (state.mode === "edit") {
          event.preventDefault();
          saveNote();
        }
        return;
      }
      const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
      if (!typing && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        $("searchInput").focus();
      }
    });

    window.addEventListener("beforeunload", (event) => {
      if (state.mode === "edit" && isDirty()) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }

  /* ---------- boot ---------- */

  async function boot() {
    applyTheme(themePreference, false);
    if (window.lucide) lucide.createIcons();
    bindEvents();
    bindShareButton();
    if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);
    if (window.ResizeObserver) {
      const head = document.querySelector(".nt-doc-head");
      if (head) new ResizeObserver(syncHeadHeight).observe(head);
    }
    syncHeadHeight();
    try {
      await loadNotes();
    } catch (err) {
      $("listStatus").textContent = "加载失败";
      toast(err.message || "加载笔记失败");
    }
  }

  boot();
})();
