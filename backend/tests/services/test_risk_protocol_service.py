"""Сервис протокола суицидального риска на реальной БД. Сценарий Марии — §7.13."""

import uuid

import pytest
from sqlalchemy import func, select

from app.domain.enums import (
    AuditAction,
    FlagLevel,
    FlagReason,
    FlagStatus,
    NotificationKind,
    PushPriority,
    ResponseLevel,
    RiskTrigger,
    Role,
)
from app.domain.risk_protocol import InvalidAnswers, NextStep
from app.models import AuditLog, Flag, Notification, RiskAssessment
from app.services.risk_protocol import RiskProtocolError, decide_after_phq9, record_risk_assessment
from tests.factories import NOW, link, make_doctor, make_patient, make_phq9, set_risk_factors

ACTIVE_NO_PLAN = {"q1": True, "q2": True, "q3": False, "q4": False, "q5": False, "q6": False}


@pytest.fixture
def maria(db):
    """Мария, F33.1, венлафаксин; «Несколько дней» на 9-й вопрос PHQ-9 (§7.13)."""
    doctor = make_doctor(db)
    patient = make_patient(db, "Мария Демо", region_code="moscow")
    link(db, doctor, patient)
    submission = make_phq9(db, patient, [2, 2, 1, 2, 1, 2, 1, 0, 1])
    return doctor, patient, submission


def _record(db, patient, submission, answers, client_id=None):
    return record_risk_assessment(
        db,
        patient_id=patient.id,
        client_id=client_id or uuid.uuid4(),
        trigger=RiskTrigger.PHQ9_ITEM9,
        trigger_ref=submission.id,
        answers=answers,
        client_submitted_at=NOW,
        now=NOW,
    )


def test_phq9_item9_positive_starts_risk_block_for_patient(db, maria):
    _, patient, submission = maria
    decision = decide_after_phq9(db, patient_id=patient.id, submission_id=submission.id)
    assert decision.next_step is NextStep.RISK_BLOCK
    assert decision.screen is None


def test_maria_active_thoughts_red_flag_urgent_push_and_help_screen(db, maria):
    doctor, patient, submission = maria
    result = _record(db, patient, submission, ACTIVE_NO_PLAN)

    assert result.created
    assert result.final_level is ResponseLevel.RED

    flag = db.get(Flag, result.flag_id)
    assert (flag.level, flag.reason, flag.status) == (FlagLevel.RED, FlagReason.RISK_BLOCK_RED, FlagStatus.OPEN)
    assert flag.source_id == result.assessment_id

    push = db.scalars(select(Notification).where(Notification.related_flag_id == flag.id)).one()
    assert push.recipient_account_id == doctor.account_id
    assert push.kind is NotificationKind.RED_FLAG
    assert push.priority is PushPriority.URGENT

    screen = result.screen
    assert screen.key == "red"
    assert [a.action for a in screen.actions] == ["call_helpline", "open_safety_plan", "call_112"]
    assert [p.id for p in screen.phones] == ["112", "8-800-100-49-94", "msk-051"]
    assert screen.helpline.id == "8-800-100-49-94"

    audit = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(result.assessment_id))).one()
    assert (audit.action, audit.actor_account_id, audit.patient_id) == (
        AuditAction.CREATE, patient.account_id, patient.id,
    )


def test_doctor_push_reveals_nothing_on_lock_screen(db, maria):
    _, patient, submission = maria
    result = _record(db, patient, submission, ACTIVE_NO_PLAN)
    push = db.scalars(select(Notification).where(Notification.related_flag_id == result.flag_id)).one()
    text = f"{push.title} {push.body_neutral}".lower()
    for sensitive in ("мария", "суицид", "самоубий", "phq", "венлафаксин", "f33"):
        assert sensitive not in text


def test_dismissed_block_still_red_flag_and_help_screen(db, maria):
    _, patient, submission = maria
    result = _record(db, patient, submission, {})
    flag = db.get(Flag, result.flag_id)
    assert (flag.level, flag.reason) == (FlagLevel.RED, FlagReason.RISK_BLOCK_DISMISSED)
    assert result.screen.key == "dismissed"
    assert result.screen.fullscreen
    assert db.get(RiskAssessment, result.assessment_id).outcome == "dismissed"


