from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.diary import (
    DiaryAnswers,
    DiaryWindow,
    InvalidDiary,
    SideEffectAnswer,
    diary_window,
    suggest_meds_taken,
    validate_diary,
)
from app.domain.enums import DoseStatus, MedsTaken

MSK = ZoneInfo("Europe/Moscow")
DAY = date(2026, 10, 26)
CODES = {"nausea", "drowsiness", "headache", "tremor", "palpitations", "libido_decrease", "other"}


@pytest.mark.parametrize(
    ("day", "now", "expected"),
    [
        (DAY, datetime(2026, 10, 26, 23, 59, tzinfo=MSK), DiaryWindow.ON_TIME),
        (DAY, datetime(2026, 10, 27, 11, 59, tzinfo=MSK), DiaryWindow.LATE),
        (DAY, datetime(2026, 10, 27, 12, 0, tzinfo=MSK), DiaryWindow.CLOSED),
        (DAY, datetime(2026, 10, 28, 9, 0, tzinfo=MSK), DiaryWindow.CLOSED),
        (DAY, datetime(2026, 10, 25, 9, 0, tzinfo=MSK), DiaryWindow.CLOSED),  # будущий день
    ],
)
def test_diary_window(day, now, expected):
    assert diary_window(day, now, cutoff_hour=12) is expected


def _validate(answers, takes_medication=True):
    validate_diary(answers, takes_medication=takes_medication, side_effect_codes=CODES, max_text=500)


def test_partial_diary_is_valid():
    _validate(DiaryAnswers(mood=0))  # 0 — «очень плохое», допустимое значение


@pytest.mark.parametrize(
    "answers",
    [
        DiaryAnswers(),
        DiaryAnswers(mood=11),
        DiaryAnswers(mood=-1),
        DiaryAnswers(mood=True),
        DiaryAnswers(energy=5.5),
        DiaryAnswers(sleep_hours=7.3),
        DiaryAnswers(sleep_hours=25),
        DiaryAnswers(had_side_effects=True),
        DiaryAnswers(had_side_effects=False, side_effects=(SideEffectAnswer("nausea"),)),
        DiaryAnswers(had_side_effects=True, side_effects=(SideEffectAnswer("rash"),)),
        DiaryAnswers(had_side_effects=True, side_effects=(SideEffectAnswer("other"),)),
        DiaryAnswers(had_side_effects=True, side_effects=(SideEffectAnswer("other", "x" * 501),)),
        DiaryAnswers(had_side_effects=True, side_effects=(SideEffectAnswer("nausea", "текст"),)),
        DiaryAnswers(had_side_effects=True, side_effects=(SideEffectAnswer("nausea"), SideEffectAnswer("nausea"))),
    ],
)
def test_invalid_diary(answers):
    with pytest.raises(InvalidDiary):
        _validate(answers)


def test_medication_questions_hidden_for_patients_without_medication():
    _validate(DiaryAnswers(mood=5), takes_medication=False)
    with pytest.raises(InvalidDiary, match="не принимает"):
        _validate(DiaryAnswers(mood=5, meds_taken=MedsTaken.ALL), takes_medication=False)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], None),
        ([DoseStatus.TAKEN, DoseStatus.TAKEN_LATE], MedsTaken.ALL),
        ([DoseStatus.TAKEN, DoseStatus.MISSED], MedsTaken.MISSED),
        ([DoseStatus.MISSED, DoseStatus.SELF_CHANGED], MedsTaken.SELF_CHANGED),
        ([DoseStatus.TAKEN, DoseStatus.NO_RESPONSE], None),  # «не знаем» — не «все»
        ([DoseStatus.PENDING], None),
    ],
)
def test_suggest_meds_taken(statuses, expected):
    assert suggest_meds_taken(statuses) == expected
