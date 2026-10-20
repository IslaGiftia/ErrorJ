(function () {
  "use strict";

  var messages = document.getElementById("agentMessages");
  var form = document.getElementById("agentForm");
  var input = document.getElementById("agentInput");
  var send = document.getElementById("agentSend");
  var suggestions = document.getElementById("agentSuggestions");
  var statusText = document.getElementById("agentStatusText");
  var topStatus = document.getElementById("agentTopStatus");
  var onlineChip = document.getElementById("agentOnlineChip");
  var avatarSrc = "/static/site/error-chan-avatar.png?v=1";

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function messageTime() {
    return new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function assistantAvatar() {
    var wrap = document.createElement("div");
    wrap.className = "agent-message-avatar";
    var image = document.createElement("img");
    image.src = avatarSrc;
    image.alt = "";
    wrap.appendChild(image);
    return wrap;
  }

  function copyButton(text) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "agent-copy";
    button.title = "复制回复";
    button.setAttribute("aria-label", "复制回复");
    button.innerHTML = '<i data-lucide="copy"></i>';
    button.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(text).then(function () {
        button.innerHTML = '<i data-lucide="check"></i>';
        button.title = "已复制";
        refreshIcons();
        window.setTimeout(function () {
          button.innerHTML = '<i data-lucide="copy"></i>';
          button.title = "复制回复";
          refreshIcons();
        }, 1400);
      });
    });
    return button;
  }

  function addMessage(role, text) {
    var article = document.createElement("article");
    article.className = "agent-message " + (role === "user" ? "is-user" : "is-assistant");
    if (role !== "user") article.appendChild(assistantAvatar());
    var body = document.createElement("div");
    body.className = "agent-message-body";
    var meta = document.createElement("div");
    meta.className = "agent-message-meta";
    var author = document.createElement("strong");
    author.textContent = role === "user" ? "管理员" : "ErrorJ Agent";
    var time = document.createElement("span");
    time.textContent = messageTime();
    meta.append(author, time);
    var bubble = document.createElement("div");
    bubble.className = "agent-bubble";
    var paragraph = document.createElement("p");
    paragraph.textContent = text;
    bubble.appendChild(paragraph);
    body.append(meta, bubble);
    if (role !== "user") body.appendChild(copyButton(text));
    article.appendChild(body);
    messages.appendChild(article);
    messages.scrollTop = messages.scrollHeight;
    refreshIcons();
    return { article: article, paragraph: paragraph };
  }

  function addThinking() {
    var article = document.createElement("article");
    article.className = "agent-message is-assistant is-pending";
    article.appendChild(assistantAvatar());
    var body = document.createElement("div");
    body.className = "agent-message-body";
    var meta = document.createElement("div");
    meta.className = "agent-message-meta";
    var author = document.createElement("strong");
    author.textContent = "ErrorJ Agent";
    var time = document.createElement("span");
    time.textContent = "正在处理";
    meta.append(author, time);
    var bubble = document.createElement("div");
    bubble.className = "agent-bubble";
    bubble.innerHTML = '<span class="agent-thinking" aria-label="正在思考"><i></i><i></i><i></i></span>';
    body.append(meta, bubble);
    article.appendChild(body);
    messages.appendChild(article);
    messages.scrollTop = messages.scrollHeight;
    return article;
  }

  function setBusy(busy) {
    send.disabled = busy;
    input.disabled = busy;
  }

  function setStatus(online, data) {
    document.body.setAttribute("data-agent-online", online ? "1" : "0");
    topStatus.textContent = online ? "在线" : "离线";
    statusText.textContent = online ? "已连接 Error酱工具" : "Agent 暂时离线";
    onlineChip.classList.toggle("is-online", online);
    onlineChip.querySelector("span").textContent = online ? "在线" : "离线";
    var agent = (data && data.agent) || {};
    document.getElementById("agentModel").textContent = agent.model || "--";
    document.getElementById("agentModelPill").textContent = agent.model || "DeepSeek";
    document.getElementById("agentAdmins").textContent = online
      ? String(agent.bound_admins || 0) + " 人"
      : "--";
    document.getElementById("agentGroups").textContent = online
      ? (agent.group_ids || []).join("、") || "未配置"
      : "--";
  }

  function loadStatus() {
    fetch("/api/agent/web/status", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        setStatus(Boolean(result.ok && result.data.ok), result.data);
      })
      .catch(function () {
        setStatus(false, null);
      });
  }

  function submitMessage(text) {
    var value = String(text || "").trim();
    if (!value || send.disabled) return;
    addMessage("user", value);
    if (suggestions) suggestions.hidden = true;
    input.value = "";
    input.style.height = "";
    setBusy(true);
    var pending = addThinking();
    fetch("/api/agent/web/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ message: value }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "请求失败");
          return data;
        });
      })
      .then(function (data) {
        pending.remove();
        addMessage("assistant", data.reply || "这次没有生成回复。");
      })
      .catch(function (error) {
        pending.remove();
        addMessage("assistant", error.message || "请求失败，请稍后再试。");
      })
      .finally(function () {
        setBusy(false);
        input.focus();
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submitMessage(input.value);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 150) + "px";
  });

  suggestions.addEventListener("click", function (event) {
    var button = event.target.closest("[data-agent-prompt]");
    if (!button) return;
    submitMessage(button.getAttribute("data-agent-prompt"));
  });

  refreshIcons();
  loadStatus();
})();
