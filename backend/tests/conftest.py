"""Тесты работают на настоящем PostgreSQL: CHECK-ограничения, частичные индексы и триггеры
неизменяемости — часть защиты данных, на SQLite их не проверить.

MC_TEST_DATABASE_URL — использовать готовую пустую БД (CI, docker-compose).
Иначе поднимается одноразовый кластер из PostgreSQL 16 (Homebrew: postgresql@16).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.content.loader import load_content
from app.services.reference_sync import sync_reference_tables

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_BIN_CANDIDATES = ("/opt/homebrew/opt/postgresql@16/bin", "/usr/local/opt/postgresql@16/bin", "/usr/lib/postgresql/16/bin")


def _pg_bin() -> Path:
    if env := os.environ.get("MC_PG_BIN"):
        return Path(env)
    if found := shutil.which("pg_ctl"):
        return Path(found).parent
    for candidate in PG_BIN_CANDIDATES:
        if (Path(candidate) / "pg_ctl").exists():
            return Path(candidate)
    pytest.exit("PostgreSQL 16 не найден: задайте MC_TEST_DATABASE_URL или MC_PG_BIN", returncode=2)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def pg_server() -> Iterator[str]:
    """Базовый URL сервера без имени БД: postgresql+psycopg://user@host:port"""
    if url := os.environ.get("MC_TEST_DATABASE_URL"):
        yield url.rsplit("/", 1)[0]
        return

    pg_bin = _pg_bin()
    tmp = Path(tempfile.mkdtemp(prefix="mc-pg-"))
    data, port = tmp / "data", _free_port()
    # На macOS postmaster падает без корректной локали («became multithreaded during startup»).
    env = {**os.environ, "LC_ALL": "en_US.UTF-8"}
    subprocess.run(
        [pg_bin / "initdb", "-D", data, "-U", "mindcare", "-A", "trust", "-E", "UTF8", "--locale=C"],
        check=True, capture_output=True, env=env,
    )
    subprocess.run(
        [pg_bin / "pg_ctl", "-D", data, "-l", tmp / "log", "-w", "start",
         "-o", f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories='' -c fsync=off"],
        check=True, capture_output=True, env=env,
    )
    try:
        yield f"postgresql+psycopg://mindcare@127.0.0.1:{port}"
    finally:
        subprocess.run([pg_bin / "pg_ctl", "-D", data, "-m", "fast", "stop"], capture_output=True, env=env)
        shutil.rmtree(tmp, ignore_errors=True)


def create_database(server_url: str, name: str) -> str:
    plain = server_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(f"{plain}/postgres", autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        conn.execute(f'CREATE DATABASE "{name}"')
    return f"{server_url}/{name}"


def alembic_config(connection) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def engine(pg_server: str) -> Iterator[Engine]:
    eng = create_engine(create_database(pg_server, "mindcare_test"))
    with eng.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    with Session(eng) as session:
        sync_reference_tables(session, load_content())
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Сессия внутри внешней транзакции: после теста всё откатывается."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
