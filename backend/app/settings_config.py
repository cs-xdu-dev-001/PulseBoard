from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import ROOT_DIR


VALUE_KEYS = [
    "PULSEBOARD_DATABASE_URL",
    "PULSEBOARD_SOURCE_URL",
    "PULSEBOARD_COLLECTION_INTERVAL_SECONDS",
    "PULSEBOARD_RETENTION_DAYS",
    "PULSEBOARD_LAB_TIMEZONE",
    "PULSEBOARD_NODE_EXPORTERS",
    "PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS",
    "PULSEBOARD_TRAFFIC_QUOTA_NODE",
    "PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB",
    "PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB",
    "PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY",
    "PULSEBOARD_LLM_USAGE_SOURCES",
    "PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS",
]

WRITABLE_VALUE_KEYS = [
    key
    for key in VALUE_KEYS
    if key != "PULSEBOARD_LLM_USAGE_SOURCES"
]

SECRET_KEYS = [
    "PULSEBOARD_LLM_DEEPSEEK_API_KEY",
    "PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN",
]

WRITABLE_KEYS = set(WRITABLE_VALUE_KEYS + SECRET_KEYS)


def load_app_settings(env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    env = _read_env(env_path)
    return {
        "values": {key: env.get(key, "") for key in VALUE_KEYS},
        "secrets": {key: {"configured": bool(env.get(key))} for key in SECRET_KEYS},
    }


def save_app_settings(values: dict[str, Any], env_path: Path | None = None) -> dict[str, Any]:
    env_path = env_path or ROOT_DIR / ".env"
    updates: dict[str, str] = {}
    for key, value in values.items():
        if key not in WRITABLE_KEYS:
            continue
        text = str(value or "").strip()
        if key in SECRET_KEYS and not text:
            continue
        updates[key] = text
    _write_env(env_path, updates)
    return {"updated": sorted(updates)}


def _read_env(env_path: Path) -> dict[str, str]:
    result = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def _write_env(env_path: Path, updates: dict[str, str]) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen = set()
    next_lines = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            next_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
