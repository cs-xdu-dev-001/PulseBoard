from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ok: Mapped[bool] = mapped_column(default=True, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    gpus: Mapped[list["Gpu"]] = relationship(back_populates="machine")


class MachineMetric(Base):
    __tablename__ = "machine_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_percent: Mapped[float | None] = mapped_column(Float)
    memory_total_mb: Mapped[float | None] = mapped_column(Float)
    memory_used_mb: Mapped[float | None] = mapped_column(Float)
    disks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Gpu(Base):
    __tablename__ = "gpus"
    __table_args__ = (UniqueConstraint("machine_id", "gpu_index", name="uq_gpu_machine_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False, index=True)
    gpu_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    memory_total_mb: Mapped[float | None] = mapped_column(Float)
    current_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    machine: Mapped[Machine] = relationship(back_populates="gpus")


class GpuMetric(Base):
    __tablename__ = "gpu_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gpu_id: Mapped[int] = mapped_column(ForeignKey("gpus.id"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    utilization: Mapped[float | None] = mapped_column(Float)
    memory_total_mb: Mapped[float | None] = mapped_column(Float)
    memory_used_mb: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class VpsNode(Base):
    __tablename__ = "vps_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    traffic_baseline_bytes: Mapped[float | None] = mapped_column(Float)
    traffic_base_used_gb: Mapped[float | None] = mapped_column(Float)
    traffic_period_key: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class VpsMetric(Base):
    __tablename__ = "vps_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("vps_nodes.id"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_percent: Mapped[float | None] = mapped_column(Float)
    memory_total_bytes: Mapped[float | None] = mapped_column(Float)
    memory_available_bytes: Mapped[float | None] = mapped_column(Float)
    disks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    network_interfaces: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    network_rx_bytes_per_sec: Mapped[float | None] = mapped_column(Float)
    network_tx_bytes_per_sec: Mapped[float | None] = mapped_column(Float)
    load1: Mapped[float | None] = mapped_column(Float)
    load5: Mapped[float | None] = mapped_column(Float)
    load15: Mapped[float | None] = mapped_column(Float)
    uptime_seconds: Mapped[float | None] = mapped_column(Float)
    traffic_used_gb: Mapped[float | None] = mapped_column(Float)
    traffic_total_gb: Mapped[float | None] = mapped_column(Float)
    traffic_used_percent: Mapped[float | None] = mapped_column(Float)


class LlmUsageSource(Base):
    __tablename__ = "llm_usage_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    balance_currency: Mapped[str | None] = mapped_column(String(16))
    balance_total: Mapped[float | None] = mapped_column(Float)
    balance_granted: Mapped[float | None] = mapped_column(Float)
    balance_topped_up: Mapped[float | None] = mapped_column(Float)
    quota_total: Mapped[float | None] = mapped_column(Float)
    quota_used: Mapped[float | None] = mapped_column(Float)
    quota_remaining: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class LlmUsageSnapshot(Base):
    __tablename__ = "llm_usage_snapshots"
    __table_args__ = (
        Index("ix_llm_usage_snapshots_source_collected_id", "source_id", "collected_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("llm_usage_sources.id"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    range_key: Mapped[str] = mapped_column(String(32), nullable=False)
    request_count: Mapped[float | None] = mapped_column(Float)
    token_count: Mapped[float | None] = mapped_column(Float)
    quota_used: Mapped[float | None] = mapped_column(Float)
    estimated_amount: Mapped[float | None] = mapped_column(Float)
    rpm: Mapped[float | None] = mapped_column(Float)
    tpm: Mapped[float | None] = mapped_column(Float)
    success_rate: Mapped[float | None] = mapped_column(Float)
    avg_latency_seconds: Mapped[float | None] = mapped_column(Float)
    model_stats: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
