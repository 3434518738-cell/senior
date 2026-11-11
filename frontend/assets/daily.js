const startButton = document.querySelector("#start-button");
const chooseButton = document.querySelector("#choose-button");
const pickerRoot = document.querySelector("#question-picker");
const selectedRoot = document.querySelector("#selected-questions");
const pickerStart = document.querySelector("#picker-start-button");
const pickerRail = document.querySelector("#picker-start-rail");
const timer = document.querySelector("#timer");
const statusText = document.querySelector("#session-status");
const errorBox = document.querySelector("#daily-error");
const itemsRoot = document.querySelector("#daily-items");

let session = null;
let timerHandle = null;
let expired = false;
const selectedQuestions = { task1: null, task2: null };
let bankPicker = null;

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
  itemsRoot.querySelectorAll("textarea, .submit-daily").forEach((element) => { element.disabled = true; });
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
  statusText.textContent = "已按你的选题开始练习 · 题目已固定";
  chooseButton.disabled = true;
  chooseButton.textContent = "选题已确认";
  chooseButton.setAttribute("aria-expanded", "false");
  selectedRoot.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  pickerRoot.classList.add("hidden");
  pickerRail.classList.add("hidden");
  itemsRoot.classList.remove("hidden");
  itemsRoot.innerHTML = session.items.map((item) => `
    <article class="card daily-item" data-order="${item.item_order}">
      <div class="daily-item-heading">
        <div><p class="eyebrow">${escapeHtml(item.task_type === "task1" ? "TASK 1" : "TASK 2")}</p><h2>${escapeHtml(item.title)}</h2></div>
        <span class="word-target">至少 ${item.task_type === "task1" ? 150 : 250} 词</span>
      </div>
      <div class="daily-writing-layout"><section class="question-panel" aria-label="练习题目"><p class="daily-question">${escapeHtml(item.question)}</p>
      ${item.task_type === "task1" && item.chart_image_url ? `
        <figure class="daily-chart-figure">
          <img class="daily-chart-image" src="${escapeHtml(item.chart_image_url)}" alt="Academic Task 1 图表：${escapeHtml(item.title)}" loading="lazy" data-zoomable tabindex="0" role="button" aria-label="放大练习题图" />
          <figcaption>点击题图放大查看 ↗ · ${escapeHtml(WritingQuestionBank.label(item))}</figcaption>
        </figure>
      ` : item.task_type === "task1" ? `
        <p class="daily-chart-missing" role="note">这道题暂缺原始图表，当前不会从每日一练中抽取。</p>
      ` : ""}
      </section><section class="writing-panel" aria-label="作文输入"><label class="field-label" for="essay-${item.item_order}">你的作文</label>
      <textarea id="essay-${item.item_order}" rows="14" placeholder="在这里完成 ${item.task_type === "task1" ? "Task 1" : "Task 2"} 作文……" ${item.essay || expired ? "disabled" : ""}>${escapeHtml(item.essay || "")}</textarea>
      <div class="form-meta"><span class="daily-word-count">${item.essay ? countWords(item.essay) : 0} words</span><button class="primary-button compact submit-daily" type="button" ${item.essay || expired ? "disabled" : ""}>${item.essay ? "已提交" : "提交并评分"}</button></div>
      </section></div><div class="daily-result ${item.report ? "" : "hidden"}"></div>
    </article>
  `).join("");
  itemsRoot.querySelectorAll("textarea").forEach((input) => input.addEventListener("input", () => {
    input.closest(".daily-item").querySelector(".daily-word-count").textContent = `${countWords(input.value)} words`;
  }));
  itemsRoot.querySelectorAll(".submit-daily").forEach((button) => button.addEventListener("click", () => submitItem(button)));
  session.items.forEach((item) => {
    if (item.report) mountDailyReport(itemsRoot.querySelector(`[data-order="${item.item_order}"] .daily-result`), item.essay || "", item.report, item.report.improvement_plan);
  });
  updateTimer();
}

function mountDailyReport(container, essay, report, plan) {
  container.innerHTML = '<section class="essay-review" aria-label="作文逐句反馈"></section><div class="daily-learning"></div>';
  WritingFeedback.mount(container.querySelector(".essay-review"), { essay, report });
  container.querySelector(".daily-learning").innerHTML = renderReport(report, plan);
}

