from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.availability import classify_gpu_status
from app.config import Settings
from app.models import DataSource, Gpu, GpuMetric, Machine, MachineMetric, RawSnapshot, VpsMetric
from app.normalizer import NormalizedGpu, normalize_latest_payload


SOURCE_NAME = "lab-gpu"


def collect_once(db: Session, settings: Settings) -> None:
    source = get_or_create_source(db, settings)
    collected_at = datetime.now(timezone.utc)
    try:
        payload = fetch_payload(settings.source_url)
    except Exception as exc:
        record_failure(db, source, collected_at, str(exc), settings)
        return

    source.consecutive_failures = 0
    source.status = "ok"
    source.last_success_at = collected_at
    source.last_error = None
    db.add(RawSnapshot(data_source_id=source.id, collected_at=collected_at, ok=True, payload=payload))

    normalized = normalize_latest_payload(payload)
    machine_by_name: dict[str, Machine] = {}
    for item in normalized.machines:
        machine = upsert_machine(db, item.name, item.status, item.source_timestamp)
        machine_by_name[item.name] = machine
        db.add(
            MachineMetric(
                machine_id=machine.id,
                collected_at=item.source_timestamp,
                status=item.status,
                cpu_percent=item.cpu_percent,
                memory_percent=item.memory_percent,
                memory_total_mb=item.memory_total_mb,
                memory_used_mb=item.memory_used_mb,
                disks=item.disks,
            )
        )

    for item in normalized.gpus:
        machine = machine_by_name[item.machine_name]
        gpu = upsert_gpu(db, machine, item)
        samples = recent_samples(db, gpu.id, limit=5)
        samples.append(
            {
                "utilization": item.utilization,
                "memory_used_mb": item.memory_used_mb,
                "memory_total_mb": item.memory_total_mb,
            }
        )
        status = classify_gpu_status(machine.status, samples, source_status=source.status)
        gpu.current_status = status
        gpu.last_seen_at = item.source_timestamp
        gpu.memory_total_mb = item.memory_total_mb
        db.add(
            GpuMetric(
                gpu_id=gpu.id,
                collected_at=item.source_timestamp,
                utilization=item.utilization,
                memory_total_mb=item.memory_total_mb,
                memory_used_mb=item.memory_used_mb,
                status=status,
            )
        )

    cleanup_old_data(db, settings.retention_days, collected_at)
    db.commit()


def fetch_payload(url: str) -> dict[str, Any]:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def get_or_create_source(db: Session, settings: Settings) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if source is None:
        source = DataSource(name=SOURCE_NAME, url=settings.source_url, status="unknown", consecutive_failures=0)
        db.add(source)
        db.flush()
    else:
        source.url = settings.source_url
    return source


def record_failure(db: Session, source: DataSource, collected_at: datetime, error: str, settings: Settings) -> None:
    source.consecutive_failures += 1
    source.last_error = error
    if source.consecutive_failures >= settings.failure_unreachable_threshold:
        source.status = "unreachable"
    elif source.consecutive_failures >= settings.failure_degraded_threshold:
        source.status = "degraded"
    db.add(RawSnapshot(data_source_id=source.id, collected_at=collected_at, ok=False, error=error))
    db.commit()


def upsert_machine(db: Session, name: str, status: str, last_seen_at: datetime) -> Machine:
    machine = db.scalar(select(Machine).where(Machine.name == name))
    if machine is None:
        machine = Machine(name=name)
        db.add(machine)
        db.flush()
    machine.status = status
    machine.last_seen_at = last_seen_at
    return machine


def upsert_gpu(db: Session, machine: Machine, item: NormalizedGpu) -> Gpu:
    gpu = db.scalar(select(Gpu).where(Gpu.machine_id == machine.id, Gpu.gpu_index == item.gpu_index))
    if gpu is None:
        gpu = Gpu(machine_id=machine.id, gpu_index=item.gpu_index, name=item.name)
        db.add(gpu)
        db.flush()
    gpu.name = item.name
    return gpu


def recent_samples(db: Session, gpu_id: int, limit: int) -> list[dict[str, float | None]]:
    rows = db.scalars(
        select(GpuMetric).where(GpuMetric.gpu_id == gpu_id).order_by(GpuMetric.collected_at.desc()).limit(limit)
    ).all()
    return [
        {
            "utilization": row.utilization,
            "memory_used_mb": row.memory_used_mb,
            "memory_total_mb": row.memory_total_mb,
        }
        for row in reversed(rows)
    ]


def cleanup_old_data(db: Session, retention_days: int, now: datetime) -> None:
    cutoff = now - timedelta(days=retention_days)
    db.execute(delete(RawSnapshot).where(RawSnapshot.collected_at < cutoff))
    db.execute(delete(MachineMetric).where(MachineMetric.collected_at < cutoff))
    db.execute(delete(GpuMetric).where(GpuMetric.collected_at < cutoff))
    db.execute(delete(VpsMetric).where(VpsMetric.collected_at < cutoff))
