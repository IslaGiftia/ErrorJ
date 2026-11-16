/*
 * 「下载 → 文件」子页：工作台里勾了「公开到下载页」的文件。
 *
 * - 游客也能看到列表（文件名 / 分类 / 大小 / 时间），下载按钮点了提示「请登录后操作」；
 * - 登录账号点下载直接走 /api/site/files/<id>/download；
 * - 站长在这里上传的文件直接落进工作台的「其他 / 源码 / 固件…」分类并标为公开；
 * - 分享按钮走和其它子页同一套分享弹窗（动态 / 下载 / 外部链接）。
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
    requiresLogin: true,
    canUpload: false,
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

  function api(path, options) {
    return fetch(path, options).then(function (response) {
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

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function paintList() {
    var list = $("fileList");
    if (!list) return;
    var count = $("fileCount");
    if (count) count.textContent = state.files.length ? state.files.length + " 个文件" : "";
    if (!state.loaded) {
      list.innerHTML = '<p class="fl-empty">加载中…</p>';
      return;
    }
    if (state.error) {
      list.innerHTML = '<p class="fl-empty">' + escapeHtml(state.error) + "</p>";
      return;
    }
    if (!state.files.length) {
      list.innerHTML = '<p class="fl-empty">还没有公开的文件。</p>';
      return;
    }
    list.innerHTML = state.files
      .map(function (item) {
        var meta = [
          CATEGORY_LABELS[item.category] || "其他",
          formatSize(item.size_bytes),
          formatDate(item.created_at),
        ];
        var guest = Boolean(item.requires_login);
        return (
          '<article class="fl-item" data-focus-id="' + item.id + '">' +
          '<span class="fl-icon"><i data-lucide="' + iconFor(item) + '"></i></span>' +
          '<div class="fl-body">' +
          '<div class="fl-title" title="' + escapeHtml(item.title || "") + '">' +
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
          '<div class="fl-actions">' +
          '<button class="fl-action" type="button" data-share-file="' + item.id +
          '" title="分享"><i data-lucide="share-2"></i></button>' +
          '<button class="fl-action fl-action-download' + (guest ? " is-guest" : "") +
          '" type="button" data-file-download="' + item.id + '"' +
          (guest ? ' title="请登录后操作"' : ' title="下载"') +
          "><i data-lucide=\"download\"></i></button>" +
          "</div>" +
          "</article>"
        );
      })
      .join("");
    if (window.lucide) lucide.createIcons();
  }

  function loadFiles() {
    return api("/api/site/files")
      .then(function (data) {
        state.files = Array.isArray(data) ? data : [];
        state.requiresLogin = state.files.length
          ? Boolean(state.files[0].requires_login)
          : false;
        state.loaded = true;
        state.error = "";
      })
      .catch(function (err) {
        state.loaded = true;
        state.error = err.message || "加载失败";
      })
      .then(paintList);
  }

  function loadAuth() {
    return api("/api/auth/status")
      .then(function (status) {
        state.canUpload = Boolean(status.owner || status.admin);
        var button = $("fileUploadBtn");
        if (button) button.hidden = !state.canUpload;
      })
      .catch(function () {
        state.canUpload = false;
      });
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

  function share(id) {
    var item = state.files.filter(function (row) {
      return Number(row.id) === Number(id);
    })[0];
    if (!item) return;
    if (!window.ErrorShare) return;
    window.ErrorShare.open(
      "workbench_asset",
      item.id,
      item.title || item.original_name || "文件"
    );
  }

  /* ---------------- 上传（只有站长看得到入口） ---------------- */

  function readFileBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        resolve(result.slice(result.indexOf(",") + 1));
      };
      reader.onerror = function () {
        reject(new Error("读取文件失败"));
      };
      reader.readAsDataURL(file);
    });
  }

  function openUpload() {
    if (!state.canUpload) return;
    var modal = $("uploadModal");
    if (!modal) return;
    $("uploadFiles").value = "";
    $("uploadName").value = "";
    $("uploadCategory").value = "other";
    $("uploadFileLabel").textContent = "选择文件";
    $("uploadHint").textContent = "上传后直接出现在这个页面，登录账号可以下载。";
    modal.hidden = false;
    if (window.ErrorEmbed) window.ErrorEmbed.notifyDialog(true);
    if (window.lucide) lucide.createIcons();
  }

  function closeUpload() {
    var modal = $("uploadModal");
    if (modal) modal.hidden = true;
    if (window.ErrorEmbed) window.ErrorEmbed.notifyDialog(false);
  }

  function submitUpload() {
    var file = $("uploadFiles").files[0];
    if (!file) {
      toast("请选择文件");
      return;
    }
    var payload = {
      file_name: file.name,
      title: $("uploadName").value.trim(),
      category: $("uploadCategory").value,
      is_public: true,
    };
    var button = $("uploadSubmit");
    button.disabled = true;
    readFileBase64(file)
      .then(function (dataBase64) {
        payload.data_base64 = dataBase64;
        return api("/api/workbench/assets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      })
      .then(function () {
        closeUpload();
        toast("文件已上传");
        return loadFiles();
      })
      .catch(function (err) {
        toast(err.message || "上传失败");
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  function bind() {
    $("fileUploadBtn").addEventListener("click", openUpload);
    $("uploadClose").addEventListener("click", closeUpload);
    $("uploadCancel").addEventListener("click", closeUpload);
    $("uploadSubmit").addEventListener("click", submitUpload);
    $("uploadFiles").addEventListener("change", function () {
      var file = $("uploadFiles").files[0];
      $("uploadFileLabel").textContent = file ? file.name : "选择文件";
    });
    var list = $("fileList");
    list.addEventListener("click", function (event) {
      var downloadButton = event.target.closest("[data-file-download]");
      if (downloadButton) {
        download(downloadButton.getAttribute("data-file-download"));
        return;
      }
      var shareButton = event.target.closest("[data-share-file]");
      if (shareButton) {
        event.stopPropagation();
        share(shareButton.getAttribute("data-share-file"));
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !$("uploadModal").hidden) closeUpload();
    });
  }

  bind();
  loadAuth().then(loadFiles);
  window.ErrorRecommendTab = { key: "files", openAdd: openUpload };
})();
