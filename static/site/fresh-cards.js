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

  function clear(node, targetId) {
    var targetKey = key(targetId);
    if (!targets[targetKey]) return;
    delete targets[targetKey];
    node.classList.remove("is-fresh");
    requestSeen(targetId);
  }

  function isFresh(targetId) {
    return Boolean(targets[key(targetId)]);
  }

  function mark(node, targetId) {
    if (!node || !isFresh(targetId)) return;
    node.classList.add("is-fresh");
    node.addEventListener(
      "mouseenter",
      function () {
        clear(node, targetId);
      },
      { once: true }
    );
    node.addEventListener(
      "click",
      function () {
        clear(node, targetId);
      },
      { once: true }
    );
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
  };
})();
