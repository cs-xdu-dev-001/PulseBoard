from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse


VIRTUAL_FILESYSTEMS = {
    "tmpfs",
    "devtmpfs",
    "overlay",
    "squashfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "nsfs",
    "ramfs",
    "autofs",
    "debugfs",
    "tracefs",
    "securityfs",
    "pstore",
    "bpf",
    "fusectl",
    "configfs",
}

IGNORED_NET_PREFIXES = ("lo", "docker", "veth", "br-", "tun", "tap")


@dataclass(frozen=True)
class MetricSample:
    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class NodeExporterTarget:
    name: str
    url: str


@dataclass(frozen=True)
class NormalizedNodeMetrics:
    name: str
    url: str
    collected_at: datetime
    cpu_percent: float | None
    memory_percent: float | None
    memory_total_bytes: float | None
    memory_available_bytes: float | None
    disks: dict
    network_interfaces: dict
    network_rx_bytes_per_sec: float | None
    network_tx_bytes_per_sec: float | None
    load1: float | None
    load5: float | None
    load15: float | None
    uptime_seconds: float | None
    total_network_bytes: float
    status: str


def parse_node_exporters(value: str) -> list[NodeExporterTarget]:
    targets: list[NodeExporterTarget] = []
    for raw in [item.strip() for item in value.split(",") if item.strip()]:
        if "=" in raw:
            name, url = raw.split("=", 1)
            targets.append(NodeExporterTarget(name=name.strip(), url=url.strip()))
            continue
        parsed = urlparse(raw)
        targets.append(NodeExporterTarget(name=parsed.hostname or raw, url=raw))
    return targets


