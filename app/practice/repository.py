"""SQLite repository for the Academic question bank and practice sessions."""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.rag.corpus_loader import TaskType, load_corpus

PracticeMode = Literal["daily", "question_bank"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class QuestionBankError(RuntimeError):
    """Raised when a question or practice session cannot be found or used."""


class QuestionBankRepository:
    """Persist reviewed Academic questions and user practice submissions."""

    def __init__(self, database_path: Path, corpus_dir: Path) -> None:
        self.database_path = database_path
        self.corpus_dir = corpus_dir
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS questions (
                    question_id TEXT PRIMARY KEY,
                    exam_type TEXT NOT NULL CHECK (exam_type = 'academic'),
                    task_type TEXT NOT NULL CHECK (task_type IN ('task1', 'task2')),
                    title TEXT NOT NULL,
                    question TEXT NOT NULL,
                    question_type TEXT,
                    chart_type TEXT,
                    chart_subtype TEXT,
                    topic TEXT,
                    source_pages_json TEXT NOT NULL,
                    retrieval_eligible INTEGER NOT NULL CHECK (retrieval_eligible IN (0, 1)),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS practice_sessions (
                    session_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL CHECK (mode IN ('daily', 'question_bank')),
                    status TEXT NOT NULL CHECK (status IN ('active', 'submitted')),
                    duration_seconds INTEGER,
                    refresh_count INTEGER NOT NULL DEFAULT 0,
                    refresh_limit INTEGER NOT NULL DEFAULT 3,
                    started_at TEXT NOT NULL,
                    submitted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS session_items (
                    session_id TEXT NOT NULL REFERENCES practice_sessions(session_id)
                        ON DELETE CASCADE,
                    item_order INTEGER NOT NULL,
                    question_id TEXT NOT NULL REFERENCES questions(question_id),
                    essay TEXT,
                    report_json TEXT,
                    submitted_at TEXT,
                    PRIMARY KEY (session_id, item_order)
                );
                CREATE INDEX IF NOT EXISTS idx_questions_task ON questions(task_type);
                CREATE INDEX IF NOT EXISTS idx_questions_type
                    ON questions(question_type, chart_type);
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(practice_sessions)")
            }
            if "refresh_count" not in columns:
                connection.execute(
                    "ALTER TABLE practice_sessions ADD COLUMN refresh_count "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            if "refresh_limit" not in columns:
                connection.execute(
                    "ALTER TABLE practice_sessions ADD COLUMN refresh_limit "
                    "INTEGER NOT NULL DEFAULT 3"
                )

    def seed_from_corpus(self) -> int:
        """Upsert all eligible reviewed Academic questions from the corpus."""

        samples = load_corpus(self.corpus_dir, include_ineligible=False)
        with self._connect() as connection:
            for sample in samples:
                connection.execute(
                    """
                    INSERT INTO questions (
                        question_id, exam_type, task_type, title, question,
                        question_type, chart_type, chart_subtype, topic,
                        source_pages_json, retrieval_eligible, updated_at
                    ) VALUES (?, 'academic', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(question_id) DO UPDATE SET
                        task_type=excluded.task_type,
                        title=excluded.title,
                        question=excluded.question,
                        question_type=excluded.question_type,
                        chart_type=excluded.chart_type,
                        chart_subtype=excluded.chart_subtype,
                        topic=excluded.topic,
                        source_pages_json=excluded.source_pages_json,
                        retrieval_eligible=excluded.retrieval_eligible,
                        updated_at=excluded.updated_at
                    """,
                    (
                        sample.sample_id,
                        sample.task_type,
                        sample.title,
                        sample.question,
                        sample.question_type,
                        sample.chart_type,
                        sample.chart_subtype,
                        sample.topic,
                        json.dumps(sample.source_pages),
                        int(sample.retrieval_eligible),
                        _now(),
                    ),
                )
        return len(samples)

    def list_questions(
        self,
        *,
        task_type: TaskType | None = None,
        question_type: str | None = None,
        chart_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List eligible questions with stable pagination and filters."""

        if limit < 1 or limit > 100 or offset < 0:
            raise ValueError("limit 必须为 1-100，offset 不能小于 0")
        clauses = ["retrieval_eligible = 1"]
        values: list[Any] = []
        if task_type:
            clauses.append("task_type = ?")
            values.append(task_type)
        if question_type:
            clauses.append("question_type = ?")
            values.append(question_type)
        if chart_type:
            clauses.append("chart_type = ?")
            values.append(chart_type)
        values.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM questions WHERE {' AND '.join(clauses)} "
                "ORDER BY question_id LIMIT ? OFFSET ?",
                values,
            ).fetchall()
        return [self._question_row(row) for row in rows]

    def get_question(self, question_id: str) -> dict[str, Any]:
        """Return one eligible question or raise a clear domain error."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM questions WHERE question_id = ? AND retrieval_eligible = 1",
                (question_id,),
            ).fetchone()
        if row is None:
            raise QuestionBankError(f"找不到可用的 Academic 题目: {question_id}")
        return self._question_row(row)

    def create_session(
        self,
        mode: PracticeMode,
        *,
        task_type: TaskType | None = None,
        question_id: str | None = None,
        duration_seconds: int | None = None,
        daily_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a daily pair or one question-bank practice session."""

        if mode == "daily":
            question_ids = self._daily_question_ids(daily_date)
        elif mode == "question_bank":
            if not task_type or not question_id:
                raise QuestionBankError("专项练习必须提供 task_type 和 question_id")
            question = self.get_question(question_id)
            if question["task_type"] != task_type:
                raise QuestionBankError("题目 task_type 与专项练习不一致")
            question_ids = [question_id]
        else:
            raise QuestionBankError(f"不支持的会话模式: {mode}")
        session_id = uuid.uuid4().hex
        started_at = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO practice_sessions "
                "(session_id, mode, status, duration_seconds, refresh_count, "
                "refresh_limit, started_at, submitted_at) "
                "VALUES (?, ?, 'active', ?, 0, 3, ?, NULL)",
                (
                    session_id,
                    mode,
                    (
                        3600
                        if duration_seconds is None and mode == "daily"
                        else duration_seconds
                    ),
                    started_at,
                ),
            )
            connection.executemany(
                "INSERT INTO session_items(session_id, item_order, question_id) "
                "VALUES (?, ?, ?)",
                [
                    (session_id, index, question_id)
                    for index, question_id in enumerate(question_ids)
                ],
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        """Return session metadata and its question items."""

        with self._connect() as connection:
            session = connection.execute(
                "SELECT * FROM practice_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise QuestionBankError(f"找不到练习会话: {session_id}")
            items = connection.execute(
                """
                SELECT si.item_order, si.question_id, si.essay, si.report_json,
                       q.task_type, q.title, q.question, q.question_type,
                       q.chart_type, q.chart_subtype, q.topic, q.source_pages_json
                FROM session_items si JOIN questions q ON q.question_id = si.question_id
                WHERE si.session_id = ? ORDER BY si.item_order
                """,
                (session_id,),
            ).fetchall()
        return {
            "session_id": session["session_id"],
            "mode": session["mode"],
            "status": session["status"],
            "duration_seconds": session["duration_seconds"],
            "refresh_count": session["refresh_count"],
            "refresh_limit": session["refresh_limit"],
            "started_at": session["started_at"],
            "submitted_at": session["submitted_at"],
            "items": [self._session_item_row(row) for row in items],
        }

    def save_submission(
        self, session_id: str, item_order: int, essay: str, report: dict[str, Any]
    ) -> dict[str, Any]:
        """Store one report and mark a session submitted after its item is saved."""

        submitted_at = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE session_items
                SET essay = ?, report_json = ?, submitted_at = ?
                WHERE session_id = ? AND item_order = ? AND essay IS NULL
                """,
                (
                    essay,
                    json.dumps(report, ensure_ascii=False),
                    submitted_at,
                    session_id,
                    item_order,
                ),
            )
            if cursor.rowcount != 1:
                raise QuestionBankError("练习项目不存在、已经提交或提交序号无效")
            pending = connection.execute(
                "SELECT COUNT(*) FROM session_items WHERE session_id = ? AND essay IS NULL",
                (session_id,),
            ).fetchone()[0]
            if pending == 0:
                connection.execute(
                    "UPDATE practice_sessions SET status = 'submitted', "
                    "submitted_at = ? WHERE session_id = ?",
                    (submitted_at, session_id),
                )
        return self.get_session(session_id)

    def refresh_daily_session(self, session_id: str) -> dict[str, Any]:
        """Replace an unsubmitted daily pair, up to the refresh limit."""

        session = self.get_session(session_id)
        if session["mode"] != "daily":
            raise QuestionBankError("只有每日一练会话可以刷新题目")
        if session["status"] != "active":
            raise QuestionBankError("已提交的每日一练不能刷新")
        if any(item.get("essay") is not None for item in session["items"]):
            raise QuestionBankError("提交作文后不能刷新每日一练题目")
        if session["refresh_count"] >= session["refresh_limit"]:
            raise QuestionBankError("每日一练刷新次数已用完")
        question_ids = self._daily_question_ids()
        started_at = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE practice_sessions SET refresh_count = refresh_count + 1, "
                "started_at = ? WHERE session_id = ?",
                (started_at, session_id),
            )
            connection.executemany(
                "UPDATE session_items SET question_id = ?, essay = NULL, "
                "report_json = NULL, submitted_at = NULL "
                "WHERE session_id = ? AND item_order = ?",
                [
                    (question_id, session_id, index)
                    for index, question_id in enumerate(question_ids)
                ],
            )
        return self.get_session(session_id)

    def _daily_question_ids(self, daily_date: str | None = None) -> list[str]:
        """Choose one random eligible question for each Academic task."""

        if daily_date is not None:
            try:
                datetime.fromisoformat(daily_date).date()
            except ValueError as exc:
                raise QuestionBankError("daily_date 必须是 YYYY-MM-DD") from exc
        task1 = self.list_questions(task_type="task1", limit=100)
        task2 = self.list_questions(task_type="task2", limit=100)
        if not task1 or not task2:
            raise QuestionBankError("每日一练需要至少一篇 Task 1 和一篇 Task 2")
        return [
            secrets.choice(task1)["question_id"],
            secrets.choice(task2)["question_id"],
        ]

    @staticmethod
    def _question_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["source_pages"] = json.loads(result.pop("source_pages_json"))
        result["retrieval_eligible"] = bool(result["retrieval_eligible"])
        return result

    @staticmethod
    def _session_item_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["source_pages"] = json.loads(result.pop("source_pages_json"))
        if result.get("report_json"):
            result["report"] = json.loads(result.pop("report_json"))
        else:
            result.pop("report_json", None)
        return result
