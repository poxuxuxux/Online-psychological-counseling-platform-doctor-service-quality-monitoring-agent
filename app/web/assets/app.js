const state = { session: null, running: false };

const metricNames = {
  D1: "专业信息采集",
  D2: "响应与咨询节奏",
  D3: "方案与专业支持",
  D4: "共情与关系建立",
  D5: "流程说明与跟进",
  "D6.1": "安全关注与回应",
  "D6.2": "专业边界与风险"
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  window.setTimeout(() => { toast.className = "toast"; }, 3200);
}

function formatTime(value) {
  if (!value) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    .format(new Date(value));
}

function renderConversation(session) {
  $("#session-id").textContent = session.session_id;
  $("#message-count").textContent = session.messages.length;
  $("#conversation-list").innerHTML = session.messages.map((message) => {
    const isDoctor = message.role === "doctor";
    return `<article class="message ${isDoctor ? "doctor" : "patient"}" id="${escapeHtml(message.message_id)}">
      <div class="message-avatar">${isDoctor ? "医生" : "咨询者"}</div>
      <div class="bubble-wrap">
        <div class="message-meta">${isDoctor ? "咨询医生" : "匿名咨询者"} · ${formatTime(message.timestamp)}</div>
        <div class="bubble">${escapeHtml(message.content)}</div>
      </div>
    </article>`;
  }).join("");
}

function setWorkflow(step, final = false) {
  document.querySelectorAll(".step").forEach((element, index) => {
    element.classList.toggle("done", final || index + 1 < step);
    element.classList.toggle("active", !final && index + 1 === step);
  });
}

function focusEvidence(messageId) {
  const target = document.getElementById(messageId);
  if (!target) return;
  document.querySelectorAll(".message.highlight").forEach((item) => item.classList.remove("highlight"));
  target.classList.add("highlight");
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => target.classList.remove("highlight"), 2600);
}

function renderReport(report) {
  const findings = report.agent_results.flatMap((result) => result.findings || []);
  const scored = findings.filter((finding) => typeof finding.score === "number");
  const average = scored.length
    ? scored.reduce((sum, finding) => sum + finding.score, 0) / scored.length
    : null;

  $("#metric-count").textContent = findings.length;
  $("#overall-score").textContent = average === null ? "需复核" : average.toFixed(1);
  $("#score-note").textContent = average === null ? "暂无有效分数" : `满分 5.0 · ${scored.length} 项计分`;
  $("#report-summary").textContent = report.summary;
  $("#empty-report").hidden = true;
  $("#report-content").hidden = false;
  $("#report-badge").className = "status success";
  $("#report-badge").textContent = "已生成 · 待复核";

  $("#dimension-list").innerHTML = findings.map((finding) => {
    const evidence = finding.evidence?.[0];
    const score = typeof finding.score === "number"
      ? `<span class="score">${finding.score.toFixed(1)} <small>/ 5.0</small></span>`
      : `<span class="na-label">不适用</span>`;
    const evidenceButton = evidence
      ? `<button class="evidence-button" type="button" data-message-id="${escapeHtml(evidence.message_ids[0])}">↳ 证据：${escapeHtml(evidence.quote)}</button>`
      : `<div class="evidence-button">本项由指标适用性规则判断，不以 Hook 是否命中为依据。</div>`;
    return `<article class="finding">
      <div class="finding-head"><span class="metric-code">${escapeHtml(finding.metric_id)}</span><span class="metric-name">${escapeHtml(metricNames[finding.metric_id] || "质量指标")}</span>${score}</div>
      <p>${escapeHtml(finding.rationale)}</p>${evidenceButton}
    </article>`;
  }).join("");

  document.querySelectorAll("[data-message-id]").forEach((button) => {
    button.addEventListener("click", () => focusEvidence(button.dataset.messageId));
  });
}

async function loadDemo() {
  try {
    const response = await fetch("/api/v1/demo/session");
    if (!response.ok) throw new Error(`加载失败（${response.status}）`);
    state.session = await response.json();
    renderConversation(state.session);
    $("#run-button").disabled = false;
  } catch (error) {
    $("#conversation-list").innerHTML = `<div class="empty-state"><p>${escapeHtml(error.message)}</p></div>`;
    showToast("示例会话加载失败，请刷新页面重试。", true);
  }
}

async function runEvaluation() {
  if (!state.session || state.running) return;
  state.running = true;
  const button = $("#run-button");
  const status = $("#run-status");
  button.disabled = true;
  $(".button-label").textContent = "正在评估…";
  status.className = "status running";
  status.textContent = "运行中";

  try {
    setWorkflow(1);
    await new Promise((resolve) => setTimeout(resolve, 380));
    setWorkflow(2);
    const responsePromise = fetch("/api/v1/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.session)
    });
    await new Promise((resolve) => setTimeout(resolve, 520));
    setWorkflow(3);
    const response = await responsePromise;
    if (!response.ok) throw new Error(`评估请求失败（${response.status}）`);
    const report = await response.json();
    await new Promise((resolve) => setTimeout(resolve, 420));
    setWorkflow(4);
    renderReport(report);
    setWorkflow(4, true);
    status.className = "status success";
    status.textContent = "本次运行完成";
    showToast("评估报告已生成，可点击证据回看原始消息。")
  } catch (error) {
    status.className = "status neutral";
    status.textContent = "运行失败";
    showToast(error.message || "评估失败，请稍后重试。", true);
  } finally {
    state.running = false;
    button.disabled = false;
    $(".button-label").textContent = "重新运行评估";
  }
}

$("#run-button").addEventListener("click", runEvaluation);
loadDemo();
