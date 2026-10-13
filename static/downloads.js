/*
 * 「推荐」页外壳：四个子页面（歌曲 / 书籍 / 网页 / 站内资源）一开始就全部加载好，
 * 切换时只翻转显隐，所以来回点不会重新加载、也不会打断正在播放的歌曲。
 *
 * - 左上角：四个纯图标按钮，切换子页面。
 * - 右上角：常驻「新增」按钮（+歌曲 / +书籍 / +网页 / +站内），文字随子页渐入渐出；
 *   只有站长看得到、点得动，点击后通过同源 iframe 调用子页的 ErrorRecommendTab.openAdd()。
 * - 角标：沿用 /api/site/notifications/summary 里的歌曲 / 书籍 / 推荐三个计数（游客不请求）。
 */
(function () {
  "use strict";

  var TABS = [
    { key: "music", label: "歌曲", module: "music", badge: true },
    { key: "books", label: "书籍", module: "books", badge: true },
    { key: "web", label: "网页", module: "recommendations", badge: true },
    { key: "resource", label: "站内", module: "recommendations", badge: false }
  ];
  var TAB_KEYS = TABS.map(function (tab) {
    return tab.key;
  });
  var counts = {};
  var activeKey = "";
  var busy = false;
  var actionTimer = null;
  // null = 还没问到；站内通知只有登录账号有，游客不用去问（否则控制台一堆 401）
  var authed = null;
  var isOwner = false;

  function $(id) {
    return document.getElementById(id);
  }

  function specOf(key) {
    for (var i = 0; i < TABS.length; i++) {
      if (TABS[i].key === key) return TABS[i];
    }
    return null;
  }

  function tabEl(key) {
    return document.querySelector('.dl-tab[data-tab="' + key + '"]');
  }

  function panelEl(key) {
    return document.querySelector('.dl-panel[data-panel="' + key + '"]');
  }

  function frameWindow(key) {
    var panel = panelEl(key);
    var frame = panel ? panel.querySelector(".dl-frame") : null;
    try {
      return frame && frame.contentWindow ? frame.contentWindow : null;
    } catch (err) {
      return null;
    }
  }

  // 子页面第一次显示（0×0 布局里渲染）后重新派发一次 resize，让卡片网格按真实宽度重排
  function requestRelayout(key) {
    var win = frameWindow(key);
    if (!win) return;
    try {
      win.dispatchEvent(new win.Event("resize"));
    } catch (err) {}
  }

  function paintBadges() {
    TABS.forEach(function (tab) {
      var node = tabEl(tab.key);
      if (!node) return;
      var badge = node.querySelector(".dl-tab-badge");
      if (!badge) return;
      var count = tab.badge ? Number(counts[tab.module]) || 0 : 0;
      badge.hidden = count <= 0;
      badge.textContent = count > 0 ? (count > 99 ? "99+" : String(count)) : "";
    });
  }

  function paintAction(key) {
    var button = $("dlAction");
    var label = $("dlActionLabel");
    if (!button || !label) return;
    var spec = specOf(key) || TABS[0];
    if (!isOwner) {
      button.hidden = true;
      label.textContent = spec.label;
      return;
    }
    button.hidden = false;
    if (label.textContent === spec.label) return;
    // 渐出 → 换文字 → 渐入
    button.classList.add("is-fading");
    clearTimeout(actionTimer);
    actionTimer = setTimeout(function () {
      label.textContent = spec.label;
      button.classList.remove("is-fading");
    }, 140);
  }

  function markSeen(key) {
    if (authed !== true) return;
    var spec = specOf(key);
    if (!spec || !spec.badge) return;
    counts[spec.module] = 0;
    paintBadges();
    fetch("/api/site/notifications/seen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: spec.module }),
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
    if (activeKey === key && (!options || !options.force)) {
      if (!options || !options.keepUrl) updateUrl(key);
      return;
    }
    activeKey = key;
    TABS.forEach(function (tab) {
      var on = tab.key === key;
      var node = tabEl(tab.key);
      var panel = panelEl(tab.key);
      if (node) {
        node.classList.toggle("is-active", on);
        node.setAttribute("aria-pressed", on ? "true" : "false");
      }
      if (panel) panel.classList.toggle("is-active", on);
    });
    paintAction(key);
    requestRelayout(key);
    markSeen(key);
    if (!options || !options.keepUrl) updateUrl(key);
  }

  function loadCounts() {
    if (authed !== true || busy) return Promise.resolve();
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
        var spec = specOf(activeKey);
        if (spec && spec.badge) counts[spec.module] = 0;
        paintBadges();
      })
      .catch(function () {})
      .then(function () {
        busy = false;
      });
  }

  function openAdd() {
    var win = frameWindow(activeKey);
    var api = win && win.ErrorRecommendTab;
    if (api && typeof api.openAdd === "function") api.openAdd();
  }

  /*
   * 子页里的编辑弹窗打开时，把整条悬浮操作区收上去，把位置让给弹窗；
   * 弹窗全部关掉后再从上面滑下来。弹窗在 iframe 里，所以由子页 postMessage 通知。
   */
  function setDialogOpen(open) {
    var dock = document.querySelector(".dl-dock");
    if (!dock) return;
    dock.classList.toggle("is-away", Boolean(open));
  }

  function bindDialogSignal() {
    window.addEventListener("message", function (event) {
      if (event.origin !== window.location.origin) return;
      var data = event.data;
      if (!data || data.type !== "errorj-recommend-dialog") return;
      setDialogOpen(data.open);
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
    var action = $("dlAction");
    if (action) action.addEventListener("click", openAdd);
    bindDialogSignal();
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

  function loadAuth() {
    return fetch("/api/auth/status", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        authed = Boolean(data && data.authenticated);
        isOwner = Boolean(data && data.owner);
        paintAction(activeKey);
        if (authed) loadCounts();
      })
      .catch(function () {
        authed = false;
        isOwner = false;
        paintAction(activeKey);
      });
  }

  function normalizeTab(value) {
    var key = String(value || "").toLowerCase();
    if (key === "music" || key === "song" || key === "songs") return "music";
    if (key === "books" || key === "book") return "books";
    if (key === "web" || key === "site" || key === "sites") return "web";
    if (key === "resource" || key === "resources" || key === "recommendations") return "resource";
    return "";
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
    // 先无条件点亮一次，保证首屏按钮 / 面板状态正确，再按 URL 参数切换
    activate(wanted || TAB_KEYS[0], { keepUrl: !wanted, force: true });
    loadAuth();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
