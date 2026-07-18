import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchLlmModels, fetchLlmSeries, fetchLlmSources, fetchLlmSummary, refreshLlmUsage } from '../api.js'

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
  const [summary, setSummary] = useState(null)
  const [series, setSeries] = useState(null)
  const [models, setModels] = useState([])
  const [expandedProviders, setExpandedProviders] = useState({})
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  async function load(nextSource = source) {
    try {
      const [nextSources, nextSummary, nextSeries, nextModels] = await Promise.all([
        fetchLlmSources(),
        fetchLlmSummary(range, nextSource),
        fetchLlmSeries(range, nextSource),
        fetchLlmModels(range, nextSource),
      ])
      setSources(nextSources.sources || [])
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

  const sourceGroups = useMemo(() => groupLlmItems(sources), [sources])
  const totalBalance = useMemo(() => totalProviderBalance(sourceGroups), [sourceGroups])

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
          {sourceGroups.map((group) => (
            <optgroup key={group.provider_id} label={group.provider_name}>
              {group.items.map((item) => (
                <option key={item.source_id} value={item.source_id}>{item.display_name}</option>
              ))}
            </optgroup>
          ))}
        </select>
        <button className="glow-button" onClick={handleRefresh} disabled={refreshing}>{refreshing ? '刷新中' : '手动刷新'}</button>
      </div>

      <div className="llm-kpi-grid">
        <Kpi label="估算费用" value={formatUsd(summary?.estimated_cost_usd)} hint="OpenAI 单价 / New API 折算" highlight />
        <Kpi label="总请求数" value={formatNumber(summary?.request_count)} hint="统计周期内请求" />
        <Kpi label="平均 RPM" value={formatDecimal(summary?.avg_rpm)} hint="每分钟请求" />
        <Kpi label="账户余额" value={formatBalanceValue(totalBalance)} hint="按供应商去重后的余额" />
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
          />
        ))}
        {sources.length === 0 && <div className="empty-panel">暂无LLM来源数据，请先在Settings配置并手动刷新。</div>}
      </div>

      <div className="llm-chart-stack">
        <AreaChart title="消耗分布" total={formatUsd(summary?.estimated_cost_usd)} series={series?.model_series || []} metric="estimated_cost_usd" formatter={formatUsd} theme={theme} />
        <AreaChart title="请求趋势" series={series?.series || []} metric="request_count" formatter={formatNumber} compact theme={theme} />
      </div>

      <ModelTable models={models} />
    </section>
  )
}

function ProviderCard({ group, activeSource, expanded, onToggle, onSelectKey }) {
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
  return formatBalanceValue(providerBalanceValue(items))
}

function providerBalanceValue(items) {
  const balanceItems = items.filter((item) => item.balance_total != null)
  if (balanceItems.length) {
    const uniqueBalances = uniqueBalanceValues(
      balanceItems,
      (item) => item.balance_currency || '',
      (item) => item.balance_total,
    )
    return balanceValueFromUniqueBalances(uniqueBalances)
  }
  const quotaItems = items.filter((item) => item.quota_remaining_usd != null)
  if (quotaItems.length) {
    const uniqueBalances = uniqueBalanceValues(quotaItems, () => 'USD', (item) => item.quota_remaining_usd)
    return balanceValueFromUniqueBalances(uniqueBalances, 'usd')
  }
  return null
}

function totalProviderBalance(groups) {
  const totals = new Map()
  for (const group of groups) {
    const balance = providerBalanceValue(group.items)
    if (!balance || balance.kind !== 'money') continue
    totals.set(balance.currency, (totals.get(balance.currency) || 0) + balance.value)
  }
  const values = Array.from(totals.entries()).map(([currency, value]) => ({ currency, value }))
  return balanceValueFromUniqueBalances(values)
}

function uniqueBalanceValues(items, currencyOf, valueOf) {
  const values = new Map()
  for (const item of items) {
    const value = Number(valueOf(item))
    if (!Number.isFinite(value)) continue
    const currency = currencyOf(item)
    values.set(`${currency}:${value.toFixed(6)}`, { currency, value })
  }
  return Array.from(values.values())
}

function balanceValueFromUniqueBalances(values, fallbackKind = 'money') {
  if (!values.length) return null
  const currencies = new Set(values.map((item) => item.currency))
  if (currencies.size === 1) {
    const currency = values[0].currency
    return { kind: fallbackKind === 'usd' ? 'usd' : 'money', currency, value: values.reduce((sum, item) => sum + item.value, 0) }
  }
  return {
    kind: 'mixed',
    values: values.map((item) => ({ currency: item.currency, value: item.value })),
  }
}

function formatBalanceValue(balance) {
  if (!balance) return '--'
  if (balance.kind === 'usd') return formatUsd(balance.value)
  if (balance.kind === 'mixed') return balance.values.map((item) => formatMoney(item.value, item.currency)).join(' / ')
  return formatMoney(balance.value, balance.currency)
}

function formatKeyBalance(item) {
  if (item.source_type === 'newapi_admin' && item.quota_remaining_usd != null) {
    return formatUsd(item.quota_remaining_usd)
  }
  if (item.source_type === 'newapi_admin') return '--'
  if (item.balance_total != null) return formatMoney(item.balance_total, item.balance_currency)
  if (item.quota_remaining_usd != null) return formatUsd(item.quota_remaining_usd)
  return '--'
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
