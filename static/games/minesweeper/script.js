(function () {
  "use strict";

  var LEVELS = {
    easy: { rows: 9, cols: 9, mines: 10 },
    medium: { rows: 16, cols: 16, mines: 40 },
    hard: { rows: 16, cols: 30, mines: 99 },
  };

  var boardEl = document.getElementById("board");
  var mineCountEl = document.getElementById("mineCount");
  var timerEl = document.getElementById("timer");
  var overlay = document.getElementById("overlay");
  var overlayTitle = document.getElementById("overlayTitle");
  var overlayText = document.getElementById("overlayText");
  var overlayPrimary = document.getElementById("overlayPrimary");

  var level = "easy";
  var config = LEVELS[level];
  var cells = [];
  var started = false;
  var finished = false;
  var minesPlaced = false;
  var flags = 0;
  var opened = 0;
  var seconds = 0;
  var timerId = null;
  var longPressTimer = null;
  var longPressFired = false;

  function index(row, col) {
    return row * config.cols + col;
  }

  function neighbors(row, col) {
    var list = [];
    for (var dr = -1; dr <= 1; dr += 1) {
      for (var dc = -1; dc <= 1; dc += 1) {
        if (!dr && !dc) continue;
        var r = row + dr;
        var c = col + dc;
        if (r >= 0 && r < config.rows && c >= 0 && c < config.cols) list.push([r, c]);
      }
    }
    return list;
  }

  function newGame() {
    config = LEVELS[level];
    cells = [];
    for (var i = 0; i < config.rows * config.cols; i += 1) {
      cells.push({ mine: false, open: false, flag: false, count: 0, boom: false, wrong: false });
    }
    started = false;
    finished = false;
    minesPlaced = false;
    flags = 0;
    opened = 0;
    seconds = 0;
    clearInterval(timerId);
    timerId = null;
    timerEl.textContent = "0";
    mineCountEl.textContent = String(config.mines);
    overlay.hidden = true;
    sizeBoard();
    render();
  }

  function sizeBoard() {
    var wrapWidth = Math.min(window.innerWidth - 40, 900);
    var size = Math.floor((wrapWidth - 20) / config.cols) - 2;
    size = Math.max(20, Math.min(34, size));
    boardEl.style.setProperty("--cell-size", size + "px");
    boardEl.style.gridTemplateColumns = "repeat(" + config.cols + ", var(--cell-size))";
  }

  function startTimer() {
    if (timerId) return;
    timerId = window.setInterval(function () {
      seconds += 1;
      timerEl.textContent = String(seconds);
    }, 1000);
  }

  function placeMines(safeRow, safeCol) {
    var safe = {};
    safe[index(safeRow, safeCol)] = true;
    neighbors(safeRow, safeCol).forEach(function (pair) {
      safe[index(pair[0], pair[1])] = true;
    });
    var candidates = [];
    cells.forEach(function (_cell, i) {
      if (!safe[i]) candidates.push(i);
    });
    // 安全区太大时（小棋盘）允许把邻居也算进去
    if (candidates.length < config.mines) {
      candidates = [];
      cells.forEach(function (_cell, i) {
        if (i !== index(safeRow, safeCol)) candidates.push(i);
      });
    }
    for (var placed = 0; placed < config.mines && candidates.length; placed += 1) {
      var pick = Math.floor(Math.random() * candidates.length);
      cells[candidates[pick]].mine = true;
      candidates.splice(pick, 1);
    }
    cells.forEach(function (cell, i) {
      if (cell.mine) return;
      var row = Math.floor(i / config.cols);
      var col = i % config.cols;
      cell.count = neighbors(row, col).filter(function (pair) {
        return cells[index(pair[0], pair[1])].mine;
      }).length;
    });
    minesPlaced = true;
  }

  function openCell(row, col) {
    if (finished) return;
    var cell = cells[index(row, col)];
    if (cell.open || cell.flag) return;
    if (!minesPlaced) placeMines(row, col);
    started = true;
    startTimer();
    reveal(row, col);
    render();
    checkState(row, col);
  }

  function reveal(row, col) {
    var cell = cells[index(row, col)];
    if (cell.open || cell.flag) return;
    cell.open = true;
    opened += 1;
    if (cell.mine) {
      cell.boom = true;
      return;
    }
    if (cell.count === 0) {
      neighbors(row, col).forEach(function (pair) {
        var next = cells[index(pair[0], pair[1])];
        if (!next.open && !next.flag && !next.mine) reveal(pair[0], pair[1]);
      });
    }
  }

  function toggleFlag(row, col) {
    if (finished) return;
    var cell = cells[index(row, col)];
    if (cell.open) return;
    cell.flag = !cell.flag;
    flags += cell.flag ? 1 : -1;
    mineCountEl.textContent = String(Math.max(0, config.mines - flags));
    render();
  }

  function checkState(row, col) {
    var cell = cells[index(row, col)];
    if (cell.mine) {
      finished = true;
      clearInterval(timerId);
      cells.forEach(function (item) {
        if (item.mine) item.open = true;
        if (item.flag && !item.mine) item.wrong = true;
      });
      render();
      showOverlay("踩到雷了", "用时 " + seconds + " 秒，再来一局试试。", "再来一局");
      return;
    }
    if (opened === config.rows * config.cols - config.mines) {
      finished = true;
      clearInterval(timerId);
      cells.forEach(function (item) {
        if (item.mine) item.flag = true;
      });
      mineCountEl.textContent = "0";
      render();
      showOverlay("全部排完！", "用时 " + seconds + " 秒，难度：" + levelName() + "。", "再来一局");
    }
  }

  function levelName() {
    return { easy: "初级", medium: "中级", hard: "高级" }[level];
  }

  function showOverlay(title, text, buttonText) {
    overlayTitle.textContent = title;
    overlayText.textContent = text;
    overlayPrimary.textContent = buttonText;
    overlayPrimary.onclick = newGame;
    overlay.hidden = false;
  }

  function render() {
    boardEl.innerHTML = "";
    var fragment = document.createDocumentFragment();
    cells.forEach(function (cell, i) {
      var row = Math.floor(i / config.cols);
      var col = i % config.cols;
      var node = document.createElement("button");
      node.type = "button";
      node.className = "mine-cell";
      if (cell.open) node.classList.add("is-open");
      if (cell.flag) node.classList.add("is-flag");
      if (cell.mine && cell.open) node.classList.add(cell.boom ? "is-boom" : "is-mine");
      if (cell.wrong) node.classList.add("is-wrong");
      if (cell.open && !cell.mine && cell.count) {
        node.dataset.count = String(cell.count);
        node.textContent = String(cell.count);
      } else if (cell.flag) {
        node.textContent = "⚑";
      } else if (cell.mine && cell.open) {
        node.textContent = "✱";
      } else if (cell.wrong) {
        node.textContent = "✕";
      }
      node.addEventListener("click", function () {
        if (longPressFired) {
          longPressFired = false;
          return;
        }
        openCell(row, col);
      });
      node.addEventListener("contextmenu", function (event) {
        event.preventDefault();
        toggleFlag(row, col);
      });
      node.addEventListener(
        "touchstart",
        function () {
          longPressFired = false;
          longPressTimer = window.setTimeout(function () {
            longPressFired = true;
            toggleFlag(row, col);
          }, 420);
        },
        { passive: true }
      );
      ["touchend", "touchmove", "touchcancel"].forEach(function (name) {
        node.addEventListener(
          name,
          function () {
            clearTimeout(longPressTimer);
          },
          { passive: true }
        );
      });
      fragment.appendChild(node);
    });
    boardEl.appendChild(fragment);
  }

  document.querySelectorAll("#levelBar [data-level]").forEach(function (button) {
    button.addEventListener("click", function () {
      level = button.dataset.level;
      document.querySelectorAll("#levelBar [data-level]").forEach(function (item) {
        item.classList.toggle("is-active", item === button);
      });
      newGame();
    });
  });

  window.addEventListener("resize", function () {
    sizeBoard();
  });

  if (window.lucide) window.lucide.createIcons();
  newGame();
})();
