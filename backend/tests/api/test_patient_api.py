"""Приложение пациента через HTTP. Сценарий Марии (§7.13): PHQ-9 → уточняющий блок → красный флаг у врача."""

import uuid

import pytest

from tests.api.conftest import bearer

SUBMITTED = "2026-10-26T15:00:00+03:00"


@pytest.fixture
def maria(api, doctor_headers):
    card = api.patient_card(doctor_headers)
    return card, bearer(api.register_patient(card["invite_code"], "+79001112233"))


def test_maria_phq9_risk_block_red_flag_reaches_doctor(api, client, maria, doctor_headers):
    card, headers = maria
    other = api.patient_card(doctor_headers, "Анна Демо")

    phq9 = client.post("/api/v1/me/questionnaires", headers=headers, json={
        "client_id": str(uuid.uuid4()), "instrument": "PHQ9", "answers": [2, 2, 1, 2, 1, 2, 1, 0, 1],
        "client_submitted_at": SUBMITTED})
    assert phq9.status_code == 201
    body = phq9.json()
    assert body["risk"]["next_step"] == "risk_block"
    assert body["feedback"]["note"] == "Результаты опросников — не диагноз, их обсуждают с врачом."

    block = client.post("/api/v1/me/risk-assessments", headers=headers, json={
        "client_id": str(uuid.uuid4()), "trigger": "phq9_item9", "trigger_ref": body["submission_id"],
        "answers": {"q1": True, "q2": True, "q3": False, "q4": False, "q5": False, "q6": False},
        "client_submitted_at": SUBMITTED}).json()
    assert block["final_level"] == "red"
    assert [p["id"] for p in block["screen"]["phones"]] == ["112", "8-800-100-49-94", "msk-051"]

    queue = client.get("/api/v1/doctor/patients", headers=doctor_headers).json()
    assert [(i["full_name"], i["color"], i["connected"]) for i in queue] == [
        ("Мария Демо", "red", True), ("Анна Демо", "green", False)]
    assert other["patient_id"] == queue[1]["patient_id"]

    flag_id = queue[0]["open_flags"][0]["flag_id"]
    ack = client.post(f"/api/v1/doctor/flags/{flag_id}/acknowledge", headers=doctor_headers)
    assert ack.json()["status"] == "acknowledged"
    assert client.get("/api/v1/doctor/patients", headers=doctor_headers).json()[0]["open_flags"] == []


def test_dismissing_block_with_risk_factors_is_emergency(api, client, maria, doctor_headers):
    card, headers = maria
    assert client.put(f"/api/v1/doctor/patients/{card['patient_id']}/risk-factors", headers=doctor_headers,
                      json={"prior_suicide_attempt": True}).status_code == 200
    phq9 = client.post("/api/v1/me/questionnaires", headers=headers, json={
        "client_id": str(uuid.uuid4()), "instrument": "PHQ9", "answers": [0] * 8 + [1],
        "client_submitted_at": SUBMITTED}).json()
    block = client.post("/api/v1/me/risk-assessments", headers=headers, json={
        "client_id": str(uuid.uuid4()), "trigger": "phq9_item9", "trigger_ref": phq9["submission_id"],
        "client_submitted_at": SUBMITTED}).json()
    assert (block["final_level"], block["screen"]["key"]) == ("emergency", "dismissed")


def test_diary_crisis_words_return_help_screen(client, maria):
    _, headers = maria
    response = client.post("/api/v1/me/diary", headers=headers, json={
        "client_id": str(uuid.uuid4()), "day": "2026-10-26", "client_submitted_at": SUBMITTED, "mood": 2})
    assert response.status_code == 201 and response.json()["help_screen"] is None

    # Вопросы 7–8 недоступны, пока врач не назначил лечение.
    meds = client.post("/api/v1/me/diary", headers=headers, json={
        "client_id": str(uuid.uuid4()), "day": "2026-10-26", "client_submitted_at": SUBMITTED,
        "had_side_effects": True, "side_effects": [{"code": "other", "other_text": "не хочу жить"}]})
    assert meds.status_code == 422 and "не принимает" in meds.json()["detail"]


@pytest.mark.parametrize("bad", [{"mood": "5"}, {"mood": True}, {"mood": 11}])
def test_diary_rejects_non_integers_and_out_of_range(client, maria, bad):
    _, headers = maria
    response = client.post("/api/v1/me/diary", headers=headers, json={
        "client_id": str(uuid.uuid4()), "day": "2026-10-26", "client_submitted_at": SUBMITTED, **bad})
    assert response.status_code == 422


def test_diary_resubmission_is_idempotent(client, maria):
    _, headers = maria
    body = {"client_id": str(uuid.uuid4()), "day": "2026-10-26", "client_submitted_at": SUBMITTED, "mood": 6}
    first = client.post("/api/v1/me/diary", headers=headers, json=body).json()
    again = client.post("/api/v1/me/diary", headers=headers, json=body).json()
    assert (again["entry_id"], again["created"]) == (first["entry_id"], False)


def test_oleg_self_check_and_14_day_limit(api, client):
    headers = bearer(api.register_self("+79005556677"))
    body = {"phq9_answers": [2, 1, 2, 1, 1, 2, 1, 2, 0], "gad7_answers": [1, 1, 1, 1, 1, 1, 1],
            "client_submitted_at": SUBMITTED}
    result = client.post("/api/v1/me/self-check", headers=headers,
                         json=body | {"phq9_client_id": str(uuid.uuid4()), "gad7_client_id": str(uuid.uuid4())})
    assert result.status_code == 201
    assert (result.json()["level"], result.json()["actions"]) == ("pronounced", ["find_specialist"])
    again = client.post("/api/v1/me/self-check", headers=headers,
                        json=body | {"phq9_client_id": str(uuid.uuid4()), "gad7_client_id": str(uuid.uuid4())})
    assert again.status_code == 409 and again.json()["available_at"].startswith("2026-11-09")
    # Уточняющий блок — только у пациента с врачом.
    assert client.post("/api/v1/me/risk-assessments", headers=headers, json={
        "client_id": str(uuid.uuid4()), "trigger": "unscheduled_mood_drop", "client_submitted_at": SUBMITTED,
    }).status_code == 422


def test_bootstrap_content_is_public_and_has_no_doctor_only_data(client):
    response = client.get("/api/v1/content/bootstrap")
    assert response.status_code == 200 and "max-age" in response.headers["Cache-Control"]
    text = response.text
    assert '"112"' in text and "покончить с собой" in text
    for doctor_only in ("severity_bands_doctor_only", "doctor_meaning", "Серотониновый синдром", "Умеренно тяжёлая"):
        assert doctor_only not in text
    assert response.json()["disclaimer"] == "Прототип. Не предназначен для диагностики и лечения. Все данные демонстрационные."
