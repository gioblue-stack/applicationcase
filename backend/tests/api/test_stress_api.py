"""Внешние факторы стресса: опросник при первом входе и раздел в карточке врача."""

import uuid

import pytest

from tests.api.conftest import bearer

URL = "/api/v1/me/stress-factors"


@pytest.fixture
def anna(api, doctor_headers):
    card = api.patient_card(doctor_headers, "Анна Демо")
    return card["patient_id"], bearer(api.register_patient(card["invite_code"], "+79006667788"))


def _flags(client, doctor_headers, patient_id):
    return [f["reason"] for f in client.get(f"/api/v1/doctor/patients/{patient_id}/flags", headers=doctor_headers).json()]


def test_first_visit_answers_reach_doctor_card(client, anna, doctor_headers):
    patient_id, headers = anna
    assert client.get("/api/v1/me/today", headers=headers).json()["stress_check_due"] is True
    assert client.get(f"/api/v1/doctor/patients/{patient_id}/stress-factors", headers=doctor_headers).json() is None

    body = {"client_id": str(uuid.uuid4()), "answers": {"finances": 2, "loneliness": 1, "job_loss": 0},
            "other_text": "Переезд в другой город"}
    first = client.post(URL, headers=headers, json=body)
    assert first.status_code == 201 and first.json()["safety_text"] is None and first.json()["help_screen"] is None
    again = client.post(URL, headers=headers, json=body)  # повторная отправка с телефона — без дубля
    assert again.json()["assessment_id"] == first.json()["assessment_id"] and again.json()["created"] is False
    assert client.get("/api/v1/me/today", headers=headers).json()["stress_check_due"] is False

    view = client.get(f"/api/v1/doctor/patients/{patient_id}/stress-factors", headers=doctor_headers).json()
    assert view["present_count"] == 2 and view["strong_count"] == 1 and view["other_text"] == "Переезд в другой город"
    top = view["answers"][0]
    assert (top["id"], top["label"], top["icd"]) == ("finances", "Есть, влияет сильно", "Z59")
    assert {a["id"]: a["label"] for a in view["answers"]}["housing"] == "Нет ответа"
    assert _flags(client, doctor_headers, patient_id) == []


def test_violence_gives_yellow_flag_and_crisis_text_help_screen(client, anna, doctor_headers):
    patient_id, headers = anna
    r = client.post(URL, headers=headers, json={"client_id": str(uuid.uuid4()), "answers": {"violence": 1},
                                                 "other_text": "не хочу жить"}).json()
    assert "112" in r["safety_text"] and r["help_screen"] is not None
    assert sorted(_flags(client, doctor_headers, patient_id)) == ["crisis_words", "stress_safety"]


@pytest.mark.parametrize("answers", [{"unknown": 1}, {"finances": 3}, {}])
def test_rejects_bad_answers(client, anna, answers):
    _, headers = anna
    assert client.post(URL, headers=headers, json={"client_id": str(uuid.uuid4()), "answers": answers}).status_code == 422


def test_bootstrap_has_stress_questions(client):
    stress = client.get("/api/v1/content/bootstrap").json()["instruments"]["STRESS"]
    assert len(stress["items"]) >= 10 and "approval" not in stress
