(function () {
  "use strict";

  if (window.ErrorDialog) return;

  var overlay = null;
  var resolveCurrent = null;
  var mode = "alert";

  if (!document.querySelector('link[data-error-dialog-style]')) {
    var styleLink = document.createElement("link");
    styleLink.rel = "stylesheet";
    styleLink.href = "/static/site/dialog.css";
    styleLink.setAttribute("data-error-dialog-style", "1");
    document.head.appendChild(styleLink);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function ensureDialog() {
    if (overlay) return overlay;
    overlay = el("div", "site-dialog-overlay");
    overlay.hidden = true;
    var dialog = el("div", "site-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "siteDialogTitle");

    var head = el("div", "site-dialog-head");
    var title = el("h2", "", "提示");
    title.id = "siteDialogTitle";
    var close = el("button", "site-dialog-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "关闭");
    head.append(title, close);

    var body = el("div", "site-dialog-body");
    var message = el("p", "site-dialog-message");
    var inputWrap = el("label", "site-dialog-input");
    var input = document.createElement("textarea");
    input.rows = 4;
    input.maxLength = 1000;
    inputWrap.appendChild(input);
    body.append(message, inputWrap);

    var error = el("p", "site-dialog-error");
    error.hidden = true;
    var actions = el("div", "site-dialog-actions");
    var cancel = el("button", "site-dialog-btn", "取消");
    cancel.type = "button";
    var confirm = el("button", "site-dialog-btn is-primary", "确定");
    confirm.type = "button";
    actions.append(cancel, confirm);

    dialog.append(head, body, error, actions);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    function finish(result) {
      var resolve = resolveCurrent;
      resolveCurrent = null;
      overlay.hidden = true;
      error.hidden = true;
      if (resolve) resolve(result);
    }

    close.addEventListener("click", function () {
      finish(mode === "prompt" ? null : false);
    });
    cancel.addEventListener("click", function () {
      finish(mode === "prompt" ? null : false);
    });
    confirm.addEventListener("click", function () {
      if (mode === "prompt") {
        finish(input.value);
      } else {
        finish(true);
      }
    });
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        finish(mode === "prompt" ? null : false);
      }
    });
    document.addEventListener("keydown", function (event) {
      if (overlay.hidden) return;
      if (event.key === "Escape") {
        finish(mode === "prompt" ? null : false);
      } else if (
        event.key === "Enter" &&
        mode === "prompt" &&
        !event.shiftKey &&
        document.activeElement === input
      ) {
        event.preventDefault();
        finish(input.value);
      }
    });
    return overlay;
  }

  function open(options) {
    var opts = options || {};
    var modal = ensureDialog();
    var dialog = modal.querySelector(".site-dialog");
    mode = opts.mode || "alert";
    dialog.querySelector(".site-dialog-head h2").textContent = opts.title || "提示";
    dialog.querySelector(".site-dialog-message").textContent = opts.message || "";
    dialog.querySelector(".site-dialog-message").hidden = !opts.message;
    dialog.querySelector(".site-dialog-error").hidden = true;
    var inputWrap = dialog.querySelector(".site-dialog-input");
    var input = inputWrap.querySelector("textarea");
    inputWrap.hidden = mode !== "prompt";
    input.value = opts.value || "";
    input.placeholder = opts.placeholder || "";
    var cancel = dialog.querySelector(".site-dialog-actions .site-dialog-btn:not(.is-primary)");
    var confirm = dialog.querySelector(".site-dialog-actions .is-primary");
    cancel.hidden = mode === "alert";
    confirm.textContent = opts.confirmText || (mode === "alert" ? "知道了" : "确定");
    cancel.textContent = opts.cancelText || "取消";
    confirm.classList.toggle("is-danger", Boolean(opts.danger));
    modal.hidden = false;
    window.setTimeout(function () {
      if (mode === "prompt") input.focus();
      else confirm.focus();
    }, 0);
    return new Promise(function (resolve) {
      resolveCurrent = resolve;
    });
  }

  window.ErrorDialog = {
    alert: function (message, options) {
      return open(
        Object.assign({}, options || {}, {
          mode: "alert",
          message: message,
        })
      );
    },
    confirm: function (message, options) {
      return open(
        Object.assign({}, options || {}, {
          mode: "confirm",
          message: message,
        })
      );
    },
    prompt: function (message, options) {
      return open(
        Object.assign({}, options || {}, {
          mode: "prompt",
          message: message,
        })
      );
    },
  };
})();
