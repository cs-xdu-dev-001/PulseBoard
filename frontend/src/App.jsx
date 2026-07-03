import { useEffect, useMemo, useState } from 'react'
import { fetchCurrentDashboard, fetchGpuHistory, fetchMachineHistory, fetchVpsHistory } from './api.js'
import { GpuCard } from './components/GpuCard.jsx'
import { MachineCard } from './components/MachineCard.jsx'
import { VpsCard } from './components/VpsCard.jsx'
import { HistoryChart } from './components/HistoryChart.jsx'
import { LlmUsageView } from './components/LlmUsageView.jsx'
import { SettingsView } from './components/SettingsView.jsx'

const refreshMs = 15000

export default function App() {
  const [dashboard, setDashboard] = useState(null)
  const [gpuHistory, setGpuHistory] = useState(null)
  const [machineHistory, setMachineHistory] = useState(null)
  const [vpsHistory, setVpsHistory] = useState(null)
  const [range, setRange] = useState('1h')
  const [activeTab, setActiveTab] = useState('infra')
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    async function loadCurrent() {
      try {
        const next = await fetchCurrentDashboard()
        if (active) {
          setDashboard(next)
          setError(null)
        }
      } catch (err) {
        if (active) setError(err.message)
      }
    }

    loadCurrent()
    const timer = setInterval(loadCurrent, refreshMs)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let active = true
    async function loadHistory() {
      try {
        const [gpu, machine, vps] = await Promise.all([
          fetchGpuHistory(range),
          fetchMachineHistory(range),
          fetchVpsHistory(range),
        ])
        if (active) {
          setGpuHistory(gpu)
          setMachineHistory(machine)
          setVpsHistory(vps)
        }
      } catch (err) {
        if (active) setError(err.message)
      }
    }
    loadHistory()
    return () => {
      active = false
    }
  }, [range])

  const sourceClass = useMemo(() => {
    const status = dashboard?.source?.status
    if (status === 'ok') return 'ok'
    if (status === 'degraded') return 'degraded'
    if (status === 'unreachable') return 'danger'
    return 'unknown'
  }, [dashboard])

  return (
    <main className="app-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />

      <header className="topbar">
        <div>
          <p className="eyebrow">PulseBoard</p>
          <h1>Infrastructure Console</h1>
        </div>
        <div className="topbar-actions">
          <div className="segmented">
            <button className={activeTab === 'infra' ? 'active' : ''} onClick={() => setActiveTab('infra')}>Infra</button>
            <button className={activeTab === 'llm' ? 'active' : ''} onClick={() => setActiveTab('llm')}>LLM</button>
            <button className={activeTab === 'settings' ? 'active' : ''} onClick={() => setActiveTab('settings')}>Settings</button>
          </div>
          <div className={`source-pill ${sourceClass}`}>
            <span className="pulse-dot" />
            <span>{sourceLabel(dashboard?.source?.status)}</span>
          </div>
        </div>
      </header>

      {error && <section className="notice danger">API 请求失败：{error}</section>}

      {activeTab === 'llm' ? (
        <LlmUsageView />
      ) : activeTab === 'settings' ? (
        <SettingsView />
      ) : (
        <InfraView
          dashboard={dashboard}
          gpuHistory={gpuHistory}
          machineHistory={machineHistory}
          vpsHistory={vpsHistory}
          range={range}
          setRange={setRange}
        />
      )}
    </main>
  )
}

