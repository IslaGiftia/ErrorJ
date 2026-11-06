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
  var jargonList = document.getElementById("agentJargonList");
  var jargonCount = document.getElementById("agentJargonCount");
  var jargonStatusFilter = document.getElementById("agentJargonStatusFilter");
  var diagnosticsThreads = document.getElementById("agentDiagnosticThreads");
  var diagnosticsCounts = document.getElementById("agentDiagnosticCounts");
  var diagnosticsCleanup = document.getElementById("agentDiagnosticCleanup");
  var diagnosticsSearchResult = document.getElementById(
    "agentDiagnosticsSearchResult"
  );
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
  var stickerLibrarySelect = document.getElementById("agentStickerLibrary");
  var stickerLibraryEnabled = document.getElementById("agentStickerLibraryEnabled");
  var stickerLibraryAdd = document.getElementById("agentStickerLibraryAdd");
  var stickerLibraryCreateForm = document.getElementById("agentStickerLibraryCreateForm");
  var stickerLibraryCreateName = document.getElementById("agentStickerLibraryCreateName");
  var stickerLibraryCreateCancel = document.getElementById("agentStickerLibraryCreateCancel");
  var stickerLibraryRenameForm = document.getElementById("agentStickerLibraryRenameForm");
  var stickerLibraryRename = document.getElementById("agentStickerLibraryRename");
  var stickerAutoCollectEnabled = document.getElementById("settingStickerAutoCollectEnabled");
  var stickerAutoCollectLibrary = document.getElementById("settingStickerAutoCollectLibrary");
  var stickerRuleScope = document.getElementById("agentStickerRuleScope");
  var stickerRuleKeyLabel = document.getElementById("agentStickerRuleKeyLabel");
  var stickerRuleKey = document.getElementById("agentStickerRuleKey");
  var stickerRuleLibraries = document.getElementById("agentStickerRuleLibraries");
  var stickerRuleSummary = document.getElementById("agentStickerRuleSummary");
  var stickerRuleSave = document.getElementById("agentStickerRuleSave");
  var stickerCandidateCount = document.getElementById("agentStickerCandidateCount");
  var stickerCandidateList = document.getElementById("agentStickerCandidateList");
  var stickerBulk = document.getElementById("agentStickerBulk");
  var stickerSelectedCount = document.getElementById("agentStickerSelectedCount");
  var stickerBulkCategory = document.getElementById("agentStickerBulkCategory");
  var stickerBulkMove = document.getElementById("agentStickerBulkMove");
  var stickerBulkCaption = document.getElementById("agentStickerBulkCaption");
  var stickerBulkKeywords = document.getElementById("agentStickerBulkKeywords");
  var stickerBulkMood = document.getElementById("agentStickerBulkMood");
  var stickerBulkUpdate = document.getElementById("agentStickerBulkUpdate");
  var stickerBulkLibrary = document.getElementById("agentStickerBulkLibrary");
  var stickerBulkLibraryMove = document.getElementById("agentStickerBulkLibraryMove");
  var stickerCategories = ["未分类"];
  var selectedStickerIds = {};
  var currentStickers = [];
  var stickerLibraries = [];
  var stickerRules = [];
  var stickerRuleGroups = [];
  var stickerCandidates = [];
  var selectedStickerLibraryId = "default";
  var stickerAutoCollectLibraryValue = "default";
  var currentJargonItems = [];
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

  function numberSetting(id, fallback) {
    var element = document.getElementById(id);
    if (!element || element.value === "") return fallback;
    var value = Number(element.value);
    return Number.isFinite(value) ? value : fallback;
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
          "settingMemoryImmediateExtractionEnabled",
          settings.memory_immediate_extraction_enabled
        );
        settingValue(
          "settingMemoryImmediateDailyLimit",
          settings.memory_immediate_extraction_daily_limit
        );
        settingValue(
          "settingPrivateHistoryRetentionDays",
          settings.private_history_retention_days
        );
        settingValue(
          "settingGroupHistoryRetentionDays",
          settings.group_history_retention_days
        );
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
        settingValue(
          "settingStickerAutoCollectEnabled",
          settings.sticker_auto_collect_enabled
        );
        stickerAutoCollectLibraryValue = String(
          settings.sticker_auto_collect_library || "default"
        );
        settingValue(
          "settingStickerAutoCollectLibrary",
          stickerAutoCollectLibraryValue
        );
        settingValue("settingChatHumanDelay", settings.chat_human_delay);
        settingValue("settingPersonaPreset", settings.persona_preset);
        settingValue(
          "settingPersonaCustomPrompt",
          settings.persona_custom_prompt
        );
        settingValue("settingWebSearchEnabled", settings.web_search_enabled);
        settingValue("settingWebSearchCount", settings.web_search_count);
        settingValue(
          "settingWebDomainRoutingEnabled",
          settings.web_domain_routing_enabled
        );
        settingValue(
          "settingGroupProactiveEnabled",
          settings.group_proactive_enabled
        );
        settingValue(
          "settingGroupIdleProactiveEnabled",
          settings.group_idle_proactive_enabled
        );
        settingValue(
          "settingGroupReplyControlEnabled",
          settings.group_reply_control_enabled
        );
        settingValue(
          "settingGroupActivityLevel",
          settings.group_activity_level || "balanced"
        );
        settingValue(
          "settingGroupJargonEnabled",
          settings.group_jargon_enabled
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
        settingValue(
          "settingGroupReplyMax",
          settings.group_reply_max_per_10m
        );
        settingValue(
          "settingGroupReplyFatigueRounds",
          settings.group_reply_fatigue_rounds
        );
        settingValue(
          "settingGroupMessageMergeSeconds",
          settings.group_message_merge_seconds
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
      memory_immediate_extraction_enabled: document.getElementById(
        "settingMemoryImmediateExtractionEnabled"
      ).checked,
      memory_immediate_extraction_daily_limit:
        Number(
          document.getElementById("settingMemoryImmediateDailyLimit").value
        ) || 12,
      private_history_retention_days:
        numberSetting("settingPrivateHistoryRetentionDays", 90),
      group_history_retention_days:
        numberSetting("settingGroupHistoryRetentionDays", 30),
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
      sticker_auto_collect_enabled: stickerAutoCollectEnabled.checked,
      sticker_auto_collect_library:
        stickerAutoCollectLibrary.value || "default",
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
      web_domain_routing_enabled: document.getElementById(
        "settingWebDomainRoutingEnabled"
      ).checked,
      group_proactive_enabled: document.getElementById(
        "settingGroupProactiveEnabled"
      ).checked,
      group_idle_proactive_enabled: document.getElementById(
        "settingGroupIdleProactiveEnabled"
      ).checked,
      group_reply_control_enabled: document.getElementById(
        "settingGroupReplyControlEnabled"
      ).checked,
      group_activity_level: document.getElementById(
        "settingGroupActivityLevel"
      ).value,
      group_jargon_enabled: document.getElementById(
        "settingGroupJargonEnabled"
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
      group_reply_max_per_10m:
        Number(document.getElementById("settingGroupReplyMax").value) || 6,
      group_reply_fatigue_rounds:
        Number(
          document.getElementById("settingGroupReplyFatigueRounds").value
        ) || 3,
      group_message_merge_seconds:
        Number(
          document.getElementById("settingGroupMessageMergeSeconds").value
        ) || 0,
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

  function jargonStatusLabel(status) {
    if (status === "approved") return "已启用";
    if (status === "rejected") return "已忽略";
    return "待确认";
  }

  function renderGroupJargon() {
    var filter = jargonStatusFilter.value || "pending";
    var items = currentJargonItems.filter(function (item) {
      return filter === "all" || item.status === filter;
    });
    jargonList.innerHTML = "";
    if (!items.length) {
      jargonList.innerHTML =
        '<div class="agent-memory-item"><p>当前没有符合条件的群黑话。</p></div>';
      return;
    }
    items.forEach(function (item) {
      var status = String(item.status || "pending");
      var element = document.createElement("div");
      element.className = "agent-memory-item agent-jargon-item";
      element.dataset.jargonId = String(item.id);
      var actions = [
        '<button type="button" data-jargon-action="save">保存</button>',
      ];
      if (status === "pending") {
        actions.unshift(
          '<button type="button" class="is-primary" data-jargon-action="approve">批准并启用</button>'
        );
        actions.push(
          '<button type="button" data-jargon-action="reject">忽略</button>'
        );
      } else if (status === "approved") {
        actions.push(
          '<button type="button" data-jargon-action="reject">停用</button>'
        );
      } else {
        actions = [
          '<button type="button" data-jargon-action="reopen">重新打开</button>',
        ];
      }
      actions.push(
        '<button type="button" data-jargon-action="delete">删除</button>'
      );
      element.innerHTML =
        '<div class="agent-jargon-copy">' +
          '<div class="agent-jargon-head">' +
            '<strong class="agent-jargon-term">' +
              escapeHtml(item.term) +
            "</strong>" +
            '<span class="agent-jargon-status ' +
              (status === "approved" ? "is-approved" : "") +
            '">' + jargonStatusLabel(status) + "</span>" +
            '<span class="agent-jargon-meta">' +
              escapeHtml(item.group_label || item.group_id || "") +
              " · 出现 " + Number(item.occurrences || 0) + " 次" +
              " · " + Number(item.member_count || 0) + " 人使用" +
            "</span>" +
          "</div>" +
          '<div class="agent-jargon-editor">' +
            "<label><span>在群里的意思</span>" +
              '<input class="agent-jargon-meaning" maxlength="500" ' +
                'value="' + escapeHtml(item.meaning || "") + '" ' +
                'placeholder="例如：表示非常赞同或夸张"></label>' +
            "<label><span>例句（可选）</span>" +
              '<input class="agent-jargon-example" maxlength="500" ' +
                'value="' + escapeHtml(item.example || "") + '" ' +
                'placeholder="例如：这操作真绝绝子"></label>' +
          "</div>" +
          '<div class="agent-jargon-actions">' + actions.join("") + "</div>" +
        "</div>";
      jargonList.appendChild(element);
    });
  }

  function loadGroupJargon() {
    return fetch("/api/agent/web/group-jargon", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(readApiResponse)
      .then(function (data) {
        currentJargonItems = data.items || [];
        jargonCount.textContent =
          Number(data.pending_count || 0) + " 待确认 · " +
          Number(data.approved_count || 0) + " 已启用";
        renderGroupJargon();
      })
      .catch(function (error) {
        currentJargonItems = [];
        jargonList.innerHTML =
          '<div class="agent-memory-item"><p>' +
          escapeHtml(error.message) +
          "</p></div>";
      });
  }

  function updateGroupJargon(item, action) {
    var meaning = item.querySelector(".agent-jargon-meaning").value.trim();
    var example = item.querySelector(".agent-jargon-example").value.trim();
    if (action === "approve" && !meaning) {
      setSettingsStatus("批准前请填写这个词在群里的意思。", settingsDirty);
      item.querySelector(".agent-jargon-meaning").focus();
      return;
    }
    var buttons = item.querySelectorAll("button");
    buttons.forEach(function (button) {
      button.disabled = true;
    });
    fetch("/api/agent/web/group-jargon", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: Number(item.dataset.jargonId),
        action: action,
        meaning: meaning,
        example: example,
      }),
    })
      .then(readApiResponse)
      .then(function (data) {
        currentJargonItems = data.items || [];
        if (action === "approve" && jargonStatusFilter.value === "pending") {
          jargonStatusFilter.value = "approved";
        } else if (
          action === "reject" &&
          jargonStatusFilter.value !== "all"
        ) {
          jargonStatusFilter.value = "all";
        } else if (
          action === "reopen" &&
          jargonStatusFilter.value !== "all"
        ) {
          jargonStatusFilter.value = "pending";
        }
        jargonCount.textContent =
          Number(data.pending_count || 0) + " 待确认 · " +
          Number(data.approved_count || 0) + " 已启用";
        setSettingsStatus("群黑话已更新", settingsDirty);
        renderGroupJargon();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
        buttons.forEach(function (button) {
          button.disabled = false;
        });
      });
  }

  function diagnosticsRow(label, value) {
    return (
      '<div class="agent-diagnostics-row"><span>' +
      escapeHtml(label) +
      "</span><strong>" +
      escapeHtml(value) +
      "</strong></div>"
    );
  }

  function formatBytes(bytes) {
    var value = Math.max(0, Number(bytes) || 0);
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
    return (value / (1024 * 1024)).toFixed(1) + " MB";
  }

  function renderDiagnostics(data) {
    var metrics = data.metrics || {};
    var today = metrics.today || {};
    var calls = Number(metrics.total_calls || 0);
    var failures = Number(metrics.failed_calls || 0);
    document.getElementById("agentDiagnosticCalls").textContent = String(calls);
    document.getElementById("agentDiagnosticFailures").textContent =
      String(failures);
    document.getElementById("agentDiagnosticDb").textContent = formatBytes(
      (data.database || {}).size_bytes
    );
    document.getElementById("agentDiagnosticQuiet").textContent = String(
      (data.active_quiet || []).length
    );
    document.getElementById("agentDiagnosticsUpdated").textContent =
      "更新于 " + new Date().toLocaleTimeString();

    var threadLabels = {
      proactive: "主动聊天",
      reminders: "定时提醒",
      memory: "记忆整理",
      qqbot: "QQBot 连接",
    };
    var threadRows = [];
    Object.keys(threadLabels).forEach(function (key) {
      var state = (data.threads || {})[key] || {};
      threadRows.push(
        diagnosticsRow(
          threadLabels[key],
          state.alive ? "运行中" : state.present ? "已停止" : "未启用"
        )
      );
    });
    ["llm", "search", "fetch", "hot_search"].forEach(function (kind) {
      if (!today[kind]) return;
      threadRows.push(
        diagnosticsRow(
          {
            llm: "今日模型调用",
            search: "今日搜索",
            fetch: "今日抓取",
            hot_search: "今日热搜",
          }[kind],
          String(
            Number(today[kind].success || 0) +
            Number(today[kind].failure || 0)
          )
        )
      );
    });
    diagnosticsThreads.innerHTML = threadRows.join("");

    var counts = (data.database || {}).counts || {};
    diagnosticsCounts.innerHTML = [
      diagnosticsRow("私聊历史", String(counts.messages || 0) + " 条"),
      diagnosticsRow("群聊历史", String(counts.group_messages || 0) + " 条"),
      diagnosticsRow("长期记忆", String(counts.memories || 0) + " 条"),
      diagnosticsRow("群黑话", String(counts.group_jargon || 0) + " 条"),
      diagnosticsRow("待发送提醒", String(counts.pending_reminders || 0) + " 条"),
    ].join("");

    var cleanup = data.history_cleanup;
    diagnosticsCleanup.innerHTML = cleanup
      ? [
          diagnosticsRow("最近清理", cleanup.day || "--"),
          diagnosticsRow(
            "清理私聊",
            String(cleanup.private_deleted || 0) + " 条"
          ),
          diagnosticsRow(
            "清理群聊",
            String(cleanup.group_deleted || 0) + " 条"
          ),
        ].join("")
      : diagnosticsRow("最近清理", "尚未运行");

    var check = data.search_check;
    if (check) {
      diagnosticsSearchResult.textContent =
        (check.ok ? "搜索测试成功：" : "搜索测试失败：") +
        (check.message || "");
    }
  }

  function loadDiagnostics(action) {
    var options = {
      credentials: "same-origin",
      cache: "no-store",
      headers: {},
    };
    if (action) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify({ action: action });
    }
    return fetch("/api/agent/web/diagnostics", options)
      .then(readApiResponse)
      .then(renderDiagnostics)
      .catch(function (error) {
        diagnosticsSearchResult.textContent = error.message;
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
      if (
        String(sticker.library_id || "default") !==
        selectedStickerLibraryId
      ) {
        return false;
      }
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
      return (
        String(sticker.library_id || "default") ===
          selectedStickerLibraryId &&
        Boolean(sticker.needs_metadata)
      );
    }).length;
    var libraryTotal = currentStickers.filter(function (sticker) {
      return (
        String(sticker.library_id || "default") ===
        selectedStickerLibraryId
      );
    }).length;
    stickerFilterSummary.textContent =
      "显示 " + visible.length + " / " + libraryTotal +
      " 张 · 待整理 " + pending + " 张";
    if (!visible.length) {
      stickerGrid.innerHTML =
        '<div class="agent-sticker-item"><span>' +
        (libraryTotal ? "没有匹配的表情" : "这个图库还是空的") +
        "</span></div>";
    }
    updateStickerSelectionUI();
    refreshIcons();
  }

  function stickerLibraryById(libraryId) {
    var targetId = String(libraryId || "default");
    return stickerLibraries.find(function (library) {
      return String(library.id) === targetId;
    }) || null;
  }

  function fillStickerLibrarySelect(select, selectedId) {
    select.innerHTML = "";
    stickerLibraries.forEach(function (library) {
      var option = document.createElement("option");
      option.value = String(library.id);
      option.textContent =
        String(library.name || library.id) +
        " · " + Number(library.sticker_count || 0) + " 张" +
        (Number(library.enabled) ? "" : "（停用）");
      select.appendChild(option);
    });
    if (stickerLibraries.length) {
      var exists = stickerLibraries.some(function (library) {
        return String(library.id) === String(selectedId);
      });
      select.value = exists
        ? String(selectedId)
        : String(stickerLibraries[0].id);
    }
  }

  function refreshStickerLibraryControls(preferredId) {
    var targetId = String(
      preferredId || selectedStickerLibraryId || "default"
    );
    fillStickerLibrarySelect(stickerLibrarySelect, targetId);
    fillStickerLibrarySelect(stickerBulkLibrary, targetId);
    fillStickerLibrarySelect(
      stickerAutoCollectLibrary,
      stickerAutoCollectLibraryValue
    );
    selectedStickerLibraryId = stickerLibrarySelect.value || "default";
    stickerLibrarySelect.value = selectedStickerLibraryId;
    var library = stickerLibraryById(selectedStickerLibraryId);
    stickerLibraryEnabled.checked = Boolean(
      library && Number(library.enabled)
    );
    stickerLibraryRename.value = library ? String(library.name || "") : "";
    stickerAutoCollectLibraryValue = stickerAutoCollectLibrary.value || "default";
  }

  function changeSelectedStickerLibrary(libraryId) {
    selectedStickerLibraryId = String(libraryId || "default");
    selectedStickerIds = {};
    refreshStickerLibraryControls(selectedStickerLibraryId);
    renderStickerGroups();
  }

  function updateStickerLibrary(action, payload) {
    return fetch("/api/agent/web/sticker-library", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ action: action }, payload || {})),
    }).then(readApiResponse);
  }

  function saveStickerLibraryEnabled() {
    var library = stickerLibraryById(selectedStickerLibraryId);
    if (!library) return;
    stickerLibraryEnabled.disabled = true;
    updateStickerLibrary("update", {
      id: selectedStickerLibraryId,
      enabled: stickerLibraryEnabled.checked,
    })
      .then(function () {
        setSettingsStatus(
          "图库“" + library.name + "”已" +
          (stickerLibraryEnabled.checked ? "启用" : "停用"),
          settingsDirty
        );
        return loadStickers();
      })
      .catch(function (error) {
        stickerLibraryEnabled.checked = !stickerLibraryEnabled.checked;
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        stickerLibraryEnabled.disabled = false;
      });
  }

  function createStickerLibrary() {
    var name = stickerLibraryCreateName.value.trim();
    if (!name) {
      stickerLibraryCreateName.focus();
      return;
    }
    updateStickerLibrary("create", { name: name })
      .then(function (data) {
        stickerLibraries = data.libraries || stickerLibraries;
        stickerLibraryCreateForm.hidden = true;
        stickerLibraryCreateName.value = "";
        selectedStickerLibraryId = String(data.id || selectedStickerLibraryId);
        setSettingsStatus("图库“" + name + "”已创建", settingsDirty);
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function renameStickerLibrary() {
    var name = stickerLibraryRename.value.trim();
    var library = stickerLibraryById(selectedStickerLibraryId);
    if (!library || !name) {
      stickerLibraryRename.focus();
      return;
    }
    updateStickerLibrary("update", {
      id: selectedStickerLibraryId,
      name: name,
    })
      .then(function () {
        setSettingsStatus("图库名称已保存", settingsDirty);
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      });
  }

  function moveSelectedStickersLibrary() {
    var ids = Object.keys(selectedStickerIds).map(Number);
    if (!ids.length) {
      setSettingsStatus("请先选择表情包", settingsDirty);
      return;
    }
    var libraryId = stickerBulkLibrary.value;
    var library = stickerLibraryById(libraryId);
    if (!library) return;
    stickerBulkLibraryMove.disabled = true;
    updateStickerLibrary("move", {
      ids: ids,
      library_id: libraryId,
    })
      .then(function (data) {
        selectedStickerIds = {};
        setSettingsStatus(
          "已移动 " + Number(data.moved || 0) +
          " 张到“" + library.name + "”",
          settingsDirty
        );
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        stickerBulkLibraryMove.disabled = false;
      });
  }

  function stickerRuleKeyOptions() {
    var scope = stickerRuleScope.value;
    if (scope === "group") {
      return stickerRuleGroups.map(function (group) {
        return {
          value: String(group.platform) + ":" + String(group.group_id),
          label: String(group.label || group.group_id),
        };
      });
    }
    if (scope === "persona") {
      var select = document.getElementById("settingPersonaPreset");
      return Array.prototype.slice.call(select.options)
        .filter(function (option) {
          return option.value;
        })
        .map(function (option) {
          return { value: option.value, label: option.textContent };
        });
    }
    return [];
  }

  function refreshStickerRuleKeys() {
    var options = stickerRuleKeyOptions();
    stickerRuleKey.innerHTML = "";
    options.forEach(function (item) {
      var option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      stickerRuleKey.appendChild(option);
    });
    stickerRuleKeyLabel.hidden = stickerRuleScope.value === "default";
    renderStickerRuleLibraries();
  }

  function selectedStickerRuleKey() {
    if (stickerRuleScope.value === "default") return "";
    return stickerRuleKey.value || "";
  }

  function selectedStickerRule() {
    var scope = stickerRuleScope.value;
    var key = selectedStickerRuleKey();
    return stickerRules.find(function (rule) {
      return (
        String(rule.scope_type) === scope &&
        String(rule.scope_key || "") === key
      );
    }) || null;
  }

  function renderStickerRuleLibraries() {
    var selected = selectedStickerRule();
    var selectedIds = {};
    ((selected && selected.library_ids) || []).forEach(function (libraryId) {
      selectedIds[String(libraryId)] = true;
    });
    stickerRuleLibraries.innerHTML = "";
    stickerLibraries.forEach(function (library) {
      var label = document.createElement("label");
      var input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(library.id);
      input.checked = Boolean(selectedIds[String(library.id)]);
      var text = document.createElement("span");
      text.textContent = String(library.name || library.id);
      label.append(input, text);
      stickerRuleLibraries.appendChild(label);
    });
    var summary = stickerRules.map(function (rule) {
      var scopeLabel = {
        default: "默认",
        group: "群聊",
        persona: "人格",
      }[rule.scope_type] || rule.scope_type;
      var keyLabel = rule.scope_key ? " " + rule.scope_key : "";
      return scopeLabel + keyLabel + " → " + (rule.library_ids || []).length + " 个图库";
    });
    stickerRuleSummary.textContent = summary.length
      ? summary.join("；")
      : "当前没有自定义规则，使用所有启用图库";
  }

  function refreshStickerRules() {
    refreshStickerRuleKeys();
  }

  function saveStickerRule() {
    var libraryIds = Array.prototype.slice.call(
      stickerRuleLibraries.querySelectorAll("input:checked")
    ).map(function (input) {
      return input.value;
    });
    stickerRuleSave.disabled = true;
    fetch("/api/agent/web/sticker-rule", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scope_type: stickerRuleScope.value,
        scope_key: selectedStickerRuleKey(),
        library_ids: libraryIds,
      }),
    })
      .then(readApiResponse)
      .then(function (data) {
        stickerRules = data.rules || stickerRules;
        setSettingsStatus(
          libraryIds.length ? "选图规则已保存" : "当前规则已清除",
          settingsDirty
        );
        refreshStickerRules();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        stickerRuleSave.disabled = false;
      });
  }

  function reviewStickerCandidate(candidate, action, categorySelect, button) {
    button.disabled = true;
    fetch("/api/agent/web/sticker-candidate", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: candidate.id,
        action: action,
        category: categorySelect ? categorySelect.value : "未分类",
      }),
    })
      .then(readApiResponse)
      .then(function () {
        setSettingsStatus(
          action === "accept" ? "表情已加入图库" : "候选表情已丢弃",
          settingsDirty
        );
        return loadStickers();
      })
      .catch(function (error) {
        setSettingsStatus(error.message, settingsDirty);
      })
      .then(function () {
        button.disabled = false;
      });
  }

  function renderStickerCandidates() {
    stickerCandidateCount.textContent = stickerCandidates.length + " 张";
    stickerCandidateList.innerHTML = "";
    if (!stickerCandidates.length) {
      stickerCandidateList.innerHTML =
        '<p class="agent-section-note">没有待审核表情</p>';
      return;
    }
    stickerCandidates.forEach(function (candidate) {
      var card = document.createElement("article");
      card.className = "agent-sticker-candidate";
      var image = document.createElement("img");
      image.src = "/agent-stickers/" + encodeURIComponent(candidate.ref);
      image.alt = candidate.source_name || "候选表情";
      image.loading = "lazy";
      var copy = document.createElement("div");
      copy.className = "agent-sticker-candidate-copy";
      var name = document.createElement("span");
      name.className = "agent-sticker-candidate-name";
      name.textContent = candidate.source_name || candidate.ref;
      var meta = document.createElement("span");
      meta.className = "agent-sticker-candidate-meta";
      meta.textContent =
        (candidate.platform === "qqbot" ? "QQBot" : "OneBot") +
        " · " + (candidate.library_name || "默认图库") +
        " · " + timelineDate(candidate.created_at);
      copy.append(name, meta);
      var actions = document.createElement("div");
      actions.className = "agent-sticker-candidate-actions";
      var category = document.createElement("select");
      stickerCategories.forEach(function (value) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        category.appendChild(option);
      });
      var accept = document.createElement("button");
      accept.type = "button";
      accept.className = "is-primary";
      accept.textContent = "接收";
      accept.addEventListener("click", function () {
        reviewStickerCandidate(candidate, "accept", category, accept);
      });
      var discard = document.createElement("button");
      discard.type = "button";
      discard.textContent = "丢弃";
      discard.addEventListener("click", function () {
        reviewStickerCandidate(candidate, "discard", null, discard);
      });
      actions.append(category, accept, discard);
      card.append(image, copy, actions);
      stickerCandidateList.appendChild(card);
    });
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
        stickerLibraries = data.libraries || [];
        stickerRules = data.rules || [];
        stickerRuleGroups = data.groups || [];
        stickerCandidates = data.candidates || [];
        var validIds = {};
        currentStickers.forEach(function (sticker) {
          validIds[String(sticker.id)] = true;
        });
        Object.keys(selectedStickerIds).forEach(function (stickerId) {
          if (!validIds[stickerId]) delete selectedStickerIds[stickerId];
        });
        refreshStickerLibraryControls(selectedStickerLibraryId);
        document.getElementById("agentStickerCount").textContent =
          stickerLibraries.length + " 个图库 · " +
          currentStickers.length + " 张";
        refreshStickerCategoryControls();
        refreshStickerRules();
        renderStickerCandidates();
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
                library_id: selectedStickerLibraryId,
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
    window.location.assign(
      "/api/agent/web/sticker-export?library_id=" +
      encodeURIComponent(selectedStickerLibraryId)
    );
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
          body: JSON.stringify({
            library_id: selectedStickerLibraryId,
            data_base64: data,
          }),
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
  jargonStatusFilter.addEventListener("change", renderGroupJargon);
  jargonList.addEventListener("click", function (event) {
    var button = event.target.closest("[data-jargon-action]");
    if (!button) return;
    var item = button.closest("[data-jargon-id]");
    if (!item) return;
    updateGroupJargon(item, button.dataset.jargonAction);
  });
  document
    .getElementById("agentDiagnosticsRefresh")
    .addEventListener("click", function () {
      loadDiagnostics();
    });
  document
    .getElementById("agentDiagnosticsSearch")
    .addEventListener("click", function () {
      var button = this;
      button.disabled = true;
      diagnosticsSearchResult.textContent = "正在测试搜索接口…";
      loadDiagnostics("search_check").then(function () {
        button.disabled = false;
      });
    });
  document
    .getElementById("agentDiagnosticsCleanup")
    .addEventListener("click", function () {
      var button = this;
      if (button.dataset.confirm !== "1") {
        button.dataset.confirm = "1";
        button.querySelector("span").textContent = "再次点击确认";
        window.setTimeout(function () {
          button.dataset.confirm = "";
          button.querySelector("span").textContent = "清理旧历史";
        }, 4000);
        return;
      }
      button.dataset.confirm = "";
      button.disabled = true;
      diagnosticsSearchResult.textContent = "正在清理旧历史…";
      loadDiagnostics("history_cleanup").then(function () {
        button.disabled = false;
        button.querySelector("span").textContent = "清理旧历史";
      });
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
  stickerLibrarySelect.addEventListener("change", function () {
    changeSelectedStickerLibrary(this.value);
  });
  stickerLibraryEnabled.addEventListener("change", saveStickerLibraryEnabled);
  stickerLibraryAdd.addEventListener("click", function () {
    stickerLibraryCreateForm.hidden = false;
    stickerLibraryCreateName.focus();
  });
  stickerLibraryCreateCancel.addEventListener("click", function () {
    stickerLibraryCreateForm.hidden = true;
    stickerLibraryCreateName.value = "";
  });
  stickerLibraryCreateForm.addEventListener("submit", function (event) {
    event.preventDefault();
    createStickerLibrary();
  });
  stickerLibraryRenameForm.addEventListener("submit", function (event) {
    event.preventDefault();
    renameStickerLibrary();
  });
  stickerAutoCollectLibrary.addEventListener("change", function () {
    stickerAutoCollectLibraryValue = this.value || "default";
  });
  stickerRuleScope.addEventListener("change", refreshStickerRuleKeys);
  stickerRuleKey.addEventListener("change", renderStickerRuleLibraries);
  stickerRuleSave.addEventListener("click", saveStickerRule);
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
  stickerBulkLibraryMove.addEventListener("click", moveSelectedStickersLibrary);
  document
    .getElementById("settingPersonaPreset")
    .addEventListener("change", function () {
      if (!stickerRuleScope || stickerRuleScope.value !== "persona") return;
      refreshStickerRuleKeys();
    });
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
  loadGroupJargon();
  loadDiagnostics();
  loadGroupMembers();
  loadTimeline();
  loadStickers();
  window.setInterval(loadStatus, 30000);
})();
