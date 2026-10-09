(function () {
  "use strict";

  var moduleName = document.body.getAttribute("data-notify-module") || "";
  if (!moduleName) return;

  fetch("/api/site/notifications/seen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module: moduleName }),
    cache: "no-store",
  }).catch(function () {});
})();
