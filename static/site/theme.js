/*
 * 全站主题同步：现在只有首页保留浅色/暗色切换按钮，
 * 这里负责让其它已打开的页面跟着一起变（监听 localStorage 的 storage 事件）。
 * 各页面自己的启动脚本仍然会在加载时直接应用一次，避免闪白。
 */
(function () {
  "use strict";

  var KEY = "errorSiteTheme";

  /*
   * 按钮反馈层是全站外壳的一部分。theme.js 已在所有内容页加载，
   * 这里统一补一次脚本，避免十几个 HTML 各抄一行、后续新增页面漏掉。
   * login.html 没有引用 theme.js，单独引入该脚本。
   */
  (function loadButtonEffects() {
    if (window.ErrorButtons || document.querySelector("script[data-button-effects]")) return;
    var script = document.createElement("script");
    script.src = "/static/site/button-effects.js";
    script.defer = true;
    script.setAttribute("data-button-effects", "");
    document.head.appendChild(script);
  })();

  function applyTheme() {
    try {
      var pref = localStorage.getItem(KEY) || "auto";
      var dark =
        pref === "dark" ||
        (pref === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    } catch (err) {}
  }

  window.ErrorTheme = { key: KEY, apply: applyTheme };

  window.addEventListener("storage", function (event) {
    if (!event.key || event.key === KEY) applyTheme();
  });

  if (window.matchMedia) {
    var query = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      try {
        if ((localStorage.getItem(KEY) || "auto") === "auto") applyTheme();
      } catch (err) {}
    };
    if (query.addEventListener) query.addEventListener("change", onChange);
    else if (query.addListener) query.addListener(onChange);
  }
})();
