from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urljoin

from app.config import ROOT_DIR, Settings
from app.llm_pricing import NEWAPI_QUOTA_PER_USD, estimate_model_cost_usd, estimate_snapshot_cost_usd

_ENV_UPDATE_LOCK = RLock()
USAGE_SOURCE_TYPES = {"deepseek_balance", "deepseek_platform", "newapi_admin", "openai_gateway"}


def _serialized_env_update(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with _ENV_UPDATE_LOCK:
            return function(*args, **kwargs)

    return wrapper


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
    request_mode: str = "responses"
    test_model: str | None = None


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
    source_list = (
        env["PULSEBOARD_LLM_USAGE_SOURCES"]
        if "PULSEBOARD_LLM_USAGE_SOURCES" in env
        else settings.llm_usage_sources
    )
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
                request_mode=(
                    env.get(prefix + "REQUEST_MODE")
                    or ("chat_completions" if source_type in {"deepseek_balance", "deepseek_platform"} else "responses")
                ).strip(),
                test_model=(
                    env.get(prefix + "TEST_MODEL")
                    or ("deepseek-chat" if source_type in {"deepseek_balance", "deepseek_platform"} else "")
                ).strip()
                or None,
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
            "request_mode": config.request_mode,
            "test_model": config.test_model,
            "has_api_key": bool(config.api_key),
            "has_access_token": bool(config.access_token),
        }
        for config in load_llm_usage_configs(settings, env_path=env_path)
    ]


@_serialized_env_update
def save_llm_usage_config(values: dict[str, Any], env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    source_id = str(values.get("source_id") or "").strip()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", source_id):
        raise ValueError("source_id must use lowercase letters, numbers, '-' or '_'")
    source_type = str(values.get("source_type") or "").strip()
    if source_type not in USAGE_SOURCE_TYPES:
        raise ValueError("source_type must be deepseek_balance, deepseek_platform, newapi_admin or openai_gateway")
    provider_id = str(values.get("provider_id") or source_id).strip()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", provider_id):
        raise ValueError("provider_id must use lowercase letters, numbers, '-' or '_'")
    provider_name = str(values.get("provider_name") or values.get("display_name") or provider_id).strip()
    base_url = str(values.get("base_url") or "").strip()
    user_id = str(values.get("user_id") or "1").strip() or "1"
    request_mode = str(
        values.get("request_mode")
        or ("chat_completions" if source_type in {"deepseek_balance", "deepseek_platform"} else "responses")
    ).strip()
    test_model = str(
        values.get("test_model")
        or ("deepseek-chat" if source_type in {"deepseek_balance", "deepseek_platform"} else "")
    ).strip()

    env = _merged_env(env_path)
    sources = [item.strip() for item in env.get("PULSEBOARD_LLM_USAGE_SOURCES", "").split(",") if item.strip()]
    source_exists = source_id in sources
    shared = _provider_shared_values(env, sources, provider_id)
    access_token = str(values.get("access_token") or "").strip()
    if shared:
        source_type = shared["source_type"]
        provider_name = shared["provider_name"]
        base_url = shared["base_url"] if shared["has_base_url"] else base_url
        if source_type != "openai_gateway":
            access_token = access_token or shared["access_token"]
        user_id = shared["user_id"] if shared["has_user_id"] else user_id
        request_mode = shared["request_mode"] if shared["has_request_mode"] else str(
            values.get("request_mode")
            or ("chat_completions" if source_type in {"deepseek_balance", "deepseek_platform"} else "responses")
        ).strip()
        test_model = shared["test_model"] if shared["has_test_model"] else str(
            values.get("test_model")
            or ("deepseek-chat" if source_type in {"deepseek_balance", "deepseek_platform"} else "")
        ).strip()
    elif source_type in {"deepseek_balance", "deepseek_platform"}:
        base_url = ""
        user_id = "1"
    if source_type == "openai_gateway" and not access_token and not source_exists:
        raise ValueError("gateway access token is required for a new gateway key")
    if source_type == "deepseek_platform" and not access_token and not source_exists and not shared:
        raise ValueError("DeepSeek platform token is required for platform usage statistics")
    if request_mode not in {"responses", "chat_completions"}:
        raise ValueError("request_mode must be responses or chat_completions")
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
        prefix + "BASE_URL": base_url,
        prefix + "USER_ID": user_id,
        prefix + "REQUEST_MODE": request_mode,
        prefix + "TEST_MODEL": test_model,
    }
    if values.get("api_key"):
        updates[prefix + "API_KEY"] = str(values["api_key"]).strip()
    if source_type in {"deepseek_platform", "newapi_admin", "openai_gateway"} and access_token:
        updates[prefix + "ACCESS_TOKEN"] = access_token

    if shared:
        for existing_source_id in sources:
            existing_prefix = f"PULSEBOARD_LLM_{_env_key(existing_source_id)}_"
            if (env.get(existing_prefix + "PROVIDER_ID") or existing_source_id).strip() != provider_id:
                continue
            updates.update(
                {
                    existing_prefix + "PROVIDER_ID": provider_id,
                    existing_prefix + "PROVIDER_NAME": provider_name,
                    existing_prefix + "TYPE": source_type,
                    existing_prefix + "BASE_URL": base_url,
                    existing_prefix + "USER_ID": user_id,
                    existing_prefix + "REQUEST_MODE": request_mode,
                    existing_prefix + "TEST_MODEL": test_model,
                }
            )
            if source_type in {"deepseek_platform", "newapi_admin"} and access_token:
                updates[existing_prefix + "ACCESS_TOKEN"] = access_token

    _write_env(env_path, updates)
    return {"source_id": source_id, "provider_id": provider_id}