function renderReport(report, learningPlan = report.improvement_plan) {
  const plan = learningPlan;
  const lessons = (plan?.sample_lessons || []).map((item) => `<div class="sample"><strong>${escapeHtml(item.sample_id)} · 范文写法</strong><p class="sample-excerpt">“${escapeHtml(item.sample_quote)}”</p><p>${escapeHtml(item.lesson)}</p><p class="muted">迁移方法：${escapeHtml(item.how_to_apply)}</p></div>`).join("");
  const actions = (plan?.actions || []).map((item) => `<li><strong>${escapeHtml(WritingFeedback.criterionLabel(item.criterion))}：</strong>${escapeHtml(item.problem)}<br>${escapeHtml(item.action)}</li>`).join("");
  const improvement = plan ? `<section class="daily-improvement"><h3>范文驱动的改进计划</h3><p>${escapeHtml(plan.summary)}</p>${actions ? `<ul class="result-list">${actions}</ul>` : ""}${lessons}</section>` : "";
  return `<p class="muted">${escapeHtml((report.warnings || []).join("；"))}</p>${improvement}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "请求失败");
  return payload;
}

async function startSession() {
  if (session || !selectedQuestions.task1 || !selectedQuestions.task2) return;
  showError("");
  startButton.disabled = true;
  pickerStart.disabled = true;
  chooseButton.disabled = true;
  pickerRoot.inert = true;
  selectedRoot.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  try {
    session = await requestJson("/api/v1/practice/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "daily", duration_seconds: 3600, question_ids: [selectedQuestions.task1.question_id, selectedQuestions.task2.question_id] }) });
    renderSession();
    timerHandle = setInterval(updateTimer, 1000);
    startButton.classList.add("hidden");
    itemsRoot.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    syncSelection();
    chooseButton.disabled = false;
    showError(error instanceof Error ? error.message : "无法开始每日一练");
  } finally {
    pickerRoot.inert = false;
  }
}

function syncSelection() {
  const count = Object.values(selectedQuestions).filter(Boolean).length;
  startButton.disabled = count !== 2;
  pickerStart.disabled = count !== 2;
  startButton.textContent = count === 2 ? "开始今日练习" : "选好两题，开始练习";
  statusText.textContent = count === 2 ? "两道题已选好，开始后进入 60 分钟计时" : `已选 ${count}/2 道题 · 请选择 Task 1 和 Task 2 各一道`;
  document.querySelector("#picker-selection-status").textContent = count === 2 ? "准备好了，就开始今天的写作" : `已选 ${count}/2 道题`;
  selectedRoot.innerHTML = ["task1", "task2"].map((task) => `<div class="selected-question${selectedQuestions[task] ? " has-selection" : ""}"><span>${task === "task1" ? "Task 1" : "Task 2"}</span><strong>${escapeHtml(selectedQuestions[task]?.title || "尚未选择题目")}</strong>${selectedQuestions[task] ? `<button type="button" class="icon-button" data-clear-task="${task}" aria-label="清除 ${task === "task1" ? "Task 1" : "Task 2"} 选题">×</button>` : ""}</div>`).join("");
}

async function loadQuestionBank() {
  chooseButton.disabled = true;
  try {
    const questions = [];
    for (let offset = 0; ; offset += 100) {
      const page = await requestJson(`/api/v1/question-bank?limit=100&offset=${offset}`);
      questions.push(...page.items);
      if (page.items.length < 100) break;
    }
    bankPicker = WritingQuestionBank.mount(pickerRoot, { questions, selected: selectedQuestions, onSelect: (question) => {
      selectedQuestions[question.task_type] = question;
      syncSelection();
    } });
    chooseButton.disabled = false;
    syncSelection();
  } catch (error) {
    statusText.textContent = "题库加载失败，请重试";
    showError(error instanceof Error ? error.message : "题库加载失败");
    pickerRoot.innerHTML = '<p class="muted">暂时无法加载题库。</p><button class="secondary-button retry-bank" type="button">重新加载题库</button>';
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
    mountDailyReport(card.querySelector(".daily-result"), essay, result.result.report, result.result.improvement_plan);
    card.querySelector(".daily-result").classList.remove("hidden");
    statusText.textContent = session.status === "submitted" ? "今日两篇作文都已提交" : "一篇作文已提交，可以继续完成另一篇";
  } catch (error) {
    button.disabled = expired;
    button.textContent = "提交并评分";
    showError(error instanceof Error ? error.message : "评分失败");
  }
}

startButton.addEventListener("click", startSession);
pickerStart.addEventListener("click", startSession);
chooseButton.addEventListener("click", () => {
  const open = pickerRoot.classList.toggle("hidden") === false;
  pickerRail.classList.toggle("hidden", !open);
  chooseButton.setAttribute("aria-expanded", String(open));
  if (open) pickerRoot.scrollIntoView({ behavior: "smooth", block: "start" });
});
selectedRoot.addEventListener("click", (event) => {
  const button = event.target.closest("[data-clear-task]");
  if (!button || session) return;
  selectedQuestions[button.dataset.clearTask] = null;
  syncSelection(); bankPicker?.update();
});
pickerRoot.addEventListener("click", (event) => {
  if (event.target.closest(".retry-bank")) { showError(""); loadQuestionBank(); }
});
loadQuestionBank();
