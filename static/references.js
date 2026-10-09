(function () {
  "use strict";

  var list = document.getElementById("referenceList");
  if (!list) return;

  var state = { admin: false, items: [] };
  var adminBar = document.getElementById("referenceAdminBar");
  var overlay = document.getElementById("referenceEditorOverlay");
  var form = document.getElementById("referenceEditorForm");
  var titleInput = document.getElementById("referenceTitle");
  var urlInput = document.getElementById("referenceUrl");
  var descriptionInput = document.getElementById("referenceDescription");
  var sortInput = document.getElementById("referenceSort");
  var idInput = document.getElementById("referenceId");
  var editorTitle = document.getElementById("referenceEditorTitle");
  var saveButton = document.getElementById("referenceSaveBtn");

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  async function api(path, options) {
    var response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...(options || {}),
    });
    var data = await response.json().catch(function () {
      return {};
    });
    if (!response.ok) throw new Error(data.error || "请求失败");
    return data;
  }

  function render(items) {
    state.items = items;
    if (!items.length) {
      list.innerHTML = '<p class="reference-empty">还没有参考项目。</p>';
      return;
    }
    list.innerHTML = items
      .map(function (item) {
        var actions = state.admin
          ? '<span class="reference-item-actions">' +
            '<button type="button" data-reference-edit="' +
            item.id +
            '" title="编辑">编辑</button>' +
            '<button type="button" data-reference-delete="' +
            item.id +
            '" title="删除">删除</button>' +
            "</span>"
          : "";
        return (
          '<article class="reference-item" data-reference-id="' +
          item.id +
          '">' +
          actions +
          '<a href="' +
          esc(item.url) +
          '" target="_blank" rel="noopener noreferrer">' +
          esc(item.title) +
          "</a><p>" +
          esc(item.description || "") +
          "</p></article>"
        );
      })
      .join("");
  }

  function openEditor(item) {
    idInput.value = item ? item.id : "";
    titleInput.value = item ? item.title || "" : "";
    urlInput.value = item ? item.url || "" : "";
    descriptionInput.value = item ? item.description || "" : "";
    sortInput.value = item ? item.sort_order || 0 : state.items.length;
    editorTitle.textContent = item ? "编辑参考项目" : "新增参考项目";
    overlay.hidden = false;
    titleInput.focus();
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    var id = Number(idInput.value) || 0;
    var payload = {
      title: titleInput.value.trim(),
      url: urlInput.value.trim(),
      description: descriptionInput.value.trim(),
      sort_order: Number(sortInput.value) || 0,
    };
    saveButton.disabled = true;
    try {
      await api(id ? "/api/references/" + id : "/api/references", {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      overlay.hidden = true;
      await loadReferences();
    } catch (err) {
      await window.ErrorDialog.alert(err.message, { title: "保存失败" });
    } finally {
      saveButton.disabled = false;
    }
  });

  document.getElementById("referenceCancelBtn").addEventListener("click", function () {
    overlay.hidden = true;
  });
  document.getElementById("referenceAddBtn").addEventListener("click", function () {
    openEditor(null);
  });
  overlay.addEventListener("click", function (event) {
    if (event.target === overlay) overlay.hidden = true;
  });
  list.addEventListener("click", async function (event) {
    var edit = event.target.closest("[data-reference-edit]");
    if (edit) {
      var editItem = state.items.find(function (item) {
        return String(item.id) === edit.dataset.referenceEdit;
      });
      if (editItem) openEditor(editItem);
      return;
    }
    var del = event.target.closest("[data-reference-delete]");
    if (!del) return;
    var item = state.items.find(function (entry) {
      return String(entry.id) === del.dataset.referenceDelete;
    });
    if (!item) return;
    var confirmed = await window.ErrorDialog.confirm(
      "删除「" + item.title + "」？",
      { title: "删除参考项目", confirmText: "删除", danger: true }
    );
    if (!confirmed) return;
    try {
      await api("/api/references/" + item.id, { method: "DELETE" });
      await loadReferences();
    } catch (err) {
      await window.ErrorDialog.alert(err.message, { title: "删除失败" });
    }
  });

  async function loadReferences() {
    var items = await api("/api/references");
    render(Array.isArray(items) ? items : []);
  }

  async function boot() {
    try {
      var status = await api("/api/auth/status");
      state.admin = Boolean(status.admin || status.owner);
      if (state.admin) adminBar.hidden = false;
    } catch (err) {}
    try {
      await loadReferences();
    } catch (err) {
      // Keep the static HTML list as a fallback when the API is unavailable.
    }
  }

  boot();
})();
