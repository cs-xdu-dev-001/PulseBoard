from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
import app.routes as routes
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


def test_llm_usage_sources_do_not_expose_secrets():
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


def test_llm_usage_series_includes_model_area_series():
    client, session_factory = make_client()
    seed_llm(session_factory)

    payload = client.get("/api/llm/usage/series?range=24h").json()

    assert payload["model_series"][0]["model"] == "gpt-4.1-mini"
    assert payload["model_series"][0]["points"][0]["estimated_cost_usd"] == 2.0
    assert payload["model_series"][0]["points"][0]["request_count"] == 10


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
            "user_id": "2",
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
                "user_id": "2",
            },
        )
    ]
