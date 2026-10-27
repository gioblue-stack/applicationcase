#!/usr/bin/env bash
# Локальный запуск API для разработки и демо: PostgreSQL в var/pg, миграции, демо-сиды при первом запуске, uvicorn.
# Секреты разработки генерируются один раз и лежат в var/dev-secrets.env (папка var/ не попадает в git).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VAR="$ROOT/var"
PG_BIN="${MC_PG_BIN:-/opt/homebrew/opt/postgresql@16/bin}"
PG_PORT="${MC_PG_PORT:-54330}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
mkdir -p "$VAR"

if [[ ! -f "$VAR/dev-secrets.env" ]]; then
  "$ROOT/.venv/bin/python" - > "$VAR/dev-secrets.env" <<'PY'
import base64, secrets
print(f"MC_JWT_SECRET={secrets.token_urlsafe(32)}")
print(f"MC_DATA_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}")
print(f"MC_OTP_PEPPER={secrets.token_urlsafe(16)}")
print(f"MC_DEMO_DOCTOR_PASSWORD={secrets.token_urlsafe(12)}")
PY
  chmod 600 "$VAR/dev-secrets.env"
fi
set -a; source "$VAR/dev-secrets.env"; set +a
export MC_ENV=development
export MC_DATABASE_URL="postgresql+psycopg://mindcare@127.0.0.1:${PG_PORT}/mindcare"
export MC_UPLOAD_DIR="$VAR/uploads"
export MC_DEV_CODES_FILE="$VAR/dev-login-codes.txt"  # коды входа: письма и SMS в разработке не отправляются

if [[ ! -d "$VAR/pg/data" ]]; then
  "$PG_BIN/initdb" -D "$VAR/pg/data" -U mindcare -A trust -E UTF8 --locale=C > /dev/null
fi
if ! "$PG_BIN/pg_ctl" -D "$VAR/pg/data" status > /dev/null 2>&1; then
  "$PG_BIN/pg_ctl" -D "$VAR/pg/data" -l "$VAR/pg/log" -w start \
    -o "-p ${PG_PORT} -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" > /dev/null
fi
"$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U mindcare -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='mindcare'" | grep -q 1 \
  || "$PG_BIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U mindcare mindcare

cd "$ROOT/backend"
../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.cli sync-reference  # изменения content/ (например, новый препарат) — и в существующую базу
if [[ ! -f "$VAR/demo-seeded" ]]; then
  ../.venv/bin/python -m app.cli seed-demo && touch "$VAR/demo-seeded"
  echo "Пароль демо-врача — MC_DEMO_DOCTOR_PASSWORD в var/dev-secrets.env"
fi
# Воркер создаёт приёмы лекарств и слоты еженедельных опросников — без него на экране «Сегодня» пусто.
../.venv/bin/python -m app.cli worker &
WORKER_PID=$!
trap 'kill "$WORKER_PID" 2>/dev/null' EXIT
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
