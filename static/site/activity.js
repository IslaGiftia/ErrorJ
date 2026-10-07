(function () {
  var panel = document.getElementById("activityPanel");
  var feed = document.getElementById("activityFeed");
  var track = document.getElementById("activityFeedTrack");
  if (!panel || !feed || !track) return;

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
    time.textContent = "⌜" + formatTime(item.created_at) + "⌟";

    var actor = document.createElement("span");
    actor.className = "activity-feed-user";
    actor.textContent = item.actor || "普通用户";

    var text = document.createElement("span");
    text.className = "activity-feed-text";
    text.textContent = item.text || "";

    row.append(time, actor, text);
    return row;
  }

  function buildSequence(alerts, logs) {
    if (!alerts.length) return logs.slice(0, 7);
    var sequence = [];
    var alertIndex = 0;
    var logIndex = 0;
    while (sequence.length < 7 && (logIndex < logs.length || alerts.length)) {
      if (sequence.length === 0 || sequence.length % 3 === 0) {
        sequence.push(alerts[alertIndex % alerts.length]);
        alertIndex += 1;
      } else if (logIndex < logs.length) {
        sequence.push(logs[logIndex]);
        logIndex += 1;
      } else {
        sequence.push(alerts[alertIndex % alerts.length]);
        alertIndex += 1;
      }
    }
    return sequence;
  }

  function buildCycle(sequence) {
    var cycle = document.createElement("div");
    cycle.className = "activity-feed-cycle";
    sequence.forEach(function (item) {
      cycle.appendChild(buildItem(item));
    });
    return cycle;
  }

  function render(items) {
    var alerts = [];
    var logs = [];
    items.forEach(function (item) {
      if (item.alert) alerts.push(item);
      else if (logs.length < 7) logs.push(item);
    });
    var sequence = buildSequence(alerts, logs);
    if (!sequence.length) {
      panel.hidden = true;
      return;
    }

    track.textContent = "";
    track.appendChild(buildCycle(sequence));
    track.appendChild(buildCycle(sequence));
    var rolling = sequence.length >= 4;
    track.classList.toggle("is-rolling", rolling);
    track.style.setProperty(
      "--activity-duration",
      Math.max(18, sequence.length * 3.4).toFixed(1) + "s"
    );
    panel.hidden = false;
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
