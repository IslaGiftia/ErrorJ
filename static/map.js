(function () {
  "use strict";

  var mapEl = document.getElementById("map");
  if (!mapEl || typeof L === "undefined") return;

  function $(id) {
    return document.getElementById(id);
  }

  var mapPhotoLimit = { max_count: 9, max_file_bytes: 8 * 1024 * 1024 };

  function mapPhotoLabel() {
    return window.ErrorUploadLimits
      ? window.ErrorUploadLimits.label(mapPhotoLimit.max_file_bytes)
      : "8MB";
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var limits = window.ErrorUploadLimits.get("map_photo");
    mapPhotoLimit.max_count = Number(limits.max_count) || mapPhotoLimit.max_count;
    mapPhotoLimit.max_file_bytes =
      Number(limits.max_file_bytes) || mapPhotoLimit.max_file_bytes;
    var hint = $("placePhotoHint");
    if (hint) {
      hint.textContent =
        "最多 " + mapPhotoLimit.max_count + " 张，单张不超过 " +
        mapPhotoLabel() + "，保存后上传。";
    }
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function lum(hex) {
    var n = parseInt(String(hex || "#7b68ee").replace("#", ""), 16);
    if (isNaN(n)) return 1;
    var rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  }

  // ---------- WGS84 / GCJ02 / BD09 ----------
  var Geo = (function () {
    var PI = Math.PI;
    var A = 6378245.0;
    var EE = 0.00669342162296594323;
    var X_PI = (PI * 3000.0) / 180.0;

    function outOfChina(lat, lng) {
      return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271;
    }

    function transformLat(x, y) {
      var ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
      ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0;
      ret += ((20.0 * Math.sin(y * PI) + 40.0 * Math.sin((y / 3.0) * PI)) * 2.0) / 3.0;
      ret += ((160.0 * Math.sin((y / 12.0) * PI) + 320 * Math.sin((y * PI) / 30.0)) * 2.0) / 3.0;
      return ret;
    }

    function transformLng(x, y) {
      var ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
      ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0;
      ret += ((20.0 * Math.sin(x * PI) + 40.0 * Math.sin((x / 3.0) * PI)) * 2.0) / 3.0;
      ret += ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x / 30.0) * PI)) * 2.0) / 3.0;
      return ret;
    }

    function wgs84ToGcj02(lat, lng) {
      if (outOfChina(lat, lng)) return [lat, lng];
      var dLat = transformLat(lng - 105.0, lat - 35.0);
      var dLng = transformLng(lng - 105.0, lat - 35.0);
      var radLat = (lat / 180.0) * PI;
      var magic = Math.sin(radLat);
      magic = 1 - EE * magic * magic;
      var sqrtMagic = Math.sqrt(magic);
      dLat = (dLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * PI);
      dLng = (dLng * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * PI);
      return [lat + dLat, lng + dLng];
    }

    function gcj02ToWgs84(lat, lng) {
      if (outOfChina(lat, lng)) return [lat, lng];
      var wLat = lat;
      var wLng = lng;
      for (var i = 0; i < 3; i++) {
        var converted = wgs84ToGcj02(wLat, wLng);
        wLat += lat - converted[0];
        wLng += lng - converted[1];
      }
      return [wLat, wLng];
    }

    function gcj02ToBd09(lat, lng) {
      var z = Math.sqrt(lng * lng + lat * lat) + 0.00002 * Math.sin(lat * X_PI);
      var theta = Math.atan2(lat, lng) + 0.000003 * Math.cos(lng * X_PI);
      return [z * Math.sin(theta) + 0.006, z * Math.cos(theta) + 0.0065];
    }

    function bd09ToGcj02(lat, lng) {
      var x = lng - 0.0065;
      var y = lat - 0.006;
      var z = Math.sqrt(x * x + y * y) - 0.00002 * Math.sin(y * X_PI);
      var theta = Math.atan2(y, x) - 0.000003 * Math.cos(x * X_PI);
      return [z * Math.sin(theta), z * Math.cos(theta)];
    }

    return {
      toGcj: wgs84ToGcj02,
      fromGcj: gcj02ToWgs84,
      gcjToBd: gcj02ToBd09,
      bdToWgs: function (lat, lng) {
        var gcj = bd09ToGcj02(lat, lng);
        return gcj02ToWgs84(gcj[0], gcj[1]);
      }
    };
  })();

  // ---------- state ----------
  var state = {
    categories: [],
    places: [],
    canManage: false,
    canAdd: false,
    canFilterOwner: false,
    myUserId: "",
    signedIn: false,
    categoryFilter: null,
    // 分类树里哪些节点是展开的（默认全折叠，只露一级分类）
    expandedKeys: new Set(),
    expandedTops: new Set(),
    keyword: "",
    ownerFilter: "",
    markers: {},
    gcj: false,
    placing: false,
    editingId: null,
    activeId: null,
    status: "",
    rating: 0,
    photoFiles: [],
    photoUrls: [],
    searchOpen: false,
    searchBusy: false,
    searchResults: [],
    searchPick: null
  };

  var VIEW_KEY = "errorMapView";

  function loadSavedView() {
    try {
      var raw = localStorage.getItem(VIEW_KEY);
      if (!raw) return null;
      var view = JSON.parse(raw);
      if (typeof view.lat === "number" && typeof view.lng === "number") {
        return { lat: view.lat, lng: view.lng, zoom: Number(view.zoom) || 12 };
      }
    } catch (err) {}
    return null;
  }

  function saveView() {
    var center = dataLatLng(map.getCenter().lat, map.getCenter().lng);
    try {
      localStorage.setItem(
        VIEW_KEY,
        JSON.stringify({ lat: center[0], lng: center[1], zoom: map.getZoom() })
      );
    } catch (err) {}
  }

  function displayLatLng(lat, lng) {
    return state.gcj ? Geo.toGcj(lat, lng) : [lat, lng];
  }

  function dataLatLng(lat, lng) {
    return state.gcj ? Geo.fromGcj(lat, lng) : [lat, lng];
  }

  // ---------- tile layers ----------
  var OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';

  function amapUrl(style, subdomains) {
    return (
      "https://web" +
      (style === 6 ? "st" : "rd") +
      "0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=" +
      style +
      "&x={x}&y={y}&z={z}"
    );
  }

  var BASE_LAYERS = {
    amap: {
      name: "高德矢量",
      tag: "浅色",
      dot: "#f0e2c3",
      gcj: true,
      zoomCap: 18,
      layer: L.tileLayer(amapUrl(8), {
        subdomains: "1234",
        minZoom: 3,
        maxZoom: 19,
        maxNativeZoom: 18,
        attribution: "&copy; 高德地图"
      })
    },
    amapSat: {
      name: "高德卫星",
      tag: "卫星",
      dot: "#4f7a52",
      gcj: true,
      zoomCap: 18,
      layer: L.tileLayer(amapUrl(6), {
        subdomains: "1234",
        minZoom: 3,
        maxZoom: 19,
        maxNativeZoom: 18,
        attribution: "&copy; 高德地图"
      })
    },
    osm: {
      name: "OSM 标准",
      tag: "浅色",
      dot: "#cfe3c8",
      gcj: false,
      zoomCap: 19,
      layer: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: OSM_ATTR
      })
    },
    esriDark: {
      name: "Esri 深色",
      tag: "深色",
      dot: "#3d4147",
      gcj: false,
      zoomCap: 16,
      layer: L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 16, attribution: "&copy; Esri" }
      )
    },
    esriSat: {
      name: "Esri 卫星",
      tag: "卫星",
      dot: "#3f5f3f",
      gcj: false,
      zoomCap: 18,
      layer: L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 18, attribution: "&copy; Esri" }
      )
    }
  };

  var savedView = loadSavedView();
  function isDarkTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  var BASE_STORAGE_PREFIX = "errorMapBase:";
  function themeKey() {
    return isDarkTheme() ? "dark" : "light";
  }
  function savedBaseForTheme() {
    try {
      var id = localStorage.getItem(BASE_STORAGE_PREFIX + themeKey());
      if (id && BASE_LAYERS[id]) return id;
    } catch (err) {}
    return isDarkTheme() ? "esriDark" : "amap";
  }

  var map = L.map(mapEl, {
    zoomControl: false,
    minZoom: 3,
    maxZoom: 19,
    worldCopyJump: true,
    preferCanvas: true
  });
  var activeBaseId = savedBaseForTheme();
  state.gcj = BASE_LAYERS[activeBaseId].gcj;
  var initialCenter = savedView
    ? displayLatLng(savedView.lat, savedView.lng)
    : displayLatLng(34.3416, 108.9398);
  map.setView(initialCenter, savedView ? savedView.zoom : 12);

  BASE_LAYERS[activeBaseId].layer.addTo(map);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.control.scale({ position: "bottomright", imperial: false }).addTo(map);

  var darkRefLayer = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 16, attribution: "&copy; Esri" }
  );

  var BASE_ORDER = ["amap", "amapSat", "esriDark", "esriSat", "osm"];
  var basePanel = $("mapBasePanel");
  var baseBtn = $("mapBaseBtn");

  function renderBasePanel() {
    if (!basePanel) return;
    basePanel.innerHTML = BASE_ORDER.filter(function (id) {
      return Boolean(BASE_LAYERS[id]);
    })
      .map(function (id) {
        var base = BASE_LAYERS[id];
        return (
          '<button type="button" role="menuitem" class="mp-base-item' +
          (id === activeBaseId ? " is-on" : "") +
          '" data-base="' +
          id +
          '"><span class="mp-base-dot" style="--dot:' +
          base.dot +
          '"></span><span class="mp-base-name">' +
          esc(base.name) +
          '</span><span class="mp-base-tag">' +
          esc(base.tag) +
          "</span></button>"
        );
      })
      .join("");
  }

  function openBasePanel(open) {
    if (!basePanel) return;
    basePanel.hidden = !open;
    if (baseBtn) baseBtn.classList.toggle("is-on", Boolean(open));
  }

  function applyBaseLayer(id, options) {
    if (!BASE_LAYERS[id]) return;
    var opts = options || {};
    if (id !== activeBaseId) {
      map.removeLayer(BASE_LAYERS[activeBaseId].layer);
      activeBaseId = id;
      map.addLayer(BASE_LAYERS[id].layer);
    }
    state.gcj = BASE_LAYERS[id].gcj;
    var cap = BASE_LAYERS[id].zoomCap || 19;
    map.setMaxZoom(cap);
    if (map.getZoom() > cap) map.setZoom(cap);
    if (id === "esriDark") {
      if (!map.hasLayer(darkRefLayer)) darkRefLayer.addTo(map);
    } else if (map.hasLayer(darkRefLayer)) {
      map.removeLayer(darkRefLayer);
    }
    mapEl.classList.toggle("is-darkmap", id === "esriDark");
    if (opts.remember) {
      try {
        localStorage.setItem(BASE_STORAGE_PREFIX + themeKey(), id);
      } catch (err) {}
    }
    renderBasePanel();
    renderMarkers();
  }

  if (window.MutationObserver) {
    new MutationObserver(function () {
      applyBaseLayer(savedBaseForTheme(), { remember: false });
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  if (baseBtn) {
    baseBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      openBasePanel(basePanel ? basePanel.hidden : false);
    });
  }
  if (basePanel) {
    basePanel.addEventListener("click", function (event) {
      var item = event.target.closest("[data-base]");
      if (!item) return;
      applyBaseLayer(item.getAttribute("data-base"), { remember: true });
      openBasePanel(false);
    });
  }
  document.addEventListener("click", function (event) {
    if (!basePanel || basePanel.hidden) return;
    if (event.target.closest("#mapBasePanel") || event.target.closest("#mapBaseBtn")) return;
    openBasePanel(false);
  });
  applyBaseLayer(activeBaseId, { remember: false });

  var cluster = L.markerClusterGroup({
    showCoverageOnHover: false,
    spiderfyOnMaxZoom: true,
    disableClusteringAtZoom: 17,
    maxClusterRadius: 46,
    iconCreateFunction: function (group) {
      var count = group.getChildCount();
      var size = count >= 100 ? 48 : count >= 20 ? 42 : 36;
      return L.divIcon({
        className: "mp-cluster",
        html: '<span class="mp-cluster-inner">' + count + "</span>",
        iconSize: L.point(size, size)
      });
    }
  });
  map.addLayer(cluster);

  map.on("moveend zoomend", saveView);

  // ---------- api ----------
  function api(path, options) {
    var opts = options || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    return fetch(path, opts).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!response.ok) throw new Error(data.error || "请求失败（" + response.status + "）");
          return data;
        });
    });
  }

  var toastEl = $("mapToast");
  var toastTimer = null;
  // 桌面端操作卡片里没权限的按钮统一给这一句，措辞保持一致
  var NO_PERMISSION_TIP = "请向管理员申请权限";

  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.hidden = true;
    }, 2600);
  }

  function notifyDockRefresh() {
    try {
      localStorage.setItem("errorMapDockRefresh", String(Date.now()));
    } catch (err) {}
  }

  function categoryById(id) {
    for (var i = 0; i < state.categories.length; i++) {
      if (state.categories[i].id === id) return state.categories[i];
    }
    return null;
  }

  function topCategories() {
    return state.categories.filter(function (cat) {
      return !cat.parent_id;
    });
  }

  function childCategories(parentId) {
    return state.categories.filter(function (cat) {
      return cat.parent_id === parentId;
    });
  }

  function categoryPath(cat) {
    if (!cat) return "";
    if (cat.parent_id) {
      var parent = categoryById(cat.parent_id);
      return (parent ? parent.name + " / " : "") + cat.name;
    }
    return cat.name;
  }

  function placeById(id) {
    for (var i = 0; i < state.places.length; i++) {
      if (state.places[i].id === id) return state.places[i];
    }
    return null;
  }

  function placeColor(place) {
    var cat = categoryById(place.category_id);
    return cat && cat.color ? cat.color : "#7b68ee";
  }

  function placeGlyph(place) {
    var cat = categoryById(place.category_id);
    return cat && cat.glyph ? cat.glyph : "·";
  }

  // ---------- rendering ----------
  function visiblePlaces() {
    var keyword = state.keyword.trim().toLowerCase();
    var categoryScope = state.categoryFilter
      ? categorySubtreeIds(state.categoryFilter)
      : null;
    return state.places.filter(function (place) {
      if (state.ownerFilter !== "" && String(place.created_by) !== state.ownerFilter) {
        return false;
      }
      if (categoryScope) {
        // 选中某一级分类 = 这一级 + 它的所有下级
        if (categoryScope.indexOf(place.category_id) < 0) return false;
      }
      if (!keyword) return true;
      var haystack = [
        place.name,
        place.subtitle,
        place.address,
        place.note,
        place.signature,
        place.tags,
        place.category_name
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.indexOf(keyword) >= 0;
    });
  }

  function renderList() {
    var box = $("mapList");
    var countEl = $("mapCount");
    if (!box) return;
    var places = visiblePlaces();
    if (countEl) {
      countEl.textContent =
        state.places.length + " 个标记 · " + state.categories.length + " 个分类";
    }
    if (!places.length) {
      box.innerHTML = '<p class="mp-empty">没有符合条件的标记。</p>';
      return;
    }
    var html = "";
    places.slice(0, 400).forEach(function (place) {
      var desc = place.address || place.note || place.subtitle || "";
      html +=
        '<button type="button" class="mp-item' +
        (state.activeId === place.id ? " is-active" : "") +
        '" data-place="' +
        place.id +
        '">' +
        '<span class="mp-item-dot" style="--dot-color:' +
        esc(placeColor(place)) +
        '">' +
        esc(placeGlyph(place)) +
        "</span>" +
        '<span class="mp-item-body">' +
        '<span class="mp-item-title"><span>' +
        esc(place.name) +
        "</span>" +
        (place.subtitle ? '<span class="mp-item-sub">' + esc(place.subtitle) + "</span>" : "") +
        "</span>" +
        '<span class="mp-item-desc">' +
        esc(desc) +
        "</span></span></button>";
    });
    box.innerHTML = html;
  }

  var ownerGroups = [];

  function ownerLabel(key) {
    // 普通账户不能挑别人，按钮就两态：全部 / 只看自己添加的
    if (!state.canFilterOwner) return key ? "只看我添加的" : "全部标记";
    if (!key) return "全部添加者";
    var hit = null;
    ownerGroups.forEach(function (item) {
      if (String(item.key) === String(key)) hit = item;
    });
    return hit ? hit.name + "（" + hit.count + "）" : "全部添加者";
  }

  function syncOwnerLabel() {
    var label = ownerLabel(state.ownerFilter);
    var button = $("mapOwnerBtn");
    if (!button) return;
    // 悬停提示只写按钮名；当前筛的是谁走 aria-label，另外有筛选生效时按钮会点亮
    button.setAttribute("data-tip", "添加者");
    // 图标按钮没有可见文字，读屏要靠 aria-label；把当前状态也带进去
    button.setAttribute("aria-label", "添加者筛选：" + label);
    button.classList.toggle("is-active", Boolean(state.ownerFilter));
  }

  // 添加者浮层：PC 与手机都锚在操作卡片正上方，不进全屏弹窗
  function setOwnerPopOpen(open) {
    var pop = $("mapOwnerPop");
    if (pop) pop.hidden = !open;
    var button = $("mapOwnerBtn");
    if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) applyPopHeight(pop);
  }

  function closeOwnerPicker() {
    setOwnerPopOpen(false);
  }

  /* ---------- 分类筛选浮层（和添加者同一套外壳，内部是多级分类树） ---------- */

  // 某一级分类 + 它的所有下级（最多再往下两级，够覆盖「一级 > 二级 > 三级」）
  function categorySubtreeIds(rootId) {
    var ids = [rootId];
    var frontier = [rootId];
    var guard = 0;
    while (frontier.length && guard < 4) {
      var next = [];
      state.categories.forEach(function (cat) {
        if (frontier.indexOf(cat.parent_id) >= 0) {
          ids.push(cat.id);
          next.push(cat.id);
        }
      });
      frontier = next;
      guard += 1;
    }
    return ids;
  }

  function categoryLabel(cat) {
    if (!cat) return "全部分类";
    var names = [cat.name];
    var node = cat;
    var guard = 0;
    while (node && node.parent_id && guard < 2) {
      node = categoryById(node.parent_id);
      if (!node) break;
      names.unshift(node.name);
      guard += 1;
    }
    return names.join(" / ");
  }

  /*
   * 分类树：默认只露一级，含下级的节点点一下展开 / 折叠（本身不参与筛选），
   * 叶子节点点一下才过滤。展开状态记在 state.expandedKeys 里，
   * 所以折叠 / 展开只动这一棵子树（隐藏 children 容器），不重建整棵树。
   */
  function categoryTreeHtml(list, depth, counts) {
    var html = "";
    list.forEach(function (cat) {
      var kids = childCategories(cat.id);
      var count = 0;
      categorySubtreeIds(cat.id).forEach(function (id) {
        count += counts[id] || 0;
      });
      var expanded = state.expandedKeys.has(cat.id);
      html +=
        '<div class="mp-cat-node" style="--cat-depth:' + depth + '">' +
        '<button type="button" class="mp-owner-option mp-cat-option' +
        (state.categoryFilter === cat.id ? " is-active" : "") +
        (kids.length ? " is-parent" : "") +
        '" data-cat="' +
        cat.id +
        '"' +
        (kids.length
          ? ' data-cat-parent="' + cat.id + '" aria-expanded="' + (expanded ? "true" : "false") + '"'
          : "") +
        ">" +
        '<i class="mp-cat-dot" style="--cat-color:' +
        esc(cat.color) +
        '">' +
        esc(cat.glyph || "·") +
        "</i><span>" +
        esc(cat.name) +
        "</span><em>" +
        count +
        " 个标记</em>" +
        (kids.length ? '<i class="mp-cat-caret" aria-hidden="true"></i>' : "") +
        "</button>";
      if (kids.length) {
        html +=
          '<div class="mp-cat-kids" data-kids="' +
          cat.id +
          '"' +
          (expanded ? "" : " hidden") +
          ">" +
          categoryTreeHtml(kids, depth + 1, counts) +
          "</div>";
      }
      html += "</div>";
    });
    return html;
  }

  function syncCatLabel() {
    var button = $("mapCatBtn");
    if (!button) return;
    var cat = state.categoryFilter ? categoryById(state.categoryFilter) : null;
    // 与「添加者」一致：悬停提示只写按钮名，当前筛的是哪一级走 aria-label，有色时按钮点亮
    button.setAttribute("data-tip", "分类");
    button.setAttribute("aria-label", "分类筛选：" + categoryLabel(cat));
    button.classList.toggle("is-active", Boolean(state.categoryFilter));
  }

  function setCatPopOpen(open) {
    var pop = $("mapCatPop");
    if (pop) pop.hidden = !open;
    var button = $("mapCatBtn");
    if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) applyPopHeight(pop);
  }

  function closeCatPicker() {
    setCatPopOpen(false);
  }

  /*
   * 浮层高度上限 = 上方检索卡片的高度（够不到就按内容自适应，靠下对齐由 CSS 的 bottom 负责），
   * 再额外压一条：别长到盖住右上角的工具列——盖过去的话，用户点「搜索 / 定位」实际会点到分类行上。
   * 卡片本身有多高随视口变，所以在打开时和窗口尺寸变化时各算一次。
   */
  function applyPopHeight(pop) {
    var node = pop || $("mapCatPop");
    var sidebar = $("mapSidebar");
    if (!node || !sidebar) return;
    var limit = Math.round(sidebar.getBoundingClientRect().height);
    var tools = document.querySelector(".mp-tools");
    var actions = $("mapActions");
    if (tools && actions) {
      var room =
        actions.getBoundingClientRect().top -
        8 -
        tools.getBoundingClientRect().bottom -
        12;
      if (room > 0) limit = Math.min(limit, Math.round(room));
    }
    node.style.maxHeight = Math.max(160, limit) + "px";
  }

  function renderCatFilter() {
    var box = $("mapCatPopList");
    if (!box) return;
    if (state.categoryFilter && !categoryById(state.categoryFilter)) {
      state.categoryFilter = null;
    }
    // 选中的若是下级分类，把它上面的层级一并展开，重新打开时能看到自己选的是哪一条
    var node = state.categoryFilter ? categoryById(state.categoryFilter) : null;
    var guard = 0;
    while (node && node.parent_id && guard < 3) {
      state.expandedKeys.add(node.parent_id);
      node = categoryById(node.parent_id);
      guard += 1;
    }
    var counts = {};
    state.places.forEach(function (place) {
      if (place.category_id) {
        counts[place.category_id] = (counts[place.category_id] || 0) + 1;
      }
    });
    var html =
      '<button type="button" class="mp-owner-option mp-cat-option' +
      (state.categoryFilter ? "" : " is-active") +
      '" data-cat="" style="--cat-depth:0">' +
      '<i class="mp-cat-dot is-all">·</i><span>全部分类</span><em>' +
      state.places.length +
      " 个标记</em></button>";
    html += categoryTreeHtml(topCategories(), 0, counts);
    box.innerHTML = html;
    applyPopHeight($("mapCatPop"));
    syncCatLabel();
  }

  function ownerOptionsHtml() {
    var current = String(state.ownerFilter || "");
    var html =
      '<button type="button" class="mp-owner-option' +
      (current ? "" : " is-active") +
      '" data-owner=""><span>全部添加者</span><em>' +
      state.places.length +
      " 个标记</em></button>";
    ownerGroups.forEach(function (item) {
      html +=
        '<button type="button" class="mp-owner-option' +
        (current === String(item.key) ? " is-active" : "") +
        '" data-owner="' +
        esc(item.key) +
        '"><span>' +
        esc(item.name) +
        "</span><em>" +
        item.count +
        " 个标记</em></button>";
    });
    return html;
  }

  function renderOwnerFilter() {
    var popList = $("mapOwnerPopList");
    if (!popList) return;
    var groups = {};
    state.places.forEach(function (place) {
      var key = String(place.created_by == null ? "" : place.created_by);
      if (!key) return;
      if (!groups[key]) {
        groups[key] = {
          key: key,
          name: place.created_by_name || "未知用户",
          count: 0
        };
      }
      groups[key].count += 1;
    });
    ownerGroups = Object.keys(groups)
      .map(function (key) {
        return groups[key];
      })
      .sort(function (a, b) {
        return String(a.name).localeCompare(String(b.name), "zh-CN");
      });
    if (state.ownerFilter && !groups[state.ownerFilter]) {
      state.ownerFilter = "";
    }
    syncOwnerLabel();
    var html = ownerOptionsHtml();
    popList.innerHTML = html;
  }

  function popupHtml(place) {
    var cat = categoryById(place.category_id);
    var color = placeColor(place);
    var gcj = Geo.toGcj(place.lat, place.lng);
    var tags = String(place.tags || "")
      .split(",")
      .map(function (tag) {
        return tag.trim();
      })
      .filter(Boolean);
    var html = '<div class="mp-popup">';
    html +=
      '<div class="mp-popup-head"><span class="mp-popup-badge" style="--popup-color:' +
      esc(color) +
      '">' +
      esc(cat ? cat.glyph || "·" : "·") +
      "</span><span><span class=\"mp-popup-title\">" +
      esc(place.name) +
      "</span>" +
      (place.subtitle ? '<div class="mp-popup-sub">' + esc(place.subtitle) + "</div>" : "") +
      "</span></div>";
    var flags = "";
    if (place.status === "wish" || place.status === "visited") {
      flags +=
        '<span class="mp-status is-' +
        place.status +
        '">' +
        (place.status === "wish" ? "想去" : "去过") +
        "</span>";
    }
    var rating = Number(place.rating) || 0;
    if (rating > 0) {
      var stars = "";
      for (var s = 1; s <= 5; s++) {
        stars += "<span" + (s <= rating ? "" : ' class="off"') + ">★</span>";
      }
      flags += '<span class="mp-popup-stars" title="推荐度 ' + rating + ' / 5">' + stars + "</span>";
    }
    if (flags) html += '<div class="mp-popup-flags">' + flags + "</div>";
    if (cat) html += '<p class="mp-popup-meta">分类：' + esc(categoryPath(cat)) + "</p>";
    if (place.address) html += '<p class="mp-popup-meta">地址：' + esc(place.address) + "</p>";
    if (place.signature) html += '<p class="mp-popup-sign">招牌：' + esc(place.signature) + "</p>";
    if (place.note) html += '<div class="mp-popup-note">' + esc(place.note) + "</div>";
    if (tags.length) {
      html +=
        '<div class="mp-popup-tags">' +
        tags
          .map(function (tag) {
            return "<span>" + esc(tag) + "</span>";
          })
          .join("") +
        "</div>";
    }
    var photos = place.photos || [];
    if (photos.length) {
      html += '<div class="mp-popup-photos">';
      photos.slice(0, 4).forEach(function (photo) {
        html +=
          '<a href="' +
          esc(photo.url) +
          '" target="_blank" rel="noopener" title="' +
          esc(photo.original_name || "照片") +
          '"><img src="' +
          esc(photo.url) +
          '" alt="" loading="lazy"></a>';
      });
      if (photos.length > 4) {
        html +=
          '<a class="mp-photo-more" href="' +
          esc(photos[4].url) +
          '" target="_blank" rel="noopener">+' +
          (photos.length - 4) +
          "</a>";
      }
      html += "</div>";
    }
    // 只保留高德导航
    var nav =
      '<a class="mp-link-btn mp-edit-btn" target="_blank" rel="noopener" href="https://uri.amap.com/marker?position=' +
      gcj[1].toFixed(6) +
      "," +
      gcj[0].toFixed(6) +
      "&name=" +
      encodeURIComponent(place.name) +
      '">导航</a>';
    html += '<div class="mp-popup-foot">';
    if (place.created_by_name) {
      html +=
        '<p class="mp-popup-by">添加者：' + esc(place.created_by_name) + "</p>";
    }
    html += "</div>";
    html += '<div class="mp-popup-actions">';
    html += nav;
    if (place.can_edit) {
      html +=
        '<button type="button" class="mp-link-btn mp-edit-btn" data-mp-action="edit" data-mp-id="' +
        place.id +
        '">编辑</button>';
      html +=
        '<button type="button" class="mp-link-btn mp-edit-btn is-danger" data-mp-action="delete" data-mp-id="' +
        place.id +
        '">删除</button>';
    }
    html += "</div></div>";
    return html;
  }

  function makeMarker(place) {
    var color = placeColor(place);
    var ink = lum(color) > 0.36 ? "#2b2d42" : "#ffffff";
    var icon = L.divIcon({
      className: "mp-marker" + (place.fresh ? " is-fresh" : ""),
      html:
        '<span class="mp-pin" style="--pin-color:' +
        esc(color) +
        ";--pin-ink:" +
        ink +
        '"><span class="mp-pin-head">' +
        esc(placeGlyph(place)) +
        '</span><span class="mp-pin-tail"></span></span>',
      iconSize: [32, 42],
      iconAnchor: [16, 40],
      popupAnchor: [0, -40]
    });
    var marker = L.marker(displayLatLng(place.lat, place.lng), {
      icon: icon,
      draggable: Boolean(place.can_edit),
      riseOnHover: true,
      title: place.name
    });
    marker.bindPopup(popupHtml(place), { maxWidth: 320, minWidth: 230, autoPanPadding: [24, 24] });
    marker.on("popupopen", function () {
      state.activeId = place.id;
      renderList();
      if (place.fresh) {
        place.fresh = false;
        var iconEl = marker.getElement();
        if (iconEl) iconEl.classList.remove("is-fresh");
        api("/api/map/seen", {
          method: "POST",
          body: JSON.stringify({ notify_targets: [place.id] })
        })
          .then(function () {
            notifyDockRefresh();
          })
          .catch(function () {});
      }
    });
    marker.on("dragend", function () {
      var latlng = marker.getLatLng();
      var wgs = dataLatLng(latlng.lat, latlng.lng);
      var nextLat = Number(wgs[0].toFixed(6));
      var nextLng = Number(wgs[1].toFixed(6));
      if (nextLat === Number(place.lat) && nextLng === Number(place.lng)) {
        return;
      }
      askConfirm(
        "更新标记位置？",
        "把「" + place.name + "」移动到新位置？确认后会保存到地图数据里。",
        "保存位置",
        function () {
          api("/api/map/places/" + place.id, {
            method: "PATCH",
            body: JSON.stringify({ lat: nextLat, lng: nextLng })
          })
            .then(function () {
              place.lat = nextLat;
              place.lng = nextLng;
              notifyDockRefresh();
              toast("位置已更新");
            })
            .catch(function (err) {
              toast(err.message);
              marker.setLatLng(displayLatLng(place.lat, place.lng));
            });
        },
        {
          danger: false,
          onCancel: function () {
            marker.setLatLng(displayLatLng(place.lat, place.lng));
          }
        }
      );
    });
    return marker;
  }

  function renderMarkers() {
    if (!cluster) return;
    cluster.clearLayers();
    state.markers = {};
    visiblePlaces().forEach(function (place) {
      var marker = makeMarker(place);
      state.markers[place.id] = marker;
      cluster.addLayer(marker);
    });
  }

  function renderAll() {
    renderCatFilter();
    renderList();
    renderMarkers();
  }

  function fitAll() {
    var places = visiblePlaces();
    if (!places.length) {
      toast("没有可显示的标记");
      return;
    }
    var points = places.map(function (place) {
      return displayLatLng(place.lat, place.lng);
    });
    map.fitBounds(L.latLngBounds(points), { padding: [48, 48], maxZoom: 16 });
  }

  function focusPlace(place) {
    var marker = state.markers[place.id];
    var target = displayLatLng(place.lat, place.lng);
    state.activeId = place.id;
    renderList();
    if (marker && cluster.hasLayer(marker)) {
      cluster.zoomToShowLayer(marker, function () {
        marker.openPopup();
      });
    } else {
      map.setView(target, Math.max(map.getZoom(), 16));
    }
  }

  // ---------- data ----------
  function loadData(fitIfEmpty) {
    return api("/api/map", { method: "GET" }).then(function (data) {
      state.categories = data.categories || [];
      state.places = data.places || [];
      if (data.signed_in) {
        // 登录账号的「已看到标记」记在服务端，换浏览器、换设备都一致
        api("/api/map/seen", {
          method: "POST",
          body: JSON.stringify({
            notify_targets: data.notify_targets || []
          })
        }).catch(function () {});
      } else {
        var maxPlaceId = 0;
        state.places.forEach(function (place) {
          maxPlaceId = Math.max(maxPlaceId, Number(place.id) || 0);
        });
        try {
          localStorage.setItem("errorMapSeenPlaceId", String(maxPlaceId));
        } catch (err) {}
      }
      state.canManage = Boolean(data.can_manage);
      state.canAdd = Boolean(data.can_add);
      state.signedIn = Boolean(data.signed_in);
      state.canImport = Boolean(data.can_import);
      state.canManageCategories = Boolean(data.can_manage_categories);
      state.canFilterOwner = Boolean(data.can_filter_owner);
      state.myUserId = data.user_id == null ? "" : String(data.user_id);
      syncOwnerLabel();
      syncMapActions();
      var categoryIds = {};
      state.categories.forEach(function (cat) {
        categoryIds[cat.id] = cat;
      });
      if (state.categoryFilter && !categoryIds[state.categoryFilter]) {
        state.categoryFilter = null;
      }
      state.expandedTops.forEach(function (id) {
        var cat = categoryIds[id];
        if (!cat || cat.parent_id) state.expandedTops.delete(id);
      });
      renderOwnerFilter();
      renderAll();
      if (fitIfEmpty && !savedView && state.places.length) fitAll();
    });
  }

  // ---------- modals ----------
  function openModal(id) {
    var el = $(id);
    if (el) el.hidden = false;
  }

  function closeModal(id) {
    var el = $(id);
    if (el) el.hidden = true;
  }

  var confirmAction = null;
  var confirmCancelAction = null;
  function askConfirm(title, text, okText, onOk, options) {
    var opts = options || {};
    confirmAction = onOk;
    confirmCancelAction = opts.onCancel || null;
    $("mapConfirmTitle").textContent = title;
    $("mapConfirmText").textContent = text;
    var okButton = $("mapConfirmOk");
    okButton.textContent = okText || "确定";
    okButton.classList.toggle("mp-btn-danger", opts.danger !== false);
    okButton.classList.toggle("mp-btn-primary", opts.danger === false);
    openModal("mapConfirmModal");
  }

  function resolveConfirm(ok) {
    var action = ok ? confirmAction : null;
    var cancelAction = ok ? null : confirmCancelAction;
    confirmAction = null;
    confirmCancelAction = null;
    closeModal("mapConfirmModal");
    if (action) {
      action();
    } else if (cancelAction) {
      cancelAction();
    }
  }

  function fillSubSelect(topId, selectedSubId) {
    var select = $("placeCategorySub");
    if (!select) return;
    if (!topId) {
      select.innerHTML = '<option value="">未分类</option>';
      select.disabled = true;
      return;
    }
    select.disabled = false;
    var html = '<option value="">不指定（直接用一级分类）</option>';
    childCategories(topId).forEach(function (cat) {
      html +=
        '<option value="' +
        cat.id +
        '"' +
        (cat.id === selectedSubId ? " selected" : "") +
        ">" +
        esc(cat.name) +
        "</option>";
    });
    select.innerHTML = html;
  }

  function fillCategorySelect(selectedId) {
    var topSelect = $("placeCategoryTop");
    if (!topSelect) return;
    var selected = selectedId ? categoryById(selectedId) : null;
    var topId = selected ? selected.parent_id || selected.id : null;
    var subId = selected && selected.parent_id ? selected.id : null;
    var html = '<option value="">按文件里的分类</option>';
    topCategories().forEach(function (cat) {
      var children = childCategories(cat.id).length;
      html +=
        '<option value="' +
        cat.id +
        '"' +
        (cat.id === topId ? " selected" : "") +
        ">" +
        esc(cat.name) +
        (children ? "（" + children + " 个子类）" : "") +
        "</option>";
    });
    topSelect.innerHTML = html;
    fillSubSelect(topId, subId);
  }

  function placeFormCategoryId() {
    var sub = $("placeCategorySub");
    var top = $("placeCategoryTop");
    if (sub && !sub.disabled && sub.value) return Number(sub.value);
    if (top && top.value) return Number(top.value);
    return null;
  }

  function showFormError(message) {
    var el = $("mapPlaceError");
    if (!el) return;
    if (message) {
      el.textContent = message;
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  }

  /* ---------- 高德地点搜索（右上角按钮 + 向左滑出的输入框） ---------- */

  /*
   * 高德 POI 搜索的唯一入口：编辑弹窗里那份调用早就搬到这儿了，
   * 别在别处再写一份（后端 /api/map/poi-search 自带缓存，避免重复消耗月配额）。
   */
  function searchAmapPoi(keywords) {
    var words = String(keywords || "").trim();
    if (!words) return Promise.reject(new Error("请输入要搜索的地点名称。"));
    return api("/api/map/poi-search?keywords=" + encodeURIComponent(words));
  }

  function showMapSearchHint(text) {
    var hint = $("mapSearchHint");
    if (!hint) return;
    if (text) {
      hint.textContent = text;
      hint.hidden = false;
    } else {
      hint.textContent = "";
      hint.hidden = true;
    }
  }

  function resetMapSearchResults() {
    state.searchResults = [];
    var list = $("mapSearchResults");
    if (list) {
      list.innerHTML = "";
      list.hidden = true;
      list.classList.remove("is-open");
    }
    showMapSearchHint("");
  }

  function setMapSearchOpen(open) {
    state.searchOpen = Boolean(open);
    var panel = $("mapSearchPanel");
    var button = $("mapSearchBtn");
    var input = $("mapPoiSearch");
    if (panel) panel.classList.toggle("is-open", state.searchOpen);
    if (button) {
      button.classList.toggle("is-on", state.searchOpen);
      button.setAttribute("aria-expanded", state.searchOpen ? "true" : "false");
    }
    if (!state.searchOpen) {
      resetMapSearchResults();
      if (input) input.blur();
      return;
    }
    // 展开后自动聚焦，光标直接落在输入框里
    if (input) {
      window.setTimeout(function () {
        input.focus();
      }, 60);
    }
  }

  function renderMapSearchResults(pois) {
    var list = $("mapSearchResults");
    if (!list) return;
    state.searchResults = pois || [];
    list.innerHTML = "";
    list.classList.remove("is-open");
    if (!state.searchResults.length) {
      list.hidden = true;
      showMapSearchHint("没有搜到匹配的地点，换个关键词试试。");
      return;
    }
    state.searchResults.forEach(function (poi, index) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "mp-poi-item";
      button.setAttribute("data-poi-index", String(index));
      var title = document.createElement("strong");
      title.textContent = poi.name || "未命名地点";
      var meta = document.createElement("span");
      meta.textContent =
        [poi.address, poi.type].filter(Boolean).join(" · ") || "高德地图";
      button.appendChild(title);
      button.appendChild(meta);
      item.appendChild(button);
      list.appendChild(item);
    });
    showMapSearchHint("");
    list.hidden = false;
    // 下一帧再加 is-open，结果面板才是从输入框下方展开出来的
    window.requestAnimationFrame(function () {
      list.classList.add("is-open");
    });
  }

  function runMapSearch() {
    var input = $("mapPoiSearch");
    if (!input || state.searchBusy) return;
    var keywords = input.value.trim();
    if (!keywords) {
      showMapSearchHint("请输入要搜索的地点名称。");
      return;
    }
    state.searchBusy = true;
    showMapSearchHint("正在搜索高德地图…");
    var list = $("mapSearchResults");
    if (list) {
      list.hidden = true;
      list.classList.remove("is-open");
    }
    searchAmapPoi(keywords)
      .then(function (data) {
        renderMapSearchResults((data && data.pois) || []);
      })
      .catch(function (err) {
        showMapSearchHint(err.message);
      })
      .then(function () {
        state.searchBusy = false;
        if (state.searchOpen && input) input.focus();
      });
  }

  /*
   * 选中一条结果：搜索框向右收回 → 地图平滑移到该点 → 立刻进中心选点模式，
   * 水滴就落在地图正中心（也就是这个地点）；确认后弹窗会自动带入它的名称和地址。
   */
  function pickMapSearchResult(index) {
    var poi = state.searchResults[index];
    if (!poi) return;
    if (!state.canAdd) {
      toast(NO_PERMISSION_TIP);
      return;
    }
    var wgs = Geo.fromGcj(Number(poi.lat), Number(poi.lng));
    state.searchPick = {
      name: poi.name || "",
      address: poi.address || "",
      lat: wgs[0],
      lng: wgs[1]
    };
    setMapSearchOpen(false);
    map.closePopup();
    map.setView(displayLatLng(wgs[0], wgs[1]), Math.max(map.getZoom(), 16), {
      animate: true
    });
    startPlacing();
  }

  function openPlaceModal(place, coords, preset) {
    state.photoFiles.forEach(function (_file, index) {
      if (state.photoUrls[index]) URL.revokeObjectURL(state.photoUrls[index]);
    });
    state.photoFiles = [];
    state.photoUrls = [];
    state.editingId = place ? place.id : null;
    state.status = place ? place.status || "" : "";
    state.rating = place && place.rating ? Number(place.rating) : 0;
    $("mapPlaceTitle").textContent = place ? "编辑标记" : "添加标记";
    // preset：从右上角搜索选中的地点，确认落点后自动带入名称 / 地址
    $("placeName").value = place ? place.name : (preset && preset.name) || "";
    $("placeSubtitle").value = place ? place.subtitle || "" : "";
    $("placeAddress").value = place
      ? place.address || ""
      : (preset && preset.address) || "";
    $("placeSignature").value = place ? place.signature || "" : "";
    $("placeTags").value = place ? place.tags || "" : "";
    $("placeNote").value = place ? place.note || "" : "";
    $("placeLat").value = place ? place.lat : coords[0].toFixed(6);
    $("placeLng").value = place ? place.lng : coords[1].toFixed(6);
    var deleteBtn = $("mapPlaceDelete");
    if (deleteBtn) deleteBtn.hidden = !place;
    fillCategorySelect(place ? place.category_id : null);
    renderStatusControl();
    renderRatingControl();
    renderPhotoEditor(place);
    var photoInput = $("placePhotoInput");
    if (photoInput) photoInput.value = "";
    showFormError("");
    openModal("mapPlaceModal");
    setTimeout(function () {
      $("placeName").focus();
    }, 30);
  }

  function renderStatusControl() {
    var box = $("placeStatus");
    if (!box) return;
    Array.prototype.forEach.call(box.querySelectorAll("button"), function (btn) {
      btn.classList.toggle(
        "is-on",
        (btn.getAttribute("data-status") || "") === state.status
      );
    });
  }

  function renderRatingControl() {
    var box = $("placeRating");
    if (!box) return;
    Array.prototype.forEach.call(box.querySelectorAll("button"), function (btn) {
      btn.classList.toggle("is-on", Number(btn.getAttribute("data-star")) <= state.rating);
    });
    var text = $("placeRatingText");
    if (text) text.textContent = state.rating ? state.rating + " / 5" : "未评分";
  }

  function renderPhotoEditor(place) {
    var box = $("placePhotos");
    if (!box) return;
    var html = "";
    ((place && place.photos) || []).forEach(function (photo) {
      html +=
        '<span class="mp-photo-item"><img src="' +
        esc(photo.url) +
        '" alt="" loading="lazy"><button type="button" class="mp-photo-remove" data-photo-remove="' +
        photo.id +
        '" title="删除照片">×</button></span>';
    });
    state.photoFiles.forEach(function (_file, index) {
      html +=
        '<span class="mp-photo-item"><img src="' +
        esc(state.photoUrls[index]) +
        '" alt=""><span class="mp-photo-pending">待上传</span>' +
        '<button type="button" class="mp-photo-remove" data-pending-remove="' +
        index +
        '" title="移除">×</button></span>';
    });
    box.innerHTML = html;
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        resolve(result.slice(result.indexOf(",") + 1));
      };
      reader.onerror = function () {
        reject(new Error("读取图片失败"));
      };
      reader.readAsDataURL(file);
    });
  }

  function uploadPendingPhotos(placeId) {
    if (!state.photoFiles.length) return Promise.resolve();
    var files = state.photoFiles.slice();
    var urls = state.photoUrls.slice();
    state.photoFiles = [];
    state.photoUrls = [];
    return files
      .reduce(function (chain, file) {
        return chain.then(function () {
          return fileToBase64(file).then(function (data) {
            return api("/api/map/places/" + placeId + "/photos", {
              method: "POST",
              body: JSON.stringify({ name: file.name, data_base64: data })
            });
          });
        });
      }, Promise.resolve())
      .then(function () {
        urls.forEach(function (url) {
          URL.revokeObjectURL(url);
        });
      })
      .catch(function (err) {
        urls.forEach(function (url) {
          URL.revokeObjectURL(url);
        });
        toast("部分照片上传失败：" + err.message);
      });
  }

  function submitPlace(event) {
    event.preventDefault();
    var payload = {
      name: $("placeName").value.trim(),
      category_id: placeFormCategoryId(),
      subtitle: $("placeSubtitle").value.trim(),
      address: $("placeAddress").value.trim(),
      signature: $("placeSignature").value.trim(),
      tags: $("placeTags").value.trim(),
      note: $("placeNote").value.trim(),
      status: state.status,
      rating: state.rating,
      lat: Number($("placeLat").value),
      lng: Number($("placeLng").value)
    };
    if (!payload.name) {
      showFormError("名称不能为空。");
      return;
    }
    if (!isFinite(payload.lat) || !isFinite(payload.lng)) {
      showFormError("坐标无效。");
      return;
    }
    var editing = state.editingId;
    var path = editing ? "/api/map/places/" + editing : "/api/map/places";
    api(path, { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) })
      .then(function (data) {
        var targetId = editing || data.id;
        return uploadPendingPhotos(targetId).then(function () {
          closeModal("mapPlaceModal");
          notifyDockRefresh();
          toast(editing ? "标记已更新" : "标记已添加");
          return loadData(false).then(function () {
            var target = placeById(targetId);
            if (target) focusPlace(target);
          });
        });
      })
      .catch(function (err) {
        showFormError(err.message);
      });
  }

  function deletePlace(place) {
    if (!place) return;
    askConfirm("删除标记？", "「" + place.name + "」会从地图上移除，这个操作不能撤销。", "删除", function () {
      api("/api/map/places/" + place.id, { method: "DELETE" })
        .then(function () {
          notifyDockRefresh();
          toast("已删除");
          return loadData(false);
        })
        .catch(function (err) {
          toast(err.message);
        });
    });
  }

  // ---------- category manager ----------
  function categoryToggleHtml(cat, childCount, expanded) {
    if (!childCount) {
      return '<span class="mp-cat-toggle is-empty" aria-hidden="true"></span>';
    }
    var label =
      (expanded ? "折叠「" : "展开「") +
      cat.name +
      "」的 " +
      childCount +
      " 个下级分类";
    return (
      '<button type="button" class="mp-cat-toggle" data-cat-toggle="' +
      cat.id +
      '" aria-expanded="' +
      (expanded ? "true" : "false") +
      '" aria-label="' +
      esc(label) +
      '" title="' +
      esc(label) +
      '"><i data-lucide="chevron-down"></i></button>'
    );
  }

  function categoryRowHtml(cat, isChild, childCount, expanded) {
    return (
      '<div class="mp-cat-row' +
      (isChild ? " is-child" : " is-top") +
      '" data-cat-row="' +
      cat.id +
      '" data-cat-old-name="' +
      esc(cat.name) +
      '">' +
      (isChild ? "" : categoryToggleHtml(cat, childCount, expanded)) +
      '<input class="mp-cat-glyph" type="text" maxlength="2" value="' +
      esc(cat.glyph || "·") +
      '" aria-label="分类字">' +
      '<input class="mp-cat-color" type="color" value="' +
      esc(cat.color || "#7b68ee") +
      '" aria-label="分类颜色">' +
      '<input class="mp-cat-name" type="text" maxlength="60" value="' +
      esc(cat.name) +
      '" aria-label="分类名称">' +
      '<input class="mp-cat-note" type="text" maxlength="500" value="' +
      esc(cat.note || "") +
      '" placeholder="分类备注" aria-label="分类备注">' +
      '<div class="mp-cat-actions">' +
      '<button type="button" class="mp-icon-btn" data-cat-save="' +
      cat.id +
      '" title="保存分类"><i data-lucide="check"></i></button>' +
      '<button type="button" class="mp-icon-btn" data-cat-delete="' +
      cat.id +
      '" title="删除分类"><i data-lucide="trash-2"></i></button>' +
      "</div></div>"
    );
  }

  function renderCatRows() {
    var box = $("mapCatRows");
    if (!box) return;
    var tops = topCategories();
    if (!tops.length) {
      box.innerHTML = '<p class="mp-empty">还没有分类。</p>';
      return;
    }
    var html = "";
    tops.forEach(function (top) {
      var kids = childCategories(top.id);
      var expanded = !kids.length || state.expandedTops.has(top.id);
      html +=
        '<div class="mp-cat-group' +
        (expanded ? "" : " is-collapsed") +
        '">' +
        categoryRowHtml(top, false, kids.length, expanded) +
        '<div class="mp-cat-children">';
      kids.forEach(function (child) {
        html += categoryRowHtml(child, true);
      });
      html +=
        '<button type="button" class="mp-cat-addchild" data-add-child="' +
        top.id +
        '">+ 添加「' +
        esc(top.name) +
        "」的下级分类</button></div></div>";
    });
    box.innerHTML = html;
    if (window.lucide && lucide.createIcons) lucide.createIcons();
  }

  // 把某一分类行滚到弹窗可视区内。弹窗顶部标题栏和底部操作栏都是 sticky 的，
  // 只靠 focus() 的自动滚动会把行停在贴边栏底下，所以要按这两条栏的高度自己算位置。
  function revealCategoryRow(id) {
    var row = document.querySelector('.mp-cat-row[data-cat-row="' + id + '"]');
    if (!row) return;
    var input = row.querySelector(".mp-cat-name");
    if (input) {
      try {
        input.focus({ preventScroll: true });
      } catch (err) {
        input.focus();
      }
    }
    var dialog = row.closest ? row.closest(".mp-dialog") : null;
    if (!dialog) {
      if (row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
      return;
    }
    var gap = 10;
    var box = dialog.getBoundingClientRect();
    var head = dialog.querySelector(".mp-dialog-head");
    var foot = dialog.querySelector(".mp-dialog-actions");
    var top = box.top + (head ? head.getBoundingClientRect().height : 0) + gap;
    var bottom = box.bottom - (foot ? foot.getBoundingClientRect().height : 0) - gap;
    var rowBox = row.getBoundingClientRect();
    if (rowBox.top < top) {
      dialog.scrollTop -= top - rowBox.top;
    } else if (rowBox.bottom > bottom) {
      dialog.scrollTop += rowBox.bottom - bottom;
    }
  }

  function createCategoryUnder(parentId) {
    var parent = categoryById(parentId);
    if (!parent) return;
    api("/api/map/categories", {
      method: "POST",
      body: JSON.stringify({
        name: "新子类",
        glyph: parent.glyph || "·",
        color: parent.color || "#7b68ee",
        parent_id: parentId
      })
    })
      .then(function (created) {
        toast("已添加下级分类，改好后点对勾保存");
        state.expandedTops.add(parentId);
        return loadData(false).then(function () {
          renderCatRows();
          revealCategoryRow(created.id);
        });
      })
      .catch(function (err) {
        toast(err.message);
      });
  }

  function saveCategory(row) {
    var id = Number(row.getAttribute("data-cat-row"));
    var payload = {
      glyph: row.querySelector(".mp-cat-glyph").value.trim() || "·",
      color: row.querySelector(".mp-cat-color").value,
      name: row.querySelector(".mp-cat-name").value.trim(),
      note: row.querySelector(".mp-cat-note").value.trim()
    };
    if (!payload.name) {
      toast("分类名称不能为空");
      return;
    }
    api("/api/map/categories/" + id, { method: "PATCH", body: JSON.stringify(payload) })
      .then(function () {
        toast("分类已保存");
        return loadData(false).then(renderCatRows);
      })
      .catch(function (err) {
        toast(err.message);
      });
  }

  function deleteCategory(row) {
    var id = Number(row.getAttribute("data-cat-row"));
    var cat = categoryById(id);
    if (!cat) return;
    var children = childCategories(id).length;
    askConfirm(
      "删除分类？",
      "「" +
        cat.name +
        "」" +
        (children ? "及其 " + children + " 个下级分类" : "") +
        "会被删除，原有标记会变成未分类，标记本身不会删除。",
      "删除",
      function () {
        api("/api/map/categories/" + id, { method: "DELETE" })
          .then(function () {
            if (state.categoryFilter === id) state.categoryFilter = null;
            toast("分类已删除");
            return loadData(false).then(renderCatRows);
          })
          .catch(function (err) {
            toast(err.message);
          });
      }
    );
  }

  // ---------- import ----------
  function convertToWgs(lat, lng, system) {
    if (system === "gcj02") return Geo.fromGcj(lat, lng);
    if (system === "bd09") return Geo.bdToWgs(lat, lng);
    return [lat, lng];
  }

  function buildPointFeature(name, lat, lng, props, system) {
    var wgs = convertToWgs(lat, lng, system);
    var properties = Object.assign({}, props || {});
    properties.name = name;
    return {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [Number(wgs[1].toFixed(6)), Number(wgs[0].toFixed(6))]
      },
      properties: properties
    };
  }

  function textOf(node, tag) {
    var el = node.getElementsByTagName(tag)[0];
    return el && el.textContent ? el.textContent.trim() : "";
  }

  function parseKmlRows(text) {
    var doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.getElementsByTagName("parsererror").length) throw new Error("KML 解析失败。");
    var rows = [];
    var marks = doc.getElementsByTagName("Placemark");
    for (var i = 0; i < marks.length; i++) {
      var mark = marks[i];
      var coordsEl = mark.getElementsByTagName("coordinates")[0];
      if (!coordsEl) continue;
      var tuple = coordsEl.textContent.trim().split(/\s+/)[0] || "";
      var parts = tuple.split(",");
      if (parts.length < 2) continue;
      var lng = parseFloat(parts[0]);
      var lat = parseFloat(parts[1]);
      if (!isFinite(lat) || !isFinite(lng)) continue;
      rows.push({
        name: textOf(mark, "name") || "未命名",
        lat: lat,
        lng: lng,
        props: { note: textOf(mark, "description") || "" }
      });
    }
    return rows;
  }

  function parseGpxRows(text) {
    var doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.getElementsByTagName("parsererror").length) throw new Error("GPX 解析失败。");
    var rows = [];
    ["wpt", "trkpt", "rtept"].forEach(function (tag) {
      var nodes = doc.getElementsByTagName(tag);
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        var lat = parseFloat(node.getAttribute("lat"));
        var lng = parseFloat(node.getAttribute("lon"));
        if (!isFinite(lat) || !isFinite(lng)) continue;
        rows.push({
          name: textOf(node, "name") || "未命名",
          lat: lat,
          lng: lng,
          props: { note: textOf(node, "desc") || "" }
        });
      }
    });
    return rows;
  }

  function parseCsvRows(text) {
    var lines = text
      .split(/\r?\n/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean);
    if (!lines.length) return [];
    var delimiter = lines[0].indexOf("\t") >= 0 ? "\t" : lines[0].indexOf(";") >= 0 ? ";" : ",";
    function split(line) {
      return line.split(delimiter).map(function (cell) {
        return cell.trim().replace(/^"|"$/g, "");
      });
    }
    var header = split(lines[0]);
    var lower = header.map(function (cell) {
      return cell.toLowerCase();
    });
    function find(keys) {
      for (var i = 0; i < lower.length; i++) {
        for (var k = 0; k < keys.length; k++) {
          if (lower[i].indexOf(keys[k]) >= 0) return i;
        }
      }
      return -1;
    }
    var hasHeader =
      find(["名称", "name", "标题", "title", "地点"]) >= 0 ||
      find(["经度", "lng", "lon", "纬度", "lat"]) >= 0;
    var idx = hasHeader
      ? {
          name: find(["名称", "name", "标题", "title", "地点"]),
          lng: find(["经度", "lng", "lon", "x"]),
          lat: find(["纬度", "lat", "y"]),
          address: find(["地址", "address"]),
          note: find(["备注", "note", "描述", "desc"]),
          category: find(["分类", "category"]),
          tags: find(["标签", "tag"])
        }
      : { name: 0, lng: 1, lat: 2, address: -1, note: -1, category: -1, tags: -1 };
    var dataLines = hasHeader ? lines.slice(1) : lines;
    var rows = [];
    dataLines.forEach(function (line) {
      var cells = split(line);
      var name = idx.name >= 0 ? cells[idx.name] : "";
      var lng = idx.lng >= 0 ? parseFloat(cells[idx.lng]) : NaN;
      var lat = idx.lat >= 0 ? parseFloat(cells[idx.lat]) : NaN;
      if (Math.abs(lat) > 90 && Math.abs(lng) <= 90) {
        var swap = lat;
        lat = lng;
        lng = swap;
      }
      if (!name || !isFinite(lat) || !isFinite(lng)) return;
      var props = {};
      if (idx.address >= 0 && cells[idx.address]) props.address = cells[idx.address];
      if (idx.note >= 0 && cells[idx.note]) props.note = cells[idx.note];
      if (idx.category >= 0 && cells[idx.category]) props.category = cells[idx.category];
      if (idx.tags >= 0 && cells[idx.tags]) props.tags = cells[idx.tags];
      rows.push({ name: name, lat: lat, lng: lng, props: props });
    });
    return rows;
  }

  function parseMapBridgeItems(parsed, meta) {
    meta.format = "mapbridge";
    var features = [];
    (parsed.items || []).forEach(function (item) {
      if (!item || typeof item !== "object") return;
      if (item.kind === "route" && Array.isArray(item.stops)) {
        item.stops.forEach(function (stop) {
          var point = stop && stop.point;
          var lat = point ? Number(point.lat) : NaN;
          var lng = point ? Number(point.lng) : NaN;
          if (!isFinite(lat) || !isFinite(lng)) return;
          features.push(
            buildPointFeature(
              (item.name ? item.name + " · " : "") + (stop.name || "途经点"),
              lat,
              lng,
              {
                note: "高德路线收藏" + (item.name ? "：" + item.name : ""),
                tags: "高德收藏,路线"
              },
              "wgs84"
            )
          );
        });
        return;
      }
      var geometry = item.geometry || {};
      var point = geometry.point;
      if (!point && geometry.type === "Point" && Array.isArray(geometry.coordinates)) {
        point = { lng: geometry.coordinates[0], lat: geometry.coordinates[1] };
      }
      if (!point) return;
      var lat = Number(point.lat);
      var lng = Number(point.lng);
      if (!isFinite(lat) || !isFinite(lng)) return;
      features.push(
        buildPointFeature(
          item.name || "高德收藏",
          lat,
          lng,
          {
            address: item.address || "",
            note: item.note || "",
            tags: Array.isArray(item.tags) ? item.tags.join(",") : item.tags || ""
          },
          "wgs84"
        )
      );
    });
    if (!features.length) throw new Error("MapBridge 文件里没有可用的点。");
    return features;
  }

  function parseImportText(text, fileName, system, meta) {
    meta = meta || {};
    var trimmed = String(text || "").trim();
    if (!trimmed) throw new Error("内容为空。");
    var lowerName = String(fileName || "").toLowerCase();
    if (
      lowerName.endsWith(".kml") ||
      trimmed.indexOf("<kml") >= 0 ||
      trimmed.indexOf("<Placemark") >= 0
    ) {
      var kmlRows = parseKmlRows(trimmed);
      if (!kmlRows.length) throw new Error("KML 里没有解析到带坐标的点。");
      return kmlRows.map(function (row) {
        return buildPointFeature(row.name, row.lat, row.lng, row.props, system);
      });
    }
    if (lowerName.endsWith(".gpx") || trimmed.indexOf("<gpx") >= 0) {
      var gpxRows = parseGpxRows(trimmed);
      if (!gpxRows.length) throw new Error("GPX 里没有解析到带坐标的点。");
      return gpxRows.map(function (row) {
        return buildPointFeature(row.name, row.lat, row.lng, row.props, system);
      });
    }
    if (trimmed[0] === "{" || trimmed[0] === "[") {
      var parsed = JSON.parse(trimmed);
      if (parsed && parsed.format === "mapbridge" && Array.isArray(parsed.items)) {
        return parseMapBridgeItems(parsed, meta);
      }
      var features = Array.isArray(parsed) ? parsed : parsed.features;
      if (!Array.isArray(features)) throw new Error("GeoJSON 里没有 features 数组。");
      var converted = [];
      features.forEach(function (item) {
        var geometry = item && item.geometry;
        var coords = geometry && geometry.coordinates;
        if (!geometry || geometry.type !== "Point" || !Array.isArray(coords)) return;
        var lat = Number(coords[1]);
        var lng = Number(coords[0]);
        if (!isFinite(lat) || !isFinite(lng)) return;
        var props = Object.assign({}, item.properties || {});
        converted.push(
          buildPointFeature(props.name || props.title || "未命名", lat, lng, props, system)
        );
      });
      if (!converted.length) throw new Error("GeoJSON 里没有可用的点要素。");
      return converted;
    }
    var csvRows = parseCsvRows(trimmed);
    if (!csvRows.length) throw new Error("CSV 里没有解析到带坐标的点。");
    return csvRows.map(function (row) {
      return buildPointFeature(row.name, row.lat, row.lng, row.props, system);
    });
  }

  function fillImportCategorySelect() {
    var select = $("mapImportCategory");
    if (!select) return;
    var html = '<option value="">未分类</option>';
    topCategories().forEach(function (top) {
      html += '<option value="' + top.id + '">' + esc(top.name) + "（一级分类）</option>";
      childCategories(top.id).forEach(function (child) {
        html +=
          '<option value="' +
          child.id +
          '">' +
          esc(top.name) +
          " / " +
          esc(child.name) +
          "</option>";
      });
    });
    select.innerHTML = html;
  }

  var importFileName = "";

  function submitImport() {
    var errorEl = $("mapImportError");
    var text = $("mapImportText").value.trim();
    if (errorEl) errorEl.hidden = true;
    if (!text) {
      if (errorEl) {
        errorEl.textContent = "请选择文件或粘贴 GeoJSON 内容。";
        errorEl.hidden = false;
      }
      return;
    }
    var coordSelect = $("mapImportCoord");
    var system = coordSelect ? coordSelect.value : "wgs84";
    var meta = {};
    var features;
    try {
      features = parseImportText(text, importFileName, system, meta);
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = "解析失败：" + err.message;
        errorEl.hidden = false;
      }
      return;
    }
    var categorySelect = $("mapImportCategory");
    var categoryId =
      categorySelect && categorySelect.value ? Number(categorySelect.value) : null;
    api("/api/map/import", {
      method: "POST",
      body: JSON.stringify({
        type: "FeatureCollection",
        features: features,
        category_id: categoryId
      })
    })
      .then(function (result) {
        closeModal("mapImportModal");
        $("mapImportText").value = "";
        $("mapImportFile").value = "";
        importFileName = "";
        toast(
          "导入完成：新增 " +
            result.imported +
            " 个，跳过 " +
            result.skipped +
            " 个" +
            (meta.format === "mapbridge" ? "（MapBridge 高德收藏，已按 WGS-84 处理）" : "")
        );
        return loadData(false);
      })
      .catch(function (err) {
        if (errorEl) {
          errorEl.textContent = err.message;
          errorEl.hidden = false;
        }
      });
  }

  /*
   * ---------- 中心选点（PC / 移动端共用一套） ----------
   * 进入后地图正中心浮着一个水滴，水滴尖端就是将要落点的坐标。
   * 用户可以随意平移缩放，中心图标跟着屏幕走、不跟地图走；
   * 点对号 = 用当前中心点开编辑框，点叉号 / 按 Esc = 取消。
   * 全程不动地图的拖拽与缩放设置，退出时也不会留下任何监听。
   */
  var pinModeEl = $("mapPinMode");

  // 记一份中心点坐标（数据坐标），确认时再读一次真实中心作为兜底
  function pinCenterLatLng() {
    var center = map.getCenter();
    return dataLatLng(center.lat, center.lng);
  }

  function isPlacing() {
    return Boolean(state.placing);
  }

  function startPlacing() {
    if (!state.canAdd || state.placing) return;
    state.placing = true;
    if (pinModeEl) pinModeEl.hidden = false;
    // 地图移动结束 / 缩放结束时中心点才有意义，这里跟着更新一次即可
    map.on("moveend", syncPinCenter);
    map.on("dragend", syncPinCenter);
    map.on("zoomend", syncPinCenter);
  }

  function stopPlacing() {
    if (!state.placing) return;
    state.placing = false;
    if (pinModeEl) pinModeEl.hidden = true;
    map.off("moveend", syncPinCenter);
    map.off("dragend", syncPinCenter);
    map.off("zoomend", syncPinCenter);
    // 取消落点：搜索带过来的名称 / 地址也一起丢掉
    state.searchPick = null;
  }

  function syncPinCenter() {
    pinCenterLatLng();
  }

  function confirmPin() {
    if (!state.placing) return;
    var coords = pinCenterLatLng();
    /*
     * 落点就是刚搜到的那个地点时，把名称和地址带进弹窗；
     * 如果用户把地图拖走了（偏离超过 200 米），就当他是另选地方，不预填。
     */
    var preset = state.searchPick;
    if (preset) {
      var away = map.distance(
        displayLatLng(preset.lat, preset.lng),
        map.getCenter()
      );
      if (away > 200) preset = null;
    }
    stopPlacing();
    map.closePopup();
    openPlaceModal(null, coords, preset);
  }

  var pinConfirmBtn = $("mapPinConfirm");
  if (pinConfirmBtn) pinConfirmBtn.addEventListener("click", confirmPin);
  var pinCancelBtn = $("mapPinCancel");
  if (pinCancelBtn) pinCancelBtn.addEventListener("click", stopPlacing);

  /*
   * 长按地图 = 直接进中心选点。
   * 用 pointer 事件而不是 click，避开双击放大；按下后只要指针挪动超过 8px、
   * 或者地图开始拖动，这次长按就作废，免得把「拖地图」误判成「长按」。
   * 长按落下后浏览器还会补一发 click，用 suppressNextClick 把它吃掉，
   * 否则松手会顺手打开标记点弹窗。
   */
  var LONG_PRESS_MS = 420;
  var LONG_PRESS_SLOP = 8;
  var pressTimer = null;
  var pressStart = null;
  var suppressNextClick = false;

  function cancelLongPress() {
    clearTimeout(pressTimer);
    pressTimer = null;
    pressStart = null;
  }

  var mapContainerEl = map.getContainer();

  mapContainerEl.addEventListener(
    "click",
    function (event) {
      if (!suppressNextClick) return;
      suppressNextClick = false;
      event.stopPropagation();
      event.preventDefault();
    },
    true
  );

  mapContainerEl.addEventListener("pointerdown", function (event) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (isPlacing() || !state.canAdd) return;
    if (event.target.closest && event.target.closest(".leaflet-control-container")) return;
    cancelLongPress();
    pressStart = { x: event.clientX, y: event.clientY };
    pressTimer = setTimeout(function () {
      pressTimer = null;
      pressStart = null;
      suppressNextClick = true;
      startPlacing();
    }, LONG_PRESS_MS);
  });

  mapContainerEl.addEventListener("pointermove", function (event) {
    if (!pressStart) return;
    var dx = event.clientX - pressStart.x;
    var dy = event.clientY - pressStart.y;
    if (Math.sqrt(dx * dx + dy * dy) > LONG_PRESS_SLOP) cancelLongPress();
  });

  ["pointerup", "pointercancel"].forEach(function (name) {
    mapContainerEl.addEventListener(name, cancelLongPress);
  });
  map.on("movestart", cancelLongPress);

  // ---------- events ----------
  /*
   * 分类筛选入口（PC 与手机同一套）：点一下在按钮上方开出多级分类树，
   * 选某一级就按「这一级 + 它的下级」过滤，再点一下收起。
   */
  var catEntry = $("mapCatBtn");
  if (catEntry) {
    catEntry.addEventListener("click", function () {
      var pop = $("mapCatPop");
      var willOpen = Boolean(pop && pop.hidden);
      if (willOpen) {
        closeOwnerPicker();
        renderCatFilter();
      }
      setCatPopOpen(willOpen);
    });
  }

  var catOptions = $("mapCatPopList");
  if (catOptions) {
    catOptions.addEventListener("click", function (event) {
      // 有下级的节点：这一下只负责展开 / 折叠，不触发筛选
      var parentRow = event.target.closest("[data-cat-parent]");
      if (parentRow) {
        var parentId = Number(parentRow.getAttribute("data-cat-parent"));
        var kids = catOptions.querySelector('[data-kids="' + parentId + '"]');
        var open = !state.expandedKeys.has(parentId);
        if (open) state.expandedKeys.add(parentId);
        else state.expandedKeys.delete(parentId);
        if (kids) kids.hidden = !open;
        parentRow.setAttribute("aria-expanded", open ? "true" : "false");
        // 只翻了这一棵子树的 display，整棵树不重建
        applyPopHeight($("mapCatPop"));
        return;
      }
      var option = event.target.closest("[data-cat]");
      if (!option) return;
      var raw = option.getAttribute("data-cat");
      state.categoryFilter = raw ? Number(raw) : null;
      closeCatPicker();
      syncCatLabel();
      renderAll();
    });
  }

  var searchInput = $("mapSearch");
  if (searchInput) {
    var searchTimer = null;
    searchInput.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.keyword = searchInput.value;
        renderAll();
      }, 120);
    });
  }

  /*
   * 操作卡片里的添加者入口（PC 与手机同一套）：点一下在按钮上方开出气泡浮层，
   * 再点一下收起来。普通账户没有「挑人」的权限，按钮退化成「全部 / 只看我添加的」开关。
   */
  var ownerEntry = $("mapOwnerBtn");
  if (ownerEntry) {
    ownerEntry.addEventListener("click", function () {
      if (!state.canFilterOwner) {
        state.ownerFilter = state.ownerFilter ? "" : state.myUserId;
        syncOwnerLabel();
        renderAll();
        return;
      }
      var pop = $("mapOwnerPop");
      var willOpen = Boolean(pop && pop.hidden);
      if (willOpen) {
        closeCatPicker();
        renderOwnerFilter();
      }
      setOwnerPopOpen(willOpen);
    });
  }

  // 点浮层和入口按钮以外的地方就把浮层收起来（分类与添加者同一套；Escape 另见键盘处理）
  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var ownerPop = $("mapOwnerPop");
    if (ownerPop && !ownerPop.hidden) {
      var inOwner = target.closest("#mapOwnerPop") || target.closest("#mapOwnerBtn");
      if (!inOwner) setOwnerPopOpen(false);
    }
    var catPop = $("mapCatPop");
    if (catPop && !catPop.hidden) {
      var inCat = target.closest("#mapCatPop") || target.closest("#mapCatBtn");
      if (!inCat) setCatPopOpen(false);
    }
    if (state.searchOpen) {
      var searchSlot = document.querySelector(".mp-search-slot");
      if (searchSlot && !searchSlot.contains(target)) setMapSearchOpen(false);
    }
  });

  var ownerOptions = $("mapOwnerPopList");
  if (ownerOptions) {
    ownerOptions.addEventListener("click", function (event) {
      var option = event.target.closest("[data-owner]");
      if (!option) return;
      state.ownerFilter = option.getAttribute("data-owner") || "";
      closeOwnerPicker();
      // 按钮的提示只在 renderOwnerFilter 里更新，选完要顺手同步一次，
      // 否则会一直停在上一个添加者的状态上，直到重新打开浮层
      syncOwnerLabel();
      renderAll();
    });
  }

  var statusBox = $("placeStatus");
  if (statusBox) {
    statusBox.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-status]");
      if (!btn) return;
      state.status = btn.getAttribute("data-status") || "";
      renderStatusControl();
    });
  }

  var placeTopSelect = $("placeCategoryTop");
  if (placeTopSelect) {
    placeTopSelect.addEventListener("change", function () {
      fillSubSelect(placeTopSelect.value ? Number(placeTopSelect.value) : null, null);
    });
  }

  var ratingBox = $("placeRating");
  if (ratingBox) {
    ratingBox.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-star]");
      if (!btn) return;
      var value = Number(btn.getAttribute("data-star"));
      state.rating = state.rating === value ? 0 : value;
      renderRatingControl();
    });
  }

  var photoInput = $("placePhotoInput");
  if (photoInput) {
    photoInput.addEventListener("change", function () {
      var place = state.editingId ? placeById(state.editingId) : null;
      var existing = place ? (place.photos || []).length : 0;
      var room = Math.max(
        0,
        mapPhotoLimit.max_count - existing - state.photoFiles.length
      );
      var files = Array.prototype.slice.call(photoInput.files || []);
      files.slice(0, room).forEach(function (file) {
        if (file.size > mapPhotoLimit.max_file_bytes) {
          toast(file.name + " 超过 " + mapPhotoLabel() + "，已跳过");
          return;
        }
        state.photoFiles.push(file);
        state.photoUrls.push(URL.createObjectURL(file));
      });
      if (files.length > room) {
        toast("每个标记最多 " + mapPhotoLimit.max_count + " 张照片");
      }
      photoInput.value = "";
      renderPhotoEditor(place);
    });

    // 足迹照片：点击 / 拖拽 / 拖文件夹（只挑图片）
    if (window.ErrorDropZone) {
      window.ErrorDropZone.attach(photoInput, {
        input: photoInput,
        dropTarget: photoInput.closest(".mp-field") || photoInput,
        accept: ["image/*", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"],
        maxCount: function () {
          return mapPhotoLimit.max_count;
        },
        multiple: true,
        pickerId: "errorjiang-map-photo",
        toast: toast
      });
    }
  }

  var photoBox = $("placePhotos");
  if (photoBox) {
    photoBox.addEventListener("click", function (event) {
      var removeExisting = event.target.closest("[data-photo-remove]");
      if (removeExisting) {
        var photoId = Number(removeExisting.getAttribute("data-photo-remove"));
        askConfirm("删除照片？", "这张照片会从标记里移除。", "删除", function () {
          api("/api/map/photos/" + photoId, { method: "DELETE" })
            .then(function () {
              toast("照片已删除");
              return loadData(false).then(function () {
                renderPhotoEditor(placeById(state.editingId));
              });
            })
            .catch(function (err) {
              toast(err.message);
            });
        });
        return;
      }
      var removePending = event.target.closest("[data-pending-remove]");
      if (removePending) {
        var index = Number(removePending.getAttribute("data-pending-remove"));
        if (state.photoUrls[index]) URL.revokeObjectURL(state.photoUrls[index]);
        state.photoFiles.splice(index, 1);
        state.photoUrls.splice(index, 1);
        renderPhotoEditor(placeById(state.editingId));
      }
    });
  }

  var listBox = $("mapList");
  if (listBox) {
    listBox.addEventListener("click", function (event) {
      var item = event.target.closest(".mp-item");
      if (!item) return;
      var place = placeById(Number(item.getAttribute("data-place")));
      if (place) focusPlace(place);
    });
  }

  mapEl.addEventListener("click", function (event) {
    var actionEl = event.target.closest("[data-mp-action]");
    if (!actionEl) return;
    var place = placeById(Number(actionEl.getAttribute("data-mp-id")));
    if (!place) return;
    if (actionEl.getAttribute("data-mp-action") === "edit") openPlaceModal(place);
    else deletePlace(place);
  });

  var locateBtn = $("mapLocateBtn");
  var locateMarker = null;
  if (locateBtn) {
    locateBtn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        toast("当前浏览器不支持定位");
        return;
      }
      locateBtn.classList.add("is-on");
      navigator.geolocation.getCurrentPosition(
        function (position) {
          locateBtn.classList.remove("is-on");
          var wgs = [position.coords.latitude, position.coords.longitude];
          var shown = displayLatLng(wgs[0], wgs[1]);
          map.setView(shown, Math.max(map.getZoom(), 15));
          if (locateMarker) map.removeLayer(locateMarker);
          locateMarker = L.marker(shown, {
            icon: L.divIcon({ className: "", html: '<span class="mp-locate-dot"></span>', iconSize: [16, 16] }),
            interactive: false
          }).addTo(map);
        },
        function () {
          locateBtn.classList.remove("is-on");
          toast("定位失败，请检查浏览器定位权限");
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
      );
    });
  }

  var fitBtn = $("mapFitBtn");
  if (fitBtn) fitBtn.addEventListener("click", fitAll);

  /*
   * 右上角地点搜索：点按钮展开（输入框向左滑出 + 自动聚焦）；
   * 已经展开时，输入框里有字就再搜一次，没字就收起。
   * 回车等于"确认搜索"，失焦 / 点外部 / ESC 都会把输入框向右收回。
   */
  var searchBtn = $("mapSearchBtn");
  var searchInput = $("mapPoiSearch");
  var searchList = $("mapSearchResults");
  if (searchBtn) {
    searchBtn.addEventListener("click", function () {
      if (!state.searchOpen) {
        openBasePanel(false);
        setMapSearchOpen(true);
        return;
      }
      if (searchInput && searchInput.value.trim()) runMapSearch();
      else setMapSearchOpen(false);
    });
  }
  if (searchInput) {
    searchInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      runMapSearch();
    });
    searchInput.addEventListener("blur", function () {
      window.setTimeout(function () {
        if (!state.searchOpen) return;
        // 焦点还在搜索这块（输入框、按钮、结果项）就当我还在用，不收
        var active = document.activeElement;
        if (active && active.closest && active.closest(".mp-search-slot")) return;
        setMapSearchOpen(false);
      }, 200);
    });
  }
  if (searchList) {
    searchList.addEventListener("click", function (event) {
      var item = event.target.closest("[data-poi-index]");
      if (!item) return;
      pickMapSearchResult(Number(item.getAttribute("data-poi-index")));
    });
  }

  var addBtn = $("mapAddBtn");
  if (addBtn) {
    addBtn.addEventListener("click", function () {
      if (!state.canAdd) {
        toast(NO_PERMISSION_TIP);
        return;
      }
      closeSidebar();
      startPlacing();
    });
  }

  var catsBtn = $("mapCatsBtn");
  if (catsBtn) {
    catsBtn.addEventListener("click", function () {
      if (!state.canManageCategories) {
        toast(NO_PERMISSION_TIP);
        return;
      }
      state.expandedTops.clear();
      renderCatRows();
      openModal("mapCatsModal");
    });
  }

  var importBtn = $("mapImportBtn");
  if (importBtn) {
    importBtn.addEventListener("click", function () {
      if (!state.canImport) {
        toast(NO_PERMISSION_TIP);
        return;
      }
      var errorEl = $("mapImportError");
      if (errorEl) errorEl.hidden = true;
      fillImportCategorySelect();
      openModal("mapImportModal");
    });
  }

  var catRows = $("mapCatRows");
  if (catRows) {
    catRows.addEventListener("click", function (event) {
      var toggle = event.target.closest("[data-cat-toggle]");
      if (toggle) {
        var toggleId = Number(toggle.getAttribute("data-cat-toggle"));
        if (state.expandedTops.has(toggleId)) state.expandedTops.delete(toggleId);
        else state.expandedTops.add(toggleId);
        renderCatRows();
        return;
      }
      var addChild = event.target.closest("[data-add-child]");
      if (addChild) {
        createCategoryUnder(Number(addChild.getAttribute("data-add-child")));
        return;
      }
      var row = event.target.closest(".mp-cat-row");
      if (!row) return;
      if (event.target.closest("[data-cat-save]")) saveCategory(row);
      else if (event.target.closest("[data-cat-delete]")) deleteCategory(row);
    });
    catRows.addEventListener("input", function (event) {
      // 改分类名时，如果图标还是旧名字首字（自动图标），实时跟随新名字
      if (event.isComposing) return; // 输入法组字过程中不跟随，等上屏后再说
      var nameInput = event.target.closest(".mp-cat-name");
      if (!nameInput) return;
      var row = nameInput.closest(".mp-cat-row");
      var glyphInput = row && row.querySelector(".mp-cat-glyph");
      if (!glyphInput) return;
      var oldGlyph = (row.getAttribute("data-cat-old-name") || "").trim().slice(0, 1);
      var nextGlyph = nameInput.value.trim().slice(0, 1);
      var currentGlyph = glyphInput.value.trim();
      if (oldGlyph && nextGlyph && (currentGlyph === oldGlyph || !currentGlyph || currentGlyph === "·")) {
        glyphInput.value = nextGlyph;
      }
    });
  }

  var catAdd = $("mapCatAdd");
  if (catAdd) {
    catAdd.addEventListener("click", function () {
      api("/api/map/categories", {
        method: "POST",
        body: JSON.stringify({ name: "新分类", glyph: "新", color: "#7b68ee" })
      })
        .then(function (created) {
          toast("已新增分类，改好后点对勾保存");
          return loadData(false).then(function () {
            renderCatRows();
            revealCategoryRow(created.id);
          });
        })
        .catch(function (err) {
          toast(err.message);
        });
    });
  }

  var placeForm = $("mapPlaceForm");
  if (placeForm) placeForm.addEventListener("submit", submitPlace);

  var placeDelete = $("mapPlaceDelete");
  if (placeDelete) {
    placeDelete.addEventListener("click", function () {
      var place = placeById(state.editingId);
      closeModal("mapPlaceModal");
      deletePlace(place);
    });
  }

  var importFile = $("mapImportFile");
  if (importFile) {
    importFile.addEventListener("change", function () {
      var file = importFile.files && importFile.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        $("mapImportText").value = String(reader.result || "");
      };
      importFileName = file.name;
      reader.readAsText(file);
    });

    // 导入文件：点击 / 拖拽（拖文件夹无用，单文件即可）
    if (window.ErrorDropZone) {
      window.ErrorDropZone.attach(importFile, {
        input: importFile,
        dropTarget: importFile.closest(".mp-field") || importFile,
        accept: [".geojson", ".json", ".kml", ".gpx", ".csv", ".tsv", ".txt"],
        multiple: false,
        folder: false,
        pickerId: "errorjiang-map-import",
        toast: toast
      });
    }
  }

  var importSubmit = $("mapImportSubmit");
  if (importSubmit) importSubmit.addEventListener("click", submitImport);

  var confirmOk = $("mapConfirmOk");
  if (confirmOk) {
    confirmOk.addEventListener("click", function () {
      resolveConfirm(true);
    });
  }
  var confirmCancel = $("mapConfirmCancel");
  if (confirmCancel) {
    confirmCancel.addEventListener("click", function () {
      resolveConfirm(false);
    });
  }

   [["mapPlaceClose", "mapPlaceModal"], ["mapPlaceCancel", "mapPlaceModal"],
    ["mapCatsClose", "mapCatsModal"], ["mapCatsDone", "mapCatsModal"],
   ["mapImportClose", "mapImportModal"], ["mapImportCancel", "mapImportModal"]].forEach(function (pair) {
    var btn = $(pair[0]);
    if (btn) btn.addEventListener("click", function () { closeModal(pair[1]); });
  });

   ["mapPlaceModal", "mapCatsModal", "mapImportModal"].forEach(function (id) {
    var modal = $(id);
    if (!modal) return;
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal(id);
    });
  });

  var confirmModal = $("mapConfirmModal");
  if (confirmModal) {
    confirmModal.addEventListener("click", function (event) {
      if (event.target === confirmModal) resolveConfirm(false);
    });
  }

  var sidebar = $("mapSidebar");
  var actionsToggle = $("mapActionsToggle");
  function isNarrowMap() {
    return window.matchMedia("(max-width: 860px)").matches;
  }
  function openSidebar() {
    if (sidebar) sidebar.classList.add("is-open");
    var app = $("mapApp");
    if (app) app.classList.add("is-panel-open");
    // 面板展开时右上角三个按钮会滑出去，别让底图选择面板孤零零留在上面
    openBasePanel(false);
    updateToggleForViewport();
  }
  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("is-open");
    var app = $("mapApp");
    if (app) app.classList.remove("is-panel-open");
    updateToggleForViewport();
  }

  /*
   * 手机端：从卡片顶部往下滑 = 收起检索卡片。
   * 只认竖直方向的下滑，往上滑和横向滑动都不拦；拖动时卡片跟着手指走一小段
   * （最多 80px），松手超过阈值就收起、没到就弹回。卡片本来盖在地图上层，
   * 不会把触摸事件传给地图，配合 header 上的 touch-action: none，
   * 浏览器也不会把这次拖动当成页面滚动或下拉刷新。
   */
  var sidebarHead = sidebar ? sidebar.querySelector(".mp-sidebar-head") : null;
  if (sidebarHead) {
    var swipeStartY = null;
    var swipeOffset = 0;
    var SWIPE_CLOSE_PX = 70;
    var SWIPE_MAX_PX = 80;

    sidebarHead.addEventListener(
      "touchstart",
      function (event) {
        if (!isNarrowMap() || !sidebar || !sidebar.classList.contains("is-open")) return;
        if (event.touches.length !== 1) return;
        swipeStartY = event.touches[0].clientY;
        swipeOffset = 0;
        sidebar.style.transition = "none";
      },
      { passive: true }
    );

    sidebarHead.addEventListener(
      "touchmove",
      function (event) {
        if (swipeStartY == null) return;
        var delta = event.touches[0].clientY - swipeStartY;
        if (delta <= 0) {
          swipeOffset = 0;
          sidebar.style.transform = "";
          return;
        }
        swipeOffset = delta;
        sidebar.style.transform = "translateY(" + Math.min(delta, SWIPE_MAX_PX) + "px)";
      },
      { passive: true }
    );

    function endSidebarSwipe() {
      if (swipeStartY == null) return;
      var shouldClose = swipeOffset > SWIPE_CLOSE_PX;
      swipeStartY = null;
      swipeOffset = 0;
      // 先把跟手的位移交还给 CSS（transition 恢复成 0.22s），再决定收起还是弹回
      sidebar.style.transition = "";
      sidebar.style.transform = "";
      if (shouldClose) closeSidebar();
    }

    sidebarHead.addEventListener("touchend", endSidebarSwipe);
    sidebarHead.addEventListener("touchcancel", endSidebarSwipe);
  }

  function setActionsToggle(collapsed) {
    if (!actionsToggle) return;
    actionsToggle.innerHTML = collapsed
      ? '<i data-lucide="chevron-up"></i>'
      : '<i data-lucide="chevron-down"></i>';
    var label = collapsed ? "展开检索区" : "收起检索区";
    actionsToggle.setAttribute("aria-label", label);
    actionsToggle.setAttribute("data-tip", label);
    if (window.lucide && lucide.createIcons) lucide.createIcons();
  }
  function updateToggleForViewport() {
    if (!actionsToggle) return;
    if (isNarrowMap()) {
      // 手机端：检索卡片收起时显示向上箭头（点击滑出），展开后显示向下箭头（点击收起）
      var open = Boolean(sidebar && sidebar.classList.contains("is-open"));
      actionsToggle.innerHTML = open
        ? '<i data-lucide="chevron-down"></i>'
        : '<i data-lucide="chevron-up"></i>';
      var label = open ? "收起检索区" : "展开检索区";
      actionsToggle.setAttribute("aria-label", label);
      actionsToggle.setAttribute("data-tip", label);
      if (window.lucide && lucide.createIcons) lucide.createIcons();
      return;
    }
    var app = $("mapApp");
    setActionsToggle(app ? app.classList.contains("is-sidebar-collapsed") : false);
  }
  function syncMapActions() {
    var app = $("mapApp");
    var actions = $("mapActions");
    if (!app || !actions) return;
    // 权限已经确定（或请求失败兜底），操作栏可以现身了
    actions.classList.remove("is-pending");
    app.style.setProperty(
      "--mp-actions-h",
      Math.round(actions.getBoundingClientRect().height) + "px"
    );
    updateToggleForViewport();
  }
  if (actionsToggle) {
    actionsToggle.addEventListener("click", function () {
      if (isNarrowMap()) {
        if (sidebar && sidebar.classList.contains("is-open")) closeSidebar();
        else openSidebar();
        return;
      }
      var app = $("mapApp");
      if (!app) return;
      setActionsToggle(app.classList.toggle("is-sidebar-collapsed"));
    });
  }
  window.addEventListener("resize", syncMapActions);
  // 视口变了，浮层的高度上限（= 检索卡片高度）也要跟着重算
  window.addEventListener("resize", function () {
    var openCat = $("mapCatPop");
    if (openCat && !openCat.hidden) applyPopHeight(openCat);
    var openOwner = $("mapOwnerPop");
    if (openOwner && !openOwner.hidden) applyPopHeight(openOwner);
  });

  var listBoxMobile = $("mapList");
  if (listBoxMobile) {
    listBoxMobile.addEventListener("click", function () {
      if (window.matchMedia("(max-width: 860px)").matches) closeSidebar();
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      stopPlacing();
      closeModal("mapPlaceModal");
      closeModal("mapCatsModal");
      closeModal("mapImportModal");
      setOwnerPopOpen(false);
      setCatPopOpen(false);
      setMapSearchOpen(false);
      resolveConfirm(false);
      openBasePanel(false);
      closeSidebar();
    }
  });

  if (window.lucide && lucide.createIcons) lucide.createIcons();
  if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);

  // 第一帧就按视口把切换按钮的箭头摆正（手机上收起状态是向上箭头），
  // 不用等地图数据回来才纠正，避免先闪一个「向左箭头」
  updateToggleForViewport();

  loadData(true)
    .then(function () {
      var placeId = Number(
        new URLSearchParams(window.location.search).get("place") || 0
      );
      if (!placeId) return;
      var place = placeById(placeId);
      if (place) {
        focusPlace(place);
      } else {
        toast("要定位的标记不存在或已删除");
      }
    })
    .catch(function (err) {
      // 数据没回来也要让操作栏现身（CSS 兜底是 1.2s，这里更快）
      syncMapActions();
      toast(err.message || "地图数据加载失败");
    });
})();
