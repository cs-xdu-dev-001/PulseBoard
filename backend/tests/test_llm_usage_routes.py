from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
import app.routes as routes
from app.llm_usage import LlmUsageConfig, LlmUsageResult
from app.main import app
from app.models import LlmUsageSnapshot, LlmUsageSource


def make_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), TestingSession


def seed_llm(session_factory):
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="Academic Gateway",
            source_type="newapi_admin",
            status="online",
            last_checked_at=now,
            balance_total=100,
            quota_used=12,
            quota_remaining=88,
        )
        db.add(source)
        db.flush()
        db.add(
            LlmUsageSnapshot(
                source_id=source.id,
                collected_at=now,
                range_key="latest",
                request_count=10,
                token_count=2000,
                quota_used=12,
                estimated_amount=12,
                rpm=0.5,
                tpm=100,
                success_rate=98,
                avg_latency_seconds=1.2,
                model_stats=[
                    {
                        "model": "gpt-4.1-mini",
                        "request_count": 10,
                        "token_count": 2000,
                        "input_tokens": 1_000_000,
                        "output_tokens": 1_000_000,
                        "amount": 12,
                    }
                ],
                raw_summary={},
            )
        )
        db.commit()


def test_llm_usage_sources_do_not_expose_secrets(monkeypatch):
    monkeypatch.setattr(
        routes,
        "list_llm_usage_config",
        lambda _settings: [
            {
                "source_id": "academic",
                "provider_id": "academic",
                "provider_name": "Academic Gateway",
                "display_name": "Academic Gateway",
                "source_type": "newapi_admin",
            }
        ],
    )
    client, session_factory = make_client()
    seed_llm(session_factory)

    response = client.get("/api/llm/usage/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["source_id"] == "academic"
    assert payload["sources"][0]["provider_id"] == "academic"
    assert payload["sources"][0]["provider_name"] == "Academic Gateway"
    assert payload["sources"][0]["display_name"] == "Academic Gateway"
    assert "access_token" not in payload["sources"][0]
    assert "api_key" not in payload["sources"][0]


def test_llm_usage_sources_follow_config_not_stale_database_rows(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=academic-key-3,deepseek-main",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_PROVIDER_ID=academic",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_PROVIDER_NAME=EduModel",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_DISPLAY_NAME=Blog",
                "PULSEBOARD_LLM_ACADEMIC_KEY_3_ACCESS_TOKEN=secret",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_TYPE=deepseek_balance",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_ID=deepseek",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_PROVIDER_NAME=DeepSeek",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_DISPLAY_NAME=codex",
                "PULSEBOARD_LLM_DEEPSEEK_MAIN_API_KEY=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.llm_usage.ROOT_DIR", tmp_path)
    client, session_factory = make_client()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add_all(
            [
                LlmUsageSource(
                    source_id="academic",
                    display_name="Academic Gateway",
                    source_type="newapi_admin",
                    status="online",
                    last_checked_at=now,
                ),
                LlmUsageSource(
                    source_id="academic-key-3",
                    display_name="Old Blog",
                    source_type="newapi_admin",
                    status="online",
                    last_checked_at=now,
                ),
            ]
        )
        db.commit()

    payload = client.get("/api/llm/usage/sources").json()

    assert [item["source_id"] for item in payload["sources"]] == ["academic-key-3", "deepseek-main"]
    assert payload["sources"][0]["provider_name"] == "EduModel"
    assert payload["sources"][0]["display_name"] == "Blog"
    assert payload["sources"][0]["status"] == "online"
    assert payload["sources"][1]["provider_name"] == "DeepSeek"
    assert payload["sources"][1]["display_name"] == "codex"
    assert payload["sources"][1]["status"] == "unknown"
    assert all(item["source_id"] != "academic" for item in payload["sources"])


def test_llm_usage_aggregates_ignore_unconfigured_database_rows(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=active-key",
                "PULSEBOARD_LLM_ACTIVE_KEY_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACTIVE_KEY_PROVIDER_ID=active",
                "PULSEBOARD_LLM_ACTIVE_KEY_PROVIDER_NAME=Active",
                "PULSEBOARD_LLM_ACTIVE_KEY_DISPLAY_NAME=Active Key",
                "PULSEBOARD_LLM_ACTIVE_KEY_ACCESS_TOKEN=secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.llm_usage.ROOT_DIR", tmp_path)
    client, session_factory = make_client()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        active = LlmUsageSource(source_id="active-key", display_name="Active Key", source_type="newapi_admin", status="online")
        stale = LlmUsageSource(source_id="stale-key", display_name="Stale Key", source_type="newapi_admin", status="online")
        db.add_all([active, stale])
        db.flush()
        db.add_all(
            [
                LlmUsageSnapshot(
                    source_id=active.id,
                    collected_at=now,
                    range_key="latest",
                    request_count=10,
                    token_count=100,
                    quota_used=1,
                    estimated_amount=1,
                    model_stats=[{"model": "active-model", "request_count": 10, "amount": 1}],
                    raw_summary={},
                ),
                LlmUsageSnapshot(
                    source_id=stale.id,
                    collected_at=now,
                    range_key="latest",
                    request_count=90,
                    token_count=900,
                    quota_used=9,
                    estimated_amount=9,
                    model_stats=[{"model": "stale-model", "request_count": 90, "amount": 9}],
                    raw_summary={},
                ),
            ]
        )
        db.commit()

    summary = client.get("/api/llm/usage/summary?range=24h").json()
    models = client.get("/api/llm/usage/models?range=24h").json()
    series = client.get("/api/llm/usage/series?range=24h").json()

    assert summary["request_count"] == 10
    assert [item["model"] for item in models["models"]] == ["active-model"]
    assert [item["source_id"] for item in series["series"]] == ["active-key"]


def test_llm_usage_summary_and_models_return_aggregates():
    client, session_factory = make_client()
    seed_llm(session_factory)

    summary = client.get("/api/llm/usage/summary?range=24h").json()
    models = client.get("/api/llm/usage/models?range=24h").json()

    assert summary["request_count"] == 10
    assert summary["token_count"] == 2000
    assert summary["avg_rpm"] == 0.5
    assert summary["estimated_cost_usd"] == 2.0
    assert models["models"][0]["model"] == "gpt-4.1-mini"
    assert models["models"][0]["amount"] == 12
    assert models["models"][0]["estimated_cost_usd"] == 2.0


def test_llm_usage_summary_prefers_model_cost_over_raw_newapi_quota():
    client, session_factory = make_client()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="Academic Gateway",
            source_type="newapi_admin",
            status="online",
            last_checked_at=now,
        )
        db.add(source)
        db.flush()
        db.add(
            LlmUsageSnapshot(
                source_id=source.id,
                collected_at=now,
                range_key="latest",
                request_count=10,
                token_count=2000,
                quota_used=3_282_920_000,
                estimated_amount=6565.84,
                model_stats=[
                    {
                        "model": "gpt-5.5",
                        "request_count": 10,
                        "token_count": 2000,
                        "amount": 5_543_995,
                    }
                ],
                raw_summary={"token_usage": {"total_used": 3_282_920_000}},
            )
        )
        db.commit()

    summary = client.get("/api/llm/usage/summary?range=24h").json()
    series = client.get("/api/llm/usage/series?range=24h").json()

    assert summary["estimated_cost_usd"] == 11.08799
    assert series["series"][0]["points"][0]["estimated_cost_usd"] == 11.08799


