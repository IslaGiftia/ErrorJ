(function () {
  const state = {
    notes: [],
    activeId: null,
    mode: "read",
    search: "",
    sort: "updated",
    tag: "",
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

  function renderTagFilter() {
    const wrap = $("tagFilter");
    const counts = new Map();
    state.notes.forEach((note) => {
      noteTags(note).forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1));
    });
    const tags = Array.from(counts.keys()).sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
    wrap.innerHTML = "";
    if (!tags.length) return;
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
      reader.onerror = () => reject(new Error("读取图片失败"));
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
    const images = Array.from(files || []).filter((file) => file.type.startsWith("image/"));
    if (!images.length) return;
    state.uploading += images.length;
    $("toolbarHint").textContent = "正在上传图片…";
    for (const file of images) {
      try {
        const prepared = await shrinkImage(file);
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

  async function importHtmlFile(file) {
    if (!file) return;
    if (isDirty()) {
      askConfirm("放弃未保存的修改？", "当前笔记有改动还没保存，导入 HTML 后会切换到新笔记。", "继续导入", () => {
        closeConfirm();
        importHtmlFile(file);
      });
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast("HTML 文件不能超过 10MB");
      return;
    }
    state.uploading += 1;
    $("toolbarHint").textContent = "正在导入 HTML…";
    try {
      const html = await file.text();
      const imported = importHtmlDocument(html, file.name);
      if (!imported.content) {
        throw new Error("HTML 中没有可导入的正文内容");
      }
      const result = await api("/api/notes", {
        method: "POST",
        body: JSON.stringify({
          title: imported.title,
          content: imported.content,
          tags: "HTML导入",
        }),
      });
      await loadNotes();
      if (result && result.id) {
        openNote(result.id, { mode: "read", force: true });
      }
      toast("HTML 已导入为笔记");
    } catch (err) {
      toast(err.message || "HTML 导入失败");
    } finally {
      state.uploading -= 1;
      if (state.uploading <= 0) {
        state.uploading = 0;
        $("toolbarHint").textContent = "";
      }
    }
  }

  /* ---------- events ---------- */

  function bindEvents() {
    $("newNoteBtn").addEventListener("click", newNote);
    $("htmlImportBtn").addEventListener("click", () => $("htmlInput").click());
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
      syncHeadHeight();
      scheduleOutlineUpdate();
    });

    $("editorInput").addEventListener("input", renderPreview);

    $("editorInput").addEventListener("paste", (event) => {
      const files = Array.from(event.clipboardData?.files || []);
      if (!files.some((file) => file.type.startsWith("image/"))) return;
      event.preventDefault();
      uploadImages(files);
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
      uploadImages(files);
    });

    $("imageInput").addEventListener("change", (event) => {
      uploadImages(event.target.files);
      event.target.value = "";
    });

    $("htmlInput").addEventListener("change", (event) => {
      importHtmlFile(event.target.files[0]);
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
