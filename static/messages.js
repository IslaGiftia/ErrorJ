(function () {
  "use strict";

  var MAX_FILES = 3;
  var MAX_FILE_BYTES = 5 * 1024 * 1024;
  var MAX_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var FILE_EXTENSIONS = IMAGE_EXTENSIONS.concat([".pdf", ".txt", ".md"]);
  var pendingFiles = [];
  var toastTimer = null;
  var canPost = false;
  var isAdmin = false;
  // 自定义设备名称的权限点：管理员天然具备，普通账号由站长在账号权限里单独开
  var DEVICE_NAME_PERMISSION = "site:device_name";
  var canCustomDevice = false;
  var viewerLikeName = "";
  var freshTargets = {};
  var jumpFrame = null;
  var dailyRemaining = null;
  var dailyLimit = 0;
  var lastMessageUnread = null;
  var messagePollBusy = false;

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var limits = window.ErrorUploadLimits.get("message_file");
    MAX_FILES = Number(limits.max_count) || MAX_FILES;
    MAX_FILE_BYTES = Number(limits.max_file_bytes) || MAX_FILE_BYTES;
    MAX_TOTAL_BYTES = Number(limits.max_total_bytes) || MAX_TOTAL_BYTES;
    var hint = $("messageUploadHint");
    if (hint) {
      hint.textContent =
        "文字、附件都行。单条最多 " + MAX_FILES + " 个附件，单个不超过 " +
        window.ErrorUploadLimits.label(MAX_FILE_BYTES) +
        "（合计 " + window.ErrorUploadLimits.label(MAX_TOTAL_BYTES) +
        "）；支持图片、PDF、文本，整条留言和附件审核通过后其他人才能看到。";
    }
  }

  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function toast(text) {
    var box = $("toast");
    if (!box) return;
    box.textContent = text;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      box.hidden = true;
    }, 2600);
  }

  function api(path, options) {
    var config = options || {};
    return fetch(path, config).then(function (response) {
      return response.json().catch(function () {
        return {};
      }).then(function (data) {
        if (!response.ok) {
          throw new Error((data && data.error) || "请求失败：" + response.status);
        }
        return data;
      });
    });
  }

  function extensionOf(name) {
    var index = String(name || "").lastIndexOf(".");
    return index < 0 ? "" : String(name).slice(index).toLowerCase();
  }

  function isImageFile(name) {
    return IMAGE_EXTENSIONS.indexOf(extensionOf(name)) >= 0;
  }

  function formatSize(bytes) {
    var size = Number(bytes) || 0;
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / (1024 * 1024)).toFixed(1) + " MB";
  }

  function formatTime(text) {
    var value = String(text || "");
    var match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!match) return value;
    var then = new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5])
    );
    var seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
    var stamp =
      match[1] + "-" + match[2] + "-" + match[3] + " " + match[4] + ":" + match[5];
    if (seconds < 60) return "刚刚";
    if (seconds < 3600) return Math.round(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.round(seconds / 3600) + " 小时前";
    if (seconds < 86400 * 7) return Math.round(seconds / 86400) + " 天前";
    return stamp;
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function applyQuota(limit, remaining) {
    dailyLimit = Number(limit) || 0;
    dailyRemaining = Number(remaining);
    var hint = $("messageQuota");
    if (hint) {
      if (!dailyLimit || isNaN(dailyRemaining)) {
        hint.textContent = "";
        hint.hidden = true;
      } else {
        // 今日可留言/回复次数：左边是今天还能发的条数，右边是每日上限
        hint.textContent =
          "今日可留言/回复次数 " +
          Math.max(0, dailyRemaining) +
          "/" +
          dailyLimit;
        hint.hidden = false;
      }
    }
    var full = !isNaN(dailyRemaining) && dailyRemaining <= 0;
    Array.prototype.forEach.call(
      document.querySelectorAll(".mg-send-btn"),
      function (button) {
        button.disabled = full;
      }
    );
  }

  function loadQuota() {
    return api("/api/site/messages/quota")
      .then(function (data) {
        applyQuota(data.limit, data.remaining);
      })
      .catch(function () {});
  }

  // ---- 外观 ----
  var themePreference = "auto";
  try {
    themePreference = localStorage.getItem("errorSiteTheme") || "auto";
  } catch (err) {
    themePreference = "auto";
  }

  function applyTheme(preference, save) {
    themePreference = preference;
    var dark =
      preference === "dark" ||
      (preference === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var glyph = $("themeGlyph");
    if (glyph) glyph.textContent = dark ? "☾" : "☀";
    if (save) {
      try {
        localStorage.setItem("errorSiteTheme", preference);
      } catch (err) {}
    }
  }

  applyTheme(themePreference, false);

  // ---- 附件选择 ----
  function totalPendingBytes() {
    return pendingFiles.reduce(function (sum, file) {
      return sum + file.size;
    }, 0);
  }

  function addFiles(fileList) {
    var incoming = Array.prototype.slice.call(fileList || []);
    if (!incoming.length) return;
    for (var i = 0; i < incoming.length; i += 1) {
      var file = incoming[i];
      if (pendingFiles.length >= MAX_FILES) {
        toast("单条留言最多上传 " + MAX_FILES + " 个附件。");
        break;
      }
      if (FILE_EXTENSIONS.indexOf(extensionOf(file.name)) < 0) {
        toast("不支持的附件类型：" + file.name);
        continue;
      }
      if (file.size > MAX_FILE_BYTES) {
        toast(
          "单个附件不能超过 " +
            (window.ErrorUploadLimits ? window.ErrorUploadLimits.label(MAX_FILE_BYTES) : "5MB") +
            "：" + file.name
        );
        continue;
      }
      if (totalPendingBytes() + file.size > MAX_TOTAL_BYTES) {
        toast(
          "附件总大小不能超过 " +
            (window.ErrorUploadLimits ? window.ErrorUploadLimits.label(MAX_TOTAL_BYTES) : "15MB") +
            "。"
        );
        break;
      }
      var duplicated = pendingFiles.some(function (item) {
        return item.name === file.name && item.size === file.size;
      });
      if (duplicated) continue;
      pendingFiles.push(file);
    }
    renderPending();
  }

  function renderPending() {
    var list = $("pendingList");
    list.innerHTML = "";
    pendingFiles.forEach(function (file, index) {
      var item = el("li", "mg-pending");
      if (isImageFile(file.name)) {
        var thumb = document.createElement("img");
        thumb.src = URL.createObjectURL(file);
        thumb.alt = file.name;
        thumb.addEventListener("load", function () {
          URL.revokeObjectURL(thumb.src);
        });
        item.appendChild(thumb);
      }
      item.appendChild(el("span", "mg-pending-name", file.name));
      item.appendChild(el("span", "mg-file-size", formatSize(file.size)));
      var remove = el("button", "mg-pending-remove", "×");
      remove.type = "button";
      remove.title = "移除";
      remove.addEventListener("click", function () {
        pendingFiles.splice(index, 1);
        renderPending();
      });
      item.appendChild(remove);
      list.appendChild(item);
    });
    var hint = $("attachHint");
    if (pendingFiles.length) {
      hint.textContent = "已选 " + pendingFiles.length + " 个，共 " + formatSize(totalPendingBytes());
    } else {
      hint.textContent = "支持图片、PDF、TXT、MD（附件会先送审核）";
    }
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        var comma = result.indexOf(",");
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = function () {
        reject(new Error("读取附件失败：" + file.name));
      };
      reader.readAsDataURL(file);
    });
  }

  $("fileInput").addEventListener("change", function () {
    addFiles($("fileInput").files);
    $("fileInput").value = "";
  });

  // 附件：点击 / 拖到留言框 / 拖文件夹（按留言附件上限取前几个）
  if (window.ErrorDropZone) {
    var messageForm = $("messageForm");
    window.ErrorDropZone.attach($("pickFileBtn"), {
      input: $("fileInput"),
      dropTarget: messageForm || $("fileInput"),
      maxCount: function () {
        return Math.max(1, MAX_FILES - pendingFiles.length);
      },
      multiple: true,
      pickerId: "errorjiang-message-file",
      toast: toast
    });
  } else {
    $("pickFileBtn").addEventListener("click", function () {
      $("fileInput").click();
    });
  }

  $("msgContent").addEventListener("paste", function (event) {
    var pasted = (event.clipboardData && event.clipboardData.files) || [];
    if (pasted.length) {
      event.preventDefault();
      addFiles(pasted);
    }
  });

  // 带附件时按钮内显示进度，上传中再点一次按钮 = 取消（已选附件保留）。
  var sendBusy = { active: false, canceled: false, abort: null, fill: null };

  function sendFill() {
    if (!sendBusy.fill) {
      sendBusy.fill = ErrorProgress.button($("submitBtn"), {
        onCancel: function () {
          sendBusy.canceled = true;
          if (sendBusy.abort) sendBusy.abort();
        },
      });
    }
    return sendBusy.fill;
  }

  /*
   * 设备平台：「设备平台」勾选项对所有人开放（勾了才公开这条的设备来源，和「IP属地」同一套），
   * 具体文案由后端按 UA 自动识别；只有管理员能额外填一个自定义名称，留空就回到自动识别。
   */

  function deviceInfoValue() {
    var box = $("msgShowDevice");
    var input = $("msgDeviceInput");
    if (!canCustomDevice || !box || !input || !box.checked) return "";
    return input.value.trim();
  }

  function resetDeviceInfoField() {
    if ($("msgDeviceInput")) $("msgDeviceInput").value = "";
  }

  if ($("msgDeviceInput")) {
    // 管理员填了自定义名称就自动勾上「设备平台」，省得再点一下
    $("msgDeviceInput").addEventListener("input", function (event) {
      if (event.target.value.trim() && $("msgShowDevice")) {
        $("msgShowDevice").checked = true;
      }
    });
  }

  $("messageForm").addEventListener("submit", function (event) {
    event.preventDefault();
    if (sendBusy.active) return;
    var content = $("msgContent").value.trim();
    if (!content && !pendingFiles.length) {
      toast("写点内容，或者加个附件吧。");
      return;
    }
    var button = $("submitBtn");
    var queued = pendingFiles.slice();
    var withFiles = queued.length > 0;
    var fill = withFiles ? sendFill() : null;
    sendBusy.active = true;
    sendBusy.canceled = false;
    sendBusy.abort = null;
    if (withFiles) {
      fill.busy("读取附件…");
      button.title = "上传中，点击可取消";
    } else {
      button.disabled = true;
    }
    Promise.all(
      queued.map(function (file) {
        return fileToBase64(file).then(function (data) {
          return { name: file.name, data_base64: data };
        });
      })
    ).then(function (files) {
      var payload = {
        content: content,
        files: files,
        show_region: $("msgShowRegion").checked,
        // 设备平台是否公开：对所有人开放的勾选项，默认不勾选
        show_device: $("msgShowDevice").checked,
      };
      // 自定义设备名称：管理员或拿到 site:device_name 权限的账号才能带
      // （空串 = 让后端按 UA 自动识别）
      if (canCustomDevice) payload.device_info = deviceInfoValue();
      if (!withFiles) {
        return api("/api/site/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      if (sendBusy.canceled) throw new Error("已取消发送");
      var task = ErrorProgress.upload("/api/site/messages", {
        payload: payload,
        onProgress: function (ratio) {
          fill.set(ratio, "取消发送 " + ErrorProgress.percentText(ratio));
        },
        onUploaded: function () {
          fill.busy("发布中…");
        },
      });
      sendBusy.abort = task.abort;
      return task.promise;
    }).then(function (result) {
      $("msgContent").value = "";
      resetDeviceInfoField();
      pendingFiles = [];
      renderPending();
      toast(
        result && result.pending_review
          ? "留言已发布，待管理员审核通过后其他人才能看到"
          : "留言已发布"
      );
      if (result && result.daily_limit) {
        applyQuota(result.daily_limit, result.daily_remaining);
      }
      return loadMessages();
    }).catch(function (err) {
      if (sendBusy.canceled || ErrorProgress.isAborted(err)) {
        toast("已取消发送，附件还在，可以直接重试");
        return;
      }
      toast(err.message);
    }).then(function () {
      sendBusy.active = false;
      sendBusy.abort = null;
      if (fill) fill.reset();
      button.removeAttribute("title");
      button.disabled = !isNaN(dailyRemaining) && dailyRemaining <= 0;
    });
  });

  // ---- 附件查看器 ----
  /*
   * 图片走「灯箱」：原图独占屏幕、左右切换，没有白色外框；非图片附件仍用
   * 原来的白色弹窗 + iframe。image-zoom 只绑定一次（换图靠改 src + 清缩放），
   * 免得反复 bind 往同一个容器上叠滚轮 / 触摸监听。
   */
  var galleryFiles = [];
  var galleryIndex = 0;
  var viewerImg = null;
  var viewerZoomBound = false;

  function viewerImageEl() {
    var stage = $("fileViewerStage");
    if (!stage) return null;
    if (!viewerImg) {
      viewerImg = document.createElement("img");
      viewerImg.alt = "";
      viewerImg.draggable = false;
      stage.appendChild(viewerImg);
    }
    if (!viewerZoomBound && window.ErrorImageZoom) {
      window.ErrorImageZoom.bind(stage, viewerImg);
      viewerZoomBound = true;
    }
    return viewerImg;
  }

  // 换图 / 关闭时清掉上一张的缩放与滚动，白框和位移都不残留
  function resetViewerZoom() {
    var stage = $("fileViewerStage");
    if (viewerImg) {
      viewerImg._ezBase = null;
      viewerImg._ezScale = 1;
      viewerImg.style.width = "";
      viewerImg.style.height = "";
      viewerImg.style.maxWidth = "";
      viewerImg.style.maxHeight = "";
      viewerImg.classList.remove("is-zoomed");
    }
    if (stage) {
      stage.scrollLeft = 0;
      stage.scrollTop = 0;
      stage.classList.remove("is-panning");
    }
  }

  function renderViewerImage() {
    var image = viewerImageEl();
    var file = galleryFiles[galleryIndex];
    if (!image || !file) return;
    resetViewerZoom();
    image.src = file.url;
    image.alt = file.file_name || "";
    var multiple = galleryFiles.length > 1;
    var prev = $("fileViewerPrev");
    var next = $("fileViewerNext");
    var counter = $("fileViewerCounter");
    if (prev) prev.hidden = !multiple;
    if (next) next.hidden = !multiple;
    if (counter) {
      counter.hidden = !multiple;
      counter.textContent = galleryIndex + 1 + " / " + galleryFiles.length;
    }
  }

  function openImageViewer(files, index) {
    var images = (files || []).filter(function (file) {
      return file && file.is_image && file.visible !== false && file.url;
    });
    var viewer = $("fileViewer");
    if (!viewer || !images.length) return;
    galleryFiles = images;
    galleryIndex = Math.max(0, Math.min(Number(index) || 0, images.length - 1));
    var gallery = $("fileViewerGallery");
    var dialog = $("fileViewerDialog");
    var body = $("fileViewerBody");
    if (gallery) gallery.hidden = false;
    if (dialog) dialog.hidden = true;
    if (body) body.innerHTML = "";
    viewer.classList.add("is-image");
    viewer.hidden = false;
    renderViewerImage();
    refreshIcons();
  }

  function stepViewerImage(delta) {
    if (galleryFiles.length < 2) return;
    galleryIndex =
      (galleryIndex + delta + galleryFiles.length) % galleryFiles.length;
    renderViewerImage();
  }

  function openFileViewer(file) {
    var viewer = $("fileViewer");
    if (!viewer || !file) return;
    if (file.is_image && file.visible !== false && file.url) {
      openImageViewer([file], 0);
      return;
    }
    var body = $("fileViewerBody");
    var title = $("fileViewerTitle");
    var gallery = $("fileViewerGallery");
    var dialog = $("fileViewerDialog");
    if (!body) return;
    if (title) title.textContent = file.file_name || "查看附件";
    body.innerHTML = "";
    var frame = document.createElement("iframe");
    frame.src = file.url;
    frame.title = file.file_name || "附件预览";
    frame.setAttribute("referrerpolicy", "no-referrer");
    body.appendChild(frame);
    if (gallery) gallery.hidden = true;
    if (dialog) dialog.hidden = false;
    viewer.classList.remove("is-image");
    viewer.hidden = false;
  }

  function closeFileViewer() {
    var viewer = $("fileViewer");
    var body = $("fileViewerBody");
    if (viewer) viewer.hidden = true;
    if (body) body.innerHTML = "";
    galleryFiles = [];
    galleryIndex = 0;
    resetViewerZoom();
  }

  // ---- 列表 ----
  // 图片附件按朋友圈九宫格排（1 张等比例、2-4 张两列、5-9 张三列），超过 9 张
  // 第九格压一个「+剩余数量」；非图片附件仍是原来的文件条。
  function buildImageGallery(images) {
    var count = images.length;
    var cols = count === 1 ? 1 : count <= 4 ? 2 : 3;
    var gallery = el("div", "mg-gallery cols-" + cols);
    var shown = images.slice(0, 9);
    var extra = count - shown.length;
    shown.forEach(function (file, index) {
      var canSave = Boolean(file.can_save);
      var cell = el(
        "button",
        "mg-gallery-cell " + (canSave ? "can-save" : "no-save")
      );
      cell.type = "button";
      cell.title = file.pending
        ? file.file_name + "（审核中，仅你和管理员可见）"
        : canSave
          ? file.file_name
          : file.file_name + "（仅可查看）";
      if (file.pending) cell.classList.add("is-pending");
      var image = document.createElement("img");
      image.src = file.url;
      image.alt = file.file_name || "";
      image.loading = "lazy";
      image.draggable = false;
      cell.appendChild(image);
      cell.appendChild(el("span", "mg-media-guard", ""));
      if (file.pending) cell.appendChild(el("span", "mg-gallery-badge", "审核中"));
      if (extra > 0 && index === shown.length - 1) {
        cell.appendChild(el("span", "mg-gallery-more", "+" + extra));
      }
      cell.addEventListener("click", function () {
        openImageViewer(images, index);
      });
      gallery.appendChild(cell);
    });
    return gallery;
  }

  function buildFiles(files) {
    var wrap = el("div", "mg-attachments");
    var previewable = function (file) {
      return Boolean(file.is_image && !file.locked && file.visible !== false);
    };
    var images = files.filter(previewable);
    var others = files.filter(function (file) {
      return !previewable(file);
    });
    if (images.length) {
      wrap.appendChild(buildImageGallery(images));
    }
    if (!others.length) return wrap;
    var chips = el("div", "mg-files");
    others.forEach(function (file) {
      if (file.locked) {
        var locked = el("span", "mg-file mg-file-locked");
        var lockIcon = document.createElement("i");
        lockIcon.setAttribute("data-lucide", "lock");
        locked.appendChild(lockIcon);
        locked.appendChild(el("span", "mg-file-name", file.file_name || "附件"));
        locked.appendChild(el("span", "mg-file-size", "请登录后操作"));
        chips.appendChild(locked);
        return;
      }
      if (file.visible === false) {
        var pending = el("span", "mg-file mg-file-pending");
        var pendingIcon = document.createElement("i");
        pendingIcon.setAttribute("data-lucide", "clock");
        pending.appendChild(pendingIcon);
        pending.appendChild(el("span", "mg-file-name", "附件审核中"));
        pending.title = "审核通过后其他人才能看到";
        chips.appendChild(pending);
        return;
      }
      var url = file.url;
      var canSave = Boolean(file.can_save);
      var node;
      if (canSave) {
        node = el("a", "mg-file");
        node.href = url;
        node.download = file.file_name;
        node.rel = "noopener";
      } else {
        node = el("button", "mg-file mg-file-view");
        node.type = "button";
        node.title = file.file_name + "（仅可查看）";
        node.addEventListener("click", function () {
          openFileViewer(file);
        });
      }
      if (file.pending) node.classList.add("mg-file-pending");
      var icon = document.createElement("i");
      icon.setAttribute("data-lucide", "file");
      node.appendChild(icon);
      node.appendChild(el("span", "mg-file-name", file.file_name));
      if (file.pending) {
        node.appendChild(el("span", "mg-file-size", "审核中"));
      }
      node.appendChild(el("span", "mg-file-size", formatSize(file.file_size)));
      if (!canSave) node.appendChild(el("span", "mg-file-view-tag", "查看"));
      chips.appendChild(node);
    });
    wrap.appendChild(chips);
    return wrap;
  }

  /*
   * 回复框：形态照搬动态页评论框——左边输入框、右边「发送」，两个控件同高。
   * 没有独立的「取消」按钮（再次点「回复」即收起），也不再带「公开 IP 属地」勾选：
   * 属地只有「发留言」编辑区那一个入口，回复一律不带。
   */
  function buildReplyForm(parentId, placeholder) {
    var form = el("form", "mg-reply-form");
    form.hidden = true;

    var textArea = document.createElement("textarea");
    textArea.maxLength = 1000;
    textArea.rows = 1;
    textArea.placeholder = placeholder || "回复一下…";

    var sendBtn = el("button", "mg-btn mg-btn-primary mg-reply-send", "发送");
    sendBtn.type = "submit";

    form.append(textArea, sendBtn);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var content = textArea.value.trim();
      if (!content) {
        toast("回复内容不能为空。");
        return;
      }
      sendBtn.disabled = true;
      api("/api/site/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content, parent_id: parentId }),
      }).then(function () {
        applyQuota(dailyLimit, Math.max(0, (Number(dailyRemaining) || 0) - 1));
        toast("回复已发布");
        return loadMessages();
      }).catch(function (err) {
        toast(err.message);
      }).then(function () {
        sendBtn.disabled = !isNaN(dailyRemaining) && dailyRemaining <= 0;
      });
    });

    return form;
  }

  /* 点「回复」展开 / 收起回复框，展开时按钮变主题色（和动态页的评论回复一致） */
  function bindReplyToggle(btn, form) {
    btn.setAttribute("aria-expanded", "false");
    btn.addEventListener("click", function () {
      var open = form.hidden;
      form.hidden = !open;
      btn.classList.toggle("is-active", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) return;
      var area = form.querySelector("textarea");
      if (area) area.focus();
    });
  }

  /* 游客看到的「回复」只是占位：点击提示先登录，不展开输入框 */
  function bindGuestReply(btn) {
    btn.addEventListener("click", function () {
      toast("请登录后操作");
    });
  }

  function buildLikeControl(targetType, target) {
    var wrap = el("div", "mg-like");
    var btn = el("button", "mg-like-btn");
    var names = el("span", "mg-like-names", "");
    btn.type = "button";
    // 大拇指图标：未点赞跟随默认灰，点赞后点亮主题色；右边跟点赞者用户名
    btn.innerHTML = '<i data-lucide="thumbs-up" aria-hidden="true"></i>';
    function syncNames() {
      var users = (target.like_users || []).slice();
      if (!users.length) {
        names.hidden = true;
        names.textContent = "";
        return;
      }
      var shown = users.slice(0, 3).join("、");
      names.hidden = false;
      names.textContent =
        users.length > 3 ? shown + " 等 " + users.length + " 人" : shown;
    }
    function sync() {
      btn.classList.toggle("is-liked", Boolean(target.liked));
      btn.title = target.liked ? "取消点赞" : "点赞";
      syncNames();
    }
    names.hidden = true;
    sync();
    btn.addEventListener("click", function () {
      if (!canPost) {
        toast("请登录后操作");
        return;
      }
      btn.disabled = true;
      api("/api/site/likes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: targetType,
          target_id: target.id,
        }),
      }).then(function (data) {
        target.liked = Boolean(data && data.liked);
        target.like_count = Number(data && data.count) || 0;
        var users = Array.isArray(target.like_users) ? target.like_users : [];
        var own = viewerLikeName;
        if (own) {
          var index = users.indexOf(own);
          if (target.liked && index < 0) users.unshift(own);
          if (!target.liked && index >= 0) users.splice(index, 1);
        }
        target.like_users = users;
        sync();
      }).catch(function (err) {
        toast(err.message || "操作失败");
      }).then(function () {
        btn.disabled = false;
      });
    });
    wrap.appendChild(btn);
    wrap.appendChild(names);
    return wrap;
  }

  /*
   * 新互动提醒：整张留言卡片方框呼吸，新回复的正文额外高亮闪烁；
   * 右下角不再单独放「↓ 新回复」按钮，而是复用页面共用的「顶部」按钮——
   * 有未读时切成「↓ + 回复 / 点赞」并带呼吸，没有未读时是普通「↑ 顶部」。
   */
  function freshCards() {
    return Array.prototype.slice.call(
      document.querySelectorAll(".mg-item.is-fresh")
    );
  }

  function freshCardBelow() {
    return (
      freshCards().filter(function (node) {
        return node.getBoundingClientRect().top > window.innerHeight - 80;
      })[0] || null
    );
  }

  function backTopApi() {
    return window.ErrorBackToTop && window.ErrorBackToTop.setPending
      ? window.ErrorBackToTop
      : null;
  }

  function clearFreshCard(card, ids) {
    card.classList.remove("is-fresh");
    Array.prototype.forEach.call(
      card.querySelectorAll(".mg-reply-text.is-new-reply"),
      function (node) {
        node.classList.remove("is-new-reply");
      }
    );
    updateJumpButton();
    if (!canPost) return;
    ids.forEach(function (id) {
      api("/api/site/notifications/seen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module: "messages", target_id: id }),
      }).catch(function () {});
    });
  }

  function markFreshCard(card, ids, kind) {
    if (!ids.length) return;
    card.classList.add("is-fresh");
    card.dataset.freshKind = kind;
    card.dataset.freshIds = ids.join(",");
    var clear = function () {
      card.removeEventListener("mouseenter", clear);
      card.removeEventListener("touchstart", clear);
      clearFreshCard(card, ids);
    };
    card.addEventListener("mouseenter", clear);
    card.addEventListener("touchstart", clear, { passive: true });
  }

  // 移动端没有 hover：滚到新回复后把正文的闪烁重放一次（CSS 在触摸设备上只闪 3 次）
  function replayReplyBlink(card) {
    var text = card.querySelector(".mg-reply-text.is-new-reply");
    if (!text) return;
    text.classList.remove("is-new-reply");
    void text.offsetWidth;
    text.classList.add("is-new-reply");
  }

  function popLikeButton(card) {
    var like = card.querySelector(".mg-like-btn");
    if (!like) return;
    like.classList.remove("is-pop");
    void like.offsetWidth;
    like.classList.add("is-pop");
    window.setTimeout(function () {
      like.classList.remove("is-pop");
    }, 620);
  }

  function jumpToFreshCard(card) {
    if (!card) return;
    var kind = card.dataset.freshKind === "reply" ? "reply" : "like";
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    if (kind === "reply") replayReplyBlink(card);
    else popLikeButton(card);
  }

  var lastPendingKey = null;

  function updateJumpButton() {
    var api = backTopApi();
    if (!api) return;
    var card = freshCardBelow();
    var key = card
      ? card.dataset.freshKind + ":" + card.dataset.freshIds
      : "";
    // 滚动时只关心状态没变就别重设，省掉每帧一次布局计算
    if (key === lastPendingKey) return;
    lastPendingKey = key;
    if (card) {
      var isReply = card.dataset.freshKind === "reply";
      api.setPending({
        active: true,
        label: isReply ? "回复" : "点赞",
        title: isReply ? "跳到新回复" : "跳到新点赞",
        onActivate: function () {
          jumpToFreshCard(freshCardBelow() || card);
        },
      });
    } else {
      api.setPending({ active: false });
    }
    document.dispatchEvent(new CustomEvent("errorjumpvisibilitychange"));
  }

  window.addEventListener(
    "scroll",
    function () {
      if (jumpFrame) return;
      jumpFrame = window.requestAnimationFrame(function () {
        jumpFrame = null;
        updateJumpButton();
      });
    },
    { passive: true }
  );

  // ---------- 卡片右下角「更多」菜单（删除 / 举报）----------
  function closeAllMoreMenus() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".mg-more.is-open"),
      function (node) {
        node.classList.remove("is-open");
        var menu = node.querySelector(".mg-more-menu");
        if (menu) menu.hidden = true;
        var btn = node.querySelector(".mg-more-btn");
        if (btn) btn.setAttribute("aria-expanded", "false");
      }
    );
  }

  function buildMoreMenu(message, canDelete, canReport) {
    var more = el("div", "mg-more");
    var btn = el("button", "mg-more-btn");
    btn.type = "button";
    btn.title = "更多操作";
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "更多操作");
    btn.innerHTML = '<i data-lucide="ellipsis" aria-hidden="true"></i>';
    var menu = el("div", "mg-more-menu");
    menu.hidden = true;
    menu.setAttribute("role", "menu");
    if (canDelete) {
      var delBtn = el("button", "mg-more-item is-danger", "删除");
      delBtn.type = "button";
      delBtn.setAttribute("role", "menuitem");
      delBtn.addEventListener("click", function () {
        closeAllMoreMenus();
        deleteMessage(message);
      });
      menu.appendChild(delBtn);
    }
    if (canReport) {
      var reportBtn = el("button", "mg-more-item", "举报");
      reportBtn.type = "button";
      reportBtn.setAttribute("role", "menuitem");
      reportBtn.setAttribute("data-report-type", "message");
      reportBtn.setAttribute("data-report-key", message.id);
      reportBtn.setAttribute(
        "data-report-title",
        "留言：" + (message.content || "").slice(0, 40)
      );
      // 举报留言不要求登录（游客也能举报）；report.js 的全局点击委托会接着弹举报框，这里只负责收起菜单
      reportBtn.addEventListener("click", function () {
        closeAllMoreMenus();
      });
      menu.appendChild(reportBtn);
    }
    btn.addEventListener("click", function (event) {
      event.stopPropagation();
      var willOpen = menu.hidden;
      closeAllMoreMenus();
      menu.hidden = !willOpen;
      btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
      more.classList.toggle("is-open", willOpen);
    });
    more.append(btn, menu);
    return more;
  }

  function deleteMessage(message) {
    var hint = (message.replies || []).length
      ? "这条留言下面的回复也会一起删除。"
      : "删除后无法恢复。";
    window.ErrorDialog.confirm("确定要删除这条留言吗？\n" + hint, {
      title: "删除留言",
      confirmText: "删除",
      danger: true,
    }).then(function (confirmed) {
      if (!confirmed) return;
      return api("/api/site/messages/" + message.id, { method: "DELETE" })
        .then(function () {
          toast("已删除");
          return loadMessages();
        })
        .catch(function (err) {
          toast(err.message);
        });
    });
  }

  function buildMessage(message) {
    var item = el("article", "mg-item " + (message.can_save ? "can-save" : "no-save"));
    var head = el("div", "mg-item-head");
    head.appendChild(el("span", "mg-nick", message.nickname || "匿名"));
    head.appendChild(el("span", "mg-time", formatTime(message.created_at)));
    // 设备信息（来自 鸿蒙 / Android / iOS / Web，或管理员自定义的名称）
    if (message.device_info) {
      head.appendChild(el("span", "mg-device", message.device_info));
    }
    if (message.region) {
      head.appendChild(el("span", "mg-region", message.region));
    }
    if (message.pending_review) {
      head.appendChild(el("span", "mg-status is-pending", "待审核"));
    } else if (message.rejected) {
      head.appendChild(el("span", "mg-status is-rejected", "未通过审核"));
    }
    item.appendChild(head);
    if (message.content) {
      item.appendChild(el("p", "mg-text", message.content));
    }
    var files = message.files || [];
    if (files.length) {
      item.appendChild(buildFiles(files));
    }
    if (!message.pending_review && !message.rejected) {
      item.appendChild(buildLikeControl("message", message));
    }

    var repliesBox = el("div", "mg-replies");
    var rootForm = null;
    var canDelete = Boolean(message.can_delete);
    var canReport = message.status === "approved" && !message.mine;
    // 游客也要保留「回复」入口占位，点了再提示登录，所以这里带上 can_reply
    if (canPost || canDelete || canReport || message.can_reply) {
      var actions = el("div", "mg-item-actions");
      if (message.can_reply) {
        var replyBtn = el("button", "mg-link-btn", "回复");
        replyBtn.type = "button";
        actions.append(replyBtn);
        if (canPost) {
          rootForm = buildReplyForm(
            message.id,
            "回复 " + (message.nickname || "这条留言") + "…"
          );
          bindReplyToggle(replyBtn, rootForm);
        } else {
          bindGuestReply(replyBtn);
        }
      }
      /*
       * 举报 / 删除收进右下角的「三个点」，和「回复」同一行；自己发的不能举报，
       * 只有管理员或作者本人能删。游客这一排只剩这一个入口。
       */
      if (canDelete || canReport) {
        actions.append(buildMoreMenu(message, canDelete, canReport));
      }
      item.appendChild(actions);
    }
    var freshReplyIds = [];
    var replies = message.replies || [];
    replies.forEach(function (reply) {
      var row = el("div", "mg-reply " + (reply.can_save ? "can-save" : "no-save"));
      var replyHead = el("div", "mg-item-head");
      replyHead.appendChild(el("span", "mg-nick", reply.nickname || "匿名"));
      if (Number(reply.parent_id) !== Number(message.id)) {
        replyHead.appendChild(
          el("span", "mg-reply-to", "回复 @" + (reply.reply_to || "某人"))
        );
      }
      replyHead.appendChild(el("span", "mg-time", formatTime(reply.created_at)));
      if (reply.region) {
        replyHead.appendChild(el("span", "mg-region", reply.region));
      }
      row.appendChild(replyHead);
      if (reply.content) {
        var replyText = el("p", "mg-reply-text", reply.content);
        // 新回复：正文变主题色并闪烁（不再给回复那一行加方框呼吸）
        if (freshTargets[String(reply.id)]) {
          replyText.classList.add("is-new-reply");
          freshReplyIds.push(reply.id);
        }
        row.appendChild(replyText);
      }
      var replyFiles = reply.files || [];
      if (replyFiles.length) {
        row.appendChild(buildFiles(replyFiles));
      }
      // 游客同样保留「回复」占位按钮，点了提示登录
      if (canPost || reply.can_reply) {
        var replyActions = el("div", "mg-item-actions");
        var subReplyBtn = el("button", "mg-link-btn", "回复");
        subReplyBtn.type = "button";
        replyActions.appendChild(subReplyBtn);
        row.appendChild(replyActions);
        if (canPost) {
          var subForm = buildReplyForm(
            reply.id,
            "回复 " + (reply.nickname || "这条回复") + "…"
          );
          bindReplyToggle(subReplyBtn, subForm);
          row.appendChild(subForm);
        } else {
          bindGuestReply(subReplyBtn);
        }
      }
      repliesBox.appendChild(row);
    });

    item.appendChild(repliesBox);
    // 整张卡片的方框呼吸：自己收到新点赞，或卡里的某条回复是新的
    var rootFresh = Boolean(freshTargets[String(message.id)]);
    if (rootFresh || freshReplyIds.length) {
      var freshIds = freshReplyIds.slice();
      if (rootFresh) freshIds.unshift(message.id);
      markFreshCard(
        item,
        freshIds,
        freshReplyIds.length ? "reply" : "like"
      );
    }
    if (rootForm) {
      item.appendChild(rootForm);
    }
    return item;
  }

  function loadMessages() {
    var list = $("messageList");
    var targetsRequest = canPost
      ? api("/api/site/messages/unread")
          .then(function (data) {
            return (data && data.targets) || [];
          })
          .catch(function () {
            return [];
          })
      : Promise.resolve([]);
    return Promise.all([api("/api/site/messages"), targetsRequest]).then(function (
      result
    ) {
      var payload = result[0] || {};
      latestMessageRows = Array.isArray(payload) ? payload : (payload.messages || []);
      freshTargets = {};
      (result[1] || []).forEach(function (id) {
        freshTargets[String(id)] = true;
      });
      var newest = 0;
      latestMessageRows.forEach(function (row) {
        newest = Math.max(newest, Number(row.id) || 0);
        (row.replies || []).forEach(function (reply) {
          newest = Math.max(newest, Number(reply.id) || 0);
        });
      });
      if (isAdmin) {
        api("/api/site/messages/seen", {
          method: "POST",
          body: JSON.stringify({}),
        }).catch(function () {});
      }
      renderRows();
    }).catch(function (err) {
      list.innerHTML = "";
      list.appendChild(el("div", "mg-empty", "加载失败：" + err.message));
    });
  }

  function pollMessageNotifications() {
    if (!canPost || messagePollBusy) return;
    messagePollBusy = true;
    fetch("/api/site/notifications/summary", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("通知状态加载失败");
        return response.json();
      })
      .then(function (data) {
        var count = Number(data.messages) || 0;
        var previous = lastMessageUnread;
        lastMessageUnread = count;
        if (
          previous !== null &&
          count !== previous &&
          !document.querySelector(".mg-reply-form:not([hidden])")
        ) {
          loadMessages();
        }
      })
      .catch(function () {})
      .then(function () {
        messagePollBusy = false;
      });
  }

  // ---------- 筛选 ----------
  var FILTER_VALUES = ["all", "mine", "replied", "liked"];
  var FILTER_LABELS = {
    all: "全部留言",
    mine: "我的",
    replied: "评论",
    liked: "点赞",
  };
  var FILTER_EMPTY_TEXT = {
    mine: "你还没有发表过留言。",
    liked: "还没有你点赞过的留言。",
    replied: "还没有你评论过的留言。",
  };
  var currentMessageFilter = "all";
  var latestMessageRows = [];

  // 悬浮按钮的文字 + 菜单里的选中态保持同步
  function syncFilterControl() {
    var label = $("messageFilterLabel");
    if (label) {
      label.textContent = FILTER_LABELS[currentMessageFilter] || FILTER_LABELS.all;
    }
    Array.prototype.forEach.call(
      document.querySelectorAll("#messageFilterMenu [data-mg-filter]"),
      function (node) {
        var active =
          node.getAttribute("data-mg-filter") === currentMessageFilter;
        node.classList.toggle("is-active", active);
        node.setAttribute("aria-selected", active ? "true" : "false");
      }
    );
  }

  function filterMenuOpen() {
    var menu = $("messageFilterMenu");
    return Boolean(menu && !menu.hidden);
  }

  function setFilterMenuOpen(open) {
    var menu = $("messageFilterMenu");
    var btn = $("messageFilterBtn");
    var dock = $("messageFilter");
    if (menu) menu.hidden = !open;
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (dock) dock.classList.toggle("is-open", open);
  }

  function closeFilterMenu() {
    if (filterMenuOpen()) setFilterMenuOpen(false);
  }

  function messageEmptyText() {
    if (currentMessageFilter !== "all") {
      return (
        FILTER_EMPTY_TEXT[currentMessageFilter] ||
        "没有符合条件的留言。"
      );
    }
    return canPost ? "还没有留言，来说点什么吧。" : "还没有留言。";
  }

  function messageMatchesFilter(row) {
    if (currentMessageFilter === "mine") return Boolean(row.mine);
    if (currentMessageFilter === "liked") return Boolean(row.liked_by_me);
    if (currentMessageFilter === "replied") return Boolean(row.replied_by_me);
    return true;
  }

  function filterRows(rows) {
    if (currentMessageFilter === "all") return rows;
    return rows.filter(messageMatchesFilter);
  }

  function setMessageFilter(value) {
    if (FILTER_VALUES.indexOf(value) < 0) value = "all";
    currentMessageFilter = value;
    syncFilterControl();
    var url = new URL(window.location.href);
    if (value === "all") url.searchParams.delete("filter");
    else url.searchParams.set("filter", value);
    history.replaceState(null, "", url.toString());
  }

  function initMessageFilters() {
    var dock = $("messageFilter");
    if (!dock || !canPost) return;
    dock.hidden = false;
    syncFilterControl();
    var btn = $("messageFilterBtn");
    if (btn) {
      btn.addEventListener("click", function () {
        setFilterMenuOpen(!filterMenuOpen());
      });
    }
    var menu = $("messageFilterMenu");
    if (menu) {
      menu.addEventListener("click", function (event) {
        var option = event.target.closest("[data-mg-filter]");
        if (!option) return;
        var value = option.getAttribute("data-mg-filter");
        setFilterMenuOpen(false);
        if (value === currentMessageFilter) return;
        setMessageFilter(value);
        renderRows();
      });
    }
    // 点菜单以外的地方关掉；Esc 同样收起
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest("#messageFilter")) return;
      closeFilterMenu();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeFilterMenu();
    });
    initSendFloat();
  }

  /*
   * 「发送留言」悬浮按钮：只有编辑框完全滚出视野上方时才渐显（纯 opacity）；
   * 点它先淡出，再平滑滚回顶部并聚焦输入框，滚回顶部后按钮继续保持隐藏。
   */
  function setSendFloatVisible(visible) {
    var btn = $("messageSendBtn");
    if (!btn) return;
    btn.classList.toggle("is-visible", Boolean(visible));
    btn.setAttribute("aria-hidden", visible ? "false" : "true");
    btn.tabIndex = visible ? 0 : -1;
  }

  function initSendFloat() {
    var btn = $("messageSendBtn");
    var composer = $("messageComposerPanel");
    if (!btn || !composer) return;
    setSendFloatVisible(false);
    btn.addEventListener("click", function () {
      setSendFloatVisible(false);
      if (typeof window.scrollTo === "function") {
        try {
          window.scrollTo({ top: 0, behavior: "smooth" });
        } catch (err) {
          window.scrollTo(0, 0);
        }
      }
      var area = $("msgContent");
      if (!area) return;
      // 等平滑滚动起步后再聚焦，并阻止聚焦把页面瞬间拽回输入框
      window.setTimeout(function () {
        try {
          area.focus({ preventScroll: true });
        } catch (err) {
          area.focus();
        }
      }, 0);
    });
    if (typeof window.IntersectionObserver === "function") {
      var observer = new IntersectionObserver(
        function (entries) {
          var entry = entries[entries.length - 1];
          // bottom <= 0 即整块编辑框已经滚到视野上方
          setSendFloatVisible(
            !entry.isIntersecting && entry.boundingClientRect.bottom <= 0
          );
        },
        { threshold: 0 }
      );
      observer.observe(composer);
      return;
    }
    // 兜底：没有 IntersectionObserver 时用 rAF 节流的滚动监听
    var ticking = false;
    var update = function () {
      ticking = false;
      setSendFloatVisible(composer.getBoundingClientRect().bottom <= 0);
    };
    window.addEventListener(
      "scroll",
      function () {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(update);
      },
      { passive: true }
    );
    update();
  }

  function renderRows() {
    var list = $("messageList");
    if (!list) return;
    var rows = filterRows(latestMessageRows);
    list.innerHTML = "";
    var total = 0;
    rows.forEach(function (row) {
      total += 1 + (row.replies || []).length;
    });
    if (!rows.length) {
      list.appendChild(el("div", "mg-empty", messageEmptyText()));
      return;
    }
    rows.forEach(function (row) {
      list.appendChild(buildMessage(row));
    });
    refreshIcons();
    updateJumpButton();
  }

  renderPending();
  setMessageFilter(new URLSearchParams(location.search).get("filter") || "all");
  $("msgShowRegion").checked = false;
  $("msgShowDevice").checked = false;
  refreshIcons();
  if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);

  var messageList = $("messageList");
  if (messageList) {
    messageList.addEventListener("contextmenu", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      if (target.closest(".can-save") || target.closest("input, textarea")) return;
      event.preventDefault();
    });
    messageList.addEventListener("dragstart", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest("img")) {
        event.preventDefault();
      }
    });
    messageList.addEventListener("copy", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      if (target.closest(".can-save") || target.closest("input, textarea")) return;
      event.preventDefault();
    });
  }

  var fileViewer = $("fileViewer");
  var fileViewerGallery = $("fileViewerGallery");
  var fileViewerStage = $("fileViewerStage");

  // 点菜单以外的地方就收起「三个点」菜单
  document.addEventListener("click", function (event) {
    if (event.target && event.target.closest && event.target.closest(".mg-more")) {
      return;
    }
    closeAllMoreMenus();
  });

  if (fileViewer) {
    fileViewer.addEventListener("click", function (event) {
      if (event.target === fileViewer) closeFileViewer();
    });
    fileViewer.addEventListener("contextmenu", function (event) {
      event.preventDefault();
    });
  }
  // 灯箱模式下点图片周围的空白（stage / gallery 本身）也退出
  if (fileViewerGallery) {
    fileViewerGallery.addEventListener("click", function (event) {
      if (event.target === fileViewerGallery || event.target === fileViewerStage) {
        closeFileViewer();
      }
    });
  }
  var fileViewerClose = $("fileViewerClose");
  if (fileViewerClose) {
    fileViewerClose.addEventListener("click", closeFileViewer);
  }
  var fileViewerCloseImg = $("fileViewerCloseImg");
  if (fileViewerCloseImg) {
    fileViewerCloseImg.addEventListener("click", closeFileViewer);
  }
  var fileViewerPrev = $("fileViewerPrev");
  if (fileViewerPrev) {
    fileViewerPrev.addEventListener("click", function () {
      stepViewerImage(-1);
    });
  }
  var fileViewerNext = $("fileViewerNext");
  if (fileViewerNext) {
    fileViewerNext.addEventListener("click", function () {
      stepViewerImage(1);
    });
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAllMoreMenus();
      closeFileViewer();
    } else if (event.key === "ArrowLeft" && fileViewer && !fileViewer.hidden) {
      stepViewerImage(-1);
    } else if (event.key === "ArrowRight" && fileViewer && !fileViewer.hidden) {
      stepViewerImage(1);
    }
  });

  api("/api/auth/status").then(function (status) {
    canPost = Boolean(status.authenticated);
    isAdmin = Boolean(status.admin || status.owner);
    // 自定义设备名称：管理员天然可以，普通账号看「工作台 → 账号权限」里有没有开这一项
    canCustomDevice =
      isAdmin ||
      (Array.isArray(status.permissions) &&
        status.permissions.indexOf(DEVICE_NAME_PERMISSION) >= 0);
    viewerLikeName = status.owner
      ? "管理员"
      : String(status.username || status.nickname || "");
    $("messageComposerPanel").hidden = !canPost;
    $("msgDeviceField").hidden = !canCustomDevice;
    if (canPost) {
      initMessageFilters();
      loadQuota();
    }
    return loadMessages().then(pollMessageNotifications);
  }).catch(function () {
    canPost = false;
    isAdmin = false;
    canCustomDevice = false;
    $("messageComposerPanel").hidden = true;
    $("msgDeviceField").hidden = true;
    return loadMessages();
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) pollMessageNotifications();
  });
  window.addEventListener("focus", pollMessageNotifications);
  window.addEventListener("online", pollMessageNotifications);
  setInterval(function () {
    if (!document.hidden) pollMessageNotifications();
  }, 5000);
})();
