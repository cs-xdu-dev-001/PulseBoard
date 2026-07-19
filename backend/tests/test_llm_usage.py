from threading import Barrier, BrokenBarrierError, Thread

import httpx
import pytest

from app import llm_usage
from app.config import Settings
from app.llm_usage import (
    LlmUsageConfig,
    delete_llm_provider_config,
    delete_llm_usage_config,
    list_llm_usage_config,
    load_llm_usage_configs,
    normalize_deepseek_balance,
    normalize_newapi,
    save_llm_usage_config,
    update_llm_provider_config,
)
from app.llm_usage_collector import check_model_connection, collect_newapi
from app.llm_pricing import estimate_model_cost_usd


def test_load_llm_usage_configs_supports_custom_source_ids(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic Gateway",
                "PULSEBOARD_LLM_ACADEMIC_BASE_URL=https://new-api.example.com",
                "PULSEBOARD_LLM_ACADEMIC_REQUEST_MODE=responses",
                "PULSEBOARD_LLM_ACADEMIC_TEST_MODEL=gpt-5.4",
                "PULSEBOARD_LLM_ACADEMIC_API_KEY=model-secret",
                "PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = Settings(llm_usage_sources="academic")
    configs = load_llm_usage_configs(settings, env_path=env_path)

    assert configs[0].source_id == "academic"
    assert configs[0].display_name == "Academic Gateway"
    assert configs[0].base_url == "https://new-api.example.com"
    assert configs[0].request_mode == "responses"
    assert configs[0].test_model == "gpt-5.4"
    assert configs[0].api_key == "model-secret"
    assert configs[0].access_token == "secret"


def test_normalize_deepseek_balance_extracts_balance():
    result = normalize_deepseek_balance(
        LlmUsageConfig("deepseek", "DeepSeek", "deepseek_balance", api_key="secret"),
        {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "12.34",
                    "granted_balance": "2.00",
                    "topped_up_balance": "10.34",
                }
            ],
        },
    )

    assert result.status == "online"
    assert result.balance_currency == "CNY"
    assert result.balance_total == 12.34
    assert result.balance_granted == 2.0
    assert result.balance_topped_up == 10.34


def test_normalize_newapi_tolerates_partial_payloads():
    result = normalize_newapi(
        LlmUsageConfig("academic", "Academic", "newapi_admin", base_url="https://example", access_token="secret"),
        {
            "stat": {"data": {"request_count": 10, "token_count": 2000, "quota_used": 1.5, "rpm": 0.2}},
            "logs": {"data": [{"model": "deepseek-chat", "count": 7, "tokens": 1000, "amount": 0.9}]},
            "channels": {"_error": "boom"},
        },
    )

    assert result.status == "degraded"
    assert result.request_count == 10
    assert result.token_count == 2000
    assert result.quota_used == 1.5
    assert result.model_stats[0]["model"] == "deepseek-chat"


def test_normalize_newapi_derives_usage_from_user_log_items():
    result = normalize_newapi(
        LlmUsageConfig("academic-key-3", "Blog", "newapi_admin", base_url="https://example", access_token="secret"),
        {
            "dashboard": {"success": True, "data": {"quota": 24_430_000, "used_quota": 20_668}},
            "stat": {"success": True, "data": {"quota": 20_668, "rpm": 1, "tpm": 1883}},
            "logs": {
                "success": True,
                "data": {
                    "page": 1,
                    "page_size": 100,
                    "total": 1,
                    "items": [
                        {
                            "model_name": "gpt-5.6-sol",
                            "prompt_tokens": 971,
                            "completion_tokens": 912,
                            "quota": 20_668,
                        }
                    ],
                },
            },
        },
    )

    assert result.status == "online"
    assert result.request_count == 1
    assert result.token_count == 1883
    assert result.quota_total == 24_450_668
    assert result.quota_used == 20_668
    assert result.quota_remaining == 24_430_000
    assert result.estimated_amount == 0.041336
    assert result.model_stats[0]["model"] == "gpt-5.6-sol"
    assert result.model_stats[0]["token_count"] == 1883
    assert result.model_stats[0]["estimated_cost_usd"] == 0.041336


