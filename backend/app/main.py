"""Точка входа API: uvicorn app.main:app"""

from fastapi import APIRouter, FastAPI

from app.api.errors import install_error_handlers
from app.api.routers import auth, content, doctor, patient

DISCLAIMER = "Прототип. Не предназначен для диагностики и лечения. Все данные демонстрационные."


def create_app() -> FastAPI:
    app = FastAPI(title="MindCare — прототип", description=DISCLAIMER, version="0.1.0")
    install_error_handlers(app)
    api = APIRouter(prefix="/api/v1")
    for module in (auth, content, patient, doctor):
        api.include_router(module.router)
    app.include_router(api)

    @app.get("/health", tags=["Служебное"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
