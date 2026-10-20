(function () {
  "use strict";

  var messages = document.getElementById("agentMessages");
  var form = document.getElementById("agentForm");
  var input = document.getElementById("agentInput");
  var send = document.getElementById("agentSend");
  var statusText = document.getElementById("agentStatusText");
  var statusLight = document.getElementById("agentStatusLight");

  function addMessage(role, text) {
    var article = document.createElement("article");
    article.className = "agent-message " + (role === "user" ? "is-user" : "is-assistant");
    var name = document.createElement("span");
    name.textContent = role === "user" ? "管理员" : "ErrorJ Agent";
    var body = document.createElement("p");
    body.textContent = text;
    article.append(name, body);
    messages.appendChild(article);
    messages.scrollTop = messages.scrollHeight;
    return article;
  }

  function setBusy(busy) {
    send.disabled = busy;
    send.textContent = busy ? "处理中" : "发送";
    input.disabled = busy;
  }

  function loadStatus() {
    fetch("/api/agent/web/status", { credentials: "same-origin", cache: "no-store" })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        var data = result.data || {};
        var agent = data.agent || {};
        var online = Boolean(result.ok && data.ok);
        statusLight.classList.toggle("is-online", online);
        statusText.textContent = online ? "在线，QQ 通知已连接" : "离线";
        document.getElementById("agentModel").textContent = agent.model || "--";
        document.getElementById("agentAdmins").textContent = online
          ? String(agent.bound_admins || 0)
          : "--";
        document.getElementById("agentGroups").textContent = online
          ? (agent.group_ids || []).join("、") || "未配置"
          : "--";
      })
      .catch(function () {
        statusLight.classList.remove("is-online");
        statusText.textContent = "离线";
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text || send.disabled) return;
    addMessage("user", text);
    input.value = "";
    setBusy(true);
    var pending = addMessage("assistant", "正在处理…");
    fetch("/api/agent/web/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ message: text }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "请求失败");
          return data;
        });
      })
      .then(function (data) {
        pending.querySelector("p").textContent = data.reply || "这次没有生成回复。";
        messages.scrollTop = messages.scrollHeight;
      })
      .catch(function (error) {
        pending.querySelector("p").textContent = error.message || "请求失败";
      })
      .finally(function () {
        setBusy(false);
        input.focus();
      });
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  loadStatus();
})();
