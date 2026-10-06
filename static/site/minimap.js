/*
 * 首页左下角的圆形小地图入口。
 * 规则：显示最近浏览的区域（/map 页面拖动、缩放后回到首页会跟随），
 * 底图固定为浅色高德矢量、暗色 Esri 深色。
 */
(function () {
  var dock = document.getElementById("mapDock");
  var holder = document.getElementById("mapDockMini");
  var countEl = document.getElementById("mapDockCount");
  if (!dock || !holder || typeof L === "undefined") return;

  // ---------- WGS84 -> GCJ02（高德底图下校正标记位置） ----------
  var Geo = (function () {
    var PI = Math.PI;
    var A = 6378245.0;
    var EE = 0.00669342162296594323;

    function outOfChina(lat, lng) {
      return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271;
    }

    function transformLat(x, y) {
      var ret =
        -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
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

    return { toGcj: wgs84ToGcj02 };
  })();

  function amapUrl(style) {
    return (
      "https://web" +
      (style === 6 ? "st" : "rd") +
      "0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=" +
      style +
      "&x={x}&y={y}&z={z}"
    );
  }

  var BASES = {
    amap: {
      id: "amap",
      url: amapUrl(8),
      options: { subdomains: "1234", minZoom: 3, maxZoom: 19, maxNativeZoom: 18 },
      gcj: true
    },
    esriDark: {
      id: "esriDark",
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      options: { minZoom: 3, maxZoom: 16 },
      gcj: false
    }
  };

  var VIEW_KEY = "errorMapView";
  var SEEN_KEY = "errorMapSeenPlaceId";
  var MAX_DOTS = 800;

  function isDarkTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  function themeBase() {
    return isDarkTheme() ? BASES.esriDark : BASES.amap;
  }

  function readSavedView() {
    try {
      var raw = localStorage.getItem(VIEW_KEY);
      if (!raw) return null;
      var view = JSON.parse(raw);
      if (typeof view.lat === "number" && typeof view.lng === "number") return view;
    } catch (err) {}
    return null;
  }

  var savedView = readSavedView();
  var savedZoom = savedView
    ? Math.max(8, Math.min(13, (Number(savedView.zoom) || 12) - 2))
    : 9;

  var mini = L.map(holder, {
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    touchZoom: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    boxZoom: false,
    keyboard: false,
    tap: false,
    minZoom: 3,
    zoomSnap: 0.25,
    fadeAnimation: false
  });

  var currentBase = themeBase();
  var tiles = createTiles(currentBase);
  var dots = L.layerGroup().addTo(mini);
  var places = [];
  var colorById = {};
  var serverSignedIn = false;
  var serverUnseenId = 0;
  var serverUnseenCount = 0;

  mini.setView(
    savedView ? [savedView.lat, savedView.lng] : [34.3416, 108.9398],
    savedZoom
  );

  function createTiles(base) {
    var options = Object.assign({ attribution: "" }, base.options);
    return L.tileLayer(base.url, options).addTo(mini);
  }

  function displayLatLng(lat, lng) {
    return currentBase.gcj ? Geo.toGcj(lat, lng) : [lat, lng];
  }

  function renderDots() {
    dots.clearLayers();
    places.slice(0, MAX_DOTS).forEach(function (place) {
      L.circleMarker(displayLatLng(place.lat, place.lng), {
        radius: 3.2,
        color: "#ffffff",
        weight: 1,
        fillColor: colorById[place.category_id] || "#7b68ee",
        fillOpacity: 1,
        interactive: false
      }).addTo(dots);
    });
  }

  function fitAll() {
    var bounds = L.latLngBounds(
      places.slice(0, MAX_DOTS).map(function (place) {
        return displayLatLng(place.lat, place.lng);
      })
    );
    mini.fitBounds(bounds, { padding: [10, 10], maxZoom: 11 });
  }

  function applyThemeBase() {
    var base = themeBase();
    if (base.id === currentBase.id) return;
    currentBase = base;
    mini.removeLayer(tiles);
    tiles = createTiles(base);
    renderDots();
  }

  function isRecentPlace(createdAt) {
    var text = String(createdAt || "").trim();
    if (!text) return false;
    var time = Date.parse(text.replace(" ", "T"));
    if (isNaN(time)) return false;
    return Date.now() - time <= 24 * 3600 * 1000;
  }

  function updateDockPending() {
    var newestNewId = 0;
    var newCount = 0;
    if (serverSignedIn) {
      // 登录账号：以服务端记录的「已看到标记」为准
      newestNewId = serverUnseenId;
      newCount = serverUnseenCount;
    } else {
      var seen = 0;
      try {
        seen = Number(localStorage.getItem(SEEN_KEY) || 0) || 0;
      } catch (err) {}
      places.forEach(function (place) {
        var id = Number(place.id) || 0;
        var isNew = seen > 0 ? id > seen : isRecentPlace(place.created_at);
        if (!isNew) return;
        newCount += 1;
        if (id > newestNewId) newestNewId = id;
      });
    }
    if (dock) {
      dock.classList.toggle("has-pending", newestNewId > 0);
      dock.href = newestNewId > 0 ? "/map?place=" + newestNewId : "/map";
    }
    window.dispatchEvent(
      new CustomEvent("errordockstats", {
        detail: { places: places.length, newPlaces: newCount }
      })
    );
  }

  new MutationObserver(applyThemeBase).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"]
  });

  fetch("/api/map", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) {
        var error = new Error("map api " + response.status);
        error.status = response.status;
        throw error;
      }
      return response.json();
    })
    .then(function (data) {
      places = data.places || [];
      serverSignedIn = Boolean(data.signed_in);
      serverUnseenId = Number(data.newest_unseen_id) || 0;
      serverUnseenCount = Number(data.unseen_count) || 0;
      colorById = {};
      (data.categories || []).forEach(function (cat) {
        colorById[cat.id] = cat.color || "#7b68ee";
      });
      renderDots();
      if (!savedView && places.length) fitAll();
      updateDockPending();
      if (countEl) {
        if (places.length) {
          countEl.textContent = places.length + " 个标记";
          countEl.hidden = false;
        } else {
          countEl.hidden = true;
        }
      }
      mini.invalidateSize();
    })
    .catch(function (err) {
      if (err && (err.status === 401 || err.status === 403)) {
        dock.hidden = true;
      }
      if (countEl) countEl.hidden = true;
    });
})();
