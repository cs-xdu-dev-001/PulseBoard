import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchLlmActivity, fetchLlmModels, fetchLlmSeries, fetchLlmSources, fetchLlmSummary, refreshLlmUsage } from '../api.js'

const ranges = [
  { value: 'today', label: '今天' },
  { value: '7d', label: '7天' },
  { value: '14d', label: '14天' },
  { value: '29d', label: '29天' },
]

const modelColors = ['#22c55e', '#f97316', '#38bdf8', '#2563eb', '#8b5cf6', '#f43f5e', '#14b8a6', '#eab308']

export function LlmUsageView({ theme = 'dark' }) {
  const [range, setRange] = useState('today')
  const [source, setSource] = useState('')
  const [sources, setSources] = useState([])
  const [summary, setSummary] = useState(null)
  const [series, setSeries] = useState(null)
  const [activity, setActivity] = useState(null)
  const [models, setModels] = useState([])
  const [expandedProviders, setExpandedProviders] = useState({})
  const [costChartMode, setCostChartMode] = useState('bar')
  const [modelView, setModelView] = useState('trend')
  const [granularity, setGranularity] = useState('day')
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const activityCacheRef = useRef(new Map())
  const activityYear = new Date().getFullYear()

  async function loadMain(nextSource = source, shouldCommit = () => true) {
    try {
      const [nextSummary, nextSeries, nextModels] = await Promise.all([
        fetchLlmSummary(range, nextSource),
        fetchLlmSeries(range, nextSource),
        fetchLlmModels(range, nextSource),
      ])
      if (!shouldCommit()) return
      setSummary(nextSummary)
      setSeries(nextSeries)
      setModels(nextModels.models || [])
      setError(null)
    } catch (err) {
      if (shouldCommit()) setError(err.message)
    }
  }

  async function loadSources(shouldCommit = () => true) {
    try {
      const nextSources = await fetchLlmSources()
      if (!shouldCommit()) return
      setSources(nextSources.sources || [])
    } catch (err) {
      if (shouldCommit()) setError(err.message)
    }
  }

  async function loadActivity(nextSource = source, shouldCommit = () => true) {
    const cacheKey = `${activityYear}:${nextSource}`
    const cached = activityCacheRef.current.get(cacheKey)
    if (cached) {
      setActivity(cached)
      return
    }
    try {
      const nextActivity = await fetchLlmActivity(activityYear, nextSource)
      if (!shouldCommit()) return
      activityCacheRef.current.set(cacheKey, nextActivity)
      setActivity(nextActivity)
      setError(null)
    } catch (err) {
      if (shouldCommit()) setError(err.message)
    }
  }

  useEffect(() => {
    let active = true
    loadSources(() => active)
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    let inFlight = false
    const run = async () => {
      if (inFlight) return
      inFlight = true
      await loadMain(source, () => active)
      inFlight = false
    }
    run()
    const timer = setInterval(run, 30000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [range, source])

  useEffect(() => {
    let active = true
    loadActivity(source, () => active)
    return () => {
      active = false
    }
  }, [source])

  useEffect(() => {
    if (range !== 'today' && granularity === 'hour') setGranularity('day')
  }, [range, granularity])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await refreshLlmUsage()
      activityCacheRef.current.delete(`${activityYear}:${source}`)
      await Promise.all([loadSources(), loadMain(source), loadActivity(source)])
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }

  const sourceGroups = useMemo(() => groupLlmItems(sources), [sources])
  const usageUnavailable = summary?.usage_supported === false
  const usagePartial = summary?.usage_scope === 'partial'
  const usageMessage = summary?.usage_message || series?.usage_message || ''
  const tokenIncomplete = summary?.token_usage_complete === false || series?.token_usage_complete === false
  const tokenUsageMessage = summary?.token_usage_message || series?.token_usage_message || ''
  const usageSeries = useMemo(() => filterUsageSeries(series?.series || []), [series])
  const usageModelSeries = useMemo(() => filterUsageSeries(series?.model_series || []), [series])
  const activityDaysData = useMemo(() => activityDays(activity), [activity])
  const activityTokenIncomplete = tokenIncomplete || (activity?.token_complete === false && (activity?.active_days || 0) > 0)
  const topModel = usageUnavailable ? '--' : (models[0]?.model || '--')
  const costSummary = useMemo(
    () => usageUnavailable ? null : costSummaryFromModels(models, summary?.estimated_cost_usd),
    [models, summary, usageUnavailable],
  )
  const costDisplay = usageUnavailable ? '--' : formatCostSummary(costSummary)

  return (
    <section className="llm-view">
      {error && <section className="notice danger">LLM数据请求失败：{error}</section>}

      <div className="llm-toolbar">
        <div className="segmented" aria-label="统计范围">
          {ranges.map((item) => (
            <button key={item.value} className={range === item.value ? 'active' : ''} onClick={() => setRange(item.value)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="segmented compact-segmented" aria-label="时间粒度">
          <button className={granularity === 'day' ? 'active' : ''} onClick={() => setGranularity('day')}>日</button>
          <button className={granularity === 'hour' ? 'active' : ''} onClick={() => setGranularity('hour')} disabled={range !== 'today'}>小时</button>
        </div>
        <label className="llm-filter-control">
          <span>来源</span>
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="">全部来源</option>
            {sourceGroups.map((group) => (
              <optgroup key={group.provider_id} label={group.provider_name}>
                <option value={`provider:${group.provider_id}`}>{group.provider_name}（供应商）</option>
                {group.items.map((item) => (
                  <option key={item.source_id} value={`source:${item.source_id}`}>{item.display_name}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <button className="glow-button" onClick={handleRefresh} disabled={refreshing}>{refreshing ? '刷新中' : '手动刷新'}</button>
      </div>

      {(usageUnavailable || usagePartial) && (
        <section className={`llm-usage-notice ${usageUnavailable ? 'balance-only' : 'partial'}`}>
          <strong>{usageUnavailable ? '官方仅余额' : '部分统计'}</strong>
          <span>{usageMessage}</span>
        </section>
      )}
      {tokenIncomplete && (
        <section className="llm-usage-notice partial">
          <strong>Token采样</strong>
          <span>{tokenUsageMessage}</span>
        </section>
      )}

      <div className="llm-kpi-grid">
        <Kpi label="官方消耗" value={costDisplay} highlight />
        <Kpi label="总请求数" value={usageUnavailable ? '--' : formatNumber(summary?.request_count)} />
        <Kpi label="常用模型" value={topModel} />
      </div>

      <PerformanceStrip summary={summary} models={models} usageUnavailable={usageUnavailable} tokenIncomplete={tokenIncomplete} />

      <div className="llm-source-grid">
        {sourceGroups.map((group) => (
          <ProviderCard
            key={group.provider_id}
            group={group}
            activeSource={source}
            expanded={expandedProviders[group.provider_id]}
            onToggle={() => setExpandedProviders((current) => ({ ...current, [group.provider_id]: !current[group.provider_id] }))}
            onSelectProvider={(providerId) => setSource(`provider:${providerId}`)}
            onSelectKey={(sourceId) => setSource(`source:${sourceId}`)}
          />
        ))}
        {sources.length === 0 && <div className="empty-panel">暂无LLM来源数据，请先在Settings配置并手动刷新。</div>}
      </div>

      <UsageDistribution
        mode={costChartMode}
        onModeChange={setCostChartMode}
        total={costDisplay}
        series={usageModelSeries}
        range={range}
        granularity={granularity}
        theme={theme}
        usageUnavailable={usageUnavailable}
        costSummary={costSummary}
      />

      <div className="llm-insight-grid">
        <ActivityHeatmap days={activityDaysData} usageUnavailable={usageUnavailable} tokenIncomplete={activityTokenIncomplete} />
        <RankPanel title="Key调用排行" items={usageUnavailable ? [] : sourceRankItems(usageSeries)} metricLabel="请求" emptyLabel={usageUnavailable ? '用量不可用' : '暂无排行数据'} />
      </div>

      <ModelAnalysisPanel
        view={modelView}
        onViewChange={setModelView}
        models={models}
        series={usageModelSeries}
        range={range}
        granularity={granularity}
        theme={theme}
        usageUnavailable={usageUnavailable}
      />

      <ModelTable models={models} usageUnavailable={usageUnavailable} />
    </section>
  )
}

function PerformanceStrip({ summary, models, usageUnavailable, tokenIncomplete }) {
  const health = summary?.snapshot_count ? '在线' : '等待数据'
  const top = usageUnavailable ? [] : models.slice(0, 3)
  return (
    <section className="llm-health-strip">
      <strong>性能健康</strong>
      <span>状态 <b>{health}</b></span>
      <span>成功率 <b>{formatPercentFromHundred(summary?.success_rate)}</b></span>
      <span>平均RPM <b>{formatDecimal(summary?.avg_rpm)}</b></span>
      <span>{tokenIncomplete ? '采样Token' : '总Token'} <b>{usageUnavailable ? '--' : formatCompact(summary?.token_count)}</b></span>
      <span>平均延迟 <b>{formatLatency(summary?.avg_latency_seconds)}</b></span>
      {top.map((item) => (
        <span className="model-pill" key={item.model}>{item.model} <b>{formatNumber(item.request_count)}次</b></span>
      ))}
    </section>
  )
}

function UsageDistribution({ mode, onModeChange, total, series, range, granularity, theme, usageUnavailable, costSummary }) {
  const buckets = useMemo(() => chartBuckets(range, granularity), [range, granularity])
  const chartSeries = useMemo(() => timeBucketSeries(series, 'estimated_cost_usd', buckets, 6), [series, buckets])
  const costFormatter = (value) => formatCostValue(value, costSummary)
  const mixedCurrency = costSummary?.kind === 'mixed'
  return (
    <ChartPanel
      title="消耗分布"
      accent="green"
      total={total}
      actions={(
        <div className="segmented compact-segmented">
          <button className={mode === 'bar' ? 'active' : ''} onClick={() => onModeChange('bar')}>柱状图</button>
          <button className={mode === 'area' ? 'active' : ''} onClick={() => onModeChange('area')}>面积图</button>
        </div>
      )}
    >
      {usageUnavailable
        ? <div className="empty-panel chart-empty">官方未提供用量统计</div>
        : mixedCurrency
          ? <div className="empty-panel chart-empty">混合币种，请选择单个供应商查看消耗分布</div>
          : <EChart option={timeSeriesOption({ title: '消耗分布', series: chartSeries, buckets, metric: 'value', formatter: costFormatter, theme, mode })} className="llm-wide-chart" />}
    </ChartPanel>
  )
}

function ActivityHeatmap({ days, usageUnavailable, tokenIncomplete }) {
  const scrollRef = useRef(null)
  const thresholds = useMemo(
    () => quantileThresholds(days.filter((day) => day.tokenAvailable).map((day) => day.value)),
    [days],
  )
  const weekCount = Math.ceil(days.length / 7)

  useEffect(() => {
    const node = scrollRef.current
    if (!node) return
    node.scrollTo({ left: activityTodayScrollLeft(days), behavior: 'auto' })
  }, [days])

  return (
    <section className="llm-panel activity-panel">
      <PanelHeader title="Token活动" accent="blue" total={`活跃${days.filter((day) => day.hasData && (day.value > 0 || day.requests > 0)).length}天`} />
      {usageUnavailable && <div className="empty-panel inline-empty">官方未提供用量统计</div>}
      <div className="activity-scroll" ref={scrollRef} aria-label="月度活动，横向滚动">
        <div className="activity-canvas" style={{ '--activity-weeks': weekCount }}>
          <div className="activity-grid" aria-label="月度活动">
            {days.map((day, index) => (
              <span
                key={day.key}
                className={`activity-cell level-${activityLevel(day.value, thresholds)} row-${index % 7} ${day.isToday ? 'today' : ''}`}
                data-tooltip={`${day.key}：Token：${day.tokenAvailable ? formatActivityTokens(day.tokens) : '不可用'}，${formatNumber(day.requests)}次请求${day.dataQuality === 'sampled' || tokenIncomplete ? '，采样' : ''}`}
                title={`${day.key}：Token：${day.tokenAvailable ? formatActivityTokens(day.tokens) : '不可用'}，${formatNumber(day.requests)}次请求${day.dataQuality === 'sampled' || tokenIncomplete ? '，采样' : ''}`}
              />
            ))}
          </div>
          <div className="activity-months">
            {activityMonthLabels(days).map((label) => <span key={label.key} style={{ gridColumn: label.column }}>{label.text}</span>)}
          </div>
        </div>
      </div>
    </section>
  )
}

function ModelAnalysisPanel({ view, onViewChange, models, series, range, granularity, theme, usageUnavailable }) {
  const total = models.reduce((sum, item) => sum + (item.request_count || 0), 0)
  const buckets = useMemo(() => chartBuckets(range, granularity), [range, granularity])
  const trendSeries = useMemo(() => timeBucketSeries(series, 'request_count', buckets, 6), [series, buckets])
  return (
    <ChartPanel
      title="模型调用分析"
      accent="pink"
      total={usageUnavailable ? '模型用量不可用' : `总计：${formatNumber(total)}`}
      actions={(
        <div className="segmented compact-segmented">
          <button className={view === 'trend' ? 'active' : ''} onClick={() => onViewChange('trend')}>调用趋势</button>
          <button className={view === 'pie' ? 'active' : ''} onClick={() => onViewChange('pie')}>调用次数分布</button>
          <button className={view === 'rank' ? 'active' : ''} onClick={() => onViewChange('rank')}>调用次数排行</button>
        </div>
      )}
    >
      {usageUnavailable && <div className="empty-panel chart-empty">官方未提供用量统计</div>}
      {!usageUnavailable && view === 'trend' && <EChart option={timeSeriesOption({ title: '调用趋势', series: trendSeries, buckets, metric: 'value', formatter: formatNumber, theme, mode: 'area' })} className="llm-wide-chart" />}
      {!usageUnavailable && view === 'pie' && <EChart option={pieOption(models, theme)} className="llm-wide-chart" />}
      {!usageUnavailable && view === 'rank' && <EChart option={rankOption(models, theme)} className="llm-wide-chart" />}
    </ChartPanel>
  )
}

function RankPanel({ title, items, metricLabel, emptyLabel = '暂无排行数据' }) {
  const max = Math.max(...items.map((item) => item.value), 0)
  return (
    <section className="llm-panel rank-panel">
      <PanelHeader title={title} accent="green" total={`Top ${Math.min(items.length, 5)}`} />
      <div className="rank-list">
        {items.slice(0, 5).map((item, index) => (
          <div className="rank-row" key={item.name}>
            <span className="rank-name">{item.name}</span>
            <div className="rank-track"><span style={{ width: `${max ? Math.max(4, (item.value / max) * 100) : 0}%`, background: modelColors[index % modelColors.length] }} /></div>
            <strong>{formatNumber(item.value)}</strong>
            <small>{metricLabel}</small>
          </div>
        ))}
        {items.length === 0 && <div className="empty-panel inline-empty">{emptyLabel}</div>}
      </div>
    </section>
  )
}

function ChartPanel({ title, accent, total, actions, children }) {
  return (
    <section className="llm-panel chart-shell">
      <PanelHeader title={title} accent={accent} total={total} actions={actions} />
      {children}
    </section>
  )
}

function PanelHeader({ title, accent = 'green', total, actions }) {
  return (
    <header className="llm-panel-header">
      <div>
        <span className={`panel-icon ${accent}`} />
        <strong>{title}</strong>
        {total && <small>{total}</small>}
      </div>
      {actions}
    </header>
  )
}

function EChart({ option, className }) {
  const ref = useRef(null)
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

  return <div ref={ref} className={`chart ${className}`} />
}

function ProviderCard({ group, activeSource, expanded, onToggle, onSelectProvider, onSelectKey }) {
  const providerValue = `provider:${group.provider_id}`
  const active = activeSource === providerValue || group.items.some((item) => `source:${item.source_id}` === activeSource)
  const status = aggregateStatus(group.items)
  const open = expanded || active
  return (
    <article
      className={`llm-source-card llm-provider-card ${active ? 'active' : ''}`}
      onClick={() => {
        onSelectProvider(group.provider_id)
        if (!open) onToggle()
      }}
    >
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
              className={`llm-key-row ${activeSource === `source:${item.source_id}` ? 'active' : ''}`}
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
              {!item.source_type?.startsWith('deepseek_') && <span>{formatKeyBalance(item)}</span>}
              <small>{formatTime(item.last_checked_at)}</small>
            </button>
          ))}
        </div>
      )}
      {group.items.some((item) => item.last_error) && <p className="error-text">{group.items.find((item) => item.last_error)?.last_error}</p>}
      <footer>{open ? '已按供应商汇总，点Key查看令牌' : '点击卡片按供应商汇总'}</footer>
    </article>
  )
}

function Kpi({ label, value, highlight = false }) {
  return (
    <article className={`llm-kpi ${highlight ? 'highlight' : ''}`}>
      <span>{label}</span>
      <strong title={String(value)}>{value}</strong>
    </article>
  )
}

function ModelTable({ models, usageUnavailable }) {
  return (
    <div className="llm-table-card">
      <div className="table-title">模型费用明细</div>
      <table>
        <thead>
          <tr>
            <th>模型</th>
            <th>消耗金额</th>
            <th>调用数</th>
            <th>原始额度</th>
            <th>计价依据</th>
          </tr>
        </thead>
        <tbody>
          {models.map((item) => (
            <tr key={item.model}>
              <td>{item.model}</td>
              <td className="money-cell">{formatModelCost(item)}</td>
              <td>{formatNumber(item.request_count)}</td>
              <td>{formatCompact(item.amount)}</td>
              <td>{basisText(item.pricing_basis)}</td>
            </tr>
          ))}
          {models.length === 0 && <tr><td colSpan="5">{usageUnavailable ? '官方未提供模型用量统计' : '暂无模型维度统计'}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function timeSeriesOption({ title, series, buckets, metric, formatter, theme, mode }) {
  const palette = chartPalette(theme)
  const labels = buckets.map((bucket) => bucket.label)
  const chartSeries = (series || []).map((item, index) => {
    const color = modelColors[index % modelColors.length]
    return {
      name: item.display_name || item.model || item.source_id,
      type: mode === 'bar' ? 'bar' : 'line',
      stack: mode === 'bar' ? 'total' : undefined,
      smooth: mode !== 'bar',
      showSymbol: false,
      barMaxWidth: 34,
      lineStyle: { width: 3, color },
      itemStyle: { color },
      areaStyle: mode === 'area'
        ? {
            opacity: 0.14,
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color },
              { offset: 1, color: palette.areaEnd },
            ]),
          }
        : undefined,
      emphasis: { focus: 'series' },
      data: labels.map((_, pointIndex) => item.points?.[pointIndex]?.[metric] || 0),
    }
  })
  return {
    backgroundColor: 'transparent',
    color: modelColors,
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.tooltipText },
      valueFormatter: (value) => formatter(value),
    },
    legend: {
      bottom: 22,
      left: 'center',
      icon: 'rect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: palette.legend, fontSize: 12 },
    },
    grid: { left: 56, right: 28, top: 32, bottom: 70 },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: mode === 'bar',
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisTick: { show: false },
      axisLabel: {
        color: palette.axis,
        interval: axisLabelInterval(labels.length),
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: palette.axis },
      splitLine: { lineStyle: { color: palette.splitLine } },
    },
    series: chartSeries,
    aria: { enabled: true },
  }
}

function pieOption(models, theme) {
  const palette = chartPalette(theme)
  return {
    color: modelColors,
    tooltip: {
      trigger: 'item',
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.tooltipText },
      valueFormatter: (value) => formatNumber(value),
    },
    legend: {
      left: 28,
      top: 'middle',
      orient: 'vertical',
      textStyle: { color: palette.legend, fontSize: 12 },
    },
    series: [
      {
        name: '调用次数分布',
        type: 'pie',
        radius: ['42%', '64%'],
        center: ['58%', '52%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 8, borderColor: palette.pieBorder, borderWidth: 3 },
        label: { color: palette.title, formatter: '{b}' },
        data: models.map((item) => ({ name: item.model, value: item.request_count || 0 })),
      },
    ],
  }
}

function rankOption(models, theme) {
  const palette = chartPalette(theme)
  const rows = [...models].sort((a, b) => (b.request_count || 0) - (a.request_count || 0)).slice(0, 8).reverse()
  return {
    color: modelColors,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.tooltipText },
      valueFormatter: (value) => formatNumber(value),
    },
    grid: { left: 120, right: 38, top: 26, bottom: 36 },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: { color: palette.axis },
      splitLine: { lineStyle: { color: palette.splitLine } },
    },
    yAxis: {
      type: 'category',
      data: rows.map((item) => item.model),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: palette.axis },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 28,
        label: { show: true, position: 'right', color: palette.title, formatter: ({ value }) => formatNumber(value) },
        itemStyle: {
          borderRadius: [0, 8, 8, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#f97316' },
            { offset: 1, color: '#39ff9d' },
          ]),
        },
        data: rows.map((item) => item.request_count || 0),
      },
    ],
  }
}

