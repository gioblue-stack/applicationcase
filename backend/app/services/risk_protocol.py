"""Протокол при суицидальном риске: оркестрация поверх доменных правил (§4.6, §7.1).

В одной транзакции: сохранить ответы уточняющего блока, поставить флаг врачу,
поставить push в очередь и записать действие в журнал доступа. Вызывающий код делает commit.
Уровень всегда пересчитывается здесь — клиентскому значению сервер не доверяет.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.loader import load_content
from app.content.models import Content
from app.domain import risk_protocol
from app.domain.enums import AuditAction, InstrumentCode, ResponseLevel, RiskTrigger
from app.domain.flag_rules import FlagCandidate
from app.domain.risk_protocol import BlockAnswers, NextStep
from app.models import Flag, QuestionnaireAnswer, QuestionnaireSubmission, RiskAssessment, RiskFactors
from app.services import audit
from app.services.care import PatientNotFound, active_doctor_id, get_patient, local_now
from app.services.flags import note_patient_activity, raise_flag
from app.services.screens import HelpScreen, build_screen


class RiskProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class RiskAssessmentResult:
    assessment_id: uuid.UUID
    final_level: ResponseLevel
    flag_id: uuid.UUID
    screen: HelpScreen
    created: bool  # False — повторная отправка того же client_id (оффлайн-синхронизация)


@dataclass(frozen=True)
class Phq9Decision:
    next_step: NextStep
    screen: HelpScreen | None  # для пользователя без врача — экран помощи сразу


def _patient(db: Session, patient_id: uuid.UUID):
    try:
        return get_patient(db, patient_id)
    except PatientNotFound as e:
        raise RiskProtocolError(str(e)) from e


def _phq9_item9(db: Session, submission: QuestionnaireSubmission, content: Content) -> int:
    value = db.scalar(
        select(QuestionnaireAnswer.value).where(
            QuestionnaireAnswer.submission_id == submission.id,
            QuestionnaireAnswer.item_no == content.phq9.safety_item,
        )
    )
    if value is None:
        raise RiskProtocolError("В опроснике нет ответа на 9-й вопрос")
    return value


def _own_phq9(db: Session, patient_id: uuid.UUID, submission_id: uuid.UUID | None) -> QuestionnaireSubmission:
    submission = db.get(QuestionnaireSubmission, submission_id) if submission_id else None
    if submission is None or submission.patient_id != patient_id:
        raise RiskProtocolError("Опросник не найден у этого пациента")
    if submission.instrument != InstrumentCode.PHQ9:
        raise RiskProtocolError("Уточняющий блок по опроснику запускается только из PHQ-9")
    return submission


def decide_after_phq9(
    db: Session, *, patient_id: uuid.UUID, submission_id: uuid.UUID, content: Content | None = None
) -> Phq9Decision:
    content = content or load_content()
    patient = _patient(db, patient_id)
    submission = _own_phq9(db, patient_id, submission_id)
    step = risk_protocol.next_step_after_phq9(
        _phq9_item9(db, submission, content),
        has_treating_doctor=active_doctor_id(db, patient_id) is not None,
    )
    screen = build_screen(content, "self_user_help", patient.region_code) if step is NextStep.SELF_USER_HELP else None
    return Phq9Decision(next_step=step, screen=screen)


def last_assessment_day(db: Session, patient, now: datetime) -> date | None:
    """День (в таймзоне пациента) последнего уточняющего блока — чтобы не предлагать его повторно."""
    last = db.scalar(
        select(RiskAssessment.submitted_at)
        .where(RiskAssessment.patient_id == patient.id)
        .order_by(RiskAssessment.submitted_at.desc())
        .limit(1)
    )
    return local_now(patient, last).date() if last is not None else None


def assessed_today(db: Session, patient, now: datetime) -> bool:
    return last_assessment_day(db, patient, now) == local_now(patient, now).date()


def _replay(db: Session, existing: RiskAssessment, patient_id: uuid.UUID, content: Content) -> RiskAssessmentResult:
    if existing.patient_id != patient_id:
        raise RiskProtocolError("client_id уже использован другим пациентом")
    flag_id = db.scalar(
        select(Flag.id).where(Flag.source_type == "risk_assessment", Flag.source_id == existing.id)
    )
    assert flag_id is not None, "у каждой оценки есть флаг: они создаются в одной транзакции"
    answers = BlockAnswers(**{q: getattr(existing, q) for q in risk_protocol.QUESTION_IDS})
    screen_key = risk_protocol.assess(answers, has_risk_factors=existing.risk_factors_present).patient_screen
    return RiskAssessmentResult(
        assessment_id=existing.id,
        final_level=existing.final_level,
        flag_id=flag_id,
        screen=build_screen(content, screen_key, _patient(db, patient_id).region_code),
        created=False,
    )


def record_risk_assessment(
    db: Session,
    *,
    patient_id: uuid.UUID,
    client_id: uuid.UUID,
    trigger: RiskTrigger,
    trigger_ref: uuid.UUID | None,
    answers: Mapping[str, object],
    client_submitted_at: datetime,
    started_at: datetime | None = None,
    content: Content | None = None,
    now: datetime | None = None,
) -> RiskAssessmentResult:
    """Сохраняет уточняющий блок. Пустые answers = «Не сейчас» / закрыт без ответа."""
    content = content or load_content()
    now = now or datetime.now(UTC)

    existing = db.scalar(select(RiskAssessment).where(RiskAssessment.client_id == client_id))
    if existing is not None:
        return _replay(db, existing, patient_id, content)

    patient = _patient(db, patient_id)
    if active_doctor_id(db, patient_id) is None:
        raise RiskProtocolError(
            "Уточняющий блок проводится только у пациента с лечащим врачом; "
            "пользователю без врача показывается экран помощи"
        )

    parsed = BlockAnswers.from_mapping(answers)
    if trigger is RiskTrigger.PHQ9_ITEM9:
        submission = _own_phq9(db, patient_id, trigger_ref)
        if _phq9_item9(db, submission, content) == 0:
            raise RiskProtocolError("На 9-й вопрос PHQ-9 ответ «Ни разу» — уточняющий блок не запускается")

    factors = db.get(RiskFactors, patient_id)
    has_factors = factors is not None and factors.any_present
    result = risk_protocol.assess(parsed, has_risk_factors=has_factors)

    assessment = RiskAssessment(
        client_id=client_id,
        patient_id=patient_id,
        trigger=trigger,
        trigger_ref=trigger_ref,
        block_version=content.suicide_block.version,
        **{q: getattr(parsed, q) for q in risk_protocol.QUESTION_IDS},
        outcome=result.outcome,
        base_level=result.base_level,
        final_level=result.final_level,
        risk_factors_present=has_factors,
        escalated_by_risk_factors=result.escalated_by_risk_factors,
        started_at=started_at,
        client_submitted_at=client_submitted_at,
        submitted_at=now,
    )
    db.add(assessment)
    db.flush()

    flag = raise_flag(
        db,
        FlagCandidate(
            result.flag_level,
            result.flag_reason,
            f"risk_assessment:{assessment.id}",
            {"final_level": result.final_level.value, "outcome": result.outcome.value},
        ),
        patient_id=patient_id,
        source_type="risk_assessment",
        source_id=assessment.id,
        now=now,
        priority=result.doctor_push,
    )
    assert flag is not None, "у пациента есть врач, а ключ флага уникален для каждой оценки"
    note_patient_activity(db, patient_id, now)
    audit.record(
        db,
        actor_account_id=patient.account_id,
        actor_role="patient",
        action=AuditAction.CREATE,
        entity="risk_assessment",
        entity_id=assessment.id,
        patient_id=patient_id,
        meta={"trigger": trigger.value, "final_level": result.final_level.value},
    )
    db.flush()

    return RiskAssessmentResult(
        assessment_id=assessment.id,
        final_level=result.final_level,
        flag_id=flag.id,
        screen=build_screen(content, result.patient_screen, patient.region_code),
        created=True,
    )
