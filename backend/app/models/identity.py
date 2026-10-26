"""Учётные записи, профили, привязка к врачу, согласие, аудит (§5.2, §5.6)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk, str_enum
from app.domain.enums import AuditAction, CareLinkStatus, ConsentKind, Role, Sex


class Account(UUIDPk, CreatedAt, Base):
    __tablename__ = "account"
    __table_args__ = (sa.CheckConstraint("phone IS NOT NULL OR email IS NOT NULL", name="has_login"),)

    role: Mapped[Role] = mapped_column(str_enum(Role))
    phone: Mapped[str | None] = mapped_column(sa.String(20), unique=True)
    email: Mapped[str | None] = mapped_column(sa.String(254), unique=True)
    # Только у врача: вход по паролю + второй фактор (TOTP).
    password_hash: Mapped[str | None] = mapped_column(sa.Text)
    totp_secret_enc: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    totp_last_step: Mapped[int | None] = mapped_column(sa.BigInteger)  # защита от повторного ввода кода
    failed_login_count: Mapped[int] = mapped_column(server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())


class LoginCode(UUIDPk, CreatedAt, Base):
    """Одноразовый код входа по телефону или e-mail (§5.2). Хранится только HMAC кода."""

    __tablename__ = "login_code"
    __table_args__ = (sa.Index("ix_login_code_login_created", "login", "created_at"),)

    login: Mapped[str] = mapped_column(sa.String(254))
    code_hash: Mapped[str] = mapped_column(sa.String(64))
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class DoctorProfile(Base):
    __tablename__ = "doctor_profile"

    account_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"), primary_key=True)
    full_name: Mapped[str] = mapped_column(sa.Text)
    specialty: Mapped[str] = mapped_column(sa.Text)
    timezone: Mapped[str] = mapped_column(sa.Text, server_default="Europe/Moscow")
    # {"mon": ["09:00", "18:00"], ...}; пациент видит до отправки вопроса.
    working_hours: Mapped[dict | None] = mapped_column(JSONB)
    response_time_hours: Mapped[int | None]
    # Когда присылать push о красных флагах (§5.3).
    red_flag_push_window: Mapped[dict | None] = mapped_column(JSONB)


class PatientProfile(UUIDPk, CreatedAt, Base):
    """Карточка пациента или пользователя без врача.

    Врач создаёт карточку до регистрации пациента (§5.2), поэтому account_id может быть пустым,
    пока пациент не ввёл код-приглашение.
    """

    __tablename__ = "patient_profile"

    account_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("account.id"), unique=True)
    full_name: Mapped[str] = mapped_column(sa.Text)
    birth_date: Mapped[date | None]
    sex: Mapped[Sex | None] = mapped_column(str_enum(Sex))
    city: Mapped[str | None] = mapped_column(sa.Text)
    region_code: Mapped[str | None] = mapped_column(sa.String(32))  # → региональный телефон помощи
    timezone: Mapped[str] = mapped_column(sa.Text, server_default="Europe/Moscow")
    diary_reminder_time: Mapped[time | None]
    quiet_hours_start: Mapped[time | None]
    quiet_hours_end: Mapped[time | None]
    # По умолчанию на заблокированном экране — только нейтральный текст (§2.2).
    notification_details_enabled: Mapped[bool] = mapped_column(server_default=sa.false())
    takes_medication: Mapped[bool] = mapped_column(server_default=sa.false())
    self_reported_diagnosis: Mapped[str | None] = mapped_column(sa.Text)  # только у пользователя, «со слов»


class CareLink(UUIDPk, CreatedAt, Base):
    __tablename__ = "care_link"
    __table_args__ = (
        # В MVP у пациента один лечащий врач.
        sa.Index(
            "uq_care_link_active_patient",
            "patient_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        ),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("doctor_profile.account_id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("patient_profile.id"), index=True)
    invite_code: Mapped[str] = mapped_column(sa.String(16), unique=True)
    invite_expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[CareLinkStatus] = mapped_column(str_enum(CareLinkStatus))
    linked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Consent(UUIDPk, Base):
    __tablename__ = "consent"

    account_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"), index=True)
    kind: Mapped[ConsentKind] = mapped_column(str_enum(ConsentKind))
    text_version: Mapped[str] = mapped_column(sa.Text)
    method: Mapped[str] = mapped_column(sa.Text)  # «электронное согласие в приложении», ЭП и т.п.
    given_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class RefreshToken(UUIDPk, CreatedAt, Base):
    __tablename__ = "refresh_token"

    account_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"), index=True)
    # Ротация: каждый refresh выдаёт новый токен той же «семьи». Повтор старого — признак кражи,
    # тогда отзывается вся семья.
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(sa.Text)


class Device(UUIDPk, CreatedAt, Base):
    __tablename__ = "device"

    account_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"), index=True)
    platform: Mapped[str] = mapped_column(sa.String(16))  # ios | android | web
    push_token: Mapped[str] = mapped_column(sa.Text, unique=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuditLog(Base):
    """Журнал доступа: каждый просмотр и изменение данных пациента (врачебная тайна, §5.6). Только INSERT."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("account.id"))  # None — система
    actor_role: Mapped[str] = mapped_column(sa.String(16))
    action: Mapped[AuditAction] = mapped_column(str_enum(AuditAction))
    entity: Mapped[str] = mapped_column(sa.String(64))
    entity_id: Mapped[str | None] = mapped_column(sa.String(64))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("patient_profile.id"), index=True)
    ip: Mapped[str | None] = mapped_column(sa.String(45))
    meta: Mapped[dict | None] = mapped_column(JSONB)
