/*
 * 图片查看器：双击 / 双指放大后可以继续缩放和平移。
 * - 电脑：双击放大，滚轮缩放，放大后按住鼠标拖动平移；
 * - 手机：双击放大，双指捏合缩放，放大后单指拖动平移（走容器原生滚动）。
 * 放大用的是「真实尺寸 + 外层容器滚动」，不用 transform，
 * 这样和浏览器自带的手势、滚动条都不打架。
 */
(function () {
  var MIN_SCALE = 1;
  var MAX_SCALE = 5;
  var DOUBLE_TAP_MS = 320;
  var DOUBLE_TAP_DIST = 32;
  var WHEEL_FACTOR = 0.0018;
  var PINCH_MIN_STEP = 0.02;

  function baseSize(image) {
    if (!image._ezBase) {
      var rect = image.getBoundingClientRect();
      image._ezBase = {
        w: rect.width || image.naturalWidth || 1,
        h: rect.height || image.naturalHeight || 1
      };
    }
    return image._ezBase;
  }

  function scaleOf(image) {
    return Number(image._ezScale || 1);
  }

  /*
   * 以 (clientX, clientY) 为锚点缩放到 scale 倍：
   * 锚点在屏幕上的位置保持不变，缩放感才自然。scale <= 1 就是还原。
   */
  function applyScale(container, image, scale, clientX, clientY) {
    var clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
    var before = image.getBoundingClientRect();
    var ratioX = before.width ? (clientX - before.left) / before.width : 0.5;
    var ratioY = before.height ? (clientY - before.top) / before.height : 0.5;
    image._ezScale = clamped;
    if (clamped <= MIN_SCALE + 0.001) {
      image.style.width = "";
      image.style.height = "";
      image.style.maxWidth = "";
      image.style.maxHeight = "";
      image.classList.remove("is-zoomed");
      container.scrollLeft = 0;
      container.scrollTop = 0;
      return;
    }
    var base = baseSize(image);
    image.style.width = Math.round(base.w * clamped) + "px";
    image.style.height = "auto";
    image.style.maxWidth = "none";
    image.style.maxHeight = "none";
    image.classList.add("is-zoomed");
    var after = image.getBoundingClientRect();
    container.scrollLeft += after.left + ratioX * after.width - clientX;
    container.scrollTop += after.top + ratioY * after.height - clientY;
  }

  function bind(container, image) {
    if (!container || !image) return;

    var lastTapAt = 0;
    var lastX = 0;
    var lastY = 0;
    var suppressDblclickUntil = 0;
    var drag = null;
    var pinch = null;

    function zoomed() {
      return scaleOf(image) > MIN_SCALE + 0.001;
    }

    /* ---- 双击 / 双点 ---- */
    image.addEventListener("dblclick", function (event) {
      if (Date.now() < suppressDblclickUntil) return;
      event.preventDefault();
      applyScale(
        container,
        image,
        zoomed() ? MIN_SCALE : 2,
        event.clientX,
        event.clientY
      );
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
          applyScale(
            container,
            image,
            zoomed() ? MIN_SCALE : 2,
            touch.clientX,
            touch.clientY
          );
          return;
        }
        lastTapAt = now;
        lastX = touch.clientX;
        lastY = touch.clientY;
      },
      { passive: false }
    );

    /* ---- 电脑：滚轮缩放 ---- */
    container.addEventListener(
      "wheel",
      function (event) {
        event.preventDefault();
        var next = scaleOf(image) * Math.exp(-event.deltaY * WHEEL_FACTOR);
        applyScale(container, image, next, event.clientX, event.clientY);
      },
      { passive: false }
    );

    /* ---- 电脑：按住拖动平移 ---- */
    image.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || !zoomed()) return;
      event.preventDefault();
      drag = { x: event.clientX, y: event.clientY };
      container.classList.add("is-panning");
    });
    window.addEventListener("mousemove", function (event) {
      if (!drag) return;
      container.scrollLeft -= event.clientX - drag.x;
      container.scrollTop -= event.clientY - drag.y;
      drag.x = event.clientX;
      drag.y = event.clientY;
    });
    window.addEventListener("mouseup", function () {
      drag = null;
      container.classList.remove("is-panning");
    });

    /* ---- 手机：双指捏合缩放（单指平移交给容器原生滚动） ---- */
    function touchDistance(touches) {
      var dx = touches[0].clientX - touches[1].clientX;
      var dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy) || 1;
    }

    container.addEventListener(
      "touchstart",
      function (event) {
        if (event.touches.length !== 2) return;
        pinch = {
          distance: touchDistance(event.touches),
          scale: scaleOf(image)
        };
        lastTapAt = 0;
      },
      { passive: true }
    );

    container.addEventListener(
      "touchmove",
      function (event) {
        if (!pinch) {
          if (event.touches.length === 2) {
            pinch = {
              distance: touchDistance(event.touches),
              scale: scaleOf(image)
            };
          }
          return;
        }
        if (event.touches.length !== 2) return;
        event.preventDefault();
        var ratio = touchDistance(event.touches) / pinch.distance;
        var next = pinch.scale * ratio;
        if (Math.abs(next - scaleOf(image)) < PINCH_MIN_STEP) return;
        var midX = (event.touches[0].clientX + event.touches[1].clientX) / 2;
        var midY = (event.touches[0].clientY + event.touches[1].clientY) / 2;
        if (next <= MIN_SCALE) {
          pinch = null;
          applyScale(container, image, MIN_SCALE, midX, midY);
          return;
        }
        applyScale(container, image, next, midX, midY);
      },
      { passive: false }
    );

    ["touchend", "touchcancel"].forEach(function (name) {
      container.addEventListener(name, function (event) {
        if (event.touches && event.touches.length < 2) pinch = null;
      });
    });
  }

  window.ErrorImageZoom = { bind: bind };
})();
