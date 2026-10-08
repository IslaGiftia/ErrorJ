(function () {
  "use strict";

  var MAX_IMAGE_BYTES = 15 * 1024 * 1024;

  function coverLimitLabel() {
    return window.ErrorUploadLimits
      ? window.ErrorUploadLimits.label(MAX_IMAGE_BYTES)
      : "15MB";
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var limits = window.ErrorUploadLimits.get("recommend_image");
    MAX_IMAGE_BYTES = Number(limits.max_file_bytes) || MAX_IMAGE_BYTES;
    var hint = $("recCoverHint");
    if (hint) {
      hint.textContent =
        "网站建议 16:9，电影和动漫建议 2:3，最大 " + coverLimitLabel() + "。";
    }
  }
  var IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"];
  var kindLabels = {
    site: "网站",
    tool: "工具",
    movie: "电影",
    anime: "动漫",
  };
  var state = {
    items: [],
    canManage: false,
    tab: "all",
    query: "",
    editingId: null,
    bookmarks: [],
    bookmarksLoaded: false,
    selectedBookmark: null,
    bookmarkQuery: "",
    coverPath: "",
    coverFile: null,
    coverObjectUrl: "",
    lastColumnCount: 0,
  };
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

  function refreshIcons() {
    if (window.lucide) window.lucide.createIcons();
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

  function toast(text) {
    var box = $("recToast");
    box.textContent = text;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      box.hidden = true;
    }, 2400);
  }

  function extensionOf(name) {
    var index = String(name || "").lastIndexOf(".");
    return index < 0 ? "" : String(name).slice(index).toLowerCase();
  }

  function isMedia(item) {
    return item.kind === "movie" || item.kind === "anime";
  }

  function splitTags(value) {
    return String(value || "")
      .split(",")
      .map(function (tag) { return tag.trim(); })
      .filter(Boolean);
  }

  function visibleItems() {
    var keyword = state.query.trim().toLowerCase();
    return state.items.filter(function (item) {
      if (state.tab === "web" && item.kind !== "site" && item.kind !== "tool") return false;
      if (state.tab === "movie" && item.kind !== "movie") return false;
      if (state.tab === "anime" && item.kind !== "anime") return false;
      if (!keyword) return true;
      return [
        item.title,
        item.subtitle,
        item.description,
        item.category,
        item.tags,
        item.status,
      ].join("\n").toLowerCase().indexOf(keyword) >= 0;
    });
  }

  function columnCount() {
    if (window.innerWidth <= 680) return 1;
    if (window.innerWidth <= 1080) return 2;
    return 3;
  }

  function coverUrl(path) {
    return path ? "/site-files/" + path : "";
  }

  function renderStats() {
    var web = state.items.filter(function (item) {
      return item.kind === "site" || item.kind === "tool";
    }).length;
    var movies = state.items.filter(function (item) { return item.kind === "movie"; }).length;
    var anime = state.items.filter(function (item) { return item.kind === "anime"; }).length;
    $("recCount").textContent = state.items.length + " 项";
    $("recSiteStat").textContent = web;
    $("recMovieStat").textContent = movies;
    $("recAnimeStat").textContent = anime;
  }

  function renderTabs() {
    Array.prototype.forEach.call($("recTabs").querySelectorAll("button"), function (button) {
      button.classList.toggle("active", button.getAttribute("data-tab") === state.tab);
    });
  }

  function adminActions(item) {
    var wrap = el("div", "rec-card-actions");
    var pin = el("button", "", item.pinned ? "取消置顶" : "置顶");
    var edit = el("button", "", "编辑");
    var remove = el("button", "danger", "删除");
    pin.type = "button";
    edit.type = "button";
    remove.type = "button";
    wrap.append(pin, edit, remove);

    pin.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      pin.disabled = true;
      api("/api/recommendations/" + item.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned: !item.pinned }),
      }).then(loadRecommendations).catch(function (err) {
        toast(err.message);
      }).then(function () {
        pin.disabled = false;
      });
    });

    edit.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      openEditor(item);
    });

    remove.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      if (!window.confirm("删除推荐「" + item.title + "」？封面文件也会一起清理。")) return;
      api("/api/recommendations/" + item.id, { method: "DELETE" }).then(function () {
        toast("已删除");
        return loadRecommendations();
      }).catch(function (err) {
        toast(err.message);
      });
    });
    return wrap;
  }

  function coverNode(item) {
    var cover = el("div", "rec-card-cover");
    var source = coverUrl(item.cover_path) || item.icon_url || "";
    if (source) {
      var image = document.createElement("img");
      image.src = source;
      image.alt = item.title || "";
      image.loading = "lazy";
      image.addEventListener("error", function () {
        image.remove();
        cover.appendChild(el("span", "rec-cover-fallback", String(item.title || "推").slice(0, 1)));
      });
      cover.appendChild(image);
    } else {
      cover.appendChild(el("span", "rec-cover-fallback", String(item.title || "推").slice(0, 1)));
    }
    cover.appendChild(el("span", "rec-kind-badge", kindLabels[item.kind] || "推荐"));
    if (isMedia(item) && item.status) {
      cover.appendChild(el("span", "rec-status-badge", item.status));
    }
    if (state.canManage) cover.appendChild(adminActions(item));
    return cover;
  }

  function cardTitle(item) {
    var row = el("div", "rec-card-title-row");
    if ((item.kind === "site" || item.kind === "tool") && item.icon_url) {
      var icon = document.createElement("img");
      icon.className = "rec-site-icon";
      icon.src = item.icon_url;
      icon.alt = "";
      icon.loading = "lazy";
      icon.addEventListener("error", function () { icon.remove(); });
      row.appendChild(icon);
    }
    row.appendChild(el("h2", "", item.title));
    return row;
  }

  function cardBody(item) {
    var body = el("div", "rec-card-body");
    body.appendChild(cardTitle(item));
    if (item.subtitle) body.appendChild(el("p", "rec-subtitle", item.subtitle));
    var meta = el("div", "rec-meta");
    if (item.category) meta.appendChild(el("span", "", item.category));
    if (item.release_year) meta.appendChild(el("span", "", item.release_year));
    if (item.rating !== null && item.rating !== undefined && item.rating !== "") {
      meta.appendChild(el("span", "rec-rating", "★ " + Number(item.rating).toFixed(1)));
    }
    if (meta.childNodes.length) body.appendChild(meta);
    if (item.description) body.appendChild(el("p", "rec-description", item.description));
    var tags = splitTags(item.tags);
    if (tags.length) {
      var tagRow = el("div", "rec-tag-row");
      tags.forEach(function (tag) { tagRow.appendChild(el("span", "", tag)); });
      body.appendChild(tagRow);
    }
    var links = el("div", "rec-link-row");
    if (item.url) {
      var open = el("a", isMedia(item) ? "" : "primary", isMedia(item) ? "查看详情" : "访问");
      open.href = item.url;
      open.target = "_blank";
      open.rel = "noopener noreferrer";
      links.appendChild(open);
    }
    if (item.download_url) {
      var download = el("a", "", "下载");
      download.href = item.download_url;
      download.target = "_blank";
      download.rel = "noopener noreferrer";
      links.appendChild(download);
    }
    if (links.childNodes.length) body.appendChild(links);
    return body;
  }

  function buildCard(item) {
    var card = el(
      "article",
      "rec-card " + (isMedia(item) ? "rec-media-card" : "rec-web-card") + (item.pinned ? " is-pinned" : "")
    );
    card.appendChild(coverNode(item));
    card.appendChild(cardBody(item));
    return card;
  }

  function renderColumns(cards) {
    var grid = $("recGrid");
    var count = columnCount();
    state.lastColumnCount = count;
    var columns = Array.from({ length: count }, function () {
      return el("div", "rec-column");
    });
    cards.forEach(function (card, index) {
      columns[index % count].appendChild(card);
    });
    grid.style.gridTemplateColumns = "repeat(" + count + ", minmax(0, 1fr))";
    grid.replaceChildren.apply(grid, columns.filter(function (column) {
      return column.childElementCount > 0;
    }));
  }

  function renderCards() {
    var rows = visibleItems();
    var cards = rows.map(buildCard);
    renderColumns(cards);
    $("recEmpty").hidden = rows.length > 0;
  }

  function loadRecommendations() {
    return api("/api/recommendations").then(function (data) {
      state.items = Array.isArray(data.items) ? data.items : [];
      state.canManage = Boolean(data.can_manage);
      $("recAddBtn").hidden = !state.canManage;
      renderStats();
      renderTabs();
      renderCards();
      refreshIcons();
    }).catch(function (err) {
      state.items = [];
      state.canManage = false;
      renderStats();
      renderCards();
      toast(err.message || "加载失败");
    });
  }

  function fileToBase64(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var value = String(reader.result || "");
        var comma = value.indexOf(",");
        resolve(comma >= 0 ? value.slice(comma + 1) : value);
      };
      reader.onerror = function () { reject(new Error("读取图片失败")); };
      reader.readAsDataURL(blob);
    });
  }

  function shrinkImage(file) {
    return new Promise(function (resolve) {
      if (!file.type || file.type === "image/gif" || file.type.indexOf("image/") !== 0) {
        resolve(file);
        return;
      }
      var objectUrl = URL.createObjectURL(file);
      var image = new Image();
      image.onload = function () {
        var longest = Math.max(image.width, image.height);
        var scale = Math.min(1, 2400 / longest);
        if (scale === 1 && file.size <= 4 * 1024 * 1024) {
          URL.revokeObjectURL(objectUrl);
          resolve(file);
          return;
        }
        var canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(image.width * scale));
        canvas.height = Math.max(1, Math.round(image.height * scale));
        canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (blob) {
          URL.revokeObjectURL(objectUrl);
          if (!blob) {
            resolve(file);
            return;
          }
          var base = String(file.name || "cover").replace(/\.[^.]+$/, "");
          resolve(new File([blob], base + ".webp", { type: "image/webp" }));
        }, "image/webp", 0.9);
      };
      image.onerror = function () {
        URL.revokeObjectURL(objectUrl);
        resolve(file);
      };
      image.src = objectUrl;
    });
  }

  function clearCoverObjectUrl() {
    if (state.coverObjectUrl) {
      URL.revokeObjectURL(state.coverObjectUrl);
      state.coverObjectUrl = "";
    }
  }

  function renderCoverPreview() {
    clearCoverObjectUrl();
    var preview = $("recCoverPreview");
    preview.innerHTML = "";
    var source = "";
    if (state.coverFile) {
      state.coverObjectUrl = URL.createObjectURL(state.coverFile);
      source = state.coverObjectUrl;
    } else if (state.coverPath) {
      source = coverUrl(state.coverPath);
    }
    if (source) {
      var image = document.createElement("img");
      image.src = source;
      image.alt = "封面预览";
      preview.appendChild(image);
      $("recClearCover").hidden = false;
    } else {
      preview.appendChild(el("i", ""));
      preview.firstChild.setAttribute("data-lucide", "image-plus");
      $("recClearCover").hidden = true;
      refreshIcons();
    }
  }

  function loadBookmarks() {
    if (!state.canManage) return Promise.resolve([]);
    if (state.bookmarksLoaded) return Promise.resolve(state.bookmarks);
    return api("/api/bookmarks").then(function (rows) {
      state.bookmarks = Array.isArray(rows) ? rows : [];
      state.bookmarksLoaded = true;
      return state.bookmarks;
    });
  }

  function renderBookmarkSummary() {
    var summary = $("recBookmarkSummary");
    if (state.selectedBookmark) {
      summary.textContent = state.selectedBookmark.title + " · " + state.selectedBookmark.url;
      $("recClearBookmark").hidden = false;
    } else {
      summary.textContent = "未关联，可手动填写标题和访问地址。";
      $("recClearBookmark").hidden = true;
    }
  }

  function visibleBookmarks() {
    var keyword = state.bookmarkQuery.trim().toLowerCase();
    if (!keyword) return state.bookmarks;
    return state.bookmarks.filter(function (item) {
      return [item.title, item.url, item.description, item.folder_name]
        .join("\n").toLowerCase().indexOf(keyword) >= 0;
    });
  }

  function renderBookmarkPicker() {
    var list = $("recBookmarkList");
    var rows = visibleBookmarks();
    list.innerHTML = "";
    $("recBookmarkEmpty").hidden = rows.length > 0;
    rows.forEach(function (item) {
      var button = el("button", "rec-bookmark-option", "");
      button.type = "button";
      if (state.selectedBookmark && state.selectedBookmark.id === item.id) {
        button.classList.add("selected");
      }
      var main = el("span", "", "");
      main.appendChild(el("strong", "", item.title || item.url));
      main.appendChild(el("span", "", item.url || ""));
      button.appendChild(main);
      button.appendChild(el("em", "", item.folder_name || "未分类"));
      button.addEventListener("click", function () {
        state.selectedBookmark = item;
        $("recTitle").value = item.title || "";
        $("recUrl").value = item.url || "";
        if (!$("recDescription").value.trim() && item.description) {
          $("recDescription").value = item.description;
        }
        renderBookmarkSummary();
        updateFormFields();
        closeBookmarkPicker();
      });
      list.appendChild(button);
    });
  }

  function openBookmarkPicker() {
    loadBookmarks().then(function () {
      state.bookmarkQuery = "";
      $("recBookmarkSearch").value = "";
      renderBookmarkPicker();
      $("recBookmarkPicker").hidden = false;
      window.setTimeout(function () { $("recBookmarkSearch").focus(); }, 0);
    }).catch(function (err) {
      toast(err.message || "加载书签失败");
    });
  }

  function closeBookmarkPicker() {
    $("recBookmarkPicker").hidden = true;
  }

  function updateFormFields() {
    var kind = $("recKind").value;
    if (kind !== "site") state.selectedBookmark = null;
    Array.prototype.forEach.call(document.querySelectorAll("[data-kinds]"), function (node) {
      var kinds = String(node.getAttribute("data-kinds") || "").split(/\s+/);
      node.hidden = kinds.indexOf(kind) < 0;
    });
    $("recUrlLabel").textContent = isMedia({ kind: kind }) ? "详情地址（可选）" : "访问地址";
    $("recUrl").required = kind === "site" || kind === "tool";
    var linked = kind === "site" && Boolean(state.selectedBookmark);
    $("recTitle").readOnly = linked;
    $("recUrl").readOnly = linked;
    $("recIconUrl").disabled = linked;
    if (linked) {
      $("recTitle").value = state.selectedBookmark.title || "";
      $("recUrl").value = state.selectedBookmark.url || "";
    }
    renderBookmarkSummary();
  }

  function openEditorForm(item) {
    state.editingId = item ? item.id : null;
    state.coverPath = item ? item.cover_path || "" : "";
    state.coverFile = null;
    $("recModalTitle").textContent = item ? "编辑推荐" : "新增推荐";
    $("recKind").value = item ? item.kind : "site";
    $("recTitle").value = item ? item.title || "" : "";
    $("recSubtitle").value = item ? item.subtitle || "" : "";
    $("recCategory").value = item ? item.category || "" : "";
    $("recTags").value = item ? item.tags || "" : "";
    $("recUrl").value = item ? item.url || "" : "";
    $("recDownloadUrl").value = item ? item.download_url || "" : "";
    $("recIconUrl").value = item && !item.bookmark_id ? item.icon_url || "" : "";
    $("recStatus").value = item ? item.status || "" : "";
    $("recRating").value = item && item.rating !== null && item.rating !== undefined ? item.rating : "";
    $("recYear").value = item ? item.release_year || "" : "";
    $("recDescription").value = item ? item.description || "" : "";
    $("recPinned").checked = Boolean(item && item.pinned);
    $("recCoverInput").value = "";
    $("recFormError").hidden = true;
    updateFormFields();
    renderCoverPreview();
    $("recModal").hidden = false;
    window.setTimeout(function () { $("recTitle").focus(); }, 0);
  }

  function openEditor(item) {
    if (!state.canManage) return;
    loadBookmarks().then(function () {
      state.selectedBookmark = item && item.bookmark_id
        ? state.bookmarks.find(function (bookmark) {
          return Number(bookmark.id) === Number(item.bookmark_id);
        }) || null
        : null;
      openEditorForm(item);
    }).catch(function (err) {
      toast(err.message || "加载书签失败");
      state.selectedBookmark = null;
      openEditorForm(item);
    });
  }

  function closeEditor() {
    $("recModal").hidden = true;
    state.editingId = null;
    state.coverPath = "";
    state.coverFile = null;
    state.selectedBookmark = null;
    clearCoverObjectUrl();
    closeBookmarkPicker();
  }

  function uploadCover(file) {
    if (!file) return Promise.resolve(state.coverPath);
    if (file.size > MAX_IMAGE_BYTES) {
      return Promise.reject(new Error("封面图片不能超过 " + coverLimitLabel()));
    }
    if (IMAGE_EXTENSIONS.indexOf(extensionOf(file.name)) < 0 && file.type.indexOf("image/") !== 0) {
      return Promise.reject(new Error("封面只支持图片文件"));
    }
    return shrinkImage(file).then(function (prepared) {
      return fileToBase64(prepared).then(function (data) {
        return api("/api/recommendations/images", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            file_name: prepared.name || "cover.webp",
            data_base64: data,
          }),
        });
      });
    }).then(function (result) {
      return result.path;
    });
  }

  function saveRecommendation(event) {
    event.preventDefault();
    if (!state.canManage) return;
    var save = $("recSave");
    save.disabled = true;
    $("recFormError").hidden = true;
    uploadCover(state.coverFile).then(function (coverPath) {
      var payload = {
        kind: $("recKind").value,
        bookmark_id: state.selectedBookmark ? state.selectedBookmark.id : null,
        title: $("recTitle").value.trim(),
        subtitle: $("recSubtitle").value.trim(),
        category: $("recCategory").value.trim(),
        tags: $("recTags").value.trim(),
        url: $("recUrl").value.trim(),
        download_url: $("recDownloadUrl").value.trim(),
        icon_url: $("recIconUrl").value.trim(),
        status: $("recStatus").value.trim(),
        rating: $("recRating").value,
        release_year: $("recYear").value,
        description: $("recDescription").value.trim(),
        cover_path: coverPath || "",
        pinned: $("recPinned").checked,
      };
      var path = state.editingId
        ? "/api/recommendations/" + state.editingId
        : "/api/recommendations";
      return api(path, {
        method: state.editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }).then(function () {
      toast(state.editingId ? "已保存" : "已新增");
      closeEditor();
      return loadRecommendations();
    }).catch(function (err) {
      $("recFormError").textContent = err.message || "保存失败";
      $("recFormError").hidden = false;
    }).then(function () {
      save.disabled = false;
    });
  }

  $("recTabs").addEventListener("click", function (event) {
    var button = event.target.closest("button[data-tab]");
    if (!button) return;
    state.tab = button.getAttribute("data-tab");
    renderTabs();
    renderCards();
  });

  $("recSearch").addEventListener("input", function (event) {
    state.query = event.target.value;
    renderCards();
  });

  $("recAddBtn").addEventListener("click", function () { openEditor(null); });
  $("recModalClose").addEventListener("click", closeEditor);
  $("recCancel").addEventListener("click", closeEditor);
  $("recModal").addEventListener("click", function (event) {
    if (event.target === $("recModal")) closeEditor();
  });
  $("recKind").addEventListener("change", updateFormFields);
  $("recPickBookmark").addEventListener("click", openBookmarkPicker);
  $("recClearBookmark").addEventListener("click", function () {
    state.selectedBookmark = null;
    updateFormFields();
    $("recTitle").focus();
  });
  $("recBookmarkSearch").addEventListener("input", function (event) {
    state.bookmarkQuery = event.target.value;
    renderBookmarkPicker();
  });
  $("recBookmarkPickerClose").addEventListener("click", closeBookmarkPicker);
  $("recBookmarkPicker").addEventListener("click", function (event) {
    if (event.target === $("recBookmarkPicker")) closeBookmarkPicker();
  });
  $("recPickCover").addEventListener("click", function () { $("recCoverInput").click(); });
  $("recCoverInput").addEventListener("change", function (event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      toast("封面图片不能超过 " + coverLimitLabel());
      event.target.value = "";
      return;
    }
    state.coverFile = file;
    state.coverPath = "";
    renderCoverPreview();
  });
  $("recClearCover").addEventListener("click", function () {
    state.coverFile = null;
    state.coverPath = "";
    $("recCoverInput").value = "";
    renderCoverPreview();
  });
  $("recForm").addEventListener("submit", saveRecommendation);

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!$("recBookmarkPicker").hidden) {
      closeBookmarkPicker();
      return;
    }
    if (!$("recModal").hidden) closeEditor();
  });

  window.addEventListener("resize", function () {
    if (columnCount() === state.lastColumnCount) return;
    renderCards();
  });

  state.lastColumnCount = columnCount();
  if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);
  loadRecommendations();
})();
