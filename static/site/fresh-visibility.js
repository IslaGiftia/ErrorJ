(function () {
  "use strict";

  if (window.ErrorFreshVisibility) return;

  var READ_PULSES = 3;
  var PULSE_MS = 3600;
  var reducedMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false };
  var entries = new Map();
  var observer = null;
  var checkFrame = 0;
  var pageVisible = !document.hidden;

  function embeddedActive() {
    if (!window.ERRORJ_EMBED) return true;
    try {
      var frame = window.frameElement;
      var panel = frame && frame.closest(".dl-panel");
      return panel ? panel.classList.contains("is-active") : false;
    } catch (err) {
      return false;
    }
  }

  var active = embeddedActive();

  function isVisible(node) {
    if (!node || !node.isConnected) return false;
    var rect = node.getBoundingClientRect();
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.top < window.innerHeight - 80
    );
  }

  function stopTimer(entry) {
    if (!entry.timer) return;
    window.clearTimeout(entry.timer);
    entry.timer = 0;
  }

  function startRead(entry) {
    entry.visible = isVisible(entry.node);
    if (!active || !pageVisible || !entry.visible || entry.timer || entry.done) {
      return;
    }
    entry.node.classList.remove("is-fresh");
    void entry.node.offsetWidth;
    entry.node.classList.add("is-fresh");
    var delay = reducedMotion.matches ? 900 : READ_PULSES * PULSE_MS + 80;
    entry.timer = window.setTimeout(function () {
      entry.timer = 0;
      entry.done = true;
      if (observer) observer.unobserve(entry.node);
      entries.delete(entry.node);
      entry.onRead();
    }, delay);
  }

  function stopRead(entry) {
    stopTimer(entry);
  }

  function reset() {
    entries.forEach(function (entry) {
      stopRead(entry);
      if (observer) observer.unobserve(entry.node);
    });
    entries.clear();
    if (observer) observer.disconnect();
    observer = createObserver();
  }

  function createObserver() {
    if (typeof window.IntersectionObserver !== "function") return null;
    return new IntersectionObserver(
      function (records) {
        records.forEach(function (record) {
          var entry = entries.get(record.target);
          if (!entry) return;
          entry.visible =
            record.isIntersecting && isVisible(record.target);
          if (active && pageVisible && entry.visible) startRead(entry);
          else stopRead(entry);
        });
      },
      { threshold: 0, rootMargin: "0px 0px -80px 0px" }
    );
  }

  function checkAll() {
    entries.forEach(function (entry) {
      entry.visible = isVisible(entry.node);
      if (active && pageVisible && entry.visible) startRead(entry);
      else stopRead(entry);
    });
  }

  function scheduleCheck() {
    if (checkFrame) return;
    var raf =
      window.requestAnimationFrame || function (callback) {
        return window.setTimeout(callback, 16);
      };
    checkFrame = raf(function () {
      checkFrame = 0;
      checkAll();
    });
  }

  function watch(node, onRead) {
    if (!node || typeof onRead !== "function") return;
    var entry = entries.get(node);
    if (entry) {
      entry.onRead = onRead;
      return;
    }
    entry = {
      node: node,
      onRead: onRead,
      visible: isVisible(node),
      timer: 0,
      done: false,
    };
    entries.set(node, entry);
    if (observer) observer.observe(node);
    if (active && pageVisible && entry.visible) startRead(entry);
  }

  function unwatch(node) {
    var entry = entries.get(node);
    if (!entry) return;
    stopRead(entry);
    if (observer) observer.unobserve(node);
    entries.delete(node);
  }

  function setActive(value) {
    active = Boolean(value);
    if (!active) {
      entries.forEach(stopRead);
      return;
    }
    checkAll();
  }

  observer = createObserver();
  document.addEventListener("scroll", scheduleCheck, { capture: true, passive: true });
  window.addEventListener("resize", scheduleCheck);
  document.addEventListener("visibilitychange", function () {
    pageVisible = !document.hidden;
    if (!pageVisible) entries.forEach(stopRead);
    else checkAll();
  });
  window.addEventListener(
    "message",
    function (event) {
      if (event.origin !== window.location.origin) return;
      var data = event.data;
      if (!data || data.type !== "errorj-recommend-visibility") return;
      setActive(data.active);
    },
    false
  );
  window.addEventListener("pageshow", function () {
    setActive(embeddedActive());
  });

  window.ErrorFreshVisibility = {
    watch: watch,
    unwatch: unwatch,
    reset: reset,
    setActive: setActive,
    isVisible: isVisible,
  };
})();
