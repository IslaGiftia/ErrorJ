(function () {
  var panel = document.getElementById("activityPanel");
  var feed = document.getElementById("activityFeed");
  var track = document.getElementById("activityFeedTrack");
  if (!panel || !feed || !track) return;

  var VISIBLE_ITEMS = 9;
  var EXPANDED_ITEMS = 20;
  var lastPayloadKey = "";
  var latestItems = [];
  var manuallyHidden = false;
  var expanded = false;
  var clickTimer = null;

  function syncTitle() {
    panel.title = expanded
      ? "单击收起，双击隐藏"
      : "单击展开，双击隐藏";
    panel.setAttribute(
      "aria-label",
      expanded ? "首页动态（已展开）" : "首页动态"
    );
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
    if (manuallyHidden) return;
    var ordered = latestItems
      .slice()
      .sort(function (left, right) {
        return String(right.created_at || "").localeCompare(
          String(left.created_at || "")
        );
      })
      .slice(0, expanded ? EXPANDED_ITEMS : VISIBLE_ITEMS);
    if (!ordered.length) {
      panel.hidden = true;
      return;
    }

    track.textContent = "";
    ordered.forEach(function (item) {
      track.appendChild(buildItem(item));
    });
    panel.hidden = false;
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
        render();
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
      expanded = !expanded;
      syncTitle();
      render();
    }, 220);
  });
  panel.addEventListener("dblclick", function () {
    if (clickTimer) {
      window.clearTimeout(clickTimer);
      clickTimer = null;
    }
    manuallyHidden = true;
    panel.hidden = true;
  });

  syncTitle();
  load();
  setInterval(load, 5000);
})();
