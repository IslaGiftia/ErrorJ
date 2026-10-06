/*
 * 首页地图入口上方的信息面板：只显示 ping 和 fps，单行、全透明，
 * 以地图圆盘的圆心为准水平居中。
 */
(function () {
  var hud = document.getElementById("dockHud");
  if (!hud) return;
  var pingEl = document.getElementById("hudPing");
  var fpsEl = document.getElementById("hudFps");

  function setValue(node, text) {
    if (node) node.textContent = text;
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
        setValue(pingEl, Math.round(performance.now() - started) + "ms");
      })
      .catch(function () {
        setValue(pingEl, "--");
      });
  }

  measurePing();
  setInterval(measurePing, 10000);

  // ---- fps：本地帧率 ----
  var frames = 0;
  var lastFrame = performance.now();
  function tick(now) {
    frames += 1;
    if (now - lastFrame >= 1000) {
      setValue(fpsEl, String(Math.round((frames * 1000) / (now - lastFrame))));
      frames = 0;
      lastFrame = now;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
