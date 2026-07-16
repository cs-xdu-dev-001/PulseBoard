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
  const [expandedProviders, setExpandedProviders] = useState({})
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    provider_id: 'deepseek',
    provider_name: 'DeepSeek',
    key_id: 'main',
    source_type: 'deepseek_balance',
    display_name: '主Key',
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
    const providerId = normalizeIdPart(form.provider_id)
    const keyId = normalizeIdPart(form.key_id)
    if (!providerId || !keyId) {
      setError('供应商ID和Key ID只能使用小写字母、数字、-、_。')
      return
    }
    const payload = {
      ...form,
      provider_id: providerId,
      provider_name: form.provider_name.trim() || providerId,
      source_id: `${providerId}-${keyId}`,
      display_name: form.display_name.trim() || form.key_id.trim() || keyId,
    }
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
  const sourceGroups = useMemo(() => groupLlmItems(sources), [sources])
  const configGroups = useMemo(() => groupLlmItems(configs), [configs])
  const selectorGroups = configGroups.length ? configGroups : sourceGroups
  const sourceIdPreview = `${normalizeIdPart(form.provider_id) || 'provider'}-${normalizeIdPart(form.key_id) || 'key'}`

  function handleAddProviderKey(group) {
    const configGroup = configGroups.find((item) => item.provider_id === group.provider_id)
    const template = configGroup?.items[0] || group.items[0] || {}
    const nextIndex = (configGroup?.items.length || group.items.length || 0) + 1
    setForm({
      provider_id: group.provider_id,
      provider_name: group.provider_name,
      key_id: `key-${nextIndex}`,
      source_type: template.source_type || 'deepseek_balance',
      display_name: `Key ${nextIndex}`,
      base_url: template.base_url || '',
      api_key: '',
      access_token: '',
      user_id: template.user_id || '1',
    })
    setShowConfig(true)
    setExpandedProviders((current) => ({ ...current, [group.provider_id]: true }))
  }

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
          {selectorGroups.map((group) => (
            <optgroup key={group.provider_id} label={group.provider_name}>
              {group.items.map((item) => (
                <option key={item.source_id} value={item.source_id}>{item.display_name}</option>
              ))}
            </optgroup>
          ))}
        </select>
        <button className="glow-button" onClick={() => setShowConfig(!showConfig)}>{showConfig ? '收起配置' : '添加API Key'}</button>
        <button className="glow-button" onClick={handleRefresh} disabled={refreshing}>{refreshing ? '刷新中' : '手动刷新'}</button>
      </div>

      {showConfig && (
        <form className="llm-config-card" onSubmit={handleSaveConfig}>
          <div className="table-title">添加API Key</div>
          <div className="config-grid">
            <label>
              <span>供应商ID</span>
              <input value={form.provider_id} onChange={(event) => setForm({ ...form, provider_id: event.target.value })} placeholder="deepseek" />
            </label>
            <label>
              <span>供应商名</span>
              <input value={form.provider_name} onChange={(event) => setForm({ ...form, provider_name: event.target.value })} placeholder="DeepSeek" />
            </label>
            <label>
              <span>Key ID</span>
              <input value={form.key_id} onChange={(event) => setForm({ ...form, key_id: event.target.value })} placeholder="main" />
            </label>
            <label>
              <span>Key展示名</span>
              <input value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} placeholder="主Key" />
            </label>
            <label>
              <span>类型</span>
              <select value={form.source_type} onChange={(event) => setForm({ ...form, source_type: event.target.value })}>
                <option value="deepseek_balance">DeepSeek 余额</option>
                <option value="newapi_admin">New API 管理统计</option>
              </select>
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
            <div className="source-id-preview">
              <span>保存ID</span>
              <strong>{sourceIdPreview}</strong>
            </div>
          </div>
          <footer className="config-footer">
            <span>密钥只写入本地 .env，不回显到前端。</span>
            <button className="glow-button" type="submit">保存配置</button>
          </footer>
        </form>
      )}

      <div className="configured-strip">
        <span>API Key</span>
        <button className={source === '' ? 'active' : ''} onClick={() => setSource('')}>全部</button>
        {configGroups.map((group) => (
          <div className="configured-group" key={group.provider_id}>
            <span>{group.provider_name}</span>
            {group.items.map((item) => (
              <button key={item.source_id} className={source === item.source_id ? 'active' : ''} onClick={() => setSource(item.source_id)}>
                {item.display_name}
                <small>{item.has_api_key || item.has_access_token ? '已配置' : '未配置'}</small>
              </button>
            ))}
          </div>
        ))}
      </div>

      <div className="llm-kpi-grid">
        <Kpi label="估算费用" value={formatUsd(summary?.estimated_cost_usd)} hint="OpenAI 单价 / New API 折算" highlight />
        <Kpi label="总请求数" value={formatNumber(summary?.request_count)} hint="统计周期内请求" />
        <Kpi label="平均 RPM" value={formatDecimal(summary?.avg_rpm)} hint="每分钟请求" />
        <Kpi label="账户余额" value={formatMoney(totalBalance, 'CNY')} hint="已接入余额来源合计" />
      </div>

      <div className="llm-source-grid">
        {sourceGroups.map((group) => (
          <ProviderCard
            key={group.provider_id}
            group={group}
            activeSource={source}
            expanded={expandedProviders[group.provider_id]}
            onToggle={() => setExpandedProviders((current) => ({ ...current, [group.provider_id]: !current[group.provider_id] }))}
            onSelectKey={(sourceId) => setSource(sourceId)}
            onAddKey={handleAddProviderKey}
          />
        ))}
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

