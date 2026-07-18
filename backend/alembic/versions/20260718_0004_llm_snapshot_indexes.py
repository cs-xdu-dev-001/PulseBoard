"""llm snapshot indexes

Revision ID: 20260718_0004
Revises: 20260702_0003
Create Date: 2026-07-18
"""
from alembic import op

revision = "20260718_0004"
down_revision = "20260702_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_llm_usage_snapshots_source_collected_id",
        "llm_usage_snapshots",
        ["source_id", "collected_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_snapshots_source_collected_id", table_name="llm_usage_snapshots")
