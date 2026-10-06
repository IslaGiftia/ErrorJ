(function () {
  const state = {
    view: "overview",
    assets: [],
    repairs: [],
    projects: [],
    editingAssetId: null,
    editingRepairId: null,
    assetCategory: "document",
    accountTab: "pending",
    adminUsers: [],
    permissionGroups: [],
    sensitiveWords: [],
    auditRows: [],
    isOwner: false,
    isAdmin: false,
    reviewFiles: [],
  };

  const $ = (id) => document.getElementById(id);
  let themePreference = "auto";
  try {
    themePreference = localStorage.getItem("errorSiteTheme") || "auto";
  } catch (err) {}

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatBytes(value) {
    const size = Number(value || 0);
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / (1024 * 1024)).toFixed(1) + " MB";
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return String(value);
    const pad = (number) => String(number).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function categoryLabel(category) {
    return {
      source: "源码与工程",
      firmware: "固件",
      document: "文档与原理图",
      image: "图片",
      other: "其他",
    }[category] || "其他";
  }

  function repairStatusLabel(status) {
    return {
      open: "待处理",
      repairing: "维修中",
      completed: "已完成",
      cancelled: "已取消",
    }[status] || "待处理";
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (err) {
      payload = null;
    }
    if (!response.ok) {
      throw new Error((payload && payload.error) || `请求失败（${response.status}）`);
    }
    return payload;
  }

  let toastTimer = null;
  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 2600);
  }

  function applyTheme(preference, save) {
    themePreference = preference;
    const dark =
      preference === "dark" ||
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

  function setView(view) {
    state.view = view;
    document.querySelectorAll(".wb-view").forEach((el) => {
      const active = el.id === `view-${view}`;
      el.hidden = !active;
      el.classList.toggle("active", active);
    });
    document.querySelectorAll(".wb-nav button").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
    const headerUpload = $("headerUploadBtn");
    if (headerUpload) headerUpload.hidden = view === "prompts";
    if (window.history && history.replaceState) {
      const target =
        view === "overview"
          ? location.pathname
          : location.pathname + "?view=" + encodeURIComponent(view);
      history.replaceState(null, "", target);
    }
    if (view === "assets" || view === "firmware") loadAssets();
    if (view === "repairs") loadRepairs();
    if (view === "accounts") loadAccounts();
    if (view === "review") loadReview();
  }

  function initialView() {
    const allowed = ["overview", "assets", "firmware", "repairs", "prompts", "accounts", "review"];
    const params = new URLSearchParams(location.search);
    const candidate = (params.get("view") || (location.hash || "").replace("#", "") || "overview").trim();
    if (candidate === "accounts" && !state.isAdmin) return "overview";
    if (candidate === "review" && !state.isAdmin) return "overview";
    return allowed.includes(candidate) ? candidate : "overview";
  }

  function projectOptions(selected, includeEmpty = true) {
    const empty = includeEmpty ? `<option value="">不关联</option>` : "";
    return empty + state.projects.map((project) =>
      `<option value="${project.id}"${String(project.id) === String(selected || "") ? " selected" : ""}>${escapeHtml(project.name)}</option>`
    ).join("");
  }

  function repairOptions(selected) {
    return `<option value="">不关联</option>` + state.repairs.map((repair) =>
      `<option value="${repair.id}"${String(repair.id) === String(selected || "") ? " selected" : ""}>${escapeHtml(repair.device_name)}</option>`
    ).join("");
  }

  function renderStats(summary) {
    const assets = summary.assets || {};
    const repairs = summary.repairs || {};
    $("overviewStats").innerHTML = [
      ["全部资料", assets.total || 0, `源码 ${assets.source || 0} · 文档 ${assets.document || 0}`],
      ["固件文件", assets.firmware || 0, "HEX / BIN / ELF"],
      ["维修记录", repairs.total || 0, `处理中 ${(repairs.open || 0) + (repairs.repairing || 0)}`],
      ["已完成", repairs.completed || 0, repairs.cancelled ? `已取消 ${repairs.cancelled}` : "维修完成记录"],
    ].map(([label, value, note]) => `
      <article class="wb-stat">
        <div class="wb-stat-label">${escapeHtml(label)}</div>
        <div class="wb-stat-value">${value}</div>
        <div class="wb-stat-note">${escapeHtml(note)}</div>
      </article>`).join("");
  }

  function renderRecentAssets(rows) {
    const wrap = $("recentAssets");
    wrap.innerHTML = rows.length
      ? rows.map((row) => `
        <div class="wb-recent-item">
          <span class="wb-recent-icon"><i data-lucide="${row.category === "firmware" ? "cpu" : "file"}"></i></span>
          <div class="wb-recent-main">
            <div class="wb-recent-title">${escapeHtml(row.title)}</div>
            <div class="wb-recent-meta">${escapeHtml(categoryLabel(row.category))} · ${formatBytes(row.size_bytes)} · ${formatTime(row.created_at)}</div>
          </div>
        </div>`).join("")
      : `<div class="wb-empty">还没有上传资料</div>`;
  }

  function renderRecentRepairs(rows) {
    const wrap = $("recentRepairs");
    wrap.innerHTML = rows.length
      ? rows.map((row) => `
        <div class="wb-recent-item">
          <span class="wb-recent-icon"><i data-lucide="wrench"></i></span>
          <div class="wb-recent-main">
            <div class="wb-recent-title">${escapeHtml(row.device_name)}</div>
            <div class="wb-recent-meta">${escapeHtml(repairStatusLabel(row.status))} · ${formatTime(row.updated_at)}</div>
          </div>
        </div>`).join("")
      : `<div class="wb-empty">还没有维修记录</div>`;
  }

  function renderAssetCards(rows, target, firmwareMode) {
    const container = $(target);
    if (!rows.length) {
      container.innerHTML = `<div class="wb-empty">${firmwareMode ? "还没有固件文件" : "还没有项目资料"}</div>`;
      return;
    }
    container.innerHTML = rows.map((row) => `
      <article class="wb-card">
        <div class="wb-card-main">
          <div class="wb-card-title">
            <strong>${escapeHtml(row.title)}</strong>
            <span class="wb-badge">${escapeHtml(categoryLabel(row.category))}</span>
          </div>
          <div class="wb-card-meta">
            ${row.version ? `<span>版本 ${escapeHtml(row.version)}</span>` : ""}
            ${row.target_chip ? `<span>芯片 ${escapeHtml(row.target_chip)}</span>` : ""}
            ${row.target_board ? `<span>开发板 ${escapeHtml(row.target_board)}</span>` : ""}
            ${row.project_name ? `<span>项目 ${escapeHtml(row.project_name)}</span>` : ""}
            <span>${escapeHtml(row.original_name || "文件")}</span>
            <span>${formatBytes(row.size_bytes)}</span>
            <span>${formatTime(row.created_at)}</span>
          </div>
        </div>
        <div class="wb-card-actions">
          ${row.flash_url ? `<a href="${escapeHtml(row.flash_url)}" target="_blank" rel="noopener" title="打开烧录链接"><button type="button"><i data-lucide="external-link"></i></button></a>` : ""}
          <a href="/api/workbench/assets/${row.id}/download" title="下载"><button type="button"><i data-lucide="download"></i></button></a>
          <button type="button" data-edit-asset="${row.id}" title="编辑"><i data-lucide="pencil"></i></button>
          <button type="button" data-delete-asset="${row.id}" title="删除"><i data-lucide="trash-2"></i></button>
        </div>
      </article>`).join("");
  }

  function renderRepairs(rows) {
    const container = $("repairList");
    if (!rows.length) {
      container.innerHTML = `<div class="wb-empty">还没有维修记录</div>`;
      return;
    }
    container.innerHTML = rows.map((row) => `
      <article class="wb-card">
        <div class="wb-card-main">
          <div class="wb-card-title">
            <strong>${escapeHtml(row.device_name)}</strong>
            <span class="wb-badge status-${escapeHtml(row.status)}">${escapeHtml(repairStatusLabel(row.status))}</span>
          </div>
          <div class="wb-card-meta">
            ${row.serial_number ? `<span>编号 ${escapeHtml(row.serial_number)}</span>` : ""}
            ${row.project_name ? `<span>项目 ${escapeHtml(row.project_name)}</span>` : ""}
            ${row.cost !== null && row.cost !== undefined ? `<span>费用 ${Number(row.cost).toFixed(2)}</span>` : ""}
            <span>${row.asset_count || 0} 个附件</span>
            <span>更新 ${formatTime(row.updated_at)}</span>
          </div>
          ${row.fault ? `<div class="wb-recent-meta">故障：${escapeHtml(row.fault)}</div>` : ""}
        </div>
        <div class="wb-card-actions">
          <button type="button" data-edit-repair="${row.id}" title="编辑"><i data-lucide="pencil"></i></button>
          <button type="button" data-delete-repair="${row.id}" title="删除"><i data-lucide="trash-2"></i></button>
        </div>
      </article>`).join("");
  }

  async function loadSummary() {
    const summary = await api("/api/workbench/summary");
    renderStats(summary);
    renderRecentAssets(summary.recent_assets || []);
    renderRecentRepairs(summary.recent_repairs || []);
    if (window.lucide) lucide.createIcons();
  }

  async function loadAssets() {
    const firmwareMode = state.view === "firmware";
    const search = firmwareMode ? $("firmwareSearch").value : $("assetSearch").value;
    const project = firmwareMode ? $("firmwareProject").value : $("assetProject").value;
    const category = firmwareMode ? "firmware" : $("assetCategory").value;
    const params = new URLSearchParams();
    if (search) params.set("q", search);
    if (project) params.set("project_id", project);
    if (category) params.set("category", category);
    state.assets = await api("/api/workbench/assets?" + params.toString());
    renderAssetCards(
      state.assets,
      firmwareMode ? "firmwareList" : "assetList",
      firmwareMode
    );
    if (window.lucide) lucide.createIcons();
  }

  async function loadRepairs() {
    const params = new URLSearchParams();
    const search = $("repairSearch").value;
    const status = $("repairStatus").value;
    if (search) params.set("q", search);
    if (status) params.set("status", status);
    state.repairs = await api("/api/workbench/repairs?" + params.toString());
    renderRepairs(state.repairs);
    syncProjectSelects();
    if (window.lucide) lucide.createIcons();
  }

  function syncProjectSelects() {
    ["assetProject", "firmwareProject", "assetFormProject", "repairProject"].forEach((id) => {
      const el = $(id);
      const value = el.value;
      el.innerHTML = projectOptions(value);
    });
    $("assetFormRepair").innerHTML = repairOptions($("assetFormRepair").value);
  }

  function openAssetModal(category, asset) {
    state.editingAssetId = asset ? asset.id : null;
    state.assetCategory = category || (asset && asset.category) || "document";
    $("assetModalTitle").textContent = asset ? "编辑文件信息" : (state.assetCategory === "firmware" ? "上传固件" : "上传文件");
    $("assetFileField").hidden = Boolean(asset);
    $("assetFile").required = !asset;
    $("assetFile").value = "";
    $("assetFileLabel").textContent = "选择文件";
    $("assetTitle").value = asset ? asset.title || "" : "";
    $("assetFormCategory").value = state.assetCategory;
    $("assetFormProject").innerHTML = projectOptions(asset ? asset.project_id : "");
    $("assetFormRepair").innerHTML = repairOptions(asset ? asset.repair_id : "");
    $("assetVersion").value = asset ? asset.version || "" : "";
    $("assetChip").value = asset ? asset.target_chip || "" : "";
    $("assetBoard").value = asset ? asset.target_board || "" : "";
    $("assetFlashUrl").value = asset ? asset.flash_url || "" : "";
    $("assetNotes").value = asset ? asset.notes || "" : "";
    $("assetModal").hidden = false;
    if (window.lucide) lucide.createIcons();
  }

  function openRepairModal(repair) {
    state.editingRepairId = repair ? repair.id : null;
    $("repairModalTitle").textContent = repair ? "编辑维修记录" : "新增维修记录";
    $("repairDevice").value = repair ? repair.device_name || "" : "";
    $("repairSerial").value = repair ? repair.serial_number || "" : "";
    $("repairProject").innerHTML = projectOptions(repair ? repair.project_id : "");
    $("repairFormStatus").value = repair ? repair.status || "open" : "open";
    $("repairStarted").value = repair ? String(repair.started_at || "").slice(0, 10) : "";
    $("repairFinished").value = repair ? String(repair.finished_at || "").slice(0, 10) : "";
    $("repairCost").value = repair && repair.cost !== null ? repair.cost : "";
    $("repairFault").value = repair ? repair.fault || "" : "";
    $("repairDiagnosis").value = repair ? repair.diagnosis || "" : "";
    $("repairAction").value = repair ? repair.action || "" : "";
    $("repairNotes").value = repair ? repair.notes || "" : "";
    $("repairModal").hidden = false;
    if (window.lucide) lucide.createIcons();
  }

  function closeModal(id) {
    $(id).hidden = true;
  }

  function readFileBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        resolve(result.slice(result.indexOf(",") + 1));
      };
      reader.onerror = () => reject(new Error("读取文件失败"));
      reader.readAsDataURL(file);
    });
  }

  function assetFormPayload() {
    return {
      title: $("assetTitle").value.trim(),
      category: $("assetFormCategory").value,
      project_id: $("assetFormProject").value || null,
      repair_id: $("assetFormRepair").value || null,
      version: $("assetVersion").value.trim(),
      target_chip: $("assetChip").value.trim(),
      target_board: $("assetBoard").value.trim(),
      flash_url: $("assetFlashUrl").value.trim(),
      notes: $("assetNotes").value.trim(),
    };
  }

  async function submitAsset(event) {
    event.preventDefault();
    const button = $("assetSubmitBtn");
    button.disabled = true;
    try {
      const payload = assetFormPayload();
      if (state.editingAssetId) {
        await api(`/api/workbench/assets/${state.editingAssetId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        toast("文件信息已更新");
      } else {
        const file = $("assetFile").files[0];
        if (!file) throw new Error("请选择文件");
        payload.file_name = file.name;
        payload.data_base64 = await readFileBase64(file);
        await api("/api/workbench/assets", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        toast("文件已上传");
      }
      closeModal("assetModal");
      await Promise.all([loadSummary(), loadAssets()]);
    } catch (err) {
      toast(err.message || "保存失败");
    } finally {
      button.disabled = false;
    }
  }

  async function submitRepair(event) {
    event.preventDefault();
    const payload = {
      device_name: $("repairDevice").value.trim(),
      serial_number: $("repairSerial").value.trim(),
      project_id: $("repairProject").value || null,
      status: $("repairFormStatus").value,
      started_at: $("repairStarted").value,
      finished_at: $("repairFinished").value,
      cost: $("repairCost").value,
      fault: $("repairFault").value.trim(),
      diagnosis: $("repairDiagnosis").value.trim(),
      action: $("repairAction").value.trim(),
      notes: $("repairNotes").value.trim(),
    };
    try {
      if (state.editingRepairId) {
        await api(`/api/workbench/repairs/${state.editingRepairId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        toast("维修记录已更新");
      } else {
        await api("/api/workbench/repairs", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        toast("维修记录已创建");
      }
      closeModal("repairModal");
      await Promise.all([loadSummary(), loadRepairs()]);
    } catch (err) {
      toast(err.message || "保存失败");
    }
  }

  async function deleteAsset(id) {
    const asset = state.assets.find((item) => item.id === id);
    if (!asset || !window.confirm(`删除「${asset.title}」及其文件？`)) return;
    try {
      await api(`/api/workbench/assets/${id}`, { method: "DELETE" });
      toast("文件已删除");
      await Promise.all([loadSummary(), loadAssets()]);
    } catch (err) {
      toast(err.message || "删除失败");
    }
  }

  async function deleteRepair(id) {
    const repair = state.repairs.find((item) => item.id === id);
    if (!repair || !window.confirm(`删除「${repair.device_name}」的维修记录？`)) return;
    try {
      await api(`/api/workbench/repairs/${id}`, { method: "DELETE" });
      toast("维修记录已删除");
      await Promise.all([loadSummary(), loadRepairs()]);
    } catch (err) {
      toast(err.message || "删除失败");
    }
  }

  function bindEvents() {
    document.querySelectorAll(".wb-nav button").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.view));
    });
    document.querySelectorAll("[data-go-view]").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.goView));
    });
    $("headerUploadBtn").addEventListener("click", () => openAssetModal("document"));
    document.querySelectorAll("[data-upload-category]").forEach((button) => {
      button.addEventListener("click", () => openAssetModal(button.dataset.uploadCategory));
    });
    $("newRepairBtn").addEventListener("click", () => openRepairModal(null));
    document.querySelectorAll("[data-close-modal]").forEach((button) => {
      button.addEventListener("click", () => closeModal(button.dataset.closeModal));
    });
    document.querySelectorAll(".wb-modal-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) overlay.hidden = true;
      });
    });
    $("assetForm").addEventListener("submit", submitAsset);
    $("repairForm").addEventListener("submit", submitRepair);
    $("assetFile").addEventListener("change", () => {
      const file = $("assetFile").files[0];
      $("assetFileLabel").textContent = file ? file.name : "选择文件";
      if (file && !$("assetTitle").value) {
        $("assetTitle").value = file.name.replace(/\.[^.]+$/, "");
      }
    });
    ["assetSearch", "assetCategory", "assetProject"].forEach((id) => {
      $(id).addEventListener(id === "assetSearch" ? "input" : "change", loadAssets);
    });
    ["firmwareSearch", "firmwareProject"].forEach((id) => {
      $(id).addEventListener(id === "firmwareSearch" ? "input" : "change", loadAssets);
    });
    ["repairSearch", "repairStatus"].forEach((id) => {
      $(id).addEventListener(id === "repairSearch" ? "input" : "change", loadRepairs);
    });
    document.addEventListener("click", (event) => {
      const editAsset = event.target.closest("[data-edit-asset]");
      if (editAsset) {
        const asset = state.assets.find((item) => item.id === Number(editAsset.dataset.editAsset));
        if (asset) openAssetModal(asset.category, asset);
        return;
      }
      const deleteAssetBtn = event.target.closest("[data-delete-asset]");
      if (deleteAssetBtn) {
        deleteAsset(Number(deleteAssetBtn.dataset.deleteAsset));
        return;
      }
      const editRepair = event.target.closest("[data-edit-repair]");
      if (editRepair) {
        const repair = state.repairs.find((item) => item.id === Number(editRepair.dataset.editRepair));
        if (repair) openRepairModal(repair);
        return;
      }
      const deleteRepairBtn = event.target.closest("[data-delete-repair]");
      if (deleteRepairBtn) {
        deleteRepair(Number(deleteRepairBtn.dataset.deleteRepair));
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        document.querySelectorAll(".wb-modal-overlay").forEach((overlay) => {
          overlay.hidden = true;
        });
      }
    });
  }

  async function boot() {
    applyTheme(themePreference, false);
    if (window.lucide) lucide.createIcons();
    bindEvents();
    bindAccountEvents();
    bindReviewEvents();
    try {
      const status = await api("/api/auth/status");
      state.isOwner = Boolean(status.owner);
      state.isAdmin = Boolean(status.admin || status.owner);
      const accountsNav = document.querySelector('[data-view="accounts"]');
      if (accountsNav) accountsNav.hidden = !state.isAdmin;
      const reviewNav = document.querySelector('[data-view="review"]');
      if (reviewNav) reviewNav.hidden = !state.isAdmin;
      if (state.isAdmin) {
        setPendingBadge(status.pending_users || 0);
        setReviewBadge(status.pending_attachments || 0);
      }
    } catch (err) {}
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && state.isAdmin) refreshNavBadges();
    });
    try {
      state.projects = await api("/api/projects");
      syncProjectSelects();
    } catch (err) {
      toast(err.message || "工作台数据加载失败");
    }
    await Promise.allSettled([loadSummary(), loadAssets(), loadRepairs()]);
    setView(initialView());
  }

  // ---------- 账号与权限 ----------
  const ACCOUNT_STATUS_LABELS = {
    pending: "待审核",
    approved: "正常",
    rejected: "已拒绝",
    disabled: "已停用",
  };

  const AUDIT_ACTION_LABELS = {
    register: "提交注册申请",
    user_approve: "同意注册",
    user_reject: "拒绝注册",
    user_disable: "停用账号",
    user_enable: "启用账号",
    grant: "发放权限",
    revoke: "收回权限",
    set_nickname: "管理员修改昵称",
    nickname_change: "用户修改昵称",
    reset_password: "重置密码",
    delete_user: "删除账号",
    add_sensitive_word: "新增敏感词",
    remove_sensitive_word: "删除敏感词",
  };

  function permissionLabel(key) {
    for (const group of state.permissionGroups) {
      for (const item of group.items || []) {
        if (item.key === key) return item.label;
      }
    }
    return key;
  }

  async function refreshNavBadges() {
    try {
      const status = await api("/api/auth/status");
      if (!(status.admin || status.owner)) return;
      setPendingBadge(status.pending_users || 0);
      setReviewBadge(status.pending_attachments || 0);
    } catch (err) {}
  }

  function setPendingBadge(count) {
    const value = Number(count) || 0;
    const nav = $("accountsNavBadge");
    const panel = $("pendingCount");
    if (nav) {
      nav.hidden = value <= 0;
      nav.textContent = value > 99 ? "99+" : String(value);
    }
    if (panel) panel.textContent = String(value);
  }

  async function loadAccounts() {
    const panel = $("accountPanel");
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api("/api/admin/users");
      state.adminUsers = data.users || [];
      setPendingBadge(data.pending || 0);
      if (!state.permissionGroups.length) {
        const catalog = await api("/api/admin/permissions");
        state.permissionGroups = catalog.groups || [];
      }
      await loadAccountTab(state.accountTab, true);
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadAccountTab(tab, skipUsers) {
    state.accountTab = tab;
    document.querySelectorAll("#accountTabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.accountTab === tab);
    });
    const panel = $("accountPanel");
    if (tab === "pending" || tab === "users") {
      if (!skipUsers) {
        const data = await api("/api/admin/users");
        state.adminUsers = data.users || [];
        setPendingBadge(data.pending || 0);
      }
      panel.innerHTML = tab === "pending" ? pendingHtml() : usersHtml();
    } else if (tab === "words") {
      const data = await api("/api/admin/sensitive-words");
      state.sensitiveWords = data.words || [];
      state.wordCategories = data.categories || [];
      panel.innerHTML = wordsHtml(data);
    } else if (tab === "notify") {
      const data = await api("/api/admin/notify");
      state.notifySettings = data;
      panel.innerHTML = notifyHtml(data);
    } else {
      state.auditRows = await api("/api/admin/audit?limit=200");
      panel.innerHTML = auditHtml();
    }
    if (window.lucide) lucide.createIcons();
  }

  function pendingHtml() {
    const pending = state.adminUsers.filter((user) => user.status === "pending");
    if (!pending.length) {
      return '<div class="wb-empty">没有待审核的注册申请。</div>';
    }
    return (
      '<div class="wb-user-list">' +
      pending
        .map(
          (user) => `
        <article class="wb-user-card">
          <div class="wb-user-main">
            <div class="wb-user-title">
              <strong>${escapeHtml(user.nickname || user.username)}</strong>
              <span class="wb-chip">待审核</span>
            </div>
            <div class="wb-user-meta">
              用户名 ${escapeHtml(user.username)} · 申请于 ${formatTime(user.created_at)}
            </div>
          </div>
          <div class="wb-user-actions">
            <button class="wb-btn wb-btn-primary" type="button" data-user-status="approve" data-user-id="${user.id}">
              <i data-lucide="check"></i><span>同意</span>
            </button>
            <button class="wb-btn" type="button" data-user-status="reject" data-user-id="${user.id}">
              <i data-lucide="x"></i><span>拒绝</span>
            </button>
          </div>
        </article>`
        )
        .join("") +
      "</div>"
    );
  }

  function usersHtml() {
    if (!state.adminUsers.length) {
      return '<div class="wb-empty">还没有注册账号。</div>';
    }
    const groups = state.permissionGroups
      .map((group) => {
        const items = (group.items || [])
          .map((item) => {
            const isAdminPerm = item.key === "system:admin";
            return `<label class="wb-perm-item"><input type="checkbox" data-perm="${item.key}"${
              isAdminPerm && !state.isOwner ? " disabled" : ""
            }><span>${escapeHtml(item.label)}</span></label>`;
          })
          .join("");
        return `<div class="wb-perm-group"><h4>${escapeHtml(group.label)}</h4><div class="wb-perm-items">${items}</div></div>`;
      })
      .join("");
    return (
      '<div class="wb-user-list">' +
      state.adminUsers
        .map((user) => {
          const permissions = new Set(user.permissions || []);
          const statusLabel = ACCOUNT_STATUS_LABELS[user.status] || user.status;
          const actions = [];
          if (user.status === "approved") {
            actions.push(
              `<button class="wb-btn" type="button" data-user-status="disable" data-user-id="${user.id}"><i data-lucide="ban"></i><span>停用</span></button>`
            );
          } else {
            actions.push(
              `<button class="wb-btn" type="button" data-user-status="approve" data-user-id="${user.id}"><i data-lucide="check"></i><span>通过</span></button>`
            );
          }
          actions.push(
            `<button class="wb-btn" type="button" data-user-reset="${user.id}"><i data-lucide="key-round"></i><span>重置密码</span></button>`,
            `<button class="wb-btn" type="button" data-user-nickname="${user.id}"><i data-lucide="pencil"></i><span>改昵称</span></button>`,
            `<button class="wb-btn wb-btn-danger" type="button" data-user-delete="${user.id}"><i data-lucide="trash-2"></i><span>删除</span></button>`
          );
          const permHtml = groups
            .replace(/data-perm="([^"]+)"/g, (match, key) =>
              permissions.has(key) ? `${match} checked` : match
            );
          return `
        <article class="wb-user-card" data-user-card="${user.id}">
          <div class="wb-user-head">
            <div class="wb-user-main">
              <div class="wb-user-title">
                <strong>${escapeHtml(user.nickname || user.username)}</strong>
                <span class="wb-chip wb-chip-${user.status}">${statusLabel}</span>
                ${user.is_admin ? '<span class="wb-chip wb-chip-admin">管理员</span>' : ""}
              </div>
              <div class="wb-user-meta">
                用户名 ${escapeHtml(user.username)} · 注册 ${formatTime(user.created_at)}
                ${user.last_login_at ? ` · 最近登录 ${formatTime(user.last_login_at)}` : ""}
              </div>
            </div>
            <div class="wb-user-actions">${actions.join("")}</div>
          </div>
          <details class="wb-user-perms">
            <summary>权限设置（已授予 ${permissions.size} 项）</summary>
            <div class="wb-perm-groups">${permHtml}</div>
          </details>
          <div class="wb-user-reset" data-reset-row="${user.id}" hidden>
            <input type="password" minlength="8" maxlength="128" placeholder="新的登录密码（至少 8 位）" data-reset-input="${user.id}">
            <button class="wb-btn wb-btn-primary" type="button" data-reset-save="${user.id}">保存密码</button>
          </div>
          <div class="wb-user-reset" data-nickname-row="${user.id}" hidden>
            <input maxlength="16" placeholder="新的昵称（2-16 位）" data-nickname-input="${user.id}">
            <button class="wb-btn wb-btn-primary" type="button" data-nickname-save="${user.id}">保存昵称</button>
          </div>
        </article>`;
        })
        .join("") +
      "</div>"
    );
  }

  function wordsHtml(data) {
    const counts = data.counts || {};
    const categories = data.categories || [];
    const words = data.words || [];
    const chips = categories
      .map(
        (category) =>
          `<span class="wb-chip">${escapeHtml(category)} ${counts[category] || 0}</span>`
      )
      .join("");
    const list = words.length
      ? words
          .map(
            (row) => `
        <span class="wb-word">
          ${escapeHtml(row.word)}
          <em>${escapeHtml(row.category)}</em>
          <button type="button" data-word-delete="${row.id}" title="删除">×</button>
        </span>`
          )
          .join("")
      : '<span class="wb-empty">词库是空的。</span>';
    return `
      <div class="wb-panel">
        <div class="wb-panel-head"><h2>敏感词库</h2><div class="wb-tags">${chips}</div></div>
        <div class="wb-word-form">
          <input id="newWordInput" maxlength="20" placeholder="新增敏感词，例如：赌博">
          <select id="newWordCategory">
            ${categories
              .map((category) => `<option value="${category}">${category}</option>`)
              .join("")}
          </select>
          <button class="wb-btn wb-btn-primary" type="button" id="addWordBtn">
            <i data-lucide="plus"></i><span>添加</span>
          </button>
        </div>
        <p class="wb-hint">命中规则：忽略大小写、全角半角和空格符号干扰；昵称命中直接拒绝，留言命中直接拒绝。</p>
        <div class="wb-word-list">${list}</div>
      </div>
      <div class="wb-panel">
        <div class="wb-panel-head"><h2>测试</h2></div>
        <textarea id="wordTestInput" rows="3" placeholder="输入一段文字，看看会命中哪些词"></textarea>
        <div class="wb-inline">
          <button class="wb-btn" type="button" id="wordTestBtn"><i data-lucide="search"></i><span>测试</span></button>
          <span id="wordTestResult" class="wb-hint"></span>
        </div>
      </div>`;
  }

  function auditHtml() {
    if (!state.auditRows.length) {
      return '<div class="wb-empty">还没有审计记录。</div>';
    }
    return (
      '<div class="wb-audit-list">' +
      state.auditRows
        .map(
          (row) => `
      <article class="wb-audit-row">
        <span class="wb-audit-time">${formatTime(row.created_at)}</span>
        <span class="wb-audit-actor">${escapeHtml(row.actor_name || "系统")}</span>
        <span class="wb-audit-action">${escapeHtml(AUDIT_ACTION_LABELS[row.action] || row.action)}</span>
        <span class="wb-audit-target">${escapeHtml(row.target_name || "")}</span>
        <span class="wb-audit-detail">${escapeHtml(row.detail || "")}</span>
      </article>`
        )
        .join("") +
      "</div>"
    );
  }

  function notifyHtml(data) {
    const channels = data.channels || [];
    const eventOptions = data.event_options || [];
    const activeEvents = new Set(data.events || []);
    const logs = data.log || [];
    const currentChannel = channels.find((item) => item.key === data.channel) || channels[0] || {};
    const eventItems = eventOptions
      .map(
        (item) =>
          `<label class="wb-perm-item wb-notify-event"><input type="checkbox" data-notify-event="${item.key}"${
            activeEvents.has(item.key) ? " checked" : ""
          }><span>${escapeHtml(item.label)}</span></label>`
      )
      .join("");
    const logRows = logs.length
      ? logs
          .map(
            (row) => `
        <article class="wb-audit-row">
          <span class="wb-audit-time">${formatTime(row.created_at)}</span>
          <span class="wb-audit-actor">${escapeHtml(row.channel || "")}</span>
          <span class="wb-audit-action">${row.status === "ok" ? "成功" : "失败"}</span>
          <span class="wb-audit-target">${escapeHtml(row.title || "")}</span>
          <span class="wb-audit-detail">${escapeHtml(row.detail || "")}</span>
        </article>`
          )
          .join("")
      : '<div class="wb-empty">还没有推送记录。</div>';
    return `
      <div class="wb-panel">
        <div class="wb-panel-head">
          <h2>推送通知</h2>
          <span class="wb-chip${data.enabled ? " wb-chip-approved" : ""}">${data.enabled ? "已开启" : "已关闭"}</span>
        </div>
        <div class="wb-panel-body">
          <p class="wb-hint">新注册申请、待审核附件、新留言会推送到你的手机或群机器人；站内的工作台呼吸提醒仍然保留。</p>
          <div class="wb-notify-grid">
            <label class="wb-perm-item"><input type="checkbox" id="notifyEnabled"${data.enabled ? " checked" : ""}><span>开启通知</span></label>
            <label class="wb-field"><span>渠道</span>
              <select id="notifyChannel">
                ${channels
                  .map(
                    (item) =>
                      `<option value="${item.key}"${item.key === data.channel ? " selected" : ""}>${escapeHtml(item.label)}</option>`
                  )
                  .join("")}
              </select>
            </label>
            <label class="wb-field wb-field-wide"><span>Webhook 地址</span>
              <input id="notifyUrl" type="text" autocomplete="off" placeholder="${
                data.url_set ? "已保存，留空表示不修改" : "粘贴机器人 Webhook 地址"
              }">
            </label>
          </div>
          <p class="wb-hint" id="notifyHint">${escapeHtml(currentChannel.hint || "")}${
            data.url_set ? ` · 当前：${escapeHtml(data.url_masked || "")}` : ""
          }</p>
          <div class="wb-perm-items wb-notify-events">
            <h4>推送哪些事件</h4>
            ${eventItems}
          </div>
          <div class="wb-inline">
            <button class="wb-btn wb-btn-primary" type="button" id="notifySave">
              <i data-lucide="check"></i><span>保存设置</span>
            </button>
            <button class="wb-btn" type="button" id="notifyTest">
              <i data-lucide="send"></i><span>发送测试通知</span>
            </button>
            ${
              data.url_set
                ? '<button class="wb-btn wb-btn-danger" type="button" id="notifyClearUrl"><i data-lucide="trash-2"></i><span>清除地址</span></button>'
                : ""
            }
            <span class="wb-hint" id="notifyResult"></span>
          </div>
        </div>
      </div>
      <div class="wb-panel">
        <div class="wb-panel-head"><h2>最近通知</h2></div>
        <div class="wb-panel-body">
          <div class="wb-audit-list">${logRows}</div>
        </div>
      </div>`;
  }

  function notifyFormPayload() {
    const panel = $("accountPanel");
    const enabled = panel.querySelector("#notifyEnabled");
    const channel = panel.querySelector("#notifyChannel");
    const url = panel.querySelector("#notifyUrl");
    const events = Array.from(panel.querySelectorAll("[data-notify-event]"))
      .filter((box) => box.checked)
      .map((box) => box.dataset.notifyEvent);
    return {
      enabled: Boolean(enabled && enabled.checked),
      channel: channel ? channel.value : "wecom",
      url: url ? url.value.trim() : "",
      events,
    };
  }

  function bindAccountEvents() {
    const tabs = $("accountTabs");
    if (tabs) {
      tabs.addEventListener("click", (event) => {
        const button = event.target.closest("[data-account-tab]");
        if (!button) return;
        loadAccountTab(button.dataset.accountTab).catch((err) => toast(err.message));
      });
    }
    const refresh = $("accountRefreshBtn");
    if (refresh) {
      refresh.addEventListener("click", () => {
        loadAccounts().catch((err) => toast(err.message));
      });
    }
    const panel = $("accountPanel");
    if (!panel) return;
    panel.addEventListener("click", async (event) => {
      const statusBtn = event.target.closest("[data-user-status]");
      if (statusBtn) {
        try {
          await api(`/api/admin/users/${statusBtn.dataset.userId}/status`, {
            method: "POST",
            body: JSON.stringify({ action: statusBtn.dataset.userStatus }),
          });
          toast("已更新账号状态");
          await loadAccounts();
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const resetBtn = event.target.closest("[data-user-reset]");
      if (resetBtn) {
        const row = panel.querySelector(`[data-reset-row="${resetBtn.dataset.userReset}"]`);
        if (row) row.hidden = !row.hidden;
        return;
      }
      const resetSave = event.target.closest("[data-reset-save]");
      if (resetSave) {
        const id = resetSave.dataset.resetSave;
        const input = panel.querySelector(`[data-reset-input="${id}"]`);
        const value = input ? input.value : "";
        if (value.length < 8) {
          toast("密码至少 8 位");
          return;
        }
        try {
          await api(`/api/admin/users/${id}/password`, {
            method: "POST",
            body: JSON.stringify({ password: value }),
          });
          toast("密码已重置");
          if (input) input.value = "";
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const nicknameBtn = event.target.closest("[data-user-nickname]");
      if (nicknameBtn) {
        const row = panel.querySelector(`[data-nickname-row="${nicknameBtn.dataset.userNickname}"]`);
        if (row) row.hidden = !row.hidden;
        return;
      }
      const nicknameSave = event.target.closest("[data-nickname-save]");
      if (nicknameSave) {
        const id = nicknameSave.dataset.nicknameSave;
        const input = panel.querySelector(`[data-nickname-input="${id}"]`);
        const value = input ? input.value.trim() : "";
        if (value.length < 2 || value.length > 16) {
          toast("昵称需为 2-16 位");
          return;
        }
        try {
          await api(`/api/admin/users/${id}/nickname`, {
            method: "POST",
            body: JSON.stringify({ nickname: value }),
          });
          toast("昵称已更新");
          await loadAccounts();
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const deleteBtn = event.target.closest("[data-user-delete]");
      if (deleteBtn) {
        const label = deleteBtn.querySelector("span");
        if (deleteBtn.dataset.armed !== "1") {
          deleteBtn.dataset.armed = "1";
          if (label) label.textContent = "再点一次确认";
          setTimeout(() => {
            if (deleteBtn.isConnected) {
              deleteBtn.dataset.armed = "0";
              if (label) label.textContent = "删除";
            }
          }, 4000);
          return;
        }
        try {
          await api(`/api/admin/users/${deleteBtn.dataset.userDelete}`, { method: "DELETE" });
          toast("账号已删除");
          await loadAccounts();
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const addWord = event.target.closest("#addWordBtn");
      if (addWord) {
        const input = $("newWordInput");
        const category = $("newWordCategory");
        const word = input ? input.value.trim() : "";
        if (!word) {
          toast("请输入敏感词");
          return;
        }
        try {
          await api("/api/admin/sensitive-words", {
            method: "POST",
            body: JSON.stringify({ word, category: category ? category.value : "自定义" }),
          });
          toast("已添加");
          await loadAccountTab("words");
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const deleteWord = event.target.closest("[data-word-delete]");
      if (deleteWord) {
        try {
          await api(`/api/admin/sensitive-words/${deleteWord.dataset.wordDelete}`, {
            method: "DELETE",
          });
          toast("已删除");
          await loadAccountTab("words");
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const testBtn = event.target.closest("#wordTestBtn");
      if (testBtn) {
        const input = $("wordTestInput");
        const result = $("wordTestResult");
        try {
          const data = await api("/api/admin/sensitive-words/test", {
            method: "POST",
            body: JSON.stringify({ text: input ? input.value : "" }),
          });
          if (result) {
            result.textContent = data.count
              ? `命中 ${data.count} 处：${data.words.join("、")}；替换后：${data.masked}`
              : "没有命中。";
          }
        } catch (err) {
          if (result) result.textContent = err.message;
        }
        return;
      }
      const notifySave = event.target.closest("#notifySave");
      if (notifySave) {
        const result = $("notifyResult");
        try {
          await api("/api/admin/notify", {
            method: "POST",
            body: JSON.stringify(notifyFormPayload()),
          });
          toast("通知设置已保存");
          await loadAccountTab("notify");
        } catch (err) {
          if (result) result.textContent = err.message;
          toast(err.message);
        }
        return;
      }
      const notifyTest = event.target.closest("#notifyTest");
      if (notifyTest) {
        const result = $("notifyResult");
        if (result) result.textContent = "正在发送…";
        try {
          await api("/api/admin/notify", {
            method: "POST",
            body: JSON.stringify(notifyFormPayload()),
          });
          const data = await api("/api/admin/notify/test", {
            method: "POST",
            body: JSON.stringify({}),
          });
          toast("测试通知已发送");
          await loadAccountTab("notify");
          const fresh = $("notifyResult");
          if (fresh) fresh.textContent = "已发送：" + (data.detail || "OK");
        } catch (err) {
          if (result) result.textContent = err.message;
          toast(err.message);
        }
        return;
      }
      const notifyClear = event.target.closest("#notifyClearUrl");
      if (notifyClear) {
        if (notifyClear.dataset.armed !== "1") {
          notifyClear.dataset.armed = "1";
          notifyClear.querySelector("span").textContent = "再点一次确认";
          setTimeout(() => {
            if (notifyClear.isConnected) {
              notifyClear.dataset.armed = "0";
              notifyClear.querySelector("span").textContent = "清除地址";
            }
          }, 4000);
          return;
        }
        const payload = notifyFormPayload();
        payload.clear_url = true;
        payload.enabled = false;
        try {
          await api("/api/admin/notify", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          toast("已清除 Webhook 地址");
          await loadAccountTab("notify");
        } catch (err) {
          toast(err.message);
        }
        return;
      }
    });
    panel.addEventListener("change", async (event) => {
      const channelSelect = event.target.closest("#notifyChannel");
      if (channelSelect && state.notifySettings) {
        const item = (state.notifySettings.channels || []).find(
          (entry) => entry.key === channelSelect.value
        );
        const hint = $("notifyHint");
        if (hint && item) hint.textContent = item.hint;
        return;
      }
      const checkbox = event.target.closest("[data-perm]");
      if (!checkbox) return;
      const card = checkbox.closest("[data-user-card]");
      if (!card) return;
      try {
        await api(`/api/admin/users/${card.dataset.userCard}/permissions`, {
          method: "POST",
          body: JSON.stringify({
            permission: checkbox.dataset.perm,
            granted: checkbox.checked,
          }),
        });
        toast(checkbox.checked ? "已发放权限" : "已收回权限");
        await loadAccounts();
      } catch (err) {
        checkbox.checked = !checkbox.checked;
        toast(err.message);
      }
    });
  }

  // ---------- 内容审核 ----------
  function setReviewBadge(count) {
    const value = Number(count) || 0;
    const nav = $("reviewNavBadge");
    if (nav) {
      nav.hidden = value <= 0;
      nav.textContent = value > 99 ? "99+" : String(value);
    }
  }

  async function loadReview() {
    const panel = $("reviewPanel");
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api("/api/admin/review?status=pending");
      state.reviewFiles = data.files || [];
      setReviewBadge(data.pending || 0);
      panel.innerHTML = reviewHtml();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function reviewHtml() {
    if (!state.reviewFiles.length) {
      return '<div class="wb-empty">没有待审核的附件。</div>';
    }
    return (
      '<div class="wb-review-grid">' +
      state.reviewFiles
        .map((file) => {
          const thumb = file.is_image
            ? `<button class="wb-review-thumb wb-review-thumb-btn" type="button" data-review-preview="${file.id}" title="点击预览">
                 <img src="${escapeHtml(file.url)}" alt="" loading="lazy">
               </button>`
            : '<i data-lucide="file-text"></i>';
          const excerpt = (file.message_content || "").slice(0, 120);
          return `
        <article class="wb-review-card">
          ${file.is_image ? thumb : `<div class="wb-review-thumb">${thumb}</div>`}
          <div class="wb-review-body">
            <div class="wb-user-title">
              <strong>${escapeHtml(file.file_name)}</strong>
              <span class="wb-chip wb-chip-pending">待审核</span>
            </div>
            <div class="wb-user-meta">
              ${escapeHtml(file.message_nickname || "匿名")} · ${formatTime(file.created_at)} · ${formatBytes(file.file_size)}
            </div>
            ${excerpt ? `<p class="wb-review-text">${escapeHtml(excerpt)}</p>` : ""}
          </div>
          <div class="wb-user-actions">
            <a class="wb-btn" href="${escapeHtml(file.url)}" download="${escapeHtml(file.file_name)}">
              <i data-lucide="download"></i><span>下载</span>
            </a>
            <button class="wb-btn wb-btn-primary" type="button" data-review-action="approve" data-review-id="${file.id}">
              <i data-lucide="check"></i><span>通过</span>
            </button>
            <button class="wb-btn wb-btn-danger" type="button" data-review-action="reject" data-review-id="${file.id}">
              <i data-lucide="trash-2"></i><span>拒绝并删除</span>
            </button>
          </div>
        </article>`;
        })
        .join("") +
      "</div>"
    );
  }

  function openReviewPreview(file) {
    const overlay = $("reviewPreview");
    const body = $("reviewPreviewBody");
    const title = $("reviewPreviewTitle");
    if (!overlay || !body) return;
    if (title) title.textContent = file.file_name || "附件预览";
    body.innerHTML = file.is_image
      ? `<img src="${escapeHtml(file.url)}" alt="">`
      : `<iframe src="${escapeHtml(file.url)}" title="${escapeHtml(file.file_name || "附件预览")}"></iframe>`;
    overlay.hidden = false;
  }

  function bindReviewEvents() {
    const refresh = $("reviewRefreshBtn");
    if (refresh) {
      refresh.addEventListener("click", () => {
        loadReview().catch((err) => toast(err.message));
      });
    }
    const approveAll = $("reviewApproveAllBtn");
    if (approveAll) {
      approveAll.addEventListener("click", async () => {
        if (approveAll.dataset.armed !== "1") {
          approveAll.dataset.armed = "1";
          approveAll.querySelector("span").textContent = "再点一次确认";
          setTimeout(() => {
            if (approveAll.isConnected) {
              approveAll.dataset.armed = "0";
              approveAll.querySelector("span").textContent = "全部通过";
            }
          }, 4000);
          return;
        }
        approveAll.dataset.armed = "0";
        approveAll.querySelector("span").textContent = "全部通过";
        try {
          const data = await api("/api/admin/review/approve-all", {
            method: "POST",
            body: JSON.stringify({}),
          });
          toast(`已通过 ${data.approved} 个附件`);
          await loadReview();
        } catch (err) {
          toast(err.message);
        }
      });
    }
    const panel = $("reviewPanel");
    if (!panel) return;
    panel.addEventListener("click", async (event) => {
      const previewBtn = event.target.closest("[data-review-preview]");
      if (previewBtn) {
        const file = state.reviewFiles.find(
          (item) => String(item.id) === previewBtn.dataset.reviewPreview
        );
        if (file) openReviewPreview(file);
        return;
      }
      const button = event.target.closest("[data-review-action]");
      if (!button) return;
      const action = button.dataset.reviewAction;
      const id = button.dataset.reviewId;
      if (action === "reject" && button.dataset.armed !== "1") {
        button.dataset.armed = "1";
        const label = button.querySelector("span");
        if (label) label.textContent = "再点一次确认";
        setTimeout(() => {
          if (button.isConnected) {
            button.dataset.armed = "0";
            if (label) label.textContent = "拒绝并删除";
          }
        }, 4000);
        return;
      }
      try {
        await api(`/api/admin/review/${id}`, {
          method: "POST",
          body: JSON.stringify({ action }),
        });
        toast(action === "approve" ? "已通过" : "已拒绝并删除");
        await loadReview();
      } catch (err) {
        toast(err.message);
      }
    });
  }

  boot();
})();
