(function () {
  const state = {
    view: "overview",
    assets: [],
    repairs: [],
    projects: [],
    editingAssetId: null,
    editingRepairId: null,
    assetCategory: "document",
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
    if (view === "assets" || view === "firmware") loadAssets();
    if (view === "repairs") loadRepairs();
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
    try {
      state.projects = await api("/api/projects");
      syncProjectSelects();
      await Promise.all([loadSummary(), loadAssets(), loadRepairs()]);
      setView("overview");
    } catch (err) {
      toast(err.message || "工作台加载失败");
    }
  }

  boot();
})();