function chartPalette(theme) {
  if (theme === 'light') {
    return {
      title: '#0f2233',
      legend: '#536a7f',
      axis: '#5d7286',
      axisLine: 'rgba(15, 34, 51, 0.14)',
      splitLine: 'rgba(15, 34, 51, 0.08)',
      tooltipBg: 'rgba(248, 252, 255, 0.96)',
      tooltipBorder: 'rgba(0, 166, 126, 0.24)',
      tooltipText: '#0f2233',
      areaEnd: 'rgba(248,252,255,0)',
      pieBorder: '#f8fcff',
    }
  }
  return {
    title: '#e8fbff',
    legend: '#9aa7b8',
    axis: '#94a3b8',
    axisLine: 'rgba(148, 163, 184, 0.22)',
    splitLine: 'rgba(148, 163, 184, 0.12)',
    tooltipBg: 'rgba(7, 12, 24, 0.94)',
    tooltipBorder: 'rgba(139, 220, 255, 0.18)',
    tooltipText: '#effcff',
    areaEnd: 'rgba(0,0,0,0)',
    pieBorder: '#07111c',
  }
}

function timeBucketSeries(series, metric, buckets, limit = 8) {
  const bucketIndex = new Map(buckets.map((bucket, index) => [bucket.key, index]))
  return (series || []).slice(0, limit).map((item) => {
    const latestByBucketMember = new Map()
    for (const point of item.points || []) {
      const key = bucketKey(point.timestamp, buckets[0]?.granularity)
      if (!bucketIndex.has(key)) continue
      const value = Number(point[metric]) || 0
      const member = point.source_id || item.source_id || item.model || item.display_name || 'default'
      const memberKey = `${key}:${member}`
      const current = latestByBucketMember.get(memberKey)
      if (!current || new Date(point.timestamp) >= new Date(current.timestamp)) {
        latestByBucketMember.set(memberKey, { key, timestamp: point.timestamp, value })
      }
    }
    const values = Array.from({ length: buckets.length }, () => 0)
    for (const point of latestByBucketMember.values()) {
      values[bucketIndex.get(point.key)] += point.value
    }
    return {
      ...item,
      points: buckets.map((bucket, index) => ({ timestamp: bucket.timestamp, value: values[index] })),
    }
  })
}

