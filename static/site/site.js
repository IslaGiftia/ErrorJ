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

  var hasLandingData = document.getElementById("repoCount") ||
    document.getElementById("bookmarkCount") ||
    document.getElementById("noteCount");

  if (hasLandingData) {
  Promise.all([
    fetch("/api/dashboard").then(function (res) { return res.json(); }).catch(function () { return null; }),
    fetch("/api/parts").then(function (res) { return res.json(); }).catch(function () { return []; }),
    fetch("/api/bookmarks").then(function (res) { return res.json(); }).catch(function () { return []; }),
        // 首页只要数量、标签和封面，用 summary=1 避免把整篇笔记正文拉下来
        fetch("/api/notes?summary=1").then(function (res) { return res.json(); }).catch(function () { return []; }),
  ]).then(function (results) {
      var data = results[0];
      var parts = results[1] || [];
      var bookmarks = results[2] || [];
      var notes = results[3] || [];
      var el = document.getElementById("repoCount");
      if (el && data && data.stats && data.stats.part_count) {
        el.textContent = data.stats.part_count;
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

      var bookmarkCount = document.getElementById("bookmarkCount");
      if (bookmarkCount) {
        bookmarkCount.textContent = bookmarks.length;
      }
      var noteCount = document.getElementById("noteCount");
      if (noteCount) {
        noteCount.textContent = notes.length;
      }
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
          let bookmark = recentBookmarks[bk];
          let bookmarkThumb = document.createElement("span");
          bookmarkThumb.className = "repo-thumb";
          var hostname = "";
          try {
            hostname = new URL(bookmark.url).hostname.replace(/^www\./i, "");
          } catch (err) {
            hostname = String(bookmark.title || "书");
          }
          let bookmarkFallback = document.createElement("span");
          bookmarkFallback.className = "repo-thumb-fallback";
          bookmarkFallback.textContent =
            (hostname.match(/[A-Za-z0-9\u4e00-\u9fff]/) || ["书"])[0].toUpperCase();
          bookmarkThumb.appendChild(bookmarkFallback);
          let bookmarkIcon = document.createElement("img");
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
    })
    .catch(function () {});
  }
})();
