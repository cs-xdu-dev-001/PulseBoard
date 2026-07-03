from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class NormalizedMachine:
    name: str
    status: str
    cpu_percent: float | None
    memory_percent: float | None
    memory_total_mb: float | None
    memory_used_mb: float | None
    disks: dict[str, Any]
    source_timestamp: datetime


@dataclass(frozen=True)
class NormalizedGpu:
    machine_name: str
    gpu_index: int
    name: str
    utilization: float | None
    memory_total_mb: float | None
    memory_used_mb: float | None
    source_timestamp: datetime


@dataclass(frozen=True)
class NormalizedPayload:
    source_timestamp: datetime
    machines: list[NormalizedMachine]
    gpus: list[NormalizedGpu]


LAB_TIMEZONE = ZoneInfo("Asia/Shanghai")


def parse_source_timestamp(value: str | None, default_timezone: ZoneInfo = LAB_TIMEZONE) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=default_timezone).astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_latest_payload(payload: dict[str, Any]) -> NormalizedPayload:
    source_timestamp = parse_source_timestamp(payload.get("timestamp"))
    machines: list[NormalizedMachine] = []
    gpus: list[NormalizedGpu] = []

    for server in payload.get("servers", []):
        name = str(server.get("name") or server.get("server") or "unknown")
        resource_metrics = server.get("resource_metrics") or {}
        disk_metrics = server.get("disk_metrics") or {}
        memory = resource_metrics.get("memory") or {}
        status = str(resource_metrics.get("status") or disk_metrics.get("status") or "unknown")
        metric_timestamp = parse_source_timestamp(resource_metrics.get("timestamp") or disk_metrics.get("timestamp"))
        disks = disk_metrics.get("disk") if isinstance(disk_metrics.get("disk"), dict) else {}

        machines.append(
            NormalizedMachine(
                name=name,
                status=status,
                cpu_percent=_to_float(resource_metrics.get("cpu")),
                memory_percent=_to_float(memory.get("percentage")),
                memory_total_mb=_to_float(memory.get("total_mb")),
                memory_used_mb=_to_float(memory.get("used_mb")),
                disks=disks,
                source_timestamp=metric_timestamp,
            )
        )

        for gpu in resource_metrics.get("gpu") or []:
            gpus.append(
                NormalizedGpu(
                    machine_name=name,
                    gpu_index=int(gpu.get("index")),
                    name=str(gpu.get("name") or f"GPU {gpu.get('index')}"),
                    utilization=_to_float(gpu.get("utilization")),
                    memory_total_mb=_to_float(gpu.get("memory_total_mb")),
                    memory_used_mb=_to_float(gpu.get("memory_used_mb")),
                    source_timestamp=metric_timestamp,
                )
            )

    return NormalizedPayload(source_timestamp=source_timestamp, machines=machines, gpus=gpus)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
