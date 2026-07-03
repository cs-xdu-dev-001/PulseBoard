# PulseBoard MVP Design

## Goal

PulseBoard MVP is a personal GPU monitoring dashboard. Its first version monitors the existing lab resource API, shows which A100 GPUs are available, stores 30 days of history, and leaves VPS monitoring plus LLM/Agent tracing for later.

## Scope

In scope:
- Pull data from `http://100.64.0.14:8080/api/latest` every 15 seconds.
- Parse server, CPU, memory, disk, GPU utilization, and GPU memory fields.
- Store raw snapshots and normalized metrics in MySQL.
- Use Alembic for database schema migrations.
- Expose dashboard APIs for current state and 1h/24h history.
- Build a dark, glowing dashboard where available GPUs are visually prominent.
- Run locally on Windows during development and via Docker Compose for deployment.

Out of scope:
- VPS agent collection.
- Login and user management.
- External notifications.
- Multiple data source management UI.
- LLM/Agent tracing.
- Production domain and HTTPS automation.

## Architecture

```text
Lab GPU API /api/latest
  -> FastAPI APScheduler collector
  -> normalizer + availability rules
  -> MySQL via SQLAlchemy
  -> Dashboard REST API
  -> React/Vite/ECharts frontend
```

FastAPI owns collection and API serving in one process for MVP. Production should run one Uvicorn worker to avoid duplicate scheduled collection. The data source URL is configurable through `.env`.

## Data Source

The source endpoint returns JSON containing a `servers` array. Each server may contain:
- `name`
- `resource_metrics.status`
- `resource_metrics.cpu`
- `resource_metrics.memory.percentage`
- `resource_metrics.memory.total_mb`
- `resource_metrics.memory.used_mb`
- `resource_metrics.gpu[]`
- `disk_metrics.disk`

Each GPU record may contain:
- `index`
- `name`
- `utilization`
- `memory_total_mb`
- `memory_used_mb`

## GPU Availability

Sampling interval is 15 seconds. A GPU is available only when the latest 6 samples, about 90 seconds, all satisfy:
- `utilization < 20`
- `memory_used_mb < 5000`

Status labels:
- `available`: latest 6 samples satisfy the rule.
- `busy`: utilization or memory exceeds the available threshold.
- `saturated`: utilization is at least 90 or memory usage is at least 80%.
- `unknown`: fewer than 6 samples, missing data, or source unavailable.
- `offline`: the machine is disconnected while the data source is reachable.

## Failure Semantics

Source collection failures are distinct from machine offline states.

- 0-2 consecutive failures: keep showing the last successful data.
- 3-11 consecutive failures: source status is `degraded`, show stale data.
- 12 or more consecutive failures: source status is `unreachable`, mark GPU availability as unknown while preserving last successful data.
- If the source is reachable and a server reports `status: disconnected`, that server is offline.

## Storage

Database: MySQL, database name `pulseboard`.

Retention:
- Keep raw snapshots and normalized metrics for 30 days.
- Cleanup runs in the same scheduled job after successful collection.

Tables:
- `data_sources`: configured pull sources and consecutive failure counts.
- `raw_snapshots`: raw JSON payloads or error metadata.
- `machines`: server identity and latest status.
- `machine_metrics`: CPU, memory, and disk JSON metrics over time.
- `gpus`: GPU identity per machine.
- `gpu_metrics`: utilization, memory, and computed availability over time.

Time handling:
- Store timestamps in UTC.
- Frontend displays local time.

## API Contract

- `GET /api/health`: backend, database, scheduler, and source status.
- `GET /api/dashboard/current`: source status, machine cards, GPU cards, and summary.
- `GET /api/gpus`: current GPU list.
- `GET /api/machines`: current machine list.
- `GET /api/history/gpus?range=1h|24h`: utilization and memory time series.
- `GET /api/history/machines?range=1h|24h`: CPU, memory, and disk time series.

Frontend never connects directly to MySQL.

## Frontend Direction

Frontend stack: React + Vite + ECharts.

Visual direction:
- Dark background.
- Electric blue, magenta, and fluorescent green accents.
- Available GPUs use strong green glow.
- Busy GPUs use restrained cyan/blue glow.
- Saturated GPUs use magenta/red warning edge glow.
- Unknown and offline cards are muted.
- Numeric text uses high contrast and tabular alignment.
- Charts use dark grid lines and readable solid labels.

Home layout:
- Top status strip with source health and summary counts.
- GPU-first card grid sorted by availability.
- Machine status section below.
- 1h/24h chart panels for GPU and machine history.

## Packaging

Development:
- Backend runs in Python virtual environment.
- Frontend runs through Vite dev server.
- MySQL can use the user's local MySQL/Navicat setup.

Deployment:
- Docker Compose runs backend, frontend static server, and optionally MySQL.
- Backend image runs FastAPI with one Uvicorn worker.
- Frontend is built into static files served by Nginx.

