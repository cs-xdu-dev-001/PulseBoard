# PulseBoard MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the PulseBoard MVP for pulling lab GPU metrics, storing them in MySQL, exposing dashboard APIs, and rendering a dark glowing GPU-first dashboard.

**Architecture:** FastAPI runs the REST API and an APScheduler collector in one process. SQLAlchemy models and Alembic migrations manage MySQL tables. React/Vite/ECharts consumes only backend APIs.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PyMySQL, APScheduler, pytest, React, Vite, ECharts, Docker Compose.

---

## File Structure

- `backend/app/config.py`: environment-driven settings.
- `backend/app/db.py`: SQLAlchemy engine/session.
- `backend/app/models.py`: database tables.
- `backend/app/normalizer.py`: source JSON parsing.
- `backend/app/availability.py`: GPU status logic.
- `backend/app/collector.py`: pull source, persist metrics, cleanup.
- `backend/app/routes.py`: dashboard REST API.
- `backend/app/main.py`: FastAPI app and scheduler lifecycle.
- `backend/alembic/*`: database migrations.
- `backend/tests/*`: unit and API tests.
- `frontend/src/*`: dashboard app.
- `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`: packaging.

## Tasks

### Task 1: Project Scaffolding

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `frontend/package.json`
- Create: `frontend/index.html`

- [ ] Create root docs and dependency manifests.
- [ ] Verify `python -m compileall backend/app` can discover the package.

### Task 2: Backend Models And Migrations

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260702_0001_initial_schema.py`

- [ ] Define settings for MySQL URL, source URL, collection interval, retention days, and failure thresholds.
- [ ] Define SQLAlchemy models for data sources, raw snapshots, machines, machine metrics, GPUs, and GPU metrics.
- [ ] Add Alembic migration matching the models.
- [ ] Verify migration files import without syntax errors.

### Task 3: Parsing And Availability Tests

**Files:**
- Create: `backend/tests/test_normalizer.py`
- Create: `backend/tests/test_availability.py`
- Create: `backend/app/normalizer.py`
- Create: `backend/app/availability.py`

- [ ] Write tests for parsing the known `/api/latest` sample shape.
- [ ] Write tests for available, busy, saturated, unknown, and offline GPU states.
- [ ] Implement parser and availability functions.
- [ ] Run `pytest backend/tests/test_normalizer.py backend/tests/test_availability.py`.

### Task 4: Collector And API

**Files:**
- Create: `backend/app/collector.py`
- Create: `backend/app/routes.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_routes.py`

- [ ] Implement source fetch with timeout and raw snapshot persistence.
- [ ] Implement upsert for machines and GPUs, insert metric rows, and 30-day cleanup.
- [ ] Implement current dashboard and history query endpoints.
- [ ] Add API tests with an in-memory SQLite override for route behavior.

### Task 5: Frontend Dashboard

**Files:**
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/api.js`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/components/GpuCard.jsx`
- Create: `frontend/src/components/MachineCard.jsx`
- Create: `frontend/src/components/HistoryChart.jsx`
- Create: `frontend/vite.config.js`

- [ ] Build GPU-first dashboard using backend API contracts.
- [ ] Use dark glowing visual language with green emphasis for available GPUs.
- [ ] Add 1h/24h chart range toggle.
- [ ] Verify `npm run build`.

### Task 6: Packaging And Verification

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Create: `docker-compose.yml`
- Update: `README.md`

- [ ] Add Docker Compose for MySQL, backend, and frontend.
- [ ] Document local Windows development and production deployment.
- [ ] Run backend tests.
- [ ] Run frontend build.
- [ ] Run syntax checks for backend modules.

## Self-Review

- Spec coverage: all MVP items map to tasks above.
- Placeholders: no open TBD items are required for implementation; environment values are documented in `.env.example`.
- Type consistency: parser output, API fields, and frontend props use machine, GPU, metric, source status naming consistently.

