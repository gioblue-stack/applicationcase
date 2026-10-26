"""Флаги срочности и уведомления (§1.1, §5.3)."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk, str_enum
from app.domain.enums import (
    FlagLevel,
    FlagReason,
    FlagStatus,
    NotificationKind,
    NotificationStatus,
    PushPriority,
)


class Flag(UUIDPk, CreatedAt, Base):
    """Флаг с причиной и ссылкой на источник. Закрывает только врач (В6)."""

    __tablename__ = "flag"
    __table_args__ = (
        # Повтор той же причины не плодит открытые флаги.
        sa.Index(
            "uq_flag_open_dedupe",
            "patient_id",
            "dedupe_key",
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
        ),
        sa.CheckConstraint(
            "(status = 'open') = (acknowledged_at IS NULL)", name="ack_consistent"
        ),
        sa.Index("ix_flag_patient_status", "patient_id", "status"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("patient_profile.id"))
    level: Mapped[FlagLevel] = mapped_column(str_enum(FlagLevel))
    reason: Mapped[FlagReason] = mapped_column(str_enum(FlagReason))
    source_type: Mapped[str] = mapped_column(sa.String(64))
    source_id: Mapped[uuid.UUID | None]
    dedupe_key: Mapped[str] = mapped_column(sa.String(128))
    details: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[FlagStatus] = mapped_column(str_enum(FlagStatus), server_default=FlagStatus.OPEN.value)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("account.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Notification(UUIDPk, CreatedAt, Base):
    """Очередь уведомлений. body_neutral — для заблокированного экрана: без препаратов и диагнозов."""

    __tablename__ = "notification"
    __table_args__ = (sa.Index("ix_notification_due", "status", "scheduled_for"),)

    recipient_account_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("account.id"), index=True)
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind))
    priority: Mapped[PushPriority] = mapped_column(str_enum(PushPriority))
    title: Mapped[str] = mapped_column(sa.Text)
    body_neutral: Mapped[str] = mapped_column(sa.Text)
    body_detailed: Mapped[str | None] = mapped_column(sa.Text)  # только если пациент включил подробности
    scheduled_for: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus), server_default=NotificationStatus.SCHEDULED.value
    )
    related_flag_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("flag.id"))
    # Напоминание о приёме отменяется, если пациент уже отметил приём (в т.ч. отложенное «через 15 минут»).
    related_dose_event_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("dose_event.id", ondelete="CASCADE"), index=True
    )
