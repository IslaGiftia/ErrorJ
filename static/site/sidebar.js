/*
 * 留言页 / 动态页共用的左右侧栏。
 *
 * 数据来自 /api/site/sidebar：
 *   左上 基础信息卡（Error酱 头像 + 在线状态 + 已加入天数 + 注册 / 留言 / 动态 三项统计）
 *     状态：在线 / 离线按站长最近一次真实页面访问算；站长点一下可以自定义一句状态
 *   左下 注册账户卡（只放已通过审核的账号、最多 5 行；游客只有脱敏用户名、看不到任何状态胶囊）
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
  /*
   * 推荐页（/downloads）的四个子模块：歌曲 / 书籍 / 网页 / 站内资源。
   * 它们只活在推荐页里（外壳用 iframe 装这四个内嵌子页），没有对外的独立入口 ——
   * 更新日志点这几类时不再新开标签页去打开独立页面，在留言 / 动态页统一提示
   * 「请在推荐页查看」，在推荐页内部则原地切到对应标签并高亮那一条。
   */
  var RECOMMEND_ACTIONS = {
    music_upload: true,
    book_upload: true,
    recommendation_create: true,
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
   * - 歌曲 / 书籍 / 网页 / 站内资源：推荐页里原地切标签 + 高亮那一条；
   *   其它页面（留言 / 动态）不跳转，只提示「请在推荐页查看」；
   * - 动态页点「更新动态」：不新开标签页，原地把那条动态高亮起来呼吸；
   * - 其余（留言页点「更新动态」、点「新增足迹」）：新标签页打开目标页面，
   *   当前页连同左右四张卡片原地不动。
   */
  function bindNavigation(node, item) {
    node.addEventListener("click", function (event) {
      if (!signedIn) {
        event.preventDefault();
        event.stopPropagation();
        toast("请登录后操作");
        return;
      }
      if (!item) return;
      if (RECOMMEND_ACTIONS[item.action]) {
        // 推荐页内部：原地切标签，不重载 iframe、不新开标签
        if (location.pathname === "/downloads" && item.tab) {
          var tabs = window.ErrorDownloadsTabs;
          if (tabs && tabs.focus) {
            event.preventDefault();
            tabs.focus(item.tab, item.target_id);
            return;
          }
        }
        // 留言 / 动态页：这四个模块没有独立入口，指路到推荐页
        event.preventDefault();
        event.stopPropagation();
        toast("请在推荐页查看");
        return;
      }
      if (!item.url) return;
      if (location.pathname === "/moments" && item.action === "moment_create") {
        event.preventDefault();
        if (window.ErrorFocus) window.ErrorFocus.apply(item.target_id);
        return;
      }
      // 其余：按 <a target="_blank"> 交给浏览器新开标签页
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

  /*
   * 「注册账户」每行第二句：优先说「最近活跃」，而不是「最近登录」。
   *
   * last_login_at 只在真的输密码登录那一刻写，靠浏览器里记住的会话继续浏览不会更新 ——
   * 所以一个一直在站内逛的账号也会显示成「10 小时前登录」（站长实测过）。
   * 这里改成取「最近一次页面访问」（last_view_at，来自 access_log）和「最近一次登录」里
   * 更晚的那个：人在站内就是「刚刚活跃 / N 分钟前活跃」。访问日志没开或记录已被清理时
   * last_view_at 为空，自动退回原来的「…前登录」。
   */
  function activityText(item) {
    var lastView = String((item && item.last_view_at) || "");
    var lastLogin = String((item && item.last_login_at) || "");
    if (lastView && (!lastLogin || lastView >= lastLogin)) {
      return relTime(lastView) + "活跃";
    }
    if (lastLogin) return relTime(lastLogin) + "登录";
    return "还没登录过";
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

  /*
   * 状态胶囊（左上「Error酱」一枚，左下每个账号各一枚）。
   *
   * 在线 / 离线不是看会话（会话能挂好几天，登录着不代表人在），后端按「站长最近一次真实
   * 页面访问」算，10 分钟窗口内有访问就算在线 —— 见 app.py 的 presence_payload()。
   * 只有本人那一枚是可点的：点开在胶囊下方弹一个小窗口 —— 在线 / 在线-<当前设备> / 隐身
   * （设备那一项只有后端认出当前设备时才有，例如 Windows 就只多一个「在线-Win」），站长
   * 多一个自定义输入框。别人的胶囊、游客看到的胶囊都只读。
   */
  function presenceOptions(device) {
    // 「离线」不在选项里 —— 在线还是离线由系统按活跃时间判，本人只能决定要不要带设备后缀
    var options = [{ mode: "auto", suffix: "", tone: "online", label: "在线" }];
    if (device) {
      options.push({
        mode: "auto",
        suffix: device,
        tone: "online",
        label: "在线-" + device,
      });
    }
    options.push({ mode: "invisible", suffix: "", tone: "invisible", label: "隐身" });
    return options;
  }
  var presenceMenu = null;
  var presenceMenuDismiss = null;
  // 节点没进文档量不出宽度，所以侧栏渲染完再统一处理滚动
  var marqueeReady = false;

  /*
   * 文字比文字区宽时，克隆一份拼成首尾相接的轨道，匀速往左循环；靠两端遮罩做渐隐渐显。
   * 鼠标悬停在胶囊上会暂停（见 sidebar.css 的 animation-play-state）。
   */
  function setupMarquee(box) {
    var track = box.querySelector(".sb-presence__track");
    var text = box.querySelector(".sb-presence__text");
    if (!track || !text || box.classList.contains("is-scrolling")) return;
    if (text.scrollWidth <= box.clientWidth + 1) return;
    var gap = el("span", "sb-presence__gap");
    var clone = text.cloneNode(true);
    clone.classList.add("sb-presence__text--clone");
    clone.setAttribute("aria-hidden", "true");
    track.append(gap, clone, gap.cloneNode(false));
    box.classList.add("is-scrolling");
    var half = track.scrollWidth / 2;
    // 大约每秒 18px，太快看不清、太慢像卡住；限定在 2.6s ~ 9s
    var seconds = Math.min(9, Math.max(2.6, half / 18));
    box.style.setProperty("--sb-presence-duration", seconds.toFixed(2) + "s");
  }

  function setupMarquees(root) {
    Array.prototype.forEach.call(
      root.querySelectorAll(".sb-presence--fixed .sb-presence__scroll"),
      setupMarquee
    );
  }

  function presenceChip(presence, options) {
    var opts = options || {};
    var node = document.createElement(opts.editable ? "button" : "span");
    node.className = "sb-presence";
    // 左下卡片里的胶囊统一尺寸、右对齐成一列，文字放不下就在圆点和右边框之间无缝滚动
    if (opts.fixed) node.classList.add("sb-presence--fixed");
    if (opts.editable) node.type = "button";
    if (opts.id) node.dataset.presenceId = String(opts.id);
    var dot = el("span", "sb-presence__dot");
    dot.setAttribute("aria-hidden", "true");
    var box = el("span", "sb-presence__scroll");
    var track = el("span", "sb-presence__track");
    var label = el("span", "sb-presence__text");
    track.appendChild(label);
    box.appendChild(track);
    node.append(dot, box);
    var state = {};

    function paint(next) {
      state = next || {};
      var text = String(state.label || "离线");
      label.textContent = text;
      // 滚过一次就把克隆份去掉，内容变了要重新量
      Array.prototype.slice
        .call(track.querySelectorAll(".sb-presence__text--clone, .sb-presence__gap"))
        .forEach(function (extra) {
          extra.remove();
        });
      box.classList.remove("is-scrolling");
      node.classList.remove("is-online", "is-offline", "is-invisible");
      node.classList.add("is-" + (state.tone || "offline"));
      node.classList.toggle("is-custom", Boolean(state.text));
      if (opts.editable) {
        node.setAttribute("aria-label", "我的状态：" + text + "，点击可以修改");
      } else {
        node.title = text;
      }
      if (opts.fixed && marqueeReady) setupMarquee(box);
    }

    paint(presence);

    if (!opts.editable) return node;

    function save(mode, suffix, text) {
      var payload = { mode: mode, suffix: suffix };
      if (opts.withCustom) payload.text = String(text || "");
      return fetch("/api/site/user-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      })
        .then(function (response) {
          return response.ok ? response.json() : null;
        })
        .then(function (result) {
          if (!result || !result.presence) {
            if (window.ErrorDialog) {
              window.ErrorDialog.alert("状态没保存成功，请稍后再试。");
            }
            return;
          }
          paint(result.presence);
          closePresenceMenu();
          toast("状态已更新");
        })
        .catch(function () {});
    }

    node.addEventListener("click", function (event) {
      event.stopPropagation();
      openPresenceMenu(node, state, opts, save);
    });
    return node;
  }

  function closePresenceMenu() {
    if (presenceMenuDismiss) {
      document.removeEventListener("click", presenceMenuDismiss);
      document.removeEventListener("keydown", presenceMenuKey);
      window.removeEventListener("resize", presenceMenuDismiss);
      window.removeEventListener("scroll", presenceMenuDismiss, true);
      presenceMenuDismiss = null;
    }
    if (presenceMenu) {
      presenceMenu.remove();
      presenceMenu = null;
    }
  }

  function presenceMenuKey(event) {
    if (event.key === "Escape") closePresenceMenu();
  }

  function isCurrentPresence(option, presence) {
    if (option.mode === "invisible") return presence.mode === "invisible";
    if (presence.mode === "invisible") return false;
    return (presence.tone || "offline") === option.tone &&
      (presence.suffix || "") === option.suffix;
  }

  /*
   * 小窗口挂在 <body> 上（卡片自己 overflow: hidden，塞进卡片会被裁掉），
   * 用 fixed 定位贴在胶囊正下方；万一下面放不下就翻到胶囊上面。
   */
  function placePresenceMenu(anchor) {
    var rect = anchor.getBoundingClientRect();
    var width = presenceMenu.offsetWidth;
    var height = presenceMenu.offsetHeight;
    var left = Math.min(Math.max(8, rect.left), Math.max(8, window.innerWidth - width - 8));
    var top = rect.bottom + 6;
    if (top + height > window.innerHeight - 8) {
      top = Math.max(8, rect.top - height - 6);
    }
    presenceMenu.style.left = Math.round(left) + "px";
    presenceMenu.style.top = Math.round(top) + "px";
  }

  function openPresenceMenu(anchor, presence, opts, save) {
    if (presenceMenu && presenceMenu.dataset.anchor === anchor.dataset.presenceId) {
      closePresenceMenu();
      return;
    }
    closePresenceMenu();
    var menu = el("div", "sb-presence-menu");
    menu.setAttribute("role", "menu");
    menu.dataset.anchor = anchor.dataset.presenceId || "";
    presenceOptions(opts.device).forEach(function (option) {
      var item = el("button", "sb-presence-menu__item");
      item.type = "button";
      if (isCurrentPresence(option, presence)) item.classList.add("is-current");
      var dot = el("span", "sb-presence-menu__dot is-" + option.tone);
      dot.setAttribute("aria-hidden", "true");
      item.append(dot, el("span", "", option.label));
      item.addEventListener("click", function (event) {
        event.stopPropagation();
        save(option.mode, option.suffix, opts.withCustom ? "" : null);
      });
      menu.appendChild(item);
    });
    if (opts.withCustom) {
      var form = el("form", "sb-presence-menu__custom");
      var input = document.createElement("input");
      input.type = "text";
      input.maxLength = 12;
      input.placeholder = "自定义状态";
      input.value = String(presence.text || "");
      var ok = el("button", "sb-presence-menu__ok", "确定");
      ok.type = "submit";
      form.append(input, ok);
      form.addEventListener("click", function (event) { event.stopPropagation(); });
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        save("auto", "", input.value);
      });
      menu.appendChild(form);
    }
    document.body.appendChild(menu);
    presenceMenu = menu;
    placePresenceMenu(anchor);
    presenceMenuDismiss = closePresenceMenu;
    window.setTimeout(function () {
      document.addEventListener("click", closePresenceMenu);
      document.addEventListener("keydown", presenceMenuKey);
      window.addEventListener("resize", closePresenceMenu);
      window.addEventListener("scroll", closePresenceMenu, true);
    }, 0);
  }

  function buildProfile(data) {
    var viewer = data.viewer || {};
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
    var nameRow = el("div", "sb-user__namerow");
    nameRow.appendChild(el("div", "sb-user__name", "Error酱"));
    nameRow.appendChild(
      presenceChip(data.presence, {
        // 只有站长能点开改（自定义输入框也只给站长），游客和普通账号只读
        editable: Boolean(viewer.admin),
        withCustom: Boolean(viewer.admin),
        device: viewer.device,
        id: "owner",
      })
    );
    textBox.appendChild(nameRow);
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

  /*
   * 每行第二句「注册 N 天 · X 前活跃」**只有管理员看得到**（活跃时间取「最近访问 /
   * 最近登录」里更晚的那个）。普通账号连自己那行也不显示，游客那边后端压根不下发这几个字段，
   * 所以这里拿不到数据就整行不渲染。
   */
  function userSubText(item) {
    if (item.masked) return "";
    if (!item.registered_days && !item.last_view_at && !item.last_login_at) return "";
    var pieces = [];
    if (item.registered_days) pieces.push("注册 " + item.registered_days + " 天");
    pieces.push(activityText(item));
    return pieces.join(" · ");
  }

  function buildUsers(data) {
    var items = data.users && Array.isArray(data.users.items) ? data.users.items : [];
    // 标题右边不再显示注册用户总数
    var built = card("注册账户", "", true);

    if (!items.length) {
      built.body.appendChild(el("div", "sb-user-row__name", "还没有注册账号。"));
      return built.root;
    }
    items.slice(0, USER_LIMIT).forEach(function (item) {
      var row = el("div", "sb-user-row");
      var main = el("div", "sb-user-row__main");
      var nameRow = el("div", "sb-user-row__namerow");
      nameRow.appendChild(el("span", "sb-user-row__name", item.name));
      // 状态胶囊：游客那边后端根本不下发（游客只看得到左上「Error酱」那一枚）；
      // 登录账号里，只有自己那一枚可点，别人的只读。
      if (item.presence) {
        nameRow.appendChild(
          presenceChip(item.presence, {
            editable: Boolean(item.self),
            device: (data.viewer || {}).device,
            // 左下卡片的胶囊固定尺寸、右对齐成一列：装不下就在胶囊里无缝滚动
            fixed: true,
            id: "user-" + item.id,
          })
        );
      }
      main.appendChild(nameRow);
      var sub = userSubText(item);
      if (sub) main.appendChild(el("div", "sb-user-row__sub", sub));
      row.appendChild(main);
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
    // 封面卡是纯展示区域：不点击、不跳转（和左上角卡片一样）
    var link = el("div", "sb-cover");
    link.setAttribute("aria-hidden", "true");
    var fallback = el("div", "sb-cover__fallback");
    fallback.appendChild(icon("image"));
    wrap.appendChild(fallback);
    wrap.appendChild(link);
    root.appendChild(wrap);

    if (!covers.length) {
      // 一张封面都没有：只留占位图标
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
    link.dataset.href = covers[0].href || "";

    var index = 0;
    var active = 0;
    var usable = covers;
    var rotating = false;

    function apply() {
      link.dataset.href = usable[index].href || "";
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
      var recommendOnly = Boolean(RECOMMEND_ACTIONS[item.action]);
      var onDownloads = location.pathname === "/downloads" && Boolean(item.tab);
      var samePage =
        onDownloads ||
        (location.pathname === "/moments" && item.action === "moment_create");
      if (signedIn && item.url) {
        if (recommendOnly && !onDownloads) {
          // 留言 / 动态页上这几行不是链接：点了只提示「请在推荐页查看」，不做任何跳转
        } else if (recommendOnly) {
          // 推荐页内部：链接也只指向推荐页的对应那一栏（中键 / 右键新开标签页同样落在推荐页，
          // 不会跑到那四个独立子页里去），点击时由 bindNavigation 原地切标签
          row.href =
            "/downloads?tab=" +
            encodeURIComponent(item.tab) +
            (item.target_id ? "&focus=" + encodeURIComponent(item.target_id) : "");
        } else {
          row.href = item.url;
          if (!samePage) {
            // 目标不在当前页：新标签页打开，当前页（含左右四张卡片）原地不动
            row.target = "_blank";
            row.rel = "noopener";
          }
        }
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
      bindNavigation(row, item);
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
    marqueeReady = true;
    setupMarquees(left);
  }

  fetch("/api/site/sidebar", { cache: "no-store" })
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .then(render)
    .catch(function () {});
})();
