from pathlib import Path

from app.config import Settings
from app.llm_usage import LlmUsageConfig, list_llm_usage_config, load_llm_usage_configs, normalize_deepseek_balance, normalize_newapi, save_llm_usage_config
from app.llm_pricing import estimate_model_cost_usd


def test_load_llm_usage_configs_supports_custom_source_ids(tmp_path, monkeypatch):
    env_path = Path("C:/Users/z2986/Desktop/PulseBoard/.env")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_TYPE", "newapi_admin")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME", "Academic Gateway")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_BASE_URL", "https://new-api.example.com")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN", "secret")

    settings = Settings(llm_usage_sources="academic")
    configs = load_llm_usage_configs(settings)

    assert env_path.name == ".env"
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


def test_openai_pricing_estimates_cost_from_tokens():
    result = estimate_model_cost_usd("gpt-4.1-mini", input_tokens=1_000_000, output_tokens=1_000_000)

    assert result["estimated_cost_usd"] == 2.0
    assert result["pricing_basis"] == "openai_tokens"


def test_newapi_quota_falls_back_to_usd_when_tokens_are_missing():
    result = estimate_model_cost_usd("gpt-5.5", raw_quota=1_000_000)

    assert result["estimated_cost_usd"] == 2.0
    assert result["pricing_basis"] == "newapi_quota"


def test_save_llm_usage_config_writes_env_without_echoing_secret(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
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
    env_path = tmp_path / ".env"

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


def test_list_llm_usage_config_masks_secret(monkeypatch):
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_TYPE", "deepseek_balance")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_DISPLAY_NAME", "DeepSeek")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_API_KEY", "secret")

    settings = Settings(llm_usage_sources="deepseek")
    result = list_llm_usage_config(settings)

    assert result[0]["source_id"] == "deepseek"
    assert result[0]["provider_id"] == "deepseek"
    assert result[0]["provider_name"] == "DeepSeek"
    assert result[0]["has_api_key"] is True
    assert "api_key" not in result[0]


def test_list_llm_usage_config_returns_provider_group_metadata(monkeypatch):
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE", "deepseek_balance")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_ID", "deepseek")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_NAME", "DeepSeek")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_DISPLAY_NAME", "主Key")
    monkeypatch.setenv("PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY", "secret")

    settings = Settings(llm_usage_sources="deepseek-main")
    result = list_llm_usage_config(settings)

    assert result[0]["source_id"] == "deepseek-main"
    assert result[0]["provider_id"] == "deepseek"
    assert result[0]["provider_name"] == "DeepSeek"
    assert result[0]["display_name"] == "主Key"