def test_llm_usage_series_includes_model_area_series():
    client, session_factory = make_client()
    seed_llm(session_factory)

    payload = client.get("/api/llm/usage/series?range=24h").json()

    assert payload["model_series"][0]["model"] == "gpt-4.1-mini"
    assert payload["model_series"][0]["points"][0]["estimated_cost_usd"] == 2.0
    assert payload["model_series"][0]["points"][0]["request_count"] == 10
    assert payload["model_series"][0]["points"][0]["source_id"] == "academic"


def test_llm_usage_series_limits_points_per_source():
    client, session_factory = make_client()
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="Academic Gateway",
            source_type="newapi_admin",
            status="online",
        )
        db.add(source)
        db.flush()
        for index in range(320):
            db.add(
                LlmUsageSnapshot(
                    source_id=source.id,
                    collected_at=now - timedelta(minutes=319 - index),
                    range_key="latest",
                    request_count=index,
                    token_count=index,
                    quota_used=index,
                    estimated_amount=index,
                    model_stats=[{"model": "gpt-4.1-mini", "request_count": index, "amount": index}],
                    raw_summary={},
                )
            )
        db.commit()

    payload = client.get("/api/llm/usage/series?range=24h").json()

    assert len(payload["series"][0]["points"]) == 288
    assert len(payload["model_series"][0]["points"]) == 288
    assert payload["series"][0]["points"][0]["request_count"] == 32


