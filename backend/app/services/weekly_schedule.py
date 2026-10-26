"""Фоновая задача графика еженедельных опросников (§4.2): слот в день срока, повтор через 1 день,
пропуск через 3 дня. Следующий опросник — по обычному графику, без сдвига."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain.enums import CareLinkStatus, NotificationKind, PushPriority, ScheduleStatus
from app.domain.weekly_schedule import due_date_for, slot_transition
from app.models import CareLink, Notification, QuestionnaireSchedule
from app.services.care import get_patient, local_now
from app.services.thresholds import get_thresholds

# Нейтральный текст: на заблокированном экране не должно быть ни названий опросников, ни диагноза.
REMINDER_TITLE = "Напоминание"
REMINDER_BODY = "Несколько вопросов о самочувствии за неделю — это займёт пару минут."


@dataclass
class ScheduleRun:
    created: list[uuid.UUID] = field(default_factory=list)
    reminded: list[uuid.UUID] = field(default_factory=list)
    missed: list[uuid.UUID] = field(default_factory=list)


def _remind(db: Session, account_id: uuid.UUID | None, now: datetime) -> None:
    if account_id is None:
        return
    db.add(Notification(recipient_account_id=account_id, kind=NotificationKind.WEEKLY_QUESTIONNAIRE,
                        priority=PushPriority.NORMAL, title=REMINDER_TITLE, body_neutral=REMINDER_BODY,
                        scheduled_for=now))


def run_weekly_schedule(db: Session, *, now: datetime, content: Content) -> ScheduleRun:
    t = get_thresholds(db, content)
    run = ScheduleRun()
    links = db.execute(
        select(CareLink.patient_id, CareLink.linked_at).where(
            CareLink.status == CareLinkStatus.ACTIVE, CareLink.linked_at.is_not(None)
        )
    ).all()
    for patient_id, linked_at in links:
        patient = get_patient(db, patient_id)
        today = local_now(patient, now).date()
        due = due_date_for(local_now(patient, linked_at).date(), today)
        if due is not None:
            slot_id = db.scalar(
                insert(QuestionnaireSchedule)
                .values(id=uuid.uuid4(), patient_id=patient_id, due_date=due, status=ScheduleStatus.PENDING)
                .on_conflict_do_nothing(index_elements=["patient_id", "due_date"])
                .returning(QuestionnaireSchedule.id)
            )
            if slot_id is not None:
                run.created.append(slot_id)
                _remind(db, patient.account_id, now)

        open_slots = db.scalars(
            select(QuestionnaireSchedule).where(
                QuestionnaireSchedule.patient_id == patient_id,
                QuestionnaireSchedule.status.in_([ScheduleStatus.PENDING, ScheduleStatus.REMINDED]),
            )
        )
        for slot in open_slots:
            new = slot_transition(slot.status, slot.due_date, today,
                                  remind_after_days=int(t["weekly_reminder_after_days"]),
                                  missed_after_days=int(t["weekly_missed_after_days"]))
            if new is slot.status:
                continue
            slot.status = new
            if new is ScheduleStatus.REMINDED:
                slot.reminded_at = now
                run.reminded.append(slot.id)
                _remind(db, patient.account_id, now)
            elif new is ScheduleStatus.MISSED:
                slot.closed_at = now
                run.missed.append(slot.id)
    db.flush()
    return run
