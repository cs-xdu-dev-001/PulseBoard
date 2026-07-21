import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteLlmConfig, deleteLlmProvider, fetchLlmActivity, refreshLlmUsage, saveLlmConfig, saveSettings, testLlmConfig, updateLlmProvider } from './api.js'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('API错误详情', () => {
  it('保存LLM配置失败时优先显示FastAPI detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'source_id deepseek_main conflicts with existing source_id deepseek-main' }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(saveLlmConfig({ source_id: 'deepseek_main' })).rejects.toThrow(
      'source_id deepseek_main conflicts with existing source_id deepseek-main',
    )
  })

  it('保存运行参数失败时保留HTTP状态兜底', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 500 })))

    await expect(saveSettings({ values: {}, secrets: {} })).rejects.toThrow('HTTP 500')
  })

  it('刷新LLM用量失败时显示字符串detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'collector failed' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(refreshLlmUsage()).rejects.toThrow('collector failed')
  })

  it('活动接口按年份和来源筛选', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ days: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchLlmActivity(2026, 'provider:academic')

    expect(fetchMock).toHaveBeenCalledWith('/api/llm/usage/activity?year=2026&source=provider%3Aacademic')
  })

  it('删除Key失败时复用FastAPI detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'source_id deepseek-main does not exist' }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(deleteLlmConfig('deepseek-main')).rejects.toThrow('source_id deepseek-main does not exist')
  })

  it('更新供应商公共配置使用PATCH', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await updateLlmProvider('academic', { provider_name: 'Academic', source_type: 'newapi_admin' })

    expect(fetchMock).toHaveBeenCalledWith('/api/llm/usage/providers/academic', expect.objectContaining({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_name: 'Academic', source_type: 'newapi_admin' }),
    }))
  })

  it('删除供应商使用DELETE', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteLlmProvider('deepseek')

    expect(fetchMock).toHaveBeenCalledWith('/api/llm/usage/providers/deepseek', { method: 'DELETE' })
  })

  it('测试单个Key使用POST并返回连通性结果', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      source_id: 'academic-main',
      status: 'offline',
      error: 'Unauthorized, invalid access token',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await testLlmConfig('academic-main')

    expect(fetchMock).toHaveBeenCalledWith('/api/llm/usage/config/academic-main/test', { method: 'POST' })
    expect(result.status).toBe('offline')
  })
})
