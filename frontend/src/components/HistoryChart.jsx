import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  LineChart,
  TitleComponent,
  TooltipComponent,
])

export function HistoryChart({ title, data, metric, unit, kind = 'gpu', theme = 'dark' }) {
  const ref = useRef(null)
  const option = useMemo(() => buildOption(title, data, metric, unit, kind, theme), [title, data, metric, unit, kind, theme])

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

function buildOption(title, data, metric, unit, kind, theme) {
  const palette = theme === 'light'
    ? {
        title: '#0f2233',
        text: '#375066',
        axis: '#5d7286',
        axisLine: 'rgba(15, 34, 51, 0.14)',
        splitLine: 'rgba(15, 34, 51, 0.08)',
        tooltipBg: 'rgba(248, 252, 255, 0.96)',
        tooltipBorder: 'rgba(0, 166, 126, 0.28)',
        tooltipText: '#0f2233',
      }
    : {
        title: '#e8fbff',
        text: '#8fa6b8',
        axis: '#7890a3',
        axisLine: 'rgba(255,255,255,0.12)',
        splitLine: 'rgba(255,255,255,0.06)',
        tooltipBg: 'rgba(7, 12, 24, 0.92)',
        tooltipBorder: 'rgba(57, 255, 157, 0.35)',
        tooltipText: '#effcff',
      }
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
      textStyle: { color: palette.title, fontSize: 14, fontWeight: 700 }
    },
    color: ['#39ff9d', '#22d3ee', '#ff4fd8', '#f59e0b', '#818cf8'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.tooltipText },
      axisPointer: { label: { formatter: (params) => formatDateTime(params.value) } },
      valueFormatter: (value) => value == null ? '--' : formatValue(value, unit)
    },
    legend: {
      top: 38,
      left: 10,
      right: 10,
      textStyle: { color: palette.text, fontSize: 11 }
    },
    grid: { left: 44, right: 18, bottom: 32, top: 78 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: {
        color: palette.axis,
        formatter: (value) => formatAxisTime(value)
      },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: palette.axis },
      splitLine: { lineStyle: { color: palette.splitLine } }
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
