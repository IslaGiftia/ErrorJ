(function () {
  var feed = document.getElementById("activityFeed");
  var track = document.getElementById("activityFeedTrack");
  if (!feed || !track) return;

  var paused = false;
  var lastStep = 0;
  var lastPayloadKey = "";
  var scrollable = false;
  var maxScroll = 0;
  var rafId = 0;

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
      scrollable = false;
      maxScroll = 0;
      return;
    }
    items.forEach(function (item) {
      track.appendChild(buildItem(item));
    });
    feed.hidden = false;
    feed.scrollTop = 0;
    updateScrollable();
    schedule();
  }

  function updateScrollable() {
    maxScroll = Math.max(0, track.scrollHeight - feed.clientHeight);
    scrollable = !feed.hidden && maxScroll > 0;
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
    rafId = 0;
    if (!paused && scrollable) {
      if (now - lastStep > 50) {
        feed.scrollTop += 1;
        if (feed.scrollTop >= maxScroll) {
          feed.scrollTop = 0;
        }
        lastStep = now;
      }
    }
    if (scrollable) schedule();
  }

  function schedule() {
    if (!rafId && scrollable) {
      rafId = requestAnimationFrame(step);
    }
  }

  feed.addEventListener("mouseenter", function () {
    paused = true;
  });
  feed.addEventListener("mouseleave", function () {
    paused = false;
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      load();
      updateScrollable();
      schedule();
    }
  });
  window.addEventListener("resize", updateScrollable);
  window.addEventListener("errorauthchange", load);

  load();
  setInterval(load, 20000);
})();
