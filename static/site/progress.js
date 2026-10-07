/*
 * Error酱全站进度反馈
 *
 * - ErrorProgress.upload(url, options)
 *   用 XMLHttpRequest 发送 JSON 请求（和原来 fetch 的请求体完全一致），
 *   区别是能拿到"已发送字节数"，所以能画真实进度；返回 { promise, abort }。
 * - ErrorProgress.fill(host) / ErrorProgress.button(host)
 *   把按钮或文字元素变成"内部填充"进度条：set(比例, 文案) / busy(文案) / reset()。
 *   button() 额外接管点击：上传中点击按钮 = 取消（通过 options.onCancel 回调）。
 * - ErrorProgress.rows(box)
 *   多文件上传弹窗用的逐文件进度列表。
 */
(function () {
  "use strict";

  function clampRatio(value) {
    var ratio = Number(value);
    if (!isFinite(ratio)) return 0;
    return Math.max(0, Math.min(1, ratio));
  }

  function formatBytes(bytes) {
    var value = Number(bytes) || 0;
    if (value < 1024) return Math.round(value) + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(value < 10 * 1024 ? 1 : 0) + " KB";
    if (value < 1024 * 1024 * 1024) {
      var mb = value / (1024 * 1024);
      return mb.toFixed(mb < 10 ? 1 : 0) + " MB";
    }
    return (value / (1024 * 1024 * 1024)).toFixed(2) + " GB";
  }

  function percentText(ratio) {
    return Math.round(clampRatio(ratio) * 100) + "%";
  }

  function abortError() {
    var error = new Error("已取消上传");
    error.name = "AbortError";
    error.aborted = true;
    return error;
  }

  function isAborted(error) {
    return Boolean(error && (error.aborted || error.name === "AbortError"));
  }

  // ---------- 上传 ----------

  function upload(url, options) {
    var opts = options || {};
    var xhr = new XMLHttpRequest();
    var body = JSON.stringify(opts.payload || {});
    var promise = new Promise(function (resolve, reject) {
      xhr.open(opts.method || "POST", url, true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.upload.onprogress = function (event) {
        if (!opts.onProgress || !event.lengthComputable) return;
        opts.onProgress(clampRatio(event.loaded / event.total));
      };
      xhr.upload.onload = function () {
        if (opts.onProgress) opts.onProgress(1);
        if (opts.onUploaded) opts.onUploaded();
      };
      xhr.onload = function () {
        var data = {};
        try {
          data = JSON.parse(xhr.responseText || "{}") || {};
        } catch (err) {
          data = {};
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error((data && data.error) || "请求失败：" + xhr.status));
        }
      };
      xhr.onerror = function () {
        reject(new Error("网络中断，上传失败"));
      };
      xhr.ontimeout = function () {
        reject(new Error("上传超时，请重试"));
      };
      xhr.onabort = function () {
        reject(abortError());
      };
      xhr.send(body);
    });
    return {
      promise: promise,
      abort: function () {
        if (xhr.readyState !== 4) xhr.abort();
      },
    };
  }

  // ---------- 按钮 / 文字内部填充 ----------

  function ensureLabel(host) {
    var label =
      host.querySelector("[data-pg-label]") || host.querySelector("span:not(.pg-fill)");
    if (label) return label;
    label = document.createElement("span");
    label.className = "pg-label";
    while (host.firstChild) label.appendChild(host.firstChild);
    host.appendChild(label);
    return label;
  }

  function fill(host, options) {
    if (!host) return null;
    if (host.__pgFill) return host.__pgFill;
    var opts = options || {};
    var label = opts.label || ensureLabel(host);
    var originalText = label.textContent;
    var bar = document.createElement("span");
    bar.className = "pg-fill";
    bar.setAttribute("aria-hidden", "true");
    host.insertBefore(bar, host.firstChild);
    host.classList.add("pg-host");
    // 按钮保持自身的 button 角色，只有纯文字/容器才声明成 progressbar
    var isButton = host.tagName === "BUTTON";
    if (!isButton) host.setAttribute("role", "progressbar");

    var controller = {
      active: false,
      label: label,
      set: function (ratio, text) {
        controller.active = true;
        host.dataset.pgMode = "determinate";
        host.setAttribute("aria-busy", "true");
        if (!isButton) {
          host.setAttribute("aria-valuenow", String(Math.round(clampRatio(ratio) * 100)));
        }
        host.style.setProperty("--pg-fill", (clampRatio(ratio) * 100).toFixed(1) + "%");
        if (text != null) label.textContent = text;
        return controller;
      },
      busy: function (text) {
        controller.active = true;
        host.dataset.pgMode = "busy";
        host.setAttribute("aria-busy", "true");
        if (!isButton) host.removeAttribute("aria-valuenow");
        host.style.setProperty("--pg-fill", "100%");
        if (text != null) label.textContent = text;
        return controller;
      },
      reset: function (text) {
        controller.active = false;
        delete host.dataset.pgMode;
        host.removeAttribute("aria-busy");
        if (!isButton) host.removeAttribute("aria-valuenow");
        host.style.setProperty("--pg-fill", "0%");
        label.textContent = text == null ? originalText : text;
        return controller;
      },
    };
    host.__pgFill = controller;
    return controller;
  }

  function button(host, options) {
    var opts = options || {};
    var controller = fill(host, opts);
    if (!controller || host.__pgButton) return host.__pgButton || controller;
    // 捕获阶段先于页面自身的 click/submit 处理，上传中点击就是"取消"。
    host.addEventListener(
      "click",
      function (event) {
        if (!controller.active) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (opts.onCancel) opts.onCancel();
      },
      true
    );
    host.__pgButton = controller;
    return controller;
  }

  // ---------- 逐文件进度列表 ----------

  var ROW_TEXT = {
    waiting: "等待上传",
    processing: "服务器处理中…",
    done: "已完成",
    canceled: "已取消",
  };

  function rows(box) {
    var items = [];

    function reset() {
      items = [];
      if (box) {
        box.innerHTML = "";
        box.hidden = true;
      }
    }

    function add(file) {
      var name = (file && (file.name || file.file_name)) || "文件";
      var size = file && file.size;
      var row = document.createElement("div");
      row.className = "pg-row";
      row.dataset.state = "waiting";

      var nameEl = document.createElement("span");
      nameEl.className = "pg-row-name";
      nameEl.textContent = name;
      nameEl.title = name;

      var metaEl = document.createElement("span");
      metaEl.className = "pg-row-meta";
      metaEl.textContent = size ? formatBytes(size) : "";

      var bar = document.createElement("span");
      bar.className = "pg-row-bar";
      bar.setAttribute("role", "progressbar");
      var barFill = document.createElement("i");
      bar.appendChild(barFill);

      row.appendChild(nameEl);
      row.appendChild(metaEl);
      row.appendChild(bar);
      if (box) {
        box.appendChild(row);
        box.hidden = false;
      }
      items.push({ row: row, meta: metaEl, bar: bar, fill: barFill });
      return items.length - 1;
    }

    function set(index, state, options) {
      var item = items[index];
      if (!item) return;
      var opts = options || {};
      item.row.dataset.state = state;
      if (opts.ratio != null) {
        var ratio = clampRatio(opts.ratio);
        item.fill.style.width = (ratio * 100).toFixed(1) + "%";
        item.bar.setAttribute("aria-valuenow", String(Math.round(ratio * 100)));
      }
      if (state === "done" || state === "processing") {
        item.fill.style.width = "100%";
        item.bar.setAttribute("aria-valuenow", "100");
      }
      if (state === "canceled" || state === "waiting") {
        item.fill.style.width = "0%";
        item.bar.removeAttribute("aria-valuenow");
      }
      item.meta.textContent =
        opts.text != null
          ? opts.text
          : ROW_TEXT[state] != null
            ? ROW_TEXT[state]
            : "";
    }

    return { reset: reset, add: add, set: set, items: items };
  }

  window.ErrorProgress = {
    upload: upload,
    fill: fill,
    button: button,
    rows: rows,
    formatBytes: formatBytes,
    percentText: percentText,
    isAborted: isAborted,
  };
})();
