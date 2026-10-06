(function () {
  "use strict";

  var mapEl = document.getElementById("map");
  if (!mapEl || typeof L === "undefined") return;

  function $(id) {
    return document.getElementById(id);
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
    signedIn: false,
    activeTop: new Set(),
    activeSubs: new Set(),
    activeTags: new Set(),
    keyword: "",
    markers: {},
    gcj: false,
    placing: false,
    editingId: null,
    activeId: null,
    status: "",
    rating: 0,
    photoFiles: [],
    photoUrls: [],
    poiResults: []
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
  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.hidden = true;
    }, 2600);
  }

  var hintEl = $("mapHint");
  function setHint(text) {
    if (!hintEl) return;
    if (text) {
      hintEl.textContent = text;
      hintEl.hidden = false;
    } else {
      hintEl.hidden = true;
    }
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
    return state.places.filter(function (place) {
      if (state.activeSubs.size) {
        if (!state.activeSubs.has(place.category_id)) return false;
      } else if (state.activeTop.size) {
        var cat = categoryById(place.category_id);
        var topId = cat ? cat.parent_id || cat.id : null;
        if (!topId || !state.activeTop.has(topId)) return false;
      }
      if (state.activeTags.size) {
        var placeTags = String(place.tags || "")
          .split(",")
          .map(function (tag) {
            return tag.trim();
          })
          .filter(Boolean);
        var matched = true;
        state.activeTags.forEach(function (tag) {
          if (placeTags.indexOf(tag) < 0) matched = false;
        });
        if (!matched) return false;
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

  function categoryCounts() {
    var counts = {};
    state.places.forEach(function (place) {
      if (place.category_id) counts[place.category_id] = (counts[place.category_id] || 0) + 1;
    });
    return counts;
  }

  function renderChips() {
    var box = $("mapCategories");
    if (!box) return;
    var counts = categoryCounts();
    var total = state.places.length;
    var html =
      '<button type="button" class="mp-chip' +
      (state.activeTop.size === 0 ? " is-on" : "") +
      '" data-top="all">' +
      '<span class="mp-chip-num">全部</span><span class="mp-chip-num">' +
      total +
      "</span></button>";
    topCategories().forEach(function (cat) {
      var count = counts[cat.id] || 0;
      childCategories(cat.id).forEach(function (child) {
        count += counts[child.id] || 0;
      });
      html +=
        '<button type="button" class="mp-chip' +
        (state.activeTop.has(cat.id) ? " is-on" : "") +
        '" data-top="' +
        cat.id +
        '" style="--chip-color:' +
        esc(cat.color) +
        '">' +
        '<span class="mp-chip-dot">' +
        esc(cat.glyph || "·") +
        "</span><span>" +
        esc(cat.name) +
        '</span><span class="mp-chip-num">' +
        count +
        "</span></button>";
    });
    box.innerHTML = html;
  }

  function renderSubcats() {
    var box = $("mapSubcats");
    if (!box) return;
    var subs = [];
    topCategories().forEach(function (cat) {
      if (!state.activeTop.has(cat.id)) return;
      subs = subs.concat(childCategories(cat.id));
    });
    if (!subs.length) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    var counts = categoryCounts();
    box.hidden = false;
    box.innerHTML = subs
      .map(function (cat) {
        return (
          '<button type="button" class="mp-chip' +
          (state.activeSubs.has(cat.id) ? " is-on" : "") +
          '" data-sub="' +
          cat.id +
          '" style="--chip-color:' +
          esc(cat.color) +
          '"><span class="mp-chip-dot">' +
          esc(cat.glyph || "·") +
          "</span><span>" +
          esc(cat.name) +
          '</span><span class="mp-chip-num">' +
          (counts[cat.id] || 0) +
          "</span></button>"
        );
      })
      .join("");
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

  function renderTags() {
    var box = $("mapTags");
    if (!box) return;
    var counts = {};
    state.places.forEach(function (place) {
      String(place.tags || "")
        .split(",")
        .forEach(function (tag) {
          tag = tag.trim();
          if (tag) counts[tag] = (counts[tag] || 0) + 1;
        });
    });
    var tags = Object.keys(counts)
      .sort(function (a, b) {
        return counts[b] - counts[a] || a.localeCompare(b, "zh-CN");
      })
      .slice(0, 24);
    if (!tags.length) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.innerHTML = tags
      .map(function (tag) {
        return (
          '<button type="button" class="mp-tag-chip' +
          (state.activeTags.has(tag) ? " is-on" : "") +
          '" data-tag="' +
          esc(tag) +
          '">#' +
          esc(tag) +
          "<em>" +
          counts[tag] +
          "</em></button>"
        );
      })
      .join("");
  }

  function popupHtml(place) {
    var cat = categoryById(place.category_id);
    var color = placeColor(place);
    var gcj = Geo.toGcj(place.lat, place.lng);
    var bd = Geo.gcjToBd(gcj[0], gcj[1]);
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
    if (place.created_by_name) {
      html += '<p class="mp-popup-by">添加者：' + esc(place.created_by_name) + "</p>";
    }
    html += '<div class="mp-popup-actions">';
    html +=
      '<a class="mp-link-btn" target="_blank" rel="noopener" href="https://uri.amap.com/marker?position=' +
      gcj[1].toFixed(6) +
      "," +
      gcj[0].toFixed(6) +
      "&name=" +
      encodeURIComponent(place.name) +
      '">高德导航</a>';
    html +=
      '<a class="mp-link-btn" target="_blank" rel="noopener" href="https://api.map.baidu.com/marker?location=' +
      bd[0].toFixed(6) +
      "," +
      bd[1].toFixed(6) +
      "&title=" +
      encodeURIComponent(place.name) +
      "&content=" +
      encodeURIComponent(place.name) +
      "&output=html&src=webapp.errorjiang.map" +
      '">百度地图</a>';
    if (place.can_edit) {
      html +=
        '<span class="mp-spacer"></span><button type="button" class="mp-link-btn" data-mp-action="edit" data-mp-id="' +
        place.id +
        '">编辑</button>';
      html +=
        '<button type="button" class="mp-link-btn is-danger" data-mp-action="delete" data-mp-id="' +
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
      className: "mp-marker",
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
    renderChips();
    renderSubcats();
    renderTags();
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
      state.canManage = Boolean(data.can_manage);
      state.canAdd = Boolean(data.can_add);
      state.signedIn = Boolean(data.signed_in);
      state.canImport = Boolean(data.can_import);
      state.canExport = Boolean(data.can_export);
      state.canManageCategories = Boolean(data.can_manage_categories);
      var addBtn = $("mapAddBtn");
      var catsBtn = $("mapCatsBtn");
      var importBtn = $("mapImportBtn");
      var exportLink = $("mapExportLink");
      if (addBtn) addBtn.hidden = !state.canAdd;
      if (catsBtn) catsBtn.hidden = !state.canManageCategories;
      if (importBtn) importBtn.hidden = !state.canImport;
      if (exportLink) exportLink.hidden = !state.canExport;
      var categoryIds = {};
      state.categories.forEach(function (cat) {
        categoryIds[cat.id] = cat;
      });
      state.activeTop.forEach(function (id) {
        if (!categoryIds[id]) state.activeTop.delete(id);
      });
      state.activeSubs.forEach(function (id) {
        var cat = categoryIds[id];
        if (!cat || !cat.parent_id || !state.activeTop.has(cat.parent_id)) {
          state.activeSubs.delete(id);
        }
      });
      var availableTags = {};
      state.places.forEach(function (place) {
        String(place.tags || "")
          .split(",")
          .forEach(function (tag) {
            tag = tag.trim();
            if (tag) availableTags[tag] = true;
          });
      });
      state.activeTags.forEach(function (tag) {
        if (!availableTags[tag]) state.activeTags.delete(tag);
      });
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

  function clearPoiSearch() {
    state.poiResults = [];
    var input = $("placePoiSearch");
    if (input) input.value = "";
    var list = $("placePoiResults");
    if (list) {
      list.innerHTML = "";
      list.hidden = true;
    }
    var hint = $("placePoiHint");
    if (hint) {
      hint.textContent = "";
      hint.hidden = true;
    }
  }

  function showPoiMessage(text) {
    var hint = $("placePoiHint");
    if (!hint) return;
    hint.textContent = text;
    hint.hidden = false;
  }

  function renderPoiResults(data) {
    var list = $("placePoiResults");
    if (!list) return;
    var pois = (data && data.pois) || [];
    state.poiResults = pois;
    list.innerHTML = "";
    if (!pois.length) {
      list.hidden = true;
      showPoiMessage("没有搜到匹配的地点，换个关键词试试。");
      return;
    }
    pois.forEach(function (poi, index) {
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
    list.hidden = false;
  }

  function searchPoi() {
    var input = $("placePoiSearch");
    if (!input) return;
    var keywords = input.value.trim();
    if (!keywords) {
      showPoiMessage("请输入要搜索的地点名称。");
      return;
    }
    var button = $("placePoiSearchBtn");
    if (button) button.disabled = true;
    showPoiMessage("正在搜索高德地图…");
    var list = $("placePoiResults");
    if (list) {
      list.hidden = true;
      list.innerHTML = "";
    }
    api("/api/map/poi-search?keywords=" + encodeURIComponent(keywords))
      .then(function (data) {
        var hint = $("placePoiHint");
        if (hint) hint.hidden = true;
        renderPoiResults(data);
      })
      .catch(function (err) {
        showPoiMessage(err.message);
      })
      .then(function () {
        if (button) button.disabled = false;
      });
  }

  function applyPoi(index) {
    var poi = state.poiResults[index];
    if (!poi) return;
    var wgs = Geo.fromGcj(poi.lat, poi.lng);
    $("placeName").value = poi.name || "";
    if (poi.address) $("placeAddress").value = poi.address;
    $("placeLat").value = wgs[0].toFixed(6);
    $("placeLng").value = wgs[1].toFixed(6);
    var list = $("placePoiResults");
    if (list) list.hidden = true;
    showPoiMessage(
      "已选择：" + (poi.name || "地点") + "，可以继续补充分类和备注。"
    );
  }

  function openPlaceModal(place, coords) {
    state.photoFiles.forEach(function (_file, index) {
      if (state.photoUrls[index]) URL.revokeObjectURL(state.photoUrls[index]);
    });
    state.photoFiles = [];
    state.photoUrls = [];
    state.editingId = place ? place.id : null;
    state.status = place ? place.status || "" : "";
    state.rating = place && place.rating ? Number(place.rating) : 0;
    $("mapPlaceTitle").textContent = place ? "编辑标记" : "添加标记";
    $("placeName").value = place ? place.name : "";
    $("placeSubtitle").value = place ? place.subtitle || "" : "";
    $("placeAddress").value = place ? place.address || "" : "";
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
    clearPoiSearch();
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
          toast("已删除");
          return loadData(false);
        })
        .catch(function (err) {
          toast(err.message);
        });
    });
  }

  // ---------- category manager ----------
  function categoryRowHtml(cat, isChild) {
    return (
      '<div class="mp-cat-row' +
      (isChild ? " is-child" : "") +
      '" data-cat-row="' +
      cat.id +
      '">' +
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
      html += '<div class="mp-cat-group">' + categoryRowHtml(top, false);
      childCategories(top.id).forEach(function (child) {
        html += categoryRowHtml(child, true);
      });
      html +=
        '<button type="button" class="mp-cat-addchild" data-add-child="' +
        top.id +
        '">+ 添加「' +
        esc(top.name) +
        "」的下级分类</button></div>";
    });
    box.innerHTML = html;
    if (window.lucide && lucide.createIcons) lucide.createIcons();
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
      .then(function () {
        toast("已添加下级分类，改好后点对勾保存");
        return loadData(false).then(function () {
          renderCatRows();
          var rows = document.querySelectorAll(".mp-cat-row.is-child");
          var last = rows[rows.length - 1];
          if (last) {
            var input = last.querySelector(".mp-cat-name");
            if (input) {
              input.focus();
            }
          }
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
            state.activeTop.delete(id);
            state.activeSubs.delete(id);
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

  // ---------- placing ----------
  function startPlacing() {
    if (!state.canManage) return;
    state.placing = true;
    map.getContainer().style.cursor = "crosshair";
    setHint("点击地图选择位置，按 Esc 取消");
  }

  function stopPlacing() {
    state.placing = false;
    map.getContainer().style.cursor = "";
    setHint("");
  }

  map.on("click", function (event) {
    if (!state.placing) return;
    stopPlacing();
    var wgs = dataLatLng(event.latlng.lat, event.latlng.lng);
    openPlaceModal(null, wgs);
  });

  // ---------- events ----------
  var chips = $("mapCategories");
  if (chips) {
    chips.addEventListener("click", function (event) {
      var chip = event.target.closest(".mp-chip");
      if (!chip) return;
      var value = chip.getAttribute("data-top");
      if (value === "all") {
        state.activeTop.clear();
        state.activeSubs.clear();
      } else {
        var id = Number(value);
        if (state.activeTop.has(id)) {
          state.activeTop.delete(id);
          state.activeSubs.forEach(function (subId) {
            var sub = categoryById(subId);
            if (sub && sub.parent_id === id) state.activeSubs.delete(subId);
          });
        } else {
          state.activeTop.add(id);
        }
      }
      renderAll();
    });
  }

  var subcatsBox = $("mapSubcats");
  if (subcatsBox) {
    subcatsBox.addEventListener("click", function (event) {
      var chip = event.target.closest("[data-sub]");
      if (!chip) return;
      var id = Number(chip.getAttribute("data-sub"));
      if (state.activeSubs.has(id)) state.activeSubs.delete(id);
      else state.activeSubs.add(id);
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

  var tagsBox = $("mapTags");
  if (tagsBox) {
    tagsBox.addEventListener("click", function (event) {
      var chip = event.target.closest(".mp-tag-chip");
      if (!chip) return;
      var tag = chip.getAttribute("data-tag");
      if (state.activeTags.has(tag)) state.activeTags.delete(tag);
      else state.activeTags.add(tag);
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
      var room = Math.max(0, 9 - existing - state.photoFiles.length);
      var files = Array.prototype.slice.call(photoInput.files || []);
      files.slice(0, room).forEach(function (file) {
        if (file.size > 8 * 1024 * 1024) {
          toast(file.name + " 超过 8MB，已跳过");
          return;
        }
        state.photoFiles.push(file);
        state.photoUrls.push(URL.createObjectURL(file));
      });
      if (files.length > room) toast("每个标记最多 9 张照片");
      photoInput.value = "";
      renderPhotoEditor(place);
    });
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

  var addBtn = $("mapAddBtn");
  if (addBtn) {
    addBtn.addEventListener("click", function () {
      closeSidebar();
      startPlacing();
    });
  }

  var catsBtn = $("mapCatsBtn");
  if (catsBtn) {
    catsBtn.addEventListener("click", function () {
      renderCatRows();
      openModal("mapCatsModal");
    });
  }

  var importBtn = $("mapImportBtn");
  if (importBtn) {
    importBtn.addEventListener("click", function () {
      var errorEl = $("mapImportError");
      if (errorEl) errorEl.hidden = true;
      fillImportCategorySelect();
      openModal("mapImportModal");
    });
  }

  var catRows = $("mapCatRows");
  if (catRows) {
    catRows.addEventListener("click", function (event) {
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
  }

  var catAdd = $("mapCatAdd");
  if (catAdd) {
    catAdd.addEventListener("click", function () {
      api("/api/map/categories", {
        method: "POST",
        body: JSON.stringify({ name: "新分类", glyph: "新", color: "#7b68ee" })
      })
        .then(function () {
          toast("已新增分类，改好后点对勾保存");
          return loadData(false).then(function () {
            renderCatRows();
            var rows = document.querySelectorAll(".mp-cat-row");
            var last = rows[rows.length - 1];
            if (last) last.querySelector(".mp-cat-name").focus();
          });
        })
        .catch(function (err) {
          toast(err.message);
        });
    });
  }

  var placeForm = $("mapPlaceForm");
  if (placeForm) placeForm.addEventListener("submit", submitPlace);

  var poiBtn = $("placePoiSearchBtn");
  if (poiBtn) poiBtn.addEventListener("click", searchPoi);

  var poiInput = $("placePoiSearch");
  if (poiInput) {
    poiInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        searchPoi();
      }
    });
  }

  var poiList = $("placePoiResults");
  if (poiList) {
    poiList.addEventListener("click", function (event) {
      var button = event.target.closest("[data-poi-index]");
      if (!button) return;
      applyPoi(Number(button.getAttribute("data-poi-index")));
    });
  }

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

  var sidebarToggle = $("mapSidebarToggle");
  function openSidebar() {
    var sidebar = $("mapSidebar");
    if (sidebar) sidebar.classList.add("is-open");
  }
  function closeSidebar() {
    var sidebar = $("mapSidebar");
    if (sidebar) sidebar.classList.remove("is-open");
  }
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", openSidebar);
  }
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
      resolveConfirm(false);
      openBasePanel(false);
      closeSidebar();
    }
  });

  if (window.lucide && lucide.createIcons) lucide.createIcons();

  loadData(true).catch(function (err) {
    toast(err.message || "地图数据加载失败");
  });
})();
