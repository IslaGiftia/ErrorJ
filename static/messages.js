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
  var dailyRemaining = null;
  var dailyLimit = 0;

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
      return localStorage.getItem(REGION_KEY) !== "0";
    } catch (err) {
      return true;
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
        toast("单个附件不能超过 5MB：" + file.name);
        continue;
      }
      if (totalPendingBytes() + file.size > MAX_TOTAL_BYTES) {
        toast("附件总大小不能超过 15MB。");
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
          ? "留言已发布，附件审核通过后其他人才能看到"
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

  function buildReplyForm(rootId) {
    var form = el("form", "mg-reply-form");
    form.hidden = true;

    var textField = el("div", "mg-field");
    textField.appendChild(el("label", "", "回复"));
    var textArea = document.createElement("textarea");
    textArea.maxLength = 1000;
    textArea.placeholder = "回复一下…";
    textField.appendChild(textArea);

    var regionLabel = el("label", "mg-region-toggle");
    var regionInput = document.createElement("input");
    regionInput.type = "checkbox";
    regionInput.checked = regionPreference();
    regionLabel.append(regionInput, el("span", "", "公开 IP 属地（仅到省份）"));

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
          parent_id: rootId,
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

  function buildMessage(message) {
    var item = el("article", "mg-item " + (message.can_save ? "can-save" : "no-save"));
    var head = el("div", "mg-item-head");
    head.appendChild(el("span", "mg-nick", message.nickname || "匿名"));
    head.appendChild(el("span", "mg-time", formatTime(message.created_at)));
    if (message.region) {
      head.appendChild(el("span", "mg-region", "IP 属地：" + message.region));
    }
    item.appendChild(head);
    if (message.content) {
      item.appendChild(el("p", "mg-text", message.content));
    }
    var files = message.files || [];
    if (files.length) {
      item.appendChild(buildFiles(files));
    }

    var repliesBox = el("div", "mg-replies");
    var replyForm = null;
    if (canPost) {
      var actions = el("div", "mg-item-actions");
      var replyBtn = el("button", "mg-link-btn", "回复");
      replyBtn.type = "button";
      actions.append(replyBtn);
      var deleteBtn = null;
      if (message.can_delete) {
        deleteBtn = el("button", "mg-link-btn is-danger", "删除");
        deleteBtn.type = "button";
        actions.append(deleteBtn);
      }
      item.appendChild(actions);
      replyForm = buildReplyForm(message.id);
    }
    (message.replies || []).forEach(function (reply) {
      var row = el("div", "mg-reply " + (reply.can_save ? "can-save" : "no-save"));
      var replyHead = el("div", "mg-item-head");
      replyHead.appendChild(el("span", "mg-nick", reply.nickname || "匿名"));
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
      repliesBox.appendChild(row);
    });

    if (replyForm) {
      var toggleReply = item.querySelector(".mg-link-btn");
      if (toggleReply) {
        toggleReply.addEventListener("click", function () {
          replyForm.hidden = !replyForm.hidden;
          if (!replyForm.hidden) {
            var area = replyForm.querySelector("textarea");
            if (area) area.focus();
          }
        });
      }
    }

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
    if (replyForm) {
      item.appendChild(replyForm);
    }
    return item;
  }

  function loadMessages() {
    var list = $("messageList");
    return api("/api/site/messages").then(function (rows) {
      list.innerHTML = "";
      var total = 0;
      var newest = 0;
      rows.forEach(function (row) {
        total += 1 + (row.replies || []).length;
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
      $("messageCount").textContent = rows.length ? "共 " + total + " 条" : "";
      if (!rows.length) {
        list.appendChild(
          el("div", "mg-empty", canPost ? "还没有留言，来说点什么吧。" : "还没有留言。")
        );
        return;
      }
      rows.forEach(function (row) {
        list.appendChild(buildMessage(row));
      });
      refreshIcons();
    }).catch(function (err) {
      list.innerHTML = "";
      list.appendChild(el("div", "mg-empty", "加载失败：" + err.message));
    });
  }

  renderPending();
  $("msgShowRegion").checked = regionPreference();
  refreshIcons();

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
    $("messageComposerPanel").hidden = !canPost;
    if (canPost) loadQuota();
    return loadMessages();
  }).catch(function () {
    canPost = false;
    $("messageComposerPanel").hidden = true;
    return loadMessages();
  });
})();
