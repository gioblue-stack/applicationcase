import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.domain.diary import DiaryAnswers, InvalidDiary, SideEffectAnswer
from app.domain.enums import DoseStatus, FlagReason, FlagStatus, MedsTaken, RiskTrigger, Role
from app.models import DiaryEntry, Flag, SideEffectReport
from app.services.diary import DiaryError, effective_entries, submit_diary, suggest_meds_taken_for_day
from app.services.flags import check_no_data
from app.services.risk_protocol import record_risk_assessment
from tests.factories import link, make_doctor, make_dose, make_patient, make_prescription

MSK = ZoneInfo("Europe/Moscow")
DAY = date(2026, 10, 26)


def at(day: date, hour: int = 15, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=MSK)


def diary(db, patient, day=DAY, now=None, client_id=None, supersedes_id=None, **answers):
    now = now or at(day)
    answers["side_effects"] = tuple(answers.get("side_effects", ()))
    return submit_diary(db, patient_id=patient.id, client_id=client_id or uuid.uuid4(), day=day,
                        answers=DiaryAnswers(**answers), client_submitted_at=now, now=now,
                        supersedes_id=supersedes_id)


def open_flags(db, patient, reason=None):
    query = select(Flag).where(Flag.patient_id == patient.id, Flag.status == FlagStatus.OPEN)
    if reason:
        query = query.where(Flag.reason == reason)
    return db.scalars(query).all()


@pytest.fixture
def maria(db):
    doctor = make_doctor(db)
    patient = make_patient(db, takes_medication=True)
    link(db, doctor, patient, linked_at=at(DAY - timedelta(days=20)))
    return doctor, patient


def test_skipped_questions_are_stored_as_null(db, maria):
    _, patient = maria
    result = diary(db, patient, mood=5)
    entry = db.get(DiaryEntry, result.entry_id)
    assert (entry.mood, entry.anxiety, entry.sleep_hours, entry.filled_late) == (5, None, None, False)


def test_yesterday_until_noon_is_marked_late_then_closed(db, maria):
    _, patient = maria
    assert diary(db, patient, now=at(DAY + timedelta(days=1), 11, 59), mood=5).filled_late
    with pytest.raises(DiaryError, match="закрыт"):
        diary(db, patient, now=at(DAY + timedelta(days=1), 12, 0), mood=5)


def test_refill_keeps_both_versions_and_latest_counts(db, maria):
    _, patient = maria
    first = diary(db, patient, mood=2)
    diary(db, patient, mood=7, supersedes_id=first.entry_id, now=at(DAY, 16))
    assert db.scalar(select(func.count()).select_from(DiaryEntry)) == 2
    assert effective_entries(db, patient.id, DAY, DAY)[DAY].mood == 7


def test_refill_must_be_same_patient_and_day(db, maria):
    _, patient = maria
    first = diary(db, patient, day=DAY - timedelta(days=1), now=at(DAY, 9), mood=2)
    with pytest.raises(DiaryError, match="тот же день"):
        diary(db, patient, mood=4, supersedes_id=first.entry_id)


def test_low_mood_three_days_in_a_row_flags_once(db, maria):
    _, patient = maria
    for k, mood in ((2, 3), (1, 2)):
        assert diary(db, patient, day=DAY - timedelta(days=k), mood=mood).raised_flags == []
    assert diary(db, patient, mood=3).raised_flags == [FlagReason.LOW_MOOD_STREAK]
    assert diary(db, patient, day=DAY + timedelta(days=1), mood=1).raised_flags == []
    assert len(open_flags(db, patient, FlagReason.LOW_MOOD_STREAK)) == 1


def test_missing_day_breaks_low_mood_streak(db, maria):
    _, patient = maria
    diary(db, patient, day=DAY - timedelta(days=2), mood=1)
    diary(db, patient, mood=1)
    assert open_flags(db, patient, FlagReason.LOW_MOOD_STREAK) == []


def test_medication_questions_rejected_when_patient_takes_none(db):
    patient = make_patient(db, takes_medication=False)
    with pytest.raises(InvalidDiary):
        diary(db, patient, mood=5, meds_taken=MedsTaken.ALL)


