from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import LlmUsageDaily, LlmUsageSource


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
