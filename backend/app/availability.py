from __future__ import annotations

AVAILABLE_WINDOW = 6
AVAILABLE_UTILIZATION_LT = 20.0
AVAILABLE_MEMORY_USED_LT_MB = 5000.0
SATURATED_UTILIZATION_GTE = 90.0
SATURATED_MEMORY_RATIO_GTE = 0.8


def classify_gpu_status(
    machine_status: str,
    samples: list[dict[str, float | None]],
    *,
    source_status: str = "ok",
) -> str:
    if source_status == "unreachable":
        return "unknown"
    if machine_status == "disconnected":
        return "offline"
    if len(samples) < AVAILABLE_WINDOW:
        return "unknown"

    recent = samples[-AVAILABLE_WINDOW:]
    if any(_is_saturated(sample) for sample in recent):
        return "saturated"
    if all(_is_available_sample(sample) for sample in recent):
        return "available"
    return "busy"


def _is_available_sample(sample: dict[str, float | None]) -> bool:
    utilization = sample.get("utilization")
    memory_used = sample.get("memory_used_mb")
    return (
        utilization is not None
        and memory_used is not None
        and utilization < AVAILABLE_UTILIZATION_LT
        and memory_used < AVAILABLE_MEMORY_USED_LT_MB
    )


def _is_saturated(sample: dict[str, float | None]) -> bool:
    utilization = sample.get("utilization")
    memory_used = sample.get("memory_used_mb")
    memory_total = sample.get("memory_total_mb")
    if utilization is not None and utilization >= SATURATED_UTILIZATION_GTE:
        return True
    if memory_used is None or not memory_total:
        return False
    return memory_used / memory_total >= SATURATED_MEMORY_RATIO_GTE

