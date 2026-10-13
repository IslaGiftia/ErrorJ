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
  /*
   * 歌曲页的「返回顶部」是按内层滚动容器挂的（data-scroll-target=".mu-stage-inner"）。
   * 内嵌模式下滚动已经挪到文档本身（见 embed.css），这里在 back-to-top.js 执行前
   * 把这个标记摘掉，让它改成看文档滚动，和其它标签、以及留言 / 动态页一致。
   */
  (function dropScrollTarget() {
    var script = document.querySelector("script[data-scroll-target]");
    if (script) script.removeAttribute("data-scroll-target");
  })();
  window.ERRORJ_EMBED = true;
  window.ErrorEmbed = {
    /*
     * 子页里的编辑弹窗打开 / 关闭时通知外层推荐页：
     * 左上 4 个 + 右上 1 个悬浮按钮整体收上去 / 放下来，别压着弹窗。
     */
    notifyDialog: function (open) {
      try {
        window.parent.postMessage(
          { type: "errorj-recommend-dialog", open: Boolean(open) },
          window.location.origin
        );
      } catch (err) {}
    },
  };
})();
