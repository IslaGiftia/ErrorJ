(function () {
  "use strict";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  var shareOverlay = null;
  var shareTitle = null;
  var shareExpiry = null;
  var shareCustom = null;
  var shareSubmit = null;
  var shareResult = null;
  var shareResultInput = null;
  var currentResource = null;

  function buildShareModal() {
    if (shareOverlay) return;
    shareOverlay = el("div", "share-overlay");
    shareOverlay.hidden = true;
    var dialog = el("div", "share-dialog");
    var head = el("div", "share-head");
    shareTitle = el("h2", "", "分享文件");
    var close = el("button", "share-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "关闭");
    head.append(shareTitle, close);

    var expiryField = el("label", "share-field");
    expiryField.appendChild(el("span", "", "有效期"));
    shareExpiry = document.createElement("select");
    [
      ["1", "1 小时"],
      ["6", "6 小时"],
      ["24", "24 小时"],
      ["72", "3 天"],
      ["168", "7 天"],
      ["custom", "自定义时间"],
    ].forEach(function (option) {
      var node = document.createElement("option");
      node.value = option[0];
      node.textContent = option[1];
      shareExpiry.appendChild(node);
    });
    shareExpiry.value = "24";
    expiryField.appendChild(shareExpiry);

    var customField = el("label", "share-field");
    customField.appendChild(el("span", "", "自定义过期时间"));
    shareCustom = document.createElement("input");
    shareCustom.type = "datetime-local";
    customField.appendChild(shareCustom);
    customField.hidden = true;

    var actions = el("div", "share-actions");
    var cancel = el("button", "share-btn", "取消");
    cancel.type = "button";
    shareSubmit = el("button", "share-btn primary", "生成并复制");
    shareSubmit.type = "button";
    actions.append(cancel, shareSubmit);

    shareResult = el("div", "share-result");
    shareResult.hidden = true;
    shareResult.appendChild(el("p", "", "链接有效期结束后自动失效："));
    shareResultInput = document.createElement("input");
    shareResultInput.type = "text";
    shareResultInput.readOnly = true;
    shareResult.appendChild(shareResultInput);

    dialog.append(head, expiryField, customField, actions, shareResult);
    shareOverlay.appendChild(dialog);
    document.body.appendChild(shareOverlay);

    close.addEventListener("click", () => {
      shareOverlay.hidden = true;
    });
    cancel.addEventListener("click", () => {
      shareOverlay.hidden = true;
    });
    shareOverlay.addEventListener("click", function (event) {
      if (event.target === shareOverlay) shareOverlay.hidden = true;
    });
    shareExpiry.addEventListener("change", function () {
      customField.hidden = shareExpiry.value !== "custom";
      if (shareExpiry.value === "custom" && !shareCustom.value) {
        var next = new Date(Date.now() + 24 * 60 * 60 * 1000);
        next.setMinutes(next.getMinutes() - next.getTimezoneOffset());
        shareCustom.value = next.toISOString().slice(0, 16);
      }
    });
    shareSubmit.addEventListener("click", submitShare);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      shareResultInput.focus();
      shareResultInput.select();
      return false;
    }
  }

  async function submitShare() {
    if (!currentResource || !shareSubmit) return;
    var payload = {
      resource_type: currentResource.resourceType,
      resource_id: currentResource.resourceId,
    };
    if (shareExpiry.value === "custom") {
      if (!shareCustom.value) return;
      payload.expires_at = shareCustom.value;
    } else {
      payload.expires_hours = Number(shareExpiry.value) || 24;
    }
    shareSubmit.disabled = true;
    shareSubmit.textContent = "生成中…";
    try {
      var response = await fetch("/api/admin/share-links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var data = await response.json().catch(function () {
        return {};
      });
      if (!response.ok) throw new Error(data.error || "生成失败");
      shareResult.hidden = false;
      shareResultInput.value = data.url || "";
      await copyText(data.url || "");
      shareSubmit.textContent = "已生成";
    } catch (err) {
      window.alert(err.message || "生成失败");
      shareSubmit.textContent = "生成并复制";
    } finally {
      shareSubmit.disabled = false;
      if (shareSubmit.textContent !== "已生成") {
        shareSubmit.textContent = "生成并复制";
      }
    }
  }

  var requestOverlay = null;
  var requestTitle = null;
  var requestSubmit = null;
  var requestText = null;
  var requestCallback = null;

  function buildRequestModal() {
    if (requestOverlay) return;
    requestOverlay = el("div", "download-request-overlay");
    requestOverlay.hidden = true;
    var dialog = el("div", "download-request-dialog");
    var head = el("div", "download-request-head");
    requestTitle = el("h2", "", "申请下载");
    var close = el("button", "share-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "关闭");
    head.append(requestTitle, close);
    requestText = el("p", "", "");
    var actions = el("div", "download-request-actions");
    var cancel = el("button", "download-request-btn", "取消");
    cancel.type = "button";
    requestSubmit = el("button", "download-request-btn primary", "提交申请");
    requestSubmit.type = "button";
    actions.append(cancel, requestSubmit);
    dialog.append(head, requestText, actions);
    requestOverlay.appendChild(dialog);
    document.body.appendChild(requestOverlay);

    close.addEventListener("click", function () {
      requestOverlay.hidden = true;
    });
    cancel.addEventListener("click", function () {
      requestOverlay.hidden = true;
    });
    requestOverlay.addEventListener("click", function (event) {
      if (event.target === requestOverlay) requestOverlay.hidden = true;
    });
    requestSubmit.addEventListener("click", async function () {
      var payload = requestSubmit.__payload;
      if (!payload) return;
      requestSubmit.disabled = true;
      requestSubmit.textContent = "提交中…";
      try {
        var response = await fetch("/api/download-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        var data = await response.json().catch(function () {
          return {};
        });
        if (!response.ok) throw new Error(data.error || "申请失败");
        requestOverlay.hidden = true;
        if (requestCallback) requestCallback(data.status || "pending");
      } catch (err) {
        window.alert(err.message || "申请失败");
      } finally {
        requestSubmit.disabled = false;
        requestSubmit.textContent = "提交申请";
      }
    });
  }

  window.ErrorShare = {
    open: function (resourceType, resourceId, title) {
      buildShareModal();
      currentResource = {
        resourceType: resourceType,
        resourceId: resourceId,
      };
      shareTitle.textContent = "分享：" + (title || "文件");
      shareResult.hidden = true;
      shareResultInput.value = "";
      shareSubmit.textContent = "生成并复制";
      shareOverlay.hidden = false;
    },
  };

  window.ErrorDownload = {
    request: function (resourceType, resourceId, title, callback) {
      buildRequestModal();
      requestTitle.textContent = "申请下载";
      requestText.textContent = "向管理员申请下载「" + (title || "文件") + "」？";
      requestSubmit.__payload = {
        resource_type: resourceType,
        resource_id: resourceId,
      };
      requestCallback = callback;
      requestOverlay.hidden = false;
    },
  };
})();
