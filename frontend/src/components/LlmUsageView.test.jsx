import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as echarts from 'echarts'

import {
  fetchLlmModels,
  fetchLlmSeries,
  fetchLlmSources,
  fetchLlmSummary,
} from '../api.js'
import { LlmUsageView } from './LlmUsageView.jsx'

vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  })),
  graphic: {
    LinearGradient: class LinearGradient {
      constructor(...args) {
        this.args = args
      }
    },
  },
}))

vi.mock('../api.js', () => ({
  fetchLlmModels: vi.fn(),
  fetchLlmSeries: vi.fn(),
  fetchLlmSources: vi.fn(),
  fetchLlmSummary: vi.fn(),
  refreshLlmUsage: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  HTMLElement.prototype.scrollTo = vi.fn()
  fetchLlmSources.mockResolvedValue({ sources: [] })
  fetchLlmSummary.mockResolvedValue({})
  fetchLlmSeries.mockResolvedValue({ series: [], model_series: [] })
  fetchLlmModels.mockResolvedValue({ models: [] })
})

it('LLM看板只保留监控操作，不再提供API Key配置', async () => {
  render(<LlmUsageView />)

  expect(await screen.findByRole('button', { name: '手动刷新' })).toBeVisible()
  expect(screen.getByRole('button', { name: '14天' })).toBeVisible()
  expect(screen.getByRole('button', { name: '29天' })).toBeVisible()
  expect(screen.getByRole('button', { name: '日' })).toBeVisible()
  expect(screen.getByRole('button', { name: '小时' })).toBeVisible()
  expect(screen.queryByRole('button', { name: '添加API Key' })).not.toBeInTheDocument()
  expect(screen.queryByText('保存ID')).not.toBeInTheDocument()
  expect(screen.queryByText('API Key')).not.toBeInTheDocument()
})

it('LLM看板支持New API风格范围切换并请求对应数据', async () => {
  render(<LlmUsageView />)

  fireEvent.click(await screen.findByRole('button', { name: '29天' }))

  await waitFor(() => expect(fetchLlmSummary).toHaveBeenLastCalledWith('29d', ''))
  expect(fetchLlmSeries).toHaveBeenLastCalledWith('29d', '')
  expect(fetchLlmModels).toHaveBeenLastCalledWith('29d', '')
})

it('同一供应商多个Key返回相同余额时只计一次账户余额', async () => {
  fetchLlmSources.mockResolvedValue({
    sources: [
      {
        source_id: 'deepseek-main',
        provider_id: 'deepseek',
        provider_name: 'DeepSeek',
        display_name: 'codex',
        status: 'online',
        balance_currency: 'CNY',
        balance_total: 48.86,
      },
      {
        source_id: 'deepseek-key-2',
        provider_id: 'deepseek',
        provider_name: 'DeepSeek',
        display_name: 'promind',
        status: 'online',
        balance_currency: 'CNY',
        balance_total: 48.86,
      },
      {
        source_id: 'deepseek-key-3',
        provider_id: 'deepseek',
        provider_name: 'DeepSeek',
        display_name: 'chatai',
        status: 'online',
        balance_currency: 'CNY',
        balance_total: 48.86,
      },
    ],
  })

  render(<LlmUsageView />)

  expect(await screen.findByText('DeepSeek')).toBeVisible()
  expect(screen.getAllByText('CNY 48.86').length).toBeGreaterThanOrEqual(2)
  expect(screen.queryByText('CNY 146.58')).not.toBeInTheDocument()
})

it('New API供应商展开后显示每个Key自己的可用额度', async () => {
  fetchLlmSources.mockResolvedValue({
    sources: [
      {
        source_id: 'academic-main',
        provider_id: 'academic',
        provider_name: 'EduModel',
        display_name: '主Key',
        source_type: 'newapi_admin',
        status: 'online',
        balance_currency: 'USD',
        balance_total: 48.86,
        quota_remaining_usd: 3.2,
      },
      {
        source_id: 'academic-backup',
        provider_id: 'academic',
        provider_name: 'EduModel',
        display_name: '备用Key',
        source_type: 'newapi_admin',
        status: 'online',
        balance_currency: 'USD',
        balance_total: 48.86,
        quota_remaining_usd: 1.9,
      },
    ],
  })

  render(<LlmUsageView />)

  const provider = await screen.findByText('EduModel')
  const card = provider.closest('.llm-provider-card')
  expect(within(card).getByText('USD 48.86')).toBeVisible()

  fireEvent.click(card)

  const mainRow = within(card).getByText('主Key').closest('.llm-key-row')
  const backupRow = within(card).getByText('备用Key').closest('.llm-key-row')
  expect(within(mainRow).getByText('$3.2000')).toBeVisible()
  expect(within(backupRow).getByText('$1.9000')).toBeVisible()
})

it('DeepSeek官方余额来源不把缺失的用量统计显示成正常0', async () => {
  fetchLlmSources.mockResolvedValue({
    sources: [
      {
        source_id: 'deepseek-main',
        provider_id: 'deepseek',
        provider_name: 'DeepSeek',
        display_name: '主Key',
        source_type: 'deepseek_balance',
        status: 'online',
        balance_currency: 'CNY',
        balance_total: 12.8,
      },
    ],
  })
  fetchLlmSummary.mockResolvedValue({
    usage_supported: false,
    usage_scope: 'balance_only',
    usage_message: 'DeepSeek官方只提供余额，未提供请求、token、模型用量统计',
    request_count: 0,
    token_count: 0,
    estimated_cost_usd: 0,
    snapshot_count: 1,
  })
  fetchLlmSeries.mockResolvedValue({
    usage_supported: false,
    usage_scope: 'balance_only',
    usage_message: 'DeepSeek官方只提供余额，未提供请求、token、模型用量统计',
    series: [{ source_id: 'deepseek-main', display_name: '主Key', points: [] }],
    model_series: [],
  })
  fetchLlmModels.mockResolvedValue({
    usage_supported: false,
    usage_scope: 'balance_only',
    usage_message: 'DeepSeek官方只提供余额，未提供请求、token、模型用量统计',
    models: [],
  })

  render(<LlmUsageView />)

  expect(await screen.findByText('官方仅余额')).toBeVisible()
  expect(screen.getByText('DeepSeek官方只提供余额，未提供请求、token、模型用量统计')).toBeVisible()
  expect(screen.getAllByText('官方未提供用量统计').length).toBeGreaterThan(0)
  expect(screen.getAllByText('用量不可用').length).toBeGreaterThan(0)
  expect(screen.getByText('模型用量不可用')).toBeVisible()
  expect(screen.queryByText('总计：0')).not.toBeInTheDocument()
})

it('部分统计视图中过滤仅余额来源的用量序列', async () => {
  fetchLlmSources.mockResolvedValue({
    sources: [
      {
        source_id: 'academic-main',
        provider_id: 'academic',
        provider_name: 'EduModel',
        display_name: '中转Key',
        source_type: 'newapi_admin',
        status: 'online',
      },
      {
        source_id: 'deepseek-main',
        provider_id: 'deepseek',
        provider_name: 'DeepSeek',
        display_name: 'DeepSeek主Key',
        source_type: 'deepseek_balance',
        status: 'online',
        balance_currency: 'CNY',
        balance_total: 67.98,
      },
    ],
  })
  fetchLlmSummary.mockResolvedValue({
    usage_supported: true,
    usage_scope: 'partial',
    usage_message: '部分来源仅提供余额，未计入请求、token、模型用量统计',
    estimated_cost_usd: 1.2,
    request_count: 12,
    token_count: 3000,
    snapshot_count: 2,
  })
  fetchLlmSeries.mockResolvedValue({
    usage_supported: true,
    usage_scope: 'partial',
    series: [
      {
        source_id: 'academic-main',
        source_type: 'newapi_admin',
        display_name: '中转Key',
        points: [{ timestamp: new Date().toISOString(), request_count: 12, token_count: 3000 }],
      },
      {
        source_id: 'deepseek-main',
        source_type: 'deepseek_balance',
        display_name: 'DeepSeek主Key',
        points: [{ timestamp: new Date().toISOString(), request_count: 99, token_count: 99000 }],
      },
    ],
    model_series: [],
  })

  render(<LlmUsageView />)

  expect(await screen.findByText('部分统计')).toBeVisible()
  const rankPanel = screen.getByText('Key调用排行').closest('.rank-panel')
  expect(within(rankPanel).getByText('中转Key')).toBeVisible()
  expect(within(rankPanel).queryByText('DeepSeek主Key')).not.toBeInTheDocument()
  expect(screen.getByTitle(new RegExp(`${localDateKey(new Date())}：12次请求，Token：3.00K`))).toBeVisible()
  expect(screen.queryByTitle(new RegExp(`${localDateKey(new Date())}：111次请求`))).not.toBeInTheDocument()
})

it('来源筛选支持按供应商汇总和按单个令牌查看', async () => {
  fetchLlmSources.mockResolvedValue({
    sources: [
      {
        source_id: 'academic-main',
        provider_id: 'academic',
        provider_name: 'EduModel',
        display_name: '主Key',
        source_type: 'newapi_admin',
        status: 'online',
        quota_remaining_usd: 3.2,
      },
      {
        source_id: 'academic-backup',
        provider_id: 'academic',
        provider_name: 'EduModel',
        display_name: '备用Key',
        source_type: 'newapi_admin',
        status: 'online',
        quota_remaining_usd: 1.9,
      },
    ],
  })

  render(<LlmUsageView />)

  const filter = await screen.findByLabelText('来源')
  expect(within(filter).getByRole('option', { name: 'EduModel（供应商）' })).toBeVisible()
  expect(within(filter).getByRole('option', { name: '主Key' })).toBeVisible()

  fireEvent.change(filter, { target: { value: 'provider:academic' } })
  await waitFor(() => expect(fetchLlmSummary).toHaveBeenLastCalledWith('today', 'provider:academic'))
  expect(fetchLlmSeries).toHaveBeenLastCalledWith('today', 'provider:academic')
  expect(fetchLlmModels).toHaveBeenLastCalledWith('today', 'provider:academic')

  fireEvent.change(filter, { target: { value: 'source:academic-main' } })
  await waitFor(() => expect(fetchLlmSummary).toHaveBeenLastCalledWith('today', 'source:academic-main'))
  expect(fetchLlmSeries).toHaveBeenLastCalledWith('today', 'source:academic-main')
  expect(fetchLlmModels).toHaveBeenLastCalledWith('today', 'source:academic-main')
})

it('LLM看板按New API风格展示活动热力图和模型分析视图', async () => {
  fetchLlmSummary.mockResolvedValue({
    estimated_cost_usd: 12.34,
    request_count: 1784,
    avg_rpm: 9.6,
    success_rate: 99.62,
  })
  fetchLlmSeries.mockResolvedValue({
    series: [
      {
        source_id: 'academic-main',
        display_name: '主Key',
        points: [
          { timestamp: '2026-07-17T10:00:00Z', request_count: 30, estimated_cost_usd: 2 },
          { timestamp: new Date().toISOString(), request_count: 120, token_count: 12_345_678, estimated_cost_usd: 10 },
        ],
      },
    ],
    model_series: [
      {
        model: 'gpt-5.5',
        display_name: 'gpt-5.5',
        points: [
          { timestamp: '2026-07-17T10:00:00Z', request_count: 20, estimated_cost_usd: 1 },
          { timestamp: '2026-07-18T10:00:00Z', request_count: 100, estimated_cost_usd: 9 },
        ],
      },
      {
        model: 'gpt-5.6-sol',
        display_name: 'gpt-5.6-sol',
        points: [
          { timestamp: '2026-07-18T10:00:00Z', request_count: 20, estimated_cost_usd: 1 },
        ],
      },
    ],
  })
  fetchLlmModels.mockResolvedValue({
    models: [
      { model: 'gpt-5.5', request_count: 1200, amount: 1200, estimated_cost_usd: 9.1, pricing_basis: 'newapi_quota' },
      { model: 'gpt-5.6-sol', request_count: 260, amount: 260, estimated_cost_usd: 1.8, pricing_basis: 'newapi_quota' },
    ],
  })

  render(<LlmUsageView />)

  expect(await screen.findByText('性能健康')).toBeVisible()
  expect(screen.getByText('月度活动')).toBeVisible()
  expect(screen.getByText('模型调用分析')).toBeVisible()
  expect(screen.getByText('成功率')).toBeVisible()
  expect(screen.getByText((_content, element) => element?.textContent === '1,200次')).toBeVisible()
  expect(screen.getByTitle(/Token：12.35M/)).toBeVisible()
  expect(screen.queryByText('82.19%')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '调用趋势' })).toBeVisible()
  expect(screen.getByRole('button', { name: '调用次数分布' })).toBeVisible()
  expect(screen.getByRole('button', { name: '调用次数排行' })).toBeVisible()
  expect(screen.getByTitle(/2026-01-01：0次请求，Token：0.00/)).toBeVisible()
  expect(screen.getByTitle(/2026-12-31：0次请求，Token：0.00/)).toBeVisible()
  expect(screen.getByTitle(/2026-01-01：0次请求，Token：0.00/)).toHaveClass('row-0')
  expect(screen.getByTitle(/2026-01-02：0次请求，Token：0.00/)).toHaveClass('row-1')
  expect(screen.getByTitle(new RegExp(`${localDateKey(new Date())}：.*Token：12.35M`))).toHaveClass('today')
  expect(screen.getByLabelText('月度活动，横向滚动').scrollTo).toHaveBeenCalledWith({ left: expect.any(Number), behavior: 'auto' })
})

