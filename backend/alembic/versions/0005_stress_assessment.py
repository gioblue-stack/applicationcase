"""stress_assessment: внешние факторы стресса + причина флага stress_safety

Revision ID: 0005_stress_assessment
Revises: 0004_notification_dose
Create Date: 2026-10-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_stress_assessment"
down_revision: Union[str, Sequence[str], None] = "0004_notification_dose"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "ck_flag_flagreason"
REASONS = ["risk_block_emergency", "risk_block_red", "risk_block_dismissed", "risk_block_yellow", "panic_button",
           "crisis_words", "alarming_symptom", "phq9_increase", "gad7_increase", "missed_doses", "self_dose_change",
           "low_mood_streak", "new_side_effect", "no_data"]


def _reasons_check(reasons: list[str]) -> None:
    op.drop_constraint(op.f(CONSTRAINT), "flag", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "flag", "reason IN ({})".format(", ".join(f"'{r}'" for r in reasons)))


def upgrade() -> None:
    op.create_table(
        "stress_assessment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_version", sa.Integer(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("other_text", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient_profile.id"],
                                name=op.f("fk_stress_assessment_patient_id_patient_profile")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stress_assessment")),
        sa.UniqueConstraint("client_id", name=op.f("uq_stress_assessment_client_id")),
    )
    op.create_index(op.f("ix_stress_assessment_patient_id"), "stress_assessment", ["patient_id"], unique=False)
    _reasons_check(REASONS + ["stress_safety"])


def downgrade() -> None:
    op.execute("DELETE FROM flag WHERE reason = 'stress_safety'")
    _reasons_check(REASONS)
    op.drop_index(op.f("ix_stress_assessment_patient_id"), table_name="stress_assessment")
    op.drop_table("stress_assessment")
