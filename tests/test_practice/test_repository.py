"""Offline tests for the SQLite Academic question bank."""

from __future__ import annotations

from pathlib import Path

from app.practice.repository import QuestionBankRepository


ROOT = Path(__file__).resolve().parents[2]


def _repository(tmp_path: Path) -> QuestionBankRepository:
    repository = QuestionBankRepository(
        tmp_path / "practice.sqlite3", ROOT / "data" / "corpus_staging"
    )
    repository.seed_from_corpus()
    return repository


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

    session = repository.create_session("daily", daily_date="2026-10-19")

    assert session["mode"] == "daily"
    assert session["status"] == "active"
    assert [item["task_type"] for item in session["items"]] == ["task1", "task2"]
    assert session["items"][0]["item_order"] == 0
    assert session["items"][1]["item_order"] == 1
    assert session["duration_seconds"] == 3600
    assert session["refresh_count"] == 0
    assert session["refresh_limit"] == 3


def test_daily_session_can_refresh_three_times_before_submission(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session("daily")

    for expected_count in range(1, 4):
        refreshed = repository.refresh_daily_session(session["session_id"])
        assert refreshed["refresh_count"] == expected_count
        assert [item["task_type"] for item in refreshed["items"]] == [
            "task1",
            "task2",
        ]

    try:
        repository.refresh_daily_session(session["session_id"])
    except Exception as exc:
        assert "刷新次数已用完" in str(exc)
    else:
        raise AssertionError("fourth refresh should be rejected")


def test_submissions_are_saved_and_close_the_session_after_all_items(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session("daily", daily_date="2026-10-19")

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
