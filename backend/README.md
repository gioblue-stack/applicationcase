# Backend (FastAPI + PostgreSQL)

> Прототип. Не предназначен для диагностики и лечения. Все данные демонстрационные.

Архитектура — [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Клинический контент — `../content/`.

## Установка

```bash
cd backend && ../.venv/bin/pip install -e ".[dev]"
```

Нужен PostgreSQL 16: `brew install postgresql@16` (или Docker).

## Тесты

```bash
cd backend && ../.venv/bin/python -m pytest
```

Фикстура сама поднимает одноразовый кластер PostgreSQL и удаляет его после прогона.
Чтобы использовать готовую пустую БД: `MC_TEST_DATABASE_URL=postgresql+psycopg://user@host:5432/db`.

## Миграции

```bash
cd backend && MC_DATABASE_URL=postgresql+psycopg://user@host:5432/mindcare ../.venv/bin/alembic upgrade head
```

## Запуск API

Секреты задаются только переменными окружения (значений по умолчанию нет):

| Переменная | Что |
|---|---|
| `MC_DATABASE_URL` | `postgresql+psycopg://user@host:5432/mindcare` |
| `MC_JWT_SECRET` | не короче 32 символов |
| `MC_DATA_KEY` | base64 от 32 случайных байт — шифрует TOTP-секреты врачей |
| `MC_OTP_PEPPER` | случайная строка — для хешей кодов входа и refresh-токенов |
| `MC_ENV` | `development` — коды входа пишутся в лог сервера; в `production` нужен SMS/e-mail-провайдер |

```bash
cd backend && ../.venv/bin/uvicorn app.main:app --reload
```

Документация API — `/docs`.

## Демо-данные (§7.13)

```bash
cd backend && ../.venv/bin/python -m app.cli seed-demo
```

Создаёт демо-врача `doctor@demo.mindcare.test` и четырёх вымышленных персонажей: Анна (зелёный), Игорь (жёлтый),
Мария (красный), Олег (пользователь без врача, самопроверка — вживую). Пароль врача — из `MC_DEMO_DOCTOR_PASSWORD`,
иначе генерируется и печатается один раз; при первом входе врач настраивает TOTP. Пациенты входят по коду
(телефоны `+7 900 000-00-01…04`). Повторный запуск отказывается — пересоздайте базу.

## Фоновый воркер

```bash
cd backend && ../.venv/bin/python -m app.cli worker          # постоянно, проход раз в 30 с
cd backend && ../.venv/bin/python -m app.cli worker --once   # один проход
```

Задачи: приёмы на 48 ч вперёд и «нет ответа» (5 мин), график опросников (15 мин), напоминание о дневнике (5 мин),
«нет данных 7 дней» (1 ч), отправка push (1 мин). Тихие часы пациента и окно push врача учитываются при отправке.
Одновременно работает один воркер (advisory-блокировка PostgreSQL). Push пока пишется в лог — провайдер подключается к пилоту.

## Что где

| Путь | Что |
|---|---|
| `app/domain/` | Чистые клинические правила без БД: протокол суицидального риска, подсчёт шкал, телефоны помощи |
| `app/content/` | Загрузка и валидация `content/*.json` — приложение не стартует при несогласованном контенте |
| `app/models/` | 40 таблиц; отправленные ответы защищены от UPDATE триггером БД |
| `app/services/` | Оркестрация: оценка + флаг + уведомление врачу + журнал доступа в одной транзакции |
| `alembic/` | Миграции |
| `tests/` | domain и content — без БД; db и services — на реальном PostgreSQL |
