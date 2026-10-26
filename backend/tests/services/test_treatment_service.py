"""Схема лечения и титрация. Сценарий Анны (§7.13): сертралин 50 мг, через 2 недели — 100 мг."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.content.loader import load_content
from app.domain.enums import MissedDoseRule, RegimenChangeType
from app.domain.treatment import DoseResponse, InvalidRegimen, Step
from app.models import DoseEvent, Prescription, TitrationStep
from app.services.doses import respond_to_dose, run_dose_schedule, steps_of
from app.services.treatment import (
    PrescriptionSpec,
    TreatmentError,
    change_dose,
    create_prescription,
    patient_plan,
    regimen_history,
    shift_titration,
    stop_prescription,
    titration_needs_attention,
    treatment_markers,
)
from tests.factories import link, make_doctor, make_patient

CONTENT = load_content()
MSK = ZoneInfo("Europe/Moscow")
TODAY = date(2026, 10, 26)
NOW = datetime.combine(TODAY, time(15), tzinfo=MSK)


def spec(**overrides):
    values = dict(substance_id="sertraline", form="таблетки", dose=Decimal(50), unit="мг", times=[time(9)],
                  start_date=date(2026, 10, 20), in_person_visit_date=date(2026, 10, 20),
                  missed_dose_rule=MissedDoseRule.TAKE_IF_MORE_THAN_HOURS, missed_dose_hours=12,
                  titration=[Step(date(2026, 11, 3), Decimal(100))])
    values.update(overrides)
    return PrescriptionSpec(**values)


@pytest.fixture
def anna(db):
    doctor = make_doctor(db)
    patient = make_patient(db, "Анна Демо")
    link(db, doctor, patient)
    return doctor, patient


def prescribe(db, doctor, patient, now=NOW, **overrides):
    return create_prescription(db, doctor_account_id=doctor.account_id, patient_id=patient.id, spec=spec(**overrides),
                               now=now, content=CONTENT)


def future_events(db, p, now=NOW):
    return db.scalars(select(DoseEvent).where(DoseEvent.prescription_id == p.id, DoseEvent.scheduled_at > now)
                      .order_by(DoseEvent.scheduled_at)).all()


def test_create_prescription_with_titration_and_history(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    assert patient.takes_medication  # теперь в дневнике появляются вопросы 7 и 8
    assert steps_of(db, p.id) == [Step(date(2026, 11, 3), Decimal(100))]
    [created] = regimen_history(db, patient.id)
    assert (created.change_type, created.changed_by, created.before) == (RegimenChangeType.CREATED, doctor.account_id, None)
    assert created.after["titration"] == [{"effective_date": "2026-11-03", "dose": "100"}]
    assert [(e.scheduled_at.astimezone(MSK).isoformat(), str(e.planned_dose)) for e in future_events(db, p)] == [
        ("2026-10-27T09:00:00+03:00", "50.000"), ("2026-10-28T09:00:00+03:00", "50.000"),
    ]


def test_only_treating_doctor_prescribes_from_formulary(db, anna):
    doctor, patient = anna
    with pytest.raises(TreatmentError, match="лечащий врач"):
        prescribe(db, make_doctor(db, "Петров Пётр"), patient)
    with pytest.raises(TreatmentError, match="справочнике"):
        prescribe(db, doctor, patient, substance_id="tramadol")
    with pytest.raises(InvalidRegimen, match="очного приёма"):
        prescribe(db, doctor, patient, in_person_visit_date=date(2026, 10, 21))
    assert db.scalar(select(func.count()).select_from(Prescription)) == 0


def test_manual_shift_moves_future_steps_and_logs_reason(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient,
                  titration=[Step(date(2026, 10, 25), Decimal(75)), Step(date(2026, 11, 3), Decimal(100))])
    shifted = shift_titration(db, doctor_account_id=doctor.account_id, prescription_id=p.id, days=7,
                              reason="Пропуски на этапе 75 мг", now=NOW, content=CONTENT)
    assert shifted == [Step(date(2026, 10, 25), Decimal(75)), Step(date(2026, 11, 10), Decimal(100))]
    last = regimen_history(db, patient.id)[-1]
    assert last.change_type is RegimenChangeType.TITRATION_SHIFTED
    assert [s["effective_date"] for s in last.before["titration"]] == ["2026-10-25", "2026-11-03"]
    assert [s["effective_date"] for s in last.after["titration"]] == ["2026-10-25", "2026-11-10"]
    assert last.reason == "Пропуски на этапе 75 мг"


def test_patient_or_other_doctor_cannot_shift(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    for account_id in (patient.account_id, make_doctor(db, "Петров Пётр").account_id):
        with pytest.raises(TreatmentError, match="лечащий врач"):
            shift_titration(db, doctor_account_id=account_id, prescription_id=p.id, days=3, reason=None, now=NOW,
                            content=CONTENT)


def test_misses_never_shift_steps_automatically(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    run_dose_schedule(db, now=NOW, content=CONTENT)
    for event in future_events(db, p):
        when = event.scheduled_at + timedelta(hours=1)
        respond_to_dose(db, patient_id=patient.id, dose_event_id=event.id, response=DoseResponse.MISSED, now=when,
                        content=CONTENT)
    assert steps_of(db, p.id) == [Step(date(2026, 11, 3), Decimal(100))]
    # Вместо автосдвига — подсказка врачу, что пора решить про сдвиг этапа.
    assert titration_needs_attention(db, p.id, NOW + timedelta(days=3))


def test_no_attention_without_misses_or_future_steps(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    assert not titration_needs_attention(db, p.id, NOW)
    q = prescribe(db, doctor, patient, substance_id="mirtazapine", titration=[])
    assert not titration_needs_attention(db, q.id, NOW)


def test_change_dose_from_tomorrow_rebuilds_calendar(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    change_dose(db, doctor_account_id=doctor.account_id, prescription_id=p.id, effective_date=TODAY + timedelta(days=2),
                dose=Decimal(75), reason="Плохо переносит", now=NOW, content=CONTENT)
    assert [str(e.planned_dose) for e in future_events(db, p)] == ["50.000", "75.000"]
    assert regimen_history(db, patient.id)[-1].change_type is RegimenChangeType.DOSE_CHANGED
    with pytest.raises(TreatmentError, match="в прошлом"):
        change_dose(db, doctor_account_id=doctor.account_id, prescription_id=p.id,
                    effective_date=TODAY - timedelta(days=1), dose=Decimal(75), reason=None, now=NOW, content=CONTENT)


def test_stop_removes_future_doses(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    stop_prescription(db, doctor_account_id=doctor.account_id, prescription_id=p.id, reason="Отмена по решению врача",
                      now=NOW, content=CONTENT)
    assert future_events(db, p) == []
    assert run_dose_schedule(db, now=NOW, content=CONTENT).created == []
    assert (p.end_date, patient.takes_medication) == (TODAY, False)
    assert db.scalar(select(func.count()).select_from(TitrationStep)) == 1  # этапы остаются в истории
    assert regimen_history(db, patient.id)[-1].change_type is RegimenChangeType.STOPPED
    with pytest.raises(TreatmentError, match="отменено"):
        stop_prescription(db, doctor_account_id=doctor.account_id, prescription_id=p.id, reason=None, now=NOW,
                          content=CONTENT)


def test_chart_markers_for_doctor(db, anna):
    doctor, patient = anna
    p = prescribe(db, doctor, patient)
    stop_prescription(db, doctor_account_id=doctor.account_id, prescription_id=p.id, reason=None,
                      now=NOW + timedelta(days=10), content=CONTENT)
    assert [(m.day.isoformat(), m.kind, m.label) for m in treatment_markers(db, patient.id, CONTENT)] == [
        ("2026-10-20", "start", "Начало: Сертралин 50 мг"),
        ("2026-11-03", "dose_change", "Доза: Сертралин 100 мг"),
        ("2026-11-05", "stop", "Отмена: Сертралин"),
    ]


def test_patient_plan_in_plain_words(db, anna):
    doctor, patient = anna
    prescribe(db, doctor, patient)
    [item] = patient_plan(db, patient.id, NOW, CONTENT)
    assert (item.inn, item.current_dose, item.unit, item.times) == ("Сертралин", "50", "мг", ["09:00"])
    assert item.upcoming == ["с 03.11.2026 — 100 мг"]
    assert "больше 12 ч" in item.missed_dose_rule_text
