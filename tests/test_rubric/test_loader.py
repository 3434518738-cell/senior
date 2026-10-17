"""Validate the checked-in Academic rubric coverage and filtering policy."""

from pathlib import Path

import pytest

from app.rubric.loader import load_academic_rubric


RUBRIC_PATH = Path("docs/rubrics/academic_writing_rubric.json")


def test_academic_rubric_has_all_task_criteria_and_bands() -> None:
    rubric = load_academic_rubric(RUBRIC_PATH)

    assert len(rubric.descriptors) == 80
    for task_type in ("task1", "task2"):
        task_descriptors = [
            item for item in rubric.descriptors if item.task_type == task_type
        ]
        assert len(task_descriptors) == 40
        assert {item.band for item in task_descriptors} == set(range(10))


def test_task1_descriptors_exclude_general_training_wording() -> None:
    rubric = load_academic_rubric(RUBRIC_PATH)
    task1_text = " ".join(
        item.text for item in rubric.descriptors if item.task_type == "task1"
    ).lower()

    assert "general training" not in task1_text
    assert "bullet points" not in task1_text
    assert "letter" not in task1_text


def test_policy_keeps_academic_task1_and_task2_rules() -> None:
    rubric = load_academic_rubric(RUBRIC_PATH)

    assert rubric.exam_type == "academic"
    assert rubric.policy["task1_minimum_words"] == 150
    assert rubric.policy["task2_minimum_words"] == 250
    assert rubric.policy["task2_weight"] == "higher_than_task1"
    assert rubric.policy["general_training_task1_included"] is False


def test_loader_rejects_general_training_descriptor(tmp_path: Path) -> None:
    content = RUBRIC_PATH.read_text(encoding="utf-8").replace(
        '"text": "All the requirements',
        '"text": "General Training All the requirements',
        1,
    )
    path = tmp_path / "bad-rubric.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="General Training"):
        load_academic_rubric(path)
