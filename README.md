# PulseBoard

PulseBoard 是一个个人用的资源监控看板，用来查看服务器 GPU、VPS 状态、VPN 流量配额，以及 LLM 账户余额和用量。

## 功能

- 服务器 GPU 可用性监控
- VPS CPU、内存、磁盘、网络、流量配额监控
- LLM 余额、调用量、费用估算
- Infra / LLM / Settings 三个页面
- 本地 Windows 开发，后续可迁移到 Linux VPS

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic、APScheduler
- 数据库：MySQL
- 前端：React、Vite、ECharts
- 采集：HTTP 拉取 GPU API、Prometheus node_exporter、LLM 管理接口

## 本地启动

先复制配置：

```powershell
copy .env.example .env
```

编辑 `.env`，把占位符替换成自己的地址、数据库和密钥。

初始化本地环境：

```powershell
.\scripts\setup-local.ps1
```

启动：

```powershell
.\scripts\start-local.ps1
```

打开：

```text
http://127.0.0.1:5173
```

## 配置说明

所有运行配置都在 `.env`，也可以在页面顶部的 `Settings` 中修改。

### GPU 数据源

```env
PULSEBOARD_SOURCE_URL=http://YOUR_GPU_API_HOST:PORT/api/latest
```

### VPS 监控

```env
PULSEBOARD_NODE_EXPORTERS=vpn-gateway=http://YOUR_VPN_VPS_IP:9100,app-server=http://YOUR_APP_SERVER_IP:9100
PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS=30
```

流量配额：

```env
PULSEBOARD_TRAFFIC_QUOTA_NODE=vpn-gateway
PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB=250
PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB=0
PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY=18
```

### LLM 用量

New API / 中转站：

```env
PULSEBOARD_LLM_USAGE_SOURCES=academic
PULSEBOARD_LLM_ACADEMIC_TYPE=newapi_admin
PULSEBOARD_LLM_ACADEMIC_DISPLAY_NAME=Academic Gateway
PULSEBOARD_LLM_ACADEMIC_BASE_URL=https://YOUR_NEW_API_DOMAIN
PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN=
PULSEBOARD_LLM_ACADEMIC_USER_ID=1
```

DeepSeek 余额：

```env
PULSEBOARD_LLM_USAGE_SOURCES=academic,deepseek
PULSEBOARD_LLM_DEEPSEEK_TYPE=deepseek_balance
PULSEBOARD_LLM_DEEPSEEK_DISPLAY_NAME=DeepSeek
PULSEBOARD_LLM_DEEPSEEK_API_KEY=
```

## 测试

后端：

```powershell
cd backend
.\.venv\Scripts\pytest
```

前端：

```powershell
cd frontend
npm run build
```

## 部署建议

个人使用建议直接部署到一台 VPS：

- FastAPI 后端用 systemd 跑在 `127.0.0.1:8000`
- 前端 `npm run build` 后用 Nginx 托管
- Nginx 反代 `/api/` 到后端
- MySQL 可以放同一台服务器

不要把 `.env` 提交到 Git。仓库里只保留 `.env.example`。