function InfraView({ dashboard, gpuHistory, machineHistory, vpsHistory, range, setRange }) {
  const [infraTab, setInfraTab] = useState('overview')
  const gpus = dashboard?.gpus || []
  const vpsNodes = dashboard?.vps_nodes || []
  const machines = dashboard?.machines || []
  const availableGpus = gpus.filter((gpu) => gpu.status === 'available')
  const attentionGpus = [...availableGpus, ...gpus.filter((gpu) => gpu.status !== 'available')].slice(0, 6)
  const abnormalVps = vpsNodes.filter((node) => ['offline', 'critical'].includes(node.status))
  const trafficNode = vpsNodes.find((node) => node.traffic_quota)

  return (
    <>
      <section className="summary-grid">
        <Metric label="GPU 总数" value={dashboard?.summary?.gpus_total ?? '--'} />
        <Metric label="可上机 GPU" value={dashboard?.summary?.available_gpus ?? '--'} tone="available" />
        <Metric label="VPS 总数" value={dashboard?.summary?.vps_total ?? '--'} />
        <Metric label="异常 VPS" value={dashboard?.summary?.vps_abnormal ?? '--'} tone="danger" />
      </section>

      <section className="infra-subnav">
        <div>
          <p className="eyebrow">Infra</p>
          <h2>{infraTitle(infraTab)}</h2>
        </div>
        <div className="segmented">
          <button className={infraTab === 'overview' ? 'active' : ''} onClick={() => setInfraTab('overview')}>Overview</button>
          <button className={infraTab === 'gpu' ? 'active' : ''} onClick={() => setInfraTab('gpu')}>GPU</button>
          <button className={infraTab === 'vps' ? 'active' : ''} onClick={() => setInfraTab('vps')}>VPS</button>
          <button className={infraTab === 'machines' ? 'active' : ''} onClick={() => setInfraTab('machines')}>Machines</button>
        </div>
      </section>

      {infraTab === 'overview' && (
        <InfraOverview
          dashboard={dashboard}
          gpus={attentionGpus}
          vpsNodes={vpsNodes}
          abnormalVps={abnormalVps}
          trafficNode={trafficNode}
        />
      )}
      {infraTab === 'gpu' && <GpuPanel dashboard={dashboard} gpuHistory={gpuHistory} range={range} setRange={setRange} />}
      {infraTab === 'vps' && <VpsPanel dashboard={dashboard} vpsHistory={vpsHistory} range={range} setRange={setRange} />}
      {infraTab === 'machines' && (
        <MachinesPanel dashboard={dashboard} machineHistory={machineHistory} range={range} setRange={setRange} />
      )}
    </>
  )
}

function InfraOverview({ dashboard, gpus, vpsNodes, abnormalVps, trafficNode }) {
  return (
    <>
      <section className="overview-grid">
        <OverviewCard title="GPU 可用性" value={`${dashboard?.summary?.available_gpus ?? '--'} / ${dashboard?.summary?.gpus_total ?? '--'}`} hint="当前可上机 / 总数" tone="available" />
        <OverviewCard title="VPS 健康" value={abnormalVps.length ? `${abnormalVps.length} 异常` : '全部在线'} hint={vpsNodes.map((node) => node.name).join(' · ') || '等待数据'} tone={abnormalVps.length ? 'danger' : 'available'} />
        <OverviewCard title="VPN 流量" value={trafficNode?.traffic_quota ? `${trafficNode.traffic_quota.used_gb?.toFixed(1)} / ${trafficNode.traffic_quota.total_gb} GB` : '--'} hint={trafficNode ? trafficNode.name : '未找到流量节点'} />
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">Priority</p>
          <h2>当前最值得看的 GPU</h2>
        </div>
        <span className="muted">优先显示可上机 GPU，其次显示忙碌和异常卡。</span>
      </section>
      <section className="gpu-grid compact-grid">
        {gpus.map((gpu) => <GpuCard key={gpu.id} gpu={gpu} />)}
        {!dashboard && <SkeletonCards count={3} />}
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">VPS</p>
          <h2>服务器摘要</h2>
        </div>
      </section>
      <section className="vps-grid">
        {vpsNodes.map((node) => <VpsCard key={node.id} node={node} />)}
      </section>
    </>
  )
}

