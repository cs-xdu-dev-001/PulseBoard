# PulseBoard VPS 监控设计

## 目标

通过标准 `node_exporter` 采集 VPS 性能指标，在 PulseBoard 中展示 VPS 健康状态、网络速率和 VPN 流量配额。

## 范围

包含：

- 从 `.env` 配置 node_exporter 目标。
- 每 30 秒采集 CPU、内存、磁盘、网络、Load、Uptime。
- 对一个指定 VPS 统计每月流量配额。
- 将 VPS 卡片和历史曲线接入 Infra 页面。

不包含：

- 自定义 agent。
- SSH 采集。
- node_exporter 自动安装。
- 告警。

## 配置示例

```env
PULSEBOARD_NODE_EXPORTERS=vpn-gateway=http://YOUR_VPN_VPS_IP:9100,app-server=http://YOUR_APP_SERVER_IP:9100
PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS=30
PULSEBOARD_TRAFFIC_QUOTA_NODE=vpn-gateway
PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB=250
PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB=0
PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY=18
```

## 指标口径

- CPU：根据 `node_cpu_seconds_total` 的采样差值计算。
- 内存：使用 `MemTotal - MemAvailable`。
- 磁盘：过滤虚拟文件系统，只保留真实挂载点。
- 网络：过滤 `lo`、Docker、veth、tun、tap 等接口。
- 流量配额：按服务商常用十进制 GB 计算，`1 GB = 1,000,000,000 bytes`。

## 状态规则

- `offline`：node_exporter 不可达。
- `critical`：CPU > 90%、内存 > 90%、任一真实磁盘 > 85%。
- `online`：可达且未触发异常阈值。
