"""PHQ-9 и GAD-7: еженедельное заполнение пациентом и самопроверка пользователя (§3.1, §4.2–4.5)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.content.loader import load_content
from app.content.models import Content
from app.domain import flag_rules, scoring
from app.domain.enums import (
    AuditAction,
    FlagReason,
    InstrumentCode,
    ScheduleStatus,
    SubmissionContext,
)
from app.domain.questionnaire_feedback import PatientFeedback, SelfCheckLevel, patient_feedback, self_check_level
from app.domain.weekly_schedule import next_self_check_at
from app.models import QuestionnaireAnswer, QuestionnaireSchedule, QuestionnaireSubmission
from app.services import audit
from app.services.care import active_doctor_id, get_patient, local_now
from app.services.flags import note_patient_activity, raise_flag
from app.services.risk_protocol import Phq9Decision, decide_after_phq9
from app.services.screens import HelpScreen, build_screen
from app.services.thresholds import get_thresholds

_INCREASE_THRESHOLD = {InstrumentCode.PHQ9: "phq9_increase_yellow", InstrumentCode.GAD7: "gad7_increase_yellow"}


class QuestionnaireError(ValueError):
    pass


class SelfCheckTooSoon(QuestionnaireError):
    def __init__(self, available_at: datetime) -> None:
        super().__init__("Повторить проверку можно не раньше чем через 2 недели")
        self.available_at = available_at


@dataclass(frozen=True)
class WeeklyResult:
    submission_id: uuid.UUID
    instrument: InstrumentCode
    total: int
    created: bool
    feedback: PatientFeedback
    raised_flags: list[FlagReason]
    risk: Phq9Decision | None  # только для PHQ-9: нужен ли уточняющий блок


@dataclass(frozen=True)
class SelfCheckResult:
    phq9_submission_id: uuid.UUID
    gad7_submission_id: uuid.UUID
    level: SelfCheckLevel
    text: str
    actions: list[str]
    screening_note: str
    help_screen: HelpScreen | None  # 9-й вопрос ≠ «Ни разу» — независимо от суммы (§3.1)


def _effective_previous(
    db: Session, patient_id: uuid.UUID, instrument: InstrumentCode, context: SubmissionContext,
    exclude_id: uuid.UUID | None,
) -> QuestionnaireSubmission | None:
    """Последнее действующее заполнение: заменённые повторным заполнением не учитываются."""
    superseded = select(QuestionnaireSubmission.supersedes_id).where(QuestionnaireSubmission.supersedes_id.is_not(None))
    query = (
        select(QuestionnaireSubmission)
        .where(
            QuestionnaireSubmission.patient_id == patient_id,
            QuestionnaireSubmission.instrument == instrument,
            QuestionnaireSubmission.context == context,
            QuestionnaireSubmission.id.not_in(superseded),
        )
        .order_by(QuestionnaireSubmission.submitted_at.desc())
        .limit(1)
    )
    if exclude_id is not None:
        query = query.where(QuestionnaireSubmission.id != exclude_id)
    return db.scalar(query)


def _insert(
    db: Session, *, patient_id: uuid.UUID, client_id: uuid.UUID, instrument: InstrumentCode, version: str,
    context: SubmissionContext, answers: Sequence[int], total: int, difficulty: int | None,
    schedule_id: uuid.UUID | None, supersedes_id: uuid.UUID | None, client_submitted_at: datetime, now: datetime,
) -> QuestionnaireSubmission:
    submission = QuestionnaireSubmission(
        client_id=client_id, patient_id=patient_id, instrument=instrument, instrument_version=version,
        context=context, schedule_id=schedule_id, supersedes_id=supersedes_id, total_score=total,
        difficulty=difficulty, client_submitted_at=client_submitted_at, submitted_at=now,
    )
    db.add(submission)
    db.flush()
    db.add_all(
        QuestionnaireAnswer(submission_id=submission.id, item_no=no, value=value)
        for no, value in enumerate(answers, start=1)
    )
    db.flush()
    return submission


def _validate_difficulty(instrument: InstrumentCode, difficulty: int | None) -> None:
    if difficulty is None:
        return
    if instrument is not InstrumentCode.PHQ9:
        raise QuestionnaireError("Вопрос о трудностях есть только в PHQ-9")
    if isinstance(difficulty, bool) or difficulty not in (0, 1, 2, 3):
        raise QuestionnaireError("Недопустимый ответ на вопрос о трудностях")


def _open_slot(db: Session, patient_id: uuid.UUID, today) -> QuestionnaireSchedule | None:
    return db.scalar(
        select(QuestionnaireSchedule)
        .where(
            QuestionnaireSchedule.patient_id == patient_id,
            QuestionnaireSchedule.status.in_([ScheduleStatus.PENDING, ScheduleStatus.REMINDED]),
            QuestionnaireSchedule.due_date <= today,
        )
        .order_by(QuestionnaireSchedule.due_date.desc())
        .limit(1)
    )


@dataclass(frozen=True)
class WeeklyDue:
    due_date: date
    pending: list[InstrumentCode]  # что ещё не заполнено в этом слоте, по порядку показа


def weekly_due(db: Session, patient_id: uuid.UUID, now: datetime) -> WeeklyDue | None:
    """Открытый еженедельный слот: PHQ-9 и GAD-7, которые пациент ещё не заполнил."""
    slot = _open_slot(db, patient_id, local_now(get_patient(db, patient_id), now).date())
    if slot is None:
        return None
    done = set(db.scalars(select(QuestionnaireSubmission.instrument).where(QuestionnaireSubmission.schedule_id == slot.id)))
    return WeeklyDue(slot.due_date, [i for i in InstrumentCode if i not in done])


def _close_slot_if_complete(db: Session, slot: QuestionnaireSchedule, now: datetime) -> None:
    done = db.scalar(
        select(func.count(func.distinct(QuestionnaireSubmission.instrument))).where(
            QuestionnaireSubmission.schedule_id == slot.id
        )
    )
    if done == len(InstrumentCode):
        slot.status = ScheduleStatus.DONE
        slot.closed_at = now


def submit_weekly(
    db: Session,
    *,
    patient_id: uuid.UUID,
    client_id: uuid.UUID,
    instrument: InstrumentCode,
    answers: Sequence[int],
    client_submitted_at: datetime,
    difficulty: int | None = None,
    supersedes_id: uuid.UUID | None = None,
    now: datetime | None = None,
    content: Content | None = None,
) -> WeeklyResult:
    content = content or load_content()
    now = now or datetime.now(UTC)
    definition = content.instrument(instrument)
    t = get_thresholds(db, content)
    threshold = int(t[_INCREASE_THRESHOLD[instrument]])

    existing = db.scalar(select(QuestionnaireSubmission).where(QuestionnaireSubmission.client_id == client_id))
    if existing is not None:
        if existing.patient_id != patient_id:
            raise QuestionnaireError("client_id уже использован другим пациентом")
        previous = _effective_previous(db, patient_id, instrument, SubmissionContext.WEEKLY, existing.id)
        return WeeklyResult(
            existing.id, instrument, existing.total_score, False,
            patient_feedback(content.patient_texts, instrument, existing.total_score,
                             previous.total_score if previous else None, threshold=threshold),
            [], decide_after_phq9(db, patient_id=patient_id, submission_id=existing.id, content=content)
            if instrument is InstrumentCode.PHQ9 else None,
        )

    patient = get_patient(db, patient_id)
    if active_doctor_id(db, patient_id) is None:
        raise QuestionnaireError("Еженедельные опросники — для пациента с лечащим врачом; пользователю — самопроверка")
    try:
        total = scoring.total_score(definition, answers)
    except scoring.InvalidQuestionnaire as e:
        raise QuestionnaireError(str(e)) from e
    _validate_difficulty(instrument, difficulty)

    slot_id = None
    if supersedes_id is not None:
        replaced = db.get(QuestionnaireSubmission, supersedes_id)
        if replaced is None or replaced.patient_id != patient_id or replaced.instrument != instrument:
            raise QuestionnaireError("Повторно заполнить можно только свой опросник того же типа")
        slot_id = replaced.schedule_id
    else:
        slot = _open_slot(db, patient_id, local_now(patient, now).date())
        slot_id = slot.id if slot else None

    previous = _effective_previous(db, patient_id, instrument, SubmissionContext.WEEKLY, supersedes_id)
    submission = _insert(
        db, patient_id=patient_id, client_id=client_id, instrument=instrument, version=definition.version,
        context=SubmissionContext.WEEKLY, answers=answers, total=total, difficulty=difficulty,
        schedule_id=slot_id, supersedes_id=supersedes_id, client_submitted_at=client_submitted_at, now=now,
    )
    if slot_id is not None:
        _close_slot_if_complete(db, db.get(QuestionnaireSchedule, slot_id), now)
    note_patient_activity(db, patient_id, now)
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="questionnaire_submission", entity_id=submission.id, patient_id=patient_id,
                 meta={"instrument": instrument.value})

    raised: list[FlagReason] = []
    previous_total = previous.total_score if previous else None
    candidate = flag_rules.score_increase(instrument, previous_total=previous_total, new_total=total,
                                          threshold=threshold, submission_id=submission.id)
    if candidate and raise_flag(db, candidate, patient_id=patient_id, source_type="questionnaire_submission",
                                source_id=submission.id, now=now):
        raised.append(candidate.reason)

    risk = None
    if instrument is InstrumentCode.PHQ9:
        risk = decide_after_phq9(db, patient_id=patient_id, submission_id=submission.id, content=content)

    db.flush()
    return WeeklyResult(
        submission.id, instrument, total, True,
        patient_feedback(content.patient_texts, instrument, total, previous_total, threshold=threshold),
        raised, risk,
    )


def submit_self_check(
    db: Session,
    *,
    patient_id: uuid.UUID,
    phq9_client_id: uuid.UUID,
    gad7_client_id: uuid.UUID,
    phq9_answers: Sequence[int],
    gad7_answers: Sequence[int],
    client_submitted_at: datetime,
    difficulty: int | None = None,
    now: datetime | None = None,
    content: Content | None = None,
) -> SelfCheckResult:
    """Самопроверка пользователя без врача: PHQ-9 и GAD-7 вместе, не чаще раза в 14 дней. Флагов нет."""
    content = content or load_content()
    now = now or datetime.now(UTC)
    patient = get_patient(db, patient_id)

    phq9 = db.scalar(select(QuestionnaireSubmission).where(QuestionnaireSubmission.client_id == phq9_client_id))
    gad7 = db.scalar(select(QuestionnaireSubmission).where(QuestionnaireSubmission.client_id == gad7_client_id))
    if phq9 is None and gad7 is None:
        if active_doctor_id(db, patient_id) is not None:
            raise QuestionnaireError("У пациента с врачом — еженедельные опросники, а не самопроверка")
        try:
            phq9_total = scoring.total_score(content.phq9, phq9_answers)
            gad7_total = scoring.total_score(content.gad7, gad7_answers)
        except scoring.InvalidQuestionnaire as e:
            raise QuestionnaireError(str(e)) from e
        _validate_difficulty(InstrumentCode.PHQ9, difficulty)

        t = get_thresholds(db, content)
        last = _effective_previous(db, patient_id, InstrumentCode.PHQ9, SubmissionContext.SELF_CHECK, None)
        available_at = next_self_check_at(last.submitted_at if last else None,
                                          min_interval_days=int(t["self_check_min_interval_days"]))
        if available_at is not None and now < available_at:
            raise SelfCheckTooSoon(available_at)

        common = dict(patient_id=patient_id, context=SubmissionContext.SELF_CHECK, schedule_id=None,
                      supersedes_id=None, client_submitted_at=client_submitted_at, now=now)
        phq9 = _insert(db, client_id=phq9_client_id, instrument=InstrumentCode.PHQ9, version=content.phq9.version,
                       answers=phq9_answers, total=phq9_total, difficulty=difficulty, **common)
        gad7 = _insert(db, client_id=gad7_client_id, instrument=InstrumentCode.GAD7, version=content.gad7.version,
                       answers=gad7_answers, total=gad7_total, difficulty=None, **common)
        audit.record(db, actor_account_id=patient.account_id, actor_role="self_user", action=AuditAction.CREATE,
                     entity="self_check", entity_id=phq9.id, patient_id=patient_id)
    elif phq9 is None or gad7 is None or phq9.patient_id != patient_id or gad7.patient_id != patient_id:
        raise QuestionnaireError("Повторная отправка не совпадает с сохранённой самопроверкой")

    item9 = db.scalar(select(QuestionnaireAnswer.value).where(
        QuestionnaireAnswer.submission_id == phq9.id, QuestionnaireAnswer.item_no == content.phq9.safety_item))
    level = self_check_level(phq9.total_score, gad7.total_score)
    texts = content.patient_texts.self_check
    chosen = getattr(texts, level.value)
    db.flush()
    return SelfCheckResult(
        phq9.id, gad7.id, level, chosen.text, list(chosen.actions), texts.screening_note,
        build_screen(content, "self_user_help", patient.region_code) if item9 else None,
    )