function chartBuckets(range, granularity) {
  const actualGranularity = effectiveGranularity(range, granularity)
  if (actualGranularity === 'hour') return hourlyBuckets(range)
  return dailyBuckets(range)
}

function dailyBuckets(range) {
  const count = rangeDayCount(range)
  const today = startOfLocalDay(new Date())
  const start = new Date(today)
  start.setDate(start.getDate() - count + 1)
  const buckets = []
  for (let index = 0; index < count; index += 1) {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    buckets.push({
      key: localDateKey(date),
      label: localShortDate(date),
      timestamp: date.toISOString(),
      granularity: 'day',
    })
  }
  return buckets
}

function hourlyBuckets(range) {
  const now = new Date()
  const start = range === '24h' ? startOfLocalHour(now) : startOfLocalDay(now)
  if (range === '24h') start.setHours(start.getHours() - 23)
  const count = range === '24h' ? 24 : 24
  const buckets = []
  for (let index = 0; index < count; index += 1) {
    const date = new Date(start)
    date.setHours(start.getHours() + index)
    buckets.push({
      key: localHourKey(date),
      label: localHourLabel(date),
      timestamp: date.toISOString(),
      granularity: 'hour',
    })
  }
  return buckets
}

function bucketKey(timestamp, granularity) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return String(timestamp)
  if (granularity === 'hour') return localHourKey(date)
  return localDateKey(date)
}

