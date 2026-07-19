from __future__ import annotations

from typing import Any

NEWAPI_QUOTA_PER_USD = 500_000

OPENAI_PRICES_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.4),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1-nano": (0.1, 0.4),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "o3": (2.0, 8.0),
    "o4-mini": (1.1, 4.4),
}


def estimate_model_cost_usd(
    model: str,
    *,
    input_tokens: float | None = None,
    output_tokens: float | None = None,
    token_count: float | None = None,
    raw_quota: float | None = None,
) -> dict[str, Any]:
    normalized = _normalize_model(model)
    pricing = OPENAI_PRICES_PER_1M.get(normalized)
    input_count = _number(input_tokens)
    output_count = _number(output_tokens)
    total_count = _number(token_count)
    quota = _number(raw_quota)

    if quota is not None:
        return {
            "estimated_cost_usd": round(quota / NEWAPI_QUOTA_PER_USD, 6),
            "pricing_basis": "newapi_quota",
            "pricing_model": normalized,
        }

    if pricing and (input_count is not None or output_count is not None or total_count is not None):
        if input_count is None and output_count is None:
            input_count = total_count or 0
            output_count = 0
        cost = ((input_count or 0) * pricing[0] + (output_count or 0) * pricing[1]) / 1_000_000
        return {
            "estimated_cost_usd": round(cost, 6),
            "pricing_basis": "openai_tokens",
            "pricing_model": normalized,
            "input_price_per_1m": pricing[0],
            "output_price_per_1m": pricing[1],
        }

    return {
        "estimated_cost_usd": None,
        "pricing_basis": "unknown",
        "pricing_model": normalized,
    }


def estimate_snapshot_cost_usd(
    *,
    model_stats: list[dict[str, Any]] | None = None,
    token_count: float | None = None,
    raw_quota: float | None = None,
) -> float | None:
    if model_stats:
        total = 0.0
        seen = False
        for item in model_stats:
            result = estimate_model_cost_usd(
                str(item.get("model") or "unknown"),
                input_tokens=item.get("input_tokens"),
                output_tokens=item.get("output_tokens"),
                token_count=item.get("token_count"),
                raw_quota=item.get("amount"),
            )
            if result["estimated_cost_usd"] is not None:
                total += result["estimated_cost_usd"]
                seen = True
        if seen:
            return round(total, 6)
    result = estimate_model_cost_usd("unknown", token_count=token_count, raw_quota=raw_quota)
    return result["estimated_cost_usd"]


def _normalize_model(model: str) -> str:
    value = model.strip().lower()
    for suffix in ("-latest", "-preview"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
