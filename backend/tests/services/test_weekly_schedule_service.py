from datetime import timedelta

from sqlalchemy import select

from app.content.loader import load_content
from app.domain.enums import NotificationKind, ScheduleStatus
from app.models import Notification, QuestionnaireSchedule
from app.services.weekly_schedule import run_weekly_schedule
from tests.factories import NOW, link, make_doctor, make_patient

CONTENT = load_content()
DAY = timedelta(days=1)


def run(db, now):
    return run_weekly_schedule(db, now=now, content=CONTENT)


def test_weekly_cycle_reminder_then_missed_then_next_week(db):
    patient = make_patient(db)
    link(db, make_doctor(db), patient, linked_at=NOW)

    first = run(db, NOW)
    [slot_id] = first.created
    slot = db.get(QuestionnaireSchedule, slot_id)
    assert (slot.due_date, slot.status) == (NOW.date(), ScheduleStatus.PENDING)
    assert run(db, NOW + timedelta(hours=2)).created == []  # не дублируется

    assert run(db, NOW + DAY).reminded == [slot_id]
    assert run(db, NOW + 2 * DAY).reminded == []
    assert run(db, NOW + 3 * DAY).missed == [slot_id]
    assert slot.status is ScheduleStatus.MISSED

    next_week = run(db, NOW + 7 * DAY)
    assert len(next_week.created) == 1
    assert db.get(QuestionnaireSchedule, next_week.created[0]).due_date == (NOW + 7 * DAY).date()


def test_reminders_are_neutral_on_lock_screen(db):
    patient = make_patient(db)
    link(db, make_doctor(db), patient, linked_at=NOW)
    run(db, NOW)
    run(db, NOW + DAY)
    reminders = db.scalars(select(Notification).where(Notification.kind == NotificationKind.WEEKLY_QUESTIONNAIRE)).all()
    assert len(reminders) == 2
    for n in reminders:
        text = f"{n.title} {n.body_neutral}".lower()
        assert n.recipient_account_id == patient.account_id
        for word in ("phq", "gad", "депресс", "тревож", "опросник"):
            assert word not in text
