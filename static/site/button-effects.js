/*
 * Error酱按钮反馈层。
 *
 * 自动接管：
 *   - 按压 92% + 松手弹性回弹
 *   - 从点击坐标扩散的液态颜色
 *   - 桌面端主操作按钮的磁吸位移和橙色光晕
 *   - 危险操作确认按钮的 100% 长按进度
 *
 * 业务动作按需调用：
 *   ErrorButtons.busy(button, "正在保存")
 *   ErrorButtons.success(button)
 *   ErrorButtons.fail(button)
 *   ErrorButtons.burst(button)
 *
 * 所有效果都跟随 prefers-reduced-motion；键盘触发长按确认时保持普通点击，
 * 不让辅助技术用户必须按住 900ms。
 */
(function () {
  "use strict";

  if (window.ErrorButtons && window.ErrorButtons.ready) return;

  var reducedMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false };
  var finePointer = window.matchMedia
    ? window.matchMedia("(hover: hover) and (pointer: fine)")
    : { matches: false };

  var ACTION_SELECTOR = [
    "button",
    "a.landing-module-btn",
    "[role='button']",
  ].join(",");

  var LIQUID_SELECTOR = [
    ".btn",
    ".mg-btn",
    ".mo-btn",
    ".mu-btn",
    ".bk-btn",
    ".rec-btn",
    ".wb-btn",
    ".nt-btn",
    ".nt-ghost-btn",
    ".pin-primary-btn",
    ".pin-secondary-btn",
    ".pin-header-btn",
    ".pin-danger-btn",
    ".auth-submit",
    ".auth-status-btn",
    ".theme-float",
    ".login-submit",
    ".register-submit",
    ".site-dialog-btn",
    ".er-report-btn",
    ".mp-btn-primary",
    ".mp-dialog-actions .mp-btn",
    ".pr-action",
    ".dl-action",
    ".landing-module-btn",
    ".mo-send-float",
    ".mg-send-float",
  ].join(",");

  var MAGNETIC_SELECTOR = [
    ".btn-primary",
    ".mg-btn-primary",
    ".mo-btn-primary",
    ".mu-btn-primary",
    ".bk-btn-primary",
    ".rec-btn-primary",
    ".wb-btn-primary",
    ".nt-btn-primary",
    ".pin-header-btn-primary",
    ".pin-primary-btn",
    ".auth-submit",
    ".login-submit",
    ".register-submit",
    ".site-dialog-btn.primary",
    ".mp-btn-primary",
    ".mp-dialog-actions .mp-btn-primary",
    ".pr-action.primary",
    ".landing-module-btn",
  ].join(",");

  var HOLD_SELECTOR = "#confirmOk, #mapConfirmOk, [data-hold-confirm]";
  var HOLD_DURATION = 900;
  var states = new WeakMap();
  var holdStates = new WeakMap();
  var pressedEl = null;
  var magneticEl = null;
  var enhanceQueued = false;

  function closestMatch(target, selector) {
    if (!target || target.nodeType !== 1 || typeof target.closest !== "function") return null;
    return target.closest(selector);
  }

  function canAnimate(el) {
    return el && !reducedMotion.matches && typeof el.animate === "function";
  }

  function ensureState(el) {
    var state = states.get(el);
    if (state) return state;
    state = {
      mark: null,
      previousLabel: null,
      resetTimer: 0,
    };
    states.set(el, state);
    return state;
  }

  function ensureStateMark(el) {
    var state = ensureState(el);
    if (state.mark && state.mark.isConnected) return state.mark;

    var mark = document.createElement("span");
    mark.className = "fx-state-mark";
    mark.setAttribute("aria-hidden", "true");

    var spinner = document.createElement("span");
    spinner.className = "fx-state-spinner";
    var check = document.createElement("span");
    check.className = "fx-state-check";
    mark.append(spinner, check);
    el.appendChild(mark);
    state.mark = mark;
    return mark;
  }

  function rememberLabel(el) {
    var state = ensureState(el);
    if (state.previousLabel === null) {
      state.previousLabel = el.getAttribute("aria-label");
    }
  }

  function restoreLabel(el) {
    var state = ensureState(el);
    if (state.previousLabel === null) return;
    if (state.previousLabel) el.setAttribute("aria-label", state.previousLabel);
    else el.removeAttribute("aria-label");
    state.previousLabel = null;
  }

  function clearResetTimer(el) {
    var state = ensureState(el);
    if (state.resetTimer) {
      window.clearTimeout(state.resetTimer);
      state.resetTimer = 0;
    }
  }

  function rememberInk(el) {
    if (el.style.getPropertyValue("--fx-button-ink")) return;
    if (!window.getComputedStyle) return;
    var style = window.getComputedStyle(el);
    var color = style.color;
    if (color) el.style.setProperty("--fx-button-ink", color);
    if (style.borderTopStyle && style.borderTopStyle !== "none" && style.borderTopWidth !== "0px") {
      el.style.setProperty("--fx-button-border", style.borderTopColor);
    }
  }

  function busy(el, label) {
    if (!el) return;
    rememberLabel(el);
    rememberInk(el);
    clearResetTimer(el);
    ensureStateMark(el);
    el.classList.remove("fx-is-done", "fx-is-error");
    el.classList.add("fx-is-loading");
    el.setAttribute("aria-busy", "true");
    if (label) el.setAttribute("aria-label", label);
  }

  function resetState(el) {
    if (!el) return;
    clearResetTimer(el);
    el.classList.remove("fx-is-loading", "fx-is-done", "fx-is-error");
    el.removeAttribute("aria-busy");
    restoreLabel(el);
    el.style.removeProperty("--fx-button-ink");
    el.style.removeProperty("--fx-button-border");
  }

  function success(el, options) {
    if (!el) return;
    options = options || {};
    rememberInk(el);
    clearResetTimer(el);
    ensureStateMark(el);
    el.classList.remove("fx-is-loading", "fx-is-error");
    el.classList.add("fx-is-done");
    el.removeAttribute("aria-busy");
    el.setAttribute("aria-label", options.label || "已完成");
    burst(el);

    var state = ensureState(el);
    state.resetTimer = window.setTimeout(function () {
      state.resetTimer = 0;
      el.classList.remove("fx-is-done");
      restoreLabel(el);
      el.style.removeProperty("--fx-button-ink");
      el.style.removeProperty("--fx-button-border");
    }, options.duration || 900);
  }

  function fail(el) {
    if (!el) return;
    clearResetTimer(el);
    el.classList.remove("fx-is-loading", "fx-is-done");
    el.classList.add("fx-is-error");
    el.removeAttribute("aria-busy");
    restoreLabel(el);
    el.style.removeProperty("--fx-button-ink");
    el.style.removeProperty("--fx-button-border");

    var state = ensureState(el);
    state.resetTimer = window.setTimeout(function () {
      state.resetTimer = 0;
      el.classList.remove("fx-is-error");
    }, 330);
  }

  function burst(el) {
    if (!el || reducedMotion.matches || !el.getBoundingClientRect) return;
    var rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;

    var layer = document.createElement("span");
    layer.className = "fx-burst-layer";
    layer.setAttribute("aria-hidden", "true");
    layer.style.left = rect.left + rect.width / 2 + "px";
    layer.style.top = rect.top + rect.height / 2 + "px";

    var colors = ["#ff9f43", "#ffbd69", "#7b68ee", "#a78bfa"];
    var count = 12;
    for (var i = 0; i < count; i += 1) {
      var particle = document.createElement("span");
      var angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.3;
      var edgeX = Math.cos(angle) * rect.width * 0.46;
      var edgeY = Math.sin(angle) * rect.height * 0.46;
      var distance = 19 + Math.random() * 22;
      var size = 3 + Math.random() * 3;
      particle.className = "fx-burst-particle";
      particle.style.setProperty("--fx-sx", edgeX.toFixed(1) + "px");
      particle.style.setProperty("--fx-sy", edgeY.toFixed(1) + "px");
      particle.style.setProperty(
        "--fx-tx",
        (edgeX + Math.cos(angle) * distance).toFixed(1) + "px"
      );
      particle.style.setProperty(
        "--fx-ty",
        (edgeY + Math.sin(angle) * distance - 7).toFixed(1) + "px"
      );
      particle.style.setProperty("--fx-size", size.toFixed(1) + "px");
      particle.style.setProperty("--fx-color", colors[i % colors.length]);
      particle.style.setProperty("--fx-delay", Math.round(Math.random() * 45) + "ms");
      particle.style.setProperty("--fx-rotate", Math.round(90 + Math.random() * 220) + "deg");
      layer.appendChild(particle);
    }

    document.body.appendChild(layer);
    window.setTimeout(function () {
      layer.remove();
    }, 780);
  }

  function isFilledButton(el) {
    return el.matches(
      ".btn-primary, .mg-btn-primary, .mo-btn-primary, .mu-btn-primary, .bk-btn-primary, " +
        ".rec-btn-primary, .wb-btn-primary, .nt-btn-primary, .pin-primary-btn, " +
        ".pin-header-btn-primary, .auth-submit, .login-submit, .register-submit, " +
        ".site-dialog-btn.primary, .mp-btn-primary, .mp-dialog-actions .mp-btn-primary, " +
        ".pr-action.primary"
    );
  }

  function ensureLiquidLayer(el) {
    var layer = el.querySelector(":scope > .fx-liquid-layer");
    if (layer) return layer;
    layer = document.createElement("span");
    layer.className = "fx-liquid-layer";
    layer.setAttribute("aria-hidden", "true");
    el.insertBefore(layer, el.firstChild);
    return layer;
  }

  function liquid(event, el) {
    if (!event || !el || reducedMotion.matches) return;
    var rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    var x = typeof event.clientX === "number" && event.clientX
      ? event.clientX - rect.left
      : rect.width / 2;
    var y = typeof event.clientY === "number" && event.clientY
      ? event.clientY - rect.top
      : rect.height / 2;
    var radius = Math.hypot(
      Math.max(x, rect.width - x),
      Math.max(y, rect.height - y)
    );
    var size = radius * 2;
    var layer = ensureLiquidLayer(el);
    var ripple = document.createElement("span");
    ripple.className = "fx-liquid-ripple";
    ripple.style.width = size + "px";
    ripple.style.height = size + "px";
    ripple.style.left = x - size / 2 + "px";
    ripple.style.top = y - size / 2 + "px";
    ripple.style.setProperty(
      "--fx-liquid",
      isFilledButton(el) ? "var(--fx-liquid-light)" : "var(--fx-liquid-soft)"
    );
    layer.appendChild(ripple);

    if (canAnimate(ripple)) {
      var animation = ripple.animate(
        [
          { transform: "scale(0.08)", opacity: 0.78 },
          { transform: "scale(1)", opacity: 0 },
        ],
        {
          duration: 620,
          easing: "cubic-bezier(0.2, 0.72, 0.22, 1)",
        }
      );
      animation.onfinish = function () {
        ripple.remove();
      };
      animation.oncancel = function () {
        ripple.remove();
      };
    } else {
      window.setTimeout(function () {
        ripple.remove();
      }, 620);
    }
  }

  function pressStart(event) {
    if (event.button !== 0) return;
    var el = closestMatch(event.target, ACTION_SELECTOR);
    if (!el || el.disabled || el.getAttribute("data-no-button-fx") !== null) return;
    pressedEl = el;
    el.classList.add("is-pressing");
  }

  function pressEnd() {
    if (!pressedEl) return;
    var el = pressedEl;
    pressedEl = null;
    el.classList.remove("is-pressing");
    if (!canAnimate(el)) return;
    el.animate(
      [
        { scale: String(0.92) },
        { scale: "1.028", offset: 0.56 },
        { scale: "1" },
      ],
      {
        duration: 430,
        easing: "cubic-bezier(0.22, 0.82, 0.28, 1.2)",
      }
    );
  }

  function resetMagnetic(el) {
    if (!el) return;
    el.classList.remove("is-magnetic-hover");
    el.style.removeProperty("--fx-mx");
    el.style.removeProperty("--fx-my");
  }

  function magneticMove(event) {
    if (!finePointer.matches || reducedMotion.matches) return;
    var el = closestMatch(event.target, MAGNETIC_SELECTOR);
    if (el && !el.disabled) {
      if (magneticEl !== el) {
        resetMagnetic(magneticEl);
        magneticEl = el;
      }
      var rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      var dx = (event.clientX - (rect.left + rect.width / 2)) * 0.1;
      var dy = (event.clientY - (rect.top + rect.height / 2)) * 0.14;
      dx = Math.max(-4.5, Math.min(4.5, dx));
      dy = Math.max(-3.5, Math.min(3.5, dy));
      el.classList.add("is-magnetic-hover");
      el.style.setProperty("--fx-mx", dx.toFixed(2) + "px");
      el.style.setProperty("--fx-my", dy.toFixed(2) + "px");
      return;
    }
    if (magneticEl) {
      resetMagnetic(magneticEl);
      magneticEl = null;
    }
  }

  function ensureHoldLayer(el) {
    var fill = el.querySelector(":scope > .fx-hold-fill");
    if (fill) return fill;
    fill = document.createElement("span");
    fill.className = "fx-hold-fill";
    fill.setAttribute("aria-hidden", "true");
    el.insertBefore(fill, el.firstChild);
    return fill;
  }

  function bindHold(el) {
    if (!el || holdStates.has(el)) return;
    var fill = ensureHoldLayer(el);
    var state = {
      active: false,
      completed: false,
      frame: 0,
      startedAt: 0,
      internalClick: false,
      suppressPointerClick: false,
    };
    holdStates.set(el, state);

    function setProgress(value) {
      fill.style.setProperty("--fx-hold-progress", String(value));
    }

    function resetProgress() {
      setProgress(0);
      el.style.removeProperty("--fx-hold-progress");
      el.classList.remove("is-holding", "fx-hold");
      el.removeAttribute("aria-busy");
    }

    function tick(now) {
      if (!state.active) return;
      if (el.disabled) {
        state.active = false;
        resetProgress();
        return;
      }
      var progress = Math.min(1, (now - state.startedAt) / HOLD_DURATION);
      setProgress(progress);
      if (progress >= 1) {
        state.active = false;
        state.completed = true;
        state.suppressPointerClick = true;
        el.classList.remove("is-holding");
        el.removeAttribute("aria-busy");
        state.internalClick = true;
        el.click();
        state.internalClick = false;
        window.setTimeout(resetProgress, 180);
        return;
      }
      state.frame = window.requestAnimationFrame(tick);
    }

    function start(event) {
      if (!el.hasAttribute("data-hold-confirm")) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
      if (el.disabled || state.active) return;
      state.active = true;
      state.completed = false;
      state.startedAt = window.performance.now();
      state.suppressPointerClick = false;
      el.classList.add("fx-hold");
      if (!el.title) el.title = "长按确认";
      el.classList.add("is-holding");
      el.setAttribute("aria-busy", "true");
      setProgress(0);
      try {
        el.setPointerCapture(event.pointerId);
      } catch (err) {}
      state.frame = window.requestAnimationFrame(tick);
    }

    function cancel(event) {
      if (!state.active) return;
      state.active = false;
      window.cancelAnimationFrame(state.frame);
      if (event && event.type === "pointercancel") state.suppressPointerClick = true;
      resetProgress();
    }

    function clickGuard(event) {
      if (!el.hasAttribute("data-hold-confirm")) return;
      if (state.internalClick) return;
      if (event.detail === 0) return;
      if (state.suppressPointerClick) {
        state.suppressPointerClick = false;
        state.completed = false;
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      if (!state.active) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }

    function contextGuard(event) {
      if (!el.hasAttribute("data-hold-confirm")) return;
      if (state.active) event.preventDefault();
    }

    el.addEventListener("pointerdown", start, true);
    el.addEventListener("pointerup", cancel, true);
    el.addEventListener("pointercancel", cancel, true);
    el.addEventListener("click", clickGuard, true);
    el.addEventListener("contextmenu", contextGuard);
  }

  function enhanceElement(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.matches(ACTION_SELECTOR) && el.getAttribute("data-no-button-fx") === null) {
      el.classList.add("fx-press");
      if (el.matches(LIQUID_SELECTOR)) el.classList.add("fx-liquid-host");
      if (el.matches(MAGNETIC_SELECTOR)) el.classList.add("fx-magnetic");
      if (el.matches(HOLD_SELECTOR)) bindHold(el);
    }
  }

  function enhanceTree(root) {
    if (!root) return;
    if (root.nodeType === 1) {
      enhanceElement(root);
    }
    if (typeof root.querySelectorAll === "function") {
      root.querySelectorAll(ACTION_SELECTOR).forEach(enhanceElement);
    }
  }

  function queueEnhance(root) {
    if (enhanceQueued) return;
    enhanceQueued = true;
    window.requestAnimationFrame(function () {
      enhanceQueued = false;
      enhanceTree(root || document);
    });
  }

  function installObserver() {
    if (!window.MutationObserver) return;
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i += 1) {
        var added = mutations[i].addedNodes;
        for (var j = 0; j < added.length; j += 1) {
          if (added[j].nodeType === 1) {
            enhanceTree(added[j]);
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function init() {
    enhanceTree(document);
    installObserver();

    document.addEventListener("pointerdown", pressStart, true);
    document.addEventListener("pointerup", pressEnd, true);
    document.addEventListener("pointercancel", pressEnd, true);
    document.addEventListener("pointermove", magneticMove, { passive: true });
    document.addEventListener("pointerout", function (event) {
      if (!magneticEl) return;
      if (!magneticEl.contains(event.relatedTarget)) {
        resetMagnetic(magneticEl);
        magneticEl = null;
      }
    });
    document.addEventListener(
      "click",
      function (event) {
        var el = closestMatch(event.target, LIQUID_SELECTOR);
        if (!el || el.disabled || el.getAttribute("data-no-button-fx") !== null) return;
        liquid(event, el);
      },
      true
    );
  }

  window.ErrorButtons = {
    ready: true,
    busy: busy,
    success: success,
    fail: fail,
    reset: resetState,
    burst: burst,
    refresh: function () {
      queueEnhance(document);
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
