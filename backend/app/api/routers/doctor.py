"""API кабинета врача. Каждый запрос к данным пациента проверяет, что это его пациент, и пишет журнал доступа."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DB, AppSettings, ContentDep, CurrentDoctor, DoctorPatient, Now, require_doctor_access
from app.domain.enums import (
    AuditAction,
    FlagLevel,
    FlagReason,
    FlagStatus,
    MessageStatus,
    MissedDoseRule,
    RegimenChangeType,
    Sex,
)
from app.domain.treatment import Step
from app.models import Flag, Prescription, RiskFactors, Substance
from app.services import (
    assistant,
    attachments,
    audit,
    flags,
    messages,
    patient_card,
    patients,
    safety_plan,
    treatment,
)
from app.services.doses import steps_of

router = APIRouter(prefix="/doctor", tags=["Врач"])


class PatientCardIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    birth_date: date
    sex: Sex | None = None
    city: str | None = Field(None, max_length=100)
    region_code: str | None = Field(None, max_length=32)


@router.post("/patients", response_model=patients.PatientCard, status_code=status.HTTP_201_CREATED)
def create_patient(body: PatientCardIn, doctor: CurrentDoctor, db: DB, now: Now):
    card = patients.create_patient_card(db, doctor_account_id=doctor.account_id, now=now, **body.model_dump())
    db.commit()
    return card


@router.get("/patients", response_model=list[patients.QueueItem])
def queue(doctor: CurrentDoctor, db: DB):
    items = patients.doctor_queue(db, doctor.account_id)
    audit.record(db, actor_account_id=doctor.account_id, actor_role="doctor", action=AuditAction.VIEW,
                 entity="patient_queue", entity_id=None, patient_id=None)
    db.commit()
    return items


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: FlagLevel
    reason: FlagReason
    status: FlagStatus
    details: dict | None
    created_at: datetime
    acknowledged_at: datetime | None


@router.get("/patients/{patient_id}/flags", response_model=list[FlagOut])
def patient_flags(patient: DoctorPatient, db: DB):
    result = db.scalars(select(Flag).where(Flag.patient_id == patient.id).order_by(Flag.created_at.desc())).all()
    db.commit()
    return result


@router.post("/flags/{flag_id}/acknowledge", response_model=FlagOut)
def acknowledge_flag(flag_id: uuid.UUID, request: Request, doctor: CurrentDoctor, db: DB, now: Now):
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Флаг не найден")
    require_doctor_access(db, doctor, flag.patient_id, request)
    flags.acknowledge(db, flag_id=flag_id, doctor_account_id=doctor.account_id, now=now)
    db.commit()
    return flag


class RiskFactorsIn(BaseModel):
    """Исходные факторы риска (компонент 1 §4.6): заполняет врач."""

    prior_suicide_attempt: bool = False
    self_harm: bool = False
    family_suicide: bool = False
    substance_abuse: bool = False
    recent_psychiatric_discharge: bool = False
    lives_alone: bool = False
    chronic_pain_or_severe_illness: bool = False


@router.put("/patients/{patient_id}/risk-factors", response_model=RiskFactorsIn)
def set_risk_factors(body: RiskFactorsIn, patient: DoctorPatient, doctor: CurrentDoctor, db: DB, now: Now):
    row = db.get(RiskFactors, patient.id)
    if row is None:
        row = RiskFactors(patient_id=patient.id, updated_by=doctor.account_id)
        db.add(row)
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    row.updated_by, row.updated_at = doctor.account_id, now
    audit.record(db, actor_account_id=doctor.account_id, actor_role="doctor", action=AuditAction.UPDATE,
                 entity="risk_factors", entity_id=patient.id, patient_id=patient.id, meta=body.model_dump())
    db.commit()
    return body


class StepIn(BaseModel):
    effective_date: date
    dose: Decimal = Field(gt=0)


class FormularyItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inn: str
    trade_names: list[str]
    group_label: str | None
    default_missed_dose_rule: MissedDoseRule | None
    default_missed_dose_hours: int | None


@router.get("/formulary", response_model=list[FormularyItem])
def formulary(doctor: CurrentDoctor, db: DB):
    """Препараты, которые можно внести в схему (демо-база §7.8). Вещества только для проверки взаимодействий — нет."""
    return db.scalars(select(Substance).where(Substance.in_formulary.is_(True)).order_by(Substance.inn)).all()


class PrescriptionIn(BaseModel):
    substance_id: str = Field(max_length=64)
    trade_name: str | None = Field(None, max_length=200)
    form: str = Field(max_length=100)
    dose: Decimal = Field(gt=0)
    unit: str = Field(max_length=16)
    times: list[time] = Field(min_length=1, max_length=6)
    with_food: str | None = Field(None, max_length=16)
    instructions: str | None = Field(None, max_length=1000)
    start_date: date
    end_date: date | None = None
    in_person_visit_date: date
    missed_dose_rule: MissedDoseRule
    missed_dose_hours: int | None = None
    titration: list[StepIn] = Field(default_factory=list, max_length=20)


class StepOut(BaseModel):
    effective_date: date
    dose: Decimal


class PrescriptionOut(BaseModel):
    id: uuid.UUID
    substance_id: str
    trade_name: str | None
    dose: Decimal
    unit: str
    times: list[time]
    start_date: date
    end_date: date | None
    missed_dose_rule: MissedDoseRule
    missed_dose_hours: int | None
    stopped_at: datetime | None
    titration: list[StepOut]


def _out(db, p: Prescription) -> PrescriptionOut:
    return PrescriptionOut(
        id=p.id, substance_id=p.substance_id, trade_name=p.trade_name, dose=p.dose, unit=p.unit, times=p.times,
        start_date=p.start_date, end_date=p.end_date, missed_dose_rule=p.missed_dose_rule,
        missed_dose_hours=p.missed_dose_hours, stopped_at=p.stopped_at,
        titration=[StepOut(effective_date=s.effective_date, dose=s.dose) for s in steps_of(db, p.id)],
    )


@router.post("/patients/{patient_id}/prescriptions", response_model=PrescriptionOut,
             status_code=status.HTTP_201_CREATED)
def prescribe(body: PrescriptionIn, patient: DoctorPatient, doctor: CurrentDoctor, db: DB, now: Now,
              content: ContentDep):
    values = body.model_dump(exclude={"titration"})
    spec = treatment.PrescriptionSpec(**values, titration=[Step(s.effective_date, s.dose) for s in body.titration])
    p = treatment.create_prescription(db, doctor_account_id=doctor.account_id, patient_id=patient.id, spec=spec,
                                      now=now, content=content)
    db.commit()
    return _out(db, p)


def _doctor_prescription(db, doctor, prescription_id: uuid.UUID, request: Request) -> Prescription:
    p = db.get(Prescription, prescription_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Назначение не найдено")
    require_doctor_access(db, doctor, p.patient_id, request)
    return p


class DoseChangeIn(BaseModel):
    effective_date: date
    dose: Decimal = Field(gt=0)
    reason: str | None = Field(None, max_length=500)


@router.post("/prescriptions/{prescription_id}/dose-change", response_model=PrescriptionOut)
def dose_change(prescription_id: uuid.UUID, body: DoseChangeIn, request: Request, doctor: CurrentDoctor, db: DB,
                now: Now, content: ContentDep):
    _doctor_prescription(db, doctor, prescription_id, request)
    p = treatment.change_dose(db, doctor_account_id=doctor.account_id, prescription_id=prescription_id,
                              effective_date=body.effective_date, dose=body.dose, reason=body.reason, now=now,
                              content=content)
    db.commit()
    return _out(db, p)


class ShiftIn(BaseModel):
    days: int
    reason: str | None = Field(None, max_length=500)


@router.post("/prescriptions/{prescription_id}/shift", response_model=PrescriptionOut)
def shift(prescription_id: uuid.UUID, body: ShiftIn, request: Request, doctor: CurrentDoctor, db: DB, now: Now,
          content: ContentDep):
    """«Сдвинуть следующие этапы на N дней» — только по решению врача (§1.3)."""
    p = _doctor_prescription(db, doctor, prescription_id, request)
    treatment.shift_titration(db, doctor_account_id=doctor.account_id, prescription_id=prescription_id,
                              days=body.days, reason=body.reason, now=now, content=content)
    db.commit()
    return _out(db, p)


class StopIn(BaseModel):
    reason: str | None = Field(None, max_length=500)


@router.post("/prescriptions/{prescription_id}/stop", response_model=PrescriptionOut)
def stop(prescription_id: uuid.UUID, body: StopIn, request: Request, doctor: CurrentDoctor, db: DB, now: Now,
         content: ContentDep):
    _doctor_prescription(db, doctor, prescription_id, request)
    p = treatment.stop_prescription(db, doctor_account_id=doctor.account_id, prescription_id=prescription_id,
                                    reason=body.reason, now=now, content=content)
    db.commit()
    return _out(db, p)


@router.get("/prescriptions/{prescription_id}/titration-attention")
def titration_attention(prescription_id: uuid.UUID, request: Request, doctor: CurrentDoctor, db: DB,
                        now: Now) -> dict:
    _doctor_prescription(db, doctor, prescription_id, request)
    result = treatment.titration_needs_attention(db, prescription_id, now)
    db.commit()
    return {"needs_attention": result}


class RegimenChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prescription_id: uuid.UUID
    change_type: RegimenChangeType
    before: dict | None
    after: dict | None
    reason: str | None
    changed_by: uuid.UUID
    changed_at: datetime


@router.get("/patients/{patient_id}/regimen-history", response_model=list[RegimenChangeOut])
def regimen_history(patient: DoctorPatient, db: DB):
    result = treatment.regimen_history(db, patient.id)
    db.commit()
    return result


@router.get("/patients/{patient_id}/treatment-markers", response_model=list[treatment.TreatmentMarker])
def markers(patient: DoctorPatient, db: DB, content: ContentDep):
    result = treatment.treatment_markers(db, patient.id, content)
    db.commit()
    return result


# --- Карточка пациента -----------------------------------------------------------------------


@router.get("/patients/{patient_id}/card", response_model=patient_card.PatientCardSummary)
def card(patient: DoctorPatient, db: DB, now: Now, content: ContentDep):
    result = patient_card.card_summary(db, patient.id, now=now, content=content)
    db.commit()
    return result


@router.get("/patients/{patient_id}/diary", response_model=patient_card.DiaryChart)
def diary_chart(patient: DoctorPatient, db: DB, now: Now, content: ContentDep,
                period: Literal["week", "month", "all"] = "month"):
    """Графики дневника за неделю, месяц или весь период. Пропущенный день — null (разрыв линии)."""
    result = patient_card.diary_chart(db, patient.id, period=period, now=now, content=content)
    db.commit()
    return result


@router.get("/patients/{patient_id}/questionnaires", response_model=list[patient_card.InstrumentHistory])
def questionnaires(patient: DoctorPatient, db: DB, content: ContentDep):
    """PHQ-9 и GAD-7 по неделям: сумма, выраженность, изменение и ответ на каждый вопрос."""
    result = patient_card.questionnaire_history(db, patient.id, content)
    db.commit()
    return result


@router.get("/patients/{patient_id}/adherence", response_model=list[patient_card.PrescriptionAdherence])
def adherence(patient: DoctorPatient, db: DB, now: Now, content: ContentDep):
    result = patient_card.adherence(db, patient.id, now=now, content=content)
    db.commit()
    return result


@router.get("/patients/{patient_id}/side-effects", response_model=list[patient_card.SideEffectEntry])
def side_effects(patient: DoctorPatient, db: DB, content: ContentDep):
    result = patient_card.side_effect_journal(db, patient.id, content)
    db.commit()
    return result


@router.get("/patients/{patient_id}/risk-assessments", response_model=list[patient_card.RiskAssessmentView])
def risk_assessments(patient: DoctorPatient, db: DB, content: ContentDep):
    result = patient_card.risk_assessments(db, patient.id, content)
    db.commit()
    return result


@router.get("/patients/{patient_id}/safety-plan", response_model=safety_plan.SafetyPlanView | None)
def get_safety_plan(patient: DoctorPatient, db: DB):
    result = safety_plan.current_plan(db, patient.id)
    db.commit()
    return result


@router.post("/patients/{patient_id}/safety-plan/review", response_model=safety_plan.SafetyPlanView)
def review_safety_plan(patient: DoctorPatient, doctor: CurrentDoctor, db: DB, now: Now):
    result = safety_plan.mark_reviewed(db, doctor_account_id=doctor.account_id, patient_id=patient.id, now=now)
    db.commit()
    return result


# --- Сообщения и история ассистента ----------------------------------------------------------


@router.get("/messages", response_model=list[messages.InboxItem])
def inbox(doctor: CurrentDoctor, db: DB, status_filter: MessageStatus | None = Query(None, alias="status")):
    """Входящие по всем пациентам: сообщения с кризисными словами — первыми."""
    items = messages.doctor_inbox(db, doctor.account_id, status_filter)
    audit.record(db, actor_account_id=doctor.account_id, actor_role="doctor", action=AuditAction.VIEW,
                 entity="inbox", entity_id=None, patient_id=None)
    db.commit()
    return items


@router.get("/patients/{patient_id}/messages", response_model=list[messages.MessageView])
def patient_messages(patient: DoctorPatient, db: DB, now: Now):
    result = messages.doctor_open_thread(db, patient_id=patient.id, now=now)
    db.commit()
    return result


class ReplyIn(BaseModel):
    body: str = Field(max_length=messages.DOCTOR_REPLY_MAX)
    in_reply_to: uuid.UUID | None = None


@router.post("/patients/{patient_id}/messages", response_model=messages.MessageView,
             status_code=status.HTTP_201_CREATED)
def reply(body: ReplyIn, patient: DoctorPatient, doctor: CurrentDoctor, db: DB, now: Now):
    result = messages.doctor_reply(db, doctor_account_id=doctor.account_id, patient=patient, body=body.body,
                                   in_reply_to=body.in_reply_to, now=now)
    db.commit()
    return result


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: uuid.UUID, request: Request, doctor: CurrentDoctor, db: DB,
                        settings: AppSettings) -> Response:
    patient_id = attachments.patient_of(db, attachment_id)
    if patient_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    require_doctor_access(db, doctor, patient_id, request)
    attachment, data = attachments.load(db, attachment_id=attachment_id, settings=settings)
    db.commit()
    return Response(data, media_type=attachment.mime,
                    headers={"Content-Disposition": f'attachment; filename="{attachment.id}"',
                             "Cache-Control": "no-store"})


@router.get("/patients/{patient_id}/assistant-history", response_model=assistant.AssistantHistory)
def assistant_history(patient: DoctorPatient, db: DB, now: Now, content: ContentDep):
    result = assistant.history(db, patient.id, now=now, content=content)
    db.commit()
    return result
