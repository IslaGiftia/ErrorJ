/*
 * 推荐页子页共用：右下角「顶部」按钮的「有新内容」形态（和留言、动态页同一套逻辑）。
 *
 * 页面自己声明配置后加载本文件：
 *   window.ERRORJ_JUMP = { label: "歌曲", scroll: ".mu-stage-inner" };
 * label 是按钮下方的文案（歌曲 / 书籍 / 推荐），scroll 是可选的滚动容器选择器
 * （歌曲页的列表在 .mu-stage-inner 里滚，不传就用窗口滚动）。
 *
 * 逻辑：有新内容（.is-fresh，由 ErrorFreshCards 打标）还在视口下方时，
 * 按钮变成「↓ 歌曲」并呼吸；点它平滑滚到那条新内容。没有新内容时恢复普通「↑ 顶部」。
 */
(function () {
  "use strict";

  if (!window.ERRORJ_EMBED) return;

  var config = window.ERRORJ_JUMP || {};
  var label = String(config.label || "新内容");
  var container = null;
  try {
    container = config.scroll ? document.querySelector(config.scroll) : null;
  } catch (err) {
    container = null;
  }

  var lastNode;
  var frame = null;

  function backTopApi() {
    return window.ErrorBackToTop && window.ErrorBackToTop.setPending
      ? window.ErrorBackToTop
      : null;
  }

  function viewportBottom() {
    if (!container) return window.innerHeight;
    return container.getBoundingClientRect().bottom;
  }

  // 第一条「还在视口下方」的新内容：它就是按钮要跳过去的目标
  function freshBelow() {
    var nodes = document.querySelectorAll(".is-fresh");
    var limit = viewportBottom() - 80;
    for (var i = 0; i < nodes.length; i += 1) {
      if (nodes[i].getBoundingClientRect().top > limit) return nodes[i];
    }
    return null;
  }

  function jumpTo(node) {
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function update() {
    var api = backTopApi();
    if (!api) return;
    var node = freshBelow();
    if (node === lastNode) return;
    lastNode = node;
    if (node) {
      api.setPending({
        active: true,
        label: label,
        title: "跳到新" + label,
        onActivate: function () {
          jumpTo(freshBelow() || node);
        },
      });
    } else {
      api.setPending({ active: false });
    }
    document.dispatchEvent(new CustomEvent("errorjumpvisibilitychange"));
  }

  function schedule() {
    if (frame) return;
    frame = window.requestAnimationFrame(function () {
      frame = null;
      update();
    });
  }

  (container || window).addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);

  window.ErrorFreshJump = { refresh: update, schedule: schedule };
})();
