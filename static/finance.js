(function () {
  "use strict";

  var state = {
    events: [],
    detail: null,
    currentUserId: 0,
    isAdmin: false,
    candidates: null,
    editingEventId: null,
    inlineEditId: null,
    draftExpense: null,
    mobileEventsOpen: false,
    expensesCollapsed: false,
    transferPulse: false,
    selectedParticipants: new Set(),
    receiptTargetId: null,
    receiptButton: null,
    requestId: 0,
    toastTimer: null,
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

  function refreshButtons() {
    if (window.ErrorButtons && typeof window.ErrorButtons.refresh === "function") {
      window.ErrorButtons.refresh();
    }
  }

  function closeSplitPicker(picker) {
    if (!picker) return;
    var panel = picker.querySelector(".fin-split-picker-panel");
    var trigger = picker.querySelector("[data-split-toggle]");
    picker.classList.remove("is-open");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    if (panel) {
      window.setTimeout(function () {
        if (!picker.classList.contains("is-open")) panel.hidden = true;
      }, 180);
    }
  }

  function closeSplitPickers(except) {
    document.querySelectorAll(".fin-split-picker.is-open").forEach(function (picker) {
      if (picker !== except) closeSplitPicker(picker);
    });
  }

  function toggleSplitPicker(picker) {
    if (!picker) return;
    var panel = picker.querySelector(".fin-split-picker-panel");
    var trigger = picker.querySelector("[data-split-toggle]");
    if (!panel) return;
    if (picker.classList.contains("is-open")) {
      closeSplitPicker(picker);
      return;
    }
    closeSplitPickers(picker);
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    window.requestAnimationFrame(function () {
      picker.classList.add("is-open");
    });
  }

  function buttonBusy(button, label) {
    if (window.ErrorButtons) window.ErrorButtons.busy(button, label);
    else if (button) button.disabled = true;
  }

  function buttonSuccess(button, label) {
    if (window.ErrorButtons) window.ErrorButtons.success(button, { label: label });
  }

  function buttonFail(button) {
    if (window.ErrorButtons) window.ErrorButtons.fail(button);
    else if (button) button.disabled = false;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
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
    state.toastTimer = window.setTimeout(function () {
      box.hidden = true;
    }, 2600);
  }

  async function api(url, options) {
    var config = options || {};
    var headers = { Accept: "application/json" };
    if (config.body !== undefined) headers["Content-Type"] = "application/json";
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

  function isMobileEvents() {
    return window.matchMedia && window.matchMedia("(max-width: 820px)").matches;
  }

  function setMobileEventsOpen(open) {
    state.mobileEventsOpen = Boolean(open) && isMobileEvents();
    var sidebar = document.querySelector(".fin-sidebar");
    var button = $("mobileEventsBtn");
    if (sidebar) sidebar.classList.toggle("is-mobile-open", state.mobileEventsOpen);
    if (button) {
      button.setAttribute("aria-expanded", state.mobileEventsOpen ? "true" : "false");
      button.title = state.mobileEventsOpen ? "收起账目" : "展开账目";
      button.setAttribute(
        "aria-label",
        state.mobileEventsOpen ? "收起账目" : "展开账目"
      );
    }
  }

  function setExpensesCollapsed(collapsed) {
    state.expensesCollapsed = Boolean(collapsed);
    var panel = document.querySelector(".fin-expenses-panel");
    var toggle = $("expensesToggle");
    var label = $("expensesToggleLabel");
    if (panel) panel.classList.toggle("is-collapsed", state.expensesCollapsed);
    if (toggle) {
      toggle.setAttribute(
        "aria-expanded",
        state.expensesCollapsed ? "false" : "true"
      );
      toggle.title = state.expensesCollapsed ? "展开费用明细" : "折叠费用明细";
      toggle.setAttribute(
        "aria-label",
        state.expensesCollapsed ? "展开费用明细" : "折叠费用明细"
      );
    }
    if (label) {
      label.textContent = state.expensesCollapsed ? "展开" : "折叠";
    }
  }

  function setTransferPulse(active) {
    state.transferPulse = Boolean(active);
    var panel = $("transferPanel");
    if (panel) panel.classList.toggle("is-fresh", state.transferPulse);
  }

  function syncFinanceLayoutHeight() {
    var layout = document.querySelector(".fin-layout");
    var side = document.querySelector(".fin-side-column");
    if (!layout || !side) return;
    if (isMobileEvents()) {
      layout.style.minHeight = "";
      return;
    }
    var bottom = side.offsetTop + side.offsetHeight + 24;
    layout.style.minHeight = Math.max(window.innerHeight, bottom) + "px";
  }

  function balanceClass(value) {
    var number = Number(value) || 0;
    if (number > 0) return "is-positive";
    if (number < 0) return "is-negative";
    return "";
  }

  function renderEventList() {
    var list = $("eventList");
    if (!state.events.length) {
      list.innerHTML = '<div class="fin-empty-row">没有账目</div>';
      return;
    }
    list.innerHTML = state.events
      .map(function (item) {
        var active = state.detail && Number(state.detail.id) === Number(item.id);
        var balance = Number(item.my_balance_cents) || 0;
        var balanceText =
          balance > 0 ? "应收 " + money(balance) : balance < 0 ? "应付 " + money(-balance) : "已平";
        return (
          '<button class="fin-event-item' +
          (active ? " is-active" : "") +
          '" type="button" data-event-id="' +
          Number(item.id) +
          '">' +
          '<span class="fin-event-item-top"><strong>' +
          escapeHtml(item.title) +
          "</strong><b>" +
          escapeHtml(money(item.total_cents)) +
          "</b></span>" +
          '<span class="fin-event-item-bottom"><span>' +
          Number(item.member_count) +
          " 人 · " +
          escapeHtml(balanceText) +
          "</span><span>" +
          escapeHtml(formatTime(item.updated_at)) +
          "</span></span></button>"
        );
      })
      .join("");
  }

  function splitCheckboxes(members, selectedIds, attributeName) {
    var selected = new Set((selectedIds || []).map(Number));
    return (members || [])
      .map(function (member) {
        var id = Number(member.user_id);
        return (
          '<label class="fin-check-item"><input type="checkbox" data-' +
          attributeName +
          '="' +
          id +
          '"' +
          (selected.has(id) ? " checked" : "") +
          "><span><strong>" +
          escapeHtml(member.name) +
          '</strong><span>@' +
          escapeHtml(member.username || "member") +
          "</span></span></label>"
        );
      })
      .join("");
  }

  function renderExpenseView(item) {
    var splitNames = (item.split_names || []).join("、") || "未设置分摊人";
    var note = item.note || "未填写备注";
    var actions = item.can_edit
      ? '<span class="fin-row-actions">' +
        '<button class="fin-row-btn is-danger" type="button" data-expense-delete="' +
        Number(item.id) +
        '" data-hold-confirm title="长按删除" aria-label="长按删除费用"><i data-lucide="trash-2"></i></button>' +
        "</span>"
      : "";
    return (
      '<div class="fin-expense-row">' +
      '<strong class="fin-expense-amount fin-expense-trigger" data-expense-start-edit="' +
      Number(item.id) +
      '" tabindex="0" role="button" title="点击编辑金额">' +
      escapeHtml(money(item.amount_cents)) +
      "</strong>" +
      '<div class="fin-expense-info fin-expense-trigger" data-expense-start-edit="' +
      Number(item.id) +
      '" tabindex="0" role="button" title="点击编辑备注"><p class="fin-expense-note' +
      (item.note ? "" : " is-empty") +
      '">' +
      escapeHtml(note) +
      '</p><span class="fin-expense-meta">' +
      escapeHtml(item.user_name || "成员") +
      " 垫付 · " +
      escapeHtml(formatTime(item.created_at)) +
      "</span></div>" +
      '<div class="fin-expense-split fin-expense-trigger" data-expense-start-edit="' +
      Number(item.id) +
      '" tabindex="0" role="button" title="点击编辑分摊人"><strong>' +
      Number((item.split_user_ids || []).length) +
      " 人分摊</strong><small>" +
      escapeHtml(splitNames) +
      "</small></div>" +
      actions +
      "</div>"
    );
  }

  function renderExpenseEditor(item) {
    var splitIds = item.split_user_ids || [];
    return (
      '<form class="fin-inline-editor" data-inline-expense-form="' +
      Number(item.id) +
      '">' +
      '<label class="fin-inline-amount"><span>¥</span><input name="amount" inputmode="decimal" value="' +
      escapeHtml((Number(item.amount_cents) / 100).toFixed(2)) +
      '"></label>' +
      '<label class="fin-inline-note"><input name="note" maxlength="120" value="' +
      escapeHtml(item.note || "") +
      '" placeholder="备注"></label>' +
      '<div class="fin-split-picker"><button class="fin-split-trigger" type="button" data-split-toggle aria-expanded="false"><span data-inline-split-summary>' +
      splitIds.length +
      ' 人分摊</span><span class="fin-split-chevron"><i data-lucide="chevron-down"></i></span></button><div class="fin-split-picker-panel" hidden>' +
      splitCheckboxes(
        state.detail.members,
        splitIds,
        "inline-split-id"
      ) +
      "</div></div>" +
      '<span class="fin-inline-actions">' +
      '<button class="fin-check-btn" type="submit" title="保存" aria-label="保存费用"><i data-lucide="check"></i></button>' +
      '<button class="fin-cancel-btn" type="button" data-inline-cancel title="取消编辑" aria-label="取消编辑"><i data-lucide="x"></i></button>' +
      '<button class="fin-row-btn is-danger" type="button" data-expense-delete="' +
      Number(item.id) +
      '" data-hold-confirm title="长按删除" aria-label="长按删除费用"><i data-lucide="trash-2"></i></button>' +
      "</span></form>"
    );
  }

  function renderDraftEditor() {
    var draft = state.draftExpense;
    var memberIds = (state.detail.members || []).map(function (member) {
      return Number(member.user_id);
    });
    return (
      '<form class="fin-inline-editor" data-draft-expense-form>' +
      '<label class="fin-inline-amount"><span>¥</span><input name="amount" inputmode="decimal" value="' +
      escapeHtml(draft.amount || "") +
      '" placeholder="0.00" autofocus></label>' +
      '<label class="fin-inline-note"><input name="note" maxlength="120" value="' +
      escapeHtml(draft.note || "") +
      '" placeholder="备注"></label>' +
      '<div class="fin-split-picker"><button class="fin-split-trigger" type="button" data-split-toggle aria-expanded="false"><span data-inline-split-summary>' +
      memberIds.length +
      ' 人分摊</span><span class="fin-split-chevron"><i data-lucide="chevron-down"></i></span></button><div class="fin-split-picker-panel" hidden>' +
      splitCheckboxes(state.detail.members, memberIds, "draft-split-id") +
      "</div></div>" +
      '<span class="fin-inline-actions">' +
      '<button class="fin-check-btn" type="submit" title="保存" aria-label="保存费用"><i data-lucide="check"></i></button>' +
      '<button class="fin-cancel-btn" type="button" data-draft-cancel title="取消" aria-label="取消这笔费用"><i data-lucide="x"></i></button>' +
      "</span></form>"
    );
  }

  function renderExpenses() {
    var detail = state.detail;
    var list = $("expenseList");
    var expenses = detail.expenses || [];
    $("expenseMeta").textContent =
      expenses.length + " 笔" + (state.draftExpense ? " · 1 笔未保存" : "");
    setAddExpenseVisibility(
      detail.can_add_expense && !state.draftExpense && !state.inlineEditId
    );
    if (!expenses.length && !state.draftExpense) {
      list.innerHTML = '<div class="fin-empty-row">还没有费用记录</div>';
      return;
    }
    var draftHtml = state.draftExpense
      ? '<article class="fin-expense-item is-draft" data-draft-expense>' +
        renderDraftEditor() +
        "</article>"
      : "";
    list.innerHTML =
      draftHtml +
      expenses
      .map(function (item) {
        return (
          '<article class="fin-expense-item' +
          (Number(state.inlineEditId) === Number(item.id) ? " is-editing" : "") +
          '" data-expense-item="' +
          Number(item.id) +
          '">' +
          (Number(state.inlineEditId) === Number(item.id)
            ? renderExpenseEditor(item)
            : renderExpenseView(item)) +
          "</article>"
        );
      })
      .join("");
    refreshIcons();
    refreshButtons();
  }

  function renderBalances() {
    var members = state.detail.members || [];
    $("balanceList").innerHTML = members
      .map(function (item) {
        var value = Number(item.balance_cents) || 0;
        var stateText = value > 0 ? "应收" : value < 0 ? "应付" : "已平";
        return (
          '<div class="fin-balance-item">' +
          '<div class="fin-person"><strong>' +
          escapeHtml(item.name) +
          "</strong><span>垫付 " +
          escapeHtml(money(item.paid_cents)) +
          " · 应分 " +
          escapeHtml(money(item.share_cents)) +
          "</span></div>" +
          '<span class="fin-balance-value ' +
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
        '<div class="fin-empty-row">' +
        (Number(state.detail.total_cents) ? "当前已经平账" : "录入费用后生成方案") +
        "</div>";
      return;
    }
    $("transferList").innerHTML = transfers
      .map(function (item) {
        return (
          '<div class="fin-transfer-item">' +
          '<div class="fin-transfer-route"><b>' +
          escapeHtml(item.from_name) +
          "</b> 转给 <b>" +
          escapeHtml(item.to_name) +
          "</b><span>单笔结清</span></div>" +
          '<span class="fin-transfer-amount">' +
          escapeHtml(money(item.amount_cents)) +
          "</span></div>"
        );
      })
      .join("");
  }

  function renderReceiptsDialog() {
    var receipts = (state.detail && state.detail.receipts) || [];
    $("receiptGrid").innerHTML = receipts
      .map(function (item) {
        var actions = item.can_edit
          ? '<div class="fin-receipt-actions">' +
            '<button class="fin-btn" type="button" data-receipt-upload="' +
            Number(item.user_id) +
            '"><i data-lucide="' +
            (item.url ? "refresh-cw" : "image-up") +
            '"></i><span>' +
            (item.url ? "更换" : "上传") +
            "</span></button>" +
            (item.url
              ? '<button class="fin-row-btn is-danger" type="button" data-receipt-delete="' +
                Number(item.user_id) +
                '" data-hold-confirm title="长按删除" aria-label="长按删除收款码"><i data-lucide="trash-2"></i></button>'
              : "") +
            "</div>"
          : "";
        return (
          '<article class="fin-receipt-card">' +
          '<div class="fin-receipt-card-head"><strong>' +
          escapeHtml(item.name) +
          "</strong><span>" +
          (item.is_self ? "我" : item.url ? "已添加" : "未添加") +
          "</span></div>" +
          (item.url
            ? '<img data-receipt-view="' +
              escapeHtml(item.url) +
              '" src="' +
              escapeHtml(item.url) +
              '" alt="' +
              escapeHtml(item.name) +
              '的收款码">'
            : '<div class="fin-receipt-placeholder"><span>还没有收款码</span></div>') +
          actions +
          "</article>"
        );
      })
      .join("");
    refreshIcons();
    refreshButtons();
  }

  function setFloatingActions() {
    var detail = state.detail;
    setAddExpenseVisibility(
      Boolean(detail && detail.can_add_expense) &&
        !state.draftExpense &&
        !state.inlineEditId
    );
    $("editEventBtn").hidden = !detail;
    $("receiptsBtn").hidden = !detail;
    $("deleteEventBtn").hidden = !detail;
    $("deleteEventBtn").toggleAttribute(
      "data-hold-confirm",
      Boolean(detail && detail.can_manage)
    );
    refreshButtons();
  }

  function setAddExpenseVisibility(visible) {
    var button = $("addExpenseBtn");
    if (!button) return;
    button.hidden = false;
    button.classList.toggle("is-fading", !visible);
  }

  function renderDetail() {
    var detail = state.detail;
    var empty = $("emptyState");
    var view = $("eventView");
    setFloatingActions();
    setExpensesCollapsed(state.expensesCollapsed);
    if (!detail) {
      empty.hidden = false;
      view.hidden = true;
      document.title = "计算器";
      return;
    }
    empty.hidden = true;
    view.hidden = false;
    document.title = "计算器";
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
    renderExpenses();
    renderBalances();
    renderTransfers();
    if ($("receiptsDialog").open) renderReceiptsDialog();
    refreshIcons();
    refreshButtons();
    syncFinanceLayoutHeight();
  }

  async function loadDetail(eventId, updateUrl) {
    var requestId = ++state.requestId;
    try {
      var detail = await api("/api/aa/events/" + Number(eventId));
      if (requestId !== state.requestId) return;
      state.detail = detail;
      state.inlineEditId = null;
      state.expensesCollapsed = false;
      setTransferPulse(false);
      if (updateUrl !== false) setEventUrl(detail.id);
      renderEventList();
      renderDetail();
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
      var wanted = Number(
        preferredId || (state.detail && state.detail.id) || currentEventIdFromUrl()
      );
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

  function renderParticipants() {
    var users = state.candidates || [];
    var html = users
      .map(function (user) {
        var id = Number(user.id);
        var checked = state.selectedParticipants.has(id);
        var isCurrent = id === Number(state.currentUserId);
        return (
          '<label class="fin-check-item"><input type="checkbox" data-participant-id="' +
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
      html || '<div class="fin-empty-row">没有可添加的账号</div>';
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
    $("eventDialogTitle").textContent = detail ? "编辑账目" : "新建账目";
    $("eventTitleInput").value = detail ? detail.title : "";
    state.selectedParticipants = new Set(
      detail
        ? (detail.members || []).map(function (item) {
            return Number(item.user_id);
          })
        : [Number(state.currentUserId)]
    );
    $("participantHint").textContent =
      "当前账号：" + (detail ? currentParticipantName() : "我");
    renderParticipants();
    $("eventDialog").showModal();
    window.setTimeout(function () {
      $("eventTitleInput").focus();
    }, 0);
  }

  async function submitEvent(event) {
    event.preventDefault();
    var title = $("eventTitleInput").value.trim();
    if (!title) {
      toast("请填写账目名称。");
      $("eventTitleInput").focus();
      return;
    }
    var memberIds = Array.from(state.selectedParticipants);
    if (memberIds.length < 2) {
      toast("至少再选择一位参与人。");
      return;
    }
    var button = $("eventDialogSubmit");
    buttonBusy(button, "正在保存");
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
      buttonSuccess(button, state.editingEventId ? "已更新" : "已创建");
      await sleep(430);
      $("eventDialog").close();
      toast(state.editingEventId ? "账目已更新" : "账目已创建");
      state.editingEventId = null;
      await loadEvents(data.event && data.event.id);
    } catch (err) {
      buttonFail(button);
      toast(err.message);
    }
  }

  function addDraftExpense() {
    if (!state.detail || state.draftExpense) return;
    setExpensesCollapsed(false);
    state.inlineEditId = null;
    state.draftExpense = { amount: "", note: "" };
    renderExpenses();
    setFloatingActions();
    var input = document.querySelector('[data-draft-expense-form] [name="amount"]');
    if (input) {
      window.setTimeout(function () {
        input.focus();
      }, 0);
    }
  }

  function cancelDraftExpense() {
    state.draftExpense = null;
    renderExpenses();
    setFloatingActions();
  }

  function activeExpenseItem() {
    return document.querySelector(
      ".fin-expense-item.is-editing, .fin-expense-item.is-draft"
    );
  }

  function cancelActiveExpenseEdit() {
    if (!state.inlineEditId && !state.draftExpense) return false;
    state.inlineEditId = null;
    state.draftExpense = null;
    closeSplitPickers(null);
    renderExpenses();
    setFloatingActions();
    return true;
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

  async function saveDraftExpense(form) {
    if (!state.detail || !form) return;
    var cents = parseMoneyCents(form.querySelector('[name="amount"]').value);
    if (!cents) {
      toast("请输入有效金额。");
      form.querySelector('[name="amount"]').focus();
      return;
    }
    var splitIds = Array.from(
      form.querySelectorAll("[data-draft-split-id]:checked")
    ).map(function (input) {
      return Number(input.getAttribute("data-draft-split-id"));
    });
    if (!splitIds.length) {
      toast("请至少选择一位分摊人。");
      return;
    }
    var button = form.querySelector('button[type="submit"]');
    buttonBusy(button, "正在保存");
    try {
      var data = await api("/api/aa/events/" + state.detail.id + "/expenses", {
        method: "POST",
        body: {
          amount_cents: cents,
          note: form.querySelector('[name="note"]').value.trim(),
          split_user_ids: splitIds,
        },
      });
      buttonSuccess(button, "已保存");
      await sleep(430);
      state.draftExpense = null;
      if (data.event) state.detail = data.event;
      renderDetail();
      await loadEvents(state.detail && state.detail.id);
      setTransferPulse(true);
      toast("费用已保存");
    } catch (err) {
      buttonFail(button);
      toast(err.message);
    }
  }

  async function saveInlineExpense(form) {
    var expenseId = Number(form.getAttribute("data-inline-expense-form"));
    var cents = parseMoneyCents(form.querySelector('[name="amount"]').value);
    if (!cents) {
      toast("请输入有效金额。");
      return;
    }
    var splitIds = Array.from(
      form.querySelectorAll("[data-inline-split-id]:checked")
    ).map(function (input) {
      return Number(input.getAttribute("data-inline-split-id"));
    });
    if (!splitIds.length) {
      toast("请至少选择一位分摊人。");
      return;
    }
    var button = form.querySelector('button[type="submit"]');
    buttonBusy(button, "正在保存");
    try {
      var data = await api("/api/aa/expenses/" + expenseId, {
        method: "PATCH",
        body: {
          amount_cents: cents,
          note: form.querySelector('[name="note"]').value.trim(),
          split_user_ids: splitIds,
        },
      });
      buttonSuccess(button, "已保存");
      await sleep(500);
      state.inlineEditId = null;
      if (data.event) state.detail = data.event;
      renderDetail();
      await loadEvents(state.detail && state.detail.id);
      setTransferPulse(true);
      toast("费用已更新");
    } catch (err) {
      buttonFail(button);
      toast(err.message);
    }
  }

  async function deleteExpense(expenseId) {
    if (!state.detail) return;
    try {
      var data = await api("/api/aa/expenses/" + Number(expenseId), {
        method: "DELETE",
      });
      state.inlineEditId = null;
      if (data.event) state.detail = data.event;
      renderDetail();
      await loadEvents(state.detail && state.detail.id);
      toast("费用已删除");
    } catch (err) {
      toast(err.message);
    }
  }

  async function deleteCurrentEvent() {
    if (!state.detail) return;
    if (!state.detail.can_manage) {
      toast("只有创建人可以删除这个账目。");
      return;
    }
    var eventId = state.detail.id;
    try {
      await api("/api/aa/events/" + eventId, { method: "DELETE" });
      state.detail = null;
      setEventUrl(null);
      await loadEvents();
      toast("账目已删除");
    } catch (err) {
      toast(err.message);
    }
  }

  function openReceipts() {
    if (!state.detail) return;
    renderReceiptsDialog();
    $("receiptsDialog").showModal();
  }

  function chooseReceipt(userId, button) {
    state.receiptTargetId = Number(userId);
    state.receiptButton = button || null;
    $("receiptInput").click();
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
    if (!state.detail || state.receiptTargetId === null) return;
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast("收款码图片不能超过 5MB。");
      return;
    }
    buttonBusy(state.receiptButton, "正在上传");
    try {
      var base64 = await readFileBase64(file);
      var data = await api("/api/aa/events/" + state.detail.id + "/receipts", {
        method: "POST",
        body: {
          user_id: state.receiptTargetId,
          name: file.name,
          data_base64: base64,
        },
      });
      if (data.event) state.detail = data.event;
      buttonSuccess(state.receiptButton, "已保存");
      renderDetail();
      renderReceiptsDialog();
      toast("收款码已保存");
    } catch (err) {
      buttonFail(state.receiptButton);
      toast(err.message);
    } finally {
      state.receiptTargetId = null;
      state.receiptButton = null;
    }
  }

  async function deleteReceipt(userId) {
    if (!state.detail) return;
    try {
      var data = await api(
        "/api/aa/events/" + state.detail.id + "/receipts/" + Number(userId),
        { method: "DELETE" }
      );
      if (data.event) state.detail = data.event;
      renderDetail();
      renderReceiptsDialog();
      toast("收款码已删除");
    } catch (err) {
      toast(err.message);
    }
  }

  function openQrViewer(url) {
    $("qrViewerImage").src = url;
    $("qrViewer").hidden = false;
  }

  function closeQrViewer() {
    $("qrViewer").hidden = true;
    $("qrViewerImage").removeAttribute("src");
  }

  function syncDialogScrollLock() {
    document.body.classList.toggle(
      "fin-dialog-open",
      Boolean(document.querySelector("dialog[open]"))
    );
  }

  function bindEvents() {
    $("newEventBtn").addEventListener("click", function () {
      openEventDialog(null);
    });
    $("addExpenseBtn").addEventListener("click", function (event) {
      event.stopPropagation();
      addDraftExpense();
    });
    $("editEventBtn").addEventListener("click", function () {
      if (!state.detail) return;
      if (!state.detail.can_manage) {
        toast("只有创建人可以修改参与人。");
        return;
      }
      openEventDialog(state.detail.id);
    });
    $("deleteEventBtn").addEventListener("click", deleteCurrentEvent);
    $("receiptsBtn").addEventListener("click", openReceipts);

    $("eventList").addEventListener("click", function (event) {
      var button = event.target.closest("[data-event-id]");
      if (!button) return;
      setMobileEventsOpen(false);
      loadDetail(Number(button.getAttribute("data-event-id")), true);
    });

    $("expenseList").addEventListener("click", function (event) {
      var active = activeExpenseItem();
      if (active && !active.contains(event.target)) {
        cancelActiveExpenseEdit();
        return;
      }
      var splitToggle = event.target.closest("[data-split-toggle]");
      if (splitToggle) {
        event.preventDefault();
        toggleSplitPicker(splitToggle.closest(".fin-split-picker"));
        return;
      }
      var cancelEdit = event.target.closest("[data-inline-cancel]");
      if (cancelEdit) {
        state.inlineEditId = null;
        renderExpenses();
        setFloatingActions();
        return;
      }
      var edit = event.target.closest("[data-expense-start-edit]");
      if (edit) {
        if (state.draftExpense) {
          toast("请先保存或取消这笔空白费用。");
          return;
        }
        state.inlineEditId = Number(edit.getAttribute("data-expense-start-edit"));
        renderExpenses();
        setFloatingActions();
        event.stopPropagation();
        return;
      }
      var cancelDraft = event.target.closest("[data-draft-cancel]");
      if (cancelDraft) {
        cancelDraftExpense();
        return;
      }
      var remove = event.target.closest("[data-expense-delete]");
      if (remove) {
        deleteExpense(Number(remove.getAttribute("data-expense-delete")));
      }
    });

    $("expenseList").addEventListener("change", function (event) {
      var input = event.target.closest(
        "[data-inline-split-id], [data-draft-split-id]"
      );
      if (!input) return;
      var form = input.closest("[data-inline-expense-form], [data-draft-expense-form]");
      var summary = form && form.querySelector("[data-inline-split-summary]");
      if (summary) {
        summary.textContent =
          form.querySelectorAll(
            "[data-inline-split-id]:checked, [data-draft-split-id]:checked"
          ).length + " 人分摊";
      }
    });

    $("expenseList").addEventListener("submit", function (event) {
      var draftForm = event.target.closest("[data-draft-expense-form]");
      if (draftForm) {
        event.preventDefault();
        saveDraftExpense(draftForm);
        return;
      }
      var form = event.target.closest("[data-inline-expense-form]");
      if (!form) return;
      event.preventDefault();
      saveInlineExpense(form);
    });

    $("expenseList").addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      var edit = event.target.closest("[data-expense-start-edit]");
      if (!edit) return;
      event.preventDefault();
      if (state.draftExpense) {
        toast("请先保存或取消这笔空白费用。");
        return;
      }
      state.inlineEditId = Number(edit.getAttribute("data-expense-start-edit"));
      renderExpenses();
      setFloatingActions();
    });

    $("participantList").addEventListener("change", function (event) {
      var input = event.target.closest("[data-participant-id]");
      if (!input) return;
      var id = Number(input.getAttribute("data-participant-id"));
      if (input.checked) state.selectedParticipants.add(id);
      else state.selectedParticipants.delete(id);
      updateParticipantCount();
    });

    $("eventForm").addEventListener("submit", submitEvent);
    $("mobileEventsBtn").addEventListener("click", function (event) {
      event.stopPropagation();
      setMobileEventsOpen(!state.mobileEventsOpen);
    });
    $("expensesToggle").addEventListener("click", function () {
      setExpensesCollapsed(!state.expensesCollapsed);
    });

    $("eventDialogClose").addEventListener("click", function () {
      $("eventDialog").close();
    });
    $("eventDialogCancel").addEventListener("click", function () {
      $("eventDialog").close();
    });
    $("receiptsDialogClose").addEventListener("click", function () {
      $("receiptsDialog").close();
    });

    $("receiptGrid").addEventListener("click", function (event) {
      var upload = event.target.closest("[data-receipt-upload]");
      if (upload) {
        chooseReceipt(
          Number(upload.getAttribute("data-receipt-upload")),
          upload
        );
        return;
      }
      var remove = event.target.closest("[data-receipt-delete]");
      if (remove) {
        deleteReceipt(Number(remove.getAttribute("data-receipt-delete")));
        return;
      }
      var image = event.target.closest("[data-receipt-view]");
      if (image) openQrViewer(image.getAttribute("data-receipt-view"));
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
      if (event.key === "Escape") closeSplitPickers(null);
    });
    document.addEventListener("click", function (event) {
      if (state.transferPulse) setTransferPulse(false);
      if (
        state.mobileEventsOpen &&
        !event.target.closest(".fin-sidebar") &&
        !event.target.closest("#mobileEventsBtn")
      ) {
        setMobileEventsOpen(false);
      }
      var active = activeExpenseItem();
      if (active && !active.contains(event.target)) {
        cancelActiveExpenseEdit();
      }
      if (event.target.closest(".fin-split-picker")) return;
      closeSplitPickers(null);
    });
    document.querySelectorAll("dialog").forEach(function (dialog) {
      dialog.addEventListener("toggle", syncDialogScrollLock);
      dialog.addEventListener("close", syncDialogScrollLock);
    });
    window.addEventListener("resize", function () {
      if (!isMobileEvents()) setMobileEventsOpen(false);
      syncFinanceLayoutHeight();
    });
    syncDialogScrollLock();
    syncFinanceLayoutHeight();
  }

  bindEvents();
  refreshIcons();
  loadEvents();
})();
