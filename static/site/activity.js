(function () {
  var feed = document.getElementById("activityFeed");
  var track = document.getElementById("activityFeedTrack");
  if (!feed || !track) return;

  var paused = false;
  var lastStep = 0;
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
    track.textContent = "";
    if (!items.length) {
      feed.hidden = true;
      return;
    }
    items.forEach(function (item) {
      track.appendChild(buildItem(item));
    });
    feed.hidden = false;
    feed.scrollTop = 0;
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

  function step(now) {
    if (!paused && !feed.hidden && track.scrollHeight > feed.clientHeight) {
      if (now - lastStep > 50) {
        feed.scrollTop += 1;
        if (feed.scrollTop >= track.scrollHeight - feed.clientHeight) {
          feed.scrollTop = 0;
        }
        lastStep = now;
      }
    }
    requestAnimationFrame(step);
  }

  feed.addEventListener("mouseenter", function () {
    paused = true;
  });
  feed.addEventListener("mouseleave", function () {
    paused = false;
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) load();
  });
  window.addEventListener("errorauthchange", load);

  load();
  setInterval(load, 20000);
  requestAnimationFrame(step);
})();
