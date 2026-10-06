(function () {
  "use strict";

  var MAX_FILES = 3;
  var MAX_FILE_BYTES = 5 * 1024 * 1024;
  var MAX_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var FILE_EXTENSIONS = IMAGE_EXTENSIONS.concat([".pdf", ".txt", ".md"]);
  var NICKNAME_KEY = "errorMessageNickname";

  var pendingFiles = [];
  var toastTimer = null;
  var canPost = false;

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

  function nicknameValue(inputId) {
    var input = $(inputId);
    return (input && input.value.trim()) || "匿名";
  }

  function rememberNickname(value) {
    try {
      localStorage.setItem(NICKNAME_KEY, value);
    } catch (err) {}
  }

  try {
    var savedNickname = localStorage.getItem(NICKNAME_KEY);
    if (savedNickname) $("msgNickname").value = savedNickname;
  } catch (err) {}

  $("messageForm").addEventListener("submit", function (event) {
    event.preventDefault();
    var content = $("msgContent").value.trim();
    if (!content && !pendingFiles.length) {
      toast("写点内容，或者加个附件吧。");
      return;
    }
    var button = $("submitBtn");
    button.disabled = true;
    var queued = pendingFiles.slice();
    Promise.all(
      queued.map(function (file) {
        return fileToBase64(file).then(function (data) {
          return { name: file.name, data_base64: data };
        });
      })
    ).then(function (files) {
      return api("/api/site/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nickname: nicknameValue("msgNickname"),
          content: content,
          files: files,
        }),
      });
    }).then(function (result) {
      rememberNickname(nicknameValue("msgNickname"));
      $("msgContent").value = "";
      pendingFiles = [];
      renderPending();
      toast(
        result && result.pending_review
          ? "留言已发布，附件审核通过后其他人才能看到"
          : "留言已发布"
      );
      return loadMessages();
    }).catch(function (err) {
      toast(err.message);
    }).then(function () {
      button.disabled = false;
    });
  });

  // ---- 列表 ----
  function buildFiles(files) {
    var wrap = el("div", "mg-files");
    files.forEach(function (file) {
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
      if (file.is_image) {
        var thumbLink = el("a", "mg-thumb");
        thumbLink.href = url;
        thumbLink.target = "_blank";
        thumbLink.rel = "noopener";
        thumbLink.title = file.pending
          ? file.file_name + "（审核中，仅你和管理员可见）"
          : file.file_name;
        if (file.pending) thumbLink.classList.add("is-pending");
        var image = document.createElement("img");
        image.src = url;
        image.alt = file.file_name;
        image.loading = "lazy";
        thumbLink.appendChild(image);
        wrap.appendChild(thumbLink);
        return;
      }
      var link = el("a", "mg-file");
      link.href = url;
      link.download = file.file_name;
      link.rel = "noopener";
      if (file.pending) link.classList.add("mg-file-pending");
      var icon = document.createElement("i");
      icon.setAttribute("data-lucide", "file");
      link.appendChild(icon);
      link.appendChild(el("span", "mg-file-name", file.file_name));
      if (file.pending) {
        link.appendChild(el("span", "mg-file-size", "审核中"));
      }
      link.appendChild(el("span", "mg-file-size", formatSize(file.file_size)));
      wrap.appendChild(link);
    });
    return wrap;
  }

  function buildReplyForm(rootId) {
    var form = el("form", "mg-reply-form");
    form.hidden = true;

    var nickField = el("div", "mg-field");
    nickField.appendChild(el("label", "", "昵称"));
    var nickInput = document.createElement("input");
    nickInput.maxLength = 30;
    nickInput.value = (function () {
      try {
        return localStorage.getItem(NICKNAME_KEY) || "匿名";
      } catch (err) {
        return "匿名";
      }
    })();
    nickField.appendChild(nickInput);

    var textField = el("div", "mg-field");
    textField.appendChild(el("label", "", "回复"));
    var textArea = document.createElement("textarea");
    textArea.maxLength = 1000;
    textArea.placeholder = "回复一下…";
    textField.appendChild(textArea);

    var row = el("div", "mg-compose-row");
    var cancelBtn = el("button", "mg-btn mg-btn-ghost", "取消");
    cancelBtn.type = "button";
    var sendBtn = el("button", "mg-btn mg-btn-primary", "提交回复");
    sendBtn.type = "submit";
    row.append(cancelBtn, sendBtn);

    form.append(nickField, textField, row);

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
          nickname: nickInput.value.trim() || "匿名",
          content: content,
          parent_id: rootId,
        }),
      }).then(function () {
        rememberNickname(nickInput.value.trim() || "匿名");
        $("msgNickname").value = nickInput.value.trim() || "匿名";
        toast("回复已发布");
        return loadMessages();
      }).catch(function (err) {
        toast(err.message);
      }).then(function () {
        sendBtn.disabled = false;
      });
    });

    return form;
  }

  function buildMessage(message) {
    var item = el("article", "mg-item");
    var head = el("div", "mg-item-head");
    head.appendChild(el("span", "mg-nick", message.nickname || "匿名"));
    head.appendChild(el("span", "mg-time", formatTime(message.created_at)));
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
      var row = el("div", "mg-reply");
      var replyHead = el("div", "mg-item-head");
      replyHead.appendChild(el("span", "mg-nick", reply.nickname || "匿名"));
      replyHead.appendChild(el("span", "mg-time", formatTime(reply.created_at)));
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
      rows.forEach(function (row) {
        total += 1 + (row.replies || []).length;
      });
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
  refreshIcons();
  api("/api/auth/status").then(function (status) {
    canPost = Boolean(status.authenticated);
    $("messageForm").hidden = !canPost;
    $("messageLoginHint").hidden = canPost;
    return loadMessages();
  }).catch(function () {
    canPost = false;
    $("messageForm").hidden = true;
    $("messageLoginHint").hidden = false;
    return loadMessages();
  });
})();
