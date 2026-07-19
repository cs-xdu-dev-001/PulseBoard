import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  deleteLlmConfig,
  deleteLlmProvider,
  fetchLlmConfig,
  fetchSettings,
  saveLlmConfig,
  saveSettings,
  testLlmConfig,
  updateLlmProvider,
} from '../api.js'
import { SettingsView } from './SettingsView.jsx'

vi.mock('../api.js', () => ({
  fetchLlmConfig: vi.fn(),
  fetchSettings: vi.fn(),
  deleteLlmConfig: vi.fn(),
  deleteLlmProvider: vi.fn(),
  saveLlmConfig: vi.fn(),
  saveSettings: vi.fn(),
  testLlmConfig: vi.fn(),
  updateLlmProvider: vi.fn(),
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
    request_mode: 'chat_completions',
    test_model: 'deepseek-chat',
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
    request_mode: 'chat_completions',
    test_model: 'deepseek-chat',
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
    request_mode: 'responses',
    test_model: 'gpt-5.4',
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
    deleteLlmConfig.mockResolvedValue({ ok: true })
    deleteLlmProvider.mockResolvedValue({ ok: true })
    saveSettings.mockResolvedValue({ ok: true })
    saveLlmConfig.mockResolvedValue({ ok: true })
    testLlmConfig.mockResolvedValue({
      source_id: 'deepseek-main',
      display_name: '主Key',
      status: 'online',
      error: null,
      statistics: { status: 'online', error: null },
      model: { status: 'online', error: null, request_mode: 'chat_completions', test_model: 'deepseek-chat' },
      checked_at: '2026-07-17T04:00:00Z',
    })
    updateLlmProvider.mockResolvedValue({ ok: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
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
    fireEvent.change(screen.getByLabelText('模型API Key'), { target: { value: 'model-key-value' } })

    expect(screen.queryByLabelText('接入类型')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Base URL')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('User ID')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('模型请求方式')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('测试模型')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('账号余额令牌')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    await waitFor(() => {
      expect(saveLlmConfig).toHaveBeenCalledWith(expect.objectContaining({
        provider_id: 'academic',
        provider_name: 'Academic Gateway',
        source_id: 'academic-backup',
        display_name: '备用账号',
        source_type: 'newapi_admin',
        base_url: 'https://gateway.example.com',
        request_mode: 'responses',
        test_model: 'gpt-5.4',
        api_key: 'model-key-value',
        access_token: '',
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

  it('New API在供应商配置显示余额令牌状态，Key行只显示模型Key状态', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-academic')
    fireEvent.click(within(provider).getByRole('button', { name: '展开Academic Gateway的Key' }))
    expect(within(provider).getByText('余额令牌')).toBeVisible()
    expect(within(provider).getByText('未填写')).toBeVisible()
    expect(within(provider).getByText('模型Key已填写')).toBeVisible()
    expect(within(provider).queryByText('未填余额令牌')).not.toBeInTheDocument()
  })

  it('新增OpenAI兼容监控网关时配置项清晰区分上游Key和网关令牌', async () => {
    render(<SettingsView />)

    fireEvent.click(await screen.findByRole('button', { name: '新增供应商' }))
    fireEvent.change(screen.getByLabelText('供应商ID'), { target: { value: 'deepseek-gateway' } })
    fireEvent.change(screen.getByLabelText('供应商名称'), { target: { value: 'DeepSeek监控网关' } })
    fireEvent.change(screen.getByLabelText('接入类型'), { target: { value: 'openai_gateway' } })

    expect(screen.getByLabelText('上游Base URL')).toHaveValue('')
    expect(screen.getByLabelText('网关访问令牌')).toHaveValue('')
    expect(screen.getByLabelText('上游模型API Key')).toHaveValue('')

    fireEvent.change(screen.getByLabelText('Key ID'), { target: { value: 'main' } })
    fireEvent.change(screen.getByLabelText('Key展示名'), { target: { value: '主Key' } })
    fireEvent.change(screen.getByLabelText('上游Base URL'), { target: { value: 'https://api.deepseek.com' } })
    fireEvent.change(screen.getByLabelText('上游模型API Key'), { target: { value: 'sk-upstream' } })
    fireEvent.change(screen.getByLabelText('网关访问令牌'), { target: { value: 'pbk-local-token' } })
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    await waitFor(() => {
      expect(saveLlmConfig).toHaveBeenCalledWith(expect.objectContaining({
        provider_id: 'deepseek-gateway',
        provider_name: 'DeepSeek监控网关',
        source_id: 'deepseek-gateway-main',
        source_type: 'openai_gateway',
        base_url: 'https://api.deepseek.com',
        api_key: 'sk-upstream',
        access_token: 'pbk-local-token',
        request_mode: 'chat_completions',
        test_model: 'deepseek-chat',
      }))
    })
  })

  it('可以测试单个Key并在对应行显示在线状态', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '测试 主Key' }))

    await waitFor(() => {
      expect(testLlmConfig).toHaveBeenCalledWith('deepseek-main')
      expect(within(provider).getAllByText('在线')).toHaveLength(2)
    })
  })

  it('Key测试离线时显示上游返回的错误', async () => {
    testLlmConfig.mockResolvedValueOnce({
      source_id: 'deepseek-main',
      display_name: '主Key',
      status: 'offline',
      error: 'Unauthorized, invalid access token',
      statistics: { status: 'offline', error: 'Unauthorized, invalid access token' },
      model: { status: 'online', error: null, request_mode: 'chat_completions', test_model: 'deepseek-chat' },
      checked_at: '2026-07-17T04:00:00Z',
    })
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '测试 主Key' }))
    const keyRow = within(provider).getByText('主Key').closest('.provider-key-row')

    expect(await within(keyRow).findByText('离线')).toBeVisible()
    expect(within(keyRow).getByText('统计')).toBeVisible()
    expect(within(keyRow).getByText('模型')).toBeVisible()
    expect(within(keyRow).getByText('在线')).toBeVisible()
    expect(within(keyRow).getByText('Unauthorized, invalid access token')).toBeVisible()
  })

  it('编辑Key后清除旧的连通性结果', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '测试 主Key' }))
    const keyRow = within(provider).getByText('主Key').closest('.provider-key-row')
    expect(await within(keyRow).findAllByText('在线')).toHaveLength(2)

    fireEvent.click(within(keyRow).getByRole('button', { name: '编辑 主Key' }))
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    await waitFor(() => {
      const refreshedRow = within(provider).getByText('主Key').closest('.provider-key-row')
      expect(within(refreshedRow).getAllByText('未测试')).toHaveLength(2)
    })
  })

  it('配置变更后忽略仍在进行的旧测试结果', async () => {
    let resolveTest
    testLlmConfig.mockImplementationOnce(() => new Promise((resolve) => {
      resolveTest = resolve
    }))
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '测试 主Key' }))
    const keyRow = within(provider).getByText('主Key').closest('.provider-key-row')
    expect(keyRow.querySelector('.connection-status')).toHaveTextContent('测试中')

    fireEvent.click(within(keyRow).getByRole('button', { name: '编辑 主Key' }))
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))
    expect(await screen.findByText('已保存主Key')).toBeVisible()

    await act(async () => {
      resolveTest({
        source_id: 'deepseek-main',
        display_name: '主Key',
        status: 'online',
        error: null,
        statistics: { status: 'online', error: null },
        model: { status: 'online', error: null, request_mode: 'chat_completions', test_model: 'deepseek-chat' },
        checked_at: '2026-07-17T04:00:00Z',
      })
    })

    const refreshedRow = within(provider).getByText('主Key').closest('.provider-key-row')
    expect(within(refreshedRow).getAllByText('未测试')).toHaveLength(2)
    expect(within(refreshedRow).queryByText('在线')).not.toBeInTheDocument()
  })

  it('source_id与对象原型属性同名时仍可测试', async () => {
    fetchLlmConfig.mockResolvedValueOnce({
      sources: [
        ...llmSources,
        {
          source_id: 'constructor',
          provider_id: 'prototype-provider',
          provider_name: 'Prototype Provider',
          display_name: 'Constructor Key',
          source_type: 'deepseek_balance',
          base_url: null,
          user_id: '1',
          request_mode: 'chat_completions',
          test_model: 'deepseek-chat',
          has_api_key: true,
          has_access_token: false,
        },
      ],
    })
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-prototype-provider')
    fireEvent.click(within(provider).getByRole('button', { name: '展开Prototype Provider的Key' }))

    expect(within(provider).getByRole('button', { name: '测试 Constructor Key' })).toBeEnabled()
    expect(within(provider).getAllByText('未测试')).toHaveLength(2)
  })

  it('编辑New API供应商公共配置时可以更新账号余额令牌', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-academic')
    fireEvent.click(within(provider).getByRole('button', { name: '编辑供应商' }))

    expect(screen.getByRole('heading', { name: '编辑Academic Gateway' })).toBeVisible()
    expect(screen.getByLabelText('供应商ID')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('供应商名称')).toHaveValue('Academic Gateway')
    expect(screen.getByLabelText('接入类型')).toHaveValue('newapi_admin')
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://gateway.example.com')
    expect(screen.getByLabelText('User ID')).toHaveValue('1')
    expect(screen.getByLabelText('模型请求方式')).toHaveValue('responses')
    expect(screen.getByLabelText('测试模型')).toHaveValue('gpt-5.4')
    expect(screen.getByLabelText('账号余额令牌')).toHaveValue('')
    expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('模型API Key')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('供应商名称'), { target: { value: 'Academic' } })
    fireEvent.change(screen.getByLabelText('User ID'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('测试模型'), { target: { value: 'gpt-5.4-mini' } })
    fireEvent.change(screen.getByLabelText('账号余额令牌'), { target: { value: 'provider-token' } })
    fireEvent.click(screen.getByRole('button', { name: '保存供应商' }))

    await waitFor(() => {
      expect(updateLlmProvider).toHaveBeenCalledWith('academic', {
        provider_name: 'Academic',
        source_type: 'newapi_admin',
        base_url: 'https://gateway.example.com',
        request_mode: 'responses',
        test_model: 'gpt-5.4-mini',
        user_id: '2',
        access_token: 'provider-token',
      })
    })
  })

  it('可以删除单个Key并重新加载配置', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '删除Key 主Key' }))

    await waitFor(() => {
      expect(deleteLlmConfig).toHaveBeenCalledWith('deepseek-main')
      expect(fetchLlmConfig).toHaveBeenCalledTimes(2)
    })
  })

  it('可以删除整个供应商', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '删除供应商' }))

    await waitFor(() => {
      expect(deleteLlmProvider).toHaveBeenCalledWith('deepseek')
      expect(fetchLlmConfig).toHaveBeenCalledTimes(2)
    })
  })

  it('折叠态显示供应商整体密钥状态', async () => {
    render(<SettingsView />)

    const academic = await screen.findByTestId('llm-provider-academic')
    const deepseek = screen.getByTestId('llm-provider-deepseek')
    expect(within(academic).getByText('New API')).toBeVisible()
    expect(within(academic).getByText('https://gateway.example.com')).toBeVisible()
    expect(within(academic).getByText('余额令牌未填')).toBeVisible()
    expect(within(academic).getByText('Responses · gpt-5.4')).toBeVisible()
    expect(within(deepseek).getByText('凭据已填写')).toBeVisible()
  })

  it('展开New API供应商后显示完整公共配置', async () => {
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-academic')
    fireEvent.click(within(provider).getByRole('button', { name: '展开Academic Gateway的Key' }))
    const panel = within(provider).getByText('供应商配置').closest('.provider-config-panel')

    expect(within(panel).getByText('管理统计')).toBeVisible()
    expect(within(panel).getByText('https://gateway.example.com/api/user/self')).toBeVisible()
    expect(within(panel).getByText('模型接口')).toBeVisible()
    expect(within(panel).getByText('https://gateway.example.com/v1/responses')).toBeVisible()
    expect(within(panel).getByText('User ID')).toBeVisible()
    expect(within(panel).getByText('1')).toBeVisible()
    expect(within(panel).getByText('测试模型')).toBeVisible()
    expect(within(panel).getByText('gpt-5.4')).toBeVisible()
  })

  it('测试模型缺失时在公共配置区提供配置入口', async () => {
    fetchLlmConfig.mockResolvedValueOnce({
      sources: [
        {
          ...llmSources[2],
          provider_name: 'EduModel',
          base_url: 'https://academicedu.me',
          test_model: '',
        },
      ],
    })
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-academic')
    fireEvent.click(within(provider).getByRole('button', { name: '展开EduModel的Key' }))
    const panel = within(provider).getByText('供应商配置').closest('.provider-config-panel')
    expect(within(panel).getByText('未配置')).toBeVisible()

    fireEvent.click(within(panel).getByRole('button', { name: '配置模型' }))

    expect(screen.getByRole('heading', { name: '编辑EduModel' })).toBeVisible()
    expect(screen.getByLabelText('测试模型')).toHaveValue('')
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

  it('保存成功但重新加载失败时也清除旧测试结果', async () => {
    fetchLlmConfig
      .mockResolvedValueOnce({ sources: llmSources })
      .mockRejectedValueOnce(new Error('重新加载失败'))
    render(<SettingsView />)

    const provider = await screen.findByTestId('llm-provider-deepseek')
    fireEvent.click(within(provider).getByRole('button', { name: '展开DeepSeek的Key' }))
    fireEvent.click(within(provider).getByRole('button', { name: '测试 主Key' }))
    const keyRow = within(provider).getByText('主Key').closest('.provider-key-row')
    expect(await within(keyRow).findAllByText('在线')).toHaveLength(2)

    fireEvent.click(within(keyRow).getByRole('button', { name: '编辑 主Key' }))
    fireEvent.click(screen.getByRole('button', { name: '保存API Key' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('重新加载失败')
    expect(within(keyRow).getAllByText('未测试')).toHaveLength(2)
    expect(within(keyRow).queryByText('在线')).not.toBeInTheDocument()
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
