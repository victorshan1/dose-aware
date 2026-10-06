const stateMeta = {
  scheduled: ["尚未开始", "计划已创建，等待提醒时间。", "neutral", "○"],
  reminding: ["正在提醒", "系统正在等待患者响应或开盒。", "warning", "⌁"],
  acknowledged: ["患者已响应", "已收到响应，等待药格打开。", "safe", "✓"],
  protected: ["安全保护中", "已记录开盒，药格处于安全保护间隔。", "safe", "✓"],
  escalating: ["提醒已升级", "暂未收到响应，提醒强度正在升级。", "warning", "⌁"],
  caregiver_notified: ["照护者已通知", "长时间未响应，照护者已收到异常通知。", "risk", "!"],
  duplicate_risk: ["重复开盒风险", "安全间隔内再次开盒，系统保持锁定并通知照护者。", "risk", "!"],
  emergency_unlocked: ["已应急解锁", "应急开启已记录，需要复核原因。", "warning", "!"],
  offline: ["设备离线", "核心提醒继续在本地运行，联网后补传事件。", "warning", "⌁"],
  syncing: ["正在同步", "网络已恢复，正在补传离线事件。", "neutral", "↻"],
  completed: ["本次流程完成", "安全保护间隔已结束。", "safe", "✓"],
};

const eventLabels = {
  reminder_started: "提醒已启动",
  reminder_escalated: "提醒已升级",
  patient_acknowledged: "患者已响应",
  compartment_opened: "药格已打开",
  caregiver_notified: "照护者已通知",
  activity_resumed: "检测到恢复活动",
  emergency_unlock_requested: "申请应急解锁",
};

const reasonLabels = {
  reminder_started: "进入持续提醒状态",
  reminder_escalated: "未响应，提升提醒等级",
  compartment_opened_and_protected: "记录开盒并进入安全保护期",
  duplicate_open_during_safety_interval: "保护期内再次开盒，识别为风险",
  caregiver_notified: "异常信息已发送给照护者",
  activity_resumed_retrigger_reminder: "小睡后恢复活动，重新触发提醒",
};

let activeSessionId = null;
let countdownTimer = null;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function formatTime(value) {
  if (!value) return "暂无记录";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2600);
}

async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

function renderState(snapshot) {
  const meta = stateMeta[snapshot?.state] || stateMeta.scheduled;
  const panel = $("#status-panel");
  panel.className = `status-panel ${meta[2]}`;
  $("#status-icon").textContent = meta[3];
  $("#state-title").textContent = meta[0];
  $("#state-description").textContent = meta[1];
  $("#last-opened").textContent = formatTime(snapshot?.last_opened_at);
  $("#scheduled-at").textContent = snapshot ? formatTime(snapshot.scheduled_at) : "尚未创建";
  $("#device-id").textContent = snapshot ? `设备 ${snapshot.device_id}` : "设备等待连接";

  const requiresCare = ["duplicate_risk", "caregiver_notified"].includes(snapshot?.state);
  $("#care-state").textContent = requiresCare ? "已触发异常介入" : "无需介入";
  $("#care-detail").textContent = requiresCare ? "照护者已收到必要的安全信息" : "异常时才通知照护者";
  $("#caregiver-state").textContent = snapshot ? meta[0] : "暂无活动会话";
  $("#caregiver-summary").textContent = snapshot ? meta[1] : "系统不会持续监控患者，只同步与服药安全相关的必要事件。";
  startCountdown(snapshot?.protected_until);
}

function startCountdown(until) {
  clearInterval(countdownTimer);
  const wrap = $("#countdown-wrap");
  if (!until) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  const tick = () => {
    const remaining = Math.max(0, new Date(until).getTime() - Date.now());
    const hours = Math.floor(remaining / 3600000);
    const minutes = Math.floor((remaining % 3600000) / 60000);
    const seconds = Math.floor((remaining % 60000) / 1000);
    $("#countdown").textContent = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  };
  tick();
  countdownTimer = setInterval(tick, 1000);
}

function renderAudit(items) {
  $("#audit-count").textContent = `${items.length} 条记录`;
  const timeline = $("#timeline");
  if (!items.length) {
    timeline.innerHTML = '<li class="empty">运行演示后，这里会显示每次状态变化和原因。</li>';
    return;
  }
  timeline.innerHTML = items.map((item) => `
    <li>
      <strong>${eventLabels[item.event_type] || item.event_type} · ${item.from_state} → ${item.to_state}</strong>
      <span>${reasonLabels[item.reason] || item.reason} · ${formatTime(item.occurred_at)}</span>
    </li>
  `).join("");
}

