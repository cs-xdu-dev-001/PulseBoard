import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

import App from './App.jsx'

vi.mock('./api.js', () => ({
  fetchCurrentDashboard: vi.fn(() => Promise.resolve({ source: { status: 'ok' }, gpus: [], machines: [], vps: [] })),
  fetchGpuHistory: vi.fn(() => Promise.resolve({ series: [] })),
  fetchMachineHistory: vi.fn(() => Promise.resolve({ series: [] })),
  fetchVpsHistory: vi.fn(() => Promise.resolve({ series: [] })),
}))

vi.mock('./components/LlmUsageView.jsx', () => ({
  LlmUsageView: () => <section>LLM视图</section>,
}))

vi.mock('./components/SettingsView.jsx', () => ({
  SettingsView: () => <section>Settings视图</section>,
}))

beforeEach(() => {
  vi.clearAllMocks()
  window.matchMedia = vi.fn(() => ({ matches: false }))
  window.localStorage.clear()
})

it('顶栏标题跟随当前页面切换', () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: 'Infrastructure Console' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'LLM' }))
  expect(screen.getByRole('heading', { name: 'LLM Usage Console' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
  expect(screen.getByRole('heading', { name: 'Settings Console' })).toBeVisible()
})
