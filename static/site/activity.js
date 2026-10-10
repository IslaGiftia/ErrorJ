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
      panel.hidden = true;
      return;
    }
    var rows = visibleItems();
    if (!rows.length) {
      panel.hidden = true;
      return;
    }

    track.textContent = "";
    rows.forEach(function (item) {
      track.appendChild(buildItem(item));
    });
    panel.hidden = false;
    syncTitle();
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
