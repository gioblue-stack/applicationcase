"""Наблюдение: дневник, опросники, уточняющий блок, тревожная кнопка, план безопасности (§1.1, §4).

Отправленные ответы не редактируются (§1.1): повторное заполнение — новая строка со ссылкой
supersedes_id. UPDATE на этих таблицах запрещён триггером в БД (см. миграцию).
Пропуск — NULL или отсутствие строки, никогда не 0.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk, str_enum
from app.domain.enums import (
    AssessmentOutcome,
    InstrumentCode,
    MedsTaken,
    ResponseLevel,
    RiskTrigger,
    ScheduleStatus,
    SideEffectSource,
    SubmissionContext,
)

PATIENT_FK = "patient_profile.id"


def _scale_0_10(column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{column} BETWEEN 0 AND 10", name=f"{column}_0_10")


class DiaryEntry(UUIDPk, Base):
    __tablename__ = "diary_entry"
    __table_args__ = (
        *(
            _scale_0_10(c)
            for c in ("mood", "interest", "anxiety", "worry_control", "sleep_quality", "energy")
        ),
        sa.CheckConstraint(
            "sleep_hours BETWEEN 0 AND 24 AND sleep_hours * 2 = trunc(sleep_hours * 2)",
            name="sleep_hours_half_steps",
        ),
        sa.Index("ix_diary_entry_patient_day", "patient_id", "day"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)  # идемпотентная оффлайн-синхронизация
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK))
    day: Mapped[date]  # день в таймзоне пациента
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("diary_entry.id"))
    filled_late: Mapped[bool] = mapped_column(server_default=sa.false())
    client_submitted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    # Все показатели без значения по умолчанию: пропущенный вопрос — NULL, а не 0.
    mood: Mapped[int | None] = mapped_column(sa.SmallInteger)
    interest: Mapped[int | None] = mapped_column(sa.SmallInteger)
    anxiety: Mapped[int | None] = mapped_column(sa.SmallInteger)
    worry_control: Mapped[int | None] = mapped_column(sa.SmallInteger)
    sleep_hours: Mapped[float | None] = mapped_column(sa.Numeric(3, 1))
    sleep_quality: Mapped[int | None] = mapped_column(sa.SmallInteger)
    energy: Mapped[int | None] = mapped_column(sa.SmallInteger)
    meds_taken: Mapped[MedsTaken | None] = mapped_column(str_enum(MedsTaken))
    had_side_effects: Mapped[bool | None]


class DiarySideEffect(UUIDPk, Base):
    __tablename__ = "diary_side_effect"

    entry_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("diary_entry.id"), index=True)
    code: Mapped[str] = mapped_column(sa.String(64))
    other_text: Mapped[str | None] = mapped_column(sa.Text)


class QuestionnaireSchedule(UUIDPk, Base):
    __tablename__ = "questionnaire_schedule"
    __table_args__ = (sa.UniqueConstraint("patient_id", "due_date"),)

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK))
    due_date: Mapped[date]
    status: Mapped[ScheduleStatus] = mapped_column(str_enum(ScheduleStatus))
    reminded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class QuestionnaireSubmission(UUIDPk, Base):
    __tablename__ = "questionnaire_submission"
    __table_args__ = (
        sa.CheckConstraint(
            "(instrument = 'PHQ9' AND total_score BETWEEN 0 AND 27)"
            " OR (instrument = 'GAD7' AND total_score BETWEEN 0 AND 21)",
            name="total_in_range",
        ),
        sa.CheckConstraint(
            "difficulty IS NULL OR (instrument = 'PHQ9' AND difficulty BETWEEN 0 AND 3)",
            name="difficulty_phq9_only",
        ),
        sa.Index("ix_questionnaire_submission_patient_time", "patient_id", "instrument", "submitted_at"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK))
    instrument: Mapped[InstrumentCode] = mapped_column(str_enum(InstrumentCode))
    instrument_version: Mapped[str] = mapped_column(sa.String(64))
    context: Mapped[SubmissionContext] = mapped_column(str_enum(SubmissionContext))
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("questionnaire_schedule.id"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("questionnaire_submission.id"))
    total_score: Mapped[int] = mapped_column(sa.SmallInteger)
    difficulty: Mapped[int | None] = mapped_column(sa.SmallInteger)
    client_submitted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class QuestionnaireAnswer(Base):
    """Ответ на каждый пункт — врачу важно, какие именно симптомы изменились (§1.1)."""

    __tablename__ = "questionnaire_answer"
    __table_args__ = (
        sa.CheckConstraint("value BETWEEN 0 AND 3", name="value_0_3"),
        sa.CheckConstraint("item_no BETWEEN 1 AND 9", name="item_no_range"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("questionnaire_submission.id"), primary_key=True
    )
    item_no: Mapped[int] = mapped_column(sa.SmallInteger, primary_key=True)
    value: Mapped[int] = mapped_column(sa.SmallInteger)


class RiskFactors(Base):
    """Исходные факторы риска (компонент 1 §4.6). Заполняет врач, а не пациент."""

    __tablename__ = "risk_factors"

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), primary_key=True)
    prior_suicide_attempt: Mapped[bool] = mapped_column(server_default=sa.false())
    self_harm: Mapped[bool] = mapped_column(server_default=sa.false())
    family_suicide: Mapped[bool] = mapped_column(server_default=sa.false())
    substance_abuse: Mapped[bool] = mapped_column(server_default=sa.false())
    recent_psychiatric_discharge: Mapped[bool] = mapped_column(server_default=sa.false())
    lives_alone: Mapped[bool] = mapped_column(server_default=sa.false())
    chronic_pain_or_severe_illness: Mapped[bool] = mapped_column(server_default=sa.false())
    updated_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())

    FACTOR_FIELDS = (
        "prior_suicide_attempt",
        "self_harm",
        "family_suicide",
        "substance_abuse",
        "recent_psychiatric_discharge",
        "lives_alone",
        "chronic_pain_or_severe_illness",
    )

    @property
    def any_present(self) -> bool:
        return any(getattr(self, name) for name in self.FACTOR_FIELDS)


class RiskAssessment(UUIDPk, Base):
    """Уточняющий блок. Хранит ответы и уровень реагирования — не балл и не «оценку риска»."""

    __tablename__ = "risk_assessment"
    __table_args__ = (
        sa.CheckConstraint(
            "q2 IS TRUE OR (q3 IS NULL AND q4 IS NULL AND q5 IS NULL)", name="follow_up_only_after_q2"
        ),
        sa.CheckConstraint(
            "outcome <> 'dismissed' OR (q1 IS NULL AND q2 IS NULL AND q6 IS NULL)",
            name="dismissed_has_no_answers",
        ),
        sa.Index("ix_risk_assessment_patient_time", "patient_id", "submitted_at"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK))
    trigger: Mapped[RiskTrigger] = mapped_column(str_enum(RiskTrigger))
    trigger_ref: Mapped[uuid.UUID | None]
    block_version: Mapped[str] = mapped_column(sa.String(64))
    q1: Mapped[bool | None]
    q2: Mapped[bool | None]
    q3: Mapped[bool | None]
    q4: Mapped[bool | None]
    q5: Mapped[bool | None]
    q6: Mapped[bool | None]
    outcome: Mapped[AssessmentOutcome] = mapped_column(str_enum(AssessmentOutcome))
    base_level: Mapped[ResponseLevel] = mapped_column(str_enum(ResponseLevel, "response_level_base"))
    final_level: Mapped[ResponseLevel] = mapped_column(str_enum(ResponseLevel, "response_level_final"))
    risk_factors_present: Mapped[bool]
    escalated_by_risk_factors: Mapped[bool]
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    client_submitted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class PanicEvent(UUIDPk, Base):
    __tablename__ = "panic_event"

    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    pressed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))  # время на устройстве
    received_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class SafetyPlan(UUIDPk, CreatedAt, Base):
    """План безопасности (§2.5). Каждое изменение — новая версия."""

    __tablename__ = "safety_plan"
    __table_args__ = (sa.UniqueConstraint("patient_id", "version"),)

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK))
    version: Mapped[int]
    warning_signs: Mapped[str | None] = mapped_column(sa.Text)
    coping_strategies: Mapped[str | None] = mapped_column(sa.Text)
    contacts: Mapped[list | None] = mapped_column(JSONB)  # [{"name", "phone"}] — «Позвонить близкому»
    professionals: Mapped[list | None] = mapped_column(JSONB)
    means_restriction: Mapped[str | None] = mapped_column(sa.Text)
    updated_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"))
    doctor_reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class SideEffectReport(UUIDPk, Base):
    """Журнал побочных эффектов (§1.1)."""

    __tablename__ = "side_effect_report"

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(PATIENT_FK), index=True)
    code: Mapped[str] = mapped_column(sa.String(64))
    other_text: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[SideEffectSource] = mapped_column(str_enum(SideEffectSource))
    source_ref: Mapped[uuid.UUID | None]
    alarming_symptom_code: Mapped[str | None] = mapped_column(sa.ForeignKey("alarming_symptom.code"))
    is_new: Mapped[bool]
    reported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
