(function () {
  "use strict";

  var noteId = Number(new URLSearchParams(location.search).get("id") || 0);
  var noteTitle = "";
  var outline = [];
  var outlineActive = -1;
  var outlineOpen = false;
  var outlineFrame = null;
  var HEAD_HIDE_OFFSET = 48;
  var lastScrollTop = 0;
  var headHidden = false;
  var suppressAutoHide = false;
  var autoHideTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function formatTime(value) {
    var text = String(value || "");
    return text.length >= 16 ? text.slice(0, 16) : text;
  }

  function renderMarkdown(text) {
    var source = String(text || "");
    if (!source.trim()) {
      return '<p class="nt-markdown-empty">这篇笔记还没有正文。</p>';
    }
    if (!window.marked || !window.DOMPurify) {
      return "<p>" + source.replace(/[&<>]/g, function (ch) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch];
      }) + "</p>";
    }
    var html = marked.parse(source);
    return DOMPurify.sanitize(html, { ADD_ATTR: ["target", "rel"] });
  }

  function decorate(container) {
    container.querySelectorAll("a[href]").forEach(function (link) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
  }

  /* ---------- 章节大纲（和笔记页一样的面包屑） ---------- */

  function outlineItems() {
    return Array.prototype.slice
      .call(document.querySelectorAll("#readContent h1, #readContent h2, #readContent h3"))
      .map(function (el) {
        return {
          el: el,
          level: Number(el.tagName.slice(1)),
          text: (el.textContent || "").trim(),
        };
      });
  }

  function chainFor(index) {
    if (index < 0 || !outline[index]) return [];
    var chain = [outline[index]];
    var level = outline[index].level;
    for (var i = index - 1; i >= 0 && level > 1; i -= 1) {
      if (outline[i].level < level) {
        chain.unshift(outline[i]);
        level = outline[i].level;
      }
    }
    return chain;
  }

  function setOutlineOpen(open) {
    outlineOpen = Boolean(open) && outline.length > 0;
    $("outlinePanel").hidden = !outlineOpen;
    $("outlineToggle").setAttribute("aria-expanded", outlineOpen ? "true" : "false");
  }

  function scrollToHeading(index) {
    var item = outline[index];
    if (!item) return;
    setHeadHidden(false);
    suppressAutoHide = true;
    clearTimeout(autoHideTimer);
    autoHideTimer = window.setTimeout(function () {
      suppressAutoHide = false;
    }, 700);
    item.el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function paintOutline() {
    var path = $("outlinePath");
    path.textContent = "";
    var chain = chainFor(outlineActive);
    var segments = [{ level: 0, text: noteTitle || "开头", index: -1 }].concat(
      chain.map(function (item) {
        return { level: item.level, text: item.text || "（空标题）", index: outline.indexOf(item) };
      })
    );
    segments.forEach(function (segment, position) {
      if (position) {
        path.appendChild(el("span", "nt-outline-sep", "›"));
      }
      var button = el(
        "button",
        "nt-outline-seg" +
          (segment.level ? " nt-lvl-" + segment.level : "") +
          (position === segments.length - 1 ? " active" : ""),
        segment.text
      );
      button.type = "button";
      button.title = segment.text;
      button.addEventListener("click", function () {
        if (segment.index < 0) {
          window.scrollTo({ top: 0, behavior: "smooth" });
        } else {
          scrollToHeading(segment.index);
        }
      });
      path.appendChild(button);
    });
    $("outlinePanel")
      .querySelectorAll(".nt-outline-item")
      .forEach(function (node) {
        node.classList.toggle(
          "active",
          Number(node.dataset.index) === outlineActive
        );
      });
  }

  function buildOutline() {
    outline = outlineItems();
    var bar = $("outlineBar");
    var panel = $("outlinePanel");
    panel.textContent = "";
    if (!outline.length) {
      bar.hidden = true;
      outlineActive = -1;
      setOutlineOpen(false);
      return;
    }
    bar.hidden = false;
    $("outlineCount").textContent = outline.length + " 节";
    outline.forEach(function (item, index) {
      var entry = el("button", "nt-outline-item nt-lvl-" + item.level);
      entry.type = "button";
      entry.dataset.index = String(index);
      entry.style.paddingLeft = 8 + (item.level - 1) * 14 + "px";
      entry.appendChild(el("span", "nt-ol-level", "H" + item.level));
      entry.appendChild(el("span", "nt-ol-text", item.text || "（空标题）"));
      entry.addEventListener("click", function () {
        scrollToHeading(index);
        setOutlineOpen(false);
      });
      panel.appendChild(entry);
    });
    outlineActive = -1;
    paintOutline();
    updateActiveHeading();
  }

  function updateActiveHeading() {
    outlineFrame = null;
    if (!outline.length) return;
    var threshold = 96;
    var index = -1;
    outline.forEach(function (item, position) {
      if (item.el.getBoundingClientRect().top <= threshold) index = position;
    });
    if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) {
      index = outline.length - 1;
    }
    if (index !== outlineActive) {
      outlineActive = index;
      paintOutline();
    }
  }

  function scheduleOutlineUpdate() {
    if (outlineFrame) return;
    outlineFrame = window.requestAnimationFrame(updateActiveHeading);
  }

  /* ---------- 向下滚动收起标题区，向上滚动再滑出来 ---------- */

  function syncReadTopHeight() {
    var top = $("readTop");
    if (!top) return;
    document.documentElement.style.setProperty(
      "--nt-read-top-h",
      (headHidden ? 0 : top.offsetHeight) + "px"
    );
  }

  function setHeadHidden(hidden) {
    headHidden = Boolean(hidden);
    var top = $("readTop");
    if (top) top.classList.toggle("is-hidden", headHidden);
    syncReadTopHeight();
  }

  function handleScroll() {
    var top = window.scrollY || document.documentElement.scrollTop || 0;
    var delta = top - lastScrollTop;
    lastScrollTop = top;
    if (!suppressAutoHide) {
      if (top <= 4) {
        if (headHidden) setHeadHidden(false);
      } else if (delta > 2 && top > HEAD_HIDE_OFFSET) {
        if (!headHidden) setHeadHidden(true);
      } else if (delta < -2) {
        if (headHidden) setHeadHidden(false);
      }
    }
    scheduleOutlineUpdate();
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function showStatus(text) {
    var status = $("readStatus");
    status.hidden = false;
    status.textContent = text;
    $("readContent").innerHTML = "";
  }

  function load() {
    if (!noteId) {
      showStatus("缺少笔记编号。");
      return;
    }
    fetch("/api/shared/notes/" + noteId, { cache: "no-store" })
      .then(function (response) {
        return response.json().catch(function () {
          return {};
        }).then(function (data) {
          if (!response.ok) {
            throw new Error((data && data.error) || "读取失败：" + response.status);
          }
          return data;
        });
      })
      .then(function (note) {
        var title = note.title || "未命名笔记";
        noteTitle = title;
        document.title = title + " · 笔记 · Error酱";
        $("crumbTitle").textContent = title;
        $("readTitle").textContent = title;
        $("readMeta").textContent =
          "更新于 " + formatTime(note.updated_at || note.created_at || "");
        var content = $("readContent");
        content.innerHTML = renderMarkdown(note.content);
        decorate(content);
        buildOutline();
        syncReadTopHeight();
      })
      .catch(function (err) {
        showStatus(err.message || "这篇笔记暂时无法阅读。");
      });
  }

  load();

  window.addEventListener("scroll", handleScroll, { passive: true });
  window.addEventListener("resize", function () {
    syncReadTopHeight();
    scheduleOutlineUpdate();
  });
  $("outlineToggle").addEventListener("click", function () {
    setOutlineOpen(!outlineOpen);
  });
  document.addEventListener("click", function (event) {
    if (!outlineOpen) return;
    if (event.target.closest && event.target.closest(".nt-read-outline")) return;
    setOutlineOpen(false);
  });
})();
