"""Карточка пациента для врача (§1.1–§1.3): сводка, графики дневника, опросники по неделям,
приверженность, журнал побочных эффектов, ответы уточняющего блока.

Только чтение. Каждый запрос врача пишет журнал доступа на уровне API (зависимость doctor_patient).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain import scoring
from app.domain.charts import AdherenceSummary, DiarySeries, adherence_summary, diary_series, effective_dose_status
from app.domain.enums import CareLinkStatus, DoseStatus, InstrumentCode, ResponseLevel, RiskTrigger, Sex
from app.domain.flag_rules import PatientColor, patient_color
from app.domain.interactions import substance_from_content
from app.domain.risk_protocol import QUESTION_IDS
from app.models import (
    CareLink,
    Diagnosis,
    DiaryEntry,
    DoseEvent,
    IcdCode,
    OtherMedication,
    PatientProfile,
    Prescription,
    QuestionnaireAnswer,
    QuestionnaireSubmission,
    RiskAssessment,
    RiskFactors,
    SideEffectReport,
)
from app.services.care import get_patient, local_now
from app.services.diary import effective_entries
from app.services.flags import last_activity_at
from app.services.patients import OpenFlag, age_on, open_flags
from app.services.safety_plan import current_plan
from app.services.thresholds import get_thresholds
from app.services.treatment import PlanItem, TreatmentMarker, patient_plan, titration_needs_attention, treatment_markers

Period = Literal["week", "month", "all"]
PERIOD_DAYS = {"week": 7, "month": 30}
_INCREASE_KEY = {InstrumentCode.PHQ9: "phq9_increase_yellow", InstrumentCode.GAD7: "gad7_increase_yellow"}


# --- Графики дневника ------------------------------------------------------------------------


@dataclass(frozen=True)
class DiaryChart:
    period: str
    start: date
    end: date
    series: DiarySeries
    markers: list[TreatmentMarker]  # вертикальные отметки изменений лечения на тех же графиках


def _first_day(db: Session, patient: PatientProfile, today: date) -> date:
    candidates = [
        db.scalar(select(func.min(DiaryEntry.day)).where(DiaryEntry.patient_id == patient.id)),
        db.scalar(select(func.min(Prescription.start_date)).where(Prescription.patient_id == patient.id)),
        db.scalar(select(func.min(CareLink.linked_at)).where(CareLink.patient_id == patient.id)),
    ]
    days = [c if isinstance(c, date) and not isinstance(c, datetime) else local_now(patient, c).date()
            for c in candidates if c is not None]
    return min(days + [today])


def diary_chart(db: Session, patient_id: uuid.UUID, *, period: Period, now: datetime, content: Content) -> DiaryChart:
    patient = get_patient(db, patient_id)
    today = local_now(patient, now).date()
    start = today - timedelta(days=PERIOD_DAYS[period] - 1) if period in PERIOD_DAYS else _first_day(db, patient, today)
    series = diary_series(effective_entries(db, patient_id, start, today), start, today)
    markers = [m for m in treatment_markers(db, patient_id, content) if start <= m.day <= today]
    return DiaryChart(period, start, today, series, markers)


# --- PHQ-9 и GAD-7 ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemAnswer:
    no: int
    text: str
    value: int
    label: str


@dataclass(frozen=True)
class QuestionnairePoint:
    submission_id: uuid.UUID
    submitted_at: datetime
    context: str
    total: int
    severity: str  # для врача; пациенту показываются только мягкие формулировки (§7.3)
    change: int | None  # к предыдущему действующему заполнению
    significant_change: bool  # |изменение| ≥ порога (PHQ-9 — 5, GAD-7 — 4)
    superseded_by: uuid.UUID | None  # пациент заполнил заново; обе версии хранятся (§1.1)
    difficulty_label: str | None
    safety_item_positive: bool | None  # 9-й вопрос PHQ-9 ≠ «Ни разу»
    answers: list[ItemAnswer]


@dataclass(frozen=True)
class InstrumentHistory:
    instrument: InstrumentCode
    title: str
    threshold: int
    points: list[QuestionnairePoint]


def questionnaire_history(db: Session, patient_id: uuid.UUID, content: Content) -> list[InstrumentHistory]:
    t = get_thresholds(db, content)
    submissions = db.scalars(select(QuestionnaireSubmission).where(QuestionnaireSubmission.patient_id == patient_id)
                             .order_by(QuestionnaireSubmission.submitted_at)).all()
    superseded_by = {s.supersedes_id: s.id for s in submissions if s.supersedes_id}
    answers: dict[uuid.UUID, dict[int, int]] = defaultdict(dict)
    for a in db.scalars(select(QuestionnaireAnswer).where(
            QuestionnaireAnswer.submission_id.in_([s.id for s in submissions]))):
        answers[a.submission_id][a.item_no] = a.value

    result = []
    for code in (InstrumentCode.PHQ9, InstrumentCode.GAD7):
        definition = content.instrument(code)
        labels = {o.value: o.label for o in definition.options}
        threshold = int(t[_INCREASE_KEY[code]])
        previous: dict[str, int] = {}
        points = []
        for s in (s for s in submissions if s.instrument == code):
            effective = s.id not in superseded_by
            change = s.total_score - previous[s.context] if effective and s.context in previous else None
            if effective:
                previous[s.context] = s.total_score
            items = answers[s.id]
            difficulty = None
            if s.difficulty is not None and definition.difficulty:
                difficulty = {o.value: o.label for o in definition.difficulty.options}[s.difficulty]
            points.append(QuestionnairePoint(
                submission_id=s.id, submitted_at=s.submitted_at, context=s.context.value, total=s.total_score,
                severity=scoring.severity_band_for_doctor(definition, s.total_score), change=change,
                significant_change=change is not None and abs(change) >= threshold,
                superseded_by=superseded_by.get(s.id), difficulty_label=difficulty,
                safety_item_positive=items.get(definition.safety_item, 0) > 0 if definition.safety_item else None,
                answers=[ItemAnswer(i.no, i.text, items[i.no], labels[items[i.no]]) for i in definition.items
                         if i.no in items],
            ))
        result.append(InstrumentHistory(code, definition.title, threshold, points))
    return result


# --- Приверженность --------------------------------------------------------------------------


@dataclass(frozen=True)
class DoseIssue:
    dose_event_id: uuid.UUID
    scheduled_at: datetime
    status: DoseStatus
    planned_dose: Decimal
    actual_dose: Decimal | None


@dataclass(frozen=True)
class PrescriptionAdherence:
    prescription_id: uuid.UUID
    inn: str
    active: bool
    week: AdherenceSummary
    month: AdherenceSummary
    issues: list[DoseIssue]  # пропуски, самостоятельные изменения, «нет ответа» за 30 дней — свежие сверху


def adherence(db: Session, patient_id: uuid.UUID, *, now: datetime, content: Content) -> list[PrescriptionAdherence]:
    patient = get_patient(db, patient_id)
    today = local_now(patient, now).date()
    tz = local_now(patient, now).tzinfo
    month_from = datetime.combine(today - timedelta(days=29), time(0), tzinfo=tz)
    week_from = datetime.combine(today - timedelta(days=6), time(0), tzinfo=tz)
    hours = int(get_thresholds(db, content)["dose_no_response_after_hours"])
    result = []
    prescriptions = db.scalars(select(Prescription).where(Prescription.patient_id == patient_id)
                               .order_by(Prescription.stopped_at.is_not(None), Prescription.start_date.desc()))
    for p in prescriptions:
        events = db.scalars(select(DoseEvent).where(DoseEvent.prescription_id == p.id,
                                                    DoseEvent.scheduled_at >= month_from,
                                                    DoseEvent.scheduled_at <= now)
                            .order_by(DoseEvent.scheduled_at.desc())).all()
        statuses = [(e, effective_dose_status(e.status, e.scheduled_at, now, no_response_hours=hours)) for e in events]
        statuses = [(e, s) for e, s in statuses if s is not None]
        result.append(PrescriptionAdherence(
            prescription_id=p.id, inn=content.drugs.by_id(p.substance_id).inn, active=p.stopped_at is None,
            week=adherence_summary(s for e, s in statuses if e.scheduled_at >= week_from),
            month=adherence_summary(s for _, s in statuses),
            issues=[DoseIssue(e.id, e.scheduled_at, s, e.planned_dose, e.actual_dose) for e, s in statuses
                    if s in (DoseStatus.MISSED, DoseStatus.SELF_CHANGED, DoseStatus.NO_RESPONSE)],
        ))
    return result


# --- Журнал побочных эффектов ----------------------------------------------------------------


@dataclass(frozen=True)
class SideEffectEntry:
    id: uuid.UUID
    reported_at: datetime
    code: str
    label: str
    other_text: str | None
    source: str
    is_new: bool
    alarming: bool
    doctor_meaning: str | None  # «что может означать» — только врачу (§7.5)


def side_effect_journal(db: Session, patient_id: uuid.UUID, content: Content) -> list[SideEffectEntry]:
    labels = {o.code: o.label for o in content.diary.side_effect_options}
    alarming = {s.code: s for s in content.alarming_symptoms.symptoms}
    entries = []
    for r in db.scalars(select(SideEffectReport).where(SideEffectReport.patient_id == patient_id)
                        .order_by(SideEffectReport.reported_at.desc())):
        symptom = alarming.get(r.alarming_symptom_code or "")
        entries.append(SideEffectEntry(
            id=r.id, reported_at=r.reported_at, code=r.code,
            label=symptom.patient_text if symptom else labels.get(r.code, r.code), other_text=r.other_text,
            source=r.source.value, is_new=r.is_new, alarming=symptom is not None,
            doctor_meaning=symptom.doctor_meaning if symptom else None,
        ))
    return entries


# --- Уточняющий блок -------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockAnswer:
    id: str
    text: str
    answer: bool | None  # None — не задавался или пациент закрыл блок


@dataclass(frozen=True)
class RiskAssessmentView:
    id: uuid.UUID
    submitted_at: datetime
    trigger: RiskTrigger
    outcome: str
    base_level: ResponseLevel
    final_level: ResponseLevel
    risk_factors_present: bool
    escalated_by_risk_factors: bool
    answers: list[BlockAnswer]


def risk_assessments(db: Session, patient_id: uuid.UUID, content: Content) -> list[RiskAssessmentView]:
    texts = {q.id: q.text for q in content.suicide_block.questions}
    return [
        RiskAssessmentView(
            id=r.id, submitted_at=r.submitted_at, trigger=r.trigger, outcome=r.outcome.value,
            base_level=r.base_level, final_level=r.final_level, risk_factors_present=r.risk_factors_present,
            escalated_by_risk_factors=r.escalated_by_risk_factors,
            answers=[BlockAnswer(q, texts[q], getattr(r, q)) for q in QUESTION_IDS],
        )
        for r in db.scalars(select(RiskAssessment).where(RiskAssessment.patient_id == patient_id)
                            .order_by(RiskAssessment.submitted_at.desc()))
    ]


# --- Сводка ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class DiagnosisView:
    classification: str
    code: str
    title: str
    set_at: datetime


@dataclass(frozen=True)
class LatestScore:
    instrument: InstrumentCode
    total: int
    severity: str
    change: int | None
    significant_change: bool
    submitted_at: datetime


@dataclass(frozen=True)
class OtherMedicationView:
    name: str
    source: str
    added_at: datetime


@dataclass(frozen=True)
class PatientCardSummary:
    patient_id: uuid.UUID
    full_name: str
    age: int | None
    sex: Sex | None
    city: str | None
    connected: bool  # пациент вошёл по коду-приглашению
    color: PatientColor
    open_flags: list[OpenFlag]
    diagnoses: list[DiagnosisView]
    latest_scores: list[LatestScore]
    treatment: list[PlanItem]
    titration_attention: list[uuid.UUID]  # назначения, где пропуск пришёлся на текущий этап перед повышением
    adherence_week_percent: float | None
    other_medications: list[OtherMedicationView]
    risk_factors: dict | None
    safety_plan_version: int | None
    safety_plan_reviewed_at: datetime | None
    last_activity_at: datetime | None


def _medication_name(content: Content, m: OtherMedication) -> str:
    known = substance_from_content(content, m.substance_id) if m.substance_id else None
    return known.name if known else (m.free_name or m.substance_id or "")


def card_summary(db: Session, patient_id: uuid.UUID, *, now: datetime, content: Content) -> PatientCardSummary:
    patient = get_patient(db, patient_id)
    flags = open_flags(db, patient_id)
    diagnoses = [
        DiagnosisView(d.classification, d.icd_code, title, d.set_at)
        for d, title in db.execute(
            select(Diagnosis, IcdCode.title)
            .join(IcdCode, (IcdCode.classification == Diagnosis.classification) & (IcdCode.code == Diagnosis.icd_code))
            .where(Diagnosis.patient_id == patient_id, Diagnosis.is_current)
            .order_by(Diagnosis.set_at.desc()))
    ]
    latest = []
    for history in questionnaire_history(db, patient_id, content):
        effective = [p for p in history.points if p.superseded_by is None and p.context == "weekly"]
        if effective:
            p = effective[-1]
            latest.append(LatestScore(history.instrument, p.total, p.severity, p.change, p.significant_change,
                                      p.submitted_at))
    adherence_rows = adherence(db, patient_id, now=now, content=content)
    week = [row.week for row in adherence_rows if row.active]
    due = sum(w.due for w in week)
    taken = sum(w.taken + w.taken_late for w in week)
    factors = db.get(RiskFactors, patient_id)
    plan = current_plan(db, patient_id)
    active_ids = db.scalars(select(Prescription.id).where(Prescription.patient_id == patient_id,
                                                          Prescription.stopped_at.is_(None))).all()
    return PatientCardSummary(
        patient_id=patient.id, full_name=patient.full_name,
        age=age_on(patient.birth_date, local_now(patient, now).date()) if patient.birth_date else None,
        sex=patient.sex, city=patient.city,
        connected=db.scalar(select(exists().where(CareLink.patient_id == patient_id,
                                                  CareLink.status == CareLinkStatus.ACTIVE))),
        color=patient_color(f.level for f in flags), open_flags=flags, diagnoses=diagnoses, latest_scores=latest,
        treatment=patient_plan(db, patient_id, now, content),
        titration_attention=[pid for pid in active_ids if titration_needs_attention(db, pid, now)],
        adherence_week_percent=round(100 * taken / due, 1) if due else None,
        other_medications=[
            OtherMedicationView(_medication_name(content, m), m.source.value, m.added_at)
            for m in db.scalars(select(OtherMedication).where(OtherMedication.patient_id == patient_id,
                                                              OtherMedication.removed_at.is_(None)))
        ],
        risk_factors={name: getattr(factors, name) for name in RiskFactors.FACTOR_FIELDS} if factors else None,
        safety_plan_version=plan.version if plan else None,
        safety_plan_reviewed_at=plan.doctor_reviewed_at if plan else None,
        last_activity_at=last_activity_at(db, patient_id),
    )
