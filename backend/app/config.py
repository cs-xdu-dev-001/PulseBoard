from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://root:password@127.0.0.1:3306/pulseboard?charset=utf8mb4"
    source_url: str = "http://100.64.0.14:8080/api/latest"
    collection_interval_seconds: int = 15
    retention_days: int = 30
    failure_degraded_threshold: int = 3
    failure_unreachable_threshold: int = 12
    collector_enabled: bool = True
    lab_timezone: str = "Asia/Shanghai"
    node_exporters: str = ""
    node_exporter_interval_seconds: int = 30
    traffic_quota_node: str = "vpn-gateway"
    traffic_quota_total_gb: float = 250.0
    traffic_quota_initial_used_gb: float = 71.23
    traffic_quota_reset_day: int = 18
    llm_usage_sources: str = ""
    llm_usage_interval_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_prefix="PULSEBOARD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
