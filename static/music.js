(function () {
  "use strict";

  var audio = document.getElementById("audioEl");
  if (!audio) return;

  var state = {
    tracks: [],
    canManage: false,
    currentId: null,
    shuffle: false,
    repeat: "off",
    keyword: "",
    editingId: null,
    seeking: false,
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
    var config = options || {};
    return fetch(path, config).then(function (response) {
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

  function currentTrack() {
    return state.currentId ? trackById(state.currentId) : null;
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

  function coverHtml(track, sizeClass) {
    if (track.cover_url) {
      return (
        '<span class="' +
        sizeClass +
        '"><img src="' +
        esc(track.cover_url) +
        '" alt="" loading="lazy"></span>'
      );
    }
    return '<span class="' + sizeClass + '">♪</span>';
  }

  function renderList() {
    var box = $("musicList");
    var tracks = visibleTracks();
    var count = $("musicCount");
    if (count) {
      count.textContent = state.tracks.length
        ? state.tracks.length + " 首歌"
        : "";
    }
    if (!tracks.length) {
      box.innerHTML =
        '<p class="mu-empty">' +
        (state.tracks.length ? "没有匹配的歌曲。" : state.canManage ? "还没有歌曲，点右上角上传。" : "歌单还是空的。") +
        "</p>";
      return;
    }
    box.innerHTML = tracks
      .map(function (track) {
        var index = state.tracks.indexOf(track) + 1;
        var active = track.id === state.currentId;
        var sub = [track.artist, track.album].filter(Boolean).join(" · ") || "未知歌手";
        var actions = state.canManage
          ? '<span class="mu-item-actions">' +
            '<button class="mu-icon-btn" type="button" data-music-edit="' +
            track.id +
            '" title="编辑"><i data-lucide="pencil"></i></button>' +
            '<button class="mu-icon-btn" type="button" data-music-delete="' +
            track.id +
            '" title="删除"><i data-lucide="trash-2"></i></button>' +
            "</span>"
          : "";
        return (
          '<div class="mu-item' +
          (active ? " is-active" : "") +
          '" data-music-play="' +
          track.id +
          '" role="button" tabindex="0">' +
          '<span class="mu-item-index">' +
          (active && !audio.paused ? "▶" : index) +
          "</span>" +
          coverHtml(track, "mu-item-cover") +
          '<span class="mu-item-body"><span class="mu-item-title">' +
          esc(track.title) +
          '</span><span class="mu-item-sub">' +
          esc(sub) +
          "</span></span>" +
          '<span class="mu-item-time">' +
          formatTime(track.duration) +
          "</span>" +
          actions +
          "</div>"
        );
      })
      .join("");
    if (window.lucide) lucide.createIcons();
  }

  function renderPlayer() {
    var track = currentTrack();
    var coverImg = $("playerCoverImg");
    var fallback = $("playerCoverFallback");
    if (!track) {
      $("playerTitle").textContent = "还没有选择歌曲";
      $("playerMeta").textContent = state.tracks.length
        ? "点击歌单里的歌曲开始播放"
        : state.canManage
          ? "上传后点击歌单里的歌曲开始播放"
          : "歌单还是空的";
      coverImg.hidden = true;
      coverImg.removeAttribute("src");
      fallback.hidden = false;
      $("playerDuration").textContent = "0:00";
      $("playerCurrent").textContent = "0:00";
      $("playerSeek").value = 0;
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
    var btn = $("btnPlay");
    var playing = !audio.paused && !audio.ended && audio.currentTime > 0;
    btn.innerHTML = '<i data-lucide="' + (playing ? "pause" : "play") + '"></i>';
    btn.setAttribute("aria-label", playing ? "暂停" : "播放");
    if (window.lucide) lucide.createIcons();
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

  function playTrack(id, autoplay) {
    var track = trackById(id);
    if (!track) return;
    var changed = state.currentId !== track.id;
    state.currentId = track.id;
    if (changed) {
      audio.src = track.url;
      audio.currentTime = 0;
      updateMediaSession(track);
    }
    renderPlayer();
    renderList();
    if (autoplay !== false) {
      var promise = audio.play();
      if (promise && promise.catch) {
        promise.catch(function () {
          toast("播放失败，可能是浏览器拦截或文件无法解码");
        });
      }
    }
    try {
      localStorage.setItem("errorMusicLast", String(track.id));
    } catch (err) {}
  }

  function togglePlay() {
    if (!state.currentId) {
      var first = visibleTracks()[0];
      if (!first) {
        toast("歌单还是空的");
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

  function setRepeat() {
    state.repeat = state.repeat === "off" ? "all" : state.repeat === "all" ? "one" : "off";
    var btn = $("btnRepeat");
    btn.classList.toggle("is-on", state.repeat !== "off");
    var icon = state.repeat === "one" ? "repeat-1" : "repeat";
    btn.innerHTML = '<i data-lucide="' + icon + '"></i>';
    btn.title =
      state.repeat === "off" ? "循环：关闭" : state.repeat === "all" ? "循环：列表" : "循环：单曲";
    if (window.lucide) lucide.createIcons();
  }

  function setShuffle(on) {
    state.shuffle = on;
    $("btnShuffle").classList.toggle("is-on", on);
  }

  function updateVolumeIcon() {
    var vol = audio.volume;
    var name = audio.muted || vol === 0 ? "volume-x" : vol < 0.5 ? "volume-1" : "volume-2";
    var btn = $("btnMute");
    btn.innerHTML = '<i data-lucide="' + name + '"></i>';
    btn.classList.toggle("is-on", audio.muted || vol === 0);
    if (window.lucide) lucide.createIcons();
  }

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
    var label = $("uploadFileLabel");
    var files = input.files ? input.files.length : 0;
    label.textContent = files ? "已选择 " + files + " 个文件" : "选择音频文件";
    $("uploadMetaFields").hidden = files > 1;
    $("uploadHint").textContent = files > 1
      ? "多选文件时按文件内的标签信息命名，重复歌名也没关系。"
      : "歌名、歌手、专辑留空时会自动读取文件里的标签。";
  }

  function submitUpload() {
    var input = $("uploadFiles");
    var files = Array.prototype.slice.call(input.files || []);
    if (!files.length) {
      toast("先选择音频文件");
      return;
    }
    var single = files.length === 1;
    var payloadMeta = {
      title: single ? $("uploadTitleInput").value.trim() : "",
      artist: single ? $("uploadArtistInput").value.trim() : "",
      album: single ? $("uploadAlbumInput").value.trim() : "",
    };
    var submit = $("uploadSubmit");
    submit.disabled = true;
    var done = 0;
    var failed = 0;
    var chain = Promise.resolve();
    files.forEach(function (file, index) {
      chain = chain.then(function () {
        $("uploadHint").textContent = "正在上传 " + (index + 1) + "/" + files.length + "：" + file.name;
        return fileToBase64(file).then(function (data) {
          return api("/api/site/music/upload", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              file_name: file.name,
              data_base64: data,
              title: payloadMeta.title,
              artist: payloadMeta.artist,
              album: payloadMeta.album,
            }),
          });
        }).then(function () {
          done += 1;
        }).catch(function (err) {
          failed += 1;
          toast(file.name + " 上传失败：" + err.message);
        });
      });
    });
    chain.then(function () {
      submit.disabled = false;
      input.value = "";
      updateUploadLabel();
      $("uploadTitleInput").value = "";
      $("uploadArtistInput").value = "";
      $("uploadAlbumInput").value = "";
      $("uploadModal").hidden = true;
      toast("上传完成：成功 " + done + " 首" + (failed ? "，失败 " + failed + " 首" : ""));
      loadTracks();
    });
  }

  function openEdit(track) {
    state.editingId = track.id;
    state.deleteArmed = false;
    $("editTitle").textContent = "编辑歌曲";
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
    var track = trackById(id);
    if (!track) return;
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

  function loadTracks() {
    return api("/api/site/music").then(function (data) {
      state.tracks = Array.isArray(data) ? data : [];
      if (state.currentId && !trackById(state.currentId)) {
        state.currentId = null;
        audio.removeAttribute("src");
      }
      renderList();
      renderPlayer();
      if (!state.currentId && state.tracks.length) {
        var last = null;
        try {
          last = Number(localStorage.getItem("errorMusicLast") || 0);
        } catch (err) {}
        var target = last ? trackById(last) : null;
        if (target) {
          state.currentId = target.id;
          audio.src = target.url;
          renderPlayer();
          renderList();
        }
      }
    });
  }

  function loadAuth() {
    return api("/api/auth/status")
      .then(function (status) {
        state.canManage = Boolean(status.owner);
        $("musicUploadBtn").hidden = !state.canManage;
        renderList();
      })
      .catch(function () {
        state.canManage = false;
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
  $("btnRepeat").addEventListener("click", setRepeat);
  $("btnMute").addEventListener("click", function () {
    audio.muted = !audio.muted;
    updateVolumeIcon();
  });
  $("playerVolume").addEventListener("input", function () {
    audio.volume = Number($("playerVolume").value);
    audio.muted = false;
    try {
      localStorage.setItem("errorMusicVolume", String(audio.volume));
    } catch (err) {}
    updateVolumeIcon();
  });

  var seek = $("playerSeek");
  seek.addEventListener("input", function () {
    state.seeking = true;
    if (audio.duration) {
      $("playerCurrent").textContent = formatTime((Number(seek.value) / 1000) * audio.duration);
    }
  });
  seek.addEventListener("change", function () {
    if (audio.duration) {
      audio.currentTime = (Number(seek.value) / 1000) * audio.duration;
    }
    state.seeking = false;
  });

  audio.addEventListener("play", updatePlayButton);
  audio.addEventListener("pause", updatePlayButton);
  audio.addEventListener("ended", function () {
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
    $("playerCurrent").textContent = formatTime(audio.currentTime);
    $("playerSeek").value = String(Math.round((audio.currentTime / audio.duration) * 1000));
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

  $("musicSearch").addEventListener("input", function (event) {
    state.keyword = event.target.value;
    renderList();
  });

  $("musicUploadBtn").addEventListener("click", function () {
    $("uploadFiles").value = "";
    updateUploadLabel();
    $("uploadModal").hidden = false;
    if (window.lucide) lucide.createIcons();
  });
  $("uploadFiles").addEventListener("change", updateUploadLabel);
  $("uploadSubmit").addEventListener("click", submitUpload);
  $("uploadClose").addEventListener("click", function () {
    $("uploadModal").hidden = true;
  });
  $("uploadCancel").addEventListener("click", function () {
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
      $("uploadModal").hidden = true;
      $("editModal").hidden = true;
      return;
    }
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowRight") {
      audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 5);
    } else if (event.key === "ArrowLeft") {
      audio.currentTime = Math.max(0, audio.currentTime - 5);
    }
  });

  var savedVolume = 0.8;
  try {
    var stored = Number(localStorage.getItem("errorMusicVolume"));
    if (isFinite(stored) && stored >= 0 && stored <= 1) savedVolume = stored;
  } catch (err) {}
  audio.volume = savedVolume;
  $("playerVolume").value = String(savedVolume);
  updateVolumeIcon();
  updatePlayButton();
  renderPlayer();

  loadAuth().then(loadTracks).catch(function () {
    loadTracks().catch(function (err) {
      toast(err.message);
    });
  });
})();
