(function () {
  "use strict";

  var MAX_IMAGES = 9;
  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  var MAX_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var REGION_KEY = "errorShowRegion";

  var pendingImages = [];
  var toastTimer = null;
  var canInteract = false;
  var viewerLikeName = "";
  var shareAudio = null;
  var freshTargets = {};
  var jumpBtn = null;
  var jumpFrame = null;

  function imageLimitLabel() {
    return window.ErrorUploadLimits
      ? window.ErrorUploadLimits.label(MAX_IMAGE_BYTES)
      : "5MB";
  }

  function imageHintText() {
    return "最多 " + MAX_IMAGES + " 张，单张 " + imageLimitLabel();
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var limits = window.ErrorUploadLimits.get("moment_image");
    MAX_IMAGES = Number(limits.max_count) || MAX_IMAGES;
    MAX_IMAGE_BYTES = Number(limits.max_file_bytes) || MAX_IMAGE_BYTES;
    MAX_TOTAL_BYTES = Number(limits.max_total_bytes) || MAX_TOTAL_BYTES;
    renderPending();
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
        if (!response.ok) throw new Error((data && data.error) || "请求失败：" + response.status);
        return data;
      });
    });
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
        toast("单张图片不能超过 " + imageLimitLabel() + "：" + file.name);
        continue;
      }
      if (totalPendingBytes() + file.size > MAX_TOTAL_BYTES) {
        toast(
          "图片总大小不能超过 " +
            (window.ErrorUploadLimits
              ? window.ErrorUploadLimits.label(MAX_TOTAL_BYTES)
              : "15MB") +
            "。"
        );
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
      hint.textContent = imageHintText();
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

  function markFreshCard(node, id) {
    if (!freshTargets[String(id)]) return;
    node.classList.add("is-fresh");
    node.addEventListener(
      "mouseenter",
      function () {
        node.classList.remove("is-fresh");
        updateJumpButton();
        if (!canInteract) return;
        api("/api/site/notifications/seen", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ module: "moments", target_id: id }),
        }).catch(function () {});
      },
      { once: true }
    );
  }

  function ensureJumpButton() {
    if (jumpBtn) return jumpBtn;
    jumpBtn = el("button", "mo-jump-btn", "↓");
    jumpBtn.type = "button";
    jumpBtn.title = "跳到有提醒的动态";
    jumpBtn.setAttribute("aria-label", "跳到有提醒的动态");
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
      document.querySelectorAll(".mo-item.is-fresh")
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

  function buildShareCard(share) {
    var info = el("div", "mo-share-info");
    info.appendChild(el("span", "mo-share-label", share.label || "内容"));
    info.appendChild(el("strong", "mo-share-title", share.title || ""));
    if (share.subtitle) {
      info.appendChild(el("span", "mo-share-subtitle", share.subtitle));
    }
    if (!share.available) {
      var missing = el("div", "mo-share is-missing");
      missing.appendChild(el("span", "mo-share-icon", "×"));
      info.textContent = "";
      info.appendChild(el("span", "mo-share-label", share.label || "内容"));
      info.appendChild(el("strong", "mo-share-title", "内容已失效"));
      missing.appendChild(info);
      return missing;
    }
    if (share.type === "music") {
      var card = el("div", "mo-share is-music");
      var cover = el("button", "mo-share-cover");
      cover.type = "button";
      cover.setAttribute("aria-label", "播放");
      if (share.cover_url) {
        var image = document.createElement("img");
        image.src = share.cover_url;
        image.alt = share.title || "";
        image.loading = "lazy";
        cover.appendChild(image);
      } else {
        cover.appendChild(el("span", "mo-share-placeholder", "♪"));
      }
      var play = el("button", "mo-share-play", "▶");
      play.type = "button";
      play.setAttribute("aria-label", "播放");
      var audio = new Audio();
      audio.preload = "none";
      audio.src = share.url;
      function sync(playing) {
        play.textContent = playing ? "❚❚" : "▶";
        cover.setAttribute("aria-label", playing ? "暂停" : "播放");
        play.setAttribute("aria-label", playing ? "暂停" : "播放");
        card.classList.toggle("is-playing", playing);
      }
      audio.addEventListener("play", function () {
        sync(true);
      });
      audio.addEventListener("pause", function () {
        sync(false);
      });
      audio.addEventListener("ended", function () {
        sync(false);
      });
      function togglePlayback() {
        if (!audio.paused) {
          audio.pause();
          return;
        }
        if (shareAudio && shareAudio !== audio) {
          shareAudio.pause();
        }
        shareAudio = audio;
        audio.play().catch(function () {
          toast("播放失败，稍后再试");
        });
      }
      cover.addEventListener("click", togglePlayback);
      play.addEventListener("click", togglePlayback);
      card.append(cover, info, play);
      return card;
    }
    var linkCard = el("button", "mo-share is-link");
    linkCard.type = "button";
    linkCard.appendChild(
      el("span", "mo-share-icon", share.type === "book" ? "📖" : "📝")
    );
    linkCard.appendChild(info);
    linkCard.appendChild(el("span", "mo-share-open", "阅读"));
    linkCard.addEventListener("click", function () {
      if (!canInteract) {
        toast("登录后可以阅读");
        return;
      }
      window.open(share.url, "_blank", "noopener");
    });
    return linkCard;
  }

  function likeNamesText(target) {
    var users = (target.like_users || []).slice();
    if (!users.length) return "";
    var shown = users.slice(0, 3).join("、");
    return users.length > 3 ? shown + " 等 " + users.length + " 人" : shown;
  }

  function bindLikeControl(wrap, btn, count, names, targetType, target) {
    var namesEl = names;
    function sync() {
      btn.classList.toggle("is-liked", Boolean(target.liked));
      btn.title = target.liked ? "取消点赞" : "点赞";
      count.textContent = String(target.like_count || 0);
      count.hidden = !target.like_count && !target.liked;
      var text = likeNamesText(target);
      namesEl.hidden = !text;
      namesEl.textContent = text;
    }
    sync();
    btn.addEventListener("click", function () {
      if (!canInteract) {
        toast("登录后可以点赞");
        return;
      }
      btn.disabled = true;
      api("/api/site/likes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: targetType, target_id: target.id }),
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
    return sync;
  }

  function buildLikeRow(targetType, target) {
    var wrap = el("div", "mo-like");
    var btn = el("button", "mo-like-btn", "♥");
    var count = el("span", "mo-like-count", "");
    var names = el("span", "mo-like-names", "");
    btn.type = "button";
    wrap.append(btn, count, names);
    bindLikeControl(wrap, btn, count, names, targetType, target);
    return wrap;
  }

  function buildMomentLike(moment) {
    return buildLikeRow("moment", moment);
  }

  function buildCommentForm(moment, parentId, placeholder) {
    var form = el("form", "mo-comment-form");
    var area = document.createElement("textarea");
    area.maxLength = 500;
    area.rows = 1;
    area.placeholder = placeholder || "写评论…";
    var submit = el("button", "mo-btn mo-btn-primary mo-comment-submit", "发送");
    submit.type = "submit";
    form.appendChild(area);
    form.appendChild(submit);
    if (parentId) form.hidden = true;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var text = area.value.trim();
      if (!text) return;
      submit.disabled = true;
      api("/api/moments/" + moment.id + "/comments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text, parent_id: parentId || null }),
      }).then(function () {
        toast(parentId ? "回复已发布" : "评论已发布");
        return loadMoments();
      }).catch(function (err) {
        toast(err.message || "发布失败");
        submit.disabled = false;
      });
    });
    return form;
  }

  function buildCommentNode(moment, comment, byParent) {
    var row = el("div", "mo-comment" + (comment.parent_id ? " is-reply" : ""));
    var head = el("div", "mo-comment-head");
    head.appendChild(el("span", "mo-comment-actor", comment.actor || "匿名"));
    head.appendChild(el("span", "mo-comment-time", formatTime(comment.created_at)));
    row.appendChild(head);
    row.appendChild(el("p", "mo-comment-text", comment.content));
    row.appendChild(buildLikeRow("comment", comment));
    var actions = el("div", "mo-comment-actions");
    if (comment.can_delete) {
      var deleteBtn = el("button", "mo-link-btn is-danger", "删除");
      deleteBtn.type = "button";
      deleteBtn.addEventListener("click", function () {
        if (!window.confirm("删除这条评论？下面的回复也会一起删除。")) return;
        api("/api/site/moment-comments/" + comment.id, { method: "DELETE" })
          .then(function () {
            toast("评论已删除");
            return loadMoments();
          })
          .catch(function (err) {
            toast(err.message || "删除失败");
          });
      });
      actions.appendChild(deleteBtn);
    }
    row.appendChild(actions);
    if (canInteract && !comment.parent_id) {
      var replyBtn = el("button", "mo-link-btn", "回复");
      replyBtn.type = "button";
      actions.insertBefore(replyBtn, actions.firstChild);
      var replyForm = buildCommentForm(
        moment,
        comment.id,
        "回复 " + (comment.actor || "这条评论") + "…"
      );
      replyBtn.addEventListener("click", function () {
        replyForm.hidden = !replyForm.hidden;
        if (!replyForm.hidden) replyForm.querySelector("textarea").focus();
      });
      row.appendChild(replyForm);
    }
    (byParent[comment.id] || []).forEach(function (child) {
      row.appendChild(buildCommentNode(moment, child, byParent));
    });
    return row;
  }

  function buildComments(moment) {
    var comments = moment.comments || [];
    var box = el("div", "mo-comments");
    var byParent = {};
    comments.forEach(function (comment) {
      if (comment.parent_id) {
        byParent[comment.parent_id] = byParent[comment.parent_id] || [];
        byParent[comment.parent_id].push(comment);
      }
    });
    if (comments.length) {
      var list = el("div", "mo-comment-list");
      comments
        .filter(function (comment) { return !comment.parent_id; })
        .forEach(function (comment) {
          list.appendChild(buildCommentNode(moment, comment, byParent));
        });
      box.appendChild(list);
    }
    if (canInteract) {
      box.appendChild(buildCommentForm(moment, null, "写评论…"));
    }
    return box;
  }

  function buildMoment(moment) {
    var item = el("article", "mo-card mo-item " + (moment.can_save ? "can-save" : "no-save"));
    markFreshCard(item, moment.id);
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

    if (moment.share) {
      body.appendChild(buildShareCard(moment.share));
    }

    if (moment.tags) {
      var tagWrap = el("div", "mo-tags");
      String(moment.tags).split(",").forEach(function (tag) {
        var text = tag.trim();
        if (text) tagWrap.appendChild(el("span", "mo-tag", text));
      });
      if (tagWrap.childNodes.length) body.appendChild(tagWrap);
    }

    body.appendChild(buildMomentLike(moment));
    body.appendChild(buildComments(moment));

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
    var targetsRequest = canInteract
      ? api("/api/site/moments/unread")
          .then(function (data) {
            return (data && data.targets) || [];
          })
          .catch(function () {
            return [];
          })
      : Promise.resolve([]);
    return Promise.all([api("/api/moments"), targetsRequest]).then(function (result) {
      var rows = result[0];
      freshTargets = {};
      (result[1] || []).forEach(function (id) {
        freshTargets[String(id)] = true;
      });
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
      updateJumpButton();
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
    canInteract = Boolean(status.authenticated);
    viewerLikeName = status.owner
      ? "管理员"
      : String(status.username || status.nickname || "");
    $("momentForm").hidden = !canManage;
    if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);
    return loadMoments();
  }).catch(function () {
    $("momentForm").hidden = true;
    return loadMoments();
  });
})();