def test_llm_usage_routes_accept_newapi_style_long_ranges():
    client, session_factory = make_client()
    seed_llm(session_factory)

    for range_value in ("14d", "29d"):
        summary = client.get(f"/api/llm/usage/summary?range={range_value}")
        series = client.get(f"/api/llm/usage/series?range={range_value}")
        models = client.get(f"/api/llm/usage/models?range={range_value}")

        assert summary.status_code == 200
        assert series.status_code == 200
        assert models.status_code == 200


def test_save_llm_usage_config_returns_422_detail(monkeypatch):
    def raise_value_error(_values):
        raise ValueError("source_id deepseek_main conflicts with existing source_id deepseek-main")

    monkeypatch.setattr("app.routes.save_llm_usage_config", raise_value_error)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/llm/usage/config",
        json={
            "source_id": "deepseek_main",
            "source_type": "deepseek_balance",
            "provider_id": "deepseek",
            "display_name": "冲突Key",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "source_id deepseek_main conflicts with existing source_id deepseek-main"


def test_llm_usage_config_test_checks_one_source_without_exposing_secrets(monkeypatch):
    config = LlmUsageConfig(
        source_id="academic-main",
        provider_id="academic",
        provider_name="Academic",
        display_name="主Key",
        source_type="newapi_admin",
        base_url="https://gateway.example.com",
        api_key="model-secret",
        access_token="secret-token",
        user_id="1",
        request_mode="responses",
        test_model="gpt-5.4",
    )
    calls = []

    monkeypatch.setattr(routes, "load_llm_usage_configs", lambda _settings: [config])

    def fake_collect_source(received_config):
        calls.append(received_config.source_id)
        return LlmUsageResult(
            source_id=received_config.source_id,
            display_name=received_config.display_name,
            source_type=received_config.source_type,
            status="degraded",
            balance_total=48.86,
            error=f"统计接口暂不可用 secret-token {'x' * 1200}",
        )

    monkeypatch.setattr(routes, "collect_source", fake_collect_source)

    def fake_check_model_connection(received_config):
        calls.append(f"model:{received_config.source_id}")
        return {
            "status": "offline",
            "error": "模型请求失败 model-secret",
            "request_mode": "responses",
            "test_model": "gpt-5.4",
        }

    monkeypatch.setattr(routes, "check_model_connection", fake_check_model_connection)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/llm/usage/config/academic-main/test")

    assert response.status_code == 200
    assert calls == ["academic-main", "model:academic-main"]
    payload = response.json()
    assert payload["source_id"] == "academic-main"
    assert payload["display_name"] == "主Key"
    assert payload["status"] == "degraded"
    assert payload["error"].startswith("统计接口暂不可用 [已脱敏]")
    assert len(payload["error"]) <= 1000
    assert payload["statistics"]["status"] == "degraded"
    assert payload["statistics"]["error"].startswith("统计接口暂不可用 [已脱敏]")
    assert payload["model"] == {
        "status": "offline",
        "error": "模型请求失败 [已脱敏]",
        "request_mode": "responses",
        "test_model": "gpt-5.4",
    }
    assert payload["checked_at"]
    assert "api_key" not in response.text
    assert "access_token" not in response.text
    assert "secret-token" not in response.text
    assert "model-secret" not in response.text


def test_llm_usage_config_test_returns_404_for_unknown_source(monkeypatch):
    monkeypatch.setattr(routes, "load_llm_usage_configs", lambda _settings: [])
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/llm/usage/config/missing-key/test")

    assert response.status_code == 404
    assert response.json()["detail"] == "未找到API Key配置：missing-key"


def test_llm_usage_test_error_redacts_url_encoded_secrets():
    message = "上游回显：model%2Bsecret%3D"

    assert routes._sanitize_llm_test_error(message, "model+secret=") == "上游回显：[已脱敏]"


def test_save_llm_usage_config_route_reads_updated_env_file_without_restart(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PULSEBOARD_LLM_USAGE_SOURCES=academic",
                "PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin",
                "PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic",
                "PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=old-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.llm_usage.ROOT_DIR", tmp_path)
    monkeypatch.setenv("PULSEBOARD_LLM_USAGE_SOURCES", "academic")
    monkeypatch.setenv("PULSEBOARD_LLM_ACADEMIC_KEY_3_ACCESS_TOKEN", "stale-token")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/llm/usage/config",
        json={
            "source_id": "academic-key-3",
            "source_type": "newapi_admin",
            "provider_id": "academic",
            "provider_name": "Academic",
            "display_name": "Key 3",
            "base_url": "https://new-api.example.com",
            "request_mode": "responses",
            "test_model": "gpt-5.4",
            "api_key": "model-key",
            "access_token": "new-token",
            "user_id": "1",
        },
    )

    assert response.status_code == 200
    payload = client.get("/api/llm/usage/config").json()
    source_ids = [item["source_id"] for item in payload["sources"]]
    key_3 = next(item for item in payload["sources"] if item["source_id"] == "academic-key-3")
    assert source_ids == ["academic", "academic-key-3"]
    assert key_3["display_name"] == "Key 3"
    assert key_3["request_mode"] == "responses"
    assert key_3["test_model"] == "gpt-5.4"
    assert key_3["has_api_key"] is True
    assert key_3["has_access_token"] is True


