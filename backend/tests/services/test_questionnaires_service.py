"""PHQ-9/GAD-7: сценарии Анны, Игоря и Олега (§7.13)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.domain.enums import FlagReason, InstrumentCode, Role, ScheduleStatus
from app.domain.questionnaire_feedback import Change, SelfCheckLevel
from app.domain.risk_protocol import NextStep
from app.models import Flag, QuestionnaireSchedule, QuestionnaireSubmission, Threshold
from app.services.questionnaires import QuestionnaireError, SelfCheckTooSoon, submit_self_check, submit_weekly
from tests.factories import NOW, link, make_doctor, make_patient

PHQ, GAD = InstrumentCode.PHQ9, InstrumentCode.GAD7
WEEK = timedelta(days=7)


def phq(total, item9=0):
    rest = total - item9
    answers = [min(3, max(0, rest - 3 * i)) for i in range(8)]
    assert sum(answers) == rest
    return answers + [item9]


def gad(total):
    answers = [min(3, max(0, total - 3 * i)) for i in range(7)]
    assert sum(answers) == total
    return answers


def weekly(db, patient, instrument, answers, now=NOW, **kw):
    return submit_weekly(db, patient_id=patient.id, client_id=kw.pop("client_id", uuid.uuid4()), instrument=instrument,
                         answers=answers, client_submitted_at=now, now=now, **kw)


@pytest.fixture
def patient(db):
    doctor = make_doctor(db)
    p = make_patient(db)
    link(db, doctor, p, linked_at=NOW - 3 * WEEK)
    return p


def flags(db, patient):
    return [f.reason for f in db.scalars(select(Flag).where(Flag.patient_id == patient.id))]


def test_anna_phq9_improves_from_16_to_8(db, patient):
    weekly(db, patient, PHQ, phq(16), now=NOW - WEEK)
    result = weekly(db, patient, PHQ, phq(8))
    assert result.total == 8
    assert result.feedback.change is Change.IMPROVED
    assert result.feedback.change_text == "По сравнению с прошлой неделей показатели заметно улучшились."
    assert result.feedback.result_text.startswith("Симптомы немного беспокоят")
    assert result.risk.next_step is NextStep.NONE
    assert flags(db, patient) == []


def test_igor_gad7_rises_by_5_yellow_flag(db, patient):
    weekly(db, patient, GAD, gad(6), now=NOW - WEEK)
    result = weekly(db, patient, GAD, gad(11))
    assert result.raised_flags == [FlagReason.GAD7_INCREASE]
    assert result.feedback.change is Change.WORSE
    assert result.risk is None


def test_phq9_rise_below_threshold_no_flag_until_doctors_lower_it(db, patient):
    weekly(db, patient, PHQ, phq(8), now=NOW - 2 * WEEK)
    assert weekly(db, patient, PHQ, phq(12), now=NOW - WEEK).raised_flags == []
    db.add(Threshold(key="phq9_increase_yellow", value=4))
    db.flush()
    assert weekly(db, patient, PHQ, phq(16)).raised_flags == [FlagReason.PHQ9_INCREASE]


def test_refill_replaces_previous_answer_and_both_versions_are_kept(db, patient):
    weekly(db, patient, PHQ, phq(5), now=NOW - WEEK)
    wrong = weekly(db, patient, PHQ, phq(12))
    assert wrong.raised_flags == [FlagReason.PHQ9_INCREASE]
    fixed = weekly(db, patient, PHQ, phq(9), supersedes_id=wrong.submission_id, now=NOW + timedelta(minutes=5))
    assert fixed.feedback.change is Change.UNCHANGED  # 9 против 5, а не против ошибочных 12
    assert db.scalar(select(func.count()).select_from(QuestionnaireSubmission)) == 3

    next_week = weekly(db, patient, PHQ, phq(14), now=NOW + WEEK)
    assert next_week.raised_flags == [FlagReason.PHQ9_INCREASE]  # 14 − 9 = 5


def test_phq9_item9_starts_risk_block(db, patient):
    result = weekly(db, patient, PHQ, phq(10, item9=1))
    assert result.risk.next_step is NextStep.RISK_BLOCK


def test_weekly_slot_is_done_after_both_questionnaires(db, patient):
    slot = QuestionnaireSchedule(patient_id=patient.id, due_date=NOW.date(), status=ScheduleStatus.REMINDED)
    db.add(slot)
    db.flush()
    weekly(db, patient, PHQ, phq(5))
    assert slot.status is ScheduleStatus.REMINDED
    weekly(db, patient, GAD, gad(4))
    assert slot.status is ScheduleStatus.DONE


@pytest.mark.parametrize(
    ("instrument", "answers", "difficulty", "match"),
    [(PHQ, [0] * 8, None, "ожидается 9"), (GAD, [0] * 7 + [1], None, "ожидается 7"),
     (GAD, [0] * 7, 1, "только в PHQ-9"), (PHQ, [0] * 9, 4, "трудностях")],
)
def test_invalid_submissions_rejected(db, patient, instrument, answers, difficulty, match):
    with pytest.raises(QuestionnaireError, match=match):
        weekly(db, patient, instrument, answers, difficulty=difficulty)


def test_idempotent_resubmission(db, patient):
    client_id = uuid.uuid4()
    first = weekly(db, patient, GAD, gad(9), client_id=client_id)
    again = weekly(db, patient, GAD, gad(9), client_id=client_id)
    assert (again.created, again.submission_id) == (False, first.submission_id)


@pytest.fixture
def oleg(db):
    return make_patient(db, "Олег Демо", region_code=None, role=Role.SELF_USER)


def self_check(db, user, phq9, gad7, now=NOW):
    return submit_self_check(db, patient_id=user.id, phq9_client_id=uuid.uuid4(), gad7_client_id=uuid.uuid4(),
                             phq9_answers=phq9, gad7_answers=gad7, client_submitted_at=now, now=now)


def test_oleg_self_check_recommends_specialist_without_flags(db, oleg):
    result = self_check(db, oleg, phq(12), gad(7))
    assert result.level is SelfCheckLevel.PRONOUNCED
    assert result.actions == ["find_specialist"]
    assert result.text.startswith("Симптомы выражены")
    assert "не диагноз" in result.screening_note
    assert result.help_screen is None
    assert db.scalar(select(func.count()).select_from(Flag)) == 0


def test_self_check_item9_shows_help_screen_regardless_of_total(db, oleg):
    result = self_check(db, oleg, phq(1, item9=1), gad(0))
    assert result.level is SelfCheckLevel.NONE
    assert result.help_screen.key == "self_user_help"


def test_self_check_not_more_often_than_every_14_days(db, oleg):
    self_check(db, oleg, phq(3), gad(3))
    with pytest.raises(SelfCheckTooSoon) as error:
        self_check(db, oleg, phq(3), gad(3), now=NOW + timedelta(days=10))
    assert error.value.available_at == NOW + timedelta(days=14)
    assert self_check(db, oleg, phq(3), gad(3), now=NOW + timedelta(days=14)).level is SelfCheckLevel.NONE


def test_roles_do_not_mix(db, patient, oleg):
    with pytest.raises(QuestionnaireError, match="самопроверка"):
        weekly(db, oleg, PHQ, phq(3))
    with pytest.raises(QuestionnaireError, match="еженедельные"):
        self_check(db, patient, phq(3), gad(3))