@_serialized_env_update
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


@_serialized_env_update
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


@_serialized_env_update
def update_llm_provider_config(provider_id: str, values: dict[str, Any], env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    provider_id = _validated_id(provider_id, "provider_id")
    source_ids = _source_ids_for_provider(provider_id, env_path)
    if not source_ids:
        raise ValueError(f"provider_id {provider_id} does not exist")
    env = _merged_env(env_path)
    existing = _provider_shared_values(env, source_ids, provider_id)
    source_type = str(values.get("source_type") or "").strip()
    if source_type not in USAGE_SOURCE_TYPES:
        raise ValueError("source_type must be deepseek_balance, deepseek_platform, newapi_admin or openai_gateway")
    provider_name = str(values.get("provider_name") or provider_id).strip()
    base_url = str(values.get("base_url") or "").strip()
    user_id = str(values.get("user_id") or "1").strip() or "1"
    same_source_type = bool(existing and existing["source_type"] == source_type)
    request_mode_value = values.get("request_mode")
    request_mode = str(request_mode_value).strip() if request_mode_value is not None else (
        existing["request_mode"]
        if same_source_type
        else ("chat_completions" if source_type in {"deepseek_balance", "deepseek_platform"} else "responses")
    )
    if request_mode not in {"responses", "chat_completions"}:
        raise ValueError("request_mode must be responses or chat_completions")
    test_model_value = values.get("test_model")
    test_model = str(test_model_value).strip() if test_model_value is not None else (
        existing["test_model"]
        if same_source_type
        else ("deepseek-chat" if source_type in {"deepseek_balance", "deepseek_platform"} else "")
    )
    access_token = str(values.get("access_token") or "").strip()

    updates: dict[str, str] = {}
    deletes: set[str] = set()
    for source_id in source_ids:
        prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
        updates.update(
            {
                prefix + "PROVIDER_ID": provider_id,
                prefix + "PROVIDER_NAME": provider_name,
                prefix + "TYPE": source_type,
                prefix + "REQUEST_MODE": request_mode,
                prefix + "TEST_MODEL": test_model,
            }
        )
        if source_type in {"newapi_admin", "openai_gateway"}:
            updates[prefix + "BASE_URL"] = base_url
            updates[prefix + "USER_ID"] = user_id
            if access_token:
                updates[prefix + "ACCESS_TOKEN"] = access_token
        elif source_type == "deepseek_platform":
            deletes.update({prefix + "BASE_URL", prefix + "USER_ID"})
            if access_token:
                updates[prefix + "ACCESS_TOKEN"] = access_token
        else:
            deletes.update({prefix + "BASE_URL", prefix + "USER_ID", prefix + "ACCESS_TOKEN"})
    _write_env(env_path, updates, deletes)
    return {"updated": source_ids}


def deepseek_balance_url() -> str:
    return "https://api.deepseek.com/user/balance"


def newapi_url(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return urljoin(normalized + "/", path.lstrip("/"))


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


def normalize_deepseek_platform(config: LlmUsageConfig, payloads: dict[str, Any]) -> LlmUsageResult:
    amount_payload = payloads.get("amount") or {}
    cost_payload = payloads.get("cost") or {}
    balance_payload = payloads.get("balance") or {}
    errors = [
        str(value.get("_error"))
        for value in payloads.values()
        if isinstance(value, dict) and value.get("_error")
    ]
    amount_series = _deepseek_platform_amount_series(amount_payload)
    cost_series, currency = _deepseek_platform_cost_series(cost_payload)
    cost_by_key: dict[tuple[str, str, int], float] = {}
    for item in cost_series:
        api_key = item.get("api_key") if isinstance(item, dict) else None
        model = str(item.get("model") or "unknown")
        tracking_id = _deepseek_api_tracking_id(api_key)
        if not _deepseek_api_key_matches(config.api_key, api_key):
            continue
        for bucket in item.get("buckets") or []:
            if not isinstance(bucket, dict):
                continue
            timestamp = int(_to_float(bucket.get("time")) or 0)
            if not timestamp:
                continue
            cost_by_key[(tracking_id, model, timestamp)] = _round_number(bucket.get("cost") or 0)

    model_totals: dict[str, dict[str, Any]] = {}
    daily_totals: dict[int, dict[str, Any]] = {}
    matched_key: dict[str, Any] | None = None
    for item in amount_series:
        if not isinstance(item, dict):
            continue
        api_key = item.get("api_key")
        if not _deepseek_api_key_matches(config.api_key, api_key):
            continue
        matched_key = matched_key or _deepseek_api_summary(api_key)
        model = str(item.get("model") or "unknown")
        tracking_id = _deepseek_api_tracking_id(api_key)
        model_total = model_totals.setdefault(
            model,
            {
                "model": model,
                "request_count": 0,
                "token_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_hit_input_tokens": 0,
                "cache_miss_input_tokens": 0,
                "amount": 0,
                "estimated_cost_usd": 0,
                "pricing_basis": "deepseek_platform_cny",
            },
        )
        for bucket in item.get("buckets") or []:
            if not isinstance(bucket, dict):
                continue
            timestamp = int(_to_float(bucket.get("time")) or 0)
            if not timestamp:
                continue
            usage = bucket.get("usage") if isinstance(bucket.get("usage"), dict) else {}
            request_count = _to_float(usage.get("REQUEST")) or 0
            output_tokens = _to_float(usage.get("RESPONSE_TOKEN")) or 0
            cache_hit_tokens = _to_float(usage.get("PROMPT_CACHE_HIT_TOKEN")) or 0
            cache_miss_tokens = _to_float(usage.get("PROMPT_CACHE_MISS_TOKEN")) or 0
            input_tokens = cache_hit_tokens + cache_miss_tokens
            token_count = input_tokens + output_tokens
            cost = cost_by_key.get((tracking_id, model, timestamp), 0)
            model_total["request_count"] += request_count
            model_total["token_count"] += token_count
            model_total["input_tokens"] += input_tokens
            model_total["output_tokens"] += output_tokens
            model_total["cache_hit_input_tokens"] += cache_hit_tokens
            model_total["cache_miss_input_tokens"] += cache_miss_tokens
            model_total["amount"] += cost
            model_total["estimated_cost_usd"] += cost
            daily = daily_totals.setdefault(
                timestamp,
                {
                    "time": timestamp,
                    "request_count": 0,
                    "token_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "amount": 0,
                },
            )
            daily["request_count"] += request_count
            daily["token_count"] += token_count
            daily["input_tokens"] += input_tokens
            daily["output_tokens"] += output_tokens
            daily["amount"] += cost

    model_stats = sorted(
        [_rounded_deepseek_platform_model(item) for item in model_totals.values()],
        key=lambda item: item["amount"],
        reverse=True,
    )
    daily = [_rounded_deepseek_platform_daily(item) for _time, item in sorted(daily_totals.items())]
    balance = normalize_deepseek_balance(config, balance_payload) if isinstance(balance_payload, dict) and balance_payload else None
    request_count = _round_number(sum(item["request_count"] for item in model_stats))
    token_count = _round_number(sum(item["token_count"] for item in model_stats))
    total_cost = _round_number(sum(item["amount"] for item in model_stats))
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="offline" if errors and not amount_series and not cost_series else "degraded" if errors else "online",
        balance_currency=(balance.balance_currency if balance else currency) or currency,
        balance_total=balance.balance_total if balance else None,
        balance_granted=balance.balance_granted if balance else None,
        balance_topped_up=balance.balance_topped_up if balance else None,
        quota_used=total_cost,
        quota_remaining=balance.balance_total if balance else None,
        request_count=request_count,
        token_count=token_count,
        estimated_amount=total_cost,
        model_stats=model_stats,
        raw_summary={
            "deepseek_platform": {
                "currency": currency,
                "api_key": matched_key,
                "daily": daily,
                "pricing_basis": "deepseek_platform_cny",
            }
        },
        error=errors[0] if errors else None,
    )


def normalize_newapi(config: LlmUsageConfig, payloads: dict[str, Any]) -> LlmUsageResult:
    dashboard = _unwrap(payloads.get("dashboard"))
    token_usage = _unwrap(payloads.get("token_usage"))
    token_logs = _unwrap(payloads.get("token_logs"))
    stat = _unwrap(payloads.get("stat"))
    logs = _unwrap(payloads.get("logs"))
    channels = _unwrap(payloads.get("channels"))
    has_token_scope = "token_usage" in payloads or "token_logs" in payloads

    request_count = _coalesce_number(
        _first_number(stat, ["count", "request_count", "total_count"]),
        None if has_token_scope else _first_number(dashboard, ["count", "request_count", "total_count"]),
    )
    token_count = _coalesce_number(
        _first_number(stat, ["token", "tokens", "token_count", "total_tokens"]),
        None if has_token_scope else _first_number(dashboard, ["token", "tokens", "token_count", "total_tokens"]),
    )
    quota_used = _coalesce_number(
        _first_number(token_usage, ["total_used", "used_quota", "quota_used"]),
        _first_number(stat, ["quota", "used_quota", "quota_used", "amount"]),
        None if has_token_scope else _first_number(dashboard, ["used_quota", "quota_used", "amount"]),
    )
    rpm = _first_number(stat, ["rpm", "request_rpm"])
    tpm = _first_number(stat, ["tpm", "token_tpm"])
    success_rate = _first_number(stat, ["success_rate"])
    avg_latency = _first_number(stat, ["avg_latency", "avg_latency_seconds", "latency"])
    model_stats = (
        _model_stats_from(token_logs)
        or _model_stats_from(logs)
        or _model_stats_from(stat)
        or _model_stats_from(dashboard)
    )
    request_count = _coalesce_number(request_count, _sum_model_stats(model_stats, "request_count"))
    token_count = _coalesce_number(token_count, _sum_model_stats(model_stats, "token_count"))
    quota_used = _coalesce_number(quota_used, _sum_model_stats(model_stats, "amount"))
    quota_remaining = _coalesce_number(
        _first_number(token_usage, ["total_available", "remain_quota", "remaining_quota"]),
        None if has_token_scope else _first_number(dashboard, ["quota", "remaining_quota"]),
    )
    dashboard_quota_used = _first_number(dashboard, ["used_quota"])
    quota_total = _coalesce_number(
        _first_number(token_usage, ["total_granted", "quota_total", "total_quota"]),
        None if has_token_scope else _first_number(dashboard, ["total_quota", "quota_total"]),
    )
    account_quota_remaining = _first_number(dashboard, ["quota", "remaining_quota"])
    balance_total = _coalesce_number(_channel_balance_total(channels), _newapi_quota_usd(account_quota_remaining))
    balance_currency = "USD" if balance_total is not None else None
    if quota_total is None and quota_remaining is not None and dashboard_quota_used is not None:
        quota_total = quota_remaining + dashboard_quota_used
    if quota_remaining is None and quota_total is not None and quota_used is not None:
        quota_remaining = quota_total - quota_used

    estimated_cost = estimate_snapshot_cost_usd(raw_quota=quota_used)
    errors = [
        str(value.get("_error"))
        for value in payloads.values()
        if isinstance(value, dict) and value.get("_error")
    ]
    core_names = [name for name in ("token_usage", "token_logs", "dashboard", "stat", "logs") if name in payloads]
    all_core_failed = bool(core_names) and all(
        isinstance(payloads.get(name), dict) and payloads.get(name, {}).get("_error") for name in core_names
    )
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="offline" if all_core_failed else "degraded" if errors else "online",
        balance_currency=balance_currency,
        balance_total=balance_total,
        quota_total=quota_total,
        quota_used=quota_used,
        quota_remaining=quota_remaining,
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
            "token_usage": _safe_summary(token_usage),
            "token_logs": _safe_summary(token_logs),
            "stat": _safe_summary(stat),
            "logs": _safe_summary(logs),
            "channels": _safe_summary(channels),
        },
        error=errors[0] if errors else None,
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
    with _ENV_UPDATE_LOCK:
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
    with _ENV_UPDATE_LOCK:
        for value in updates.values():
            if any(character in str(value) for character in ("\r", "\n", "\0")):
                raise ValueError("environment values must not contain line breaks or NUL bytes")
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


