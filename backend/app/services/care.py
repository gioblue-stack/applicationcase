"""Общие запросы о пациенте: лечащий врач, таймзона."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import CareLinkStatus
from app.models import CareLink, PatientProfile


class PatientNotFound(LookupError):
    pass


def get_patient(db: Session, patient_id: uuid.UUID) -> PatientProfile:
    patient = db.get(PatientProfile, patient_id)
    if patient is None:
        raise PatientNotFound("Пациент не найден")
    return patient


def active_doctor_id(db: Session, patient_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(CareLink.doctor_id).where(
            CareLink.patient_id == patient_id, CareLink.status == CareLinkStatus.ACTIVE
        )
    )


def local_now(patient: PatientProfile, now: datetime) -> datetime:
    """Границы дня (дневник, график опросников) считаются в таймзоне пациента."""
    return now.astimezone(ZoneInfo(patient.timezone))
