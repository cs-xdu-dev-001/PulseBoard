# PulseBoard MVP 设计

## 目标

第一版用于个人监控实验室 GPU。系统定时拉取实验室 GPU API，写入 MySQL，并在前端突出显示可上机的 GPU。

## 范围

包含：

- 从 `.env` 中配置 GPU API 地址。
- 每 15 秒采集一次 GPU、CPU、内存、磁盘信息。
- 保存原始快照和归一化指标。
- 使用 Alembic 管理数据库迁移。
- 提供当前状态和 1h/24h 历史接口。
- 前端使用暗色发光风格，优先展示可用 GPU。

不包含：

- 登录和多用户。
- 告警。
- LLM 追踪。
- 生产域名和 HTTPS 自动化。

## 配置示例

```env
PULSEBOARD_SOURCE_URL=http://YOUR_GPU_API_HOST:PORT/api/latest
PULSEBOARD_COLLECTION_INTERVAL_SECONDS=15
PULSEBOARD_RETENTION_DAYS=30
```

## GPU 空闲规则

某张 GPU 连续 6 次采样都满足：

- GPU 利用率 `< 20%`
- 显存占用 `< 5000 MB`

才标记为可上机。

## 存储

数据库使用 MySQL，数据保留 30 天。

主要表：

- `data_sources`
- `raw_snapshots`
- `machines`
- `machine_metrics`
- `gpus`
- `gpu_metrics`

时间统一存 UTC，前端按本地时区显示。
