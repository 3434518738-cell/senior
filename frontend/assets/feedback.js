/* Shared essay review. Only verified quotations can anchor a sentence. */
(function (root) {
  "use strict";
  const directions = {
    accuracy: { label: "语法与准确性", short: "语法", symbol: "!" },
    structure: { label: "内容与结构", short: "结构", symbol: "↔" },
    expression: { label: "用词与表达", short: "表达", symbol: "Aa" },
  };
  const names = {
    task_achievement: "任务完成度", task_response: "任务回应",
    coherence_and_cohesion: "连贯与衔接", lexical_resource: "词汇运用",
    grammatical_range_and_accuracy: "语法多样性与准确性",
  };
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
  const direction = (criterion) => criterion === "grammatical_range_and_accuracy" ? "accuracy"
    : criterion === "lexical_resource" ? "expression" : "structure";

  function splitSentences(text) {
    // Paragraphs are kept intact in the rendered document, including blank lines.
    const parts = [];
    const segmenter = typeof Intl.Segmenter === "function"
      ? new Intl.Segmenter("en", { granularity: "sentence" }) : null;
    const lines = text.matchAll(/[^\r\n]+|\r\n|[\r\n]/g);
    for (const line of lines) {
      if (/^[\r\n]+$/.test(line[0])) {
        parts.push({ text: line[0], start: line.index, end: line.index + line[0].length });
        continue;
      }
      const segments = segmenter ? [...segmenter.segment(line[0])].map((s) => ({ text: s.segment, index: s.index }))
        : [...line[0].matchAll(/[^.!?]+(?:[.!?]+["'’”)]*\s*|$)|[.!?]+\s*/g)].map((s) => ({ text: s[0], index: s.index }));
      for (const segment of segments) {
        parts.push({ text: segment.text, start: line.index + segment.index, end: line.index + segment.index + segment.text.length });
      }
    }
    return parts;
  }

  function quoteRanges(text, quote) {
    if (typeof quote !== "string" || !quote.trim()) return [];
    // The server collapses whitespace before grading. Map that exact text back
    // to the user's original offsets without fuzzy matching or altering words.
    let normalized = "";
    const starts = [], ends = [];
    for (const match of text.matchAll(/\s+|\S/g)) {
      normalized += /^\s/.test(match[0]) ? " " : match[0];
      starts.push(match.index);
      ends.push(match.index + match[0].length);
    }
    const needle = quote.replace(/\s+/g, " ").trim();
    const ranges = [];
    let from = 0, index;
    while ((index = normalized.indexOf(needle, from)) !== -1) {
      ranges.push({ start: starts[index], end: ends[index + needle.length - 1] });
      from = index + needle.length;
    }
    return ranges;
  }

  function buildAnnotations(essay, report) {
    const sentences = splitSentences(essay).map((s, id) => ({ ...s, id, notes: [] }));
    const unlocated = [];
    for (const result of report.criterion_results || []) {
      const observations = [...(result.issues || [])];
      for (const check of result.task_review?.checks || []) {
        if (["missing", "partial"].includes(check.status)
          && !observations.some((item) => item.explanation === check.explanation)) observations.push(check);
      }
      for (const issue of observations) {
        const note = { criterion: result.criterion, direction: direction(result.criterion), quote: issue.quote,
          explanation: issue.explanation, improvements: result.improvements || [] };
        const ranges = quoteRanges(essay, issue.quote);
        let matched = false;
        sentences.forEach((sentence) => {
          if (sentence.text.trim() && ranges.some((range) => range.start < sentence.end && range.end > sentence.start)) {
            sentence.notes.push(note);
            matched = true;
          }
        });
        if (!matched) unlocated.push(note);
      }
    }
    return { sentences, unlocated };
  }

  function renderSummary(report) {
    const band = report.essay_band_estimate == null ? "—" : Number(report.essay_band_estimate).toFixed(1);
    const task = report.task_type === "task1" ? "Task 1" : report.task_type === "task2" ? "Task 2" : "本篇 Task";
    return `<div class="review-score"><div><p class="eyebrow">WRITING REPORT</p><h3>这一次，看见你的进步空间</h3></div>
      <div class="review-band"><strong>${escape(band)}</strong><span>${task} 总估分 / 9</span></div></div>
      <p class="muted">${escape(report.word_count ?? "—")} words · ${report.essay_band_estimate == null ? "本次仅作诊断，不提供可靠总估分" : "基于 Academic 四项评分标准"}</p>
      ${report.overall_feedback ? `<section class="overall-feedback"><h4>模型总评</h4><p>${escape(report.overall_feedback)}</p></section>` : ""}
      <div class="criterion-grid">${(report.criterion_results || []).map((c) => `<div class="criterion"><span class="criterion-name">${escape(names[c.criterion] || c.criterion)}</span><strong class="criterion-band">${escape(c.band)}</strong></div>`).join("")}</div>`;
  }

  function mount(container, { essay, report }) {
    const model = buildAnnotations(essay, report);
    let activeFilter = "all", selected = null, lastTrigger = null;
    const counts = Object.fromEntries(Object.keys(directions).map((key) => [key,
      model.sentences.filter((s) => s.notes.some((n) => n.direction === key)).length]));
    const marked = model.sentences.filter((s) => s.notes.length);
    container.innerHTML = `<div class="review-summary">${renderSummary(report)}</div>
      <div class="review-toolbar"><div><h3>逐句修改，让每次练习都有收获</h3><p class="muted">点击彩色句子，在右侧查看反馈。颜色区分修改方向，不代表分数或严重程度。</p></div>
        <button type="button" class="secondary-button general-feedback">全文建议</button></div>
      <div class="review-filters" aria-label="修改方向筛选"><button type="button" class="filter-chip active" data-filter="all" aria-pressed="true">全部 <span>${marked.length}</span></button>
      ${Object.entries(directions).map(([key, value]) => `<button type="button" class="filter-chip ${key}" data-filter="${key}" aria-pressed="false"><span class="direction-dot"></span>${value.label} <span>${counts[key]}</span></button>`).join("")}</div>
      ${marked.length ? "" : `<p class="review-notice">本次反馈没有可定位到原文的引句。你仍可在「全文建议」中查看评分理由和修改方向。</p>`}
      <div class="review-workspace"><article class="essay-paper"><div class="paper-heading"><span>YOUR WRITING</span><span>你的原文 · ${marked.length} 句有反馈</span></div><div class="annotated-essay"></div></article>
        <aside class="feedback-sidebar" aria-label="AI 修改建议"><div class="sidebar-heading"><span>AI 写作教练</span><button type="button" class="icon-button close-feedback" aria-label="关闭修改建议">×</button></div><div class="feedback-body" aria-live="polite"></div></aside></div>`;
    const paper = container.querySelector(".annotated-essay");
    const sidebar = container.querySelector(".feedback-sidebar");
    const body = container.querySelector(".feedback-body");

    function renderEssay() {
      paper.innerHTML = model.sentences.map((s) => {
        const notes = s.notes.filter((n) => activeFilter === "all" || n.direction === activeFilter);
        if (!notes.length) return escape(s.text);
        const types = [...new Set(notes.map((n) => n.direction))];
        const primary = ["accuracy", "structure", "expression"].find((key) => types.includes(key));
        const label = types.map((key) => directions[key].label).join("、");
        const [, leading, text, trailing] = s.text.match(/^(\s*)([\s\S]*?)(\s*)$/);
        return `${escape(leading)}<button type="button" class="essay-sentence ${primary}${selected === s.id ? " selected" : ""}" data-sentence="${s.id}" aria-label="${escape(label)}：${escape(s.text.trim())}" aria-pressed="${selected === s.id}" title="${escape(label)} · 点击查看建议">${escape(text)}${types.length > 1 ? `<sup class="annotation-count" data-count="${types.length}" aria-hidden="true"></sup>` : ""}</button>${escape(trailing)}`;
      }).join("");
    }

    function emptySidebar() {
      sidebar.classList.remove("is-open");
      body.innerHTML = `<div class="feedback-empty"><span class="feedback-empty-icon" aria-hidden="true">↖</span><h4>从一句话开始改进</h4><p>点击左侧高亮句子，查看具体问题和对应维度的修改建议。</p><div class="direction-key">${Object.entries(directions).map(([key, value]) => `<span class="${key}"><i class="direction-dot"></i>${value.label}</span>`).join("")}</div><button type="button" class="secondary-button general-feedback">查看全文建议</button></div>`;
    }

    function showSentence(id, trigger) {
      const sentence = model.sentences[id];
      if (!sentence?.notes.length) return;
      selected = id;
      lastTrigger = trigger;
      renderEssay();
      sidebar.classList.add("is-open");
      const notes = sentence.notes.filter((n) => activeFilter === "all" || n.direction === activeFilter);
      const visible = model.sentences.filter((s) => s.notes.some((n) => activeFilter === "all" || n.direction === activeFilter));
      const position = visible.findIndex((s) => s.id === id);
      body.innerHTML = `<div class="feedback-navigation"><span>第 ${position + 1} / ${visible.length} 句</span><div><button type="button" class="icon-button" data-jump="${visible[position - 1]?.id ?? ""}" ${position === 0 ? "disabled" : ""} aria-label="上一句">←</button><button type="button" class="icon-button" data-jump="${visible[position + 1]?.id ?? ""}" ${position === visible.length - 1 ? "disabled" : ""} aria-label="下一句">→</button></div></div>
        <p class="eyebrow">原文句子</p><blockquote class="selected-quote">${escape(sentence.text.trim())}</blockquote>
        ${notes.map((n) => `<section class="feedback-note"><span class="note-label ${n.direction}">${directions[n.direction].symbol} ${directions[n.direction].label}</span><h4>${escape(names[n.criterion] || n.criterion)}</h4><p>${escape(n.explanation)}</p>${n.quote ? `<p class="quote-context">对应片段：<q>${escape(n.quote)}</q></p>` : ""}</section>`).join("")}
        ${[...new Set(notes.map((n) => n.criterion))].map((criterion) => {
          const tips = [...new Set(notes.filter((n) => n.criterion === criterion).flatMap((n) => n.improvements))];
          return tips.length ? `<section class="feedback-actions"><h4>${escape(names[criterion])} · 改进建议</h4><ul>${tips.map((tip) => `<li>${escape(tip)}</li>`).join("")}</ul></section>` : "";
        }).join("")}`;
      // Keep keyboard focus on the new sentence node after replacing markup.
      if (trigger?.matches(".essay-sentence")) paper.querySelector(`[data-sentence="${id}"]`)?.focus({ preventScroll: true });
    }

    function showGeneral() {
      selected = null;
      renderEssay();
      sidebar.classList.add("is-open");
      body.innerHTML = `<p class="eyebrow">WHOLE ESSAY</p><h4 class="sidebar-title">全文建议</h4><p class="muted">这里包含整体反馈，以及无法定位到某一句的建议。</p>
        ${(report.criterion_results || []).map((c) => `<section class="feedback-note"><span class="note-label ${direction(c.criterion)}">${escape(names[c.criterion] || c.criterion)}</span><p>${escape(c.rationale)}</p>${(c.strengths || []).length ? `<h4>值得保留</h4><ul>${c.strengths.map((s) => `<li>${escape(s)}</li>`).join("")}</ul>` : ""}${(c.improvements || []).length ? `<h4>下一步怎么改</h4><ul>${c.improvements.map((s) => `<li>${escape(s)}</li>`).join("")}</ul>` : ""}${model.unlocated.filter((n) => n.criterion === c.criterion).map((n) => `<p class="unlocated-note">${escape(n.explanation)}</p>`).join("")}</section>`).join("")}`;
    }

    container.addEventListener("click", (event) => {
      const sentence = event.target.closest("[data-sentence]");
      if (sentence) return showSentence(Number(sentence.dataset.sentence), sentence);
      const filter = event.target.closest("[data-filter]");
      if (filter) {
        activeFilter = filter.dataset.filter;
        selected = null;
        container.querySelectorAll("[data-filter]").forEach((button) => {
          button.classList.toggle("active", button === filter);
          button.setAttribute("aria-pressed", String(button === filter));
        });
        renderEssay(); emptySidebar(); return;
      }
      const jump = event.target.closest("[data-jump]");
      if (jump && jump.dataset.jump !== "") {
        showSentence(Number(jump.dataset.jump), jump);
        paper.querySelector(`[data-sentence="${selected}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      if (event.target.closest(".general-feedback")) {
        lastTrigger = event.target.closest("button"); showGeneral();
      }
      if (event.target.closest(".close-feedback")) closeSidebar();
    });
    function closeSidebar() {
      const previous = selected;
      selected = null; renderEssay(); emptySidebar();
      (previous !== null ? paper.querySelector(`[data-sentence="${previous}"]`) : lastTrigger)?.focus({ preventScroll: true });
    }
    container.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && sidebar.classList.contains("is-open")) closeSidebar();
    });
    renderEssay(); emptySidebar();
  }

  function enableImageZoom() {
    const dialog = document.createElement("dialog");
    dialog.className = "image-dialog";
    dialog.innerHTML = `<div class="image-dialog-toolbar"><strong>题目原图</strong><span>可滚动查看完整图片</span><button type="button" class="secondary-button image-size">查看原尺寸</button><button type="button" class="icon-button image-close" aria-label="关闭大图">×</button></div><div class="image-dialog-canvas"><img alt="题目原图放大预览" /></div>`;
    document.body.append(dialog);
    const image = dialog.querySelector("img");
    const sizeButton = dialog.querySelector(".image-size");
    document.addEventListener("click", (event) => {
      const target = event.target.closest("[data-zoomable]");
      if (!target) return;
      image.src = target.currentSrc || target.src;
      dialog.classList.remove("natural-size");
      sizeButton.textContent = "查看原尺寸";
      dialog.showModal();
    });
    document.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key) && event.target.matches("[data-zoomable]")) {
        event.preventDefault(); event.target.click();
      }
    });
    dialog.querySelector(".image-close").addEventListener("click", () => dialog.close());
    sizeButton.addEventListener("click", () => {
      const natural = dialog.classList.toggle("natural-size");
      sizeButton.textContent = natural ? "适应窗口" : "查看原尺寸";
    });
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  }

  const api = { mount, buildAnnotations, splitSentences, quoteRanges, renderSummary, criterionLabel: (key) => names[key] || key };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    root.WritingFeedback = api;
    document.addEventListener("DOMContentLoaded", enableImageZoom, { once: true });
  }
})(typeof window !== "undefined" ? window : globalThis);
