"""Приёмы по расписанию: генерация, напоминания, «нет ответа», ответы пациента (§1.2, §2.2, §5.3).

Напоминания о приёме приходят и в «тихие часы», если приём назначен на это время (§5.3).
На заблокированном экране — только «Пора отметить приём» (§2.2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain import treatment
from app.domain.enums import (
    AuditAction,
    DoseStatus,
    FlagReason,
    NotificationKind,
    PushPriority,
    RiskTrigger,
)
from app.domain.treatment import DoseResponse, MissedDoseHint, Step
from app.domain.unscheduled_check import treatment_change_block_due
from app.models import DoseEvent, Notification, PatientProfile, Prescription, Substance, TitrationStep
from app.services import audit
from app.services.adherence import evaluate_dose_response
from app.services.care import active_doctor_id, get_patient, local_now
from app.services.risk_protocol import assessed_today, last_assessment_day
from app.services.thresholds import get_thresholds

HORIZON = timedelta(hours=48)
LOOKBACK = timedelta(hours=1)  # напоминание о приёме, который воркер создал с небольшим опозданием


class DoseError(ValueError):
    pass


class DoseNotFound(DoseError, LookupError):
    pass


def steps_of(db: Session, prescription_id: uuid.UUID) -> list[Step]:
    rows = db.scalars(
        select(TitrationStep).where(TitrationStep.prescription_id == prescription_id).order_by(TitrationStep.effective_date)
    )
    return [Step(r.effective_date, Decimal(r.dose)) for r in rows]


def planned(p: Prescription, patient: PatientProfile, steps: list[Step], window_from: datetime, window_to: datetime):
    if p.stopped_at is not None:
        window_to = min(window_to, p.stopped_at)
    return treatment.planned_doses(
        start_date=p.start_date, end_date=p.end_date, times=p.times, timezone=patient.timezone,
        base_dose=p.dose, steps=steps, window_from=window_from, window_to=window_to,
    )


def _reminder(db: Session, patient: PatientProfile, p: Prescription, dose: Decimal, when: datetime,
              content: Content, dose_event_id: uuid.UUID) -> None:
    if patient.account_id is None:
        return
    texts = content.treatment_texts.reminder
    detailed = None
    if patient.notification_details_enabled:
        inn = content.drugs.by_id(p.substance_id).inn
        detailed = texts.body_detailed.format(inn=inn, dose=treatment.format_dose(dose), unit=p.unit)
    db.add(Notification(recipient_account_id=patient.account_id, kind=NotificationKind.DOSE_REMINDER,
                        priority=PushPriority.NORMAL, title=texts.title, body_neutral=texts.body_neutral,
                        body_detailed=detailed, scheduled_for=when,
                        related_dose_event_id=dose_event_id))


def generate_events(db: Session, p: Prescription, window_from: datetime, window_to: datetime,
                    content: Content, *, remind_after: datetime | None = None) -> list[uuid.UUID]:
    patient = get_patient(db, p.patient_id)
    created = []
    for at, dose in planned(p, patient, steps_of(db, p.id), window_from, window_to):
        event_id = db.scalar(
            insert(DoseEvent)
            .values(id=uuid.uuid4(), prescription_id=p.id, patient_id=p.patient_id, scheduled_at=at,
                    planned_dose=dose, status=DoseStatus.PENDING)
            .on_conflict_do_nothing(index_elements=["prescription_id", "scheduled_at"])
            .returning(DoseEvent.id)
        )
        if event_id is not None:
            created.append(event_id)
            if remind_after is None or at >= remind_after:
                _reminder(db, patient, p, dose, at, content, event_id)
    return created


def regenerate_future(db: Session, p: Prescription, now: datetime, content: Content) -> None:
    """После изменения схемы: будущие неотмеченные приёмы пересоздаются по новой схеме."""
    db.execute(
        DoseEvent.__table__.delete().where(
            DoseEvent.prescription_id == p.id, DoseEvent.status == DoseStatus.PENDING, DoseEvent.scheduled_at > now
        )
    )
    if p.stopped_at is None:
        generate_events(db, p, now, now + HORIZON, content)


@dataclass
class DoseRun:
    created: list[uuid.UUID] = field(default_factory=list)
    no_response: list[uuid.UUID] = field(default_factory=list)


def run_dose_schedule(db: Session, *, now: datetime, content: Content) -> DoseRun:
    """Фоновая задача: приёмы на 48 часов вперёд с напоминаниями, «нет ответа» по истечении N часов (В4)."""
    run = DoseRun()
    for p in db.scalars(select(Prescription).where(Prescription.stopped_at.is_(None))).all():
        run.created += generate_events(db, p, now - LOOKBACK, now + HORIZON, content, remind_after=now - LOOKBACK)

    hours = int(get_thresholds(db, content)["dose_no_response_after_hours"])
    run.no_response = list(db.scalars(
        update(DoseEvent)
        .where(DoseEvent.status == DoseStatus.PENDING, DoseEvent.scheduled_at <= now - timedelta(hours=hours))
        .values(status=DoseStatus.NO_RESPONSE)
        .returning(DoseEvent.id)
    ))
    db.flush()
    return run


@dataclass(frozen=True)
class MissedDoseGuidance:
    rule_text: str  # правило, которое задал врач
    hint: MissedDoseHint | None
    hint_text: str | None
    author_note: str


@dataclass(frozen=True)
class DoseResponseResult:
    dose_event_id: uuid.UUID
    status: DoseStatus
    guidance: MissedDoseGuidance | None  # при пропуске — сразу правило врача (§1.3)
    raised_flags: list[FlagReason]
    offer_risk_block: RiskTrigger | None  # пропуски/самостоятельная смена дозы — повод для блока (§4.6 к. 4)


def _own_event(db: Session, patient_id: uuid.UUID, dose_event_id: uuid.UUID) -> DoseEvent:
    event = db.get(DoseEvent, dose_event_id)
    if event is None or event.patient_id != patient_id:
        raise DoseNotFound("Приём не найден")
    return event


def missed_dose_guidance(p: Prescription, patient: PatientProfile, scheduled_at: datetime, now: datetime,
                         content: Content, db: Session) -> MissedDoseGuidance:
    texts = content.treatment_texts
    upcoming = planned(p, patient, steps_of(db, p.id), max(now, scheduled_at) + timedelta(seconds=1),
                       scheduled_at + timedelta(days=8))
    hint = treatment.missed_dose_hint(p.missed_dose_rule, p.missed_dose_hours, now=now,
                                      next_dose_at=upcoming[0][0] if upcoming else None)
    return MissedDoseGuidance(
        rule_text=texts.missed_dose_rules[p.missed_dose_rule].format(hours=p.missed_dose_hours),
        hint=hint,
        hint_text=texts.missed_dose_hints[hint.value].format(hours=p.missed_dose_hours) if hint else None,
        author_note=texts.rule_author_note,
    )


def respond_to_dose(
    db: Session, *, patient_id: uuid.UUID, dose_event_id: uuid.UUID, response: DoseResponse, now: datetime,
    content: Content, actual_dose=None,
) -> DoseResponseResult:
    event = _own_event(db, patient_id, dose_event_id)
    p = db.get(Prescription, event.prescription_id)
    patient = get_patient(db, patient_id)
    try:
        status, actual = treatment.apply_response(
            current=event.status, scheduled_at=event.scheduled_at, now=now, response=response,
            planned_dose=event.planned_dose, actual_dose=actual_dose,
        )
    except treatment.InvalidDoseResponse as e:
        raise DoseError(str(e)) from e
    event.status, event.actual_dose, event.responded_at, event.snoozed_until = status, actual, now, None
    db.flush()

    guidance = missed_dose_guidance(p, patient, event.scheduled_at, now, content, db) if status is DoseStatus.MISSED else None
    raised = evaluate_dose_response(db, dose_event_id=event.id, now=now, content=content)
    offer = None
    if raised and active_doctor_id(db, patient_id) is not None and not assessed_today(db, patient, now):
        offer = RiskTrigger.UNSCHEDULED_ADHERENCE
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.UPDATE,
                 entity="dose_event", entity_id=event.id, patient_id=patient_id, meta={"status": status.value})
    db.flush()
    return DoseResponseResult(event.id, status, guidance, raised, offer)


@dataclass(frozen=True)
class DoseView:
    id: uuid.UUID
    scheduled_at: datetime
    local_time: str  # «09:00» в таймзоне пациента
    inn: str
    trade_name: str | None
    dose: str
    unit: str
    status: DoseStatus
    answerable: bool  # «нет ответа» тоже можно отметить позже (В4)
    snoozed_until: datetime | None


def doses_for_day(db: Session, *, patient_id: uuid.UUID, day: date, content: Content) -> list[DoseView]:
    """Приёмы за день пациента — экран «Сегодня», где их можно отметить и без push-напоминания."""
    patient = get_patient(db, patient_id)
    zone = ZoneInfo(patient.timezone)
    start = datetime.combine(day, time.min, zone)
    rows = db.execute(
        select(DoseEvent, Prescription)
        .join(Prescription, Prescription.id == DoseEvent.prescription_id)
        .where(DoseEvent.patient_id == patient_id, DoseEvent.scheduled_at >= start,
               DoseEvent.scheduled_at < start + timedelta(days=1))
        .order_by(DoseEvent.scheduled_at)
    ).all()
    return [
        DoseView(e.id, e.scheduled_at, e.scheduled_at.astimezone(zone).strftime("%H:%M"),
                 content.drugs.by_id(p.substance_id).inn, p.trade_name, treatment.format_dose(e.planned_dose),
                 p.unit, e.status, e.status in treatment.ANSWERABLE, e.snoozed_until)
        for e, p in rows
    ]


@dataclass(frozen=True)
class NextDose:
    prescription_id: uuid.UUID
    inn: str
    trade_name: str | None
    dose: str
    unit: str
    scheduled_at: datetime
    local_date: date
    local_time: str


NEXT_DOSE_HORIZON = timedelta(days=120)


def next_doses_without_day(db: Session, *, patient_id: uuid.UUID, day: date, now: datetime,
                           content: Content) -> list[NextDose]:
    """Лекарства, у которых в этот день приёмов нет, и когда ближайший приём.

    Так пациент видит, что назначение не потерялось: «первый приём завтра в 09:00», если врач назначил
    препарат после сегодняшнего времени приёма или курс начинается позже. Время считается по схеме,
    а не по созданным приёмам — воркер создаёт их только на 48 часов вперёд.
    """
    patient = get_patient(db, patient_id)
    zone = ZoneInfo(patient.timezone)
    start = datetime.combine(day, time.min, zone)
    with_doses = set(db.scalars(
        select(DoseEvent.prescription_id)
        .where(DoseEvent.patient_id == patient_id, DoseEvent.scheduled_at >= start,
               DoseEvent.scheduled_at < start + timedelta(days=1))
    ))
    result = []
    for p in db.scalars(select(Prescription).where(Prescription.patient_id == patient_id,
                                                   Prescription.stopped_at.is_(None))
                        .order_by(Prescription.created_at)):
        if p.id in with_doses:
            continue
        upcoming = planned(p, patient, steps_of(db, p.id), max(now, start), now + NEXT_DOSE_HORIZON)
        if not upcoming:
            continue  # курс закончился
        at, dose = upcoming[0]
        local = at.astimezone(zone)
        result.append(NextDose(p.id, content.drugs.by_id(p.substance_id).inn, p.trade_name,
                               treatment.format_dose(dose), p.unit, at, local.date(), local.strftime("%H:%M")))
    return result


def snooze_dose(db: Session, *, patient_id: uuid.UUID, dose_event_id: uuid.UUID, minutes: int, now: datetime,
                content: Content) -> datetime:
    """«Напомнить через 15/30 минут»."""
    if minutes not in content.treatment_texts.snooze_minutes:
        raise DoseError("Можно отложить на 15 или 30 минут")
    event = _own_event(db, patient_id, dose_event_id)
    if event.status is not DoseStatus.PENDING:
        raise DoseError("Этот приём уже отмечен")
    event.snoozed_until = now + timedelta(minutes=minutes)
    _reminder(db, get_patient(db, patient_id), db.get(Prescription, event.prescription_id), Decimal(event.planned_dose),
              event.snoozed_until, content, event.id)
    db.flush()
    return event.snoozed_until


def due_treatment_change_block(db: Session, *, patient_id: uuid.UUID, now: datetime,
                               content: Content) -> RiskTrigger | None:
    """Первые недели антидепрессанта и после смены дозы — уточняющий блок чаще (§4.6 к. 4, В5)."""
    if active_doctor_id(db, patient_id) is None:
        return None
    patient = get_patient(db, patient_id)
    rows = db.execute(
        select(Prescription, Substance.classes)
        .join(Substance, Substance.id == Prescription.substance_id)
        .where(Prescription.patient_id == patient_id, Prescription.stopped_at.is_(None))
    ).all()
    change_dates = []
    for p, classes in rows:
        if "antidepressant" in classes:
            change_dates += [p.start_date] + [s.effective_date for s in steps_of(db, p.id)]
    t = get_thresholds(db, content)
    due = treatment_change_block_due(
        change_dates, last_assessment_day(db, patient, now), local_now(patient, now).date(),
        every_days=int(t["unscheduled_after_dose_change_every_days"]),
        window_days=int(t["unscheduled_after_dose_change_window_days"]),
    )
    return RiskTrigger.UNSCHEDULED_TREATMENT_CHANGE if due else None
