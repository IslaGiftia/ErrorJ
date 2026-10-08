(function () {
  "use strict";

  var noteId = Number(new URLSearchParams(location.search).get("id") || 0);

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
        document.title = title + " · 笔记 · Error酱";
        $("crumbTitle").textContent = title;
        $("readTitle").textContent = title;
        $("readMeta").textContent =
          "更新于 " + formatTime(note.updated_at || note.created_at || "");
        var content = $("readContent");
        content.innerHTML = renderMarkdown(note.content);
        decorate(content);
      })
      .catch(function (err) {
        showStatus(err.message || "这篇笔记暂时无法阅读。");
      });
  }

  load();
})();
