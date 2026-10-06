/*
 * 首页左下角地图入口上方的「游戏风」信息面板：
 * PING（/api/health 往返）、FPS、标记总数（来自 minimap.js 的统计事件）、
 * 新留言数（复用留言未读逻辑）。
 */
(function () {
  var hud = document.getElementById("dockHud");
  if (!hud) return;
  var pingEl = document.getElementById("hudPing");
  var fpsEl = document.getElementById("hudFps");
  var placesEl = document.getElementById("hudPlaces");
  var messagesEl = document.getElementById("hudMessages");
  var seenKey = "errorMessagesSeen";

  function setValue(node, text, level) {
    if (!node) return;
    node.textContent = text;
    if (level) {
      node.setAttribute("data-level", level);
    } else {
      node.removeAttribute("data-level");
    }
  }

  // ---- PING ----
  function measurePing() {
    var started = performance.now();
    fetch("/api/health", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("bad status");
        return response.json().catch(function () {
          return null;
        });
      })
      .then(function () {
        var ms = Math.round(performance.now() - started);
        setValue(pingEl, ms + "ms", ms < 100 ? "good" : ms < 300 ? "warn" : "bad");
      })
      .catch(function () {
        setValue(pingEl, "断线", "bad");
      });
  }

  measurePing();
  setInterval(measurePing, 10000);

  // ---- FPS ----
  var frames = 0;
  var lastFrame = performance.now();
  function tick(now) {
    frames += 1;
    if (now - lastFrame >= 1000) {
      var fps = Math.round((frames * 1000) / (now - lastFrame));
      setValue(fpsEl, String(fps), fps >= 50 ? "good" : fps >= 30 ? "warn" : "bad");
      frames = 0;
      lastFrame = now;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  // ---- 标记总数（minimap.js 取完 /api/map 后广播） ----
  window.addEventListener("errordockstats", function (event) {
    var detail = (event && event.detail) || {};
    if (typeof detail.places === "number") {
      setValue(placesEl, String(detail.places));
    }
  });

  // ---- 新留言数 ----
  function loadMessages() {
    var raw = null;
    try {
      raw = localStorage.getItem(seenKey);
    } catch (err) {}
    fetch("/api/site/messages", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : [];
      })
      .then(function (rows) {
        var ids = [];
        var newest = 0;
        (rows || []).forEach(function (row) {
          var id = Number(row.id) || 0;
          ids.push(id);
          if (id > newest) newest = id;
          (row.replies || []).forEach(function (reply) {
            var replyId = Number(reply.id) || 0;
            ids.push(replyId);
            if (replyId > newest) newest = replyId;
          });
        });
        if (raw === null || raw === "") {
          try {
            localStorage.setItem(seenKey, String(newest));
          } catch (err) {}
          setValue(messagesEl, "+0");
          return;
        }
        var seen = Number(raw) || 0;
        var count = ids.filter(function (id) {
          return id > seen;
        }).length;
        setValue(messagesEl, "+" + count, count > 0 ? "warn" : "good");
      })
      .catch(function () {
        setValue(messagesEl, "--", "bad");
      });
  }

  loadMessages();
})();
