"""Вход и регистрация через HTTP (§5.2)."""

from sqlalchemy import select

from app.core.security import totp_code
from app.models import AuditLog, Consent
from tests.api.conftest import DOCTOR_PASSWORD, bearer, years_ago

CONSENT = "health-data-2026-10-alpha"
PHONE = "+79001234567"


def test_code_is_sent_for_unknown_login_and_rate_limited(client, clock, sender):
    assert client.post("/api/v1/auth/code", json={"login": "8 (900) 123-45-67"}).status_code == 202
    assert PHONE in sender.codes  # телефон нормализован
    again = client.post("/api/v1/auth/code", json={"login": PHONE})
    assert again.status_code == 429 and int(again.headers["Retry-After"]) > 0
    clock.advance(seconds=61)
    assert client.post("/api/v1/auth/code", json={"login": PHONE}).status_code == 202


def test_malformed_login_rejected(client):
    assert client.post("/api/v1/auth/code", json={"login": "12"}).status_code == 422


def test_patient_joins_doctor_by_invite_code(api, client, doctor_headers, db):
    card = api.patient_card(doctor_headers)
    assert card["qr_payload"] == f"mindcare://invite/{card['invite_code']}"
    tokens = api.register_patient(card["invite_code"].lower(), PHONE)
    assert tokens["role"] == "patient"
    me = client.get("/api/v1/me", headers=bearer(tokens)).json()
    assert (me["patient_id"], me["has_doctor"]) == (card["patient_id"], True)
    consent = db.scalars(select(Consent)).one()
    assert consent.text_version == CONSENT

    clock_code = api.code("+79007654321")
    reused = client.post("/api/v1/auth/register/patient", json={
        "invite_code": card["invite_code"], "login": "+79007654321", "code": clock_code,
        "consent_accepted": True, "consent_version": CONSENT})
    assert reused.status_code == 422 and "недействителен" in reused.json()["detail"]


def test_registration_requires_current_consent(api, client, doctor_headers):
    card = api.patient_card(doctor_headers)
    code = api.code(PHONE)
    body = {"invite_code": card["invite_code"], "login": PHONE, "code": code}
    for consent in ({"consent_accepted": False, "consent_version": CONSENT},
                    {"consent_accepted": True, "consent_version": "old"}):
        response = client.post("/api/v1/auth/register/patient", json=body | consent)
        assert response.status_code == 422
    # Код не потрачен на отклонённые попытки без согласия.
    ok = client.post("/api/v1/auth/register/patient", json=body | {"consent_accepted": True, "consent_version": CONSENT})
    assert ok.status_code == 201


def test_login_code_burns_after_five_wrong_attempts(api, client):
    api.register_self(PHONE)
    api.clock.advance(minutes=2)
    code = api.code(PHONE)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"login": PHONE, "code": wrong}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"login": PHONE, "code": code}).status_code == 401


def test_login_code_expires(api, client, clock):
    api.register_self(PHONE)
    clock.advance(minutes=2)
    code = api.code(PHONE)
    clock.advance(minutes=11)
    assert client.post("/api/v1/auth/login", json={"login": PHONE, "code": code}).status_code == 401


def test_unknown_account_gets_same_answer_as_wrong_code(api, client):
    code = api.code(PHONE)
    response = client.post("/api/v1/auth/login", json={"login": PHONE, "code": code})
    assert (response.status_code, response.json()["detail"]) == (401, "Неверный код или пароль")


def test_self_user_must_be_adult_and_login_is_unique(api, client, clock):
    minor = client.post("/api/v1/auth/register/self", json={
        "login": PHONE, "code": api.code(PHONE), "full_name": "Подросток", "birth_date": years_ago(18, days=1),
        "consent_accepted": True, "consent_version": CONSENT})
    assert minor.status_code == 422 and "18+" in minor.json()["detail"]
    clock.advance(minutes=2)
    assert api.register_self(PHONE)["role"] == "self_user"
    clock.advance(minutes=2)
    taken = client.post("/api/v1/auth/register/self", json={
        "login": PHONE, "code": api.code(PHONE), "full_name": "Олег", "birth_date": "1990-01-01",
        "consent_accepted": True, "consent_version": CONSENT})
    assert taken.status_code == 409
    clock.advance(minutes=2)
    login = client.post("/api/v1/auth/login", json={"login": PHONE, "code": api.code(PHONE)})
    assert login.status_code == 200 and login.json()["role"] == "self_user"


