"""Карточка пациента через HTTP на демо-данных: доступ только лечащему врачу, каждый просмотр — в журнал."""

from sqlalchemy import func, select

from app.content.loader import load_content
from app.models import AuditLog, PatientProfile
from app.seed.demo import DEMO_DOCTOR_EMAIL, LOGINS, seed_demo
from app.services.auth import create_doctor
from tests.api.conftest import START, bearer

PASSWORD = "demo password 2026"
SECTIONS = ("card", "diary?period=week", "diary?period=all", "questionnaires", "adherence", "side-effects",
            "risk-assessments", "safety-plan")


def _setup(api, db):
    seed_demo(db, now=START, content=load_content(), doctor_password=PASSWORD)
    maria = db.scalar(select(PatientProfile).where(PatientProfile.full_name == "Мария Демо"))
    return maria, bearer(api.doctor_tokens(DEMO_DOCTOR_EMAIL, PASSWORD))


def _views(db, patient_id):
    return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.patient_id == patient_id,
                                                                      AuditLog.action == "view"))


def test_every_card_section_for_treating_doctor_is_audited(api, client, db):
    maria, doctor = _setup(api, db)
    before = _views(db, maria.id)
    responses = {s: client.get(f"/api/v1/doctor/patients/{maria.id}/{s}", headers=doctor) for s in SECTIONS}
    assert {s: r.status_code for s, r in responses.items()} == dict.fromkeys(SECTIONS, 200)
    assert _views(db, maria.id) - before == len(SECTIONS)

    card = responses["card"].json()
    assert (card["color"], card["full_name"]) == ("red", "Мария Демо")
    week = responses["diary?period=week"].json()
    assert len(week["series"]["days"]) == 7 and week["series"]["values"]["mood"][-1] is None  # сегодня ещё нет
    assert responses["risk-assessments"].json()[0]["final_level"] == "red"


def test_other_doctor_sees_nothing(api, client, db):
    maria, _ = _setup(api, db)
    create_doctor(db, email="petrov@demo.test", password="another long password", full_name="Петров Пётр",
                  specialty="психотерапевт")
    other = bearer(api.doctor_tokens("petrov@demo.test", "another long password"))
    for section in SECTIONS:
        assert client.get(f"/api/v1/doctor/patients/{maria.id}/{section}", headers=other).status_code == 404


def test_patient_fills_safety_plan_doctor_reviews(api, client, db):
    maria, doctor = _setup(api, db)
    login = LOGINS["maria"]
    patient = bearer(client.post("/api/v1/auth/login", json={"login": login, "code": api.code(login)}).json())

    assert client.get("/api/v1/me/safety-plan", headers=patient).json()["version"] == 1
    bad = client.put("/api/v1/me/safety-plan", headers=patient,
                     json={"contacts": [{"name": "Сестра", "phone": "позвонить вечером"}]})
    assert bad.status_code == 422
    empty = client.put("/api/v1/me/safety-plan", headers=patient, json={})
    assert empty.status_code == 422 and "хотя бы один" in empty.json()["detail"]
    saved = client.put("/api/v1/me/safety-plan", headers=patient, json={
        "warning_signs": "Не сплю ночами", "coping_strategies": "Прогулка, душ",
        "contacts": [{"name": "Сестра (демо)", "phone": "+7 900 000-00-99"}]}).json()
    assert (saved["version"], saved["doctor_reviewed_at"]) == (2, None)

    seen = client.get(f"/api/v1/doctor/patients/{maria.id}/safety-plan", headers=doctor).json()
    assert seen["version"] == 2 and seen["updated_by_role"] == "patient"
    reviewed = client.post(f"/api/v1/doctor/patients/{maria.id}/safety-plan/review", headers=doctor).json()
    assert reviewed["doctor_reviewed_at"] is not None
    assert client.get("/api/v1/me/safety-plan", headers=patient).json()["doctor_reviewed_at"] is not None


def test_diary_period_is_validated(api, client, db):
    maria, doctor = _setup(api, db)
    assert client.get(f"/api/v1/doctor/patients/{maria.id}/diary?period=year", headers=doctor).status_code == 422
