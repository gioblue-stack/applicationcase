"""Перевод исключений сервисов в HTTP-ответы. Тексты ошибок — для пользователя, на русском."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import SecretNotConfigured
from app.domain.diary import InvalidDiary
from app.domain.risk_protocol import InvalidAnswers
from app.domain.scoring import InvalidQuestionnaire
from app.domain.treatment import InvalidDoseResponse, InvalidRegimen
from app.services.auth import AccountLocked, AuthError, TooManyRequests
from app.services.care import PatientNotFound
from app.services.code_sender import SenderNotConfigured
from app.services.diary import DiaryError
from app.services.doses import DoseError, DoseNotFound
from app.services.flags import FlagError
from app.services.patients import PatientCardError
from app.services.questionnaires import QuestionnaireError, SelfCheckTooSoon
from app.services.assistant import AssistantError, InteractionNotFound
from app.services.attachments import AttachmentError, AttachmentNotFound
from app.services.messages import MessageError, MessageNotFound
from app.services.risk_protocol import RiskProtocolError
from app.services.safety_plan import SafetyPlanError
from app.services.treatment import TreatmentError

VALIDATION_ERRORS = (
    InvalidAnswers, InvalidDiary, InvalidQuestionnaire, InvalidRegimen, InvalidDoseResponse,
    RiskProtocolError, DiaryError, QuestionnaireError, TreatmentError, DoseError, FlagError, PatientCardError,
    SafetyPlanError, MessageError, AttachmentError, AssistantError,
)


def _detail(status: int, exc: Exception, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": str(exc), **extra})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    async def auth_error(_: Request, exc: AuthError):
        headers = {}
        if isinstance(exc, TooManyRequests):
            headers["Retry-After"] = str(exc.retry_after)
        if exc.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        extra = {"locked_until": exc.until.isoformat()} if isinstance(exc, AccountLocked) else {}
        return JSONResponse(status_code=exc.status, content={"detail": str(exc), **extra}, headers=headers)

    @app.exception_handler(SelfCheckTooSoon)
    async def self_check_too_soon(_: Request, exc: SelfCheckTooSoon):
        return _detail(409, exc, available_at=exc.available_at.isoformat())

    for error in VALIDATION_ERRORS:
        app.add_exception_handler(error, lambda _, exc: _detail(422, exc))

    for error in (PatientNotFound, DoseNotFound, MessageNotFound, AttachmentNotFound, InteractionNotFound,
                  LookupError):
        app.add_exception_handler(error, lambda _, exc: _detail(404, exc))

    @app.exception_handler(SecretNotConfigured)
    @app.exception_handler(SenderNotConfigured)
    async def not_configured(_: Request, __: Exception):
        return JSONResponse(status_code=503, content={"detail": "Сервис не настроен"})
