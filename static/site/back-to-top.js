(function () {
  "use strict";

  if (window.ErrorBackToTop) return;

  var script = document.currentScript;
  var scrollSelector = script && script.getAttribute("data-scroll-target");
  /*
   * 一个页面可能有不止一个滚动容器：书签的导航视图 / 列表视图、笔记的列表栏 / 正文栏
   * 都各自是滚动容器，只是同一时刻只有一个是可见的。这里把它们全收着，
   * 用的时候挑当前真正可见的那个 —— 藏起来的那个滚不动，也不该参与「滚到哪儿了」的判断。
   */
  var containers = scrollSelector
    ? Array.prototype.slice.call(document.querySelectorAll(scrollSelector))
    : [];
  /* 最近一次真正滚动 / 滚轮过的容器，见 currentContainer() */
  var lastScrolled = null;
  var button = document.createElement("button");
  var style = document.createElement("style");
  var scrollingElement = document.scrollingElement || document.documentElement;
  /*
   * pending：把「回到顶部」临时切成「有新互动」形态（向下箭头 + 自定义文案 + 呼吸）。
   * 只有留言页会用到；其它页面不调用 setPending 时行为和以前完全一样。
   */
  var pending = null;

  style.textContent = [
    /*
     * 显隐走 opacity / transform，不用 display：
     * 以前 [hidden] 是 display:none，下面那条 transition 永远不会播放，按钮是硬闪进出。
     * visibility:hidden 一样会把它移出可聚焦与无障碍树，但元素仍保留布局盒，
     * positionButton() 里读布局的代码不受影响。
     */
    /*
     * visibility 也放进过渡列表：否则隐藏那一刻它立刻生效，透明度那 160ms 的淡出就看不见了
     * （visibility 会在过渡结束后才真正切成 hidden）。
     */
    /*
     * display 这里必须抢回 inline-flex：站点各页都有一句全局的
     * [hidden]{display:none !important}（防止作者样式盖掉原生 hidden），
     * 它会把隐藏态的按钮真的变成 display:none，而 Chrome 对 display:none 的
     * 元素不跑过渡 —— 除了留言页（它的 CSS 没有那条全局规则），其余页面的
     * 淡入淡出全都会失效。所以用同权重的 !important + 更高的选择器权重顶回去，
     * 隐藏态只靠 visibility / opacity，元素留在渲染树里过渡才播得出来。
     */
    /*
     * 这里只管定位、显隐和过渡 —— 尺寸 / 圆角 / 毛玻璃底色 / 文字都归 static/fonts.css 的
     * .site-back-top 管。两边刻意不碰同一个属性：字体样式表是静态加载的，本脚本注入的
     * 样式挂在它后面，同权重会盖掉它，所以各管一半最省事。
     */
    ".site-back-top{position:fixed;right:22px;bottom:var(--site-back-top-bottom,22px);z-index:39;display:inline-flex;align-items:center;justify-content:center;padding:0;cursor:pointer;opacity:1;transform:none;transition:bottom var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1)),opacity var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1)),transform var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1)),visibility var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1))}",
    ".site-back-top:hover{transform:translateY(-2px)}",
    ".site-back-top[hidden]{display:inline-flex!important;visibility:hidden;opacity:0;transform:translateY(4px);pointer-events:none}",
    "@media(max-width:640px){.site-back-top{right:14px}}",
    "@media(prefers-reduced-motion:reduce){.site-back-top{transition:none}}",
  ].join("");

  button.className = "site-back-top";
  button.type = "button";
  button.hidden = true;
  button.title = "返回顶部";
  button.setAttribute("aria-label", "返回顶部");
  button.innerHTML = '<i data-lucide="arrow-up"></i>';

  document.head.appendChild(style);
  document.body.appendChild(button);

  function renderMode() {
    if (pending) {
      button.classList.add("is-pending");
      button.dataset.freshLabel = pending.label || "";
      button.title = pending.title || pending.label || "有新互动";
      button.setAttribute("aria-label", button.title);
    } else {
      button.classList.remove("is-pending");
      delete button.dataset.freshLabel;
      button.title = "返回顶部";
      button.setAttribute("aria-label", "返回顶部");
    }
  }

  function scrollTop() {
    var box = currentContainer();
    return box ? box.scrollTop : window.scrollY || scrollingElement.scrollTop || 0;
  }

  function overflows() {
    var box = currentContainer();
    if (box) {
      return box.scrollHeight > box.clientHeight + 8;
    }
    return document.documentElement.scrollHeight > window.innerHeight + 8;
  }

  /*
   * 当前真正在滚的那个容器。先看「最近一次滚过谁」—— 桌面上的笔记页列表栏和正文栏
   * 是同时可见的，只按可见性挑会一直选中列表栏，用户在正文里滚到哪儿按钮都没反应。
   * 还没滚动过（或那个容器已经不在文档里）时，退回到第一个可见的容器；
   * 都没有容器就是 null，走窗口滚动。
   */
  function currentContainer() {
    if (lastScrolled && lastScrolled.isConnected) return lastScrolled;
    for (var i = 0; i < containers.length; i += 1) {
      if (containers[i].offsetParent !== null) return containers[i];
    }
    return containers.length ? containers[0] : null;
  }

  function visibleJumpButton() {
    return document.querySelector(
      ".mg-jump-btn:not([hidden]), .mo-jump-btn:not([hidden])"
    );
  }

  function baseBottom() {
    var player = document.querySelector("#playerBar:not([hidden])");
    var base = 22;
    if (player && player.getBoundingClientRect().height > 0) {
      base = Math.round(player.getBoundingClientRect().height) + 16;
    }
    /* 仓库页有底部导航栏（桌面上 display:none，高度为 0 会被跳过），按钮得抬到它上面 */
    var nav = document.querySelector(".bottom-nav");
    if (nav) {
      var navHeight = Math.round(nav.getBoundingClientRect().height);
      if (navHeight > 0) base = Math.max(base, navHeight + 16);
    }
    return base;
  }

  function positionButton() {
    var bottom = baseBottom();
    var jump = visibleJumpButton();
    if (jump) {
      bottom += Math.round(jump.getBoundingClientRect().height || 44) + 10;
    }
    button.style.setProperty("--site-back-top-bottom", bottom + "px");
  }

  function hideIfNeeded() {
    // 有新互动时按钮必须常驻，用户才有可能点它跳过去
    if (pending) {
      positionButton();
      button.hidden = false;
      return;
    }
    if (!overflows() || scrollTop() < 24) {
      button.hidden = true;
    }
  }

  function showIfPossible() {
    if (!overflows() || scrollTop() < 1) return;
    positionButton();
    button.hidden = false;
  }

  function refresh() {
    positionButton();
    hideIfNeeded();
  }

  function onWheel(event) {
    if (event.deltaY > 0) showIfPossible();
  }

  function onTouchMove(event) {
    var touch = event.touches && event.touches[0];
    if (!touch) return;
    if (button.dataset.touchY && Number(button.dataset.touchY) > touch.clientY) {
      showIfPossible();
    }
    button.dataset.touchY = String(touch.clientY);
  }

  /*
   * 触摸滚动时，浏览器经常把第一次点按用来停住惯性，click 不一定会派发。
   * 触摸设备在 pointerdown 就执行（并阻止随后可能落到下层元素上的合成 click）；
   * 鼠标在 pointerup 判断没有明显拖动后执行，键盘仍走 click。
   */
  var fastClickBlockUntil = 0;
  var fastClickBlockInstalled = false;

  function fastClickGuard(event) {
    var now = window.performance ? window.performance.now() : Date.now();
    if (now >= fastClickBlockUntil) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function armFastClickBlock() {
    var now = window.performance ? window.performance.now() : Date.now();
    fastClickBlockUntil = now + 700;
    if (fastClickBlockInstalled) return;
    fastClickBlockInstalled = true;
    document.addEventListener("click", fastClickGuard, true);
  }

  function bindFastActivate(el, activate) {
    if (!el || typeof activate !== "function") return;
    var press = null;
    var suppressClickUntil = 0;

    function suppressClick() {
      var now = window.performance ? window.performance.now() : Date.now();
      suppressClickUntil = now + 700;
      window.setTimeout(function () {
        if (suppressClickUntil === now + 700) suppressClickUntil = 0;
      }, 720);
    }

    function finish(event) {
      if (!press || event.pointerId !== press.id) return;
      var moved = Math.hypot(event.clientX - press.x, event.clientY - press.y);
      press = null;
      if (moved > 12) return;
      suppressClick();
      activate();
    }

    el.addEventListener(
      "pointerdown",
      function (event) {
        if (event.pointerType === "mouse") {
          if (event.button !== 0) return;
          press = { id: event.pointerId, x: event.clientX, y: event.clientY };
          return;
        }
        if (event.isPrimary === false) return;
        event.preventDefault();
        armFastClickBlock();
        suppressClick();
        activate();
      },
      { passive: false }
    );
    el.addEventListener("pointerup", finish, { passive: true });
    el.addEventListener("pointercancel", finish, { passive: true });
    el.addEventListener("click", function (event) {
      var now = window.performance ? window.performance.now() : Date.now();
      if (now < suppressClickUntil) {
        suppressClickUntil = 0;
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      activate();
    });
  }

  function activate() {
    if (window.ErrorInertiaScroll) {
      if (window.ErrorInertiaScroll.ignoreNextTouch) {
        window.ErrorInertiaScroll.ignoreNextTouch();
      }
      window.ErrorInertiaScroll.cancel();
    }
    if (pending && typeof pending.onActivate === "function") {
      pending.onActivate();
      return;
    }
    var box = currentContainer();
    if (box) {
      box.scrollTo({ top: 0, behavior: "smooth" });
    } else if (window.ErrorInertiaScroll && window.ErrorInertiaScroll.toTop) {
      window.ErrorInertiaScroll.toTop();
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    button.hidden = true;
  }

  bindFastActivate(button, activate);

  (containers.length ? containers : [window]).forEach(function (target) {
    function remember() {
      lastScrolled = target === window ? null : target;
    }
    target.addEventListener(
      "wheel",
      function (event) {
        remember();
        onWheel(event);
      },
      { passive: true }
    );
    target.addEventListener(
      "touchmove",
      function (event) {
        remember();
        onTouchMove(event);
      },
      { passive: true }
    );
    target.addEventListener(
      "scroll",
      function () {
        remember();
        hideIfNeeded();
      },
      { passive: true }
    );
  });
  window.addEventListener("resize", refresh);
  document.addEventListener("errorjumpvisibilitychange", refresh);
  document.addEventListener("errorauthchange", refresh);

  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }

  renderMode();
  window.ErrorBackToTop = {
    refresh: refresh,
    /**
     * 切到「有新互动」形态：setPending({active:true, label, title, onActivate})
     * 或恢复正常：setPending({active:false})。
     */
    setPending: function (options) {
      var opts = options || {};
      pending = opts.active
        ? {
            label: opts.label || "",
            title: opts.title || "",
            onActivate: opts.onActivate,
          }
        : null;
      renderMode();
      refresh();
    },
  };
  window.ErrorFastActivate = { bind: bindFastActivate };
  requestAnimationFrame(refresh);
})();
