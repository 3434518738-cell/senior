const { test } = require("node:test");
const assert = require("node:assert/strict");
const bank = require("../../frontend/assets/question-bank.js");
const questions = [
  { question_id: "task1_a", task_type: "task1", chart_type: "line_graph", title: "Population", question: "Compare the trends." },
  { question_id: "task1_b", task_type: "task1", chart_type: "map", title: "Village map", question: "Describe the changes." },
  { question_id: "task2_a", task_type: "task2", question_type: "opinion", title: "Education", question: "Do you agree?" },
  { question_id: "task2_b", task_type: "task2", question_type: "causes_and_opinion", title: "Foreign films", question: "Why? Should governments help?" },
];
test("uses the original Task 1 visual type and Task 2 question label", () => {
  assert.equal(bank.label(questions[0]), "折线图");
  assert.equal(bank.label(questions[1]), "地图");
  assert.equal(bank.label(questions[2]), "观点立场题");
  assert.equal(bank.label(questions[3]), "原因与观点");
});
test("counts categories within the selected task without inventing empty groups", () => {
  assert.deepEqual(bank.categories(questions, "task1"), [
    {key:"line_graph",label:"折线图",count:1}, {key:"map",label:"地图",count:1},
  ]);
  assert.equal(bank.categories(questions, "task2").reduce((n, c) => n + c.count, 0), 2);
});
test("combines task, category and case-insensitive keyword filters", () => {
  assert.deepEqual(bank.filter(questions, "task1", "line_graph", " POPULATION "), [questions[0]]);
  assert.deepEqual(bank.filter(questions, "task2", "all", "原因"), [questions[3]]);
  assert.deepEqual(bank.filter(questions, "task2", "opinion", "foreign"), []);
});
test("keeps hybrid Task 2 labels distinct and does not expose sample answers", () => {
  const mixed = ["two_part_question", "problems_and_solutions", "multi_part_problem_solution", "positive_negative_development", "advantages_disadvantages_opinion", "discuss_both_views"].map((question_type) => ({task_type:"task2",question_type}));
  assert.equal(new Set(mixed.map(bank.label)).size, 6);
});
test("retains unknown categories rather than dropping their questions", () => {
  const other = { task_type: "task2", question_type: "new_source_label", title: "New question" };
  assert.equal(bank.typeOf(other), "other");
  assert.equal(bank.categories([other], "task2")[0].count, 1);
  assert.deepEqual(bank.filter([other], "task2", "other"), [other]);
});