def test_dismissed_with_risk_factors_escalates_to_emergency(db, maria):
    doctor, patient, submission = maria
    set_risk_factors(db, patient, doctor, prior_suicide_attempt=True)
    result = _record(db, patient, submission, {})
    assert result.final_level is ResponseLevel.EMERGENCY
    row = db.get(RiskAssessment, result.assessment_id)
    assert (row.base_level, row.risk_factors_present, row.escalated_by_risk_factors) == ("red", True, True)
    push = db.scalars(select(Notification).where(Notification.related_flag_id == result.flag_id)).one()
    assert push.priority is PushPriority.IMMEDIATE


def test_risk_factors_row_without_factors_does_not_escalate(db, maria):
    doctor, patient, submission = maria
    set_risk_factors(db, patient, doctor)
    assert _record(db, patient, submission, ACTIVE_NO_PLAN).final_level is ResponseLevel.RED


def test_passive_thoughts_yellow_flag_normal_priority(db, maria):
    _, patient, submission = maria
    result = _record(db, patient, submission, {"q1": True, "q2": False, "q6": False})
    flag = db.get(Flag, result.flag_id)
    assert (flag.level, flag.reason) == (FlagLevel.YELLOW, FlagReason.RISK_BLOCK_YELLOW)
    push = db.scalars(select(Notification).where(Notification.related_flag_id == flag.id)).one()
    assert (push.kind, push.priority) == (NotificationKind.YELLOW_FLAG, PushPriority.NORMAL)
    assert {a.action for a in result.screen.actions} >= {"open_safety_plan"}


def test_resubmitting_same_client_id_is_idempotent(db, maria):
    _, patient, submission = maria
    client_id = uuid.uuid4()
    first = _record(db, patient, submission, ACTIVE_NO_PLAN, client_id=client_id)
    again = _record(db, patient, submission, ACTIVE_NO_PLAN, client_id=client_id)
    assert not again.created
    assert (again.assessment_id, again.flag_id, again.screen.key) == (first.assessment_id, first.flag_id, "red")
    assert db.scalar(select(func.count()).select_from(Flag).where(Flag.patient_id == patient.id)) == 1


def test_block_requires_positive_item9(db, maria):
    _, patient, _ = maria
    calm = make_phq9(db, patient, [1] * 8 + [0])
    with pytest.raises(RiskProtocolError, match="Ни разу"):
        _record(db, patient, calm, ACTIVE_NO_PLAN)


def test_block_rejects_other_patients_questionnaire(db, maria):
    doctor, patient, _ = maria
    other = make_patient(db, "Другой Пациент")
    link(db, doctor, other)
    foreign = make_phq9(db, other, [0] * 8 + [2])
    with pytest.raises(RiskProtocolError, match="не найден"):
        _record(db, patient, foreign, ACTIVE_NO_PLAN)


def test_invalid_answers_save_nothing(db, maria):
    _, patient, submission = maria
    with pytest.raises(InvalidAnswers):
        _record(db, patient, submission, {"q1": True, "q2": False, "q4": True})
    assert db.scalar(select(func.count()).select_from(RiskAssessment)) == 0
    assert db.scalar(select(func.count()).select_from(Flag)) == 0


def test_self_user_gets_help_screen_without_block_or_flag(db):
    oleg = make_patient(db, "Олег Демо", region_code=None, role=Role.SELF_USER)
    submission = make_phq9(db, oleg, [2, 1, 2, 1, 1, 2, 1, 1, 1])
    decision = decide_after_phq9(db, patient_id=oleg.id, submission_id=submission.id)
    assert decision.next_step is NextStep.SELF_USER_HELP
    assert decision.screen.key == "self_user_help"
    assert decision.screen.fullscreen
    assert [p.id for p in decision.screen.phones] == ["112", "8-800-100-49-94"]
    with pytest.raises(RiskProtocolError, match="лечащим врачом"):
        _record(db, oleg, submission, {})
    assert db.scalar(select(func.count()).select_from(Flag)) == 0
