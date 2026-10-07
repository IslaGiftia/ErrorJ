/*
 * 首页地图入口上方的信息面板：单行、全透明，以地图圆盘圆心为准水平居中。
 * PING：<100ms 绿、<300ms 黄、更高红；
 * FPS：<=30 红、<=60 绿、更高墨绿。
 */
(function () {
  var hud = document.getElementById("dockHud");
  if (!hud) return;
  var pingEl = document.getElementById("hudPing");
  var fpsEl = document.getElementById("hudFps");

  function setValue(node, text, level) {
    if (!node) return;
    node.textContent = text;
    if (level) {
      node.setAttribute("data-level", level);
    } else {
      node.removeAttribute("data-level");
    }
  }

  // ---- ping：每 10 秒测一次 /api/health 往返 ----
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
        setValue(pingEl, ms + "ms", ms < 100 ? "ok" : ms < 300 ? "warn" : "bad");
      })
      .catch(function () {
        setValue(pingEl, "--", "bad");
      });
  }

  measurePing();
  setInterval(measurePing, 10000);

  // ---- fps：本地帧率 ----
  var frames = 0;
  var lastFrame = performance.now();
  function tick(now) {
    if (document.hidden) {
      frames = 0;
      lastFrame = now;
      requestAnimationFrame(tick);
      return;
    }
    frames += 1;
    if (now - lastFrame >= 1000) {
      var fps = Math.round((frames * 1000) / (now - lastFrame));
      setValue(fpsEl, fps + "F", fps <= 30 ? "bad" : fps <= 60 ? "ok" : "deep");
      frames = 0;
      lastFrame = now;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
