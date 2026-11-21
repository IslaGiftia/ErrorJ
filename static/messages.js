(function () {
  "use strict";

  var MAX_ATTACHMENTS = 3;
  var MAX_ATTACHMENT_BYTES = 500 * 1024 * 1024;
  var MAX_ATTACHMENT_TOTAL_BYTES = 500 * 1024 * 1024;
  var MAX_IMAGES = 9;
  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  var MAX_IMAGE_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var FILE_EXTENSIONS = IMAGE_EXTENSIONS.concat([
    ".7z",
    ".apk",
    ".bin",
    ".brd",
    ".csv",
    ".elf",
    ".exe",
    ".gz",
    ".hex",
    ".json",
    ".kicad_pcb",
    ".kicad_sch",
    ".md",
    ".pdf",
    ".pcb",
    ".rar",
    ".sch",
    ".tar",
    ".tgz",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
  ]);
  var pendingAttachments = [];
  var pendingImages = [];
  var toastTimer = null;
  var toastLeaveTimer = null;
  var canPost = false;
  var isAdmin = false;
  var viewerLikeName = "";
  var freshTargets = {};
  var jumpFrame = null;
  var dailyRemaining = null;
  var dailyLimit = 0;
  var lastMessageUnread = null;
  var messagePollBusy = false;
  var messageContentInput = null;
  var messageCharCount = null;

  function updateMessageSubmitAppearance() {
    var button = $("submitBtn");
    if (!button) return;
    button.classList.toggle(
      "is-inactive",
      !String(messageContentInput && messageContentInput.value || "").trim() &&
        !pendingCount()
    );
  }

  function updateMessageCharCount() {
    if (!messageContentInput || !messageCharCount) return;
    var length = messageContentInput.value.length;
    messageCharCount.textContent = String(length);
    messageCharCount.hidden =
      length === 0 && document.activeElement !== messageContentInput;
    updateMessageSubmitAppearance();
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var attachmentLimits = window.ErrorUploadLimits.get("message_file");
    var imageLimits = window.ErrorUploadLimits.get("message_image");
    MAX_ATTACHMENTS = Number(attachmentLimits.max_count) || MAX_ATTACHMENTS;
    MAX_ATTACHMENT_BYTES =
      Number(attachmentLimits.max_file_bytes) || MAX_ATTACHMENT_BYTES;
    MAX_ATTACHMENT_TOTAL_BYTES =
      Number(attachmentLimits.max_total_bytes) || MAX_ATTACHMENT_TOTAL_BYTES;
    MAX_IMAGES = Number(imageLimits.max_count) || MAX_IMAGES;
    MAX_IMAGE_BYTES = Number(imageLimits.max_file_bytes) || MAX_IMAGE_BYTES;
    MAX_IMAGE_TOTAL_BYTES =
      Number(imageLimits.max_total_bytes) || MAX_IMAGE_TOTAL_BYTES;
    var hint = $("messageUploadHint");
    if (hint) {
      hint.textContent =
        "单条最多 " + MAX_ATTACHMENTS + " 个私有附件，单个不超过 " +
        window.ErrorUploadLimits.label(MAX_ATTACHMENT_BYTES) +
        "；配图最多 " + MAX_IMAGES + " 张，单张不超过 " +
        window.ErrorUploadLimits.label(MAX_IMAGE_BYTES) +
        "。私有附件仅上传者本人和管理员可下载。";
    }
  }

  function $(id) {
    return document.getElementById(id);
  }

  function bindVisibilityToggle(buttonId, checkboxId, label) {
    var button = $(buttonId);
    var checkbox = $(checkboxId);
    if (!button || !checkbox) return;

    function render() {
      var visible = checkbox.checked;
      var text = label + "：" + (visible ? "展示" : "不展示");
      button.setAttribute("aria-pressed", visible ? "true" : "false");
      button.title = text;
      button.setAttribute("aria-label", text);
    }

    button.addEventListener("click", function () {
      checkbox.checked = !checkbox.checked;
      render();
    });
    render();
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
    box.classList.remove("is-leaving");
    box.hidden = false;
    clearTimeout(toastTimer);
    clearTimeout(toastLeaveTimer);
    toastTimer = setTimeout(function () {
      box.classList.add("is-leaving");
      // 和 .mg-toast.is-leaving 的过渡时长（--dur-fast 160ms）对齐，别让淡出被提前掐断
      toastLeaveTimer = setTimeout(function () {
        box.hidden = true;
        box.classList.remove("is-leaving");
      }, 160);
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
    if (window.ErrorRelativeTime) {
      return window.ErrorRelativeTime.format(text);
    }
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
    if (seconds < 60) return "刚刚";
    if (seconds < 3600) return Math.round(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.round(seconds / 3600) + " 小时前";
    var days = Math.max(1, Math.floor(seconds / 86400));
    return Math.min(999999, days) + " 天前";
  }

  function timeNode(className, text) {
    var node = el("span", className);
    if (window.ErrorRelativeTime) {
      window.ErrorRelativeTime.render(node, text);
    } else {
      node.textContent = formatTime(text);
    }
    return node;
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function applyQuota(limit, remaining) {
    dailyLimit = Number(limit) || 0;
    dailyRemaining = Number(remaining);
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
  function collectionBytes(files) {
    return files.reduce(function (sum, file) {
      return sum + file.size;
    }, 0);
  }

  function pendingCount() {
    return pendingAttachments.length + pendingImages.length;
  }

  function addFiles(fileList, purpose) {
    var incoming = Array.prototype.slice.call(fileList || []);
    if (!incoming.length) return;
    var isImage = purpose === "image";
    var target = isImage ? pendingImages : pendingAttachments;
    var maxCount = isImage ? MAX_IMAGES : MAX_ATTACHMENTS;
    var maxBytes = isImage ? MAX_IMAGE_BYTES : MAX_ATTACHMENT_BYTES;
    var maxTotalBytes = isImage
      ? MAX_IMAGE_TOTAL_BYTES
      : MAX_ATTACHMENT_TOTAL_BYTES;
    var label = isImage ? "配图" : "附件";
    var allowedExtensions = isImage ? IMAGE_EXTENSIONS : FILE_EXTENSIONS;
    for (var i = 0; i < incoming.length; i += 1) {
      var file = incoming[i];
      if (target.length >= maxCount) {
        toast("单条留言最多上传 " + maxCount + " 个" + label + "。");
        break;
      }
      if (allowedExtensions.indexOf(extensionOf(file.name)) < 0) {
        toast("不支持的" + label + "类型：" + file.name);
        continue;
      }
      if (file.size > maxBytes) {
        toast(
          "单个" + label + "不能超过 " +
            (window.ErrorUploadLimits
              ? window.ErrorUploadLimits.label(maxBytes)
              : formatSize(maxBytes)) +
            "：" + file.name
        );
        continue;
      }
      if (collectionBytes(target) + file.size > maxTotalBytes) {
        toast(
          label + "总大小不能超过 " +
            (window.ErrorUploadLimits
              ? window.ErrorUploadLimits.label(maxTotalBytes)
              : formatSize(maxTotalBytes)) +
            "。"
        );
        break;
      }
      var duplicated = target.some(function (item) {
        return item.name === file.name && item.size === file.size;
      });
      if (duplicated) continue;
      target.push(file);
    }
    renderPending();
  }

  function renderPending() {
    var list = $("pendingList");
    list.innerHTML = "";
    function appendEntries(files, purpose) {
      files.forEach(function (file, index) {
        var item = el(
          "li",
          "mg-pending mg-pending-" + purpose
        );
        if (purpose === "image") {
          var thumb = document.createElement("img");
          thumb.src = URL.createObjectURL(file);
          thumb.alt = file.name;
          thumb.addEventListener("load", function () {
            URL.revokeObjectURL(thumb.src);
          });
          item.appendChild(thumb);
        } else {
          item.classList.add("mg-pending-file");
          var fileIcon = document.createElement("i");
          fileIcon.setAttribute("data-lucide", "file");
          item.appendChild(fileIcon);
        }
        item.appendChild(el("span", "mg-pending-name", file.name));
        item.appendChild(el("span", "mg-file-size", formatSize(file.size)));
        var remove = el("button", "mg-pending-remove", "×");
        remove.type = "button";
        remove.title = "移除";
        remove.addEventListener("click", function () {
          files.splice(index, 1);
          renderPending();
        });
        item.appendChild(remove);
        list.appendChild(item);
      });
    }
    appendEntries(pendingAttachments, "attachment");
    appendEntries(pendingImages, "image");
    var hint = $("attachHint");
    if (pendingCount()) {
      hint.textContent =
        "附件 " + pendingAttachments.length + " 个 · 配图 " +
        pendingImages.length + " 张";
    } else {
      hint.textContent = "附件仅上传者本人和管理员可下载";
    }
    updateMessageSubmitAppearance();
    refreshIcons();
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
    addFiles($("fileInput").files, "attachment");
    $("fileInput").value = "";
  });

  $("imageInput").addEventListener("change", function () {
    addFiles($("imageInput").files, "image");
    $("imageInput").value = "";
  });

  // 附件：点击 / 拖到留言框 / 拖文件夹（按留言附件上限取前几个）
  if (window.ErrorDropZone) {
    var messageForm = $("messageForm");
    window.ErrorDropZone.attach($("pickFileBtn"), {
      input: $("fileInput"),
      dropTarget: messageForm || $("fileInput"),
      accept: FILE_EXTENSIONS,
      maxCount: function () {
        return Math.max(1, MAX_ATTACHMENTS - pendingAttachments.length);
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

  if (window.ErrorDropZone) {
    window.ErrorDropZone.attach($("pickImageBtn"), {
      input: $("imageInput"),
      dropTarget: $("pickImageBtn"),
      accept: ["image/*"].concat(IMAGE_EXTENSIONS),
      maxCount: function () {
        return Math.max(1, MAX_IMAGES - pendingImages.length);
      },
      multiple: true,
      pickerId: "errorjiang-message-image",
      toast: toast
    });
  } else {
    $("pickImageBtn").addEventListener("click", function () {
      $("imageInput").click();
    });
  }

  $("msgContent").addEventListener("paste", function (event) {
    var pasted = Array.prototype.slice.call(
      (event.clipboardData && event.clipboardData.files) || []
    );
    if (pasted.length) {
      event.preventDefault();
      addFiles(
        pasted.filter(function (file) {
          return file.type.indexOf("image/") === 0;
        }),
        "image"
      );
      addFiles(
        pasted.filter(function (file) {
          return file.type.indexOf("image/") !== 0;
        }),
        "attachment"
      );
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

  $("messageForm").addEventListener("submit", function (event) {
    event.preventDefault();
    if (sendBusy.active) return;
    var content = $("msgContent").value.trim();
    if (!content && !pendingCount()) {
      toast("写点内容，或者加个附件吧。");
      return;
    }
    var button = $("submitBtn");
    var queued = pendingAttachments
      .map(function (file) {
        return { file: file, kind: "attachment" };
      })
      .concat(
        pendingImages.map(function (file) {
          return { file: file, kind: "image" };
        })
      );
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
      if (window.ErrorButtons) window.ErrorButtons.busy(button, "正在发布");
    }
    Promise.all(
      queued.map(function (item) {
        return fileToBase64(item.file).then(function (data) {
          return {
            name: item.file.name,
            data_base64: data,
            kind: item.kind,
          };
        });
      })
    ).then(function (files) {
      var payload = {
        content: content,
        files: files,
        show_region: $("msgShowRegion").checked,
        show_device: $("msgShowDevice").checked,
      };
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
          fill.set(ratio, "发布");
        },
        onUploaded: function () {
          fill.busy("发布");
        },
      });
      sendBusy.abort = task.abort;
      return task.promise;
    }).then(function (result) {
      if (window.ErrorButtons) window.ErrorButtons.success(button, { label: "已发布" });
      $("msgContent").value = "";
      updateMessageCharCount();
      pendingAttachments = [];
      pendingImages = [];
      renderPending();
      toast(
        result && result.pending_review
          ? "留言已发布，待管理员审核通过后其他人才能看到"
          : "留言已发布"
      );
      if (result && result.daily_limit) {
        applyQuota(result.daily_limit, result.daily_remaining);
      }
      // 左上卡片的三项统计立刻跟上（不等侧栏下一轮轮询）
      if (window.ErrorSidebar) window.ErrorSidebar.refresh();
      return loadMessages();
    }).catch(function (err) {
      if (!withFiles && window.ErrorButtons) window.ErrorButtons.fail(button);
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
        if (file.private_attachment) {
          node.classList.add("mg-file-private");
          node.title = "私有附件，仅上传者本人和管理员可下载";
        }
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
      icon.setAttribute(
        "data-lucide",
        file.private_attachment ? "lock" : "file"
      );
      node.appendChild(icon);
      node.appendChild(el("span", "mg-file-name", file.file_name));
      if (file.pending) {
        node.appendChild(el("span", "mg-file-size", "审核中"));
      }
      node.appendChild(el("span", "mg-file-size", formatSize(file.file_size)));
      if (!canSave) node.appendChild(el("span", "mg-file-view-tag", "查看"));
      else if (file.private_attachment) {
        node.appendChild(el("span", "mg-file-view-tag", "下载"));
      }
      chips.appendChild(node);
    });
    wrap.appendChild(chips);
    return wrap;
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
   * 新点赞提醒：整张留言卡片方框呼吸；有未读时复用页面共用的
   * 「顶部」按钮，切成「↓ 点赞」并带呼吸，没有未读时是普通「↑ 顶部」。
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
    if (window.ErrorFreshVisibility) window.ErrorFreshVisibility.unwatch(card);
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

  function markFreshCard(card, ids) {
    if (!ids.length) return;
    card.classList.add("is-fresh");
    card.dataset.freshKind = "like";
    card.dataset.freshIds = ids.join(",");
    if (window.ErrorFreshVisibility) {
      window.ErrorFreshVisibility.watch(card, function () {
        clearFreshCard(card, ids);
      });
    }
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
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    popLikeButton(card);
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
      api.setPending({
        active: true,
        label: "点赞",
        title: "跳到新点赞",
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
    btn.innerHTML = '<i data-lucide="ellipsis-vertical" aria-hidden="true"></i>';
    var menu = el("div", "mg-more-menu");
    menu.hidden = true;
    menu.setAttribute("role", "menu");
    if (canDelete) {
      var delBtn = el("button", "mg-more-item is-danger", "删除");
      delBtn.type = "button";
      delBtn.setAttribute("role", "menuitem");
      delBtn.setAttribute("data-hold-confirm", "");
      delBtn.title = "长按删除";
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
    api("/api/site/messages/" + message.id, { method: "DELETE" })
      .then(function () {
        toast("已删除");
        return loadMessages();
      })
      .catch(function (err) {
        toast(err.message);
      });
  }

  function buildMessage(message) {
    var item = el("article", "mg-item " + (message.can_save ? "can-save" : "no-save"));
    var head = el("div", "mg-item-head");
    head.appendChild(el("span", "mg-nick", message.nickname || "匿名"));
    head.appendChild(timeNode("mg-time", message.created_at));
    // 设备信息（自动识别成「来自 Windows / macOS / Linux / 鸿蒙 / Android / iOS / ChromeOS」，
    // 认不出记「来自 Web」；有 site:device_name 权限的账号也可以自定义名称）
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
    var social = el("div", "mg-item-social");
    if (!message.pending_review && !message.rejected) {
      social.appendChild(buildLikeControl("message", message));
    }
    var canDelete = Boolean(message.can_delete);
    var canReport = message.status === "approved" && !message.mine;
    if (canDelete || canReport) {
      social.appendChild(buildMoreMenu(message, canDelete, canReport));
    }
    if (social.childElementCount) {
      item.appendChild(social);
    }
    // 整张卡片的方框呼吸：自己收到新点赞
    var rootFresh = Boolean(freshTargets[String(message.id)]);
    if (rootFresh) {
      markFreshCard(item, [message.id]);
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
      var visibleIds = {};
      latestMessageRows.forEach(function (row) {
        visibleIds[String(row.id)] = true;
      });
      (result[1] || []).forEach(function (id) {
        if (visibleIds[String(id)]) freshTargets[String(id)] = true;
      });
      var newest = 0;
      latestMessageRows.forEach(function (row) {
        newest = Math.max(newest, Number(row.id) || 0);
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
          !document.querySelector(".mg-more.is-open")
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
  var FILTER_VALUES = ["all", "mine", "liked"];
  var FILTER_LABELS = {
    all: "全部留言",
    mine: "我的",
    liked: "点赞",
  };
  var FILTER_EMPTY_TEXT = {
    mine: "你还没有发表过留言。",
    liked: "还没有你点赞过的留言。",
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
    function activate() {
      if (window.ErrorInertiaScroll) window.ErrorInertiaScroll.cancel();
      setSendFloatVisible(false);
      if (window.ErrorInertiaScroll && window.ErrorInertiaScroll.toTop) {
        window.ErrorInertiaScroll.toTop();
      } else if (typeof window.scrollTo === "function") {
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
    }
    if (window.ErrorFastActivate) window.ErrorFastActivate.bind(btn, activate);
    else btn.addEventListener("click", activate);
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
    if (window.ErrorFreshVisibility) window.ErrorFreshVisibility.reset();
    list.innerHTML = "";
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
  messageContentInput = $("msgContent");
  messageCharCount = $("messageCharCount");
  messageContentInput.addEventListener("input", updateMessageCharCount);
  messageContentInput.addEventListener("focus", updateMessageCharCount);
  messageContentInput.addEventListener("blur", updateMessageCharCount);
  updateMessageCharCount();
  setMessageFilter(new URLSearchParams(location.search).get("filter") || "all");
  $("msgShowRegion").checked = false;
  $("msgShowDevice").checked = false;
  bindVisibilityToggle("msgShowRegionBtn", "msgShowRegion", "IP属地");
  bindVisibilityToggle("msgShowDeviceBtn", "msgShowDevice", "设备平台");
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
    viewerLikeName = status.owner
      ? "管理员"
      : String(status.username || status.nickname || "");
    $("messageComposerPanel").hidden = !canPost;
    if (canPost) {
      initMessageFilters();
      loadQuota();
    }
    return loadMessages().then(pollMessageNotifications);
  }).catch(function () {
    canPost = false;
    isAdmin = false;
    $("messageComposerPanel").hidden = true;
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
