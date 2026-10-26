"""Демо-данные §7.13: порядок в кабинете врача и то, что показываем по каждому персонажу."""

from contextlib import nullcontext
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.content.loader import load_content
from app.domain.enums import DoseStatus, FlagStatus, NotificationStatus, Role
from app.models import (
    DiaryEntry,
    DoseEvent,
    Flag,
    Message,
    Notification,
    OtherMedication,
    PatientProfile,
    QuestionnaireSubmission,
    RiskAssessment,
    SafetyPlan,
)
from app.seed.demo import LOGINS, DemoAlreadySeeded, seed_demo
from app.services.care import active_doctor_id
from app.services.notifications import DevLogPushProvider
from app.services.patients import doctor_queue
from app.services.treatment import treatment_markers
from app.worker import WorkerState, default_jobs, run_due_jobs

CONTENT = load_content()
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))


@pytest.fixture
def demo(db):
    summary = seed_demo(db, now=NOW, content=CONTENT, doctor_password="demo password 2026")
    people = {p.key: db.scalar(select(PatientProfile).where(PatientProfile.full_name == p.full_name))
              for p in summary.people}
    return summary, people


def _open_reasons(db, patient):
    return {f.reason.value for f in db.scalars(select(Flag).where(Flag.patient_id == patient.id,
                                                                  Flag.status == FlagStatus.OPEN))}


def test_doctor_queue_order_maria_igor_anna(db, demo):
    _, people = demo
    queue = doctor_queue(db, active_doctor_id(db, people["anna"].id))
    assert [(i.full_name, i.color) for i in queue] == [
        ("Мария Демо", "red"), ("Игорь Демо", "yellow"), ("Анна Демо", "green")]
    assert "Олег Демо" not in {i.full_name for i in queue}  # пользователь без врача


def test_flags_come_from_real_rules(db, demo):
    _, people = demo
    assert _open_reasons(db, people["anna"]) == set()
    assert _open_reasons(db, people["igor"]) == {"missed_doses", "gad7_increase"}
    assert _open_reasons(db, people["maria"]) == {"risk_block_red"}


def test_anna_progress_with_gaps_and_dose_increase(db, demo):
    _, people = demo
    anna = people["anna"]
    totals = db.scalars(select(QuestionnaireSubmission.total_score)
                        .where(QuestionnaireSubmission.patient_id == anna.id, QuestionnaireSubmission.instrument == "PHQ9")
                        .order_by(QuestionnaireSubmission.submitted_at)).all()
    assert totals == [16, 15, 13, 12, 11, 9, 8]
    days = set(db.scalars(select(DiaryEntry.day).where(DiaryEntry.patient_id == anna.id)))
    start = NOW.date() - timedelta(days=42)
    assert len(days) == 39 and start + timedelta(days=9) not in days  # пропуск — разрыв, а не ноль
    markers = [(m.day - start, m.kind, m.label) for m in treatment_markers(db, anna.id, CONTENT)]
    assert markers == [(timedelta(0), "start", "Начало: Сертралин 50 мг"),
                       (timedelta(days=14), "dose_change", "Доза: Сертралин 100 мг")]


def test_igor_three_missed_doses_and_tramadol(db, demo):
    _, people = demo
    igor = people["igor"]
    statuses = db.scalars(select(DoseEvent.status).where(DoseEvent.patient_id == igor.id,
                                                         DoseEvent.scheduled_at < NOW - timedelta(hours=8))
                          .order_by(DoseEvent.scheduled_at)).all()
    assert statuses[-3:] == [DoseStatus.MISSED] * 3 and DoseStatus.MISSED not in statuses[:-3]
    assert db.scalars(select(OtherMedication.substance_id).where(OtherMedication.patient_id == igor.id)).one() \
        == "tramadol"
    # Врач получил уведомление из блока 9 с результатом проверки взаимодействий (эсциталопрам + трамадол — жёлтое).
    [note] = db.scalars(select(Message).where(Message.patient_id == igor.id, Message.origin == "block9_other_doctor"))
    assert note.body == "Добавлен препарат от другого врача: Трамадол. Проверка взаимодействий: предупреждений: 1."


def test_maria_red_level_and_safety_plan(db, demo):
    _, people = demo
    maria = people["maria"]
    assessment = db.scalars(select(RiskAssessment).where(RiskAssessment.patient_id == maria.id)).one()
    assert (assessment.outcome, assessment.final_level) == ("answered", "red")
    plan = db.scalars(select(SafetyPlan).where(SafetyPlan.patient_id == maria.id)).one()
    assert plan.contacts[0]["phone"].startswith("+7900000")


def test_oleg_is_a_fresh_self_user(db, demo):
    summary, people = demo
    oleg = people["oleg"]
    assert next(p for p in summary.people if p.key == "oleg").role is Role.SELF_USER
    assert active_doctor_id(db, oleg.id) is None
    assert db.scalar(select(func.count()).select_from(QuestionnaireSubmission)
                     .where(QuestionnaireSubmission.patient_id == oleg.id)) == 0  # самопроверка — вживую


def test_only_fictional_demo_logins(demo):
    summary, _ = demo
    assert {p.login for p in summary.people} == set(LOGINS.values())
    assert all(login.startswith("+7900000000") for login in LOGINS.values())
    assert summary.doctor_email.endswith(".test")


def test_no_stale_reminders_left_from_history(db, demo):
    stale = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.status == NotificationStatus.SCHEDULED, Notification.scheduled_for < NOW - timedelta(hours=1)))
    assert stale == 0


def test_seeding_twice_is_refused(db, demo):
    with pytest.raises(DemoAlreadySeeded):
        seed_demo(db, now=NOW, content=CONTENT, doctor_password="demo password 2026")


def test_worker_runs_cleanly_over_demo_data(db, demo):
    outcomes = run_due_jobs(lambda: nullcontext(db), now=NOW, jobs=default_jobs(CONTENT, DevLogPushProvider()),
                            state=WorkerState())
    assert [(o.name, o.ok) for o in outcomes] == [("doses", True), ("weekly_questionnaires", True),
                                                  ("diary_reminders", True), ("no_data", True), ("dispatch", True)]
    # Врач получил push о флагах Марии и Игоря — нейтральным текстом.
    sent = db.scalars(select(Notification).where(Notification.status == NotificationStatus.SENT)).all()
    assert {n.title for n in sent} >= {"Красный флаг", "Новая отметка"}
