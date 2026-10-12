/*
 * 下载页内嵌模式：页面带 ?embed=1 打开时，只保留内容本身，
 * 由下载页的 Tab 条提供标题与返回入口，避免和页面自带品牌条重复。
 */
(function () {
  "use strict";

  var embed = false;
  try {
    embed = new URLSearchParams(location.search).get("embed") === "1";
  } catch (err) {
    embed = false;
  }
  if (!embed) return;

  document.documentElement.classList.add("is-embed");
  window.ERRORJ_EMBED = true;
})();
