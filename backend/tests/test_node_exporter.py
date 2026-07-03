from datetime import datetime, timezone

from app.node_collector import traffic_period_key
from app.node_collector import _interfaces_with_rates
from app.node_exporter import (
    calculate_traffic_quota,
    normalize_node_metrics,
    parse_bandwidth,
    parse_node_exporters,
    parse_prometheus_text,
)


PROM_TEXT = """
node_cpu_seconds_total{cpu="0",mode="idle"} 100
node_cpu_seconds_total{cpu="0",mode="user"} 40
node_cpu_seconds_total{cpu="0",mode="system"} 10
node_memory_MemTotal_bytes 1000
node_memory_MemAvailable_bytes 250
node_filesystem_size_bytes{mountpoint="/",fstype="ext4",device="/dev/vda1"} 1000
node_filesystem_avail_bytes{mountpoint="/",fstype="ext4",device="/dev/vda1"} 200
node_filesystem_size_bytes{mountpoint="/run",fstype="tmpfs",device="tmpfs"} 1000
node_filesystem_avail_bytes{mountpoint="/run",fstype="tmpfs",device="tmpfs"} 900
node_network_receive_bytes_total{device="eth0"} 10000
node_network_transmit_bytes_total{device="eth0"} 5000
node_network_receive_bytes_total{device="lo"} 100000
node_network_transmit_bytes_total{device="lo"} 100000
node_load1 0.42
node_load5 0.55
node_load15 0.61
node_boot_time_seconds 1000
node_time_seconds 87400
"""


def test_parse_prometheus_text_extracts_metric_labels_and_values():
    parsed = parse_prometheus_text('node_load1 0.42\nnode_network_receive_bytes_total{device="eth0"} 100\n')

    assert parsed["node_load1"][0].value == 0.42
    assert parsed["node_network_receive_bytes_total"][0].labels["device"] == "eth0"
    assert parsed["node_network_receive_bytes_total"][0].value == 100


def test_normalize_node_metrics_filters_virtual_disk_and_loopback():
    metrics = normalize_node_metrics("vpn-gateway", "http://example:9100", PROM_TEXT, None)

    assert metrics.name == "vpn-gateway"
    assert round(metrics.memory_percent, 2) == 75.0
    assert metrics.disks["/"]["percentage"] == 80.0
    assert "/run" not in metrics.disks
    assert metrics.network_interfaces["eth0"]["rx_bytes_total"] == 10000
    assert "lo" not in metrics.network_interfaces
    assert metrics.uptime_seconds == 86400


def test_normalize_node_metrics_calculates_rates_from_previous_sample():
    previous = {
        "collected_at": datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc),
        "network_interfaces": {
            "eth0": {"rx_bytes_total": 4000, "tx_bytes_total": 1000},
        },
    }

    metrics = normalize_node_metrics(
        "vpn-gateway",
        "http://example:9100",
        PROM_TEXT,
        previous,
        collected_at=datetime(2026, 7, 2, 0, 1, tzinfo=timezone.utc),
    )

    assert metrics.network_rx_bytes_per_sec == 100
    assert round(metrics.network_tx_bytes_per_sec, 2) == 66.67


def test_parse_node_exporters_supports_named_and_unnamed_targets():
    targets = parse_node_exporters("vpn-gateway=http://1.2.3.4:9100,http://5.6.7.8:9100")

    assert targets[0].name == "vpn-gateway"
    assert targets[0].url == "http://1.2.3.4:9100"
    assert targets[1].name == "5.6.7.8"


def test_traffic_quota_uses_initial_usage_plus_network_delta():
    quota = calculate_traffic_quota(
        node_name="vpn-gateway",
        quota_node="vpn-gateway",
        total_gb=250,
        initial_used_gb=71.23,
        current_total_bytes=3_000_000_000,
        baseline_total_bytes=1_000_000_000,
    )

    assert quota is not None
    assert quota["total_gb"] == 250
    assert quota["used_gb"] > 71.23
    assert quota["used_gb"] == 73.23
    assert round(quota["used_percent"], 2) == round(quota["used_gb"] / 250 * 100, 2)


def test_traffic_quota_uses_decimal_gb_for_provider_billing_units():
    quota = calculate_traffic_quota(
        node_name="vpn-gateway",
        quota_node="vpn-gateway",
        total_gb=250,
        initial_used_gb=71.23,
        current_total_bytes=3_000_000_000,
        baseline_total_bytes=1_000_000_000,
    )

    assert quota is not None
    assert quota["used_gb"] == 73.23


def test_traffic_quota_is_absent_for_other_nodes():
    assert calculate_traffic_quota("vps-us", "vpn-gateway", 250, 71.23, 3000, 1000) is None


def test_parse_bandwidth_accepts_common_units():
    assert parse_bandwidth("100Mbps") == 100_000_000
    assert parse_bandwidth("1Gbps") == 1_000_000_000
    assert parse_bandwidth("") is None


def test_traffic_period_key_uses_monthly_reset_day():
    assert traffic_period_key(datetime(2026, 7, 18, tzinfo=timezone.utc), 18) == "2026-07"
    assert traffic_period_key(datetime(2026, 7, 17, tzinfo=timezone.utc), 18) == "2026-06"


def test_interfaces_with_rates_ignores_internal_cpu_totals():
    current = {
        "eth0": {"rx_bytes_total": 10000, "tx_bytes_total": 5000},
        "_cpu_totals": {"total": 200, "busy": 50},
    }
    previous = {
        "collected_at": datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc),
        "network_interfaces": {
            "eth0": {"rx_bytes_total": 4000, "tx_bytes_total": 1000},
            "_cpu_totals": {"total": 100, "busy": 20},
        },
    }

    result = _interfaces_with_rates(current, previous, datetime(2026, 7, 2, 0, 1, tzinfo=timezone.utc))

    assert result["eth0"]["rx_bytes_per_sec"] == 100
    assert result["eth0"]["tx_bytes_per_sec"] == 66.67
    assert "rx_bytes_per_sec" not in result["_cpu_totals"]
