(function () {
  "use strict";

  var state = {
    events: [],
    detail: null,
    currentUserId: 0,
    isAdmin: false,
    candidates: null,
    editingEventId: null,
    editingExpenseId: null,
    selectedParticipants: new Set(),
    confirmResolve: null,
    toastTimer: null,
    requestId: 0,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function money(cents) {
    var value = Number(cents) || 0;
    return "¥" + (value / 100).toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function signedMoney(cents) {
    var value = Number(cents) || 0;
    if (value > 0) return "+" + money(value);
    if (value < 0) return "-" + money(-value);
    return money(0);
  }

  function initials(name) {
    var text = String(name || "?").trim();
    return text ? text.slice(0, 1).toUpperCase() : "?";
  }

  function formatTime(value) {
    var text = String(value || "");
    var match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!match) return text;
    return match[1] + "-" + match[2] + "-" + match[3] + " " + match[4] + ":" + match[5];
  }

  function toast(message) {
    var box = $("toast");
    if (!box) return;
    box.textContent = String(message || "");
    box.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () {
      box.hidden = true;
    }, 2600);
  }

  async function api(url, options) {
    var config = options || {};
    var headers = { Accept: "application/json" };
    if (config.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    var response = await fetch(url, {
      method: config.method || "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: headers,
      body: config.body === undefined ? undefined : JSON.stringify(config.body),
    });
    var data = null;
    try {
      data = await response.json();
    } catch (err) {}
    if (!response.ok) {
      throw new Error((data && data.error) || "请求失败，请稍后再试。");
    }
    return data || {};
  }

  function currentEventIdFromUrl() {
    try {
      var value = Number(new URL(location.href).searchParams.get("event"));
      return Number.isFinite(value) && value > 0 ? value : null;
    } catch (err) {
      return null;
    }
  }

  function setEventUrl(eventId) {
    try {
      var url = new URL(location.href);
      if (eventId) url.searchParams.set("event", String(eventId));
      else url.searchParams.delete("event");
      history.replaceState(null, "", url.pathname + url.search);
    } catch (err) {}
  }

  function renderEventList() {
    var list = $("eventList");
    $("eventCount").textContent = state.events.length + " 个活动";
    if (!state.events.length) {
      list.innerHTML = '<div class="aa-empty-row">没有活动</div>';
      return;
    }
    list.innerHTML = state.events
      .map(function (item) {
        var active = state.detail && Number(state.detail.id) === Number(item.id);
        var balance = Number(item.my_balance_cents) || 0;
        var balanceText =
          balance > 0 ? "应收 " + money(balance) : balance < 0 ? "应付 " + money(-balance) : "已平";
        return (
          '<button class="aa-event-item' +
          (active ? " is-active" : "") +
          '" type="button" data-event-id="' +
          Number(item.id) +
          '">' +
          '<span class="aa-event-item-top"><strong>' +
          escapeHtml(item.title) +
          "</strong><b>" +
          escapeHtml(money(item.total_cents)) +
          "</b></span>" +
          '<span class="aa-event-item-bottom"><span>' +
          Number(item.member_count) +
          " 人 · " +
          escapeHtml(balanceText) +
          "</span><span>" +
          escapeHtml(formatTime(item.updated_at)) +
          "</span></span>" +
          "</button>"
        );
      })
      .join("");
  }

  function balanceClass(value) {
    var number = Number(value) || 0;
    if (number > 0) return "is-positive";
    if (number < 0) return "is-negative";
    return "";
  }

  function renderReceipt() {
    var box = $("receiptBox");
    var detail = state.detail;
    var meta = $("receiptMeta");
    if (!detail) return;
    if (!detail.qr_url) {
      meta.textContent = "未设置";
      box.innerHTML =
        '<div class="aa-receipt-empty"><span>发起人还没有设置收款码</span></div>' +
        (detail.can_manage
          ? '<div class="aa-receipt-actions"><button class="aa-btn" id="uploadReceiptBtn" type="button"><i data-lucide="image-up"></i><span>上传收款码</span></button></div>'
          : "");
    } else {
      meta.textContent = detail.qr_name || "已设置";
      box.innerHTML =
        '<img class="aa-receipt-image" id="receiptImage" src="' +
        escapeHtml(detail.qr_url) +
        '" alt="收款码">' +
        '<div class="aa-receipt-actions">' +
        '<button class="aa-btn" id="viewReceiptBtn" type="button"><i data-lucide="maximize-2"></i><span>查看大图</span></button>' +
        (detail.can_manage
          ? '<button class="aa-btn" id="replaceReceiptBtn" type="button"><i data-lucide="refresh-cw"></i><span>更换</span></button>' +
            '<button class="aa-btn aa-btn-danger" id="deleteReceiptBtn" type="button"><i data-lucide="trash-2"></i><span>移除</span></button>'
          : "") +
        "</div>";
      var image = $("receiptImage");
      if (image) {
        image.addEventListener("click", function () {
          openQrViewer(detail.qr_url);
        });
      }
      var viewButton = $("viewReceiptBtn");
      if (viewButton) {
        viewButton.addEventListener("click", function () {
          openQrViewer(detail.qr_url);
        });
      }
      var replaceButton = $("replaceReceiptBtn");
      if (replaceButton) {
        replaceButton.addEventListener("click", chooseReceipt);
      }
      var deleteButton = $("deleteReceiptBtn");
      if (deleteButton) {
        deleteButton.addEventListener("click", deleteReceipt);
      }
    }
    var uploadButton = $("uploadReceiptBtn");
    if (uploadButton) uploadButton.addEventListener("click", chooseReceipt);
  }

  function renderExpenses() {
    var detail = state.detail;
    var list = $("expenseList");
    var expenses = detail.expenses || [];
    $("expenseMeta").textContent = expenses.length + " 笔";
    if (!expenses.length) {
      list.innerHTML = '<div class="aa-empty-row">还没有费用记录</div>';
      return;
    }
    list.innerHTML = expenses
      .map(function (item) {
        var note = item.note || "未填写备注";
        var actions = item.can_edit
          ? '<span class="aa-row-actions">' +
            '<button class="aa-row-btn" type="button" data-expense-edit="' +
            Number(item.id) +
            '" aria-label="编辑费用"><i data-lucide="pencil"></i></button>' +
            '<button class="aa-row-btn is-danger" type="button" data-expense-delete="' +
            Number(item.id) +
            '" aria-label="删除费用"><i data-lucide="trash-2"></i></button>' +
            "</span>"
          : "";
        return (
          '<article class="aa-expense-item" data-expense-item="' +
          Number(item.id) +
          '">' +
          '<div class="aa-expense-main"><p class="aa-expense-note' +
          (item.note ? "" : " is-empty") +
          '">' +
          escapeHtml(note) +
          "</p>" +
          '<div class="aa-expense-meta"><span>' +
          escapeHtml(item.user_name || "成员") +
          " 垫付</span><span>" +
          escapeHtml(formatTime(item.created_at)) +
          "</span></div></div>" +
          '<div class="aa-expense-side"><strong class="aa-expense-amount">' +
          escapeHtml(money(item.amount_cents)) +
          "</strong>" +
          actions +
          "</div>" +
          "</article>"
        );
      })
      .join("");
  }

  function renderBalances() {
    var members = state.detail.members || [];
    $("balanceList").innerHTML = members
      .map(function (item) {
        var value = Number(item.balance_cents) || 0;
        var stateText = value > 0 ? "应收" : value < 0 ? "应付" : "已平";
        return (
          '<div class="aa-balance-item">' +
          '<div class="aa-person"><strong>' +
          escapeHtml(item.name) +
          "</strong><span>垫付 " +
          escapeHtml(money(item.paid_cents)) +
          " · 应分 " +
          escapeHtml(money(item.share_cents)) +
          "</span></div>" +
          '<span class="aa-balance-value ' +
          balanceClass(value) +
          '">' +
          escapeHtml(stateText + " " + money(Math.abs(value))) +
          "</span></div>"
        );
      })
      .join("");
  }

  function renderTransfers() {
    var transfers = state.detail.transfers || [];
    $("transferMeta").textContent = transfers.length + " 笔";
    if (!transfers.length) {
      $("transferList").innerHTML =
        '<div class="aa-empty-row">' +
        (Number(state.detail.total_cents) ? "当前已经平账" : "录入费用后生成方案") +
        "</div>";
      return;
    }
    $("transferList").innerHTML = transfers
      .map(function (item) {
        return (
          '<div class="aa-transfer-item">' +
          '<div class="aa-transfer-route"><b>' +
          escapeHtml(item.from_name) +
          "</b> 转给 <b>" +
          escapeHtml(item.to_name) +
          "</b><span>单笔结清</span></div>" +
          '<span class="aa-transfer-amount">' +
          escapeHtml(money(item.amount_cents)) +
          "</span></div>"
        );
      })
      .join("");
  }

  function renderDetail() {
    var detail = state.detail;
    var empty = $("emptyState");
    var view = $("eventView");
    if (!detail) {
      empty.hidden = false;
      view.hidden = true;
      document.title = "AA 分账";
      return;
    }
    empty.hidden = true;
    view.hidden = false;
    document.title = detail.title + " - AA 分账";
    $("eventTitle").textContent = detail.title;
    $("eventMeta").textContent =
      detail.member_count +
      " 人 · 发起人 " +
      detail.owner_name +
      " · 更新于 " +
      formatTime(detail.updated_at);
    $("metricTotal").textContent = money(detail.total_cents);
    $("metricAverage").textContent = money(
      detail.member_count ? Number(detail.total_cents) / detail.member_count : 0
    );
    var balance = Number(detail.my_balance_cents) || 0;
    $("metricBalance").textContent = signedMoney(balance);
    $("metricBalanceBox").classList.remove("is-positive", "is-negative");
    if (balance > 0) $("metricBalanceBox").classList.add("is-positive");
    if (balance < 0) $("metricBalanceBox").classList.add("is-negative");
    $("eventActions").hidden = !detail.can_manage;
    $("addExpenseBtn").hidden = !detail.can_add_expense;
    renderExpenses();
    renderBalances();
    renderTransfers();
    renderReceipt();
    refreshIcons();
  }

  async function loadDetail(eventId, updateUrl) {
    var requestId = ++state.requestId;
    try {
      var detail = await api("/api/aa/events/" + Number(eventId));
      if (requestId !== state.requestId) return;
      state.detail = detail;
      if (updateUrl !== false) setEventUrl(detail.id);
      renderEventList();
      renderDetail();
      refreshIcons();
    } catch (err) {
      if (requestId !== state.requestId) return;
      state.detail = null;
      renderEventList();
      renderDetail();
      toast(err.message);
    }
  }

  async function loadEvents(preferredId) {
    try {
      var data = await api("/api/aa/events");
      state.events = Array.isArray(data.events) ? data.events : [];
      state.currentUserId = Number(data.current_user_id) || 0;
      state.isAdmin = Boolean(data.is_admin);
      renderEventList();
      var wanted = Number(preferredId || (state.detail && state.detail.id) || currentEventIdFromUrl());
      var target = state.events.find(function (item) {
        return Number(item.id) === wanted;
      });
      if (!target && state.events.length) target = state.events[0];
      if (target) {
        await loadDetail(target.id, true);
      } else {
        state.detail = null;
        setEventUrl(null);
        renderDetail();
      }
      refreshIcons();
    } catch (err) {
      toast(err.message);
    }
  }

  function chooseReceipt() {
    $("receiptInput").click();
  }

  function openQrViewer(url) {
    $("qrViewerImage").src = url;
    $("qrViewer").hidden = false;
  }

  function closeQrViewer() {
    $("qrViewer").hidden = true;
    $("qrViewerImage").removeAttribute("src");
  }

  function readFileBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        var comma = result.indexOf(",");
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = function () {
        reject(new Error("读取图片失败。"));
      };
      reader.readAsDataURL(file);
    });
  }

  async function uploadReceipt(file) {
    if (!state.detail) return;
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast("收款码图片不能超过 5MB。");
      return;
    }
    try {
      var base64 = await readFileBase64(file);
      await api("/api/aa/events/" + state.detail.id + "/qr", {
        method: "POST",
        body: { name: file.name, data_base64: base64 },
      });
      await loadDetail(state.detail.id, false);
      toast("收款码已保存");
    } catch (err) {
      toast(err.message);
    }
  }

  async function deleteReceipt() {
    if (!state.detail) return;
    var ok = await askConfirm(
      "移除收款码",
      "确定移除这个活动的收款码吗？",
      "移除"
    );
    if (!ok) return;
    try {
      await api("/api/aa/events/" + state.detail.id + "/qr", { method: "DELETE" });
      await loadDetail(state.detail.id, false);
      toast("收款码已移除");
    } catch (err) {
      toast(err.message);
    }
  }

  async function loadCandidates() {
    if (state.candidates) return state.candidates;
    var data = await api("/api/aa/candidates");
    state.candidates = Array.isArray(data.users) ? data.users : [];
    return state.candidates;
  }

  function currentParticipantName() {
    if (!state.detail) return "我";
    var member = (state.detail.members || []).find(function (item) {
      return Number(item.user_id) === Number(state.currentUserId);
    });
    return member ? member.name : "我";
  }

  function updateParticipantCount() {
    var count = state.selectedParticipants.size;
    if (state.currentUserId === 0 && !state.selectedParticipants.has(0)) count += 1;
    $("participantCount").textContent = "已选 " + count + " 人";
  }

  function renderParticipants(filter) {
    var keyword = String(filter || "").trim().toLowerCase();
    var users = state.candidates || [];
    var html = users
      .filter(function (user) {
        if (!keyword) return true;
        return (
          String(user.name || "").toLowerCase().indexOf(keyword) >= 0 ||
          String(user.username || "").toLowerCase().indexOf(keyword) >= 0
        );
      })
      .map(function (user) {
        var id = Number(user.id);
        var checked = state.selectedParticipants.has(id);
        var isCurrent = id === Number(state.currentUserId);
        return (
          '<label class="aa-participant"><input type="checkbox" data-participant-id="' +
          id +
          '"' +
          (checked ? " checked" : "") +
          (isCurrent ? " disabled" : "") +
          "><span><strong>" +
          escapeHtml(user.name) +
          (isCurrent ? "（我）" : "") +
          "</strong><span>@" +
          escapeHtml(user.username) +
          "</span></span></label>"
        );
      })
      .join("");
    $("participantList").innerHTML =
      html || '<div class="aa-empty-row">没有可添加的账号</div>';
    updateParticipantCount();
  }

  async function openEventDialog(eventId) {
    try {
      await loadCandidates();
    } catch (err) {
      toast(err.message);
      return;
    }
    state.editingEventId = eventId ? Number(eventId) : null;
    var detail = eventId ? state.detail : null;
    $("eventDialogTitle").textContent = detail ? "编辑分账" : "新建分账";
    $("eventTitleInput").value = detail ? detail.title : "";
    state.selectedParticipants = new Set(
      detail
        ? (detail.members || []).map(function (item) {
            return Number(item.user_id);
          })
        : [Number(state.currentUserId)]
    );
    $("participantSearch").value = "";
    $("participantHint").textContent =
      "当前账号：" + (detail ? currentParticipantName() : "我");
    renderParticipants("");
    $("eventDialog").showModal();
    setTimeout(function () {
      $("eventTitleInput").focus();
    }, 0);
  }

  async function submitEvent(event) {
    event.preventDefault();
    var title = $("eventTitleInput").value.trim();
    if (!title) {
      toast("请填写活动名称。");
      $("eventTitleInput").focus();
      return;
    }
    var memberIds = Array.from(state.selectedParticipants);
    if (memberIds.length < 2) {
      toast("至少再选择一位参与人。");
      return;
    }
    var button = $("eventDialogSubmit");
    button.disabled = true;
    try {
      var data;
      if (state.editingEventId) {
        data = await api("/api/aa/events/" + state.editingEventId, {
          method: "PATCH",
          body: { title: title, member_ids: memberIds },
        });
      } else {
        data = await api("/api/aa/events", {
          method: "POST",
          body: { title: title, member_ids: memberIds },
        });
      }
      $("eventDialog").close();
      toast(state.editingEventId ? "分账已更新" : "分账已创建");
      state.editingEventId = null;
      await loadEvents(data.event && data.event.id);
    } catch (err) {
      toast(err.message);
    } finally {
      button.disabled = false;
    }
  }

  function openExpenseDialog(expenseId) {
    if (!state.detail) return;
    var expense = null;
    if (expenseId) {
      expense = (state.detail.expenses || []).find(function (item) {
        return Number(item.id) === Number(expenseId);
      });
    }
    state.editingExpenseId = expense ? Number(expense.id) : null;
    $("expenseDialogTitle").textContent = expense ? "修改费用" : "记一笔";
    $("expenseDialogMeta").textContent = "记在 " + currentParticipantName() + " 名下";
    $("expenseAmountInput").value = expense
      ? (Number(expense.amount_cents) / 100).toFixed(2)
      : "";
    $("expenseNoteInput").value = expense ? expense.note || "" : "";
    $("expenseDialog").showModal();
    setTimeout(function () {
      $("expenseAmountInput").focus();
    }, 0);
  }

  function parseMoneyCents(value) {
    var text = String(value || "").trim().replace(/,/g, "");
    if (!/^\d+(\.\d{0,2})?$/.test(text)) return null;
    var parts = text.split(".");
    var whole = Number(parts[0]);
    var fraction = Number(((parts[1] || "") + "00").slice(0, 2));
    var cents = whole * 100 + fraction;
    if (!Number.isSafeInteger(cents) || cents <= 0 || cents > 100000000) return null;
    return cents;
  }

  async function submitExpense(event) {
    event.preventDefault();
    if (!state.detail) return;
    var cents = parseMoneyCents($("expenseAmountInput").value);
    if (!cents) {
      toast("请输入有效金额。");
      $("expenseAmountInput").focus();
      return;
    }
    var note = $("expenseNoteInput").value.trim();
    var button = $("expenseDialogSubmit");
    button.disabled = true;
    try {
      var data;
      if (state.editingExpenseId) {
        data = await api("/api/aa/expenses/" + state.editingExpenseId, {
          method: "PATCH",
          body: { amount_cents: cents, note: note },
        });
      } else {
        data = await api("/api/aa/events/" + state.detail.id + "/expenses", {
          method: "POST",
          body: { amount_cents: cents, note: note },
        });
      }
      $("expenseDialog").close();
      state.editingExpenseId = null;
      if (data.event) {
        state.detail = data.event;
        renderDetail();
      }
      await loadEvents(data.event && data.event.id);
      toast("费用已保存");
    } catch (err) {
      toast(err.message);
    } finally {
      button.disabled = false;
    }
  }

  function askConfirm(title, text, okText) {
    if (state.confirmResolve) {
      state.confirmResolve(false);
      state.confirmResolve = null;
    }
    $("confirmTitle").textContent = title;
    $("confirmText").textContent = text;
    $("confirmOk").textContent = okText || "确定";
    $("confirmDialog").showModal();
    return new Promise(function (resolve) {
      state.confirmResolve = resolve;
    });
  }

  function finishConfirm(value) {
    if ($("confirmDialog").open) $("confirmDialog").close();
    if (state.confirmResolve) {
      state.confirmResolve(Boolean(value));
      state.confirmResolve = null;
    }
  }

  async function deleteExpense(expenseId) {
    if (!state.detail) return;
    var ok = await askConfirm("删除费用", "确定删除这笔费用吗？", "删除");
    if (!ok) return;
    try {
      var data = await api("/api/aa/expenses/" + Number(expenseId), {
        method: "DELETE",
      });
      if (data.event) {
        state.detail = data.event;
        renderDetail();
      }
      await loadEvents(state.detail && state.detail.id);
      toast("费用已删除");
    } catch (err) {
      toast(err.message);
    }
  }

  async function deleteCurrentEvent() {
    if (!state.detail) return;
    var eventId = state.detail.id;
    var ok = await askConfirm(
      "删除分账",
      "确定删除「" + state.detail.title + "」及其全部费用吗？",
      "删除"
    );
    if (!ok) return;
    try {
      await api("/api/aa/events/" + eventId, { method: "DELETE" });
      state.detail = null;
      setEventUrl(null);
      await loadEvents();
      toast("分账已删除");
    } catch (err) {
      toast(err.message);
    }
  }

  function bindEvents() {
    $("newEventBtn").addEventListener("click", function () {
      openEventDialog(null);
    });
    $("emptyCreateBtn").addEventListener("click", function () {
      openEventDialog(null);
    });
    $("eventList").addEventListener("click", function (event) {
      var button = event.target.closest("[data-event-id]");
      if (!button) return;
      loadDetail(Number(button.getAttribute("data-event-id")), true);
    });
    $("editEventBtn").addEventListener("click", function () {
      if (state.detail) openEventDialog(state.detail.id);
    });
    $("deleteEventBtn").addEventListener("click", deleteCurrentEvent);
    $("addExpenseBtn").addEventListener("click", function () {
      openExpenseDialog(null);
    });
    $("expenseList").addEventListener("click", function (event) {
      var edit = event.target.closest("[data-expense-edit]");
      if (edit) {
        openExpenseDialog(Number(edit.getAttribute("data-expense-edit")));
        return;
      }
      var remove = event.target.closest("[data-expense-delete]");
      if (remove) {
        deleteExpense(Number(remove.getAttribute("data-expense-delete")));
      }
    });
    $("participantList").addEventListener("change", function (event) {
      var input = event.target.closest("[data-participant-id]");
      if (!input) return;
      var id = Number(input.getAttribute("data-participant-id"));
      if (input.checked) state.selectedParticipants.add(id);
      else state.selectedParticipants.delete(id);
      updateParticipantCount();
    });
    $("participantSearch").addEventListener("input", function () {
      renderParticipants($("participantSearch").value);
    });
    $("eventForm").addEventListener("submit", submitEvent);
    $("expenseForm").addEventListener("submit", submitExpense);
    $("eventDialogClose").addEventListener("click", function () {
      $("eventDialog").close();
    });
    $("eventDialogCancel").addEventListener("click", function () {
      $("eventDialog").close();
    });
    $("expenseDialogClose").addEventListener("click", function () {
      $("expenseDialog").close();
    });
    $("expenseDialogCancel").addEventListener("click", function () {
      $("expenseDialog").close();
    });
    $("confirmOk").addEventListener("click", function () {
      finishConfirm(true);
    });
    $("confirmCancel").addEventListener("click", function () {
      finishConfirm(false);
    });
    $("confirmDialog").addEventListener("cancel", function (event) {
      event.preventDefault();
      finishConfirm(false);
    });
    $("receiptInput").addEventListener("change", function () {
      var file = this.files && this.files[0];
      this.value = "";
      uploadReceipt(file);
    });
    $("qrViewerClose").addEventListener("click", closeQrViewer);
    $("qrViewer").addEventListener("click", function (event) {
      if (event.target === $("qrViewer")) closeQrViewer();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !$("qrViewer").hidden) closeQrViewer();
    });
  }

  bindEvents();
  refreshIcons();
  loadEvents();
})();
