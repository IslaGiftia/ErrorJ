(function () {
  "use strict";

  var moduleName = document.body.getAttribute("data-notify-module") || "";
  if (!moduleName) return;

  var targets = {};
  var loading = null;

  function key(value) {
    return String(value);
  }

  function requestSeen(targetId) {
    fetch("/api/site/notifications/seen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: moduleName, target_id: targetId }),
      cache: "no-store",
    }).catch(function () {});
  }

  function notifyParent() {
    if (!window.ERRORJ_EMBED) return;
    try {
      window.parent.postMessage(
        { type: "errorj-notification-seen", module: moduleName },
        window.location.origin
      );
    } catch (err) {}
  }

  function clear(node, targetId) {
    var targetKey = key(targetId);
    if (!targets[targetKey]) return;
    delete targets[targetKey];
    node.classList.remove("is-fresh");
    if (window.ErrorFreshVisibility) window.ErrorFreshVisibility.unwatch(node);
    requestSeen(targetId);
    notifyParent();
  }

  function isFresh(targetId) {
    return Boolean(targets[key(targetId)]);
  }

  function mark(node, targetId) {
    if (!node || !isFresh(targetId)) return;
    node.classList.add("is-fresh");
    if (window.ErrorFreshVisibility) {
      window.ErrorFreshVisibility.watch(node, function () {
        clear(node, targetId);
      });
    }
  }

  function load() {
    if (loading) return loading;
    loading = fetch(
      "/api/site/notifications/unread?module=" + encodeURIComponent(moduleName),
      { cache: "no-store" }
    )
      .then(function (response) {
        return response.ok ? response.json() : { targets: [] };
      })
      .then(function (data) {
        targets = {};
        (Array.isArray(data.targets) ? data.targets : []).forEach(function (id) {
          targets[key(id)] = true;
        });
      })
      .catch(function () {
        targets = {};
      })
      .then(function () {
        loading = null;
      });
    return loading;
  }

  window.ErrorFreshCards = {
    load: load,
    isFresh: isFresh,
    mark: mark,
    reset: function () {
      if (window.ErrorFreshVisibility) window.ErrorFreshVisibility.reset();
    },
  };
})();
