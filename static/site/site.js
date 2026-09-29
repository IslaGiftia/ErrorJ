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

  var menuBtn = document.getElementById("menuBtn");
  var nav = document.getElementById("siteNav");
  if (menuBtn && nav) {
    menuBtn.addEventListener("click", function () {
      nav.classList.toggle("open");
    });
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        nav.classList.remove("open");
      }
    });
  }

  var landingToast = document.getElementById("landingToast");
  var landingToastTimer = null;
  document.querySelectorAll("[data-landing-placeholder]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!landingToast) return;
      landingToast.textContent = button.getAttribute("data-landing-placeholder") || "功能正在规划中";
      landingToast.hidden = false;
      clearTimeout(landingToastTimer);
      landingToastTimer = setTimeout(function () {
        landingToast.hidden = true;
      }, 2200);
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

  // 下雨动画统一由 /static/site/rain.js 提供（页面里需引入该文件与 rain.css）。
  if (window.ErrorRain) window.ErrorRain.init();

  var authState = { enabled: false, authenticated: false, ready: false };
  var pendingPrivateUrl = "";

  function setText(id, text) {
    var node = document.getElementById(id);
    if (node) node.textContent = text;
  }

  function setThumbPlaceholder(id, glyph) {
    var wrap = document.getElementById(id);
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!glyph) return;
    var item = document.createElement("span");
    item.className = "repo-thumb";
    item.textContent = glyph;
    wrap.appendChild(item);
  }

  function setPrivateModuleState(authenticated) {
    document.querySelectorAll("[data-private-module]").forEach(function (entry) {
      entry.classList.toggle("is-locked", !authenticated);
    });
    if (authenticated) return;
    setText("repoCount", "登录后查看");
    setText("bookmarkCount", "登录后查看");
    setText("noteCount", "登录后查看");
    setText("workbenchCount", "登录后查看");
    setThumbPlaceholder("repoThumbs", "锁");
    setThumbPlaceholder("bookmarkThumbs", "锁");
    setThumbPlaceholder("notesThumbs", "锁");
  }

  function setAuthUi() {
    var button = document.getElementById("authStatusBtn");
    var text = document.getElementById("authStatusText");
    var menu = document.getElementById("authMenu");
    document.body.setAttribute("data-auth-enabled", authState.enabled ? "1" : "0");
    document.body.setAttribute("data-authenticated", authState.authenticated ? "1" : "0");
    if (!button || !text) return;
    button.classList.toggle("is-authenticated", authState.authenticated);
    text.textContent = authState.authenticated
      ? (authState.enabled ? "已登录" : "本地模式")
      : "游客";
    button.setAttribute(
      "aria-label",
      authState.authenticated ? "已登录，点击打开管理菜单" : "游客，点击登录"
    );
    button.setAttribute("aria-haspopup", authState.authenticated ? "menu" : "dialog");
    if (!authState.authenticated && menu) menu.hidden = true;
  }

  function openAuthModal() {
    if (!authState.enabled || authState.authenticated) return;
    var modal = document.getElementById("authModal");
    var password = document.getElementById("authPassword");
    var error = document.getElementById("authError");
    if (!modal || !password) return;
    error.hidden = true;
    error.textContent = "";
    modal.hidden = false;
    password.value = "";
    window.setTimeout(function () { password.focus(); }, 0);
  }

  function closeAuthModal() {
    var modal = document.getElementById("authModal");
    if (modal) modal.hidden = true;
  }

  function loadPrivateLandingData() {
    if (!authState.authenticated) return;
    Promise.all([
      fetch("/api/dashboard").then(function (res) { return res.json(); }).catch(function () { return null; }),
      fetch("/api/parts").then(function (res) { return res.json(); }).catch(function () { return []; }),
      fetch("/api/bookmarks").then(function (res) { return res.json(); }).catch(function () { return []; }),
      // 首页只要数量、标签和封面，用 summary=1 避免把整篇笔记正文拉下来
      fetch("/api/notes?summary=1").then(function (res) { return res.json(); }).catch(function () { return []; }),
      fetch("/api/workbench/summary").then(function (res) { return res.json(); }).catch(function () { return null; }),
    ]).then(function (results) {
      var data = results[0];
      var parts = results[1] || [];
      var bookmarks = results[2] || [];
      var notes = results[3] || [];
      var workbench = results[4];
      setPrivateModuleState(true);

      var el = document.getElementById("repoCount");
      if (el && data && data.stats) {
        el.textContent = Number(data.stats.part_count || 0) + " 种元件";
      }
      var wrap = document.getElementById("repoThumbs");
      if (wrap && data && data.stats) {
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

      setText("bookmarkCount", bookmarks.length + " 个网页");
      setText("noteCount", notes.length + " 篇笔记");
      setText(
        "workbenchCount",
        workbench && workbench.assets ? Number(workbench.assets.total || 0) + " 项" : "工作台"
      );

      var notesWrap = document.getElementById("notesThumbs");
      if (notesWrap) {
        notesWrap.innerHTML = "";
        var noteShown = Math.min(5, notes.length);
        for (var ni = 0; ni < noteShown; ni++) {
          var noteThumb = document.createElement("span");
          noteThumb.className = "repo-thumb";
          if (notes[ni].cover_path) {
            var noteImage = document.createElement("img");
            noteImage.src = "/site-files/" + notes[ni].cover_path;
            noteImage.alt = "";
            noteImage.loading = "lazy";
            noteThumb.appendChild(noteImage);
          } else {
            noteThumb.textContent = (String(notes[ni].title || "笔").match(/[A-Za-z0-9\u4e00-\u9fff]/) || ["笔"])[0];
          }
          notesWrap.appendChild(noteThumb);
        }
        if (!notes.length) {
          ["笔", "记", "本"].forEach(function (glyph) {
            var empty = document.createElement("span");
            empty.className = "repo-thumb";
            empty.textContent = glyph;
            notesWrap.appendChild(empty);
          });
        }
      }
      var bookmarkWrap = document.getElementById("bookmarkThumbs");
      if (bookmarkWrap) {
        bookmarkWrap.innerHTML = "";
        var recentBookmarks = bookmarks.slice();
        for (var bi = recentBookmarks.length - 1; bi > 0; bi--) {
          var bj = Math.floor(Math.random() * (bi + 1));
          var btmp = recentBookmarks[bi];
          recentBookmarks[bi] = recentBookmarks[bj];
          recentBookmarks[bj] = btmp;
        }
        var bookmarkShown = Math.min(5, recentBookmarks.length);
        for (var bk = 0; bk < bookmarkShown; bk++) {
          var bookmark = recentBookmarks[bk];
          var bookmarkThumb = document.createElement("span");
          bookmarkThumb.className = "repo-thumb";
          var hostname = "";
          try {
            hostname = new URL(bookmark.url).hostname.replace(/^www\./i, "");
          } catch (err) {
            hostname = String(bookmark.title || "书");
          }
          var bookmarkFallback = document.createElement("span");
          bookmarkFallback.className = "repo-thumb-fallback";
          bookmarkFallback.textContent =
            (hostname.match(/[A-Za-z0-9\u4e00-\u9fff]/) || ["书"])[0].toUpperCase();
          bookmarkThumb.appendChild(bookmarkFallback);
          var bookmarkIcon = document.createElement("img");
          bookmarkIcon.alt = "";
          bookmarkIcon.loading = "lazy";
          bookmarkIcon.referrerPolicy = "no-referrer";
          bookmarkIcon.addEventListener("load", function () {
            bookmarkThumb.classList.add("has-icon");
          });
          bookmarkIcon.addEventListener("error", function () {
            bookmarkIcon.remove();
          });
          bookmarkIcon.src = "/api/bookmarks/" + bookmark.id + "/favicon?v=" +
            encodeURIComponent(bookmark.favicon_updated_at || "");
          bookmarkThumb.appendChild(bookmarkIcon);
          bookmarkWrap.appendChild(bookmarkThumb);
        }
        if (bookmarks.length > 5) {
          var bookmarkExtra = document.createElement("span");
          bookmarkExtra.className = "repo-thumb repo-count";
          bookmarkExtra.textContent = "+" + (bookmarks.length - 5);
          bookmarkWrap.appendChild(bookmarkExtra);
        }
      }
    }).catch(function () {});
  }

  document.querySelectorAll("[data-private-module]").forEach(function (entry) {
    entry.addEventListener("click", function (event) {
      if (authState.authenticated) return;
      event.preventDefault();
      pendingPrivateUrl = entry.getAttribute("href") || "";
      if (!authState.ready) return;
      openAuthModal();
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
      var password = document.getElementById("authPassword");
      submit.disabled = true;
      error.hidden = true;
      fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password: password.value,
          remember: document.getElementById("authRemember").checked,
        }),
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok) throw new Error(data.error || "登录失败");
          return data;
        });
      }).then(function () {
        authState.authenticated = true;
        setAuthUi();
        closeAuthModal();
        loadPrivateLandingData();
        if (pendingPrivateUrl) {
          var target = pendingPrivateUrl;
          pendingPrivateUrl = "";
          window.location.href = target;
        }
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

  setPrivateModuleState(false);
  setAuthUi();
  fetch("/api/auth/status", { cache: "no-store" })
    .then(function (response) { return response.json(); })
    .then(function (status) {
      authState.enabled = Boolean(status.enabled);
      authState.authenticated = Boolean(status.authenticated);
      authState.ready = true;
      setAuthUi();
      if (authState.authenticated) {
        loadPrivateLandingData();
      } else {
        setPrivateModuleState(false);
        if (pendingPrivateUrl) openAuthModal();
      }
    })
    .catch(function () {
      authState.ready = true;
      setPrivateModuleState(false);
      setAuthUi();
    });
})();