function effectiveGranularity(range, granularity) {
  if (granularity === 'hour' && (range === 'today' || range === '24h')) return 'hour'
  return 'day'
}

function rangeDayCount(range) {
  return { today: 1, '24h': 1, '7d': 7, '14d': 14, '29d': 29 }[range] || 1
}

function axisLabelInterval(length) {
  if (length <= 14) return 0
  if (length <= 24) return 2
  return 4
}

function startOfLocalHour(date) {
  const result = new Date(date)
  result.setMinutes(0, 0, 0)
  return result
}

function localHourKey(date) {
  return `${localDateKey(date)}T${String(date.getHours()).padStart(2, '0')}`
}

function localShortDate(date) {
  return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function localHourLabel(date) {
  return `${String(date.getHours()).padStart(2, '0')}:00`
}

function activityDays(activity) {
  const today = startOfLocalDay(new Date())
  const todayKey = localDateKey(today)
  const start = new Date(today.getFullYear(), 0, 1)
  const end = new Date(today.getFullYear(), 11, 31)
  const values = new Map((activity?.days || []).map((day) => [day.date, day]))
  const days = []
  for (let cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    const key = localDateKey(cursor)
    const value = values.get(key)
    days.push({
      key,
      value: value?.token_count ?? null,
      tokens: value?.token_count ?? null,
      requests: value?.request_count || 0,
      hasData: value?.has_data === true,
      tokenAvailable: value?.token_count != null,
      dataQuality: value?.data_quality || 'unavailable',
      isToday: key === todayKey,
    })
  }
  return days
}

function activityTodayScrollLeft(days) {
  const todayIndex = days.findIndex((day) => day.isToday)
  if (todayIndex < 0) return 0
  const weekIndex = Math.floor(todayIndex / 7)
  return Math.max(0, weekIndex * 32 - 180)
}

function activityMonthLabels(days) {
  const labels = []
  let lastMonth = ''
  days.forEach((day, index) => {
    const month = day.key.slice(5, 7)
    if (month !== lastMonth) {
      labels.push({ key: day.key, text: `${Number(month)}月`, column: Math.floor(index / 7) + 1 })
      lastMonth = month
    }
  })
  return labels
}

function activityLevel(value, thresholds) {
  if (value == null || !thresholds.length) return 0
  if (value >= thresholds[2]) return 4
  if (value >= thresholds[1]) return 3
  if (value >= thresholds[0]) return 2
  return 1
}

function quantileThresholds(values) {
  const sorted = values.filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b)
  if (!sorted.length) return []
  const at = (ratio) => sorted[Math.floor((sorted.length - 1) * ratio)]
  return [at(0.25), at(0.5), at(0.75)]
}