def _provider_shared_values(env: dict[str, str], source_ids: list[str], provider_id: str) -> dict[str, Any] | None:
    for source_id in source_ids:
        prefix = f"PULSEBOARD_LLM_{_env_key(source_id)}_"
        if (env.get(prefix + "PROVIDER_ID") or source_id).strip() != provider_id:
            continue
        source_type = (env.get(prefix + "TYPE") or "").strip()
        if not source_type:
            continue
        return {
            "source_type": source_type,
            "provider_name": (env.get(prefix + "PROVIDER_NAME") or provider_id).strip(),
            "base_url": (env.get(prefix + "BASE_URL") or "").strip(),
            "has_base_url": bool((env.get(prefix + "BASE_URL") or "").strip()),
            "access_token": (env.get(prefix + "ACCESS_TOKEN") or "").strip(),
            "has_access_token": bool((env.get(prefix + "ACCESS_TOKEN") or "").strip()),
            "user_id": (env.get(prefix + "USER_ID") or "1").strip() or "1",
            "has_user_id": prefix + "USER_ID" in env,
            "request_mode": (
                env.get(prefix + "REQUEST_MODE")
                or ("chat_completions" if source_type in {"deepseek_balance", "deepseek_platform"} else "responses")
            ).strip(),
            "has_request_mode": prefix + "REQUEST_MODE" in env,
            "test_model": (
                env.get(prefix + "TEST_MODEL")
                if prefix + "TEST_MODEL" in env
                else ("deepseek-chat" if source_type in {"deepseek_balance", "deepseek_platform"} else "")
            ).strip(),
            "has_test_model": prefix + "TEST_MODEL" in env,
        }
    return None


