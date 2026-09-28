/*
 * 标签页复用：页面通过 <meta name="tab-name" content="ej-xxx"> 认领一个名字，
 * 首页对应卡片的链接写成 target="ej-xxx"，再次点击就会切回已打开的那个标签页，
 * 而不是新开一个（浏览器会重新导航一次，等于刷新那页）。
 *
 * 离开本页时把名字清掉，避免这个标签页后来打开别的页面还占着这个名字。
 * 注意：链接上不能带 rel="noopener"，否则浏览器会忽略具名 target。
 */
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="tab-name"]');
  var tabName = meta && meta.getAttribute("content");
  if (!tabName) return;

  function claim() {
    try {
      window.name = tabName;
    } catch (err) {}
  }

  function release() {
    try {
      window.name = "";
    } catch (err) {}
  }

  claim();
  window.addEventListener("pagehide", release);
  window.addEventListener("pageshow", claim);
})();
