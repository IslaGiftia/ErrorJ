/*
 * 书籍页（推荐页的「书籍」子页）：
 * - 没有检索框；阅读器整体下线，这一页只负责下载（卡片 / 右下角按钮都是下载）。
 * - 上传 / 编辑 / 分享 / 举报 仍在卡片上；上传弹窗既可以从本页的「+书籍」打开，
 *   也可以由外层推荐页的常驻按钮通过 window.ErrorRecommendTab.openAdd() 打开。
 */
(function () {
  "use strict";

  var MAX_BOOK_BYTES = 60 * 1024 * 1024;
  var MAX_BOOK_COUNT = 20;

  function bookLimitLabel() {
    return window.ErrorUploadLimits
      ? window.ErrorUploadLimits.label(MAX_BOOK_BYTES)
      : "60MB";
  }

  function applyUploadLimits() {
    if (!window.ErrorUploadLimits) return;
    var limits = window.ErrorUploadLimits.get("book_file");
    MAX_BOOK_BYTES = Number(limits.max_file_bytes) || MAX_BOOK_BYTES;
    MAX_BOOK_COUNT = Number(limits.max_count) || MAX_BOOK_COUNT;
    var hint = $("bookUploadHint");
    if (hint) {
      hint.textContent =
        "支持 EPUB / MOBI / AZW3 / FB2 / CBZ / PDF / TXT / Markdown，单个不超过 " +
        bookLimitLabel() +
        "；EPUB、MOBI 会自动读取书名、作者和封面。";
    }
  }

  var state = {
    books: [],
    authenticated: false,
    canManage: false,
    editingId: null,
    deleteArmed: false,
    uploading: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function api(path, options) {
    return fetch(path, options).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!response.ok) {
            throw new Error((data && data.error) || "请求失败：" + response.status);
          }
          return data;
        });
    });
  }

  var toastTimer = null;
  function toast(message) {
    var el = $("bookToast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.hidden = true;
    }, 3000);
  }

  function formatSize(bytes) {
    var value = Number(bytes) || 0;
    if (value < 1024 * 1024) return Math.max(1, Math.round(value / 1024)) + " KB";
    return (value / (1024 * 1024)).toFixed(value < 10 * 1024 * 1024 ? 1 : 0) + " MB";
  }

  // 没有检索也没有排序：固定按书名 A~Z（中文按拼音）
  function visibleBooks() {
    return state.books.slice().sort(function (a, b) {
      return String(a.title || "").localeCompare(String(b.title || ""), "zh-Hans-CN");
    });
  }

  function renderGrid() {
    var grid = $("bookGrid");
    var books = visibleBooks();
    var count = $("bookCount");
    count.textContent = state.books.length ? state.books.length + " 本" : "";
    if (!books.length) {
      grid.innerHTML =
        '<p class="bk-empty">' +
        (state.canManage ? "书架还是空的，点右上角「+书籍」上传。" : "书架还是空的。") +
        "</p>";
      if (window.lucide) lucide.createIcons();
      return;
    }
    grid.innerHTML = books
      .map(function (book) {
        var size = state.authenticated
          ? "<span>" + formatSize(book.file_size) + "</span>"
          : "";
        // 卡片右下角（封面右下角）放操作按钮，下载排在最右边
        var edit = state.canManage
          ? '<button class="bk-card-edit" type="button" data-book-edit="' +
            book.id +
            '" title="编辑"><i data-lucide="pencil"></i></button>'
          : "";
        // 站点内容都是管理员上传的，自己举报自己没意义：管理员不显示举报入口
        var report = !state.canManage
          ? '<button class="bk-card-edit" type="button" data-report-type="book" data-report-key="' +
            book.id +
            '" data-report-title="' +
            esc(book.title || "电子书") +
            '" title="举报"><i data-lucide="flag"></i></button>'
          : "";
        var share = state.canManage
          ? '<button class="bk-card-edit" type="button" data-book-share="' +
            book.id +
            '" title="分享"><i data-lucide="share-2"></i></button>'
          : "";
        // 登录后直接下载原文件
        var download = state.authenticated
          ? '<button class="bk-card-edit" type="button" data-book-download="' +
            book.id +
            '" title="下载原文件"><i data-lucide="download"></i></button>'
          : "";
        // 游客只有「举报」这一颗按钮（下载要登录）；右上角的格式标签仍然只给登录账号
        var coverActions =
          edit + report + share + download
            ? '<div class="bk-cover-actions">' + edit + report + share + download + "</div>"
            : "";
        var formatBadge = state.authenticated
          ? '<span class="bk-format">' +
            esc(String(book.format || "").toUpperCase()) +
            "</span>"
          : "";
        return (
          '<article class="bk-card" data-book-download-card="' +
          book.id +
          '" tabindex="0" role="button" aria-label="下载 ' +
          esc(book.title) +
          '">' +
          '<div class="bk-cover">' +
          (book.cover_url
            ? '<img src="' + esc(book.cover_url) + '" alt="" loading="lazy">'
            : '<span class="bk-cover-fallback"><i data-lucide="book-open"></i><span>' +
              esc(book.title) +
              "</span></span>") +
          formatBadge +
          coverActions +
          "</div>" +
          '<div class="bk-card-title">' +
          esc(book.title) +
          "</div>" +
          '<div class="bk-card-meta"><span>' +
          esc(book.author || "未知作者") +
          "</span>" +
          size +
          "</div>" +
          "</article>"
        );
      })
      .join("");
    if (window.lucide) lucide.createIcons();
    if (window.ErrorFreshCards) {
      books.forEach(function (book) {
        var node = grid.querySelector('[data-book-download-card="' + book.id + '"]');
        window.ErrorFreshCards.mark(node, book.id);
      });
    }
    // 有新书还没滚到眼前时，右下角「顶部」按钮切成「↓ 书籍」
    if (window.ErrorFreshJump) window.ErrorFreshJump.schedule();
  }

  function loadBooks() {
    return api("/api/books").then(function (data) {
      state.books = Array.isArray(data) ? data : [];
      renderGrid();
    });
  }

  function loadAuth() {
    return api("/api/auth/status")
      .then(function (status) {
        state.authenticated = Boolean(status.authenticated);
        state.canManage = Boolean(status.owner);
        $("bookUploadBtn").hidden = !state.canManage;
      })
      .catch(function () {
        state.authenticated = false;
        state.canManage = false;
      });
  }

  // ---------- 下载 ----------

  function downloadBook(id) {
    if (!state.authenticated) {
      toast("请登录后操作");
      return;
    }
    location.href = "/api/books/" + id + "/download";
  }

  // ---------- 上传 ----------

  var uploadState = { abort: null, rows: null, fill: null, canceled: false };

  function uploadRows() {
    if (!uploadState.rows) uploadState.rows = ErrorProgress.rows($("uploadRows"));
    return uploadState.rows;
  }

  function uploadFill() {
    if (!uploadState.fill) {
      uploadState.fill = ErrorProgress.button($("uploadSubmit"), {
        onCancel: function () {
          uploadState.canceled = true;
          if (uploadState.abort) uploadState.abort();
        },
      });
    }
    return uploadState.fill;
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        resolve(result.slice(result.indexOf(",") + 1));
      };
      reader.onerror = function () {
        reject(new Error("读取文件失败"));
      };
      reader.readAsDataURL(file);
    });
  }

  function updateUploadLabel() {
    var input = $("uploadFiles");
    var files = input.files ? input.files.length : 0;
    $("uploadFileLabel").textContent = files ? "已选择 " + files + " 个文件" : "选择电子书文件";
    $("uploadMetaFields").hidden = files > 1;
    if (!state.uploading && uploadState.rows) uploadState.rows.reset();
  }

  function submitUpload() {
    if (state.uploading) return;
    var input = $("uploadFiles");
    var files = Array.prototype.slice.call(input.files || []);
    if (!files.length) {
      toast("先选择电子书文件");
      return;
    }
    if (files.length > MAX_BOOK_COUNT) {
      toast("一次最多选择 " + MAX_BOOK_COUNT + " 个电子书文件");
      return;
    }
    var tooBig = files.filter(function (file) {
      return file.size > MAX_BOOK_BYTES;
    });
    if (tooBig.length) {
      toast(tooBig[0].name + " 超过 " + bookLimitLabel());
      return;
    }
    var single = files.length === 1;
    var meta = {
      title: single ? $("uploadTitleInput").value.trim() : "",
      author: single ? $("uploadAuthorInput").value.trim() : "",
    };
    var rows = uploadRows();
    var fill = uploadFill();
    rows.reset();
    files.forEach(function (file) {
      rows.add(file);
    });
    state.uploading = true;
    uploadState.canceled = false;
    $("uploadCancel").disabled = true;
    $("uploadClose").disabled = true;
    var total = files.reduce(function (sum, file) {
      return sum + Math.max(1, file.size);
    }, 0);
    var finished = 0;
    var done = 0;
    var failed = 0;

    function paint() {
      var ratio = total ? finished / total : 0;
      fill.set(ratio, "取消上传 " + ErrorProgress.percentText(ratio));
      $("uploadSubmit").title = "点击取消上传";
    }
    paint();

    var chain = Promise.resolve();
    files.forEach(function (file, index) {
      var size = Math.max(1, file.size);
      chain = chain.then(function () {
        if (uploadState.canceled) {
          rows.set(index, "canceled");
          return;
        }
        rows.set(index, "uploading", { ratio: 0, text: "读取文件…" });
        return fileToBase64(file).then(function (data) {
          if (uploadState.canceled) {
            rows.set(index, "canceled");
            return;
          }
          var task = ErrorProgress.upload("/api/books/upload", {
            payload: {
              file_name: file.name,
              data_base64: data,
              title: meta.title,
              author: meta.author,
            },
            onProgress: function (ratio) {
              rows.set(index, "uploading", {
                ratio: ratio,
                text: ErrorProgress.percentText(ratio) + " · " + formatSize(file.size),
              });
              var live = finished + size * ratio;
              fill.set(total ? live / total : ratio, "取消上传 " + ErrorProgress.percentText(total ? live / total : ratio));
            },
            onUploaded: function () {
              rows.set(index, "processing", { text: "解析元数据…" });
            },
          });
          uploadState.abort = task.abort;
          return task.promise.then(
            function () {
              uploadState.abort = null;
              done += 1;
              finished += size;
              rows.set(index, "done", { text: "已入库" });
              paint();
            },
            function (err) {
              uploadState.abort = null;
              if (ErrorProgress.isAborted(err)) {
                uploadState.canceled = true;
                rows.set(index, "canceled");
                return;
              }
              failed += 1;
              finished += size;
              rows.set(index, "error", { text: "失败：" + err.message });
              paint();
            }
          );
        });
      });
    });

    chain.then(function () {
      state.uploading = false;
      $("uploadCancel").disabled = false;
      $("uploadClose").disabled = false;
      fill.reset();
      $("uploadSubmit").removeAttribute("title");
      if (uploadState.canceled) {
        $("uploadHint").textContent = "已取消上传，文件仍然保留，可以直接重新开始。";
        toast("已取消上传，文件已保留");
        return;
      }
      var uploaded = done;
      input.value = "";
      $("uploadTitleInput").value = "";
      $("uploadAuthorInput").value = "";
      updateUploadLabel();
      uploadRows().reset();
      $("uploadModal").hidden = true;
      toast("上传完成：成功 " + uploaded + " 本" + (failed ? "，失败 " + failed + " 本" : ""));
      loadBooks();
    });
  }

  // ---------- 编辑 ----------

  function openEdit(book) {
    state.editingId = book.id;
    state.deleteArmed = false;
    $("editTitleInput").value = book.title || "";
    $("editAuthorInput").value = book.author || "";
    $("editDelete").innerHTML = '<i data-lucide="trash-2"></i><span>删除</span>';
    $("editError").hidden = true;
    $("editModal").hidden = false;
    notifyDock(true);
    if (window.lucide) lucide.createIcons();
  }

  /* 编辑弹窗打开时，外层推荐页那排悬浮按钮要收上去（见 embed.js） */
  function notifyDock(open) {
    if (window.ErrorEmbed) window.ErrorEmbed.notifyDialog(open);
  }

  function closeEditModal() {
    if ($("editModal").hidden) return;
    $("editModal").hidden = true;
    notifyDock(false);
  }

  function submitEdit(event) {
    event.preventDefault();
    var id = state.editingId;
    if (!id) return;
    var title = $("editTitleInput").value.trim();
    if (!title) {
      $("editError").textContent = "书名不能为空。";
      $("editError").hidden = false;
      return;
    }
    api("/api/books/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title,
        author: $("editAuthorInput").value.trim(),
      }),
    })
      .then(function () {
        closeEditModal();
        toast("已保存");
        loadBooks();
      })
      .catch(function (err) {
        $("editError").textContent = err.message;
        $("editError").hidden = false;
      });
  }

  function deleteCurrent() {
    var id = state.editingId;
    if (!id) return;
    if (!state.deleteArmed) {
      state.deleteArmed = true;
      $("editDelete").innerHTML = '<i data-lucide="alert-triangle"></i><span>再点一次确认删除</span>';
      if (window.lucide) lucide.createIcons();
      return;
    }
    api("/api/books/" + id, { method: "DELETE" })
      .then(function () {
        closeEditModal();
        toast("已删除");
        loadBooks();
      })
      .catch(function (err) {
        toast(err.message);
      });
  }

  // ---------- 事件 ----------

  $("bookGrid").addEventListener("click", function (event) {
    if (event.target.closest("[data-report-type]")) return;
    var share = event.target.closest("[data-book-share]");
    if (share) {
      event.stopPropagation();
      var shareBook = state.books.filter(function (book) {
        return book.id === Number(share.getAttribute("data-book-share"));
      })[0];
      if (shareBook && window.ErrorShare) {
        window.ErrorShare.open("book", shareBook.id, shareBook.title);
      }
      return;
    }
    var download = event.target.closest("[data-book-download]");
    if (download) {
      event.stopPropagation();
      downloadBook(Number(download.getAttribute("data-book-download")));
      return;
    }
    var edit = event.target.closest("[data-book-edit]");
    if (edit) {
      event.stopPropagation();
      var target = state.books.filter(function (book) {
        return book.id === Number(edit.getAttribute("data-book-edit"));
      })[0];
      if (target) openEdit(target);
      return;
    }
    var card = event.target.closest("[data-book-download-card]");
    if (card) downloadBook(Number(card.getAttribute("data-book-download-card")));
  });
  $("bookGrid").addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("[data-report-type]")) return;
    var card = event.target.closest("[data-book-download-card]");
    if (!card) return;
    event.preventDefault();
    downloadBook(Number(card.getAttribute("data-book-download-card")));
  });

  function openUpload() {
    $("uploadFiles").value = "";
    updateUploadLabel();
    if (uploadState.rows) uploadState.rows.reset();
    $("uploadHint").textContent = "多选时按每个文件自己的元数据入库，上面两个输入框只在单文件上传时生效。";
    $("uploadModal").hidden = false;
    if (window.lucide) lucide.createIcons();
  }

  $("bookUploadBtn").addEventListener("click", openUpload);
  $("uploadFiles").addEventListener("change", updateUploadLabel);

  // 点击 / 拖拽 / 拖文件夹上传，Chromium 下会记住上次打开的目录
  var bookUploadField = $("uploadFiles").closest(".bk-file-field");
  if (window.ErrorDropZone && bookUploadField) {
    window.ErrorDropZone.attach(bookUploadField, {
      input: $("uploadFiles"),
      accept: [".epub", ".mobi", ".azw", ".azw3", ".fb2", ".cbz", ".pdf", ".txt", ".md", ".markdown"],
      maxCount: function () {
        return MAX_BOOK_COUNT;
      },
      multiple: true,
      pickerId: "errorjiang-books",
      toast: toast
    });
  }
  $("uploadSubmit").addEventListener("click", submitUpload);
  $("uploadClose").addEventListener("click", function () {
    if (state.uploading) return;
    $("uploadModal").hidden = true;
  });
  $("uploadCancel").addEventListener("click", function () {
    if (state.uploading) return;
    $("uploadModal").hidden = true;
  });

  $("editForm").addEventListener("submit", submitEdit);
  $("editClose").addEventListener("click", function () {
    closeEditModal();
  });
  $("editCancel").addEventListener("click", function () {
    closeEditModal();
  });
  $("editDelete").addEventListener("click", deleteCurrent);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if (state.uploading) return;
      $("uploadModal").hidden = true;
      closeEditModal();
    }
  });

  // 外层推荐页的「+书籍」按钮通过它打开上传弹窗
  window.ErrorRecommendTab = { key: "books", openAdd: openUpload };

  loadAuth()
    .then(function () {
      return window.ErrorFreshCards ? window.ErrorFreshCards.load() : null;
    })
    .then(loadBooks)
    .catch(function (err) {
      toast(err.message);
    });
  if (window.ErrorUploadLimits) window.ErrorUploadLimits.apply(applyUploadLimits);
})();