def test_delete_llm_usage_config_route(monkeypatch):
    calls = []

    def fake_delete(source_id):
        calls.append(source_id)
        return {"deleted": [source_id]}

    monkeypatch.setattr(routes, "delete_llm_usage_config", fake_delete)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.delete("/api/llm/usage/config/deepseek-main")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "deleted": ["deepseek-main"]}
    assert calls == ["deepseek-main"]


def test_delete_llm_provider_config_route(monkeypatch):
    calls = []

    def fake_delete(provider_id):
        calls.append(provider_id)
        return {"deleted": ["deepseek-main", "deepseek-backup"]}

    monkeypatch.setattr(routes, "delete_llm_provider_config", fake_delete)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.delete("/api/llm/usage/providers/deepseek")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "deleted": ["deepseek-main", "deepseek-backup"]}
    assert calls == ["deepseek"]


def test_update_llm_provider_config_route(monkeypatch):
    calls = []

    def fake_update(provider_id, values):
        calls.append((provider_id, values))
        return {"updated": ["academic-main"]}

    monkeypatch.setattr(routes, "update_llm_provider_config", fake_update)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.patch(
        "/api/llm/usage/providers/academic",
        json={
            "provider_name": "Academic",
            "source_type": "newapi_admin",
            "base_url": "https://gateway.example.com",
            "request_mode": "responses",
            "test_model": "gpt-5.4",
            "user_id": "2",
            "access_token": "provider-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "updated": ["academic-main"]}
    assert calls == [
        (
            "academic",
            {
                "provider_name": "Academic",
                "source_type": "newapi_admin",
                "base_url": "https://gateway.example.com",
                "request_mode": "responses",
                "test_model": "gpt-5.4",
                "user_id": "2",
                "access_token": "provider-token",
            },
        )
    ]
