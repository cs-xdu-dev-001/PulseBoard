from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import quote_plus

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
    normalize_deepseek_platform,
    normalize_newapi,
)
from app.models import LlmUsageSnapshot, LlmUsageSource


NEWAPI_ENDPOINTS = {
    "dashboard": ("/api/user/self",),
    "token_usage": ("/api/usage/token/",),
    "token_logs": ("/api/log/token",),
    "token_search": "/api/token/search?p=1&page_size=1&token={api_key}",
    "self_stat_by_token": "/api/log/self/stat?type=2&token_name={token_name}&{time_query}",
    "self_logs_by_token": "/api/log/self?p={page}&page_size={page_size}&type=2&token_name={token_name}&{time_query}",
    "stat": ("/api/log/self/stat?type=2&{time_query}", "/api/log/stat?type=2&{time_query}"),
    "logs": (
        "/api/log/self?p={page}&page_size={page_size}&type=2&{time_query}",
        "/api/log/?p={page}&page_size={page_size}&type=2&{time_query}",
    ),
}
NEWAPI_LOG_PAGE_SIZE = 1000
NEWAPI_LOG_MAX_PAGES = 20
DEEPSEEK_PLATFORM_BASE_URL = "https://platform.deepseek.com"
DEEPSEEK_PLATFORM_ENDPOINTS = {
    "amount": "/api/v0/usage/by_api_key/amount?start={start}&end={end}&tz=0",
    "cost": "/api/v0/usage/by_api_key/cost?start={start}&end={end}&tz=0",
}


def collect_llm_usage_once(db: Session, settings: Settings) -> None:
    for config in load_llm_usage_configs(settings):
        if config.source_type == "openai_gateway":
            continue
        result = collect_source(config)
        persist_result(db, result, datetime.now(timezone.utc))
    db.commit()


def collect_source(config: LlmUsageConfig) -> LlmUsageResult:
    try:
        if config.source_type == "deepseek_balance":
            return collect_deepseek(config)
        if config.source_type == "deepseek_platform":
            return collect_deepseek_platform(config)
        if config.source_type == "newapi_admin":
            return collect_newapi(config)
        if config.source_type == "openai_gateway":
            return collect_openai_gateway_config(config)
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


def collect_deepseek_platform(config: LlmUsageConfig) -> LlmUsageResult:
    if not config.access_token:
        return error_result(config, "DeepSeek platform token is not configured")
    start, end = _deepseek_platform_range()
    headers = _deepseek_platform_headers(config.access_token)
    payloads = {}
    with httpx.Client(timeout=20) as client:
        for name, template in DEEPSEEK_PLATFORM_ENDPOINTS.items():
            payloads[name] = _collect_deepseek_platform_payload(
                client,
                f"{DEEPSEEK_PLATFORM_BASE_URL}{template.format(start=start, end=end)}",
                headers,
            )
        if config.api_key:
            payloads["balance"] = _collect_deepseek_platform_payload(
                client,
                deepseek_balance_url(),
                {"Authorization": f"Bearer {config.api_key}"},
            )
    return normalize_deepseek_platform(config, payloads)


def collect_openai_gateway_config(config: LlmUsageConfig) -> LlmUsageResult:
    missing = []
    if not config.base_url:
        missing.append("上游Base URL")
    if not config.api_key:
        missing.append("上游模型API Key")
    if not config.access_token:
        missing.append("网关访问令牌")
    if missing:
        return error_result(config, f"监控网关缺少配置：{'、'.join(missing)}")
    return LlmUsageResult(
        source_id=config.source_id,
        display_name=config.display_name,
        source_type=config.source_type,
        status="online",
        raw_summary={
            "gateway": {
                "usage_mode": "proxy_only",
                "message": "网关用量由真实模型请求写入，不执行定时拉取",
            }
        },
    )


