const state = {
  page: "dashboard",
  manageTab: "categories",
  categories: [],
  locations: [],
  projects: [],
  parts: [],
  inventory: [],
  wishlist: [],
  dashboard: null,
  partsSearch: "",
  partsCategory: "",
  partsLocation: "",
  stockSearch: "",
  locationFilter: "",
  stockCategory: "",
  expandedLocations: new Set(),
  expandedCategories: new Set(),
  importFile: null,
  bomFile: null,
  projectBomFile: null,
  partImageFile: null,
  partImageRemoved: false,
  bomStatus: null,
  bomReports: [],
  movementItems: [],
  movementType: "",
  confirmAction: null,
};

const $ = (id) => document.getElementById(id);

let themePreference = localStorage.getItem("errorSiteTheme") || "auto";

function applyTheme(preference, save = true) {
  themePreference = preference;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = preference === "dark" || (preference === "auto" && systemDark);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#171717" : "#ffffff");
  if (save) localStorage.setItem("errorSiteTheme", preference);
  const button = $("themeToggle");
  if (button) {
    const glyph = button.querySelector(".theme-glyph");
    if (glyph) glyph.textContent = dark ? "☾" : "☀";
    button.title = dark ? "外观：深色" : "外观：浅色";
  }
}

window.addEventListener("storage", (event) => {
  if (event.key === "errorSiteTheme" && event.newValue) {
    applyTheme(event.newValue, false);
  }
});

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeUrl(value) {
  const text = String(value || "").trim();
  return /^https?:\/\//i.test(text) ? text : "";
}

function numText(value) {
  const n = Number(value || 0);
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(3).replace(/\.?0+$/, "");
}

function priceText(value) {
  const n = Number(value || 0);
  return n ? "¥" + n.toFixed(2) : "—";
}

function shortDate(value) {
  if (!value) return "—";
  return String(value).slice(0, 10);
}

function pathFor(rows, id, field = "name") {
  if (!id) return "";
  const byId = new Map(rows.map((row) => [row.id, row]));
  const chain = [];
  const seen = new Set();
  let current = byId.get(Number(id));
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    chain.push(current[field] || "");
    current = current.parent_id ? byId.get(current.parent_id) : null;
  }
  return chain.reverse().join("/");
}

async function api(path, options = {}) {
  const config = {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  const response = await fetch(path, config);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function showToast(message, type = "success") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = "toast " + type;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.hidden = true;
  }, 2600);
}

function openModal(id) {
  $(id).hidden = false;
}

function closeModal(id) {
  $(id).hidden = true;
}

function closeAllModals() {
  document.querySelectorAll(".modal-overlay").forEach((modal) => {
    modal.hidden = true;
  });
}

function openDrawer(html) {
  const drawer = $("drawer");
  $("drawerBody").innerHTML = html;
  drawer.hidden = false;
  $("drawerBackdrop").hidden = false;
  document.body.style.overflow = "hidden";
  lucide.createIcons();
}

function closeDrawer() {
  const drawer = $("drawer");
  drawer.hidden = true;
  $("drawerBackdrop").hidden = true;
  document.body.style.overflow = "";
}

function positionImageZoom(event) {
  const zoom = $("imageZoom");
  const width = zoom.offsetWidth;
  const height = zoom.offsetHeight;
  let left = event.clientX - width - 16;
  let top = event.clientY - height - 16;
  if (left < 12) left = event.clientX + 16;
  if (top < 12) top = event.clientY + 16;
  left = Math.max(12, Math.min(left, window.innerWidth - width - 12));
  top = Math.max(12, Math.min(top, window.innerHeight - height - 12));
  zoom.style.left = `${left}px`;
  zoom.style.top = `${top}px`;
}

function showImageZoom(img, event) {
  const zoom = $("imageZoom");
  zoom.querySelector("img").src = img.src;
  zoom.hidden = false;
  positionImageZoom(event);
}

function hideImageZoom() {
  const zoom = $("imageZoom");
  zoom.hidden = true;
  zoom.querySelector("img").src = "";
}

function updateBackTop() {
  $("backTop").hidden = window.scrollY < 240;
}

function confirmDialog(text, action) {
  state.confirmAction = action;
  $("confirmText").textContent = text;
  openModal("confirmModal");
}

async function loadAll() {
  const [categories, locations, projects, parts, inventory, wishlist, dashboard] =
    await Promise.all([
      api("/api/categories"),
      api("/api/locations"),
      api("/api/projects"),
      api("/api/parts"),
      api("/api/inventory"),
      api("/api/wishlist"),
      api("/api/dashboard"),
    ]);
  state.categories = categories;
  state.locations = locations;
  state.projects = projects;
  state.parts = parts;
  state.inventory = inventory;
  state.wishlist = wishlist;
  state.dashboard = dashboard;
  populateSelects();
  renderCurrentPage();
}

function renderCurrentPage() {
  if (state.page === "dashboard") renderDashboard();
  if (state.page === "parts") renderParts();
  if (state.page === "stock") renderStock();
  if (state.page === "projects") renderProjects();
  if (state.page === "wishlist") renderWishlist();
  if (state.page === "bom") renderBomPage();
  if (state.page === "manage") renderManage();
  lucide.createIcons();
}

const pageHeadAutoHide = { hidden: false, lastY: 0, ticking: false };

function setPageHeadHidden(hidden) {
  pageHeadAutoHide.hidden = Boolean(hidden);
  document.body.classList.toggle("head-hidden", pageHeadAutoHide.hidden);
}

// 向下滚动（内容上滑）时顶部标题栏向上收起，向上滚动（内容下滑）时再滑出来。
function bindPageHeadAutoHide() {
  pageHeadAutoHide.lastY = window.scrollY;
  window.addEventListener("scroll", () => {
    if (pageHeadAutoHide.ticking) return;
    pageHeadAutoHide.ticking = true;
    window.requestAnimationFrame(() => {
      pageHeadAutoHide.ticking = false;
      const y = window.scrollY;
      const delta = y - pageHeadAutoHide.lastY;
      if (Math.abs(delta) < 6) return;
      pageHeadAutoHide.lastY = y;
      if (y <= 8 || delta < 0) {
        setPageHeadHidden(false);
      } else if (y > 90) {
        setPageHeadHidden(true);
      }
    });
  }, { passive: true });
}

function switchPage(page, options) {
  const opts = options || {};
  state.page = page;
  // 首屏恢复（打开默认仪表盘 / 刷新回到原页面）不写回记录，只有用户主动切换才记
  if (opts.persist !== false) {
    try {
      localStorage.setItem("inventoryPage", page);
    } catch (err) {}
  }
  document.querySelectorAll(".nav-link, .bottom-link").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === page);
  });
  document.querySelectorAll(".page").forEach((section) => {
    const isTarget = section.id === `page-${page}`;
    section.hidden = !isTarget;
    section.classList.remove("is-enter");
    if (isTarget && opts.animate) {
      void section.offsetWidth;  // 强制重排，保证连续切换时动画能重新播放
      section.classList.add("is-enter");
    }
  });
  const sidebar = document.querySelector(".app-sidebar");
  if (sidebar) sidebar.classList.remove("open");
  renderCurrentPage();
  window.scrollTo(0, 0);
  setPageHeadHidden(false);
}

