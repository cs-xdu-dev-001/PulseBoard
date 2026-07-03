# PulseBoard LLM Usage Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an LLM balance and usage dashboard that polls DeepSeek balance and New API admin statistics.

**Architecture:** Add focused backend modules for provider config, collectors, normalizers, and routes. Store current source state and periodic snapshots in MySQL, then add a tabbed frontend with an LLM usage page.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, APScheduler, httpx, React, ECharts, MySQL.

---

### Task 1: Database And Config

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/20260702_0003_llm_usage.py`
- Test: `backend/tests/test_llm_usage_config.py`

- [ ] Add LLM usage config fields:
  - `llm_usage_sources`
  - `llm_usage_interval_seconds`
  - dynamic source config lookup through environment variables.
- [ ] Add `LlmUsageSource` and `LlmUsageSnapshot` models.
- [ ] Add Alembic migration creating `llm_usage_sources` and `llm_usage_snapshots`.
- [ ] Test source ID normalization and config loading.

### Task 2: Collectors And Normalizers

**Files:**
- Create: `backend/app/llm_usage.py`
- Create: `backend/app/llm_usage_collector.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_llm_usage.py`

- [ ] Implement source parsing from `.env`.
- [ ] Implement DeepSeek `/user/balance` fetch and normalization.
- [ ] Implement New API admin fetch with tolerant parsing for dashboard/stat/log/channel responses.
- [ ] Implement snapshot persistence and source status updates.
- [ ] Add APScheduler job controlled by `PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS`.

### Task 3: Backend API

**Files:**
- Modify: `backend/app/routes.py`
- Test: `backend/tests/test_llm_usage_routes.py`

- [ ] Add `GET /api/llm/usage/sources`.
- [ ] Add `GET /api/llm/usage/summary?range=today|24h|7d&source=`.
- [ ] Add `GET /api/llm/usage/series?range=today|24h|7d&source=`.
- [ ] Add `GET /api/llm/usage/models?range=today|24h|7d&source=`.
- [ ] Add `POST /api/llm/usage/refresh`.
- [ ] Ensure no secret fields are returned.

### Task 4: Frontend LLM Tab

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/api.js`
- Create: `frontend/src/components/LlmUsageView.jsx`
- Modify: `frontend/src/styles.css`

- [ ] Add top-level `Infra` / `LLM` tabs.
- [ ] Move current dashboard content under `Infra`.
- [ ] Add LLM source cards, summary cards, charts, model table, range/provider/status controls, and manual refresh.
- [ ] Keep dark glow visual language consistent with existing dashboard.

### Task 5: Local Config And Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] Document DeepSeek and New API `.env` fields.
- [ ] Add local config examples without real secrets.
- [ ] Run backend tests, Alembic SQL generation, frontend build, and API smoke checks.
