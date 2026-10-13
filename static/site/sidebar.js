/*
 * 留言页 / 动态页共用的左右侧栏。
 *
 * 数据来自 /api/site/sidebar：
 *   左上 基础信息卡（Error酱 头像 + 已加入天数 + 注册 / 留言 / 动态 三项统计）
 *   左下 注册账户卡（管理员看前 5 个账号，普通账号只看自己，游客只占一位并提示「登录后展示」）
 *   右上 资源封面卡（歌曲 / 电子书封面，只有图片、渐隐渐出轮播）
 *   右下 更新日志卡（管理员的上传 / 发布类更新，前 8 条，点击跳转）
 *
 * 游客：四张卡都展示，内容不脱敏，但点图片 / 日志 / 账户卡一律提示「请登录后操作」。
 */
(function () {
  "use strict";

  var left = document.getElementById("sidebarLeft");
  var right = document.getElementById("sidebarRight");
  if (!left || !right) return;

  var CAROUSEL_INTERVAL = 4000;
  var LOG_LIMIT = 8;
  var USER_LIMIT = 5;
  var AVATAR_SRC = "/static/site/error-chan-avatar.png?v=1";
  var ACTION_ICONS = {
    music_upload: "music",
    book_upload: "book-open",
    moment_create: "newspaper",
    map_place_create: "map-pin",
    recommendation_create: "star",
  };

  var toastTimer = null;
  var signedIn = false;

  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function icon(name, className) {
    var node = document.createElement("i");
    node.setAttribute("data-lucide", name);
    node.setAttribute("aria-hidden", "true");
    if (className) node.className = className;
    return node;
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  /* 和页面里那个 #toast 共用：提示统一由页面样式负责 */
  function toast(text) {
    var box = $("toast");
    if (!box) return;
    box.textContent = text;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      box.hidden = true;
    }, 2600);
  }

  /* 游客点了需要登录的区域：拦下跳转，只提示 */
  function guard(node) {
    node.addEventListener("click", function (event) {
      if (signedIn) return;
      event.preventDefault();
      event.stopPropagation();
      toast("请登录后操作");
    });
  }

  function relTime(value) {
    var text = String(value || "");
    var match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!match) return text;
    var then = new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5])
    );
    var seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
    if (seconds < 60) return "刚刚";
    if (seconds < 3600) return Math.round(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.round(seconds / 3600) + " 小时前";
    if (seconds < 86400 * 7) return Math.round(seconds / 86400) + " 天前";
    return match[1] + "-" + match[2] + "-" + match[3] + " " + match[4] + ":" + match[5];
  }

  function initialOf(text) {
    var value = String(text || "").trim();
    return value ? value.slice(0, 1).toUpperCase() : "?";
  }

  function card(title, metaText, bottom) {
    var wrap = el("section", "sb-card " + (bottom ? "sb-card--bottom" : "sb-card--top"));
    if (title) {
      var head = el("header", "sb-card__head");
      head.appendChild(el("span", "sb-card__title", title));
      var meta = el("span", "sb-card__meta", metaText || "");
      if (!metaText) meta.hidden = true;
      head.appendChild(meta);
      wrap.appendChild(head);
    }
    var body = el("div", "sb-card__body");
    wrap.appendChild(body);
    return { root: wrap, body: body };
  }

  /* ---------------- 左上：基础信息卡 ---------------- */

  function buildProfile(data) {
    var stats = data.stats || {};
    var root = el("section", "sb-card sb-card--top");
    var body = el("div", "sb-card__body");

    var userRow = el("div", "sb-user");
    var avatar = document.createElement("img");
    avatar.className = "sb-avatar";
    avatar.src = AVATAR_SRC;
    avatar.alt = "";
    userRow.appendChild(avatar);

    var textBox = el("div", "sb-user__text");
    textBox.appendChild(el("div", "sb-user__name", "Error酱"));
    textBox.appendChild(el("div", "sb-user__role", "已加入 " + (stats.site_days || 0) + " 天"));
    userRow.appendChild(textBox);
    body.appendChild(userRow);

    var grid = el("div", "sb-stats");
    [
      ["注册", stats.user_total || 0],
      ["留言", stats.message_total || 0],
      ["动态", stats.moment_total || 0],
    ].forEach(function (pair) {
      var box = el("div", "sb-stat");
      box.appendChild(el("span", "sb-stat__label", pair[0]));
      box.appendChild(el("span", "sb-stat__value", pair[1]));
      grid.appendChild(box);
    });
    body.appendChild(grid);

    root.appendChild(body);
    return root;
  }

  /* ---------------- 左下：注册账户卡 ---------------- */

  function buildUsers(data) {
    var isAll = !signedIn || (data.users && data.users.scope === "all");
    var items = data.users && Array.isArray(data.users.items) ? data.users.items : [];
    var built = card(
      "注册账户",
      isAll && items.length ? String(data.users.total || items.length) : "",
      true
    );

    if (!signedIn) {
      // 游客：只占一位注册用户的高度，点一下提示登录
      var locked = el("div", "sb-user-row sb-user-row--locked");
      var lockedAvatar = el("span", "sb-user-row__avatar");
      lockedAvatar.appendChild(icon("user"));
      locked.appendChild(lockedAvatar);
      var lockedMain = el("div", "sb-user-row__main");
      lockedMain.appendChild(el("div", "sb-user-row__name", "登录后展示"));
      locked.appendChild(lockedMain);
      guard(locked);
      built.body.appendChild(locked);
      return built.root;
    }

    if (!items.length) {
      built.body.appendChild(el("div", "sb-user-row__name", "还没有注册账号。"));
      return built.root;
    }
    items.slice(0, USER_LIMIT).forEach(function (item) {
      var row = el("div", "sb-user-row");
      row.appendChild(el("span", "sb-user-row__avatar", initialOf(item.name)));
      var main = el("div", "sb-user-row__main");
      main.appendChild(el("div", "sb-user-row__name", item.name));
      var pieces = [];
      if (item.registered_days) pieces.push("注册 " + item.registered_days + " 天");
      pieces.push(
        item.last_login_at ? relTime(item.last_login_at) + "登录" : "还没登录过"
      );
      main.appendChild(el("div", "sb-user-row__sub", pieces.join(" · ")));
      row.appendChild(main);
      if (item.status === "pending") {
        row.appendChild(el("span", "sb-chip", "待审核"));
      }
      built.body.appendChild(row);
    });
    return built.root;
  }

  /* ---------------- 右上：资源封面卡（只有图片，渐隐渐出） ---------------- */

  function buildCovers(data) {
    var covers = Array.isArray(data.covers) ? data.covers : [];
    var root = el("section", "sb-card sb-card--top");
    var wrap = el("div", "sb-cover-wrap");
    var link = el("a", "sb-cover");
    var fallback = el("div", "sb-cover__fallback");
    fallback.appendChild(icon("image"));
    wrap.appendChild(fallback);
    wrap.appendChild(link);
    root.appendChild(wrap);

    if (!covers.length) {
      link.removeAttribute("href");
      return root;
    }

    // 两层图片叠着，切的时候新图淡入、旧图淡出
    var layers = [0, 1].map(function (index) {
      var image = document.createElement("img");
      image.className = "sb-cover__img" + (index === 0 ? " is-active" : "");
      image.alt = "";
      image.loading = "lazy";
      image.src = covers[0].cover_url;
      link.appendChild(image);
      return image;
    });
    // 先把封面都预热一遍，切的时候不会先闪一下空白
    covers.forEach(function (item) {
      var preload = new Image();
      preload.src = item.cover_url;
    });

    var index = 0;
    var active = 0;
    var timer = null;

    function apply() {
      link.href = covers[index].href || "#";
      link.setAttribute("aria-label", covers[index].title || "站内资源");
      var next = active === 0 ? 1 : 0;
      layers[next].src = covers[index].cover_url;
      layers[next].classList.add("is-active");
      layers[active].classList.remove("is-active");
      active = next;
    }

    if (covers.length > 1) {
      timer = window.setInterval(function () {
        if (document.hidden || wrap.matches(":hover")) return;
        index = (index + 1) % covers.length;
        apply();
      }, CAROUSEL_INTERVAL);
    }

    apply();
    guard(link);
    return root;
  }

  /* ---------------- 右下：更新日志卡 ---------------- */

  function buildLogs(data) {
    var items = Array.isArray(data.activities) ? data.activities : [];
    items = items.slice(0, LOG_LIMIT);
    var built = card("更新日志", "", true);
    built.body.classList.add("sb-card__body--flush");

    if (!items.length) {
      built.body.appendChild(el("div", "sb-user-row__sub", "最近还没有更新。"));
      return built.root;
    }
    items.forEach(function (item, position) {
      var row = el("a", "sb-log" + (signedIn ? "" : " sb-log--locked"));
      if (signedIn && item.href) {
        row.href = item.href;
      }
      row.appendChild(el("span", "sb-log__rank", String(position + 1)));
      var iconBox = el("span", "sb-log__icon");
      iconBox.appendChild(icon(ACTION_ICONS[item.action] || "activity"));
      row.appendChild(iconBox);
      row.appendChild(el("span", "sb-log__text", item.text || ""));
      guard(row);
      built.body.appendChild(row);
    });
    return built.root;
  }

  function render(data) {
    if (!data || !data.viewer) return;
    signedIn = Boolean(data.viewer.signed_in);
    left.textContent = "";
    right.textContent = "";
    left.append(buildProfile(data), buildUsers(data));
    right.append(buildCovers(data), buildLogs(data));
    refreshIcons();
  }

  fetch("/api/site/sidebar", { cache: "no-store" })
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .then(render)
    .catch(function () {});
})();
