"""Вход и регистрация: пациент и пользователь — код, врач — пароль + TOTP (§5.2)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DB, AppSettings, ContentDep, Now, get_code_sender
from app.services import auth
from app.services.auth import AuthError, MfaChallenge, TokenPair, TotpSetup
from app.services.code_sender import CodeSender

router = APIRouter(prefix="/auth", tags=["Вход"])
T = TypeVar("T")


def _run(db: Session, action: Callable[[], T]) -> T:
    """Счётчики неудачных попыток и отзыв сессий сохраняются и тогда, когда вход отклонён."""
    try:
        result = action()
    except AuthError:
        db.commit()
        raise
    db.commit()
    return result


class CodeRequest(BaseModel):
    login: str = Field(max_length=254, description="Телефон или e-mail")


class CodeLogin(CodeRequest):
    code: str = Field(min_length=4, max_length=8)


class PatientRegistration(CodeLogin):
    invite_code: str = Field(min_length=4, max_length=16)
    consent_accepted: bool
    consent_version: str = Field(max_length=64)


class SelfRegistration(CodeLogin):
    full_name: str = Field(min_length=1, max_length=200)
    birth_date: date
    region_code: str | None = Field(None, max_length=32)
    consent_accepted: bool
    consent_version: str = Field(max_length=64)


class DoctorLogin(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class MfaToken(BaseModel):
    mfa_token: str = Field(max_length=2048)


class MfaCode(MfaToken):
    code: str = Field(min_length=6, max_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=256)


@router.post("/code", status_code=status.HTTP_202_ACCEPTED)
def request_code(body: CodeRequest, db: DB, now: Now, settings: AppSettings,
                 sender: Annotated[CodeSender, Depends(get_code_sender)]) -> dict:
    _run(db, lambda: auth.request_login_code(db, login=body.login, now=now, settings=settings, sender=sender))
    # Ответ одинаковый для известных и неизвестных адресов.
    return {"detail": "Если адрес указан верно, мы отправили код"}


@router.post("/login", response_model=TokenPair)
def login(body: CodeLogin, db: DB, now: Now, settings: AppSettings):
    return _run(db, lambda: auth.login_with_code(db, login=body.login, code=body.code, now=now, settings=settings))


@router.post("/register/patient", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register_patient(body: PatientRegistration, db: DB, now: Now, settings: AppSettings, content: ContentDep):
    return _run(db, lambda: auth.register_patient(
        db, invite_code=body.invite_code, login=body.login, code=body.code, consent_accepted=body.consent_accepted,
        consent_version=body.consent_version, now=now, settings=settings, content=content))


@router.post("/register/self", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register_self(body: SelfRegistration, db: DB, now: Now, settings: AppSettings, content: ContentDep):
    return _run(db, lambda: auth.register_self_user(
        db, login=body.login, code=body.code, full_name=body.full_name, birth_date=body.birth_date,
        region_code=body.region_code, consent_accepted=body.consent_accepted, consent_version=body.consent_version,
        now=now, settings=settings, content=content))


@router.post("/doctor/login", response_model=MfaChallenge)
def doctor_login(body: DoctorLogin, db: DB, now: Now, settings: AppSettings):
    return _run(db, lambda: auth.doctor_password_login(db, email=body.email, password=body.password, now=now,
                                                       settings=settings))


@router.post("/doctor/totp/setup", response_model=TotpSetup)
def doctor_totp_setup(body: MfaToken, db: DB, now: Now, settings: AppSettings):
    return _run(db, lambda: auth.setup_totp(db, mfa_token=body.mfa_token, now=now, settings=settings))


@router.post("/doctor/mfa", response_model=TokenPair)
def doctor_mfa(body: MfaCode, request: Request, db: DB, now: Now, settings: AppSettings):
    return _run(db, lambda: auth.complete_doctor_mfa(db, mfa_token=body.mfa_token, code=body.code, now=now,
                                                     settings=settings, user_agent=request.headers.get("user-agent")))


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: DB, now: Now, settings: AppSettings):
    return _run(db, lambda: auth.refresh_tokens(db, refresh_token=body.refresh_token, now=now, settings=settings))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, db: DB, now: Now, settings: AppSettings) -> Response:
    _run(db, lambda: auth.logout(db, refresh_token=body.refresh_token, now=now, settings=settings))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
