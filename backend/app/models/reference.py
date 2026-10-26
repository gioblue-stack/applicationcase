"""Справочники. Наполняются из content/*.json; врач и пациент их не редактируют."""

from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, str_enum
from app.domain.enums import FlagLevel, InteractionSeverity, MissedDoseRule, TextStatus


class IcdCode(Base):
    """Диагнозы. Классификация — часть ключа, чтобы перейти на МКБ-11 без переделки схемы (§5.2)."""

    __tablename__ = "icd_code"

    classification: Mapped[str] = mapped_column(sa.String(16), primary_key=True)  # ICD-10 | ICD-11
    code: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    title: Mapped[str] = mapped_column(sa.Text)


class Instrument(Base):
    """Версии опросников. Каждый ответ ссылается на версию текста, который видел пациент."""

    __tablename__ = "instrument"

    code: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    version: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    definition: Mapped[dict] = mapped_column(JSONB)
    loaded_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class Substance(Base):
    """Препараты демо-базы (§7.8) и вещества для проверки взаимодействий (трамадол, алкоголь…)."""

    __tablename__ = "substance"

    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)  # slug: sertraline
    inn: Mapped[str] = mapped_column(sa.Text)  # МНН
    trade_names: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), server_default="{}")
    group_label: Mapped[str | None] = mapped_column(sa.Text)
    classes: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), server_default="{}")  # ssri, snri, maoi…
    in_formulary: Mapped[bool] = mapped_column(server_default=sa.false())  # можно назначить в схеме
    default_missed_dose_rule: Mapped[MissedDoseRule | None] = mapped_column(str_enum(MissedDoseRule))
    default_missed_dose_hours: Mapped[int | None]
    instruction: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(sa.Text)


class InteractionRule(Base):
    __tablename__ = "interaction_rule"

    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    # {"substances": [...]} или {"classes": [...]}
    selector_a: Mapped[dict] = mapped_column(JSONB)
    selector_b: Mapped[dict] = mapped_column(JSONB)
    severity: Mapped[InteractionSeverity] = mapped_column(str_enum(InteractionSeverity))
    patient_text: Mapped[str] = mapped_column(sa.Text)
    ask_doctor: Mapped[bool]
    source: Mapped[str | None] = mapped_column(sa.Text)


class ApprovedText(Base):
    """Тексты [К] и прочие медицинские тексты с отметкой утверждения (§5.4)."""

    __tablename__ = "approved_text"
    __table_args__ = (
        sa.CheckConstraint(
            "status <> 'approved' OR (approved_by_name IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_signed",
        ),
    )

    key: Mapped[str] = mapped_column(sa.String(128), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[TextStatus] = mapped_column(str_enum(TextStatus))
    approved_by_name: Mapped[str | None] = mapped_column(sa.Text)
    approved_at: Mapped[date | None]
    review_due: Mapped[date | None]


class HelpPhone(Base):
    __tablename__ = "help_phone"

    id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    display: Mapped[str] = mapped_column(sa.Text)
    tel: Mapped[str] = mapped_column(sa.String(20))
    service: Mapped[str] = mapped_column(sa.Text)
    region: Mapped[str] = mapped_column(sa.String(32))  # "*" — вся Россия
    hours: Mapped[str] = mapped_column(sa.Text)
    verified_at: Mapped[date]


class AlarmingSymptom(Base):
    """Тревожные побочные симптомы (§7.5). doctor_meaning пациенту не показывается."""

    __tablename__ = "alarming_symptom"

    code: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    patient_text: Mapped[str] = mapped_column(sa.Text)
    doctor_meaning: Mapped[str] = mapped_column(sa.Text)
    action: Mapped[str] = mapped_column(sa.String(64))  # emergency_112 | contact_doctor_today… | risk_protocol
    flag_level: Mapped[FlagLevel | None] = mapped_column(str_enum(FlagLevel))


class Threshold(Base):
    """Пороги флагов (§7.2): меняются врачами без новой сборки."""

    __tablename__ = "threshold"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[float] = mapped_column(sa.Numeric)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_by: Mapped[str | None] = mapped_column(sa.Text)


class SpecialistDemo(Base):
    """Демонстрационный каталог специалистов (§3.2)."""

    __tablename__ = "specialist_demo"

    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)
    full_name: Mapped[str] = mapped_column(sa.Text)
    specialty: Mapped[str] = mapped_column(sa.Text)
    experience_years: Mapped[int]
    format: Mapped[str] = mapped_column(sa.String(16))  # offline | online | both
    city: Mapped[str | None] = mapped_column(sa.Text)
    price_rub: Mapped[int | None]
    documents_verified: Mapped[bool]
