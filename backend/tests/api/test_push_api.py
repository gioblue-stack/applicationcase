"""Напоминания на телефон (Web Push): подписка, проверочное уведомление, отправка из очереди воркером."""

import base64
import json
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr
from pywebpush import WebPushException
from sqlalchemy import select

from app.content.loader import load_content
from app.domain.enums import NotificationStatus
from app.models import Device, Notification
from app.services import push
from app.services.doses import run_dose_schedule
from app.services.notifications import dispatch_due
from tests.api.conftest import bearer
from tests.api.test_doctor_api import PRESCRIPTION

SUB = {"endpoint": "https://push.example.test/send/abc", "keys": {"p256dh": "BPk", "auth": "c2Vj"}}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture
def vapid(settings):
    key = ec.generate_private_key(ec.SECP256R1())
    settings.vapid_private_key = SecretStr(_b64(key.private_numbers().private_value.to_bytes(32, "big")))
    settings.vapid_public_key = _b64(key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return settings


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(push, "webpush", lambda **kw: calls.append(kw))
    return calls


@pytest.fixture
def patient(api, doctor_headers):
    card = api.patient_card(doctor_headers, "Анна Демо")
    return card, bearer(api.register_patient(card["invite_code"], "+79004445574"))


def test_without_keys_push_is_unavailable(client, patient):
    _, headers = patient
    assert client.get("/api/v1/me/push", headers=headers).json() == {"available": False, "public_key": None,
                                                                      "devices": 0}
    assert client.post("/api/v1/me/push/test", headers=headers).status_code == 503


def test_subscribe_test_and_unsubscribe(client, patient, vapid, sent):
    _, headers = patient
    status = client.get("/api/v1/me/push", headers=headers).json()
    assert status["available"] is True and status["public_key"] == vapid.vapid_public_key

    assert client.post("/api/v1/me/push/subscribe", headers=headers, json=SUB).status_code == 204
    assert client.post("/api/v1/me/push/subscribe", headers=headers, json=SUB).status_code == 204  # повтор — без дубля
    assert client.get("/api/v1/me/push", headers=headers).json()["devices"] == 1
    bad = client.post("/api/v1/me/push/subscribe", headers=headers, json={"endpoint": "http://x", "keys": {}})
    assert bad.status_code == 422

    assert client.post("/api/v1/me/push/test", headers=headers).json() == {"delivered": 1}
    [call] = sent
    assert call["subscription_info"] == SUB and call["vapid_claims"]["sub"].startswith("mailto:")
    assert json.loads(call["data"])["body"] == "Уведомления работают"

    client.post("/api/v1/me/push/unsubscribe", headers=headers, json={"endpoint": SUB["endpoint"]})
    assert client.get("/api/v1/me/push", headers=headers).json()["devices"] == 0


def test_worker_sends_neutral_dose_reminder_to_phone(client, api, patient, doctor_headers, vapid, sent, db, clock):
    card, headers = patient
    client.post("/api/v1/me/push/subscribe", headers=headers, json=SUB)
    client.post(f"/api/v1/doctor/patients/{card['patient_id']}/prescriptions", headers=doctor_headers,
                json=PRESCRIPTION)
    run_dose_schedule(db, now=clock.now, content=load_content())

    report = dispatch_due(db, now=clock.now + timedelta(hours=7), provider=push.provider_for(vapid))
    assert report.sent and not report.failed
    payloads = [json.loads(c["data"]) for c in sent]
    # На заблокированном экране — без названия препарата и дозы (§2.2).
    assert {p["body"] for p in payloads} == {"Пора отметить приём"} and {p["url"] for p in payloads} == {"/"}
    assert all("Эсциталопрам" not in c["data"] for c in sent)


def test_expired_subscription_is_removed(client, patient, vapid, monkeypatch, db):
    _, headers = patient
    client.post("/api/v1/me/push/subscribe", headers=headers, json=SUB)

    class Gone:
        status_code = 410

    def expired(**_):
        raise WebPushException("gone", response=Gone())

    monkeypatch.setattr(push, "webpush", expired)
    assert client.post("/api/v1/me/push/test", headers=headers).json() == {"delivered": 0}
    assert db.scalars(select(Device)).all() == []
    assert db.scalars(select(Notification).where(Notification.status == NotificationStatus.FAILED)).all() == []


def test_doctor_gets_neutral_red_flag_push(client, patient, doctor_headers, vapid, sent, db, clock):
    _, headers = patient
    assert client.get("/api/v1/doctor/push", headers=doctor_headers).json()["available"] is True
    assert client.post("/api/v1/doctor/push/subscribe", headers=doctor_headers, json=SUB).status_code == 204
    assert client.get("/api/v1/doctor/push", headers=doctor_headers).json()["devices"] == 1

    client.post("/api/v1/me/panic-events", headers=headers,
                json={"client_id": str(uuid.uuid4()), "pressed_at": clock.now.isoformat()})
    report = dispatch_due(db, now=clock.now, provider=push.provider_for(vapid))
    assert report.sent and not report.failed
    [payload] = [json.loads(c["data"]) for c in sent]
    # Без имени пациента и диагноза; по нажатию — очередь, где красные сверху.
    assert payload["title"] == "Красный флаг" and payload["url"] == "/" and "Анна" not in payload["body"]

    client.post("/api/v1/doctor/push/unsubscribe", headers=doctor_headers, json={"endpoint": SUB["endpoint"]})
    assert client.get("/api/v1/doctor/push", headers=doctor_headers).json()["devices"] == 0
