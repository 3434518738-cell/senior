"""Offline tests for the SQLite Academic question bank."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.practice.repository import QuestionBankError, QuestionBankRepository


ROOT = Path(__file__).resolve().parents[2]


def _repository(tmp_path: Path) -> QuestionBankRepository:
    repository = QuestionBankRepository(
        tmp_path / "practice.sqlite3", ROOT / "data" / "corpus_staging"
    )
    repository.seed_from_corpus()
    return repository


def _daily_pair(repository: QuestionBankRepository) -> list[str]:
    return [
        repository.list_questions(task_type=task, limit=100)[-1]["question_id"]
        for task in ("task1", "task2")
    ]


def test_seed_and_filter_academic_question_bank(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    task1 = repository.list_questions(task_type="task1", limit=100)
    task2 = repository.list_questions(task_type="task2", limit=100)

    assert task1
    assert task2
    assert all(item["exam_type"] == "academic" for item in task1 + task2)
    assert all(item["task_type"] == "task1" for item in task1)
    assert all(item["task_type"] == "task2" for item in task2)
    assert repository.get_question(task1[0]["question_id"])["question"]


def test_daily_session_contains_one_task1_and_one_task2(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    chosen = _daily_pair(repository)
    session = repository.create_session("daily", question_ids=list(reversed(chosen)))

    assert session["mode"] == "daily"
    assert session["status"] == "active"
    assert [item["task_type"] for item in session["items"]] == ["task1", "task2"]
    assert session["items"][0]["item_order"] == 0
    assert session["items"][1]["item_order"] == 1
    assert session["duration_seconds"] == 3600
    assert [item["question_id"] for item in session["items"]] == chosen
    assert "refresh_count" not in session
    assert session["items"][0]["chart_image_url"].startswith("/assets/question-images/")


def test_daily_question_bank_excludes_task1_items_without_original_images(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)

    task1 = repository.list_questions(task_type="task1", limit=100)

    assert task1
    assert all(item["chart_image_url"] for item in task1)
    assert all(item["question_id"] != "task1_009" for item in task1)


@pytest.mark.parametrize(
    "question_ids",
    [
        None,
        [],
        ["task1_001"],
        ["task1_001", "task1_001"],
        ["task1_001", "task1_002"],
        ["task2_001", "task2_002"],
        ["task1_009", "task2_001"],
        ["missing", "task2_001"],
    ],
)
def test_daily_session_rejects_invalid_or_unavailable_selection(
    tmp_path: Path,
    question_ids: list[str] | None,
) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(QuestionBankError):
        repository.create_session("daily", question_ids=question_ids)


def test_submissions_are_saved_and_close_the_session_after_all_items(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session("daily", question_ids=_daily_pair(repository))

    after_first = repository.save_submission(
        session["session_id"], 0, "Task 1 essay", {"band": 6.0}
    )
    assert after_first["status"] == "active"
    assert after_first["items"][0]["report"] == {"band": 6.0}

    after_second = repository.save_submission(
        session["session_id"], 1, "Task 2 essay", {"band": 6.5}
    )
    assert after_second["status"] == "submitted"
    assert after_second["submitted_at"]


def test_old_session_columns_and_saved_reports_are_preserved(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session("daily", question_ids=_daily_pair(repository))
    repository.save_submission(session["session_id"], 0, "Saved essay", {"band": 6.5})
    with repository._connect() as connection:
        connection.execute(
            "ALTER TABLE practice_sessions ADD COLUMN refresh_count INTEGER DEFAULT 2"
        )
        connection.execute(
            "ALTER TABLE practice_sessions ADD COLUMN refresh_limit INTEGER DEFAULT 3"
        )
    reopened = QuestionBankRepository(repository.database_path, repository.corpus_dir)
    saved = reopened.get_session(session["session_id"])
    assert saved["items"][0]["essay"] == "Saved essay"
    assert saved["items"][0]["report"] == {"band": 6.5}
    assert "refresh_count" not in saved
