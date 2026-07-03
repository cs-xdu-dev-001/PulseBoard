export function VpsCard({ node }) {
  const mainDisk = pickMainDisk(node.disks)
  const traffic = node.traffic_quota

  return (
    <article className={`vps-card vps-${node.status}`}>
      <div className="card-top">
        <div>
          <span className="chip">node_exporter</span>
          <h3>{node.name}</h3>
        </div>
        <span className="status-label">{statusText(node.status)}</span>
      </div>

      <div className="vps-stats">
        <Metric label="CPU" value={formatPercent(node.cpu_percent)} />
        <Metric label="内存" value={formatPercent(node.memory_percent)} />
        <Metric label={`磁盘 ${mainDisk?.mount || '/'}`} value={formatPercent(mainDisk?.percentage)} />
        <Metric label="Load" value={formatLoad(node)} />
      </div>

      <div className="network-row">
        <span>入站</span>
        <strong>{formatRate(node.network_rx_bytes_per_sec)}</strong>
        <span>出站</span>
        <strong>{formatRate(node.network_tx_bytes_per_sec)}</strong>
      </div>

      {traffic && (
        <div className="quota-block">
          <div className="meter-row">
            <span>流量配额</span>
            <strong>{traffic.used_gb?.toFixed(2)} / {traffic.total_gb} GB</strong>
          </div>
          <div className="bar quota">
            <div style={{ width: `${clamp(traffic.used_percent || 0)}%` }} />
          </div>
          <footer>{formatPercent(traffic.used_percent)}，每月 18 号重置</footer>
        </div>
      )}

      <footer>Uptime {formatUptime(node.uptime_seconds)} · 最后采样 {formatTime(node.last_seen_at)}</footer>
    </article>
  )
}

function Metric({ label, value }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function statusText(status) {
  return {
    online: '在线',
    critical: '异常',
    offline: '离线',
    unknown: '未知',
  }[status] || status
}

function pickMainDisk(disks = {}) {
  if (disks['/']) return { mount: '/', ...disks['/'] }
  const first = Object.entries(disks)[0]
  return first ? { mount: first[0], ...first[1] } : null
}

function formatPercent(value) {
  return value == null ? '--' : `${Math.round(value)}%`
}

function formatLoad(node) {
  if (node.load1 == null) return '--'
  return `${node.load1.toFixed(2)} / ${node.load5?.toFixed(2) ?? '--'} / ${node.load15?.toFixed(2) ?? '--'}`
}

function formatRate(value) {
  if (value == null) return '--'
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB/s`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB/s`
  return `${Math.round(value)} B/s`
}

function formatUptime(seconds) {
  if (seconds == null) return '--'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return `${days}d ${hours}h`
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleTimeString()
}

function clamp(value) {
  return Math.max(0, Math.min(100, value))
}

