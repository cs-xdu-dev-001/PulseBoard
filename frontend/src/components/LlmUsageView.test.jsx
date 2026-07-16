import { render, screen } from '@testing-library/react'
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
