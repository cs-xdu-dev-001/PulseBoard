"""widen llm numeric precision

Revision ID: 20260721_0006
Revises: 20260721_0005
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_0006"
down_revision = "20260721_0005"
branch_labels = None
depends_on = None


SOURCE_DOUBLE_COLUMNS = (
    "balance_total",
    "balance_granted",
    "balance_topped_up",
    "quota_total",
    "quota_used",
    "quota_remaining",
)
SNAPSHOT_COUNT_COLUMNS = ("request_count", "token_count")
SNAPSHOT_DOUBLE_COLUMNS = ("quota_used", "estimated_amount")
DAILY_COUNT_COLUMNS = ("request_count", "token_count", "input_tokens", "output_tokens")
DAILY_DOUBLE_COLUMNS = ("estimated_amount", "estimated_cost_usd")


def upgrade() -> None:
    _alter_columns("llm_usage_sources", SOURCE_DOUBLE_COLUMNS, sa.Float(), sa.Double())
    _alter_columns("llm_usage_snapshots", SNAPSHOT_COUNT_COLUMNS, sa.Float(), sa.BigInteger())
    _alter_columns("llm_usage_snapshots", SNAPSHOT_DOUBLE_COLUMNS, sa.Float(), sa.Double())
    _alter_columns("llm_usage_daily", DAILY_COUNT_COLUMNS, sa.Float(), sa.BigInteger())
    _alter_columns("llm_usage_daily", DAILY_DOUBLE_COLUMNS, sa.Float(), sa.Double())


def downgrade() -> None:
    _alter_columns("llm_usage_daily", DAILY_DOUBLE_COLUMNS, sa.Double(), sa.Float())
    _alter_columns("llm_usage_daily", DAILY_COUNT_COLUMNS, sa.BigInteger(), sa.Float())
    _alter_columns("llm_usage_snapshots", SNAPSHOT_DOUBLE_COLUMNS, sa.Double(), sa.Float())
    _alter_columns("llm_usage_snapshots", SNAPSHOT_COUNT_COLUMNS, sa.BigInteger(), sa.Float())
    _alter_columns("llm_usage_sources", SOURCE_DOUBLE_COLUMNS, sa.Double(), sa.Float())


def _alter_columns(table: str, columns: tuple[str, ...], existing_type: sa.types.TypeEngine, target_type: sa.types.TypeEngine) -> None:
    with op.batch_alter_table(table) as batch_op:
        for column in columns:
            batch_op.alter_column(column, existing_type=existing_type, type_=target_type, existing_nullable=True)
