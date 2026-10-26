from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.content.loader import load_content
from app.domain.enums import DoseStatus, MissedDoseRule
from app.domain.treatment import (
    DoseResponse,
    InvalidDoseResponse,
    InvalidRegimen,
    MissedDoseHint,
    Step,
    apply_response,
    dose_on,
    format_dose,
    format_step,
    missed_dose_hint,
    no_response_due,
    planned_doses,
    shift_future_steps,
    validate_regimen,
)
from app.domain.unscheduled_check import treatment_change_block_due

START = date(2026, 10, 12)
STEP = Step(date(2026, 10, 26), Decimal(100))
R = MissedDoseRule


def regimen(**overrides):
    values = dict(dose=50, times=[time(9)], start_date=START, end_date=None, in_person_visit_date=START,
                  missed_dose_rule=R.SKIP_NO_DOUBLE, missed_dose_hours=None, steps=[STEP])
    values.update(overrides)
    validate_regimen(**values)


def test_valid_regimen():
    regimen()
    regimen(missed_dose_rule=R.TAKE_IF_MORE_THAN_HOURS, missed_dose_hours=12)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"dose": 0}, "больше нуля"),
        ({"times": []}, "время"),
        ({"times": [time(9), time(9)]}, "повторяется"),
        ({"in_person_visit_date": START + timedelta(days=1)}, "очного приёма"),
        ({"end_date": START - timedelta(days=1)}, "окончания"),
        ({"missed_dose_rule": R.TAKE_IF_MORE_THAN_HOURS}, "N от 1"),
        ({"missed_dose_rule": R.TAKE_IF_MORE_THAN_HOURS, "missed_dose_hours": 49}, "N от 1"),
        ({"missed_dose_hours": 6}, "только для правила"),
        ({"steps": [Step(START, Decimal(100))]}, "после даты начала"),
        ({"steps": [STEP], "end_date": date(2026, 10, 20)}, "после окончания"),
        ({"steps": [STEP, Step(STEP.effective_date, Decimal(150))]}, "одну дату"),
        ({"steps": [Step(STEP.effective_date, Decimal(0))]}, "больше нуля"),
    ],
)
def test_invalid_regimen(overrides, match):
    with pytest.raises(InvalidRegimen, match=match):
        regimen(**overrides)


def test_dose_follows_titration_steps():
    assert dose_on(STEP.effective_date - timedelta(days=1), 50, [STEP]) == 50
    assert dose_on(STEP.effective_date, 50, [STEP]) == 100


def test_planned_doses_in_patient_timezone_with_titration_and_end_date():
    doses = planned_doses(
        start_date=START, end_date=date(2026, 10, 27), times=[time(21), time(9)], timezone="Europe/Moscow",
        base_dose=50, steps=[STEP], window_from=datetime(2026, 10, 25, tzinfo=UTC),
        window_to=datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert [(at.isoformat(), str(dose)) for at, dose in doses] == [
        ("2026-10-25T06:00:00+00:00", "50"), ("2026-10-25T18:00:00+00:00", "50"),
        ("2026-10-26T06:00:00+00:00", "100"), ("2026-10-26T18:00:00+00:00", "100"),
        ("2026-10-27T06:00:00+00:00", "100"), ("2026-10-27T18:00:00+00:00", "100"),
    ]


def test_shift_moves_only_future_steps():
    past, future = Step(date(2026, 10, 20), Decimal(75)), Step(date(2026, 11, 3), Decimal(100))
    shifted = shift_future_steps([past, future], today=date(2026, 10, 26), days=7)
    assert shifted == [past, Step(date(2026, 11, 10), Decimal(100))]


@pytest.mark.parametrize(("steps", "days", "match"), [([STEP], 0, "от 1"), ([STEP], 61, "от 1"),
                                                      ([STEP], 3, "Нет предстоящих")])
def test_shift_rejects(steps, days, match):
    with pytest.raises(InvalidRegimen, match=match):
        shift_future_steps(steps, today=STEP.effective_date, days=days)


def test_plan_wording():
    template = load_content().treatment_texts.plan_step
    assert format_step(template, Step(date(2027, 9, 20), Decimal("100.000")), "мг") == "с 20.09.2027 — 100 мг"
    assert (format_dose(Decimal("12.500")), format_dose(Decimal("0.25"))) == ("12,5", "0,25")


SCHEDULED = datetime(2026, 10, 26, 6, tzinfo=UTC)


def respond(current=DoseStatus.PENDING, now=SCHEDULED, response=DoseResponse.TAKEN, actual=None):
    return apply_response(current=current, scheduled_at=SCHEDULED, now=now, response=response,
                          planned_dose=Decimal(50), actual_dose=actual)


def test_responses():
    assert respond() == (DoseStatus.TAKEN, None)
    assert respond(response=DoseResponse.MISSED) == (DoseStatus.MISSED, None)
    assert respond(current=DoseStatus.NO_RESPONSE, response=DoseResponse.TAKEN_LATE) == (DoseStatus.TAKEN_LATE, None)
    assert respond(response=DoseResponse.SELF_CHANGED, actual=25) == (DoseStatus.SELF_CHANGED, Decimal(25))
    assert respond(now=SCHEDULED - timedelta(minutes=59))[0] is DoseStatus.TAKEN


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"current": DoseStatus.TAKEN}, "уже отмечен"),
        ({"current": DoseStatus.MISSED}, "уже отмечен"),
        ({"now": SCHEDULED - timedelta(minutes=61)}, "ещё не пришло"),
        ({"response": DoseResponse.SELF_CHANGED}, "какую дозу"),
        ({"response": DoseResponse.SELF_CHANGED, "actual": 50}, "совпадает"),
        ({"actual": 50}, "только при самостоятельном"),
    ],
)
def test_invalid_responses(kwargs, match):
    with pytest.raises(InvalidDoseResponse, match=match):
        respond(**kwargs)


