from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from app.config import ROOT_DIR, Settings
from app.llm_pricing import estimate_model_cost_usd, estimate_snapshot_cost_usd


@dataclass(frozen=True)
class LlmUsageConfig:
    source_id: str
    display_name: str
    source_type: str
    provider_id: str | None = None
    provider_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    access_token: str | None = None
    user_id: str = "1"


@dataclass(frozen=True)
class LlmUsageResult:
    source_id: str
    display_name: str
    source_type: str
    status: str
    balance_currency: str | None = None
    balance_total: float | None = None
    balance_granted: float | None = None
    balance_topped_up: float | None = None
    quota_total: float | None = None
    quota_used: float | None = None
    quota_remaining: float | None = None
    request_count: float | None = None
    token_count: float | None = None
    estimated_amount: float | None = None
    rpm: float | None = None
    tpm: float | None = None
    success_rate: float | None = None
    avg_latency_seconds: float | None = None
    model_stats: list[dict[str, Any]] | None = None
    raw_summary: dict[str, Any] | None = None
    error: str | None = None


def load_llm_usage_configs(settings: Settings, env_path: Path | None = None) -> list[LlmUsageConfig]:
    env = _merged_env(env_path or ROOT_DIR / ".env")
    configs = []
    source_list = env.get("PULSEBOARD_LLM_USAGE_SOURCES") or settings.llm_usage_sources
    for source_id in [item.strip() for item in source_list.split(",") if item.strip()]:
        prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
        source_type = env.get(prefix + "TYPE", "").strip()
        display_name = env.get(prefix + "DISPLAY_NAME", "").strip() or source_id
        provider_id = env.get(prefix + "PROVIDER_ID", "").strip() or source_id
        provider_name = env.get(prefix + "PROVIDER_NAME", "").strip() or display_name
        if not source_type:
            continue
        configs.append(
            LlmUsageConfig(
                source_id=source_id,
                display_name=display_name,
                source_type=source_type,
                provider_id=provider_id,
                provider_name=provider_name,
                base_url=(env.get(prefix + "BASE_URL") or "").strip() or None,
                api_key=(env.get(prefix + "API_KEY") or "").strip() or None,
                access_token=(env.get(prefix + "ACCESS_TOKEN") or "").strip() or None,
                user_id=(env.get(prefix + "USER_ID") or "1").strip() or "1",
            )
        )
    return configs


def list_llm_usage_config(settings: Settings, env_path: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "source_id": config.source_id,
            "provider_id": config.provider_id,
            "provider_name": config.provider_name,
            "display_name": config.display_name,
            "source_type": config.source_type,
            "base_url": config.base_url,
            "user_id": config.user_id,
            "has_api_key": bool(config.api_key),
            "has_access_token": bool(config.access_token),
        }
        for config in load_llm_usage_configs(settings, env_path=env_path)
    ]


