(function () {
  "use strict";

  var LEVELS = {
    easy: { cols: 4, rows: 3 },
    normal: { cols: 4, rows: 4 },
    hard: { cols: 4, rows: 5 },
  };

  var FACES = ["⚡", "🔌", "🔋", "📡", "🧲", "🚀", "⭐", "🐞", "❤️", "💡", "🧪", "🛠️"];

  var boardEl = document.getElementById("board");
  var movesEl = document.getElementById("moves");
  var timerEl = document.getElementById("timer");
  var bestHint = document.getElementById("bestHint");
  var overlay = document.getElementById("overlay");
  var overlayTitle = document.getElementById("overlayTitle");
  var overlayText = document.getElementById("overlayText");
  var overlayPrimary = document.getElementById("overlayPrimary");

  var level = "easy";
  var moves = 0;
  var seconds = 0;
  var timerId = null;
  var firstCard = null;
  var secondCard = null;
  var locked = false;
  var matched = 0;
  var totalPairs = 0;

  function bestKey() {
    return "errorMemoryBest:" + level;
  }

  function readBest() {
    try {
      var raw = localStorage.getItem(bestKey());
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function writeBest(value) {
    try {
      localStorage.setItem(bestKey(), JSON.stringify(value));
    } catch (err) {}
  }

  function renderBestHint() {
    var best = readBest();
    bestHint.textContent = best ? "最好成绩：" + best.moves + " 步 / " + best.seconds + " 秒" : "";
  }

  function shuffle(list) {
    for (var i = list.length - 1; i > 0; i -= 1) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = list[i];
      list[i] = list[j];
      list[j] = tmp;
    }
    return list;
  }

  function newGame() {
    var config = LEVELS[level];
    totalPairs = (config.cols * config.rows) / 2;
    moves = 0;
    seconds = 0;
    matched = 0;
    firstCard = null;
    secondCard = null;
    locked = false;
    clearInterval(timerId);
    timerId = null;
    movesEl.textContent = "0";
    timerEl.textContent = "0";
    overlay.hidden = true;
    renderBestHint();

    var faces = shuffle(FACES.slice()).slice(0, totalPairs);
    var deck = shuffle(faces.concat(faces));

    boardEl.innerHTML = "";
    boardEl.style.gridTemplateColumns = "repeat(" + config.cols + ", minmax(0, 1fr))";
    deck.forEach(function (face) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "memory-card";
      card.dataset.face = face;

      var back = document.createElement("span");
      back.className = "memory-face is-back";
      back.textContent = "?";

      var front = document.createElement("span");
      front.className = "memory-face is-front";
      front.textContent = face;

      card.append(back, front);
      card.addEventListener("click", function () {
        flip(card);
      });
      boardEl.appendChild(card);
    });
  }

  function startTimer() {
    if (timerId) return;
    timerId = window.setInterval(function () {
      seconds += 1;
      timerEl.textContent = String(seconds);
    }, 1000);
  }

  function flip(card) {
    if (locked || card.classList.contains("is-flipped") || card.classList.contains("is-matched")) return;
    card.classList.add("is-flipped");
    startTimer();

    if (!firstCard) {
      firstCard = card;
      return;
    }
    secondCard = card;
    moves += 1;
    movesEl.textContent = String(moves);

    if (firstCard.dataset.face === secondCard.dataset.face) {
      firstCard.classList.add("is-matched");
      secondCard.classList.add("is-matched");
      firstCard = null;
      secondCard = null;
      matched += 1;
      if (matched === totalPairs) finish();
      return;
    }

    locked = true;
    var a = firstCard;
    var b = secondCard;
    firstCard = null;
    secondCard = null;
    window.setTimeout(function () {
      a.classList.remove("is-flipped");
      b.classList.remove("is-flipped");
      a.classList.add("is-shake");
      b.classList.add("is-shake");
      window.setTimeout(function () {
        a.classList.remove("is-shake");
        b.classList.remove("is-shake");
      }, 340);
      locked = false;
    }, 700);
  }

  function finish() {
    clearInterval(timerId);
    timerId = null;
    var best = readBest();
    var isBest = !best || moves < best.moves || (moves === best.moves && seconds < best.seconds);
    if (isBest) writeBest({ moves: moves, seconds: seconds });
    renderBestHint();
    overlayTitle.textContent = isBest ? "新纪录！" : "全部配对完成";
    overlayText.textContent = "用了 " + moves + " 步、" + seconds + " 秒。";
    overlayPrimary.textContent = "再来一局";
    overlayPrimary.onclick = newGame;
    overlay.hidden = false;
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

  if (window.lucide) window.lucide.createIcons();
  newGame();
})();
