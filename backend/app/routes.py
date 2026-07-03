from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.llm_usage import list_llm_usage_config, load_llm_usage_configs, save_llm_usage_config
from app.llm_usage_collector import collect_llm_usage_once
from app.llm_pricing import estimate_model_cost_usd, estimate_snapshot_cost_usd
from app.models import DataSource, Gpu, GpuMetric, LlmUsageSnapshot, LlmUsageSource, Machine, MachineMetric, VpsMetric, VpsNode
from app.settings_config import load_app_settings, save_app_settings

router = APIRouter(prefix="/api")


class LlmUsageConfigPayload(BaseModel):
    source_id: str
    source_type: str
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    access_token: str | None = None
    user_id: str | None = None


class SettingsPayload(BaseModel):
    values: dict[str, str] = {}
    secrets: dict[str, str] = {}


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    source = db.scalar(select(DataSource).where(DataSource.name == "lab-gpu"))
    return {
        "ok": source is None or source.status != "unreachable",
        "source_status": source.status if source else "unknown",
    }


@router.get("/settings")
def app_settings() -> dict:
    return load_app_settings()


@router.post("/settings")
def save_settings(payload: SettingsPayload) -> dict:
    result = save_app_settings({**payload.values, **payload.secrets})
    get_settings.cache_clear()
    return {"ok": True, **result}