def collect_newapi(config: LlmUsageConfig) -> LlmUsageResult:
    if not config.base_url:
        return error_result(config, "New API base URL is not configured")
    if not config.api_key and not config.access_token:
        return error_result(config, "New API API key or access token is not configured")
    payloads = {}
    time_query = _today_timestamp_query()
    with httpx.Client(timeout=20) as client:
        if config.access_token:
            account_headers = {
                "Authorization": f"Bearer {config.access_token}",
                "New-Api-User": config.user_id,
            }
            payloads["dashboard"] = _collect_newapi_payload(
                client, config.base_url, NEWAPI_ENDPOINTS["dashboard"], account_headers
            )
        if config.api_key:
            if config.access_token:
                search_path = NEWAPI_ENDPOINTS["token_search"].format(api_key=quote_plus(config.api_key))
                token_search = _collect_newapi_payload(client, config.base_url, (search_path,), account_headers)
                payloads["token_usage"] = _token_usage_from_search(token_search)
                token_name = _token_name_from_search(token_search)
                if token_name:
                    token_name_param = quote_plus(token_name)
                    payloads["stat"] = _collect_newapi_payload(
                        client,
                        config.base_url,
                        (NEWAPI_ENDPOINTS["self_stat_by_token"].format(token_name=token_name_param, time_query=time_query),),
                        account_headers,
                    )
                    payloads["logs"] = _collect_newapi_paginated_payload(
                        client,
                        config.base_url,
                        (
                            NEWAPI_ENDPOINTS["self_logs_by_token"].format(
                                token_name=token_name_param,
                                time_query=time_query,
                                page="{page}",
                                page_size="{page_size}",
                            ),
                        ),
                        account_headers,
                    )
            else:
                key_headers = {"Authorization": f"Bearer {config.api_key}"}
                payloads["token_usage"] = _collect_newapi_payload(
                    client, config.base_url, NEWAPI_ENDPOINTS["token_usage"], key_headers
                )
                payloads["token_logs"] = _collect_newapi_payload(
                    client, config.base_url, NEWAPI_ENDPOINTS["token_logs"], key_headers
                )
        elif config.access_token and not _is_auth_failure(payloads.get("dashboard", {})):
            for name in ("stat", "logs"):
                if name == "logs":
                    payloads[name] = _collect_newapi_paginated_payload(
                        client,
                        config.base_url,
                        tuple(
                            path.format(time_query=time_query, page="{page}", page_size="{page_size}")
                            for path in NEWAPI_ENDPOINTS[name]
                        ),
                        account_headers,
                    )
                else:
                    payloads[name] = _collect_newapi_payload(
                        client,
                        config.base_url,
                        tuple(path.format(time_query=time_query) for path in NEWAPI_ENDPOINTS[name]),
                        account_headers,
                    )
    return normalize_newapi(config, payloads)


def _today_timestamp_query(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end = current.replace(hour=23, minute=59, second=59, microsecond=0)
    return f"start_timestamp={int(start.timestamp())}&end_timestamp={int(end.timestamp())}"


def _deepseek_platform_range(now: datetime | None = None) -> tuple[int, int]:
    current = now or datetime.now(timezone.utc)
    end = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=7)
    return int(start.timestamp()), int(end.timestamp())


def _deepseek_platform_headers(access_token: str) -> dict[str, str]:
    token = access_token.strip()
    if not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return {
        "Authorization": token,
        "Accept": "*/*",
        "Referer": "https://platform.deepseek.com/usage",
        "x-client-bundle-id": "com.deepseek.chat",
        "x-client-locale": "zh_CN",
        "x-client-platform": "web",
        "x-client-timezone-offset": "28800",
        "x-client-version": "1.0.0",
    }


def check_model_connection(config: LlmUsageConfig) -> dict[str, str | None]:
    if not config.api_key:
        return _model_connection_result(config, "not_configured", "模型API Key未配置")
    if not config.test_model:
        return _model_connection_result(config, "not_configured", "测试模型未配置")

    base_url = config.base_url
    if config.source_type in {"deepseek_balance", "deepseek_platform"}:
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
            if isinstance(payload, dict) and payload.get("code") is False:
                raise RuntimeError(str(payload.get("message") or "New API request failed"))
            return payload
        except Exception as exc:
            last_error = _sanitize_newapi_error(str(exc), headers)
    return {"_error": last_error or "New API request failed"}


def _collect_newapi_paginated_payload(
    client: httpx.Client,
    base_url: str,
    paths: tuple[str, ...],
    headers: dict[str, str],
) -> dict:
    last_error = None
    for path_template in paths:
        try:
            return _collect_newapi_paginated_path(client, base_url, path_template, headers)
        except Exception as exc:
            last_error = _sanitize_newapi_error(str(exc), headers)
    return {"_error": last_error or "New API request failed"}


