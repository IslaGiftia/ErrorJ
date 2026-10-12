(function () {
  "use strict";

  var MAX_IMAGES = 9;
  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  var MAX_TOTAL_BYTES = 15 * 1024 * 1024;
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var pendingImages = [];
  var toastTimer = null;
  var canInteract = false;
  var viewerLikeName = "";
  var shareAudio = null;
  var freshTargets = {};
  var jumpFrame = null;
  var lastMomentUnread = null;
  var momentPollBusy = false;

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

  $("imageInput").addEventListener("change", function () {
    addImages($("imageInput").files);
    $("imageInput").value = "";
  });

  // 配图：点击 / 拖到发布框 / 拖文件夹（按动态图片上限取前几张）
  if (window.ErrorDropZone) {
    window.ErrorDropZone.attach($("pickImageBtn"), {
      input: $("imageInput"),
      dropTarget: $("momentForm"),
      accept: ["image/*", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"],
      maxCount: function () {
        return Math.max(1, MAX_IMAGES - pendingImages.length);
      },
      multiple: true,
      pickerId: "errorjiang-moment-image",
      toast: toast
    });
  } else {
    $("pickImageBtn").addEventListener("click", function () {
      $("imageInput").click();
    });
  }

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

  // ---------- 图片：朋友圈九宫格 + 灯箱查看器（同留言页） ----------
  var galleryImages = [];
  var galleryIndex = 0;
  var viewerImg = null;
  var viewerZoomBound = false;

  function viewerImageEl() {
    var stage = $("momentViewerStage");
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

  // 换图 / 关闭时清掉上一张的缩放与滚动
  function resetViewerZoom() {
    var stage = $("momentViewerStage");
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
    var file = galleryImages[galleryIndex];
    if (!image || !file) return;
    resetViewerZoom();
    image.src = "/site-files/" + file.file_path;
    image.alt = file.file_name || "";
    var multiple = galleryImages.length > 1;
    var prev = $("momentViewerPrev");
    var next = $("momentViewerNext");
    var counter = $("momentViewerCounter");
    if (prev) prev.hidden = !multiple;
    if (next) next.hidden = !multiple;
    if (counter) {
      counter.hidden = !multiple;
      counter.textContent = galleryIndex + 1 + " / " + galleryImages.length;
    }
  }

  function openImageViewer(files, index) {
    var images = (files || []).slice();
    var viewer = $("momentViewer");
    if (!viewer || !images.length) return;
    galleryImages = images;
    galleryIndex = Math.max(0, Math.min(Number(index) || 0, images.length - 1));
    viewer.hidden = false;
    renderViewerImage();
    refreshIcons();
  }

  function stepViewerImage(delta) {
    if (galleryImages.length < 2) return;
    galleryIndex = (galleryIndex + delta + galleryImages.length) % galleryImages.length;
    renderViewerImage();
  }

  function closeImageViewer() {
    var viewer = $("momentViewer");
    if (viewer) viewer.hidden = true;
    galleryImages = [];
    galleryIndex = 0;
    resetViewerZoom();
  }

  function buildImages(files, canSave) {
    var count = files.length;
    var cols = count === 1 ? 1 : count <= 4 ? 2 : 3;
    var gallery = el("div", "mo-gallery cols-" + cols);
    var shown = files.slice(0, 9);
    var extra = count - shown.length;
    shown.forEach(function (file, index) {
      var thumb = el("button", "mo-gallery-cell " + (canSave ? "can-save" : "no-save"));
      thumb.type = "button";
      thumb.title = canSave ? file.file_name : file.file_name + "（仅可查看）";
      var image = document.createElement("img");
      image.src = "/site-files/" + file.file_path;
      image.alt = file.file_name;
      image.loading = "lazy";
      image.draggable = false;
      thumb.appendChild(image);
      thumb.appendChild(el("span", "mo-media-guard", ""));
      if (extra > 0 && index === shown.length - 1) {
        thumb.appendChild(el("span", "mo-gallery-more", "+" + extra));
      }
      thumb.addEventListener("click", function () {
        openImageViewer(files, index);
      });
      gallery.appendChild(thumb);
    });
    return gallery;
  }

  /*
   * 新互动提醒（同留言页）：整张卡片方框呼吸，新评论的正文额外高亮闪烁；
   * 右下角不再单独放「↓」按钮，而是复用页面共用的「顶部」按钮——
   * 有未读时切成「↓ 评论 / ↓ 动态」并带呼吸，没有未读时是普通「↑ 顶部」。
   */
  function freshCards() {
    return Array.prototype.slice.call(document.querySelectorAll(".mo-item.is-fresh"));
  }

  // 评论类提醒的目标是「评论 id」，其它（新动态）指向动态本身
  var MOMENT_COMMENT_KINDS = {
    moment_comment: 1,
    comment_reply: 1,
    comment_like: 1,
  };

  function isCommentFresh(id) {
    return Boolean(MOMENT_COMMENT_KINDS[freshTargets[String(id)]]);
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
      card.querySelectorAll(".mo-comment-text.is-new-comment"),
      function (node) {
        node.classList.remove("is-new-comment");
      }
    );
    updateJumpButton();
    if (!canInteract) return;
    ids.forEach(function (id) {
      api("/api/site/notifications/seen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module: "moments", target_id: id }),
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

  // 移动端没有 hover：滚到新评论后把正文的闪烁重放一次（CSS 在触摸设备上只闪 3 次）
  function replayCommentBlink(card) {
    var text = card.querySelector(".mo-comment-text.is-new-comment");
    if (!text) return;
    text.classList.remove("is-new-comment");
    void text.offsetWidth;
    text.classList.add("is-new-comment");
  }

  function popLikeButton(card) {
    var like = card.querySelector(".mo-like-btn");
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
    var kind = card.dataset.freshKind === "comment" ? "comment" : "moment";
    var target = card;
    if (kind === "comment") {
      target = card.querySelector(".mo-comment-text.is-new-comment") || card;
      replayCommentBlink(card);
    } else {
      popLikeButton(card);
    }
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  var lastPendingKey = null;

  function updateJumpButton() {
    var api = backTopApi();
    if (!api) return;
    var card = freshCardBelow();
    var key = card ? card.dataset.freshKind + ":" + card.dataset.freshIds : "";
    if (key === lastPendingKey) return;
    lastPendingKey = key;
    if (card) {
      var isComment = card.dataset.freshKind === "comment";
      api.setPending({
        active: true,
        label: isComment ? "评论" : "动态",
        title: isComment ? "跳到新评论" : "跳到新动态",
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

  function buildShareCard(share) {
    var info = el("div", "mo-share-info");
    /*
     * 歌曲卡只留「歌名 + 歌手」两行，笔记卡也去掉标签那行小字（书籍卡照旧保留）；
     * 去掉之后信息块正好两行，和左侧封面垂直居中。
     */
    var hideLabel = share.type === "music" || share.type === "note";
    if (!hideLabel) {
      info.appendChild(el("span", "mo-share-label", share.label || "内容"));
    }
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
      /*
       * 播放键和歌曲播放页是同一套：同样的实心圆形样式 + morphicons 的 play↔pause 形变。
       * 先把 morph 实例按「播放」建好（不播动画），之后每次切换才有形变；
       * 没有 morphicons 时退回原来的 lucide 图标硬切。
       */
      var play = el("button", "mo-share-play");
      play.innerHTML = '<i data-lucide="play" aria-hidden="true"></i>';
      play.type = "button";
      play.title = "播放";
      play.setAttribute("aria-label", "播放");
      play.setAttribute("data-icon", "play");
      if (window.ErrorMorph) window.ErrorMorph.set(play, "play");
      var audio = new Audio();
      audio.preload = "none";
      audio.src = share.url;
      function sync(playing) {
        var icon = playing ? "pause" : "play";
        if (play.getAttribute("data-icon") !== icon) {
          play.setAttribute("data-icon", icon);
          if (!(window.ErrorMorph && window.ErrorMorph.morph(play, icon))) {
            play.innerHTML = '<i data-lucide="' + icon + '" aria-hidden="true"></i>';
            if (window.lucide) window.lucide.createIcons();
          }
        }
        cover.setAttribute("aria-label", playing ? "暂停" : "播放");
        play.title = playing ? "暂停" : "播放";
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

  function bindLikeControl(btn, names, targetType, target) {
    var namesEl = names;
    function sync() {
      btn.classList.toggle("is-liked", Boolean(target.liked));
      btn.title = target.liked ? "取消点赞" : "点赞";
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
    var btn = el("button", "mo-like-btn");
    var names = el("span", "mo-like-names", "");
    btn.type = "button";
    // 线框大拇指：未赞灰、已赞只换主题色描边；右边跟点赞者用户名
    btn.innerHTML = '<i data-lucide="thumbs-up" aria-hidden="true"></i>';
    wrap.append(btn, names);
    bindLikeControl(btn, names, targetType, target);
    return wrap;
  }

  function buildMomentLike(moment) {
    return buildLikeRow("moment", moment);
  }

  // ---------- 卡片右下角「更多」菜单 ----------
  function closeAllMoreMenus() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".mo-more.is-open"),
      function (node) {
        node.classList.remove("is-open");
        var menu = node.querySelector(".mo-more-menu");
        if (menu) menu.hidden = true;
        var btn = node.querySelector(".mo-more-btn");
        if (btn) btn.setAttribute("aria-expanded", "false");
      }
    );
  }

  function buildMoreMenu(items) {
    var more = el("div", "mo-more");
    var btn = el("button", "mo-more-btn");
    btn.type = "button";
    btn.title = "更多操作";
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "更多操作");
    btn.innerHTML = '<i data-lucide="ellipsis" aria-hidden="true"></i>';
    var menu = el("div", "mo-more-menu");
    menu.hidden = true;
    menu.setAttribute("role", "menu");
    items.forEach(function (item) {
      var node = el(
        "button",
        "mo-more-item" + (item.danger ? " is-danger" : ""),
        item.label
      );
      node.type = "button";
      node.setAttribute("role", "menuitem");
      if (item.report) {
        node.setAttribute("data-report-type", "moment");
        node.setAttribute("data-report-key", item.report.id);
        node.setAttribute(
          "data-report-title",
          "动态：" + String(item.report.content || "").slice(0, 40)
        );
        node.setAttribute("data-report-login", "1");
      }
      node.addEventListener("click", function () {
        closeAllMoreMenus();
        if (item.onPick) item.onPick();
      });
      menu.appendChild(node);
    });
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

  /* 手机上聚焦评论框时把它滚到键盘上方（桌面端浏览器自己会处理） */
  function focusCommentArea(area) {
    if (!window.matchMedia("(max-width: 640px)").matches) return;
    window.setTimeout(function () {
      if (document.activeElement !== area) return;
      var viewportHeight = window.visualViewport
        ? window.visualViewport.height
        : window.innerHeight;
      var rect = area.getBoundingClientRect();
      if (rect.bottom > viewportHeight - 24 || rect.top < 16) {
        area.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 320);
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
    area.addEventListener("focus", function () {
      focusCommentArea(area);
    });
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

  /*
   * 评论树：后端 moment_comments 用 parent_id 记录「回复了谁」。
   * 这里拍平成两层显示——顶层评论 + 挂在它下面的子回复，回复的回复也挂回顶层，
   * 避免出现第三层缩进把卡片撑乱。
   */
  function groupComments(comments) {
    var byId = {};
    (comments || []).forEach(function (comment) {
      byId[String(comment.id)] = comment;
    });
    var roots = [];
    var replies = {};
    (comments || []).forEach(function (comment) {
      var parent = comment.parent_id ? byId[String(comment.parent_id)] : null;
      if (!parent) {
        roots.push(comment);
        return;
      }
      var guard = 0;
      while (parent.parent_id && byId[String(parent.parent_id)] && guard < 50) {
        parent = byId[String(parent.parent_id)];
        guard += 1;
      }
      var key = String(parent.id);
      if (!replies[key]) replies[key] = [];
      replies[key].push(comment);
    });
    return { roots: roots, replies: replies, byId: byId };
  }

  /*
   * 单条评论：正文 + 「回复」（就地展开行内回复框）+ 作者 / 管理员可用的「删除」。
   * 回复框由 ctx 统一管着，同一时间只展开一个。
   */
  function buildCommentNode(moment, comment, freshIds, grouped, ctx) {
    var row = el("div", "mo-comment");
    row.dataset.commentId = String(comment.id);
    var head = el("div", "mo-comment-head");
    head.appendChild(el("span", "mo-comment-actor", comment.actor || "匿名"));
    var parent = comment.parent_id ? grouped.byId[String(comment.parent_id)] : null;
    if (parent) {
      // 回复：带上被回复人，肉眼能看出这条挂在谁下面
      head.appendChild(
        el("span", "mo-comment-reply-to", "回复 @" + (parent.actor || "匿名"))
      );
    }
    head.appendChild(el("span", "mo-comment-time", formatTime(comment.created_at)));
    row.appendChild(head);
    var text = el("p", "mo-comment-text", comment.content);
    // 新评论：正文变主题色并闪烁（不再给评论行加方框呼吸）
    if (isCommentFresh(comment.id)) {
      text.classList.add("is-new-comment");
      freshIds.push(comment.id);
    }
    row.appendChild(text);
    /*
     * 行动区二选一：自己写的（管理员自己评论 / 回复的内容）能删，
     * 别人的评论只给「回复」——不在别人的评论下面挂删除按钮。
     */
    if (canInteract) {
      var actions = el("div", "mo-comment-actions");
      if (comment.mine) {
        var deleteBtn = el("button", "mo-link-btn is-danger", "删除");
        deleteBtn.type = "button";
        deleteBtn.addEventListener("click", async function () {
          var confirmed = await window.ErrorDialog.confirm(
            "确定要删除这条评论吗？",
            { title: "删除评论", confirmText: "删除", danger: true }
          );
          if (!confirmed) return;
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
        row.appendChild(actions);
      } else {
        var replyBtn = el("button", "mo-link-btn", "回复");
        replyBtn.type = "button";
        replyBtn.setAttribute("aria-expanded", "false");
        replyBtn.addEventListener("click", function () {
          ctx.toggleReply(comment, replyBtn);
        });
        actions.appendChild(replyBtn);
        row.appendChild(actions);
        // 回复框挂在被回复的评论下面，提交后由 loadMoments() 重新渲染出子回复
        var form = buildCommentForm(
          moment,
          comment.id,
          "回复 @" + (comment.actor || "匿名") + "…"
        );
        ctx.replies[String(comment.id)] = form;
        row.appendChild(form);
      }
    }
    return row;
  }

  function buildComments(moment, freshIds) {
    var comments = moment.comments || [];
    var box = el("div", "mo-comments");
    var grouped = groupComments(comments);
    var ctx = { replies: {}, active: null };
    ctx.closeReply = function () {
      var active = ctx.active;
      if (!active) return;
      active.form.hidden = true;
      active.form.reset();
      active.btn.classList.remove("is-active");
      active.btn.setAttribute("aria-expanded", "false");
      ctx.active = null;
    };
    ctx.toggleReply = function (comment, btn) {
      var key = String(comment.id);
      var form = ctx.replies[key];
      if (!form) return;
      if (ctx.active && ctx.active.key === key) {
        ctx.closeReply();
        return;
      }
      ctx.closeReply();
      ctx.active = { key: key, form: form, btn: btn };
      form.hidden = false;
      btn.classList.add("is-active");
      btn.setAttribute("aria-expanded", "true");
      var area = form.querySelector("textarea");
      if (!area) return;
      try {
        area.focus({ preventScroll: true });
      } catch (err) {
        area.focus();
      }
      area.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    if (comments.length) {
      var list = el("div", "mo-comment-list");
      grouped.roots.forEach(function (comment) {
        list.appendChild(buildCommentNode(moment, comment, freshIds, grouped, ctx));
        var children = grouped.replies[String(comment.id)] || [];
        if (!children.length) return;
        var nest = el("div", "mo-comment-replies");
        children.forEach(function (child) {
          nest.appendChild(buildCommentNode(moment, child, freshIds, grouped, ctx));
        });
        list.appendChild(nest);
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
    var avatar = document.createElement("img");
    avatar.className = "mo-avatar";
    /* 透明底的角色立绘（和标签页图标同一张画的高清版），由 CSS 负责尺寸与中心对齐 */
    avatar.src = "/static/site/error-chan-avatar.png?v=1";
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
      head.appendChild(el("span", "mo-region", moment.region));
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

    var freshCommentIds = [];
    body.appendChild(buildComments(moment, freshCommentIds));

    /*
     * 右上角「⋯」（和 Error酱 / 时间 / 属地同一行）：举报（别人发的动态）
     * 或 置顶 / 编辑 / 删除（管理员），和留言页一样收进菜单，不平铺按钮。
     */
    var menuItems = [];

    function togglePin() {
      api("/api/moments/" + moment.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned: !moment.pinned }),
      }).then(function () {
        return loadMoments();
      }).catch(function (err) {
        toast(err.message);
      });
    }

    function startEdit() {
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
      body.appendChild(box);
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
    }

    function removeMoment() {
      window.ErrorDialog.confirm("确定要删除这条动态吗？", {
        title: "删除动态",
        confirmText: "删除",
        danger: true,
      }).then(function (confirmed) {
        if (!confirmed) return;
        return api("/api/moments/" + moment.id, { method: "DELETE" })
          .then(function () {
            toast("已删除");
            return loadMoments();
          })
          .catch(function (err) {
            toast(err.message);
          });
      });
    }

    if (moment.can_manage) {
      menuItems.push({ label: moment.pinned ? "取消置顶" : "置顶", onPick: togglePin });
      menuItems.push({ label: "编辑", onPick: startEdit });
      menuItems.push({ label: "删除", danger: true, onPick: removeMoment });
    } else if (canInteract) {
      menuItems.push({ label: "举报", report: moment });
    }
    if (menuItems.length) {
      head.appendChild(buildMoreMenu(menuItems));
    }

    item.appendChild(body);

    // 整张卡片的方框呼吸：自己收到新评论，或卡片本身就是新的
    var rootFresh =
      Boolean(freshTargets[String(moment.id)]) && !isCommentFresh(moment.id);
    if (rootFresh || freshCommentIds.length) {
      var freshIds = freshCommentIds.slice();
      if (rootFresh) freshIds.unshift(moment.id);
      markFreshCard(item, freshIds, freshCommentIds.length ? "comment" : "moment");
    }
    return item;
  }

  function loadMoments() {
    var list = $("momentList");
    var targetsRequest = canInteract
      ? api("/api/site/moments/unread")
          .then(function (data) {
            return data || {};
          })
          .catch(function () {
            return {};
          })
      : Promise.resolve({});
    return Promise.all([api("/api/moments"), targetsRequest]).then(function (result) {
      var payload = result[0] || {};
      momentsRequireLogin = Boolean(payload.requires_login);
      latestMomentRows = Array.isArray(payload) ? payload : (payload.items || []);
      // 游客先落在「开发日志」那一栏（日志本来就对外公开），登录账号仍默认「我的动态」
      if (momentsRequireLogin && !explicitMomentKind) setMomentKind("log");
      /*
       * freshTargets: 目标 id → 提醒类型。动态 id 和评论 id 是两张表的自增主键，
       * 可能撞号，所以一定要靠 kind 区分「动态本体」和「某条评论」。
       */
      freshTargets = {};
      var unread = result[1] || {};
      var targetKinds = unread.target_kinds || {};
      (unread.targets || []).forEach(function (id) {
        freshTargets[String(id)] = targetKinds[String(id)] || "";
      });
      renderMomentRows();
    }).catch(function (err) {
      list.innerHTML = "";
      list.appendChild(el("div", "mo-empty", "加载失败：" + err.message));
    });
  }

  function pollMomentNotifications() {
    if (!canInteract || momentPollBusy) return;
    momentPollBusy = true;
    fetch("/api/site/notifications/summary", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("通知状态加载失败");
        return response.json();
      })
      .then(function (data) {
        var count = Number(data.moments) || 0;
        var previous = lastMomentUnread;
        lastMomentUnread = count;
        if (
          previous !== null &&
          count !== previous &&
          !document.querySelector(".mo-comment-form textarea:focus, .mo-edit")
        ) {
          loadMoments();
        }
      })
      .catch(function () {})
      .then(function () {
        momentPollBusy = false;
      });
  }

  // ---------- 筛选 ----------
  var MOMENT_FILTER_VALUES = ["all", "share", "commented", "liked"];
  var MOMENT_FILTER_LABELS = {
    all: "全部动态",
    share: "分享",
    commented: "评论",
    liked: "点赞",
  };
  var MOMENT_KIND_VALUES = ["post", "log"];
  var currentMomentKind = "post";
  // 地址栏里明确带了 ?kind= 就听用户的，否则游客会默认落到「开发日志」
  var explicitMomentKind =
    MOMENT_KIND_VALUES.indexOf(
      new URLSearchParams(location.search).get("kind") || ""
    ) >= 0;
  var canManageMoments = false;
  var MOMENT_FILTER_EMPTY_TEXT = {
    share: "还没有从 Error酱分享过的资源。",
    commented: "还没有被评论过的动态。",
    liked: "还没有被点赞过的动态。",
  };
  var currentMomentFilter = "all";
  var latestMomentRows = [];
  var momentsRequireLogin = false;

  function momentMatchesFilter(row) {
    // 分享 = 从 Error酱分享过去的资源；评论 / 点赞 = 任何用户（含管理员）动过的动态
    if (currentMomentFilter === "share") return Boolean(row.share);
    // has_comments / has_likes 是后端按行算好的标记；静态文件先上线、后端还没重启时，
    // 用同一份响应里的 comments / like_count 兜底，避免筛出来一片空白。
    if (currentMomentFilter === "commented") {
      return typeof row.has_comments === "boolean"
        ? row.has_comments
        : Boolean((row.comments || []).length);
    }
    if (currentMomentFilter === "liked") {
      return typeof row.has_likes === "boolean"
        ? row.has_likes
        : Number(row.like_count || 0) > 0;
    }
    return true;
  }

  function setMomentFilter(value) {
    if (MOMENT_FILTER_VALUES.indexOf(value) < 0) value = "all";
    currentMomentFilter = value;
    syncFilterControl();
    var url = new URL(window.location.href);
    if (value === "all") url.searchParams.delete("filter");
    else url.searchParams.set("filter", value);
    history.replaceState(null, "", url.toString());
  }

  // 悬浮按钮上的文字 + 菜单里的选中态保持同步
  function syncFilterControl() {
    var label = $("momentFilterLabel");
    if (label) {
      label.textContent =
        MOMENT_FILTER_LABELS[currentMomentFilter] || MOMENT_FILTER_LABELS.all;
    }
    Array.prototype.forEach.call(
      document.querySelectorAll("#momentFilterMenu [data-mo-filter]"),
      function (node) {
        var active =
          node.getAttribute("data-mo-filter") === currentMomentFilter;
        node.classList.toggle("is-active", active);
        node.setAttribute("aria-selected", active ? "true" : "false");
      }
    );
  }

  function filterMenuOpen() {
    var menu = $("momentFilterMenu");
    return Boolean(menu && !menu.hidden);
  }

  function setFilterMenuOpen(open) {
    var menu = $("momentFilterMenu");
    var btn = $("momentFilterBtn");
    var wrap = $("momentFilterWrap");
    var dock = $("momentDock");
    if (menu) menu.hidden = !open;
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (wrap) wrap.classList.toggle("is-open", open);
    // 和留言页一致：菜单打开时这一排按钮的图标一起转（含「写动态」的飞机）
    if (dock) dock.classList.toggle("is-open", open);
  }

  function closeFilterMenu() {
    if (filterMenuOpen()) setFilterMenuOpen(false);
  }

  function initMomentFilters() {
    syncFilterControl();
    var btn = $("momentFilterBtn");
    if (!btn || !canInteract) return;
    btn.addEventListener("click", function () {
      setFilterMenuOpen(!filterMenuOpen());
    });
    var menu = $("momentFilterMenu");
    if (menu) {
      menu.addEventListener("click", function (event) {
        var option = event.target.closest("[data-mo-filter]");
        if (!option) return;
        var value = option.getAttribute("data-mo-filter");
        setFilterMenuOpen(false);
        if (value === currentMomentFilter) return;
        setMomentFilter(value);
        renderMomentRows();
      });
    }
    // 点菜单以外的地方关掉；Esc 同样收起
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest("#momentFilterWrap")) return;
      closeFilterMenu();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeFilterMenu();
    });
    initSendFloat();
  }

  /*
   * 动态分两栏：我的动态（kind=post）与开发日志（kind=log）。
   * 数据由后端在 moments.kind 上标记，前端只做分流，不发新请求、不刷新页面。
   */
  function setMomentKind(value) {
    if (MOMENT_KIND_VALUES.indexOf(value) < 0) value = "post";
    currentMomentKind = value;
    var box = $("momentKinds");
    if (box) {
      box.querySelectorAll("[data-mo-kind]").forEach(function (node) {
        var active = node.getAttribute("data-mo-kind") === value;
        node.classList.toggle("is-active", active);
        node.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }
    var url = new URL(window.location.href);
    if (value === "post") url.searchParams.delete("kind");
    else url.searchParams.set("kind", value);
    history.replaceState(null, "", url.toString());
    applyKindVisibility();
  }

  /*
   * 栏位开关（我的动态 / 开发日志）常驻；筛选和「写动态」只在「我的动态」下出现——
   * 开发日志没有点赞 / 评论可筛，也不能发布。发布框本身也只对管理员显示。
   */
  function applyKindVisibility() {
    var composer = $("momentForm");
    if (composer) composer.hidden = !canManageMoments || currentMomentKind === "log";
    var isLog = currentMomentKind === "log";
    var filterWrap = $("momentFilterWrap");
    if (filterWrap) filterWrap.hidden = !canInteract || isLog;
    var sendBtn = $("momentSendBtn");
    if (sendBtn) sendBtn.hidden = !canManageMoments || isLog;
    closeFilterMenu();
  }

  function initMomentKinds() {
    var dock = $("momentDock");
    if (!dock) return;
    dock.hidden = false;
    var box = $("momentKinds");
    if (box) {
      box.addEventListener("click", function (event) {
        var btn = event.target.closest("[data-mo-kind]");
        if (!btn) return;
        var value = btn.getAttribute("data-mo-kind");
        if (value === currentMomentKind) return;
        setMomentKind(value);
        renderMomentRows();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
    applyKindVisibility();
  }

  /*
   * 「写动态」悬浮按钮：只有发布框完全滚出视野上方时才渐显（纯 opacity），
   * 和留言页的「发送留言」一致；点它先淡出，再平滑滚回顶部并聚焦输入的文本域。
   */
  function setSendFloatVisible(visible) {
    var btn = $("momentSendBtn");
    if (!btn) return;
    btn.classList.toggle("is-visible", Boolean(visible));
    btn.setAttribute("aria-hidden", visible ? "false" : "true");
    btn.tabIndex = visible ? 0 : -1;
  }

  function initSendFloat() {
    var btn = $("momentSendBtn");
    var composer = $("momentForm");
    if (!btn || !composer) return;
    setSendFloatVisible(false);
    btn.addEventListener("click", function () {
      setSendFloatVisible(false);
      try {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err) {
        window.scrollTo(0, 0);
      }
      var area = $("momentContent");
      if (!area) return;
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
          setSendFloatVisible(
            !entry.isIntersecting && entry.boundingClientRect.bottom <= 0
          );
        },
        { threshold: 0 }
      );
      observer.observe(composer);
      return;
    }
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

  /* 「【更新日志】2026-10-11　标题」+ 若干「· 条目」→ 标题与条目 */
  function parseLogRow(row) {
    var text = String(row.content || "").replace(/^【更新日志】\s*/, "");
    var lines = text.split("\n");
    var head = (lines.shift() || "").trim();
    var matched = head.match(/^(\d{4}-\d{2}-\d{2})[\s\u3000]+([\s\S]*)$/);
    var items = lines
      .map(function (line) {
        return line.replace(/^\s*[·•\-*]\s*/, "").trim();
      })
      .filter(Boolean);
    return { title: (matched ? matched[2] : head).trim() || "更新", items: items };
  }

  /*
   * 开发日志：按「月份」手风琴分组。
   * - 默认只展开日志里最新的那个月（也就是「最近 1 个月」；若本月没有日志，
   *   天然落到上一个有日志的月份）。
   * - 折叠的月份只渲染标题，正文等到第一次展开时才建 DOM（懒渲染），
   *   所以日志再多也不会一次性堆出几千个节点。
   * - 展开状态存在 logMonthOpen 里，切栏、刷新列表都不会丢。
   */
  var logMonthOpen = {};

  function logMonthKey(row) {
    return String(row.created_at || "").slice(0, 7);
  }

  function logMonthLabel(key) {
    var parts = String(key).split("-");
    return parts[0] + "年" + parts[1] + "月";
  }

  function buildLogMonthBody(body, rows) {
    var order = [];
    var byDate = {};
    rows.forEach(function (row) {
      var date = String(row.created_at || "").slice(0, 10);
      if (!byDate[date]) {
        byDate[date] = [];
        order.push(date);
      }
      byDate[date].push(row);
    });
    order.forEach(function (date) {
      body.appendChild(el("h4", "mo-log-date", date));
      var ol = el("ol", "mo-log-rows");
      byDate[date].forEach(function (row) {
        var parsed = parseLogRow(row);
        var li = el("li", "mo-log-row");
        var btn = el("button", "mo-log-head");
        btn.type = "button";
        btn.setAttribute("aria-expanded", "false");
        var node = el("span", "mo-log-node");
        node.innerHTML = '<i data-lucide="git-commit-vertical"></i>';
        var time = el("time", "mo-log-time", String(row.created_at || "").slice(11, 16));
        var title = el("span", "mo-log-title", parsed.title);
        var caret = el("span", "mo-log-caret");
        caret.innerHTML = '<i data-lucide="chevron-down"></i>';
        btn.append(node, time, title, caret);
        var detail = el("div", "mo-log-body");
        detail.hidden = true;
        var ul = el("ul", "mo-log-items");
        parsed.items.forEach(function (item) {
          ul.appendChild(el("li", "", item));
        });
        detail.appendChild(ul);
        li.append(btn, detail);
        btn.addEventListener("click", function () {
          var open = !li.classList.contains("is-open");
          li.classList.toggle("is-open", open);
          detail.hidden = !open;
          btn.setAttribute("aria-expanded", open ? "true" : "false");
        });
        ol.appendChild(li);
      });
      body.appendChild(ol);
    });
  }

  function applyLogMonth(panel, open) {
    if (open && !panel.built) {
      buildLogMonthBody(panel.body, panel.rows);
      panel.built = true;
      refreshIcons();
    }
    panel.section.classList.toggle("is-open", open);
    panel.body.hidden = !open;
    panel.header.setAttribute("aria-expanded", open ? "true" : "false");
    logMonthOpen[panel.key] = open;
  }

  function buildLogList(list, rows) {
    var order = [];
    var byMonth = {};
    rows.forEach(function (row) {
      var key = logMonthKey(row);
      if (!byMonth[key]) {
        byMonth[key] = [];
        order.push(key);
      }
      byMonth[key].push(row);
    });
    if (!order.length) return;
    // 默认展开最近 1 个月；用户手动开合过就沿用他的选择
    if (!Object.keys(logMonthOpen).length) logMonthOpen[order[0]] = true;

    var panels = [];
    order.forEach(function (key) {
      var section = el("section", "mo-log-month-group");
      var header = el("button", "mo-log-month");
      header.type = "button";
      header.append(
        el("span", "mo-log-month-label", logMonthLabel(key)),
        el("em", "mo-log-month-num", "共 " + byMonth[key].length + " 条")
      );
      var caret = el("span", "mo-log-caret");
      caret.innerHTML = '<i data-lucide="chevron-down"></i>';
      header.appendChild(caret);
      var body = el("div", "mo-log-month-body");
      body.id = "mo-log-month-" + key;
      header.setAttribute("aria-controls", body.id);
      section.append(header, body);
      list.appendChild(section);

      var panel = { key: key, section: section, header: header, body: body, rows: byMonth[key], built: false };
      panels.push(panel);
      header.addEventListener("click", function () {
        applyLogMonth(panel, !section.classList.contains("is-open"));
      });
    });

    panels.forEach(function (panel) {
      applyLogMonth(panel, Boolean(logMonthOpen[panel.key]));
    });
  }

  function momentEmptyText() {
    if (currentMomentKind === "log") return "还没有开发日志。";
    if (momentsRequireLogin) return "请登录后查看我的动态。";
    if (currentMomentFilter !== "all") {
      return (
        MOMENT_FILTER_EMPTY_TEXT[currentMomentFilter] ||
        "没有符合条件的动态。"
      );
    }
    return "还没有记录，写第一条吧。";
  }

  function renderMomentRows() {
    var list = $("momentList");
    if (!list) return;
    // 先按 kind 分流，再套用「全部 / 分享 / 评论 / 点赞」的筛选
    var rows = latestMomentRows.filter(function (row) {
      return (row.kind || "post") === currentMomentKind;
    });
    // 开发日志不参与筛选（日志没有分享 / 点赞 / 评论），否则切到日志会整页空白
    if (currentMomentKind !== "log" && currentMomentFilter !== "all") {
      rows = rows.filter(momentMatchesFilter);
    }
    list.innerHTML = "";
    if (!rows.length) {
      list.appendChild(el("div", "mo-empty", momentEmptyText()));
      return;
    }
    // 开发日志对游客也开放正文（后端只给 log 行带 content），所以这里不做登录判断
    if (currentMomentKind === "log") {
      buildLogList(list, rows);
      refreshIcons();
      updateJumpButton();
      return;
    }
    // 「我的动态」只对登录账号开放，游客看到一句占位提示
    if (momentsRequireLogin) {
      list.appendChild(el("div", "mo-empty", "请登录后查看我的动态。"));
      return;
    }
    rows.forEach(function (row) {
      list.appendChild(buildMoment(row));
    });
    refreshIcons();
    updateJumpButton();
  }

  renderPending();
  setMomentFilter(new URLSearchParams(location.search).get("filter") || "all");
  setMomentKind(new URLSearchParams(location.search).get("kind") || "post");
  initMomentKinds();
  $("momentShowRegion").checked = false;
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
  var imageViewerStage = $("momentViewerStage");
  if (imageViewer) {
    imageViewer.addEventListener("click", function (event) {
      // 灯箱：点图片周围的空白（stage / viewer 本身）退出
      if (
        event.target === imageViewer ||
        event.target === imageViewerStage
      ) {
        closeImageViewer();
      }
    });
    imageViewer.addEventListener("contextmenu", function (event) {
      event.preventDefault();
    });
  }
  var imageViewerClose = $("momentViewerClose");
  if (imageViewerClose) {
    imageViewerClose.addEventListener("click", closeImageViewer);
  }
  var imageViewerPrev = $("momentViewerPrev");
  if (imageViewerPrev) {
    imageViewerPrev.addEventListener("click", function () {
      stepViewerImage(-1);
    });
  }
  var imageViewerNext = $("momentViewerNext");
  if (imageViewerNext) {
    imageViewerNext.addEventListener("click", function () {
      stepViewerImage(1);
    });
  }
  // 点菜单以外的地方收起「⋯」菜单
  document.addEventListener("click", function (event) {
    if (event.target && event.target.closest && event.target.closest(".mo-more")) {
      return;
    }
    closeAllMoreMenus();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAllMoreMenus();
      closeImageViewer();
    } else if (event.key === "ArrowLeft" && imageViewer && !imageViewer.hidden) {
      stepViewerImage(-1);
    } else if (event.key === "ArrowRight" && imageViewer && !imageViewer.hidden) {
      stepViewerImage(1);
    }
  });

  api("/api/auth/status").then(function (status) {
    canManageMoments = Boolean(status.admin);
    canInteract = Boolean(status.authenticated);
    viewerLikeName = status.owner
      ? "管理员"
      : String(status.username || status.nickname || "");
    if (canInteract) initMomentFilters();
    applyKindVisibility();
    if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);
    return loadMoments().then(pollMomentNotifications);
  }).catch(function () {
    canManageMoments = false;
    applyKindVisibility();
    return loadMoments();
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) pollMomentNotifications();
  });
  window.addEventListener("focus", pollMomentNotifications);
  window.addEventListener("online", pollMomentNotifications);
  setInterval(function () {
    if (!document.hidden) pollMomentNotifications();
  }, 5000);
})();