def test_doctor_needs_password_and_totp(api, client, doctor, clock, db):
    bad = client.post("/api/v1/auth/doctor/login", json={"email": "ivanova@demo.test", "password": "wrong password"})
    assert (bad.status_code, bad.json()["detail"]) == (401, "Неверный код или пароль")

    challenge = client.post("/api/v1/auth/doctor/login",
                            json={"email": "IVANOVA@demo.test", "password": DOCTOR_PASSWORD}).json()
    assert challenge["totp_enrolled"] is False
    # Токен первого фактора не открывает API.
    assert client.get("/api/v1/doctor/patients",
                      headers={"Authorization": f"Bearer {challenge['mfa_token']}"}).status_code == 401

    secret = client.post("/api/v1/auth/doctor/totp/setup", json={"mfa_token": challenge["mfa_token"]}).json()["secret"]
    assert client.post("/api/v1/auth/doctor/mfa", json={"mfa_token": challenge["mfa_token"], "code": "000000"}) \
        .status_code == 401
    code = totp_code(secret, clock.now)
    tokens = client.post("/api/v1/auth/doctor/mfa", json={"mfa_token": challenge["mfa_token"], "code": code}).json()
    assert client.get("/api/v1/doctor/patients", headers=bearer(tokens)).status_code == 200

    second = client.post("/api/v1/auth/doctor/login", json={"email": "ivanova@demo.test", "password": DOCTOR_PASSWORD}).json()
    assert second["totp_enrolled"] is True
    assert client.post("/api/v1/auth/doctor/totp/setup", json={"mfa_token": second["mfa_token"]}).status_code == 409
    replay = client.post("/api/v1/auth/doctor/mfa", json={"mfa_token": second["mfa_token"], "code": code})
    assert replay.status_code == 401  # тот же код второй раз не принимается
    clock.advance(seconds=30)
    fresh = client.post("/api/v1/auth/doctor/mfa",
                        json={"mfa_token": second["mfa_token"], "code": totp_code(secret, clock.now)})
    assert fresh.status_code == 200
    assert db.scalars(select(AuditLog).where(AuditLog.entity == "session")).all()


def test_doctor_locked_after_five_failures(client, doctor, clock):
    for _ in range(5):
        client.post("/api/v1/auth/doctor/login", json={"email": "ivanova@demo.test", "password": "wrong password"})
    locked = client.post("/api/v1/auth/doctor/login", json={"email": "ivanova@demo.test", "password": DOCTOR_PASSWORD})
    assert locked.status_code == 423 and "locked_until" in locked.json()
    clock.advance(minutes=16)
    assert client.post("/api/v1/auth/doctor/login",
                       json={"email": "ivanova@demo.test", "password": DOCTOR_PASSWORD}).status_code == 200


def test_access_expires_refresh_rotates_and_reuse_kills_session(api, client, clock):
    tokens = api.register_self(PHONE)
    clock.advance(minutes=16)
    assert client.get("/api/v1/me", headers=bearer(tokens)).status_code == 401
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    assert client.get("/api/v1/me", headers=bearer(rotated)).status_code == 200
    # Повтор старого refresh-токена: признак кражи — закрывается вся цепочка, включая новый токен.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}).status_code == 401


def test_doctor_refresh_expires_after_idle_timeout(api, client, doctor, clock):
    tokens = api.doctor_tokens("ivanova@demo.test")
    clock.advance(minutes=20)
    tokens = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    clock.advance(minutes=20)  # активность продлевает сессию
    tokens = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    clock.advance(minutes=31)
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_logout_revokes_session(api, client):
    tokens = api.register_self(PHONE)
    assert client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_roles_are_separated(api, client, doctor_headers):
    patient = bearer(api.register_self(PHONE))
    assert client.get("/api/v1/doctor/patients", headers=patient).status_code == 403
    assert client.get("/api/v1/me", headers=doctor_headers).status_code == 403
    assert client.get("/api/v1/me").status_code == 401
