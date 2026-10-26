"""Приверженность (§1.2) и тревожные симптомы (§7.5). Сценарий Игоря — 3 пропуска подряд (§7.13)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.content.loader import load_content
from app.domain.enums import DoseStatus, FlagLevel, FlagReason
from app.models import Flag, SideEffectReport
from app.services.adherence import evaluate_dose_response
from app.services.side_effects import report_alarming_symptom
from tests.factories import NOW, link, make_doctor, make_dose, make_patient, make_prescription

CONTENT = load_content()
D = DoseStatus


@pytest.fixture
def igor(db):
    doctor = make_doctor(db)
    patient = make_patient(db, "Игорь Демо", takes_medication=True)
    link(db, doctor, patient)
    return patient, make_prescription(db, patient, doctor, substance_id="escitalopram")


def answer_doses(db, prescription, statuses):
    raised = []
    for k, status in enumerate(statuses):
        event = make_dose(db, prescription, NOW + timedelta(days=k), status,
                          actual_dose=20 if status is D.SELF_CHANGED else None)
        raised.append(evaluate_dose_response(db, dose_event_id=event.id, now=NOW + timedelta(days=k), content=CONTENT))
    return raised


def test_igor_three_misses_in_a_row_one_yellow_flag(db, igor):
    _, prescription = igor
    assert answer_doses(db, prescription, [D.MISSED, D.MISSED, D.MISSED]) == [[], [FlagReason.MISSED_DOSES], []]
    assert db.scalar(select(func.count()).select_from(Flag)) == 1


def test_no_response_neither_counts_nor_breaks_streak(db, igor):
    _, prescription = igor
    assert answer_doses(db, prescription, [D.MISSED, D.NO_RESPONSE, D.MISSED])[-1] == [FlagReason.MISSED_DOSES]


def test_taken_dose_breaks_streak(db, igor):
    _, prescription = igor
    assert answer_doses(db, prescription, [D.MISSED, D.TAKEN, D.MISSED]) == [[], [], []]


def test_self_dose_change_flags(db, igor):
    _, prescription = igor
    assert answer_doses(db, prescription, [D.SELF_CHANGED]) == [[FlagReason.SELF_DOSE_CHANGE]]


def _symptom(db, patient, code):
    return report_alarming_symptom(db, patient_id=patient.id, code=code, now=NOW, content=CONTENT)


def test_serotonin_syndrome_symptoms_red_flag_and_112(db, igor):
    patient, _ = igor
    result = _symptom(db, patient, "serotonin_syndrome")
    flag = db.get(Flag, result.flag_id)
    assert (flag.level, flag.reason) == (FlagLevel.RED, FlagReason.ALARMING_SYMPTOM)
    assert "112" in result.patient_text
    assert db.scalars(select(SideEffectReport)).one().alarming_symptom_code == "serotonin_syndrome"


def test_akathisia_is_yellow(db, igor):
    patient, _ = igor
    assert db.get(Flag, _symptom(db, patient, "akathisia").flag_id).level is FlagLevel.YELLOW


def test_suicidal_thoughts_symptom_hands_over_to_risk_protocol(db, igor):
    patient, _ = igor
    result = _symptom(db, patient, "suicidal_thoughts")
    assert result.start_risk_protocol and result.flag_id is None


def test_doctor_meaning_never_reaches_patient(db, igor):
    patient, _ = igor
    for symptom in CONTENT.alarming_symptoms.symptoms:
        result = _symptom(db, patient, symptom.code)
        assert symptom.doctor_meaning not in (result.patient_text or "")
