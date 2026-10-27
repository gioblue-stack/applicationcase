"""Кнопка «Мне сейчас очень плохо» (§5.5): красный флаг врачу и экран помощи.

Экран помощи открывается на устройстве сразу, без ожидания сервера; событие доходит позже
(оффлайн-очередь), поэтому повтор того же client_id не создаёт второе событие.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain.enums import AuditAction, FlagLevel, FlagReason, PushPriority
from app.domain.flag_rules import FlagCandidate
from app.models import PanicEvent, PatientProfile
from app.services import audit
from app.services.care import active_doctor_id
from app.services.flags import raise_flag
from app.services.screens import HelpScreen, help_screen_for


@dataclass(frozen=True)
class PanicResult:
    event_id: uuid.UUID
    created: bool
    flag_raised: bool
    screen: HelpScreen


def press_panic(db: Session, *, patient: PatientProfile, client_id: uuid.UUID, pressed_at: datetime, now: datetime,
                content: Content) -> PanicResult:
    has_doctor = active_doctor_id(db, patient.id) is not None
    screen = help_screen_for(content, patient.region_code, has_doctor=has_doctor)
    existing = db.scalar(select(PanicEvent).where(PanicEvent.client_id == client_id,
                                                  PanicEvent.patient_id == patient.id))
    if existing is not None:
        return PanicResult(existing.id, False, False, screen)

    event = PanicEvent(client_id=client_id, patient_id=patient.id, pressed_at=pressed_at, received_at=now)
    db.add(event)
    db.flush()
    # Пока открыт прошлый флаг кнопки, новый не ставится: врач уже видит красный сигнал.
    flag = raise_flag(db, FlagCandidate(FlagLevel.RED, FlagReason.PANIC_BUTTON, "panic_button",
                                        {"pressed_at": pressed_at.isoformat()}),
                      patient_id=patient.id, source_type="panic_event", source_id=event.id, now=now,
                      priority=PushPriority.URGENT)
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="panic_event", entity_id=event.id, patient_id=patient.id)
    db.flush()
    return PanicResult(event.id, True, flag is not None, screen)