function ProviderCard({ group, activeSource, expanded, onToggle, onSelectKey, onAddKey }) {
  const active = group.items.some((item) => item.source_id === activeSource)
  const status = aggregateStatus(group.items)
  const open = expanded || active
  return (
    <article className={`llm-source-card llm-provider-card ${active ? 'active' : ''}`} onClick={onToggle}>
      <div className="llm-source-top">
        <div>
          <span className="chip">{group.items.length} keys</span>
          <h3>{group.provider_name}</h3>
          <p>{group.provider_id}</p>
        </div>
        <div className="llm-source-actions">
          <span className={`llm-status ${status}`}>{statusText(status)}</span>
          <button
            type="button"
            className="mini-action"
            onClick={(event) => {
              event.stopPropagation()
              onAddKey(group)
            }}
          >
            添加Key
          </button>
        </div>
      </div>
      <div className="llm-source-metrics">
        <div>
          <span>可用余额</span>
          <strong>{formatProviderBalance(group.items)}</strong>
        </div>
        <div>
          <span>Key数量</span>
          <strong>{group.items.length}</strong>
        </div>
      </div>
      {open && (
        <div className="llm-key-list">
          {group.items.map((item) => (
            <button
              type="button"
              key={item.source_id}
              className={`llm-key-row ${activeSource === item.source_id ? 'active' : ''}`}
              onClick={(event) => {
                event.stopPropagation()
                onSelectKey(item.source_id)
              }}
            >
              <span>
                <strong>{item.display_name}</strong>
                <small>{item.source_id}</small>
              </span>
              <span className={`llm-status ${item.status}`}>{statusText(item.status)}</span>
              <span>{formatKeyBalance(item)}</span>
              <small>{formatTime(item.last_checked_at)}</small>
            </button>
          ))}
        </div>
      )}
      {group.items.some((item) => item.last_error) && <p className="error-text">{group.items.find((item) => item.last_error)?.last_error}</p>}
      <footer>{open ? '点击卡片收起' : '点击卡片查看Key'}</footer>
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

function groupLlmItems(items = []) {
  const groups = new Map()
  for (const item of items) {
    const providerId = item.provider_id || item.source_id
    const providerName = item.provider_name || item.display_name || providerId
    if (!groups.has(providerId)) {
      groups.set(providerId, { provider_id: providerId, provider_name: providerName, items: [] })
    }
    groups.get(providerId).items.push(item)
  }
  return Array.from(groups.values()).sort((a, b) => a.provider_name.localeCompare(b.provider_name))
}

function aggregateStatus(items) {
  if (!items.length) return 'unknown'
  if (items.every((item) => item.status === 'online')) return 'online'
  if (items.every((item) => item.status === 'offline')) return 'offline'
  if (items.some((item) => item.status === 'degraded' || item.status === 'offline')) return 'degraded'
  return 'unknown'
}

function formatProviderBalance(items) {
  const balanceItems = items.filter((item) => item.balance_total != null)
  if (balanceItems.length) {
    const currency = balanceItems[0].balance_currency || ''
    const total = balanceItems.reduce((sum, item) => sum + (item.balance_total || 0), 0)
    return formatMoney(total, currency)
  }
  const quotaItems = items.filter((item) => item.quota_remaining_usd != null)
  if (quotaItems.length) {
    const total = quotaItems.reduce((sum, item) => sum + (item.quota_remaining_usd || 0), 0)
    return formatUsd(total)
  }
  return '--'
}

function formatKeyBalance(item) {
  if (item.balance_total != null) return formatMoney(item.balance_total, item.balance_currency)
  if (item.quota_remaining_usd != null) return formatUsd(item.quota_remaining_usd)
  return '--'
}

function normalizeIdPart(value) {
  const normalized = String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')
  return /^[a-z0-9_-]{1,64}$/.test(normalized) ? normalized : ''
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
