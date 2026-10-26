"""Карточка пациента у врача, код-приглашение и очередь пациентов по флагам (§1.1, §5.2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import new_invite_code
from app.domain import flag_rules
from app.domain.enums import AuditAction, CareLinkStatus, FlagLevel, FlagReason, FlagStatus, Sex
from app.domain.flag_rules import PatientColor
from app.models import CareLink, Flag, PatientProfile
from app.services import audit

INVITE_TTL = timedelta(days=7)
ADULT_AGE = 18  # MVP только для взрослых (§0)


class PatientCardError(ValueError):
    pass


def age_on(birth_date: date, today: date) -> int:
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def is_adult(birth_date: date, today: date) -> bool:
    return age_on(birth_date, today) >= ADULT_AGE


def invite_qr_payload(code: str) -> str:
    return f"mindcare://invite/{code}"


@dataclass(frozen=True)
class PatientCard:
    patient_id: uuid.UUID
    invite_code: str
    invite_expires_at: datetime
    qr_payload: str


def create_patient_card(
    db: Session, *, doctor_account_id: uuid.UUID, full_name: str, birth_date: date, sex: Sex | None,
    city: str | None, region_code: str | None, now: datetime,
) -> PatientCard:
    """Врач создаёт карточку → система выдаёт код-приглашение и QR (§5.2)."""
    if not is_adult(birth_date, now.date()):
        raise PatientCardError("MVP рассчитан только на взрослых пациентов (18+)")
    patient = PatientProfile(full_name=full_name.strip(), birth_date=birth_date, sex=sex, city=city,
                             region_code=region_code)
    db.add(patient)
    db.flush()
    for _ in range(5):
        code = new_invite_code()
        try:
            with db.begin_nested():
                link = CareLink(doctor_id=doctor_account_id, patient_id=patient.id, invite_code=code,
                                invite_expires_at=now + INVITE_TTL, status=CareLinkStatus.PENDING)
                db.add(link)
            break
        except IntegrityError:
            continue
    else:
        raise RuntimeError("Не удалось выдать уникальный код-приглашение")
    audit.record(db, actor_account_id=doctor_account_id, actor_role="doctor", action=AuditAction.CREATE,
                 entity="patient_profile", entity_id=patient.id, patient_id=patient.id)
    db.flush()
    return PatientCard(patient.id, code, link.invite_expires_at, invite_qr_payload(code))


def doctor_has_patient(db: Session, doctor_account_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    """Врач видит своих пациентов — подключённых и ещё не вошедших по приглашению."""
    return db.scalar(
        select(CareLink.id).where(
            CareLink.doctor_id == doctor_account_id, CareLink.patient_id == patient_id,
            CareLink.status.in_([CareLinkStatus.ACTIVE, CareLinkStatus.PENDING]),
        )
    ) is not None


@dataclass(frozen=True)
class OpenFlag:
    flag_id: uuid.UUID
    level: FlagLevel
    reason: FlagReason
    created_at: datetime


@dataclass(frozen=True)
class QueueItem:
    patient_id: uuid.UUID
    full_name: str
    connected: bool  # False — пациент ещё не ввёл код-приглашение
    color: PatientColor
    open_flags: list[OpenFlag] = field(default_factory=list)


def open_flags(db: Session, patient_id: uuid.UUID) -> list[OpenFlag]:
    return [
        OpenFlag(f.id, f.level, f.reason, f.created_at)
        for f in db.scalars(select(Flag).where(Flag.patient_id == patient_id, Flag.status == FlagStatus.OPEN)
                            .order_by(Flag.created_at.desc()))
    ]


def doctor_queue(db: Session, doctor_account_id: uuid.UUID) -> list[QueueItem]:
    """Главный экран врача — очередь по срочности, а не алфавит (§1.1)."""
    rows = db.execute(
        select(PatientProfile, CareLink.status)
        .join(CareLink, CareLink.patient_id == PatientProfile.id)
        .where(CareLink.doctor_id == doctor_account_id,
               CareLink.status.in_([CareLinkStatus.ACTIVE, CareLinkStatus.PENDING]))
    ).all()
    items = []
    for patient, status in rows:
        flags = open_flags(db, patient.id)
        items.append(QueueItem(patient.id, patient.full_name, status is CareLinkStatus.ACTIVE,
                               flag_rules.patient_color(f.level for f in flags), flags))
    return sorted(items, key=lambda i: (*flag_rules.queue_sort_key(i.color, i.open_flags[0].created_at
                                                                    if i.open_flags else None), i.full_name))
