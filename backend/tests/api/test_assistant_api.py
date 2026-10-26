"""Ассистент, сообщения и вложения через HTTP на демо-данных (Игорь, §7.13)."""

import uuid

import pytest
from sqlalchemy import select

from app.content.loader import load_content
from app.models import PatientProfile
from app.seed.demo import DEMO_DOCTOR_EMAIL, LOGINS, seed_demo
from app.services.auth import create_doctor
from tests.api.conftest import START, bearer

PASSWORD = "demo password 2026"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def igor(api, client, db):
    seed_demo(db, now=START, content=load_content(), doctor_password=PASSWORD)
    patient = db.scalar(select(PatientProfile).where(PatientProfile.full_name == "Игорь Демо"))
    login = LOGINS["igor"]
    tokens = client.post("/api/v1/auth/login", json={"login": login, "code": api.code(login)}).json()
    return patient, bearer(tokens), bearer(api.doctor_tokens(DEMO_DOCTOR_EMAIL, PASSWORD))


def test_tree_and_answer(client, igor):
    _, me, _ = igor
    tree = client.get("/api/v1/me/assistant", headers=me).json()
    assert [b["no"] for b in tree["blocks"]] == list(range(1, 10))
    answer = client.post("/api/v1/me/assistant/answers", headers=me, json={"button_id": "missed_dose"}).json()
    assert answer["parts"][0]["source"] == "Д" and answer["follow_up"] == ["helped", "still_ask_doctor"]
    assert client.post(f"/api/v1/me/assistant/interactions/{answer['interaction_id']}/feedback", headers=me,
                       json={"helped": False}).status_code == 204
    assert client.post("/api/v1/me/assistant/answers", headers=me, json={"button_id": "nope"}).status_code == 404


def test_combination_and_bootstrap_choices(client, igor):
    _, me, _ = igor
    result = client.post("/api/v1/me/assistant/combinations", headers=me, json={"substance_id": "aspirin"}).json()
    assert [f["rule_id"] for f in result["findings"]][:1] == ["bleeding"] and result["handed_to_doctor"]
    names = {s["id"] for s in client.get("/api/v1/content/bootstrap").json()["interaction_substances"]}
    assert {"maoi", "tramadol", "alcohol"} <= names


def test_crisis_message_reaches_doctor_first_and_doctor_replies(client, igor):
    patient, me, doctor = igor
    preface = client.get("/api/v1/me/messages/preface", headers=me).json()
    assert preface["response_time_hours"] == 24
    sent = client.post("/api/v1/me/messages", headers=me, json={
        "client_id": str(uuid.uuid4()), "origin": "still_ask_doctor", "body": "Покончить с собой хочется иногда"})
    assert sent.status_code == 201 and sent.json()["help_screen"]["key"] == "help"
    assert client.post("/api/v1/me/messages", headers=me, json={
        "client_id": str(uuid.uuid4()), "origin": "assistant_handoff", "body": "x"}).status_code == 422

    inbox = client.get("/api/v1/doctor/messages?status=new", headers=doctor).json()
    assert inbox[0]["crisis_match"] is True and inbox[0]["patient_name"] == "Игорь Демо"
    thread = client.get(f"/api/v1/doctor/patients/{patient.id}/messages", headers=doctor).json()
    assert all(m["status"] in ("read", "answered") for m in thread if m["direction"] == "patient_to_doctor")
    reply = client.post(f"/api/v1/doctor/patients/{patient.id}/messages", headers=doctor,
                        json={"body": "Видел ваше сообщение, позвоню сегодня.", "in_reply_to": inbox[0]["message_id"]})
    assert reply.status_code == 201
    mine = client.get("/api/v1/me/messages", headers=me).json()
    assert mine[-1]["direction"] == "doctor_to_patient"


def test_block9_attachment_upload_and_download(client, db, api, igor):
    patient, me, doctor = igor
    message = client.post("/api/v1/me/messages", headers=me, json={
        "client_id": str(uuid.uuid4()), "origin": "block9_other_doctor", "body": "Заключение кардиолога"}).json()
    upload = client.post(f"/api/v1/me/messages/{message['message']['id']}/attachments", headers=me,
                         files={"file": ("photo.jpg", PNG, "image/jpeg")})
    assert upload.status_code == 201 and upload.json()["mime"] == "image/png"  # тип — по содержимому
    downloaded = client.get(f"/api/v1/doctor/attachments/{upload.json()['id']}", headers=doctor)
    assert downloaded.content == PNG and downloaded.headers["cache-control"] == "no-store"

    create_doctor(db, email="petrov@demo.test", password="another long password", full_name="Петров Пётр",
                  specialty="психотерапевт")
    other = bearer(api.doctor_tokens("petrov@demo.test", "another long password"))
    assert client.get(f"/api/v1/doctor/attachments/{upload.json()['id']}", headers=other).status_code == 404


def test_doctor_sees_assistant_history(client, igor):
    patient, me, doctor = igor
    for _ in range(2):
        client.post("/api/v1/me/assistant/answers", headers=me, json={"button_id": "reduce_or_stop"})
    history = client.get(f"/api/v1/doctor/patients/{patient.id}/assistant-history", headers=doctor).json()
    assert history["week_counts"]["reduce_or_stop"] == 2
