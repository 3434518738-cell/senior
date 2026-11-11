const { test } = require("node:test");
const assert = require("node:assert/strict");
const { buildAnnotations, splitSentences, quoteRanges, renderSummary } = require("../../frontend/assets/feedback.js");

test("keeps the submitted text, paragraph breaks, and Unicode offsets intact", () => {
  const essay = "  First idea.\r\n\r\nA student's idea is useful! 📝 Another one?\nFinal line";
  const parts = splitSentences(essay);
  assert.equal(parts.map((s) => s.text).join(""), essay);
  for (const part of parts) assert.equal(essay.slice(part.start, part.end), part.text);
});

test("maps server-normalized quotes to the original whitespace without fuzzy matches", () => {
  const essay = "People\n  has ideas. Another sentence.";
  const result = buildAnnotations(essay, { criterion_results: [{
    criterion: "grammatical_range_and_accuracy", issues: [{ quote: "People has ideas.", explanation: "Check subject–verb agreement." }], improvements: ["Use have with people."],
  }] });
  assert.equal(result.sentences.filter((s) => s.notes.length).map((s) => s.text).join(""), "People  has ideas. ");
  assert.equal(result.sentences.find((s) => s.notes.length).notes[0].direction, "accuracy");
  assert.deepEqual(quoteRanges(essay, "People have ideas."), []);
});

test("retains multiple improvement directions on the same sentence", () => {
  const report = { criterion_results: [
    { criterion: "lexical_resource", issues: [{ quote: "things", explanation: "Use a specific noun." }] },
    { criterion: "task_response", issues: [{ quote: "Many things are good.", explanation: "Explain the claim." }] },
  ] };
  const { sentences } = buildAnnotations("Many things are good. Other ideas follow.", report);
  assert.deepEqual(sentences[0].notes.map((n) => n.direction), ["expression", "structure"]);
  assert.equal(sentences[1].notes.length, 0);
});

test("keeps missing or invalid quotations in whole-essay feedback", () => {
  const { sentences, unlocated } = buildAnnotations("A real sentence.", { criterion_results: [{
    criterion: "task_response", issues: [{ quote: null, explanation: "Add a conclusion." }, { quote: "Invented evidence.", explanation: "Not in this essay." }],
  }] });
  assert.equal(sentences[0].notes.length, 0);
  assert.equal(unlocated.length, 2);
});

test("anchors a quote that crosses sentence boundaries without dropping either observation", () => {
  const { sentences } = buildAnnotations("One point. Another point.", { criterion_results: [{
    criterion: "coherence_and_cohesion", issues: [{ quote: "point. Another", explanation: "Make the relationship explicit." }],
  }] });
  assert.equal(sentences.filter((s) => s.notes.length).length, 2);
});

test("retains partial task checks and escapes model content in the score summary", () => {
  const report = { word_count: 25, essay_band_estimate: null, criterion_results: [{
    criterion: "<script>alert(1)</script>", band: 5,
    task_review: { checks: [{ status: "partial", quote: "An idea.", explanation: "Needs development." }] },
  }] };
  assert.equal(buildAnnotations("An idea.", report).sentences[0].notes.length, 1);
  const html = renderSummary(report);
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("不提供可靠总估分"));
});

test("shows the Task total and escaped model summary together", () => {
  const html = renderSummary({ task_type: "task2", word_count: 280, essay_band_estimate: 6.5,
    overall_feedback: "整体论证清楚。请检查 <script> 之类的引用。", criterion_results: [] });
  assert.ok(html.includes("Task 2 总估分 / 9"));
  assert.ok(html.includes("6.5"));
  assert.ok(html.includes("模型总评"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<script>"));
});
