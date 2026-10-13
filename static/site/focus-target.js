/*
 * 「点更新日志 → 跳到这条内容」的通用入口。
 *
 * 目标页加载本文件后注册一个「按 id 找卡片」的函数：
 *   window.ErrorFocus.register(function (id) {
 *     return document.querySelector('[data-focus-id="' + id + '"]');
 *   });
 *
 * 之后本文件会：
 *   1. 读地址栏的 ?focus=<id>（地图页是 ?place=<id>，页面自己传 id 进来）；
 *   2. 也接受推荐页外壳发来的 postMessage（{type:"errorj-focus", id}），
 *      这样在推荐页原地切标签时不用重新加载 iframe；
 *   3. 找到卡片后给它打上 .is-fresh（呼吸闪烁，鼠标移入或点击后清除），
 *      并把右下角「顶部」按钮切成「↓ 更新」+ 呼吸，点它平滑滚到这条内容。
 */
(function () {
  "use strict";

  // 默认就是按 data-focus-id 找（各页面的卡片都带这个属性，页面也可以自己 register 覆盖）
  function defaultFind(id) {
    return document.querySelector('[data-focus-id="' + id + '"]');
  }

  var finder = defaultFind;
  var current = null;

  function params() {
    try {
      return new URLSearchParams(location.search);
    } catch (err) {
      return null;
    }
  }

  function focusId() {
    var search = params();
    if (!search) return 0;
    var id = Number(search.get("focus") || search.get("place") || 0) || 0;
    return id;
  }

  function clearPending() {
    var api = window.ErrorBackToTop;
    if (api && api.setPending) api.setPending({ active: false });
    current = null;
    window.ERRORJ_FOCUS_ACTIVE = false;
    // 交回给「有新内容就跳过去」那套逻辑
    document.dispatchEvent(new CustomEvent("errorjumpvisibilitychange"));
  }

  function render(id) {
    if (!id) return;
    var node = null;
    try {
      node = (finder || defaultFind)(id);
    } catch (err) {
      node = null;
    }
    if (!node) return;
    current = node;
    node.classList.add("is-fresh");
    // 按钮文案统一成「更新」（fresh-jump.js 会读这个覆盖值）
    window.ERRORJ_JUMP_LABEL = "更新";
    // 高亮期间按钮由本文件负责，通知驱动的那套先让开
    window.ERRORJ_FOCUS_ACTIVE = true;

    var cleared = false;
    function clear() {
      if (cleared) return;
      cleared = true;
      node.classList.remove("is-fresh");
      clearPending();
    }
    node.addEventListener("mouseenter", clear, { once: true });
    node.addEventListener("click", clear, { once: true });

    var api = window.ErrorBackToTop;
    if (api && api.setPending) {
      api.setPending({
        active: true,
        label: "更新",
        title: "跳到更新的内容",
        onActivate: function () {
          clear();
          try {
            node.scrollIntoView({ behavior: "smooth", block: "center" });
          } catch (err) {
            node.scrollIntoView();
          }
        },
      });
    }
  }

  window.ErrorFocus = {
    register: function (fn) {
      finder = fn;
      render(focusId());
    },
    // 页面渲染完卡片之后再调一次（首次渲染时卡片可能还不存在）
    apply: function (id) {
      render(Number(id) || focusId());
    },
    clear: clearPending,
  };

  window.addEventListener("message", function (event) {
    if (event.origin !== location.origin) return;
    var data = event.data || {};
    if (data.type !== "errorj-focus") return;
    render(Number(data.id) || 0);
  });
})();
