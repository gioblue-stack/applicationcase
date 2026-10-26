"""Напоминания, ответы на них и правило при пропуске. Сценарий Игоря (§7.13): эсциталопрам, пропуски."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.content.loader import load_content
from app.domain.enums import DoseStatus, FlagReason, MissedDoseRule, NotificationKind, RiskTrigger
from app.domain.treatment import DoseResponse, MissedDoseHint, Step
from app.models import DoseEvent, Notification
from app.services.doses import (
    DoseError,
    due_treatment_change_block,
    respond_to_dose,
    run_dose_schedule,
    snooze_dose,
)
from app.services.risk_protocol import record_risk_assessment
from app.services.treatment import PrescriptionSpec, create_prescription
from tests.factories import link, make_doctor, make_patient

CONTENT = load_content()
MSK = ZoneInfo("Europe/Moscow")
TODAY = date(2026, 10, 26)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=MSK)


START_RUN = at(TODAY, 0, 30)


@pytest.fixture
def igor(db):
    doctor = make_doctor(db)
    patient = make_patient(db, "Игорь Демо")
    link(db, doctor, patient)
    return doctor, patient


def prescribe(db, doctor, patient, substance_id="escitalopram", rule=MissedDoseRule.TAKE_IF_MORE_THAN_HOURS, hours=6,
              start=date(2026, 10, 1), steps=()):
    return create_prescription(
        db, doctor_account_id=doctor.account_id, patient_id=patient.id, now=START_RUN, content=CONTENT,
        spec=PrescriptionSpec(substance_id=substance_id, form="таблетки", dose=Decimal(10), unit="мг",
                              times=[time(9), time(21)], start_date=start, in_person_visit_date=start,
                              missed_dose_rule=rule, missed_dose_hours=hours, titration=list(steps)),
    )


def event_at(db, p, when):
    return db.scalars(select(DoseEvent).where(DoseEvent.prescription_id == p.id, DoseEvent.scheduled_at == when)).one()


def answer(db, patient, event, response, now, **kw):
    return respond_to_dose(db, patient_id=patient.id, dose_event_id=event.id, response=response, now=now,
                           content=CONTENT, **kw)


def test_schedule_creates_reminders_with_neutral_text(db, igor):
    doctor, patient = igor
    prescribe(db, doctor, patient)
    run_dose_schedule(db, now=START_RUN, content=CONTENT)
    assert run_dose_schedule(db, now=START_RUN + timedelta(minutes=5), content=CONTENT).created == []
    reminders = db.scalars(select(Notification).where(Notification.kind == NotificationKind.DOSE_REMINDER)).all()
    assert len(reminders) == 4  # 2 приёма в день × 48 часов
    for n in reminders:
        assert (n.title, n.body_neutral, n.body_detailed) == ("Напоминание", "Пора отметить приём", None)
        assert "эсциталопрам" not in f"{n.title} {n.body_neutral}".lower()


def test_detailed_text_only_when_patient_enabled_it(db, igor):
    doctor, patient = igor
    patient.notification_details_enabled = True
    prescribe(db, doctor, patient)
    reminder = db.scalars(select(Notification).where(Notification.kind == NotificationKind.DOSE_REMINDER)).first()
    assert reminder.body_neutral == "Пора отметить приём"
    assert reminder.body_detailed == "Пора принять: Эсциталопрам 10 мг"


def test_missed_dose_shows_doctor_rule_with_hint(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient)
    morning = event_at(db, p, at(TODAY, 9))
    result = answer(db, patient, morning, DoseResponse.MISSED, at(TODAY, 10))
    g = result.guidance
    assert g.rule_text.startswith("Примите пропущенную дозу, если до следующего приёма больше 6 ч")
    assert (g.hint, g.hint_text) == (MissedDoseHint.TAKE_NOW, "Сейчас до следующего приёма больше 6 ч — пропущенную дозу можно принять.")
    assert g.author_note == "Это правило задал ваш лечащий врач."

    evening = event_at(db, p, at(TODAY, 21))
    late = answer(db, patient, evening, DoseResponse.MISSED, at(TODAY + timedelta(days=1), 4))
    assert late.guidance.hint is MissedDoseHint.SKIP_NOW  # до приёма в 09:00 осталось 5 ч


def test_skip_rule_has_no_hint_only_rule(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient, rule=MissedDoseRule.SKIP_NO_DOUBLE, hours=None)
    result = answer(db, patient, event_at(db, p, at(TODAY, 9)), DoseResponse.MISSED, at(TODAY, 10))
    assert result.guidance.hint is None
    assert "Двойную дозу не принимайте" in result.guidance.rule_text


def test_two_misses_in_a_row_flag_doctor_and_offer_block(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient)
    first = answer(db, patient, event_at(db, p, at(TODAY, 9)), DoseResponse.MISSED, at(TODAY, 10))
    second = answer(db, patient, event_at(db, p, at(TODAY, 21)), DoseResponse.MISSED, at(TODAY, 22))
    assert (first.raised_flags, first.offer_risk_block) == ([], None)
    assert second.raised_flags == [FlagReason.MISSED_DOSES]
    assert second.offer_risk_block is RiskTrigger.UNSCHEDULED_ADHERENCE


def test_taken_late_and_self_changed(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient)
    assert answer(db, patient, event_at(db, p, at(TODAY, 9)), DoseResponse.TAKEN_LATE, at(TODAY, 11)).status \
        is DoseStatus.TAKEN_LATE
    evening = event_at(db, p, at(TODAY, 21))
    with pytest.raises(DoseError, match="какую дозу"):
        answer(db, patient, evening, DoseResponse.SELF_CHANGED, at(TODAY, 21))
    result = answer(db, patient, evening, DoseResponse.SELF_CHANGED, at(TODAY, 21), actual_dose=Decimal(20))
    assert result.raised_flags == [FlagReason.SELF_DOSE_CHANGE]
    assert evening.actual_dose == Decimal(20)


def test_answer_is_final_and_only_for_own_doses(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient)
    event = event_at(db, p, at(TODAY, 9))
    answer(db, patient, event, DoseResponse.TAKEN, at(TODAY, 9))
    with pytest.raises(DoseError, match="уже отмечен"):
        answer(db, patient, event, DoseResponse.MISSED, at(TODAY, 10))
    with pytest.raises(DoseError, match="не найден"):
        answer(db, make_patient(db, "Чужой Пациент"), event_at(db, p, at(TODAY, 21)), DoseResponse.TAKEN, at(TODAY, 21))


def test_no_response_after_three_hours_then_late_answer(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient)
    event = event_at(db, p, at(TODAY, 9))
    assert event.id not in run_dose_schedule(db, now=at(TODAY, 11, 59), content=CONTENT).no_response
    assert event.id in run_dose_schedule(db, now=at(TODAY, 12), content=CONTENT).no_response
    db.refresh(event)
    assert event.status is DoseStatus.NO_RESPONSE  # «не знаем», а не «пропустил»
    assert answer(db, patient, event, DoseResponse.TAKEN_LATE, at(TODAY, 13)).status is DoseStatus.TAKEN_LATE


def test_snooze(db, igor):
    doctor, patient = igor
    p = prescribe(db, doctor, patient)
    event = event_at(db, p, at(TODAY, 9))
    until = snooze_dose(db, patient_id=patient.id, dose_event_id=event.id, minutes=15, now=at(TODAY, 9),
                        content=CONTENT)
    assert until == at(TODAY, 9, 15)
    assert db.scalars(select(Notification).where(Notification.scheduled_for == until)).one().body_neutral == \
        "Пора отметить приём"
    with pytest.raises(DoseError, match="15 или 30"):
        snooze_dose(db, patient_id=patient.id, dose_event_id=event.id, minutes=20, now=at(TODAY, 9), content=CONTENT)
    answer(db, patient, event, DoseResponse.TAKEN, at(TODAY, 9, 15))
    assert event.snoozed_until is None
    with pytest.raises(DoseError, match="уже отмечен"):
        snooze_dose(db, patient_id=patient.id, dose_event_id=event.id, minutes=30, now=at(TODAY, 9, 20),
                    content=CONTENT)


def _block(db, patient, now):
    return due_treatment_change_block(db, patient_id=patient.id, now=now, content=CONTENT)


def test_block_offered_more_often_after_starting_antidepressant(db, igor):
    doctor, patient = igor
    prescribe(db, doctor, patient, start=TODAY)
    assert _block(db, patient, at(TODAY, 10)) is RiskTrigger.UNSCHEDULED_TREATMENT_CHANGE
    record_risk_assessment(db, patient_id=patient.id, client_id=uuid.uuid4(), trigger=RiskTrigger.UNSCHEDULED_TREATMENT_CHANGE,
                           trigger_ref=None, answers={"q1": False, "q2": False, "q6": False},
                           client_submitted_at=at(TODAY, 10), now=at(TODAY, 10))
    assert _block(db, patient, at(TODAY + timedelta(days=2), 10)) is None
    assert _block(db, patient, at(TODAY + timedelta(days=3), 10)) is RiskTrigger.UNSCHEDULED_TREATMENT_CHANGE
    assert _block(db, patient, at(TODAY + timedelta(days=14), 10)) is None


def test_dose_step_restarts_the_window(db, igor):
    doctor, patient = igor
    prescribe(db, doctor, patient, start=TODAY - timedelta(days=30), steps=[Step(TODAY - timedelta(days=2), Decimal(20))])
    assert _block(db, patient, at(TODAY, 10)) is RiskTrigger.UNSCHEDULED_TREATMENT_CHANGE


def test_no_frequent_block_for_anxiolytic(db, igor):
    doctor, patient = igor
    prescribe(db, doctor, patient, substance_id="phenazepam", start=TODAY)
    assert _block(db, patient, at(TODAY, 10)) is None