def test_collect_newapi_uses_user_scoped_log_endpoints(monkeypatch):
    requested_urls = []

    class FakeResponse:
        def __init__(self, url):
            self.url = url

        def raise_for_status(self):
            return None

        def json(self):
            if "/api/user/self" in self.url:
                return {"success": True, "data": {"quota": 24_430_000, "used_quota": 20_668}}
            if "/api/log/self/stat" in self.url:
                return {"success": True, "data": {"quota": 20_668, "rpm": 1, "tpm": 1883}}
            if "/api/log/self" in self.url:
                return {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "model_name": "gpt-5.6-sol",
                                "prompt_tokens": 971,
                                "completion_tokens": 912,
                                "quota": 20_668,
                            }
                        ]
                    },
                }
            return {"success": True, "data": []}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            requested_urls.append(url)
            return FakeResponse(url)

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)

    result = collect_newapi(
        LlmUsageConfig("academic-key-3", "Blog", "newapi_admin", base_url="https://example", access_token="secret")
    )

    assert any("/api/log/self/stat" in url for url in requested_urls)
    assert any("/api/log/self?" in url for url in requested_urls)
    assert not any("/api/log/stat" in url for url in requested_urls)
    assert result.request_count == 1
    assert result.token_count == 1883
    assert result.estimated_amount == 0.041336


def test_collect_newapi_uses_user_token_search_when_access_token_is_configured(monkeypatch):
    requested = []

    class FakeResponse:
        def __init__(self, url):
            self.url = url

        def raise_for_status(self):
            return None

        def json(self):
            if "/api/user/self" in self.url:
                return {"success": True, "data": {"quota": 24_430_000, "used_quota": 20_668}}
            if "/api/token/search" in self.url:
                return {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "name": "codex-key",
                                "used_quota": 400_000,
                                "remain_quota": 1_600_000,
                                "unlimited_quota": False,
                            }
                        ]
                    },
                }
            if "/api/log/self/stat" in self.url:
                return {
                    "success": True,
                    "data": {
                        "quota": 400_000,
                        "rpm": 2,
                        "tpm": 250,
                    },
                }
            if "/api/log/self" in self.url:
                return {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "model_name": "gpt-5.6-sol",
                                "prompt_tokens": 100,
                                "completion_tokens": 50,
                                "quota": 4000,
                            },
                            {
                                "model_name": "deepseek-chat",
                                "prompt_tokens": 80,
                                "completion_tokens": 20,
                                "quota": 1000,
                            },
                        ],
                    },
                }
            return {"success": True, "data": []}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            requested.append((url, dict(headers)))
            return FakeResponse(url)

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)

    result = collect_newapi(
        LlmUsageConfig(
            "academic-main",
            "Codex",
            "newapi_admin",
            base_url="https://example",
            api_key="sk-token-key",
            access_token="account-token",
        )
    )

    search_call = next(item for item in requested if "/api/token/search" in item[0])
    stat_call = next(item for item in requested if "/api/log/self/stat" in item[0])
    log_call = next(item for item in requested if "/api/log/self" in item[0] and "/stat" not in item[0])

    assert "token=sk-token-key" in search_call[0]
    assert "token_name=codex-key" in stat_call[0]
    assert "token_name=codex-key" in log_call[0]
    assert search_call[1]["Authorization"] == "Bearer account-token"
    assert log_call[1]["Authorization"] == "Bearer account-token"
    assert not any("/api/usage/token" in url for url, _headers in requested)
    assert not any("/api/log/token" in url for url, _headers in requested)
    assert result.status == "online"
    assert result.balance_currency == "USD"
    assert result.balance_total == 48.86
    assert result.quota_total == 2_000_000
    assert result.quota_used == 400_000
    assert result.quota_remaining == 1_600_000
    assert result.request_count == 2
    assert result.token_count == 250
    assert [item["model"] for item in result.model_stats] == ["gpt-5.6-sol", "deepseek-chat"]