def save_llm_usage_config(values: dict[str, Any], env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    source_id = str(values.get("source_id") or "").strip()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", source_id):
        raise ValueError("source_id must use lowercase letters, numbers, '-' or '_'")
    source_type = str(values.get("source_type") or "").strip()
    if source_type not in {"deepseek_balance", "newapi_admin"}:
        raise ValueError("source_type must be deepseek_balance or newapi_admin")
    provider_id = str(values.get("provider_id") or source_id).strip()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", provider_id):
        raise ValueError("provider_id must use lowercase letters, numbers, '-' or '_'")
    provider_name = str(values.get("provider_name") or values.get("display_name") or provider_id).strip()

    env = _merged_env(env_path)
    sources = [item.strip() for item in env.get("PULSEBOARD_LLM_USAGE_SOURCES", "").split(",") if item.strip()]
    for existing_source_id in sources:
        if existing_source_id != source_id and _env_key(existing_source_id) == _env_key(source_id):
            raise ValueError(f"source_id {source_id} conflicts with existing source_id {existing_source_id}")
    if source_id not in sources:
        sources.append(source_id)
    prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
    updates = {
        "PULSEBOARD_LLM_USAGE_SOURCES": ",".join(sources),
        prefix + "TYPE": source_type,
        prefix + "PROVIDER_ID": provider_id,
        prefix + "PROVIDER_NAME": provider_name,
        prefix + "DISPLAY_NAME": str(values.get("display_name") or source_id).strip(),
    }
    if values.get("base_url") is not None:
        updates[prefix + "BASE_URL"] = str(values.get("base_url") or "").strip()
    if values.get("api_key"):
        updates[prefix + "API_KEY"] = str(values["api_key"]).strip()
    if values.get("access_token"):
        updates[prefix + "ACCESS_TOKEN"] = str(values["access_token"]).strip()
    if values.get("user_id") is not None:
        updates[prefix + "USER_ID"] = str(values.get("user_id") or "1").strip()

    _write_env(env_path, updates)
    return {"source_id": source_id, "provider_id": provider_id}


def delete_llm_usage_config(source_id: str, env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    source_id = _validated_id(source_id, "source_id")
    env = _merged_env(env_path)
    sources = [item.strip() for item in env.get("PULSEBOARD_LLM_USAGE_SOURCES", "").split(",") if item.strip()]
    if source_id not in sources:
        raise ValueError(f"source_id {source_id} does not exist")
    next_sources = [item for item in sources if item != source_id]
    prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
    updates = {"PULSEBOARD_LLM_USAGE_SOURCES": ",".join(next_sources)}
    deletes = {key for key in env if key.startswith(prefix)}
    _write_env(env_path, updates, deletes)
    return {"deleted": [source_id]}


def delete_llm_provider_config(provider_id: str, env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    provider_id = _validated_id(provider_id, "provider_id")
    source_ids = _source_ids_for_provider(provider_id, env_path)
    if not source_ids:
        raise ValueError(f"provider_id {provider_id} does not exist")
    env = _merged_env(env_path)
    sources = [item.strip() for item in env.get("PULSEBOARD_LLM_USAGE_SOURCES", "").split(",") if item.strip()]
    updates = {"PULSEBOARD_LLM_USAGE_SOURCES": ",".join([item for item in sources if item not in source_ids])}
    deletes = set()
    for source_id in source_ids:
        prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
        deletes.update(key for key in env if key.startswith(prefix))
    _write_env(env_path, updates, deletes)
    return {"deleted": source_ids}


def update_llm_provider_config(provider_id: str, values: dict[str, Any], env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    provider_id = _validated_id(provider_id, "provider_id")
    source_type = str(values.get("source_type") or "").strip()
    if source_type not in {"deepseek_balance", "newapi_admin"}:
        raise ValueError("source_type must be deepseek_balance or newapi_admin")
    provider_name = str(values.get("provider_name") or provider_id).strip()
    base_url = str(values.get("base_url") or "").strip()
    user_id = str(values.get("user_id") or "1").strip() or "1"
    source_ids = _source_ids_for_provider(provider_id, env_path)
    if not source_ids:
        raise ValueError(f"provider_id {provider_id} does not exist")

    updates: dict[str, str] = {}
    deletes: set[str] = set()
    for source_id in source_ids:
        prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
        updates.update(
            {
                prefix + "PROVIDER_ID": provider_id,
                prefix + "PROVIDER_NAME": provider_name,
                prefix + "TYPE": source_type,
            }
        )
        if source_type == "newapi_admin":
            updates[prefix + "BASE_URL"] = base_url
            updates[prefix + "USER_ID"] = user_id
        else:
            deletes.update({prefix + "BASE_URL", prefix + "USER_ID"})
    _write_env(env_path, updates, deletes)
    return {"updated": source_ids}


def deepseek_balance_url() -> str:
    return "https://api.deepseek.com/user/balance"


def newapi_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def normalize_deepseek_balance(config: LlmUsageConfig, payload: dict[str, Any]) -> LlmUsageResult:
    infos = payload.get("balance_infos") or []
    first = infos[0] if infos else {}
    total = _to_float(first.get("total_balance"))
    granted = _to_float(first.get("granted_balance"))
    topped_up = _to_float(first.get("topped_up_balance"))
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="online" if payload.get("is_available", True) else "degraded",
        balance_currency=first.get("currency"),
        balance_total=total,
        balance_granted=granted,
        balance_topped_up=topped_up,
        quota_total=total,
        quota_used=None,
        quota_remaining=total,
        raw_summary={"deepseek": _safe_summary(payload)},
    )


def normalize_newapi(config: LlmUsageConfig, payloads: dict[str, Any]) -> LlmUsageResult:
    dashboard = _unwrap(payloads.get("dashboard"))
    stat = _unwrap(payloads.get("stat"))
    logs = _unwrap(payloads.get("logs"))
    channels = _unwrap(payloads.get("channels"))

    request_count = _first_number(stat, ["count", "request_count", "total_count"]) or _first_number(
        dashboard, ["count", "request_count", "total_count"]
    )
    token_count = _first_number(stat, ["token", "tokens", "token_count", "total_tokens"]) or _first_number(
        dashboard, ["token", "tokens", "token_count", "total_tokens"]
    )
    quota_used = _first_number(stat, ["quota", "used_quota", "quota_used", "amount"]) or _first_number(
        dashboard, ["quota", "used_quota", "quota_used", "amount"]
    )
    rpm = _first_number(stat, ["rpm", "request_rpm"])
    tpm = _first_number(stat, ["tpm", "token_tpm"])
    success_rate = _first_number(stat, ["success_rate"])
    avg_latency = _first_number(stat, ["avg_latency", "avg_latency_seconds", "latency"])
    model_stats = _model_stats_from(logs) or _model_stats_from(stat) or _model_stats_from(dashboard)
    quota_total = _first_number(dashboard, ["quota"])
    dashboard_quota_used = _first_number(dashboard, ["used_quota"])
    balance_total = _channel_balance_total(channels)
    if dashboard_quota_used is not None:
        quota_used = dashboard_quota_used
    if quota_total is None:
        quota_total = balance_total

    estimated_cost = estimate_snapshot_cost_usd(model_stats=model_stats, token_count=token_count, raw_quota=quota_used)
    degraded = any(isinstance(value, dict) and value.get("_error") for value in payloads.values())
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="degraded" if degraded else "online",
        balance_total=balance_total,
        quota_total=quota_total,
        quota_used=quota_used,
        quota_remaining=quota_total - quota_used if quota_total is not None and quota_used is not None else None,
        request_count=request_count,
        token_count=token_count,
        estimated_amount=estimated_cost,
        rpm=rpm,
        tpm=tpm,
        success_rate=success_rate,
        avg_latency_seconds=avg_latency,
        model_stats=model_stats,
        raw_summary={
            "dashboard": _safe_summary(dashboard),
            "stat": _safe_summary(stat),
            "logs": _safe_summary(logs),
            "channels": _safe_summary(channels),
        },
    )


def error_result(config: LlmUsageConfig, message: str) -> LlmUsageResult:
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="offline",
        error=message[:1000],
        raw_summary={},
    )


def _merged_env(env_path: Path) -> dict[str, str]:
    result = dict(os.environ)
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"')
    return result


def _write_env(env_path: Path, updates: dict[str, str], deletes: set[str] | None = None) -> None:
    deletes = deletes or set()
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen = set()
    next_lines = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in deletes:
            continue
        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            next_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def _validated_id(value: str, label: str) -> str:
    item = str(value or "").strip()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", item):
        raise ValueError(f"{label} must use lowercase letters, numbers, '-' or '_'")
    return item


def _source_ids_for_provider(provider_id: str, env_path: Path) -> list[str]:
    env = _merged_env(env_path)
    source_ids = [item.strip() for item in env.get("PULSEBOARD_LLM_USAGE_SOURCES", "").split(",") if item.strip()]
    result = []
    for source_id in source_ids:
        prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
        if (env.get(prefix + "PROVIDER_ID") or source_id).strip() == provider_id:
            result.append(source_id)
    return result


def _env_key(value: str) -> str:
    return value.upper().replace("-", "_")


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("data", "result"):
            if key in value:
                return value[key]
    return value


def _first_number(value: Any, keys: list[str]) -> float | None:
    if isinstance(value, dict):
        for key in keys:
            number = _to_float(value.get(key))
            if number is not None:
                return number
        for child in value.values():
            number = _first_number(child, keys)
            if number is not None:
                return number
    if isinstance(value, list):
        for child in value:
            number = _first_number(child, keys)
            if number is not None:
                return number
    return None


def _model_stats_from(value: Any) -> list[dict[str, Any]]:
    rows = _model_rows(value)
    if not rows:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        model = item.get("model") or item.get("model_name")
        if not model:
            continue
        grouped_item = grouped.setdefault(
            str(model),
            {
                "model": str(model),
                "request_count": 0,
                "token_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "amount": 0,
                "estimated_cost_usd": 0,
                "pricing_basis": "unknown",
            },
        )
        grouped_item["request_count"] += _to_float(item.get("count") or item.get("request_count")) or 1
        input_tokens = _to_float(item.get("input_tokens") or item.get("prompt_tokens"))
        output_tokens = _to_float(item.get("output_tokens") or item.get("completion_tokens"))
        token_count = _to_float(item.get("token") or item.get("tokens") or item.get("token_count") or item.get("total_tokens"))
        grouped_item["token_count"] += token_count or 0
        grouped_item["input_tokens"] += input_tokens or 0
        grouped_item["output_tokens"] += output_tokens or 0
        grouped_item["amount"] += _to_float(item.get("amount") or item.get("quota") or item.get("used_quota")) or 0
    for grouped_item in grouped.values():
        estimate = estimate_model_cost_usd(
            grouped_item["model"],
            input_tokens=grouped_item["input_tokens"] or None,
            output_tokens=grouped_item["output_tokens"] or None,
            token_count=grouped_item["token_count"] or None,
            raw_quota=grouped_item["amount"] or None,
        )
        grouped_item.update(estimate)
    return sorted(grouped.values(), key=lambda item: item.get("estimated_cost_usd") or item["amount"], reverse=True)[:50]


def _model_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows = []
        for key in ("items", "logs", "data"):
            child = value.get(key)
            if isinstance(child, list):
                rows.extend(_model_rows(child))
            elif isinstance(child, dict):
                rows.extend(_model_rows(child))
        if any(key in value for key in ("model", "model_name")):
            rows.append(value)
        return rows
    return []


def _channel_balance_total(value: Any) -> float | None:
    items = value if isinstance(value, list) else value.get("items") if isinstance(value, dict) else None
    if not isinstance(items, list):
        return _first_number(value, ["balance", "remaining_quota", "quota"])
    total = 0.0
    seen = False
    for item in items:
        if not isinstance(item, dict):
            continue
        number = _first_number(item, ["balance", "remaining_quota"])
        if number is not None:
            total += number
            seen = True
    return total if seen else None


def _safe_summary(value: Any) -> Any:
    if isinstance(value, dict):
        blocked = ("token", "key", "email", "ip", "content", "request_id", "username", "other", "setting")
        return {
            key: _safe_summary(child)
            for key, child in list(value.items())[:50]
            if not any(part in key.lower() for part in blocked)
        }
    if isinstance(value, list):
        return [_safe_summary(child) for child in value[:20]]
    return value
