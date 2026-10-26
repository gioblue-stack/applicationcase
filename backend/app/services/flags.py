"""Флаги срочности: постановка, закрытие врачом, автозакрытие «нет данных» (§1.1, В6).

Флаг ставится только пациенту с лечащим врачом — у пользователя без врача флаги видеть некому.
Повтор открытого флага с тем же dedupe_key не создаётся (частичный уникальный индекс).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain import flag_rules
from app.domain.enums import (
    AuditAction,
    CareLinkStatus,
    FlagLevel,
    FlagReason,
    FlagStatus,
    MessageDirection,
    NotificationKind,
    PushPriority,
)
from app.domain.flag_rules import FlagCandidate
from app.models import (
    CareLink,
    DiaryEntry,
    DoseEvent,
    Flag,
    Message,
    Notification,
    PanicEvent,
    QuestionnaireSubmission,
    RiskAssessment,
)
from app.services import audit
from app.services.care import active_doctor_id, get_patient, local_now

# Уведомление врачу видно на заблокированном экране: без имени пациента, диагноза и препаратов.
DOCTOR_PUSH_TEXT = {
    FlagLevel.RED: ("Красный флаг", "У пациента новый сигнал, требующий внимания. Откройте кабинет врача."),
    FlagLevel.YELLOW: ("Новая отметка", "У пациента новая отметка в списке. Посмотрите в ближайший рабочий день."),
}
DEFAULT_PRIORITY = {FlagLevel.RED: PushPriority.URGENT, FlagLevel.YELLOW: PushPriority.NORMAL}


class FlagError(ValueError):
    pass


def raise_flag(
    db: Session,
    candidate: FlagCandidate,
    *,
    patient_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID | None,
    now: datetime,
    priority: PushPriority | None = None,
) -> Flag | None:
    """Ставит флаг и push врачу. None — нет лечащего врача или такой флаг уже открыт."""
    doctor_id = active_doctor_id(db, patient_id)
    if doctor_id is None:
        return None

    flag_id = db.scalar(
        insert(Flag)
        .values(
            id=uuid.uuid4(),
            patient_id=patient_id,
            level=candidate.level,
            reason=candidate.reason,
            source_type=source_type,
            source_id=source_id,
            dedupe_key=candidate.dedupe_key,
            details=candidate.details or None,
            status=FlagStatus.OPEN,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["patient_id", "dedupe_key"], index_where=sa.text("status = 'open'"))
        .returning(Flag.id)
    )
    if flag_id is None:
        return None

    title, body = DOCTOR_PUSH_TEXT[candidate.level]
    db.add(
        Notification(
            recipient_account_id=doctor_id,
            kind=NotificationKind.RED_FLAG if candidate.level is FlagLevel.RED else NotificationKind.YELLOW_FLAG,
            priority=priority or DEFAULT_PRIORITY[candidate.level],
            title=title,
            body_neutral=body,
            scheduled_for=now,
            related_flag_id=flag_id,
        )
    )
    audit.record(
        db,
        actor_account_id=None,
        actor_role="system",
        action=AuditAction.CREATE,
        entity="flag",
        entity_id=flag_id,
        patient_id=patient_id,
        meta={"reason": candidate.reason.value, "level": candidate.level.value},
    )
    db.flush()
    return db.get(Flag, flag_id)


def acknowledge(db: Session, *, flag_id: uuid.UUID, doctor_account_id: uuid.UUID, now: datetime) -> Flag:
    """«Взял в работу». Закрыть флаг может только лечащий врач этого пациента (В6)."""
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise FlagError("Флаг не найден")
    if active_doctor_id(db, flag.patient_id) != doctor_account_id:
        raise FlagError("Закрыть флаг может только лечащий врач пациента")
    if flag.status is not FlagStatus.OPEN:
        raise FlagError("Флаг уже закрыт")
    flag.status = FlagStatus.ACKNOWLEDGED
    flag.acknowledged_by = doctor_account_id
    flag.acknowledged_at = now
    audit.record(
        db,
        actor_account_id=doctor_account_id,
        actor_role="doctor",
        action=AuditAction.UPDATE,
        entity="flag",
        entity_id=flag.id,
        patient_id=flag.patient_id,
        meta={"status": FlagStatus.ACKNOWLEDGED.value},
    )
    db.flush()
    return flag


def note_patient_activity(db: Session, patient_id: uuid.UUID, now: datetime) -> None:
    """Пациент снова прислал данные — флаг «нет данных» закрывается сам, но остаётся в истории (В6)."""
    db.execute(
        update(Flag)
        .where(Flag.patient_id == patient_id, Flag.reason == FlagReason.NO_DATA, Flag.status == FlagStatus.OPEN)
        .values(status=FlagStatus.AUTO_RESOLVED, acknowledged_at=now)
    )


def last_activity_at(db: Session, patient_id: uuid.UUID) -> datetime | None:
    candidates = [
        select(func.max(DiaryEntry.submitted_at)).where(DiaryEntry.patient_id == patient_id),
        select(func.max(QuestionnaireSubmission.submitted_at)).where(QuestionnaireSubmission.patient_id == patient_id),
        select(func.max(DoseEvent.responded_at)).where(DoseEvent.patient_id == patient_id),
        select(func.max(RiskAssessment.submitted_at)).where(RiskAssessment.patient_id == patient_id),
        select(func.max(PanicEvent.received_at)).where(PanicEvent.patient_id == patient_id),
        select(func.max(Message.created_at)).where(
            Message.patient_id == patient_id, Message.direction == MessageDirection.PATIENT_TO_DOCTOR
        ),
    ]
    values = [v for q in candidates if (v := db.scalar(q)) is not None]
    return max(values, default=None)


def check_no_data(db: Session, *, now: datetime, days: int) -> list[Flag]:
    """Фоновая проверка: «нет данных 7 дней» по всем пациентам с лечащим врачом."""
    raised: list[Flag] = []
    for patient_id, linked_at in db.execute(
        select(CareLink.patient_id, CareLink.linked_at).where(CareLink.status == CareLinkStatus.ACTIVE)
    ):
        patient = get_patient(db, patient_id)
        last = last_activity_at(db, patient_id) or linked_at
        if last is None:
            continue
        today: date = local_now(patient, now).date()
        candidate = flag_rules.no_data(local_now(patient, last).date(), today, days=days)
        if candidate and (flag := raise_flag(db, candidate, patient_id=patient_id, source_type="no_data",
                                              source_id=None, now=now)):
            raised.append(flag)
    return raised
