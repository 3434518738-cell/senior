const form = document.querySelector("#practice-form");
const taskType = document.querySelector("#task-type");
const fileInput = document.querySelector("#question-image");
const essayInput = document.querySelector("#essay");
const wordCount = document.querySelector("#word-count");
const minimumHint = document.querySelector("#minimum-hint");
const fileTitle = document.querySelector("#file-title");
const fileHelp = document.querySelector("#file-help");
const previewWrap = document.querySelector("#image-preview-wrap");
const preview = document.querySelector("#image-preview");
const errorBox = document.querySelector("#form-error");
const submitButton = document.querySelector("#submit-button");
const submitLabel = document.querySelector("#submit-label");
const spinner = document.querySelector("#spinner");
const resultSection = document.querySelector("#result-section");

let imageBase64 = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));
}

function countWords(text) {
  return (text.match(/\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b/g) || []).length;
}

function updateWordCount() {
  const count = countWords(essayInput.value);
  wordCount.textContent = `${count} words`;
  minimumHint.textContent = `${taskType.value === "task1" ? "Task 1" : "Task 2"} 建议至少 ${taskType.value === "task1" ? 150 : 250} 词`;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.toggle("hidden", !message);
}

function setBusy(busy) {
  submitButton.disabled = busy;
  spinner.classList.toggle("hidden", !busy);
  submitLabel.textContent = busy ? "Qwen 正在识别并评分…" : "开始识别并评分";
}

function renderList(items, className = "result-list") {
  if (!items || !items.length) return "<p class=\"muted\">暂无内容</p>";
  return `<ul class="${className}">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderResult(payload, submittedEssay) {
  const recognized = payload.recognized_question;
  const recognitionCard = document.querySelector("#recognition-card");
  recognitionCard.innerHTML = `<h3>Qwen 识别出的题目</h3>
    <div class="recognized-question">${escapeHtml(recognized?.question_text || "题目文字未返回")}</div>
    ${recognized?.uncertain_or_unreadable?.length ? `<div class="uncertain"><strong>需要核对：</strong>${escapeHtml(recognized.uncertain_or_unreadable.join("；"))}</div>` : ""}`;

  const report = payload.report || {};
  const visualCard = document.querySelector("#visual-card");
  if (report.chart_understanding) {
    visualCard.classList.remove("hidden");
    visualCard.innerHTML = `<h3>Task 1 视觉识别结果</h3><pre class="visual-json">${escapeHtml(JSON.stringify(report.chart_understanding, null, 2))}</pre>`;
  } else visualCard.classList.add("hidden");

  const warnings = report.warnings || [];
  const warningsCard = document.querySelector("#warnings-card");
  if (warnings.length) {
    warningsCard.classList.remove("hidden");
    warningsCard.innerHTML = `<h3>提交与识别提示</h3>${renderList(warnings, "result-list warning-list")}`;
  } else warningsCard.classList.add("hidden");

  const oldReview = document.querySelector("#essay-review");
  const review = oldReview.cloneNode(false);
  oldReview.replaceWith(review);
  WritingFeedback.mount(review, { essay: submittedEssay, report });
  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.querySelectorAll(".task-button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".task-button").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  taskType.value = button.dataset.task;
  updateWordCount();
}));

essayInput.addEventListener("input", updateWordCount);

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) return showError("请选择 PNG、JPEG、GIF 或 WebP 图片。");
  if (file.size > 10 * 1024 * 1024) return showError("图片不能超过 10 MB。");
  showError("");
  fileTitle.textContent = file.name;
  fileHelp.textContent = `${Math.round(file.size / 1024)} KB · 已准备识别`;
  const reader = new FileReader();
  reader.onload = () => {
    imageBase64 = String(reader.result).split(",")[1];
    preview.src = String(reader.result);
    previewWrap.classList.remove("hidden");
  };
  reader.readAsDataURL(file);
});

document.querySelector("#clear-image").addEventListener("click", () => {
  fileInput.value = "";
  imageBase64 = null;
  previewWrap.classList.add("hidden");
  fileTitle.textContent = "点击选择题目照片";
  fileHelp.textContent = "支持 PNG、JPEG、GIF、WebP，单张不超过 10 MB";
});

document.querySelector("#new-practice").addEventListener("click", () => {
  resultSection.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  if (!imageBase64) return showError("请先上传题目照片。");
  if (!essayInput.value.trim()) return showError("请先输入作文。");
  setBusy(true);
  const submittedEssay = essayInput.value.trim();
  try {
    const body = {
      mode: "upload",
      task_type: taskType.value,
      essay: submittedEssay,
      question_image_base64: imageBase64,
    };
    const response = await fetch("/api/v1/practice/score", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "评分服务返回错误");
    renderResult(payload, submittedEssay);
  } catch (error) {
    showError(error instanceof Error ? error.message : "提交失败，请检查本地服务是否运行。");
  } finally {
    setBusy(false);
  }
});

updateWordCount();
