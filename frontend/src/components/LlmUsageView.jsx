import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchLlmConfig, fetchLlmModels, fetchLlmSeries, fetchLlmSources, fetchLlmSummary, refreshLlmUsage, saveLlmConfig } from '../api.js'

const ranges = [
  { value: 'today', label: '今天' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
]

const modelColors = ['#7c3aed', '#22c55e', '#f97316', '#38bdf8', '#2563eb', '#f43f5e']

export function LlmUsageView({ theme = 'dark' }) {
  const [range, setRange] = useState('today')
  const [source, setSource] = useState('')
  const [sources, setSources] = useState([])
  const [configs, setConfigs] = useState([])
  const [summary, setSummary] = useState(null)
  const [series, setSeries] = useState(null)
  const [models, setModels] = useState([])
  const [showConfig, setShowConfig] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    source_id: 'deepseek',
    source_type: 'deepseek_balance',
    display_name: 'DeepSeek',
    base_url: '',
    api_key: '',
    access_token: '',
    user_id: '1',
  })

  async function load(nextSource = source) {
    try {
      const [nextSources, nextConfig, nextSummary, nextSeries, nextModels] = await Promise.all([
        fetchLlmSources(),
        fetchLlmConfig(),
        fetchLlmSummary(range, nextSource),
        fetchLlmSeries(range, nextSource),
        fetchLlmModels(range, nextSource),
      ])
      setSources(nextSources.sources || [])
      setConfigs(nextConfig.sources || [])
      setSummary(nextSummary)
      setSeries(nextSeries)
      setModels(nextModels.models || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(() => load(), 30000)
    return () => clearInterval(timer)
  }, [range, source])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await refreshLlmUsage()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }

  async function handleSaveConfig(event) {
    event.preventDefault()
    const payload = { ...form }
    if (payload.source_type === 'deepseek_balance') {
      payload.base_url = ''
      payload.access_token = ''
      payload.user_id = ''
    }
    if (payload.source_type === 'newapi_admin') {
      payload.api_key = ''
    }
    try {
      await saveLlmConfig(payload)
      setSource(payload.source_id)
      await load(payload.source_id)
      setShowConfig(false)
    } catch (err) {
      setError(err.message)
    }
  }

  const totalBalance = sources.reduce((sum, item) => sum + (item.balance_total || 0), 0)

  return (
    <section className="llm-view">
      {error && <section className="notice danger">LLM 数据请求失败：{error}</section>}

      <div className="llm-toolbar">
        <div className="segmented">
          {ranges.map((item) => (
            <button key={item.value} className={range === item.value ? 'active' : ''} onClick={() => setRange(item.value)}>
              {item.label}
            </button>
          ))}
        </div>
        <select value={source} onChange={(event) => setSource(event.target.value)}>
          <option value="">全部来源</option>
          {sources.map((item) => (
            <option key={item.source_id} value={item.source_id}>{item.display_name}</option>
          ))}
        </select>
        <button className="glow-button" onClick={() => setShowConfig(!showConfig)}>{showConfig ? '收起配置' : '添加来源'}</button>
        <button className="glow-button" onClick={handleRefresh} disabled={refreshing}>{refreshing ? '刷新中' : '手动刷新'}</button>
      </div>

      {showConfig && (
        <form className="llm-config-card" onSubmit={handleSaveConfig}>
          <div className="table-title">配置 LLM 来源</div>
          <div className="config-grid">
            <label>
              <span>Source ID</span>
              <input value={form.source_id} onChange={(event) => setForm({ ...form, source_id: event.target.value })} placeholder="deepseek" />
            </label>
            <label>
              <span>类型</span>
              <select value={form.source_type} onChange={(event) => setForm({ ...form, source_type: event.target.value })}>
                <option value="deepseek_balance">DeepSeek 余额</option>
                <option value="newapi_admin">New API 管理统计</option>
              </select>
            </label>
            <label>
              <span>展示名</span>
              <input value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} placeholder="DeepSeek 官方" />
            </label>
            {form.source_type === 'newapi_admin' && (
              <label>
                <span>Base URL</span>
                <input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="https://your-new-api.example.com" />
              </label>
            )}
            {form.source_type === 'deepseek_balance' ? (
              <label>
                <span>API Key</span>
                <input type="password" value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} placeholder="sk-..." />
              </label>
            ) : (
              <>
                <label>
                  <span>访问令牌</span>
                  <input type="password" value={form.access_token} onChange={(event) => setForm({ ...form, access_token: event.target.value })} placeholder="New API access token" />
                </label>
                <label>
                  <span>User ID</span>
                  <input value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} placeholder="1" />
                </label>
              </>
            )}
          </div>
          <footer className="config-footer">
            <span>密钥只写入本地 .env，不回显到前端。</span>
            <button className="glow-button" type="submit">保存配置</button>
          </footer>
        </form>
      )}

      <div className="configured-strip">
        <span>来源</span>
        <button className={source === '' ? 'active' : ''} onClick={() => setSource('')}>全部</button>
        {configs.map((item) => (
          <button key={item.source_id} className={source === item.source_id ? 'active' : ''} onClick={() => setSource(item.source_id)}>
            {item.display_name}
            <small>{item.has_api_key || item.has_access_token ? '已配置密钥' : '未配置密钥'}</small>
          </button>
        ))}
      </div>

      <div className="llm-kpi-grid">
        <Kpi label="估算费用" value={formatUsd(summary?.estimated_cost_usd)} hint="OpenAI 单价 / New API 折算" highlight />
        <Kpi label="总请求数" value={formatNumber(summary?.request_count)} hint="统计周期内请求" />
        <Kpi label="平均 RPM" value={formatDecimal(summary?.avg_rpm)} hint="每分钟请求" />
        <Kpi label="账户余额" value={formatMoney(totalBalance, 'CNY')} hint="已接入余额来源合计" />
      </div>

      <div className="llm-source-grid">
        {sources.map((item) => <SourceCard key={item.source_id} source={item} active={source === item.source_id} onSelect={() => setSource(item.source_id)} />)}
        {sources.length === 0 && <div className="empty-panel">暂无 LLM 来源数据，保存配置后点击手动刷新。</div>}
      </div>

      <div className="llm-chart-stack">
        <AreaChart title="消耗分布" total={formatUsd(summary?.estimated_cost_usd)} series={series?.model_series || []} metric="estimated_cost_usd" formatter={formatUsd} theme={theme} />
        <AreaChart title="请求趋势" series={series?.series || []} metric="request_count" formatter={formatNumber} compact theme={theme} />
      </div>

      <ModelTable models={models} />
    </section>
  )
}