function populateSelects() {
  const categoryChildren = {};
  state.categories.forEach((item) => {
    const parentKey = item.parent_id ? String(item.parent_id) : "root";
    (categoryChildren[parentKey] = categoryChildren[parentKey] || []).push(item);
  });
  const sortCategory = (a, b) =>
    (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id;
  const renderCategoryOptions = (parentKey, depth) => {
    return (categoryChildren[parentKey] || [])
      .sort(sortCategory)
      .map((item) => {
        const indent = depth ? "\u3000".repeat(depth) : "";
        return (
          `<option value="${item.id}">${escapeHtml(indent + item.name)}</option>` +
          renderCategoryOptions(String(item.id), depth + 1)
        );
      })
      .join("");
  };
  const categoryOptions = (categoryChildren["root"] || [])
    .sort(sortCategory)
    .map(
      (root) =>
        `<optgroup label="${escapeHtml(root.name)}">` +
        `<option value="${root.id}">${escapeHtml(root.name)}</option>` +
        renderCategoryOptions(String(root.id), 1) +
        `</optgroup>`
    )
    .join("");
  const sortedLocations = [...state.locations].sort((a, b) => {
    const aRoot = a.parent_id ? 1 : 0;
    const bRoot = b.parent_id ? 1 : 0;
    if (aRoot !== bRoot) return aRoot - bRoot;
    return (a.sort_order || 0) - (b.sort_order || 0) || a.code.localeCompare(b.code);
  });
  const locationOptions = sortedLocations
    .map(
      (item) =>
        `<option value="${item.id}">${escapeHtml(pathFor(state.locations, item.id, "code"))}</option>`
    )
    .join("");
  const projectOptions = state.projects
    .map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`)
    .join("");

  $("partsCategory").innerHTML =
    `<option value="">全部分类</option>` + categoryOptions;
  $("partsLocation").innerHTML =
    `<option value="">全部位置</option>` + locationOptions;
  $("partCategory").innerHTML =
    `<option value="">未分类</option>` + categoryOptions;
  $("importCategory").innerHTML =
    `<option value="">未分类</option>` + categoryOptions;
  $("convertCategory").innerHTML =
    `<option value="">未分类</option>` + categoryOptions;
  $("stockInLocation").innerHTML = locationOptions;
  $("importLocation").innerHTML = locationOptions;
  $("convertLocation").innerHTML = locationOptions;
  $("partStockLocation").innerHTML = locationOptions;
  $("stockOutProject").innerHTML = projectOptions;
  $("partProject").innerHTML = `<option value="">不关联</option>` + projectOptions;
  $("movementProject").innerHTML = `<option value="">不关联</option>` + projectOptions;
  $("wishlistPart").innerHTML =
    `<option value="">暂不关联</option>` +
    state.parts
      .map(
        (item) =>
          `<option value="${item.id}">${escapeHtml(item.part_number)}${item.lcsc_code ? " / " + escapeHtml(item.lcsc_code) : ""}</option>`
      )
      .join("");
  $("stockInPart").innerHTML =
    `<option value="">选择元件</option>` +
    state.parts
      .map(
        (item) =>
          `<option value="${item.id}">${escapeHtml(item.part_number)}${item.lcsc_code ? " / " + escapeHtml(item.lcsc_code) : ""}</option>`
      )
      .join("");
  $("stockOutPart").innerHTML =
    `<option value="">选择元件</option>` +
    state.parts
      .map(
        (item) =>
          `<option value="${item.id}">${escapeHtml(item.part_number)}${item.lcsc_code ? " / " + escapeHtml(item.lcsc_code) : ""}</option>`
      )
      .join("");
}

function renderDashboard() {
  const data = state.dashboard || { stats: {}, low_stock: [], recent_movements: [] };
  const stats = data.stats || {};
  $("page-dashboard").innerHTML = `
    <div class="page-head">
      <div>
        <h1>仪表盘</h1>
        <p class="page-sub">库存、出入库和待购入概览</p>
      </div>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label"><i data-lucide="cpu"></i><span>元件种类</span></div>
        <div class="stat-value">${numText(stats.part_count)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label"><i data-lucide="archive"></i><span>当前库存</span></div>
        <div class="stat-value">${numText(stats.stock_quantity)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label"><i data-lucide="upload"></i><span>已出库</span></div>
        <div class="stat-value">${numText(stats.used_quantity)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label"><i data-lucide="shopping-cart"></i><span>待购入</span></div>
        <div class="stat-value">${numText(stats.wishlist_count)}</div>
      </div>
    </div>
    <div class="dash-grid">
      <div class="panel">
        <div class="panel-title"><i data-lucide="bell-ring"></i><span>低库存提醒</span></div>
        ${
          data.low_stock.length
            ? data.low_stock
                .map(
                  (item) => `
                    <div class="item-row">
                      <div class="item-main">
                        <div class="item-title">
                          <span>${escapeHtml(item.part_number)}</span>
                          ${item.lcsc_code ? `<span class="badge badge-accent">${escapeHtml(item.lcsc_code)}</span>` : ""}
                          <span class="badge badge-danger">库存 ${numText(item.stock_quantity)}</span>
                        </div>
                        <div class="item-sub"><span>最低 ${numText(item.min_stock)}</span></div>
                      </div>
                      <div class="row-actions">
                        <button class="btn btn-sm" data-action="part-detail" data-id="${item.id}">查看</button>
                        <button class="btn btn-sm btn-primary" data-action="part-in" data-id="${item.id}">入库</button>
                      </div>
                    </div>`
                )
                .join("")
            : `<div class="empty-state"><i data-lucide="check-circle-2"></i><p>暂无低库存元件</p></div>`
        }
      </div>
      <div class="panel">
        <div class="panel-title"><i data-lucide="history"></i><span>最近出入库</span></div>
        ${
          data.recent_movements.length
            ? data.recent_movements
                .map(
                  (item) => `
                    <div class="item-row">
                      <div class="item-main">
                        <div class="item-title">
                          <span>${escapeHtml(item.part_number)}</span>
                          <span class="badge ${item.movement_type === "in" ? "badge-accent" : "badge-warn"}">${item.movement_type === "in" ? "入库" : "出库"}</span>
                          <span class="qty">${numText(item.quantity)}</span>
                        </div>
                        <div class="item-sub">
                          <span>${escapeHtml(item.project_name || "未关联项目")}</span>
                          <span>${escapeHtml(shortDate(item.created_at))}</span>
                        </div>
                      </div>
                      <button class="btn btn-sm" data-action="part-detail" data-id="${item.part_id}">查看</button>
                    </div>`
                )
                .join("")
            : `<div class="empty-state"><i data-lucide="inbox"></i><p>暂无出入库记录</p></div>`
        }
      </div>
    </div>`;
}

function locationIdSet(rootId) {
  const ids = new Set();
  const walk = (id) => {
    ids.add(String(id));
    state.locations
      .filter((item) => String(item.parent_id) === String(id))
      .forEach((child) => walk(child.id));
  };
  walk(rootId);
  return ids;
}

function categoryIdSet(rootId) {
  const ids = new Set();
  const walk = (id) => {
    ids.add(String(id));
    state.categories
      .filter((item) => String(item.parent_id) === String(id))
      .forEach((child) => walk(child.id));
  };
  walk(rootId);
  return ids;
}

function filteredParts() {
  const keyword = state.partsSearch.trim().toLowerCase();
  const locationIds = state.partsLocation ? locationIdSet(state.partsLocation) : null;
  return state.parts.filter((part) => {
    const categoryMatch =
      !state.partsCategory ||
      String(part.category_id) === String(state.partsCategory);
    const partInventory = state.inventory.filter(
      (row) => String(row.part_id) === String(part.id)
    );
    const locationMatch =
      !locationIds ||
      partInventory.some((row) => locationIds.has(String(row.location_id)));
    const searchMatch =
      !keyword ||
      [
        part.part_number,
        part.lcsc_code,
        part.brand,
        part.package,
        part.description,
        part.category_name,
        ...partInventory.flatMap((row) => [
          row.location_path,
          row.location_code,
          row.location_name,
        ]),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    return categoryMatch && locationMatch && searchMatch;
  });
}

function categoryRootName(categoryId) {
  const byId = new Map(state.categories.map((item) => [String(item.id), item]));
  let current = byId.get(String(categoryId));
  if (!current) return "";
  while (current.parent_id && byId.has(String(current.parent_id))) {
    current = byId.get(String(current.parent_id));
  }
  return current.name || "";
}

function categoryIconSvg(categoryId) {
  const name = categoryRootName(categoryId).toLowerCase();
  const svg = (body) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  if (name.includes("电阻") || name.includes("resistor")) {
    return svg(`<path d="M3 12h3l2-6 4 12 3-9 2 3h4"/>`);
  }
  if (name.includes("电容") || name.includes("capacitor")) {
    return svg(`<path d="M6 12h12M10 4v16M14 4v16"/>`);
  }
  if (name === "ic" || name.includes("芯片") || name.includes("单片机") || name.includes("mcu")) {
    return svg(`<rect x="5" y="4" width="14" height="16" rx="1"/><path d="M9 4v4M15 4v4M9 20v-4M15 20v-4M9 10v4M15 10v4"/>`);
  }
  if (name.includes("pcb") || name.includes("印制电路") || name.includes("电路板")) {
    return svg(`<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M8 8h4v4h4M8 8v-1M16 16h-4v-4M12 8V4M12 20v-4M4 12h4M16 12h4"/>`);
  }
  if (name.includes("oled") || name.includes("显示") || name.includes("屏幕")) {
    return svg(`<rect x="4" y="5" width="16" height="13" rx="1"/><path d="M9 18v2M15 18v2M7 8h4v4H7zM13 8h4v4h-4z"/>`);
  }
  if (name.includes("电感") || name.includes("inductor")) {
    return svg(`<path d="M4 12h3c0-3 2-3 2 0s2 3 2 0 2-3 2 0 2 3 2 0 2-3 2 0h3"/>`);
  }
  if (name.includes("二极管") || name.includes("diode")) {
    return svg(`<path d="M6 5l11 7-11 7V5zM17 5v14"/>`);
  }
  if (name.includes("晶体管") || name.includes("三极管") || name.includes("transistor")) {
    return svg(`<circle cx="12" cy="12" r="7"/><path d="M12 3v3M12 18v3M6 7l2 2M18 7l-2 2M5 12h3M16 12h3"/>`);
  }
  if (name.includes("连接器") || name.includes("接插件") || name.includes("connector")) {
    return svg(`<path d="M8 4v16M16 4v16M4 8h4M16 8h4M4 16h4M16 16h4"/>`);
  }
  if (name.includes("电源") || name.includes("power")) {
    return svg(`<rect x="7" y="4" width="10" height="16" rx="1"/><path d="M10 8h4v4h-4zM12 2v2M12 20v2"/>`);
  }
  if (name.includes("传感器") || name.includes("sensor")) {
    return svg(`<path d="M4 8a8 8 0 0 1 16 0M4 16a8 8 0 0 0 16 0M12 8v5M8 10v3M16 10v3"/>`);
  }
  if (name.includes("开关") || name.includes("switch")) {
    return svg(`<rect x="6" y="8" width="12" height="8" rx="1"/><path d="M10 4v4M14 4v4M10 16v4M14 16v4"/>`);
  }
  if (name.includes("其他") || name.includes("other")) {
    return svg(`<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M4 9h16M9 4v16"/>`);
  }
  return svg(`<rect x="5" y="6" width="14" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4"/>`);
}

function renderParts() {
  const parts = filteredParts();
  const container = $("partsList");
  if (!parts.length) {
    container.innerHTML = `<div class="empty-state"><i data-lucide="cpu"></i><p>没有找到元件</p></div>`;
    return;
  }
  container.innerHTML = parts
    .map((part) => {
      const locations = [
        ...new Set(
          state.inventory
            .filter((row) => String(row.part_id) === String(part.id))
            .map((row) => row.location_path)
            .filter(Boolean)
        ),
      ];
      const locationText = locations.length ? locations.join("、") : "未入库";
      const categoryIcon = categoryIconSvg(part.category_id);
      return `
        <div class="item-row">
          ${
            part.image_path
              ? `<img class="part-thumb" src="/api/parts/${part.id}/image?v=${encodeURIComponent(part.image_path)}" alt="">`
              : `<span class="part-thumb part-thumb-empty category-icon">${categoryIcon}</span>`
          }
          <div class="item-main">
            <div class="item-title">
              <span class="part-name">${escapeHtml(part.part_number)}</span>
              ${part.category_name ? `<span class="badge badge-accent">${escapeHtml(part.category_name)}</span>` : ""}
              <span class="badge badge-info">位置 ${escapeHtml(locationText)}</span>
              <span class="badge badge-warn">封装 ${escapeHtml(part.package || "未填")}</span>
            </div>
            <div class="item-sub">
              ${part.lcsc_code ? `<span class="text-muted">LCSC ${escapeHtml(part.lcsc_code)}</span>` : ""}
              <span class="text-muted">${escapeHtml(part.brand || "未填品牌")}</span>
              <span class="text-muted">${escapeHtml((part.description || "").slice(0, 60))}</span>
            </div>
          </div>
          <div class="item-meta">
            <div><div class="detail-label">库存</div><div class="qty">${numText(part.stock_quantity)}</div></div>
            <div><div class="detail-label">已用</div><div class="qty">${numText(part.used_quantity)}</div></div>
          </div>
          <div class="row-actions">
            <button class="btn btn-sm" data-action="part-in" data-id="${part.id}"><i data-lucide="download"></i>入库</button>
            <button class="btn btn-sm" data-action="part-out" data-id="${part.id}"><i data-lucide="upload"></i>出库</button>
            <button class="btn btn-sm btn-primary" data-action="part-detail" data-id="${part.id}">详情</button>
          </div>
        </div>`
    })
    .join("");
}

function renderStock() {
  $("locationTree").innerHTML = buildLocationTree(null);
  $("categoryTree").innerHTML = buildCategoryTree(null);
  document.querySelector(".location-all").classList.toggle("active", !state.locationFilter);
  document.querySelector(".category-all").classList.toggle("active", !state.stockCategory);
  const keyword = state.stockSearch.trim().toLowerCase();
  const categoryIds = state.stockCategory ? categoryIdSet(state.stockCategory) : null;
  const rows = state.inventory.filter((row) => {
    const locationMatch =
      !state.locationFilter || String(row.location_id) === String(state.locationFilter);
    const categoryMatch =
      !categoryIds || categoryIds.has(String(row.category_id));
    const searchMatch =
      !keyword ||
      [
        row.part_number,
        row.lcsc_code,
        row.brand,
        row.package,
        row.category_name,
        row.location_path,
        row.location_code,
        row.location_name,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    return locationMatch && categoryMatch && searchMatch;
  });
  const container = $("stockList");
  if (!rows.length) {
    container.innerHTML = `<div class="empty-state"><i data-lucide="archive"></i><p>当前筛选下没有库存</p></div>`;
    return;
  }
  container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>位置</th>
          <th>元件</th>
          <th>LCSC</th>
          <th>封装</th>
          <th>可用</th>
          <th>已用</th>
          <th>购买日期</th>
          <th>订单号</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td><strong>${escapeHtml(row.location_path)}</strong><div class="table-sub">${escapeHtml(row.location_name || "")}</div></td>
                <td class="table-main">
                  <div class="part-cell">
                    ${
                      row.image_path
                        ? `<img src="/api/parts/${row.part_id}/image?v=${encodeURIComponent(row.image_path)}" alt="">`
                        : `<span class="part-cell-icon category-icon">${categoryIconSvg(row.category_id)}</span>`
                    }
                    <div>
                      <strong>${escapeHtml(row.part_number)}</strong>
                      <div class="table-sub">${escapeHtml(row.brand || "")}</div>
                    </div>
                  </div>
                </td>
                <td>${escapeHtml(row.lcsc_code || "—")}</td>
                <td>${escapeHtml(row.package || "—")}</td>
                <td class="qty">${numText(row.quantity)}</td>
                <td>${numText(row.used_quantity)}</td>
                <td>${escapeHtml(shortDate(row.purchase_date))}</td>
                <td>${escapeHtml(row.order_number || "—")}</td>
                <td>
                  <div class="row-actions">
                    <button class="btn btn-sm" data-action="part-in" data-id="${row.part_id}">入库</button>
                    <button class="btn btn-sm" data-action="batch-out" data-id="${row.batch_id}" data-part="${row.part_id}">出库</button>
                    <button class="btn btn-sm btn-primary" data-action="part-detail" data-id="${row.part_id}">详情</button>
                  </div>
                </td>
              </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function buildLocationTree(parentId = null, depth = 0) {
  const children = state.locations.filter(
    (item) => (item.parent_id ?? null) === (parentId ?? null)
  );
  if (!children.length) return "";
  return children
    .map((item) => {
      const hasChildren = state.locations.some(
        (child) => (child.parent_id ?? null) === item.id
      );
      const expanded = state.expandedLocations.has(item.id);
      const active = state.locationFilter && String(state.locationFilter) === String(item.id);
      return `
        <div>
          <div class="tree-item">
            ${
              hasChildren
                ? `<button class="tree-node twisty ${expanded ? "open" : ""}" data-tree-toggle="${item.id}" aria-label="展开"><i data-lucide="chevron-right"></i></button>`
                : `<span class="tree-indent"></span>`
            }
            <button class="tree-node ${active ? "active" : ""}" data-location-id="${item.id}">
              <span>${escapeHtml(item.code)}</span>
              <span class="badge">${item.batch_count}</span>
            </button>
          </div>
          ${
            hasChildren && expanded
              ? `<div class="tree-children-list">${buildLocationTree(item.id, depth + 1)}</div>`
              : ""
          }
        </div>`;
    })
    .join("");
}

function categoryTreeCount(categoryId) {
  const ids = categoryIdSet(categoryId);
  return state.inventory.filter((row) => ids.has(String(row.category_id))).length;
}

function buildCategoryTree(parentId = null, depth = 0) {
  const children = state.categories.filter(
    (item) => (item.parent_id ?? null) === (parentId ?? null)
  );
  if (!children.length) return "";
  return children
    .map((item) => {
      const hasChildren = state.categories.some(
        (child) => (child.parent_id ?? null) === item.id
      );
      const expanded = state.expandedCategories.has(item.id);
      const active = state.stockCategory && String(state.stockCategory) === String(item.id);
      return `
        <div>
          <div class="tree-item">
            ${
              hasChildren
                ? `<button class="tree-node twisty ${expanded ? "open" : ""}" data-category-toggle="${item.id}" aria-label="展开"><i data-lucide="chevron-right"></i></button>`
                : `<span class="tree-indent"></span>`
            }
            <button class="tree-node ${active ? "active" : ""}" data-category-id="${item.id}">
              <span>${escapeHtml(item.name)}</span>
              <span class="badge">${categoryTreeCount(item.id)}</span>
            </button>
          </div>
          ${
            hasChildren && expanded
              ? `<div class="tree-children-list">${buildCategoryTree(item.id, depth + 1)}</div>`
              : ""
          }
        </div>`;
    })
    .join("");
}

function renderProjects() {
  const container = $("projectsList");
  if (!state.projects.length) {
    container.innerHTML = `<div class="empty-state"><i data-lucide="folder-kanban"></i><p>还没有项目</p></div>`;
    return;
  }
  container.innerHTML = state.projects
    .map(
      (project) => `
        <div class="project-card" data-action="project-detail" data-id="${project.id}">
          <div class="project-title">
            <h3>${escapeHtml(project.name)}</h3>
            <span class="badge ${project.status === "active" ? "badge-accent" : "badge"}">${project.status === "active" ? "进行中" : "已完成"}</span>
          </div>
          <div class="project-stats">
            <span><strong>${numText(project.used_quantity)}</strong> 个已用</span>
            <span><strong>${numText(project.part_count)}</strong> 种元件</span>
          </div>
          <p class="page-sub">${escapeHtml(project.description || "暂无描述")}</p>
          <div class="project-actions">
            <button class="btn btn-sm" data-action="project-edit" data-id="${project.id}"><i data-lucide="pencil"></i>编辑</button>
            <button class="btn btn-sm btn-danger" data-action="project-delete" data-id="${project.id}"><i data-lucide="trash-2"></i>删除</button>
          </div>
        </div>`
    )
    .join("");
}

function renderWishlist() {
  const container = $("wishlistList");
  if (!state.wishlist.length) {
    container.innerHTML = `<div class="empty-state"><i data-lucide="shopping-cart"></i><p>待购入清单是空的</p></div>`;
    return;
  }
  container.innerHTML = state.wishlist
    .map(
      (item) => `
        <div class="item-row">
          <div class="item-main">
            <div class="item-title">
              <span>${escapeHtml(item.part_number || item.linked_part_number || item.lcsc_code || "未命名元件")}</span>
              ${item.lcsc_code ? `<span class="badge badge-accent">${escapeHtml(item.lcsc_code)}</span>` : ""}
              <span class="badge ${item.status === "open" ? "badge-warn" : "badge-accent"}">${item.status === "open" ? "待购入" : "已购入"}</span>
              ${item.priority === "high" ? `<span class="badge badge-danger">高优先</span>` : ""}
            </div>
            <div class="item-sub">
              <span>${escapeHtml(item.brand || "未填品牌")}</span>
              <span>${escapeHtml(item.package || "未填封装")}</span>
              <span>目标 ${numText(item.target_quantity)}</span>
              <span>${priceText(item.unit_price)}</span>
              ${item.linked_part_number ? `<span>已关联 ${escapeHtml(item.linked_part_number)}</span>` : ""}
            </div>
          </div>
          <div class="row-actions">
            <button class="btn btn-sm btn-primary" data-action="wishlist-convert" data-id="${item.id}"><i data-lucide="package-check"></i>转为入库</button>
            <button class="btn btn-sm" data-action="wishlist-edit" data-id="${item.id}">编辑</button>
            <button class="btn btn-sm btn-danger" data-action="wishlist-delete" data-id="${item.id}">删除</button>
          </div>
        </div>`
    )
    .join("");
}

function renderManage() {
  const tabs = document.querySelectorAll(".manage-tab");
  tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.manage === state.manageTab));
  const content = $("manageContent");
  if (state.manageTab === "categories") {
    content.innerHTML = `
      <div class="manage-toolbar">
        <p class="page-sub">分类可无限层级，用于组织电阻、电容、IC、PCB 等。</p>
        <button class="btn btn-primary" data-action="category-add"><i data-lucide="plus"></i>新增根分类</button>
      </div>
      <div class="tree-list">${manageTree("categories", null, 0)}</div>`;
  } else if (state.manageTab === "locations") {
    content.innerHTML = `
      <div class="manage-toolbar">
        <p class="page-sub">第一级 XP/XA，第二级 A~Z，第三级开始可用 A1、A2 等。</p>
        <button class="btn btn-primary" data-action="location-add"><i data-lucide="plus"></i>新增一级位置</button>
      </div>
      <div class="tree-list">${manageTree("locations", null, 0)}</div>`;
  } else {
    content.innerHTML = `
      <div class="manage-toolbar">
        <p class="page-sub">项目用于出库时追溯元件去向。</p>
        <button class="btn btn-primary" data-action="project-add"><i data-lucide="plus"></i>新增项目</button>
      </div>
      <div class="list-stack">
        ${state.projects
          .map(
            (project) => `
              <div class="item-row">
                <div class="item-main">
                  <div class="item-title"><span>${escapeHtml(project.name)}</span><span class="badge ${project.status === "active" ? "badge-accent" : ""}">${project.status === "active" ? "进行中" : "已完成"}</span></div>
                  <div class="item-sub"><span>已用 ${numText(project.used_quantity)}</span><span>${numText(project.part_count)} 种元件</span></div>
                </div>
                <div class="row-actions">
                  <button class="btn btn-sm" data-action="project-edit" data-id="${project.id}">编辑</button>
                  <button class="btn btn-sm btn-danger" data-action="project-delete" data-id="${project.id}">删除</button>
                </div>
              </div>`
          )
          .join("")}
      </div>`;
  }
  lucide.createIcons();
}

function manageTree(type, parentId, depth) {
  const rows = type === "categories" ? state.categories : state.locations;
  const codeField = type === "locations" ? "code" : "name";
  const children = rows.filter((item) => (item.parent_id ?? null) === (parentId ?? null));
  if (!children.length) return "";
  return children
    .map((item) => {
      const countText =
        type === "categories" ? `${item.part_count} 个元件` : `${item.batch_count} 个批次`;
      const actionPrefix = type === "categories" ? "category" : "location";
      return `
        <div>
          <div class="tree-item">
            <div class="tree-item-main">
              ${depth ? `<span class="tree-indent"></span>` : ""}
              <strong>${escapeHtml(item[codeField])}</strong>
              <span class="badge">${countText}</span>
            </div>
            <div class="row-actions">
              <button class="btn btn-sm" data-action="${actionPrefix}-add" data-parent="${item.id}">添加下级</button>
              <button class="btn btn-sm" data-action="${actionPrefix}-edit" data-id="${item.id}">编辑</button>
              <button class="btn btn-sm btn-danger" data-action="${actionPrefix}-delete" data-id="${item.id}">删除</button>
            </div>
          </div>
          <div class="tree-children-list">${manageTree(type, item.id, depth + 1)}</div>
        </div>`;
    })
    .join("");
}

function openPartModal(part = null) {
  $("modalPartTitle").textContent = part ? "编辑元件" : "新增元件";
  $("partId").value = part ? part.id : "";
  $("partNumber").value = part ? part.part_number || "" : "";
  $("partLcsc").value = part ? part.lcsc_code || "" : "";
  $("partBrand").value = part ? part.brand || "" : "";
  $("partCategory").value = part ? part.category_id || "" : "";
  $("partPackage").value = part ? part.package || "" : "";
  $("partTemp").value = part ? part.temperature_range || "" : "";
  $("partVoltage").value = part ? part.voltage_rating || "" : "";
  $("partDescription").value = part ? part.description || "" : "";
  $("partDatasheet").value = part ? part.datasheet_url || "" : "";
  $("partMinStock").value = part ? part.min_stock || 0 : 0;
  $("partNotes").value = part ? part.notes || "" : "";
  $("partStockQty").value = part && part.stock_quantity !== undefined ? part.stock_quantity : "";
  const invRows = state.inventory.filter(
    (row) => part && String(row.part_id) === String(part.id)
  );
  $("partStockLocation").value = invRows.length ? String(invRows[0].location_id) : "";
  $("partProject").value = part && part.linked_project_id ? String(part.linked_project_id) : "";
  state.partImageFile = null;
  state.partImageRemoved = false;
  $("partImageFile").value = "";
  const previewWrap = $("partImagePreviewWrap");
  const preview = $("partImagePreview");
  if (part && part.image_path) {
    preview.src = `/api/parts/${part.id}/image?v=${encodeURIComponent(part.image_path)}`;
    previewWrap.hidden = false;
  } else {
    preview.src = "";
    previewWrap.hidden = true;
  }
  $("partImageDropzone").querySelector("strong").textContent = "选择元件图片";
  const partModalBox = $("modalPart").querySelector(".modal");
  window.scrollTo(0, 0);
  openModal("modalPart");
  if (partModalBox) partModalBox.scrollTop = 0;
}

function openStockIn(partId = null) {
  $("stockInPartId").value = partId || "";
  $("stockInPart").value = partId || "";
  $("stockInQty").value = "";
  $("stockInDate").value = new Date().toISOString().slice(0, 10);
  $("stockInPrice").value = "";
  $("stockInChannel").value = "";
  $("stockInOrder").value = "";
  $("stockInNotes").value = "";
  openModal("modalStockIn");
}

function openStockOut(partId = null, batchId = null) {
  $("stockOutPartId").value = partId || "";
  $("stockOutBatchId").value = batchId || "";
  $("stockOutPart").value = partId || "";
  $("stockOutQty").value = "";
  $("stockOutNote").value = "";
  updateStockOutBatches(batchId);
  openModal("modalStockOut");
}

function updateStockOutBatches(selectedBatchId = "") {
  const partId = $("stockOutPart").value;
  const rows = state.inventory.filter((row) => row.quantity > 0 && String(row.part_id) === String(partId));
  const options = rows.length
    ? rows
        .map(
          (row) =>
            `<option value="${row.batch_id}" ${String(row.batch_id) === String(selectedBatchId) ? "selected" : ""}>${escapeHtml(row.location_path)} / ${escapeHtml(shortDate(row.purchase_date))} / 可用 ${numText(row.quantity)}</option>`
        )
        .join("")
    : `<option value="">无可用库存</option>`;
  $("stockOutBatch").innerHTML =
    `<option value="">自动选择最早批次</option>` + options;
}

function openMovementModal(item) {
  state.movementType = item.movement_type;
  $("movementId").value = item.id;
  $("movementNote").value = item.note || "";
  $("movementTime").value = String(item.created_at || "").replace(" ", "T").slice(0, 16);
  const projectSelect = $("movementProject");
  projectSelect.value = item.project_id ? String(item.project_id) : "";
  projectSelect.disabled = item.movement_type === "in";
  openModal("modalMovement");
}

function openProjectModal(project = null) {
  $("modalProjectTitle").textContent = project ? "编辑项目" : "新增项目";
  $("projectId").value = project ? project.id : "";
  $("projectName").value = project ? project.name : "";
  $("projectStatus").value = project ? project.status : "active";
  $("projectDescription").value = project ? project.description || "" : "";
  state.projectBomFile = null;
  $("projectBomField").hidden = Boolean(project);
  $("projectBomDropzone").querySelector("strong").textContent = "选择 BOM（可选）";
  openModal("modalProject");
}

function openWishlistModal(item = null) {
  $("modalWishlistTitle").textContent = item ? "编辑待购" : "添加待购";
  $("wishlistId").value = item ? item.id : "";
  $("wishlistPart").value = item && item.part_id ? item.part_id : "";
  $("wishlistLcsc").value = item ? item.lcsc_code || "" : "";
  $("wishlistPartNumber").value = item ? item.part_number || "" : "";
  $("wishlistBrand").value = item ? item.brand || "" : "";
  $("wishlistPackage").value = item ? item.package || "" : "";
  $("wishlistQty").value = item ? item.target_quantity : 1;
  $("wishlistPrice").value = item ? item.unit_price || "" : "";
  $("wishlistPriority").value = item ? item.priority : "normal";
  $("wishlistDescription").value = item ? item.description || "" : "";
  $("wishlistNotes").value = item ? item.notes || "" : "";
  openModal("modalWishlist");
}

function openConvertModal(item) {
  $("convertId").value = item.id;
  $("convertQty").value = item.target_quantity || 1;
  $("convertDate").value = new Date().toISOString().slice(0, 10);
  $("convertPrice").value = item.unit_price || "";
  $("convertChannel").value = item.lcsc_code ? "LCSC" : "";
  $("convertOrder").value = "";
  $("convertNotes").value = "";
  openModal("modalConvert");
}

function openCategoryModal(parentId = null, category = null) {
  $("categoryId").value = category ? category.id : "";
  $("categoryParentId").value = parentId || "";
  $("categoryName").value = category ? category.name : "";
  openModal("modalCategory");
}

function openLocationModal(parentId = null, location = null) {
  $("locationId").value = location ? location.id : "";
  $("locationParentId").value = parentId || "";
  $("locationCode").value = location ? location.code : "";
  $("locationName").value = location ? location.name || "" : "";
  openModal("modalLocation");
}

async function openPartDrawer(partId) {
  try {
    const data = await api(`/api/parts/${partId}`);
    state.movementItems = data.movements;
    const part = data.part;
    const batchHtml = data.batches.length
      ? data.batches
          .map(
            (batch) => `
              <div class="item-row">
                <div class="item-main">
                  <div class="item-title"><span>${escapeHtml(batch.location_path || batch.location_code)}</span><span class="badge badge-accent">可用 ${numText(batch.quantity)}</span></div>
                  <div class="item-sub">
                    <span>购入 ${escapeHtml(shortDate(batch.purchase_date))}</span>
                    <span>${escapeHtml(batch.order_number || "无订单号")}</span>
                    <span>${escapeHtml(batch.channel || "无渠道")}</span>
                  </div>
                </div>
                <div class="row-actions">
                  <button class="btn btn-sm" data-action="batch-out" data-id="${batch.id}" data-part="${part.id}">出库</button>
                </div>
              </div>`
          )
          .join("")
      : `<div class="empty-state"><i data-lucide="archive"></i><p>暂无库存批次</p></div>`;
    const usageHtml = data.project_usage.length
      ? data.project_usage
          .map(
            (item) => `
              <div class="item-row">
                <div class="item-main">
                  <div class="item-title"><span>${escapeHtml(item.name)}</span><span class="badge">${item.status === "active" ? "进行中" : "已完成"}</span></div>
                  <div class="item-sub"><span>已用 ${numText(item.used_quantity)}</span><span>出库 ${numText(item.times)} 次</span></div>
                </div>
              </div>`
          )
          .join("")
      : `<div class="empty-state"><i data-lucide="folder-kanban"></i><p>还未关联项目</p></div>`;
    const movementHtml = data.movements.length
      ? data.movements
          .map(
            (item) => `
              <div class="item-row">
                <div class="item-main">
                  <div class="item-title">
                    <span class="badge ${item.movement_type === "in" ? "badge-accent" : "badge-warn"}">${item.movement_type === "in" ? "入库" : "出库"}</span>
                    <span class="qty">${numText(item.quantity)}</span>
                    <span>${escapeHtml(item.project_name || "未关联项目")}</span>
                  </div>
                  <div class="item-sub">
                    <span>${escapeHtml(shortDate(item.created_at))}</span>
                    <span>${escapeHtml(item.note || "")}</span>
                  </div>
                </div>
                <div class="row-actions">
                  <button class="btn btn-sm" data-action="movement-edit" data-id="${item.id}">编辑</button>
                  <button class="btn btn-sm btn-danger" data-action="movement-delete" data-id="${item.id}">删除</button>
                </div>
              </div>`
          )
          .join("")
      : `<div class="empty-state"><i data-lucide="history"></i><p>暂无出入库记录</p></div>`;
    const datasheet = safeUrl(part.datasheet_url);
    const linkedHtml = (data.linked_projects || []).length
      ? data.linked_projects
          .map((item) => `<span class="badge badge-info">${escapeHtml(item.name)}</span>`)
          .join("")
      : "—";
    openDrawer(`
      <div class="drawer-section">
        ${part.image_path ? `<img class="part-drawer-image" src="/api/parts/${part.id}/image?v=${encodeURIComponent(part.image_path)}" alt="元件图片">` : ""}
        <h2>${escapeHtml(part.part_number)}</h2>
        <div class="detail-actions">
          <button class="btn btn-primary" data-action="part-in" data-id="${part.id}"><i data-lucide="download"></i>入库</button>
          <button class="btn" data-action="part-out" data-id="${part.id}"><i data-lucide="upload"></i>出库</button>
          <button class="btn" data-action="part-edit" data-id="${part.id}"><i data-lucide="pencil"></i>编辑</button>
          <button class="btn btn-danger" data-action="part-delete" data-id="${part.id}"><i data-lucide="trash-2"></i>删除</button>
        </div>
        <div class="detail-grid">
          <div class="detail-field"><div class="detail-label">LCSC 编号</div><div class="detail-value">${escapeHtml(part.lcsc_code || "—")}</div></div>
          <div class="detail-field"><div class="detail-label">品牌 Brand</div><div class="detail-value">${escapeHtml(part.brand || "—")}</div></div>
          <div class="detail-field"><div class="detail-label">分类 Category</div><div class="detail-value">${escapeHtml(part.category_name || "未分类")}</div></div>
          <div class="detail-field"><div class="detail-label">封装 Package</div><div class="detail-value">${escapeHtml(part.package || "—")}</div></div>
          <div class="detail-field"><div class="detail-label">温度范围</div><div class="detail-value">${escapeHtml(part.temperature_range || "—")}</div></div>
          <div class="detail-field"><div class="detail-label">耐压 / 额定值</div><div class="detail-value">${escapeHtml(part.voltage_rating || "—")}</div></div>
          <div class="detail-field"><div class="detail-label">当前库存</div><div class="detail-value qty">${numText(part.stock_quantity)}</div></div>
          <div class="detail-field"><div class="detail-label">已出库</div><div class="detail-value qty">${numText(part.used_quantity)}</div></div>
          <div class="detail-field"><div class="detail-label">最低库存</div><div class="detail-value">${numText(part.min_stock)}</div></div>
          <div class="detail-field"><div class="detail-label">关联项目</div><div class="detail-value">${linkedHtml}</div></div>
          <div class="detail-field"><div class="detail-label">数据手册</div><div class="detail-value">${datasheet ? `<a href="${escapeHtml(datasheet)}" target="_blank" rel="noopener">打开 Datasheet</a>` : "—"}</div></div>
        </div>
        <p class="page-sub" style="margin-top:12px">${escapeHtml(part.description || "暂无描述")}</p>
      </div>
      <div class="drawer-section">
        <h3>库存批次</h3>
        ${batchHtml}
      </div>
      <div class="drawer-section">
        <h3>项目用量</h3>
        ${usageHtml}
      </div>
      <div class="drawer-section">
        <h3>出入库记录</h3>
        ${movementHtml}
      </div>
    `);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function openProjectDrawer(projectId) {
  const project = state.projects.find((item) => String(item.id) === String(projectId));
  if (!project) return;
  const movements = await api(`/api/movements?project_id=${projectId}`);
  state.movementItems = movements;
  const usageMap = new Map();
  movements
    .filter((item) => item.movement_type === "out")
    .forEach((item) => {
      const key = item.part_id;
      const current = usageMap.get(key) || { part_id: key, part_number: item.part_number, lcsc_code: item.lcsc_code, quantity: 0, times: 0 };
      current.quantity += Number(item.quantity || 0);
      current.times += 1;
      usageMap.set(key, current);
    });
  const usage = [...usageMap.values()].sort((a, b) => b.quantity - a.quantity);
  const usageHtml = usage.length
    ? usage
        .map(
          (item) => `
            <div class="item-row">
              <div class="item-main">
                <div class="item-title">
                  <span>${escapeHtml(item.part_number)}</span>
                  ${item.lcsc_code ? `<span class="badge badge-accent">${escapeHtml(item.lcsc_code)}</span>` : ""}
                </div>
                <div class="item-sub"><span>已用 ${numText(item.quantity)}</span><span>出库 ${numText(item.times)} 次</span></div>
              </div>
              <button class="btn btn-sm" data-action="part-detail" data-id="${item.part_id}">查看</button>
            </div>`
        )
        .join("")
    : `<div class="empty-state"><i data-lucide="folder-kanban"></i><p>该项目还没有出库记录</p></div>`;
  const movementHtml = movements.length
    ? movements
        .map(
          (item) => `
            <div class="item-row">
              <div class="item-main">
                <div class="item-title">
                  <span class="badge ${item.movement_type === "in" ? "badge-accent" : "badge-warn"}">${item.movement_type === "in" ? "入库" : "出库"}</span>
                  <span>${escapeHtml(item.part_number)}</span>
                  <span class="qty">${numText(item.quantity)}</span>
                </div>
                  <div class="item-sub"><span>${escapeHtml(shortDate(item.created_at))}</span><span>${escapeHtml(item.note || "")}</span></div>
                </div>
                <div class="row-actions">
                  <button class="btn btn-sm" data-action="movement-edit" data-id="${item.id}">编辑</button>
                  <button class="btn btn-sm btn-danger" data-action="movement-delete" data-id="${item.id}">删除</button>
                </div>
              </div>`
        )
        .join("")
    : `<div class="empty-state"><i data-lucide="history"></i><p>暂无记录</p></div>`;
  const allReports = await api("/api/bom/reports");
  const projectReports = allReports.filter(
    (report) => String(report.project_id) === String(projectId)
  );
  const projectBomHtml = projectReports.length
    ? projectReports
        .map((report) => {
          const summary = report.summary || {};
          return `
            <div class="report-item">
              <div class="report-item-main">
                <div class="report-item-title">
                  <span>${escapeHtml(report.file_name)}</span>
                  <span class="badge ${summary.shortage ? "badge-danger" : "badge-accent"}">缺料 ${numText(summary.shortage)}</span>
                  <span class="badge badge-warn">未匹配 ${numText(summary.unmatched)}</span>
                </div>
                <div class="report-item-sub"><span>${escapeHtml((report.created_at || "").slice(0, 19))}</span></div>
              </div>
              <div class="report-actions">
                <a class="btn btn-sm" href="/api/bom/reports/${encodeURIComponent(report.id)}/csv" download><i data-lucide="download"></i>CSV</a>
                <button class="btn btn-sm btn-primary" data-action="bom-view" data-id="${escapeHtml(report.id)}">查看</button>
              </div>
            </div>`;
        })
        .join("")
    : `<div class="empty-state"><i data-lucide="clipboard-list"></i><p>该项目还没有 BOM 对比记录</p></div>`;
  openDrawer(`
    <div class="drawer-section">
      <div class="project-title">
        <h2>${escapeHtml(project.name)}</h2>
        <span class="badge ${project.status === "active" ? "badge-accent" : ""}">${project.status === "active" ? "进行中" : "已完成"}</span>
      </div>
      <p class="page-sub" style="margin-top:10px">${escapeHtml(project.description || "暂无描述")}</p>
      <div class="detail-grid">
        <div class="detail-field"><div class="detail-label">已用数量</div><div class="detail-value">${numText(project.used_quantity)}</div></div>
        <div class="detail-field"><div class="detail-label">元件种类</div><div class="detail-value">${numText(project.part_count)}</div></div>
      </div>
      <div class="detail-actions" style="margin-top:14px">
        <button class="btn" data-action="project-edit" data-id="${project.id}"><i data-lucide="pencil"></i>编辑</button>
        <button class="btn btn-danger" data-action="project-delete" data-id="${project.id}"><i data-lucide="trash-2"></i>删除</button>
      </div>
    </div>
    <div class="drawer-section">
      <h3>BOM 缺料</h3>
      ${projectBomHtml}
    </div>
    <div class="drawer-section">
      <h3>元件用量</h3>
      ${usageHtml}
    </div>
    <div class="drawer-section">
      <h3>出入库记录</h3>
      ${movementHtml}
    </div>
  `);
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function renderBomWatchStatus() {
  const status = state.bomStatus || {};
  const errorHtml = status.last_error
    ? `<div class="error-text"><i data-lucide="alert-triangle"></i> ${escapeHtml(status.last_error)}</div>`
    : "";
  $("bomWatchStatus").innerHTML = `
    <div class="status-line"><span>状态</span><span><span class="badge ${status.running ? "badge-accent" : ""}">${status.running ? "监控中" : "未监控"}</span></span></div>
    <div class="status-line"><span>文件夹</span><span>${escapeHtml(status.folder || "—")}</span></div>
    <div class="status-line"><span>检查间隔</span><span>${status.interval || 30} 秒</span></div>
    <div class="status-line"><span>上次检查</span><span>${escapeHtml(status.last_run || "—")}</span></div>
    <div class="status-line"><span>已处理文件</span><span>${numText(status.processed_count || 0)}</span></div>
    ${errorHtml}
  `;
  lucide.createIcons();
}

function renderBomReports() {
  const container = $("bomReports");
  if (!state.bomReports.length) {
    container.innerHTML = `<div class="empty-state"><i data-lucide="history"></i><p>还没有对比记录</p></div>`;
    return;
  }
  container.innerHTML = state.bomReports
    .map((report) => {
      const summary = report.summary || {};
      return `
        <div class="report-item">
          <div class="report-item-main">
            <div class="report-item-title">
              <span>${escapeHtml(report.file_name)}</span>
              <span class="badge ${summary.shortage ? "badge-danger" : "badge-accent"}">缺料 ${numText(summary.shortage)}</span>
              <span class="badge badge-warn">未匹配 ${numText(summary.unmatched)}</span>
            </div>
            <div class="report-item-sub">
              <span>${escapeHtml(shortDate(report.created_at))} ${escapeHtml((report.created_at || "").slice(11, 19))}</span>
              <span>${numText(summary.item_count)} 行</span>
              ${report.project_name ? `<span>项目：${escapeHtml(report.project_name)}</span>` : ""}
            </div>
          </div>
          <div class="report-actions">
            <a class="btn btn-sm" href="/api/bom/reports/${encodeURIComponent(report.id)}/csv" download><i data-lucide="download"></i>CSV</a>
            <button class="btn btn-sm btn-primary" data-action="bom-view" data-id="${escapeHtml(report.id)}">查看</button>
          </div>
        </div>`;
    })
    .join("");
  lucide.createIcons();
}

async function refreshBomMeta() {
  try {
    const [status, reports] = await Promise.all([
      api("/api/bom/watch"),
      api("/api/bom/reports"),
    ]);
    state.bomStatus = status;
    state.bomReports = reports;
    renderBomWatchStatus();
    renderBomReports();
  } catch (error) {
    showToast(error.message || "无法读取 BOM 状态", "error");
  }
}

function renderBomPage() {
  $("bomWatchStatus").innerHTML = `<div class="page-sub">正在读取监控状态...</div>`;
  $("bomReports").innerHTML = `<div class="page-sub">正在加载...</div>`;
  refreshBomMeta();
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

function downloadBomCsv(items) {
  const headers = ["位号", "型号/规格", "封装", "LCSC", "需求数量", "库存可用", "缺口", "状态", "匹配元件ID", "匹配型号", "匹配LCSC", "匹配方式"];
  const lines = [headers.map(csvCell).join(",")];
  items.forEach((row) => {
    lines.push(
      [
        row.designators,
        row.mpn,
        row.package,
        row.lcsc,
        row.qty,
        row.stock,
        row.shortage,
        row.status,
        row.matched_part_id,
        row.matched_part_number,
        row.matched_lcsc,
        row.matched_by,
      ].map(csvCell).join(",")
    );
  });
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `BOM_缺料清单_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

function renderBomResult(report) {
  const summary = report.summary || {};
  const rowsHtml = report.items && report.items.length
    ? report.items
        .map((row) => {
          const cls = row.status === "缺料" ? "danger" : row.status === "未匹配" ? "warn" : "ok";
          const badgeCls = row.status === "缺料" ? "badge-danger" : row.status === "未匹配" ? "badge-warn" : "badge-accent";
          return `
            <tr class="${cls}">
              <td>${escapeHtml(row.designators)}</td>
              <td class="table-main">${escapeHtml(row.mpn || "—")}</td>
              <td>${escapeHtml(row.package || "—")}</td>
              <td>${escapeHtml(row.lcsc || "—")}</td>
              <td class="num">${numText(row.qty)}</td>
              <td class="num">${numText(row.stock)}</td>
              <td class="num">${numText(row.shortage)}</td>
              <td><span class="badge ${badgeCls}">${escapeHtml(row.status)}</span></td>
              <td>${escapeHtml(row.matched_part_number || "—")}</td>
              <td>${escapeHtml(row.matched_by || "—")}</td>
            </tr>`;
        })
        .join("")
    : `<tr><td colspan="10" class="empty-cell">没有可显示的数据</td></tr>`;
  $("bomResult").innerHTML = `
    <div class="bom-result">
      <h3>${escapeHtml(report.file_name || "对比结果")}</h3>
      <div class="stats">
        <div class="stat"><b>${numText(summary.item_count)}</b>元件行</div>
        <div class="stat"><b>${numText(summary.shortage)}</b>缺料</div>
        <div class="stat"><b>${numText(summary.unmatched)}</b>未匹配</div>
        <div class="stat"><b>${numText(summary.ok)}</b>充足</div>
      </div>
      <div class="toolbar">
        <button class="btn btn-primary" id="bomCsvExport"><i data-lucide="download"></i><span>导出 CSV</span></button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>位号</th><th>型号/规格</th><th>封装</th><th>LCSC</th><th>需求</th><th>库存</th><th>缺口</th><th>状态</th><th>匹配型号</th><th>匹配方式</th></tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
    </div>`;
  $("bomCsvExport").addEventListener("click", () => downloadBomCsv(report.items || []));
  lucide.createIcons();
}

async function runBomCompare() {
  if (!state.bomFile) {
    showToast("请先选择 BOM 文件", "error");
    return;
  }
  const button = $("bomRunBtn");
  button.disabled = true;
  button.querySelector("span").textContent = "正在对比...";
  try {
    const dataBase64 = await fileToBase64(state.bomFile);
    const result = await api("/api/bom/compare", {
      method: "POST",
      body: JSON.stringify({
        file_name: state.bomFile.name,
        data_base64: dataBase64,
        match_mode: $("bomMatchMode").value,
      }),
    });
    renderBomResult(result.report);
    await refreshBomMeta();
    showToast(`对比完成：缺料 ${result.report.summary.shortage}，未匹配 ${result.report.summary.unmatched}`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "开始对比";
  }
}

async function startBomWatch() {
  const folder = $("bomWatchFolder").value.trim();
  const interval = Number($("bomWatchInterval").value || 30);
  try {
    await api("/api/bom/watch", {
      method: "POST",
      body: JSON.stringify({ folder, interval }),
    });
    showToast("文件夹监控已启动");
    await refreshBomMeta();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function stopBomWatch() {
  try {
    await api("/api/bom/watch/stop", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showToast("文件夹监控已停止");
    await refreshBomMeta();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderImportResult(result) {
  const container = $("importPreview");
  const errorHtml = result.errors.length
    ? `<p>部分行导入失败：</p><ul>${result.errors.slice(0, 6).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";
  container.innerHTML = `
    <div class="import-result">
      <h3>导入结果</h3>
      <p>新增元件 ${numText(result.imported)}，更新已有元件 ${numText(result.updated)}，跳过 ${numText(result.skipped)}。</p>
      ${errorHtml}
    </div>`;
}

async function runImport() {
  if (!state.importFile) {
    showToast("请先选择 LCSC.xlsx 文件", "error");
    return;
  }
  const button = $("importRunBtn");
  button.disabled = true;
  button.querySelector("span").textContent = "正在导入...";
  try {
    const dataBase64 = await fileToBase64(state.importFile);
    const result = await api("/api/import/lcsc", {
      method: "POST",
      body: JSON.stringify({
        file_name: state.importFile.name,
        data_base64: dataBase64,
        category_id: $("importCategory").value || null,
        location_id: $("importLocation").value || null,
        update_existing: $("importUpdateExisting").checked,
        auto_fetch_images: $("importAutoImages").checked,
      }),
    });
    renderImportResult(result);
    await loadAll();
    showToast(
      `导入完成：新增 ${result.imported}，更新 ${result.updated}` +
        ($("importAutoImages").checked ? "，图片后台抓取中" : "")
    );
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "开始导入";
  }
}

function bindStaticEvents() {
  const systemThemeMedia = window.matchMedia("(prefers-color-scheme: dark)");
  systemThemeMedia.addEventListener("change", () => {
    if (themePreference === "auto") applyTheme("auto", false);
  });
  applyTheme(themePreference, false);

  document.querySelectorAll(".nav-link:not(.site-link), .bottom-link").forEach((button) => {
    button.addEventListener("click", () => switchPage(button.dataset.page, { animate: true }));
  });
  const appSidebar = document.querySelector(".app-sidebar");
  const menuBtn = $("menuBtn");
  if (menuBtn && appSidebar) {
    menuBtn.addEventListener("click", () => appSidebar.classList.toggle("open"));
  }
  document.querySelectorAll(".app-sidebar .nav-link").forEach((button) => {
    if (appSidebar) button.addEventListener("click", () => appSidebar.classList.remove("open"));
  });
  document.querySelectorAll(".nav-item[data-page]").forEach((item) => {
    if (item.getAttribute("data-page") === "inventory") item.classList.add("active");
  });
  $("drawerClose").addEventListener("click", closeDrawer);
  $("drawerBackdrop").addEventListener("click", closeDrawer);
  document.addEventListener("mouseover", (event) => {
    const img = event.target.closest(".part-thumb, .part-cell img");
    if (img && img.src) showImageZoom(img, event);
  });
  document.addEventListener("mousemove", (event) => {
    if (!$("imageZoom").hidden) positionImageZoom(event);
  });
  document.addEventListener("mouseout", (event) => {
    if (event.target.closest(".part-thumb, .part-cell img")) hideImageZoom();
  });
  window.addEventListener("scroll", updateBackTop, { passive: true });
  $("backTop").addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  document.querySelectorAll(".modal-close").forEach((button) => {
    button.addEventListener("click", () => {
      const modal = button.closest(".modal-overlay");
      if (modal) modal.hidden = true;
    });
  });
  document.querySelectorAll(".modal-overlay").forEach((overlay) => {
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) overlay.hidden = true;
    });
  });

  $("confirmOk").addEventListener("click", async () => {
    closeModal("confirmModal");
    if (state.confirmAction) {
      try {
        await state.confirmAction();
      } catch (error) {
        showToast(error.message, "error");
      }
      state.confirmAction = null;
    }
  });

  $("addPartBtn").addEventListener("click", () => openPartModal());
  $("addProjectBtn").addEventListener("click", () => openProjectModal());
  $("addWishlistBtn").addEventListener("click", () => openWishlistModal());

  document.querySelectorAll("[data-stock-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.stockAction === "in") openStockIn();
      else openStockOut();
    });
  });

  $("partsSearch").addEventListener("input", (event) => {
    state.partsSearch = event.target.value;
    renderParts();
    lucide.createIcons();
  });
  $("partsCategory").addEventListener("change", (event) => {
    state.partsCategory = event.target.value;
    renderParts();
    lucide.createIcons();
  });
  $("partsLocation").addEventListener("change", (event) => {
    state.partsLocation = event.target.value;
    renderParts();
    lucide.createIcons();
  });
  $("stockSearch").addEventListener("input", (event) => {
    state.stockSearch = event.target.value;
    renderStock();
    lucide.createIcons();
  });

  $("locationTree").addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-tree-toggle]");
    if (toggle) {
      const id = Number(toggle.dataset.treeToggle);
      if (state.expandedLocations.has(id)) state.expandedLocations.delete(id);
      else state.expandedLocations.add(id);
      renderStock();
      lucide.createIcons();
      return;
    }
    const node = event.target.closest("[data-location-id]");
    if (node) {
      state.locationFilter = node.dataset.locationId;
      renderStock();
      lucide.createIcons();
    }
  });
  $("categoryTree").addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-category-toggle]");
    if (toggle) {
      const id = Number(toggle.dataset.categoryToggle);
      if (state.expandedCategories.has(id)) state.expandedCategories.delete(id);
      else state.expandedCategories.add(id);
      renderStock();
      lucide.createIcons();
      return;
    }
    const node = event.target.closest("[data-category-id]");
    if (node) {
      state.stockCategory = node.dataset.categoryId;
      renderStock();
      lucide.createIcons();
    }
  });
  document.querySelector(".category-all").addEventListener("click", () => {
    state.stockCategory = "";
    renderStock();
    lucide.createIcons();
  });

  $("stockOutPart").addEventListener("change", () => updateStockOutBatches());
  $("stockOutPart").addEventListener("change", () => {
    $("stockOutPartId").value = $("stockOutPart").value || "";
    $("stockOutBatchId").value = "";
  });
  $("stockOutBatch").addEventListener("change", (event) => {
    $("stockOutBatchId").value = event.target.value || "";
  });
  document.querySelector(".location-all").addEventListener("click", () => {
    state.locationFilter = "";
    renderStock();
    lucide.createIcons();
  });

  $("partForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("partId").value;
    const payload = {
      part_number: $("partNumber").value.trim(),
      lcsc_code: $("partLcsc").value.trim(),
      brand: $("partBrand").value.trim(),
      category_id: $("partCategory").value ? Number($("partCategory").value) : null,
      package: $("partPackage").value.trim(),
      temperature_range: $("partTemp").value.trim(),
      voltage_rating: $("partVoltage").value.trim(),
      description: $("partDescription").value.trim(),
      datasheet_url: $("partDatasheet").value.trim(),
      min_stock: Number($("partMinStock").value || 0),
      notes: $("partNotes").value.trim(),
      stock_quantity: $("partStockQty").value.trim()
        ? Number($("partStockQty").value)
        : null,
      location_id: $("partStockLocation").value
        ? Number($("partStockLocation").value)
        : null,
      project_id: $("partProject").value ? Number($("partProject").value) : null,
    };
    try {
      let savedId = null;
      if (id) {
        await api(`/api/parts/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
        savedId = Number(id);
      } else {
        const created = await api("/api/parts", { method: "POST", body: JSON.stringify(payload) });
        savedId = created.id;
      }
      if (state.partImageRemoved) {
        await api(`/api/parts/${savedId}/image`, { method: "DELETE" });
      } else if (state.partImageFile) {
        const dataBase64 = await fileToBase64(state.partImageFile);
        await api(`/api/parts/${savedId}/image`, {
          method: "POST",
          body: JSON.stringify({
            file_name: state.partImageFile.name,
            data_base64: dataBase64,
          }),
        });
      }
      closeModal("modalPart");
      if (!$("drawer").hidden) closeDrawer();
      showToast("元件已保存");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("stockInForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      part_id: Number($("stockInPart").value),
      location_id: Number($("stockInLocation").value),
      quantity: Number($("stockInQty").value),
      purchase_date: $("stockInDate").value,
      unit_price: $("stockInPrice").value ? Number($("stockInPrice").value) : null,
      channel: $("stockInChannel").value.trim(),
      order_number: $("stockInOrder").value.trim(),
      notes: $("stockInNotes").value.trim(),
    };
    try {
      await api("/api/stock/inbound", { method: "POST", body: JSON.stringify(payload) });
      closeModal("modalStockIn");
      showToast("入库成功");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("stockOutForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      part_id: $("stockOutPartId").value ? Number($("stockOutPartId").value) : null,
      batch_id: $("stockOutBatchId").value ? Number($("stockOutBatchId").value) : null,
      quantity: Number($("stockOutQty").value),
      project_id: $("stockOutProject").value ? Number($("stockOutProject").value) : null,
      note: $("stockOutNote").value.trim(),
    };
    try {
      await api("/api/stock/outbound", { method: "POST", body: JSON.stringify(payload) });
      closeModal("modalStockOut");
      showToast("出库成功");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("movementForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("movementId").value;
    const payload = {
      note: $("movementNote").value.trim(),
      created_at: $("movementTime").value,
    };
    if (state.movementType !== "in") {
      payload.project_id = $("movementProject").value
        ? Number($("movementProject").value)
        : null;
    }
    try {
      await api(`/api/movements/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      closeModal("modalMovement");
      if (!$("drawer").hidden) closeDrawer();
      showToast("出入库记录已更新");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("projectForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("projectId").value;
    const payload = {
      name: $("projectName").value.trim(),
      status: $("projectStatus").value,
      description: $("projectDescription").value.trim(),
    };
    try {
      let result = null;
      if (id) {
        await api(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        if (state.projectBomFile) {
          payload.bom_file_name = state.projectBomFile.name;
          payload.bom_data_base64 = await fileToBase64(state.projectBomFile);
          payload.match_mode = "auto";
        }
        result = await api("/api/projects", { method: "POST", body: JSON.stringify(payload) });
      }
      closeModal("modalProject");
      await loadAll();
      if (result && result.bom_report) {
        showToast(`项目已保存，BOM 对比：缺料 ${result.bom_report.summary.shortage}，未匹配 ${result.bom_report.summary.unmatched}`);
        openProjectDrawer(result.id);
      } else {
        showToast("项目已保存");
      }
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  const projectBomDropzone = $("projectBomDropzone");
  const projectBomFileInput = $("projectBomFile");
  projectBomFileInput.addEventListener("change", () => {
    if (projectBomFileInput.files.length) {
      state.projectBomFile = projectBomFileInput.files[0];
      projectBomDropzone.querySelector("strong").textContent = state.projectBomFile.name;
    }
  });
  projectBomDropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    projectBomDropzone.classList.add("drag");
  });
  projectBomDropzone.addEventListener("dragleave", () => projectBomDropzone.classList.remove("drag"));
  projectBomDropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    projectBomDropzone.classList.remove("drag");
    if (event.dataTransfer.files.length) {
      state.projectBomFile = event.dataTransfer.files[0];
      projectBomFileInput.files = event.dataTransfer.files;
      projectBomDropzone.querySelector("strong").textContent = state.projectBomFile.name;
    }
  });

  const partImageDropzone = $("partImageDropzone");
  const partImageFileInput = $("partImageFile");
  const partImagePreviewWrap = $("partImagePreviewWrap");
  const partImagePreview = $("partImagePreview");
  partImageFileInput.addEventListener("change", () => {
    if (partImageFileInput.files.length) {
      state.partImageFile = partImageFileInput.files[0];
      state.partImageRemoved = false;
      partImagePreview.src = URL.createObjectURL(state.partImageFile);
      partImagePreviewWrap.hidden = false;
    }
  });
  partImageDropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    partImageDropzone.classList.add("drag");
  });
  partImageDropzone.addEventListener("dragleave", () => partImageDropzone.classList.remove("drag"));
  partImageDropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    partImageDropzone.classList.remove("drag");
    if (event.dataTransfer.files.length) {
      state.partImageFile = event.dataTransfer.files[0];
      state.partImageRemoved = false;
      partImageFileInput.files = event.dataTransfer.files;
      partImagePreview.src = URL.createObjectURL(state.partImageFile);
      partImagePreviewWrap.hidden = false;
    }
  });
  $("partImageRemove").addEventListener("click", () => {
    state.partImageFile = null;
    state.partImageRemoved = true;
    partImageFileInput.value = "";
    partImagePreview.src = "";
    partImagePreviewWrap.hidden = true;
  });

  $("wishlistForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("wishlistId").value;
    const editingItem = id ? state.wishlist.find((item) => String(item.id) === String(id)) : null;
    const payload = {
      part_id: $("wishlistPart").value ? Number($("wishlistPart").value) : null,
      lcsc_code: $("wishlistLcsc").value.trim(),
      part_number: $("wishlistPartNumber").value.trim(),
      brand: $("wishlistBrand").value.trim(),
      package: $("wishlistPackage").value.trim(),
      description: $("wishlistDescription").value.trim(),
      target_quantity: Number($("wishlistQty").value),
      unit_price: $("wishlistPrice").value ? Number($("wishlistPrice").value) : null,
      priority: $("wishlistPriority").value,
      notes: $("wishlistNotes").value.trim(),
      status: editingItem ? editingItem.status : "open",
    };
    try {
      if (id) await api(`/api/wishlist/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await api("/api/wishlist", { method: "POST", body: JSON.stringify(payload) });
      closeModal("modalWishlist");
      showToast("待购条目已保存");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("convertForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("convertId").value;
    const payload = {
      quantity: Number($("convertQty").value),
      location_id: Number($("convertLocation").value),
      category_id: $("convertCategory").value ? Number($("convertCategory").value) : null,
      purchase_date: $("convertDate").value,
      unit_price: $("convertPrice").value ? Number($("convertPrice").value) : null,
      channel: $("convertChannel").value.trim(),
      order_number: $("convertOrder").value.trim(),
      notes: $("convertNotes").value.trim(),
    };
    try {
      await api(`/api/wishlist/${id}/convert`, { method: "POST", body: JSON.stringify(payload) });
      closeModal("modalConvert");
      showToast("已转为采购入库");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("categoryForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("categoryId").value;
    const payload = {
      name: $("categoryName").value.trim(),
      parent_id: $("categoryParentId").value ? Number($("categoryParentId").value) : null,
    };
    try {
      if (id) await api(`/api/categories/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await api("/api/categories", { method: "POST", body: JSON.stringify(payload) });
      closeModal("modalCategory");
      showToast("分类已保存");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  $("locationForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("locationId").value;
    const payload = {
      code: $("locationCode").value.trim(),
      name: $("locationName").value.trim(),
      parent_id: $("locationParentId").value ? Number($("locationParentId").value) : null,
    };
    try {
      if (id) await api(`/api/locations/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await api("/api/locations", { method: "POST", body: JSON.stringify(payload) });
      closeModal("modalLocation");
      showToast("位置已保存");
      await loadAll();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  const dropzone = $("dropzone");
  const fileInput = $("importFile");
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) {
      state.importFile = fileInput.files[0];
      dropzone.querySelector("strong").textContent = state.importFile.name;
      $("importPreview").innerHTML = "";
    }
  });
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("drag");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag");
    if (event.dataTransfer.files.length) {
      state.importFile = event.dataTransfer.files[0];
      fileInput.files = event.dataTransfer.files;
      dropzone.querySelector("strong").textContent = state.importFile.name;
      $("importPreview").innerHTML = "";
    }
  });
  $("importRunBtn").addEventListener("click", runImport);

  const bomDropzone = $("bomDropzone");
  const bomFileInput = $("bomFile");
  bomFileInput.addEventListener("change", () => {
    if (bomFileInput.files.length) {
      state.bomFile = bomFileInput.files[0];
      bomDropzone.querySelector("strong").textContent = state.bomFile.name;
      $("bomResult").innerHTML = "";
    }
  });
  bomDropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    bomDropzone.classList.add("drag");
  });
  bomDropzone.addEventListener("dragleave", () => bomDropzone.classList.remove("drag"));
  bomDropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    bomDropzone.classList.remove("drag");
    if (event.dataTransfer.files.length) {
      state.bomFile = event.dataTransfer.files[0];
      bomFileInput.files = event.dataTransfer.files;
      bomDropzone.querySelector("strong").textContent = state.bomFile.name;
      $("bomResult").innerHTML = "";
    }
  });
  $("bomRunBtn").addEventListener("click", runBomCompare);
  $("bomWatchStart").addEventListener("click", startBomWatch);
  $("bomWatchStop").addEventListener("click", stopBomWatch);

  document.querySelectorAll(".manage-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.manageTab = tab.dataset.manage;
      renderManage();
      lucide.createIcons();
    });
  });

  document.addEventListener("click", async (event) => {
    const actionButton = event.target.closest("[data-action]");
    if (!actionButton) return;
    const action = actionButton.dataset.action;
    const id = actionButton.dataset.id;
    const partId = actionButton.dataset.part;
    const parentId = actionButton.dataset.parent;

    if (action === "part-detail") await openPartDrawer(id);
    if (action === "part-edit") {
      const part = state.parts.find((item) => String(item.id) === String(id));
      openPartModal(part);
    }
    if (action === "part-delete") {
      confirmDialog("删除该元件会同时删除库存和出入库记录，确认继续吗？", async () => {
        await api(`/api/parts/${id}`, { method: "DELETE" });
        closeDrawer();
        showToast("元件已删除");
        await loadAll();
      });
    }
    if (action === "part-in") openStockIn(id);
    if (action === "part-out") openStockOut(id);
    if (action === "batch-out") openStockOut(partId, id);
    if (action === "movement-edit") {
      const item = state.movementItems.find((entry) => String(entry.id) === String(id));
      if (item) openMovementModal(item);
    }
    if (action === "movement-delete") {
      confirmDialog("删除这条出入库记录会同步恢复或扣回库存，确认继续吗？", async () => {
        await api(`/api/movements/${id}`, { method: "DELETE" });
        closeDrawer();
        showToast("出入库记录已删除");
        await loadAll();
      });
    }
    if (action === "project-add") openProjectModal();
    if (action === "project-edit") {
      const project = state.projects.find((item) => String(item.id) === String(id));
      openProjectModal(project);
    }
    if (action === "project-delete") {
      confirmDialog("删除项目后，相关出库记录会保留但不关联项目。确认继续吗？", async () => {
        await api(`/api/projects/${id}`, { method: "DELETE" });
        closeDrawer();
        showToast("项目已删除");
        await loadAll();
      });
    }
    if (action === "project-detail") await openProjectDrawer(id);
    if (action === "wishlist-edit") {
      const item = state.wishlist.find((entry) => String(entry.id) === String(id));
      openWishlistModal(item);
    }
    if (action === "wishlist-delete") {
      confirmDialog("确认删除这条待购记录吗？", async () => {
        await api(`/api/wishlist/${id}`, { method: "DELETE" });
        showToast("待购条目已删除");
        await loadAll();
      });
    }
    if (action === "wishlist-convert") {
      const item = state.wishlist.find((entry) => String(entry.id) === String(id));
      openConvertModal(item);
    }
    if (action === "bom-view") {
      try {
        const saved = await api(`/api/bom/reports/${encodeURIComponent(id)}`);
        closeDrawer();
        switchPage("bom", { animate: true });
        renderBomResult(saved);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (error) {
        showToast(error.message, "error");
      }
    }
    if (action === "category-add") openCategoryModal(parentId || null);
    if (action === "category-edit") {
      const item = state.categories.find((entry) => String(entry.id) === String(id));
      openCategoryModal(null, item);
    }
    if (action === "category-delete") {
      confirmDialog("删除分类后，其子分类会提升为根分类，元件会变为未分类。确认继续吗？", async () => {
        await api(`/api/categories/${id}`, { method: "DELETE" });
        showToast("分类已删除");
        await loadAll();
      });
    }
    if (action === "location-add") openLocationModal(parentId || null);
    if (action === "location-edit") {
      const item = state.locations.find((entry) => String(entry.id) === String(id));
      openLocationModal(null, item);
    }
    if (action === "location-delete") {
      confirmDialog("只有没有子位置和库存的位置才能删除。确认继续吗？", async () => {
        await api(`/api/locations/${id}`, { method: "DELETE" });
        showToast("位置已删除");
        await loadAll();
      });
    }
    lucide.createIcons();
  });
}

async function init() {
  bindStaticEvents();
  bindPageHeadAutoHide();
  try {
    await loadAll();
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    const savedPage = localStorage.getItem("inventoryPage");
    // 首屏要显示哪一页在 index.html 里的引导脚本已经算好并放出来了，这里沿用同一个结果，
    // 不再重新决定，也不写回 localStorage（避免把“上次停留页”覆盖成仪表盘）。
    switchPage(
      window.__inventoryBootPage ||
        (savedPage && document.getElementById(`page-${savedPage}`) ? savedPage : "dashboard"),
      { animate: false, persist: false }
    );
  } catch (error) {
    showToast(error.message || "无法连接服务", "error");
  }
}

document.addEventListener("DOMContentLoaded", init);
