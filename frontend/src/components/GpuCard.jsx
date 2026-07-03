export function GpuCard({ gpu }) {
  const memoryRatio = gpu.memory_total_mb ? gpu.memory_used_mb / gpu.memory_total_mb : 0
  const memoryPercent = Number.isFinite(memoryRatio) ? Math.round(memoryRatio * 100) : 0

  return (
    <article className={`gpu-card status-${gpu.status}`}>
      <div className="card-top">
        <div>
          <span className="chip">{gpu.machine_name}</span>
          <h3>GPU {gpu.gpu_index}</h3>
        </div>
        <span className="status-label">{statusText(gpu.status)}</span>
      </div>
      <p className="gpu-name">{gpu.name}</p>
      <div className="meter-row">
        <span>利用率</span>
        <strong>{formatPercent(gpu.utilization)}</strong>
      </div>
      <div className="bar">
        <div style={{ width: `${clamp(gpu.utilization || 0)}%` }} />
      </div>
      <div className="meter-row">
        <span>显存</span>
        <strong>{formatMemory(gpu.memory_used_mb)} / {formatMemory(gpu.memory_total_mb)}</strong>
      </div>
      <div className="bar memory">
        <div style={{ width: `${clamp(memoryPercent)}%` }} />
      </div>
      <footer>最后采样 {formatTime(gpu.last_seen_at)}</footer>
    </article>
  )
}

function statusText(status) {
  return {
    available: '可上机',
    busy: '占用中',
    saturated: '满载',
    unknown: '未知',
    offline: '离线'
  }[status] || status
}

function formatPercent(value) {
  return value == null ? '--' : `${Math.round(value)}%`
}

function formatMemory(value) {
  if (value == null) return '--'
  if (value >= 1024) return `${(value / 1024).toFixed(1)} GB`
  return `${Math.round(value)} MB`
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleTimeString()
}

function clamp(value) {
  return Math.max(0, Math.min(100, value))
}

