(function () {
  var panel = document.getElementById("activityPanel");
  var alertsBox = document.getElementById("activityAlerts");
  var feed = document.getElementById("activityFeed");
  var track = document.getElementById("activityFeedTrack");
  if (!panel || !alertsBox || !feed || !track) return;

  var lastPayloadKey = "";

  function formatTime(value) {
    var text = String(value || "");
    return text.length >= 16 ? text.slice(5, 16) : "现在";
  }

  function buildItem(item) {
    var row = document.createElement("div");
    row.className = "activity-feed-item" + (item.alert ? " is-alert" : "");

    var time = document.createElement("span");
    time.className = "activity-feed-time";
    time.textContent = formatTime(item.created_at);

    var actor = document.createElement("span");
    actor.className = "activity-feed-user";
    actor.textContent = item.actor || "普通用户";

    var text = document.createElement("span");
    text.className = "activity-feed-text";
    text.textContent = item.text || "";

    row.append(time, actor, text);
    return row;
  }

  function render(items) {
    var alerts = [];
    var logs = [];
    items.forEach(function (item) {
      if (item.alert) alerts.push(item);
      else if (logs.length < 9) logs.push(item);
    });

    alertsBox.textContent = "";
    alerts.forEach(function (item) {
      alertsBox.appendChild(buildItem(item));
    });
    alertsBox.hidden = alerts.length === 0;

    track.textContent = "";
    logs.forEach(function (item) {
      track.appendChild(buildItem(item));
    });
    feed.hidden = logs.length === 0;
    panel.hidden = alerts.length === 0 && logs.length === 0;
  }

  function load() {
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
        render(items);
      })
      .catch(function () {});
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) load();
  });
  window.addEventListener("errorauthchange", load);

  load();
  setInterval(load, 10000);
})();
