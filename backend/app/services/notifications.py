"""Отправка уведомлений из очереди и ежедневное напоминание о дневнике (§5.3).

Реальный push-провайдер (APNs/FCM/Web Push) подключается к пилоту; интерфейс — PushProvider.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain.enums import DoseStatus, NotificationKind, NotificationStatus, PushPriority, Role
from app.domain.notifications import parse_hhmm, postpone_into, postpone_out_of
from app.models import Account, DiaryEntry, DoctorProfile, DoseEvent, Notification, PatientProfile
from app.services.care import local_now

log = logging.getLogger("mindcare.push")

# В «тихие часы» пациента откладываются все напоминания, кроме приёма лекарств (§5.3).
QUIET_HOURS_KINDS = {
    NotificationKind.DIARY_REMINDER,
    NotificationKind.WEEKLY_QUESTIONNAIRE,
    NotificationKind.LAB_REMINDER,
    NotificationKind.DOCTOR_REPLY,
}
DOCTOR_WINDOW_KINDS = {NotificationKind.RED_FLAG, NotificationKind.YELLOW_FLAG}


class PushProvider(Protocol):
    def send(self, notification: Notification) -> None: ...


class DevLogPushProvider:
    """Разработка: пишет в лог только нейтральный текст — подробности не попадают даже в логи."""

    def send(self, notification: Notification) -> None:
        log.info("PUSH → %s: %s — %s", notification.recipient_account_id, notification.title,
                 notification.body_neutral)


@dataclass
class DispatchReport:
    sent: list[uuid.UUID] = field(default_factory=list)
    cancelled: list[uuid.UUID] = field(default_factory=list)
    postponed: list[uuid.UUID] = field(default_factory=list)
    failed: list[uuid.UUID] = field(default_factory=list)


def _postpone_until(db: Session, n: Notification, now: datetime) -> datetime | None:
    account = db.get(Account, n.recipient_account_id)
    if account is None:
        return None
    if account.role is Role.DOCTOR and n.kind in DOCTOR_WINDOW_KINDS:
        doctor = db.get(DoctorProfile, account.id)
        window = doctor.red_flag_push_window if doctor else None
        if window:
            local = now.astimezone(ZoneInfo(doctor.timezone))
            return postpone_into(local, parse_hhmm(window["start"]), parse_hhmm(window["end"]))
    if account.role is not Role.DOCTOR and n.kind in QUIET_HOURS_KINDS:
        patient = db.scalar(select(PatientProfile).where(PatientProfile.account_id == account.id))
        if patient and patient.quiet_hours_start and patient.quiet_hours_end:
            return postpone_out_of(local_now(patient, now), patient.quiet_hours_start, patient.quiet_hours_end)
    return None


def dispatch_due(db: Session, *, now: datetime, provider: PushProvider, limit: int = 500) -> DispatchReport:
    """Отправляет наступившие уведомления. SKIP LOCKED — несколько воркеров не отправят одно дважды."""
    report = DispatchReport()
    due = db.scalars(
        select(Notification)
        .where(Notification.status == NotificationStatus.SCHEDULED, Notification.scheduled_for <= now)
        .order_by(Notification.scheduled_for)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for n in due:
        if n.related_dose_event_id is not None:
            event = db.get(DoseEvent, n.related_dose_event_id)
            if event is None or event.status is not DoseStatus.PENDING:
                n.status = NotificationStatus.CANCELLED  # приём уже отмечен — напоминать незачем
                report.cancelled.append(n.id)
                continue
        until = _postpone_until(db, n, now)
        if until is not None:
            n.scheduled_for = until
            report.postponed.append(n.id)
            continue
        try:
            provider.send(n)
        except Exception:
            log.exception("Не удалось отправить уведомление %s", n.id)
            n.status = NotificationStatus.FAILED
            report.failed.append(n.id)
            continue
        n.status, n.sent_at = NotificationStatus.SENT, now
        report.sent.append(n.id)
    db.flush()
    return report


def create_diary_reminders(db: Session, *, now: datetime, content: Content) -> list[uuid.UUID]:
    """Раз в день, в выбранное пациентом время, если дневник за сегодня ещё не заполнен.

    Текст — «Отметим самочувствие?», без упрёков за пропуски (§5.7).
    """
    created = []
    patients = db.scalars(select(PatientProfile).where(PatientProfile.account_id.is_not(None),
                                                       PatientProfile.diary_reminder_time.is_not(None))).all()
    for patient in patients:
        local = local_now(patient, now)
        if local.time() < patient.diary_reminder_time:
            continue
        day_start = datetime.combine(local.date(), time(0), tzinfo=local.tzinfo)
        filled = db.scalar(select(exists().where(DiaryEntry.patient_id == patient.id, DiaryEntry.day == local.date())))
        reminded = db.scalar(select(exists().where(
            Notification.recipient_account_id == patient.account_id,
            Notification.kind == NotificationKind.DIARY_REMINDER,
            Notification.created_at >= day_start)))
        if filled or reminded:
            continue
        n = Notification(recipient_account_id=patient.account_id, kind=NotificationKind.DIARY_REMINDER,
                         priority=PushPriority.NORMAL, title=content.treatment_texts.reminder.title,
                         body_neutral=content.diary.invitation, scheduled_for=now, created_at=now)
        db.add(n)
        db.flush()
        created.append(n.id)
    return created
