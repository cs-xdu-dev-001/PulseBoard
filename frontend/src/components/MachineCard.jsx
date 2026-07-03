export function MachineCard({ machine }) {
  return (
    <article className={`machine-card ${machine.status}`}>
      <div className="card-top">
        <h3>{machine.name}</h3>
        <span className="status-label">{machine.status === 'connected' ? '在线' : '离线'}</span>
      </div>
      <div className="machine-stats">
        <Metric label="CPU" value={formatPercent(machine.cpu_percent)} />
        <Metric label="内存" value={formatPercent(machine.memory_percent)} />
      </div>
      <div className="disk-list">
        {Object.entries(machine.disks || {}).map(([path, disk]) => (
          <div key={path}>
            <span>{path}</span>
            <strong>{disk ? formatPercent(disk.percentage) : '--'}</strong>
          </div>
        ))}
        {Object.keys(machine.disks || {}).length === 0 && <div><span>磁盘</span><strong>--</strong></div>}
      </div>
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

function formatPercent(value) {
  return value == null ? '--' : `${Math.round(value)}%`
}

