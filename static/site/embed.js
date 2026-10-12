/*
 * 推荐页内嵌模式：页面带 ?embed=1 打开时，只保留内容本身，
 * 由推荐页左上角的常驻按钮和右上角的「新增」按钮提供标题与操作，避免重复。
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