@pytest.mark.parametrize(
    ("rule", "hours", "next_in", "expected"),
    [
        (R.SKIP_NO_DOUBLE, None, timedelta(hours=10), None),
        (R.CONTACT_DOCTOR, None, timedelta(hours=10), None),
        (R.TAKE_IF_MORE_THAN_HOURS, 6, timedelta(hours=10), MissedDoseHint.TAKE_NOW),
        (R.TAKE_IF_MORE_THAN_HOURS, 6, timedelta(hours=6), MissedDoseHint.SKIP_NOW),  # «больше N», не «не меньше»
        (R.TAKE_IF_MORE_THAN_HOURS, 6, timedelta(hours=2), MissedDoseHint.SKIP_NOW),
        (R.TAKE_IF_MORE_THAN_HOURS, 6, None, MissedDoseHint.TAKE_NOW),  # приём был последним
    ],
)
def test_missed_dose_hint(rule, hours, next_in, expected):
    now = SCHEDULED + timedelta(hours=1)
    assert missed_dose_hint(rule, hours, now=now, next_dose_at=now + next_in if next_in else None) == expected


def test_every_missed_dose_rule_warns_against_double_dose():
    for text in load_content().treatment_texts.missed_dose_rules.values():
        assert "Двойную дозу не принимайте" in text


def test_lock_screen_reminder_text_is_neutral():
    assert load_content().treatment_texts.reminder.body_neutral == "Пора отметить приём"


@pytest.mark.parametrize(("delta", "status", "due"), [(timedelta(hours=2, minutes=59), DoseStatus.PENDING, False),
                                                      (timedelta(hours=3), DoseStatus.PENDING, True),
                                                      (timedelta(hours=5), DoseStatus.TAKEN, False)])
def test_no_response_due(delta, status, due):
    assert no_response_due(status, SCHEDULED, SCHEDULED + delta, hours=3) is due


TODAY = date(2026, 10, 26)


@pytest.mark.parametrize(
    ("changes", "last_block", "due"),
    [
        ([TODAY], None, True),
        ([TODAY - timedelta(days=13)], TODAY - timedelta(days=3), True),
        ([TODAY - timedelta(days=13)], TODAY - timedelta(days=2), False),
        ([TODAY - timedelta(days=14)], None, False),  # окно 14 дней прошло
        ([], None, False),
    ],
)
def test_treatment_change_block_due(changes, last_block, due):
    assert treatment_change_block_due(changes, last_block, TODAY, every_days=3, window_days=14) is due