function renderNotifications(items) {
  const pending = items.filter((item) => !item.acknowledged);
  $("#notification-count").textContent = `${pending.length} 条未确认`;
  const list = $("#notifications");
  if (!items.length) {
    list.innerHTML = '<li class="empty">当前没有需要处理的异常。</li>';
    return;
  }
  list.innerHTML = [...items].reverse().map((item) => `
    <li class="${item.acknowledged ? "acknowledged" : ""}">
      <strong>${item.reason === "duplicate_open_risk" ? "重复开盒风险" : "患者长时间未响应"}</strong>
      <span>${formatTime(item.created_at)} · ${item.acknowledged ? "已确认" : "待确认"}</span>
    </li>
  `).join("");
}

function renderSessions(items) {
  $("#session-count").textContent = `${items.length} 个`;
  const list = $("#session-list");
  if (!items.length) {
    list.innerHTML = '<li class="empty">尚未创建服药会话。</li>';
    return;
  }
  list.innerHTML = items.slice(0, 8).map((item) => `
    <li data-session-id="${item.session_id}">
      <strong>${stateMeta[item.state]?.[0] || item.state}</strong>
      <span>${formatTime(item.scheduled_at)} · ${item.compartment_id}</span>
    </li>
  `).join("");
}

async function refresh() {
  try {
    const health = await request("/health");
    $("#connection").className = "connection online";
    $("#connection").innerHTML = `<i></i>${health.status === "ok" ? "系统在线" : "状态异常"}`;
    const [sessions, notifications] = await Promise.all([
      request("/sessions"),
      request("/notifications"),
    ]);
    renderSessions(sessions);
    renderNotifications(notifications);
    if (!activeSessionId && sessions.length) activeSessionId = sessions[0].session_id;
    if (activeSessionId) {
      const [snapshot, audit] = await Promise.all([
        request(`/sessions/${activeSessionId}`),
        request(`/sessions/${activeSessionId}/audit`),
      ]);
      renderState(snapshot);
      renderAudit(audit);
    } else {
      renderState(null);
      renderAudit([]);
    }
  } catch (error) {
    $("#connection").className = "connection error";
    $("#connection").innerHTML = "<i></i>连接失败";
    showToast(error.message);
  }
}

async function runScenario(name, button) {
  $$(".scenario").forEach((item) => { item.disabled = true; });
  $("#scenario-status").textContent = "正在运行…";
  try {
    const result = await request(`/demo/scenarios/${name}`, { method: "POST" });
    activeSessionId = result.session_id;
    $("#scenario-status").textContent = "运行完成";
    showToast("场景已执行，状态来自真实后端状态机");
    await refresh();
  } catch (error) {
    $("#scenario-status").textContent = "运行失败";
    showToast(error.message);
  } finally {
    $$(".scenario").forEach((item) => { item.disabled = false; });
    button.blur();
  }
}

$$('[data-view]').forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((item) => item.classList.toggle("active", item === tab));
    $$(".view").forEach((view) => view.classList.remove("active"));
    $(`#${tab.dataset.view}-view`).classList.add("active");
  });
});

$$(".scenario").forEach((button) => {
  button.addEventListener("click", () => runScenario(button.dataset.scenario, button));
});

$("#refresh-button").addEventListener("click", refresh);
$("#contact-button").addEventListener("click", () => showToast("演示模式：真实版本将调用用户授权的联系方式"));
$("#privacy-toggle").addEventListener("click", async () => {
  const current = await request("/privacy");
  const next = await request("/privacy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: !current.privacy_mode }),
  });
  $("#privacy-toggle").textContent = next.privacy_mode ? "隐私模式" : "详细模式";
  showToast(next.privacy_mode ? "已开启隐私模式" : "已关闭隐私模式");
});
$("#ack-all-button").addEventListener("click", async () => {
  const notifications = await request("/notifications");
  const pending = notifications.filter((item) => !item.acknowledged);
  await Promise.all(pending.map((item) => request(`/notifications/${item.notification_id}/acknowledge`, { method: "POST" })));
  showToast(pending.length ? "异常通知已确认" : "没有待确认通知");
  await refresh();
});
$("#session-list").addEventListener("click", async (event) => {
  const item = event.target.closest("[data-session-id]");
  if (!item) return;
  activeSessionId = item.dataset.sessionId;
  await refresh();
  $$('.tab').forEach((tab) => tab.classList.toggle("active", tab.dataset.view === "patient"));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === "patient-view"));
});

refresh();
