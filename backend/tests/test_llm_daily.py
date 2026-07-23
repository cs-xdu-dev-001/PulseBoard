from datetime import date, datetime, timezone

import pytest
from sqlalchemy import BigInteger, Double, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import llm_usage_collector
from app import main as app_main
from app.db import Base
from app.llm_daily import rebuild_daily_rollups, upsert_daily_from_result
from app.llm_usage import LlmUsageConfig, LlmUsageResult
from app.models import LlmUsageDaily, LlmUsageSnapshot, LlmUsageSource


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_llm_usage_numeric_columns_preserve_large_counts_and_amounts():
    for column in (
        LlmUsageSnapshot.__table__.c.request_count,
        LlmUsageSnapshot.__table__.c.token_count,
        LlmUsageDaily.__table__.c.request_count,
        LlmUsageDaily.__table__.c.token_count,
        LlmUsageDaily.__table__.c.input_tokens,
        LlmUsageDaily.__table__.c.output_tokens,
    ):
        assert isinstance(column.type, BigInteger)

    for column in (
        LlmUsageSource.__table__.c.balance_total,
        LlmUsageSource.__table__.c.balance_granted,
        LlmUsageSource.__table__.c.balance_topped_up,
        LlmUsageSource.__table__.c.quota_total,
        LlmUsageSource.__table__.c.quota_used,
        LlmUsageSource.__table__.c.quota_remaining,
        LlmUsageSnapshot.__table__.c.quota_used,
        LlmUsageSnapshot.__table__.c.estimated_amount,
        LlmUsageDaily.__table__.c.estimated_amount,
        LlmUsageDaily.__table__.c.estimated_cost_usd,
    ):
        assert isinstance(column.type, Double)


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


def test_daily_upsert_does_not_replace_complete_total_with_sampled_result():
    Session = make_session()
    usage_date = date(2026, 7, 22)
    complete_at = datetime(2026, 7, 22, 14, tzinfo=timezone.utc)
    sampled_at = datetime(2026, 7, 22, 15, tzinfo=timezone.utc)
    with Session() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="EduModel",
            source_type="newapi_admin",
            status="online",
        )
        db.add(source)
        db.flush()
        db.add(
            LlmUsageDaily(
                source_id=source.id,
                usage_date=usage_date,
                model="__total__",
                request_count=200,
                token_count=20_000,
                token_complete=True,
                data_quality="complete",
                observed_at=complete_at,
            )
        )
        db.commit()
        sampled = LlmUsageResult(
            source_id="academic",
            display_name="EduModel",
            source_type="newapi_admin",
            status="online",
            request_count=50,
            token_count=5_000,
            model_stats=[],
            raw_summary={
                "newapi": {
                    "buckets": [
                        {
                            "timestamp": "2026-07-22T08:00:00+08:00",
                            "model": "gpt-5.5",
                            "request_count": 50,
                            "input_tokens": 4_000,
                            "output_tokens": 1_000,
                        }
                    ]
                }
            },
        )

        upsert_daily_from_result(
            db,
            sampled,
            sampled_at,
            "Asia/Shanghai",
            source_db_id=source.id,
            replace=True,
        )
        db.commit()
        total = db.query(LlmUsageDaily).filter(LlmUsageDaily.model == "__total__").one()

    assert total.request_count == 200
    assert total.token_count == 20_000
    assert total.token_complete is True
    assert total.data_quality == "complete"
    assert total.observed_at.replace(tzinfo=timezone.utc) == complete_at


def test_daily_upsert_writes_newapi_result_to_explicit_target_date():
    Session = make_session()
    collected_at = datetime(2026, 7, 23, 1, tzinfo=timezone.utc)
    target_date = date(2026, 7, 22)
    with Session() as db:
        source = LlmUsageSource(
            source_id="academic",
            display_name="EduModel",
            source_type="newapi_admin",
            status="online",
        )
        db.add(source)
        db.flush()
        result = LlmUsageResult(
            source_id="academic",
            display_name="EduModel",
            source_type="newapi_admin",
            status="online",
            request_count=120,
            token_count=12_000,
            quota_used=250_000,
            estimated_amount=0.5,
            model_stats=[],
            raw_summary={"stat": {"count": 120, "token": 12_000, "quota": 250_000}},
        )

        upsert_daily_from_result(
            db,
            result,
            collected_at,
            "Asia/Shanghai",
            source_db_id=source.id,
            target_date=target_date,
        )
        db.commit()
        total = db.query(LlmUsageDaily).one()

    assert total.usage_date == target_date
    assert total.token_count == 12_000
    assert total.observed_at.replace(tzinfo=timezone.utc) == collected_at


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