@router.get("/dashboard/current")
def dashboard_current(db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    source = db.scalar(select(DataSource).where(DataSource.name == "lab-gpu"))
    machines = _current_machines(db, now)
    gpus = _current_gpus(db, source.status if source else "unknown", now)
    vps_nodes = _current_vps_nodes(db, now)
    return {
        "source": _source_payload(source),
        "summary": {
            "machines_total": len(machines),
            "machines_online": sum(1 for machine in machines if machine["status"] == "connected"),
            "gpus_total": len(gpus),
            "available_gpus": sum(1 for gpu in gpus if gpu["status"] == "available"),
            "saturated_gpus": sum(1 for gpu in gpus if gpu["status"] == "saturated"),
            "vps_total": len(vps_nodes),
            "vps_abnormal": sum(1 for node in vps_nodes if node["status"] in {"offline", "critical"}),
        },
        "machines": machines,
        "gpus": sorted(gpus, key=_gpu_sort_key),
        "vps_nodes": vps_nodes,
    }


@router.get("/gpus")
def list_gpus(db: Session = Depends(get_db)) -> dict:
    source = db.scalar(select(DataSource).where(DataSource.name == "lab-gpu"))
    return {"gpus": _current_gpus(db, source.status if source else "unknown", datetime.now(timezone.utc))}


@router.get("/machines")
def list_machines(db: Session = Depends(get_db)) -> dict:
    return {"machines": _current_machines(db, datetime.now(timezone.utc))}


@router.get("/history/gpus")
def gpu_history(range: Literal["1h", "24h"] = Query("1h"), db: Session = Depends(get_db)) -> dict:
    since, until = _range_bounds(range)
    gpus = db.scalars(select(Gpu).join(Machine).order_by(Machine.name, Gpu.gpu_index)).all()
    series = []
    for gpu in gpus:
        points = db.scalars(
            select(GpuMetric)
            .where(GpuMetric.gpu_id == gpu.id, GpuMetric.collected_at >= since, GpuMetric.collected_at <= until)
            .order_by(GpuMetric.collected_at, GpuMetric.id)
        ).all()
        points = _dedupe_by_timestamp(points)
        series.append(
            {
                "gpu_id": gpu.id,
                "machine_name": gpu.machine.name,
                "gpu_index": gpu.gpu_index,
                "name": gpu.name,
                "points": [
                    {
                        "timestamp": _iso(point.collected_at),
                        "utilization": point.utilization,
                        "memory_used_mb": point.memory_used_mb,
                        "status": point.status,
                    }
                    for point in points
                ],
            }
        )
    return {"range": range, "series": series}


@router.get("/history/machines")
def machine_history(range: Literal["1h", "24h"] = Query("1h"), db: Session = Depends(get_db)) -> dict:
    since, until = _range_bounds(range)
    machines = db.scalars(select(Machine).order_by(Machine.name)).all()
    series = []
    for machine in machines:
        points = db.scalars(
            select(MachineMetric)
            .where(
                MachineMetric.machine_id == machine.id,
                MachineMetric.collected_at >= since,
                MachineMetric.collected_at <= until,
            )
            .order_by(MachineMetric.collected_at, MachineMetric.id)
        ).all()
        points = _dedupe_by_timestamp(points)
        series.append(
            {
                "machine_id": machine.id,
                "name": machine.name,
                "points": [
                    {
                        "timestamp": _iso(point.collected_at),
                        "cpu_percent": point.cpu_percent,
                        "memory_percent": point.memory_percent,
                        "disks": point.disks,
                        "status": point.status,
                    }
                    for point in points
                ],
            }
        )
    return {"range": range, "series": series}


@router.get("/history/vps")
def vps_history(range: Literal["1h", "24h"] = Query("1h"), db: Session = Depends(get_db)) -> dict:
    since, until = _range_bounds(range)
    nodes = db.scalars(select(VpsNode).order_by(VpsNode.name)).all()
    series = []
    for node in nodes:
        points = db.scalars(
            select(VpsMetric)
            .where(VpsMetric.node_id == node.id, VpsMetric.collected_at >= since, VpsMetric.collected_at <= until)
            .order_by(VpsMetric.collected_at, VpsMetric.id)
        ).all()
        points = _dedupe_by_timestamp(points)
        series.append(
            {
                "node_id": node.id,
                "name": node.name,
                "points": [
                    {
                        "timestamp": _iso(point.collected_at),
                        "status": point.status,
                        "cpu_percent": point.cpu_percent,
                        "memory_percent": point.memory_percent,
                        "disks": point.disks,
                        "network_rx_bytes_per_sec": point.network_rx_bytes_per_sec,
                        "network_tx_bytes_per_sec": point.network_tx_bytes_per_sec,
                        "traffic_used_percent": point.traffic_used_percent,
                    }
                    for point in points
                ],
            }
        )
    return {"range": range, "series": series}


@router.get("/llm/usage/providers")
def llm_usage_providers() -> dict:
    settings = get_settings()
    return {
        "providers": [
            {
                "source_id": config.source_id,
                "display_name": config.display_name,
                "source_type": config.source_type,
            }
            for config in load_llm_usage_configs(settings)
        ]
    }


@router.get("/llm/usage/config")
def llm_usage_config() -> dict:
    return {"sources": list_llm_usage_config(get_settings())}


@router.post("/llm/usage/config")
def save_llm_usage_source(payload: LlmUsageConfigPayload) -> dict:
    result = save_llm_usage_config(payload.model_dump())
    get_settings.cache_clear()
    return {"ok": True, **result}


@router.get("/llm/usage/sources")
def llm_usage_sources(db: Session = Depends(get_db)) -> dict:
    sources = db.scalars(select(LlmUsageSource).order_by(LlmUsageSource.display_name)).all()
    return {"sources": [_llm_source_payload(source) for source in sources]}


@router.get("/llm/usage/summary")
def llm_usage_summary(
    range: Literal["today", "24h", "7d"] = Query("today"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    snapshots = _latest_llm_snapshots(db, range, source)
    request_count = sum(point.request_count or 0 for point in snapshots)
    token_count = sum(point.token_count or 0 for point in snapshots)
    amount = sum(point.estimated_amount or 0 for point in snapshots)
    estimated_cost = sum(_snapshot_cost(point) or 0 for point in snapshots)
    rpm_values = [point.rpm for point in snapshots if point.rpm is not None]
    tpm_values = [point.tpm for point in snapshots if point.tpm is not None]
    latency_values = [point.avg_latency_seconds for point in snapshots if point.avg_latency_seconds is not None]
    return {
        "range": range,
        "request_count": request_count,
        "token_count": token_count,
        "estimated_amount": amount,
        "estimated_cost_usd": round(estimated_cost, 6),
        "avg_rpm": round(sum(rpm_values) / len(rpm_values), 4) if rpm_values else None,
        "avg_tpm": round(sum(tpm_values) / len(tpm_values), 4) if tpm_values else None,
        "avg_latency_seconds": round(sum(latency_values) / len(latency_values), 4) if latency_values else None,
        "snapshot_count": len(snapshots),
    }


@router.get("/llm/usage/series")
def llm_usage_series(
    range: Literal["today", "24h", "7d"] = Query("today"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    rows = _llm_snapshots(db, range, source)
    series_by_source: dict[int, dict] = {}
    series_by_model: dict[str, dict] = {}
    for row in rows:
        source_row = db.get(LlmUsageSource, row.source_id)
        if source_row is None:
            continue
        item = series_by_source.setdefault(
            source_row.id,
            {
                "source_id": source_row.source_id,
                "display_name": source_row.display_name,
                "points": [],
            },
        )
        item["points"].append(
            {
                "timestamp": _iso(row.collected_at),
                "request_count": row.request_count,
                "token_count": row.token_count,
                "quota_used": row.quota_used,
                "estimated_amount": row.estimated_amount,
                "estimated_cost_usd": _snapshot_cost(row),
                "rpm": row.rpm,
                "tpm": row.tpm,
            }
        )
        for model_item in row.model_stats or []:
            model = model_item.get("model") or "unknown"
            model_series = series_by_model.setdefault(model, {"model": model, "display_name": model, "points": []})
            estimate = estimate_model_cost_usd(
                model,
                input_tokens=model_item.get("input_tokens") or None,
                output_tokens=model_item.get("output_tokens") or None,
                token_count=model_item.get("token_count") or None,
                raw_quota=model_item.get("amount") or None,
            )
            model_series["points"].append(
                {
                    "timestamp": _iso(row.collected_at),
                    "request_count": model_item.get("request_count") or 0,
                    "amount": model_item.get("amount") or 0,
                    "estimated_cost_usd": estimate["estimated_cost_usd"],
                    "pricing_basis": estimate["pricing_basis"],
                }
            )
    return {
        "range": range,
        "series": list(series_by_source.values()),
        "model_series": sorted(
            series_by_model.values(),
            key=lambda item: sum(point.get("estimated_cost_usd") or 0 for point in item["points"]),
            reverse=True,
        ),
    }


@router.get("/llm/usage/models")
def llm_usage_models(
    range: Literal["today", "24h", "7d"] = Query("today"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    totals: dict[str, dict] = {}
    for snapshot in _latest_llm_snapshots(db, range, source):
        for item in snapshot.model_stats or []:
            model = item.get("model") or "unknown"
            total = totals.setdefault(
                model,
                {
                    "model": model,
                    "request_count": 0,
                    "token_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "amount": 0,
                    "estimated_cost_usd": 0,
                    "pricing_basis": "unknown",
                },
            )
            total["request_count"] += item.get("request_count") or 0
            total["token_count"] += item.get("token_count") or 0
            total["input_tokens"] += item.get("input_tokens") or 0
            total["output_tokens"] += item.get("output_tokens") or 0
            total["amount"] += item.get("amount") or 0
    for total in totals.values():
        estimate = estimate_model_cost_usd(
            total["model"],
            input_tokens=total["input_tokens"] or None,
            output_tokens=total["output_tokens"] or None,
            token_count=total["token_count"] or None,
            raw_quota=total["amount"] or None,
        )
        total.update(estimate)
    return {
        "range": range,
        "models": sorted(totals.values(), key=lambda item: item.get("estimated_cost_usd") or item["amount"], reverse=True),
    }


@router.post("/llm/usage/refresh")
def llm_usage_refresh(db: Session = Depends(get_db)) -> dict:
    collect_llm_usage_once(db, get_settings())
    return {"ok": True}


def _source_payload(source: DataSource | None) -> dict:
    if source is None:
        return {"status": "unknown", "consecutive_failures": 0, "last_success_at": None}
    return {
        "status": source.status,
        "consecutive_failures": source.consecutive_failures,
        "last_success_at": _iso(source.last_success_at),
        "last_error": source.last_error,
    }


def _current_machines(db: Session, until: datetime) -> list[dict]:
    machines = db.scalars(select(Machine).order_by(Machine.name)).all()
    result = []
    for machine in machines:
        latest = db.scalar(
            select(MachineMetric)
            .where(MachineMetric.machine_id == machine.id, MachineMetric.collected_at <= until)
            .order_by(desc(MachineMetric.collected_at), desc(MachineMetric.id))
            .limit(1)
        )
        result.append(
            {
                "id": machine.id,
                "name": machine.name,
                "status": machine.status,
                "last_seen_at": _iso(machine.last_seen_at),
                "cpu_percent": latest.cpu_percent if latest else None,
                "memory_percent": latest.memory_percent if latest else None,
                "memory_total_mb": latest.memory_total_mb if latest else None,
                "memory_used_mb": latest.memory_used_mb if latest else None,
                "disks": latest.disks if latest else {},
            }
        )
    return result


def _current_gpus(db: Session, source_status: str, until: datetime) -> list[dict]:
    gpus = db.scalars(select(Gpu).join(Machine).order_by(Machine.name, Gpu.gpu_index)).all()
    result = []
    for gpu in gpus:
        latest = db.scalar(
            select(GpuMetric)
            .where(GpuMetric.gpu_id == gpu.id, GpuMetric.collected_at <= until)
            .order_by(desc(GpuMetric.collected_at), desc(GpuMetric.id))
            .limit(1)
        )
        status = "unknown" if source_status == "unreachable" else gpu.current_status
        result.append(
            {
                "id": gpu.id,
                "machine_name": gpu.machine.name,
                "machine_status": gpu.machine.status,
                "gpu_index": gpu.gpu_index,
                "name": gpu.name,
                "status": status,
                "last_seen_at": _iso(gpu.last_seen_at),
                "utilization": latest.utilization if latest else None,
                "memory_total_mb": latest.memory_total_mb if latest else gpu.memory_total_mb,
                "memory_used_mb": latest.memory_used_mb if latest else None,
            }
        )
    return result


def _current_vps_nodes(db: Session, until: datetime) -> list[dict]:
    nodes = db.scalars(select(VpsNode).order_by(VpsNode.name)).all()
    result = []
    for node in nodes:
        latest = db.scalar(
            select(VpsMetric)
            .where(VpsMetric.node_id == node.id, VpsMetric.collected_at <= until)
            .order_by(desc(VpsMetric.collected_at), desc(VpsMetric.id))
            .limit(1)
        )
        traffic_quota = None
        if latest and latest.traffic_total_gb:
            traffic_quota = {
                "used_gb": latest.traffic_used_gb,
                "total_gb": latest.traffic_total_gb,
                "used_percent": latest.traffic_used_percent,
            }
        result.append(
            {
                "id": node.id,
                "name": node.name,
                "url": node.url,
                "status": node.status,
                "last_seen_at": _iso(node.last_seen_at),
                "last_error": node.last_error,
                "cpu_percent": latest.cpu_percent if latest else None,
                "memory_percent": latest.memory_percent if latest else None,
                "disks": latest.disks if latest else {},
                "network_interfaces": _public_network_interfaces(latest.network_interfaces if latest else {}),
                "network_rx_bytes_per_sec": latest.network_rx_bytes_per_sec if latest else None,
                "network_tx_bytes_per_sec": latest.network_tx_bytes_per_sec if latest else None,
                "load1": latest.load1 if latest else None,
                "load5": latest.load5 if latest else None,
                "load15": latest.load15 if latest else None,
                "uptime_seconds": latest.uptime_seconds if latest else None,
                "traffic_quota": traffic_quota,
            }
        )
    return result


def _range_bounds(range_value: str) -> tuple[datetime, datetime]:
    until = datetime.now(timezone.utc)
    hours = 1 if range_value == "1h" else 24
    return until - timedelta(hours=hours), until


def _llm_range_bounds(range_value: str) -> tuple[datetime, datetime]:
    until = datetime.now(timezone.utc)
    if range_value == "today":
        local_now = until.astimezone()
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_start.astimezone(timezone.utc), until
    if range_value == "7d":
        return until - timedelta(days=7), until
    return until - timedelta(hours=24), until


def _llm_snapshots(db: Session, range_value: str, source_id: str | None) -> list[LlmUsageSnapshot]:
    since, until = _llm_range_bounds(range_value)
    stmt = (
        select(LlmUsageSnapshot)
        .join(LlmUsageSource, LlmUsageSource.id == LlmUsageSnapshot.source_id)
        .where(LlmUsageSnapshot.collected_at >= since, LlmUsageSnapshot.collected_at <= until)
        .order_by(LlmUsageSnapshot.collected_at)
    )
    if source_id:
        stmt = stmt.where(LlmUsageSource.source_id == source_id)
    return db.scalars(stmt).all()


def _latest_llm_snapshots(db: Session, range_value: str, source_id: str | None) -> list[LlmUsageSnapshot]:
    latest = {}
    for snapshot in _llm_snapshots(db, range_value, source_id):
        latest[snapshot.source_id] = snapshot
    return list(latest.values())


def _llm_source_payload(source: LlmUsageSource) -> dict:
    is_newapi = source.source_type == "newapi_admin"
    return {
        "id": source.id,
        "source_id": source.source_id,
        "display_name": source.display_name,
        "source_type": source.source_type,
        "status": source.status,
        "last_checked_at": _iso(source.last_checked_at),
        "last_error": source.last_error,
        "balance_currency": source.balance_currency,
        "balance_total": source.balance_total,
        "balance_granted": source.balance_granted,
        "balance_topped_up": source.balance_topped_up,
        "quota_total": source.quota_total,
        "quota_used": source.quota_used,
        "quota_remaining": source.quota_remaining,
        "quota_used_usd": estimate_snapshot_cost_usd(raw_quota=source.quota_used) if is_newapi else None,
        "quota_remaining_usd": estimate_snapshot_cost_usd(raw_quota=source.quota_remaining) if is_newapi else None,
    }


def _snapshot_cost(snapshot: LlmUsageSnapshot) -> float | None:
    return estimate_snapshot_cost_usd(
        model_stats=snapshot.model_stats or [],
        token_count=snapshot.token_count,
        raw_quota=snapshot.quota_used,
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _gpu_sort_key(gpu: dict) -> tuple[int, str, int]:
    priority = {"available": 0, "busy": 1, "saturated": 2, "unknown": 3, "offline": 4}
    return (priority.get(gpu["status"], 5), gpu["machine_name"], gpu["gpu_index"])


def _public_network_interfaces(value: dict) -> dict:
    return {name: data for name, data in value.items() if not name.startswith("_")}


def _dedupe_by_timestamp(points: list) -> list:
    by_timestamp = {}
    for point in points:
        by_timestamp[point.collected_at] = point
    return list(by_timestamp.values())
