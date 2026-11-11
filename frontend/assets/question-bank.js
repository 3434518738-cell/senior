/* Categories mirror the reviewed corpus metadata, not model-generated labels. */
(function (root) {
  "use strict";
  const types = {
    task1: {
      line_graph: "折线图", bar_chart: "柱状图", pie_chart: "饼图", table: "表格",
      process_diagram: "流程图", map: "地图", mixed_chart: "混合图表",
    },
    task2: {
      opinion: "观点立场题", discuss_both_views: "双边讨论题",
      advantages_disadvantages_opinion: "利弊权衡题", problems_and_solutions: "问题与解决",
      two_part_question: "双问题题", causes_and_opinion: "原因与观点",
      multi_part_problem_solution: "多方解决方案", positive_negative_development: "正负发展题",
    },
  };
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
  function typeOf(question) {
    const key = question.task_type === "task1" ? question.chart_type || question.question_type : question.question_type;
    return Object.hasOwn(types[question.task_type] || {}, key) ? key : "other";
  }
  function label(question) { return types[question.task_type]?.[typeOf(question)] || "其他题型"; }
  function categories(questions, task) {
    const counts = new Map();
    questions.filter((q) => q.task_type === task).forEach((q) => counts.set(typeOf(q), (counts.get(typeOf(q)) || 0) + 1));
    return [...Object.keys(types[task] || {}), "other"].filter((key) => counts.has(key)).map((key) => ({
      key, label: types[task]?.[key] || "其他题型", count: counts.get(key),
    }));
  }
  function filter(questions, task, category = "all", query = "") {
    const search = query.trim().toLocaleLowerCase();
    return questions.filter((q) => q.task_type === task && (category === "all" || typeOf(q) === category)
      && (!search || [q.title, q.question, q.topic, label(q)].join(" ").toLocaleLowerCase().includes(search)));
  }

  function mount(container, { questions, selected, onSelect }) {
    let task = "task1", category = "all", previewId = null;
    container.innerHTML = `<div class="bank-heading"><div><p class="eyebrow">CHOOSE YOUR PRACTICE</p><h2>按题型，找到今天的练习</h2><p class="muted">来自已上传范文资料。先选题，再开始计时；提交后再学习参考范文。</p></div><span class="bank-total">${questions.length} 道可练题目</span></div>
      <div class="bank-controls"><div class="bank-task-switch" aria-label="选择任务类型"><button type="button" data-bank-task="task1" aria-pressed="true" class="active">Task 1 <span>${filter(questions, "task1").length} 题</span></button><button type="button" data-bank-task="task2" aria-pressed="false">Task 2 <span>${filter(questions, "task2").length} 题</span></button></div><label class="bank-search-label"><span>搜索题目</span><input type="search" class="bank-search" placeholder="搜索标题、题目或主题" autocomplete="off" /></label></div>
      <div class="bank-categories" aria-label="题型分类"></div><p class="bank-result-count muted" role="status"></p>
      <div class="bank-browser"><div class="bank-question-list" aria-label="可选题目"></div><article class="bank-question-detail" aria-label="题目预览"></article></div>`;
    const list = container.querySelector(".bank-question-list");
    const detail = container.querySelector(".bank-question-detail");
    const search = container.querySelector(".bank-search");
    function renderCategories() {
      const all = { key: "all", label: "全部题型", count: filter(questions, task).length };
      container.querySelector(".bank-categories").innerHTML = [all, ...categories(questions, task)].map((item) => `<button type="button" class="bank-category${category === item.key ? " active" : ""}" data-category="${item.key}" aria-pressed="${category === item.key}">${item.label}<span>${item.count}</span></button>`).join("");
    }
    function renderDetail(question) {
      if (!question) {
        detail.innerHTML = '<div class="bank-empty"><h3>试试其他题型或关键词</h3><p>当前筛选没有匹配题目，你已经选好的题目会保留。</p><button type="button" class="secondary-button bank-clear">清除筛选</button></div>';
        return;
      }
      const chosen = selected[task]?.question_id === question.question_id;
      detail.innerHTML = `<div class="bank-preview-meta"><span class="bank-type-label">${label(question)}</span><span>${question.source_pages?.length ? `资料第 ${question.source_pages.map(escape).join("、")} 页` : "来自上传资料"}</span></div><h3>${escape(question.title)}</h3><p class="bank-full-question">${escape(question.question)}</p>
        ${question.chart_image_url ? `<figure class="bank-preview-image"><img src="${escape(question.chart_image_url)}" alt="${escape(question.title)} 的原始题图" data-zoomable tabindex="0" role="button" aria-label="放大题库预览图" /><figcaption>点击查看大图 ↗</figcaption></figure>` : ""}
        <div class="bank-detail-footer"><span>建议 ${task === "task1" ? "20" : "40"} 分钟 · 至少 ${task === "task1" ? "150" : "250"} 词</span><button type="button" class="primary-button bank-confirm" ${chosen ? "disabled" : ""}>${chosen ? `✓ 已选为 ${task === "task1" ? "Task 1" : "Task 2"}` : `选为 ${task === "task1" ? "Task 1" : "Task 2"} 题目`}</button></div>`;
    }
    function renderResults() {
      const items = filter(questions, task, category, search.value);
      const preview = items.find((q) => q.question_id === previewId) || items.find((q) => q.question_id === selected[task]?.question_id) || items[0];
      previewId = preview?.question_id ?? null;
      container.querySelector(".bank-result-count").textContent = `找到 ${items.length} 道题目 · ${task === "task1" ? "先看原图，再确认题目" : "完整阅读题干，再确认题目"}`;
      list.innerHTML = items.length ? items.map((q) => `<button type="button" class="bank-question${q.question_id === previewId ? " is-preview" : ""}${selected[task]?.question_id === q.question_id ? " is-chosen" : ""}" data-question-id="${escape(q.question_id)}" aria-pressed="${q.question_id === previewId}"><span class="bank-question-top"><span>${label(q)}</span>${selected[task]?.question_id === q.question_id ? '<span class="chosen-label">✓ 已选</span>' : '<span aria-hidden="true">↗</span>'}</span><strong>${escape(q.title)}</strong><span class="bank-question-excerpt">${escape(q.question)}</span></button>`).join("") : '<p class="bank-list-empty">没有匹配的题目</p>';
      renderDetail(preview);
    }
    search.addEventListener("input", renderResults);
    container.addEventListener("click", (event) => {
      const taskButton = event.target.closest("[data-bank-task]");
      if (taskButton) {
        task = taskButton.dataset.bankTask; category = "all"; search.value = ""; previewId = selected[task]?.question_id ?? null;
        container.querySelectorAll("[data-bank-task]").forEach((button) => {
          button.classList.toggle("active", button === taskButton);
          button.setAttribute("aria-pressed", String(button === taskButton));
        });
        renderCategories(); renderResults(); return;
      }
      const categoryButton = event.target.closest("[data-category]");
      if (categoryButton) {
        category = categoryButton.dataset.category; previewId = null;
        renderCategories(); renderResults();
        container.querySelector(`[data-category="${category}"]`)?.focus({ preventScroll: true }); return;
      }
      const questionButton = event.target.closest("[data-question-id]");
      if (questionButton) {
        previewId = questionButton.dataset.questionId; renderResults();
        list.querySelector(`[data-question-id="${previewId}"]`)?.focus({ preventScroll: true }); return;
      }
      if (event.target.closest(".bank-confirm")) {
        const question = questions.find((q) => q.question_id === previewId);
        if (question) { onSelect(question); renderResults(); }
      }
      if (event.target.closest(".bank-clear")) {
        category = "all"; search.value = ""; renderCategories(); renderResults(); search.focus();
      }
    });
    renderCategories(); renderResults();
    return { update: renderResults };
  }
  const api = { typeOf, label, categories, filter, mount };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WritingQuestionBank = api;
})(typeof window !== "undefined" ? window : globalThis);
