from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import time
import re
from typing import Literal
from urllib.parse import quote, quote_plus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.llm_usage import (
    delete_llm_provider_config,
    delete_llm_usage_config,
    list_llm_usage_config,
    load_llm_usage_configs,
    save_llm_usage_config,
    update_llm_provider_config,
    LlmUsageConfig,
    LlmUsageResult,
)
from app.llm_usage_collector import check_model_connection, collect_llm_usage_once, collect_source, persist_result
from app.llm_pricing import estimate_model_cost_usd, estimate_snapshot_cost_usd
from app.models import DataSource, Gpu, GpuMetric, LlmUsageSnapshot, LlmUsageSource, Machine, MachineMetric, VpsMetric, VpsNode
from app.settings_config import load_app_settings, save_app_settings

router = APIRouter(prefix="/api")
LlmRange = Literal["today", "24h", "7d", "14d", "29d"]
LLM_SERIES_POINTS_PER_SOURCE = {"today": 288, "24h": 288, "7d": 2016, "14d": 4032, "29d": 8352}


class LlmUsageConfigPayload(BaseModel):
    source_id: str
    source_type: str
    provider_id: str | None = None
    provider_name: str | None = None
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    access_token: str | None = None
    user_id: str | None = None
    request_mode: str | None = None
    test_model: str | None = None


