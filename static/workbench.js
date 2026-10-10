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
    roleDefaults: [],
    rolePermissionData: null,
    isOwner: false,
    isAdmin: false,
    reviewMessages: [],
    reviewLegacyFiles: [],
    reports: [],
    reportStatus: "pending",
    reportPendingCount: 0,
    badgeCounts: {
      pending_users: 0,
      pending_reviews: 0,
      pending_reports: 0,
      pending_downloads: 0,
    },
    downloadRequests: [],
    downloadRequestStatus: "pending",
    uploadLimitSchema: [],
    uploadLimits: null,
    uploadLimitDefaults: null,
    uploadLimitHardMaxBytes: 60 * 1024 * 1024,
    uploadLimitHardMaxCount: 100,
    defaultMessageLimit: 9,
    logTab: "activity",
    logPage: 1,
    logLimit: 50,
    logActions: [],
    logUsers: [],
    logFilters: { action: "", user: "", q: "", ip: "", dateFrom: "", dateTo: "", path: "", visitor: "" },
    logStats: null,
    auditPage: 1,
    auditActions: [],
    auditFilters: { action: "", q: "", dateFrom: "", dateTo: "" },
    notifyLogs: [],
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
    // 日志只对管理员开放，普通账号和游客一律退回概览
    if (view === "logs" && !state.isAdmin) view = "overview";
    state.view = view;
    document.querySelectorAll(".wb-view").forEach((el) => {
      const active = el.id === `view-${view}`;
      el.hidden = !active;
      el.classList.toggle("active", active);
    });
    document.querySelectorAll(".wb-nav button").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
    const main = document.querySelector(".wb-main");
    if (main) main.scrollTop = 0;
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
    if (view === "reports") loadReports();
    if (view === "downloads") loadDownloadRequests();
    if (view === "uploads") loadUploadLimits();
    if (view === "logs") loadLogs();
  }

  function initialView() {
    const allowed = ["overview", "assets", "firmware", "repairs", "prompts", "accounts", "review", "reports", "downloads", "uploads", "logs"];
    const params = new URLSearchParams(location.search);
    const candidate = (params.get("view") || (location.hash || "").replace("#", "") || "overview").trim();
    if (candidate === "accounts" && !state.isAdmin) return "overview";
    if (candidate === "review" && !state.isAdmin) return "overview";
    if (candidate === "reports" && !state.isAdmin) return "overview";
    if (candidate === "downloads" && !state.isAdmin) return "overview";
    if (candidate === "uploads" && !state.isAdmin) return "overview";
    if (candidate === "logs" && !state.isAdmin) return "overview";
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
          ${row.notes ? `<div class="wb-card-note" title="${escapeHtml(row.notes)}">备注：${escapeHtml(row.notes)}</div>` : ""}
        </div>
        <div class="wb-card-actions">
          ${row.flash_url ? `<a href="${escapeHtml(row.flash_url)}" target="_blank" rel="noopener" title="打开烧录链接"><button type="button"><i data-lucide="external-link"></i></button></a>` : ""}
          <button type="button" data-share-asset="${row.id}" title="分享"><i data-lucide="share-2"></i></button>
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
          ${row.notes ? `<div class="wb-card-note" title="${escapeHtml(row.notes)}">备注：${escapeHtml(row.notes)}</div>` : ""}
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

  // 上传固件/资料：按钮内显示进度，上传中再点一次按钮 = 取消（文件保留在表单里）。
  const assetBusy = { active: false, canceled: false, abort: null, fill: null };

  function assetFill() {
    if (!assetBusy.fill) {
      assetBusy.fill = ErrorProgress.button($("assetSubmitBtn"), {
        onCancel: () => {
          assetBusy.canceled = true;
          if (assetBusy.abort) assetBusy.abort();
        },
      });
    }
    return assetBusy.fill;
  }

  async function submitAsset(event) {
    event.preventDefault();
    if (assetBusy.active) return;
    const button = $("assetSubmitBtn");
    try {
      const payload = assetFormPayload();
      if (state.editingAssetId) {
        button.disabled = true;
        await api(`/api/workbench/assets/${state.editingAssetId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        toast("文件信息已更新");
      } else {
        const file = $("assetFile").files[0];
        if (!file) throw new Error("请选择文件");
        const uploadKey = "workbench_" + (payload.category || "other");
        if (window.ErrorUploadLimits) {
          await window.ErrorUploadLimits.ready();
        }
        const limit = window.ErrorUploadLimits
          ? window.ErrorUploadLimits.get(uploadKey)
          : null;
        if (limit && limit.max_file_bytes && file.size > limit.max_file_bytes) {
          throw new Error(
            "文件不能超过 " + window.ErrorUploadLimits.label(limit.max_file_bytes)
          );
        }
        const fill = assetFill();
        assetBusy.active = true;
        assetBusy.canceled = false;
        assetBusy.abort = null;
        button.title = "上传中，点击可取消";
        fill.busy("读取文件…");
        payload.file_name = file.name;
        const dataBase64 = await readFileBase64(file);
        if (assetBusy.canceled) throw new Error("已取消上传");
        const task = ErrorProgress.upload("/api/workbench/assets", {
          payload: Object.assign({}, payload, { data_base64: dataBase64 }),
          onProgress: (ratio) =>
            fill.set(ratio, `取消上传 ${ErrorProgress.percentText(ratio)}`),
          onUploaded: () => fill.busy("保存中…"),
        });
        assetBusy.abort = task.abort;
        await task.promise;
        toast("文件已上传");
      }
      closeModal("assetModal");
      await Promise.all([loadSummary(), loadAssets()]);
    } catch (err) {
      if (assetBusy.canceled || ErrorProgress.isAborted(err)) {
        toast("已取消上传，文件还在，可以直接重试");
        return;
      }
      toast(err.message || "保存失败");
    } finally {
      assetBusy.active = false;
      assetBusy.abort = null;
      button.disabled = false;
      button.removeAttribute("title");
      if (assetBusy.fill) assetBusy.fill.reset();
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
    if (!asset) return;
    const confirmed = await window.ErrorDialog.confirm(
      `删除「${asset.title}」及其文件？`,
      { title: "删除资料", confirmText: "删除", danger: true }
    );
    if (!confirmed) return;
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
    if (!repair) return;
    const confirmed = await window.ErrorDialog.confirm(
      `删除「${repair.device_name}」的维修记录？`,
      { title: "删除维修记录", confirmText: "删除", danger: true }
    );
    if (!confirmed) return;
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
    // 文件：点击 / 拖拽（单个文件，拖文件夹没用）
    if (window.ErrorDropZone) {
      window.ErrorDropZone.attach($("assetFileField"), {
        input: $("assetFile"),
        dropTarget: $("assetFileField"),
        multiple: false,
        folder: false,
        pickerId: "errorjiang-workbench-asset",
        toast: toast
      });
    }
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
      const shareAsset = event.target.closest("[data-share-asset]");
      if (shareAsset) {
        const asset = state.assets.find((item) => item.id === Number(shareAsset.dataset.shareAsset));
        if (asset && window.ErrorShare) {
          window.ErrorShare.open("workbench_asset", asset.id, asset.title || asset.original_name);
        }
        return;
      }
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
    bindReportEvents();
    bindDownloadEvents();
    bindLogEvents();
    bindUploadLimitEvents();
    try {
      const status = await api("/api/auth/status");
      state.isOwner = Boolean(status.owner);
      state.isAdmin = Boolean(status.admin || status.owner);
      const accountsNav = document.querySelector('[data-view="accounts"]');
      if (accountsNav) accountsNav.hidden = !state.isAdmin;
      const reviewNav = document.querySelector('[data-view="review"]');
      if (reviewNav) reviewNav.hidden = !state.isAdmin;
      const reportsNav = document.querySelector('[data-view="reports"]');
      if (reportsNav) reportsNav.hidden = !state.isAdmin;
      const downloadsNav = document.querySelector('[data-view="downloads"]');
      if (downloadsNav) downloadsNav.hidden = !state.isAdmin;
      const uploadsNav = document.querySelector('[data-view="uploads"]');
      if (uploadsNav) uploadsNav.hidden = !state.isAdmin;
      const logsNav = document.querySelector('[data-view="logs"]');
      if (logsNav) logsNav.hidden = !state.isAdmin;
      if (state.isAdmin) {
        setPendingBadge(status.pending_users || 0);
        setReviewBadge(status.pending_attachments || 0);
        setReportsBadge(status.pending_reports || 0);
        setDownloadsBadge(status.pending_download_requests || 0);
        state.badgeCounts = {
          pending_users: Number(status.pending_users) || 0,
          pending_reviews: Number(status.pending_attachments) || 0,
          pending_reports: Number(status.pending_reports) || 0,
          pending_downloads: Number(status.pending_download_requests) || 0,
        };
      }
    } catch (err) {}
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && state.isAdmin) refreshNavBadges();
    });
    window.addEventListener("focus", () => {
      if (state.isAdmin) refreshNavBadges();
    });
    window.addEventListener("online", () => {
      if (state.isAdmin) refreshNavBadges();
    });
    setInterval(() => {
      if (!document.hidden && state.isAdmin) refreshNavBadges();
    }, 5000);
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
    set_message_limit: "调整留言额度",
    approve_attachment: "通过附件审核",
    reject_attachment: "拒绝附件审核",
    approve_attachment_batch: "批量通过附件",
    download_request_approve: "批准下载申请",
    download_request_reject: "拒绝下载申请",
    download_request_revoke: "撤销下载权限",
    notify_settings: "修改通知设置",
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
      const data = await api("/api/site/notifications/summary");
      if (!data.admin) return;
      const next = {
        pending_users: Number(data.pending_users) || 0,
        pending_reviews: Number(data.pending_reviews) || 0,
        pending_reports: Number(data.pending_reports) || 0,
        pending_downloads: Number(data.pending_downloads) || 0,
      };
      const previous = state.badgeCounts || {};
      setPendingBadge(next.pending_users);
      setReviewBadge(next.pending_reviews);
      setReportsBadge(next.pending_reports);
      setDownloadsBadge(next.pending_downloads);
      state.badgeCounts = next;
      if (
        state.view === "accounts" &&
        state.accountTab === "pending" &&
        previous.pending_users !== next.pending_users
      ) {
        loadAccounts();
      }
      if (
        state.view === "review" &&
        previous.pending_reviews !== next.pending_reviews
      ) {
        loadReview();
      }
      if (
        state.view === "reports" &&
        previous.pending_reports !== next.pending_reports
      ) {
        loadReports();
      }
      if (
        state.view === "downloads" &&
        previous.pending_downloads !== next.pending_downloads
      ) {
        loadDownloadRequests();
      }
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
    if (panel) {
      panel.hidden = value <= 0;
      panel.textContent = value > 99 ? "99+" : String(value);
    }
  }

  function updateMessageLimitHint(panel, userId, value) {
    const hint = panel.querySelector(`[data-msg-limit-hint="${userId}"]`);
    if (!hint) return;
    const limit = Math.max(0, Math.min(999, Math.trunc(Number(value) || 0)));
    hint.textContent = `每天最多 ${limit} 条（含回复），默认 ${state.defaultMessageLimit || 9} 条/天`;
  }

  async function loadAccounts() {
    const panel = $("accountPanel");
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api("/api/admin/users");
      state.adminUsers = data.users || [];
      setPendingBadge(data.pending || 0);
      state.defaultMessageLimit = Number(data.default_message_limit) || 9;
      state.roleDefaults = data.role_defaults || [];
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
    } else if (tab === "roles") {
      const data = await api("/api/admin/role-permissions");
      state.rolePermissionData = data;
      state.roleDefaults = data.member_defaults || state.roleDefaults;
      panel.innerHTML = rolesHtml(data);
    } else if (tab === "notify") {
      const data = await api("/api/admin/notify");
      state.notifySettings = data;
      panel.innerHTML = notifyHtml(data);
    } else if (tab === "password") {
      panel.innerHTML = passwordHtml();
    } else {
      const data = await api("/api/admin/audit?limit=200");
      state.auditRows = Array.isArray(data) ? data : data.items || [];
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

  function userPermissionItemHtml(user, item) {
    const overrides = user.permission_overrides || {};
    const mode = overrides[item.key] || "inherit";
    if (item.key === "system:admin") {
      return `<label class="wb-perm-item"><input type="checkbox" data-perm-admin="${item.key}"${
        mode === "allow" ? " checked" : ""
      }${state.isOwner ? "" : " disabled"}><span>${escapeHtml(item.label)}</span></label>`;
    }
    const inRole = (state.roleDefaults || []).includes(item.key);
    const inheritLabel = inRole ? "继承角色（当前允许）" : "继承角色（当前未允许）";
    return `<label class="wb-perm-item wb-perm-mode"><span>${escapeHtml(item.label)}</span>
      <select data-perm-mode="${item.key}" data-user-id="${user.id}">
        <option value="inherit"${mode === "inherit" ? " selected" : ""}>${escapeHtml(inheritLabel)}</option>
        <option value="allow"${mode === "allow" ? " selected" : ""}>允许</option>
        <option value="deny"${mode === "deny" ? " selected" : ""}>禁止</option>
      </select></label>`;
  }

  function usersHtml() {
    if (!state.adminUsers.length) {
      return '<div class="wb-empty">还没有注册账号。</div>';
    }
    return (
      '<div class="wb-user-list">' +
      state.adminUsers
        .map((user) => {
          const permissions = new Set(user.permissions || []);
          const defaultLimit = state.defaultMessageLimit || 9;
          const hasCustomLimit =
            user.message_daily_limit !== null && user.message_daily_limit !== undefined;
          const limitValue = hasCustomLimit
            ? Math.max(0, Math.min(999, Number(user.message_daily_limit) || 0))
            : defaultLimit;
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
          const permHtml = state.permissionGroups
            .map((group) => {
              const items = (group.items || [])
                .map((item) => userPermissionItemHtml(user, item))
                .join("");
              return `<div class="wb-perm-group"><h4>${escapeHtml(group.label)}</h4><div class="wb-perm-items">${items}</div></div>`;
            })
            .join("");
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
            <div class="wb-msg-limit" data-msg-limit-row="${user.id}">
              <div class="wb-msg-limit-main">
                <div class="wb-msg-limit-title">
                  <strong>留言次数</strong>
                  <span class="wb-chip">${hasCustomLimit ? "自定义" : "默认"}</span>
                </div>
                <div class="wb-msg-limit-hint" data-msg-limit-hint="${user.id}">每天最多 ${limitValue} 条（含回复），默认 ${defaultLimit} 条/天</div>
              </div>
              <div class="wb-msg-limit-control">
                <button class="wb-btn wb-step-btn" type="button" data-msg-limit-step="-1" data-user-id="${user.id}" aria-label="减少留言次数"><i data-lucide="minus"></i></button>
                <input type="number" min="0" max="999" step="1" value="${limitValue}" data-msg-limit-input="${user.id}" aria-label="每天留言次数">
                <button class="wb-btn wb-step-btn" type="button" data-msg-limit-step="1" data-user-id="${user.id}" aria-label="增加留言次数"><i data-lucide="plus"></i></button>
                <button class="wb-btn wb-btn-primary" type="button" data-msg-limit-save="${user.id}"><i data-lucide="check"></i><span>保存</span></button>
                <button class="wb-btn" type="button" data-msg-limit-reset="${user.id}"${hasCustomLimit ? "" : " hidden"}><span>恢复默认</span></button>
              </div>
            </div>
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

  function rolesHtml(data) {
    const guestSet = new Set(data.guest || []);
    const memberSet = new Set(data.member || []);
    const guestItems = (data.guest_options || [])
      .map(
        (item) => `
      <label class="wb-perm-item wb-role-perm"><input type="checkbox" data-role-perm data-role="guest" data-permission="${escapeHtml(
          item.key
        )}"${guestSet.has(item.key) ? " checked" : ""}><span>${escapeHtml(item.label)}</span></label>`
      )
      .join("");
    const memberGroups = (data.member_groups || [])
      .map((group) => {
        const items = (group.items || [])
          .map(
            (item) => `
          <label class="wb-perm-item wb-role-perm"><input type="checkbox" data-role-perm data-role="member" data-permission="${escapeHtml(
              item.key
            )}"${memberSet.has(item.key) ? " checked" : ""}><span>${escapeHtml(item.label)}</span></label>`
          )
          .join("");
        return `<div class="wb-perm-group"><h4>${escapeHtml(group.label)}</h4><div class="wb-perm-items">${items}</div></div>`;
      })
      .join("");
    const adminItems = (data.admin_permissions || [])
      .map((item) => `<span class="wb-role-fixed">${escapeHtml(item.label)}</span>`)
      .join("");
    return `
      <div class="wb-role-grid">
        <section class="wb-panel wb-role-card">
          <div class="wb-panel-head"><h2>游客</h2><span class="wb-hint">未登录访客能浏览哪些公开页面</span></div>
          <div class="wb-panel-body">
            <div class="wb-perm-items wb-role-perms">${guestItems}</div>
            <p class="wb-hint">游客没有任何留言、标记、编辑、下载或导出权限；地图始终不对游客开放。</p>
          </div>
        </section>
        <section class="wb-panel wb-role-card">
          <div class="wb-panel-head"><h2>普通账户</h2><span class="wb-hint">角色默认权限，单个账户可再增减</span></div>
          <div class="wb-panel-body">
            <div class="wb-perm-groups">${memberGroups}</div>
            <p class="wb-hint">只读权限（查看仓库、笔记、工作台等）不在这里分配，仍到「全部账户」里按账号单独授予。</p>
          </div>
        </section>
        <section class="wb-panel wb-role-card">
          <div class="wb-panel-head"><h2>管理员</h2><span class="wb-chip wb-chip-admin">全部权限 · 不可收回</span></div>
          <div class="wb-panel-body">
            <div class="wb-role-fixed-list">${adminItems}</div>
            <p class="wb-hint">管理员权限固定为全部，不能收回；目前站点由站长自行维护。</p>
          </div>
        </section>
      </div>`;
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
        <div class="wb-panel-body">
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
      </div>
      <div class="wb-panel">
        <div class="wb-panel-head"><h2>测试</h2></div>
        <div class="wb-panel-body">
          <textarea id="wordTestInput" rows="3" placeholder="输入一段文字，看看会命中哪些词"></textarea>
          <div class="wb-inline">
            <button class="wb-btn" type="button" id="wordTestBtn"><i data-lucide="search"></i><span>测试</span></button>
            <span id="wordTestResult" class="wb-hint"></span>
          </div>
        </div>
      </div>`;
  }

  function auditRowHtml(row) {
    return `
      <article class="wb-audit-row">
        <span class="wb-audit-time">${formatTime(row.created_at)}</span>
        <span class="wb-audit-actor">${escapeHtml(row.actor_name || "系统")}</span>
        <span class="wb-audit-action">${escapeHtml(AUDIT_ACTION_LABELS[row.action] || row.action)}</span>
        <span class="wb-audit-target">${escapeHtml(row.target_name || "")}</span>
        <span class="wb-audit-detail">${escapeHtml(row.detail || "")}</span>
      </article>`;
  }

  function auditHtml() {
    if (!state.auditRows.length) {
      return '<div class="wb-empty">还没有审计记录。</div>';
    }
    return '<div class="wb-audit-list">' + state.auditRows.map(auditRowHtml).join("") + "</div>";
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
          <p class="wb-hint">新注册申请、待审核留言和内容举报会推送到你的手机或群机器人；站内的工作台呼吸提醒仍然保留。</p>
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

  function passwordHtml() {
    return `
      <div class="wb-panel">
        <div class="wb-panel-head">
          <h2>管理员登录密码</h2>
          <span class="wb-chip">仅站长</span>
        </div>
        <div class="wb-panel-body">
          <p class="wb-hint">改完立即生效，不用重启服务；同一账号在其它设备上的登录会被下线，需要重新登录。</p>
          <div class="wb-notify-grid">
            <label class="wb-field"><span>当前密码</span>
              <input id="passwordCurrent" type="password" autocomplete="current-password" maxlength="128">
            </label>
            <label class="wb-field"><span>新密码（8-128 位）</span>
              <input id="passwordNew" type="password" autocomplete="new-password" maxlength="128">
            </label>
            <label class="wb-field"><span>再输一次新密码</span>
              <input id="passwordConfirm" type="password" autocomplete="new-password" maxlength="128">
            </label>
          </div>
          <div class="wb-inline">
            <button class="wb-btn wb-btn-primary" type="button" id="passwordSave">
              <i data-lucide="key-round"></i><span>修改密码</span>
            </button>
            <span class="wb-hint" id="passwordResult"></span>
          </div>
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
      const limitStep = event.target.closest("[data-msg-limit-step]");
      if (limitStep) {
        const id = limitStep.dataset.userId;
        const input = panel.querySelector(`[data-msg-limit-input="${id}"]`);
        if (!input) return;
        const delta = Number(limitStep.dataset.msgLimitStep) || 0;
        const current = Math.max(0, Math.min(999, Math.trunc(Number(input.value) || 0)));
        const next = Math.max(0, Math.min(999, current + delta));
        input.value = String(next);
        updateMessageLimitHint(panel, id, next);
        return;
      }
      const limitSave = event.target.closest("[data-msg-limit-save]");
      if (limitSave) {
        const id = limitSave.dataset.msgLimitSave;
        const input = panel.querySelector(`[data-msg-limit-input="${id}"]`);
        const raw = input ? input.value.trim() : "";
        const value = Number(raw);
        if (!raw || !Number.isInteger(value) || value < 0 || value > 999) {
          toast("留言次数需为 0-999 的整数");
          return;
        }
        try {
          await api(`/api/admin/users/${id}/message-limit`, {
            method: "POST",
            body: JSON.stringify({ limit: value }),
          });
          toast("留言次数已更新");
          await loadAccounts();
        } catch (err) {
          toast(err.message);
        }
        return;
      }
      const limitReset = event.target.closest("[data-msg-limit-reset]");
      if (limitReset) {
        const id = limitReset.dataset.msgLimitReset;
        try {
          await api(`/api/admin/users/${id}/message-limit`, {
            method: "POST",
            body: JSON.stringify({ limit: null }),
          });
          toast("已恢复默认留言次数");
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
      const passwordSave = event.target.closest("#passwordSave");
      if (passwordSave) {
        const result = $("passwordResult");
        const current = panel.querySelector("#passwordCurrent");
        const fresh = panel.querySelector("#passwordNew");
        const confirm = panel.querySelector("#passwordConfirm");
        if (!current || !current.value) {
          toast("请先输入当前密码");
          return;
        }
        if (!fresh || fresh.value.length < 8) {
          toast("新密码至少 8 位");
          return;
        }
        if (fresh.value !== (confirm ? confirm.value : "")) {
          toast("两次输入的新密码不一致");
          return;
        }
        if (result) result.textContent = "正在保存…";
        try {
          await api("/api/admin/password", {
            method: "POST",
            body: JSON.stringify({
              current_password: current.value,
              new_password: fresh.value,
            }),
          });
          current.value = "";
          fresh.value = "";
          if (confirm) confirm.value = "";
          if (result) result.textContent = "密码已更新";
          toast("管理员密码已更新");
        } catch (err) {
          if (result) result.textContent = err.message;
          toast(err.message);
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
    panel.addEventListener("input", (event) => {
      const input = event.target.closest("[data-msg-limit-input]");
      if (!input) return;
      updateMessageLimitHint(panel, input.dataset.msgLimitInput, input.value);
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
      const roleCheckbox = event.target.closest("[data-role-perm]");
      if (roleCheckbox) {
        try {
          const data = await api("/api/admin/role-permissions", {
            method: "POST",
            body: JSON.stringify({
              role: roleCheckbox.dataset.role,
              permission: roleCheckbox.dataset.permission,
              granted: roleCheckbox.checked,
            }),
          });
          state.rolePermissionData = data;
          state.roleDefaults = data.member_defaults || state.roleDefaults;
          toast(roleCheckbox.checked ? "角色权限已开启" : "角色权限已关闭");
          panel.innerHTML = rolesHtml(data);
          if (window.lucide) lucide.createIcons();
        } catch (err) {
          roleCheckbox.checked = !roleCheckbox.checked;
          toast(err.message);
        }
        return;
      }
      const modeSelect = event.target.closest("[data-perm-mode]");
      if (modeSelect) {
        const card = modeSelect.closest("[data-user-card]");
        if (!card) return;
        try {
          await api(`/api/admin/users/${card.dataset.userCard}/permissions`, {
            method: "POST",
            body: JSON.stringify({
              permission: modeSelect.dataset.permMode,
              mode: modeSelect.value,
            }),
          });
          toast(
            modeSelect.value === "inherit"
              ? "已改为继承角色"
              : modeSelect.value === "allow"
                ? "已单独允许"
                : "已单独禁止"
          );
          await loadAccounts();
        } catch (err) {
          toast(err.message);
          await loadAccounts();
        }
        return;
      }
      const adminCheckbox = event.target.closest("[data-perm-admin]");
      if (adminCheckbox) {
        const card = adminCheckbox.closest("[data-user-card]");
        if (!card) return;
        try {
          await api(`/api/admin/users/${card.dataset.userCard}/permissions`, {
            method: "POST",
            body: JSON.stringify({
              permission: adminCheckbox.dataset.permAdmin,
              mode: adminCheckbox.checked ? "allow" : "inherit",
            }),
          });
          toast(adminCheckbox.checked ? "已授予管理员" : "已取消管理员");
          await loadAccounts();
        } catch (err) {
          adminCheckbox.checked = !adminCheckbox.checked;
          toast(err.message);
        }
        return;
      }
    });
  }

  // ---------- 日志 ----------
  const LOG_ACTION_LABELS = {
    message_create: "发布留言",
    message_reply: "回复留言",
    message_delete: "删除留言",
    moment_create: "发布动态",
    moment_update: "编辑动态",
    moment_delete: "删除动态",
    map_place_create: "新增标记",
    map_place_update: "编辑标记",
    map_place_delete: "删除标记",
    map_photo_upload: "上传标记照片",
    map_photo_delete: "删除标记照片",
    register: "提交注册",
    login: "登录成功",
    login_fail: "登录失败",
    login_blocked: "登录被限流",
    nickname_change: "修改昵称",
    asset_download: "下载资料",
    share_create: "生成分享链接",
    share_download: "通过分享链接下载",
    download_request_create: "提交下载申请",
    download_request_approve: "批准下载申请",
    download_request_reject: "拒绝下载申请",
    download_request_revoke: "撤销下载权限",
    music_download: "下载歌曲",
    music_upload: "上传歌曲",
    music_delete: "删除歌曲",
    book_upload: "上架电子书",
    book_update: "编辑电子书",
    book_delete: "删除电子书",
    book_download: "下载电子书",
    prompt_create: "新增提示词",
    prompt_update: "编辑提示词",
    prompt_delete: "删除提示词",
    stock_inbound: "元件入库",
    stock_outbound: "元件出库",
    movement_update: "修改出入库",
    movement_delete: "删除出入库",
    project_create: "新建项目",
    project_update: "编辑项目",
    project_delete: "删除项目",
  };

  function logFilterValue(id) {
    const el = $(id);
    return el ? String(el.value || "").trim() : "";
  }

  function renderLogStats(data) {
    const today = (data && data.today) || {};
    const retention = Number(data && data.retention_days) || 29;
    $("logStats").innerHTML = [
      ["今日 PV", today.pv || 0, "页面访问次数"],
      ["今日 UV", today.uv || 0, "按 IP 去重"],
      ["今日留言", today.messages || 0, "含回复"],
      ["今日登录失败", today.login_failed || 0, `明细保留 ${retention} 天`],
    ]
      .map(
        ([label, value, note]) => `
      <article class="wb-stat">
        <div class="wb-stat-label">${escapeHtml(label)}</div>
        <div class="wb-stat-value">${Number(value) || 0}</div>
        <div class="wb-stat-note">${escapeHtml(note)}</div>
      </article>`
      )
      .join("");
  }

  async function loadLogs() {
    try {
      state.logStats = await api("/api/admin/logs/stats?days=7");
      renderLogStats(state.logStats);
    } catch (err) {
      $("logStats").innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
    await loadLogTab();
  }

  async function loadLogTab() {
    document.querySelectorAll("#logTabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.logTab === state.logTab);
    });
    const panel = $("logPanel");
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      if (state.logTab === "activity") {
        const params = new URLSearchParams({ page: state.logPage, limit: state.logLimit });
        const filters = state.logFilters;
        if (filters.action) params.set("action", filters.action);
        if (filters.user) params.set("user", filters.user);
        if (filters.q) params.set("q", filters.q);
        if (filters.ip) params.set("ip", filters.ip);
        if (filters.dateFrom) params.set("date_from", filters.dateFrom);
        if (filters.dateTo) params.set("date_to", filters.dateTo);
        const data = await api("/api/admin/logs/activity?" + params.toString());
        state.logActions = data.actions || [];
        state.logUsers = data.users || [];
        panel.innerHTML = activityLogHtml(data);
      } else if (state.logTab === "access") {
        const params = new URLSearchParams({ page: state.logPage, limit: state.logLimit });
        const filters = state.logFilters;
        if (filters.path) params.set("path", filters.path);
        if (filters.ip) params.set("ip", filters.ip);
        if (filters.visitor) params.set("visitor", filters.visitor);
        if (filters.dateFrom) params.set("date_from", filters.dateFrom);
        if (filters.dateTo) params.set("date_to", filters.dateTo);
        const data = await api("/api/admin/logs/access?" + params.toString());
        panel.innerHTML = accessLogHtml(data);
      } else if (state.logTab === "audit") {
        const params = new URLSearchParams({ page: state.auditPage, limit: state.logLimit });
        const filters = state.auditFilters;
        if (filters.action) params.set("action", filters.action);
        if (filters.q) params.set("q", filters.q);
        if (filters.dateFrom) params.set("date_from", filters.dateFrom);
        if (filters.dateTo) params.set("date_to", filters.dateTo);
        const data = await api("/api/admin/audit?" + params.toString());
        state.auditRows = data.items || [];
        state.auditActions = data.actions || [];
        panel.innerHTML = auditLogHtml(data);
      } else {
        const data = await api("/api/admin/notify");
        state.notifyLogs = data.log || [];
        panel.innerHTML = notifyLogHtml();
      }
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function logPagerHtml(total, page, limit) {
    const size = Number(limit) || 50;
    const pages = Math.max(1, Math.ceil((Number(total) || 0) / size));
    const current = Math.max(1, Number(page) || 1);
    return `<div class="wb-log-pager">
      <button class="wb-btn" type="button" data-log-page="${current - 1}"${current <= 1 ? " disabled" : ""}>上一页</button>
      <span>第 ${current} / ${pages} 页 · 共 ${Number(total) || 0} 条</span>
      <button class="wb-btn" type="button" data-log-page="${current + 1}"${current >= pages ? " disabled" : ""}>下一页</button>
    </div>`;
  }

  function trendChartHtml(series) {
    const items = Array.isArray(series) ? series : [];
    if (!items.length) {
      return '<section class="wb-panel"><div class="wb-panel-head"><h2>近 7 天趋势</h2></div><div class="wb-panel-body"><div class="wb-empty">暂无数据。</div></div></section>';
    }
    const width = 720;
    const height = 190;
    const pad = { top: 16, right: 12, bottom: 30, left: 38 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const maxValue = Math.max(
      1,
      ...items.map((item) => Math.max(Number(item.pv) || 0, Number(item.uv) || 0))
    );
    const groupW = innerW / items.length;
    const barW = Math.max(6, Math.min(18, groupW * 0.26));
    const baseline = pad.top + innerH;
    const bars = items
      .map((item, index) => {
        const pv = Number(item.pv) || 0;
        const uv = Number(item.uv) || 0;
        const pvH = Math.round((pv / maxValue) * innerH);
        const uvH = Math.round((uv / maxValue) * innerH);
        const center = pad.left + index * groupW + groupW / 2;
        const label = String(item.date || "").slice(5);
        return `
        <g>
          <rect x="${(center - barW - 1.5).toFixed(1)}" y="${baseline - pvH}" width="${barW}" height="${pvH}" rx="2" fill="var(--wb-accent)"><title>${escapeHtml(item.date || "")} PV ${pv}</title></rect>
          <rect x="${(center + 1.5).toFixed(1)}" y="${baseline - uvH}" width="${barW}" height="${uvH}" rx="2" fill="var(--wb-success)"><title>${escapeHtml(item.date || "")} UV ${uv}</title></rect>
          <text x="${center.toFixed(1)}" y="${height - 9}" text-anchor="middle" font-size="11" fill="var(--wb-muted)">${escapeHtml(label)}</text>
        </g>`;
      })
      .join("");
    const grid = [0, 0.5, 1]
      .map((ratio) => {
        const y = pad.top + innerH * (1 - ratio);
        return `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}" stroke="var(--wb-line)" stroke-width="1"/><text x="${pad.left - 7}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--wb-faint)">${Math.round(maxValue * ratio)}</text>`;
      })
      .join("");
    const pvTotal = items.reduce((sum, item) => sum + (Number(item.pv) || 0), 0);
    const uvAvg = Math.round(
      items.reduce((sum, item) => sum + (Number(item.uv) || 0), 0) / items.length
    );
    return `
      <section class="wb-panel">
        <div class="wb-panel-head">
          <h2>近 7 天趋势</h2>
          <span class="wb-log-legend"><em class="pv"></em>PV<em class="uv"></em>UV · 合计 PV ${pvTotal} / 日均 UV ${uvAvg}</span>
        </div>
        <div class="wb-panel-body">
          <svg class="wb-log-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="近 7 天 PV / UV 趋势">${grid}${bars}</svg>
        </div>
      </section>`;
  }

  function logExportHref() {
    const params = new URLSearchParams({ kind: state.logTab === "access" ? "access" : "activity" });
    const filters = state.logFilters;
    if (filters.q) params.set("q", filters.q);
    if (filters.action) params.set("action", filters.action);
    if (filters.user) params.set("user", filters.user);
    if (filters.ip) params.set("ip", filters.ip);
    if (filters.path) params.set("path", filters.path);
    if (filters.visitor) params.set("visitor", filters.visitor);
    if (filters.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters.dateTo) params.set("date_to", filters.dateTo);
    return "/api/admin/logs/export?" + params.toString();
  }

  function activityLogHtml(data) {
    const items = data.items || [];
    const options = state.logActions
      .map(
        (item) =>
          `<option value="${escapeHtml(item.action)}"${
            state.logFilters.action === item.action ? " selected" : ""
          }>${escapeHtml(LOG_ACTION_LABELS[item.action] || item.action)}（${item.count}）</option>`
      )
      .join("");
    const userOptions = state.logUsers
      .map(
        (item) =>
          `<option value="${item.user_id}"${
            state.logFilters.user === String(item.user_id) ? " selected" : ""
          }>${escapeHtml(item.actor_name || "账号 " + item.user_id)}（${item.count}）</option>`
      )
      .join("");
    const rows = items.length
      ? items
          .map(
            (row) => `
        <article class="wb-log-item">
          <div class="wb-log-main">
            <span class="wb-log-tag">${escapeHtml(LOG_ACTION_LABELS[row.action] || row.action)}</span>
            <strong>${escapeHtml(row.summary || "")}</strong>
          </div>
          <div class="wb-log-meta">
            <span>${formatTime(row.created_at)}</span>
            <span>${escapeHtml(row.actor_name || "游客")}</span>
            <span>${escapeHtml(row.ip || "未知 IP")}${row.source_port ? ":" + row.source_port : ""}${row.ip_region ? " · " + escapeHtml(row.ip_region) : ""}</span>
            ${row.method || row.target_host ? `<span>${escapeHtml(row.method || "")} → ${escapeHtml(row.target_host || "")}${row.target_port ? ":" + row.target_port : ""}</span>` : ""}
            ${row.client_platform ? `<span>${escapeHtml(row.client_platform)}</span>` : ""}
            ${row.source_path ? `<span>来源 ${escapeHtml(row.source_path)}</span>` : ""}
          </div>
        </article>`
          )
          .join("")
      : '<div class="wb-empty">没有符合条件的记录。</div>';
    return `
      <section class="wb-panel">
        <div class="wb-panel-body">
          <div class="wb-toolbar">
            <label class="wb-search"><i data-lucide="search"></i><input id="logQ" value="${escapeHtml(state.logFilters.q)}" placeholder="搜索摘要、账号或来源"></label>
            <select id="logAction"><option value="">全部动作</option>${options}</select>
            <select id="logUser">
              <option value="">全部账号</option>
              <option value="guest"${state.logFilters.user === "guest" ? " selected" : ""}>游客</option>
              <option value="admin"${state.logFilters.user === "admin" ? " selected" : ""}>管理员 / 本地</option>
              ${userOptions}
            </select>
            <input class="wb-log-input" id="logIp" value="${escapeHtml(state.logFilters.ip)}" placeholder="IP">
            <input class="wb-log-input" id="logDateFrom" type="date" value="${escapeHtml(state.logFilters.dateFrom)}">
            <input class="wb-log-input" id="logDateTo" type="date" value="${escapeHtml(state.logFilters.dateTo)}">
            <button class="wb-btn wb-btn-primary" id="logQueryBtn" type="button"><i data-lucide="filter"></i><span>查询</span></button>
            <a class="wb-btn" href="${logExportHref()}"><i data-lucide="download"></i><span>导出 CSV</span></a>
          </div>
          <div class="wb-log-list">${rows}</div>
          ${logPagerHtml(data.total, data.page, data.limit)}
        </div>
      </section>`;
  }

  function accessLogHtml(data) {
    const items = data.items || [];
    const stats = state.logStats || {};
    const topPaths = (stats.top_paths || []).length
      ? (stats.top_paths || [])
          .map((row) => `<span class="wb-chip">${escapeHtml(row.path)} · ${row.count}</span>`)
          .join("")
      : '<span class="wb-hint">暂无数据</span>';
    const rows = items.length
      ? items
          .map(
            (row) => `
        <article class="wb-log-item">
          <div class="wb-log-main">
            <span class="wb-log-tag">${row.actor_kind === "guest" ? "游客" : escapeHtml(row.actor_name || "登录")}</span>
            <strong>${escapeHtml(row.path)}</strong>
            <span class="wb-chip">${row.status}</span>
          </div>
          <div class="wb-log-meta">
            <span>${formatTime(row.created_at)}</span>
            <span>${escapeHtml(row.ip || "未知 IP")}${row.source_port ? ":" + row.source_port : ""}${row.ip_region ? " · " + escapeHtml(row.ip_region) : ""}</span>
            ${row.method || row.target_host ? `<span>${escapeHtml(row.method || "")} → ${escapeHtml(row.target_host || "")}${row.target_port ? ":" + row.target_port : ""}</span>` : ""}
            ${row.client_platform ? `<span>${escapeHtml(row.client_platform)}</span>` : ""}
            ${row.referer ? `<span>来源 ${escapeHtml(row.referer)}</span>` : ""}
            ${row.device ? `<span>${escapeHtml(row.device)}</span>` : ""}
          </div>
        </article>`
          )
          .join("")
      : '<div class="wb-empty">没有符合条件的访问记录。</div>';
    return `
      ${trendChartHtml(stats.series)}
      <section class="wb-panel">
        <div class="wb-panel-head"><h2>热门页面</h2><span class="wb-hint">近 7 天</span></div>
        <div class="wb-panel-body"><div class="wb-log-hot">${topPaths}</div></div>
      </section>
      <section class="wb-panel">
        <div class="wb-panel-body">
          <div class="wb-toolbar">
            <label class="wb-search"><i data-lucide="search"></i><input id="logPath" value="${escapeHtml(state.logFilters.path)}" placeholder="按路径筛选，如 /messages"></label>
            <input class="wb-log-input" id="logIp" value="${escapeHtml(state.logFilters.ip)}" placeholder="IP">
            <select id="logVisitor">
              <option value="">全部访客</option>
              <option value="guest"${state.logFilters.visitor === "guest" ? " selected" : ""}>仅游客</option>
              <option value="user"${state.logFilters.visitor === "user" ? " selected" : ""}>仅登录账号</option>
            </select>
            <input class="wb-log-input" id="logDateFrom" type="date" value="${escapeHtml(state.logFilters.dateFrom)}">
            <input class="wb-log-input" id="logDateTo" type="date" value="${escapeHtml(state.logFilters.dateTo)}">
            <button class="wb-btn wb-btn-primary" id="logQueryBtn" type="button"><i data-lucide="filter"></i><span>查询</span></button>
            <a class="wb-btn" href="${logExportHref()}"><i data-lucide="download"></i><span>导出 CSV</span></a>
          </div>
          <div class="wb-log-list">${rows}</div>
          ${logPagerHtml(data.total, data.page, data.limit)}
        </div>
      </section>`;
  }

  function auditLogHtml(data) {
    const actionOptions = state.auditActions
      .map(
        (item) =>
          `<option value="${escapeHtml(item.action)}"${
            state.auditFilters.action === item.action ? " selected" : ""
          }>${escapeHtml(AUDIT_ACTION_LABELS[item.action] || item.action)}（${item.count}）</option>`
      )
      .join("");
    const rows = state.auditRows.length
      ? '<div class="wb-audit-list">' + state.auditRows.map(auditRowHtml).join("") + "</div>"
      : '<div class="wb-empty">还没有审计记录。</div>';
    return `
      <section class="wb-panel">
        <div class="wb-panel-head"><h2>管理审计</h2><span class="wb-hint">注册审批、权限、敏感词与审核操作</span></div>
        <div class="wb-panel-body">
          <div class="wb-toolbar">
            <label class="wb-search"><i data-lucide="search"></i><input id="auditQ" value="${escapeHtml(state.auditFilters.q)}" placeholder="搜索操作人、对象或详情"></label>
            <select id="auditAction"><option value="">全部动作</option>${actionOptions}</select>
            <input class="wb-log-input" id="auditDateFrom" type="date" value="${escapeHtml(state.auditFilters.dateFrom)}">
            <input class="wb-log-input" id="auditDateTo" type="date" value="${escapeHtml(state.auditFilters.dateTo)}">
            <button class="wb-btn wb-btn-primary" id="auditQueryBtn" type="button"><i data-lucide="filter"></i><span>查询</span></button>
          </div>
          ${rows}
          ${logPagerHtml(data.total, data.page, data.limit)}
        </div>
      </section>`;
  }

  function notifyLogHtml() {
    const rows = state.notifyLogs.length
      ? state.notifyLogs
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
      : "";
    return `
      <section class="wb-panel">
        <div class="wb-panel-head"><h2>推送记录</h2><span class="wb-hint">最近 30 条</span></div>
        <div class="wb-panel-body"><div class="wb-audit-list">${
          rows || '<div class="wb-empty">还没有推送记录。</div>'
        }</div></div>
      </section>`;
  }

  function bindLogEvents() {
    const tabs = $("logTabs");
    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-log-tab]");
      if (!button) return;
      state.logTab = button.dataset.logTab;
      state.logPage = 1;
      state.auditPage = 1;
      loadLogTab().catch((err) => toast(err.message));
    });
    const refresh = $("logRefreshBtn");
    refresh.addEventListener("click", () => {
      loadLogs().catch((err) => toast(err.message));
    });
    const panel = $("logPanel");
    panel.addEventListener("click", (event) => {
      const pageButton = event.target.closest("[data-log-page]");
      if (pageButton) {
        const page = Number(pageButton.dataset.logPage);
        if (page >= 1) {
          if (state.logTab === "audit") state.auditPage = page;
          else state.logPage = page;
          loadLogTab().catch((err) => toast(err.message));
        }
        return;
      }
      if (event.target.closest("#auditQueryBtn")) {
        state.auditFilters = {
          action: logFilterValue("auditAction"),
          q: logFilterValue("auditQ"),
          dateFrom: logFilterValue("auditDateFrom"),
          dateTo: logFilterValue("auditDateTo"),
        };
        state.auditPage = 1;
        loadLogTab().catch((err) => toast(err.message));
        return;
      }
      if (!event.target.closest("#logQueryBtn")) return;
      state.logFilters = {
        action: logFilterValue("logAction"),
        user: logFilterValue("logUser"),
        q: logFilterValue("logQ"),
        ip: logFilterValue("logIp"),
        dateFrom: logFilterValue("logDateFrom"),
        dateTo: logFilterValue("logDateTo"),
        path: logFilterValue("logPath"),
        visitor: logFilterValue("logVisitor"),
      };
      state.logPage = 1;
      loadLogTab().catch((err) => toast(err.message));
    });
    panel.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || !event.target.matches("input")) return;
      event.preventDefault();
      const button = $("logQueryBtn") || $("auditQueryBtn");
      if (button) button.click();
    });
  }

  // ---------- 留言审核与举报处理 ----------
  function uploadLimitMb(bytes) {
    const value = Number(bytes || 0) / (1024 * 1024);
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }

  async function loadUploadLimits() {
    const panel = $("uploadLimitsPanel");
    if (!panel) return;
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api("/api/admin/upload-limits");
      state.uploadLimitSchema = data.schema || [];
      state.uploadLimits = data.limits || {};
      state.uploadLimitDefaults = data.defaults || {};
      state.uploadLimitHardMaxBytes =
        Number(data.hard_max_bytes) || state.uploadLimitHardMaxBytes;
      state.uploadLimitHardMaxCount =
        Number(data.hard_max_count) || state.uploadLimitHardMaxCount;
      panel.innerHTML = uploadLimitsHtml();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function uploadLimitsHtml() {
    return (
      '<div class="wb-upload-limit-grid">' +
      state.uploadLimitSchema
        .map((item) => {
          const limits = state.uploadLimits[item.key] || {};
          const defaults = state.uploadLimitDefaults[item.key] || {};
          return `
            <section class="wb-panel wb-upload-limit-card" data-upload-limit-key="${escapeHtml(item.key)}">
              <div class="wb-panel-head">
                <h2>${escapeHtml(item.label)}</h2>
                <button class="wb-link-btn" type="button" data-upload-limit-reset="${escapeHtml(item.key)}">恢复默认</button>
              </div>
              <div class="wb-panel-body">
                <p class="wb-hint">${escapeHtml(item.description || "")}</p>
                <div class="wb-form-grid">
                  ${
                    item.count
                      ? `<label class="wb-field"><span>最大数量</span><input type="number" min="1" max="${state.uploadLimitHardMaxCount}" data-upload-field="count" value="${Number(limits.max_count || defaults.max_count || 1)}"></label>`
                      : ""
                  }
                  <label class="wb-field"><span>单文件上限（MB）</span><input type="number" min="0.001" step="0.1" max="${uploadLimitMb(state.uploadLimitHardMaxBytes)}" data-upload-field="file" value="${uploadLimitMb(limits.max_file_bytes || defaults.max_file_bytes)}"></label>
                  ${
                    item.total
                      ? `<label class="wb-field"><span>合计上限（MB）</span><input type="number" min="0.001" step="0.1" max="${uploadLimitMb(state.uploadLimitHardMaxBytes)}" data-upload-field="total" value="${uploadLimitMb(limits.max_total_bytes || defaults.max_total_bytes || limits.max_file_bytes)}"></label>`
                      : ""
                  }
                </div>
              </div>
            </section>`;
        })
        .join("") +
      "</div>"
    );
  }

  function bindUploadLimitEvents() {
    const panel = $("uploadLimitsPanel");
    if (panel) {
      panel.addEventListener("click", (event) => {
        const reset = event.target.closest("[data-upload-limit-reset]");
        if (!reset) return;
        const key = reset.dataset.uploadLimitReset;
        const card = panel.querySelector(`[data-upload-limit-key="${key}"]`);
        const defaults = state.uploadLimitDefaults[key] || {};
        if (!card) return;
        const count = card.querySelector('[data-upload-field="count"]');
        const file = card.querySelector('[data-upload-field="file"]');
        const total = card.querySelector('[data-upload-field="total"]');
        if (count) count.value = defaults.max_count || 1;
        if (file) file.value = uploadLimitMb(defaults.max_file_bytes);
        if (total) total.value = uploadLimitMb(defaults.max_total_bytes || defaults.max_file_bytes);
      });
    }
    const save = $("uploadLimitsSaveBtn");
    if (save) {
      save.addEventListener("click", async () => {
        if (!panel) return;
        const limits = {};
        state.uploadLimitSchema.forEach((item) => {
          const card = panel.querySelector(`[data-upload-limit-key="${item.key}"]`);
          if (!card) return;
          const count = card.querySelector('[data-upload-field="count"]');
          const file = card.querySelector('[data-upload-field="file"]');
          const total = card.querySelector('[data-upload-field="total"]');
          limits[item.key] = {
            max_count: count ? Number(count.value) : 1,
            max_file_bytes: Math.round(Number(file ? file.value : 0) * 1024 * 1024),
          };
          if (item.total) {
            limits[item.key].max_total_bytes = Math.round(
              Number(total ? total.value : 0) * 1024 * 1024
            );
          }
        });
        save.disabled = true;
        try {
          await api("/api/admin/upload-limits", {
            method: "POST",
            body: JSON.stringify({ limits }),
          });
          toast("上传限制已保存");
          await loadUploadLimits();
        } catch (err) {
          toast(err.message);
        } finally {
          save.disabled = false;
        }
      });
    }
  }

  function setDownloadsBadge(count) {
    const value = Number(count) || 0;
    const nav = $("downloadsNavBadge");
    if (nav) {
      nav.hidden = value <= 0;
      nav.textContent = value > 99 ? "99+" : String(value);
    }
  }

  async function loadDownloadRequests() {
    const panel = $("downloadRequestPanel");
    if (!panel) return;
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api(
        "/api/admin/download-requests?status=" +
          encodeURIComponent(state.downloadRequestStatus)
      );
      state.downloadRequests = data.items || [];
      setDownloadsBadge(data.pending || 0);
      panel.innerHTML = downloadRequestsHtml();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function downloadStatusLabel(status) {
    return {
      pending: "待处理",
      approved: "已批准",
      rejected: "已拒绝",
      revoked: "已撤销",
    }[status] || status;
  }

  function downloadRequestsHtml() {
    if (!state.downloadRequests.length) {
      return '<div class="wb-empty">没有匹配的下载申请。</div>';
    }
    return (
      '<div class="wb-review-grid">' +
      state.downloadRequests
        .map((row) => {
          const pending = row.status === "pending";
          const approved = row.status === "approved";
          const statusClass =
            row.status === "approved"
              ? "approved"
              : row.status === "pending"
                ? "pending"
                : "rejected";
          const actions = [
            pending
              ? `<button class="wb-btn wb-btn-primary" type="button" data-download-action="approve" data-download-id="${row.id}"><i data-lucide="check"></i><span>批准</span></button>`
              : "",
            pending
              ? `<button class="wb-btn wb-btn-danger" type="button" data-download-action="reject" data-download-id="${row.id}"><i data-lucide="x"></i><span>拒绝</span></button>`
              : "",
            approved
              ? `<button class="wb-btn wb-btn-danger" type="button" data-download-action="revoke" data-download-id="${row.id}"><i data-lucide="ban"></i><span>撤销</span></button>`
              : "",
          ].join("");
          return `
            <article class="wb-review-card">
              <div class="wb-review-thumb"><i data-lucide="download"></i></div>
              <div class="wb-review-body">
                <div class="wb-user-title">
                  <strong>${escapeHtml(row.resource_title || "文件已删除")}</strong>
                  <span class="wb-chip wb-chip-${statusClass}">${escapeHtml(downloadStatusLabel(row.status))}</span>
                </div>
                <div class="wb-user-meta">
                  ${escapeHtml(row.resource_kind || "")} · ${escapeHtml(row.user_name || "用户")} · 申请 ${formatTime(row.updated_at || row.created_at)}
                </div>
                ${row.reviewed_by ? `<p class="wb-review-text">处理人：${escapeHtml(row.reviewed_by)} · ${formatTime(row.reviewed_at)}</p>` : ""}
              </div>
              <div class="wb-user-actions">${actions}</div>
            </article>`;
        })
        .join("") +
      "</div>"
    );
  }

  function bindDownloadEvents() {
    const refresh = $("downloadsRefreshBtn");
    if (refresh) {
      refresh.addEventListener("click", () => {
        loadDownloadRequests().catch((err) => toast(err.message));
      });
    }
    const tabs = $("downloadRequestTabs");
    if (tabs) {
      tabs.addEventListener("click", (event) => {
        const button = event.target.closest("[data-download-status]");
        if (!button) return;
        state.downloadRequestStatus = button.dataset.downloadStatus;
        tabs.querySelectorAll("button").forEach((item) => {
          item.classList.toggle("active", item === button);
        });
        loadDownloadRequests();
      });
    }
    const panel = $("downloadRequestPanel");
    if (!panel) return;
    panel.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-download-action]");
      if (!button) return;
      if (button.dataset.downloadAction === "reject" && button.dataset.armed !== "1") {
        button.dataset.armed = "1";
        button.querySelector("span").textContent = "再点一次确认";
        setTimeout(() => {
          if (button.isConnected) {
            button.dataset.armed = "0";
            button.querySelector("span").textContent = "拒绝";
          }
        }, 4000);
        return;
      }
      try {
        await api(`/api/admin/download-requests/${button.dataset.downloadId}`, {
          method: "POST",
          body: JSON.stringify({ action: button.dataset.downloadAction }),
        });
        toast("下载申请已更新");
        await loadDownloadRequests();
      } catch (err) {
        toast(err.message);
      }
    });
  }

  function setReviewBadge(count) {
    const value = Number(count) || 0;
    const nav = $("reviewNavBadge");
    if (nav) {
      nav.hidden = value <= 0;
      nav.textContent = value > 99 ? "99+" : String(value);
    }
  }

  function setReportsBadge(count) {
    const value = Number(count) || 0;
    const nav = $("reportsNavBadge");
    if (nav) {
      nav.hidden = value <= 0;
      nav.textContent = value > 99 ? "99+" : String(value);
    }
    const panel = $("reportPendingCount");
    if (panel) {
      panel.hidden = value <= 0;
      panel.textContent = value > 99 ? "99+" : String(value);
    }
  }

  async function loadReview() {
    const panel = $("reviewPanel");
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api("/api/admin/review?status=pending");
      state.reviewMessages = data.messages || [];
      state.reviewLegacyFiles = data.legacy_files || [];
      setReviewBadge(data.pending || 0);
      panel.innerHTML = reviewHtml();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function reviewHtml() {
    if (!state.reviewMessages.length && !state.reviewLegacyFiles.length) {
      return '<div class="wb-empty">没有待审核的留言。</div>';
    }
    return (
      '<div class="wb-review-grid">' +
      state.reviewMessages.map((message) => {
        const files = (message.files || []).map((file) => {
          const thumb = file.is_image
            ? `<button class="wb-review-thumb wb-review-thumb-btn" type="button" data-review-preview="${file.id}" title="点击预览">
                 <img src="${escapeHtml(file.url)}" alt="" loading="lazy">
               </button>`
            : '<i data-lucide="file-text"></i>';
          return `<div class="wb-report-file">
            ${file.is_image ? thumb : `<div class="wb-review-thumb">${thumb}</div>`}
            <span>${escapeHtml(file.file_name || "")} · ${formatBytes(file.file_size || 0)}</span>
          </div>`;
        }).join("");
        return `
        <article class="wb-review-card">
          <div class="wb-review-body">
            <div class="wb-user-title">
              <strong>留言 #${message.id} · ${escapeHtml(message.message_author || message.message_nickname || "匿名")}</strong>
              <span class="wb-chip wb-chip-pending">待审核</span>
            </div>
            <div class="wb-user-meta">
              发布时间 ${formatTime(message.created_at)}
            </div>
            <p class="wb-review-text">${escapeHtml(message.message_content || "（仅附件）")}</p>
            <div class="wb-report-files">${files || '<span class="wb-user-meta">无附件</span>'}</div>
          </div>
          <div class="wb-user-actions">
            <button class="wb-btn wb-btn-primary" type="button" data-review-message="approve" data-review-id="${message.id}">
              <i data-lucide="check"></i><span>通过</span>
            </button>
            <button class="wb-btn wb-btn-danger" type="button" data-review-message="reject" data-review-id="${message.id}">
              <i data-lucide="x"></i><span>拒绝</span>
            </button>
          </div>
        </article>`;
      }).join("") +
      state.reviewLegacyFiles.map((file) => {
        const thumb = file.is_image
          ? `<button class="wb-review-thumb wb-review-thumb-btn" type="button" data-review-preview="${file.id}" title="点击预览">
               <img src="${escapeHtml(file.url)}" alt="" loading="lazy">
             </button>`
          : '<i data-lucide="file-text"></i>';
        return `
        <article class="wb-review-card">
          ${file.is_image ? thumb : `<div class="wb-review-thumb">${thumb}</div>`}
          <div class="wb-review-body">
            <div class="wb-user-title">
              <strong>历史附件 · ${escapeHtml(file.file_name)}</strong>
              <span class="wb-chip wb-chip-pending">待审核</span>
            </div>
            <div class="wb-user-meta">
              ${escapeHtml(file.message_author || file.message_nickname || "匿名")} · ${formatTime(file.created_at)}
            </div>
            <p class="wb-review-text">${escapeHtml((file.message_content || "").slice(0, 160))}</p>
          </div>
          <div class="wb-user-actions">
            <button class="wb-btn wb-btn-primary" type="button" data-review-file="approve" data-review-file-id="${file.id}">
              <i data-lucide="check"></i><span>通过</span>
            </button>
            <button class="wb-btn wb-btn-danger" type="button" data-review-file="reject" data-review-file-id="${file.id}">
              <i data-lucide="x"></i><span>拒绝</span>
            </button>
          </div>
        </article>`;
      }).join("") +
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
          toast(`已通过 ${data.approved_messages || 0} 条留言和 ${data.approved_legacy_files || 0} 个历史附件`);
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
        const file = state.reviewLegacyFiles.find(
          (item) => String(item.id) === previewBtn.dataset.reviewPreview
        ) || state.reviewMessages
          .flatMap((message) => message.files || [])
          .find((item) => String(item.id) === previewBtn.dataset.reviewPreview);
        if (file) openReviewPreview(file);
        return;
      }
      const messageButton = event.target.closest("[data-review-message]");
      const fileButton = event.target.closest("[data-review-file]");
      if (!messageButton && !fileButton) return;
      try {
        if (messageButton) {
          const action = messageButton.dataset.reviewMessage;
          let reviewNote = "";
          if (action === "reject") {
            reviewNote = await window.ErrorDialog.prompt("拒绝原因（可选）", {
              title: "拒绝留言",
              placeholder: "填写原因，可留空",
            });
            if (reviewNote === null) return;
          }
          await api(`/api/admin/review/${messageButton.dataset.reviewId}`, {
            method: "POST",
            body: JSON.stringify({ action, review_note: reviewNote }),
          });
        } else {
          await api(`/api/admin/review-files/${fileButton.dataset.reviewFileId}`, {
            method: "POST",
            body: JSON.stringify({ action: fileButton.dataset.reviewFile }),
          });
        }
        toast("审核结果已保存");
        await loadReview();
      } catch (err) {
        toast(err.message);
      }
    });
  }

  async function loadReports() {
    const panel = $("reportsPanel");
    panel.innerHTML = '<div class="wb-empty">正在加载…</div>';
    try {
      const data = await api(`/api/admin/reports?status=${encodeURIComponent(state.reportStatus)}`);
      state.reports = data.reports || [];
      state.reportPendingCount = Number(data.pending) || 0;
      setReportsBadge(state.reportPendingCount);
      panel.innerHTML = reportHtml();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      panel.innerHTML = `<div class="wb-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function reportStatusLabel(status) {
    return { pending: "待处理", resolved: "已处理", dismissed: "已驳回" }[status] || status;
  }

  function reportTargetLabel(type) {
    return { message: "留言", moment: "动态", game: "游戏", book: "电子书", recommendation: "推荐" }[type] || type;
  }

  function reportHtml() {
    if (!state.reports.length) {
      return '<div class="wb-empty">当前没有举报记录。</div>';
    }
    return '<div class="wb-review-grid">' + state.reports.map((report) => {
      const snapshot = report.target_snapshot_data || {};
      const content = snapshot.content || snapshot.description || snapshot.title || "";
      const actions = report.status === "pending"
        ? `<button class="wb-btn wb-btn-primary" type="button" data-report-action="resolve" data-report-id="${report.id}"><i data-lucide="check"></i><span>处理完成</span></button>
           <button class="wb-btn" type="button" data-report-action="dismiss" data-report-id="${report.id}"><i data-lucide="x"></i><span>驳回举报</span></button>`
        : `<button class="wb-btn" type="button" data-report-action="reopen" data-report-id="${report.id}"><i data-lucide="rotate-ccw"></i><span>重新打开</span></button>`;
      return `
        <article class="wb-review-card wb-report-card">
          <div class="wb-review-body">
            <div class="wb-user-title">
              <strong>${escapeHtml(report.target_title || "未命名内容")}</strong>
              <span class="wb-chip ${report.status === "pending" ? "wb-chip-pending" : ""}">${escapeHtml(reportStatusLabel(report.status))}</span>
              ${report.overdue ? '<span class="wb-chip wb-chip-danger">超过 24 小时</span>' : ""}
            </div>
            <div class="wb-user-meta">
              ${escapeHtml(reportTargetLabel(report.target_type))} · ${escapeHtml(report.reporter_name || "游客")} · ${formatTime(report.created_at)} · ${escapeHtml(report.ip || "")}
            </div>
            <p class="wb-review-text"><strong>理由：</strong>${escapeHtml(report.reason || "")}</p>
            ${report.detail ? `<p class="wb-review-text">${escapeHtml(report.detail)}</p>` : ""}
            ${report.contact ? `<div class="wb-user-meta">联系方式：${escapeHtml(report.contact)}</div>` : ""}
            ${content ? `<pre class="wb-report-snapshot">${escapeHtml(String(content).slice(0, 800))}</pre>` : ""}
            ${report.resolution ? `<div class="wb-user-meta">处理说明：${escapeHtml(report.resolution)}</div>` : ""}
            ${report.handled_by ? `<div class="wb-user-meta">处理人：${escapeHtml(report.handled_by)} · ${formatTime(report.handled_at)}</div>` : ""}
          </div>
          <div class="wb-user-actions">${actions}</div>
        </article>`;
    }).join("") + "</div>";
  }

  function bindReportEvents() {
    const refresh = $("reportsRefreshBtn");
    if (refresh) {
      refresh.addEventListener("click", () => loadReports().catch((err) => toast(err.message)));
    }
    const tabs = $("reportTabs");
    if (tabs) {
      tabs.addEventListener("click", (event) => {
        const button = event.target.closest("[data-report-status]");
        if (!button) return;
        state.reportStatus = button.dataset.reportStatus;
        tabs.querySelectorAll("button").forEach((item) => {
          item.classList.toggle("active", item === button);
        });
        loadReports().catch((err) => toast(err.message));
      });
    }
    const panel = $("reportsPanel");
    if (!panel) return;
    panel.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-report-action]");
      if (!button) return;
      const action = button.dataset.reportAction;
      let resolution = "";
      if (action !== "reopen") {
        resolution = await window.ErrorDialog.prompt("处理说明（可选）", {
          title: action === "resolve" ? "处理完成" : "驳回举报",
          placeholder: "填写处理说明，可留空",
        });
        if (resolution === null) return;
      }
      try {
        await api(`/api/admin/reports/${button.dataset.reportId}`, {
          method: "POST",
          body: JSON.stringify({ action, resolution }),
        });
        toast("举报状态已更新");
        await loadReports();
        await refreshNavBadges();
      } catch (err) {
        toast(err.message);
      }
    });
  }

  boot();
})();
