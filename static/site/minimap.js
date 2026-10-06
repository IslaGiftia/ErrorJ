(function () {
  var dock = document.getElementById("mapDock");
  var holder = document.getElementById("mapDockMini");
  var countEl = document.getElementById("mapDockCount");
  if (!dock || !holder || typeof L === "undefined") return;

  var savedView = null;
  try {
    var raw = localStorage.getItem("errorMapView");
    if (raw) {
      var parsed = JSON.parse(raw);
      if (typeof parsed.lat === "number" && typeof parsed.lng === "number") savedView = parsed;
    }
  } catch (err) {}

  function isDark() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  var LIGHT_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  var DARK_TILES =
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";

  function tileUrl() {
    return isDark() ? DARK_TILES : LIGHT_TILES;
  }

  function tileLayer() {
    return L.tileLayer(tileUrl(), { maxZoom: 19, maxNativeZoom: 16, attribution: "" });
  }

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
    zoomSnap: 0.25,
    fadeAnimation: false
  });
  var tiles = tileLayer().addTo(mini);
  mini.setView(
    savedView ? [savedView.lat, savedView.lng] : [34.3416, 108.9398],
    savedView ? Math.max(8, Math.min(13, (Number(savedView.zoom) || 12) - 2)) : 9
  );

  var observer = new MutationObserver(function () {
    tiles.setUrl(tileUrl());
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

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
      var places = data.places || [];
      var colorById = {};
      (data.categories || []).forEach(function (cat) {
        colorById[cat.id] = cat.color || "#7b68ee";
      });
      places.slice(0, 800).forEach(function (place) {
        L.circleMarker([place.lat, place.lng], {
          radius: 3.2,
          color: "#ffffff",
          weight: 1,
          fillColor: colorById[place.category_id] || "#7b68ee",
          fillOpacity: 1,
          interactive: false
        }).addTo(mini);
      });
      if (countEl) {
        if (places.length) {
          countEl.textContent = places.length + " 个标记";
          countEl.hidden = false;
        } else {
          countEl.hidden = true;
        }
      }
      if (!savedView && places.length) {
        var bounds = L.latLngBounds(
          places.slice(0, 800).map(function (place) {
            return [place.lat, place.lng];
          })
        );
        mini.fitBounds(bounds, { padding: [10, 10], maxZoom: 11 });
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
