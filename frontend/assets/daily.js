const startButton = document.querySelector("#start-button");
const refreshButton = document.querySelector("#refresh-button");
const timer = document.querySelector("#timer");
const statusText = document.querySelector("#session-status");
const errorBox = document.querySelector("#daily-error");
const itemsRoot = document.querySelector("#daily-items");

let session = null;
let timerHandle = null;
let expired = false;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));
}

function countWords(text) {
  return (text.match(/\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b/g) || []).length;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.toggle("hidden", !message);
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function setExpired() {
  expired = true;
  timer.classList.add("timer-expired");
  timer.textContent = "00:00";
  statusText.textContent = "时间已到，不能继续提交新的作文";
  itemsRoot.querySelectorAll("textarea, button").forEach((element) => { element.disabled = true; });
}

function updateTimer() {
  if (!session?.duration_seconds) return;
  const started = Date.parse(session.started_at);
  const remaining = Math.max(0, Math.ceil((started + session.duration_seconds * 1000 - Date.now()) / 1000));
  timer.textContent = formatTime(remaining);
  if (remaining === 0) {
    clearInterval(timerHandle);
    setExpired();
  }
}

function renderSession() {
  const refreshLeft = Math.max(0, session.refresh_limit - session.refresh_count);
  statusText.textContent = `今日练习 · 已刷新 ${session.refresh_count}/${session.refresh_limit} 次`;
  refreshButton.classList.remove("hidden");
  refreshButton.textContent = `刷新题目（还可 ${refreshLeft} 次）`;
  refreshButton.disabled = refreshLeft === 0 || session.items.some((item) => item.essay);
  itemsRoot.classList.remove("hidden");
  itemsRoot.innerHTML = session.items.map((item) => `
    <article class="card daily-item" data-order="${item.item_order}">
      <div class="daily-item-heading">
        <div><p class="eyebrow">${escapeHtml(item.task_type === "task1" ? "TASK 1" : "TASK 2")}</p><h2>${escapeHtml(item.title)}</h2></div>
        <span class="word-target">至少 ${item.task_type === "task1" ? 150 : 250} 词</span>
      </div>
      <p class="daily-question">${escapeHtml(item.question)}</p>
      <label class="field-label" for="essay-${item.item_order}">你的作文</label>
      <textarea id="essay-${item.item_order}" rows="14" placeholder="在这里完成 ${item.task_type === "task1" ? "Task 1" : "Task 2"} 作文……" ${item.essay || expired ? "disabled" : ""}>${escapeHtml(item.essay || "")}</textarea>
      <div class="form-meta"><span class="daily-word-count">${item.essay ? countWords(item.essay) : 0} words</span><button class="primary-button compact submit-daily" type="button" ${item.essay || expired ? "disabled" : ""}>${item.essay ? "已提交" : "提交并评分"}</button></div>
      <div class="daily-result ${item.report ? "" : "hidden"}">${item.report ? renderReport(item.report) : ""}</div>
    </article>
  `).join("");
  itemsRoot.querySelectorAll("textarea").forEach((input) => input.addEventListener("input", () => {
    input.closest(".daily-item").querySelector(".daily-word-count").textContent = `${countWords(input.value)} words`;
  }));
  itemsRoot.querySelectorAll(".submit-daily").forEach((button) => button.addEventListener("click", () => submitItem(button)));
  updateTimer();
}

function renderReport(report) {
  const band = report.essay_band_estimate == null ? "—" : report.essay_band_estimate;
  const criteria = (report.criterion_results || []).map((item) => `${escapeHtml(item.criterion)} ${escapeHtml(item.band)}`).join(" · ");
  return `<div class="daily-score"><strong>估分 ${escapeHtml(band)}</strong><span>${criteria}</span></div><p class="muted">${escapeHtml((report.warnings || []).join("；"))}</p>`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "请求失败");
  return payload;
}

async function startSession() {
  showError("");
  startButton.disabled = true;
  try {
    session = await requestJson("/api/v1/practice/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "daily", duration_seconds: 3600 }) });
    renderSession();
    timerHandle = setInterval(updateTimer, 1000);
    startButton.classList.add("hidden");
  } catch (error) {
    startButton.disabled = false;
    showError(error instanceof Error ? error.message : "无法开始每日一练");
  }
}

async function refreshSession() {
  if (!session || refreshButton.disabled) return;
  showError("");
  refreshButton.disabled = true;
  try {
    session = await requestJson(`/api/v1/practice/sessions/${session.session_id}/refresh`, { method: "POST" });
    expired = false;
    timer.classList.remove("timer-expired");
    renderSession();
  } catch (error) {
    showError(error instanceof Error ? error.message : "刷新失败");
    refreshButton.disabled = false;
  }
}

async function submitItem(button) {
  if (!session || expired) return;
  const card = button.closest(".daily-item");
  const itemOrder = Number(card.dataset.order);
  const essay = card.querySelector("textarea").value.trim();
  if (!essay) return showError("请先完成作文再提交。");
  button.disabled = true;
  button.textContent = "Qwen 评分中…";
  try {
    const result = await requestJson(`/api/v1/practice/sessions/${session.session_id}/submit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_order: itemOrder, essay }) });
    session = result.session;
    card.querySelector("textarea").disabled = true;
    button.textContent = "已提交";
    card.querySelector(".daily-result").innerHTML = renderReport(result.result.report);
    card.querySelector(".daily-result").classList.remove("hidden");
    refreshButton.disabled = true;
    statusText.textContent = session.status === "submitted" ? "今日两篇作文都已提交" : "一篇作文已提交，可以继续完成另一篇";
  } catch (error) {
    button.disabled = false;
    button.textContent = "提交并评分";
    showError(error instanceof Error ? error.message : "评分失败");
  }
}

startButton.addEventListener("click", startSession);
refreshButton.addEventListener("click", refreshSession);
