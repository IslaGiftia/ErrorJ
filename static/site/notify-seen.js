/* 首页左下角提醒的「已读」时机：进过对应模块页面就算已读。
 * 离开页面时才提交，页面内的卡片高亮仍然保留，逛一圈回来提醒就不见了。
 */
(function () {
  function markOnLeave(moduleName) {
    if (!moduleName) return;
    var sent = false;

    function flush() {
      if (sent) return;
      sent = true;
      try {
        fetch("/api/site/notifications/seen", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ module: moduleName }),
          cache: "no-store",
          keepalive: true,
        }).catch(function () {});
      } catch (err) {}
    }

    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) flush();
    });
  }

  var moduleName = document.body && document.body.getAttribute("data-notify-module");
  if (moduleName) markOnLeave(moduleName);

  window.ErrorNotifySeen = { markOnLeave: markOnLeave };
})();