function GpuPanel({ dashboard, gpuHistory, range, setRange }) {
  return (
    <>
      <section className="section-heading">
        <div>
          <p className="eyebrow">Primary</p>
          <h2>GPU 状态</h2>
        </div>
        <span className="muted">空闲判定：连续 6 次采样利用率 &lt; 20%，显存 &lt; 5000 MB</span>
      </section>
      <section className="gpu-grid">
        {(dashboard?.gpus || []).map((gpu) => <GpuCard key={gpu.id} gpu={gpu} />)}
        {!dashboard && <SkeletonCards count={3} />}
      </section>
      <HistorySection range={range} setRange={setRange}>
        <HistoryChart title="GPU 利用率" data={gpuHistory} metric="utilization" unit="%" />
        <HistoryChart title="GPU 显存占用" data={gpuHistory} metric="memory_used_mb" unit="MB" />
      </HistorySection>
    </>
  )
}

function VpsPanel({ dashboard, vpsHistory, range, setRange }) {
  return (
    <>
      <section className="section-heading">
        <div>
          <p className="eyebrow">VPS</p>
          <h2>VPS 监控</h2>
        </div>
        <span className="muted">异常：离线，CPU &gt; 90%，内存 &gt; 90%，任一真实磁盘 &gt; 85%</span>
      </section>
      <section className="vps-grid">
        {(dashboard?.vps_nodes || []).map((node) => <VpsCard key={node.id} node={node} />)}
      </section>
      <HistorySection range={range} setRange={setRange}>
        <HistoryChart title="VPS CPU" data={vpsHistory} metric="cpu_percent" unit="%" kind="node" />
        <HistoryChart title="VPS 内存" data={vpsHistory} metric="memory_percent" unit="%" kind="node" />
        <HistoryChart title="VPS 入站速率" data={vpsHistory} metric="network_rx_bytes_per_sec" unit="B/s" kind="node" />
        <HistoryChart title="VPS 出站速率" data={vpsHistory} metric="network_tx_bytes_per_sec" unit="B/s" kind="node" />
        <HistoryChart title="流量配额使用率" data={vpsHistory} metric="traffic_used_percent" unit="%" kind="node" />
      </HistorySection>
    </>
  )
}

function MachinesPanel({ dashboard, machineHistory, range, setRange }) {
  return (
    <>
      <section className="section-heading">
        <div>
          <p className="eyebrow">Nodes</p>
          <h2>实验室机器</h2>
        </div>
      </section>
      <section className="machine-grid">
        {(dashboard?.machines || []).map((machine) => <MachineCard key={machine.id} machine={machine} />)}
      </section>
      <HistorySection range={range} setRange={setRange}>
        <HistoryChart title="实验室机器 CPU" data={machineHistory} metric="cpu_percent" unit="%" kind="machine" />
        <HistoryChart title="实验室机器内存" data={machineHistory} metric="memory_percent" unit="%" kind="machine" />
      </HistorySection>
    </>
  )
}

function HistorySection({ range, setRange, children }) {
  return (
    <section className="charts-panel">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">History</p>
          <h2>历史曲线</h2>
        </div>
        <div className="segmented">
          <button className={range === '1h' ? 'active' : ''} onClick={() => setRange('1h')}>1h</button>
          <button className={range === '24h' ? 'active' : ''} onClick={() => setRange('24h')}>24h</button>
        </div>
      </div>
      <div className="chart-grid">{children}</div>
    </section>
  )
}

function OverviewCard({ title, value, hint, tone = '' }) {
  return (
    <article className={`overview-card ${tone}`}>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  )
}

function Metric({ label, value, tone = '' }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}

function SkeletonCards({ count }) {
  return Array.from({ length: count }).map((_, index) => <div className="skeleton-card" key={index} />)
}

function infraTitle(tab) {
  return {
    overview: '总览',
    gpu: 'GPU 详情',
    vps: 'VPS 详情',
    machines: '实验室机器',
  }[tab]
}

function sourceLabel(status) {
  if (status === 'ok') return '数据源正常'
  if (status === 'degraded') return '数据源异常'
  if (status === 'unreachable') return '数据源不可达'
  return '等待数据'
}
