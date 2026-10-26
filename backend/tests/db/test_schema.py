"""Ограничения схемы, которые защищают достоверность данных на уровне БД."""

import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from sqlalchemy.orm import Session

from app.content.loader import load_content
from app.db.base import Base
from app.services.reference_sync import sync_reference_tables
from app.domain.enums import (
    AssessmentOutcome,
    AuditAction,
    CareLinkStatus,
    ResponseLevel,
    RiskTrigger,
)
from app.models import IMMUTABLE_TABLES, AuditLog, CareLink, DiaryEntry, RiskAssessment
from tests.conftest import alembic_config, create_database
from tests.factories import NOW, link, make_doctor, make_patient, make_phq9


def test_migrations_match_models_and_roll_back_cleanly(pg_server):
    engine = create_engine(create_database(pg_server, "mindcare_migrations"))
    try:
        with engine.begin() as conn:
            command.upgrade(alembic_config(conn), "head")
            assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
            command.downgrade(alembic_config(conn), "base")
            tables = set(sa.inspect(conn).get_table_names())
            assert tables == {"alembic_version"}
            functions = conn.scalar(sa.text("SELECT count(*) FROM pg_proc WHERE proname = 'forbid_mutation'"))
            assert functions == 0
    finally:
        engine.dispose()


def test_migrations_roll_back_with_reference_data_present(pg_server):
    """Откат должен работать и на заполненной базе, а не только на пустой."""
    engine = create_engine(create_database(pg_server, "mindcare_rollback"))
    try:
        with engine.begin() as conn:
            command.upgrade(alembic_config(conn), "head")
            with Session(bind=conn) as session:
                sync_reference_tables(session, load_content())
                session.flush()
            command.downgrade(alembic_config(conn), "base")
            assert set(sa.inspect(conn).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()


def test_every_immutable_table_has_update_trigger(db):
    rows = db.execute(
        sa.text(
            "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE NOT t.tgisinternal AND t.tgname LIKE 'trg_%_no_update'"
        )
    ).scalars()
    assert set(rows) == set(IMMUTABLE_TABLES)


def _assessment(patient_id, **overrides):
    values = dict(
        client_id=uuid.uuid4(),
        patient_id=patient_id,
        trigger=RiskTrigger.PHQ9_ITEM9,
        block_version="test",
        q1=True,
        q2=False,
        q6=False,
        outcome=AssessmentOutcome.ANSWERED,
        base_level=ResponseLevel.YELLOW,
        final_level=ResponseLevel.YELLOW,
        risk_factors_present=False,
        escalated_by_risk_factors=False,
        client_submitted_at=NOW,
    )
    values.update(overrides)
    return RiskAssessment(**values)


def test_submitted_answers_cannot_be_edited(db):
    patient = make_patient(db)
    submission = make_phq9(db, patient, [0] * 8 + [1])
    with pytest.raises(DBAPIError, match="неизменяема"), db.begin_nested():
        db.execute(sa.text("UPDATE questionnaire_answer SET value = 0 WHERE submission_id = :id"), {"id": submission.id})
    with pytest.raises(DBAPIError, match="неизменяема"), db.begin_nested():
        db.execute(sa.text("UPDATE questionnaire_submission SET total_score = 0 WHERE id = :id"), {"id": submission.id})


def test_risk_assessment_cannot_be_downgraded_after_the_fact(db):
    patient = make_patient(db)
    row = _assessment(patient.id, final_level=ResponseLevel.RED, base_level=ResponseLevel.RED)
    db.add(row)
    db.flush()
    with pytest.raises(DBAPIError, match="неизменяема"), db.begin_nested():
        db.execute(sa.text("UPDATE risk_assessment SET final_level = 'yellow' WHERE id = :id"), {"id": row.id})


def test_audit_log_cannot_be_deleted(db):
    db.add(AuditLog(actor_role="system", action=AuditAction.VIEW, entity="test", entity_id="1"))
    db.flush()
    with pytest.raises(DBAPIError, match="неизменяема"), db.begin_nested():
        db.execute(sa.text("DELETE FROM audit_log"))


def test_follow_up_answers_require_active_thoughts(db):
    patient = make_patient(db)
    with pytest.raises(IntegrityError, match="follow_up_only_after_q2"), db.begin_nested():
        db.add(_assessment(patient.id, q2=False, q4=True))
        db.flush()


def test_dismissed_assessment_cannot_carry_answers(db):
    patient = make_patient(db)
    with pytest.raises(IntegrityError, match="dismissed_has_no_answers"), db.begin_nested():
        db.add(_assessment(patient.id, outcome=AssessmentOutcome.DISMISSED, base_level=ResponseLevel.RED,
                           final_level=ResponseLevel.RED))
        db.flush()


def test_skipped_diary_questions_stay_null_not_zero(db):
    patient = make_patient(db)
    entry = DiaryEntry(client_id=uuid.uuid4(), patient_id=patient.id, day=NOW.date(), mood=4,
                       client_submitted_at=NOW)
    db.add(entry)
    db.flush()
    row = db.execute(sa.text("SELECT mood, interest, anxiety, sleep_hours, energy FROM diary_entry WHERE id = :id"),
                     {"id": entry.id}).one()
    assert tuple(row) == (4, None, None, None, None)


@pytest.mark.parametrize(("field", "value"), [("mood", 11), ("mood", -1), ("sleep_hours", 7.3), ("sleep_hours", 25)])
def test_diary_rejects_out_of_range_values(db, field, value):
    patient = make_patient(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(DiaryEntry(client_id=uuid.uuid4(), patient_id=patient.id, day=NOW.date(),
                          client_submitted_at=NOW, **{field: value}))
        db.flush()


def test_patient_has_one_active_doctor(db):
    patient = make_patient(db)
    link(db, make_doctor(db), patient)
    with pytest.raises(IntegrityError, match="uq_care_link_active_patient"), db.begin_nested():
        link(db, make_doctor(db, "Петров Пётр Петрович"), patient)
    # Завершённые связи не мешают.
    db.add(CareLink(doctor_id=make_doctor(db, "Сидорова Анна").account_id, patient_id=patient.id,
                    invite_code="ended-1", invite_expires_at=NOW, status=CareLinkStatus.ENDED))
    db.flush()