def test_daily_upsert_filters_deepseek_buckets_to_target_date():
    Session = make_session()
    collected_at = datetime(2026, 7, 23, 1, tzinfo=timezone.utc)
    target_date = date(2026, 7, 22)
    with Session() as db:
        source = LlmUsageSource(
            source_id="deepseek-main",
            display_name="DeepSeek",
            source_type="deepseek_platform",
            status="online",
        )
        db.add(source)
        db.flush()
        result = LlmUsageResult(
            source_id="deepseek-main",
            display_name="DeepSeek",
            source_type="deepseek_platform",
            status="online",
            raw_summary={
                "deepseek_platform": {
                    "currency": "CNY",
                    "daily": [
                        {"time": "2026-07-21T00:00:00+00:00", "request_count": 10, "token_count": 1_000},
                        {"time": "2026-07-22T00:00:00+00:00", "request_count": 20, "token_count": 2_000},
                    ],
                }
            },
        )

        upsert_daily_from_result(
            db,
            result,
            collected_at,
            "Asia/Shanghai",
            source_db_id=source.id,
            target_date=target_date,
        )
        db.commit()
        rows = db.query(LlmUsageDaily).all()

    assert len(rows) == 1
    assert rows[0].usage_date == target_date
    assert rows[0].token_count == 2_000


def test_daily_collection_only_persists_official_usage_sources(monkeypatch):
    Session = make_session()
    target_date = date(2026, 7, 22)
    configs = [
        LlmUsageConfig("academic", "EduModel", "newapi_admin"),
        LlmUsageConfig("deepseek-main", "DeepSeek", "deepseek_platform"),
        LlmUsageConfig("deepseek-balance", "DeepSeek余额", "deepseek_balance"),
        LlmUsageConfig("gateway-main", "Gateway", "openai_gateway"),
    ]
    collected = []

    def fake_collect_source(config, *, usage_date=None, lab_timezone="Asia/Shanghai"):
        collected.append((config.source_id, usage_date, lab_timezone))
        if config.source_type == "newapi_admin":
            return LlmUsageResult(
                source_id=config.source_id,
                display_name=config.display_name,
                source_type=config.source_type,
                status="online",
                request_count=12,
                token_count=1_200,
                raw_summary={"stat": {"count": 12, "token": 1_200}},
            )
        return LlmUsageResult(
            source_id=config.source_id,
            display_name=config.display_name,
            source_type=config.source_type,
            status="online",
            raw_summary={
                "deepseek_platform": {
                    "currency": "CNY",
                    "daily": [
                        {
                            "time": "2026-07-22T00:00:00+00:00",
                            "request_count": 8,
                            "token_count": 800,
                            "amount": 0.8,
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(llm_usage_collector, "load_llm_usage_configs", lambda settings: configs)
    monkeypatch.setattr(llm_usage_collector, "collect_source", fake_collect_source)
    settings = type("SettingsStub", (), {"lab_timezone": "Asia/Shanghai"})()

    with Session() as db:
        llm_usage_collector.collect_llm_usage_daily_once(db, settings, target_date)
        rows = db.query(LlmUsageDaily).order_by(LlmUsageDaily.source_id).all()

    assert [item[0] for item in collected] == ["academic", "deepseek-main"]
    assert all(item[1] == target_date for item in collected)
    assert len(rows) == 2
    assert {row.usage_date for row in rows} == {target_date}
    assert sum(row.token_count for row in rows) == 2_000


def test_daily_collection_job_uses_previous_configured_local_date(monkeypatch):
    captured = {}
    settings = type(
        "SettingsStub",
        (),
        {
            "lab_timezone": "Asia/Shanghai",
            "llm_usage_sources": "academic",
        },
    )()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "SessionLocal", FakeSession)
    monkeypatch.setattr(
        app_main,
        "collect_llm_usage_daily_once",
        lambda db, current_settings, target_date: captured.update(
            db=db,
            settings=current_settings,
            target_date=target_date,
        ),
        raising=False,
    )

    app_main.run_llm_usage_daily_collection_job(
        now=datetime(2026, 7, 22, 16, 5, tzinfo=timezone.utc)
    )

    assert captured["target_date"] == date(2026, 7, 22)
    assert captured["settings"] is settings


def test_rebuild_daily_rollups_reads_deepseek_daily_model_buckets():
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
                raw_summary={
                    "deepseek_platform": {
                        "currency": "CNY",
                        "daily": [
                            {
                                "time": 1784592000,
                                "request_count": 5,
                                "token_count": 500,
                                "amount": 1.5,
                                "models": [
                                    {
                                        "model": "deepseek-v4-flash",
                                        "request_count": 4,
                                        "token_count": 450,
                                        "input_tokens": 400,
                                        "output_tokens": 50,
                                        "amount": 1.2,
                                    },
                                    {
                                        "model": "deepseek-v4-pro",
                                        "request_count": 1,
                                        "token_count": 50,
                                        "input_tokens": 40,
                                        "output_tokens": 10,
                                        "amount": 0.3,
                                    },
                                ],
                            }
                        ],
                    }
                },
            )
        )
        db.commit()

        rebuild_daily_rollups(db, "Asia/Shanghai", observed_at)
        rows = db.query(LlmUsageDaily).order_by(LlmUsageDaily.model).all()

    assert [row.model for row in rows] == ["__total__", "deepseek-v4-flash", "deepseek-v4-pro"]
    flash = next(row for row in rows if row.model == "deepseek-v4-flash")
    assert flash.request_count == 4
    assert flash.token_count == 450
    assert flash.estimated_cost_usd == 1.2


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
