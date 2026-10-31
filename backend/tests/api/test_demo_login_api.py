"""ВРЕМЕННЫЙ демо-вход для презентации: по умолчанию выключен, в production не работает, только демо-аккаунты."""

import pytest

from app.content.loader import load_content
from app.seed.demo import seed_demo
from tests.api.conftest import START, bearer


@pytest.fixture
def seeded(db):
    seed_demo(db, now=START, content=load_content(), doctor_password="demo password 2026")


def test_demo_login_is_off_by_default(client, seeded):
    assert client.get("/api/v1/auth/demo").status_code == 404
    assert client.post("/api/v1/auth/demo/login", json={"who": "maria"}).status_code == 404


def test_demo_buttons_log_in_as_doctor_and_patients(client, seeded, settings):
    settings.demo_login = True
    options = client.get("/api/v1/auth/demo").json()
    assert options["doctor"] is True
    assert [(p["key"], p["full_name"]) for p in options["patients"]] == [
        ("anna", "Анна Демо"), ("igor", "Игорь Демо"), ("maria", "Мария Демо"), ("oleg", "Олег Демо")]

    maria = client.post("/api/v1/auth/demo/login", json={"who": "maria"})
    assert maria.status_code == 200 and maria.json()["role"] == "patient"
    assert client.get("/api/v1/me", headers=bearer(maria.json())).json()["full_name"] == "Мария Демо"

    # Врач — без пароля и TOTP, но только демо-врач и только пока включён флаг.
    doctor = client.post("/api/v1/auth/demo/login", json={"who": "doctor"})
    assert doctor.status_code == 200 and doctor.json()["role"] == "doctor"
    queue = client.get("/api/v1/doctor/patients", headers=bearer(doctor.json())).json()
    assert {item["full_name"] for item in queue} >= {"Анна Демо", "Игорь Демо", "Мария Демо"}

    assert client.post("/api/v1/auth/demo/login", json={"who": "admin"}).status_code == 404


def test_demo_login_never_works_in_production(client, seeded, settings):
    settings.demo_login = True
    settings.env = "production"
    assert client.get("/api/v1/auth/demo").status_code == 404
    assert client.post("/api/v1/auth/demo/login", json={"who": "doctor"}).status_code == 404
