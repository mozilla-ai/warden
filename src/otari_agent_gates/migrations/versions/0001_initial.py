"""Create policy_check_records and policy_check_policies.

Both tables are deployment-wide: no workspace or user scoping, and no foreign
key into a gateway table. A record row is append-only history, so it has lookup
indexes and no uniqueness; a policy is the resource being edited, so its name is
unique. The unique constraint is declared inline on create_table because SQLite
cannot add one afterward outside batch mode.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "policy_check_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("policy_name", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("turn_id", sa.String(), nullable=True),
        sa.Column("repo", sa.String(), nullable=True),
        sa.Column("branch", sa.String(), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=False),
        sa.Column("compliant", sa.Boolean(), nullable=False),
        sa.Column("violations", sa.JSON(), nullable=False),
        sa.Column("guidance", sa.String(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=True),
        sa.Column("total_cost_usd", sa.Float(), nullable=True),
        sa.Column("total_input_tokens", sa.Integer(), nullable=True),
        sa.Column("total_output_tokens", sa.Integer(), nullable=True),
        sa.Column("gave_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="policy_check_records_pkey"),
    )
    op.create_index("ix_policy_check_records_policy_name", "policy_check_records", ["policy_name"])
    op.create_index("ix_policy_check_records_created_at", "policy_check_records", ["created_at"])
    op.create_index("ix_policy_check_records_repo", "policy_check_records", ["repo"])
    op.create_index("ix_policy_check_records_branch", "policy_check_records", ["branch"])

    op.create_table(
        "policy_check_policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("on_unavailable", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="policy_check_policies_pkey"),
        sa.UniqueConstraint("name", name="uq_policy_check_policies_name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("policy_check_policies")
    op.drop_index("ix_policy_check_records_branch", table_name="policy_check_records")
    op.drop_index("ix_policy_check_records_repo", table_name="policy_check_records")
    op.drop_index("ix_policy_check_records_created_at", table_name="policy_check_records")
    op.drop_index("ix_policy_check_records_policy_name", table_name="policy_check_records")
    op.drop_table("policy_check_records")
