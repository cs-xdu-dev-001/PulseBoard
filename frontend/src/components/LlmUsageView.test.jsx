import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

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
  fetchLlmSources.mockResolvedValue({ sources: [] })
  fetchLlmSummary.mockResolvedValue({})
  fetchLlmSeries.mockResolvedValue({ series: [], model_series: [] })
  fetchLlmModels.mockResolvedValue({ models: [] })
})

it('LLM看板只保留监控操作，不再提供API Key配置', async () => {
  render(<LlmUsageView />)

  expect(await screen.findByRole('button', { name: '手动刷新' })).toBeVisible()
  expect(screen.queryByRole('button', { name: '添加API Key' })).not.toBeInTheDocument()
  expect(screen.queryByText('保存ID')).not.toBeInTheDocument()
  expect(screen.queryByText('API Key')).not.toBeInTheDocument()
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
