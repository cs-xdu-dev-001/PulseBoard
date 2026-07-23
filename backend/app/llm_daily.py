from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import LlmUsageDaily, LlmUsageSnapshot, LlmUsageSource


TOTAL_MODEL = "__total__"
_ROLLUP_LOCK = RLock()


def upsert_daily_from_result(
    db: Session,
    result: Any,
    collected_at: datetime,
    lab_timezone: str,
    *,
    source_db_id: int | None = None,
    replace: bool = True,
    target_date: date | None = None,
) -> None:
    source_id = source_db_id
    if source_id is None:
        source = db.scalar(select(LlmUsageSource).where(LlmUsageSource.source_id == result.source_id))
        if source is None:
            return
        source_id = source.id
    values = _values_from_observation(
        source_id=source_id,
        source_type=result.source_type,
        collected_at=collected_at,
        request_count=result.request_count,
        token_count=result.token_count,
        quota_used=result.quota_used,
        estimated_amount=result.estimated_amount,
        model_stats=result.model_stats or [],
        raw_summary=result.raw_summary or {},
        lab_timezone=lab_timezone,
        target_date=target_date,
    )
    for value in values:
        _upsert_value(db, value, replace=replace)


def rebuild_daily_rollups(
    db: Session,
    lab_timezone: str,
    now: datetime,
    snapshot_retention_days: int = 30,
    daily_retention_days: int = 365,
) -> None:
    with _ROLLUP_LOCK:
        db.execute(delete(LlmUsageDaily))
        sources = {source.id: source for source in db.scalars(select(LlmUsageSource)).all()}
        snapshots = db.scalars(
            select(LlmUsageSnapshot).order_by(LlmUsageSnapshot.source_id, LlmUsageSnapshot.collected_at, LlmUsageSnapshot.id)
        ).all()
        latest_by_source_day: dict[tuple[int, date], LlmUsageSnapshot] = {}
        latest_deepseek: dict[int, LlmUsageSnapshot] = {}
        gateway_snapshots: list[tuple[LlmUsageSnapshot, LlmUsageSource]] = []
        tz = _zone(lab_timezone)
        for snapshot in snapshots:
            source = sources.get(snapshot.source_id)
            if source is None:
                continue
            if source.source_type == "newapi_admin":
                key = (source.id, _local_date(snapshot.collected_at, tz))
                latest_by_source_day[key] = snapshot
            elif source.source_type == "deepseek_platform":
                latest_deepseek[source.id] = snapshot
            elif source.source_type == "openai_gateway":
                gateway_snapshots.append((snapshot, source))

        for (source_id, _usage_date), snapshot in latest_by_source_day.items():
            source = sources[source_id]
            for value in _values_from_snapshot(snapshot, source, lab_timezone):
                _upsert_value(db, value, replace=True)
        for source_id, snapshot in latest_deepseek.items():
            source = sources[source_id]
            for value in _values_from_snapshot(snapshot, source, lab_timezone):
                _upsert_value(db, value, replace=True)
        for snapshot, source in gateway_snapshots:
            for value in _values_from_snapshot(snapshot, source, lab_timezone):
                _upsert_value(db, value, replace=False)
        cleanup_daily_rollups(db, now, snapshot_retention_days, daily_retention_days, lab_timezone)


def cleanup_daily_rollups(
    db: Session,
    now: datetime,
    snapshot_retention_days: int = 30,
    daily_retention_days: int = 365,
    lab_timezone: str = "Asia/Shanghai",
) -> None:
    snapshot_cutoff = now - timedelta(days=snapshot_retention_days)
    daily_cutoff = _local_date(now, _zone(lab_timezone)) - timedelta(days=daily_retention_days)
    db.execute(
        delete(LlmUsageSnapshot)
        .where(LlmUsageSnapshot.collected_at < snapshot_cutoff)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(LlmUsageDaily)
        .where(LlmUsageDaily.usage_date < daily_cutoff)
        .execution_options(synchronize_session=False)
    )


def ensure_daily_rollups(
    db: Session,
    lab_timezone: str,
    now: datetime,
    snapshot_retention_days: int = 30,
    daily_retention_days: int = 365,
) -> bool:
    with _ROLLUP_LOCK:
        count = db.scalar(select(func.count()).select_from(LlmUsageDaily)) or 0
        if count:
            return False
        rebuild_daily_rollups(db, lab_timezone, now, snapshot_retention_days, daily_retention_days)
        db.commit()
        return True


