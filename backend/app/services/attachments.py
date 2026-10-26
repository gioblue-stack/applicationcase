"""Вложения: только в блоке 9, изображения и PDF до 10 МБ (§7.11).

Тип определяется по содержимому файла, а не по расширению или заголовку от клиента.
Файл хранится зашифрованным (AES-256-GCM, ключ MC_DATA_KEY): данные о здоровье шифруются и «на диске».
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.domain.enums import AuditAction, MessageOrigin
from app.models import Attachment, Message, PatientProfile
from app.models.communication import MAX_ATTACHMENT_BYTES
from app.services import audit

MAX_PER_MESSAGE = 5
_SIGNATURES = ((b"%PDF-", "application/pdf"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"))


class AttachmentError(ValueError):
    pass


class AttachmentNotFound(AttachmentError, LookupError):
    pass


def sniff_mime(data: bytes) -> str | None:
    return next((mime for magic, mime in _SIGNATURES if data.startswith(magic)), None)


def _path(settings: Settings, storage_key: str) -> Path:
    return settings.upload_dir / storage_key


def store(db: Session, *, patient: PatientProfile, message_id: uuid.UUID, data: bytes, settings: Settings,
          now: datetime) -> Attachment:
    message = db.get(Message, message_id)
    if message is None or message.patient_id != patient.id:
        raise AttachmentNotFound("Сообщение не найдено")
    if message.origin is not MessageOrigin.BLOCK9_OTHER_DOCTOR:
        raise AttachmentError("Файлы можно прикрепить только в блоке «Я был(а) у другого врача»")
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentError("Файл должен быть не больше 10 МБ")
    mime = sniff_mime(data)
    if mime is None:
        raise AttachmentError("Можно прикрепить фото (JPEG, PNG) или PDF")
    count = db.scalar(select(func.count()).select_from(Attachment).where(Attachment.message_id == message_id))
    if count >= MAX_PER_MESSAGE:
        raise AttachmentError(f"К одному сообщению — не больше {MAX_PER_MESSAGE} файлов")
    storage_key = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    _path(settings, storage_key).write_bytes(security.encrypt_bytes(settings.secret("data_key"), data))
    attachment = Attachment(message_id=message_id, mime=mime, size_bytes=len(data), storage_key=storage_key,
                            created_at=now)
    db.add(attachment)
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="attachment", entity_id=message_id, patient_id=patient.id, meta={"mime": mime})
    db.flush()
    return attachment


def load(db: Session, *, attachment_id: uuid.UUID, settings: Settings) -> tuple[Attachment, bytes]:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise AttachmentNotFound("Файл не найден")
    blob = _path(settings, attachment.storage_key).read_bytes()
    return attachment, security.decrypt_bytes(settings.secret("data_key"), blob)


def patient_of(db: Session, attachment_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(Message.patient_id).join(Attachment, Attachment.message_id == Message.id)
                     .where(Attachment.id == attachment_id))
