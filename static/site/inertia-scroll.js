/*
 * 移动端惯性滚动兜底。
 *
 * 大多数手机浏览器本身就有惯性滚动，这份脚本不会去抢它：
 * 松手后先等原生滚动落定，有继续滚动就立刻退出；只有原生确实停住时，
 * 才按手指离开前的速度补一段带衰减的滑动。这样不支持惯性的 WebView / 桌面触摸仿真
 * 也能有「松手后继续滑」的手感，同时不会在正常手机上滚两倍距离。
 */
(function () {
  "use strict";

  if (window.ErrorInertiaScroll) return;

  var reducedMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false };
  var coarsePointer = window.matchMedia
    ? window.matchMedia("(hover: none), (pointer: coarse)")
    : { matches: false };

  var samples = [];
  var tracking = false;
  var frame = 0;
  var topFrame = 0;
  var topToken = 0;
  var ignoreStartUntil = 0;
  var velocity = 0;
  var expectedY = null;
  var lastFrameTime = 0;
  var scrollLimit = 0;

  function now() {
    return window.performance && window.performance.now
      ? window.performance.now()
      : Date.now();
  }

  function scrollTop() {
    return (
      window.pageYOffset ||
      (document.scrollingElement && document.scrollingElement.scrollTop) ||
      document.documentElement.scrollTop ||
      0
    );
  }

  function maxScroll() {
    var root = document.scrollingElement || document.documentElement;
    return Math.max(0, root.scrollHeight - window.innerHeight);
  }

  function inNestedScroller(target) {
    if (!target || target.nodeType !== 1) return false;
    if (
      target.closest(
        "[role='dialog'], [aria-modal='true'], .mg-viewer, .mo-viewer, .rec-modal, .rec-picker"
      )
    ) {
      return true;
    }
    var node = target;
    while (node && node !== document.body && node !== document.documentElement) {
      var style = window.getComputedStyle(node);
      if (
        (style.overflowY === "auto" || style.overflowY === "scroll") &&
        node.scrollHeight > node.clientHeight + 1
      ) {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  function cancel() {
    if (frame) window.cancelAnimationFrame(frame);
    topToken += 1;
    if (topFrame) window.cancelAnimationFrame(topFrame);
    frame = 0;
    topFrame = 0;
    velocity = 0;
    expectedY = null;
    lastFrameTime = 0;
    scrollLimit = 0;
  }

  function step(timestamp) {
    var actual = scrollTop();
    if (expectedY !== null && Math.abs(actual - expectedY) > 1.5) {
      cancel();
      return;
    }

    var dt = lastFrameTime ? Math.min(32, timestamp - lastFrameTime) : 16;
    lastFrameTime = timestamp;
    var limit = scrollLimit;
    var next = actual + velocity * dt;

    if (next <= 0) {
      window.scrollTo(0, 0);
      cancel();
      return;
    }
    if (next >= limit) {
      window.scrollTo(0, limit);
      cancel();
      return;
    }

    expectedY = next;
    window.scrollTo(0, next);
    velocity *= Math.pow(0.94, dt / 16.67);
    if (Math.abs(velocity) < 0.02) {
      cancel();
      return;
    }
    frame = window.requestAnimationFrame(step);
  }

  function toTop() {
    cancel();
    var startY = scrollTop();
    if (startY <= 0) return;
    if (
      reducedMotion.matches ||
      typeof window.requestAnimationFrame !== "function"
    ) {
      window.scrollTo(0, 0);
      return;
    }

    var token = topToken;
    var startedAt = now();
    var duration = Math.min(380, Math.max(220, startY * 0.15));
    topFrame = window.requestAnimationFrame(function stepTop(timestamp) {
      if (token !== topToken) return;
      var progress = Math.min(1, Math.max(0, (timestamp - startedAt) / duration));
      var eased = 1 - Math.pow(1 - progress, 3);
      window.scrollTo(0, startY * (1 - eased));
      if (progress < 1) {
        topFrame = window.requestAnimationFrame(stepTop);
      } else {
        topFrame = 0;
      }
    });
  }

  function arm() {
    if (samples.length < 2) return;
    scrollLimit = maxScroll();
    if (scrollLimit <= 0) return;

    var last = samples[samples.length - 1];
    var first = samples[0];
    for (var i = 0; i < samples.length; i += 1) {
      if (last.t - samples[i].t <= 110) {
        first = samples[i];
        break;
      }
    }

    var elapsed = last.t - first.t;
    if (elapsed <= 0) elapsed = Math.max(16, (samples.length - 1) * 16);
    if (elapsed < 20) return;
    var speed = (last.scroll - first.scroll) / elapsed;
    var fingerDelta = first.y - last.y;
    if (Math.abs(speed) < 0.08 && Math.abs(fingerDelta) > 4) {
      speed = (fingerDelta / elapsed) * 0.9;
    }
    if (Math.abs(speed) < 0.08) return;
    speed = Math.max(-2.4, Math.min(2.4, speed));

    var endY = scrollTop();
    expectedY = endY;
    var settleUntil = now() + 60;
    frame = window.requestAnimationFrame(function settle() {
      if (now() < settleUntil) {
        frame = window.requestAnimationFrame(settle);
        return;
      }
      if (Math.abs(scrollTop() - endY) > 4) {
        cancel();
        return;
      }
      velocity = speed * 0.85;
      lastFrameTime = 0;
      expectedY = scrollTop();
      frame = window.requestAnimationFrame(step);
    });
  }

  function ignoreNextTouch() {
    ignoreStartUntil = now() + 700;
  }

  function onStart(event) {
    if (now() < ignoreStartUntil) {
      tracking = false;
      return;
    }
    /*
     * 顶部按钮在 pointerdown 就启动回顶动画；touchstart 紧随其后。
     * 这里不能再 cancel，否则手机上回顶动画刚启动就被同一根手指取消。
     */
    if (event.target && event.target.closest && event.target.closest(".site-back-top")) {
      tracking = false;
      return;
    }
    cancel();
    samples = [];
    tracking = event.touches.length === 1 && !inNestedScroller(event.target);
    if (!tracking) return;
    samples.push({
      t: event.timeStamp || now(),
      y: event.touches[0].clientY,
      scroll: scrollTop(),
    });
  }

  function onMove(event) {
    if (!tracking || event.touches.length !== 1) return;
    samples.push({
      t: event.timeStamp || now(),
      y: event.touches[0].clientY,
      scroll: scrollTop(),
    });
    if (samples.length > 12) samples.shift();
  }

  function onEnd() {
    if (!tracking) return;
    tracking = false;
    arm();
  }

  if (
    reducedMotion.matches ||
    !coarsePointer.matches ||
    typeof window.requestAnimationFrame !== "function"
  ) {
    window.ErrorInertiaScroll = {
      cancel: function () {},
      ignoreNextTouch: function () {},
      enabled: false,
      toTop: toTop,
    };
    return;
  }

  document.addEventListener("touchstart", onStart, { passive: true });
  document.addEventListener("touchmove", onMove, { passive: true });
  document.addEventListener("touchend", onEnd, { passive: true });
  document.addEventListener("touchcancel", onEnd, { passive: true });
  window.addEventListener("wheel", cancel, { passive: true });
  document.addEventListener("keydown", cancel);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) cancel();
  });

  window.ErrorInertiaScroll = {
    cancel: cancel,
    ignoreNextTouch: ignoreNextTouch,
    enabled: true,
    toTop: toTop,
  };
})();