def test_collect_newapi_key_usage_differs_per_api_key(monkeypatch):
    token_payloads = {
        "sk-main": {"name": "main", "used_quota": 400_000, "remain_quota": 1_600_000},
        "sk-backup": {"name": "backup", "used_quota": 50_000, "remain_quota": 950_000},
    }

    class FakeResponse:
        def __init__(self, url, headers):
            self.url = url
            self.headers = headers

        def raise_for_status(self):
            return None

        def json(self):
            if "/api/user/self" in self.url:
                return {"success": True, "data": {"quota": 24_430_000, "used_quota": 20_668}}
            if "/api/token/search" in self.url:
                api_key = "sk-main" if "sk-main" in self.url else "sk-backup"
                return {"success": True, "data": {"items": [token_payloads[api_key]]}}
            if "/api/log/self/stat" in self.url:
                token_name = "main" if "token_name=main" in self.url else "backup"
                payload = next(item for item in token_payloads.values() if item["name"] == token_name)
                return {"success": True, "data": {"quota": payload["used_quota"]}}
            if "/api/log/self" in self.url:
                token_name = "main" if "token_name=main" in self.url else "backup"
                payload = next(item for item in token_payloads.values() if item["name"] == token_name)
                return {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "model_name": "gpt-5.6-sol",
                                "prompt_tokens": payload["used_quota"],
                                "completion_tokens": 0,
                                "quota": payload["used_quota"],
                            }
                        ]
                    },
                }
            return {"success": True, "data": []}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            return FakeResponse(url, headers)

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)
    shared = {"base_url": "https://example", "access_token": "account-token"}

    main = collect_newapi(LlmUsageConfig("academic-main", "Main", "newapi_admin", api_key="sk-main", **shared))
    backup = collect_newapi(LlmUsageConfig("academic-backup", "Backup", "newapi_admin", api_key="sk-backup", **shared))

    assert main.balance_total == backup.balance_total == 48.86
    assert main.quota_remaining == 1_600_000
    assert backup.quota_remaining == 950_000
    assert main.quota_used != backup.quota_used


def test_normalize_newapi_token_scope_error_does_not_reuse_account_usage():
    result = normalize_newapi(
        LlmUsageConfig("academic-main", "Main", "newapi_admin", base_url="https://example", api_key="sk-main"),
        {
            "dashboard": {"success": True, "data": {"quota": 24_430_000, "used_quota": 20_668}},
            "token_usage": {"_error": "HTTP 429 Too Many Requests"},
        },
    )

    assert result.status == "degraded"
    assert result.balance_total == 48.86
    assert result.quota_remaining is None
    assert result.quota_used is None


def test_collect_newapi_token_search_error_redacts_query_secret(monkeypatch):
    class FakeResponse:
        def __init__(self, url):
            self.url = url

        def raise_for_status(self):
            if "/api/user/self" in self.url:
                return None
            raise httpx.HTTPStatusError(
                f"Client error '429 Too Many Requests' for url '{self.url}'",
                request=httpx.Request("GET", self.url),
                response=httpx.Response(429, request=httpx.Request("GET", self.url)),
            )

        def json(self):
            if "/api/user/self" in self.url:
                return {"success": True, "data": {"quota": 24_430_000, "used_quota": 20_668}}
            return {}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            return FakeResponse(url)

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)

    result = collect_newapi(
        LlmUsageConfig(
            "academic-main",
            "Main",
            "newapi_admin",
            base_url="https://example",
            api_key="sk-secret-token-value",
            access_token="account-token",
        )
    )

    assert result.status == "degraded"
    assert "sk-secret-token-value" not in result.error
    assert "account-token" not in result.error
    assert "token=[已脱敏]" in result.error


def test_collect_newapi_falls_back_to_token_readonly_without_access_token(monkeypatch):
    requested = []

    class FakeResponse:
        def __init__(self, url):
            self.url = url

        def raise_for_status(self):
            return None

        def json(self):
            if "/api/usage/token" in self.url:
                return {
                    "code": True,
                    "data": {
                        "name": "codex-key",
                        "total_granted": 2_000_000,
                        "total_used": 400_000,
                        "total_available": 1_600_000,
                    },
                }
            if "/api/log/token" in self.url:
                return {"success": True, "data": [{"model_name": "gpt-5.6-sol", "quota": 400_000}]}
            return {"success": True, "data": []}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            requested.append(url)
            return FakeResponse(url)

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)

    result = collect_newapi(
        LlmUsageConfig("academic-main", "Codex", "newapi_admin", base_url="https://example", api_key="sk-token-key")
    )

    assert any("/api/usage/token" in url for url in requested)
    assert any("/api/log/token" in url for url in requested)
    assert result.quota_remaining == 1_600_000


def test_newapi_admin_url_accepts_openai_compatible_v1_base_url():
    assert llm_usage.newapi_url("https://gateway.example.com/v1", "/api/user/self") == (
        "https://gateway.example.com/api/user/self"
    )
    assert llm_usage.newapi_url("https://gateway.example.com/v1/", "/api/log/self/stat") == (
        "https://gateway.example.com/api/log/self/stat"
    )
    assert llm_usage.newapi_url("https://gateway.example.com", "/api/user/self") == (
        "https://gateway.example.com/api/user/self"
    )


