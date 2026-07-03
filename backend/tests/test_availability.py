from app.availability import classify_gpu_status


def sample(utilization, memory_used_mb, memory_total_mb=81920.0):
    return {
        "utilization": utilization,
        "memory_used_mb": memory_used_mb,
        "memory_total_mb": memory_total_mb,
    }


def test_gpu_is_available_after_six_low_samples():
    samples = [sample(0.0, 1000.0) for _ in range(6)]

    assert classify_gpu_status("connected", samples) == "available"


def test_gpu_is_unknown_when_sample_window_is_too_short():
    samples = [sample(0.0, 1000.0) for _ in range(5)]

    assert classify_gpu_status("connected", samples) == "unknown"


def test_gpu_is_busy_when_recent_window_exceeds_available_threshold():
    samples = [sample(0.0, 1000.0) for _ in range(5)] + [sample(25.0, 1000.0)]

    assert classify_gpu_status("connected", samples) == "busy"


def test_gpu_is_saturated_on_high_utilization_or_memory_ratio():
    assert classify_gpu_status("connected", [sample(95.0, 1000.0) for _ in range(6)]) == "saturated"
    assert classify_gpu_status("connected", [sample(10.0, 70000.0) for _ in range(6)]) == "saturated"


def test_gpu_is_offline_when_machine_is_disconnected():
    assert classify_gpu_status("disconnected", [sample(0.0, 0.0) for _ in range(6)]) == "offline"


def test_gpu_is_unknown_when_source_is_unreachable():
    assert classify_gpu_status("connected", [sample(0.0, 0.0) for _ in range(6)], source_status="unreachable") == "unknown"

