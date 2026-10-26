"""Диагноз, схема лечения, титрация, приёмы, анализы (§1.2, §1.3).

Схема в приложении — продолжение назначений очного приёма (ст. 36.2 323-ФЗ),
поэтому у назначения обязательна дата очного приёма.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk, str_enum
from app.domain.enums import (
    DoseStatus,
    LabEventStatus,
    MissedDoseRule,
    OtherMedicationSource,
    RegimenChangeType,
)

PATIENT_FK = "patient_profile.id"


class Diagnosis(UUIDPk, Base):
    __tablename__ = "diagnosis"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["classification", "icd_code"],
            ["icd_code.classification", "icd_code.code"],
            name="fk_diagnosis_icd_code",
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    classification: Mapped[str] = mapped_column(sa.String(16))
    icd_code: Mapped[str] = mapped_column(sa.String(16))
    is_current: Mapped[bool] = mapped_column(server_default=sa.true())
    set_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"))
    set_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class Prescription(UUIDPk, CreatedAt, Base):
    __tablename__ = "prescription"
    __table_args__ = (
        sa.CheckConstraint("dose > 0", name="dose_positive"),
        sa.CheckConstraint(
            "(missed_dose_rule = 'take_if_more_than_hours') = (missed_dose_hours IS NOT NULL)",
            name="missed_dose_hours_iff_rule",
        ),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="dates_ordered"),
        sa.CheckConstraint("in_person_visit_date <= start_date", name="visit_before_start"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    substance_id: Mapped[str] = mapped_column(sa.ForeignKey("substance.id"))
    trade_name: Mapped[str | None] = mapped_column(sa.Text)
    form: Mapped[str] = mapped_column(sa.Text)  # таблетки, капсулы…
    dose: Mapped[float] = mapped_column(sa.Numeric(8, 3))
    unit: Mapped[str] = mapped_column(sa.String(16))
    times: Mapped[list[time]] = mapped_column(ARRAY(sa.Time))
    with_food: Mapped[str | None] = mapped_column(sa.String(16))  # before | after | any
    instructions: Mapped[str | None] = mapped_column(sa.Text)
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    missed_dose_rule: Mapped[MissedDoseRule] = mapped_column(str_enum(MissedDoseRule))
    missed_dose_hours: Mapped[int | None]
    in_person_visit_date: Mapped[date]
    created_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"))
    stopped_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class TitrationStep(UUIDPk, Base):
    __tablename__ = "titration_step"
    __table_args__ = (
        sa.UniqueConstraint("prescription_id", "effective_date"),
        sa.CheckConstraint("dose > 0", name="dose_positive"),
    )

    prescription_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("prescription.id"))
    effective_date: Mapped[date]
    dose: Mapped[float] = mapped_column(sa.Numeric(8, 3))


class RegimenChange(UUIDPk, Base):
    """История изменений схемы: кто, когда, что. Она же — отметки на графиках. Только INSERT."""

    __tablename__ = "regimen_change"

    prescription_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("prescription.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    change_type: Mapped[RegimenChangeType] = mapped_column(str_enum(RegimenChangeType))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(sa.Text)
    changed_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"))
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class DoseEvent(UUIDPk, Base):
    __tablename__ = "dose_event"
    __table_args__ = (
        sa.UniqueConstraint("prescription_id", "scheduled_at"),
        sa.CheckConstraint(
            "status <> 'self_changed' OR actual_dose IS NOT NULL", name="self_changed_has_dose"
        ),
        sa.Index("ix_dose_event_patient_time", "patient_id", "scheduled_at"),
    )

    prescription_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("prescription.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK))
    scheduled_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    planned_dose: Mapped[float] = mapped_column(sa.Numeric(8, 3))
    status: Mapped[DoseStatus] = mapped_column(str_enum(DoseStatus), server_default=DoseStatus.PENDING.value)
    responded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    actual_dose: Mapped[float | None] = mapped_column(sa.Numeric(8, 3))
    snoozed_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class OtherMedication(UUIDPk, Base):
    """Препараты от других врачей, безрецептурные, БАД — для проверки взаимодействий (§2.3)."""

    __tablename__ = "other_medication"
    __table_args__ = (
        sa.CheckConstraint("substance_id IS NOT NULL OR free_name IS NOT NULL", name="has_name"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    substance_id: Mapped[str | None] = mapped_column(sa.ForeignKey("substance.id"))
    free_name: Mapped[str | None] = mapped_column(sa.Text)  # нет в базе → «данных о сочетании нет»
    source: Mapped[OtherMedicationSource] = mapped_column(str_enum(OtherMedicationSource))
    added_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    removed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class LabOrder(UUIDPk, CreatedAt, Base):
    __tablename__ = "lab_order"

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    lab_type: Mapped[str] = mapped_column(sa.Text)  # какие именно анализы — решает врач
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"))


class LabEvent(UUIDPk, Base):
    """Конкретная дата сдачи. Нерегулярные графики (агомелатин: старт, 6, 12, 24 нед.) — набор строк."""

    __tablename__ = "lab_event"

    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("lab_order.id"), index=True)
    due_date: Mapped[date]
    status: Mapped[LabEventStatus] = mapped_column(
        str_enum(LabEventStatus), server_default=LabEventStatus.SCHEDULED.value
    )
    marked_done_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