def _collect_newapi_paginated_path(
    client: httpx.Client,
    base_url: str,
    path_template: str,
    headers: dict[str, str],
) -> dict:
    first_payload: dict | None = None
    combined_items: list[dict] = []
    total = None
    collected_pages = 0
    for page in range(1, NEWAPI_LOG_MAX_PAGES + 1):
        path = path_template.format(page=page, page_size=NEWAPI_LOG_PAGE_SIZE)
        response = client.get(newapi_url(base_url, path), headers=headers)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(str(payload.get("message") or "New API request failed"))
        if isinstance(payload, dict) and payload.get("code") is False:
            raise RuntimeError(str(payload.get("message") or "New API request failed"))
        if first_payload is None:
            first_payload = payload if isinstance(payload, dict) else {"data": payload}
        data = _newapi_data(payload)
        if total is None:
            total = _number(data.get("total")) if isinstance(data, dict) else None
        items = _newapi_items(data)
        combined_items.extend(items)
        collected_pages = page
        if not items:
            break
        if total is not None and len(combined_items) >= total:
            break
        if len(items) < NEWAPI_LOG_PAGE_SIZE:
            break

    if first_payload is None:
        return {"success": True, "data": {"items": []}}
    result = dict(first_payload)
    data = _newapi_data(result)
    if isinstance(data, dict):
        next_data = dict(data)
        next_data["items"] = combined_items
        next_data["page"] = 1
        next_data["page_size"] = NEWAPI_LOG_PAGE_SIZE
        next_data["pages_collected"] = collected_pages
        if total is not None:
            next_data["total"] = total
        if total is not None and len(combined_items) < total:
            next_data["truncated"] = True
        result["data"] = next_data
    else:
        result["data"] = combined_items
    return result


def _newapi_data(payload) -> dict | list:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, (dict, list)):
            return data
    return payload if isinstance(payload, list) else {}


def _newapi_items(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "logs", "rows", "records", "list", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _collect_deepseek_platform_payload(client: httpx.Client, url: str, headers: dict[str, str]) -> dict:
    try:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            code = payload.get("code")
            if code not in (None, 0, True):
                raise RuntimeError(str(payload.get("msg") or payload.get("message") or "DeepSeek platform request failed"))
            data = payload.get("data")
            if isinstance(data, dict) and data.get("biz_code") not in (None, 0, True):
                raise RuntimeError(str(data.get("biz_msg") or "DeepSeek platform request failed"))
        return payload
    except Exception as exc:
        return {"_error": _sanitize_newapi_error(str(exc), headers)}


def _sanitize_newapi_error(message: str, headers: dict[str, str]) -> str:
    sanitized = re.sub(r"([?&]token=)[^&'\"]+", r"\1[已脱敏]", message)
    authorization = headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        secret = authorization[7:].strip()
        if secret:
            sanitized = sanitized.replace(secret, "[已脱敏]")
            sanitized = sanitized.replace(quote_plus(secret), "[已脱敏]")
    return sanitized


def _is_auth_failure(payload: dict) -> bool:
    message = str(payload.get("_error") or payload.get("message") or "").lower()
    return "unauthorized" in message or "invalid access token" in message


def _token_usage_from_search(payload: dict) -> dict:
    token = _token_row_from_search(payload)
    if not token:
        if isinstance(payload, dict) and payload.get("_error"):
            return {"_error": payload["_error"]}
        return {"_error": "New API token search returned no matching key"}
    used = _number(token.get("used_quota"))
    remaining = _number(token.get("remain_quota"))
    return {
        "code": True,
        "message": "ok",
        "data": {
            "object": "token_usage",
            "name": token.get("name"),
            "total_granted": (used or 0) + (remaining or 0) if used is not None or remaining is not None else None,
            "total_used": used,
            "total_available": remaining,
            "unlimited_quota": token.get("unlimited_quota"),
            "expires_at": token.get("expired_time"),
        },
    }


def _token_name_from_search(payload: dict) -> str | None:
    token = _token_row_from_search(payload)
    if not token:
        return None
    name = token.get("name")
    return str(name) if name else None


def _token_row_from_search(payload: dict) -> dict | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return None


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
