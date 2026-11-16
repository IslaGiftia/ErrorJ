/*
 * 「下载 → 文件」子页：列出工作台里勾了「公开到下载页」的文件。
 *
 * - 游客也能看到列表（文件名 / 分类 / 大小 / 时间），下载按钮点了提示「请登录后操作」；
 * - 登录账号点下载直接走 /api/site/files/<id>/download（服务端仍然只放行公开文件）。
 * - 分类筛选和搜索都在前端做：文件数量不多，不用再打接口。
 */
(function () {
  "use strict";

  var CATEGORY_LABELS = {
    source: "源码与工程",
    firmware: "固件",
    document: "文档",
    image: "图片",
    other: "其他",
  };
  var CATEGORY_ICONS = {
    source: "code",
    firmware: "cpu",
    document: "file-text",
    image: "image",
    other: "file",
  };
  var EXT_ICONS = {
    ".apk": "package",
    ".exe": "app-window",
  };

  var state = {
    files: [],
    category: "all",
    query: "",
    requiresLogin: true,
    loaded: false,
    error: "",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function toast(message) {
    var node = $("fileToast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () {
      node.hidden = true;
    }, 2600);
  }

  function api(path) {
    return fetch(path, { cache: "no-store", credentials: "same-origin" }).then(function (
      response
    ) {
      return response
        .json()
        .catch(function () {
          return null;
        })
        .then(function (data) {
          if (!response.ok) {
            throw new Error((data && data.error) || "加载失败（" + response.status + "）");
          }
          return data;
        });
    });
  }

  function formatSize(bytes) {
    var value = Number(bytes) || 0;
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return Math.max(1, Math.round(value / 1024)) + " KB";
    return (value / (1024 * 1024)).toFixed(value < 10 * 1024 * 1024 ? 1 : 0) + " MB";
  }

  function formatDate(text) {
    var value = String(text || "");
    return value.length >= 10 ? value.slice(0, 10) : value;
  }

  function iconFor(item) {
    return EXT_ICONS[item.extension] || CATEGORY_ICONS[item.category] || "file";
  }

  function visibleFiles() {
    var query = state.query.trim().toLowerCase();
    return state.files.filter(function (item) {
      if (state.category !== "all" && item.category !== state.category) return false;
      if (!query) return true;
      return (
        String(item.title || "").toLowerCase().indexOf(query) >= 0 ||
        String(item.original_name || "").toLowerCase().indexOf(query) >= 0
      );
    });
  }

  function paintFilters() {
    var box = $("fileFilters");
    if (!box) return;
    var present = {};
    state.files.forEach(function (item) {
      present[item.category || "other"] = true;
    });
    var keys = Object.keys(CATEGORY_LABELS).filter(function (key) {
      return present[key];
    });
    var html = '<button class="fl-chip' + (state.category === "all" ? " is-active" : "") +
      '" type="button" data-category="all" aria-pressed="' +
      (state.category === "all" ? "true" : "false") + '">全部</button>';
    keys.forEach(function (key) {
      var active = state.category === key;
      html +=
        '<button class="fl-chip' + (active ? " is-active" : "") +
        '" type="button" data-category="' + key + '" aria-pressed="' +
        (active ? "true" : "false") + '">' + CATEGORY_LABELS[key] + "</button>";
    });
    box.innerHTML = html;
  }

  function paintList() {
    var list = $("fileList");
    if (!list) return;
    var items = visibleFiles();
    var count = $("fileCount");
    if (count) {
      count.textContent = state.files.length
        ? state.files.length + " 个文件"
        : "";
    }
    if (!state.loaded) {
      list.innerHTML = '<p class="fl-empty">加载中…</p>';
      return;
    }
    if (state.error) {
      list.innerHTML = '<p class="fl-empty">' + state.error + "</p>";
      return;
    }
    if (!items.length) {
      list.innerHTML =
        '<p class="fl-empty">' +
        (state.files.length ? "没有匹配的文件。" : "还没有公开的文件。") +
        "</p>";
      return;
    }
    list.innerHTML = items
      .map(function (item) {
        var meta = [
          CATEGORY_LABELS[item.category] || "其他",
          formatSize(item.size_bytes),
          formatDate(item.created_at),
        ];
        var guest = Boolean(item.requires_login);
        return (
          '<article class="fl-item">' +
          '<span class="fl-icon"><i data-lucide="' + iconFor(item) + '"></i></span>' +
          '<div class="fl-body">' +
          '<div class="fl-title" title="' + escapeAttr(item.title || "") + '">' +
          escapeHtml(item.title || item.original_name || "文件") +
          "</div>" +
          '<div class="fl-meta">' +
          meta
            .filter(function (part) {
              return part !== "";
            })
            .map(function (part) {
              return "<span>" + escapeHtml(String(part)) + "</span>";
            })
            .join("") +
          "</div>" +
          "</div>" +
          '<button class="fl-dl' + (guest ? " is-guest" : " is-primary") +
          '" type="button" data-file-download="' + item.id + '"' +
          (guest ? ' title="请登录后操作"' : "") + ">" +
          '<i data-lucide="download"></i><span>下载</span></button>' +
          "</article>"
        );
      })
      .join("");
    if (window.lucide) lucide.createIcons();
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }

  function render() {
    paintFilters();
    paintList();
  }

  function load() {
    return api("/api/site/files")
      .then(function (data) {
        var items = Array.isArray(data) ? data : [];
        state.files = items;
        state.requiresLogin = items.length ? Boolean(items[0].requires_login) : false;
        state.loaded = true;
        state.error = "";
      })
      .catch(function (err) {
        state.loaded = true;
        state.error = err.message || "加载失败";
      })
      .then(render);
  }

  function download(id) {
    var item = state.files.filter(function (row) {
      return Number(row.id) === Number(id);
    })[0];
    if (!item) return;
    if (item.requires_login) {
      toast("请登录后操作");
      return;
    }
    location.href = "/api/site/files/" + item.id + "/download";
  }

  function bind() {
    var search = $("fileSearch");
    if (search) {
      search.addEventListener("input", function () {
        state.query = search.value || "";
        paintList();
      });
    }
    var filters = $("fileFilters");
    if (filters) {
      filters.addEventListener("click", function (event) {
        var button = event.target.closest("[data-category]");
        if (!button) return;
        state.category = button.getAttribute("data-category") || "all";
        render();
      });
    }
    var list = $("fileList");
    if (list) {
      list.addEventListener("click", function (event) {
        var button = event.target.closest("[data-file-download]");
        if (!button) return;
        download(button.getAttribute("data-file-download"));
      });
    }
  }

  bind();
  load();
})();
