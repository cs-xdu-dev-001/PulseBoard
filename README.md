# PulseBoard

PulseBoard is a personal GPU monitoring dashboard. The MVP pulls lab GPU metrics from a JSON endpoint, stores 30 days of MySQL history, and highlights available A100 GPUs.

## MVP Defaults

- Backend: FastAPI + SQLAlchemy + Alembic
- Database: MySQL, database name `pulseboard`
- Collector: APScheduler, every 15 seconds
- Source: `http://100.64.0.14:8080/api/latest`
- VPS monitoring: node_exporter, every 30 seconds
- Frontend: React + Vite + ECharts
- Local run: Windows PowerShell scripts

## Local Setup, No Docker

```powershell
.\scripts\setup-local.ps1
```

The script asks for your local MySQL password, writes `.env`, creates the `pulseboard` database, installs backend/frontend dependencies, and runs Alembic migrations.

You can also pass values explicitly:

```powershell
.\scripts\setup-local.ps1 -DbHost 127.0.0.1 -DbPort 3306 -DbUser root -DbPassword "your-password" -Database pulseboard
```

Configure VPS node_exporter targets in `.env`:

```text
PULSEBOARD_NODE_EXPORTERS=vpn-gateway=http://YOUR_VPS_IP:9100,vps-us=http://OTHER_VPS_IP:9100
```

If this value is empty, VPS collection is disabled and the GPU dashboard still works.

Install node_exporter on a Linux VPS using your preferred package manager or the official release binary, then expose `:9100/metrics` to the PulseBoard host only.

Traffic quota is tracked for `vpn-gateway`:

```text
PULSEBOARD_TRAFFIC_QUOTA_NODE=vpn-gateway
PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB=250
PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB=71.23
PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY=18
```

node_exporter should be reachable from the machine running PulseBoard. Prefer firewall rules that allow only the PulseBoard host to access port `9100`.

## Start Locally

```powershell
.\scripts\start-local.ps1
```

Then open:

```text
http://127.0.0.1:5173
```

Backend only:

```powershell
.\scripts\run-backend.ps1
```

Frontend only:

```powershell
.\scripts\run-frontend.ps1
```

Check local prerequisites:

```powershell
.\scripts\check-local.ps1
```

## Tests

```powershell
cd backend
.\.venv\Scripts\pytest
```

## API

- `GET /api/health`
- `GET /api/dashboard/current`
- `GET /api/gpus`
- `GET /api/machines`
- `GET /api/history/gpus?range=1h|24h`
- `GET /api/history/machines?range=1h|24h`
- `GET /api/history/vps?range=1h|24h`
- `GET /api/llm/usage/sources`
- `GET /api/llm/usage/summary?range=today|24h|7d`
- `GET /api/llm/usage/series?range=today|24h|7d`
- `GET /api/llm/usage/models?range=today|24h|7d`
- `POST /api/llm/usage/refresh`

## LLM Usage Dashboard

Configure LLM usage sources in `.env`:

```text
PULSEBOARD_LLM_USAGE_SOURCES=academic
PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS=300
PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin
PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic Gateway
PULSEBOARD_LLM_ACADEMIC_BASE_URL=https://academicedu.me
PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=your-new-api-access-token
PULSEBOARD_LLM_ACADEMIC_USER_ID=1
```

Optional DeepSeek balance source:

```text
PULSEBOARD_LLM_USAGE_SOURCES=academic,deepseek
PULSEBOARD_LLM_DEEPSEEK_TYPE=deepseek_balance
PULSEBOARD_LLM_DEEPSEEK_DISPLAY_NAME=DeepSeek Official
PULSEBOARD_LLM_DEEPSEEK_API_KEY=your-deepseek-api-key
```
