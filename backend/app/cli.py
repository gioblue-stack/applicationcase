"""Командная строка: python -m app.cli seed-demo | sync-reference | worker [--once]"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import signal
import threading
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from app.content.loader import load_content
from app.core.config import get_settings
from app.core.security import utcnow
from app.db.session import get_engine
from app.seed.demo import DemoAlreadySeeded, seed_demo
from app.services.reference_sync import sync_reference_tables
from app.services.notifications import DevLogPushProvider
from app.worker import WorkerState, default_jobs, run_due_jobs, run_forever


def _seed(args: argparse.Namespace) -> None:
    password = os.environ.get("MC_DEMO_DOCTOR_PASSWORD")
    generated = password is None
    password = password or secrets.token_urlsafe(12)
    now = datetime.fromisoformat(args.now) if args.now else utcnow()
    with sessionmaker(bind=get_engine())() as db:
        try:
            summary = seed_demo(db, now=now, content=load_content(), doctor_password=password)
        except DemoAlreadySeeded as e:
            raise SystemExit(str(e)) from None
        db.commit()
    print("Прототип. Не предназначен для диагностики и лечения. Все данные демонстрационные.\n")
    print(f"Врач: {summary.doctor_email}")
    if generated:
        print(f"Пароль врача (показывается один раз): {password}")
    print("При первом входе врач настраивает двухфакторный вход (TOTP).\n")
    for person in summary.people:
        print(f"{person.full_name:<12} {person.login}  {person.role.value:<9} {person.scenario}")
    print("\nПациенты входят по коду; в режиме разработки код пишется в лог API.")


def _sync_reference(args: argparse.Namespace) -> None:
    """Справочники из content/*.json → БД. Идемпотентно: новые препараты появляются и в уже заполненной базе."""
    with sessionmaker(bind=get_engine())() as db:
        sync_reference_tables(db, load_content())
        db.commit()
    print("Справочники обновлены")


def _worker(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    if settings.env not in ("development", "test"):
        raise SystemExit("В production нужен push-провайдер (APNs/FCM/Web Push); сейчас подключён только лог")
    jobs = default_jobs(load_content(), DevLogPushProvider())
    engine = get_engine()
    if args.once:
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        for outcome in run_due_jobs(sessions, now=utcnow(), jobs=jobs, state=WorkerState()):
            print(f"{outcome.name}: {'ok' if outcome.ok else outcome.error}")
        return
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run_forever(engine, jobs=jobs, stop=stop, tick_seconds=args.tick)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(required=True)
    seed = commands.add_parser("seed-demo", help="Загрузить демо-данные §7.13")
    seed.add_argument("--now", help="Момент «сейчас» для демо (ISO 8601), по умолчанию — текущее время")
    seed.set_defaults(func=_seed)
    sync = commands.add_parser("sync-reference", help="Обновить справочники (препараты, телефоны, МКБ) из content/")
    sync.set_defaults(func=_sync_reference)
    worker = commands.add_parser("worker", help="Фоновый воркер расписаний и уведомлений")
    worker.add_argument("--once", action="store_true", help="Один проход по всем задачам")
    worker.add_argument("--tick", type=float, default=30, help="Пауза между проходами, секунд")
    worker.set_defaults(func=_worker)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