def test_collect_newapi_reports_success_false_payloads(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "message": "Unauthorized, invalid access token"}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            return FakeResponse()

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)

    result = collect_newapi(
        LlmUsageConfig("academic-key-3", "Blog", "newapi_admin", base_url="https://example", access_token="bad")
    )

    assert result.status == "offline"
    assert result.error == "Unauthorized, invalid access token"


def test_collect_newapi_stops_after_dashboard_auth_failure(monkeypatch):
    requested_urls = []

    class FakeResponse:
        def __init__(self, url):
            self.url = url

        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "message": "Unauthorized, invalid access token"}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers):
            requested_urls.append(url)
            return FakeResponse(url)

    monkeypatch.setattr("app.llm_usage_collector.httpx.Client", FakeClient)

    result = collect_newapi(
        LlmUsageConfig("academic-key-3", "Blog", "newapi_admin", base_url="https://example", access_token="bad")
    )

    assert requested_urls == ["https://example/api/user/self"]
    assert result.status == "offline"
    assert result.error == "Unauthorized, invalid access token"


def test_check_model_connection_uses_responses_endpoint(monkeypatch):
    request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, headers, json, timeout):
        request.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("app.llm_usage_collector.httpx.post", fake_post)

    result = check_model_connection(
        LlmUsageConfig(
            "academic-main",
            "Academic",
            "newapi_admin",
            base_url="https://gateway.example.com/v1",
            api_key="model-secret",
            request_mode="responses",
            test_model="gpt-5.4",
        )
    )

    assert request == {
        "url": "https://gateway.example.com/v1/responses",
        "headers": {
            "Authorization": "Bearer model-secret",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        "json": {
            "model": "gpt-5.4",
            "stream": True,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Reply with OK only."}],
                }
            ],
        },
        "timeout": 30,
    }
    assert result == {
        "status": "online",
        "error": None,
        "request_mode": "responses",
        "test_model": "gpt-5.4",
    }


def test_check_model_connection_uses_chat_completions_endpoint(monkeypatch):
    request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, headers, json, timeout):
        request.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("app.llm_usage_collector.httpx.post", fake_post)

    result = check_model_connection(
        LlmUsageConfig(
            "deepseek-main",
            "DeepSeek",
            "deepseek_balance",
            api_key="model-secret",
            request_mode="chat_completions",
            test_model="deepseek-chat",
        )
    )

    assert request["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert request["json"] == {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Reply with OK only."}],
    }
    assert result["status"] == "online"


def test_check_model_connection_includes_upstream_error_message(monkeypatch):
    request = httpx.Request("POST", "https://gateway.example.com/v1/responses")
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "The requested model does not exist"}},
    )
    monkeypatch.setattr("app.llm_usage_collector.httpx.post", lambda *_args, **_kwargs: response)

    result = check_model_connection(
        LlmUsageConfig(
            "academic-main",
            "Academic",
            "newapi_admin",
            base_url="https://gateway.example.com",
            api_key="model-secret",
            request_mode="responses",
            test_model="missing-model",
        )
    )

    assert result["status"] == "offline"
    assert result["error"] == "HTTP 400: The requested model does not exist"


@pytest.mark.parametrize(
    ("api_key", "test_model", "error"),
    [
        (None, "gpt-5.4", "模型API Key未配置"),
        ("model-secret", None, "测试模型未配置"),
    ],
)
def test_check_model_connection_reports_missing_config_without_request(monkeypatch, api_key, test_model, error):
    def fail_post(*_args, **_kwargs):
        raise AssertionError("不应发送模型请求")

    monkeypatch.setattr("app.llm_usage_collector.httpx.post", fail_post)

    result = check_model_connection(
        LlmUsageConfig(
            "academic-main",
            "Academic",
            "newapi_admin",
            base_url="https://gateway.example.com",
            api_key=api_key,
            request_mode="responses",
            test_model=test_model,
        )
    )

    assert result["status"] == "not_configured"
    assert result["error"] == error


def test_openai_pricing_estimates_cost_from_tokens():
    result = estimate_model_cost_usd("gpt-4.1-mini", input_tokens=1_000_000, output_tokens=1_000_000)

    assert result["estimated_cost_usd"] == 2.0
    assert result["pricing_basis"] == "openai_tokens"


