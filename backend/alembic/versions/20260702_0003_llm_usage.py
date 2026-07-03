"""llm usage dashboard

Revision ID: 20260702_0003
Revises: 20260702_0002
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_0003"
down_revision = "20260702_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("balance_currency", sa.String(length=16), nullable=True),
        sa.Column("balance_total", sa.Float(), nullable=True),
        sa.Column("balance_granted", sa.Float(), nullable=True),
        sa.Column("balance_topped_up", sa.Float(), nullable=True),
        sa.Column("quota_total", sa.Float(), nullable=True),
        sa.Column("quota_used", sa.Float(), nullable=True),
        sa.Column("quota_remaining", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index("ix_llm_usage_sources_last_checked_at", "llm_usage_sources", ["last_checked_at"])
    op.create_table(
        "llm_usage_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("llm_usage_sources.id"), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_key", sa.String(length=32), nullable=False),
        sa.Column("request_count", sa.Float(), nullable=True),
        sa.Column("token_count", sa.Float(), nullable=True),
        sa.Column("quota_used", sa.Float(), nullable=True),
        sa.Column("estimated_amount", sa.Float(), nullable=True),
        sa.Column("rpm", sa.Float(), nullable=True),
        sa.Column("tpm", sa.Float(), nullable=True),
        sa.Column("success_rate", sa.Float(), nullable=True),
        sa.Column("avg_latency_seconds", sa.Float(), nullable=True),
        sa.Column("model_stats", sa.JSON(), nullable=False),
        sa.Column("raw_summary", sa.JSON(), nullable=False),
    )
    op.create_index("ix_llm_usage_snapshots_source_id", "llm_usage_snapshots", ["source_id"])
    op.create_index("ix_llm_usage_snapshots_collected_at", "llm_usage_snapshots", ["collected_at"])


def downgrade() -> None:
    op.drop_table("llm_usage_snapshots")
    op.drop_table("llm_usage_sources")
