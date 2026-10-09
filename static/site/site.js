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
    nickname: "",
    owner: false,
    admin: false,
    permissions: [],
  };
  function setText(id, text) {
    var node = document.getElementById(id);
    if (node) node.textContent = text;
  }

  function canViewModule(moduleName) {
    if (!authState.authenticated) return false;
    if (authState.owner || authState.admin) return true;
    if (moduleName === "workbench") return false;
    return (
      authState.permissions.indexOf(moduleName + ":view") >= 0 ||
      authState.permissions.indexOf(moduleName + ":write") >= 0
    );
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
      text.textContent = authState.nickname || authState.username || "普通用户";
    }
    if (menuUser) {
      menuUser.textContent = authState.owner
        ? (authState.enabled ? "管理员已登录" : "本地模式")
        : ("已登录：" + (authState.nickname || authState.username || "普通用户"));
    }
    var nicknameBtn = document.getElementById("nicknameBtn");
    if (nicknameBtn) {
      nicknameBtn.hidden = !authState.authenticated || authState.owner;
    }
    button.setAttribute(
      "aria-label",
      authState.authenticated ? "已登录，点击打开账号菜单" : "游客，点击登录"
    );
    button.setAttribute("aria-haspopup", authState.authenticated ? "menu" : "dialog");
    if (!authState.authenticated && menu) menu.hidden = true;
  }

  function applyPendingBadge(count) {
    var entry = document.querySelector('.repo-entry[href="/workbench"]');
    var badge = document.getElementById("workbenchPending");
    var value = Number(count) || 0;
    if (entry) entry.classList.toggle("has-pending", value > 0);
    if (badge) {
      badge.hidden = value <= 0;
      badge.textContent = value > 99 ? "99+" : String(value);
    }
  }

  function applyMessagesBadge(count) {
    var entry = document.getElementById("messagesEntry");
    var badge = document.getElementById("messagesPending");
    var value = Number(count) || 0;
    if (entry) entry.classList.toggle("has-pending", value > 0);
    if (badge) {
      badge.hidden = value <= 0;
      badge.textContent = value > 99 ? "99+" : String(value);
    }
  }

  function applyMomentsBadge(count) {
    var entry = document.getElementById("momentsEntry");
    var badge = document.getElementById("momentsPending");
    var value = Number(count) || 0;
    if (entry) entry.classList.toggle("has-pending", value > 0);
    if (badge) {
      badge.hidden = value <= 0;
      badge.textContent = value > 99 ? "99+" : String(value);
    }
  }

  var notificationSummaryBusy = false;

  function loadNotificationSummary() {
    if (!authState.authenticated) {
      applyMessagesBadge(0);
      applyMomentsBadge(0);
      applyPendingBadge(0);
      return Promise.resolve();
    }
    if (notificationSummaryBusy) return notificationSummaryBusy;
    notificationSummaryBusy = fetch("/api/site/notifications/summary", {
      cache: "no-store",
    })
      .then(function (response) {
        if (!response.ok) throw new Error("通知状态加载失败");
        return response.json();
      })
      .then(function (data) {
        applyMessagesBadge(Number(data.messages) || 0);
        applyMomentsBadge(Number(data.moments) || 0);
        applyPendingBadge(Number(data.workbench) || 0);
      })
      .catch(function () {})
      .then(function () {
        notificationSummaryBusy = false;
      });
    return notificationSummaryBusy;
  }

  function applyGuestPageVisibility(status) {
    var isGuest = !status || !status.authenticated;
    var allowed = {};
    ((status && status.guest_pages) || []).forEach(function (key) {
      allowed[key] = true;
    });
    document.querySelectorAll("[data-guest-page]").forEach(function (el) {
      el.hidden = isGuest && !allowed[el.getAttribute("data-guest-page")];
    });
  }

  function applyAuthStatus(status) {
    applyGuestPageVisibility(status);
    authState.enabled = Boolean(status.enabled);
    authState.authenticated = Boolean(status.authenticated);
    authState.role = status.role || (authState.authenticated ? "owner" : "guest");
    authState.username = status.username || "";
    authState.nickname = status.nickname || "";
    authState.owner = Boolean(status.owner) || (!status.enabled && authState.authenticated);
    authState.admin = Boolean(status.admin) || authState.owner;
    authState.permissions = Array.isArray(status.permissions) ? status.permissions : [];
    authState.ready = true;
    setAuthUi();
    loadNotificationSummary();
    if (authState.authenticated) {
      loadPrivateLandingData();
    }
    window.dispatchEvent(
      new CustomEvent("errorauthchange", {
        detail: { authenticated: authState.authenticated, role: authState.role },
      })
    );
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
    var assets = workbench && workbench.assets ? workbench.assets : null;
    var total = assets ? Math.max(0, Number(assets.total) || 0) : 0;
    setText("workbenchCount", assets ? total + " 份资料" : "工作台");
    var wrap = document.getElementById("workbenchThumbs");
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!assets || !total) return;
    var badge = document.createElement("span");
    badge.className = "repo-thumb repo-count";
    badge.textContent = total > 99 ? "99+" : String(total);
    badge.title = "共 " + total + " 份资料";
    wrap.appendChild(badge);
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
      var account = username ? username.value.trim() : "";
      fetch(account ? "/api/member/login" : "/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: account,
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
        closeAuthModal();
        fetch("/api/auth/status", { cache: "no-store" })
          .then(function (response) { return response.json(); })
          .then(applyAuthStatus)
          .catch(function () {
            setAuthUi();
            loadPrivateLandingData();
          });
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
      closeNicknameModal();
      if (authMenu) authMenu.hidden = true;
    }
  });

  var nicknameModal = document.getElementById("nicknameModal");
  var nicknameBtn = document.getElementById("nicknameBtn");

  function closeNicknameModal() {
    if (nicknameModal) nicknameModal.hidden = true;
  }

  if (nicknameBtn) {
    nicknameBtn.addEventListener("click", function () {
      var input = document.getElementById("nicknameInput");
      var error = document.getElementById("nicknameError");
      if (input) input.value = authState.nickname || "";
      if (error) error.hidden = true;
      if (nicknameModal) nicknameModal.hidden = false;
      if (authMenu) authMenu.hidden = true;
      if (input) setTimeout(function () { input.focus(); }, 30);
    });
  }

  var nicknameClose = document.getElementById("nicknameClose");
  if (nicknameClose) {
    nicknameClose.addEventListener("click", closeNicknameModal);
  }
  if (nicknameModal) {
    nicknameModal.addEventListener("click", function (event) {
      if (event.target === nicknameModal) closeNicknameModal();
    });
  }

  var nicknameForm = document.getElementById("nicknameForm");
  if (nicknameForm) {
    nicknameForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var input = document.getElementById("nicknameInput");
      var error = document.getElementById("nicknameError");
      var submit = document.getElementById("nicknameSubmit");
      var value = input ? input.value.trim() : "";
      if (value.length < 2 || value.length > 16) {
        error.textContent = "昵称需为 2-16 位。";
        error.hidden = false;
        return;
      }
      if (submit) submit.disabled = true;
      fetch("/api/account/nickname", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nickname: value }),
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok) throw new Error(data.error || "修改失败");
          return data;
        });
      }).then(function (data) {
        authState.nickname = data.nickname || value;
        setAuthUi();
        closeNicknameModal();
        showLandingToast("昵称已更新");
      }).catch(function (err) {
        error.textContent = err.message || "修改失败";
        error.hidden = false;
      }).then(function () {
        if (submit) submit.disabled = false;
      });
    });
  }

  setAuthUi();
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) return;
    loadNotificationSummary();
  });
  window.addEventListener("focus", loadNotificationSummary);
  window.addEventListener("online", loadNotificationSummary);
  setInterval(function () {
    if (!document.hidden) loadNotificationSummary();
  }, 5000);
  fetch("/api/auth/status", { cache: "no-store" })
    .then(function (response) { return response.json(); })
    .then(applyAuthStatus)
    .catch(function () {
      authState.ready = true;
      setAuthUi();
    });
})();
