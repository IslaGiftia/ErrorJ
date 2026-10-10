/*
 * 图片查看器的双击放大。
 * 电脑端双击图片放大到 2 倍，手机端连点两下同样放大，再双击/双点还原。
 * 放大后不是简单缩放，而是把图片真实撑大，交给外层容器滚动，
 * 手机上可以直接用手指拖着看细节。
 */
(function () {
  var ZOOM_SCALE = 2;
  var DOUBLE_TAP_MS = 320;
  var DOUBLE_TAP_DIST = 32;

  function clearZoom(image) {
    image.classList.remove("is-zoomed");
    image.style.width = "";
    image.style.height = "";
    image.style.maxWidth = "";
    image.style.maxHeight = "";
  }

  function zoomAt(container, image, clientX, clientY) {
    var cRect = container.getBoundingClientRect();
    var iRect = image.getBoundingClientRect();
    // 双击点在滚动内容里的位置，放大后把它保持在原来的屏幕位置
    var localX = clientX - cRect.left + container.scrollLeft;
    var localY = clientY - cRect.top + container.scrollTop;
    var anchorX = clientX - cRect.left;
    var anchorY = clientY - cRect.top;
    image.style.width = Math.round(iRect.width * ZOOM_SCALE) + "px";
    image.style.height = "auto";
    image.style.maxWidth = "none";
    image.style.maxHeight = "none";
    image.classList.add("is-zoomed");
    container.scrollLeft = localX * ZOOM_SCALE - anchorX;
    container.scrollTop = localY * ZOOM_SCALE - anchorY;
  }

  function toggleZoom(container, image, clientX, clientY) {
    if (image.classList.contains("is-zoomed")) {
      clearZoom(image);
      container.scrollLeft = 0;
      container.scrollTop = 0;
      return;
    }
    zoomAt(container, image, clientX, clientY);
  }

  /*
   * container：可滚动的图片容器；image：容器里的 <img>。
   * 手机端要自己识别「双击」，不然 iOS / 安卓会当成双击缩放整页。
   */
  function bind(container, image) {
    if (!container || !image) return;
    var lastTapAt = 0;
    var lastX = 0;
    var lastY = 0;
    var suppressDblclickUntil = 0;

    image.addEventListener("dblclick", function (event) {
      if (Date.now() < suppressDblclickUntil) return;
      event.preventDefault();
      toggleZoom(container, image, event.clientX, event.clientY);
    });

    image.addEventListener(
      "touchend",
      function (event) {
        var touch = event.changedTouches && event.changedTouches[0];
        if (!touch) return;
        var now = Date.now();
        var near =
          Math.abs(touch.clientX - lastX) < DOUBLE_TAP_DIST &&
          Math.abs(touch.clientY - lastY) < DOUBLE_TAP_DIST;
        if (now - lastTapAt < DOUBLE_TAP_MS && near) {
          lastTapAt = 0;
          suppressDblclickUntil = now + 600;
          event.preventDefault();
          toggleZoom(container, image, touch.clientX, touch.clientY);
          return;
        }
        lastTapAt = now;
        lastX = touch.clientX;
        lastY = touch.clientY;
      },
      { passive: false }
    );
  }

  window.ErrorImageZoom = { bind: bind };
})();