def test_new_side_effect_flags_only_first_time(db, maria):
    _, patient = maria
    first = diary(db, patient, day=DAY - timedelta(days=1), had_side_effects=True,
                  side_effects=[SideEffectAnswer("nausea")])
    second = diary(db, patient, had_side_effects=True, side_effects=[SideEffectAnswer("nausea")])
    assert (first.raised_flags, second.raised_flags) == ([FlagReason.NEW_SIDE_EFFECT], [])
    reports = db.scalars(select(SideEffectReport).order_by(SideEffectReport.reported_at)).all()
    assert [r.is_new for r in reports] == [True, False]


def test_self_dose_change_in_diary_flags_doctor(db, maria):
    _, patient = maria
    assert diary(db, patient, meds_taken=MedsTaken.SELF_CHANGED).raised_flags == [FlagReason.SELF_DOSE_CHANGE]


def test_crisis_words_in_free_text_open_help_screen_and_red_flag(db, maria):
    _, patient = maria
    result = diary(db, patient, had_side_effects=True,
                   side_effects=[SideEffectAnswer("other", "тошнит, и вообще не хочу больше жить")])
    assert FlagReason.CRISIS_WORDS in result.raised_flags
    assert result.help_screen.key == "help"
    assert [p.id for p in result.help_screen.phones] == ["112", "8-800-100-49-94", "msk-051"]
    [flag] = open_flags(db, patient, FlagReason.CRISIS_WORDS)
    assert flag.level == "red"


def test_self_user_crisis_words_get_help_screen_without_flag(db):
    user = make_patient(db, "Олег Демо", region_code=None, role=Role.SELF_USER, takes_medication=True)
    result = diary(db, user, had_side_effects=True, side_effects=[SideEffectAnswer("other", "суицид")])
    assert result.help_screen.key == "self_user_help"
    assert result.raised_flags == []
    assert db.scalar(select(func.count()).select_from(Flag)) == 0


def test_mood_drop_offers_unscheduled_block_once_a_day(db, maria):
    _, patient = maria
    for k in (3, 2, 1):
        diary(db, patient, day=DAY - timedelta(days=k), mood=7)
    result = diary(db, patient, mood=2)
    assert result.offer_risk_block is RiskTrigger.UNSCHEDULED_MOOD_DROP

    record_risk_assessment(db, patient_id=patient.id, client_id=uuid.uuid4(), trigger=result.offer_risk_block,
                           trigger_ref=result.entry_id, answers={}, client_submitted_at=at(DAY, 15, 5),
                           now=at(DAY, 15, 5))
    again = diary(db, patient, mood=2, supersedes_id=result.entry_id, now=at(DAY, 18))
    assert again.offer_risk_block is None


def test_resubmitting_same_client_id_is_idempotent(db, maria):
    _, patient = maria
    client_id = uuid.uuid4()
    first = diary(db, patient, client_id=client_id, mood=4)
    again = diary(db, patient, client_id=client_id, mood=4)
    assert (again.created, again.entry_id) == (False, first.entry_id)
    assert db.scalar(select(func.count()).select_from(DiaryEntry)) == 1


def test_question7_suggestion_from_dose_marks(db, maria):
    doctor, patient = maria
    prescription = make_prescription(db, patient, doctor)
    make_dose(db, prescription, at(DAY, 9), DoseStatus.TAKEN)
    make_dose(db, prescription, at(DAY, 21), DoseStatus.MISSED)
    make_dose(db, prescription, at(DAY - timedelta(days=1), 9), DoseStatus.SELF_CHANGED, actual_dose=150)
    assert suggest_meds_taken_for_day(db, patient.id, DAY) is MedsTaken.MISSED


def test_new_diary_entry_auto_resolves_no_data_flag(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link(db, doctor, patient, linked_at=at(DAY - timedelta(days=10)))
    [flag] = check_no_data(db, now=at(DAY, 10), days=7)
    diary(db, patient, mood=5)
    db.refresh(flag)
    assert flag.status is FlagStatus.AUTO_RESOLVED  # закрыт, но остался в истории
    assert open_flags(db, patient) == []
