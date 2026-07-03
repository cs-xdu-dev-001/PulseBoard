"""initial schema

Revision ID: 20260702_0001
Revises:
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "machines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "raw_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_raw_snapshots_data_source_id", "raw_snapshots", ["data_source_id"])
    op.create_index("ix_raw_snapshots_collected_at", "raw_snapshots", ["collected_at"])
    op.create_table(
        "machine_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("memory_total_mb", sa.Float(), nullable=True),
        sa.Column("memory_used_mb", sa.Float(), nullable=True),
        sa.Column("disks", sa.JSON(), nullable=False),
    )
    op.create_index("ix_machine_metrics_machine_id", "machine_metrics", ["machine_id"])
    op.create_index("ix_machine_metrics_collected_at", "machine_metrics", ["collected_at"])
    op.create_table(
        "gpus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False),
        sa.Column("gpu_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("memory_total_mb", sa.Float(), nullable=True),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("machine_id", "gpu_index", name="uq_gpu_machine_index"),
    )
    op.create_index("ix_gpus_machine_id", "gpus", ["machine_id"])
    op.create_index("ix_gpus_last_seen_at", "gpus", ["last_seen_at"])
    op.create_table(
        "gpu_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gpu_id", sa.Integer(), sa.ForeignKey("gpus.id"), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utilization", sa.Float(), nullable=True),
        sa.Column("memory_total_mb", sa.Float(), nullable=True),
        sa.Column("memory_used_mb", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_gpu_metrics_gpu_id", "gpu_metrics", ["gpu_id"])
    op.create_index("ix_gpu_metrics_collected_at", "gpu_metrics", ["collected_at"])


def downgrade() -> None:
    op.drop_table("gpu_metrics")
    op.drop_table("gpus")
    op.drop_table("machine_metrics")
    op.drop_table("raw_snapshots")
    op.drop_table("machines")
    op.drop_table("data_sources")

