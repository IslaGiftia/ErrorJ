(function () {
  const ALL_FOLDER = "__all__";
  const UNFILED_FOLDER = "__unfiled__";
  const IMPORT_PENDING_LABEL = "导入待分配的地址";
  const state = {
    bookmarks: [],
    folders: [],
    selectedFolder: ALL_FOLDER,
    view: "nav",
    expandedFolders: new Set(),
    treeInitialized: false,
    suppressScrollSpy: false,
    scrollSpyFrame: null,
    search: "",
    sort: "manual",
    brokenOnly: false,
    collapsed: new Set(),
    selectedIds: new Set(),
    confirmAction: null,
    checkStatus: null,
    checkPollTimer: null,
    contextTarget: null,
    dragPayload: null,
  };

  const $ = (id) => document.getElementById(id);
  let themePreference = "auto";
  try {
    themePreference = localStorage.getItem("errorSiteTheme") || "auto";
  } catch (err) {}

  function applyTheme(preference, save) {
    themePreference = preference;
    const dark = preference === "dark" ||
      (preference === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    const glyph = $("themeGlyph");
    if (glyph) glyph.textContent = dark ? "☾" : "☀";
    if (save) {
      try {
        localStorage.setItem("errorSiteTheme", preference);
      } catch (err) {}
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function shortDate(value) {
    return value ? String(value).slice(0, 10) : "—";
  }

  function hostnameOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./i, "");
    } catch (err) {
      return String(url || "").replace(/^https?:\/\//i, "").split("/")[0] || "bookmark";
    }
  }

  function faviconMarkup(item) {
    const letter = (hostnameOf(item.url).match(/[A-Za-z0-9\u4e00-\u9fff]/) || ["#"])[0].toUpperCase();
    return `
      <span class="pin-favicon-wrap">
        <span class="pin-favicon-fallback">${escapeHtml(letter)}</span>
        <img class="pin-favicon" src="/api/bookmarks/${item.id}/favicon?v=${encodeURIComponent(item.favicon_updated_at || "")}"
             alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">
      </span>`;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "请求失败");
    return data;
  }

  function showToast(message, type = "success", action = null) {
    const toast = $("toast");
    toast.innerHTML = "";
    toast.className = "pin-toast" + (type === "error" ? " error" : "");
    const label = document.createElement("span");
    label.textContent = message;
    toast.appendChild(label);
    if (action) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "pin-toast-action";
      button.textContent = action.label;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await action.run();
          toast.hidden = true;
        } catch (error) {
          showToast(error.message, "error");
        }
      });
      toast.appendChild(button);
    }
    toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => {
      toast.hidden = true;
    }, action ? 6000 : 2600);
  }

  function openModal(id) {
    $(id).hidden = false;
  }

  function closeModal(id) {
    $(id).hidden = true;
  }

  function closeAllModals() {
    document.querySelectorAll(".pin-modal-overlay").forEach((modal) => {
      modal.hidden = true;
    });
  }

  function confirmDialog(text, action) {
    state.confirmAction = action;
    $("confirmText").textContent = text;
    openModal("confirmModal");
  }

  function folderChildren(parentId) {
    return state.folders
      .filter((folder) => String(folder.parent_id || "") === String(parentId || ""))
      .sort((a, b) =>
        Number(a.sort_order || 0) - Number(b.sort_order || 0) ||
        String(a.name).localeCompare(String(b.name), "zh-CN")
      );
  }

  function folderHasChildren(folderId) {
    return state.folders.some((folder) =>
      String(folder.parent_id || "") === String(folderId)
    );
  }

  function persistExpandedFolders() {
    try {
      localStorage.setItem(
        "bookmarkExpandedFolders",
        JSON.stringify([...state.expandedFolders])
      );
    } catch (err) {}
  }

  function initializeTreeExpansion() {
    if (state.treeInitialized) return;
    state.treeInitialized = true;
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem("bookmarkExpandedFolders") || "null");
    } catch (err) {}
    if (Array.isArray(saved)) {
      saved.forEach((id) => state.expandedFolders.add(String(id)));
      return;
    }
    state.folders.forEach((folder) => {
      if (folderHasChildren(folder.id)) state.expandedFolders.add(String(folder.id));
    });
  }

  function flattenedFolders() {
    const rows = [];
    const walk = (parentId, depth) => {
      folderChildren(parentId).forEach((folder) => {
        rows.push({ folder, depth });
        walk(folder.id, depth + 1);
      });
    };
    walk("", 0);
    return rows;
  }

  function descendantFolderIds(folderId) {
    const ids = new Set([String(folderId)]);
    let changed = true;
    while (changed) {
      changed = false;
      state.folders.forEach((folder) => {
        if (folder.parent_id &&
            ids.has(String(folder.parent_id)) &&
            !ids.has(String(folder.id))) {
          ids.add(String(folder.id));
          changed = true;
        }
      });
    }
    return ids;
  }

  function folderOptions(parentId = "", depth = 0, disabledIds = null) {
    return folderChildren(parentId).flatMap((folder) => {
      if (disabledIds && disabledIds.has(String(folder.id))) return [];
      const indent = "\u3000".repeat(depth);
      return [
        `<option value="${folder.id}">${escapeHtml(indent + folder.name)}</option>`,
        ...folderOptions(folder.id, depth + 1, disabledIds),
      ];
    }).join("");
  }

  function folderById(folderId) {
    return state.folders.find((folder) => String(folder.id) === String(folderId));
  }

  function folderDirectBookmarks(folderId) {
    return state.bookmarks.filter((item) => String(item.folder_id || "") === String(folderId || ""));
  }

  function selectedFolderName() {
    if (state.selectedFolder === ALL_FOLDER) return "全部书签";
    if (state.selectedFolder === UNFILED_FOLDER) return IMPORT_PENDING_LABEL;
    return folderById(state.selectedFolder)?.name || "全部书签";
  }

  function sortedBookmarks(rows) {
    const result = rows.slice();
    if (state.sort === "manual") {
      return result.sort((a, b) =>
        Number(a.sort_order || 0) - Number(b.sort_order || 0) ||
        String(b.created_at || "").localeCompare(String(a.created_at || "")) ||
        Number(b.id || 0) - Number(a.id || 0)
      );
    }
    if (state.sort === "oldest") return result.reverse();
    if (state.sort === "title") {
      return result.sort((a, b) =>
        String(a.title || "").localeCompare(String(b.title || ""), "zh-CN")
      );
    }
    if (state.sort === "folder") {
      return result.sort((a, b) =>
        String(a.folder_path || IMPORT_PENDING_LABEL).localeCompare(
          String(b.folder_path || IMPORT_PENDING_LABEL),
          "zh-CN"
        ) || String(a.title || "").localeCompare(String(b.title || ""), "zh-CN")
      );
    }
    return result;
  }

  function syncSortButtons() {
    document.querySelectorAll("[data-sort]").forEach((button) => {
      button.classList.toggle("active", button.dataset.sort === state.sort);
    });
  }

  function setSort(sort) {
    state.sort = sort;
    syncSortButtons();
    render();
  }

  function visibleBookmarks(ignoreFolder = false) {
    const keyword = state.search.trim().toLowerCase();
    return sortedBookmarks(state.bookmarks.filter((item) => {
      if (state.brokenOnly && item.link_status !== "broken") return false;
      if (!ignoreFolder) {
        if (state.selectedFolder === UNFILED_FOLDER && item.folder_id) return false;
        if (state.selectedFolder !== ALL_FOLDER &&
            state.selectedFolder !== UNFILED_FOLDER &&
            String(item.folder_id) !== String(state.selectedFolder)) return false;
      }
      if (!keyword) return true;
      return [item.title, item.url, item.description, item.folder_path]
        .some((value) => String(value || "").toLowerCase().includes(keyword));
    }));
  }

  function renderFolderTree() {
    const target = $("folderTree");
    const allCount = state.bookmarks.length;
    const unfiledCount = folderDirectBookmarks("").length;
    const renderRows = (parentId, depth) => folderChildren(parentId).map((folder) => {
      const hasChildren = folderHasChildren(folder.id);
      const expanded = state.expandedFolders.has(String(folder.id));
      const row = `
        <div class="pin-folder-row ${String(state.selectedFolder) === String(folder.id) ? "active" : ""}"
             data-folder="${folder.id}" data-drop-folder="${folder.id}"
             role="button" tabindex="0" draggable="true"
             style="padding-left:${8 + depth * 18}px">
          ${hasChildren
            ? `<button class="pin-folder-toggle ${expanded ? "expanded" : ""}" type="button"
                       data-toggle-folder="${folder.id}" aria-label="${expanded ? "折叠" : "展开"}"
                       aria-expanded="${expanded}"><i data-lucide="chevron-right"></i></button>`
            : '<span class="pin-folder-toggle-spacer"></span>'}
          <i data-lucide="folder"></i>
          <span class="pin-folder-name">${escapeHtml(folder.name)}</span>
          <span class="pin-folder-count">${folderDirectBookmarks(folder.id).length}</span>
          <span class="pin-folder-actions">
            <button type="button" data-action="edit-folder" data-id="${folder.id}" title="编辑"><i data-lucide="pencil"></i></button>
            <button type="button" data-action="delete-folder" data-id="${folder.id}" title="删除"><i data-lucide="trash-2"></i></button>
          </span>
        </div>`;
      return row + (hasChildren && expanded ? renderRows(folder.id, depth + 1) : "");
    }).join("");
    const rows = renderRows("", 0);
    target.innerHTML = `
      <div class="pin-folder-row ${state.selectedFolder === ALL_FOLDER ? "active" : ""}"
           data-folder="${ALL_FOLDER}" data-drop-folder="" role="button" tabindex="0">
        <span class="pin-folder-toggle-spacer"></span>
        <i data-lucide="library"></i>
        <span class="pin-folder-name">全部书签</span>
        <span class="pin-folder-count">${allCount}</span>
      </div>
      <div class="pin-folder-row ${state.selectedFolder === UNFILED_FOLDER ? "active" : ""}"
           data-folder="${UNFILED_FOLDER}" data-drop-folder="__unfiled__" role="button" tabindex="0">
        <span class="pin-folder-toggle-spacer"></span>
        <i data-lucide="inbox"></i>
        <span class="pin-folder-name">${IMPORT_PENDING_LABEL}</span>
        <span class="pin-folder-count">${unfiledCount}</span>
      </div>
      <div class="pin-folder-divider"></div>
      ${rows}
    `;
  }

  function sectionForFolder(folder, items, key, title = "") {
    const dropFolder = folder ? folder.id : (key === "unfiled" ? "__unfiled__" : "");
    const scrollId = folder ? String(folder.id) : UNFILED_FOLDER;
    return `
      <section class="pin-grid-section" id="bookmark-section-${escapeHtml(scrollId)}"
               data-section-key="${escapeHtml(key)}"
               data-section-folder="${escapeHtml(scrollId)}">
        <div class="pin-grid-section-head"
             ${dropFolder !== "" ? `data-drop-folder="${dropFolder}"` : ""}>
          <i data-lucide="${folder ? "folder" : "inbox"}"></i>
          <span class="pin-grid-section-title">${escapeHtml(title || folder?.name || IMPORT_PENDING_LABEL)}</span>
          <span class="pin-grid-section-count">${items.length}</span>
        </div>
        <div class="pin-grid-section-body">
          ${items.length ? items.map(renderGridCard).join("") : '<div class="pin-empty">这个文件夹是空的</div>'}
        </div>
      </section>
    `;
  }

  function linkStatusMarkup(item) {
    const checking = Boolean(state.checkStatus?.running);
    if (checking) {
      return '<span class="pin-link-status checking" title="检查中">◌</span>';
    }
    if (item.link_status === "valid") {
      return `<span class="pin-link-status valid" title="链接有效${item.link_status_code ? ` (${item.link_status_code})` : ""}">✓</span>`;
    }
    if (item.link_status === "broken") {
      return `<span class="pin-link-status broken" title="${escapeHtml(item.link_error || "链接失效")}">✕</span>`;
    }
    return "";
  }

  function noteChipMarkup(item) {
    if (!item.description) return "";
    return `<span class="pin-note-chip" data-action="edit-note" data-id="${item.id}"
                  title="${escapeHtml(item.description)}">
      <i data-lucide="sticky-note"></i><span>${escapeHtml(item.description)}</span>
    </span>`;
  }

  function noteListMarkup(item) {
    if (!item.description) {
      return '<span class="pin-list-note pin-list-note-empty"></span>';
    }
    return `<span class="pin-list-note" data-action="edit-note" data-id="${item.id}"
                  title="${escapeHtml(item.description)}">${escapeHtml(item.description)}</span>`;
  }

  function renderGridCard(item) {
    const status = linkStatusMarkup(item);
    return `
      <div class="pin-bookmark-card ${item.link_status === "broken" ? "link-broken" : ""}"
           data-bookmark-card="${item.id}" draggable="true">
        ${faviconMarkup(item)}
        <a class="pin-bookmark-title" href="${escapeHtml(item.url)}" target="_blank" rel="noopener" draggable="false" title="${escapeHtml(item.title || item.url)}">${escapeHtml(item.title || item.url)}</a>
        ${status}
        ${noteChipMarkup(item)}
      </div>
    `;
  }

  function gridColumnCount() {
    const container = $("gridSections");
    const available = Math.max(280, container.clientWidth - 28);
    return Math.max(1, Math.min(5, Math.floor((available + 12) / 312)));
  }

  function renderGridColumns(sections) {
    const columnCount = gridColumnCount();
    const columns = Array.from({ length: columnCount }, () => ({
      html: [],
    }));
    sections.forEach((section, index) => {
      const target = columns[index % columnCount];
      target.html.push(
        sectionForFolder(section.folder, section.items, section.key, section.title)
      );
    });
    $("gridSections").style.gridTemplateColumns =
      `repeat(${columnCount}, minmax(0, 1fr))`;
    $("gridSections").innerHTML = columns
      .filter((column) => column.html.length)
      .map((column) => `<div class="pin-grid-column">${column.html.join("")}</div>`)
      .join("");
  }

  function renderGrid() {
    const target = $("gridSections");
    $("currentScope").textContent = selectedFolderName();
    let sections = [];
    if (state.search.trim()) {
      sections = [{ key: "search", folder: null, title: "搜索结果", items: visibleBookmarks(true) }];
    } else {
      sections = flattenedFolders().map(({ folder }) => ({
        key: `folder:${folder.id}`,
        folder,
        items: sortedBookmarks(folderDirectBookmarks(folder.id)),
      }));
      const unfiled = folderDirectBookmarks("");
      sections.push({
        key: "unfiled",
        folder: null,
        title: IMPORT_PENDING_LABEL,
        items: sortedBookmarks(unfiled),
      });
      if (state.brokenOnly) {
        sections = sections
          .map((section) => ({
            ...section,
            items: section.items.filter((item) => item.link_status === "broken"),
          }))
          .filter((section) => section.items.length);
      }
    }
    if (!sections.length) {
      target.style.gridTemplateColumns = "1fr";
      target.innerHTML = `
        <div class="pin-empty">
          <i data-lucide="bookmark-x"></i>
          <div>${state.search.trim() ? "没有匹配的书签" : "还没有收藏网页"}</div>
          <button class="pin-primary-btn" type="button" id="emptyAddBookmark"><i data-lucide="plus"></i><span>添加书签</span></button>
        </div>`;
      return;
    }
    renderGridColumns(sections);
  }

  function renderListRow(item) {
    const selected = state.selectedIds.has(String(item.id));
    return `
      <div class="pin-list-row ${selected ? "selected" : ""} ${item.link_status === "broken" ? "link-broken" : ""}"
           data-list-row="${item.id}" draggable="true">
        <input class="pin-list-check" type="checkbox" data-select-bookmark="${item.id}" ${selected ? "checked" : ""}>
        ${faviconMarkup(item)}
        <a class="pin-list-title-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener" draggable="false">${escapeHtml(item.title || item.url)}</a>
        <span class="pin-list-url" title="${escapeHtml(item.url)}">${escapeHtml(item.url)}</span>
        <span class="pin-list-date">${escapeHtml(shortDate(item.created_at))}</span>
        ${linkStatusMarkup(item)}
        ${noteListMarkup(item)}
      </div>
    `;
  }

  function renderList() {
    const rows = visibleBookmarks();
    const visibleIds = new Set(rows.map((item) => String(item.id)));
    [...state.selectedIds].forEach((id) => {
      if (!visibleIds.has(id)) state.selectedIds.delete(id);
    });
    $("listFolderTitle").textContent = state.search.trim() ? "搜索结果" : selectedFolderName();
    $("listBookmarkCount").textContent = `${rows.length} 个书签`;
    $("selectedHint").textContent = state.selectedIds.size ? `${state.selectedIds.size} 已选` : "";
    $("deleteSelectedBtn").disabled = state.selectedIds.size === 0;
    $("moveSelectedBtn").disabled = state.selectedIds.size === 0;
    if (!rows.length) {
      $("listRows").innerHTML = `
        <div class="pin-empty">
          <i data-lucide="bookmark-x"></i>
          <div>${state.search.trim() ? "没有匹配的书签" : "这个位置还没有书签"}</div>
        </div>`;
      return;
    }
    $("listRows").innerHTML = rows.map(renderListRow).join("");
  }

  function renderHeader() {
    $("headerBookmarkCount").textContent = `${state.bookmarks.length} 个书签`;
  }

  function renderCheckControls() {
    const brokenCount = state.bookmarks.filter((item) => item.link_status === "broken").length;
    $("brokenCount").textContent = brokenCount;
    $("brokenOnlyBtn").classList.toggle("active", state.brokenOnly);
    const checkedDates = state.bookmarks
      .map((item) => item.link_checked_at)
      .filter(Boolean)
      .sort();
    $("lastCheckedText").textContent = checkedDates.length
      ? `上次检查 ${String(checkedDates[checkedDates.length - 1]).slice(0, 16)}`
      : "";
    const button = $("checkLinksBtn");
    const status = state.checkStatus;
    button.disabled = Boolean(status?.running);
    const label = button.querySelector("span");
    if (label) {
      label.textContent = status?.running
        ? `检查中 ${status.completed}/${status.total}`
        : "检查链接";
    }
  }

  function render() {
    renderHeader();
    renderCheckControls();
    renderFolderTree();
    if (state.view === "nav") renderGrid();
    else renderList();
    lucide.createIcons();
  }

  async function loadAll() {
    const [bookmarks, folders] = await Promise.all([
      api("/api/bookmarks"),
      api("/api/bookmark-folders"),
    ]);
    state.bookmarks = bookmarks;
    state.folders = folders;
    initializeTreeExpansion();
    if (state.selectedFolder !== ALL_FOLDER &&
        state.selectedFolder !== UNFILED_FOLDER &&
        !folderById(state.selectedFolder)) {
      state.selectedFolder = ALL_FOLDER;
    }
    render();
  }

  function switchView(view) {
    state.view = view;
    try {
      localStorage.setItem("bookmarkView", view);
    } catch (err) {}
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
    $("navView").hidden = view !== "nav";
    $("listView").hidden = view !== "list";
    render();
    if (view === "nav" && state.selectedFolder !== ALL_FOLDER) {
      requestAnimationFrame(() => scrollToFolderSection(state.selectedFolder));
    }
  }

  function updateFolderHighlight(folderId = state.selectedFolder) {
    document.querySelectorAll(".pin-folder-row[data-folder]").forEach((row) => {
      row.classList.toggle(
        "active",
        String(row.dataset.folder) === String(folderId)
      );
    });
    $("currentScope").textContent =
      folderId === ALL_FOLDER
        ? "全部书签"
        : folderId === UNFILED_FOLDER
          ? IMPORT_PENDING_LABEL
          : (folderById(folderId)?.name || "全部书签");
  }

  function scrollToFolderSection(folderId) {
    const container = $("gridSections");
    state.suppressScrollSpy = true;
    if (folderId === ALL_FOLDER) {
      container.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      const section = document.getElementById(`bookmark-section-${folderId}`);
      if (section) {
        const targetTop = container.scrollTop +
          section.getBoundingClientRect().top -
          container.getBoundingClientRect().top;
        container.scrollTo({
          top: Math.max(0, targetTop - 6),
          behavior: "smooth",
        });
      }
    }
    clearTimeout(scrollToFolderSection.timer);
    scrollToFolderSection.timer = setTimeout(() => {
      state.suppressScrollSpy = false;
    }, 750);
  }

  function handleGridScroll() {
    if (state.suppressScrollSpy || state.scrollSpyFrame) return;
    state.scrollSpyFrame = requestAnimationFrame(() => {
      state.scrollSpyFrame = null;
      const container = $("gridSections");
      const sections = [...container.querySelectorAll("[data-section-folder]")];
      if (!sections.length) return;
      const scrollTop = container.scrollTop;
      const containerTop = container.getBoundingClientRect().top;
      const measured = sections.map((section, index) => {
        const top = section.getBoundingClientRect().top - containerTop + scrollTop;
        const bottom = top + section.getBoundingClientRect().height;
        return {
          section,
          index,
          top,
          bottom,
        };
      });
      const viewportBottom = scrollTop + container.clientHeight;
      const visible = measured
        .map((item) => ({
          ...item,
          visibleHeight: Math.max(
            0,
            Math.min(item.bottom, viewportBottom) - Math.max(item.top, scrollTop)
          ),
        }))
        .filter((item) => item.visibleHeight > 0)
        .sort((a, b) => b.visibleHeight - a.visibleHeight || a.index - b.index);
      let current = visible[0]?.section || sections[0];
      const folderId = current.dataset.sectionFolder;
      if (String(state.selectedFolder) !== String(folderId)) {
        state.selectedFolder = folderId;
        updateFolderHighlight(folderId);
      }
    });
  }

  function selectFolder(folderId, toggleIfParent = false) {
    const folder = folderById(folderId);
    if (toggleIfParent && folder && folderHasChildren(folder.id)) {
      toggleFolder(folder.id);
    }
    state.selectedFolder = folderId;
    state.selectedIds.clear();
    closeMobileFolders();
    renderFolderTree();
    updateFolderHighlight(folderId);
    lucide.createIcons();
    if (state.view === "list") {
      renderList();
      lucide.createIcons();
      return;
    }
    if (state.brokenOnly) {
      state.brokenOnly = false;
      renderCheckControls();
    }
    if (state.search) {
      state.search = "";
      $("searchInput").value = "";
      renderGrid();
    }
    requestAnimationFrame(() => scrollToFolderSection(folderId));
  }

  function toggleFolder(folderId) {
    const key = String(folderId);
    if (state.expandedFolders.has(key)) state.expandedFolders.delete(key);
    else state.expandedFolders.add(key);
    persistExpandedFolders();
  }

  function openMobileFolders() {
    $("folderPanel").classList.add("open");
    $("folderBackdrop").hidden = false;
  }

  function closeMobileFolders() {
    $("folderPanel").classList.remove("open");
    $("folderBackdrop").hidden = true;
  }

  function openBookmarkModal(item = null, defaultFolderId = null) {
    $("bookmarkForm").reset();
    $("bookmarkId").value = item ? item.id : "";
    $("bookmarkModalTitle").textContent = item ? "编辑书签" : "新增书签";
    $("bookmarkUrl").value = item ? item.url : "";
    $("bookmarkTitle").value = item ? item.title : "";
    $("bookmarkDescription").value = item ? item.description || "" : "";
    $("bookmarkFolder").innerHTML =
      `<option value="">${IMPORT_PENDING_LABEL}</option>` + folderOptions();
    const defaultFolder = item?.folder_id ||
      defaultFolderId ||
      (state.selectedFolder !== ALL_FOLDER && state.selectedFolder !== UNFILED_FOLDER
        ? state.selectedFolder
        : "");
    $("bookmarkFolder").value = defaultFolder ? String(defaultFolder) : "";
    openModal("bookmarkModal");
    setTimeout(() => $("bookmarkUrl").focus(), 0);
  }

  function openFolderModal(folder = null, parentId = null) {
    $("folderForm").reset();
    $("folderId").value = folder ? folder.id : "";
    $("folderModalTitle").textContent = folder ? "编辑文件夹" : "新建文件夹";
    $("folderName").value = folder ? folder.name : "";
    $("folderParent").innerHTML =
      '<option value="">根目录</option>' +
      folderOptions("", 0, folder ? descendantFolderIds(folder.id) : null);
    $("folderParent").value = folder?.parent_id
      ? String(folder.parent_id)
      : (parentId ? String(parentId) : "");
    openModal("folderModal");
    setTimeout(() => $("folderName").focus(), 0);
  }

  function openNoteModal(item) {
    $("noteForm").reset();
    $("noteBookmarkId").value = item.id;
    $("noteText").value = item.description || "";
    openModal("noteModal");
    setTimeout(() => $("noteText").focus(), 0);
  }

  function bookmarkById(id) {
    return state.bookmarks.find((item) => String(item.id) === String(id));
  }

  function deleteBookmark(item) {
    confirmDialog(`确认删除“${item.title || item.url}”？`, async () => {
      await api(`/api/bookmarks/${item.id}`, { method: "DELETE" });
      state.selectedIds.delete(String(item.id));
      showToast("书签已删除", "success", {
        label: "撤销",
        run: () => undoDeleteBookmarks([item]),
      });
      await loadAll();
    });
  }

  function deleteFolder(folder) {
    const directBookmarks = folderDirectBookmarks(folder.id);
    const childFolders = state.folders.filter((item) =>
      String(item.parent_id) === String(folder.id)
    );
    const detail = directBookmarks.length || childFolders.length
      ? `其中 ${directBookmarks.length} 个书签会移到${IMPORT_PENDING_LABEL}，${childFolders.length} 个子文件夹会移到根目录。`
      : "";
    confirmDialog(`确认删除文件夹“${folder.name}”？${detail}`, async () => {
      const restoreData = {
        name: folder.name,
        parent_id: folder.parent_id,
        sort_order: folder.sort_order,
        bookmarkIds: directBookmarks.map((item) => item.id),
        childFolderIds: childFolders.map((item) => item.id),
      };
      await api(`/api/bookmark-folders/${folder.id}`, { method: "DELETE" });
      if (String(state.selectedFolder) === String(folder.id)) {
        state.selectedFolder = ALL_FOLDER;
      }
      showToast("文件夹已删除", "success", {
        label: "撤销",
        run: () => undoDeleteFolder(restoreData),
      });
      await loadAll();
    });
  }

  async function undoDeleteFolder(data) {
    const created = await api("/api/bookmark-folders", {
      method: "POST",
      body: JSON.stringify({
        name: data.name,
        parent_id: data.parent_id,
        sort_order: data.sort_order,
      }),
    });
    await Promise.all(data.childFolderIds.map((id) => api(`/api/bookmark-folders/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ parent_id: created.id }),
    })));
    await Promise.all(data.bookmarkIds.map((id) => api(`/api/bookmarks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ folder_id: created.id }),
    })));
    showToast("文件夹已恢复");
    await loadAll();
  }

  async function deleteSelected() {
    const items = state.bookmarks.filter((item) =>
      state.selectedIds.has(String(item.id))
    );
    if (!items.length) return;
    confirmDialog(`确认删除选中的 ${items.length} 个书签？`, async () => {
      await Promise.all(items.map((item) =>
        api(`/api/bookmarks/${item.id}`, { method: "DELETE" })
      ));
      state.selectedIds.clear();
      showToast("选中的书签已删除", "success", {
        label: "撤销",
        run: () => undoDeleteBookmarks(items),
      });
      await loadAll();
    });
  }

  async function deleteBookmarkIds(ids) {
    const items = state.bookmarks.filter((item) =>
      ids.map(String).includes(String(item.id))
    );
    if (!items.length) return;
    await Promise.all(items.map((item) =>
      api(`/api/bookmarks/${item.id}`, { method: "DELETE" })
    ));
    showToast(`已删除 ${items.length} 个书签`);
    await loadAll();
  }

  async function deleteCleanupFolder(folderId) {
    await api(`/api/bookmark-folders/${folderId}`, { method: "DELETE" });
    showToast("空文件夹已删除");
    await loadAll();
    renderCleanup();
  }

  async function moveBookmarks(ids, folderId) {
    const cleanFolder = folderId === UNFILED_FOLDER ? null : folderId;
    await Promise.all(ids.map((id) => api(`/api/bookmarks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ folder_id: cleanFolder }),
    })));
    state.selectedIds.clear();
    showToast(`已移动 ${ids.length} 个书签`);
    await loadAll();
  }

  async function reorderBookmarks(folderKey, movingIds, targetId, placeAfter) {
    const section = [...document.querySelectorAll(".pin-grid-section")].find(
      (node) => String(node.dataset.sectionFolder) === String(folderKey)
    );
    if (!section) return;
    const currentIds = [...section.querySelectorAll("[data-bookmark-card]")]
      .map((node) => String(node.dataset.bookmarkCard));
    const moving = movingIds
      .map(String)
      .filter((id) => currentIds.includes(id));
    const cleanTargetId = String(targetId);
    if (!moving.length || moving.includes(cleanTargetId)) return;
    const remaining = currentIds.filter((id) => !moving.includes(id));
    const targetIndex = remaining.indexOf(cleanTargetId);
    if (targetIndex < 0) return;
    const ordered = remaining.slice();
    ordered.splice(targetIndex + (placeAfter ? 1 : 0), 0, ...moving);
    if (ordered.join(",") === currentIds.join(",")) return;

    const previousSort = state.sort;
    state.sort = "manual";
    syncSortButtons();
    try {
      await api("/api/bookmarks/reorder", {
        method: "POST",
        body: JSON.stringify({
          folder_id: folderKey === UNFILED_FOLDER ? null : folderKey,
          ids: ordered,
        }),
      });
    } catch (error) {
      state.sort = previousSort;
      syncSortButtons();
      throw error;
    }
    showToast("书签顺序已更新");
    await loadAll();
  }

  async function moveFolder(folderId, parentId) {
    await api(`/api/bookmark-folders/${folderId}`, {
      method: "PATCH",
      body: JSON.stringify({ parent_id: parentId || null }),
    });
    showToast("文件夹已移动");
    await loadAll();
  }

  async function reorderFolders(parentId, ids) {
    await api("/api/bookmark-folders/reorder", {
      method: "POST",
      body: JSON.stringify({
        parent_id: parentId || null,
        ids,
      }),
    });
    showToast("分类顺序已更新");
    await loadAll();
  }

  async function pinFolderTop(folderId) {
    const folder = folderById(folderId);
    if (!folder) return;
    const siblings = folderChildren(folder.parent_id);
    const ordered = [
      folder.id,
      ...siblings
        .filter((item) => String(item.id) !== String(folder.id))
        .map((item) => item.id),
    ];
    await reorderFolders(folder.parent_id, ordered);
  }

  function openMoveModal() {
    if (!state.selectedIds.size) return;
    $("moveFolder").innerHTML =
      `<option value="__unfiled__">${IMPORT_PENDING_LABEL}</option>` + folderOptions();
    openModal("moveModal");
  }

  function duplicateGroups() {
    const groups = new Map();
    state.bookmarks.forEach((item) => {
      const key = String(item.url || "").trim().toLowerCase();
      if (!key) return;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    });
    return [...groups.values()].filter((items) => items.length > 1);
  }

  function emptyFolders() {
    return state.folders.filter((folder) =>
      folderDirectBookmarks(folder.id).length === 0 &&
      state.folders.every((child) => String(child.parent_id || "") !== String(folder.id))
    );
  }

  function renderCleanup() {
    const groups = duplicateGroups();
    const empty = emptyFolders();
    const duplicateRows = groups.map((items) => {
      const duplicateItems = items.slice(1);
      return `
        <div class="pin-cleanup-row">
          <div class="pin-cleanup-main">
            <strong>${escapeHtml(items[0].title || items[0].url)}</strong>
            <span>${escapeHtml(items[0].url)} · ${items.length} 条</span>
          </div>
          <button type="button" data-cleanup-delete="${duplicateItems.map((item) => item.id).join(",")}">
            删除重复 ${duplicateItems.length}
          </button>
        </div>`;
    }).join("");
    const emptyRows = empty.map((folder) => `
      <div class="pin-cleanup-row">
        <div class="pin-cleanup-main">
          <strong>${escapeHtml(folder.name)}</strong>
          <span>${escapeHtml(folder.path || "空文件夹")}</span>
        </div>
        <button type="button" data-cleanup-folder="${folder.id}">删除</button>
      </div>
    `).join("");
    $("cleanupContent").innerHTML = `
      <section class="pin-cleanup-section">
        <h3>重复网址 ${groups.length ? `(${groups.length} 组)` : ""}</h3>
        ${duplicateRows || '<div class="pin-empty">没有发现重复网址</div>'}
      </section>
      <section class="pin-cleanup-section">
        <h3>空文件夹 ${empty.length ? `(${empty.length} 个)` : ""}</h3>
        ${emptyRows || '<div class="pin-empty">没有空文件夹</div>'}
      </section>`;
    openModal("cleanupModal");
    lucide.createIcons();
  }

  function closeContextMenu() {
    $("contextMenu").hidden = true;
    state.contextTarget = null;
  }

  function contextMenuButton(label, action, icon, danger = false) {
    return `<button type="button" data-context-action="${action}" class="${danger ? "danger" : ""}"><i data-lucide="${icon}"></i><span>${label}</span></button>`;
  }

  function openContextMenu(x, y, kind, id) {
    state.contextTarget = { kind, id: String(id) };
    const menu = $("contextMenu");
    if (kind === "folder") {
      const folder = folderById(id);
      if (!folder) return;
      menu.innerHTML = [
        contextMenuButton("新建书签", "folder-add-bookmark", "bookmark-plus"),
        contextMenuButton("新建子文件夹", "folder-add-subfolder", "folder-plus"),
        contextMenuButton("重命名", "folder-rename", "pencil"),
        contextMenuButton("置顶分类", "folder-pin-top", "arrow-up-to-line"),
        '<div class="pin-context-menu-sep"></div>',
        contextMenuButton("打开全部", "folder-open-all", "external-link"),
        contextMenuButton("删除文件夹", "folder-delete", "trash-2", true),
      ].join("");
    } else {
      const bookmark = bookmarkById(id);
      if (!bookmark) return;
      menu.innerHTML = [
        contextMenuButton("打开网址", "bookmark-open", "external-link"),
        contextMenuButton("复制网址", "bookmark-copy", "copy"),
        contextMenuButton("标记为有效链接", "bookmark-mark-valid", "circle-check"),
        contextMenuButton("编辑", "bookmark-edit", "pencil"),
        '<div class="pin-context-menu-sep"></div>',
        contextMenuButton("删除", "bookmark-delete", "trash-2", true),
      ].join("");
    }
    menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - 190))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - 260))}px`;
    menu.hidden = false;
    lucide.createIcons();
  }

  function folderBookmarkUrls(folderId) {
    const ids = descendantFolderIds(folderId);
    return state.bookmarks
      .filter((item) => item.folder_id && ids.has(String(item.folder_id)))
      .map((item) => item.url);
  }

  function openUrls(urls) {
    urls.forEach((url, index) => {
      setTimeout(() => window.open(url, "_blank", "noopener"), index * 120);
    });
  }

  async function undoDeleteBookmarks(items) {
    await Promise.all(items.map((item) => api("/api/bookmarks", {
      method: "POST",
      body: JSON.stringify({
        title: item.title,
        url: item.url,
        folder_id: item.folder_id,
        description: item.description,
      }),
    })));
    showToast(`已恢复 ${items.length} 个书签`);
    await loadAll();
  }

  async function importFirefoxBookmarks() {
    try {
      showToast("正在读取 Firefox 书签...");
      const result = await api("/api/bookmarks/firefox/import", {
        method: "POST",
        body: JSON.stringify({}),
      });
      showToast(
        `Firefox 导入完成：${result.imported} 个已放入${IMPORT_PENDING_LABEL}，跳过 ${result.skipped_duplicates}`
      );
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function refreshCheckStatus(finalize = false) {
    const status = await api("/api/bookmarks/check-links");
    state.checkStatus = status;
    render();
    if (status.running) {
      clearTimeout(state.checkPollTimer);
      state.checkPollTimer = setTimeout(() => {
        refreshCheckStatus(true).catch((error) => showToast(error.message, "error"));
      }, 1000);
      return;
    }
    if (finalize) {
      await loadAll();
      showToast(`检查完成：有效 ${status.valid}，失效 ${status.broken}`);
    }
  }

  async function startLinkCheck() {
    const targets = visibleBookmarks();
    if (!targets.length) {
      showToast("当前范围没有可检查的链接", "error");
      return;
    }
    try {
      const status = await api("/api/bookmarks/check-links", {
        method: "POST",
        body: JSON.stringify({
          ids: state.brokenOnly ? [] : targets.map((item) => item.id),
          broken_only: state.brokenOnly,
        }),
      });
      state.checkStatus = status;
      render();
      clearTimeout(state.checkPollTimer);
      state.checkPollTimer = setTimeout(() => {
        refreshCheckStatus(true).catch((error) => showToast(error.message, "error"));
      }, 700);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function bindEvents() {
    window.addEventListener("storage", (event) => {
      if (event.key === "errorSiteTheme" && event.newValue) applyTheme(event.newValue, false);
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (themePreference === "auto") applyTheme("auto", false);
    });
    window.addEventListener("resize", () => {
      clearTimeout(bindEvents.resizeTimer);
      bindEvents.resizeTimer = setTimeout(() => {
        if (state.view === "nav") {
          renderGrid();
          updateFolderHighlight();
          lucide.createIcons();
        }
      }, 160);
    });

    $("mobileMenuBtn").addEventListener("click", openMobileFolders);
    $("folderBackdrop").addEventListener("click", closeMobileFolders);
    $("newFolderBtn").addEventListener("click", () => openFolderModal());
    $("headerAddBookmark").addEventListener("click", () => openBookmarkModal());
    $("importFirefoxBtn").addEventListener("click", importFirefoxBookmarks);
    $("checkLinksBtn").addEventListener("click", startLinkCheck);
    $("cleanupBtn").addEventListener("click", renderCleanup);
    $("brokenOnlyBtn").addEventListener("click", () => {
      state.brokenOnly = !state.brokenOnly;
      state.selectedIds.clear();
      render();
    });

    document.querySelectorAll("[data-view]").forEach((button) => {
      button.addEventListener("click", () => switchView(button.dataset.view));
    });
    document.querySelectorAll("[data-sort]").forEach((button) => {
      button.addEventListener("click", () => setSort(button.dataset.sort));
    });

    $("searchInput").addEventListener("input", (event) => {
      state.search = event.target.value;
      state.selectedIds.clear();
      render();
    });
    $("gridSections").addEventListener("scroll", handleGridScroll, { passive: true });

    $("selectAllBtn").addEventListener("click", () => {
      const rows = visibleBookmarks();
      const allSelected = rows.length > 0 && rows.every((item) =>
        state.selectedIds.has(String(item.id))
      );
      if (allSelected) state.selectedIds.clear();
      else rows.forEach((item) => state.selectedIds.add(String(item.id)));
      renderList();
      lucide.createIcons();
    });
    $("deleteSelectedBtn").addEventListener("click", deleteSelected);
    $("moveSelectedBtn").addEventListener("click", openMoveModal);

    $("moveForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const ids = [...state.selectedIds];
      if (!ids.length) return;
      try {
        await moveBookmarks(ids, $("moveFolder").value);
        closeModal("moveModal");
      } catch (error) {
        showToast(error.message, "error");
      }
    });

    $("bookmarkForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = $("bookmarkId").value;
      const payload = {
        url: $("bookmarkUrl").value,
        title: $("bookmarkTitle").value,
        folder_id: $("bookmarkFolder").value || null,
        description: $("bookmarkDescription").value,
      };
      try {
        if (id) {
          await api(`/api/bookmarks/${id}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          });
          showToast("书签已更新");
        } else {
          const result = await api("/api/bookmarks", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          showToast(result.duplicate_count > 1 ? "已添加，当前存在重复网址" : "书签已添加");
        }
        closeModal("bookmarkModal");
        await loadAll();
      } catch (error) {
        showToast(error.message, "error");
      }
    });

    $("folderForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = $("folderId").value;
      const payload = {
        name: $("folderName").value,
        parent_id: $("folderParent").value || null,
      };
      try {
        if (id) {
          await api(`/api/bookmark-folders/${id}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          });
          showToast("文件夹已更新");
        } else {
          await api("/api/bookmark-folders", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          showToast("文件夹已创建");
        }
        closeModal("folderModal");
        await loadAll();
      } catch (error) {
        showToast(error.message, "error");
      }
    });

    $("noteForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = $("noteBookmarkId").value;
      try {
        await api(`/api/bookmarks/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ description: $("noteText").value }),
        });
        closeModal("noteModal");
        showToast("备注已更新");
        await loadAll();
      } catch (error) {
        showToast(error.message, "error");
      }
    });

    $("confirmOk").addEventListener("click", async () => {
      const action = state.confirmAction;
      state.confirmAction = null;
      closeModal("confirmModal");
      if (!action) return;
      try {
        await action();
      } catch (error) {
        showToast(error.message, "error");
      }
    });

    document.querySelectorAll(".pin-modal-close").forEach((button) => {
      button.addEventListener("click", () => {
        const modal = button.closest(".pin-modal-overlay");
        if (modal) modal.hidden = true;
      });
    });
    document.querySelectorAll(".pin-modal-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) overlay.hidden = true;
      });
    });

    document.addEventListener("contextmenu", (event) => {
      const bookmarkNode = event.target.closest("[data-bookmark-card], [data-list-row]");
      if (bookmarkNode) {
        event.preventDefault();
        const id = bookmarkNode.dataset.bookmarkCard || bookmarkNode.dataset.listRow;
        openContextMenu(event.clientX, event.clientY, "bookmark", id);
        return;
      }
      const folderNode = event.target.closest("[data-drop-folder]");
      if (folderNode &&
          folderNode.dataset.dropFolder &&
          folderNode.dataset.dropFolder !== UNFILED_FOLDER) {
        event.preventDefault();
        openContextMenu(event.clientX, event.clientY, "folder", folderNode.dataset.dropFolder);
      }
    });

    document.addEventListener("dragstart", (event) => {
      const bookmarkNode = event.target.closest("[data-bookmark-card], [data-list-row]");
      if (bookmarkNode) {
        const id = String(bookmarkNode.dataset.bookmarkCard || bookmarkNode.dataset.listRow);
        const ids = state.selectedIds.has(id) && state.selectedIds.size > 1
          ? [...state.selectedIds]
          : [id];
        const section = bookmarkNode.closest(".pin-grid-section");
        const sourceFolder = section?.dataset.sectionFolder || null;
        const reorder = Boolean(
          section &&
          !state.search.trim() &&
          !state.brokenOnly
        );
        event.dataTransfer.effectAllowed = "move";
        state.dragPayload = {
          kind: "bookmarks",
          ids,
          sourceFolder,
          reorder,
        };
        event.dataTransfer.setData("text/plain", JSON.stringify(state.dragPayload));
        document.querySelectorAll(
          ids.map((itemId) => `[data-bookmark-card="${itemId}"], [data-list-row="${itemId}"]`).join(",")
        ).forEach((node) => node.classList.add("dragging"));
        return;
      }
      const folderNode = event.target.closest("[data-folder]");
      const folderId = folderNode?.dataset.folder;
      if (folderNode && folderId &&
          folderId !== ALL_FOLDER &&
          folderId !== UNFILED_FOLDER) {
        event.dataTransfer.effectAllowed = "move";
        state.dragPayload = { kind: "folder", id: folderId };
        event.dataTransfer.setData("text/plain", JSON.stringify(state.dragPayload));
      }
    });

    document.addEventListener("dragover", (event) => {
      const payload = state.dragPayload;
      const bookmarkCard = event.target.closest(".pin-grid-section [data-bookmark-card]");
      if (bookmarkCard && payload?.kind === "bookmarks" && payload.reorder) {
        const section = bookmarkCard.closest(".pin-grid-section");
        const targetId = String(bookmarkCard.dataset.bookmarkCard);
        const movingIds = payload.ids.map(String);
        if (section?.dataset.sectionFolder === payload.sourceFolder &&
            !movingIds.includes(targetId)) {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          document.querySelectorAll(".drop-before, .drop-after").forEach((node) => {
            node.classList.remove("drop-before", "drop-after");
          });
          const rect = bookmarkCard.getBoundingClientRect();
          const ratio = (event.clientY - rect.top) / Math.max(1, rect.height);
          bookmarkCard.classList.add(ratio < 0.5 ? "drop-before" : "drop-after");
          return;
        }
      }
      const target = event.target.closest("[data-drop-folder]");
      if (!target) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      const container = target.closest(".pin-folder-row, .pin-grid-section");
      document.querySelectorAll(".drop-before, .drop-after").forEach((node) => {
        node.classList.remove("drop-before", "drop-after");
      });
      const folderRow = target.closest(".pin-folder-row");
      const destination = target.dataset.dropFolder;
      if (state.dragPayload?.kind === "folder" &&
          folderRow &&
          destination &&
          destination !== UNFILED_FOLDER &&
          destination !== state.dragPayload.id) {
        const rect = folderRow.getBoundingClientRect();
        const ratio = (event.clientY - rect.top) / Math.max(1, rect.height);
        folderRow.classList.remove("drag-over");
        folderRow.classList.add(ratio < 0.5 ? "drop-before" : "drop-after");
      } else {
        container?.classList.add("drag-over");
      }
    });

    document.addEventListener("dragleave", (event) => {
      const bookmarkCard = event.target.closest("[data-bookmark-card]");
      if (bookmarkCard) {
        if (event.relatedTarget && bookmarkCard.contains(event.relatedTarget)) return;
        bookmarkCard.classList.remove("drop-before", "drop-after");
        return;
      }
      const target = event.target.closest("[data-drop-folder]");
      if (target) {
        target.closest(".pin-folder-row, .pin-grid-section")
          ?.classList.remove("drag-over", "drop-before", "drop-after");
      }
    });

    document.addEventListener("drop", async (event) => {
      let payload = state.dragPayload;
      if (!payload) {
        try {
          payload = JSON.parse(event.dataTransfer.getData("text/plain"));
        } catch (error) {
          return;
        }
      }
      const bookmarkCard = event.target.closest(".pin-grid-section [data-bookmark-card]");
      if (bookmarkCard && payload?.kind === "bookmarks" && payload.reorder) {
        const section = bookmarkCard.closest(".pin-grid-section");
        const targetId = String(bookmarkCard.dataset.bookmarkCard);
        const dropBefore = bookmarkCard.classList.contains("drop-before");
        const dropAfter = bookmarkCard.classList.contains("drop-after");
        bookmarkCard.classList.remove("drop-before", "drop-after");
        if (section?.dataset.sectionFolder !== payload.sourceFolder) return;
        event.preventDefault();
        if (payload.ids.map(String).includes(targetId)) return;
        try {
          await reorderBookmarks(
            payload.sourceFolder,
            payload.ids,
            targetId,
            dropAfter && !dropBefore
          );
        } catch (error) {
          showToast(error.message, "error");
        }
        return;
      }
      const target = event.target.closest("[data-drop-folder]");
      if (!target) return;
      event.preventDefault();
      const container = target.closest(".pin-folder-row, .pin-grid-section");
      const dropBefore = container?.classList.contains("drop-before");
      const dropAfter = container?.classList.contains("drop-after");
      container?.classList.remove("drag-over", "drop-before", "drop-after");
      const destination = target.dataset.dropFolder;
      if (payload.kind === "bookmarks") {
        if (!destination && destination !== UNFILED_FOLDER) return;
        try {
          await moveBookmarks(payload.ids, destination);
        } catch (error) {
          showToast(error.message, "error");
        }
      }
      if (payload.kind === "folder") {
        if (destination === UNFILED_FOLDER || destination === payload.id) return;
        const targetFolder = folderById(destination);
        if ((dropBefore || dropAfter) && targetFolder) {
          if (descendantFolderIds(payload.id).has(String(targetFolder.parent_id || ""))) {
            showToast("不能移动到自己的子文件夹", "error");
            return;
          }
          const siblings = folderChildren(targetFolder.parent_id)
            .filter((folder) => String(folder.id) !== String(payload.id));
          const targetIndex = siblings.findIndex(
            (folder) => String(folder.id) === String(targetFolder.id)
          );
          siblings.splice(
            targetIndex + (dropAfter ? 1 : 0),
            0,
            folderById(payload.id)
          );
          try {
            await reorderFolders(
              targetFolder.parent_id,
              siblings.map((folder) => folder.id)
            );
          } catch (error) {
            showToast(error.message, "error");
          }
          return;
        }
        if (destination && descendantFolderIds(payload.id).has(String(destination))) {
          showToast("不能移动到自己的子文件夹", "error");
          return;
        }
        try {
          await moveFolder(payload.id, destination || null);
        } catch (error) {
          showToast(error.message, "error");
        }
      }
    });

    document.addEventListener("dragend", () => {
      state.dragPayload = null;
      document.querySelectorAll(".dragging, .drag-over, .drop-before, .drop-after").forEach((node) => {
        node.classList.remove("dragging", "drag-over", "drop-before", "drop-after");
      });
    });

    document.addEventListener("click", async (event) => {
      const contextAction = event.target.closest("[data-context-action]");
      if (contextAction) {
        const target = state.contextTarget;
        const action = contextAction.dataset.contextAction;
        closeContextMenu();
        if (!target) return;
        if (action === "bookmark-open") {
          const bookmark = bookmarkById(target.id);
          if (bookmark) window.open(bookmark.url, "_blank", "noopener");
        }
        if (action === "bookmark-copy") {
          const bookmark = bookmarkById(target.id);
          if (bookmark) {
            try {
              await navigator.clipboard.writeText(bookmark.url);
              showToast("网址已复制");
            } catch (error) {
              showToast("复制失败", "error");
            }
          }
        }
        if (action === "bookmark-mark-valid") {
          try {
            await api(`/api/bookmarks/${target.id}/mark-valid`, { method: "POST" });
            showToast("已标记为有效链接");
            await loadAll();
          } catch (error) {
            showToast(error.message, "error");
          }
        }
        if (action === "bookmark-edit") {
          const bookmark = bookmarkById(target.id);
          if (bookmark) openBookmarkModal(bookmark);
        }
        if (action === "bookmark-delete") {
          const bookmark = bookmarkById(target.id);
          if (bookmark) deleteBookmark(bookmark);
        }
        if (action === "folder-add-bookmark") openBookmarkModal(null, target.id);
        if (action === "folder-add-subfolder") openFolderModal(null, target.id);
        if (action === "folder-rename") {
          const folder = folderById(target.id);
          if (folder) openFolderModal(folder);
        }
        if (action === "folder-pin-top") {
          try {
            await pinFolderTop(target.id);
          } catch (error) {
            showToast(error.message, "error");
          }
        }
        if (action === "folder-open-all") {
          const urls = folderBookmarkUrls(target.id);
          if (!urls.length) showToast("这个文件夹没有书签", "error");
          else {
            openUrls(urls);
            showToast(`正在打开 ${urls.length} 个书签`);
          }
        }
        if (action === "folder-delete") {
          const folder = folderById(target.id);
          if (folder) deleteFolder(folder);
        }
        return;
      }
      const cleanupDelete = event.target.closest("[data-cleanup-delete]");
      if (cleanupDelete) {
        await deleteBookmarkIds(cleanupDelete.dataset.cleanupDelete.split(","));
        renderCleanup();
        return;
      }
      const cleanupFolder = event.target.closest("[data-cleanup-folder]");
      if (cleanupFolder) {
        await deleteCleanupFolder(cleanupFolder.dataset.cleanupFolder);
        return;
      }
      if (!event.target.closest("#contextMenu")) closeContextMenu();

      const actionButton = event.target.closest("[data-action]");
      if (actionButton) {
        const bookmark = bookmarkById(actionButton.dataset.id);
        const folder = folderById(actionButton.dataset.id);
        if (actionButton.dataset.action === "edit-bookmark" && bookmark) openBookmarkModal(bookmark);
        if (actionButton.dataset.action === "edit-note" && bookmark) openNoteModal(bookmark);
        if (actionButton.dataset.action === "delete-bookmark" && bookmark) deleteBookmark(bookmark);
        if (actionButton.dataset.action === "edit-folder" && folder) openFolderModal(folder);
        if (actionButton.dataset.action === "delete-folder" && folder) deleteFolder(folder);
        return;
      }

      const toggle = event.target.closest("[data-toggle-section]");
      if (toggle) {
        const key = toggle.dataset.toggleSection;
        if (state.collapsed.has(key)) state.collapsed.delete(key);
        else state.collapsed.add(key);
        renderGrid();
        lucide.createIcons();
        return;
      }

      const folderToggle = event.target.closest("[data-toggle-folder]");
      if (folderToggle) {
        toggleFolder(folderToggle.dataset.toggleFolder);
        renderFolderTree();
        lucide.createIcons();
        return;
      }

      const folderRow = event.target.closest("[data-folder]");
      if (folderRow) {
        selectFolder(folderRow.dataset.folder, true);
        return;
      }

      const checkbox = event.target.closest("[data-select-bookmark]");
      if (checkbox) {
        const id = String(checkbox.dataset.selectBookmark);
        if (checkbox.checked) state.selectedIds.add(id);
        else state.selectedIds.delete(id);
        renderList();
        lucide.createIcons();
        return;
      }

      if (event.target.closest("#emptyAddBookmark")) openBookmarkModal();
    });

    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        $("searchInput").focus();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a" &&
          state.view === "list" &&
          !event.target.closest("input, textarea, select")) {
        event.preventDefault();
        visibleBookmarks().forEach((item) => state.selectedIds.add(String(item.id)));
        renderList();
        lucide.createIcons();
      }
      if (event.key === "Escape") {
        closeAllModals();
        closeMobileFolders();
        closeContextMenu();
      }
      if ((event.key === "Delete" || event.key === "Backspace") &&
          state.view === "list" &&
          state.selectedIds.size &&
          !event.target.closest("input, textarea, select")) {
        event.preventDefault();
        deleteSelected();
      }
    });
  }

  async function init() {
    bindEvents();
    applyTheme(themePreference, false);
    try {
      let savedView = "nav";
      try {
        savedView = localStorage.getItem("bookmarkView") || "nav";
      } catch (err) {}
      const requestedView = new URLSearchParams(window.location.search).get("view");
      if (requestedView === "list" || requestedView === "nav") savedView = requestedView;
      state.view = savedView;
      await loadAll();
      switchView(savedView);
      const status = await api("/api/bookmarks/check-links");
      if (status.running) {
        state.checkStatus = status;
        render();
        refreshCheckStatus(true).catch((error) => showToast(error.message, "error"));
      }
    } catch (error) {
      showToast(error.message || "书签数据读取失败", "error");
      $("gridSections").innerHTML = '<div class="pin-empty">书签数据读取失败</div>';
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