function localDateKey(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

it('消耗和趋势图不启用横坐标缩放', async () => {
  fetchLlmSeries.mockResolvedValue({
    series: [
      {
        source_id: 'academic-main',
        display_name: '主Key',
        points: [
          { timestamp: '2026-07-18T09:00:00Z', request_count: 2, estimated_cost_usd: 0.1 },
          { timestamp: '2026-07-18T10:00:00Z', request_count: 5, estimated_cost_usd: 0.4 },
        ],
      },
    ],
    model_series: [
      {
        model: 'gpt-5.5',
        display_name: 'gpt-5.5',
        points: [
          { timestamp: '2026-07-18T09:00:00Z', request_count: 2, estimated_cost_usd: 0.1 },
          { timestamp: '2026-07-18T10:00:00Z', request_count: 5, estimated_cost_usd: 0.4 },
        ],
      },
    ],
  })

  render(<LlmUsageView />)

  await waitFor(() => expect(echarts.init).toHaveBeenCalled())
  const options = echarts.init.mock.results
    .map((item) => item.value.setOption.mock.calls.at(-1)?.[0])
    .filter(Boolean)
  expect(options.some((option) => option.dataZoom)).toBe(false)
  expect(options.some((option) => typeof option.aria?.label === 'string')).toBe(false)
})

it('消耗和趋势图使用固定日期分类轴，避免单点数据自动扩成年份跨度', async () => {
  fetchLlmSeries.mockResolvedValue({
    series: [
      {
        source_id: 'academic-main',
        display_name: '主Key',
        points: [
          { timestamp: '2026-07-18T10:00:00Z', request_count: 100, estimated_cost_usd: 17.089 },
        ],
      },
    ],
    model_series: [
      {
        model: 'gpt-5.5',
        display_name: 'gpt-5.5',
        points: [
          { timestamp: '2026-07-18T10:00:00Z', request_count: 100, estimated_cost_usd: 17.089 },
        ],
      },
    ],
  })

  render(<LlmUsageView />)

  fireEvent.click(await screen.findByRole('button', { name: '7天' }))
  await waitFor(() => expect(fetchLlmSeries).toHaveBeenLastCalledWith('7d', ''))
  await waitFor(() => expect(echarts.init).toHaveBeenCalled())
  const options = echarts.init.mock.results
    .map((item) => item.value.setOption.mock.calls.at(-1)?.[0])
    .filter(Boolean)
  const costOption = options.filter((option) => option.series?.some((item) => item.name === 'gpt-5.5')).at(-1)
  expect(costOption.xAxis.type).toBe('category')
  expect(costOption.xAxis.data).toContain('07-18')
  expect(costOption.xAxis.data.join(' ')).not.toMatch(/202[0-9]/)
})
