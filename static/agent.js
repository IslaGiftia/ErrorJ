(function () {
  "use strict";

  var statusText = document.getElementById("agentStatusText");
  var topStatus = document.getElementById("agentTopStatus");
  var onlineChip = document.getElementById("agentOnlineChip");
  var settingsStatus = document.getElementById("agentSettingsStatus");
  var topFeedback = document.getElementById("agentTopFeedback");
  var settingsSave = document.getElementById("agentSettingsSave");
  var memoryList = document.getElementById("agentMemoryList");
  var memorySearch = document.getElementById("agentMemorySearch");
  var memoryArchived = document.getElementById("agentMemoryArchived");
  var memoryCount = document.getElementById("agentMemoryCount");
  var groupMemberList = document.getElementById("agentGroupMemberList");
  var timelineList = document.getElementById("agentTimelineList");
  var timelineForm = document.getElementById("agentTimelineForm");
  var stickerGrid = document.getElementById("agentStickerGrid");
  var stickerInput = document.getElementById("agentStickerInput");
  var stickerUploadBtn = document.getElementById("agentStickerUploadBtn");
  var stickerCategorySelect = document.getElementById("agentStickerCategory");
  var stickerCategoryForm = document.getElementById("agentStickerCategoryForm");
  var stickerCategoryName = document.getElementById("agentStickerCategoryName");
  var stickerCategoryAdd = document.getElementById("agentStickerCategoryAdd");
  var stickerCategoryCancel = document.getElementById("agentStickerCategoryCancel");
  var stickerUploadTarget = document.getElementById("agentStickerUploadTarget");
  var stickerUploadCaption = document.getElementById("agentStickerUploadCaption");
  var stickerUploadKeywords = document.getElementById("agentStickerUploadKeywords");
  var stickerUploadMood = document.getElementById("agentStickerUploadMood");
  var stickerSearch = document.getElementById("agentStickerSearch");
  var stickerMoodFilter = document.getElementById("agentStickerMoodFilter");
  var stickerSort = document.getElementById("agentStickerSort");
  var stickerPendingOnly = document.getElementById("agentStickerPendingOnly");
  var stickerFilterSummary = document.getElementById("agentStickerFilterSummary");
  var stickerExport = document.getElementById("agentStickerExport");
  var stickerImportBtn = document.getElementById("agentStickerImportBtn");
  var stickerImportInput = document.getElementById("agentStickerImportInput");
  var stickerBulk = document.getElementById("agentStickerBulk");
  var stickerSelectedCount = document.getElementById("agentStickerSelectedCount");
  var stickerBulkCategory = document.getElementById("agentStickerBulkCategory");
  var stickerBulkMove = document.getElementById("agentStickerBulkMove");
  var stickerBulkCaption = document.getElementById("agentStickerBulkCaption");
  var stickerBulkKeywords = document.getElementById("agentStickerBulkKeywords");
  var stickerBulkMood = document.getElementById("agentStickerBulkMood");
  var stickerBulkUpdate = document.getElementById("agentStickerBulkUpdate");
  var stickerCategories = ["未分类"];
  var selectedStickerIds = {};
  var currentStickers = [];
  var settingsDirty = false;
  var memorySearchTimer = null;
  var memoryRequestId = 0;

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(
      /[&<>"']/g,
      function (character) {
        return {
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[character];
      }
    );
  }

  function setSettingsStatus(message, dirty) {
    settingsDirty = Boolean(dirty);
    settingsStatus.textContent = message;
    settingsStatus.classList.toggle("is-dirty", settingsDirty);
    topFeedback.textContent = message;
    topFeedback.classList.toggle("is-dirty", settingsDirty);
  }

  function markSettingsDirty() {
    if (settingsSave.disabled) return;
    setSettingsStatus("有未保存的基础设置", true);
  }

  function readApiResponse(response) {
    return response.text().then(function (raw) {
      var body = {};
      try {
        body = raw ? JSON.parse(raw) : {};
      } catch (error) {
        body = {};
      }
      if (!response.ok) {
        throw new Error(
          body.error || "请求失败（HTTP " + response.status + "）"
        );
      }
      return body;
    });
  }

  function setStatus(online, data) {
    document.body.setAttribute("data-agent-online", online ? "1" : "0");
    topStatus.textContent = online ? "在线" : "离线";
    onlineChip.classList.toggle("is-online", online);
    onlineChip.querySelector("span").textContent = online ? "在线" : "离线";
    statusText.textContent = online
      ? "鲸鲸工具已连接，配置修改可正常保存"
      : "鲸鲸暂时离线，请检查服务连接";

    var agent = (data && data.agent) || {};
    var qqbot = agent.qqbot || {};
    document.getElementById("agentModel").textContent = agent.model || "--";
    var qqbotLabel = "未启用";
    if (qqbot.enabled) {
      qqbotLabel = qqbot.connected ? "已连接" : "连接中";
    }
    document.getElementById("agentQQBotStatus").textContent = qqbotLabel;
    var legacyAdmins = agent.qq_admins;
    if (legacyAdmins === undefined || legacyAdmins === null) {
      legacyAdmins = agent.bound_admins || 0;
    }
    var admins = Number(legacyAdmins) + Number(agent.qqbot_admins || 0);
    document.getElementById("agentAdmins").textContent = online
      ? admins + " 人"
      : "--";
    var groups = Array.isArray(agent.group_ids) ? agent.group_ids : [];
    document.getElementById("agentGroups").textContent = online
      ? groups.length
        ? groups.length + " 个"
        : "未配置"
      : "--";
    renderGroupIdleStatus(
      agent.group_idle_proactive,
      online
    );
  }

  function compactDuration(seconds) {
    var value = Math.max(0, Number(seconds) || 0);
    if (value < 60) return "不到1分钟";
    if (value < 3600) return Math.ceil(value / 60) + "分钟";
    if (value < 86400) return Math.ceil(value / 3600) + "小时";
    return Math.ceil(value / 86400) + "天";
  }

  function renderGroupIdleStatus(idle, online) {
    var target = document.getElementById("agentGroupIdleStatus");
    var cards = document.getElementById("agentGroupIdleGroups");
    var runsTarget = document.getElementById("agentGroupIdleRuns");
    if (!target) return;
    if (!online) {
      target.textContent = "冷场聊天状态：鲸鲸离线";
      if (cards) cards.innerHTML = "";
      if (runsTarget) runsTarget.innerHTML = "";
      return;
    }
    if (!idle) {
      target.textContent = "冷场聊天状态：暂无数据";
      if (cards) cards.innerHTML = "";
      if (runsTarget) runsTarget.innerHTML = "";
      return;
    }
    if (!idle.enabled) {
      target.textContent = "冷场聊天状态：已关闭";
      renderGroupIdleCards(idle);
      renderGroupIdleRuns(idle.runs || []);
      return;
    }
    var groups = Array.isArray(idle.groups) ? idle.groups : [];
    if (!groups.length) {
      target.textContent = "冷场聊天状态：已启用，等待群消息建立计时";
      renderGroupIdleCards(idle);
      renderGroupIdleRuns(idle.runs || []);
      return;
    }
    var now = Math.floor(Date.now() / 1000);
    var parts = groups.slice(0, 4).map(function (group) {
      var label = "…" + String(group.group_tail || "");
      if (!group.enabled) return label + " 已单独暂停";
      var unanswered = Number(group.unanswered_count || 0);
      var maxUnanswered = Number(idle.max_unanswered || 2);
      var dailyLimit = Number(group.daily_limit || idle.daily_limit || 1);
      if (Number(group.sent_today || 0) >= dailyLimit) {
        return label + " 今日已达上限";
      }
      if (unanswered >= maxUnanswered) {
        return label + " 连续未回应，暂停";
      }
      var nextAt = Number(group.next_proactive_at || 0);
      if (nextAt) {
        var waiting = nextAt <= now
          ? label + " 即将判断"
          : label + " 约 " + compactDuration(nextAt - now) + "后判断";
        return group.last_error
          ? waiting + " · 上次失败待重试"
          : waiting;
      }
      var lastUserAt = Number(group.last_user_at || 0);
      if (!lastUserAt) return label + " 等待首条群消息";
      var idleLabel = label + " 已安静 " + compactDuration(now - lastUserAt);
      return group.last_error
        ? idleLabel + " · 上次失败待重试"
        : idleLabel;
    });
    target.textContent =
      "冷场聊天状态：已启用｜" +
      parts.join("；") +
      (groups.length > parts.length
        ? "；另有 " + (groups.length - parts.length) + " 个群"
        : "");
    renderGroupIdleCards(idle);
    renderGroupIdleRuns(idle.runs || []);
  }

  function groupIdleCardText(group, idle, now) {
    if (!group.enabled) return "这个群已单独暂停";
    var unanswered = Number(group.unanswered_count || 0);
    var maxUnanswered = Number(idle.max_unanswered || 2);
    var dailyLimit = Number(group.daily_limit || idle.daily_limit || 1);
    if (Number(group.sent_today || 0) >= dailyLimit) {
      return "今日主动次数已用完";
    }
    if (unanswered >= maxUnanswered) {
      return "连续 " + unanswered + " 次没有有效接话，等待群重新活跃";
    }
    var awaitingUntil = Number(group.awaiting_reply_until || 0);
    if (awaitingUntil > now) {
      return "已发言，正在观察 " + compactDuration(awaitingUntil - now) + "内的有效接话";
    }
    var nextAt = Number(group.next_proactive_at || 0);
    if (nextAt) {
      return nextAt <= now
        ? "已到判断时间，正在等待调度"
        : "约 " + compactDuration(nextAt - now) + "后重新判断";
    }
    var lastUserAt = Number(group.last_user_at || 0);
    if (!lastUserAt) return "等待首条群消息建立计时";
    return "已安静 " + compactDuration(now - lastUserAt);
  }

  function groupIdleThresholdText(group) {
    var effective = Number(group.effective_idle_minutes || group.idle_minutes || 90);
    var sample = Number(group.sample_count || 0);
    var text = "自适应门槛 " + effective + " 分钟 · 近 7 天 " + sample + " 条真人消息";
    if (group.sparse && group.weekly_limit) {
      text += " · 低频群每周最多 " + group.weekly_limit + " 次";
    }
    return text;
  }

  function renderGroupIdleCards(idle) {
    var target = document.getElementById("agentGroupIdleGroups");
    if (!target) return;
    target.innerHTML = "";
    var groups = Array.isArray(idle.groups) ? idle.groups : [];
    var now = Math.floor(Date.now() / 1000);
    groups.forEach(function (group) {
      var row = document.createElement("div");
      row.className = "agent-idle-group";
      var copy = document.createElement("div");
      copy.className = "agent-idle-group-main";
      var title = document.createElement("strong");
      title.textContent = "群 …" + String(group.group_tail || "");
      var status = document.createElement("small");
      status.textContent =
        groupIdleCardText(group, idle, now) +
        " · " + groupIdleThresholdText(group);
      copy.append(title, status);

      var actions = document.createElement("div");
      actions.className = "agent-idle-actions";
      [
        ["preview", "生成预览"],
        ["send", "试发一次"],
        [group.enabled ? "pause" : "resume", group.enabled ? "暂停此群" : "恢复此群"],
      ].forEach(function (item) {
        var button = document.createElement("button");
        button.type = "button";
        button.dataset.groupId = String(group.group_id || "");
        button.dataset.action = item[0];
        button.textContent = item[1];
        button.addEventListener("click", function () {
          runGroupIdleAction(
            button.dataset.groupId,
            button.dataset.action,
            button
          );
        });
        actions.appendChild(button);
      });
      var limits = document.createElement("div");
      limits.className = "agent-idle-limits";
      var thresholdLabel = document.createElement("label");
      var thresholdCopy = document.createElement("span");
      thresholdCopy.textContent = "此群门槛";
      var thresholdInput = document.createElement("input");
      thresholdInput.type = "number";
      thresholdInput.min = "15";
      thresholdInput.max = "1440";
      thresholdInput.step = "5";
      thresholdInput.value = String(group.idle_minutes || 90);
      thresholdLabel.append(thresholdCopy, thresholdInput);
      var dailyLabel = document.createElement("label");
      var dailyCopy = document.createElement("span");
      dailyCopy.textContent = "每日最多";
      var dailyInput = document.createElement("input");
      dailyInput.type = "number";
      dailyInput.min = "1";
      dailyInput.max = "6";
      dailyInput.value = String(group.daily_limit || 1);
      dailyLabel.append(dailyCopy, dailyInput);
      var saveLimits = document.createElement("button");
      saveLimits.type = "button";
      saveLimits.textContent = "保存群参数";
      saveLimits.addEventListener("click", function () {
        runGroupIdleAction(
          String(group.group_id || ""),
          "configure",
          saveLimits,
          {
            idle_trigger_minutes: Number(thresholdInput.value) || 90,
            max_per_day: Number(dailyInput.value) || 1,
          }
        );
      });
      limits.append(thresholdLabel, dailyLabel, saveLimits);
      row.append(copy, actions, limits);
      target.appendChild(row);
    });
  }

  function renderGroupIdleRuns(runs) {
    var target = document.getElementById("agentGroupIdleRuns");
    if (!target) return;
    target.innerHTML = "";
    var labels = {
      running: "生成中",
      sent: "已发送",
      replied: "已接话",
      skipped: "已跳过",
      cancelled: "已取消",
      failed: "失败",
      expired: "未接话",
      preview: "预览",
      private_fallback: "私聊兜底",
    };
    (Array.isArray(runs) ? runs : []).slice(0, 8).forEach(function (run) {
      var row = document.createElement("div");
      row.className = "agent-idle-run";
      var status = document.createElement("span");
      status.className = "agent-idle-run-status";
      status.textContent = labels[run.status] || run.status || "记录";
      var copy = document.createElement("div");
      copy.className = "agent-idle-run-copy";
      var reason = document.createElement("span");
      reason.textContent =
        "…" + String(run.group_tail || "") +
        " · " + String(run.trigger_reason || "群聊冷场判断");
      var detail = document.createElement("span");
      detail.textContent =
        String(run.detail || run.generated_text || run.reply_text || "")
          .replace(/\s+/g, " ")
          .slice(0, 100);
      copy.append(reason, detail);
      var time = document.createElement("span");
      time.className = "agent-idle-run-time";
      time.textContent = timelineDate(run.started_at);
      row.append(status, copy, time);
      target.appendChild(row);
    });
  }

  function runGroupIdleAction(groupId, action, button, extra) {
    if (!groupId || !action) return;
    button.disabled = true;
    fetch("/api/agent/web/group-idle-action", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        Object.assign(
          { group_id: groupId, action: action },
          extra || {}
        )
      ),
    })
      .then(readApiResponse)
      .then(function (data) {
        var preview = document.getElementById("agentGroupIdlePreview");
        if (preview) {
          preview.hidden = !data.message;
          preview.textContent = data.message || "";
        }
        setSettingsStatus(data.message || "群主动操作已完成", false);
        return loadStatus();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, true);
      })
      .then(function () {
        button.disabled = false;
      });
  }

  function loadStatus() {
    return fetch("/api/agent/web/status", {
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

  function settingValue(id, value) {
    var element = document.getElementById(id);
    if (!element) return;
    if (element.type === "checkbox") element.checked = Boolean(value);
    else element.value = value == null ? "" : String(value);
  }

  function loadSettings() {
    return fetch("/api/agent/web/settings", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(readApiResponse)
      .then(function (data) {
        var settings = data.settings || {};
        settingValue("settingMemoryEnabled", settings.memory_enabled);
        settingValue(
          "settingMemoryConsolidationEnabled",
          settings.memory_consolidation_enabled
        );
        settingValue(
          "settingMemoryConsolidationTime",
          settings.memory_consolidation_time
        );
        settingValue(
          "settingMemoryDecayEnabled",
          settings.memory_decay_enabled
        );
        settingValue("settingProactiveEnabled", settings.proactive_enabled);
        settingValue("settingStickerEnabled", settings.sticker_enabled);
        settingValue("settingChatHumanDelay", settings.chat_human_delay);
        settingValue("settingPersonaPreset", settings.persona_preset);
        settingValue(
          "settingPersonaCustomPrompt",
          settings.persona_custom_prompt
        );
        settingValue("settingWebSearchEnabled", settings.web_search_enabled);
        settingValue("settingWebSearchCount", settings.web_search_count);
        settingValue(
          "settingGroupProactiveEnabled",
          settings.group_proactive_enabled
        );
        settingValue(
          "settingGroupIdleProactiveEnabled",
          settings.group_idle_proactive_enabled
        );
        settingValue(
          "settingGroupWeatherEnabled",
          settings.group_weather_enabled
        );
        settingValue(
          "settingGroupHolidayEnabled",
          settings.group_holiday_enabled
        );
        settingValue("settingGroupWeatherCity", settings.group_weather_city);
        settingValue(
          "settingGroupProactiveTime",
          settings.group_proactive_time
        );
        settingValue(
          "settingGroupIdleTriggerMinutes",
          settings.group_idle_trigger_minutes
        );
        settingValue(
          "settingGroupIdleRandomMin",
          settings.group_idle_random_min_minutes
        );
        settingValue(
          "settingGroupIdleRandomMax",
          settings.group_idle_random_max_minutes
        );
        settingValue(
          "settingGroupIdleMaxPerDay",
          settings.group_idle_max_per_day
        );
        settingValue(
          "settingGroupIdleMaxUnanswered",
          settings.group_idle_max_unanswered
        );
        settingValue("settingProactiveMax", settings.proactive_max_per_day);
        settingValue("settingMorningTime", settings.morning_time);
        settingValue("settingNightTime", settings.night_time);
        settingValue("settingQuietStart", settings.quiet_start);
        settingValue("settingQuietEnd", settings.quiet_end);
        settingsSave.disabled = false;
        setSettingsStatus("基础设置已载入", false);
      })
      .catch(function (error) {
        settingsSave.disabled = true;
        setSettingsStatus(error.message, false);
      });
  }

  function saveSettings() {
    if (settingsSave.disabled) return;
    settingsSave.disabled = true;
    setSettingsStatus("正在保存基础设置…", true);
    var values = {
      memory_enabled: document.getElementById("settingMemoryEnabled").checked,
      memory_consolidation_enabled: document.getElementById(
        "settingMemoryConsolidationEnabled"
      ).checked,
      memory_consolidation_time: document.getElementById(
        "settingMemoryConsolidationTime"
      ).value,
      memory_decay_enabled: document.getElementById(
        "settingMemoryDecayEnabled"
      ).checked,
      proactive_enabled: document.getElementById(
        "settingProactiveEnabled"
      ).checked,
      sticker_enabled: document.getElementById("settingStickerEnabled").checked,
      chat_human_delay: document.getElementById("settingChatHumanDelay").checked,
      persona_preset: document.getElementById("settingPersonaPreset").value,
      persona_custom_prompt: document.getElementById(
        "settingPersonaCustomPrompt"
      ).value,
      web_search_enabled: document.getElementById(
        "settingWebSearchEnabled"
      ).checked,
      web_search_count:
        Number(document.getElementById("settingWebSearchCount").value) || 5,
      group_proactive_enabled: document.getElementById(
        "settingGroupProactiveEnabled"
      ).checked,
      group_idle_proactive_enabled: document.getElementById(
        "settingGroupIdleProactiveEnabled"
      ).checked,
      group_weather_enabled: document.getElementById(
        "settingGroupWeatherEnabled"
      ).checked,
      group_holiday_enabled: document.getElementById(
        "settingGroupHolidayEnabled"
      ).checked,
      group_weather_city: document.getElementById(
        "settingGroupWeatherCity"
      ).value,
      group_proactive_time: document.getElementById(
        "settingGroupProactiveTime"
      ).value,
      group_idle_trigger_minutes:
        Number(
          document.getElementById("settingGroupIdleTriggerMinutes").value
        ) || 90,
      group_idle_random_min_minutes:
        Number(
          document.getElementById("settingGroupIdleRandomMin").value
        ) || 15,
      group_idle_random_max_minutes:
        Number(
          document.getElementById("settingGroupIdleRandomMax").value
        ) || 45,
      group_idle_max_per_day:
        Number(
          document.getElementById("settingGroupIdleMaxPerDay").value
        ) || 1,
      group_idle_max_unanswered:
        Number(
          document.getElementById("settingGroupIdleMaxUnanswered").value
        ) || 2,
      proactive_max_per_day:
        Number(document.getElementById("settingProactiveMax").value) || 2,
      morning_time: document.getElementById("settingMorningTime").value,
      night_time: document.getElementById("settingNightTime").value,
      quiet_start: document.getElementById("settingQuietStart").value,
      quiet_end: document.getElementById("settingQuietEnd").value,
    };
    fetch("/api/agent/web/settings", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: values }),
    })
      .then(readApiResponse)
      .then(function () {
        setSettingsStatus("基础设置已保存", false);
      })
      .catch(function (error) {
        setSettingsStatus(error.message, true);
      })
      .then(function () {
        settingsSave.disabled = false;
      });
  }

  function platformLabel(platform) {
    if (platform === "qq") return "QQ 私聊";
    if (platform === "qqbot") return "QQBot";
    return "网页对话";
  }

  function loadMemories(query) {
    var requestId = ++memoryRequestId;
    var url = "/api/agent/web/memories";
    var searchText = String(query || "").trim();
    if (searchText) url += "?q=" + encodeURIComponent(searchText);
    if (memoryArchived.checked) {
      url += (searchText ? "&" : "?") + "include_archived=1";
    }
    return fetch(url, { credentials: "same-origin", cache: "no-store" })
      .then(readApiResponse)
      .then(function (data) {
        if (requestId !== memoryRequestId) return;
        memoryList.innerHTML = "";
        memoryCount.textContent = (data.memories || []).length + " 条";
        (data.memories || []).forEach(function (memory) {
          var item = document.createElement("div");
          item.className = "agent-memory-item";
          var copy = document.createElement("div");
          var text = document.createElement("p");
          text.textContent = memory.content;
          var meta = document.createElement("small");
          meta.textContent =
            platformLabel(memory.platform) +
            " · " + memory.kind +
            " · 强度 " + Math.round(Number(memory.strength || 0) * 100) + "%" +
            " · 重要度 " + memory.importance +
            " · 置信度 " + (memory.confidence || 5) +
            (Number(memory.pinned) ? " · 固定" : "") +
            (memory.archived_at ? " · 已归档" : "") +
            (memory.source === "consolidation" ? " · 空闲整理" : "");
          copy.append(text, meta);
          if (memory.evidence) {
            var evidence = document.createElement("small");
            evidence.className = "agent-memory-evidence";
            evidence.textContent = "证据：" + memory.evidence;
            copy.appendChild(evidence);
          }
          var actions = document.createElement("div");
          actions.className = "agent-memory-actions";
          var archive = document.createElement("button");
          archive.type = "button";
          archive.title = memory.archived_at ? "恢复记忆" : "归档记忆";
          archive.setAttribute(
            "aria-label",
            memory.archived_at ? "恢复记忆" : "归档记忆"
          );
          archive.innerHTML =
            '<i data-lucide="' +
            (memory.archived_at ? "rotate-ccw" : "archive") +
            '"></i>';
          archive.addEventListener("click", function () {
            fetch("/api/agent/web/memory-status", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: memory.id,
                platform: memory.platform,
                archived: !memory.archived_at,
              }),
            })
              .then(readApiResponse)
              .then(function () {
                return loadMemories(memorySearch.value);
              })
              .catch(function (error) {
                setSettingsStatus(error.message, settingsDirty);
              });
          });
          actions.appendChild(archive);
          var remove = document.createElement("button");
          remove.type = "button";
          remove.title = "删除记忆";
          remove.setAttribute("aria-label", "删除记忆");
          remove.innerHTML = '<i data-lucide="trash-2"></i>';
          remove.addEventListener("click", function () {
            fetch("/api/agent/web/memory-delete", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: memory.id,
                platform: memory.platform,
              }),
            })
              .then(readApiResponse)
              .then(function () {
                return loadMemories(memorySearch.value);
              })
              .catch(function (error) {
                setSettingsStatus(error.message, settingsDirty);
              });
          });
          actions.appendChild(remove);
          item.append(copy, actions);
          memoryList.appendChild(item);
        });
        if (!(data.memories || []).length) {
          memoryList.innerHTML =
            '<div class="agent-memory-item"><p>' +
            (searchText ? "没有匹配的记忆。" : "还没有长期记忆。") +
            "</p></div>";
        }
        refreshIcons();
      })
      .catch(function (error) {
        if (requestId !== memoryRequestId) return;
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function loadGroupMembers() {
    return fetch("/api/agent/web/group-members", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(readApiResponse)
      .then(function (data) {
        var members = data.members || [];
        groupMemberList.innerHTML = "";
        document.getElementById("agentGroupMemberCount").textContent =
          members.length + " 人";
        members.forEach(function (member) {
          var item = document.createElement("div");
          item.className = "agent-memory-item agent-group-member";
          var copy = document.createElement("div");
          var name = document.createElement("p");
          name.textContent =
            member.alias || member.display_name || "未命名群友";
          var meta = document.createElement("small");
          var bound = member.user_id
            ? "Error酱 #" + member.user_id
            : "未绑定";
          var memberTail = String(member.member_id || "").slice(-8);
          meta.textContent =
            bound +
            " · " + Number(member.message_count || 0) + " 次发言" +
            " · " + memberTail +
            " · " + timelineDate(member.last_seen);
          copy.append(name, meta);
          var actions = document.createElement("div");
          actions.className = "agent-member-actions";
          var edit = document.createElement("button");
          edit.type = "button";
          edit.title = "编辑群友档案";
          edit.setAttribute("aria-label", "编辑群友档案");
          edit.innerHTML = '<i data-lucide="pencil"></i>';
          actions.appendChild(edit);

          var editor = document.createElement("form");
          editor.className = "agent-member-editor";
          editor.hidden = true;
          editor.innerHTML =
            '<label><span>别名</span><input name="alias" maxlength="80" value="' +
            escapeHtml(member.alias || "") +
            '"></label>' +
            '<label><span>关系</span><input name="relationship" maxlength="80" value="' +
            escapeHtml(member.relationship || "群友") +
            '"></label>' +
            '<label class="agent-member-notes"><span>档案备注</span><textarea name="notes" rows="2" maxlength="300">' +
            escapeHtml(member.notes || "") +
            "</textarea></label>" +
            '<div class="agent-member-switches">' +
            '<label><input type="checkbox" name="allow_chat"' +
            (Number(member.allow_chat) ? " checked" : "") +
            ">允许聊天</label>" +
            '<label><input type="checkbox" name="allow_tools"' +
            (Number(member.allow_tools) ? " checked" : "") +
            ">允许工具</label>" +
            '<label><input type="checkbox" name="memory_enabled"' +
            (Number(member.memory_enabled) ? " checked" : "") +
            ">启用记忆</label>" +
            "</div>" +
            '<button type="submit">保存档案</button>';
          edit.addEventListener("click", function () {
            editor.hidden = !editor.hidden;
          });
          editor.addEventListener("submit", function (event) {
            event.preventDefault();
            var formData = new FormData(editor);
            var values = {
              alias: String(formData.get("alias") || ""),
              relationship: String(formData.get("relationship") || ""),
              notes: String(formData.get("notes") || ""),
              allow_chat: formData.get("allow_chat") === "on",
              allow_tools: formData.get("allow_tools") === "on",
              memory_enabled: formData.get("memory_enabled") === "on",
            };
            fetch("/api/agent/web/group-member-update", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                platform: member.platform,
                group_id: member.group_id,
                member_id: member.member_id,
                values: values,
              }),
            })
              .then(readApiResponse)
              .then(loadGroupMembers)
              .catch(function (error) {
                setSettingsStatus(error.message, settingsDirty);
              });
          });
          item.append(copy, actions, editor);
          groupMemberList.appendChild(item);
        });
        if (!members.length) {
          groupMemberList.innerHTML =
            '<div class="agent-memory-item"><p>还没有群友主动 @ 过鲸鲸。</p></div>';
        }
        refreshIcons();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function timelineTypeLabel(type) {
    return {
      event: "事件",
      plan: "计划",
      promise: "约定",
      milestone: "节点",
      relationship: "关系",
    }[type] || "事件";
  }

  function timelineDate(timestamp) {
    if (!timestamp) return "未设置";
    return new Date(Number(timestamp) * 1000).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function timelineTimestamp(value) {
    if (!value) return null;
    var date = new Date(value);
    return Number.isNaN(date.getTime())
      ? null
      : Math.floor(date.getTime() / 1000);
  }

  function loadTimeline() {
    return fetch("/api/agent/web/timeline?status=all", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(readApiResponse)
      .then(function (data) {
        timelineList.innerHTML = "";
        var events = data.events || [];
        document.getElementById("agentTimelineCount").textContent =
          events.length + " 条";
        events.forEach(function (event) {
          var item = document.createElement("article");
          item.className = "agent-timeline-item";
          if (event.status === "done") item.classList.add("is-done");
          var now = Math.floor(Date.now() / 1000);
          if (
            event.status === "open" &&
            event.follow_up_at &&
            Number(event.follow_up_at) <= now
          ) {
            item.classList.add("is-due");
          }

          var dot = document.createElement("span");
          dot.className = "agent-timeline-dot";
          dot.setAttribute("aria-hidden", "true");
          var body = document.createElement("div");
          body.className = "agent-timeline-copy";
          var title = document.createElement("h4");
          title.textContent = event.title || "未命名事件";
          var content = document.createElement("p");
          content.textContent = event.content || "没有补充内容";
          var meta = document.createElement("small");
          var metaParts = [
            platformLabel(event.platform),
            timelineTypeLabel(event.event_type),
            "发生 " + timelineDate(event.event_at),
          ];
          if (event.follow_up_at) {
            metaParts.push("跟进 " + timelineDate(event.follow_up_at));
          }
          metaParts.push(event.status === "done" ? "已完成" : "待跟进");
          meta.textContent = metaParts.join(" · ");
          body.append(title, content, meta);

          var actions = document.createElement("div");
          actions.className = "agent-timeline-actions";
          var toggle = document.createElement("button");
          toggle.type = "button";
          toggle.title = event.status === "done" ? "重新打开" : "标记完成";
          toggle.setAttribute("aria-label", toggle.title);
          toggle.innerHTML =
            '<i data-lucide="' +
            (event.status === "done" ? "rotate-ccw" : "check") +
            '"></i>';
          toggle.addEventListener("click", function () {
            fetch("/api/agent/web/timeline-status", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: event.id,
                platform: event.platform,
                status: event.status === "done" ? "open" : "done",
              }),
            })
              .then(readApiResponse)
              .then(loadTimeline)
              .catch(function (error) {
                setSettingsStatus(error.message, settingsDirty);
              });
          });
          var remove = document.createElement("button");
          remove.type = "button";
          remove.title = "删除事件";
          remove.setAttribute("aria-label", "删除事件");
          remove.innerHTML = '<i data-lucide="trash-2"></i>';
          remove.addEventListener("click", function () {
            fetch("/api/agent/web/timeline-delete", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: event.id,
                platform: event.platform,
              }),
            })
              .then(readApiResponse)
              .then(loadTimeline)
              .catch(function (error) {
                setSettingsStatus(error.message, settingsDirty);
              });
          });
          actions.append(toggle, remove);
          item.append(dot, body, actions);
          timelineList.appendChild(item);
        });
        if (!events.length) {
          timelineList.innerHTML =
            '<div class="agent-timeline-empty">还没有事件，聊天里提到的约定和计划会自动出现在这里。</div>';
        }
        refreshIcons();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function cleanStickerCategories(categories) {
    var result = ["未分类"];
    (categories || []).forEach(function (category) {
      category = String(category || "").trim();
      if (category && result.indexOf(category) === -1) result.push(category);
    });
    return result;
  }

  function setStickerCategoryOptions(select, categories, preferred) {
    var current = preferred == null ? select.value : preferred;
    select.innerHTML = "";
    categories.forEach(function (category) {
      var option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      select.appendChild(option);
    });
    select.value =
      categories.indexOf(current) === -1 ? categories[0] : current;
  }

  function refreshStickerCategoryControls(preferred) {
    stickerCategories = cleanStickerCategories(stickerCategories);
    var bulkCurrent = stickerBulkCategory.value;
    setStickerCategoryOptions(
      stickerCategorySelect,
      stickerCategories,
      preferred
    );
    setStickerCategoryOptions(
      stickerBulkCategory,
      stickerCategories,
      bulkCurrent
    );
    stickerUploadTarget.textContent =
      "上传到“" + stickerCategorySelect.value + "”";
  }

  function updateStickerSelectionUI() {
    var count = Object.keys(selectedStickerIds).length;
    stickerBulk.hidden = count === 0;
    stickerSelectedCount.textContent = "已选 " + count + " 张";
    document.querySelectorAll("[data-sticker-check]").forEach(function (input) {
      input.checked = Boolean(selectedStickerIds[input.value]);
    });
    document
      .querySelectorAll(".agent-sticker-category-group")
      .forEach(function (group) {
        var checks = group.querySelectorAll("[data-sticker-check]");
        var allSelected = checks.length > 0;
        checks.forEach(function (input) {
          if (!input.checked) allSelected = false;
        });
        var button = group.querySelector(".agent-sticker-select-group");
        if (button) {
          button.textContent = allSelected ? "取消本组" : "全选本组";
        }
      });
  }

  function filteredStickerList() {
    var query = stickerSearch.value.trim().toLowerCase();
    var tokens = query
      ? query.split(/[\s,，、/|;；:：]+/).filter(Boolean)
      : [];
    var mood = stickerMoodFilter.value;
    var pendingOnly = stickerPendingOnly.checked;
    var rows = currentStickers.filter(function (sticker) {
      if (mood && (sticker.effective_mood || sticker.mood) !== mood) {
        return false;
      }
      if (pendingOnly && !sticker.needs_metadata) return false;
      if (!tokens.length) return true;
      var hay = [
        sticker.source_name,
        sticker.caption,
        sticker.keywords,
        sticker.category,
        sticker.tags,
        sticker.effective_mood,
        stickerMoodLabel(sticker.effective_mood || sticker.mood),
      ].join(" ").toLowerCase();
      return tokens.every(function (token) {
        return hay.indexOf(token) >= 0;
      });
    });
    var sortMode = stickerSort.value;
    rows.sort(function (left, right) {
      if (sortMode === "recent") {
        return Number(right.last_used_at || 0) - Number(left.last_used_at || 0);
      }
      if (sortMode === "used") {
        return Number(right.use_count || 0) - Number(left.use_count || 0);
      }
      if (sortMode === "name") {
        return String(left.source_name || "").localeCompare(
          String(right.source_name || ""),
          "zh-CN"
        );
      }
      return Number(right.id || 0) - Number(left.id || 0);
    });
    return rows;
  }

  function toggleStickerGroup(category) {
    var stickers = filteredStickerList().filter(function (sticker) {
      return (sticker.category || "未分类") === category;
    });
    var allSelected =
      stickers.length > 0 &&
      stickers.every(function (sticker) {
        return Boolean(selectedStickerIds[String(sticker.id)]);
      });
    stickers.forEach(function (sticker) {
      if (allSelected) delete selectedStickerIds[String(sticker.id)];
      else selectedStickerIds[String(sticker.id)] = true;
    });
    updateStickerSelectionUI();
  }

  function stickerMoodLabel(value) {
    return {
      happy: "开心",
      angry: "生气",
      sad: "难过",
      shy: "害羞",
      confused: "困惑",
      daily: "日常",
    }[value] || value || "未识别";
  }

  function createStickerCard(sticker) {
    var item = document.createElement("div");
    item.className = "agent-sticker-item";
    var check = document.createElement("label");
    check.className = "agent-sticker-check";
    check.title = "选择这张表情";
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = String(sticker.id);
    checkbox.setAttribute("data-sticker-check", "");
    checkbox.checked = Boolean(selectedStickerIds[String(sticker.id)]);
    checkbox.addEventListener("change", function () {
      if (checkbox.checked) selectedStickerIds[String(sticker.id)] = true;
      else delete selectedStickerIds[String(sticker.id)];
      updateStickerSelectionUI();
    });
    check.appendChild(checkbox);
    item.appendChild(check);

    if (sticker.kind === "image") {
      var image = document.createElement("img");
      image.src = "/agent-stickers/" + encodeURIComponent(sticker.ref);
      image.alt = "";
      image.title = sticker.source_name || sticker.category || "";
      item.appendChild(image);
    } else {
      var face = document.createElement("span");
      face.textContent = "表情 " + sticker.ref;
      item.appendChild(face);
    }
    var fileName = document.createElement("span");
    fileName.className = "agent-sticker-file-name";
    fileName.textContent = sticker.source_name || "未记录文件名";
    fileName.title = sticker.source_name || "未记录文件名";
    item.appendChild(fileName);
    var caption = document.createElement("span");
    caption.className = "agent-sticker-caption";
    caption.textContent =
      sticker.caption || "未填写描述";
    caption.title = sticker.caption || "未填写描述";
    item.appendChild(caption);
    var meta = document.createElement("span");
    meta.className = "agent-sticker-meta";
    meta.textContent =
      stickerMoodLabel(sticker.effective_mood || sticker.mood) +
      " · 使用 " + Number(sticker.use_count || 0) + " 次" +
      (sticker.keywords ? " · " + sticker.keywords : "");
    meta.title = meta.textContent;
    item.appendChild(meta);

    var remove = document.createElement("button");
    remove.type = "button";
    remove.title = "删除表情";
    remove.setAttribute("aria-label", "删除表情");
    remove.innerHTML = '<i data-lucide="x"></i>';
    remove.addEventListener("click", function () {
      fetch("/api/agent/web/sticker-delete", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: sticker.id }),
      })
        .then(readApiResponse)
        .then(loadStickers)
        .catch(function (error) {
          setSettingsStatus(error.message, settingsDirty);
        });
    });
    item.appendChild(remove);
    return item;
  }

  function renderStickerGroups() {
    stickerGrid.innerHTML = "";
    var grouped = {};
    var visible = filteredStickerList();
    visible.forEach(function (sticker) {
      var category = String(sticker.category || "未分类");
      if (!grouped[category]) grouped[category] = [];
      grouped[category].push(sticker);
    });
    stickerCategories.forEach(function (category) {
      var stickers = grouped[category] || [];
      if (!stickers.length) return;
      var group = document.createElement("section");
      group.className = "agent-sticker-category-group";
      var head = document.createElement("header");
      head.className = "agent-sticker-category-head";
      var title = document.createElement("div");
      var heading = document.createElement("h4");
      heading.textContent = category;
      var count = document.createElement("span");
      count.textContent = stickers.length + " 张";
      title.append(heading, count);
      var selectGroup = document.createElement("button");
      selectGroup.type = "button";
      selectGroup.className = "agent-sticker-select-group";
      selectGroup.textContent = "全选本组";
      selectGroup.addEventListener("click", function () {
        toggleStickerGroup(category);
      });
      head.append(title, selectGroup);
      var grid = document.createElement("div");
      grid.className = "agent-sticker-grid";
      stickers.forEach(function (sticker) {
        grid.appendChild(createStickerCard(sticker));
      });
      group.append(head, grid);
      stickerGrid.appendChild(group);
    });
    var pending = currentStickers.filter(function (sticker) {
      return Boolean(sticker.needs_metadata);
    }).length;
    stickerFilterSummary.textContent =
      "显示 " + visible.length + " / " + currentStickers.length +
      " 张 · 待整理 " + pending + " 张";
    if (!visible.length) {
      stickerGrid.innerHTML =
        '<div class="agent-sticker-item"><span>' +
        (currentStickers.length ? "没有匹配的表情" : "暂无") +
        "</span></div>";
    }
    updateStickerSelectionUI();
    refreshIcons();
  }

  function loadStickers() {
    return fetch("/api/agent/web/stickers", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(readApiResponse)
      .then(function (data) {
        currentStickers = data.stickers || [];
        stickerCategories = cleanStickerCategories(data.categories);
        var validIds = {};
        currentStickers.forEach(function (sticker) {
          validIds[String(sticker.id)] = true;
        });
        Object.keys(selectedStickerIds).forEach(function (stickerId) {
          if (!validIds[stickerId]) delete selectedStickerIds[stickerId];
        });
        document.getElementById("agentStickerCount").textContent =
          currentStickers.length + " 个";
        refreshStickerCategoryControls();
        renderStickerGroups();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function fileBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var value = String(reader.result || "");
        resolve(value.slice(value.indexOf(",") + 1));
      };
      reader.onerror = function () {
        reject(new Error("读取图片失败"));
      };
      reader.readAsDataURL(file);
    });
  }

  function uploadStickerFiles(files) {
    var category = stickerCategorySelect.value || "未分类";
    var caption = stickerUploadCaption.value.trim();
    var keywords = stickerUploadKeywords.value.trim();
    var mood = stickerUploadMood.value;
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;
    stickerUploadBtn.classList.add("is-uploading");
    stickerUploadBtn.setAttribute("aria-disabled", "true");
    setSettingsStatus("正在上传表情包…", settingsDirty);
    list
      .reduce(function (chain, file) {
        return chain.then(function () {
          if (file.size > 5 * 1024 * 1024) {
            throw new Error(file.name + " 超过 5MB");
          }
          return fileBase64(file).then(function (data) {
            return fetch("/api/agent/web/sticker-upload", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                file_name: file.name,
                category: category,
                caption: caption,
                keywords: keywords,
                mood: mood,
                data_base64: data,
              }),
            }).then(readApiResponse);
          });
        });
      }, Promise.resolve())
      .then(function () {
        setSettingsStatus(
          "表情包已上传到“" + category + "”",
          settingsDirty
        );
        stickerUploadCaption.value = "";
        stickerUploadKeywords.value = "";
        stickerUploadMood.value = "";
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(
          error && error.message ? error.message : "上传失败",
          settingsDirty
        );
      })
      .then(function () {
        stickerUploadBtn.classList.remove("is-uploading");
        stickerUploadBtn.removeAttribute("aria-disabled");
        stickerInput.value = "";
      });
  }

  function createStickerCategory() {
    var name = stickerCategoryName.value.trim();
    if (!name) {
      setSettingsStatus("请填写分类名称", settingsDirty);
      stickerCategoryName.focus();
      return;
    }
    setSettingsStatus("正在创建分类…", settingsDirty);
    fetch("/api/agent/web/sticker-category-create", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name }),
    })
      .then(readApiResponse)
      .then(function (data) {
        stickerCategories = cleanStickerCategories(data.categories);
        refreshStickerCategoryControls(data.category);
        stickerCategoryForm.hidden = true;
        stickerCategoryName.value = "";
        setSettingsStatus("分类“" + data.category + "”已创建", settingsDirty);
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function moveSelectedStickers() {
    var ids = Object.keys(selectedStickerIds).map(Number);
    if (!ids.length) {
      setSettingsStatus("请先选择表情包", settingsDirty);
      return;
    }
    var category = stickerBulkCategory.value || "未分类";
    stickerBulkMove.disabled = true;
    setSettingsStatus("正在移动表情包…", settingsDirty);
    fetch("/api/agent/web/sticker-move", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids, category: category }),
    })
      .then(readApiResponse)
      .then(function (data) {
        selectedStickerIds = {};
        setSettingsStatus(
          "已移动 " + data.moved + " 张到“" + data.category + "”",
          settingsDirty
        );
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        stickerBulkMove.disabled = false;
      });
  }

  function updateSelectedStickerMetadata() {
    var ids = Object.keys(selectedStickerIds).map(Number);
    if (!ids.length) {
      setSettingsStatus("请先选择表情包", settingsDirty);
      return;
    }
    var payload = { ids: ids };
    var caption = stickerBulkCaption.value.trim();
    var keywords = stickerBulkKeywords.value.trim();
    var mood = stickerBulkMood.value;
    if (caption) payload.caption = caption;
    if (keywords) payload.keywords = keywords;
    if (mood) payload.mood = mood;
    if (Object.keys(payload).length === 1) {
      setSettingsStatus("填写描述、关键词或情绪后再保存", settingsDirty);
      return;
    }
    stickerBulkUpdate.disabled = true;
    setSettingsStatus("正在更新表情元数据…", settingsDirty);
    fetch("/api/agent/web/sticker-update", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(readApiResponse)
      .then(function (data) {
        setSettingsStatus(
          "已更新 " + Number(data.updated || 0) + " 张表情的元数据",
          settingsDirty
        );
        stickerBulkCaption.value = "";
        stickerBulkKeywords.value = "";
        stickerBulkMood.value = "";
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        stickerBulkUpdate.disabled = false;
      });
  }

  function exportStickerPack() {
    setSettingsStatus("正在准备表情包 ZIP…", settingsDirty);
    window.location.assign("/api/agent/web/sticker-export");
  }

  function importStickerPack(file) {
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) {
      setSettingsStatus("表情包 ZIP 不能超过 50MB", true);
      return;
    }
    stickerImportBtn.classList.add("is-uploading");
    stickerImportBtn.setAttribute("aria-disabled", "true");
    setSettingsStatus("正在导入表情包 ZIP…", settingsDirty);
    fileBase64(file)
      .then(function (data) {
        return fetch("/api/agent/web/sticker-import", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data_base64: data }),
        }).then(readApiResponse);
      })
      .then(function (data) {
        setSettingsStatus(
          "已导入 " + Number(data.imported || 0) +
          " 张，跳过重复 " + Number(data.duplicates || 0) +
          " 张，忽略 " + Number(data.skipped || 0) + " 张",
          settingsDirty
        );
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, true);
      })
      .then(function () {
        stickerImportBtn.classList.remove("is-uploading");
        stickerImportBtn.removeAttribute("aria-disabled");
        stickerImportInput.value = "";
      });
  }

  function setupSectionNavigation() {
    var links = Array.prototype.slice.call(
      document.querySelectorAll("[data-section-link]")
    );
    var sections = Array.prototype.slice.call(
      document.querySelectorAll("[data-console-section]")
    );
    var nav = document.querySelector(".agent-console-nav");
    var navigationLockUntil = 0;
    var framePending = false;
    var activeSectionId = "";
    function setActive(sectionId, revealLink) {
      var changed = activeSectionId !== sectionId;
      activeSectionId = sectionId;
      links.forEach(function (link) {
        var active =
          link.getAttribute("data-section-link") === sectionId;
        link.classList.toggle("is-active", active);
        if (active) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
        if (active && changed && revealLink && window.innerWidth <= 900) {
          nav.scrollLeft = Math.max(
            0,
            link.offsetLeft - (nav.clientWidth - link.offsetWidth) / 2
          );
        }
      });
    }
    function syncActiveFromScroll() {
      framePending = false;
      if (Date.now() < navigationLockUntil || !sections.length) return;
      var current = sections[0].id;
      sections.forEach(function (section) {
        if (section.getBoundingClientRect().top <= 112) {
          current = section.id;
        }
      });
      var pageAtBottom =
        window.scrollY + window.innerHeight >=
        document.documentElement.scrollHeight - 2;
      if (pageAtBottom) current = sections[sections.length - 1].id;
      setActive(current, false);
    }
    function requestSync() {
      if (framePending) return;
      framePending = true;
      window.requestAnimationFrame(syncActiveFromScroll);
    }
    links.forEach(function (link) {
      link.addEventListener("click", function () {
        var sectionId = link.getAttribute("data-section-link");
        setActive(sectionId, true);
        navigationLockUntil = Date.now() + 700;
        window.setTimeout(syncActiveFromScroll, 720);
      });
    });
    window.addEventListener("scroll", requestSync, { passive: true });
    window.addEventListener("resize", requestSync, { passive: true });
    requestSync();
  }

  settingsSave.addEventListener("click", saveSettings);
  document
    .querySelectorAll("[data-setting-input]")
    .forEach(function (input) {
      input.addEventListener("input", markSettingsDirty);
      input.addEventListener("change", markSettingsDirty);
    });
  memorySearch.addEventListener("input", function () {
    var value = this.value;
    window.clearTimeout(memorySearchTimer);
    memorySearchTimer = window.setTimeout(function () {
      loadMemories(value);
    }, 180);
  });
  memoryArchived.addEventListener("change", function () {
    loadMemories(memorySearch.value);
  });
  stickerUploadBtn.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    stickerInput.click();
  });
  stickerInput.addEventListener("change", function () {
    uploadStickerFiles(this.files);
  });
  stickerSearch.addEventListener("input", renderStickerGroups);
  stickerMoodFilter.addEventListener("change", renderStickerGroups);
  stickerSort.addEventListener("change", renderStickerGroups);
  stickerPendingOnly.addEventListener("change", renderStickerGroups);
  stickerExport.addEventListener("click", exportStickerPack);
  stickerImportInput.addEventListener("change", function () {
    importStickerPack(this.files && this.files[0]);
  });
  stickerImportBtn.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    stickerImportInput.click();
  });
  stickerCategorySelect.addEventListener("change", function () {
    stickerUploadTarget.textContent = "上传到“" + this.value + "”";
  });
  stickerCategoryAdd.addEventListener("click", function () {
    stickerCategoryForm.hidden = false;
    stickerCategoryName.focus();
  });
  stickerCategoryCancel.addEventListener("click", function () {
    stickerCategoryForm.hidden = true;
    stickerCategoryName.value = "";
  });
  stickerCategoryForm.addEventListener("submit", function (event) {
    event.preventDefault();
    createStickerCategory();
  });
  stickerBulkMove.addEventListener("click", moveSelectedStickers);
  stickerBulkUpdate.addEventListener("click", updateSelectedStickerMetadata);
  timelineForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var title = document.getElementById("agentTimelineTitle").value.trim();
    var content = document.getElementById("agentTimelineContent").value.trim();
    if (!title && !content) {
      setSettingsStatus("请填写事件标题或内容", settingsDirty);
      return;
    }
    var addButton = document.getElementById("agentTimelineAdd");
    addButton.disabled = true;
    fetch("/api/agent/web/timeline-create", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title,
        content: content,
        event_type: document.getElementById("agentTimelineType").value,
        event_at: timelineTimestamp(
          document.getElementById("agentTimelineEventAt").value
        ),
        follow_up_at: timelineTimestamp(
          document.getElementById("agentTimelineFollowUpAt").value
        ),
      }),
    })
      .then(readApiResponse)
      .then(function () {
        timelineForm.reset();
        setSettingsStatus("已加入时间线", settingsDirty);
        return loadTimeline();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        addButton.disabled = false;
      });
  });

  refreshIcons();
  setupSectionNavigation();
  loadStatus();
  loadSettings();
  loadMemories("");
  loadGroupMembers();
  loadTimeline();
  loadStickers();
  window.setInterval(loadStatus, 30000);
})();
