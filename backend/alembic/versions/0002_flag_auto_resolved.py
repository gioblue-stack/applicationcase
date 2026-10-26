"""flag status auto_resolved (В6) + alarming_symptom.action до 64 символов

Revision ID: 0002_flag_auto_resolved
Revises: 697e08f00ff3
Create Date: 2026-10-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_flag_auto_resolved"
down_revision: Union[str, Sequence[str], None] = "697e08f00ff3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "ck_flag_flagstatus"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "flag", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "flag", "status IN ('open', 'acknowledged', 'auto_resolved')")
    # Коды действий §7.5 длиннее 32 символов (contact_doctor_today_112_if_confusion).
    op.alter_column("alarming_symptom", "action", type_=sa.String(64), existing_nullable=False)


def downgrade() -> None:
    # Справочник перезагружается из content/; при откате длинные коды обрезаются, а не валят откат.
    op.alter_column("alarming_symptom", "action", type_=sa.String(32), existing_nullable=False,
                    postgresql_using="left(action, 32)")
    op.execute("UPDATE flag SET status = 'acknowledged' WHERE status = 'auto_resolved'")
    op.drop_constraint(op.f(CONSTRAINT), "flag", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "flag", "status IN ('open', 'acknowledged')")
