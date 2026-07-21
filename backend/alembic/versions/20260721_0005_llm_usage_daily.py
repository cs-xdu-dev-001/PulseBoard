"""llm daily usage rollups

Revision ID: 20260721_0005
Revises: 20260718_0004
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_0005"
down_revision = "20260718_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("llm_usage_sources.id"), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("request_count", sa.Float(), nullable=True),
        sa.Column("token_count", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Float(), nullable=True),
        sa.Column("output_tokens", sa.Float(), nullable=True),
        sa.Column("estimated_amount", sa.Float(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("token_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data_quality", sa.String(length=16), nullable=False, server_default="unavailable"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "usage_date", "model", name="uq_llm_usage_daily_source_date_model"),
    )
    op.create_index("ix_llm_usage_daily_source_id", "llm_usage_daily", ["source_id"])
    op.create_index("ix_llm_usage_daily_source_date", "llm_usage_daily", ["source_id", "usage_date"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_daily_source_date", table_name="llm_usage_daily")
    op.drop_index("ix_llm_usage_daily_source_id", table_name="llm_usage_daily")
    op.drop_table("llm_usage_daily")