def _env_key(value: str) -> str:
    return value.upper().replace("-", "_")


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _newapi_quota_usd(value: Any) -> float | None:
    quota = _to_float(value)
    if quota is None:
        return None
    return round(quota / NEWAPI_QUOTA_PER_USD, 6)


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


def _coalesce_number(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _number_from_keys(value: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        number = _to_float(value.get(key))
        if number is not None:
            return number
    return None


def _sum_model_stats(model_stats: list[dict[str, Any]], field: str) -> float | None:
    total = 0.0
    seen = False
    for item in model_stats:
        number = _to_float(item.get(field))
        if number is None:
            continue
        total += number
        seen = True
    return total if seen else None


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
        grouped_item["request_count"] += _coalesce_number(
            _number_from_keys(item, ["count", "request_count", "total_count"]),
            1,
        )
        input_tokens = _number_from_keys(item, ["input_tokens", "prompt_tokens"])
        output_tokens = _number_from_keys(item, ["output_tokens", "completion_tokens"])
        token_count = _number_from_keys(item, ["token", "tokens", "token_count", "total_tokens", "total_token"])
        if token_count is None and (input_tokens is not None or output_tokens is not None):
            token_count = (input_tokens or 0) + (output_tokens or 0)
        grouped_item["token_count"] += token_count or 0
        grouped_item["input_tokens"] += input_tokens or 0
        grouped_item["output_tokens"] += output_tokens or 0
        grouped_item["amount"] += _number_from_keys(item, ["amount", "quota", "used_quota", "cost", "price"]) or 0
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
        for key in ("items", "logs", "data", "rows", "records", "list"):
            child = value.get(key)
            if isinstance(child, list):
                rows.extend(_model_rows(child))
            elif isinstance(child, dict):
                rows.extend(_model_rows(child))
        if any(key in value for key in ("model", "model_name")):
            rows.append(value)
        return rows
    return []


def _deepseek_platform_amount_series(payload: Any) -> list[dict[str, Any]]:
    biz_data = _deepseek_platform_biz_data(payload)
    series = biz_data.get("series") if isinstance(biz_data, dict) else None
    return series if isinstance(series, list) else []


def _deepseek_platform_cost_series(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    biz_data = _deepseek_platform_biz_data(payload)
    if not isinstance(biz_data, dict):
        return [], None
    series = biz_data.get("series")
    if isinstance(series, list):
        return series, None
    data = biz_data.get("data")
    if not isinstance(data, list):
        return [], None
    result: list[dict[str, Any]] = []
    currency = None
    for item in data:
        if not isinstance(item, dict):
            continue
        currency = currency or item.get("currency")
        child_series = item.get("series")
        if isinstance(child_series, list):
            result.extend(child for child in child_series if isinstance(child, dict))
    return result, str(currency) if currency else None


def _deepseek_platform_biz_data(payload: Any) -> dict[str, Any]:
    value = payload
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    if isinstance(value, dict) and "biz_data" in value:
        value = value["biz_data"]
    return value if isinstance(value, dict) else {}


def _deepseek_api_tracking_id(api_key: Any) -> str:
    if isinstance(api_key, dict):
        return str(api_key.get("tracking_id") or api_key.get("sensitive_id") or api_key.get("name") or "unknown")
    return "unknown"


def _deepseek_api_key_matches(config_key: str | None, api_key: Any) -> bool:
    if not config_key or not isinstance(api_key, dict):
        return True
    sensitive_id = str(api_key.get("sensitive_id") or "")
    if not sensitive_id:
        return True
    parts = [part for part in sensitive_id.split("*") if part]
    return all(part in config_key for part in parts)


def _deepseek_api_summary(api_key: Any) -> dict[str, Any] | None:
    if not isinstance(api_key, dict):
        return None
    return {
        "tracking_id": api_key.get("tracking_id"),
        "name": api_key.get("name"),
        "sensitive_id": api_key.get("sensitive_id"),
        "valid": api_key.get("valid"),
    }


def _rounded_deepseek_platform_model(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "request_count": _round_number(item["request_count"]),
        "token_count": _round_number(item["token_count"]),
        "input_tokens": _round_number(item["input_tokens"]),
        "output_tokens": _round_number(item["output_tokens"]),
        "cache_hit_input_tokens": _round_number(item["cache_hit_input_tokens"]),
        "cache_miss_input_tokens": _round_number(item["cache_miss_input_tokens"]),
        "amount": _round_number(item["amount"]),
        "estimated_cost_usd": _round_number(item["estimated_cost_usd"]),
    }


def _rounded_deepseek_platform_daily(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "request_count": _round_number(item["request_count"]),
        "token_count": _round_number(item["token_count"]),
        "input_tokens": _round_number(item["input_tokens"]),
        "output_tokens": _round_number(item["output_tokens"]),
        "amount": _round_number(item["amount"]),
    }


def _round_number(value: Any) -> float:
    number = _to_float(value) or 0
    return round(number, 6)


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