def daily_usage_query(
    db: Session,
    start_date: date,
    end_date: date,
    source_id: str | None,
    configured_source_ids: list[str] | None,
) -> list[LlmUsageDaily]:
    stmt = (
        select(LlmUsageDaily)
        .join(LlmUsageSource, LlmUsageSource.id == LlmUsageDaily.source_id)
        .where(LlmUsageDaily.usage_date >= start_date, LlmUsageDaily.usage_date <= end_date)
        .order_by(LlmUsageDaily.usage_date, LlmUsageDaily.source_id, LlmUsageDaily.model)
    )
    if source_id:
        stmt = stmt.where(LlmUsageSource.source_id == source_id)
    elif configured_source_ids is not None:
        if not configured_source_ids:
            return []
        stmt = stmt.where(LlmUsageSource.source_id.in_(configured_source_ids))
    return db.scalars(stmt).all()


def _values_from_snapshot(snapshot: LlmUsageSnapshot, source: LlmUsageSource, lab_timezone: str) -> list[dict[str, Any]]:
    return _values_from_observation(
        source_id=source.id,
        source_type=source.source_type,
        collected_at=snapshot.collected_at,
        request_count=snapshot.request_count,
        token_count=snapshot.token_count,
        quota_used=snapshot.quota_used,
        estimated_amount=snapshot.estimated_amount,
        model_stats=snapshot.model_stats or [],
        raw_summary=snapshot.raw_summary or {},
        lab_timezone=lab_timezone,
    )


def _values_from_observation(
    *,
    source_id: int,
    source_type: str,
    collected_at: datetime,
    request_count: float | None,
    token_count: float | None,
    quota_used: float | None,
    estimated_amount: float | None,
    model_stats: list[dict[str, Any]],
    raw_summary: dict[str, Any],
    lab_timezone: str,
    target_date: date | None = None,
) -> list[dict[str, Any]]:
    if source_type == "deepseek_platform":
        return _deepseek_values(
            source_id,
            collected_at,
            raw_summary,
            lab_timezone,
            request_count,
            token_count,
            estimated_amount,
            target_date,
        )
    if source_type == "newapi_admin":
        return _newapi_values(
            source_id,
            collected_at,
            raw_summary,
            lab_timezone,
            request_count,
            token_count,
            quota_used,
            estimated_amount,
            model_stats,
            target_date,
        )
    if source_type == "openai_gateway":
        return _gateway_values(source_id, collected_at, model_stats, request_count, token_count, estimated_amount, lab_timezone)
    return []


def _newapi_values(
    source_id: int,
    collected_at: datetime,
    raw_summary: dict[str, Any],
    lab_timezone: str,
    request_count: float | None,
    token_count: float | None,
    quota_used: float | None,
    estimated_amount: float | None,
    model_stats: list[dict[str, Any]],
    target_date: date | None = None,
) -> list[dict[str, Any]]:
    usage_date = target_date or _local_date(collected_at, _zone(lab_timezone))
    stat = raw_summary.get("stat") if isinstance(raw_summary.get("stat"), dict) else {}
    stat_has_count = _first_number(stat, ("count", "request_count", "total_count")) is not None
    stat_has_tokens = _first_number(stat, ("token", "tokens", "token_count", "total_tokens")) is not None
    stat_has_quota = _first_number(stat, ("quota", "used_quota", "quota_used", "amount")) is not None
    buckets = _newapi_buckets(raw_summary)
    trusted_buckets = [bucket for bucket in buckets if _trusted_bucket(bucket)]
    bucket_requests = sum(_number(bucket.get("request_count")) or 0 for bucket in trusted_buckets)
    sampled_tokens = sum(_number(bucket.get("input_tokens")) or 0 for bucket in trusted_buckets) + sum(
        _number(bucket.get("output_tokens")) or 0 for bucket in trusted_buckets
    )
    bucket_amount = sum(_number(bucket.get("amount")) or 0 for bucket in trusted_buckets)
    bucket_cost = sum(_number(bucket.get("estimated_cost_usd")) or 0 for bucket in trusted_buckets)
    if not stat_has_count and trusted_buckets:
        request_count = bucket_requests
    if not stat_has_tokens and trusted_buckets:
        token_count = sampled_tokens
    if not stat_has_quota and trusted_buckets:
        quota_used = bucket_amount
        estimated_amount = bucket_cost
    quality = "complete" if stat_has_tokens else "sampled" if trusted_buckets else "unavailable"
    total = _value(
        source_id=source_id,
        usage_date=usage_date,
        model=TOTAL_MODEL,
        request_count=request_count,
        token_count=token_count,
        estimated_amount=quota_used,
        estimated_cost_usd=estimated_amount,
        currency="USD",
        token_complete=quality == "complete",
        data_quality=quality,
        observed_at=collected_at,
    )
    values = [total]
    model_values: dict[tuple[date, str], dict[str, Any]] = {}
    for bucket in trusted_buckets:
        model = str(bucket.get("model") or "unknown")
        bucket_date = _local_date(bucket.get("timestamp") or collected_at, _zone(lab_timezone))
        if target_date is not None and bucket_date != target_date:
            continue
        key = (bucket_date, model)
        item = model_values.setdefault(
            key,
            _value(
                source_id=source_id,
                usage_date=bucket_date,
                model=model,
                request_count=0,
                token_count=0,
                input_tokens=0,
                output_tokens=0,
                estimated_amount=0,
                estimated_cost_usd=0,
                currency="USD",
                token_complete=True,
                data_quality="sampled",
                observed_at=collected_at,
            ),
        )
        item["request_count"] += _number(bucket.get("request_count")) or 0
        item["input_tokens"] += _number(bucket.get("input_tokens")) or 0
        item["output_tokens"] += _number(bucket.get("output_tokens")) or 0
        item["token_count"] += (_number(bucket.get("input_tokens")) or 0) + (_number(bucket.get("output_tokens")) or 0)
        item["estimated_amount"] += _number(bucket.get("amount")) or 0
        item["estimated_cost_usd"] += _number(bucket.get("estimated_cost_usd")) or 0
    if not model_values:
        for item in model_stats:
            model = str(item.get("model") or "unknown")
            values.append(
                _value(
                    source_id=source_id,
                    usage_date=usage_date,
                    model=model,
                    request_count=_number(item.get("request_count")),
                    token_count=_number(item.get("token_count")),
                    input_tokens=_number(item.get("input_tokens")),
                    output_tokens=_number(item.get("output_tokens")),
                    estimated_amount=_number(item.get("amount")),
                    estimated_cost_usd=_number(item.get("estimated_cost_usd")),
                    currency="USD",
                    token_complete=quality == "complete",
                    data_quality=quality,
                    observed_at=collected_at,
                )
            )
    else:
        values.extend(model_values.values())
    for item in values:
        for key in ("request_count", "token_count", "input_tokens", "output_tokens", "estimated_amount", "estimated_cost_usd"):
            if item.get(key) is not None:
                item[key] = round(item[key], 6)
    return values


