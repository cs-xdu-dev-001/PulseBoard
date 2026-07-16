import { afterEach, describe, expect, it, vi } from 'vitest'

import { refreshLlmUsage, saveLlmConfig, saveSettings } from './api.js'

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
})
