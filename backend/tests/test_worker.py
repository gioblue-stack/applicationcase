from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.domain.enums import NotificationKind, PushPriority
from app.models import Notification
from app.worker import Job, WorkerState, run_due_jobs, try_acquire_lock
from tests.factories import make_patient

T0 = datetime(2026, 10, 26, 12, tzinfo=UTC)


def _jobs(calls):
    def job(name):
        return lambda db, now: calls.append(name)

    return [Job("doses", timedelta(minutes=5), job("doses")), Job("weekly", timedelta(minutes=15), job("weekly")),
            Job("dispatch", timedelta(minutes=1), job("dispatch"))]


def test_jobs_run_at_their_own_intervals(db):
    calls, state = [], WorkerState()
    jobs = _jobs(calls)
    for minutes in (0, 1, 2, 5, 15):
        run_due_jobs(lambda: nullcontext(db), now=T0 + timedelta(minutes=minutes), jobs=jobs, state=state)
    assert calls == ["doses", "weekly", "dispatch", "dispatch", "dispatch",
                     "doses", "dispatch", "doses", "weekly", "dispatch"]


def test_failing_job_is_rolled_back_isolated_and_retried(db):
    patient = make_patient(db)
    attempts = []

    def flaky(session, now):
        attempts.append(now)
        session.add(Notification(recipient_account_id=patient.account_id, kind=NotificationKind.DIARY_REMINDER,
                                 priority=PushPriority.NORMAL, title="t", body_neutral="b", scheduled_for=now))
        session.flush()
        raise RuntimeError("сбой")

    calls = []
    jobs = [Job("flaky", timedelta(hours=1), flaky), *_jobs(calls)]
    state = WorkerState()
    outcomes = run_due_jobs(lambda: nullcontext(db), now=T0, jobs=jobs, state=state)
    assert [(o.name, o.ok) for o in outcomes] == [("flaky", False), ("doses", True), ("weekly", True), ("dispatch", True)]
    assert "RuntimeError" in outcomes[0].error
    assert db.scalar(select(func.count()).select_from(Notification)) == 0  # частичная запись откатилась
    run_due_jobs(lambda: nullcontext(db), now=T0 + timedelta(seconds=30), jobs=jobs, state=state)
    assert len(attempts) == 2  # повтор на следующем проходе, а не через час


def test_only_one_worker_holds_the_lock(engine):
    first, second = engine.connect(), engine.connect()
    try:
        assert try_acquire_lock(first)
        assert not try_acquire_lock(second)
        first.execute(text("SELECT pg_advisory_unlock_all()"))
        assert try_acquire_lock(second)
    finally:
        for conn in (first, second):
            conn.execute(text("SELECT pg_advisory_unlock_all()"))
            conn.close()
