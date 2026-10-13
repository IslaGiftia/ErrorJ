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
