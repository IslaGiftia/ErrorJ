(function () {
  var panel = document.getElementById("activityPanel");
  var feed = document.getElementById("activityFeed");
  var track = document.getElementById("activityFeedTrack");
  if (!panel || !feed || !track) return;

  var LOG_ITEMS = 9;
  var EXPANDED_ITEMS = 20;
  var lastPayloadKey = "";
  var latestItems = [];
  var isAdmin = false;
  var signedIn = false;
  var manuallyHidden = false;
  var mode = "default";
  var clickTimer = null;
  /*
   * 鼠标跟随：指针附近的行轻微上下错开（行级波浪）+ 字重小幅加重。
   * 行位移用布局偏移（offsetTop）算，不用 getBoundingClientRect，
   * 这样已经位移过的行不会反过来影响下一帧的距离计算（否则会自己抖）。
   */
  var WAVE_RADIUS = 44;
  var WAVE_LIFT = 2.5;
  var WAVE_LEAN = 1.5;
  var WAVE_WEIGHT = 100;
  var RELEASE_MS = 160;
  var BASE_WEIGHT = 400;
  var motionQuery = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;
  var rowMetrics = [];
  var waveFrame = null;
  var releaseAt = 0;
  var pointerInside = false;
  var clientX = 0;
  var clientY = 0;
  var pointerX = 0;
  var pointerY = 0;
  var panelWidth = 0;

  function waveDisabled() {
    return Boolean(motionQuery && motionQuery.matches);
  }

  function measureRows() {
    rowMetrics = Array.prototype.map.call(track.children, function (row) {
      return {
        el: row,
        center: row.offsetTop + row.offsetHeight / 2,
        x: 0,
        y: 0,
        weight: BASE_WEIGHT,
      };
    });
  }

  function clearWave() {
    rowMetrics.forEach(function (metric) {
      metric.x = 0;
      metric.y = 0;
      metric.weight = BASE_WEIGHT;
      metric.el.style.transform = "";
      metric.el.style.fontVariationSettings = "";
    });
  }

  function applyWave(now) {
    waveFrame = null;
    var releasing = releaseAt > 0;
    if (releasing && now - releaseAt >= RELEASE_MS) {
      releaseAt = 0;
      clearWave();
      return;
    }
    var falloff = 1;
    if (releasing) {
      var eased = 1 - Math.pow(1 - Math.min(1, (now - releaseAt) / RELEASE_MS), 3);
      falloff = 1 - eased;
    } else {
      // 每帧只读一次面板位置：跟手阶段不写样式，所以这一次读不会引发布局抖动
      var panelRect = panel.getBoundingClientRect();
      pointerX = clientX - panelRect.left;
      pointerY = clientY - panelRect.top;
      panelWidth = panelRect.width;
    }
    // 展开后列表可以滚动：行的布局偏移不变，视觉位置靠 scrollTop 换算
    var scrolled = feed.scrollTop || 0;
    var lean = panelWidth > 0 ? pointerX / panelWidth - 0.5 : 0;
    rowMetrics.forEach(function (metric) {
      var x = 0;
      var y = 0;
      var weight = BASE_WEIGHT;
      if (releasing) {
        x = metric.x * falloff;
        y = metric.y * falloff;
        weight = BASE_WEIGHT + (metric.weight - BASE_WEIGHT) * falloff;
      } else {
        var distance = Math.abs(pointerY - (metric.center - scrolled));
        if (distance < WAVE_RADIUS) {
          var t = 1 - distance / WAVE_RADIUS;
          var influence = t * t * (3 - 2 * t);
          var up = pointerY >= metric.center - scrolled;
          // 指针上方的行往上让、下方的行往下让，整列像被指针轻轻顶开（不会互相挤到）
          y = (up ? -1 : 1) * influence * WAVE_LIFT;
          // 横向再朝指针那边偏一点，鼠标左右滑也有反应
          x = lean * 2 * influence * WAVE_LEAN;
          weight = BASE_WEIGHT + influence * WAVE_WEIGHT;
        }
      }
      x = Math.round(x * 10) / 10;
      y = Math.round(y * 10) / 10;
      weight = Math.round(weight / 5) * 5;
      if (x === metric.x && y === metric.y && weight === metric.weight) return;
      metric.x = x;
      metric.y = y;
      metric.weight = weight;
      if (!x && !y && weight === BASE_WEIGHT) {
        metric.el.style.transform = "";
        metric.el.style.fontVariationSettings = "";
      } else {
        metric.el.style.transform = "translate3d(" + x + "px," + y + "px,0)";
        metric.el.style.fontVariationSettings = '"wght" ' + weight;
      }
    });
    if (releasing) waveFrame = window.requestAnimationFrame(applyWave);
  }

  function scheduleWave() {
    if (waveFrame === null) waveFrame = window.requestAnimationFrame(applyWave);
  }

  function dropRows() {
    rowMetrics = [];
    releaseAt = 0;
    if (waveFrame !== null) {
      window.cancelAnimationFrame(waveFrame);
      waveFrame = null;
    }
  }

  function onPointerMove(event) {
    if (waveDisabled()) return;
    pointerInside = true;
    clientX = event.clientX;
    clientY = event.clientY;
    releaseAt = 0;
    scheduleWave();
  }

  function onPointerLeave() {
    pointerInside = false;
    if (waveDisabled() || !rowMetrics.length) return;
    releaseAt = window.performance && window.performance.now
      ? window.performance.now()
      : Date.now();
    scheduleWave();
  }

  panel.addEventListener("pointermove", onPointerMove);
  panel.addEventListener("pointerleave", onPointerLeave);
  if (motionQuery && motionQuery.addEventListener) {
    motionQuery.addEventListener("change", function () {
      if (!waveDisabled()) return;
      pointerInside = false;
      releaseAt = 0;
      clearWave();
    });
  }

  function ordered() {
    return latestItems.slice().sort(function (left, right) {
      return String(right.created_at || "").localeCompare(
        String(left.created_at || "")
      );
    });
  }

  // 普通账号：默认只看未读提醒，点开后才显示日志
  function visibleItems() {
    var rows = ordered();
    if (isAdmin) return rows.slice(0, mode === "expanded" ? EXPANDED_ITEMS : LOG_ITEMS);
    if (mode === "default") {
      return rows.filter(function (item) {
        return Boolean(item.alert);
      });
    }
    return rows.slice(0, mode === "expanded" ? EXPANDED_ITEMS : LOG_ITEMS);
  }

  function syncTitle() {
    var expanded = mode !== "default";
    var label;
    if (isAdmin) {
      label = expanded ? "单击收起，双击隐藏" : "单击展开，双击隐藏";
    } else if (mode === "default") {
      label = "单击查看日志，双击展开更多";
    } else if (mode === "log") {
      label = "单击只看新提醒，双击展开更多";
    } else {
      label = "单击只看新提醒，双击收起日志";
    }
    panel.title = label;
    panel.setAttribute("aria-label", "首页动态");
    panel.classList.toggle("is-expanded", expanded);
  }

  function formatTime(value) {
    var text = String(value || "");
    return text.length >= 16 ? text.slice(5, 16) : "现在";
  }

  function buildItem(item) {
    var row = document.createElement("div");
    row.className = "activity-feed-item" + (item.alert ? " is-alert" : "");

    var time = document.createElement("span");
    time.className = "activity-feed-time";
    time.textContent = "「" + formatTime(item.created_at) + "」";

    var actor = document.createElement("span");
    actor.className = "activity-feed-user";
    actor.textContent = item.actor || "普通用户";

    var text = document.createElement("span");
    text.className = "activity-feed-text";
    text.textContent = item.text || "";

    row.append(time, actor, text);
    return row;
  }

  function render() {
    if (!signedIn || manuallyHidden) {
      dropRows();
      panel.hidden = true;
      return;
    }
    var rows = visibleItems();
    if (!rows.length) {
      dropRows();
      panel.hidden = true;
      return;
    }

    track.textContent = "";
    rows.forEach(function (item) {
      track.appendChild(buildItem(item));
    });
    panel.hidden = false;
    syncTitle();
    // 行是重建的，波形数据跟着重测；指针还在面板里就立刻重算一次
    measureRows();
    if (pointerInside) {
      releaseAt = 0;
      scheduleWave();
    }
  }

  function load() {
    if (manuallyHidden || document.hidden) return;
    fetch("/api/site/activity", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : { items: [] };
      })
      .then(function (data) {
        var items = Array.isArray(data.items) ? data.items : null;
        if (!items) return;
        var key = JSON.stringify(items);
        if (key === lastPayloadKey) return;
        lastPayloadKey = key;
        latestItems = items;
        isAdmin = Boolean(data.admin);
        signedIn = data.signed_in !== false;
        render();
        window.dispatchEvent(new CustomEvent("erroractivitychange"));
      })
      .catch(function () {});
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) load();
  });
  window.addEventListener("errorauthchange", load);
  panel.addEventListener("click", function () {
    if (clickTimer) return;
    clickTimer = window.setTimeout(function () {
      clickTimer = null;
      if (isAdmin) {
        mode = mode === "default" ? "expanded" : "default";
      } else {
        mode = mode === "default" ? "log" : "default";
      }
      render();
    }, 220);
  });
  panel.addEventListener("dblclick", function () {
    if (clickTimer) {
      window.clearTimeout(clickTimer);
      clickTimer = null;
    }
    if (isAdmin) {
      manuallyHidden = true;
      panel.hidden = true;
      return;
    }
    mode = mode === "expanded" ? "default" : "expanded";
    render();
  });

  load();
  setInterval(load, 5000);
})();
