import pytest

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
from app.llm_usage_collector import collect_newapi
from app.llm_pricing import estimate_model_cost_usd


def test_load_llm_usage_configs_supports_custom_source_ids(tmp_path):
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic Gateway",
                "PULSEBOARD_LLM_ACADEMIC_BASE_URL=https://new-api.example.com",
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
            "user_id": "2",
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
    assert "PULSEBOARD_LLM_ACADEMIC_MAIN_ACCESS_TOKEN=main-token" in text


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
