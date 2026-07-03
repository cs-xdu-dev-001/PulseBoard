# Settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a lightweight Settings page that edits PulseBoard `.env` configuration for personal use.

**Architecture:** Backend exposes `/api/settings` for masked config read and selected `.env` writes. Frontend adds a top-level Settings tab with simple forms for General, GPU, VPS, and LLM source basics.

**Tech Stack:** FastAPI, pydantic, React, Vite, existing CSS.

---

### Task 1: Backend Settings API

**Files:**
- Create: `backend/app/settings_config.py`
- Modify: `backend/app/routes.py`
- Test: `backend/tests/test_settings_config.py`

- [ ] Add tests for reading masked settings and writing `.env`.
- [ ] Implement `.env` read/write helpers and allowed setting keys.
- [ ] Add `GET /api/settings` and `POST /api/settings`.
- [ ] Clear FastAPI settings cache after saving.

### Task 2: Frontend Settings Page

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Create: `frontend/src/components/SettingsView.jsx`
- Modify: `frontend/src/styles.css`

- [ ] Add API helpers.
- [ ] Add top-level Settings tab.
- [ ] Render grouped forms.
- [ ] Save changes through `/api/settings`.
- [ ] Run backend tests and frontend build.
