"""Флаги по отметкам о приёме (§1.2): ≥ 2 пропуска подряд, самостоятельное изменение дозы.

Вызывается после того, как пациент ответил на напоминание (модуль схемы лечения).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain import flag_rules
from app.domain.enums import DoseStatus, FlagReason
from app.models import DoseEvent
from app.services.flags import note_patient_activity, raise_flag
from app.services.thresholds import get_thresholds


def evaluate_dose_response(db: Session, *, dose_event_id: uuid.UUID, now: datetime, content: Content) -> list[FlagReason]:
    event = db.get(DoseEvent, dose_event_id)
    if event is None:
        raise LookupError("Приём не найден")
    if event.status in (DoseStatus.PENDING, DoseStatus.NO_RESPONSE):
        return []
    note_patient_activity(db, event.patient_id, now)

    candidate = None
    if event.status is DoseStatus.SELF_CHANGED:
        candidate = flag_rules.self_dose_change("dose_event", event.id)
    elif event.status is DoseStatus.MISSED:
        statuses = db.scalars(
            select(DoseEvent.status)
            .where(DoseEvent.prescription_id == event.prescription_id, DoseEvent.scheduled_at <= event.scheduled_at)
            .order_by(DoseEvent.scheduled_at)
        ).all()
        threshold = int(get_thresholds(db, content)["missed_doses_in_row_yellow"])
        candidate = flag_rules.missed_doses(statuses, threshold=threshold, prescription_id=event.prescription_id)

    if candidate and raise_flag(db, candidate, patient_id=event.patient_id, source_type="dose_event",
                                source_id=event.id, now=now):
        return [candidate.reason]
    return []
