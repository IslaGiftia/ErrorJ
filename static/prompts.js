(function () {
  "use strict";

  var state = {
    items: [],
    canManage: false,
    category: "全部",
    keyword: "",
    editingId: null,
    previewItem: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function api(path, options) {
    var config = options || {};
    return fetch(path, config).then(function (response) {
      return response.json().catch(function () {
        return {};
      }).then(function (data) {
        if (!response.ok) {
          throw new Error((data && data.error) || "请求失败：" + response.status);
        }
        return data;
      });
    });
  }

  function splitTags(value) {
    return String(value || "")
      .split(",")
      .map(function (tag) { return tag.trim(); })
      .filter(Boolean);
  }

  function categories() {
    var result = ["全部"];
    state.items.forEach(function (item) {
      if (result.indexOf(item.category) < 0) result.push(item.category);
    });
    return result;
  }

  function visiblePrompts() {
    var keyword = state.keyword.trim().toLowerCase();
    return state.items.filter(function (item) {
      if (state.category !== "全部" && item.category !== state.category) return false;
      if (!keyword) return true;
      return [item.title, item.description, item.prompt, item.category]
        .concat(splitTags(item.tags))
        .join("\n")
        .toLowerCase()
        .indexOf(keyword) >= 0;
    });
  }

  function renderTabs() {
    var tabs = $("promptTabs");
    tabs.innerHTML = "";
    categories().forEach(function (category) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "pr-tab" + (state.category === category ? " active" : "");
      button.textContent = category;
      button.addEventListener("click", function () {
        state.category = category;
        renderTabs();
        renderCards();
      });
      tabs.appendChild(button);
    });
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (err) {
        reject(err);
      } finally {
        textarea.remove();
      }
    });
  }

  var toastTimer = null;
  function toast(text) {
    var box = $("promptToast");
    box.textContent = text;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      box.hidden = true;
    }, 1800);
  }

  function openEditor(item) {
    if (!state.canManage) return;
    state.editingId = item ? item.id : null;
    $("promptModalTitle").textContent = item ? "编辑提示词" : "新增提示词";
    $("promptTitle").value = item ? item.title || "" : "";
    $("promptCategory").value = item ? item.category || "" : "";
    $("promptDescription").value = item ? item.description || "" : "";
    $("promptTags").value = item ? item.tags || "" : "";
    $("promptBody").value = item ? item.prompt || "" : "";
    $("promptFormError").hidden = true;
    $("promptModal").hidden = false;
    window.setTimeout(function () { $("promptTitle").focus(); }, 0);
  }

  function closeEditor() {
    $("promptModal").hidden = true;
    state.editingId = null;
    $("promptFormError").hidden = true;
  }

  function savePrompt(event) {
    event.preventDefault();
    if (!state.canManage) return;
    var payload = {
      title: $("promptTitle").value.trim(),
      category: $("promptCategory").value.trim() || "未分类",
      description: $("promptDescription").value.trim(),
      tags: $("promptTags").value.replace(/，/g, ",").replace(/、/g, ",").trim(),
      prompt: $("promptBody").value.trim(),
    };
    var editing = Boolean(state.editingId);
    var path = state.editingId ? "/api/prompts/" + state.editingId : "/api/prompts";
    var method = state.editingId ? "PATCH" : "POST";
    var save = $("promptSave");
    save.disabled = true;
    api(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function () {
      closeEditor();
      toast(editing ? "已保存" : "已新增");
      return loadPrompts();
    }).catch(function (err) {
      $("promptFormError").textContent = err.message;
      $("promptFormError").hidden = false;
    }).then(function () {
      save.disabled = false;
    });
  }

  async function deletePrompt(item) {
    if (!state.canManage) return;
    var confirmed = await window.ErrorDialog.confirm(
      "删除提示词「" + item.title + "」？",
      { title: "删除提示词", confirmText: "删除", danger: true }
    );
    if (!confirmed) return;
    api("/api/prompts/" + item.id, { method: "DELETE" }).then(function () {
      toast("已删除");
      return loadPrompts();
    }).catch(function (err) {
      toast(err.message);
    });
  }

  function togglePinned(item) {
    if (!state.canManage) return;
    api("/api/prompts/" + item.id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned: !item.pinned }),
    }).then(function () {
      toast(item.pinned ? "已取消置顶" : "已置顶");
      return loadPrompts();
    }).catch(function (err) {
      toast(err.message);
    });
  }

  function actionButton(label, className, handler) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "pr-action" + (className ? " " + className : "");
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function openPreview(item) {
    state.previewItem = item;
    $("previewCategory").textContent = item.category || "未分类";
    $("previewTitle").textContent = item.title || "未命名提示词";
    $("previewDescription").textContent = item.description || "";
    $("previewDescription").hidden = !item.description;
    $("previewBody").textContent = item.prompt || "";
    var tagWrap = $("previewTags");
    tagWrap.innerHTML = "";
    splitTags(item.tags).forEach(function (tag) {
      var node = document.createElement("span");
      node.textContent = tag;
      tagWrap.appendChild(node);
    });
    tagWrap.hidden = !tagWrap.childNodes.length;
    $("promptPreview").hidden = false;
    window.setTimeout(function () { $("promptPreviewClose").focus(); }, 0);
  }

  function closePreview() {
    $("promptPreview").hidden = true;
    state.previewItem = null;
  }

  function renderCards() {
    var rows = visiblePrompts();
    var grid = $("promptGrid");
    grid.innerHTML = "";
    $("promptEmpty").hidden = rows.length > 0;
    rows.forEach(function (item) {
      var card = document.createElement("article");
      card.className = "pr-card" + (item.pinned ? " is-pinned" : "");

      var head = document.createElement("div");
      head.className = "pr-card-head";
      var titleWrap = document.createElement("div");
      titleWrap.className = "pr-card-title";
      var title = document.createElement("h2");
      title.textContent = item.title;
      titleWrap.appendChild(title);
      if (item.pinned) {
        var pinBadge = document.createElement("span");
        pinBadge.className = "pr-pin-badge";
        pinBadge.textContent = "置顶";
        titleWrap.appendChild(pinBadge);
      }
      var category = document.createElement("span");
      category.className = "pr-category";
      category.textContent = item.category || "未分类";
      head.append(titleWrap, category);

      var description = document.createElement("p");
      description.className = "pr-description";
      description.textContent = item.description || "";

      var prompt = document.createElement("pre");
      prompt.className = "pr-prompt is-collapsed";
      prompt.textContent = item.prompt;

      var tags = document.createElement("div");
      tags.className = "pr-tags";
      splitTags(item.tags).forEach(function (tag) {
        var node = document.createElement("span");
        node.textContent = tag;
        tags.appendChild(node);
      });

      var actions = document.createElement("div");
      actions.className = "pr-actions";
      var expand = actionButton("展开", "", function () {
        openPreview(item);
      });
      var copy = actionButton("复制", "primary", function () {
        copyText(item.prompt).then(function () {
          toast("已复制提示词");
        }).catch(function () {
          toast("复制失败，请手动选择");
        });
      });
      actions.append(expand, copy);

      if (state.canManage) {
        actions.append(
          actionButton(item.pinned ? "取消置顶" : "置顶", "", function () {
            togglePinned(item);
          }),
          actionButton("编辑", "", function () {
            openEditor(item);
          }),
          actionButton("删除", "danger", function () {
            deletePrompt(item);
          })
        );
      }

      card.append(head, description, prompt, tags, actions);
      grid.appendChild(card);
    });
    if (window.lucide) window.lucide.createIcons();
  }

  function loadPrompts() {
    return api("/api/prompts").then(function (data) {
      state.items = Array.isArray(data.items) ? data.items : [];
      state.canManage = Boolean(data.can_manage);
      $("promptAddBtn").hidden = !state.canManage;
      if (state.category !== "全部" && categories().indexOf(state.category) < 0) {
        state.category = "全部";
      }
      renderTabs();
      renderCards();
    }).catch(function (err) {
      state.items = [];
      state.canManage = false;
      $("promptAddBtn").hidden = true;
      renderTabs();
      renderCards();
      toast(err.message || "加载失败");
    });
  }

  $("promptSearch").addEventListener("input", function (event) {
    state.keyword = event.target.value;
    renderCards();
  });

  $("promptAddBtn").addEventListener("click", function () {
    openEditor(null);
  });

  $("promptForm").addEventListener("submit", savePrompt);
  $("promptCancel").addEventListener("click", closeEditor);
  $("promptModalClose").addEventListener("click", closeEditor);
  $("promptModal").addEventListener("click", function (event) {
    if (event.target === $("promptModal")) closeEditor();
  });
  $("promptPreviewClose").addEventListener("click", closePreview);
  $("promptPreviewCloseFooter").addEventListener("click", closePreview);
  $("promptPreview").addEventListener("click", function (event) {
    if (event.target === $("promptPreview")) closePreview();
  });
  $("previewCopy").addEventListener("click", function () {
    if (!state.previewItem) return;
    copyText(state.previewItem.prompt || "").then(function () {
      toast("已复制提示词");
    }).catch(function () {
      toast("复制失败，请手动选择");
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!$("promptPreview").hidden) {
      closePreview();
      return;
    }
    if (!$("promptModal").hidden) closeEditor();
  });

  loadPrompts();
})();
