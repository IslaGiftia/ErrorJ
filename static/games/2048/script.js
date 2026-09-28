(function () {
  "use strict";

  var SIZE = 4;
  var BEST_KEY = "error2048Best";

  var board = document.getElementById("board");
  var scoreEl = document.getElementById("score");
  var bestEl = document.getElementById("best");
  var overlay = document.getElementById("overlay");
  var overlayTitle = document.getElementById("overlayTitle");
  var overlayText = document.getElementById("overlayText");
  var overlayPrimary = document.getElementById("overlayPrimary");
  var overlaySecondary = document.getElementById("overlaySecondary");

  var cells = [];
  var score = 0;
  var best = Number(localStorage.getItem(BEST_KEY) || 0) || 0;
  var won = false;
  var finished = false;
  var freshIndexes = [];
  var mergedIndexes = [];

  function emptyGrid() {
    var grid = [];
    for (var i = 0; i < SIZE * SIZE; i += 1) grid.push(0);
    return grid;
  }

  function render() {
    board.innerHTML = "";
    cells.forEach(function (value, index) {
      var tile = document.createElement("div");
      tile.className = "tile";
      if (value) {
        tile.dataset.value = String(value);
        tile.textContent = String(value);
        if (freshIndexes.indexOf(index) >= 0) tile.classList.add("is-new");
        if (mergedIndexes.indexOf(index) >= 0) tile.classList.add("is-merged");
      }
      board.appendChild(tile);
    });
    scoreEl.textContent = String(score);
    bestEl.textContent = String(best);
  }

  function availableIndexes() {
    var list = [];
    cells.forEach(function (value, index) {
      if (!value) list.push(index);
    });
    return list;
  }

  function addRandomTile() {
    var free = availableIndexes();
    if (!free.length) return -1;
    var index = free[Math.floor(Math.random() * free.length)];
    cells[index] = Math.random() < 0.9 ? 2 : 4;
    return index;
  }

  function newGame() {
    cells = emptyGrid();
    score = 0;
    won = false;
    finished = false;
    freshIndexes = [];
    mergedIndexes = [];
    freshIndexes.push(addRandomTile());
    freshIndexes.push(addRandomTile());
    overlay.hidden = true;
    render();
  }

  function lineIndexes(direction) {
    var lines = [];
    for (var i = 0; i < SIZE; i += 1) {
      var line = [];
      for (var j = 0; j < SIZE; j += 1) {
        if (direction === "left") line.push(i * SIZE + j);
        if (direction === "right") line.push(i * SIZE + (SIZE - 1 - j));
        if (direction === "up") line.push(j * SIZE + i);
        if (direction === "down") line.push((SIZE - 1 - j) * SIZE + i);
      }
      lines.push(line);
    }
    return lines;
  }

  function move(direction) {
    if (finished) return;
    var moved = false;
    var gained = 0;
    mergedIndexes = [];
    var lines = lineIndexes(direction);

    lines.forEach(function (line) {
      var compact = [];
      line.forEach(function (index) {
        if (cells[index]) compact.push(cells[index]);
      });
      var result = [];
      var mergedFlags = [];
      for (var i = 0; i < compact.length; i += 1) {
        if (i + 1 < compact.length && compact[i] === compact[i + 1]) {
          var merged = compact[i] * 2;
          result.push(merged);
          mergedFlags.push(true);
          gained += merged;
          if (merged === 2048) won = true;
          i += 1;
        } else {
          result.push(compact[i]);
          mergedFlags.push(false);
        }
      }
      while (result.length < SIZE) {
        result.push(0);
        mergedFlags.push(false);
      }

      line.forEach(function (index, position) {
        var next = result[position] || 0;
        if (cells[index] !== next) moved = true;
        cells[index] = next;
        if (next && mergedFlags[position]) mergedIndexes.push(index);
      });
    });

    if (!moved) return;
    score += gained;
    if (score > best) {
      best = score;
      try {
        localStorage.setItem(BEST_KEY, String(best));
      } catch (err) {}
    }
    freshIndexes = [addRandomTile()];
    render();
    if (won) {
      showOverlay("达成 2048！", "当前得分 " + score + "，可以继续冲更高分。", "继续挑战", "重开一局", function () {
        overlay.hidden = true;
      }, newGame);
      won = false;
      return;
    }
    if (isStuck()) {
      finished = true;
      showOverlay("没有可移动的了", "本局得分 " + score + "，最高分 " + best + "。", "再来一局", "", newGame, null);
    }
  }

  function isStuck() {
    if (availableIndexes().length) return false;
    for (var row = 0; row < SIZE; row += 1) {
      for (var col = 0; col < SIZE; col += 1) {
        var value = cells[row * SIZE + col];
        if (col + 1 < SIZE && cells[row * SIZE + col + 1] === value) return false;
        if (row + 1 < SIZE && cells[(row + 1) * SIZE + col] === value) return false;
      }
    }
    return true;
  }

  function showOverlay(title, text, primaryText, secondaryText, onPrimary, onSecondary) {
    overlayTitle.textContent = title;
    overlayText.textContent = text;
    overlayPrimary.textContent = primaryText;
    overlayPrimary.onclick = onPrimary;
    if (secondaryText) {
      overlaySecondary.hidden = false;
      overlaySecondary.textContent = secondaryText;
      overlaySecondary.onclick = onSecondary;
    } else {
      overlaySecondary.hidden = true;
    }
    overlay.hidden = false;
  }

  document.addEventListener("keydown", function (event) {
    var key = event.key;
    var map = {
      ArrowLeft: "left",
      ArrowRight: "right",
      ArrowUp: "up",
      ArrowDown: "down",
      a: "left",
      d: "right",
      w: "up",
      s: "down",
      A: "left",
      D: "right",
      W: "up",
      S: "down",
    };
    var direction = map[key];
    if (!direction) return;
    event.preventDefault();
    move(direction);
  });

  var touchStart = null;
  board.addEventListener(
    "touchstart",
    function (event) {
      var touch = event.touches[0];
      touchStart = { x: touch.clientX, y: touch.clientY };
    },
    { passive: true }
  );

  board.addEventListener(
    "touchend",
    function (event) {
      if (!touchStart) return;
      var touch = event.changedTouches[0];
      var dx = touch.clientX - touchStart.x;
      var dy = touch.clientY - touchStart.y;
      touchStart = null;
      if (Math.abs(dx) < 24 && Math.abs(dy) < 24) return;
      if (Math.abs(dx) > Math.abs(dy)) move(dx > 0 ? "right" : "left");
      else move(dy > 0 ? "down" : "up");
    },
    { passive: true }
  );

  document.getElementById("newGameBtn").addEventListener("click", newGame);

  if (window.lucide) window.lucide.createIcons();
  newGame();
})();