function sourceRankItems(series) {
  return (series || [])
    .map((item) => ({
      name: item.display_name || item.source_id,
      value: latestPointValue(item.points, 'request_count'),
    }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value)
}

function filterUsageSeries(series) {
  return (series || []).filter((item) => item.source_type !== 'deepseek_balance')
}

function latestPointValue(points, key) {
  const latest = [...(points || [])].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0]
  return Number(latest?.[key]) || 0
}

function startOfLocalDay(date) {
  const result = new Date(date)
  result.setHours(0, 0, 0, 0)
  return result
}

function localDateKey(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
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
  return {
    openai_tokens: 'OpenAI参考价',
    deepseek_tokens: 'DeepSeek官方价',
    deepseek_platform_cny: 'DeepSeek平台统计',
    newapi_quota: 'NewAPI官方',
    unknown: '未知',
  }[value] || value || '--'
}

function costSummaryFromModels(models, fallbackUsd) {
  const totals = new Map()
  for (const item of models || []) {
    const value = Number(item.estimated_cost_usd)
    if (!Number.isFinite(value)) continue
    const currency = currencyForPricingBasis(item.pricing_basis)
    totals.set(currency, (totals.get(currency) || 0) + value)
  }
  if (totals.size === 1 && totals.has('USD') && fallbackUsd != null) {
    const official = Number(fallbackUsd)
    if (Number.isFinite(official)) totals.set('USD', official)
  }
  if (!totals.size && fallbackUsd != null) {
    const value = Number(fallbackUsd)
    if (Number.isFinite(value)) totals.set('USD', value)
  }
  const values = Array.from(totals.entries())
    .map(([currency, value]) => ({ currency, value }))
    .filter((item) => item.value !== 0)
    .sort((a, b) => a.currency.localeCompare(b.currency))
  if (!values.length) return { kind: 'single', currency: 'USD', value: 0 }
  if (values.length === 1) return { kind: 'single', currency: values[0].currency, value: values[0].value }
  return { kind: 'mixed', values }
}

