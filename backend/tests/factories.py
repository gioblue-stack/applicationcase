"""Минимальные фабрики тестовых данных. Все люди — вымышленные."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.domain.enums import CareLinkStatus, DoseStatus, InstrumentCode, MissedDoseRule, Role, SubmissionContext
from app.models import (
    Account,
    CareLink,
    DoctorProfile,
    DoseEvent,
    PatientProfile,
    Prescription,
    QuestionnaireAnswer,
    QuestionnaireSubmission,
    RiskFactors,
    Substance,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # 15:00 по Москве


def make_doctor(db: Session, full_name: str = "Иванова Елена Сергеевна") -> DoctorProfile:
    account = Account(role=Role.DOCTOR, email=f"doctor-{uuid.uuid4().hex[:8]}@demo.test", password_hash="x")
    db.add(account)
    db.flush()
    doctor = DoctorProfile(account_id=account.id, full_name=full_name, specialty="врач-психиатр")
    db.add(doctor)
    db.flush()
    return doctor


def make_patient(
    db: Session,
    full_name: str = "Мария Демо",
    region_code: str | None = "moscow",
    role: Role = Role.PATIENT,
    takes_medication: bool = False,
) -> PatientProfile:
    account = Account(role=role, phone=f"+7900{secrets.randbelow(10**7):07d}")
    db.add(account)
    db.flush()
    patient = PatientProfile(account_id=account.id, full_name=full_name, region_code=region_code,
                             takes_medication=takes_medication)
    db.add(patient)
    db.flush()
    return patient


def link(db: Session, doctor: DoctorProfile, patient: PatientProfile, linked_at: datetime = NOW) -> CareLink:
    care_link = CareLink(
        doctor_id=doctor.account_id,
        patient_id=patient.id,
        invite_code=secrets.token_hex(4),
        invite_expires_at=linked_at + timedelta(days=7),
        status=CareLinkStatus.ACTIVE,
        linked_at=linked_at,
    )
    db.add(care_link)
    db.flush()
    return care_link


def make_phq9(db: Session, patient: PatientProfile, answers: list[int],
              context: SubmissionContext = SubmissionContext.WEEKLY, submitted_at: datetime = NOW) -> QuestionnaireSubmission:
    assert len(answers) == 9
    submission = QuestionnaireSubmission(
        client_id=uuid.uuid4(),
        patient_id=patient.id,
        instrument=InstrumentCode.PHQ9,
        instrument_version="ru-pfizer-v1",
        context=context,
        total_score=sum(answers),
        client_submitted_at=submitted_at,
        submitted_at=submitted_at,
    )
    db.add(submission)
    db.flush()
    db.add_all(
        QuestionnaireAnswer(submission_id=submission.id, item_no=no, value=value)
        for no, value in enumerate(answers, start=1)
    )
    db.flush()
    return submission


def set_risk_factors(db: Session, patient: PatientProfile, doctor: DoctorProfile, **factors: bool) -> RiskFactors:
    row = RiskFactors(patient_id=patient.id, updated_by=doctor.account_id, **factors)
    db.add(row)
    db.flush()
    return row


def make_prescription(db: Session, patient: PatientProfile, doctor: DoctorProfile,
                      substance_id: str = "venlafaxine") -> Prescription:
    if db.get(Substance, substance_id) is None:
        db.add(Substance(id=substance_id, inn=substance_id, in_formulary=True))
        db.flush()
    prescription = Prescription(
        patient_id=patient.id, substance_id=substance_id, form="таблетки", dose=75, unit="мг",
        times=[time(9, 0)], start_date=date(2026, 10, 1), missed_dose_rule=MissedDoseRule.SKIP_NO_DOUBLE,
        in_person_visit_date=date(2026, 10, 1), created_by=doctor.account_id,
    )
    db.add(prescription)
    db.flush()
    return prescription


def make_dose(db: Session, prescription: Prescription, scheduled_at: datetime, status: DoseStatus,
              actual_dose: float | None = None) -> DoseEvent:
    event = DoseEvent(
        prescription_id=prescription.id, patient_id=prescription.patient_id, scheduled_at=scheduled_at,
        planned_dose=75, status=status, actual_dose=actual_dose,
        responded_at=None if status in (DoseStatus.PENDING, DoseStatus.NO_RESPONSE) else scheduled_at,
    )
    db.add(event)
    db.flush()
    return event
