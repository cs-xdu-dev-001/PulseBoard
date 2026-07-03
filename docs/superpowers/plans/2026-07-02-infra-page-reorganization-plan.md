# Infra Page Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the crowded Infra page into Overview, GPU, VPS, and Machines subviews.

**Architecture:** Keep the existing API and card components. Refactor `frontend/src/App.jsx` so `InfraView` owns an internal tab state and renders focused sections. Add CSS for the subnav and compact overview cards.

**Tech Stack:** React, Vite, ECharts, existing CSS.

---

### Task 1: Refactor Infra View

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`

- [ ] Add `infraTab` state inside `InfraView`.
- [ ] Render a secondary segmented control: Overview, GPU, VPS, Machines.
- [ ] Move the full GPU list and GPU history charts into the GPU tab.
- [ ] Move the full VPS list and VPS history charts into the VPS tab.
- [ ] Move machine cards and machine history into the Machines tab.
- [ ] Keep Overview focused on key metrics and a small number of attention cards.
- [ ] Run `npm run build`.
