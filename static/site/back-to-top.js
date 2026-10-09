(function () {
  "use strict";

  if (window.ErrorBackToTop) return;

  var script = document.currentScript;
  var scrollSelector = script && script.getAttribute("data-scroll-target");
  var container = scrollSelector ? document.querySelector(scrollSelector) : null;
  var button = document.createElement("button");
  var style = document.createElement("style");
  var scrollingElement = document.scrollingElement || document.documentElement;

  style.textContent = [
    ".site-back-top{position:fixed;right:22px;bottom:var(--site-back-top-bottom,22px);z-index:39;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;padding:0;border:1px solid rgba(123,104,238,.52);border-radius:50%;background:#6d5be8;color:#fff;box-shadow:0 10px 24px rgba(80,60,200,.32);cursor:pointer;transition:bottom .18s ease,opacity .18s ease,transform .18s ease}",
    ".site-back-top:hover{transform:translateY(-2px)}",
    ".site-back-top[hidden]{display:none!important}",
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

  window.ErrorBackToTop = { refresh: refresh };
  requestAnimationFrame(refresh);
})();
