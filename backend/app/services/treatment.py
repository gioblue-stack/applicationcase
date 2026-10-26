"""Схема лечения: назначение, изменение дозы, ручной сдвиг этапов, отмена, история (§1.3, §2.2).

Схему ведёт только лечащий врач; каждое изменение — строка в истории (кто, когда, что было, что стало).
Автоматического сдвига этапов нет: только кнопка врача «Сдвинуть следующие этапы на N дней».
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain import treatment
from app.domain.enums import AuditAction, DoseStatus, MissedDoseRule, RegimenChangeType
from app.domain.treatment import Step
from app.models import DoseEvent, PatientProfile, Prescription, RegimenChange, Substance, TitrationStep
from app.services import audit
from app.services.care import get_patient, local_now
from app.services.doses import regenerate_future, steps_of
from app.services.patients import doctor_has_patient


class TreatmentError(ValueError):
    pass


@dataclass(frozen=True)
class PrescriptionSpec:
    substance_id: str
    form: str
    dose: Decimal
    unit: str
    times: Sequence[time]
    start_date: date
    in_person_visit_date: date
    missed_dose_rule: MissedDoseRule
    missed_dose_hours: int | None = None
    trade_name: str | None = None
    with_food: str | None = None
    instructions: str | None = None
    end_date: date | None = None
    titration: Sequence[Step] = field(default_factory=tuple)


def _require_doctor(db: Session, patient_id: uuid.UUID, doctor_account_id: uuid.UUID) -> None:
    # Схему можно внести сразу на приёме — до того, как пациент введёт код-приглашение.
    if not doctor_has_patient(db, doctor_account_id, patient_id):
        raise TreatmentError("Схему лечения ведёт только лечащий врач пациента")


def _active(db: Session, prescription_id: uuid.UUID) -> Prescription:
    p = db.get(Prescription, prescription_id)
    if p is None:
        raise TreatmentError("Назначение не найдено")
    if p.stopped_at is not None:
        raise TreatmentError("Назначение отменено")
    return p


def _plain(value) -> str:
    """50.000 → «50», 100 → «100» (а не «1E+2»), 12.500 → «12.5»."""
    return format(Decimal(value).normalize(), "f")


def snapshot(p: Prescription, steps: Sequence[Step]) -> dict:
    return {
        "substance_id": p.substance_id,
        "trade_name": p.trade_name,
        "form": p.form,
        "dose": _plain(p.dose),
        "unit": p.unit,
        "times": [t.strftime("%H:%M") for t in p.times],
        "with_food": p.with_food,
        "instructions": p.instructions,
        "start_date": p.start_date.isoformat(),
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "missed_dose_rule": p.missed_dose_rule.value,
        "missed_dose_hours": p.missed_dose_hours,
        "in_person_visit_date": p.in_person_visit_date.isoformat(),
        "titration": [{"effective_date": s.effective_date.isoformat(), "dose": _plain(s.dose)}
                      for s in steps],
    }


def _log(db: Session, p: Prescription, change_type: RegimenChangeType, *, before: dict | None, after: dict | None,
         reason: str | None, doctor_account_id: uuid.UUID, now: datetime) -> None:
    db.add(RegimenChange(prescription_id=p.id, patient_id=p.patient_id, change_type=change_type, before=before,
                         after=after, reason=reason, changed_by=doctor_account_id, changed_at=now))
    audit.record(db, actor_account_id=doctor_account_id, actor_role="doctor",
                 action=AuditAction.CREATE if change_type is RegimenChangeType.CREATED else AuditAction.UPDATE,
                 entity="prescription", entity_id=p.id, patient_id=p.patient_id,
                 meta={"change": change_type.value})


def _replace_steps(db: Session, p: Prescription, steps: Sequence[Step]) -> None:
    db.execute(TitrationStep.__table__.delete().where(TitrationStep.prescription_id == p.id))
    db.add_all(TitrationStep(prescription_id=p.id, effective_date=s.effective_date, dose=s.dose) for s in steps)
    db.flush()


def create_prescription(db: Session, *, doctor_account_id: uuid.UUID, patient_id: uuid.UUID, spec: PrescriptionSpec,
                        now: datetime, content: Content) -> Prescription:
    _require_doctor(db, patient_id, doctor_account_id)
    substance = db.get(Substance, spec.substance_id)
    if substance is None or not substance.in_formulary:
        raise TreatmentError("Препарата нет в справочнике")
    treatment.validate_regimen(
        dose=spec.dose, times=spec.times, start_date=spec.start_date, end_date=spec.end_date,
        in_person_visit_date=spec.in_person_visit_date, missed_dose_rule=spec.missed_dose_rule,
        missed_dose_hours=spec.missed_dose_hours, steps=spec.titration,
    )
    p = Prescription(
        patient_id=patient_id, substance_id=spec.substance_id, trade_name=spec.trade_name, form=spec.form,
        dose=spec.dose, unit=spec.unit, times=sorted(spec.times), with_food=spec.with_food,
        instructions=spec.instructions, start_date=spec.start_date, end_date=spec.end_date,
        missed_dose_rule=spec.missed_dose_rule, missed_dose_hours=spec.missed_dose_hours,
        in_person_visit_date=spec.in_person_visit_date, created_by=doctor_account_id, created_at=now,
    )
    db.add(p)
    db.flush()
    _replace_steps(db, p, spec.titration)
    get_patient(db, patient_id).takes_medication = True
    _log(db, p, RegimenChangeType.CREATED, before=None, after=snapshot(p, spec.titration), reason=None,
         doctor_account_id=doctor_account_id, now=now)
    regenerate_future(db, p, now, content)
    db.flush()
    return p


def change_dose(db: Session, *, doctor_account_id: uuid.UUID, prescription_id: uuid.UUID, effective_date: date,
                dose: Decimal, reason: str | None, now: datetime, content: Content) -> Prescription:
    """Новая доза с даты (не в прошлом). Это этап титрации, добавленный врачом."""
    p = _active(db, prescription_id)
    _require_doctor(db, p.patient_id, doctor_account_id)
    today = local_now(get_patient(db, p.patient_id), now).date()
    if effective_date < today:
        raise TreatmentError("Изменение дозы не может начаться в прошлом")
    steps = steps_of(db, p.id)
    before = snapshot(p, steps)
    if effective_date <= p.start_date:
        if Decimal(dose) <= 0:
            raise treatment.InvalidRegimen("Доза должна быть больше нуля")
        p.dose = dose
    else:
        steps = [s for s in steps if s.effective_date != effective_date] + [Step(effective_date, Decimal(dose))]
        steps.sort(key=lambda s: s.effective_date)
        treatment.validate_steps(steps, start_date=p.start_date, end_date=p.end_date)
        _replace_steps(db, p, steps)
    _log(db, p, RegimenChangeType.DOSE_CHANGED, before=before, after=snapshot(p, steps), reason=reason,
         doctor_account_id=doctor_account_id, now=now)
    regenerate_future(db, p, now, content)
    db.flush()
    return p


def shift_titration(db: Session, *, doctor_account_id: uuid.UUID, prescription_id: uuid.UUID, days: int,
                    reason: str | None, now: datetime, content: Content) -> list[Step]:
    """Кнопка врача «Сдвинуть следующие этапы на N дней» (§1.3). Одно нажатие — календарь перестроен."""
    p = _active(db, prescription_id)
    _require_doctor(db, p.patient_id, doctor_account_id)
    today = local_now(get_patient(db, p.patient_id), now).date()
    steps = steps_of(db, p.id)
    shifted = treatment.shift_future_steps(steps, today=today, days=days)
    treatment.validate_steps(shifted, start_date=p.start_date, end_date=p.end_date)
    _replace_steps(db, p, shifted)
    _log(db, p, RegimenChangeType.TITRATION_SHIFTED, before=snapshot(p, steps), after=snapshot(p, shifted),
         reason=reason, doctor_account_id=doctor_account_id, now=now)
    regenerate_future(db, p, now, content)
    db.flush()
    return shifted


def stop_prescription(db: Session, *, doctor_account_id: uuid.UUID, prescription_id: uuid.UUID, reason: str | None,
                      now: datetime, content: Content) -> Prescription:
    p = _active(db, prescription_id)
    _require_doctor(db, p.patient_id, doctor_account_id)
    patient = get_patient(db, p.patient_id)
    steps = steps_of(db, p.id)
    before = snapshot(p, steps)
    p.stopped_at = now
    p.end_date = max(p.start_date, local_now(patient, now).date())
    regenerate_future(db, p, now, content)
    patient.takes_medication = db.scalar(
        select(exists().where(Prescription.patient_id == patient.id, Prescription.stopped_at.is_(None)))
    )
    _log(db, p, RegimenChangeType.STOPPED, before=before, after=snapshot(p, steps), reason=reason,
         doctor_account_id=doctor_account_id, now=now)
    db.flush()
    return p


def regimen_history(db: Session, patient_id: uuid.UUID) -> list[RegimenChange]:
    return list(db.scalars(
        select(RegimenChange).where(RegimenChange.patient_id == patient_id).order_by(RegimenChange.changed_at)
    ))


@dataclass(frozen=True)
class TreatmentMarker:
    """Вертикальная отметка на графиках врача: начало, смена дозы, отмена (§1.1)."""

    day: date
    kind: str  # start | dose_change | stop
    prescription_id: uuid.UUID
    label: str


def treatment_markers(db: Session, patient_id: uuid.UUID, content: Content) -> list[TreatmentMarker]:
    patient = get_patient(db, patient_id)
    markers = []
    for p in db.scalars(select(Prescription).where(Prescription.patient_id == patient_id)):
        inn = content.drugs.by_id(p.substance_id).inn
        markers.append(TreatmentMarker(p.start_date, "start", p.id,
                                       f"Начало: {inn} {treatment.format_dose(p.dose)} {p.unit}"))
        for s in steps_of(db, p.id):
            if p.stopped_at is None or s.effective_date <= local_now(patient, p.stopped_at).date():
                markers.append(TreatmentMarker(s.effective_date, "dose_change", p.id,
                                               f"Доза: {inn} {treatment.format_dose(s.dose)} {p.unit}"))
        if p.stopped_at is not None:
            markers.append(TreatmentMarker(local_now(patient, p.stopped_at).date(), "stop", p.id, f"Отмена: {inn}"))
    return sorted(markers, key=lambda m: m.day)


def titration_needs_attention(db: Session, prescription_id: uuid.UUID, now: datetime) -> bool:
    """Пропуск пришёлся на текущий этап, а впереди повышение — показать врачу кнопку сдвига (§1.3)."""
    p = db.get(Prescription, prescription_id)
    patient = get_patient(db, p.patient_id)
    today = local_now(patient, now).date()
    steps = steps_of(db, p.id)
    if not treatment.upcoming_steps(steps, today):
        return False
    current_from = max([s.effective_date for s in steps if s.effective_date <= today], default=p.start_date)
    missed = db.scalars(
        select(DoseEvent.scheduled_at).where(DoseEvent.prescription_id == p.id, DoseEvent.status == DoseStatus.MISSED)
    )
    return any(local_now(patient, at).date() >= current_from for at in missed)


@dataclass(frozen=True)
class PlanItem:
    prescription_id: uuid.UUID
    inn: str
    trade_name: str | None
    form: str
    current_dose: str
    unit: str
    times: list[str]
    with_food: str | None
    instructions: str | None
    upcoming: list[str]  # «с 20.09.2027 — 100 мг»
    missed_dose_rule_text: str


def patient_plan(db: Session, patient_id: uuid.UUID, now: datetime, content: Content) -> list[PlanItem]:
    """«Мой план лечения» простым языком (§2.2)."""
    patient: PatientProfile = get_patient(db, patient_id)
    today = local_now(patient, now).date()
    texts = content.treatment_texts
    items = []
    for p in db.scalars(select(Prescription).where(Prescription.patient_id == patient_id,
                                                   Prescription.stopped_at.is_(None))):
        steps = steps_of(db, p.id)
        items.append(PlanItem(
            prescription_id=p.id,
            inn=content.drugs.by_id(p.substance_id).inn,
            trade_name=p.trade_name,
            form=p.form,
            current_dose=treatment.format_dose(treatment.dose_on(today, p.dose, steps)),
            unit=p.unit,
            times=[t.strftime("%H:%M") for t in p.times],
            with_food=p.with_food,
            instructions=p.instructions,
            upcoming=[treatment.format_step(texts.plan_step, s, p.unit) for s in treatment.upcoming_steps(steps, today)],
            missed_dose_rule_text=texts.missed_dose_rules[p.missed_dose_rule].format(hours=p.missed_dose_hours),
        ))
    return items
