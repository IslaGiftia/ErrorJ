(function () {
  "use strict";

  var MAX_DAYS = 999999;
  var tooltip = null;

  function parse(value) {
    var text = String(value || "");
    var match = text.match(
      /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/
    );
    if (!match) return null;
    var date = new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      Number(match[6] || 0)
    );
    return isNaN(date.getTime())
      ? null
      : {
          date: date,
          stamp:
            match[1] +
            "-" +
            match[2] +
            "-" +
            match[3] +
            " " +
            match[4] +
            ":" +
            match[5] +
            (match[6] ? ":" + match[6] : ""),
        };
  }

  function format(value) {
    var parsed = parse(value);
    if (!parsed) return String(value || "");
    var seconds = Math.max(
      0,
      Math.round((Date.now() - parsed.date.getTime()) / 1000)
    );
    if (seconds < 60) return "刚刚";
    if (seconds < 3600) return Math.round(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.round(seconds / 3600) + " 小时前";
    var days = Math.max(1, Math.floor(seconds / 86400));
    return Math.min(MAX_DAYS, days) + " 天前";
  }

  function stamp(value) {
    var parsed = parse(value);
    return parsed ? parsed.stamp : String(value || "");
  }

  function ensureTooltip() {
    if (tooltip) return tooltip;
    tooltip = document.createElement("div");
    tooltip.className = "error-relative-time-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function placeTooltip(node) {
    var tip = ensureTooltip();
    var rect = node.getBoundingClientRect();
    tip.style.left = "0px";
    tip.style.top = "0px";
    tip.hidden = false;
    var tipRect = tip.getBoundingClientRect();
    var left = rect.left + rect.width / 2 - tipRect.width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
    var top = rect.top - tipRect.height - 8;
    if (top < 8) top = rect.bottom + 8;
    tip.style.left = Math.round(left) + "px";
    tip.style.top = Math.round(top) + "px";
  }

  function showTooltip(node) {
    if (!node || !node.dataset.exactTime) return;
    var tip = ensureTooltip();
    tip.textContent = node.dataset.exactTime;
    placeTooltip(node);
  }

  function hideTooltip() {
    if (tooltip) tooltip.hidden = true;
  }

  function attach(node, value) {
    if (!node) return node;
    var exact = stamp(value);
    if (!exact) return node;
    node.classList.add("relative-time");
    node.dataset.exactTime = exact;
    node.tabIndex = 0;
    node.setAttribute("aria-label", format(value) + "，具体时间 " + exact);
    return node;
  }

  function render(node, value) {
    if (!node) return node;
    node.textContent = format(value);
    return attach(node, value);
  }

  document.addEventListener("mouseover", function (event) {
    var target =
      event.target && event.target.closest
        ? event.target.closest(".relative-time")
        : null;
    if (target) showTooltip(target);
  });
  document.addEventListener("mouseout", function (event) {
    var target =
      event.target && event.target.closest
        ? event.target.closest(".relative-time")
        : null;
    if (!target) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    hideTooltip();
  });
  document.addEventListener("focusin", function (event) {
    var target =
      event.target && event.target.closest
        ? event.target.closest(".relative-time")
        : null;
    if (target) showTooltip(target);
  });
  document.addEventListener("focusout", hideTooltip);
  window.addEventListener("resize", hideTooltip);
  window.addEventListener("scroll", hideTooltip, true);

  window.ErrorRelativeTime = {
    MAX_DAYS: MAX_DAYS,
    format: format,
    stamp: stamp,
    attach: attach,
    render: render,
    hide: hideTooltip,
  };
})();
