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

  var CAROUSEL_INTERVAL = 5000;
  var LOG_LIMIT = 11;
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

  /*
   * 卡片里的跳转：
   * - 游客：一律拦下，只提示「请登录后操作」；
   * - 指向推荐页某个标签的链接（封面 / 更新日志）：原地切标签，不刷新页面；
   * - 其它链接（动态、足迹等）：照常整页跳转。
   */
  function bindNavigation(node) {
    node.addEventListener("click", function (event) {
      if (!signedIn) {
        event.preventDefault();
        event.stopPropagation();
        toast("请登录后操作");
        return;
      }
      var href = node.getAttribute("href");
      if (!href) return;
      var tabs = window.ErrorDownloadsTabs;
      if (!tabs) return;
      var url;
      try {
        url = new URL(href, location.origin);
      } catch (err) {
        return;
      }
      if (url.pathname !== "/downloads") return;
      var key = normalizeTabKey(url.searchParams.get("tab"));
      if (!key) return;
      event.preventDefault();
      tabs.activate(key);
    });
  }

  function normalizeTabKey(value) {
    var key = String(value || "").toLowerCase();
    if (key === "music" || key === "song" || key === "songs") return "music";
    if (key === "books" || key === "book") return "books";
    if (key === "web" || key === "site" || key === "sites") return "web";
    if (key === "resource" || key === "resources") return "resource";
    return "";
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
      // 数字在上、文字在下
      box.appendChild(el("span", "sb-stat__value", pair[1]));
      box.appendChild(el("span", "sb-stat__label", pair[0]));
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
      var lockedMain = el("div", "sb-user-row__main");
      lockedMain.appendChild(el("div", "sb-user-row__name", "登录后展示"));
      locked.appendChild(lockedMain);
      bindNavigation(locked);
      built.body.appendChild(locked);
      return built.root;
    }

    if (!items.length) {
      built.body.appendChild(el("div", "sb-user-row__name", "还没有注册账号。"));
      return built.root;
    }
    items.slice(0, USER_LIMIT).forEach(function (item) {
      var row = el("div", "sb-user-row");
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

  /*
   * 先把封面下载 + 解码好再开始轮播：
   * 没封面 / 加载失败的条目直接剔除（不占那 5 秒），也不会出现淡入时才解码的空白跳变。
   */
  function prepareCovers(covers, done) {
    if (!covers.length) {
      done([]);
      return;
    }
    var ready = [];
    var pending = covers.length;
    function settle(entry) {
      if (entry) ready.push(entry);
      pending -= 1;
      if (pending > 0) return;
      ready.sort(function (left, right) {
        return left.position - right.position;
      });
      done(
        ready.map(function (entry) {
          return entry.item;
        })
      );
    }
    covers.forEach(function (item, position) {
      var probe = new Image();
      var settled = false;
      probe.onload = function () {
        var decoded = probe.decode ? probe.decode() : null;
        if (decoded && typeof decoded.then === "function") {
          decoded.then(
            function () {
              finish({ position: position, item: item });
            },
            function () {
              finish({ position: position, item: item });
            }
          );
        } else {
          finish({ position: position, item: item });
        }
      };
      probe.onerror = function () {
        finish(null);
      };
      // 单张图卡住（网络慢 / 文件异常）不能拖住整张卡：超时就当它不可用
      var timer = window.setTimeout(function () {
        finish(null);
      }, 6000);
      function finish(entry) {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        settle(entry);
      }
      probe.src = item.cover_url;
    });
  }

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
      // 一张封面都没有：只留占位图标
      link.removeAttribute("href");
      return root;
    }

    // 两张图一开始就摆上（第一张先显示），免得等所有封面下载完卡片是空的
    var layers = [0, 1].map(function (index) {
      var image = document.createElement("img");
      image.className = "sb-cover__img" + (index === 0 ? " is-active" : "");
      image.alt = "";
      image.decoding = "async";
      image.src = covers[0].cover_url;
      link.appendChild(image);
      return image;
    });
    link.href = covers[0].href || "#";
    link.setAttribute("aria-label", covers[0].title || "站内资源");
    bindNavigation(link);

    var index = 0;
    var active = 0;
    var usable = covers;
    var rotating = false;

    function apply() {
      link.href = usable[index].href || "#";
      link.setAttribute("aria-label", usable[index].title || "站内资源");
      var next = active === 0 ? 1 : 0;
      layers[next].src = usable[index].cover_url;
      layers[next].classList.add("is-active");
      layers[active].classList.remove("is-active");
      active = next;
    }

    /*
     * 所有封面下载 + 解码完之后再定轮播名单：没封面 / 加载失败的条目直接剔除，
     * 不占那 5 秒，也不会在淡入时才解码而闪一下空白。
     */
    prepareCovers(covers, function (ready) {
      if (ready.length) {
        usable = ready;
        index = 0;
      }
      if (rotating || usable.length < 2) return;
      rotating = true;
      window.setInterval(function () {
        if (document.hidden || wrap.matches(":hover")) return;
        index = (index + 1) % usable.length;
        apply();
      }, CAROUSEL_INTERVAL);
    });

    return root;
  }

  /* ---------------- 右下：更新日志卡 ---------------- */

  function buildLogs(data) {
    var items = Array.isArray(data.activities) ? data.activities : [];
    items = items.slice(0, LOG_LIMIT);
    var built = card("更新日志", items.length ? "最新" + items.length + "条" : "", true);
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
      var text = el("span", "sb-log__text");
      text.appendChild(el("span", "sb-log__label", item.label || "更新"));
      if (item.target) {
        text.appendChild(document.createTextNode(" "));
        text.appendChild(el("span", "sb-log__name", item.target));
      }
      row.appendChild(text);
      bindNavigation(row);
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
