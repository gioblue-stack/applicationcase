import json

import pytest

from app.core.config import get_settings
from app.domain.enums import ResponseLevel
from app.domain.risk_protocol import (
    BlockAnswers,
    InvalidAnswers,
    NextStep,
    assess,
    next_step_after_phq9,
    raise_one_step,
    visible_questions,
)

VECTORS = json.loads((get_settings().content_dir / "test_vectors" / "risk_levels.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_shared_vectors(case):
    result = assess(BlockAnswers.from_mapping(case["answers"]), has_risk_factors=case["risk_factors"])
    expected = case["expected"]
    assert result.outcome == expected["outcome"]
    assert result.base_level == expected["base"]
    assert result.final_level == expected["final"]
    assert result.escalated_by_risk_factors == expected["escalated"]
    assert result.flag_level == expected["flag_level"]
    assert result.flag_reason == expected["flag_reason"]
    assert result.patient_screen == expected["screen"]
    assert result.doctor_push == expected["push"]


@pytest.mark.parametrize("case", VECTORS["invalid"], ids=lambda c: c["name"])
def test_shared_invalid_vectors(case):
    with pytest.raises(InvalidAnswers):
        BlockAnswers.from_mapping(case["answers"])


def test_every_outcome_reaches_doctor():
    """При любом исходе есть флаг: экран помощи и уведомление врачу срабатывают всегда (§4.6)."""
    for case in VECTORS["cases"]:
        result = assess(BlockAnswers.from_mapping(case["answers"]), has_risk_factors=case["risk_factors"])
        assert result.flag_level in {"yellow", "red"}


def test_there_is_no_level_below_yellow():
    assert [level.value for level in ResponseLevel] == ["yellow", "red", "emergency"]


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({}, ("q1", "q2", "q6")),
        ({"q2": False}, ("q1", "q2", "q6")),
        ({"q2": True}, ("q1", "q2", "q3", "q4", "q5", "q6")),
    ],
)
def test_follow_up_questions_only_after_active_thoughts(answers, expected):
    assert visible_questions(BlockAnswers.from_mapping(answers)) == expected


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (ResponseLevel.YELLOW, ResponseLevel.RED),
        (ResponseLevel.RED, ResponseLevel.EMERGENCY),
        (ResponseLevel.EMERGENCY, ResponseLevel.EMERGENCY),
    ],
)
def test_raise_one_step_caps_at_emergency(level, expected):
    assert raise_one_step(level) == expected


@pytest.mark.parametrize(
    ("item9", "has_doctor", "expected"),
    [
        (0, True, NextStep.NONE),
        (0, False, NextStep.NONE),
        (1, True, NextStep.RISK_BLOCK),
        (3, True, NextStep.RISK_BLOCK),
        (1, False, NextStep.SELF_USER_HELP),
        (3, False, NextStep.SELF_USER_HELP),
    ],
)
def test_next_step_after_phq9(item9, has_doctor, expected):
    assert next_step_after_phq9(item9, has_treating_doctor=has_doctor) == expected
