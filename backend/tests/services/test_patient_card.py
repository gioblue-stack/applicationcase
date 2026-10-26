"""Карточка пациента на демо-данных §7.13: врач видит то, что показываем на презентации."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.content.loader import load_content
from app.domain.enums import DoseStatus, InstrumentCode
from app.models import PatientProfile
from app.seed.demo import seed_demo
from app.services import patient_card, safety_plan
from app.services.care import active_doctor_id
from app.services.questionnaires import submit_weekly
from app.services.side_effects import report_alarming_symptom

CONTENT = load_content()
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
TODAY = NOW.date()


@pytest.fixture
def people(db):
    summary = seed_demo(db, now=NOW, content=CONTENT, doctor_password="demo password 2026")
    return {p.key: db.scalar(select(PatientProfile).where(PatientProfile.full_name == p.full_name))
            for p in summary.people}


def test_anna_month_chart_has_gaps_and_dose_marker(db, people):
    chart = patient_card.diary_chart(db, people["anna"].id, period="month", now=NOW, content=CONTENT)
    assert (chart.start, chart.end, len(chart.series.days)) == (TODAY - timedelta(days=29), TODAY, 30)
    mood = dict(zip(chart.series.days, chart.series.values["mood"], strict=True))
    for gap in (TODAY - timedelta(days=19), TODAY - timedelta(days=12), TODAY):
        assert mood[gap] is None  # пропуск — разрыв линии
    assert chart.series.filled_days == 27
    assert [(m.day, m.kind) for m in chart.markers] == [(TODAY - timedelta(days=28), "dose_change")]


def test_anna_whole_period_starts_at_treatment_start(db, people):
    chart = patient_card.diary_chart(db, people["anna"].id, period="all", now=NOW, content=CONTENT)
    assert chart.start == TODAY - timedelta(days=42)
    assert [m.kind for m in chart.markers] == ["start", "dose_change"]


def test_anna_phq9_by_weeks_with_answers(db, people):
    phq9, gad7 = patient_card.questionnaire_history(db, people["anna"].id, CONTENT)
    assert [p.total for p in phq9.points] == [16, 15, 13, 12, 11, 9, 8]
    assert (phq9.points[0].change, phq9.points[-1].change) == (None, -1)
    assert (phq9.points[0].severity, phq9.points[-1].severity) == ("Умеренно тяжёлая", "Лёгкая")
    last = phq9.points[-1]
    assert [a.no for a in last.answers] == list(range(1, 10))
    assert last.answers[8].text == CONTENT.phq9.items[8].text and last.safety_item_positive is False
    assert sum(a.value for a in last.answers) == 8
    assert (gad7.threshold, [p.total for p in gad7.points][-1]) == (4, 6)


def test_refill_shows_both_versions_and_compares_with_valid_one(db, people):
    anna = people["anna"]
    phq9 = patient_card.questionnaire_history(db, anna.id, CONTENT)[0]
    wrong_id = phq9.points[-1].submission_id
    submit_weekly(db, patient_id=anna.id, client_id=uuid.uuid4(), instrument=InstrumentCode.PHQ9,
                  answers=[1, 1, 1, 1, 1, 1, 1, 0, 0], supersedes_id=wrong_id, client_submitted_at=NOW, now=NOW,
                  content=CONTENT)
    points = patient_card.questionnaire_history(db, anna.id, CONTENT)[0].points
    replaced = next(p for p in points if p.submission_id == wrong_id)
    assert replaced.superseded_by == points[-1].submission_id and replaced.change is None
    assert (points[-1].total, points[-1].change) == (7, -2)  # к 9 баллам прошлой недели, а не к ошибочным 8


def test_igor_adherence_week_and_month(db, people):
    [row] = patient_card.adherence(db, people["igor"].id, now=NOW, content=CONTENT)
    assert (row.inn, row.active) == ("Эсциталопрам", True)
    assert (row.week.due, row.week.taken, row.week.missed, row.week.taken_percent) == (7, 4, 3, 57.1)
    assert (row.month.due, row.month.taken_percent) == (30, 90.0)
    assert [i.status for i in row.issues] == [DoseStatus.MISSED] * 3
    assert row.issues[0].scheduled_at > row.issues[-1].scheduled_at  # свежие сверху


def test_side_effect_journal_with_doctor_only_meaning(db, people):
    anna, igor = people["anna"], people["igor"]
    journal = patient_card.side_effect_journal(db, anna.id, CONTENT)
    assert [e.label for e in journal] == ["Тошнота"] * 6
    assert [e.is_new for e in journal] == [False] * 5 + [True]
    report_alarming_symptom(db, patient_id=igor.id, code="serotonin_syndrome", now=NOW, content=CONTENT)
    [entry] = patient_card.side_effect_journal(db, igor.id, CONTENT)
    assert (entry.alarming, entry.doctor_meaning) == (True, "Серотониновый синдром")


def test_maria_risk_block_answers_for_doctor(db, people):
    [view] = patient_card.risk_assessments(db, people["maria"].id, CONTENT)
    assert (view.final_level, view.outcome) == ("red", "answered")
    assert [(a.id, a.answer) for a in view.answers] == [
        ("q1", True), ("q2", True), ("q3", False), ("q4", False), ("q5", False), ("q6", False)]
    assert view.answers[1].text == "За последнюю неделю думали ли вы о том, чтобы покончить с собой?"


def test_card_summaries(db, people):
    maria = patient_card.card_summary(db, people["maria"].id, now=NOW, content=CONTENT)
    assert (maria.color, maria.connected, maria.age) == ("red", True, 27)
    assert [(d.code, d.title) for d in maria.diagnoses] == [
        ("F33.1", "Рекуррентное депрессивное расстройство, текущий эпизод средней степени")]
    assert {(s.instrument, s.total) for s in maria.latest_scores} == {("PHQ9", 16), ("GAD7", 12)}
    assert maria.safety_plan_version == 1 and maria.safety_plan_reviewed_at is not None
    assert [t.inn for t in maria.treatment] == ["Венлафаксин"]

    igor = patient_card.card_summary(db, people["igor"].id, now=NOW, content=CONTENT)
    assert (igor.color, igor.adherence_week_percent, igor.risk_factors) == ("yellow", 57.1, None)
    assert [m.name for m in igor.other_medications] == ["Трамадол"]
    gad7 = next(s for s in igor.latest_scores if s.instrument == "GAD7")
    assert (gad7.change, gad7.significant_change) == (5, True)

    anna = patient_card.card_summary(db, people["anna"].id, now=NOW, content=CONTENT)
    assert (anna.color, anna.open_flags, anna.titration_attention) == ("green", [], [])


def test_safety_plan_versions_and_review(db, people):
    maria = people["maria"]
    doctor_id = active_doctor_id(db, maria.id)
    with pytest.raises(safety_plan.SafetyPlanError, match="хотя бы один"):
        safety_plan.save_by_patient(db, patient=maria, data=safety_plan.SafetyPlanInput(warning_signs="  "), now=NOW)
    saved = safety_plan.save_by_patient(db, patient=maria, now=NOW, data=safety_plan.SafetyPlanInput(
        warning_signs="Не сплю ночами", contacts=[safety_plan.Contact("Подруга (демо)", "+79000000098")]))
    assert (saved.version, saved.versions_total, saved.updated_by_role, saved.doctor_reviewed_at) == (
        2, 2, "patient", None)
    reviewed = safety_plan.mark_reviewed(db, doctor_account_id=doctor_id, patient_id=maria.id, now=NOW)
    assert reviewed.doctor_reviewed_at == NOW
    with pytest.raises(safety_plan.SafetyPlanError, match="ещё не заполнен"):
        safety_plan.mark_reviewed(db, doctor_account_id=doctor_id, patient_id=people["oleg"].id, now=NOW)
