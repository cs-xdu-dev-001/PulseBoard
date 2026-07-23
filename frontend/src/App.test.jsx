import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

import App from './App.jsx'

const moduleLoads = vi.hoisted(() => ({ history: 0, llm: 0, settings: 0 }))

vi.mock('./api.js', () => ({
  fetchCurrentDashboard: vi.fn(() => Promise.resolve({ source: { status: 'ok' }, gpus: [], machines: [], vps: [] })),
  fetchGpuHistory: vi.fn(() => Promise.resolve({ series: [] })),
  fetchMachineHistory: vi.fn(() => Promise.resolve({ series: [] })),
  fetchVpsHistory: vi.fn(() => Promise.resolve({ series: [] })),
}))

vi.mock('./components/LlmUsageView.jsx', () => {
  moduleLoads.llm += 1
  return { LlmUsageView: () => <section>LLM视图</section> }
})

vi.mock('./components/SettingsView.jsx', () => {
  moduleLoads.settings += 1
  return { SettingsView: () => <section>Settings视图</section> }
})

vi.mock('./components/HistoryChart.jsx', () => {
  moduleLoads.history += 1
  return { HistoryChart: () => <div>历史曲线图</div> }
})

beforeEach(() => {
  vi.clearAllMocks()
  window.matchMedia = vi.fn(() => ({ matches: false }))
  window.localStorage.clear()
})

it('顶栏标题跟随当前页面切换并按需加载页面模块', async () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: 'Infrastructure Console' })).toBeVisible()
  expect(moduleLoads).toEqual({ history: 0, llm: 0, settings: 0 })

  fireEvent.click(screen.getByRole('button', { name: 'LLM' }))
  expect(screen.getByRole('heading', { name: 'LLM Usage Console' })).toBeVisible()
  expect(await screen.findByText('LLM视图')).toBeVisible()
  expect(moduleLoads.llm).toBe(1)

  fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
  expect(screen.getByRole('heading', { name: 'Settings Console' })).toBeVisible()
  expect(await screen.findByText('Settings视图')).toBeVisible()
  expect(moduleLoads.settings).toBe(1)
})

it('基础设施曲线仅在进入详情页后加载', async () => {
  render(<App />)

  expect(moduleLoads.history).toBe(0)
  fireEvent.click(screen.getByRole('button', { name: 'GPU' }))

  expect(await screen.findAllByText('历史曲线图')).toHaveLength(2)
  expect(moduleLoads.history).toBe(1)
})
