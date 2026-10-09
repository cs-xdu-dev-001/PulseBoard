from datetime import datetime, timedelta, timezone

import pytest

from app.node_collector import traffic_period_key
from app.node_collector import _interfaces_with_rates
from app.node_exporter import (
    calculate_traffic_quota,
    cpu_totals_from_text,
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


WINDOWS_TEXT = """
windows_cpu_time_total{core="0,0",mode="idle"} 100
windows_cpu_time_total{core="0,0",mode="user"} 40
windows_cpu_time_total{core="0,0",mode="privileged"} 10
windows_cpu_time_total{core="0,0",mode="dpc"} 2
windows_cpu_time_total{core="0,0",mode="interrupt"} 1
windows_cpu_time_total{core="0,1",mode="idle"} 200
windows_cpu_time_total{core="0,1",mode="user"} 70
windows_cpu_time_total{core="0,1",mode="privileged"} 30
windows_cpu_time_total{core="0,1",mode="dpc"} 2
windows_cpu_time_total{core="0,1",mode="interrupt"} 1
windows_memory_physical_total_bytes 1000
windows_memory_available_bytes 250
windows_logical_disk_info{volume="C:",filesystem="NTFS"} 1
windows_logical_disk_size_bytes{volume="C:"} 1000
windows_logical_disk_free_bytes{volume="C:"} 200
windows_logical_disk_size_bytes{volume="D:"} 2000
windows_logical_disk_free_bytes{volume="D:"} 1500
windows_logical_disk_size_bytes{volume="HarddiskVolume1"} 1000
windows_logical_disk_free_bytes{volume="HarddiskVolume1"} 10
windows_logical_disk_size_bytes{volume="_Total"} 4000
windows_logical_disk_free_bytes{volume="_Total"} 1710
windows_logical_disk_size_bytes{volume="E:"} 0
windows_logical_disk_free_bytes{volume="E:"} 0
windows_logical_disk_size_bytes{volume="F:"} 1000
windows_net_bytes_received_total{nic="Ethernet 2"} 10000
windows_net_bytes_sent_total{nic="Ethernet 2"} 5000
windows_net_bytes_received_total{nic="ZeroTier One"} 300
windows_net_bytes_sent_total{nic="ZeroTier One"} 200
windows_net_bytes_received_total{nic="Loopback Pseudo-Interface 1"} 100000
windows_net_bytes_sent_total{nic="Loopback Pseudo-Interface 1"} 100000
windows_net_bytes_received_total{nic="_Total"} 110300
windows_net_bytes_sent_total{nic="_Total"} 105200
windows_system_boot_time_timestamp 1000
"""


def test_windows_metrics_normalize_memory_disks_network_and_uptime():
    metrics = normalize_node_metrics(
        "host-monitor", "http://windows:9182/metrics", WINDOWS_TEXT, None,
        collected_at=datetime.fromtimestamp(87400, tz=timezone.utc),
    )

    assert metrics.memory_total_bytes == 1000
    assert metrics.memory_available_bytes == 250
    assert metrics.memory_percent == 75
    assert set(metrics.disks) == {"C:", "D:"}
    assert metrics.disks["C:"] == {
        "fstype": "NTFS", "device": "C:", "total_bytes": 1000,
        "available_bytes": 200, "used_bytes": 800, "percentage": 80,
    }
    assert metrics.disks["D:"]["percentage"] == 25
    assert set(metrics.network_interfaces) == {"Ethernet 2", "ZeroTier One", "_cpu_totals"}
    assert metrics.total_network_bytes == 15500
    assert metrics.uptime_seconds == 86400
    assert metrics.cpu_percent is None  # Rates require two samples.
    assert metrics.network_rx_bytes_per_sec is None
    assert metrics.load1 is None and metrics.load5 is None and metrics.load15 is None
    assert metrics.status == "online"


def test_windows_rates_use_two_samples_without_double_counting_cpu_modes():
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    first = normalize_node_metrics("windows", "http://windows:9182", WINDOWS_TEXT, None, collected_at=now)
    previous = {
        "collected_at": now, "network_interfaces": first.network_interfaces,
        "cpu_totals": first.network_interfaces["_cpu_totals"],
    }
    second_text = WINDOWS_TEXT.replace('mode="idle"} 100', 'mode="idle"} 130').replace(
        'mode="user"} 40', 'mode="user"} 60'
    ).replace('mode="privileged"} 10', 'mode="privileged"} 20').replace(
        'mode="idle"} 200', 'mode="idle"} 240'
    ).replace('mode="user"} 70', 'mode="user"} 80').replace(
        'mode="privileged"} 30', 'mode="privileged"} 40'
    ).replace('mode="dpc"} 2', 'mode="dpc"} 4').replace(
        'mode="interrupt"} 1', 'mode="interrupt"} 3'
    ).replace('nic="Ethernet 2"} 10000', 'nic="Ethernet 2"} 16000').replace(
        'nic="Ethernet 2"} 5000', 'nic="Ethernet 2"} 9000'
    )
    second = normalize_node_metrics(
        "windows", "http://windows:9182", second_text, previous, collected_at=now + timedelta(seconds=60),
    )

    assert cpu_totals_from_text(WINDOWS_TEXT) == {"total": 450, "busy": 150}
    assert second.cpu_percent == 41.67  # 50 busy seconds out of 120 across two cores.
    assert second.network_rx_bytes_per_sec == 100
    assert second.network_tx_bytes_per_sec == 66.67
    interfaces = _interfaces_with_rates(second.network_interfaces, previous, second.collected_at)
    assert interfaces["Ethernet 2"]["rx_bytes_per_sec"] == 100
    assert interfaces["ZeroTier One"]["rx_bytes_per_sec"] == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_windows_memory_exhaustion_and_legacy_metric_names(legacy):
    text = WINDOWS_TEXT.replace("windows_memory_available_bytes 250", "windows_memory_available_bytes 0")
    if legacy:
        text = text.replace("windows_memory_physical_total_bytes", "windows_cs_physical_memory_bytes").replace(
            "windows_memory_available_bytes", "windows_os_physical_memory_free_bytes"
        ).replace("windows_system_boot_time_timestamp", "windows_system_system_up_time")
    metrics = normalize_node_metrics(
        "windows", "http://windows:9182", text, None,
        collected_at=datetime.fromtimestamp(87400, tz=timezone.utc),
    )
    assert metrics.memory_percent == 100
    assert metrics.status == "critical"
    assert metrics.uptime_seconds == 86400


def test_windows_uptime_prefers_host_clock_when_available():
    text = WINDOWS_TEXT + "windows_time_current_timestamp_seconds 87400\n"
    metrics = normalize_node_metrics("windows", "http://windows:9182", text, None)
    assert metrics.uptime_seconds == 86400


def test_windows_disabled_collectors_leave_gauges_unavailable():
    metrics = normalize_node_metrics("windows", "http://windows:9182", "windows_exporter_build_info 1\n", None)
    assert metrics.memory_percent is None
    assert metrics.cpu_percent is None
    assert metrics.uptime_seconds is None
    assert metrics.disks == {}


def test_windows_counter_reset_does_not_report_negative_rates():
    previous = {
        "collected_at": datetime(2026, 10, 9, tzinfo=timezone.utc),
        "cpu_totals": {"total": 10000, "busy": 4000},
        "network_interfaces": {"Ethernet 2": {"rx_bytes_total": 90000, "tx_bytes_total": 80000}},
    }
    metrics = normalize_node_metrics(
        "windows", "http://windows:9182", WINDOWS_TEXT, previous,
        collected_at=previous["collected_at"] + timedelta(seconds=30),
    )
    assert metrics.cpu_percent is None
    assert metrics.network_rx_bytes_per_sec == 0
    assert metrics.network_tx_bytes_per_sec == 0


def test_linux_cpu_rate_is_preserved():
    previous = {"cpu_totals": {"total": 100, "busy": 30}}
    metrics = normalize_node_metrics("linux", "http://linux:9100", PROM_TEXT, previous)
    assert metrics.cpu_percent == 40
