/*
 * 歌曲页（推荐页的「歌曲」子页）：
 * - 没有搜索框、没有底部播放条；只剩歌单本身。
 * - 点某首歌的专辑封面开始播放，再点一次暂停；播放中封面外圈是主题色方框 + 呼吸闪光
 *   （和动态页分享卡上的歌曲封面同一套节奏）。
 * - 上传 / 编辑 / 分享 / 下载 都在行尾的小按钮里；上传弹窗既可以从本页的「+歌曲」打开，
 *   也可以由外层推荐页的常驻按钮通过 window.ErrorRecommendTab.openAdd() 打开。
 */
(function () {
  "use strict";

  var audio = document.getElementById("audioEl");
  if (!audio) return;

  var LAST_KEY = "errorMusicLast";
  var MAX_MUSIC_BYTES = 60 * 1024 * 1024;
  var MAX_MUSIC_COUNT = 20;

  function musicLimitLabel() {
    return window.ErrorUploadLimits
      ? window.ErrorUploadLimits.label(MAX_MUSIC_BYTES)
      : "60MB";
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var limits = window.ErrorUploadLimits.get("music_file");
    MAX_MUSIC_BYTES = Number(limits.max_file_bytes) || MAX_MUSIC_BYTES;
    MAX_MUSIC_COUNT = Number(limits.max_count) || MAX_MUSIC_COUNT;
    var hint = $("musicUploadHint");
    if (hint) {
      hint.textContent =
        "支持 mp3 / wav / flac / m4a / aac / ogg / opus，单个不超过 " +
        musicLimitLabel() +
        "；会尝试读取文件里的歌名、歌手、专辑和内嵌封面，没有标签时按文件名猜（例如「茶汤-郁可唯」）。";
    }
  }

  var state = {
    tracks: [],
    canManage: false,
    authenticated: false,
    currentId: null,
    editingId: null,
    deleteArmed: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function api(path, options) {
    return fetch(path, options).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!response.ok) {
            throw new Error((data && data.error) || "请求失败：" + response.status);
          }
          return data;
        });
    });
  }

  var toastTimer = null;
  function toast(message) {
    var el = $("musicToast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.hidden = true;
    }, 3000);
  }

  function formatTime(seconds) {
    var value = Number(seconds);
    if (!isFinite(value) || value <= 0) return "0:00";
    var total = Math.floor(value);
    var mins = Math.floor(total / 60);
    var secs = total % 60;
    return mins + ":" + (secs < 10 ? "0" : "") + secs;
  }

  function trackById(id) {
    for (var i = 0; i < state.tracks.length; i++) {
      if (state.tracks[i].id === id) return state.tracks[i];
    }
    return null;
  }

  function isPlaying() {
    return !audio.paused && !audio.ended && Boolean(state.currentId);
  }

  // ---------- 歌单渲染 ----------

  function emptyHtml() {
    return (
      '<li class="mu-empty"><i data-lucide="music-4"></i><p>歌单还是空的</p>' +
      "<small>" +
      (state.canManage ? "点右上角「+歌曲」把喜欢的歌放进来。" : "等管理员上传歌曲后就能听了。") +
      "</small></li>"
    );
  }

  function coverHtml(track) {
    var inner = track.cover_url
      ? '<img src="' + esc(track.cover_url) + '" alt="" loading="lazy">'
      : '<i data-lucide="music"></i>';
    if (!state.authenticated) {
      return '<span class="mu-row-cover">' + inner + "</span>";
    }
    var label = (isPlaying() && track.id === state.currentId ? "暂停 " : "播放 ") +
      (track.title || "歌曲");
    return (
      '<button class="mu-row-cover" type="button" data-music-cover="' +
      track.id +
      '" aria-label="' +
      esc(label) +
      '" title="' +
      esc(label) +
      '">' +
      inner +
      "</button>"
    );
  }

  function renderList() {
    var box = $("musicList");
    var tracks = state.tracks;
    var count = $("musicCount");
    if (count) count.textContent = tracks.length ? tracks.length + " 首" : "";
    box.classList.toggle("is-manager", state.canManage);
    // 管理员有分享 / 下载 / 编辑 / 删除，其它人（含游客）至少有「举报」
    box.classList.toggle(
      "has-actions",
      state.canManage || tracks.length > 0
    );
    // 普通登录账号看得到「下载 + 举报」两颗，行尾要留够宽度
    box.classList.toggle(
      "actions-2",
      !state.canManage &&
        state.authenticated &&
        tracks.some(function (track) {
          return track.source_type === "file";
        })
    );

    if (!tracks.length) {
      box.innerHTML = emptyHtml();
      if (window.lucide) lucide.createIcons();
      return;
    }

    var playing = isPlaying();
    box.innerHTML = tracks
      .map(function (track) {
        var index = state.tracks.indexOf(track) + 1;
        var active = track.id === state.currentId;
        var actionButtons = "";
        if (state.canManage) {
          if (track.source_type === "file") {
            actionButtons +=
              '<button class="mu-icon-btn" type="button" data-music-share="' +
              track.id +
              '" title="分享"><i data-lucide="share-2"></i></button>' +
              '<button class="mu-icon-btn" type="button" data-music-download="' +
              track.id +
              '" title="下载歌曲"><i data-lucide="download"></i></button>';
          }
          actionButtons +=
            '<button class="mu-icon-btn" type="button" data-music-edit="' +
            track.id +
            '" title="编辑歌曲"><i data-lucide="pencil"></i></button>' +
            '<button class="mu-icon-btn" type="button" data-music-delete="' +
            track.id +
            '" title="删除歌曲"><i data-lucide="trash-2"></i></button>';
        } else {
          if (state.authenticated && track.source_type === "file") {
            actionButtons +=
              '<button class="mu-icon-btn" type="button" data-music-download="' +
              track.id +
              '" title="下载歌曲"><i data-lucide="download"></i></button>';
          }
          // 站点内容都是管理员上传的：非管理员（含游客）只留举报入口
          actionButtons +=
            '<button class="mu-icon-btn" type="button" data-report-type="music" data-report-key="' +
            track.id +
            '" data-report-title="' +
            esc(track.title || "歌曲") +
            '" title="举报"><i data-lucide="flag"></i></button>';
        }
        var actions = actionButtons
          ? '<span class="mu-row-actions">' + actionButtons + "</span>"
          : "";
        return (
          '<li data-focus-id="' + track.id + '" class="mu-row' +
          (active ? " is-active" : "") +
          (active && playing ? " is-playing" : "") +
          '" ' +
          (state.authenticated
            ? 'data-music-play="' + track.id + '"'
            : 'data-music-locked="' + track.id + '"') +
          ">" +
          '<span class="mu-row-index">' +
          (active
            ? '<span class="mu-eq" aria-hidden="true"><i></i><i></i><i></i></span>'
            : index) +
          "</span>" +
          coverHtml(track) +
          '<span class="mu-row-main"><span class="mu-row-title">' +
          esc(track.title || "未命名歌曲") +
          '</span><span class="mu-row-artist">' +
          esc(track.artist || "未知歌手") +
          "</span></span>" +
          '<span class="mu-row-album">' +
          esc(track.album || "") +
          "</span>" +
          '<span class="mu-row-time">' +
          formatTime(track.duration) +
          "</span>" +
          actions +
          "</li>"
        );
      })
      .join("");
    if (window.lucide) lucide.createIcons();
    if (window.ErrorFreshCards) {
      tracks.forEach(function (track) {
        var node = box.querySelector('[data-music-play="' + track.id + '"]');
        window.ErrorFreshCards.mark(node, track.id);
      });
    }
    // 从更新日志跳进来的那一条：高亮呼吸 + 按钮切成「↓ 更新」
    if (window.ErrorFocus) window.ErrorFocus.apply();
    // 有新歌还没滚到眼前时，右下角「顶部」按钮切成「↓ 歌曲」
    if (window.ErrorFreshJump) window.ErrorFreshJump.schedule();
  }

  function scrollActiveIntoView() {
    if (!state.currentId) return;
    var row = $("musicList").querySelector('[data-music-play="' + state.currentId + '"]');
    if (!row) return;
    requestAnimationFrame(function () {
      row.scrollIntoView({ block: "nearest" });
    });
  }

  // ---------- 播放控制 ----------

  function updateMediaSession(track) {
    if (!("mediaSession" in navigator)) return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title || "未命名歌曲",
        artist: track.artist || "Error酱",
        album: track.album || "",
        artwork: track.cover_url
          ? [{ src: new URL(track.cover_url, location.origin).href, sizes: "512x512" }]
          : [],
      });
    } catch (err) {}
  }

  function bindMediaSession() {
    if (!("mediaSession" in navigator) || !navigator.mediaSession.setActionHandler) return;
    var handlers = {
      play: function () {
        audio.play().catch(function () {});
      },
      pause: function () {
        audio.pause();
      },
    };
    Object.keys(handlers).forEach(function (name) {
      try {
        navigator.mediaSession.setActionHandler(name, handlers[name]);
      } catch (err) {}
    });
  }

  function playTrack(id) {
    var track = trackById(id);
    if (!track) return;
    var changed = state.currentId !== track.id;
    state.currentId = track.id;
    if (changed) {
      audio.src = track.url;
      updateMediaSession(track);
      try {
        localStorage.setItem(LAST_KEY, String(track.id));
      } catch (err) {}
    }
    renderList();
    scrollActiveIntoView();
    var promise = audio.play();
    if (promise && promise.catch) {
      promise.catch(function () {
        toast("播放失败，可能是浏览器拦截或文件无法解码");
      });
    }
  }

  function toggleTrack(id) {
    if (!trackById(id)) return;
    if (state.currentId === id && !audio.paused && !audio.ended) {
      audio.pause();
      return;
    }
    playTrack(id);
  }

  // ---------- 上传 / 编辑 ----------

  function fileToBase64(file) {
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

  function updateUploadLabel() {
    var input = $("uploadFiles");
    var files = input.files ? input.files.length : 0;
    $("uploadFileLabel").textContent = files ? "已选择 " + files + " 个文件" : "选择音频文件";
    $("uploadMetaFields").hidden = files > 1;
    $("uploadHint").textContent =
      files > 1
        ? "多选文件时按文件内的标签信息命名，重复歌名也没关系。"
        : "歌名、歌手、专辑留空时会自动读取文件里的标签；没有标签时按文件名猜。";
    if (!uploadBusy.active && uploadBusy.rows) uploadBusy.rows.reset();
  }

  // 上传状态：按钮内显示总进度，点按钮即取消，逐文件进度显示在弹窗列表里。
  var uploadBusy = { active: false, canceled: false, abort: null, fill: null, rows: null };

  function uploadRows() {
    if (!uploadBusy.rows) uploadBusy.rows = ErrorProgress.rows($("uploadRows"));
    return uploadBusy.rows;
  }

  function uploadFill() {
    if (!uploadBusy.fill) {
      uploadBusy.fill = ErrorProgress.button($("uploadSubmit"), { onCancel: cancelUpload });
    }
    return uploadBusy.fill;
  }

  function cancelUpload() {
    if (!uploadBusy.active) return;
    uploadBusy.canceled = true;
    if (uploadBusy.abort) uploadBusy.abort();
  }

  function lockUploadFields(locked) {
    $("uploadCancel").disabled = locked;
    $("uploadClose").disabled = locked;
    $("uploadFiles").disabled = locked;
    $("uploadTitleInput").disabled = locked;
    $("uploadArtistInput").disabled = locked;
    $("uploadAlbumInput").disabled = locked;
  }

  function submitUpload() {
    var input = $("uploadFiles");
    var files = Array.prototype.slice.call(input.files || []);
    if (uploadBusy.active) return;
    if (!files.length) {
      toast("先选择音频文件");
      return;
    }
    if (files.length > MAX_MUSIC_COUNT) {
      toast("一次最多选择 " + MAX_MUSIC_COUNT + " 个音频文件");
      return;
    }
    var oversize = files.filter(function (file) {
      return file.size > MAX_MUSIC_BYTES;
    });
    if (oversize.length) {
      toast(oversize[0].name + " 超过 " + musicLimitLabel() + "，先压缩一下再上传");
      return;
    }
    var single = files.length === 1;
    var meta = {
      title: single ? $("uploadTitleInput").value.trim() : "",
      artist: single ? $("uploadArtistInput").value.trim() : "",
      album: single ? $("uploadAlbumInput").value.trim() : "",
    };
    var rows = uploadRows();
    var fill = uploadFill();
    rows.reset();
    files.forEach(function (file) {
      rows.add(file);
    });
    uploadBusy.active = true;
    uploadBusy.canceled = false;
    uploadBusy.abort = null;
    lockUploadFields(true);

    var totalBytes = files.reduce(function (sum, file) {
      return sum + Math.max(1, file.size);
    }, 0);
    var finishedBytes = 0;
    var done = 0;
    var failed = 0;

    function paintOverall() {
      var ratio = totalBytes ? finishedBytes / totalBytes : 0;
      fill.set(ratio, "取消上传 " + ErrorProgress.percentText(ratio));
      $("uploadSubmit").title = "点击取消上传";
    }
    paintOverall();

    var chain = Promise.resolve();
    files.forEach(function (file, index) {
      var fileSize = Math.max(1, file.size);
      chain = chain.then(function () {
        if (uploadBusy.canceled) {
          rows.set(index, "canceled");
          return;
        }
        rows.set(index, "uploading", { ratio: 0, text: "读取文件…" });
        $("uploadHint").textContent =
          "正在上传 " + (index + 1) + "/" + files.length + "：" + file.name;
        return fileToBase64(file).then(function (data) {
          if (uploadBusy.canceled) {
            rows.set(index, "canceled");
            return;
          }
          var task = ErrorProgress.upload("/api/site/music/upload", {
            payload: {
              file_name: file.name,
              data_base64: data,
              title: meta.title,
              artist: meta.artist,
              album: meta.album,
            },
            onProgress: function (ratio) {
              rows.set(index, "uploading", {
                ratio: ratio,
                text:
                  ErrorProgress.percentText(ratio) +
                  " · " +
                  ErrorProgress.formatBytes(file.size),
              });
              var live = finishedBytes + fileSize * ratio;
              fill.set(
                totalBytes ? live / totalBytes : ratio,
                "取消上传 " + ErrorProgress.percentText(totalBytes ? live / totalBytes : ratio)
              );
            },
            onUploaded: function () {
              rows.set(index, "processing", { text: "处理中 · " + ErrorProgress.formatBytes(file.size) });
            },
          });
          uploadBusy.abort = task.abort;
          return task.promise.then(
            function () {
              uploadBusy.abort = null;
              done += 1;
              finishedBytes += fileSize;
              rows.set(index, "done", { text: "已完成 · " + ErrorProgress.formatBytes(file.size) });
              paintOverall();
            },
            function (err) {
              uploadBusy.abort = null;
              if (ErrorProgress.isAborted(err)) {
                uploadBusy.canceled = true;
                rows.set(index, "canceled");
                return;
              }
              failed += 1;
              finishedBytes += fileSize;
              rows.set(index, "error", { text: "失败：" + err.message });
              paintOverall();
            }
          );
        });
      });
    });

    chain.then(function () {
      uploadBusy.active = false;
      uploadBusy.abort = null;
      lockUploadFields(false);
      fill.reset();
      $("uploadSubmit").removeAttribute("title");
      if (uploadBusy.canceled) {
        $("uploadHint").textContent = "已取消上传，文件仍然保留，可以直接重新开始。";
        toast("已取消上传，文件已保留");
        return;
      }
      input.value = "";
      $("uploadTitleInput").value = "";
      $("uploadArtistInput").value = "";
      $("uploadAlbumInput").value = "";
      updateUploadLabel();
      uploadRows().reset();
      $("uploadModal").hidden = true;
      toast("上传完成：成功 " + done + " 首" + (failed ? "，失败 " + failed + " 首" : ""));
      loadTracks();
    });
  }

  /*
   * 「删除 → 再点一次确认」按钮是图标 + 文字：
   * 图标交给 morphicons 形变（trash-2 → alert-triangle），文字照旧直接改；
   * 没有 morphicons 时退回原来的整体重建。label 都是写死的字面量，不涉及用户输入。
   */
  function setDeleteButton(icon, label) {
    var btn = $("editDelete");
    if (window.ErrorMorph && window.ErrorMorph.morph(btn, icon)) {
      var text = btn.querySelector("span");
      if (text) text.textContent = label;
      return;
    }
    btn.innerHTML = '<i data-lucide="' + icon + '"></i><span>' + label + "</span>";
    if (window.lucide) lucide.createIcons();
  }

  function openEdit(track) {
    state.editingId = track.id;
    state.deleteArmed = false;
    $("editTitleInput").value = track.title || "";
    $("editArtistInput").value = track.artist || "";
    $("editAlbumInput").value = track.album || "";
    setDeleteButton("trash-2", "删除");
    $("editError").hidden = true;
    $("editModal").hidden = false;
    notifyDock(true);
    if (window.lucide) lucide.createIcons();
  }

  /* 编辑弹窗打开时，外层推荐页那排悬浮按钮要收上去（见 embed.js） */
  function notifyDock(open) {
    if (window.ErrorEmbed) window.ErrorEmbed.notifyDialog(open);
  }

  function closeEditModal() {
    if ($("editModal").hidden) return;
    $("editModal").hidden = true;
    notifyDock(false);
  }

  function submitEdit(event) {
    event.preventDefault();
    var id = state.editingId;
    if (!id) return;
    var title = $("editTitleInput").value.trim();
    if (!title) {
      $("editError").textContent = "歌名不能为空。";
      $("editError").hidden = false;
      return;
    }
    api("/api/site/music/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title,
        artist: $("editArtistInput").value.trim(),
        album: $("editAlbumInput").value.trim(),
      }),
    })
      .then(function () {
        closeEditModal();
        toast("已保存");
        loadTracks();
      })
      .catch(function (err) {
        $("editError").textContent = err.message;
        $("editError").hidden = false;
      });
  }

  function deleteCurrent() {
    var id = state.editingId;
    if (!id) return;
    if (!state.deleteArmed) {
      state.deleteArmed = true;
      setDeleteButton("alert-triangle", "再点一次确认删除");
      return;
    }
    api("/api/site/music/" + id, { method: "DELETE" })
      .then(function () {
        if (state.currentId === id) {
          audio.pause();
          audio.removeAttribute("src");
          audio.load();
          state.currentId = null;
        }
        closeEditModal();
        toast("已删除");
        loadTracks();
      })
      .catch(function (err) {
        toast(err.message);
      });
  }

  // ---------- 数据加载 ----------

  function loadTracks() {
    return api("/api/site/music").then(function (data) {
      state.tracks = Array.isArray(data) ? data : [];
      if (state.currentId && !trackById(state.currentId)) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
        state.currentId = null;
      }
      renderList();
      if (!state.currentId && state.tracks.length && state.authenticated) {
        var last = null;
        try {
          last = Number(localStorage.getItem(LAST_KEY) || 0);
        } catch (err) {}
        var target = last ? trackById(last) : null;
        if (target) {
          state.currentId = target.id;
          audio.src = target.url;
          renderList();
          scrollActiveIntoView();
        }
      }
    });
  }

  function loadAuth() {
    return api("/api/auth/status")
      .then(function (status) {
        state.canManage = Boolean(status.owner);
        state.authenticated = Boolean(status.authenticated);
        $("musicUploadBtn").hidden = !state.canManage;
        if (!state.authenticated) {
          audio.pause();
          audio.removeAttribute("src");
          audio.load();
          state.currentId = null;
        }
        renderList();
      })
      .catch(function () {
        state.canManage = false;
        state.authenticated = false;
      });
  }

  // 外层推荐页的「+歌曲」按钮通过它打开上传弹窗
  function openUpload() {
    $("uploadFiles").value = "";
    updateUploadLabel();
    if (uploadBusy.rows) uploadBusy.rows.reset();
    $("uploadModal").hidden = false;
    if (window.lucide) lucide.createIcons();
  }
  window.ErrorRecommendTab = { key: "music", openAdd: openUpload };

  // ---------- 事件 ----------

  audio.addEventListener("play", renderList);
  audio.addEventListener("pause", renderList);
  audio.addEventListener("playing", renderList);
  audio.addEventListener("ended", renderList);
  audio.addEventListener("error", function () {
    if (audio.src) toast("这首歌无法播放，可能是格式不受支持或文件缺失");
  });
  audio.addEventListener("loadedmetadata", function () {
    if (!isFinite(audio.duration) || audio.duration <= 0) return;
    var track = trackById(state.currentId);
    if (track && !track.duration) {
      track.duration = audio.duration;
      renderList();
    }
  });

  $("musicList").addEventListener("click", function (event) {
    if (event.target.closest("[data-report-type]")) return;
    var edit = event.target.closest("[data-music-edit]");
    if (edit) {
      event.stopPropagation();
      var editTrack = trackById(Number(edit.getAttribute("data-music-edit")));
      if (editTrack) openEdit(editTrack);
      return;
    }
    var del = event.target.closest("[data-music-delete]");
    if (del) {
      event.stopPropagation();
      var delTrack = trackById(Number(del.getAttribute("data-music-delete")));
      if (delTrack) openEdit(delTrack);
      return;
    }
    var share = event.target.closest("[data-music-share]");
    if (share) {
      event.stopPropagation();
      var shareTrack = trackById(Number(share.getAttribute("data-music-share")));
      if (shareTrack && window.ErrorShare) {
        window.ErrorShare.open("music", shareTrack.id, shareTrack.title);
      }
      return;
    }
    var download = event.target.closest("[data-music-download]");
    if (download) {
      event.stopPropagation();
      location.href =
        "/api/site/music/" + download.getAttribute("data-music-download") + "/download";
      return;
    }
    var locked = event.target.closest("[data-music-locked]");
    if (locked) {
      toast("请登录后操作");
      return;
    }
    if (!state.authenticated) {
      return;
    }
    var cover = event.target.closest("[data-music-cover]");
    if (cover) {
      event.stopPropagation();
      toggleTrack(Number(cover.getAttribute("data-music-cover")));
      return;
    }
    var row = event.target.closest("[data-music-play]");
    if (row) playTrack(Number(row.getAttribute("data-music-play")));
  });

  $("musicUploadBtn").addEventListener("click", openUpload);
  $("uploadFiles").addEventListener("change", updateUploadLabel);

  // 点击 / 拖拽 / 拖文件夹上传，Chromium 下会记住上次打开的目录
  var uploadField = $("uploadFiles").closest(".mu-file-field");
  if (window.ErrorDropZone && uploadField) {
    window.ErrorDropZone.attach(uploadField, {
      input: $("uploadFiles"),
      accept: [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", "audio/*"],
      maxCount: function () {
        return MAX_MUSIC_COUNT;
      },
      multiple: true,
      pickerId: "errorjiang-music",
      toast: toast
    });
  }
  $("uploadSubmit").addEventListener("click", submitUpload);
  $("uploadClose").addEventListener("click", function () {
    if (uploadBusy.active) return;
    $("uploadModal").hidden = true;
  });
  $("uploadCancel").addEventListener("click", function () {
    if (uploadBusy.active) return;
    $("uploadModal").hidden = true;
  });

  $("editForm").addEventListener("submit", submitEdit);
  $("editClose").addEventListener("click", function () {
    closeEditModal();
  });
  $("editCancel").addEventListener("click", function () {
    closeEditModal();
  });
  $("editDelete").addEventListener("click", deleteCurrent);

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (uploadBusy.active) return;
    $("uploadModal").hidden = true;
    closeEditModal();
  });

  // ---------- 初始化 ----------

  audio.volume = 0.8;
  renderList();
  bindMediaSession();

  loadAuth()
    .then(function () {
      return window.ErrorFreshCards ? window.ErrorFreshCards.load() : null;
    })
    .then(loadTracks)
    .catch(function () {
      loadTracks().catch(function (err) {
        toast(err.message);
      });
    });
  if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);
})();