function currencyForPricingBasis(value) {
  if (value === 'deepseek_platform_cny') return 'CNY'
  return 'USD'
}

function formatCostSummary(summary) {
  if (!summary) return '--'
  if (summary.kind === 'mixed') return summary.values.map((item) => formatCostMoney(item.value, item.currency)).join(' / ')
  return formatCostMoney(summary.value, summary.currency)
}

function formatCostValue(value, summary) {
  if (summary?.kind === 'single') return formatCostMoney(value, summary.currency)
  return formatUsd(value)
}

function formatModelCost(item) {
  return formatCostMoney(item.estimated_cost_usd, currencyForPricingBasis(item.pricing_basis))
}

function formatPercentFromHundred(value) {
  if (value == null) return '--'
  return `${Number(value).toFixed(2)}%`
}

function formatNumber(value) {
  if (value == null) return '--'
  return Math.round(Number(value)).toLocaleString()
}

function formatDecimal(value) {
  if (value == null) return '--'
  return Number(value).toFixed(2)
}

function formatLatency(value) {
  if (value == null) return '--'
  return `${Number(value).toFixed(2)}s`
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

function formatCostMoney(value, currency = 'USD') {
  if (value == null) return '--'
  return `${currency} ${Number(value).toFixed(2)}`
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

function formatActivityTokens(value) {
  const number = Number(value)
  if (Math.abs(number) < 100_000_000) return formatCompact(number)
  const billions = (number / 1_000_000_000).toFixed(2).replace(/\.?0+$/, '')
  return `${billions}B`
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString()
}