def _deepseek_values(
    source_id: int,
    collected_at: datetime,
    raw_summary: dict[str, Any],
    lab_timezone: str,
    request_count: float | None,
    token_count: float | None,
    estimated_amount: float | None,
    target_date: date | None = None,
) -> list[dict[str, Any]]:
    platform = raw_summary.get("deepseek_platform") if isinstance(raw_summary.get("deepseek_platform"), dict) else {}
    currency = str(platform.get("currency") or "CNY")
    daily = platform.get("daily") if isinstance(platform.get("daily"), list) else []
    values = []
    for item in daily:
        if not isinstance(item, dict):
            continue
        usage_date = _local_date(item.get("time") or collected_at, _zone(lab_timezone))
        if target_date is not None and usage_date != target_date:
            continue
        values.append(
            _value(
                source_id=source_id,
                usage_date=usage_date,
                model=TOTAL_MODEL,
                request_count=_number(item.get("request_count")),
                token_count=_number(item.get("token_count")),
                input_tokens=_number(item.get("input_tokens")),
                output_tokens=_number(item.get("output_tokens")),
                estimated_amount=_number(item.get("amount")),
                estimated_cost_usd=_number(item.get("amount")),
                currency=currency,
                token_complete=True,
                data_quality="complete",
                observed_at=collected_at,
            )
        )
        models = item.get("models") if isinstance(item.get("models"), list) else []
        for model in models:
            if not isinstance(model, dict):
                continue
            values.append(
                _value(
                    source_id=source_id,
                    usage_date=usage_date,
                    model=str(model.get("model") or "unknown"),
                    request_count=_number(model.get("request_count")),
                    token_count=_number(model.get("token_count")),
                    input_tokens=_number(model.get("input_tokens")),
                    output_tokens=_number(model.get("output_tokens")),
                    estimated_amount=_number(model.get("amount")),
                    estimated_cost_usd=_number(model.get("amount")),
                    currency=currency,
                    token_complete=_number(model.get("token_count")) is not None,
                    data_quality="complete" if _number(model.get("token_count")) is not None else "unavailable",
                    observed_at=collected_at,
                )
            )
    if values:
        return values
    return [
        _value(
            source_id=source_id,
            usage_date=target_date or _local_date(collected_at, _zone(lab_timezone)),
            model=TOTAL_MODEL,
            request_count=request_count,
            token_count=token_count,
            estimated_amount=estimated_amount,
            estimated_cost_usd=estimated_amount,
            currency=currency,
            token_complete=token_count is not None,
            data_quality="complete" if token_count is not None else "unavailable",
            observed_at=collected_at,
        )
    ]


