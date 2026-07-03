"""vps metrics

Revision ID: 20260702_0002
Revises: 20260702_0001
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_0002"
down_revision = "20260702_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vps_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("traffic_baseline_bytes", sa.Float(), nullable=True),
        sa.Column("traffic_base_used_gb", sa.Float(), nullable=True),
        sa.Column("traffic_period_key", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_vps_nodes_last_seen_at", "vps_nodes", ["last_seen_at"])
    op.create_table(
        "vps_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("vps_nodes.id"), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("memory_total_bytes", sa.Float(), nullable=True),
        sa.Column("memory_available_bytes", sa.Float(), nullable=True),
        sa.Column("disks", sa.JSON(), nullable=False),
        sa.Column("network_interfaces", sa.JSON(), nullable=False),
        sa.Column("network_rx_bytes_per_sec", sa.Float(), nullable=True),
        sa.Column("network_tx_bytes_per_sec", sa.Float(), nullable=True),
        sa.Column("load1", sa.Float(), nullable=True),
        sa.Column("load5", sa.Float(), nullable=True),
        sa.Column("load15", sa.Float(), nullable=True),
        sa.Column("uptime_seconds", sa.Float(), nullable=True),
        sa.Column("traffic_used_gb", sa.Float(), nullable=True),
        sa.Column("traffic_total_gb", sa.Float(), nullable=True),
        sa.Column("traffic_used_percent", sa.Float(), nullable=True),
    )
    op.create_index("ix_vps_metrics_node_id", "vps_metrics", ["node_id"])
    op.create_index("ix_vps_metrics_collected_at", "vps_metrics", ["collected_at"])


def downgrade() -> None:
    op.drop_table("vps_metrics")
    op.drop_table("vps_nodes")
