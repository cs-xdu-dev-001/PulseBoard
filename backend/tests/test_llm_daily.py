from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.llm_daily import rebuild_daily_rollups, upsert_daily_from_result
from app.llm_usage import LlmUsageResult
from app.models import LlmUsageDaily, LlmUsageSnapshot, LlmUsageSource


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_llm_usage_daily_has_defaults_and_unique_source_date_model():
    Session = make_session()
    with Session() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="EduModel",
            source_type="newapi_admin",
            status="online",
        )
        db.add(source)
        db.flush()
        row = LlmUsageDaily(
            source_id=source.id,
            usage_date=date(2026, 7, 21),
            model="__total__",
            request_count=12,
            token_count=None,
            observed_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        )
        db.add(row)
        db.commit()
        assert row.data_quality == "unavailable"
        assert row.token_complete is False

        db.add(
            LlmUsageDaily(
                source_id=source.id,
                usage_date=date(2026, 7, 21),
                model="__total__",
                observed_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_rebuild_daily_rollups_uses_latest_newapi_snapshot():
    Session = make_session()
    observed_at = datetime(2026, 7, 21, 8, tzinfo=timezone.utc)
    with Session() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="EduModel",
            source_type="newapi_admin",
            status="online",
        )
        db.add(source)
        db.flush()
        for index, token_count in enumerate((100, 250)):
            db.add(
                LlmUsageSnapshot(
                    source_id=source.id,
                    collected_at=observed_at.replace(minute=index),
                    range_key="latest",
                    request_count=10 + index,
                    token_count=token_count,
                    quota_used=500 + index,
                    estimated_amount=0.001 + index,
                    model_stats=[],
                    raw_summary={
                        "stat": {"count": 10 + index, "token": token_count, "quota": 500 + index},
                        "newapi": {
                            "buckets": [
                                {
                                    "timestamp": "2026-07-21T08:00:00+00:00",
                                    "model": "gpt-5.5",
                                    "request_count": 10 + index,
                                    "input_tokens": token_count - 25,
                                    "output_tokens": 25,
                                    "amount": 500 + index,
                                    "estimated_cost_usd": 0.001 + index,
                                }
                            ]
                        },
                    },
                )
            )
        db.commit()

        rebuild_daily_rollups(db, "Asia/Shanghai", observed_at)
        rows = db.query(LlmUsageDaily).order_by(LlmUsageDaily.model).all()

    total = next(row for row in rows if row.model == "__total__")
    assert total.request_count == 11
    assert total.token_count == 250
    assert total.estimated_amount == 501
    assert len([row for row in rows if row.model == "__total__"]) == 1


def test_rebuild_daily_rollups_reads_deepseek_daily_buckets():
    Session = make_session()
    observed_at = datetime(2026, 7, 21, 8, tzinfo=timezone.utc)
    with Session() as db:
        source = LlmUsageSource(
            source_id="deepseek-main",
            display_name="DeepSeek",
            source_type="deepseek_platform",
            status="online",
        )
        db.add(source)
        db.flush()
        db.add(
            LlmUsageSnapshot(
                source_id=source.id,
                collected_at=observed_at,
                range_key="latest",
                request_count=15,
                token_count=1_500,
                estimated_amount=3.5,
                model_stats=[],
                raw_summary={
                    "deepseek_platform": {
                        "currency": "CNY",
                        "daily": [
                            {"time": 1784505600, "request_count": 10, "token_count": 1000, "amount": 2.0},
                            {"time": 1784592000, "request_count": 5, "token_count": 500, "amount": 1.5},
                        ],
                    }
                },
            )
        )
        db.commit()

        rebuild_daily_rollups(db, "Asia/Shanghai", observed_at)
        rows = db.query(LlmUsageDaily).all()

    assert len(rows) == 2
    assert {row.usage_date.isoformat() for row in rows} == {"2026-07-20", "2026-07-21"}
    assert sum(row.token_count for row in rows) == 1_500
    assert all(row.currency == "CNY" for row in rows)


def test_gateway_daily_total_does_not_double_model_usage():
    Session = make_session()
    observed_at = datetime(2026, 7, 21, 8, tzinfo=timezone.utc)
    with Session() as db:
        source = LlmUsageSource(
            source_id="gateway-main",
            display_name="Gateway",
            source_type="openai_gateway",
            status="online",
        )
        db.add(source)
        db.flush()
        result = LlmUsageResult(
            source_id="gateway-main",
            display_name="Gateway",
            source_type="openai_gateway",
            status="online",
            request_count=1,
            token_count=90,
            estimated_amount=0.001,
            model_stats=[
                {
                    "model": "gpt-5.5",
                    "request_count": 1,
                    "token_count": 90,
                    "input_tokens": 60,
                    "output_tokens": 30,
                    "estimated_cost_usd": 0.001,
                }
            ],
        )

        upsert_daily_from_result(db, result, observed_at, "Asia/Shanghai", source_db_id=source.id, replace=False)
        total = db.query(LlmUsageDaily).filter(LlmUsageDaily.model == "__total__").one()

    assert total.request_count == 1
    assert total.token_count == 90
    assert total.estimated_cost_usd == 0.001
