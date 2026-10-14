(function () {
  "use strict";

  if (window.ErrorBackToTop) return;

  var script = document.currentScript;
  var scrollSelector = script && script.getAttribute("data-scroll-target");
  var container = scrollSelector ? document.querySelector(scrollSelector) : null;
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
    ".site-back-top{position:fixed;right:22px;bottom:var(--site-back-top-bottom,22px);z-index:39;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;padding:0;border:1px solid rgba(123,104,238,.52);border-radius:50%;background:#6d5be8;color:#fff;box-shadow:0 10px 24px rgba(80,60,200,.32);cursor:pointer;opacity:1;transform:none;transition:bottom var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1)),opacity var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1)),transform var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1)),visibility var(--dur-fast, 160ms) var(--ease-out-strong, cubic-bezier(0.23,1,0.32,1))}",
    ".site-back-top:hover{transform:translateY(-2px)}",
    ".site-back-top[hidden]{visibility:hidden;opacity:0;transform:translateY(4px);pointer-events:none}",
    ".site-back-top svg{width:20px;height:20px}",
    "@media(max-width:640px){.site-back-top{right:14px;width:42px;height:42px}}",
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
    return container
      ? container.scrollTop
      : window.scrollY || scrollingElement.scrollTop || 0;
  }

  function overflows() {
    if (container) {
      return container.scrollHeight > container.clientHeight + 8;
    }
    return document.documentElement.scrollHeight > window.innerHeight + 8;
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

  button.addEventListener("click", function () {
    if (pending && typeof pending.onActivate === "function") {
      pending.onActivate();
      return;
    }
    if (container) {
      container.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    button.hidden = true;
  });

  var listenerTarget = container || window;
  listenerTarget.addEventListener("wheel", onWheel, { passive: true });
  listenerTarget.addEventListener("touchmove", onTouchMove, { passive: true });
  listenerTarget.addEventListener("scroll", hideIfNeeded, { passive: true });
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
  requestAnimationFrame(refresh);
})();
