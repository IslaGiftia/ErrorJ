(function () {
  var themePref = "auto";
  try {
    themePref = localStorage.getItem("errorSiteTheme") || "auto";
  } catch (err) {}
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  function applyTheme(pref) {
    themePref = pref;
    var dark = pref === "dark" || (pref === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    try {
      localStorage.setItem("errorSiteTheme", pref);
    } catch (err) {}
    var glyph = document.getElementById("themeGlyph");
    if (glyph) {
      glyph.textContent = pref === "dark" ? "☾" : "☀";
    }
    var toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.setAttribute("title", "外观：" + (pref === "auto" ? "跟随系统" : pref === "dark" ? "深色" : "浅色"));
    }
  }

  var themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var next = themePref === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  }

  window.addEventListener("storage", function (event) {
    if (event.key === "errorSiteTheme" && event.newValue) {
      applyTheme(event.newValue);
    }
  });

  function syncLandingDescriptionWidth() {
    var titleText = document.getElementById("landingTitleText");
    var description = document.getElementById("landingDesc");
    if (!titleText || !description) return;
    var width = Math.ceil(titleText.getBoundingClientRect().width);
    if (width > 0) {
      description.style.maxWidth = width + "px";
    }
  }

  syncLandingDescriptionWidth();
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(syncLandingDescriptionWidth);
  }
  window.addEventListener("resize", syncLandingDescriptionWidth);

  var landingToast = document.getElementById("landingToast");
  var landingToastTimer = null;

  function showLandingToast(message) {
    if (!landingToast) return;
    landingToast.textContent = message;
    landingToast.hidden = false;
    clearTimeout(landingToastTimer);
    landingToastTimer = setTimeout(function () {
      landingToast.hidden = true;
    }, 2200);
  }

  document.querySelectorAll("[data-landing-placeholder]").forEach(function (button) {
    button.addEventListener("click", function () {
      showLandingToast(button.getAttribute("data-landing-placeholder") || "功能正在规划中");
    });
  });

  var page = document.body.getAttribute("data-page") || "home";
  document.querySelectorAll(".nav-item").forEach(function (item) {
    if (item.getAttribute("data-page") === page) {
      item.classList.add("active");
    }
  });

  applyTheme(themePref);
  window.scrollTo(0, 0);
  if (window.ErrorRain) window.ErrorRain.init();

  var authState = {
    enabled: false,
    authenticated: false,
    ready: false,
    role: "guest",
    username: "",
    owner: false,
  };
  function setText(id, text) {
    var node = document.getElementById(id);
    if (node) node.textContent = text;
  }

  function canViewModule(moduleName) {
    return authState.authenticated && authState.owner;
  }

  function setPrivateModuleState() {
    if (!canViewModule("inventory")) {
      setText("repoCount", authState.authenticated ? "仅管理员" : "登录后查看");
    }
    if (!canViewModule("bookmarks")) {
      setText("bookmarkCount", authState.authenticated ? "仅管理员" : "登录后查看");
    }
    if (!canViewModule("notes")) {
      setText("noteCount", authState.authenticated ? "仅管理员" : "登录后查看");
    }
    if (!canViewModule("workbench")) {
      setText("workbenchCount", authState.authenticated ? "仅管理员" : "登录后查看");
    }
  }

  function setAuthUi() {
    var button = document.getElementById("authStatusBtn");
    var text = document.getElementById("authStatusText");
    var menu = document.getElementById("authMenu");
    var menuUser = document.getElementById("authMenuUser");
    document.body.setAttribute("data-auth-enabled", authState.enabled ? "1" : "0");
    document.body.setAttribute("data-authenticated", authState.authenticated ? "1" : "0");
    document.body.setAttribute("data-auth-role", authState.role);
    if (!button || !text) return;
    button.classList.toggle("is-authenticated", authState.authenticated);
    if (!authState.authenticated) {
      text.textContent = "游客";
    } else if (!authState.enabled) {
      text.textContent = "本地模式";
    } else if (authState.owner) {
      text.textContent = "管理员";
    } else {
      text.textContent = authState.username || "普通用户";
    }
    if (menuUser) {
      menuUser.textContent = authState.owner
        ? (authState.enabled ? "管理员已登录" : "本地模式")
        : ("已登录：" + (authState.username || "普通用户"));
    }
    button.setAttribute(
      "aria-label",
      authState.authenticated ? "已登录，点击打开账号菜单" : "游客，点击登录"
    );
    button.setAttribute("aria-haspopup", authState.authenticated ? "menu" : "dialog");
    if (!authState.authenticated && menu) menu.hidden = true;
  }

  function openAuthModal() {
    if (!authState.enabled || authState.authenticated) return;
    var modal = document.getElementById("authModal");
    var username = document.getElementById("authUsername");
    var password = document.getElementById("authPassword");
    var error = document.getElementById("authError");
    if (!modal || !password) return;
    error.hidden = true;
    error.textContent = "";
    modal.hidden = false;
    if (username) username.value = "";
    password.value = "";
    window.setTimeout(function () {
      (username || password).focus();
    }, 0);
  }

  function closeAuthModal() {
    var modal = document.getElementById("authModal");
    if (modal) modal.hidden = true;
  }

  function renderInventoryLanding(data, parts) {
    var el = document.getElementById("repoCount");
    if (el && data && data.stats) {
      el.textContent = Number(data.stats.part_count || 0) + " 种元件";
    }
    var wrap = document.getElementById("repoThumbs");
    if (!wrap || !data || !data.stats) return;
    var count = data.stats.part_count || 0;
    wrap.innerHTML = "";
    var withImage = parts.filter(function (p) { return p.image_path; });
    for (var i = withImage.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = withImage[i];
      withImage[i] = withImage[j];
      withImage[j] = tmp;
    }
    var shown = Math.min(5, withImage.length);
    for (var k = 0; k < shown; k++) {
      var p = withImage[k];
      var thumb = document.createElement("span");
      thumb.className = "repo-thumb";
      var img = document.createElement("img");
      img.src = "/api/parts/" + p.id + "/image?v=" + encodeURIComponent(p.image_path);
      img.alt = "";
      thumb.appendChild(img);
      wrap.appendChild(thumb);
    }
    if (count > 5) {
      var extra = document.createElement("span");
      extra.className = "repo-thumb repo-count";
      extra.textContent = "+" + (count - 5);
      wrap.appendChild(extra);
    }
  }

  function renderBookmarkLanding(bookmarks) {
    setText("bookmarkCount", bookmarks.length + " 个网页");
    var wrap = document.getElementById("bookmarkThumbs");
    if (!wrap) return;
    wrap.innerHTML = "";
    var recentBookmarks = bookmarks.slice();
    for (var bi = recentBookmarks.length - 1; bi > 0; bi--) {
      var bj = Math.floor(Math.random() * (bi + 1));
      var btmp = recentBookmarks[bi];
      recentBookmarks[bi] = recentBookmarks[bj];
      recentBookmarks[bj] = btmp;
    }
    var shown = Math.min(5, recentBookmarks.length);
    for (var bk = 0; bk < shown; bk++) {
      var bookmark = recentBookmarks[bk];
      var thumb = document.createElement("span");
      thumb.className = "repo-thumb";
      var hostname = "";
      try {
        hostname = new URL(bookmark.url).hostname.replace(/^www\./i, "");
      } catch (err) {
        hostname = String(bookmark.title || "书");
      }
      var fallback = document.createElement("span");
      fallback.className = "repo-thumb-fallback";
      fallback.textContent =
        (hostname.match(/[A-Za-z0-9\u4e00-\u9fff]/) || ["书"])[0].toUpperCase();
      thumb.appendChild(fallback);
      var icon = document.createElement("img");
      icon.alt = "";
      icon.loading = "lazy";
      icon.referrerPolicy = "no-referrer";
      icon.addEventListener("load", function () {
        thumb.classList.add("has-icon");
      });
      icon.addEventListener("error", function () {
        icon.remove();
      });
      icon.src = "/api/bookmarks/" + bookmark.id + "/favicon?v=" +
        encodeURIComponent(bookmark.favicon_updated_at || "");
      thumb.appendChild(icon);
      wrap.appendChild(thumb);
    }
    if (bookmarks.length > 5) {
      var extra = document.createElement("span");
      extra.className = "repo-thumb repo-count";
      extra.textContent = "+" + (bookmarks.length - 5);
      wrap.appendChild(extra);
    }
  }

  function renderNotesLanding(notes) {
    setText("noteCount", notes.length + " 篇笔记");
    var wrap = document.getElementById("notesThumbs");
    if (!wrap) return;
    wrap.innerHTML = "";
    var shown = Math.min(5, notes.length);
    for (var i = 0; i < shown; i++) {
      var thumb = document.createElement("span");
      thumb.className = "repo-thumb";
      if (notes[i].cover_path) {
        var image = document.createElement("img");
        image.src = "/site-files/" + notes[i].cover_path;
        image.alt = "";
        image.loading = "lazy";
        thumb.appendChild(image);
      } else {
        thumb.textContent = (String(notes[i].title || "笔").match(/[A-Za-z0-9\u4e00-\u9fff]/) || ["笔"])[0];
      }
      wrap.appendChild(thumb);
    }
  }

  function renderWorkbenchLanding(workbench) {
    setText(
      "workbenchCount",
      workbench && workbench.assets ? Number(workbench.assets.total || 0) + " 项" : "工作台"
    );
  }

  function loadPrivateLandingData() {
    if (!authState.owner) return;
    var canInventory = authState.owner;
    var canBookmarks = authState.owner;
    var canOwnerModules = authState.owner;
    Promise.all([
      canInventory
        ? fetch("/api/dashboard").then(function (res) { return res.ok ? res.json() : null; }).catch(function () { return null; })
        : Promise.resolve(null),
      canInventory
        ? fetch("/api/parts").then(function (res) { return res.ok ? res.json() : []; }).catch(function () { return []; })
        : Promise.resolve([]),
      canBookmarks
        ? fetch("/api/bookmarks").then(function (res) { return res.ok ? res.json() : []; }).catch(function () { return []; })
        : Promise.resolve([]),
      canOwnerModules
        ? fetch("/api/notes?summary=1").then(function (res) { return res.ok ? res.json() : []; }).catch(function () { return []; })
        : Promise.resolve([]),
      canOwnerModules
        ? fetch("/api/workbench/summary").then(function (res) { return res.ok ? res.json() : null; }).catch(function () { return null; })
        : Promise.resolve(null),
    ]).then(function (results) {
      setPrivateModuleState();
      if (canInventory) renderInventoryLanding(results[0], results[1] || []);
      if (canBookmarks) renderBookmarkLanding(results[2] || []);
      if (canOwnerModules) {
        renderNotesLanding(results[3] || []);
        renderWorkbenchLanding(results[4]);
      }
    });
  }

  document.querySelectorAll("[data-private-module]").forEach(function (entry) {
    entry.addEventListener("click", function (event) {
      var moduleName = entry.getAttribute("data-private-module") || "";
      if (canViewModule(moduleName)) return;
      event.preventDefault();
      showLandingToast("该模块仅管理员可以访问。");
    });
  });

  var authButton = document.getElementById("authStatusBtn");
  var authMenu = document.getElementById("authMenu");
  if (authButton) {
    authButton.addEventListener("click", function (event) {
      event.stopPropagation();
      if (!authState.ready) return;
      if (authState.authenticated) {
        if (authMenu) authMenu.hidden = !authMenu.hidden;
      } else {
        openAuthModal();
      }
    });
  }

  document.addEventListener("click", function (event) {
    if (authMenu && !event.target.closest("#authMenu") && !event.target.closest("#authStatusBtn")) {
      authMenu.hidden = true;
    }
  });

  var authClose = document.getElementById("authClose");
  if (authClose) authClose.addEventListener("click", closeAuthModal);

  var authModal = document.getElementById("authModal");
  if (authModal) {
    authModal.addEventListener("click", function (event) {
      if (event.target === authModal) closeAuthModal();
    });
  }

  var authForm = document.getElementById("authForm");
  if (authForm) {
    authForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var submit = document.getElementById("authSubmit");
      var error = document.getElementById("authError");
      var username = document.getElementById("authUsername");
      var password = document.getElementById("authPassword");
      submit.disabled = true;
      error.hidden = true;
      fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username ? username.value.trim() : "",
          password: password.value,
          remember: document.getElementById("authRemember").checked,
        }),
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok) throw new Error(data.error || "登录失败");
          return data;
        });
      }).then(function (data) {
        authState.authenticated = true;
        authState.role = data.role || "member";
        authState.username = data.username || "";
        authState.owner = authState.role === "owner";
        setAuthUi();
        setPrivateModuleState();
        closeAuthModal();
        loadPrivateLandingData();
      }).catch(function (err) {
        error.textContent = err.message || "登录失败";
        error.hidden = false;
      }).then(function () {
        submit.disabled = false;
      });
    });
  }

  var logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
      fetch("/api/logout", { method: "POST" }).then(function () {
        window.location.reload();
      });
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAuthModal();
      if (authMenu) authMenu.hidden = true;
    }
  });

  setPrivateModuleState();
  setAuthUi();
  fetch("/api/auth/status", { cache: "no-store" })
    .then(function (response) { return response.json(); })
    .then(function (status) {
      authState.enabled = Boolean(status.enabled);
      authState.authenticated = Boolean(status.authenticated);
      authState.role = status.role || (authState.authenticated ? "owner" : "guest");
      authState.username = status.username || "";
      authState.owner = Boolean(status.owner) || (!status.enabled && authState.authenticated);
      authState.ready = true;
      setAuthUi();
      setPrivateModuleState();
      if (authState.authenticated) {
        loadPrivateLandingData();
      }
    })
    .catch(function () {
      authState.ready = true;
      setPrivateModuleState();
      setAuthUi();
    });
})();
