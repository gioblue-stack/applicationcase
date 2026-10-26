"""Сообщения пациент ↔ врач (§1.4, §2.4, §5.4, §7.11).

Свободный текст — только в трёх местах (блок 7, блок 9, «Всё равно хочу спросить врача»), до 500 знаков,
и всегда проверяется по кризисным словам: при совпадении сообщение доставляется как обычно,
но пациент сразу видит экран помощи, а врач получает красный флаг (§7.4). Переписка не удаляется.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain.crisis_words import CrisisMatcher, default_matcher
from app.domain.enums import (
    AuditAction,
    FlagLevel,
    FlagReason,
    MessageDirection,
    MessageOrigin,
    MessageStatus,
    NotificationKind,
    PushPriority,
)
from app.domain.flag_rules import FlagCandidate
from app.models import AssistantInteraction, Attachment, CareLink, DoctorProfile, Message, Notification, PatientProfile
from app.services import audit
from app.services.care import active_doctor_id
from app.services.flags import note_patient_activity, raise_flag
from app.services.screens import HelpScreen, help_screen_for
from app.services.thresholds import get_thresholds

FREE_TEXT_ORIGINS = {MessageOrigin.BLOCK7_QUESTION, MessageOrigin.BLOCK9_OTHER_DOCTOR, MessageOrigin.STILL_ASK_DOCTOR}
DOCTOR_REPLY_MAX = 5000
REPLY_NOTIFICATION = ("Новое сообщение", "Новое сообщение в приложении")  # без слов «врач», «лечение»


class MessageError(ValueError):
    pass


class MessageNotFound(MessageError, LookupError):
    pass


@dataclass(frozen=True)
class MessagePreface:
    """Что пациент видит до отправки вопроса (§1.4, §2.4)."""

    doctor_name: str
    response_time_hours: int | None
    working_hours: dict | None
    warning: str


@dataclass(frozen=True)
class AttachmentView:
    id: uuid.UUID
    mime: str
    size_bytes: int


@dataclass(frozen=True)
class MessageView:
    id: uuid.UUID
    direction: MessageDirection
    origin: MessageOrigin
    template_key: str | None
    body: str
    status: MessageStatus
    crisis_match: bool
    created_at: datetime
    in_reply_to: uuid.UUID | None
    attachments: list[AttachmentView] = field(default_factory=list)


@dataclass(frozen=True)
class SentMessage:
    message: MessageView
    created: bool
    help_screen: HelpScreen | None  # кризисные слова → экран помощи сразу


def _view(db: Session, m: Message) -> MessageView:
    files = db.scalars(select(Attachment).where(Attachment.message_id == m.id).order_by(Attachment.created_at))
    return MessageView(m.id, m.direction, m.origin, m.template_key, m.body, m.status, m.crisis_match, m.created_at,
                       m.in_reply_to, [AttachmentView(a.id, a.mime, a.size_bytes) for a in files])


def _doctor_of(db: Session, patient: PatientProfile) -> uuid.UUID:
    doctor_id = active_doctor_id(db, patient.id)
    if doctor_id is None:
        raise MessageError("Сообщения врачу доступны пациенту, подключённому к лечащему врачу")
    return doctor_id


def preface(db: Session, patient: PatientProfile, content: Content) -> MessagePreface:
    doctor = db.get(DoctorProfile, _doctor_of(db, patient))
    return MessagePreface(doctor.full_name, doctor.response_time_hours, doctor.working_hours,
                          content.approved_texts["emergency_disclaimer"].text)


def send_from_patient(
    db: Session, *, patient: PatientProfile, client_id: uuid.UUID, origin: MessageOrigin, body: str, now: datetime,
    content: Content, assistant_interaction_id: uuid.UUID | None = None, matcher: CrisisMatcher | None = None,
) -> SentMessage:
    existing = db.scalar(select(Message).where(Message.client_id == client_id))
    if existing is not None:
        if existing.patient_id != patient.id:
            raise MessageError("client_id уже использован")
        return SentMessage(_view(db, existing), False, None)
    if origin not in FREE_TEXT_ORIGINS:
        raise MessageError("Свободный текст доступен только в блоке 7, блоке 9 и после «Всё равно хочу спросить врача»")
    doctor_id = _doctor_of(db, patient)
    text = body.strip()
    limit = int(get_thresholds(db, content)["free_text_max_chars"])
    if not text:
        raise MessageError("Напишите вопрос")
    if len(text) > limit:
        raise MessageError(f"Сообщение не длиннее {limit} знаков")
    interaction = None
    if assistant_interaction_id is not None:
        interaction = db.get(AssistantInteraction, assistant_interaction_id)
        if interaction is None or interaction.patient_id != patient.id:
            raise MessageNotFound("Ответ ассистента не найден")

    crisis = (matcher or default_matcher()).is_crisis(text)
    message = Message(client_id=client_id, patient_id=patient.id, doctor_id=doctor_id,
                      direction=MessageDirection.PATIENT_TO_DOCTOR, origin=origin, body=text,
                      status=MessageStatus.NEW, crisis_match=crisis, created_at=now)
    db.add(message)
    db.flush()
    if interaction is not None:
        interaction.escalated_message_id = message.id
    help_screen = None
    if crisis:
        raise_flag(db, FlagCandidate(FlagLevel.RED, FlagReason.CRISIS_WORDS, f"crisis_words:message:{message.id}"),
                   patient_id=patient.id, source_type="message", source_id=message.id, now=now)
        help_screen = help_screen_for(content, patient.region_code, has_doctor=True)
    note_patient_activity(db, patient.id, now)
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="message", entity_id=message.id, patient_id=patient.id, meta={"origin": origin.value})
    db.flush()
    return SentMessage(_view(db, message), True, help_screen)


def handoff(db: Session, *, patient: PatientProfile, template_key: str, body: str, now: datetime,
            origin: MessageOrigin = MessageOrigin.ASSISTANT_HANDOFF) -> Message:
    """[В] — шаблонный вопрос уходит врачу без свободного текста пациента."""
    message = Message(patient_id=patient.id, doctor_id=_doctor_of(db, patient),
                      direction=MessageDirection.PATIENT_TO_DOCTOR, origin=origin, template_key=template_key,
                      body=body[:500], status=MessageStatus.NEW, created_at=now)
    db.add(message)
    db.flush()
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="message", entity_id=message.id, patient_id=patient.id, meta={"template": template_key})
    return message


def thread(db: Session, patient_id: uuid.UUID) -> list[MessageView]:
    return [_view(db, m) for m in db.scalars(select(Message).where(Message.patient_id == patient_id)
                                             .order_by(Message.created_at))]


def doctor_open_thread(db: Session, *, patient_id: uuid.UUID, now: datetime) -> list[MessageView]:
    """Врач открыл переписку — новые сообщения пациента становятся прочитанными."""
    for m in db.scalars(select(Message).where(Message.patient_id == patient_id,
                                              Message.direction == MessageDirection.PATIENT_TO_DOCTOR,
                                              Message.status == MessageStatus.NEW)):
        m.status, m.read_at = MessageStatus.READ, now
    db.flush()
    return thread(db, patient_id)


def doctor_reply(db: Session, *, doctor_account_id: uuid.UUID, patient: PatientProfile, body: str,
                 in_reply_to: uuid.UUID | None, now: datetime) -> MessageView:
    """Врач отвечает полностью, своими словами (§1.4)."""
    text = body.strip()
    if not text or len(text) > DOCTOR_REPLY_MAX:
        raise MessageError(f"Ответ — от 1 до {DOCTOR_REPLY_MAX} знаков")
    unanswered = select(Message).where(Message.patient_id == patient.id,
                                       Message.direction == MessageDirection.PATIENT_TO_DOCTOR,
                                       Message.status != MessageStatus.ANSWERED)
    if in_reply_to is not None:
        original = db.get(Message, in_reply_to)
        if original is None or original.patient_id != patient.id or \
                original.direction is not MessageDirection.PATIENT_TO_DOCTOR:
            raise MessageNotFound("Сообщение пациента не найдено")
        unanswered = unanswered.where(Message.id == in_reply_to)
    for m in db.scalars(unanswered):
        m.status, m.answered_at = MessageStatus.ANSWERED, now
        m.read_at = m.read_at or now
    reply = Message(patient_id=patient.id, doctor_id=doctor_account_id, direction=MessageDirection.DOCTOR_TO_PATIENT,
                    origin=MessageOrigin.DOCTOR_REPLY, body=text, status=MessageStatus.READ, in_reply_to=in_reply_to,
                    created_at=now)
    db.add(reply)
    db.flush()
    if patient.account_id is not None:
        title, neutral = REPLY_NOTIFICATION
        db.add(Notification(recipient_account_id=patient.account_id, kind=NotificationKind.DOCTOR_REPLY,
                            priority=PushPriority.NORMAL, title=title, body_neutral=neutral, scheduled_for=now))
    audit.record(db, actor_account_id=doctor_account_id, actor_role="doctor", action=AuditAction.CREATE,
                 entity="message", entity_id=reply.id, patient_id=patient.id)
    db.flush()
    return _view(db, reply)


@dataclass(frozen=True)
class InboxItem:
    message_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    origin: MessageOrigin
    template_key: str | None
    body: str
    status: MessageStatus
    crisis_match: bool
    created_at: datetime
    attachments: int


def doctor_inbox(db: Session, doctor_account_id: uuid.UUID, status: MessageStatus | None) -> list[InboxItem]:
    """Входящие: сообщения с кризисными словами — первыми, дальше свежие сверху."""
    query = (select(Message, PatientProfile.full_name)
             .join(PatientProfile, PatientProfile.id == Message.patient_id)
             .join(CareLink, CareLink.patient_id == Message.patient_id)
             .where(CareLink.doctor_id == doctor_account_id, CareLink.status == "active",
                    Message.direction == MessageDirection.PATIENT_TO_DOCTOR))
    if status is not None:
        query = query.where(Message.status == status)
    items = []
    for m, name in db.execute(query.order_by(Message.crisis_match.desc(), Message.created_at.desc())):
        count = len(db.scalars(select(Attachment.id).where(Attachment.message_id == m.id)).all())
        items.append(InboxItem(m.id, m.patient_id, name, m.origin, m.template_key, m.body, m.status,
                               m.crisis_match, m.created_at, count))
    return items
