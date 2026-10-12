/*
 * 下载页：三张 Tab 分别装歌曲 / 书籍 / 推荐，内容仍是各自原来的页面（?embed=1 只藏掉品牌条）。
 *
 * - 面板懒加载：第一次切到某个 Tab 才创建 iframe，切回来不重建，所以歌曲切走也不会中断播放。
 * - 角标与呼吸沿用站点通知：/api/site/notifications/summary 里的 music / books / recommendations。
 * - 打开某个 Tab 就算读过这一栏，首页「下载」入口的角标随之减少。
 */
(function () {
  "use strict";

  var TABS = [
    { key: "music", src: "/music?embed=1" },
    { key: "books", src: "/books?embed=1" },
    { key: "recommendations", src: "/recommendations?embed=1" }
  ];
  var TAB_KEYS = TABS.map(function (tab) {
    return tab.key;
  });
  var counts = {};
  var mounted = {};
  var activeKey = "";
  var busy = false;

  function $(id) {
    return document.getElementById(id);
  }

  function tabEl(key) {
    return document.querySelector('.dl-tab[data-tab="' + key + '"]');
  }

  function panelEl(key) {
    return document.querySelector('.dl-panel[data-panel="' + key + '"]');
  }

  function normalizeTab(value) {
    var key = String(value || "").toLowerCase();
    if (key === "music" || key === "song" || key === "songs") return "music";
    if (key === "books" || key === "book") return "books";
    if (key === "recommendations" || key === "recommendation" || key === "picks") {
      return "recommendations";
    }
    return "";
  }

  function mount(key) {
    if (mounted[key]) return;
    var panel = panelEl(key);
    var tab = TABS.filter(function (item) {
      return item.key === key;
    })[0];
    if (!panel || !tab) return;
    var frame = document.createElement("iframe");
    frame.className = "dl-frame";
    frame.setAttribute("title", "下载内容");
    frame.src = tab.src;
    panel.appendChild(frame);
    mounted[key] = true;
  }

  function paintBadges() {
    TABS.forEach(function (tab) {
      var node = tabEl(tab.key);
      if (!node) return;
      var badge = node.querySelector(".dl-tab-badge");
      var count = Number(counts[tab.key]) || 0;
      node.classList.toggle("has-pending", count > 0);
      if (!badge) return;
      badge.hidden = count <= 0;
      badge.textContent = count > 0 ? (count > 99 ? "99+" : String(count)) : "";
    });
  }

  function clearTab(key) {
    counts[key] = 0;
    var node = tabEl(key);
    if (!node) return;
    node.classList.remove("has-pending");
    var badge = node.querySelector(".dl-tab-badge");
    if (badge) {
      badge.hidden = true;
      badge.textContent = "";
    }
  }

  function markSeen(key) {
    clearTab(key);
    fetch("/api/site/notifications/seen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: key }),
      cache: "no-store"
    }).catch(function () {});
  }

  function updateUrl(key) {
    try {
      var url = new URL(location.href);
      url.searchParams.set("tab", key);
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    } catch (err) {}
  }

  function activate(key, options) {
    if (TAB_KEYS.indexOf(key) < 0) key = TAB_KEYS[0];
    activeKey = key;
    TABS.forEach(function (tab) {
      var node = tabEl(tab.key);
      var panel = panelEl(tab.key);
      var on = tab.key === key;
      if (node) {
        node.classList.toggle("is-active", on);
        node.setAttribute("aria-selected", on ? "true" : "false");
      }
      if (panel) panel.hidden = !on;
    });
    mount(key);
    markSeen(key);
    if (!options || !options.keepUrl) updateUrl(key);
  }

  function loadCounts() {
    if (busy) return Promise.resolve();
    busy = true;
    return fetch("/api/site/notifications/summary", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("通知状态加载失败");
        return response.json();
      })
      .then(function (data) {
        counts = {
          music: Number(data.music) || 0,
          books: Number(data.books) || 0,
          recommendations: Number(data.recommendations) || 0
        };
        // 正在看的这一栏已经算读过
        if (activeKey) counts[activeKey] = 0;
        paintBadges();
      })
      .catch(function () {})
      .then(function () {
        busy = false;
      });
  }

  function moveTab(step) {
    var index = TAB_KEYS.indexOf(activeKey);
    if (index < 0) index = 0;
    var next = (index + step + TAB_KEYS.length) % TAB_KEYS.length;
    activate(TAB_KEYS[next]);
    var node = tabEl(TAB_KEYS[next]);
    if (node) node.focus();
  }

  function bind() {
    var nav = $("dlTabs");
    if (nav) {
      nav.addEventListener("click", function (event) {
        var node = event.target.closest(".dl-tab");
        if (!node) return;
        activate(node.getAttribute("data-tab"));
      });
      nav.addEventListener("keydown", function (event) {
        if (event.key === "ArrowRight") {
          event.preventDefault();
          moveTab(1);
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          moveTab(-1);
        }
      });
    }
    window.addEventListener("pageshow", function () {
      loadCounts();
    });
    window.addEventListener("focus", function () {
      loadCounts();
    });
    window.setInterval(function () {
      if (document.hidden) return;
      loadCounts();
    }, 5000);
  }

  function init() {
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    bind();
    var wanted = "";
    try {
      wanted = normalizeTab(new URLSearchParams(location.search).get("tab"));
    } catch (err) {
      wanted = "";
    }
    activate(wanted || TAB_KEYS[0], { keepUrl: !wanted });
    loadCounts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
