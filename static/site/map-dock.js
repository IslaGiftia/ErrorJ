/*
 * 首页右下角的「足迹」入口。
 * 画面是两张静态线稿（见 map-dock.css），这里只管状态：提醒数 / 角标、
 * 「有新标记」时给入口加 .has-pending（触发细小缩放提示）、以及把链接指向最新那条未读标记。
 * 规则：有地图权限才请求 /api/map?dock=1；游客和没有权限的账号点了给提示、不跳转。
 */
(function () {
  var dock = document.getElementById("mapDock");
  var countEl = document.getElementById("mapDockCount");
  var badgeEl = document.getElementById("mapDockBadge");
  if (!dock) return;

  // 游客 / 无地图权限的账号：入口保留，但点击时提示，不进入地图页
  var dockBlocked = 0;
  var dockToastTimer = null;

  function showDockToast(message) {
    var toast = document.getElementById("dockMapToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "dockMapToast";
      toast.className = "dock-map-toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("is-visible");
    clearTimeout(dockToastTimer);
    dockToastTimer = setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 2600);
  }

  dock.addEventListener("click", function (event) {
    if (!dockBlocked) return;
    event.preventDefault();
    showDockToast(
      dockBlocked === 401
        ? "请登录后操作"
        : "当前账号没有地图权限，请联系管理员"
    );
  });

  var SEEN_KEY = "errorMapSeenPlaceId";

  var places = [];
  var serverSignedIn = false;
  var serverUnseenId = 0;
  var serverUnseenCount = 0;
  var serverNotifyIds = [];
  var serverNotifyCount = 0;

  function isRecentPlace(createdAt) {
    var text = String(createdAt || "").trim();
    if (!text) return false;
    var time = Date.parse(text.replace(" ", "T"));
    if (isNaN(time)) return false;
    return Date.now() - time <= 24 * 3600 * 1000;
  }

  function updateDockPending() {
    var newestNewId = 0;
    var newCount = 0;
    if (serverSignedIn) {
      // 登录账号：以服务端记录的「已看到标记」为准
      newestNewId = serverUnseenId;
      newCount = serverUnseenCount;
    } else {
      var seen = 0;
      try {
        seen = Number(localStorage.getItem(SEEN_KEY) || 0) || 0;
      } catch (err) {}
      places.forEach(function (place) {
        var id = Number(place.id) || 0;
        var isNew = seen > 0 ? id > seen : isRecentPlace(place.created_at);
        if (!isNew) return;
        newCount += 1;
        if (id > newestNewId) newestNewId = id;
      });
    }
    var notifiedId = serverNotifyIds.length
      ? Math.max.apply(null, serverNotifyIds)
      : 0;
    var totalCount = newCount + serverNotifyCount;
    if (!newestNewId && notifiedId) newestNewId = notifiedId;
    /*
     * 只在状态真的变了的时候动 DOM：这个函数会被高频调用（每次取数都会跑），
     * 无条件 toggle / 改 href 会让缩放提示和角标反复重绘，看起来就是「闪」。
     */
    var pending = newestNewId > 0;
    if (dock.classList.contains("has-pending") !== pending) {
      dock.classList.toggle("has-pending", pending);
    }
    var target = pending ? "/map?place=" + newestNewId : "/map";
    if (dock.getAttribute("href") !== target) dock.href = target;
    if (countEl) {
      var countText = "";
      if (totalCount > 0) countText = totalCount + " 条提醒";
      else if (places.length) countText = places.length + " 个标记";
      if (countEl.textContent !== countText) countEl.textContent = countText;
      var hideCount = !countText;
      if (countEl.hidden !== hideCount) countEl.hidden = hideCount;
    }
    if (badgeEl) {
      var badgeText = totalCount > 0 ? (totalCount > 99 ? "99+" : String(totalCount)) : "";
      if (badgeEl.textContent !== badgeText) badgeEl.textContent = badgeText;
      var hideBadge = !badgeText;
      if (badgeEl.hidden !== hideBadge) badgeEl.hidden = hideBadge;
    }
    window.dispatchEvent(
      new CustomEvent("errordockstats", {
        detail: {
          places: places.length,
          newPlaces: newCount,
          notifications: serverNotifyCount
        }
      })
    );
  }

  var mapRequestSerial = 0;
  // /api/auth/status 回来之前先别发请求：游客在「地图不公开」的站点上必然 401，
  // 白跑一次请求还会在控制台留一条红字。auth 事件一定会来，另加 2 秒兜底。
  var authKnown = false;
  var guestMapDenied = false;

  function applyDockBlocked(status) {
    if (status) {
      // 入口和 HUD 保留；点击入口时给出注册 / 权限提示
      dockBlocked = status;
      dock.classList.remove("has-pending");
      dock.href = "/map";
      serverNotifyIds = [];
      serverNotifyCount = 0;
    }
    if (countEl) countEl.hidden = true;
    if (badgeEl) badgeEl.hidden = true;
  }

  function loadMapData() {
    if (!authKnown) return;
    if (guestMapDenied) {
      applyDockBlocked(401);
      return;
    }
    var requestId = ++mapRequestSerial;
    fetch("/api/map?dock=1", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          var error = new Error("map api " + response.status);
          error.status = response.status;
          throw error;
        }
        return response.json();
      })
      .then(function (data) {
        if (requestId !== mapRequestSerial) return;
        dockBlocked = 0;
        places = data.places || [];
        serverSignedIn = Boolean(data.signed_in);
        serverUnseenId = Number(data.newest_unseen_id) || 0;
        serverUnseenCount = Number(data.unseen_count) || 0;
        serverNotifyIds = Array.isArray(data.notify_targets)
          ? data.notify_targets.map(Number).filter(function (id) { return id > 0; })
          : [];
        serverNotifyCount = Number(data.notify_count) || serverNotifyIds.length;
        updateDockPending();
      })
      .catch(function (err) {
        if (requestId !== mapRequestSerial) return;
        var status = err && err.status;
        if (status === 401 || status === 403) {
          applyDockBlocked(status);
          return;
        }
        /*
         * 网络抖动 / 5xx：保留上一次的角标和文案，别把入口清空。
         */
      });
  }

  window.addEventListener("errorauthchange", function (event) {
    var detail = (event && event.detail) || {};
    authKnown = true;
    guestMapDenied = !detail.authenticated && detail.mapDockAllowed === false;
    loadMapData();
  });
  window.addEventListener("pageshow", loadMapData);
  window.addEventListener("storage", function (event) {
    if (event.key === "errorMapDockRefresh") loadMapData();
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) loadMapData();
  });
  window.setTimeout(function () {
    // 登录状态接口没回来（异常 / 老版本）时也要能加载，别把入口卡死
    if (authKnown) return;
    authKnown = true;
    loadMapData();
  }, 2000);
  // 正常情况下这次调用什么都不做（要等 auth 结果），留着是为了脚本顺序变化时也能自愈
  loadMapData();
})();