def parse_prometheus_text(text: str) -> dict[str, list[MetricSample]]:
    result: dict[str, list[MetricSample]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        left, value_raw = line.rsplit(maxsplit=1)
        try:
            value = float(value_raw)
        except ValueError:
            continue
        if "{" in left:
            name, labels_raw = left.split("{", 1)
            labels = _parse_labels(labels_raw.rstrip("}"))
        else:
            name, labels = left, {}
        result.setdefault(name, []).append(MetricSample(labels=labels, value=value))
    return result


def normalize_node_metrics(
    name: str,
    url: str,
    text: str,
    previous: dict | None,
    *,
    collected_at: datetime | None = None,
) -> NormalizedNodeMetrics:
    collected_at = collected_at or datetime.now(timezone.utc)
    metrics = parse_prometheus_text(text)
    memory_total = _first_value(metrics, "node_memory_MemTotal_bytes")
    memory_available = _first_value(metrics, "node_memory_MemAvailable_bytes")
    memory_percent = None
    if memory_total and memory_available is not None:
        memory_percent = round((memory_total - memory_available) / memory_total * 100, 2)

    disks = _parse_disks(metrics)
    network_interfaces = _parse_network(metrics)
    rx_rate, tx_rate = _network_rates(network_interfaces, previous, collected_at)
    cpu_percent = _cpu_percent(metrics, previous)
    load1 = _first_value(metrics, "node_load1")
    load5 = _first_value(metrics, "node_load5")
    load15 = _first_value(metrics, "node_load15")
    boot_time = _first_value(metrics, "node_boot_time_seconds")
    node_time = _first_value(metrics, "node_time_seconds")
    uptime = node_time - boot_time if node_time is not None and boot_time is not None else None
    status = _node_status(cpu_percent, memory_percent, disks)

    return NormalizedNodeMetrics(
        name=name,
        url=url,
        collected_at=collected_at,
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        memory_total_bytes=memory_total,
        memory_available_bytes=memory_available,
        disks=disks,
        network_interfaces=network_interfaces,
        network_rx_bytes_per_sec=rx_rate,
        network_tx_bytes_per_sec=tx_rate,
        load1=load1,
        load5=load5,
        load15=load15,
        uptime_seconds=uptime,
        total_network_bytes=sum(
            item["rx_bytes_total"] + item["tx_bytes_total"]
            for key, item in network_interfaces.items()
            if not key.startswith("_")
        ),
        status=status,
    )


def calculate_traffic_quota(
    node_name: str,
    quota_node: str,
    total_gb: float,
    initial_used_gb: float,
    current_total_bytes: float,
    baseline_total_bytes: float | None,
) -> dict | None:
    if node_name != quota_node or not total_gb:
        return None
    baseline = current_total_bytes if baseline_total_bytes is None else baseline_total_bytes
    delta_gb = max(0.0, current_total_bytes - baseline) / 1_000_000_000
    used_gb = initial_used_gb + delta_gb
    return {
        "used_gb": round(used_gb, 4),
        "total_gb": total_gb,
        "used_percent": round(min(100.0, used_gb / total_gb * 100), 4),
    }


def parse_bandwidth(value: str) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([MGT]?bps)\s*", value, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    factor = {"bps": 1, "mbps": 1_000_000, "gbps": 1_000_000_000, "tbps": 1_000_000_000_000}[unit]
    return int(amount * factor)


def _parse_labels(raw: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, value in re.findall(r'(\w+)="((?:\\"|[^"])*)"', raw):
        labels[key] = value.replace('\\"', '"')
    return labels


def _first_value(metrics: dict[str, list[MetricSample]], name: str) -> float | None:
    samples = metrics.get(name) or []
    return samples[0].value if samples else None


def _parse_disks(metrics: dict[str, list[MetricSample]]) -> dict:
    sizes: dict[str, MetricSample] = {}
    avails: dict[str, MetricSample] = {}
    for sample in metrics.get("node_filesystem_size_bytes", []):
        if _is_real_filesystem(sample):
            sizes[sample.labels["mountpoint"]] = sample
    for sample in metrics.get("node_filesystem_avail_bytes", []):
        if _is_real_filesystem(sample):
            avails[sample.labels["mountpoint"]] = sample
    disks = {}
    for mount, size_sample in sizes.items():
        avail_sample = avails.get(mount)
        if not avail_sample or size_sample.value <= 0:
            continue
        used = size_sample.value - avail_sample.value
        disks[mount] = {
            "fstype": size_sample.labels.get("fstype"),
            "device": size_sample.labels.get("device"),
            "total_bytes": size_sample.value,
            "available_bytes": avail_sample.value,
            "used_bytes": used,
            "percentage": round(used / size_sample.value * 100, 2),
        }
    return disks


def _parse_network(metrics: dict[str, list[MetricSample]]) -> dict:
    rx = {sample.labels["device"]: sample.value for sample in metrics.get("node_network_receive_bytes_total", [])}
    tx = {sample.labels["device"]: sample.value for sample in metrics.get("node_network_transmit_bytes_total", [])}
    interfaces = {}
    for device, rx_value in rx.items():
        if _is_ignored_interface(device):
            continue
        interfaces[device] = {
            "rx_bytes_total": rx_value,
            "tx_bytes_total": tx.get(device, 0.0),
        }
    interfaces["_cpu_totals"] = _cpu_totals(metrics)
    return interfaces


def _network_rates(interfaces: dict, previous: dict | None, collected_at: datetime) -> tuple[float | None, float | None]:
    if not previous or not previous.get("collected_at"):
        return None, None
    elapsed = (collected_at - previous["collected_at"]).total_seconds()
    if elapsed <= 0:
        return None, None
    previous_interfaces = previous.get("network_interfaces") or {}
    rx_delta = 0.0
    tx_delta = 0.0
    for device, current in interfaces.items():
        if device.startswith("_"):
            continue
        old = previous_interfaces.get(device)
        if not old:
            continue
        rx_delta += max(0.0, current["rx_bytes_total"] - old.get("rx_bytes_total", 0.0))
        tx_delta += max(0.0, current["tx_bytes_total"] - old.get("tx_bytes_total", 0.0))
    return round(rx_delta / elapsed, 2), round(tx_delta / elapsed, 2)


def _cpu_percent(metrics: dict[str, list[MetricSample]], previous: dict | None) -> float | None:
    current = _cpu_totals(metrics)
    if not previous or not previous.get("cpu_totals"):
        return None
    previous_totals = previous["cpu_totals"]
    total_delta = current["total"] - previous_totals.get("total", 0.0)
    busy_delta = current["busy"] - previous_totals.get("busy", 0.0)
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, busy_delta / total_delta * 100)), 2)


def cpu_totals_from_text(text: str) -> dict[str, float]:
    return _cpu_totals(parse_prometheus_text(text))


def _cpu_totals(metrics: dict[str, list[MetricSample]]) -> dict[str, float]:
    idle_modes = {"idle", "iowait", "steal"}
    total = 0.0
    busy = 0.0
    for sample in metrics.get("node_cpu_seconds_total", []):
        total += sample.value
        if sample.labels.get("mode") not in idle_modes:
            busy += sample.value
    return {"total": total, "busy": busy}


def _is_real_filesystem(sample: MetricSample) -> bool:
    return sample.labels.get("fstype") not in VIRTUAL_FILESYSTEMS


def _is_ignored_interface(device: str) -> bool:
    return device.startswith(IGNORED_NET_PREFIXES)


def _node_status(cpu_percent: float | None, memory_percent: float | None, disks: dict) -> str:
    if cpu_percent is not None and cpu_percent > 90:
        return "critical"
    if memory_percent is not None and memory_percent > 90:
        return "critical"
    if any(disk.get("percentage", 0) > 85 for disk in disks.values()):
        return "critical"
    return "online"