def _gateway_values(
    source_id: int,
    collected_at: datetime,
    model_stats: list[dict[str, Any]],
    request_count: float | None,
    token_count: float | None,
    estimated_amount: float | None,
    lab_timezone: str,
) -> list[dict[str, Any]]:
    usage_date = _local_date(collected_at, _zone(lab_timezone))
    values = []
    model_tokens = 0.0
    model_requests = 0.0
    model_amount = 0.0
    has_model_tokens = False
    has_model_requests = False
    has_model_amount = False
    for item in model_stats:
        item_tokens = _number(item.get("token_count"))
        item_requests = _number(item.get("request_count"))
        item_amount = _number(item.get("estimated_cost_usd"))
        if item_tokens is not None:
            model_tokens += item_tokens
            has_model_tokens = True
        if item_requests is not None:
            model_requests += item_requests
            has_model_requests = True
        if item_amount is not None:
            model_amount += item_amount
            has_model_amount = True
        values.append(
            _value(
                source_id=source_id,
                usage_date=usage_date,
                model=str(item.get("model") or "unknown"),
                request_count=item_requests,
                token_count=item_tokens,
                input_tokens=_number(item.get("input_tokens")),
                output_tokens=_number(item.get("output_tokens")),
                estimated_amount=item_amount,
                estimated_cost_usd=item_amount,
                currency="USD",
                token_complete=item_tokens is not None,
                data_quality="complete" if item_tokens is not None else "unavailable",
                observed_at=collected_at,
            )
        )
    total_tokens = token_count if token_count is not None else model_tokens if has_model_tokens else None
    total_requests = request_count if request_count is not None else model_requests if has_model_requests else None
    total_amount = estimated_amount if estimated_amount is not None else model_amount if has_model_amount else None
    values.insert(
        0,
        _value(
            source_id=source_id,
            usage_date=usage_date,
            model=TOTAL_MODEL,
            request_count=total_requests,
            token_count=total_tokens,
            estimated_amount=total_amount,
            estimated_cost_usd=total_amount,
            currency="USD",
            token_complete=total_tokens is not None,
            data_quality="complete" if total_tokens is not None else "unavailable",
            observed_at=collected_at,
        ),
    )
    return values


def _upsert_value(db: Session, value: dict[str, Any], *, replace: bool) -> None:
    row = db.scalar(
        select(LlmUsageDaily).where(
            LlmUsageDaily.source_id == value["source_id"],
            LlmUsageDaily.usage_date == value["usage_date"],
            LlmUsageDaily.model == value["model"],
        )
    )
    if row is None:
        row = LlmUsageDaily(**value)
        db.add(row)
        db.flush()
        return
    if replace:
        if _quality_rank(value["data_quality"]) < _quality_rank(row.data_quality):
            return
        for key, item in value.items():
            if key != "source_id":
                setattr(row, key, item)
        return
    for key in ("request_count", "token_count", "input_tokens", "output_tokens", "estimated_amount", "estimated_cost_usd"):
        current = getattr(row, key)
        incoming = value.get(key)
        if current is not None or incoming is not None:
            setattr(row, key, (current or 0) + (incoming or 0))
    row.token_complete = row.token_complete and value["token_complete"]
    row.data_quality = _worst_quality(row.data_quality, value["data_quality"])
    row.observed_at = max(row.observed_at, value["observed_at"])


def _value(**values: Any) -> dict[str, Any]:
    values.setdefault("request_count", None)
    values.setdefault("token_count", None)
    values.setdefault("input_tokens", None)
    values.setdefault("output_tokens", None)
    values.setdefault("estimated_amount", None)
    values.setdefault("estimated_cost_usd", None)
    values.setdefault("currency", None)
    values.setdefault("token_complete", False)
    values.setdefault("data_quality", "unavailable")
    return values


def _newapi_buckets(raw_summary: dict[str, Any]) -> list[dict[str, Any]]:
    newapi = raw_summary.get("newapi") if isinstance(raw_summary.get("newapi"), dict) else {}
    buckets = newapi.get("buckets")
    return [item for item in buckets if isinstance(item, dict)] if isinstance(buckets, list) else []


def _trusted_bucket(bucket: dict[str, Any]) -> bool:
    return "input_tokens" in bucket or "output_tokens" in bucket


def _first_number(value: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        number = _number(value.get(key))
        if number is not None:
            return number
    return None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _local_date(value: Any, zone: ZoneInfo) -> date:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(zone).date()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone).date()


def _worst_quality(left: str, right: str) -> str:
    order = {"complete": 0, "sampled": 1, "unavailable": 2}
    return left if order.get(left, 2) >= order.get(right, 2) else right


def _quality_rank(value: str) -> int:
    return {"unavailable": 0, "sampled": 1, "complete": 2}.get(value, 0)