function SourceCard({ source, active, onSelect }) {
  const isBalance = source.source_type === 'deepseek_balance'
  return (
    <article className={`llm-source-card ${active ? 'active' : ''}`} onClick={onSelect}>
      <div className="llm-source-top">
        <div>
          <span className="chip">{source.source_type}</span>
          <h3>{source.display_name}</h3>
          <p>{source.source_id}</p>
        </div>
        <span className={`llm-status ${source.status}`}>{statusText(source.status)}</span>
      </div>
      <div className="llm-source-metrics">
        <div>
          <span>{isBalance ? '账户余额' : '余额估算'}</span>
          <strong>{isBalance ? formatMoney(source.balance_total, source.balance_currency) : formatUsd(source.quota_remaining_usd)}</strong>
        </div>
        <div>
          <span>{isBalance ? '充值余额' : '累计花费'}</span>
          <strong>{isBalance ? formatMoney(source.balance_topped_up, source.balance_currency) : formatUsd(source.quota_used_usd)}</strong>
        </div>
      </div>
      {source.last_error && <p className="error-text">{source.last_error}</p>}
      <footer>最后采集 {formatTime(source.last_checked_at)}</footer>
    </article>
  )
}

function Kpi({ label, value, hint, highlight = false }) {
  return (
    <article className={`llm-kpi ${highlight ? 'highlight' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  )
}

function ModelTable({ models }) {
  return (
    <div className="llm-table-card">
      <div className="table-title">模型费用分析</div>
      <table>
        <thead>
          <tr>
            <th>模型</th>
            <th>估算费用</th>
            <th>调用数</th>
            <th>原始额度</th>
            <th>计价依据</th>
          </tr>
        </thead>
        <tbody>
          {models.map((item) => (
            <tr key={item.model}>
              <td>{item.model}</td>
              <td className="money-cell">{formatUsd(item.estimated_cost_usd)}</td>
              <td>{formatNumber(item.request_count)}</td>
              <td>{formatCompact(item.amount)}</td>
              <td>{basisText(item.pricing_basis)}</td>
            </tr>
          ))}
          {models.length === 0 && <tr><td colSpan="5">暂无模型维度统计</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function AreaChart({ title, total, series, metric, formatter, compact = false, theme = 'dark' }) {
  const ref = useRef(null)
  const option = useMemo(() => {
    const palette = theme === 'light'
      ? {
          title: '#0f2233',
          legend: '#536a7f',
          axis: '#5d7286',
          axisLine: 'rgba(15, 34, 51, 0.14)',
          splitLine: 'rgba(15, 34, 51, 0.08)',
          tooltipBg: 'rgba(248, 252, 255, 0.96)',
          tooltipBorder: 'rgba(0, 166, 126, 0.24)',
          tooltipText: '#0f2233',
          areaEnd: 'rgba(248,252,255,0)',
        }
      : {
          title: '#e8fbff',
          legend: '#9aa7b8',
          axis: '#94a3b8',
          axisLine: 'rgba(148, 163, 184, 0.22)',
          splitLine: 'rgba(148, 163, 184, 0.12)',
          tooltipBg: 'rgba(7, 12, 24, 0.94)',
          tooltipBorder: 'rgba(139, 220, 255, 0.18)',
          tooltipText: '#effcff',
          areaEnd: 'rgba(0,0,0,0)',
        }
    const chartSeries = (series || []).map((item, index) => {
      const color = modelColors[index % modelColors.length]
      return {
        name: item.display_name || item.model || item.source_id,
        type: 'line',
        smooth: true,
        showSymbol: false,
        symbolSize: 6,
        lineStyle: { width: compact ? 2 : 3, color },
        areaStyle: {
          opacity: compact ? 0.12 : 0.18,
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color },
            { offset: 1, color: palette.areaEnd },
          ]),
        },
        emphasis: { focus: 'series' },
        data: (item.points || []).map((point) => [point.timestamp, point[metric] || 0]),
      }
    })
    return {
      backgroundColor: 'transparent',
      color: modelColors,
      title: {
        text: total ? `${title}  总计：${total}` : title,
        left: 24,
        top: 18,
        textStyle: { color: palette.title, fontSize: 16, fontWeight: 800 },
      },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: palette.tooltipBg,
        borderColor: palette.tooltipBorder,
        textStyle: { color: palette.tooltipText },
        valueFormatter: (value) => formatter(value),
      },
      legend: {
        bottom: 14,
        left: 'center',
        icon: 'rect',
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: palette.legend, fontSize: 12 },
      },
      grid: { left: 64, right: 30, bottom: compact ? 64 : 72, top: 70 },
      xAxis: {
        type: 'time',
        boundaryGap: false,
        axisLine: { lineStyle: { color: palette.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: palette.axis },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: palette.axis },
        splitLine: { lineStyle: { color: palette.splitLine } },
      },
      series: chartSeries,
    }
  }, [title, total, series, metric, formatter, compact, theme])

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(option, true)
    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [option])

  return <div className={`chart-card area-chart-card ${compact ? 'compact' : ''}`}><div ref={ref} className="chart area-chart" /></div>
}

function statusText(status) {
  return { online: '在线', degraded: '部分异常', offline: '离线', unknown: '未知' }[status] || status
}

function basisText(value) {
  return { openai_tokens: 'OpenAI 单价', newapi_quota: 'New API 折算', unknown: '未知' }[value] || value || '--'
}

function formatNumber(value) {
  if (value == null) return '--'
  return Math.round(Number(value)).toLocaleString()
}

function formatDecimal(value) {
  if (value == null) return '--'
  return Number(value).toFixed(2)
}

function formatUsd(value) {
  if (value == null) return '--'
  return `$${Number(value).toFixed(4)}`
}

function formatMoney(value, currency = '') {
  if (value == null) return '--'
  const prefix = currency ? `${currency} ` : ''
  return `${prefix}${Number(value).toFixed(2)}`
}

function formatCompact(value) {
  if (value == null) return '--'
  const number = Number(value)
  if (Math.abs(number) >= 1_000_000_000_000) return `${(number / 1_000_000_000_000).toFixed(2)}T`
  if (Math.abs(number) >= 1_000_000_000) return `${(number / 1_000_000_000).toFixed(2)}B`
  if (Math.abs(number) >= 1_000_000) return `${(number / 1_000_000).toFixed(2)}M`
  if (Math.abs(number) >= 1_000) return `${(number / 1_000).toFixed(2)}K`
  return number.toFixed(2)
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString()
}
