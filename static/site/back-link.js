/*
 * 游戏页的“返回”链接：能确定是从上一级页面点进来的，就真的调用浏览器后退，
 * 否则用 location.replace 直接跳到上一级页面。
 *
 * 两种方式都**不会新增历史记录**，避免出现“返回大厅 → 返回首页 → 再点返回又回到大厅”
 * 这种历史栈里堆着一串返回页的情况。
 */
(function () {
  "use strict";

  function parentPath(link) {
    return link.getAttribute("data-back-parent") || "/games";
  }

  function cameFrom(expected) {
    try {
      var referrer = document.referrer;
      if (!referrer) return false;
      var url = new URL(referrer);
      if (url.origin !== location.origin) return false;
      var path = url.pathname;
      if (expected === "/") return path === "/" || path === "/index.html";
      return path === expected || path.indexOf(expected + "/") === 0;
    } catch (err) {
      return false;
    }
  }

  document.querySelectorAll("[data-back]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
      var expected = parentPath(link);
      event.preventDefault();
      if (window.history.length > 1 && cameFrom(expected)) {
        window.history.back();
      } else {
        window.location.replace(expected);
      }
    });
  });
})();
