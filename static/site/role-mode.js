(function () {
  "use strict";

  function showReadonlyMessage() {
    if (document.querySelector(".readonly-banner")) return;
    var banner = document.createElement("div");
    banner.className = "readonly-banner";
    banner.textContent = "当前为只读账号：可以查看仓库和网页收藏，不能修改内容。";
    document.body.insertBefore(banner, document.body.firstChild);
  }

  function installInventoryGuard() {
    var allowed = new Set(["part-detail", "project-detail", "bom-view"]);
    document.addEventListener("click", function (event) {
      var action = event.target.closest("[data-action]");
      if (!action || allowed.has(action.getAttribute("data-action") || "")) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      event.stopPropagation();
      showReadonlyMessage();
    }, true);
  }

  function installBookmarkGuard() {
    ["dragover", "drop"].forEach(function (name) {
      document.addEventListener(name, function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }, true);
    });
  }

  fetch("/api/auth/status", { cache: "no-store" })
    .then(function (response) { return response.json(); })
    .then(function (status) {
      var role = status.role || "guest";
      document.documentElement.setAttribute("data-auth-role", role);
      if (role !== "member") return;
      showReadonlyMessage();
      installInventoryGuard();
      installBookmarkGuard();
    })
    .catch(function () {});
})();
