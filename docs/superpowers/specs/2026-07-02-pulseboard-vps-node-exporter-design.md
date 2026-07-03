# PulseBoard MVP 2 Design

## Goal

Add Linux VPS monitoring to PulseBoard using standard `node_exporter` endpoints. PulseBoard will pull Prometheus metrics, store 30 days of history, show VPS status on the existing dashboard, and fix the existing lab GPU timestamp offset.

## Scope

In scope:
- Configure VPS node_exporter targets in `.env`.
- Pull node_exporter metrics every 30 seconds.
- Parse CPU, memory, disk, network, load average, uptime, and exporter reachability.
- Store normalized VPS metrics in MySQL.
- Show a unified infrastructure summary, GPU section, VPS section, and history charts.
- Track monthly traffic quota for one VPN gateway VPS.
- Interpret naive lab GPU timestamps as Asia/Shanghai time before storing UTC.

Out of scope:
- Custom VPS agent.
- SSH-based collection.
- node_exporter install automation.
- VPS target management UI.
- Login, alerts, LLM tracing.

## Configuration

```text
PULSEBOARD_NODE_EXPORTERS=vpn-gateway=http://1.2.3.4:9100,vps-us=http://5.6.7.8:9100
PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS=30
PULSEBOARD_TRAFFIC_QUOTA_NODE=vpn-gateway
PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB=250
PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB=71.23
PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY=18
```

`PULSEBOARD_NODE_EXPORTERS` starts in `.env` for MVP 2. Later it can move to a database-backed settings page.

## Metrics

CPU:
- Parse `node_cpu_seconds_total`.
- CPU usage is calculated from deltas between samples, excluding `idle`, `iowait`, and `steal`.

Memory:
- Parse `node_memory_MemTotal_bytes`, `node_memory_MemAvailable_bytes`.
- Usage percent is `(total - available) / total * 100`.

Disk:
- Parse `node_filesystem_size_bytes`, `node_filesystem_avail_bytes`, `node_filesystem_readonly`.
- Exclude virtual filesystems such as tmpfs, devtmpfs, overlay, squashfs, proc, sysfs, cgroup, nsfs, ramfs, autofs.
- Store all real mount points. The card highlights any real mount over 85%.

Network:
- Parse `node_network_receive_bytes_total`, `node_network_transmit_bytes_total`.
- Exclude `lo`, `docker*`, `veth*`, `br-*`, `tun*`, `tap*`.
- Store per-interface bytes/s and aggregate total inbound/outbound bytes/s.

Load and uptime:
- Parse `node_load1`, `node_load5`, `node_load15`.
- Parse `node_time_seconds - node_boot_time_seconds`.

Traffic quota:
- Applies only to `vpn-gateway`.
- Total quota is 250 GB.
- Initial used quota is 71.23 GB.
- Reset day is the 18th of each month.
- Usage after setup is estimated from aggregate network byte deltas and added to the configured initial value.

## Status Rules

VPS status:
- `offline`: node_exporter fetch fails.
- `critical`: CPU > 90%, memory > 90%, or any real disk > 85%.
- `online`: reachable and no critical threshold is exceeded.

## Dashboard

Homepage structure:
- Unified infrastructure summary at the top.
- GPU monitoring section.
- VPS monitoring section.
- History charts for GPU and VPS.

VPS card fields:
- CPU %
- Memory %
- Disk summary
- Network inbound/outbound
- Load average
- Uptime
- Traffic quota, only for `vpn-gateway`

## Time Handling Fix

Database continues to store UTC. Lab GPU API timestamps without timezone are interpreted as Asia/Shanghai before conversion to UTC. Frontend displays local time.

