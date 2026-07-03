from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.collector import collect_once
from app.config import get_settings
from app.db import SessionLocal
from app.llm_usage_collector import collect_llm_usage_once
from app.node_collector import collect_nodes_once
from app.routes import router


def run_collection_job() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        collect_once(db, settings)


def run_node_collection_job() -> None:
    settings = get_settings()
    if not settings.node_exporters.strip():
        return
    with SessionLocal() as db:
        collect_nodes_once(db, settings)


def run_llm_usage_collection_job() -> None:
    settings = get_settings()
    if not settings.llm_usage_sources.strip():
        return
    with SessionLocal() as db:
        collect_llm_usage_once(db, settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler: BackgroundScheduler | None = None
    settings = get_settings()
    if settings.collector_enabled:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            run_collection_job,
            "interval",
            seconds=settings.collection_interval_seconds,
            id="lab-gpu-collector",
            max_instances=1,
            coalesce=True,
        )
        if settings.node_exporters.strip():
            scheduler.add_job(
                run_node_collection_job,
                "interval",
                seconds=settings.node_exporter_interval_seconds,
                id="node-exporter-collector",
                max_instances=1,
                coalesce=True,
            )
        if settings.llm_usage_sources.strip():
            scheduler.add_job(
                run_llm_usage_collection_job,
                "interval",
                seconds=settings.llm_usage_interval_seconds,
                id="llm-usage-collector",
                max_instances=1,
                coalesce=True,
            )
        scheduler.start()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="PulseBoard API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