class LlmProviderConfigPayload(BaseModel):
    provider_name: str | None = None
    source_type: str
    base_url: str | None = None
    user_id: str | None = None
    access_token: str | None = None
    request_mode: str | None = None
    test_model: str | None = None


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
        if not _gpu_matches_model_filter(gpu):
            continue
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
    try:
        result = save_llm_usage_config(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_settings.cache_clear()
    return {"ok": True, **result}


@router.post("/llm/usage/config/{source_id}/test")
def test_llm_usage_source(source_id: str) -> dict:
    config = next(
        (item for item in load_llm_usage_configs(get_settings()) if item.source_id == source_id),
        None,
    )
    if config is None:
        raise HTTPException(status_code=404, detail=f"未找到API Key配置：{source_id}")

    result = collect_source(config)
    model_result = check_model_connection(config)
    statistics_error = _sanitize_llm_test_error(result.error, config.api_key, config.access_token)
    model_error = _sanitize_llm_test_error(model_result.get("error"), config.api_key, config.access_token)
    return {
        "source_id": result.source_id,
        "display_name": result.display_name,
        "status": result.status,
        "error": statistics_error,
        "statistics": {
            "status": result.status,
            "error": statistics_error,
        },
        "model": {
            "status": model_result.get("status"),
            "error": model_error,
            "request_mode": model_result.get("request_mode"),
            "test_model": model_result.get("test_model"),
        },
        "checked_at": datetime.now(timezone.utc),
    }


def _sanitize_llm_test_error(message: str | None, *secrets: str | None) -> str | None:
    if not message:
        return None
    sanitized = str(message)
    for secret in secrets:
        if secret:
            for variant in {secret, quote(secret, safe=""), quote_plus(secret, safe="")}:
                sanitized = re.sub(re.escape(variant), "[已脱敏]", sanitized, flags=re.IGNORECASE)
    return sanitized[:1000]


@router.delete("/llm/usage/config/{source_id}")
def delete_llm_usage_source(source_id: str) -> dict:
    try:
        result = delete_llm_usage_config(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_settings.cache_clear()
    return {"ok": True, **result}


@router.patch("/llm/usage/providers/{provider_id}")
def update_llm_usage_provider(provider_id: str, payload: LlmProviderConfigPayload) -> dict:
    try:
        result = update_llm_provider_config(provider_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_settings.cache_clear()
    return {"ok": True, **result}


@router.delete("/llm/usage/providers/{provider_id}")
def delete_llm_usage_provider(provider_id: str) -> dict:
    try:
        result = delete_llm_provider_config(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_settings.cache_clear()
    return {"ok": True, **result}


@router.get("/llm/usage/sources")
def llm_usage_sources(db: Session = Depends(get_db)) -> dict:
    config_items = list_llm_usage_config(get_settings())
    source_ids = [config["source_id"] for config in config_items]
    rows = []
    if source_ids:
        rows = db.scalars(select(LlmUsageSource).where(LlmUsageSource.source_id.in_(source_ids))).all()
    sources_by_id = {source.source_id: source for source in rows}
    return {"sources": [_llm_source_payload(sources_by_id.get(config["source_id"]), config) for config in config_items]}


@router.get("/llm/usage/summary")
def llm_usage_summary(
    range: LlmRange = Query("today"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    source_id, configured_source_ids = _llm_source_selection(source)
    source_rows = _llm_source_rows(db, source_id, configured_source_ids)
    snapshot_rows = _latest_llm_snapshot_rows(db, range, source_id, configured_source_ids)
    snapshots = [snapshot for snapshot, _source_row in snapshot_rows]
    request_count = sum(point.request_count or 0 for point in snapshots)
    token_count = sum(_snapshot_token_count(point, source_row) for point, source_row in snapshot_rows)
    amount = sum(point.estimated_amount or 0 for point in snapshots)
    estimated_cost = sum(_snapshot_cost(point) or 0 for point in snapshots)
    rpm_values = [point.rpm for point in snapshots if point.rpm is not None]
    tpm_values = [point.tpm for point in snapshots if point.tpm is not None]
    latency_values = [point.avg_latency_seconds for point in snapshots if point.avg_latency_seconds is not None]
    success_values = [point.success_rate for point in snapshots if point.success_rate is not None]
    return {
        "range": range,
        "request_count": request_count,
        "token_count": token_count,
        "estimated_amount": amount,
        "estimated_cost_usd": round(estimated_cost, 6),
        "avg_rpm": round(sum(rpm_values) / len(rpm_values), 4) if rpm_values else None,
        "avg_tpm": round(sum(tpm_values) / len(tpm_values), 4) if tpm_values else None,
        "avg_latency_seconds": round(sum(latency_values) / len(latency_values), 4) if latency_values else None,
        "success_rate": round(sum(success_values) / len(success_values), 4) if success_values else None,
        "snapshot_count": len(snapshots),
        **_llm_usage_capability(source_rows),
        **_llm_token_usage_status(snapshot_rows),
    }


@router.get("/llm/usage/series")
def llm_usage_series(
    range: LlmRange = Query("today"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    source_id, configured_source_ids = _llm_source_selection(source)
    source_rows = _llm_source_rows(db, source_id, configured_source_ids)
    rows = _llm_snapshot_rows(
        db,
        range,
        source_id,
        configured_source_ids,
        per_source_limit=_llm_series_point_limit(range),
    )
    series_by_source: dict[int, dict] = {}
    series_by_model: dict[str, dict] = {}
    latest_bucket_snapshot_ids = _latest_newapi_bucket_snapshot_ids_by_day(rows)
    for row, source_row in rows:
        if source_row.source_type == "deepseek_balance":
            continue
        newapi_buckets = _newapi_snapshot_buckets(row)
        if newapi_buckets:
            filtered_buckets = [
                bucket
                for bucket in newapi_buckets
                if latest_bucket_snapshot_ids.get((source_row.id, _newapi_bucket_date_key(bucket))) == row.id
            ]
            if filtered_buckets:
                _append_newapi_bucket_series(series_by_source, series_by_model, row, source_row, filtered_buckets)
            continue
        item = series_by_source.setdefault(
            source_row.id,
            {
                "source_id": source_row.source_id,
                "display_name": source_row.display_name,
                "source_type": source_row.source_type,
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
            if model_item.get("pricing_basis") == "deepseek_platform_cny":
                estimate = {
                    "estimated_cost_usd": model_item.get("estimated_cost_usd") or model_item.get("amount") or 0,
                    "pricing_basis": "deepseek_platform_cny",
                }
            model_series["points"].append(
                {
                    "timestamp": _iso(row.collected_at),
                    "source_id": source_row.source_id,
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
        **_llm_usage_capability(source_rows),
        **_llm_token_usage_status(rows),
    }


@router.get("/llm/usage/models")
def llm_usage_models(
    range: LlmRange = Query("today"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    totals: dict[str, dict] = {}
    source_id, configured_source_ids = _llm_source_selection(source)
    source_rows = _llm_source_rows(db, source_id, configured_source_ids)
    for snapshot in _latest_llm_snapshots(db, range, source_id, configured_source_ids):
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
            if item.get("pricing_basis") == "deepseek_platform_cny":
                total["estimated_cost_usd"] += item.get("estimated_cost_usd") or item.get("amount") or 0
                total["pricing_basis"] = "deepseek_platform_cny"
    for total in totals.values():
        if total.get("pricing_basis") == "deepseek_platform_cny":
            total["estimated_cost_usd"] = round(total["estimated_cost_usd"] or total["amount"], 6)
        else:
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
        **_llm_usage_capability(source_rows),
    }


@router.post("/llm/usage/refresh")
def llm_usage_refresh(db: Session = Depends(get_db)) -> dict:
    collect_llm_usage_once(db, get_settings())
    return {"ok": True}


@router.post("/llm/gateway/{source_id}/v1/{resource:path}")
async def llm_gateway_proxy(
    source_id: str,
    resource: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    config = _llm_gateway_config(source_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"gateway source {source_id} does not exist")
    if resource not in {"chat/completions", "responses"}:
        raise HTTPException(status_code=404, detail="only chat/completions and responses are supported")
    if not config.base_url:
        raise HTTPException(status_code=422, detail="gateway upstream Base URL is not configured")
    if not config.api_key:
        raise HTTPException(status_code=422, detail="gateway upstream API Key is not configured")
    if not config.access_token:
        raise HTTPException(status_code=422, detail="gateway access token is not configured")
    if _bearer_token(request.headers.get("authorization")) != config.access_token:
        raise HTTPException(status_code=401, detail="invalid gateway token")

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")

    started = time.perf_counter()
    forward_payload = _gateway_forward_payload(payload, resource)
    response = httpx.post(
        _gateway_upstream_url(config.base_url, resource),
        headers=_gateway_upstream_headers(request, config),
        json=forward_payload,
        timeout=600,
    )
    latency = time.perf_counter() - started
    result = _gateway_usage_result(config, forward_payload, response, latency)
    persist_result(db, result, datetime.now(timezone.utc))
    db.commit()
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json").split(";", 1)[0],
    )


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
        if not _gpu_matches_model_filter(gpu):
            continue
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
    if range_value == "14d":
        return until - timedelta(days=14), until
    if range_value == "29d":
        return until - timedelta(days=29), until
    return until - timedelta(hours=24), until


def _configured_llm_source_ids() -> list[str]:
    return [config["source_id"] for config in list_llm_usage_config(get_settings())]


def _llm_source_selection(selection: str | None) -> tuple[str | None, list[str]]:
    config_items = list_llm_usage_config(get_settings())
    configured_source_ids = [config["source_id"] for config in config_items]
    if not selection:
        return None, configured_source_ids
    if selection.startswith("provider:"):
        provider_id = selection.split(":", 1)[1]
        return None, [config["source_id"] for config in config_items if config.get("provider_id") == provider_id]
    if selection.startswith("source:"):
        return selection.split(":", 1)[1], configured_source_ids
    return selection, configured_source_ids


def _llm_source_rows(
    db: Session,
    source_id: str | None,
    configured_source_ids: list[str] | None = None,
) -> list[LlmUsageSource]:
    if source_id:
        if configured_source_ids is not None and source_id not in configured_source_ids:
            return []
        stmt = select(LlmUsageSource).where(LlmUsageSource.source_id == source_id)
    elif configured_source_ids is not None:
        if not configured_source_ids:
            return []
        stmt = select(LlmUsageSource).where(LlmUsageSource.source_id.in_(configured_source_ids))
    else:
        stmt = select(LlmUsageSource)
    return db.scalars(stmt).all()


def _llm_snapshot_rows(
    db: Session,
    range_value: str,
    source_id: str | None,
    configured_source_ids: list[str] | None = None,
    per_source_limit: int | None = None,
) -> list[tuple[LlmUsageSnapshot, LlmUsageSource]]:
    since, until = _llm_range_bounds(range_value)
    source_rows = _llm_source_rows(db, source_id, configured_source_ids)
    rows: list[tuple[LlmUsageSnapshot, LlmUsageSource]] = []
    for source_row in source_rows:
        stmt = select(LlmUsageSnapshot).where(
            LlmUsageSnapshot.source_id == source_row.id,
            LlmUsageSnapshot.collected_at >= since,
            LlmUsageSnapshot.collected_at <= until,
        )
        if per_source_limit is not None:
            stmt = stmt.order_by(desc(LlmUsageSnapshot.collected_at), desc(LlmUsageSnapshot.id)).limit(
                per_source_limit
            )
            snapshots = list(reversed(db.scalars(stmt).all()))
        else:
            stmt = stmt.order_by(LlmUsageSnapshot.collected_at, LlmUsageSnapshot.id)
            snapshots = db.scalars(stmt).all()
        rows.extend((snapshot, source_row) for snapshot in snapshots)
    return sorted(rows, key=lambda item: (item[0].collected_at, item[0].id))


def _latest_llm_snapshots(
    db: Session,
    range_value: str,
    source_id: str | None,
    configured_source_ids: list[str] | None = None,
) -> list[LlmUsageSnapshot]:
    rows = _latest_llm_snapshot_rows(db, range_value, source_id, configured_source_ids)
    return [snapshot for snapshot, _source in rows]


def _latest_llm_snapshot_rows(
    db: Session,
    range_value: str,
    source_id: str | None,
    configured_source_ids: list[str] | None = None,
) -> list[tuple[LlmUsageSnapshot, LlmUsageSource]]:
    return _llm_snapshot_rows(db, range_value, source_id, configured_source_ids, per_source_limit=1)


def _llm_series_point_limit(range_value: str) -> int:
    return LLM_SERIES_POINTS_PER_SOURCE.get(range_value, 288)


def _llm_source_payload(source: LlmUsageSource | None, config: dict | None = None) -> dict:
    source_type = config.get("source_type") if config else source.source_type
    is_newapi = source_type == "newapi_admin"
    provider_id = config.get("provider_id") if config else source.source_id
    provider_name = config.get("provider_name") if config else source.display_name
    source_id = config.get("source_id") if config else source.source_id
    display_name = config.get("display_name") if config else source.display_name
    return {
        "id": source.id if source else None,
        "source_id": source_id,
        "provider_id": provider_id or source_id,
        "provider_name": provider_name or display_name,
        "display_name": display_name,
        "source_type": source_type,
        "status": source.status if source else "unknown",
        "last_checked_at": _iso(source.last_checked_at) if source else None,
        "last_error": source.last_error if source else None,
        "balance_currency": source.balance_currency if source else None,
        "balance_total": source.balance_total if source else None,
        "balance_granted": source.balance_granted if source else None,
        "balance_topped_up": source.balance_topped_up if source else None,
        "quota_total": source.quota_total if source else None,
        "quota_used": source.quota_used if source else None,
        "quota_remaining": source.quota_remaining if source else None,
        "quota_used_usd": estimate_snapshot_cost_usd(raw_quota=source.quota_used) if is_newapi and source else None,
        "quota_remaining_usd": estimate_snapshot_cost_usd(raw_quota=source.quota_remaining) if is_newapi and source else None,
    }


def _snapshot_cost(snapshot: LlmUsageSnapshot) -> float | None:
    if (snapshot.raw_summary or {}).get("deepseek_platform"):
        return snapshot.estimated_amount
    model_cost = estimate_snapshot_cost_usd(
        model_stats=snapshot.model_stats or [],
        token_count=snapshot.token_count,
        raw_quota=snapshot.quota_used,
    )
    if snapshot.model_stats and model_cost is not None:
        return model_cost
    if snapshot.estimated_amount is not None and (snapshot.raw_summary or {}).get("token_usage"):
        return snapshot.estimated_amount
    return model_cost


def _latest_newapi_bucket_snapshot_ids_by_day(
    rows: list[tuple[LlmUsageSnapshot, LlmUsageSource]],
) -> dict[tuple[int, str], int]:
    latest: dict[tuple[int, str], tuple[datetime, int]] = {}
    for row, source_row in rows:
        buckets = _newapi_snapshot_buckets(row)
        if source_row.source_type != "newapi_admin" or not buckets:
            continue
        for bucket in buckets:
            date_key = _newapi_bucket_date_key(bucket)
            if not date_key:
                continue
            key = (source_row.id, date_key)
            current = latest.get(key)
            value = (row.collected_at, row.id)
            if current is None or value > current:
                latest[key] = value
    return {key: snapshot_id for key, (_collected_at, snapshot_id) in latest.items()}


def _newapi_snapshot_buckets(snapshot: LlmUsageSnapshot) -> list[dict]:
    newapi = (snapshot.raw_summary or {}).get("newapi")
    buckets = newapi.get("buckets") if isinstance(newapi, dict) else None
    return buckets if isinstance(buckets, list) else []


def _snapshot_token_count(snapshot: LlmUsageSnapshot, source_row: LlmUsageSource) -> float:
    if source_row.source_type != "newapi_admin":
        return snapshot.token_count or 0
    buckets = _newapi_snapshot_buckets(snapshot)
    if not buckets:
        return snapshot.token_count or 0
    total = 0.0
    seen = False
    for bucket in buckets:
        value = _trusted_newapi_bucket_token_count(bucket)
        if value is None:
            continue
        total += value
        seen = True
    return total if seen else 0


def _trusted_newapi_bucket_token_count(bucket: dict) -> float | None:
    if not isinstance(bucket, dict):
        return None
    if "input_tokens" not in bucket and "output_tokens" not in bucket:
        return None
    return (_number_from_any(bucket, ["input_tokens"]) or 0) + (_number_from_any(bucket, ["output_tokens"]) or 0)


def _llm_token_usage_status(rows: list[tuple[LlmUsageSnapshot, LlmUsageSource]]) -> dict:
    has_newapi = False
    logs_truncated = False
    legacy_untrusted = False
    logs_total = 0
    logs_collected = 0
    saw_log_meta = False
    for snapshot, source_row in rows:
        if source_row.source_type != "newapi_admin":
            continue
        has_newapi = True
        meta = _newapi_logs_meta(snapshot)
        if meta["total"] is not None:
            saw_log_meta = True
            logs_total += meta["total"]
            logs_collected += meta["collected"]
        logs_truncated = logs_truncated or meta["truncated"]
        legacy_untrusted = legacy_untrusted or _newapi_has_untrusted_bucket_tokens(snapshot)

    if not has_newapi:
        return {
            "token_usage_complete": True,
            "token_usage_scope": "full",
            "token_usage_message": None,
            "logs_truncated": False,
            "logs_total": None,
            "logs_collected": None,
        }
    if logs_truncated:
        return {
            "token_usage_complete": False,
            "token_usage_scope": "sampled_logs",
            "token_usage_message": "NewAPI日志超过当前采集上限，Token为采样值，官方消耗金额仍以额度统计为准",
            "logs_truncated": True,
            "logs_total": logs_total if saw_log_meta else None,
            "logs_collected": logs_collected if saw_log_meta else None,
        }
    if legacy_untrusted:
        return {
            "token_usage_complete": False,
            "token_usage_scope": "untrusted_legacy_logs",
            "token_usage_message": "历史NewAPI快照缺少输入/输出Token明细，已忽略不可信Token值",
            "logs_truncated": False,
            "logs_total": logs_total if saw_log_meta else None,
            "logs_collected": logs_collected if saw_log_meta else None,
        }
    return {
        "token_usage_complete": True,
        "token_usage_scope": "full",
        "token_usage_message": None,
        "logs_truncated": False,
        "logs_total": logs_total if saw_log_meta else None,
        "logs_collected": logs_collected if saw_log_meta else None,
    }


def _newapi_has_untrusted_bucket_tokens(snapshot: LlmUsageSnapshot) -> bool:
    for bucket in _newapi_snapshot_buckets(snapshot):
        if _trusted_newapi_bucket_token_count(bucket) is None and _number_from_any(bucket, ["token_count"]) not in (None, 0):
            return True
    return False


def _newapi_logs_meta(snapshot: LlmUsageSnapshot) -> dict[str, int | bool | None]:
    logs = (snapshot.raw_summary or {}).get("logs")
    if isinstance(logs, dict) and isinstance(logs.get("data"), dict):
        logs = logs["data"]
    if not isinstance(logs, dict):
        return {"total": None, "collected": 0, "truncated": False}
    total = _optional_int(_number_from_any(logs, ["total"]))
    page_size = _optional_int(_number_from_any(logs, ["page_size"]))
    pages_collected = _optional_int(_number_from_any(logs, ["pages_collected"]))
    items = logs.get("items")
    item_count = len(items) if isinstance(items, list) else None
    if page_size is not None and pages_collected is not None:
        collected = page_size * pages_collected
    else:
        collected = item_count or 0
    if total is not None:
        collected = min(collected, total)
    return {
        "total": total,
        "collected": collected,
        "truncated": logs.get("truncated") is True or (total is not None and collected < total),
    }


def _optional_int(value: float | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _newapi_bucket_date_key(bucket: dict) -> str:
    if not isinstance(bucket, dict):
        return ""
    timestamp = bucket.get("timestamp")
    if not timestamp:
        return ""
    text = str(timestamp)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().date().isoformat()


def _append_newapi_bucket_series(
    series_by_source: dict[int, dict],
    series_by_model: dict[str, dict],
    snapshot: LlmUsageSnapshot,
    source_row: LlmUsageSource,
    buckets: list[dict],
) -> None:
    item = series_by_source.setdefault(
        source_row.id,
        {
            "source_id": source_row.source_id,
            "display_name": source_row.display_name,
            "source_type": source_row.source_type,
            "points": [],
        },
    )
    source_totals: dict[str, dict] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        timestamp = bucket.get("timestamp")
        if not timestamp:
            continue
        source_total = source_totals.setdefault(
            str(timestamp),
            {
                "timestamp": str(timestamp),
                "request_count": 0,
                "token_count": None,
                "quota_used": 0,
                "estimated_amount": 0,
                "estimated_cost_usd": 0,
                "rpm": snapshot.rpm,
                "tpm": snapshot.tpm,
            },
        )
        amount = bucket.get("amount") or 0
        estimated_cost = bucket.get("estimated_cost_usd") or 0
        token_count = _trusted_newapi_bucket_token_count(bucket)
        source_total["request_count"] += bucket.get("request_count") or 0
        if token_count is not None:
            source_total["token_count"] = (source_total["token_count"] or 0) + token_count
        source_total["quota_used"] += amount
        source_total["estimated_amount"] += amount
        source_total["estimated_cost_usd"] += estimated_cost

        model = bucket.get("model") or "unknown"
        model_series = series_by_model.setdefault(str(model), {"model": str(model), "display_name": str(model), "points": []})
        model_series["points"].append(
            {
                "timestamp": str(timestamp),
                "source_id": source_row.source_id,
                "request_count": bucket.get("request_count") or 0,
                "amount": amount,
                "estimated_cost_usd": estimated_cost,
                "pricing_basis": bucket.get("pricing_basis") or "newapi_quota",
            }
        )
    item["points"].extend(
        {
            **point,
            "quota_used": round(point["quota_used"], 6),
            "estimated_amount": round(point["estimated_amount"], 6),
            "estimated_cost_usd": round(point["estimated_cost_usd"], 6),
        }
        for _timestamp, point in sorted(source_totals.items())
    )


def _llm_usage_capability(source_rows: list[LlmUsageSource]) -> dict:
    deepseek_count = sum(1 for source in source_rows if source.source_type == "deepseek_balance")
    usage_source_count = len(source_rows) - deepseek_count
    if deepseek_count and not usage_source_count:
        return {
            "usage_supported": False,
            "usage_scope": "balance_only",
            "usage_message": "DeepSeek官方只提供余额，未提供请求、token、模型用量统计",
        }
    if deepseek_count and usage_source_count:
        return {
            "usage_supported": True,
            "usage_scope": "partial",
            "usage_message": "部分来源仅提供余额，未计入请求、token、模型用量统计",
        }
    return {"usage_supported": True, "usage_scope": "full", "usage_message": None}


def _llm_gateway_config(source_id: str) -> LlmUsageConfig | None:
    return next(
        (
            config
            for config in load_llm_usage_configs(get_settings())
            if config.source_id == source_id and config.source_type == "openai_gateway"
        ),
        None,
    )


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _gateway_upstream_url(base_url: str, resource: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{resource}"
    return f"{normalized}/v1/{resource}"


def _gateway_upstream_headers(request: Request, config: LlmUsageConfig) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
    accept = request.headers.get("accept")
    if accept:
        headers["Accept"] = accept
    return headers


def _gateway_forward_payload(payload: dict, resource: str) -> dict:
    result = dict(payload)
    if resource == "chat/completions" and result.get("stream") is True:
        stream_options = result.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
        result["stream_options"] = {**stream_options, "include_usage": True}
    return result


def _gpu_matches_model_filter(gpu: Gpu) -> bool:
    filters = [item.strip().lower() for item in get_settings().gpu_model_filter.split(",") if item.strip()]
    if not filters:
        return True
    name = (gpu.name or "").lower()
    return any(item in name for item in filters)


def _gateway_usage_result(
    config: LlmUsageConfig,
    request_payload: dict,
    response: httpx.Response,
    latency_seconds: float,
) -> LlmUsageResult:
    response_payload = _response_json(response)
    usage = response_payload.get("usage") if isinstance(response_payload, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    model = str(
        (response_payload.get("model") if isinstance(response_payload, dict) else None)
        or request_payload.get("model")
        or config.test_model
        or "unknown"
    )
    input_tokens = _number_from_any(usage, ["prompt_tokens", "input_tokens"])
    output_tokens = _number_from_any(usage, ["completion_tokens", "output_tokens"])
    cache_hit_tokens = _number_from_any(usage, ["prompt_cache_hit_tokens", "cache_hit_input_tokens"])
    cache_miss_tokens = _number_from_any(usage, ["prompt_cache_miss_tokens", "cache_miss_input_tokens"])
    total_tokens = _number_from_any(usage, ["total_tokens", "total_token"])
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    estimate = estimate_model_cost_usd(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit_input_tokens=cache_hit_tokens,
        cache_miss_input_tokens=cache_miss_tokens,
        token_count=total_tokens,
    )
    model_stats = [
        {
            "model": model,
            "request_count": 1,
            "token_count": total_tokens or 0,
            "input_tokens": input_tokens or 0,
            "output_tokens": output_tokens or 0,
            "cache_hit_input_tokens": cache_hit_tokens or 0,
            "cache_miss_input_tokens": cache_miss_tokens or 0,
            "estimated_cost_usd": estimate["estimated_cost_usd"],
            "pricing_basis": estimate["pricing_basis"],
        }
    ]
    error = None if response.status_code < 400 else _gateway_error_message(response)
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="online" if response.status_code < 400 else "offline",
        request_count=1,
        token_count=total_tokens,
        estimated_amount=estimate["estimated_cost_usd"],
        success_rate=100 if response.status_code < 400 else 0,
        avg_latency_seconds=round(latency_seconds, 4),
        model_stats=model_stats,
        raw_summary={
            "gateway": {
                "resource": request_payload.get("model"),
                "status_code": response.status_code,
                "usage": usage,
                "pricing_basis": estimate["pricing_basis"],
            }
        },
        error=error,
    )


def _response_json(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return _sse_usage_payload(response.text)
    return payload if isinstance(payload, dict) else {}


def _sse_usage_payload(text: str) -> dict:
    usage = None
    model = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        model = payload.get("model") or model
        if isinstance(payload.get("usage"), dict):
            usage = payload["usage"]
    if usage:
        return {"model": model, "usage": usage}
    return {"model": model} if model else {}


def _number_from_any(value: dict, keys: list[str]) -> float | None:
    for key in keys:
        number = value.get(key)
        if number is None or number == "":
            continue
        try:
            return float(number)
        except (TypeError, ValueError):
            continue
    return None


def _gateway_error_message(response: httpx.Response) -> str:
    payload = _response_json(response)
    if payload:
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or f"HTTP {response.status_code}")[:1000]
        if error:
            return str(error)[:1000]
        for key in ("message", "detail"):
            if payload.get(key):
                return str(payload[key])[:1000]
    return f"HTTP {response.status_code}"


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
