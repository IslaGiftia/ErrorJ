(function () {
  var games = {
    "/games/gomoku": "五子棋",
    "/games/2048": "2048",
    "/games/minesweeper": "扫雷",
    "/games/memory": "记忆翻牌",
  };
  var game = games[window.location.pathname];
  if (!game) return;

  var reported = false;
  function report() {
    if (reported || document.hidden) return;
    reported = true;
    fetch("/api/site/game-play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game: game }),
      cache: "no-store",
    }).catch(function () {});
  }

  report();
  document.addEventListener("visibilitychange", report);
})();
