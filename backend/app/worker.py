"""Фоновый воркер: расписания приёмов и опросников, напоминания, «нет данных 7 дней», отправка push.

Каждая задача идемпотентна и выполняется в своей транзакции: сбой одной не мешает остальным,
повтор после сбоя не создаёт дублей. Одновременно работает один воркер — его держит
advisory-блокировка PostgreSQL, второй экземпляр ждёт, пока первый не остановится.

Отличие от ARCHITECTURE.md (arq + Redis): для MVP хватает цикла поверх PostgreSQL —
на одну зависимость меньше. Очередь можно вынести в Redis, не меняя сами задачи.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.content.models import Content
from app.core.security import utcnow
from app.services.doses import run_dose_schedule
from app.services.flags import check_no_data
from app.services.notifications import PushProvider, create_diary_reminders, dispatch_due
from app.services.thresholds import get_thresholds
from app.services.weekly_schedule import run_weekly_schedule

log = logging.getLogger("mindcare.worker")

WORKER_LOCK_KEY = 0x6D696E64  # «mind»


@dataclass(frozen=True)
class Job:
    name: str
    interval: timedelta
    run: Callable[[Session, datetime], object]


def default_jobs(content: Content, provider: PushProvider) -> list[Job]:
    """Порядок важен: отправка — последней, чтобы ушло всё, что создано в этом же проходе."""
    return [
        Job("doses", timedelta(minutes=5), lambda db, now: run_dose_schedule(db, now=now, content=content)),
        Job("weekly_questionnaires", timedelta(minutes=15),
            lambda db, now: run_weekly_schedule(db, now=now, content=content)),
        Job("diary_reminders", timedelta(minutes=5),
            lambda db, now: create_diary_reminders(db, now=now, content=content)),
        Job("no_data", timedelta(hours=1),
            lambda db, now: check_no_data(db, now=now, days=int(get_thresholds(db, content)["no_data_days_yellow"]))),
        Job("dispatch", timedelta(minutes=1), lambda db, now: dispatch_due(db, now=now, provider=provider)),
    ]


@dataclass
class WorkerState:
    last_success: dict[str, datetime] = field(default_factory=dict)


@dataclass(frozen=True)
class JobOutcome:
    name: str
    ok: bool
    error: str | None = None


SessionFactory = Callable[[], AbstractContextManager[Session]]


def run_due_jobs(session_factory: SessionFactory, *, now: datetime, jobs: list[Job],
                 state: WorkerState) -> list[JobOutcome]:
    outcomes = []
    for job in jobs:
        last = state.last_success.get(job.name)
        if last is not None and now - last < job.interval:
            continue
        with session_factory() as db:
            try:
                job.run(db, now)
                db.commit()
            except Exception as e:  # сбой задачи не останавливает воркер; повтор — на следующем проходе
                db.rollback()
                log.exception("Задача %s завершилась ошибкой", job.name)
                outcomes.append(JobOutcome(job.name, False, f"{type(e).__name__}: {e}"))
                continue
        state.last_success[job.name] = now
        outcomes.append(JobOutcome(job.name, True))
    return outcomes


def try_acquire_lock(connection) -> bool:
    return bool(connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK_KEY}))


def run_forever(engine: Engine, *, jobs: list[Job], stop: threading.Event, tick_seconds: float = 30,
                clock: Callable[[], datetime] = utcnow) -> None:
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    state = WorkerState()
    with engine.connect() as lock_connection:
        while not stop.is_set():
            if try_acquire_lock(lock_connection):
                lock_connection.commit()
                break
            log.info("Другой воркер уже работает — жду")
            stop.wait(tick_seconds)
        log.info("Воркер запущен")
        while not stop.is_set():
            run_due_jobs(sessions, now=clock(), jobs=jobs, state=state)
            stop.wait(tick_seconds)
