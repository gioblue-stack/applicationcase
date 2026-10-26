from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.domain.enums import AuditAction, FlagLevel, FlagReason, FlagStatus, Role
from app.domain.flag_rules import FlagCandidate
from app.models import AuditLog, Flag, Notification
from app.services.flags import FlagError, acknowledge, check_no_data, raise_flag
from tests.factories import NOW, link, make_doctor, make_patient

CANDIDATE = FlagCandidate(FlagLevel.YELLOW, FlagReason.LOW_MOOD_STREAK, "low_mood_streak")


@pytest.fixture
def pair(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link(db, doctor, patient)
    return doctor, patient


def _raise(db, patient, candidate=CANDIDATE):
    return raise_flag(db, candidate, patient_id=patient.id, source_type="test", source_id=None, now=NOW)


def test_open_flag_is_not_duplicated(db, pair):
    _, patient = pair
    assert _raise(db, patient) is not None
    assert _raise(db, patient) is None
    assert db.scalar(select(func.count()).select_from(Flag)) == 1
    assert db.scalar(select(func.count()).select_from(Notification)) == 1


def test_same_reason_can_flag_again_after_doctor_closed_it(db, pair):
    doctor, patient = pair
    first = _raise(db, patient)
    acknowledge(db, flag_id=first.id, doctor_account_id=doctor.account_id, now=NOW)
    assert _raise(db, patient) is not None


def test_no_flags_without_treating_doctor(db):
    user = make_patient(db, "Олег Демо", role=Role.SELF_USER)
    assert _raise(db, user) is None


def test_yellow_push_is_normal_priority_red_is_urgent(db, pair):
    _, patient = pair
    yellow = _raise(db, patient)
    red = _raise(db, patient, FlagCandidate(FlagLevel.RED, FlagReason.CRISIS_WORDS, "crisis:1"))
    priorities = {n.related_flag_id: n.priority for n in db.scalars(select(Notification))}
    assert (priorities[yellow.id], priorities[red.id]) == ("normal", "urgent")


def test_only_treating_doctor_closes_flag(db, pair):
    doctor, patient = pair
    flag = _raise(db, patient)
    stranger = make_doctor(db, "Петров Пётр")
    with pytest.raises(FlagError, match="лечащий врач"):
        acknowledge(db, flag_id=flag.id, doctor_account_id=stranger.account_id, now=NOW)

    acknowledge(db, flag_id=flag.id, doctor_account_id=doctor.account_id, now=NOW)
    assert (flag.status, flag.acknowledged_by) == (FlagStatus.ACKNOWLEDGED, doctor.account_id)
    entry = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(flag.id),
                                              AuditLog.action == AuditAction.UPDATE)).one()
    assert entry.actor_account_id == doctor.account_id
    with pytest.raises(FlagError, match="уже закрыт"):
        acknowledge(db, flag_id=flag.id, doctor_account_id=doctor.account_id, now=NOW)


def test_no_data_seven_days_after_linking(db):
    doctor = make_doctor(db)
    silent = make_patient(db, "Тихий Пациент")
    link(db, doctor, silent, linked_at=NOW - timedelta(days=8))
    fresh = make_patient(db, "Новый Пациент")
    link(db, doctor, fresh, linked_at=NOW - timedelta(days=6))

    raised = check_no_data(db, now=NOW, days=7)
    assert [(f.patient_id, f.reason) for f in raised] == [(silent.id, FlagReason.NO_DATA)]
    assert check_no_data(db, now=NOW + timedelta(hours=1), days=7) == []  # не дублируется
