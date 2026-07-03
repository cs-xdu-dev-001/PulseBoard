from app.normalizer import normalize_latest_payload, parse_source_timestamp


SAMPLE_PAYLOAD = {
    "servers": [
        {
            "name": "a100",
            "disk_metrics": {
                "disk": {
                    "/data": {
                        "available_mb": 1103787,
                        "percentage": 84.6,
                        "total_mb": 7569530,
                        "used_mb": 6084251,
                    }
                },
                "status": "connected",
                "timestamp": "2026-07-02T08:29:09.520678",
            },
            "resource_metrics": {
                "cpu": 12.4,
                "gpu": [
                    {
                        "index": 0,
                        "memory_total_mb": 81920.0,
                        "memory_used_mb": 66504.0,
                        "name": "NVIDIA A100 80GB PCIe",
                        "utilization": 100.0,
                    }
                ],
                "memory": {
                    "percentage": 10.7,
                    "total_mb": 1031433.31640625,
                    "used_mb": 110290.3984375,
                },
                "server": "a100",
                "status": "connected",
                "timestamp": "2026-07-02T14:24:09.521518",
            },
        },
        {
            "name": "3090",
            "disk_metrics": {
                "error": "Failed to connect to server",
                "server": "3090",
                "status": "disconnected",
                "timestamp": "2026-07-02T08:29:09.555347",
            },
            "resource_metrics": {
                "error": "Failed to connect to server",
                "server": "3090",
                "status": "disconnected",
                "timestamp": "2026-07-02T14:24:10.662702",
            },
        },
    ],
    "timestamp": "2026-07-02T14:24:53.079017",
}


def test_normalize_latest_payload_extracts_machine_and_gpu_metrics():
    result = normalize_latest_payload(SAMPLE_PAYLOAD)

    assert result.source_timestamp.isoformat() == "2026-07-02T06:24:53.079017+00:00"
    assert len(result.machines) == 2
    assert result.machines[0].name == "a100"
    assert result.machines[0].status == "connected"
    assert result.machines[0].cpu_percent == 12.4
    assert result.machines[0].memory_percent == 10.7
    assert result.machines[0].disks["/data"]["percentage"] == 84.6
    assert len(result.gpus) == 1
    assert result.gpus[0].machine_name == "a100"
    assert result.gpus[0].gpu_index == 0
    assert result.gpus[0].name == "NVIDIA A100 80GB PCIe"
    assert result.gpus[0].utilization == 100.0
    assert result.gpus[0].memory_used_mb == 66504.0


def test_normalize_latest_payload_keeps_disconnected_machine_without_metrics():
    result = normalize_latest_payload(SAMPLE_PAYLOAD)
    machine = result.machines[1]

    assert machine.name == "3090"
    assert machine.status == "disconnected"
    assert machine.cpu_percent is None
    assert machine.memory_percent is None
    assert machine.disks == {}


def test_naive_lab_timestamp_is_interpreted_as_asia_shanghai():
    parsed = parse_source_timestamp("2026-07-02T14:24:53.079017")

    assert parsed.isoformat() == "2026-07-02T06:24:53.079017+00:00"
