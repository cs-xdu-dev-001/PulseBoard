import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'

export function HistoryChart({ title, data, metric, unit, kind = 'gpu' }) {
  const ref = useRef(null)
  const option = useMemo(() => buildOption(title, data, metric, unit, kind), [title, data, metric, unit, kind])

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(option)
    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [option])

  return <div className="chart-card"><div ref={ref} className="chart" /></div>
}

function buildOption(title, data, metric, unit, kind) {
  const series = (data?.series || []).map((item) => ({
    name: kind === 'gpu' ? `${item.machine_name} GPU${item.gpu_index}` : item.name,
    type: 'line',
    smooth: true,
    showSymbol: false,
    data: (item.points || []).map((point) => [point.timestamp, point[metric]]),
    lineStyle: { width: 2 },
    emphasis: { focus: 'series' }
  }))

  return {
    backgroundColor: 'transparent',
    title: {
      text: title,
      left: 12,
      top: 10,
      textStyle: { color: '#e8fbff', fontSize: 14, fontWeight: 700 }
    },
    color: ['#39ff9d', '#22d3ee', '#ff4fd8', '#f59e0b', '#818cf8'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: 'rgba(7, 12, 24, 0.92)',
      borderColor: 'rgba(57, 255, 157, 0.35)',
      textStyle: { color: '#effcff' },
      axisPointer: { label: { formatter: (params) => formatDateTime(params.value) } },
      valueFormatter: (value) => value == null ? '--' : formatValue(value, unit)
    },
    legend: {
      top: 38,
      left: 10,
      right: 10,
      textStyle: { color: '#8fa6b8', fontSize: 11 }
    },
    grid: { left: 44, right: 18, bottom: 32, top: 78 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
      axisLabel: {
        color: '#7890a3',
        formatter: (value) => formatAxisTime(value)
      },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#7890a3' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }
    },
    series
  }
}

function formatValue(value, unit) {
  if (unit === 'B/s') {
    if (value >= 1024 * 1024) return (value / 1024 / 1024).toFixed(2) + ' MB/s'
    if (value >= 1024) return (value / 1024).toFixed(1) + ' KB/s'
    return Math.round(value) + ' B/s'
  }
  return `${Math.round(value)} ${unit}`
}

function formatAxisTime(value) {
  const date = new Date(value)
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  if (hours === '00' && minutes === '00') {
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${hours}:${minutes}`
  }
  return `${hours}:${minutes}`
}

function formatDateTime(value) {
  const date = new Date(value)
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function pad(value) {
  return String(value).padStart(2, '0')
}
