(function () {
  "use strict";

  var audio = document.getElementById("audioEl");
  if (!audio) return;

  var VOLUME_KEY = "errorMusicVolume";
  var LAST_KEY = "errorMusicLast";
  var MAX_MUSIC_BYTES = 60 * 1024 * 1024;
  var FINE_POINTER = window.matchMedia
    ? window.matchMedia("(hover: hover) and (pointer: fine)").matches
    : true;

  var state = {
    tracks: [],
    canManage: false,
    authenticated: false,
    currentId: null,
    shuffle: false,
    repeat: "off",
    keyword: "",
    editingId: null,
    seeking: false,
    deleteArmed: false,
    lastVolume: 0.8,
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

  function paintRange(input, ratio) {
    var percent = Math.max(0, Math.min(1, ratio || 0)) * 100;
    input.style.setProperty("--mu-fill", percent.toFixed(1) + "%");
  }

  function trackById(id) {
    for (var i = 0; i < state.tracks.length; i++) {
      if (state.tracks[i].id === id) return state.tracks[i];
    }
    return null;
  }

  function currentTrack() {
    return state.currentId ? trackById(state.currentId) : null;
  }

  function isPlaying() {
    return !audio.paused && !audio.ended && Boolean(state.currentId);
  }

  function visibleTracks() {
    var keyword = state.keyword.trim().toLowerCase();
    if (!keyword) return state.tracks;
    return state.tracks.filter(function (track) {
      return [track.title, track.artist, track.album]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .indexOf(keyword) >= 0;
    });
  }

  function updateSearchClear() {
    $("searchClear").hidden = !state.keyword;
  }

  // ---------- 歌单渲染 ----------

  function emptyHtml() {
    if (state.tracks.length) {
      return (
        '<li class="mu-empty"><i data-lucide="search-x"></i><p>没有匹配的歌曲</p>' +
        '<button class="mu-btn" type="button" data-search-clear>清空搜索</button></li>'
      );
    }
    return (
      '<li class="mu-empty"><i data-lucide="music-4"></i><p>歌单还是空的</p>' +
      "<small>" +
      (state.canManage ? "点右上角「上传歌曲」把喜欢的歌放进来。" : "等管理员上传歌曲后就能听了。") +
      "</small></li>"
    );
  }

  function coverHtml(track) {
    if (track.cover_url) {
      return '<span class="mu-row-cover"><img src="' + esc(track.cover_url) + '" alt="" loading="lazy"></span>';
    }
    return '<span class="mu-row-cover"><i data-lucide="music"></i></span>';
  }

  function renderList() {
    var box = $("musicList");
    var tracks = visibleTracks();
    var count = $("musicCount");
    if (count) {
      if (!state.tracks.length) {
        count.textContent = "";
      } else if (state.keyword) {
        count.textContent = tracks.length + " / " + state.tracks.length + " 首";
      } else {
        count.textContent = state.tracks.length + " 首";
      }
    }
    box.classList.toggle("is-manager", state.canManage);
    box.classList.toggle(
      "has-actions",
      state.canManage ||
        (state.authenticated &&
          tracks.some(function (track) {
            return track.source_type === "file";
          }))
    );
    updateSearchClear();

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
              '" title="生成限时分享链接"><i data-lucide="share-2"></i></button>' +
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
        } else if (state.authenticated && track.source_type === "file") {
          if (track.download_state === "approved") {
            actionButtons +=
              '<button class="mu-icon-btn" type="button" data-music-download="' +
              track.id +
              '" title="下载歌曲"><i data-lucide="download"></i></button>';
          } else if (track.download_state === "pending") {
            actionButtons +=
              '<button class="mu-icon-btn is-pending" type="button" disabled title="下载申请待审核"><i data-lucide="clock"></i></button>';
          } else {
            actionButtons +=
              '<button class="mu-icon-btn" type="button" data-music-request="' +
              track.id +
              '" title="申请下载"><i data-lucide="download"></i></button>';
          }
        }
        var actions = actionButtons
          ? '<span class="mu-row-actions">' + actionButtons + "</span>"
          : "";
        return (
          '<li class="mu-row' +
          (active ? " is-active" : "") +
          (active && playing ? " is-playing" : "") +
          '" data-music-play="' +
          track.id +
          '" role="button" tabindex="0" aria-label="播放 ' +
          esc(track.title) +
          '">' +
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
  }

  function scrollActiveIntoView() {
    if (!state.currentId) return;
    var row = $("musicList").querySelector('[data-music-play="' + state.currentId + '"]');
    if (!row) return;
    requestAnimationFrame(function () {
      row.scrollIntoView({ block: "nearest" });
    });
  }

  function renderPlayer() {
    var track = currentTrack();
    var coverImg = $("playerCoverImg");
    var fallback = $("playerCoverFallback");
    if (!track) {
      $("playerTitle").textContent = "还没有选择歌曲";
      $("playerMeta").textContent = state.tracks.length
        ? "点歌单里的歌曲开始播放"
        : state.canManage
          ? "上传后点歌单里的歌曲开始播放"
          : "歌单还是空的";
      coverImg.hidden = true;
      coverImg.removeAttribute("src");
      fallback.hidden = false;
      $("playerCurrent").textContent = "0:00";
      $("playerDuration").textContent = "0:00";
      $("playerSeek").value = "0";
      paintRange($("playerSeek"), 0);
      return;
    }
    $("playerTitle").textContent = track.title || "未命名歌曲";
    $("playerMeta").textContent =
      [track.artist, track.album].filter(Boolean).join(" · ") || "未知歌手";
    if (track.cover_url) {
      coverImg.src = track.cover_url;
      coverImg.hidden = false;
      fallback.hidden = true;
    } else {
      coverImg.hidden = true;
      coverImg.removeAttribute("src");
      fallback.hidden = false;
    }
    $("playerDuration").textContent = formatTime(track.duration || audio.duration);
  }

  function updatePlayButton() {
    var playing = !audio.paused && !audio.ended;
    var btn = $("btnPlay");
    var icon = playing ? "pause" : "play";
    if (btn.getAttribute("data-icon") !== icon) {
      btn.setAttribute("data-icon", icon);
      btn.innerHTML = '<i data-lucide="' + icon + '"></i>';
      if (window.lucide) lucide.createIcons();
    }
    btn.title = playing ? "暂停" : "播放";
    btn.setAttribute("aria-label", playing ? "暂停" : "播放");
  }

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
      previoustrack: function () {
        prevTrack();
      },
      nexttrack: function () {
        nextTrack(false);
      },
      seekbackward: function () {
        audio.currentTime = Math.max(0, audio.currentTime - 10);
      },
      seekforward: function () {
        audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
      },
    };
    Object.keys(handlers).forEach(function (name) {
      try {
        navigator.mediaSession.setActionHandler(name, handlers[name]);
      } catch (err) {}
    });
  }

  // ---------- 播放控制 ----------

  function playTrack(id, autoplay) {
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
    renderPlayer();
    renderList();
    scrollActiveIntoView();
    if (autoplay !== false) {
      var promise = audio.play();
      if (promise && promise.catch) {
        promise.catch(function () {
          toast("播放失败，可能是浏览器拦截或文件无法解码");
        });
      }
    }
  }

  function togglePlay() {
    if (!state.currentId) {
      var first = visibleTracks()[0];
      if (!first) {
        toast(state.tracks.length ? "没有匹配的歌曲" : "歌单还是空的");
        return;
      }
      playTrack(first.id, true);
      return;
    }
    if (audio.paused) {
      audio.play().catch(function () {
        toast("播放失败");
      });
    } else {
      audio.pause();
    }
  }

  function nextIndex(step) {
    var tracks = state.tracks;
    if (!tracks.length) return -1;
    var index = tracks.indexOf(currentTrack());
    if (state.shuffle && tracks.length > 1) {
      var pick = index;
      while (pick === index) pick = Math.floor(Math.random() * tracks.length);
      return pick;
    }
    return (index + step + tracks.length) % tracks.length;
  }

  function nextTrack(auto) {
    if (!state.tracks.length) return;
    var index = nextIndex(1);
    if (index < 0) return;
    if (auto && state.repeat === "one") {
      audio.currentTime = 0;
      audio.play().catch(function () {});
      return;
    }
    playTrack(state.tracks[index].id, true);
  }

  function prevTrack() {
    if (audio.currentTime > 3) {
      audio.currentTime = 0;
      return;
    }
    var index = nextIndex(-1);
    if (index >= 0) playTrack(state.tracks[index].id, true);
  }

  function renderRepeatButton() {
    var btn = $("btnRepeat");
    var icon = state.repeat === "one" ? "repeat-1" : "repeat";
    btn.classList.toggle("is-on", state.repeat !== "off");
    btn.title =
      state.repeat === "off" ? "循环：关闭" : state.repeat === "all" ? "循环：列表" : "循环：单曲";
    btn.setAttribute("aria-label", btn.title);
    if (btn.getAttribute("data-icon") !== icon) {
      btn.setAttribute("data-icon", icon);
      btn.innerHTML = '<i data-lucide="' + icon + '"></i>';
      if (window.lucide) lucide.createIcons();
    }
  }

  function cycleRepeat() {
    state.repeat = state.repeat === "off" ? "all" : state.repeat === "all" ? "one" : "off";
    renderRepeatButton();
  }

  function setShuffle(on) {
    state.shuffle = on;
    var btn = $("btnShuffle");
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }

  // ---------- 音量：滚轮 + 悬停浮层 ----------

  function saveVolume(value) {
    try {
      localStorage.setItem(VOLUME_KEY, String(value));
    } catch (err) {}
  }

  function updateVolumeIcon() {
    var muted = audio.muted || audio.volume === 0;
    var percent = Math.round((muted ? 0 : audio.volume) * 100);
    var slider = $("playerVolume");
    slider.value = String(percent);
    paintRange(slider, percent / 100);
    $("volumeNum").textContent = percent + "%";

    var icon = muted ? "volume-x" : audio.volume < 0.5 ? "volume-1" : "volume-2";
    var btn = $("btnMute");
    if (btn.getAttribute("data-icon") !== icon) {
      btn.setAttribute("data-icon", icon);
      btn.innerHTML = '<i data-lucide="' + icon + '"></i>';
      if (window.lucide) lucide.createIcons();
    }
    btn.classList.toggle("is-on", muted);
    btn.title = muted
      ? "已静音（滚轮调节音量）"
      : "音量 " + percent + "%（滚轮调节，点击静音）";
  }

  function setVolume(value, persist) {
    var next = Math.max(0, Math.min(1, value));
    if (audio.muted) audio.muted = false;
    audio.volume = next;
    if (next > 0) state.lastVolume = next;
    if (persist !== false) saveVolume(next);
    updateVolumeIcon();
  }

  var volumeFlashTimer = null;
  function flashVolume() {
    var wrap = $("volumeWrap");
    wrap.classList.add("is-open");
    clearTimeout(volumeFlashTimer);
    volumeFlashTimer = setTimeout(function () {
      wrap.classList.remove("is-open");
    }, 1400);
  }

  function toggleMute() {
    if (audio.muted || audio.volume === 0) {
      audio.muted = false;
      if (audio.volume === 0) audio.volume = state.lastVolume || 0.5;
      saveVolume(audio.volume);
    } else {
      state.lastVolume = audio.volume;
      audio.muted = true;
    }
    updateVolumeIcon();
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
    var oversize = files.filter(function (file) {
      return file.size > MAX_MUSIC_BYTES;
    });
    if (oversize.length) {
      toast(oversize[0].name + " 超过 60MB，先压缩一下再上传");
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

  function openEdit(track) {
    state.editingId = track.id;
    state.deleteArmed = false;
    $("editTitleInput").value = track.title || "";
    $("editArtistInput").value = track.artist || "";
    $("editAlbumInput").value = track.album || "";
    $("editDelete").innerHTML = '<i data-lucide="trash-2"></i><span>删除</span>';
    $("editError").hidden = true;
    $("editModal").hidden = false;
    if (window.lucide) lucide.createIcons();
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
        $("editModal").hidden = true;
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
      $("editDelete").innerHTML = '<i data-lucide="alert-triangle"></i><span>再点一次确认删除</span>';
      if (window.lucide) lucide.createIcons();
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
        $("editModal").hidden = true;
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
      renderPlayer();
      if (!state.currentId && state.tracks.length) {
        var last = null;
        try {
          last = Number(localStorage.getItem(LAST_KEY) || 0);
        } catch (err) {}
        var target = last ? trackById(last) : null;
        if (target) {
          state.currentId = target.id;
          audio.src = target.url;
          renderPlayer();
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
        renderList();
      })
      .catch(function () {
        state.canManage = false;
        state.authenticated = false;
      });
  }

  // ---------- 事件 ----------

  $("btnPlay").addEventListener("click", togglePlay);
  $("btnNext").addEventListener("click", function () {
    nextTrack(false);
  });
  $("btnPrev").addEventListener("click", prevTrack);
  $("btnShuffle").addEventListener("click", function () {
    setShuffle(!state.shuffle);
  });
  $("btnRepeat").addEventListener("click", cycleRepeat);

  // 音量按钮：鼠标悬停展示调节区（纯 CSS），滚轮直接调节音量，点击静音。
  $("btnMute").addEventListener("click", function () {
    if (FINE_POINTER) {
      toggleMute();
      return;
    }
    $("volumeWrap").classList.toggle("is-open");
  });

  $("volumeWrap").addEventListener(
    "wheel",
    function (event) {
      event.preventDefault();
      var step = event.shiftKey ? 0.1 : 0.05;
      var base = audio.muted ? 0 : audio.volume;
      setVolume(base + (event.deltaY < 0 ? step : -step));
      flashVolume();
    },
    { passive: false }
  );

  document.addEventListener("click", function (event) {
    if (event.target.closest && event.target.closest(".mu-volume")) return;
    $("volumeWrap").classList.remove("is-open");
  });

  $("playerVolume").addEventListener("input", function (event) {
    setVolume(Number(event.target.value) / 100);
  });

  var seek = $("playerSeek");
  seek.addEventListener("input", function () {
    state.seeking = true;
    if (audio.duration) {
      var ratio = Number(seek.value) / 1000;
      paintRange(seek, ratio);
      $("playerCurrent").textContent = formatTime(ratio * audio.duration);
    }
  });
  seek.addEventListener("change", function () {
    if (audio.duration) {
      audio.currentTime = (Number(seek.value) / 1000) * audio.duration;
    }
    state.seeking = false;
  });

  audio.addEventListener("play", function () {
    updatePlayButton();
    renderList();
  });
  audio.addEventListener("pause", function () {
    updatePlayButton();
    renderList();
  });
  audio.addEventListener("playing", function () {
    updatePlayButton();
    renderList();
  });
  audio.addEventListener("volumechange", updateVolumeIcon);
  audio.addEventListener("ended", function () {
    updatePlayButton();
    renderList();
    if (state.repeat === "one") {
      audio.currentTime = 0;
      audio.play().catch(function () {});
      return;
    }
    var index = nextIndex(1);
    var isLast = state.tracks.indexOf(currentTrack()) === state.tracks.length - 1;
    if (state.repeat === "off" && !state.shuffle && isLast) {
      updatePlayButton();
      renderList();
      return;
    }
    if (index >= 0) playTrack(state.tracks[index].id, true);
  });
  audio.addEventListener("timeupdate", function () {
    if (state.seeking || !audio.duration) return;
    var ratio = audio.currentTime / audio.duration;
    $("playerCurrent").textContent = formatTime(audio.currentTime);
    seek.value = String(Math.round(ratio * 1000));
    paintRange(seek, ratio);
  });
  audio.addEventListener("loadedmetadata", function () {
    $("playerDuration").textContent = formatTime(audio.duration);
    var track = currentTrack();
    if (track && !track.duration) {
      track.duration = audio.duration;
      renderList();
    }
  });
  audio.addEventListener("error", function () {
    if (audio.src) toast("这首歌无法播放，可能是格式不受支持或文件缺失");
  });

  $("musicList").addEventListener("click", function (event) {
    var clear = event.target.closest("[data-search-clear]");
    if (clear) {
      clearSearch();
      return;
    }
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
    var request = event.target.closest("[data-music-request]");
    if (request) {
      event.stopPropagation();
      var requestTrack = trackById(Number(request.getAttribute("data-music-request")));
      if (requestTrack && window.ErrorDownload) {
        window.ErrorDownload.request("music", requestTrack.id, requestTrack.title, function () {
          requestTrack.download_state = "pending";
          renderList();
        });
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
    var row = event.target.closest("[data-music-play]");
    if (row) playTrack(Number(row.getAttribute("data-music-play")), true);
  });

  $("musicList").addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var row = event.target.closest("[data-music-play]");
    if (!row) return;
    event.preventDefault();
    playTrack(Number(row.getAttribute("data-music-play")), true);
  });

  function clearSearch() {
    state.keyword = "";
    $("musicSearch").value = "";
    renderList();
  }

  $("musicSearch").addEventListener("input", function (event) {
    state.keyword = event.target.value;
    renderList();
  });
  $("musicSearch").addEventListener("keydown", function (event) {
    if (event.key === "Escape" && state.keyword) {
      event.stopPropagation();
      clearSearch();
    }
  });
  $("searchClear").addEventListener("click", clearSearch);

  $("musicUploadBtn").addEventListener("click", function () {
    $("uploadFiles").value = "";
    updateUploadLabel();
    if (uploadBusy.rows) uploadBusy.rows.reset();
    $("uploadModal").hidden = false;
    if (window.lucide) lucide.createIcons();
  });
  $("uploadFiles").addEventListener("change", updateUploadLabel);
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
    $("editModal").hidden = true;
  });
  $("editCancel").addEventListener("click", function () {
    $("editModal").hidden = true;
  });
  $("editDelete").addEventListener("click", deleteCurrent);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if (uploadBusy.active) return;
      $("uploadModal").hidden = true;
      $("editModal").hidden = true;
      $("volumeWrap").classList.remove("is-open");
      return;
    }
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      $("musicSearch").focus();
    } else if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowRight") {
      audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 5);
    } else if (event.key === "ArrowLeft") {
      audio.currentTime = Math.max(0, audio.currentTime - 5);
    }
  });

  // 底部播放条高度随时同步给悬浮地图入口和提示条，避免互相遮挡。
  function syncPlayerHeight() {
    var bar = $("playerBar");
    if (!bar) return;
    var height = Math.round(bar.getBoundingClientRect().height);
    if (height > 0) {
      document.documentElement.style.setProperty("--mu-player-h", height + "px");
    }
  }

  // ---------- 初始化 ----------

  var savedVolume = 0.8;
  try {
    var rawVolume = localStorage.getItem(VOLUME_KEY);
    var stored = rawVolume === null ? NaN : Number(rawVolume);
    if (isFinite(stored) && stored >= 0 && stored <= 1) savedVolume = stored;
  } catch (err) {}
  audio.volume = savedVolume;
  state.lastVolume = savedVolume > 0 ? savedVolume : 0.8;
  updateVolumeIcon();
  updatePlayButton();
  renderPlayer();
  bindMediaSession();

  syncPlayerHeight();
  window.addEventListener("resize", syncPlayerHeight);
  if (window.ResizeObserver) {
    new ResizeObserver(syncPlayerHeight).observe($("playerBar"));
  }

  loadAuth()
    .then(loadTracks)
    .catch(function () {
      loadTracks().catch(function (err) {
        toast(err.message);
      });
    });
})();
