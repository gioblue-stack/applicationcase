import base64
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.content.loader import load_content
from app.core.config import Settings
from app.domain.enums import FlagReason, MessageOrigin, MessageStatus, NotificationKind, Role
from app.models import Flag, Notification
from app.services import attachments, messages
from tests.factories import link, make_doctor, make_patient

CONTENT = load_content()
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
PDF = b"%PDF-1.4\n% demo\n"


@pytest.fixture
def pair(db):
    doctor = make_doctor(db)
    doctor.response_time_hours = 24
    patient = make_patient(db)
    link(db, doctor, patient)
    return doctor, patient


def send(db, patient, body="Можно ли пить кофе?", origin=MessageOrigin.BLOCK7_QUESTION, client_id=None, now=NOW):
    return messages.send_from_patient(db, patient=patient, client_id=client_id or uuid.uuid4(), origin=origin,
                                      body=body, now=now, content=CONTENT)


def test_preface_shows_deadline_and_not_emergency_warning(db, pair):
    _, patient = pair
    preface = messages.preface(db, patient, CONTENT)
    assert preface.response_time_hours == 24
    assert preface.warning == "Это не канал экстренной связи. Если вам сейчас очень плохо — нажмите тревожную кнопку"


def test_regular_question_and_idempotency(db, pair):
    _, patient = pair
    client_id = uuid.uuid4()
    sent = send(db, patient, client_id=client_id)
    assert (sent.message.status, sent.message.crisis_match, sent.help_screen) == (MessageStatus.NEW, False, None)
    again = send(db, patient, client_id=client_id)
    assert (again.created, again.message.id) == (False, sent.message.id)


def test_crisis_words_deliver_message_open_help_and_flag(db, pair):
    _, patient = pair
    sent = send(db, patient, body="Вопрос про дозу. И честно — иногда не хочу жить.")
    assert sent.message.crisis_match and sent.help_screen.key == "help"
    flag = db.scalars(select(Flag).where(Flag.patient_id == patient.id)).one()
    assert (flag.level, flag.reason) == ("red", FlagReason.CRISIS_WORDS)


@pytest.mark.parametrize(("body", "origin", "match"), [
    ("", MessageOrigin.BLOCK7_QUESTION, "Напишите"),
    ("я" * 501, MessageOrigin.BLOCK7_QUESTION, "500"),
    ("текст", MessageOrigin.ASSISTANT_HANDOFF, "Свободный текст доступен только"),
])
def test_free_text_rules(db, pair, body, origin, match):
    _, patient = pair
    with pytest.raises(messages.MessageError, match=match):
        send(db, patient, body=body, origin=origin)


def test_user_without_doctor_cannot_message(db):
    user = make_patient(db, role=Role.SELF_USER)
    with pytest.raises(messages.MessageError, match="лечащему врачу"):
        send(db, user)


def test_doctor_reads_and_replies(db, pair):
    doctor, patient = pair
    first = send(db, patient).message
    crisis = send(db, patient, body="суицид", now=NOW + timedelta(minutes=1)).message
    inbox = messages.doctor_inbox(db, doctor.account_id, MessageStatus.NEW)
    assert [i.message_id for i in inbox] == [crisis.id, first.id]  # кризис — первым

    thread = messages.doctor_open_thread(db, patient_id=patient.id, now=NOW)
    assert {m.status for m in thread} == {MessageStatus.READ}
    reply = messages.doctor_reply(db, doctor_account_id=doctor.account_id, patient=patient,
                                  body="Кофе можно, но не позже 16:00.", in_reply_to=first.id, now=NOW)
    statuses = {m.id: m.status for m in messages.thread(db, patient.id)}
    assert (statuses[first.id], statuses[crisis.id]) == (MessageStatus.ANSWERED, MessageStatus.READ)
    assert reply.in_reply_to == first.id
    note = db.scalars(select(Notification).where(Notification.kind == NotificationKind.DOCTOR_REPLY)).one()
    assert note.body_neutral == "Новое сообщение в приложении"

    other = make_patient(db, "Другой Пациент")
    link(db, doctor, other)
    with pytest.raises(messages.MessageNotFound):
        messages.doctor_reply(db, doctor_account_id=doctor.account_id, patient=other, body="…", in_reply_to=first.id,
                              now=NOW)


@pytest.fixture
def settings(tmp_path):
    return Settings(upload_dir=tmp_path, data_key=base64.b64encode(secrets.token_bytes(32)).decode())


def test_attachment_encrypted_at_rest_and_only_in_block9(db, pair, settings):
    _, patient = pair
    block9 = send(db, patient, body="Был у кардиолога", origin=MessageOrigin.BLOCK9_OTHER_DOCTOR).message
    stored = attachments.store(db, patient=patient, message_id=block9.id, data=PDF, settings=settings, now=NOW)
    on_disk = (settings.upload_dir / stored.storage_key).read_bytes()
    assert b"%PDF" not in on_disk
    _, data = attachments.load(db, attachment_id=stored.id, settings=settings)
    assert (stored.mime, data) == ("application/pdf", PDF)

    with pytest.raises(attachments.AttachmentError, match="фото"):
        attachments.store(db, patient=patient, message_id=block9.id, data=b"MZ\x90 exe", settings=settings, now=NOW)
    with pytest.raises(attachments.AttachmentError, match="10 МБ"):
        attachments.store(db, patient=patient, message_id=block9.id, data=PDF + b"0" * 10 * 1024 * 1024,
                          settings=settings, now=NOW)
    block7 = send(db, patient).message
    with pytest.raises(attachments.AttachmentError, match="блоке"):
        attachments.store(db, patient=patient, message_id=block7.id, data=PDF, settings=settings, now=NOW)
