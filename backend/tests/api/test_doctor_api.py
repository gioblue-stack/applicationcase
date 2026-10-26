"""Кабинет врача через HTTP: карточка, доступ только к своим пациентам, схема лечения, приёмы."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.content.loader import load_content
from app.models import AuditLog, DoseEvent
from app.services.auth import create_doctor
from app.services.doses import run_dose_schedule
from tests.api.conftest import MSK, bearer, years_ago

PRESCRIPTION = {
    "substance_id": "escitalopram", "form": "таблетки", "dose": "10", "unit": "мг", "times": ["09:00", "21:00"],
    "start_date": "2026-10-20", "in_person_visit_date": "2026-10-20", "missed_dose_rule": "take_if_more_than_hours",
    "missed_dose_hours": 6, "titration": [{"effective_date": "2026-11-10", "dose": "20"}],
}


def test_patient_card_only_for_adults(client, doctor_headers):
    response = client.post("/api/v1/doctor/patients", headers=doctor_headers, json={
        "full_name": "Подросток", "birth_date": years_ago(17)})
    assert response.status_code == 422 and "18+" in response.json()["detail"]


def test_other_doctor_cannot_see_patient_and_views_are_audited(api, client, doctor_headers, db):
    card = api.patient_card(doctor_headers)
    create_doctor(db, email="petrov@demo.test", password="another long password", full_name="Петров Пётр",
                  specialty="психотерапевт")
    other = bearer(api.doctor_tokens("petrov@demo.test", "another long password"))

    assert client.get(f"/api/v1/doctor/patients/{card['patient_id']}/flags", headers=other).status_code == 404
    assert client.get(f"/api/v1/doctor/patients/{uuid.uuid4()}/flags", headers=other).status_code == 404
    assert client.get(f"/api/v1/doctor/patients/{card['patient_id']}/flags", headers=doctor_headers).status_code == 200
    [view] = db.scalars(select(AuditLog).where(AuditLog.entity == "patient", AuditLog.action == "view")).all()
    assert view.patient_id == uuid.UUID(card["patient_id"]) and view.ip is not None


def test_igor_prescription_misses_and_manual_shift(api, client, doctor_headers, db, clock):
    card = api.patient_card(doctor_headers, "Игорь Демо")
    pid = card["patient_id"]
    # Схему можно внести на приёме, до того как пациент ввёл код.
    created = client.post(f"/api/v1/doctor/patients/{pid}/prescriptions", headers=doctor_headers, json=PRESCRIPTION)
    assert created.status_code == 201, created.text
    prescription = created.json()

    headers = bearer(api.register_patient(card["invite_code"], "+79004445566"))
    [item] = client.get("/api/v1/me/plan", headers=headers).json()
    assert (item["inn"], item["upcoming"]) == ("Эсциталопрам", ["с 10.11.2026 — 20 мг"])

    # Воркер создал приёмы с 25.10; сейчас 26.10 15:00 — приёмы 25.10 21:00 и 26.10 09:00 уже прошли.
    run_dose_schedule(db, now=clock.now - timedelta(days=1, hours=14), content=load_content())
    events = {e.scheduled_at.astimezone(MSK).strftime("%d.%m %H:%M"): e
              for e in db.scalars(select(DoseEvent).where(DoseEvent.patient_id == uuid.UUID(pid)))}
    first = client.post(f"/api/v1/me/doses/{events['25.10 21:00'].id}/response", headers=headers,
                        json={"response": "missed"})
    assert first.status_code == 200
    # До следующего приёма (21:00) ровно 6 ч — правило «больше 6 ч» не выполнено.
    assert first.json()["guidance"]["hint"] == "skip_now"
    second = client.post(f"/api/v1/me/doses/{events['26.10 09:00'].id}/response", headers=headers,
                         json={"response": "missed"}).json()
    assert (second["raised_flags"], second["offer_risk_block"]) == (["missed_doses"], "unscheduled_adherence")
    assert client.post(f"/api/v1/me/doses/{events['26.10 09:00'].id}/response", headers=headers,
                       json={"response": "taken"}).status_code == 422

    attention = client.get(f"/api/v1/doctor/prescriptions/{prescription['id']}/titration-attention",
                           headers=doctor_headers).json()
    assert attention["needs_attention"] is True
    shifted = client.post(f"/api/v1/doctor/prescriptions/{prescription['id']}/shift", headers=doctor_headers,
                          json={"days": 7, "reason": "Два пропуска подряд"}).json()
    assert shifted["titration"] == [{"effective_date": "2026-11-17", "dose": "20.000"}]
    history = client.get(f"/api/v1/doctor/patients/{pid}/regimen-history", headers=doctor_headers).json()
    assert [h["change_type"] for h in history] == ["created", "titration_shifted"]


def test_patient_cannot_answer_someone_elses_dose(api, client, doctor_headers, db, clock):
    card = api.patient_card(doctor_headers, "Игорь Демо")
    client.post(f"/api/v1/doctor/patients/{card['patient_id']}/prescriptions", headers=doctor_headers,
                json=PRESCRIPTION)
    api.register_patient(card["invite_code"], "+79004445566")
    stranger = bearer(api.register_self("+79009998877"))
    event = db.scalars(select(DoseEvent)).first()
    response = client.post(f"/api/v1/me/doses/{event.id}/response", headers=stranger, json={"response": "taken"})
    assert response.status_code == 404


def test_invalid_prescription_explained_in_russian(api, client, doctor_headers):
    card = api.patient_card(doctor_headers)
    response = client.post(f"/api/v1/doctor/patients/{card['patient_id']}/prescriptions", headers=doctor_headers,
                           json=PRESCRIPTION | {"in_person_visit_date": "2026-10-21"})
    assert response.status_code == 422 and "очного приёма" in response.json()["detail"]


def test_other_doctor_cannot_touch_prescription(api, client, doctor_headers, db):
    card = api.patient_card(doctor_headers)
    prescription = client.post(f"/api/v1/doctor/patients/{card['patient_id']}/prescriptions", headers=doctor_headers,
                               json=PRESCRIPTION).json()
    create_doctor(db, email="petrov@demo.test", password="another long password", full_name="Петров Пётр",
                  specialty="психотерапевт")
    other = bearer(api.doctor_tokens("petrov@demo.test", "another long password"))
    for action, body in (("shift", {"days": 3}), ("stop", {}), ("dose-change", {"effective_date": "2026-11-01", "dose": "5"})):
        assert client.post(f"/api/v1/doctor/prescriptions/{prescription['id']}/{action}", headers=other,
                           json=body).status_code == 404
