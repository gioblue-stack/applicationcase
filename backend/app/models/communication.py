"""Сообщения, вложения, история ассистента (§1.4, §5.4, §7.11). Переписка не удаляется."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk, str_enum
from app.domain.enums import MessageDirection, MessageOrigin, MessageStatus

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class Message(UUIDPk, CreatedAt, Base):
    __tablename__ = "message"
    __table_args__ = (
        # Лимит 500 знаков — для свободного текста пациента; врач отвечает полностью (§1.4).
        sa.CheckConstraint(
            "direction <> 'patient_to_doctor' OR char_length(body) <= 500", name="patient_body_500"
        ),
        sa.Index("ix_message_patient_time", "patient_id", "created_at"),
    )

    client_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("patient_profile.id"))
    doctor_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("doctor_profile.account_id"))
    direction: Mapped[MessageDirection] = mapped_column(str_enum(MessageDirection))
    origin: Mapped[MessageOrigin] = mapped_column(str_enum(MessageOrigin))
    template_key: Mapped[str | None] = mapped_column(sa.String(128))
    body: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[MessageStatus] = mapped_column(str_enum(MessageStatus), server_default=MessageStatus.NEW.value)
    crisis_match: Mapped[bool] = mapped_column(server_default=sa.false())
    in_reply_to: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("message.id"))
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Attachment(UUIDPk, CreatedAt, Base):
    """Только блок 9: изображения и PDF до 10 МБ (§7.11)."""

    __tablename__ = "attachment"
    __table_args__ = (
        sa.CheckConstraint(f"size_bytes > 0 AND size_bytes <= {MAX_ATTACHMENT_BYTES}", name="size_limit"),
        sa.CheckConstraint("mime LIKE 'image/%' OR mime = 'application/pdf'", name="allowed_mime"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("message.id"), index=True)
    mime: Mapped[str] = mapped_column(sa.String(64))
    size_bytes: Mapped[int]
    storage_key: Mapped[str] = mapped_column(sa.Text)


class AssistantInteraction(UUIDPk, CreatedAt, Base):
    """История вопросов ассистенту. Врач видит её: 5 вопросов про отмену за неделю — сигнал (§1.4)."""

    __tablename__ = "assistant_interaction"

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("patient_profile.id"), index=True)
    button_key: Mapped[str] = mapped_column(sa.String(128))
    answer_sources: Mapped[list[str]] = mapped_column(ARRAY(sa.String(1)))  # Д, И, К, В
    answer_ref: Mapped[str | None] = mapped_column(sa.String(128))
    helped: Mapped[bool | None]
    escalated_message_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("message.id"))
