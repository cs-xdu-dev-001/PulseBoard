from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
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
