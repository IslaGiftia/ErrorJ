(function () {
  "use strict";

  var MAX_FILES = 3;
  var MAX_FILE_BYTES = 5 * 1024 * 1024;
  var MAX_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var FILE_EXTENSIONS = IMAGE_EXTENSIONS.concat([".pdf", ".txt", ".md"]);
  var REGION_KEY = "errorShowRegion";

  var pendingFiles = [];
  var toastTimer = null;
  var canPost = false;
  var isAdmin = false;
  var viewerLikeName = "";
  var freshTargets = {};
  var jumpBtn = null;
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
    return match[2] + "-" + match[3] + " " + match[4] + ":" + match[5];
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function regionPreference() {
    try {
      // 默认不公开 IP 属地，用户主动勾选后才记住
      return localStorage.getItem(REGION_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function rememberRegionPreference(value) {
    try {
      localStorage.setItem(REGION_KEY, value ? "1" : "0");
    } catch (err) {}
  }

  function applyQuota(limit, remaining) {
    dailyLimit = Number(limit) || 0;
    dailyRemaining = Number(remaining);
    var hint = $("messageQuota");
    if (hint) {
      if (!dailyLimit || isNaN(dailyRemaining)) {
        hint.textContent = "";
        hint.hidden = true;
      } else if (dailyRemaining > 0) {
        hint.textContent =
          "每天最多 " + dailyLimit + " 条留言（含回复），今天还可以发 " + dailyRemaining + " 条";
        hint.hidden = false;
      } else {
        hint.textContent = "今天的 " + dailyLimit + " 条留言已用完，明天 0 点恢复";
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

  $("pickFileBtn").addEventListener("click", function () {
    $("fileInput").click();
  });

  $("fileInput").addEventListener("change", function () {
    addFiles($("fileInput").files);
    $("fileInput").value = "";
  });

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
          fill.set(ratio, "取消发送 " + ErrorProgress.percentText(ratio));
        },
        onUploaded: function () {
          fill.busy("发布中…");
        },
      });
      sendBusy.abort = task.abort;
      return task.promise;
    }).then(function (result) {
      rememberRegionPreference($("msgShowRegion").checked);
      $("msgContent").value = "";
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

  // ---- 列表 ----
  function openFileViewer(file) {
    var viewer = $("fileViewer");
    var body = $("fileViewerBody");
    var title = $("fileViewerTitle");
    if (!viewer || !body) return;
    if (title) title.textContent = file.file_name || "查看附件";
    body.innerHTML = "";
    if (file.is_image) {
      var image = document.createElement("img");
      image.src = file.url;
      image.alt = file.file_name || "";
      image.draggable = false;
      body.appendChild(image);
    } else {
      var frame = document.createElement("iframe");
      frame.src = file.url;
      frame.title = file.file_name || "附件预览";
      frame.setAttribute("referrerpolicy", "no-referrer");
      body.appendChild(frame);
    }
    viewer.hidden = false;
  }

  function closeFileViewer() {
    var viewer = $("fileViewer");
    var body = $("fileViewerBody");
    if (viewer) viewer.hidden = true;
    if (body) body.innerHTML = "";
  }

  function buildFiles(files) {
    var wrap = el("div", "mg-files");
    files.forEach(function (file) {
      if (file.locked) {
        var locked = el("span", "mg-file mg-file-locked");
        var lockIcon = document.createElement("i");
        lockIcon.setAttribute("data-lucide", "lock");
        locked.appendChild(lockIcon);
        locked.appendChild(el("span", "mg-file-name", file.file_name || "附件"));
        locked.appendChild(el("span", "mg-file-size", "登录后可查看"));
        wrap.appendChild(locked);
        return;
      }
      if (file.visible === false) {
        var pending = el("span", "mg-file mg-file-pending");
        var pendingIcon = document.createElement("i");
        pendingIcon.setAttribute("data-lucide", "clock");
        pending.appendChild(pendingIcon);
        pending.appendChild(el("span", "mg-file-name", "附件审核中"));
        pending.title = "审核通过后其他人才能看到";
        wrap.appendChild(pending);
        return;
      }
      var url = file.url;
      var canSave = Boolean(file.can_save);
      if (file.is_image) {
        var thumb = el("button", "mg-thumb " + (canSave ? "can-save" : "no-save"));
        thumb.type = "button";
        thumb.title = file.pending
          ? file.file_name + "（审核中，仅你和管理员可见）"
          : canSave
            ? file.file_name
            : file.file_name + "（仅可查看）";
        if (file.pending) thumb.classList.add("is-pending");
        var image = document.createElement("img");
        image.src = url;
        image.alt = file.file_name;
        image.loading = "lazy";
        image.draggable = false;
        thumb.appendChild(image);
        thumb.appendChild(el("span", "mg-media-guard", ""));
        thumb.addEventListener("click", function () {
          openFileViewer(file);
        });
        wrap.appendChild(thumb);
        return;
      }
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
      wrap.appendChild(node);
    });
    return wrap;
  }

  function buildReplyForm(parentId, placeholder) {
    var form = el("form", "mg-reply-form");
    form.hidden = true;

    var textField = el("div", "mg-field");
    textField.appendChild(el("label", "", "回复"));
    var textArea = document.createElement("textarea");
    textArea.maxLength = 1000;
    textArea.placeholder = placeholder || "回复一下…";
    textField.appendChild(textArea);

    var regionLabel = el("label", "mg-region-toggle");
    var regionInput = document.createElement("input");
    regionInput.type = "checkbox";
    regionInput.checked = regionPreference();
    regionLabel.append(
      regionInput,
      el("span", "", "公开 IP 属地（国内显示省份，国外显示国家 / 地区）")
    );

    var row = el("div", "mg-compose-row");
    var cancelBtn = el("button", "mg-btn mg-btn-ghost", "取消");
    cancelBtn.type = "button";
    var sendBtn = el("button", "mg-btn mg-btn-primary", "提交回复");
    sendBtn.classList.add("mg-send-btn");
    sendBtn.type = "submit";
    row.append(cancelBtn, sendBtn);

    form.append(textField, regionLabel, row);

    cancelBtn.addEventListener("click", function () {
      textArea.value = "";
      form.hidden = true;
    });

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
        body: JSON.stringify({
          content: content,
          parent_id: parentId,
          show_region: regionInput.checked,
        }),
      }).then(function () {
        rememberRegionPreference(regionInput.checked);
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

  function buildLikeControl(targetType, target) {
    var wrap = el("div", "mg-like");
    var btn = el("button", "mg-like-btn", "♥");
    var count = el("span", "mg-like-count", String(target.like_count || 0));
    var names = el("span", "mg-like-names", "");
    btn.type = "button";
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
      count.textContent = String(target.like_count || 0);
      count.hidden = !target.like_count && !target.liked;
      syncNames();
    }
    count.hidden = true;
    names.hidden = true;
    sync();
    btn.addEventListener("click", function () {
      if (!canPost) {
        toast("登录后可以点赞");
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
    wrap.appendChild(count);
    wrap.appendChild(names);
    return wrap;
  }

  function markFreshCard(node, id) {
    if (!freshTargets[String(id)]) return;
    node.classList.add("is-fresh");
    node.addEventListener(
      "mouseenter",
      function () {
        node.classList.remove("is-fresh");
        updateJumpButton();
        if (!canPost) return;
        api("/api/site/notifications/seen", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ module: "messages", target_id: id }),
        }).catch(function () {});
      },
      { once: true }
    );
  }

  function ensureJumpButton() {
    if (jumpBtn) return jumpBtn;
    jumpBtn = el("button", "mg-jump-btn", "↓");
    jumpBtn.type = "button";
    jumpBtn.title = "跳到有提醒的留言";
    jumpBtn.setAttribute("aria-label", "跳到有提醒的留言");
    jumpBtn.hidden = true;
    jumpBtn.addEventListener("click", function () {
      var target = freshBelowNode();
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    document.body.appendChild(jumpBtn);
    return jumpBtn;
  }

  function freshNodes() {
    return Array.prototype.slice.call(
      document.querySelectorAll(".mg-item.is-fresh, .mg-reply.is-fresh")
    );
  }

  function freshBelowNode() {
    return (
      freshNodes().filter(function (node) {
        return node.getBoundingClientRect().top > window.innerHeight - 80;
      })[0] || null
    );
  }

  function updateJumpButton() {
    var btn = ensureJumpButton();
    btn.hidden = !freshBelowNode();
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

  function buildMessage(message) {
    var item = el("article", "mg-item " + (message.can_save ? "can-save" : "no-save"));
    markFreshCard(item, message.id);
    var head = el("div", "mg-item-head");
    head.appendChild(el("span", "mg-nick", message.nickname || "匿名"));
    head.appendChild(el("span", "mg-time", formatTime(message.created_at)));
    if (message.region) {
      head.appendChild(el("span", "mg-region", "IP 属地：" + message.region));
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
    var deleteBtn = null;
    if (canPost) {
      var actions = el("div", "mg-item-actions");
      var replyBtn = null;
      if (message.can_reply) {
        replyBtn = el("button", "mg-link-btn", "回复");
        replyBtn.type = "button";
        actions.append(replyBtn);
      }
      if (message.status === "approved") {
        var reportBtn = el("button", "mg-link-btn", "举报");
        reportBtn.type = "button";
        reportBtn.setAttribute("data-report-type", "message");
        reportBtn.setAttribute("data-report-key", message.id);
        reportBtn.setAttribute("data-report-title", "留言：" + (message.content || "").slice(0, 40));
        reportBtn.setAttribute("data-report-login", "1");
        actions.append(reportBtn);
      }
      if (message.can_delete) {
        deleteBtn = el("button", "mg-link-btn is-danger", "删除");
        deleteBtn.type = "button";
        actions.append(deleteBtn);
      }
      item.appendChild(actions);
      if (replyBtn) {
        rootForm = buildReplyForm(
          message.id,
          "回复 " + (message.nickname || "这条留言") + "…"
        );
        replyBtn.addEventListener("click", function () {
          rootForm.hidden = !rootForm.hidden;
          if (!rootForm.hidden) {
            var area = rootForm.querySelector("textarea");
            if (area) area.focus();
          }
        });
      }
    }
    (message.replies || []).forEach(function (reply) {
      var row = el("div", "mg-reply " + (reply.can_save ? "can-save" : "no-save"));
      markFreshCard(row, reply.id);
      var replyHead = el("div", "mg-item-head");
      replyHead.appendChild(el("span", "mg-nick", reply.nickname || "匿名"));
      if (Number(reply.parent_id) !== Number(message.id)) {
        replyHead.appendChild(
          el("span", "mg-reply-to", "回复 @" + (reply.reply_to || "某人"))
        );
      }
      replyHead.appendChild(el("span", "mg-time", formatTime(reply.created_at)));
      if (reply.region) {
        replyHead.appendChild(el("span", "mg-region", "IP 属地：" + reply.region));
      }
      row.appendChild(replyHead);
      if (reply.content) {
        row.appendChild(el("p", "mg-reply-text", reply.content));
      }
      var replyFiles = reply.files || [];
      if (replyFiles.length) {
        row.appendChild(buildFiles(replyFiles));
      }
      row.appendChild(buildLikeControl("message", reply));
      if (canPost) {
        var replyActions = el("div", "mg-item-actions");
        var subReplyBtn = el("button", "mg-link-btn", "回复");
        subReplyBtn.type = "button";
        replyActions.appendChild(subReplyBtn);
        row.appendChild(replyActions);
        var subForm = buildReplyForm(
          reply.id,
          "回复 " + (reply.nickname || "这条回复") + "…"
        );
        subReplyBtn.addEventListener("click", function () {
          subForm.hidden = !subForm.hidden;
          if (!subForm.hidden) {
            var area = subForm.querySelector("textarea");
            if (area) area.focus();
          }
        });
        row.appendChild(subForm);
      }
      repliesBox.appendChild(row);
    });

    if (deleteBtn) {
      deleteBtn.addEventListener("click", function () {
        var hint = (message.replies || []).length ? "这条留言下面的回复也会一起删除。" : "删除后无法恢复。";
        if (!window.confirm("确认删除这条留言？\n" + hint)) return;
        api("/api/site/messages/" + message.id, { method: "DELETE" }).then(function () {
          toast("已删除");
          return loadMessages();
        }).catch(function (err) {
          toast(err.message);
        });
      });
    }

    item.appendChild(repliesBox);
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
      if (payload.requires_login) {
        latestMessageRows = [];
        $("messageCount").textContent = "";
        list.innerHTML = "";
        var locked = el("div", "mg-locked");
        locked.appendChild(el("i", "mg-locked-icon", "🔒"));
        locked.appendChild(el("strong", "", "登录后查看留言"));
        locked.appendChild(el("p", "", "留言内容仅向经管理员审核通过的登录账号开放。"));
        var login = el("a", "mg-btn mg-btn-primary", "前往登录");
        login.href = "/login?next=" + encodeURIComponent("/messages");
        locked.appendChild(login);
        list.appendChild(locked);
        return;
      }
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
  var FILTER_VALUES = ["all", "mine", "liked", "replied"];
  var FILTER_EMPTY_TEXT = {
    mine: "你还没有发表过留言。",
    liked: "还没有你点赞过的留言。",
    replied: "还没有你评论过的留言。",
  };
  var currentMessageFilter = "all";
  var latestMessageRows = [];

  function messageEmptyText() {
    if (currentMessageFilter !== "all") {
      return (
        FILTER_EMPTY_TEXT[currentMessageFilter] ||
        "没有符合条件的留言。"
      );
    }
    return canPost ? "还没有留言，来说点什么吧。" : "登录后查看留言。";
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
    var filterBox = $("messageFilters");
    if (filterBox) {
      filterBox.querySelectorAll("[data-mg-filter]").forEach(function (node) {
        node.classList.toggle(
          "is-active",
          node.getAttribute("data-mg-filter") === value
        );
      });
    }
    var url = new URL(window.location.href);
    if (value === "all") url.searchParams.delete("filter");
    else url.searchParams.set("filter", value);
    history.replaceState(null, "", url.toString());
  }

  function initMessageFilters() {
    var filterBox = $("messageFilters");
    if (!filterBox || !canPost) return;
    filterBox.hidden = false;
    filterBox.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-mg-filter]");
      if (!btn) return;
      var value = btn.getAttribute("data-mg-filter");
      if (value === currentMessageFilter) return;
      setMessageFilter(value);
      renderRows();
    });
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
    $("messageCount").textContent = rows.length ? "共 " + total + " 条" : "";
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
  $("msgShowRegion").checked = regionPreference();
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
  if (fileViewer) {
    fileViewer.addEventListener("click", function (event) {
      if (event.target === fileViewer) closeFileViewer();
    });
    fileViewer.addEventListener("contextmenu", function (event) {
      event.preventDefault();
    });
  }
  var fileViewerClose = $("fileViewerClose");
  if (fileViewerClose) {
    fileViewerClose.addEventListener("click", closeFileViewer);
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeFileViewer();
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
