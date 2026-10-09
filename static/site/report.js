(function () {
  "use strict";

  var REPORT_EMAIL = "2873523107@qq.com";
  var REASONS = ["违法违规", "色情低俗", "暴力恐怖", "诈骗广告", "侵权或隐私", "其他"];
  var overlay = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function ensureModal() {
    if (overlay) return overlay;
    overlay = el("div", "er-report-overlay");
    overlay.hidden = true;
    var dialog = el("form", "er-report-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "erReportTitle");

    var head = el("div", "er-report-head");
    var title = el("h2", "", "举报与投诉");
    title.id = "erReportTitle";
    var close = el("button", "er-report-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "关闭");
    head.append(title, close);

    var target = el("p", "er-report-target");
    var reasonLabel = el("label", "er-report-field");
    reasonLabel.appendChild(el("span", "", "举报理由"));
    var select = document.createElement("select");
    select.required = true;
    select.appendChild(new Option("请选择举报理由", ""));
    REASONS.forEach(function (reason) {
      select.appendChild(new Option(reason, reason));
    });
    reasonLabel.appendChild(select);

    var detailLabel = el("label", "er-report-field");
    detailLabel.appendChild(el("span", "", "补充说明（可选）"));
    var detail = document.createElement("textarea");
    detail.rows = 4;
    detail.maxLength = 1000;
    detail.placeholder = "请说明问题和发生位置，便于管理员核实。";
    detailLabel.appendChild(detail);

    var contactLabel = el("label", "er-report-field");
    contactLabel.appendChild(el("span", "", "联系方式（可选）"));
    var contact = document.createElement("input");
    contact.type = "text";
    contact.maxLength = 200;
    contact.placeholder = "邮箱、手机号或其他联系方式";
    contactLabel.appendChild(contact);

    var note = el("p", "er-report-note");
    note.append("也可以直接发送邮件至 ");
    var mail = el("a", "", REPORT_EMAIL);
    mail.href = "mailto:" + REPORT_EMAIL;
    note.appendChild(mail);
    note.append("。管理员会在 24 小时内开始核实处理。");

    var error = el("p", "er-report-error");
    error.hidden = true;
    var actions = el("div", "er-report-actions");
    var cancel = el("button", "er-report-btn", "取消");
    cancel.type = "button";
    var submit = el("button", "er-report-btn is-primary", "提交举报");
    submit.type = "submit";
    actions.append(cancel, submit);

    dialog.append(head, target, reasonLabel, detailLabel, contactLabel, note, error, actions);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    function closeModal() {
      overlay.hidden = true;
      dialog.reset();
      error.hidden = true;
      submit.disabled = false;
    }
    close.addEventListener("click", closeModal);
    cancel.addEventListener("click", closeModal);
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) closeModal();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !overlay.hidden) closeModal();
    });
    dialog.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (!select.value) {
        error.textContent = "请选择举报理由。";
        error.hidden = false;
        return;
      }
      submit.disabled = true;
      error.hidden = true;
      try {
        var response = await fetch("/api/site/reports", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_type: dialog.dataset.targetType,
            target_key: dialog.dataset.targetKey,
            reason: select.value,
            detail: detail.value.trim(),
            contact: contact.value.trim(),
          }),
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok) throw new Error(data.error || "提交失败");
        closeModal();
        await window.ErrorDialog.alert("举报已提交，管理员会尽快核实处理。", {
          title: "举报已提交",
        });
      } catch (err) {
        error.textContent = err.message || "提交失败";
        error.hidden = false;
        submit.disabled = false;
      }
    });
    return overlay;
  }

  async function open(options) {
    var opts = options || {};
    if (!opts.targetType || !opts.targetKey) return;
    var modal = ensureModal();
    var dialog = modal.querySelector(".er-report-dialog");
    if (opts.requiresLogin) {
      try {
        var response = await fetch("/api/auth/status", { cache: "no-store" });
        var status = await response.json();
        if (!status.authenticated) {
          await window.ErrorDialog.alert("登录后可以举报留言和动态。", {
            title: "请先登录",
          });
          return;
        }
      } catch (err) {
        await window.ErrorDialog.alert("暂时无法确认登录状态，请稍后再试。", {
          title: "暂时无法提交",
        });
        return;
      }
    }
    dialog.dataset.targetType = opts.targetType;
    dialog.dataset.targetKey = String(opts.targetKey);
    dialog.querySelector(".er-report-target").textContent =
      "举报对象：" + (opts.title || "当前内容");
    modal.hidden = false;
    var select = dialog.querySelector("select");
    if (select) select.focus();
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-report-type]");
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();
    open({
      targetType: trigger.getAttribute("data-report-type"),
      targetKey: trigger.getAttribute("data-report-key"),
      title: trigger.getAttribute("data-report-title") || "",
      requiresLogin: trigger.getAttribute("data-report-login") === "1",
    }).catch(function () {});
  });

  window.ErrorReport = { open: open, email: REPORT_EMAIL };
})();
