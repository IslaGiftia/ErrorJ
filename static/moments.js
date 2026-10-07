(function () {
  "use strict";

  var MAX_IMAGES = 9;
  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  var MAX_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var REGION_KEY = "errorShowRegion";

  var pendingImages = [];
  var toastTimer = null;

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
        if (!response.ok) throw new Error((data && data.error) || "请求失败：" + response.status);
        return data;
      });
    });
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

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function extensionOf(name) {
    var index = String(name || "").lastIndexOf(".");
    return index < 0 ? "" : String(name).slice(index).toLowerCase();
  }

  function formatTime(text) {
    var value = String(text || "");
    var match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!match) return value;
    var then = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]));
    var seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
    var stamp = match[1] + "-" + match[2] + "-" + match[3] + " " + match[4] + ":" + match[5];
    if (seconds < 60) return "刚刚";
    if (seconds < 3600) return Math.round(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.round(seconds / 3600) + " 小时前";
    if (seconds < 86400 * 7) return Math.round(seconds / 86400) + " 天前";
    return stamp;
  }

  function formatStamp(text) {
    var match = String(text || "").match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    return match
      ? match[1] + "-" + match[2] + "-" + match[3] + " " + match[4] + ":" + match[5]
      : String(text || "");
  }

  function hasTag(moment, tag) {
    return String((moment && moment.tags) || "")
      .split(/[,，]/)
      .map(function (item) { return item.trim(); })
      .indexOf(tag) >= 0;
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
        reject(new Error("读取图片失败：" + file.name));
      };
      reader.readAsDataURL(file);
    });
  }

  // ---------- 配图选择 ----------
  function totalPendingBytes() {
    return pendingImages.reduce(function (sum, file) {
      return sum + file.size;
    }, 0);
  }

  function addImages(fileList) {
    var incoming = Array.prototype.slice.call(fileList || []);
    if (!incoming.length) return;
    for (var i = 0; i < incoming.length; i += 1) {
      var file = incoming[i];
      if (pendingImages.length >= MAX_IMAGES) {
        toast("最多 " + MAX_IMAGES + " 张图片。");
        break;
      }
      if (IMAGE_EXTENSIONS.indexOf(extensionOf(file.name)) < 0 && file.type.indexOf("image/") !== 0) {
        toast("只支持图片：" + file.name);
        continue;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        toast("单张图片不能超过 5MB：" + file.name);
        continue;
      }
      if (totalPendingBytes() + file.size > MAX_TOTAL_BYTES) {
        toast("图片总大小不能超过 15MB。");
        break;
      }
      pendingImages.push(file);
    }
    renderPending();
  }

  function renderPending() {
    var list = $("pendingList");
    list.innerHTML = "";
    pendingImages.forEach(function (file, index) {
      var item = document.createElement("li");
      var image = document.createElement("img");
      image.src = URL.createObjectURL(file);
      image.alt = file.name;
      image.addEventListener("load", function () {
        URL.revokeObjectURL(image.src);
      });
      item.appendChild(image);
      var remove = el("button", "", "×");
      remove.type = "button";
      remove.title = "移除";
      remove.addEventListener("click", function () {
        pendingImages.splice(index, 1);
        renderPending();
      });
      item.appendChild(remove);
      list.appendChild(item);
    });
    var hint = $("imageHint");
    if (pendingImages.length) {
      hint.textContent = "已选 " + pendingImages.length + " 张，共 " + (totalPendingBytes() / 1024 / 1024).toFixed(1) + " MB";
    } else {
      hint.textContent = "最多 9 张，单张 5MB";
    }
  }

  $("pickImageBtn").addEventListener("click", function () {
    $("imageInput").click();
  });

  $("imageInput").addEventListener("change", function () {
    addImages($("imageInput").files);
    $("imageInput").value = "";
  });

  $("momentContent").addEventListener("paste", function (event) {
    var pasted = (event.clipboardData && event.clipboardData.files) || [];
    var images = Array.prototype.slice.call(pasted).filter(function (file) {
      return file.type.indexOf("image/") === 0;
    });
    if (images.length) {
      event.preventDefault();
      addImages(images);
    }
  });

  // ---------- 发布 ----------
  // 带配图时按钮内显示进度，上传中再点一次按钮 = 取消（已选图片保留）。
  var publishBusy = { active: false, canceled: false, abort: null, fill: null };

  function publishFill() {
    if (!publishBusy.fill) {
      publishBusy.fill = ErrorProgress.button($("submitBtn"), {
        onCancel: function () {
          publishBusy.canceled = true;
          if (publishBusy.abort) publishBusy.abort();
        },
      });
    }
    return publishBusy.fill;
  }

  $("momentForm").addEventListener("submit", function (event) {
    event.preventDefault();
    if (publishBusy.active) return;
    var content = $("momentContent").value.trim();
    if (!content && !pendingImages.length) {
      toast("写点什么，或者配张图吧。");
      return;
    }
    var button = $("submitBtn");
    var queued = pendingImages.slice();
    var withImages = queued.length > 0;
    var fill = withImages ? publishFill() : null;
    publishBusy.active = true;
    publishBusy.canceled = false;
    publishBusy.abort = null;
    if (withImages) {
      fill.busy("读取图片…");
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
    ).then(function (images) {
      var payload = {
        content: content,
        tags: $("momentTags").value.trim(),
        images: images,
        show_region: $("momentShowRegion").checked,
      };
      if (!withImages) {
        return api("/api/moments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      if (publishBusy.canceled) throw new Error("已取消发布");
      var task = ErrorProgress.upload("/api/moments", {
        payload: payload,
        onProgress: function (ratio) {
          fill.set(ratio, "取消发布 " + ErrorProgress.percentText(ratio));
        },
        onUploaded: function () {
          fill.busy("发布中…");
        },
      });
      publishBusy.abort = task.abort;
      return task.promise;
    }).then(function () {
      rememberRegionPreference($("momentShowRegion").checked);
      $("momentContent").value = "";
      $("momentTags").value = "";
      pendingImages = [];
      renderPending();
      toast("已发布");
      return loadMoments();
    }).catch(function (err) {
      if (publishBusy.canceled || ErrorProgress.isAborted(err)) {
        toast("已取消发布，图片还在，可以直接重试");
        return;
      }
      toast(err.message);
    }).then(function () {
      publishBusy.active = false;
      publishBusy.abort = null;
      if (fill) fill.reset();
      button.removeAttribute("title");
      button.disabled = false;
    });
  });

  // ---------- 列表 ----------
  function openImageViewer(file) {
    var viewer = $("momentViewer");
    var body = $("momentViewerBody");
    var title = $("momentViewerTitle");
    if (!viewer || !body) return;
    if (title) title.textContent = file.file_name || "查看图片";
    body.innerHTML = "";
    var image = document.createElement("img");
    image.src = "/site-files/" + file.file_path;
    image.alt = file.file_name || "";
    image.draggable = false;
    body.appendChild(image);
    viewer.hidden = false;
  }

  function closeImageViewer() {
    var viewer = $("momentViewer");
    var body = $("momentViewerBody");
    if (viewer) viewer.hidden = true;
    if (body) body.innerHTML = "";
  }

  function buildImages(files, canSave) {
    var wrap = el("div", "mo-images" + (files.length === 1 ? " is-single" : ""));
    files.forEach(function (file) {
      var thumb = el("button", "mo-thumb " + (canSave ? "can-save" : "no-save"));
      thumb.type = "button";
      thumb.title = canSave ? file.file_name : file.file_name + "（仅可查看）";
      var image = document.createElement("img");
      image.src = "/site-files/" + file.file_path;
      image.alt = file.file_name;
      image.loading = "lazy";
      image.draggable = false;
      thumb.appendChild(image);
      thumb.appendChild(el("span", "mo-media-guard", ""));
      thumb.addEventListener("click", function () {
        openImageViewer(file);
      });
      wrap.appendChild(thumb);
    });
    return wrap;
  }

  function buildMoment(moment) {
    var item = el("article", "mo-card mo-item " + (moment.can_save ? "can-save" : "no-save"));
    var avatar = document.createElement("img");
    avatar.className = "mo-avatar";
    avatar.src = "/static/site/error-chan-favicon.png?v=3";
    avatar.alt = "Error酱";
    item.appendChild(avatar);

    var body = el("div", "mo-item-body");
    var head = el("div", "mo-item-head");
    head.appendChild(el("span", "mo-nick", "Error酱"));
    if (moment.pinned) head.appendChild(el("span", "mo-pin-badge", "置顶"));
    head.appendChild(
      el(
        "span",
        "mo-time",
        hasTag(moment, "更新日志") ? formatStamp(moment.created_at) : formatTime(moment.created_at)
      )
    );
    if (moment.region) {
      head.appendChild(el("span", "mo-region", "IP 属地：" + moment.region));
    }
    body.appendChild(head);

    if (moment.content) body.appendChild(el("p", "mo-text", moment.content));

    var files = moment.files || [];
    if (files.length) {
      body.appendChild(buildImages(files, Boolean(moment.can_save)));
    }

    if (moment.tags) {
      var tagWrap = el("div", "mo-tags");
      String(moment.tags).split(",").forEach(function (tag) {
        var text = tag.trim();
        if (text) tagWrap.appendChild(el("span", "mo-tag", text));
      });
      if (tagWrap.childNodes.length) body.appendChild(tagWrap);
    }

    item.appendChild(body);

    if (moment.can_manage) {
      var actions = el("div", "mo-actions");
      var pinBtn = el("button", "mo-link-btn", moment.pinned ? "取消置顶" : "置顶");
      var editBtn = el("button", "mo-link-btn", "编辑");
      var deleteBtn = el("button", "mo-link-btn is-danger", "删除");
      pinBtn.type = "button";
      editBtn.type = "button";
      deleteBtn.type = "button";
      actions.append(pinBtn, editBtn, deleteBtn);
      body.appendChild(actions);

      pinBtn.addEventListener("click", function () {
        pinBtn.disabled = true;
        api("/api/moments/" + moment.id, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pinned: !moment.pinned }),
        }).then(function () {
          return loadMoments();
        }).catch(function (err) {
          toast(err.message);
        }).then(function () {
          pinBtn.disabled = false;
        });
      });

      editBtn.addEventListener("click", function () {
        if (body.querySelector(".mo-edit")) return;
        var box = el("div", "mo-edit");
        var area = document.createElement("textarea");
        area.maxLength = 2000;
        area.value = moment.content || "";
        var tagInput = document.createElement("input");
        tagInput.className = "mo-tag-input";
        tagInput.maxLength = 200;
        tagInput.value = moment.tags || "";
        tagInput.placeholder = "标签（逗号分隔）";
        tagInput.style.cssText = "width:100%;margin-top:8px;padding:8px 12px;border-radius:8px;border:1px solid var(--mo-border);background:var(--mo-bg);color:var(--mo-text);font:inherit;font-size:13px;";
        var row = el("div", "mo-edit-actions");
        var cancel = el("button", "mo-btn mo-btn-ghost", "取消");
        var save = el("button", "mo-btn mo-btn-primary", "保存");
        cancel.type = "button";
        save.type = "button";
        row.append(cancel, save);
        box.append(area, tagInput, row);
        body.insertBefore(box, actions);
        area.focus();

        cancel.addEventListener("click", function () {
          box.remove();
        });
        save.addEventListener("click", function () {
          save.disabled = true;
          api("/api/moments/" + moment.id, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: area.value, tags: tagInput.value }),
          }).then(function () {
            toast("已保存");
            return loadMoments();
          }).catch(function (err) {
            toast(err.message);
            save.disabled = false;
          });
        });
      });

      deleteBtn.addEventListener("click", function () {
        if (!window.confirm("删除这条说说？配图也会一起删掉。")) return;
        api("/api/moments/" + moment.id, { method: "DELETE" }).then(function () {
          toast("已删除");
          return loadMoments();
        }).catch(function (err) {
          toast(err.message);
        });
      });
    }

    return item;
  }

  function loadMoments() {
    var list = $("momentList");
    return api("/api/moments").then(function (rows) {
      list.innerHTML = "";
      $("momentCount").textContent = rows.length ? "共 " + rows.length + " 条" : "";
      if (!rows.length) {
        list.appendChild(el("div", "mo-empty", "还没有记录，写第一条吧。"));
        return;
      }
      rows.forEach(function (row) {
        list.appendChild(buildMoment(row));
      });
      refreshIcons();
    }).catch(function (err) {
      list.innerHTML = "";
      list.appendChild(el("div", "mo-empty", "加载失败：" + err.message));
    });
  }

  renderPending();
  $("momentShowRegion").checked = regionPreference();
  refreshIcons();

  var momentList = $("momentList");
  if (momentList) {
    momentList.addEventListener("contextmenu", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      if (target.closest(".can-save") || target.closest("input, textarea")) return;
      event.preventDefault();
    });
    momentList.addEventListener("dragstart", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest("img")) {
        event.preventDefault();
      }
    });
    momentList.addEventListener("copy", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      if (target.closest(".can-save") || target.closest("input, textarea")) return;
      event.preventDefault();
    });
  }

  var imageViewer = $("momentViewer");
  if (imageViewer) {
    imageViewer.addEventListener("click", function (event) {
      if (event.target === imageViewer) closeImageViewer();
    });
    imageViewer.addEventListener("contextmenu", function (event) {
      event.preventDefault();
    });
  }
  var imageViewerClose = $("momentViewerClose");
  if (imageViewerClose) {
    imageViewerClose.addEventListener("click", closeImageViewer);
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeImageViewer();
  });

  api("/api/auth/status").then(function (status) {
    var canManage = Boolean(status.admin);
    $("momentForm").hidden = !canManage;
    return loadMoments();
  }).catch(function () {
    $("momentForm").hidden = true;
    return loadMoments();
  });
})();
