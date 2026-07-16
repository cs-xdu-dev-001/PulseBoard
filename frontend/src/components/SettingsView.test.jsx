import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchLlmConfig, fetchSettings, saveLlmConfig, saveSettings } from '../api.js'
import { SettingsView } from './SettingsView.jsx'

vi.mock('../api.js', () => ({
  fetchLlmConfig: vi.fn(),
  fetchSettings: vi.fn(),
  saveLlmConfig: vi.fn(),
  saveSettings: vi.fn(),
}))

const llmSources = [
  {
    source_id: 'deepseek-main',
    provider_id: 'deepseek',
    provider_name: 'DeepSeek',
    display_name: '主Key',
    source_type: 'deepseek_balance',
    base_url: null,
    user_id: '1',
    has_api_key: true,
    has_access_token: false,
  },
  {
    source_id: 'deepseek-backup',
    provider_id: 'deepseek',
    provider_name: 'DeepSeek',
    display_name: '备用Key',
    source_type: 'deepseek_balance',
    base_url: null,
    user_id: '1',
    has_api_key: true,
    has_access_token: false,
  },
]

describe('Settings LLM供应商配置', () => {
  beforeEach(() => {
    fetchSettings.mockResolvedValue({
      values: { PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS: '300' },
      secrets: {},
    })
    fetchLlmConfig.mockResolvedValue({ sources: llmSources })
    saveSettings.mockResolvedValue({ ok: true })
    saveLlmConfig.mockResolvedValue({ ok: true })
  })

  it('将同一供应商的多个Key显示在一个分组中', async () => {
    render(<SettingsView />)

    expect(await screen.findByRole('heading', { name: 'LLM供应商' })).toBeVisible()
    const provider = screen.getByTestId('llm-provider-deepseek')
    expect(within(provider).getByText('2个Key')).toBeVisible()
    expect(within(provider).getByText('主Key')).toBeVisible()
    expect(within(provider).getByText('备用Key')).toBeVisible()
  })

  it('可以在已有供应商下新增Key', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '添加Key' }))
    fireEvent.change(screen.getByLabelText('Key ID'), { target: { value: 'backup-2' } })
    fireEvent.change(screen.getByLabelText('Key展示名'), { target: { value: '备用Key 2' } })
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'secret-value' } })
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    await waitFor(() => {
      expect(saveLlmConfig).toHaveBeenCalledWith(expect.objectContaining({
        provider_id: 'deepseek',
        provider_name: 'DeepSeek',
        source_id: 'deepseek-backup-2',
        display_name: '备用Key 2',
        api_key: 'secret-value',
      }))
    })
  })

  it('编辑Key时锁定ID并且不回显已有密钥', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '编辑 主Key' }))

    expect(screen.getByLabelText('供应商ID')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('保存ID')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('保存ID')).toHaveValue('deepseek-main')
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByLabelText('API Key')).toHaveAttribute('placeholder', '留空则保留原密钥')
  })
})
