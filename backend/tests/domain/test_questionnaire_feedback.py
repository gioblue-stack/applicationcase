from datetime import date

import pytest

from app.content.loader import load_content
from app.domain.enums import InstrumentCode, ScheduleStatus
from app.domain.questionnaire_feedback import (
    Change,
    SelfCheckLevel,
    classify_change,
    patient_feedback,
    result_text,
    self_check_level,
)
from app.domain.weekly_schedule import due_date_for, slot_transition

CONTENT = load_content()
TEXTS = CONTENT.patient_texts


@pytest.mark.parametrize(
    ("previous", "total", "threshold", "expected"),
    [(None, 10, 5, None), (16, 8, 5, Change.IMPROVED), (16, 12, 5, Change.UNCHANGED),
     (8, 13, 5, Change.WORSE), (6, 10, 4, Change.WORSE), (10, 6, 4, Change.IMPROVED)],
)
def test_classify_change(previous, total, threshold, expected):
    assert classify_change(previous, total, threshold=threshold) == expected


def test_patient_never_sees_severity_labels():
    labels = {b.label.lower() for i in (CONTENT.phq9, CONTENT.gad7) for b in i.severity_bands_doctor_only}
    for instrument, max_total in ((InstrumentCode.PHQ9, 27), (InstrumentCode.GAD7, 21)):
        for total in range(max_total + 1):
            text = result_text(TEXTS, instrument, total).lower()
            assert not any(label in text for label in labels if label != "лёгкая"), (instrument, total)
            assert "депресс" not in text


@pytest.mark.parametrize(("total", "start"), [(4, "Сейчас симптомы почти"), (5, "Симптомы немного"),
                                              (14, "Симптомы заметно"), (15, "Сейчас вам непросто")])
def test_phq9_soft_text_bands(total, start):
    assert result_text(TEXTS, InstrumentCode.PHQ9, total).startswith(start)


def test_feedback_always_carries_not_a_diagnosis_note():
    feedback = patient_feedback(TEXTS, InstrumentCode.GAD7, 3, None, threshold=4)
    assert feedback.change is None and feedback.change_text is None
    assert feedback.note == "Результаты опросников — не диагноз, их обсуждают с врачом."


@pytest.mark.parametrize(
    ("phq9", "gad7", "expected"),
    [(0, 4, SelfCheckLevel.NONE), (4, 5, SelfCheckLevel.MILD), (9, 9, SelfCheckLevel.MILD),
     (12, 7, SelfCheckLevel.PRONOUNCED), (3, 10, SelfCheckLevel.PRONOUNCED)],
)
def test_self_check_level(phq9, gad7, expected):
    assert self_check_level(phq9, gad7) is expected


ANCHOR = date(2026, 10, 1)


@pytest.mark.parametrize(
    ("today", "expected"),
    [(date(2026, 9, 30), None), (ANCHOR, ANCHOR), (date(2026, 10, 7), ANCHOR), (date(2026, 10, 8), date(2026, 10, 8))],
)
def test_weekly_due_dates(today, expected):
    assert due_date_for(ANCHOR, today) == expected


@pytest.mark.parametrize(
    ("status", "days_overdue", "expected"),
    [
        (ScheduleStatus.PENDING, 0, ScheduleStatus.PENDING),
        (ScheduleStatus.PENDING, 1, ScheduleStatus.REMINDED),
        (ScheduleStatus.REMINDED, 2, ScheduleStatus.REMINDED),
        (ScheduleStatus.REMINDED, 3, ScheduleStatus.MISSED),
        (ScheduleStatus.PENDING, 5, ScheduleStatus.MISSED),
        (ScheduleStatus.DONE, 5, ScheduleStatus.DONE),
    ],
)
def test_weekly_slot_transition(status, days_overdue, expected):
    today = date.fromordinal(ANCHOR.toordinal() + days_overdue)
    assert slot_transition(status, ANCHOR, today, remind_after_days=1, missed_after_days=3) is expected
