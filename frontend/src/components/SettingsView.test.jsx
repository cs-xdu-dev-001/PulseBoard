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
  {
    source_id: 'academic-main',
    provider_id: 'academic',
    provider_name: 'Academic Gateway',
    display_name: '主账号',
    source_type: 'newapi_admin',
    base_url: 'https://gateway.example.com',
    user_id: '1',
    has_api_key: true,
    has_access_token: false,
  },
]

describe('Settings LLM供应商配置', () => {
  beforeEach(() => {
    fetchSettings.mockResolvedValue({
      values: {
        PULSEBOARD_LLM_USAGE_SOURCES: 'deepseek-main',
        PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS: '300',
      },
      secrets: {},
    })
    fetchLlmConfig.mockResolvedValue({ sources: llmSources })
    saveSettings.mockResolvedValue({ ok: true })
    saveLlmConfig.mockResolvedValue({ ok: true })
  })

  it('默认折叠供应商并在展开后显示多个Key', async () => {
    render(<SettingsView />)

    expect(await screen.findByRole('heading', { name: 'LLM供应商' })).toBeVisible()
    const provider = screen.getByTestId('llm-provider-deepseek')
    expect(within(provider).getByText('2个Key')).toBeVisible()
    expect(within(provider).queryByText('主Key')).not.toBeInTheDocument()
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
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

  it('已有New API供应商下新增Key时只填写Key级配置', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-academic')
    fireEvent.click(within(provider).getByRole('button', { name: '添加Key' }))
    fireEvent.change(screen.getByLabelText('Key ID'), { target: { value: 'backup' } })
    fireEvent.change(screen.getByLabelText('Key展示名'), { target: { value: '备用账号' } })
    fireEvent.change(screen.getByLabelText('访问令牌'), { target: { value: 'token-value' } })

    expect(screen.queryByLabelText('接入类型')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Base URL')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('User ID')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    await waitFor(() => {
      expect(saveLlmConfig).toHaveBeenCalledWith(expect.objectContaining({
        provider_id: 'academic',
        provider_name: 'Academic Gateway',
        source_id: 'academic-backup',
        display_name: '备用账号',
        source_type: 'newapi_admin',
        base_url: 'https://gateway.example.com',
        access_token: 'token-value',
        user_id: '1',
      }))
    })
  })

  it('编辑Key时只展示Key级字段并且不回显已有密钥', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '编辑 主Key' }))

    expect(screen.queryByLabelText('供应商ID')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('供应商名称')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('接入类型')).not.toBeInTheDocument()
    const editor = screen.getByRole('heading', { name: '编辑主Key' }).closest('form')
    expect(within(editor).getAllByText('DeepSeek').length).toBeGreaterThan(0)
    expect(within(editor).getByText('deepseek')).toBeVisible()
    expect(screen.getByLabelText('保存ID')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('保存ID')).toHaveValue('deepseek-main')
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByLabelText('API Key')).toHaveAttribute('placeholder', '留空则保留原密钥')
  })

  it('New API只按访问令牌判断密钥状态', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-academic')
    fireEvent.click(within(provider).getByRole('button', { name: '展开Academic Gateway的Key' }))
    expect(within(provider).getByText('密钥未配置')).toBeVisible()
  })

  it('折叠态显示供应商整体密钥状态', async () => {
    render(<SettingsView />)

    const academic = await screen.findByTestId('llm-provider-academic')
    const deepseek = screen.getByTestId('llm-provider-deepseek')
    expect(within(academic).getByText('New API')).toBeVisible()
    expect(within(academic).getByText('https://gateway.example.com')).toBeVisible()
    expect(within(academic).getByText('1个未配置')).toBeVisible()
    expect(within(deepseek).getByText('全部已配置')).toBeVisible()
  })

  it('保存后重新加载失败时保留编辑器并显示错误', async () => {
    fetchLlmConfig
      .mockResolvedValueOnce({ sources: llmSources })
      .mockRejectedValueOnce(new Error('重新加载失败'))
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '添加Key' }))
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('重新加载失败')
    expect(screen.getByRole('heading', { name: '为DeepSeek添加Key' })).toBeVisible()
    expect(screen.queryByText(/已保存Key 3/)).not.toBeInTheDocument()
  })

  it('保存运行参数时不会回写隐藏的LLM来源列表', async () => {
    render(<SettingsView />)

    await screen.findByRole('heading', { name: 'LLM供应商' })
    fireEvent.click(screen.getByRole('button', { name: '保存运行参数' }))

    await waitFor(() => {
      expect(saveSettings).toHaveBeenCalledWith({
        values: { PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS: '300' },
        secrets: {},
      })
    })
  })

  it('保存运行参数后重新加载失败时不显示成功', async () => {
    fetchSettings
      .mockResolvedValueOnce({
        values: {
          PULSEBOARD_LLM_USAGE_SOURCES: 'deepseek-main',
          PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS: '300',
        },
        secrets: {},
      })
      .mockRejectedValueOnce(new Error('Settings重新加载失败'))

    render(<SettingsView />)

    await screen.findByRole('heading', { name: 'LLM供应商' })
    fireEvent.click(screen.getByRole('button', { name: '保存运行参数' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Settings重新加载失败')
    expect(screen.queryByText('已保存，部分采集配置可能需要等待下一轮采集生效')).not.toBeInTheDocument()
  })

  it('拒绝超过64字符的最终保存ID', async () => {
    render(<SettingsView />)

    await screen.findByRole('heading', { name: 'LLM供应商' })
    fireEvent.click(screen.getByRole('button', { name: '新增供应商' }))
    fireEvent.change(screen.getByLabelText('供应商ID'), { target: { value: 'p'.repeat(40) } })
    fireEvent.change(screen.getByLabelText('Key ID'), { target: { value: 'k'.repeat(30) } })
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    expect(await screen.findByText(/保存ID不能超过64个字符/)).toBeVisible()
    expect(saveLlmConfig).not.toHaveBeenCalled()
  })

  it('拒绝与现有Key产生env前缀冲突的保存ID', async () => {
    render(<SettingsView />)

    await screen.findByRole('heading', { name: 'LLM供应商' })
    fireEvent.click(screen.getByRole('button', { name: '新增供应商' }))
    fireEvent.change(screen.getByLabelText('供应商ID'), { target: { value: 'deepseek' } })
    fireEvent.change(screen.getByLabelText('Key ID'), { target: { value: 'main' } })
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    expect(await screen.findByText(/保存ID与现有Key“主Key”冲突/)).toBeVisible()
    expect(saveLlmConfig).not.toHaveBeenCalled()
  })
})
