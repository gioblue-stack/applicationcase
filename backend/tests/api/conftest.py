"""HTTP-тесты: настоящее приложение FastAPI поверх транзакции тестовой БД.

Время, настройки и доставка кодов подменяются: часы двигает тест, коды перехватываются.
Секреты генерируются на каждый прогон.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import Settings
from app.core.security import totp_code
from app.main import create_app
from app.services.auth import create_doctor

MSK = ZoneInfo("Europe/Moscow")
START = datetime(2026, 10, 26, 15, 0, tzinfo=MSK)
DOCTOR_PASSWORD = "correct horse battery staple"


@dataclass
class Clock:
    now: datetime = START

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@dataclass
class CapturingSender:
    codes: dict[str, str] = field(default_factory=dict)

    def send(self, login: str, code: str) -> None:
        self.codes[login] = code


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(env="test", jwt_secret=secrets.token_urlsafe(32), upload_dir=tmp_path / "uploads",
                    data_key=base64.b64encode(secrets.token_bytes(32)).decode(), otp_pepper=secrets.token_urlsafe(16))


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def sender() -> CapturingSender:
    return CapturingSender()


@pytest.fixture
def client(db, settings, clock, sender):
    app = create_app()

    def test_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[deps.get_db] = test_db
    app.dependency_overrides[deps.get_now] = lambda: clock.now
    app.dependency_overrides[deps.get_app_settings] = lambda: settings
    app.dependency_overrides[deps.get_code_sender] = lambda: sender
    with TestClient(app) as test_client:
        yield test_client


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@dataclass
class Api:
    """Сценарии входа, повторяющиеся во многих тестах."""

    client: TestClient
    clock: Clock
    sender: CapturingSender

    def code(self, login: str) -> str:
        assert self.client.post("/api/v1/auth/code", json={"login": login}).status_code == 202
        return self.sender.codes[login]

    def doctor_tokens(self, email: str, password: str = DOCTOR_PASSWORD) -> dict:
        challenge = self.client.post("/api/v1/auth/doctor/login", json={"email": email, "password": password}).json()
        setup = self.client.post("/api/v1/auth/doctor/totp/setup", json={"mfa_token": challenge["mfa_token"]}).json()
        tokens = self.client.post("/api/v1/auth/doctor/mfa", json={
            "mfa_token": challenge["mfa_token"], "code": totp_code(setup["secret"], self.clock.now)})
        assert tokens.status_code == 200, tokens.text
        return tokens.json() | {"totp_secret": setup["secret"]}

    def patient_card(self, doctor_headers: dict, full_name: str = "Мария Демо",
                     birth_date: str = "1999-05-10") -> dict:
        response = self.client.post("/api/v1/doctor/patients", headers=doctor_headers, json={
            "full_name": full_name, "birth_date": birth_date, "region_code": "moscow"})
        assert response.status_code == 201, response.text
        return response.json()

    def register_patient(self, invite_code: str, login: str) -> dict:
        response = self.client.post("/api/v1/auth/register/patient", json={
            "invite_code": invite_code, "login": login, "code": self.code(login), "consent_accepted": True,
            "consent_version": "health-data-2026-10-alpha"})
        assert response.status_code == 201, response.text
        return response.json()

    def register_self(self, login: str, birth_date: str = "1997-01-01") -> dict:
        response = self.client.post("/api/v1/auth/register/self", json={
            "login": login, "code": self.code(login), "full_name": "Олег Демо", "birth_date": birth_date,
            "consent_accepted": True, "consent_version": "health-data-2026-10-alpha"})
        assert response.status_code == 201, response.text
        return response.json()


@pytest.fixture
def api(client, clock, sender) -> Api:
    return Api(client, clock, sender)


@pytest.fixture
def doctor(db):
    return create_doctor(db, email="ivanova@demo.test", password=DOCTOR_PASSWORD,
                         full_name="Иванова Елена Сергеевна", specialty="врач-психиатр")


@pytest.fixture
def doctor_headers(api, doctor) -> dict:
    return bearer(api.doctor_tokens("ivanova@demo.test"))


def years_ago(years: int, days: int = 0) -> str:
    today = START.date()
    return (date(today.year - years, today.month, today.day) + timedelta(days=days)).isoformat()
