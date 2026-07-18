from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.llm_usage import (
    LlmUsageConfig,
    LlmUsageResult,
    deepseek_balance_url,
    error_result,
    load_llm_usage_configs,
    newapi_url,
    normalize_deepseek_balance,
    normalize_newapi,
)
from app.models import LlmUsageSnapshot, LlmUsageSource


NEWAPI_ENDPOINTS = {
    "dashboard": ("/api/user/self",),
    "stat": ("/api/log/self/stat", "/api/log/stat"),
    "logs": ("/api/log/self?p=1&page_size=100&type=2", "/api/log/?p=1&page_size=100&type=2"),
}


def collect_llm_usage_once(db: Session, settings: Settings) -> None:
    for config in load_llm_usage_configs(settings):
        result = collect_source(config)
        persist_result(db, result, datetime.now(timezone.utc))
    db.commit()


def collect_source(config: LlmUsageConfig) -> LlmUsageResult:
    try:
        if config.source_type == "deepseek_balance":
            return collect_deepseek(config)
        if config.source_type == "newapi_admin":
            return collect_newapi(config)
        return error_result(config, f"Unsupported LLM usage source type: {config.source_type}")
    except Exception as exc:
        return error_result(config, str(exc))


def collect_deepseek(config: LlmUsageConfig) -> LlmUsageResult:
    if not config.api_key:
        return error_result(config, "DeepSeek API key is not configured")
    response = httpx.get(
        deepseek_balance_url(),
        headers={"Authorization": f"Bearer {config.api_key}"},
        timeout=15,
    )
    response.raise_for_status()
    return normalize_deepseek_balance(config, response.json())


def collect_newapi(config: LlmUsageConfig) -> LlmUsageResult:
    if not config.base_url:
        return error_result(config, "New API base URL is not configured")
    if not config.access_token:
        return error_result(config, "New API access token is not configured")
    headers = {
        "Authorization": f"Bearer {config.access_token}",
        "New-Api-User": config.user_id,
    }
    payloads = {}
    with httpx.Client(timeout=20) as client:
        payloads["dashboard"] = _collect_newapi_payload(client, config.base_url, NEWAPI_ENDPOINTS["dashboard"], headers)
        if _is_auth_failure(payloads["dashboard"]):
            return normalize_newapi(config, payloads)
        for name in ("stat", "logs"):
            payloads[name] = _collect_newapi_payload(client, config.base_url, NEWAPI_ENDPOINTS[name], headers)
    return normalize_newapi(config, payloads)


def check_model_connection(config: LlmUsageConfig) -> dict[str, str | None]:
    if not config.api_key:
        return _model_connection_result(config, "not_configured", "模型API Key未配置")
    if not config.test_model:
        return _model_connection_result(config, "not_configured", "测试模型未配置")

    base_url = config.base_url
    if config.source_type == "deepseek_balance":
        base_url = base_url or "https://api.deepseek.com"
    if not base_url:
        return _model_connection_result(config, "not_configured", "模型Base URL未配置")

    if config.request_mode == "responses":
        resource = "responses"
        payload = {
            "model": config.test_model,
            "stream": True,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Reply with OK only."}],
                }
            ],
        }
    elif config.request_mode == "chat_completions":
        resource = "chat/completions"
        payload = {
            "model": config.test_model,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
        }
    else:
        return _model_connection_result(config, "not_configured", "模型请求方式无效")

    try:
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        if config.request_mode == "responses":
            headers["Accept"] = "text/event-stream"
        response = httpx.post(
            _model_api_url(base_url, resource),
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return _model_connection_result(config, "offline", _http_status_error_message(exc.response))
    except Exception as exc:
        return _model_connection_result(config, "offline", str(exc))
    return _model_connection_result(config, "online", None)


def _model_api_url(base_url: str, resource: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{resource}"
    return f"{normalized}/v1/{resource}"


def _model_connection_result(config: LlmUsageConfig, status: str, error: str | None) -> dict[str, str | None]:
    return {
        "status": status,
        "error": error,
        "request_mode": config.request_mode,
        "test_model": config.test_model,
    }


def _http_status_error_message(response: httpx.Response) -> str:
    detail = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or error.get("detail") or error.get("code")
        elif error:
            detail = error
        detail = detail or payload.get("message") or payload.get("detail")
    if not detail:
        detail = response.text.strip()
    prefix = f"HTTP {response.status_code}"
    return f"{prefix}: {str(detail)[:1000]}" if detail else prefix


def _collect_newapi_payload(client: httpx.Client, base_url: str, paths: tuple[str, ...], headers: dict[str, str]) -> dict:
    last_error = None
    for path in paths:
        try:
            response = client.get(newapi_url(base_url, path), headers=headers)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("success") is False:
                raise RuntimeError(str(payload.get("message") or "New API request failed"))
            return payload
        except Exception as exc:
            last_error = str(exc)
    return {"_error": last_error or "New API request failed"}


def _is_auth_failure(payload: dict) -> bool:
    message = str(payload.get("_error") or payload.get("message") or "").lower()
    return "unauthorized" in message or "invalid access token" in message


def get_or_create_source(db: Session, result: LlmUsageResult) -> LlmUsageSource:
    source = db.query(LlmUsageSource).filter(LlmUsageSource.source_id == result.source_id).one_or_none()
    if source is None:
        source = LlmUsageSource(
            source_id=result.source_id,
            display_name=result.display_name,
            source_type=result.source_type,
        )
        db.add(source)
        db.flush()
    return source


def persist_result(db: Session, result: LlmUsageResult, collected_at: datetime) -> None:
    source = get_or_create_source(db, result)
    source.display_name = result.display_name
    source.source_type = result.source_type
    source.status = result.status
    source.last_checked_at = collected_at
    source.last_error = result.error
    source.balance_currency = result.balance_currency
    source.balance_total = result.balance_total
    source.balance_granted = result.balance_granted
    source.balance_topped_up = result.balance_topped_up
    source.quota_total = result.quota_total
    source.quota_used = result.quota_used
    source.quota_remaining = result.quota_remaining
    db.add(
        LlmUsageSnapshot(
            source_id=source.id,
            collected_at=collected_at,
            range_key="latest",
            request_count=result.request_count,
            token_count=result.token_count,
            quota_used=result.quota_used,
            estimated_amount=result.estimated_amount,
            rpm=result.rpm,
            tpm=result.tpm,
            success_rate=result.success_rate,
            avg_latency_seconds=result.avg_latency_seconds,
            model_stats=result.model_stats or [],
            raw_summary=result.raw_summary or {},
        )
    )
