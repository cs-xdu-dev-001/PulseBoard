# PulseBoard VPS Node Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add node_exporter-based VPS monitoring, one VPS traffic quota card, and fix lab GPU timestamp timezone handling.

**Architecture:** FastAPI runs two collectors: lab GPU pull every 15 seconds and node_exporter pull every 30 seconds. Parsed VPS metrics are stored in new SQLAlchemy tables via Alembic. React dashboard consumes expanded current/history APIs.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, httpx, APScheduler, pytest, React, Vite, ECharts.

---

## Tasks

### Task 1: Tests

**Files:**
- Create: `backend/tests/test_node_exporter.py`
- Update: `backend/tests/test_normalizer.py`

- [ ] Test Prometheus text parsing.
- [ ] Test node_exporter normalization for CPU, memory, disk, network, load, uptime.
- [ ] Test traffic quota calculation for `vpn-gateway`.
- [ ] Test naive lab timestamps are interpreted as Asia/Shanghai.

### Task 2: Backend Domain

**Files:**
- Create: `backend/app/node_exporter.py`
- Create: `backend/app/node_collector.py`
- Update: `backend/app/config.py`
- Update: `backend/app/models.py`
- Update: `backend/app/normalizer.py`

- [ ] Add node_exporter target and traffic quota settings.
- [ ] Add models for VPS nodes and VPS metrics.
- [ ] Implement parser, normalizer, and quota calculation.
- [ ] Add second APScheduler job.

### Task 3: Migration And API

**Files:**
- Add: `backend/alembic/versions/20260702_0002_vps_metrics.py`
- Update: `backend/app/routes.py`
- Update: `backend/tests/test_routes.py`

- [ ] Add migration for VPS tables.
- [ ] Extend current dashboard response with `vps_nodes`.
- [ ] Add `GET /api/history/vps?range=1h|24h`.

### Task 4: Frontend

**Files:**
- Update: `frontend/src/App.jsx`
- Update: `frontend/src/api.js`
- Add: `frontend/src/components/VpsCard.jsx`
- Update: `frontend/src/components/HistoryChart.jsx`
- Update: `frontend/src/styles.css`

- [ ] Add unified summary fields.
- [ ] Add VPS monitoring section.
- [ ] Add VPS history charts including network and traffic quota.

### Task 5: Local Scripts And Verification

**Files:**
- Update: `.env.example`
- Update: `scripts/setup-local.ps1`
- Update: `README.md`

- [ ] Add node_exporter and traffic quota configuration.
- [ ] Run backend tests.
- [ ] Run frontend build.
- [ ] Run PowerShell script syntax check.

