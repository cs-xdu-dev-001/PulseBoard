from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import VpsMetric, VpsNode
from app.node_exporter import calculate_traffic_quota, normalize_node_metrics, parse_node_exporters


def collect_nodes_once(db: Session, settings: Settings) -> None:
    for target in parse_node_exporters(settings.node_exporters):
        collect_node_once(db, settings, target.name, target.url)
    cleanup_old_vps_data(db, settings.retention_days, datetime.now(timezone.utc))
    db.commit()


def collect_node_once(db: Session, settings: Settings, name: str, url: str) -> None:
    node = get_or_create_vps_node(db, name, url)
    collected_at = datetime.now(timezone.utc)
    try:
        text = fetch_metrics(url)
    except Exception as exc:
        node.status = "offline"
        node.last_error = str(exc)
        db.add(
            VpsMetric(
                node_id=node.id,
                collected_at=collected_at,
                status="offline",
                disks={},
                network_interfaces={},
            )
        )
        return

    previous = previous_metric_payload(db, node.id)
    normalized = normalize_node_metrics(name, url, text, previous, collected_at=collected_at)
    if name == settings.traffic_quota_node:
        ensure_traffic_period(node, normalized.total_network_bytes, collected_at, settings)
    quota = calculate_traffic_quota(
        node_name=name,
        quota_node=settings.traffic_quota_node,
        total_gb=settings.traffic_quota_total_gb,
        initial_used_gb=node.traffic_base_used_gb or 0.0,
        current_total_bytes=normalized.total_network_bytes,
        baseline_total_bytes=node.traffic_baseline_bytes,
    )

    node.url = url
    node.status = normalized.status
    node.last_seen_at = collected_at
    node.last_error = None
    db.add(
        VpsMetric(
            node_id=node.id,
            collected_at=collected_at,
            status=normalized.status,
            cpu_percent=normalized.cpu_percent,
            memory_percent=normalized.memory_percent,
            memory_total_bytes=normalized.memory_total_bytes,
            memory_available_bytes=normalized.memory_available_bytes,
            disks=normalized.disks,
            network_interfaces=_interfaces_with_rates(normalized.network_interfaces, previous, collected_at),
            network_rx_bytes_per_sec=normalized.network_rx_bytes_per_sec,
            network_tx_bytes_per_sec=normalized.network_tx_bytes_per_sec,
            load1=normalized.load1,
            load5=normalized.load5,
            load15=normalized.load15,
            uptime_seconds=normalized.uptime_seconds,
            traffic_used_gb=quota["used_gb"] if quota else None,
            traffic_total_gb=quota["total_gb"] if quota else None,
            traffic_used_percent=quota["used_percent"] if quota else None,
        )
    )


def fetch_metrics(url: str) -> str:
    response = httpx.get(_metrics_url(url), timeout=10)
    response.raise_for_status()
    return response.text


def get_or_create_vps_node(db: Session, name: str, url: str) -> VpsNode:
    node = db.scalar(select(VpsNode).where(VpsNode.name == name))
    if node is None:
        node = VpsNode(name=name, url=url)
        db.add(node)
        db.flush()
    return node


def previous_metric_payload(db: Session, node_id: int) -> dict | None:
    row = db.scalar(
        select(VpsMetric).where(VpsMetric.node_id == node_id).order_by(VpsMetric.collected_at.desc()).limit(1)
    )
    if row is None:
        return None
    return {
        "collected_at": row.collected_at.replace(tzinfo=timezone.utc) if row.collected_at.tzinfo is None else row.collected_at,
        "network_interfaces": row.network_interfaces,
        "cpu_totals": row.network_interfaces.get("_cpu_totals", {}) if row.network_interfaces else {},
    }


def cleanup_old_vps_data(db: Session, retention_days: int, now: datetime) -> None:
    cutoff = now - timedelta(days=retention_days)
    db.execute(delete(VpsMetric).where(VpsMetric.collected_at < cutoff))


def ensure_traffic_period(node: VpsNode, current_total_bytes: float, now: datetime, settings: Settings) -> None:
    period_key = traffic_period_key(now, settings.traffic_quota_reset_day)
    if node.traffic_period_key == period_key:
        return
    node.traffic_baseline_bytes = current_total_bytes
    node.traffic_base_used_gb = settings.traffic_quota_initial_used_gb if node.traffic_period_key is None else 0.0
    node.traffic_period_key = period_key


def traffic_period_key(now: datetime, reset_day: int) -> str:
    if now.day >= reset_day:
        return f"{now.year:04d}-{now.month:02d}"
    year = now.year
    month = now.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def _metrics_url(url: str) -> str:
    return url.rstrip("/") + "/metrics" if not url.rstrip("/").endswith("/metrics") else url


def _interfaces_with_rates(interfaces: dict, previous: dict | None, collected_at: datetime) -> dict:
    result = {name: dict(values) for name, values in interfaces.items()}
    if not previous or not previous.get("collected_at"):
        return result
    elapsed = (collected_at - previous["collected_at"]).total_seconds()
    if elapsed <= 0:
        return result
    previous_interfaces = previous.get("network_interfaces") or {}
    for name, values in result.items():
        if name.startswith("_"):
            continue
        old = previous_interfaces.get(name)
        if not old:
            continue
        values["rx_bytes_per_sec"] = round(max(0.0, values["rx_bytes_total"] - old.get("rx_bytes_total", 0.0)) / elapsed, 2)
        values["tx_bytes_per_sec"] = round(max(0.0, values["tx_bytes_total"] - old.get("tx_bytes_total", 0.0)) / elapsed, 2)
    return result