def test_newapi_quota_falls_back_to_usd_when_tokens_are_missing():
    result = estimate_model_cost_usd("gpt-5.5", raw_quota=1_000_000)

    assert result["estimated_cost_usd"] == 2.0
    assert result["pricing_basis"] == "newapi_quota"


def test_save_llm_usage_config_writes_env_without_echoing_secret(tmp_path, monkeypatch):
    env_path = tmp_path / "test.env"
    env_path.write_text("PULSEBOARD_LLM_USAGE_SOURCES=academic\n", encoding="utf-8")

    result = save_llm_usage_config(
        {
            "source_id": "deepseek",
            "source_type": "deepseek_balance",
            "display_name": "DeepSeek",
            "api_key": "secret-key",
        },
        env_path=env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    assert result == {"source_id": "deepseek", "provider_id": "deepseek"}
    assert "PULSEBOARD_LLM_USAGE_SOURCES=academic,deepseek" in text
    assert "PULSEBOARD_LLM_DEEPSEEK_API_KEY=secret-key" in text


def test_save_llm_usage_config_writes_provider_group_metadata(tmp_path):
    env_path = tmp_path / "test.env"

    result = save_llm_usage_config(
        {
            "source_id": "deepseek-main",
            "source_type": "deepseek_balance",
            "provider_id": "deepseek",
            "provider_name": "DeepSeek",
            "display_name": "主Key",
            "api_key": "secret-key",
        },
        env_path=env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    assert result == {"source_id": "deepseek-main", "provider_id": "deepseek"}
    assert "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_ID=deepseek" in text
    assert "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_NAME=DeepSeek" in text
    assert "PULSEBOARD_LLM_DEEPSEEK_MAIN_DISPLAY_NAME=主Key" in text


def test_save_newapi_config_writes_model_test_settings_and_both_secrets(tmp_path):
    env_path = tmp_path / "test.env"

    save_llm_usage_config(
        {
            "source_id": "academic-main",
            "source_type": "newapi_admin",
            "provider_id": "academic",
            "provider_name": "Academic",
            "display_name": "主Key",
            "base_url": "https://gateway.example.com",
            "request_mode": "responses",
            "test_model": "gpt-5.4",
            "api_key": "model-secret",
            "access_token": "stats-secret",
            "user_id": "1",
        },
        env_path=env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_REQUEST_MODE=responses" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_TEST_MODEL=gpt-5.4" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_API_KEY=model-secret" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_ACCESS_TOKEN=stats-secret" in text


def test_save_llm_usage_config_rejects_unknown_request_mode(tmp_path):
    with pytest.raises(ValueError, match="request_mode"):
        save_llm_usage_config(
            {
                "source_id": "academic-main",
                "source_type": "newapi_admin",
                "request_mode": "legacy-completions",
            },
            env_path=tmp_path / "test.env",
        )


def test_save_llm_usage_config_rejects_env_prefix_collision(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text("PULSEBOARD_LLM_USAGE_SOURCES=deepseek-main\n", encoding="utf-8")

    with pytest.raises(ValueError, match="conflicts with existing source_id deepseek-main"):
        save_llm_usage_config(
            {
                "source_id": "deepseek_main",
                "source_type": "deepseek_balance",
                "provider_id": "deepseek",
                "display_name": "冲突Key",
            },
            env_path=env_path,
        )


def test_load_llm_usage_configs_prefers_updated_env_file_over_process_environment(tmp_path, monkeypatch):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=academic,academic-key-3",
                "PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic",
                "PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=old-token",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_DISPLAY_NAME=Key 3",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_ACCESS_TOKEN=new-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PULSEBOARD_LLM_USAGE_SOURCES", "academic")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN", "stale-token")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_KEY_3_ACCESS_TOKEN", "stale-missing-token")

    configs = load_llm_usage_configs(Settings(llm_usage_sources="academic"), env_path=env_path)

    assert [config.source_id for config in configs] == ["academic", "academic-key-3"]
    assert configs[0].access_token == "old-token"
    assert configs[1].display_name == "Key 3"
    assert configs[1].access_token == "new-token"


def test_delete_llm_usage_config_removes_source_and_secret(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=deepseek-main,deepseek-backup,academic-main",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY=main-secret",
                "PULSEBOARD_LLM_DEEPSEEK_BACKUP_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_BACKUP_API_KEY=backup-secret",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TYPE=newapi_admin",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = delete_llm_usage_config("deepseek-backup", env_path=env_path)

    text = env_path.read_text(encoding="utf-8")
    assert result == {"deleted": ["deepseek-backup"]}
    assert "PULSEBOARD_LLM_USAGE_SOURCES=deepseek-main,academic-main" in text
    assert "PULSEBOARD_LLM_DEEPSEEK_BACKUP_" not in text
    assert "PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY=main-secret" in text


def test_delete_last_llm_config_does_not_restore_stale_process_environment(tmp_path, monkeypatch):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=deepseek-main",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY=file-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PULSEBOARD_LLM_USAGE_SOURCES", "deepseek-main")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE", "deepseek_balance")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY", "stale-process-secret")

    delete_llm_usage_config("deepseek-main", env_path=env_path)

    configs = load_llm_usage_configs(Settings(llm_usage_sources="deepseek-main"), env_path=env_path)
    assert configs == []


def test_delete_llm_provider_config_removes_all_provider_sources(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=deepseek-main,deepseek-backup,academic-main",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_ID=deepseek",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_BACKUP_PROVIDER_ID=deepseek",
                "PULSEBOARD_LLM_DEEPSEEK_BACKUP_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_ID=academic",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TYPE=newapi_admin",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = delete_llm_provider_config("deepseek", env_path=env_path)

    text = env_path.read_text(encoding="utf-8")
    assert result == {"deleted": ["deepseek-main", "deepseek-backup"]}
    assert "PULSEBOARD_LLM_USAGE_SOURCES=academic-main" in text
    assert "PULSEBOARD_LLM_DEEPSEEK_MAIN_" not in text
    assert "PULSEBOARD_LLM_DEEPSEEK_BACKUP_" not in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_TYPE=newapi_admin" in text


def test_update_llm_provider_config_updates_shared_fields(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=academic-main,academic-backup",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_ID=academic",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_NAME=Academic Gateway",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_BASE_URL=https://old.example.com",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_ACCESS_TOKEN=main-token",
                "PULSEBOARD_LLM_ACADEMIC_BACKUP_PROVIDER_ID=academic",
                "PULSEBOARD_LLM_ACADEMIC_BACKUP_PROVIDER_NAME=Academic Gateway",
                "PULSEBOARD_LLM_ACADEMIC_BACKUP_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_BACKUP_BASE_URL=https://old.example.com",
                "PULSEBOARD_LLM_ACADEMIC_BACKUP_ACCESS_TOKEN=backup-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = update_llm_provider_config(
        "academic",
        {
            "provider_name": "Academic",
            "source_type": "newapi_admin",
            "base_url": "https://new.example.com",
            "request_mode": "responses",
            "test_model": "gpt-5.4",
            "user_id": "2",
            "access_token": "provider-token",
        },
        env_path=env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    assert result == {"updated": ["academic-main", "academic-backup"]}
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_NAME=Academic" in text
    assert "PULSEBOARD_LLM_ACADEMIC_BACKUP_PROVIDER_NAME=Academic" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_BASE_URL=https://new.example.com" in text
    assert "PULSEBOARD_LLM_ACADEMIC_BACKUP_BASE_URL=https://new.example.com" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_USER_ID=2" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_REQUEST_MODE=responses" in text
    assert "PULSEBOARD_LLM_ACADEMIC_BACKUP_REQUEST_MODE=responses" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_TEST_MODEL=gpt-5.4" in text
    assert "PULSEBOARD_LLM_ACADEMIC_BACKUP_TEST_MODEL=gpt-5.4" in text
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_ACCESS_TOKEN=provider-token" in text
    assert "PULSEBOARD_LLM_ACADEMIC_BACKUP_ACCESS_TOKEN=provider-token" in text


def test_save_key_inherits_existing_provider_shared_fields(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=academic-main",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_ID=academic",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_NAME=Academic Gateway",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_BASE_URL=https://gateway.example.com",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_ACCESS_TOKEN=provider-token",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_USER_ID=7",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_REQUEST_MODE=responses",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TEST_MODEL=gpt-5.4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    save_llm_usage_config(
        {
            "source_id": "academic-backup",
            "provider_id": "academic",
            "provider_name": "被忽略的名称",
            "display_name": "备用Key",
            "source_type": "deepseek_balance",
            "base_url": "https://attacker.example.com",
            "user_id": "99",
            "request_mode": "chat_completions",
            "test_model": "other-model",
            "api_key": "model-secret",
        },
        env_path=env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    configs = load_llm_usage_configs(Settings(llm_usage_sources=""), env_path=env_path)
    added = next(config for config in configs if config.source_id == "academic-backup")
    assert added.provider_name == "Academic Gateway"
    assert added.source_type == "newapi_admin"
    assert added.base_url == "https://gateway.example.com"
    assert added.user_id == "7"
    assert added.request_mode == "responses"
    assert added.test_model == "gpt-5.4"
    assert added.access_token == "provider-token"
    assert "PULSEBOARD_LLM_ACADEMIC_BACKUP_ACCESS_TOKEN=provider-token" in text


def test_update_provider_preserves_request_settings_when_optional_fields_are_missing(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=academic-main",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_ID=academic",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_PROVIDER_NAME=Academic Gateway",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_BASE_URL=https://gateway.example.com",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_REQUEST_MODE=responses",
                "PULSEBOARD_LLM_ACADEMIC_MAIN_TEST_MODEL=gpt-5.4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    update_llm_provider_config(
        "academic",
        {
            "provider_name": "Academic",
            "source_type": "newapi_admin",
            "base_url": "https://gateway.example.com",
            "user_id": "1",
        },
        env_path=env_path,
    )

    config = load_llm_usage_configs(Settings(llm_usage_sources=""), env_path=env_path)[0]
    assert config.request_mode == "responses"
    assert config.test_model == "gpt-5.4"


def test_save_llm_usage_config_rejects_newlines_in_env_values(tmp_path):
    env_path = tmp_path / "test.env"

    with pytest.raises(ValueError, match="line breaks"):
        save_llm_usage_config(
            {
                "source_id": "academic-main",
                "provider_id": "academic",
                "provider_name": "Academic",
                "display_name": "主Key",
                "source_type": "newapi_admin",
                "base_url": "https://gateway.example.com",
                "request_mode": "responses",
                "test_model": "gpt-5.4\nPULSEBOARD_LLM_USAGE_SOURCES=stolen",
            },
            env_path=env_path,
        )

    assert not env_path.exists()


def test_concurrent_llm_config_saves_do_not_lose_sources(tmp_path, monkeypatch):
    env_path = tmp_path / "test.env"
    env_path.write_text("PULSEBOARD_LLM_USAGE_SOURCES=\n", encoding="utf-8")
    barrier = Barrier(2)
    original_write_env = llm_usage._write_env

    def synchronized_write(*args, **kwargs):
        try:
            barrier.wait(timeout=0.5)
        except BrokenBarrierError:
            pass
        return original_write_env(*args, **kwargs)

    monkeypatch.setattr(llm_usage, "_write_env", synchronized_write)

    def save(source_id):
        save_llm_usage_config(
            {
                "source_id": source_id,
                "provider_id": source_id,
                "provider_name": source_id,
                "display_name": "主Key",
                "source_type": "deepseek_balance",
                "api_key": f"{source_id}-secret",
            },
            env_path=env_path,
        )

    threads = [Thread(target=save, args=(source_id,)) for source_id in ("provider-a", "provider-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    configs = load_llm_usage_configs(Settings(llm_usage_sources=""), env_path=env_path)
    assert {config.source_id for config in configs} == {"provider-a", "provider-b"}


def test_list_llm_usage_config_masks_secret(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_DEEPSEEK_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_DISPLAY_NAME=DeepSeek",
                "PULSEBOARD_LLM_DEEPSEEK_API_KEY=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = Settings(llm_usage_sources="deepseek")
    result = list_llm_usage_config(settings, env_path=env_path)

    assert result[0]["source_id"] == "deepseek"
    assert result[0]["provider_id"] == "deepseek"
    assert result[0]["provider_name"] == "DeepSeek"
    assert result[0]["has_api_key"] is True
    assert "api_key" not in result[0]


def test_list_llm_usage_config_returns_provider_group_metadata(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_ID=deepseek",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_NAME=DeepSeek",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_DISPLAY_NAME=主Key",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = Settings(llm_usage_sources="deepseek-main")
    result = list_llm_usage_config(settings, env_path=env_path)

    assert result[0]["source_id"] == "deepseek-main"
    assert result[0]["provider_id"] == "deepseek"
    assert result[0]["provider_name"] == "DeepSeek"
    assert result[0]["display_name"] == "主Key"
