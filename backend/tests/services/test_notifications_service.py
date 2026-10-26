import uuid
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.content.loader import load_content
from app.domain.diary import DiaryAnswers
from app.domain.enums import MissedDoseRule, NotificationKind, NotificationStatus, PushPriority
from app.domain.treatment import DoseResponse
from app.models import DoseEvent, Notification
from app.services.diary import submit_diary
from app.services.doses import respond_to_dose
from app.services.notifications import create_diary_reminders, dispatch_due
from app.services.treatment import PrescriptionSpec, create_prescription
from tests.factories import link, make_doctor, make_patient

CONTENT = load_content()
MSK = ZoneInfo("Europe/Moscow")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=MSK)


class Recorder:
    def __init__(self, fail_for=()):
        self.sent, self.fail_for = [], set(fail_for)

    def send(self, n):
        if n.id in self.fail_for:
            raise ConnectionError("push недоступен")
        self.sent.append((n.title, n.body_neutral, n.body_detailed))


def notify(db, account_id, kind, when, title="Напоминание", body="Текст"):
    n = Notification(recipient_account_id=account_id, kind=kind, priority=PushPriority.NORMAL, title=title,
                     body_neutral=body, scheduled_for=when)
    db.add(n)
    db.flush()
    return n


def test_due_sent_future_kept_failures_isolated(db):
    patient = make_patient(db)
    due = notify(db, patient.account_id, NotificationKind.DOCTOR_REPLY, at(26, 12))
    broken = notify(db, patient.account_id, NotificationKind.DOCTOR_REPLY, at(26, 12, 1))
    future = notify(db, patient.account_id, NotificationKind.DOCTOR_REPLY, at(26, 18))
    report = dispatch_due(db, now=at(26, 15), provider=Recorder(fail_for={broken.id}))
    assert (report.sent, report.failed) == ([due.id], [broken.id])
    assert (due.status, broken.status, future.status) == ("sent", "failed", "scheduled")


def test_dose_reminder_cancelled_after_dose_marked(db):
    doctor, patient = make_doctor(db), make_patient(db)
    link(db, doctor, patient)
    create_prescription(db, doctor_account_id=doctor.account_id, patient_id=patient.id, now=at(26, 8), content=CONTENT,
                        spec=PrescriptionSpec(substance_id="sertraline", form="таблетки", dose=Decimal(50), unit="мг",
                                              times=[time(9)], start_date=date(2026, 10, 26),
                                              in_person_visit_date=date(2026, 10, 26),
                                              missed_dose_rule=MissedDoseRule.SKIP_NO_DOUBLE))
    event = db.scalars(select(DoseEvent).where(DoseEvent.scheduled_at == at(26, 9))).one()
    respond_to_dose(db, patient_id=patient.id, dose_event_id=event.id, response=DoseResponse.TAKEN, now=at(26, 8, 50),
                    content=CONTENT)
    report = dispatch_due(db, now=at(26, 9), provider=Recorder())
    reminder = db.scalars(select(Notification).where(Notification.related_dose_event_id == event.id)).one()
    assert reminder.id in report.cancelled and reminder.status is NotificationStatus.CANCELLED


def test_doctor_gets_flag_push_only_inside_chosen_hours(db):
    doctor = make_doctor(db)
    doctor.red_flag_push_window = {"start": "08:00", "end": "22:00"}
    n = notify(db, doctor.account_id, NotificationKind.RED_FLAG, at(26, 23), title="Красный флаг")
    assert dispatch_due(db, now=at(26, 23), provider=Recorder()).postponed == [n.id]
    assert (n.status, n.scheduled_for) == ("scheduled", at(27, 8))
    assert dispatch_due(db, now=at(27, 8), provider=Recorder()).sent == [n.id]


def test_quiet_hours_delay_everything_except_medication(db):
    patient = make_patient(db)
    patient.quiet_hours_start, patient.quiet_hours_end = time(23), time(8)
    weekly = notify(db, patient.account_id, NotificationKind.WEEKLY_QUESTIONNAIRE, at(26, 23, 30))
    dose = notify(db, patient.account_id, NotificationKind.DOSE_REMINDER, at(26, 23, 30), body="Пора отметить приём")
    report = dispatch_due(db, now=at(26, 23, 30), provider=Recorder())
    assert (report.postponed, report.sent) == ([weekly.id], [dose.id])
    assert weekly.scheduled_for == at(27, 8)


def test_diary_reminder_once_a_day_at_chosen_time_unless_filled(db):
    patient = make_patient(db)
    patient.diary_reminder_time = time(20)
    assert create_diary_reminders(db, now=at(26, 19), content=CONTENT) == []
    [first] = create_diary_reminders(db, now=at(26, 20, 5), content=CONTENT)
    assert db.get(Notification, first).body_neutral == "Отметим самочувствие?"
    assert create_diary_reminders(db, now=at(26, 20, 10), content=CONTENT) == []

    submit_diary(db, patient_id=patient.id, client_id=uuid.uuid4(), day=date(2026, 10, 27),
                 answers=DiaryAnswers(mood=6), client_submitted_at=at(27, 19), now=at(27, 19), content=CONTENT)
    assert create_diary_reminders(db, now=at(27, 20, 5), content=CONTENT) == []
    assert len(create_diary_reminders(db, now=at(28, 20, 5), content=CONTENT)) == 1
