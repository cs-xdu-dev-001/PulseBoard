import { useEffect, useMemo, useRef, useState } from 'react'

import { deleteLlmConfig, deleteLlmProvider, fetchLlmConfig, saveLlmConfig, testLlmConfig, updateLlmProvider } from '../api.js'

const emptyForm = {
  mode: 'create-provider',
  original_source_id: '',
  provider_id: '',
  provider_name: '',
  key_id: 'main',
  display_name: '主Key',
  source_type: 'deepseek_balance',
  base_url: '',
  api_key: '',
  access_token: '',
  user_id: '1',
  request_mode: 'chat_completions',
  test_model: 'deepseek-chat',
}

export function LlmProviderSettings() {
  const [configs, setConfigs] = useState([])
  const [editor, setEditor] = useState(null)
  const [expandedProviders, setExpandedProviders] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testingSources, setTestingSources] = useState(() => new Map())
  const [testResults, setTestResults] = useState(() => new Map())
  const testRequestIds = useRef(new Map())
  const nextTestRequestId = useRef(0)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const groups = useMemo(() => groupConfigs(configs), [configs])

  async function load() {
    setLoading(true)
    try {
      const payload = await fetchLlmConfig()
      setConfigs(payload.sources || [])
      invalidateTestResults()
      setError('')
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function openNewProvider() {
    setEditor({ ...emptyForm })
    setStatus('')
    setError('')
  }

  function openEditProvider(group) {
    const template = providerMetadata(group)
    setEditor({
      ...emptyForm,
      mode: 'edit-provider',
      provider_id: group.provider_id,
      provider_name: group.provider_name,
      source_type: template.source_type || 'deepseek_balance',
      base_url: template.base_url || '',
      user_id: template.user_id || '1',
      request_mode: template.request_mode || defaultRequestMode(template.source_type),
      test_model: template.test_model || defaultTestModel(template.source_type),
    })
    setStatus('')
    setError('')
  }

  function openNewKey(group) {
    const template = providerMetadata(group)
    setEditor({
      ...emptyForm,
      mode: 'create-key',
      provider_id: group.provider_id,
      provider_name: group.provider_name,
      key_id: `key-${group.items.length + 1}`,
      display_name: `Key ${group.items.length + 1}`,
      source_type: template.source_type || 'deepseek_balance',
      base_url: template.base_url || '',
      user_id: template.user_id || '1',
      request_mode: template.request_mode || defaultRequestMode(template.source_type),
      test_model: template.test_model || defaultTestModel(template.source_type),
    })
    setStatus('')
    setError('')
  }

  function openEditKey(item) {
    const providerId = item.provider_id || item.source_id
    setEditor({
      ...emptyForm,
      mode: 'edit-key',
      original_source_id: item.source_id,
      provider_id: providerId,
      provider_name: item.provider_name || item.display_name || providerId,
      key_id: keyIdFromSource(item.source_id, providerId),
      display_name: item.display_name || item.source_id,
      source_type: item.source_type,
      base_url: item.base_url || '',
      user_id: item.user_id || '1',
      request_mode: item.request_mode || defaultRequestMode(item.source_type),
      test_model: item.test_model || defaultTestModel(item.source_type),
    })
    setStatus('')
    setError('')
  }

  async function refreshAfterMutation(message) {
    invalidateTestResults()
    const refreshed = await load()
    if (!refreshed) return false
    setEditor(null)
    setStatus(message)
    setError('')
    return true
  }

  function invalidateTestResults() {
    testRequestIds.current.clear()
    setTestingSources(new Map())
    setTestResults(new Map())
  }

  async function handleSave(event) {
    event.preventDefault()
    if (!editor) return
    setError('')
    setStatus('')
    setSaving(true)
    try {
      if (editor.mode === 'edit-provider') {
        await updateLlmProvider(editor.provider_id, providerPayload(editor))
        await refreshAfterMutation(`已更新${editor.provider_name || editor.provider_id}`)
        return
      }

      const providerId = normalizeIdPart(editor.provider_id)
      const keyId = normalizeIdPart(editor.key_id)
      if (!providerId || !keyId) {
        setError('供应商ID和Key ID只能使用小写字母、数字、-、_。')
        return
      }
      const sourceId = editor.original_source_id || `${providerId}-${keyId}`
      if (sourceId.length > 64) {
        setError('保存ID不能超过64个字符。')
        return
      }
      const conflict = configs.find((item) => item.source_id !== editor.original_source_id && envKey(item.source_id) === envKey(sourceId))
      if (conflict) {
        setError(`保存ID与现有Key“${conflict.display_name}”冲突。`)
        return
      }

      const payload = keyPayload(editor, providerId, keyId, sourceId)
      await saveLlmConfig(payload)
      await refreshAfterMutation(`已保存${payload.display_name}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteKey(item) {
    if (!window.confirm(`删除Key“${item.display_name}”？`)) return
    setError('')
    setStatus('')
    setSaving(true)
    try {
      await deleteLlmConfig(item.source_id)
      await refreshAfterMutation(`已删除${item.display_name}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteProvider(group) {
    if (!window.confirm(`删除供应商“${group.provider_name}”及其${group.items.length}个Key？`)) return
    setError('')
    setStatus('')
    setSaving(true)
    try {
      await deleteLlmProvider(group.provider_id)
      await refreshAfterMutation(`已删除${group.provider_name}`)
      setExpandedProviders((current) => {
        const next = { ...current }
        delete next[group.provider_id]
        return next
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleTestKey(item) {
    const requestId = nextTestRequestId.current + 1
    nextTestRequestId.current = requestId
    testRequestIds.current.set(item.source_id, requestId)
    setTestingSources((current) => new Map(current).set(item.source_id, true))
    setTestResults((current) => {
      const next = new Map(current)
      next.delete(item.source_id)
      return next
    })
    try {
      const result = await testLlmConfig(item.source_id)
      if (testRequestIds.current.get(item.source_id) === requestId) {
        setTestResults((current) => new Map(current).set(item.source_id, result))
      }
    } catch (err) {
      if (testRequestIds.current.get(item.source_id) === requestId) {
        setTestResults((current) => new Map(current).set(item.source_id, {
          status: 'error',
          error: err.message,
          statistics: { status: 'error', error: err.message },
          model: { status: 'error', error: err.message },
        }))
      }
    } finally {
      if (testRequestIds.current.get(item.source_id) === requestId) {
        testRequestIds.current.delete(item.source_id)
        setTestingSources((current) => {
          const next = new Map(current)
          next.delete(item.source_id)
          return next
        })
      }
    }
  }

  function handleSourceTypeChange(sourceType) {
    setEditor({
      ...editor,
      source_type: sourceType,
      request_mode: defaultRequestMode(sourceType),
      test_model: defaultTestModel(sourceType),
    })
  }

  const sourceIdPreview = editor && editor.mode !== 'edit-provider'
    ? editor.original_source_id || `${normalizeIdPart(editor.provider_id) || 'provider'}-${normalizeIdPart(editor.key_id) || 'key'}`
    : ''
  const showProviderFields = editor?.mode === 'create-provider' || editor?.mode === 'edit-provider'
  const showKeyFields = editor?.mode !== 'edit-provider'
  const isExistingKey = editor?.mode === 'edit-key'
  const isProviderLocked = editor?.mode === 'edit-provider'

  return (
    <section className="llm-settings-panel">
      <header className="llm-settings-header">
        <div>
          <h2>LLM供应商</h2>
          <span>{configs.length}个API Key</span>
        </div>
        <button className="glow-button" type="button" onClick={openNewProvider}>新增供应商</button>
      </header>

      {error && <div className="settings-inline-message danger" role="alert">配置请求失败：{error}</div>}
      {status && <div className="settings-inline-message" role="status" aria-live="polite">{status}</div>}

      {editor && (
        <form className="llm-key-editor" onSubmit={handleSave}>
          <div className="llm-key-editor-title">
            <h3>{editorTitle(editor)}</h3>
            <button className="subtle-button" type="button" onClick={() => setEditor(null)}>取消</button>
          </div>

          {!showProviderFields && (
            <div className="llm-provider-context">
              <strong>{editor.provider_name}</strong>
              <code>{editor.provider_id}</code>
              <span>{sourceTypeText(editor.source_type)}</span>
              <span>{providerEndpointText(editor)}</span>
              <span>{requestConfigText(editor)}</span>
            </div>
          )}

          <div className="llm-editor-sections">
            {showProviderFields && (
              <fieldset className="llm-editor-section">
                <legend>供应商</legend>
                <div className="llm-key-editor-grid">
                  <label>
                    <span>供应商ID</span>
                    <input
                      value={editor.provider_id}
                      onChange={(event) => setEditor({ ...editor, provider_id: event.target.value })}
                      placeholder="deepseek"
                      readOnly={isProviderLocked}
                    />
                  </label>
                  <label>
                    <span>供应商名称</span>
                    <input
                      value={editor.provider_name}
                      onChange={(event) => setEditor({ ...editor, provider_name: event.target.value })}
                      placeholder="DeepSeek"
                    />
                  </label>
                  <label>
                    <span>接入类型</span>
                    <select value={editor.source_type} onChange={(event) => handleSourceTypeChange(event.target.value)}>
                      <option value="deepseek_balance">DeepSeek官方余额</option>
                      <option value="newapi_admin">New API管理统计</option>
                      <option value="openai_gateway">OpenAI兼容监控网关</option>
                    </select>
                  </label>
                  {providerUsesBaseUrl(editor.source_type) && (
                    <>
                      <label>
                        <span>{editor.source_type === 'openai_gateway' ? '上游Base URL' : 'Base URL'}</span>
                        <input value={editor.base_url} onChange={(event) => setEditor({ ...editor, base_url: event.target.value })} placeholder={editor.source_type === 'openai_gateway' ? 'https://api.deepseek.com' : 'https://your-new-api.example.com'} />
                      </label>
                      {editor.source_type === 'newapi_admin' && (
                        <>
                          <label>
                            <span>User ID</span>
                            <input value={editor.user_id} onChange={(event) => setEditor({ ...editor, user_id: event.target.value })} placeholder="1" />
                          </label>
                          <label className="llm-secret-field">
                            <span>账号余额令牌</span>
                            <input
                              type="password"
                              value={editor.access_token}
                              onChange={(event) => setEditor({ ...editor, access_token: event.target.value })}
                              placeholder={editor.mode === 'edit-provider' ? '留空则保留原令牌' : '用于读取账号余额'}
                            />
                          </label>
                        </>
                      )}
                    </>
                  )}
                  <label>
                    <span>模型请求方式</span>
                    <select value={editor.request_mode} onChange={(event) => setEditor({ ...editor, request_mode: event.target.value })}>
                      <option value="responses">Responses API</option>
                      <option value="chat_completions">Chat Completions</option>
                    </select>
                  </label>
                  <label>
                    <span>测试模型</span>
                    <input value={editor.test_model} onChange={(event) => setEditor({ ...editor, test_model: event.target.value })} placeholder={defaultTestModel(editor.source_type) || 'gpt-5.4'} />
                  </label>
                </div>
              </fieldset>
            )}

            {showKeyFields && (
              <fieldset className="llm-editor-section">
                <legend>{editor.mode === 'create-provider' ? '首个Key' : 'API Key'}</legend>
                <div className="llm-key-editor-grid">
                  <label>
                    <span>Key ID</span>
                    <input
                      value={editor.key_id}
                      onChange={(event) => setEditor({ ...editor, key_id: event.target.value })}
                      placeholder="main"
                      readOnly={isExistingKey}
                    />
                  </label>
                  <label>
                    <span>Key展示名</span>
                    <input value={editor.display_name} onChange={(event) => setEditor({ ...editor, display_name: event.target.value })} placeholder="主Key" />
                  </label>
                  <label>
                    <span>保存ID</span>
                    <input className="source-id-input" value={sourceIdPreview} readOnly />
                  </label>
                  {editor.source_type === 'deepseek_balance' ? (
                    <label className="llm-secret-field">
                      <span>API Key</span>
                      <input
                        type="password"
                        value={editor.api_key}
                        onChange={(event) => setEditor({ ...editor, api_key: event.target.value })}
                        placeholder={isExistingKey ? '留空则保留原密钥' : 'sk-...'}
                      />
                    </label>
                  ) : editor.source_type === 'openai_gateway' ? (
                    <>
                      <label className="llm-secret-field">
                        <span>上游模型API Key</span>
                        <input
                          type="password"
                          value={editor.api_key}
                          onChange={(event) => setEditor({ ...editor, api_key: event.target.value })}
                          placeholder={isExistingKey ? '留空则保留上游Key' : 'sk-...'}
                        />
                      </label>
                      <label className="llm-secret-field">
                        <span>网关访问令牌</span>
                        <input
                          type="password"
                          value={editor.access_token}
                          onChange={(event) => setEditor({ ...editor, access_token: event.target.value })}
                          placeholder={isExistingKey ? '留空则保留网关令牌' : 'pbk-...'}
                        />
                      </label>
                    </>
                  ) : (
                    <label className="llm-secret-field">
                      <span>模型API Key</span>
                      <input
                        type="password"
                        value={editor.api_key}
                        onChange={(event) => setEditor({ ...editor, api_key: event.target.value })}
                        placeholder={isExistingKey ? '留空则保留原Key' : 'sk-...'}
                      />
                    </label>
                  )}
                </div>
              </fieldset>
            )}
          </div>

          <footer className="llm-key-editor-actions">
            <span>密钥只写入服务器.env，页面不会回显。</span>
            <button className="glow-button" type="submit" disabled={saving}>{saving ? '保存中' : editor.mode === 'edit-provider' ? '保存供应商' : '保存API Key'}</button>
          </footer>
        </form>
      )}

      <div className="provider-settings-list">
        {groups.map((group) => {
          const expanded = Boolean(expandedProviders[group.provider_id])
          const unconfiguredCount = group.items.filter((item) => !credentialState(item).complete).length
          const providerMeta = providerMetadata(group)
          const providerTokenMissing = providerMeta.source_type === 'newapi_admin' && !providerMeta.has_access_token
          const credentialSummary = providerTokenMissing
            ? '余额令牌未填'
            : unconfiguredCount
              ? `${unconfiguredCount}个Key凭据不完整`
              : '凭据已填写'
          return (
            <article className="provider-settings-row" data-testid={`llm-provider-${group.provider_id}`} key={group.provider_id}>
              <header>
                <div className="provider-settings-identity">
                  <h3>{group.provider_name}</h3>
                  <code>{group.provider_id}</code>
                  <div className="provider-settings-summary">
                    <span className="provider-source-type">{sourceTypeText(providerMeta.source_type)}</span>
                    <span className="provider-endpoint">{providerEndpointText(providerMeta)}</span>
                    <span className="provider-model-config">{requestConfigText(providerMeta)}</span>
                    <span className="provider-key-count">{group.items.length}个Key</span>
                    <span className={`provider-secret-summary ${providerTokenMissing || unconfiguredCount ? 'warning' : 'configured'}`}>
                      {credentialSummary}
                    </span>
                  </div>
                </div>
                <div className="provider-settings-actions">
                  <button
                    className="provider-toggle"
                    type="button"
                    aria-label={`${expanded ? '收起' : '展开'}${group.provider_name}的Key`}
                    aria-expanded={expanded}
                    onClick={() => setExpandedProviders((current) => ({ ...current, [group.provider_id]: !expanded }))}
                  >
                    <span aria-hidden="true" />
                  </button>
                  <button className="subtle-button" type="button" onClick={() => openEditProvider(group)}>编辑供应商</button>
                  <button className="subtle-button" type="button" onClick={() => openNewKey(group)}>添加Key</button>
                  <button className="subtle-button danger-button" type="button" onClick={() => handleDeleteProvider(group)}>删除供应商</button>
                </div>
              </header>
              {expanded && (
                <>
                  <ProviderConfigPanel item={providerMeta} onConfigureModel={() => openEditProvider(group)} />
                  <div className="provider-key-list">
                    <div className="provider-key-columns" aria-hidden="true">
                      <span>API Key</span>
                      <span>Key凭据</span>
                      <span>连通性</span>
                      <span>操作</span>
                    </div>
                    {group.items.map((item) => {
                      const testing = Boolean(testingSources.get(item.source_id))
                      const testResult = testResults.get(item.source_id)
                      return (
                        <div className="provider-key-row" key={item.source_id}>
                          <div className="provider-key-name">
                            <strong>{item.display_name}</strong>
                            <code>{item.source_id}</code>
                          </div>
                          <CredentialBadges item={item} />
                          <div className="key-test-status" aria-live="polite">
                            <ConnectionResult label="统计" result={testResult?.statistics} testing={testing} />
                            <ConnectionResult label="模型" result={testResult?.model} testing={testing} />
                          </div>
                          <div className="provider-key-actions">
                            <button
                              className="subtle-button test-button"
                              type="button"
                              aria-label={`测试 ${item.display_name}`}
                              disabled={testing}
                              onClick={() => handleTestKey(item)}
                            >
                              {testing ? '测试中' : '测试'}
                            </button>
                            <button className="subtle-button" type="button" aria-label={`编辑 ${item.display_name}`} onClick={() => openEditKey(item)}>编辑</button>
                            <button className="subtle-button danger-button" type="button" aria-label={`删除Key ${item.display_name}`} onClick={() => handleDeleteKey(item)}>删除Key</button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </article>
          )
        })}
        {!loading && groups.length === 0 && <div className="settings-empty">尚未配置LLM供应商。</div>}
        {loading && <div className="settings-empty" role="status">正在读取LLM配置</div>}
      </div>
    </section>
  )
}

function ProviderConfigPanel({ item, onConfigureModel }) {
  const missingModel = !item.test_model
  return (
    <section className="provider-config-panel">
      <div className="provider-config-title">
        <strong>供应商配置</strong>
        {missingModel && <button className="subtle-button" type="button" onClick={onConfigureModel}>配置模型</button>}
      </div>
      <div className="provider-config-grid">
        {providerConfigItems(item).map((entry) => (
          <div className={`provider-config-item ${entry.warning ? 'warning' : ''}`} key={entry.label}>
            <span>{entry.label}</span>
            <strong title={entry.value}>{entry.value}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}

function CredentialBadges({ item }) {
  return (
    <div className="credential-stack">
      {credentialItems(item).map((entry) => (
        <span className={`secret-status ${entry.complete ? 'configured' : ''}`} key={entry.label}>
          {entry.text}
        </span>
      ))}
    </div>
  )
}

function keyPayload(editor, providerId, keyId, sourceId) {
  return {
    provider_id: providerId,
    provider_name: editor.provider_name.trim() || providerId,
    source_id: sourceId,
    display_name: editor.display_name.trim() || keyId,
    source_type: editor.source_type,
    base_url: providerUsesBaseUrl(editor.source_type) ? editor.base_url.trim() : '',
    api_key: editor.api_key.trim(),
    access_token: editor.source_type === 'newapi_admin' || editor.source_type === 'openai_gateway' ? editor.access_token.trim() : '',
    user_id: editor.source_type === 'newapi_admin' ? editor.user_id.trim() || '1' : '',
    request_mode: editor.request_mode,
    test_model: editor.test_model.trim(),
  }
}

function providerPayload(editor) {
  return {
    provider_name: editor.provider_name.trim() || editor.provider_id,
    source_type: editor.source_type,
    base_url: providerUsesBaseUrl(editor.source_type) ? editor.base_url.trim() : '',
    user_id: editor.source_type === 'newapi_admin' ? editor.user_id.trim() || '1' : '',
    request_mode: editor.request_mode,
    test_model: editor.test_model.trim(),
    access_token: editor.source_type === 'newapi_admin' ? editor.access_token.trim() : '',
  }
}

function groupConfigs(items = []) {
  const groups = new Map()
  for (const item of items) {
    const providerId = item.provider_id || item.source_id
    const providerName = item.provider_name || item.display_name || providerId
    if (!groups.has(providerId)) {
      groups.set(providerId, { provider_id: providerId, provider_name: providerName, items: [] })
    }
    groups.get(providerId).items.push(item)
  }
  return Array.from(groups.values()).sort((a, b) => a.provider_name.localeCompare(b.provider_name))
}

function normalizeIdPart(value) {
  const normalized = String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')
  return /^[a-z0-9_-]{1,64}$/.test(normalized) ? normalized : ''
}

function envKey(value) {
  return String(value || '').toUpperCase().replaceAll('-', '_')
}

function keyIdFromSource(sourceId, providerId) {
  const prefix = `${providerId}-`
  return sourceId.startsWith(prefix) ? sourceId.slice(prefix.length) : 'main'
}

function sourceTypeText(sourceType) {
  if (sourceType === 'newapi_admin') return 'New API'
  if (sourceType === 'openai_gateway') return '监控网关'
  return 'DeepSeek'
}

function providerMetadata(group) {
  return group.items[0] || {}
}

function providerEndpointText(item) {
  if (item.source_type === 'openai_gateway') return item.base_url || '未配置上游接口'
  return item.source_type === 'newapi_admin' ? item.base_url || '未配置接口' : '官方接口'
}

function providerConfigItems(item) {
  if (item.source_type === 'openai_gateway') {
    return [
      { label: '接入类型', value: sourceTypeText(item.source_type) },
      { label: '上游Base URL', value: item.base_url || '未配置上游接口', warning: !item.base_url },
      { label: '上游模型接口', value: modelEndpointText(item), warning: !item.base_url },
      { label: '请求方式', value: requestModeText(item.request_mode || defaultRequestMode(item.source_type)) },
      { label: '测试模型', value: item.test_model || defaultTestModel(item.source_type) || '未配置', warning: !item.test_model },
      { label: '网关地址', value: '/api/llm/gateway/{保存ID}/v1' },
    ]
  }
  if (item.source_type === 'newapi_admin') {
    return [
      { label: '接入类型', value: sourceTypeText(item.source_type) },
      { label: 'Base URL', value: item.base_url || '未配置接口', warning: !item.base_url },
      { label: '管理统计', value: newApiAdminEndpointText(item), warning: !item.base_url },
      { label: '模型接口', value: modelEndpointText(item), warning: !item.base_url },
      { label: '余额令牌', value: item.has_access_token ? '已填写' : '未填写', warning: !item.has_access_token },
      { label: 'User ID', value: item.user_id || '1' },
      { label: '请求方式', value: requestModeText(item.request_mode || defaultRequestMode(item.source_type)) },
      { label: '测试模型', value: item.test_model || '未配置', warning: !item.test_model },
    ]
  }
  return [
    { label: '接入类型', value: sourceTypeText(item.source_type) },
    { label: '余额接口', value: deepseekBalanceEndpointText() },
    { label: '模型接口', value: modelEndpointText(item) },
    { label: '请求方式', value: requestModeText(item.request_mode || defaultRequestMode(item.source_type)) },
    { label: '测试模型', value: item.test_model || defaultTestModel(item.source_type) || '未配置', warning: !item.test_model },
  ]
}

function credentialItems(item) {
  if (item.source_type === 'openai_gateway') {
    return [
      {
        label: 'api_key',
        complete: Boolean(item.has_api_key),
        text: item.has_api_key ? '上游Key已填写' : '缺上游Key',
      },
      {
        label: 'access_token',
        complete: Boolean(item.has_access_token),
        text: item.has_access_token ? '网关令牌已填写' : '缺网关令牌',
      },
    ]
  }
  if (item.source_type !== 'newapi_admin') {
    return [{
      label: 'api_key',
      complete: Boolean(item.has_api_key),
      text: item.has_api_key ? 'API Key已填写' : '缺API Key',
    }]
  }
  return [
    {
      label: 'api_key',
      complete: Boolean(item.has_api_key),
      text: item.has_api_key ? '模型Key已填写' : '缺模型Key',
    },
  ]
}

function credentialState(item) {
  if (item.source_type === 'openai_gateway') {
    if (item.has_api_key && item.has_access_token) return { complete: true, label: '网关凭据已填写' }
    return { complete: false, label: '缺网关凭据' }
  }
  if (item.source_type !== 'newapi_admin') {
    return { complete: Boolean(item.has_api_key), label: item.has_api_key ? 'API Key已填写' : '缺API Key' }
  }
  if (item.has_api_key) return { complete: true, label: '模型Key已填写' }
  return { complete: false, label: '缺模型Key' }
}

function connectionStatusText(status) {
  if (status === 'online') return '在线'
  if (status === 'degraded') return '部分异常'
  if (status === 'offline') return '离线'
  if (status === 'error') return '测试失败'
  if (status === 'not_configured') return '未配置'
  return '未测试'
}

function ConnectionResult({ label, result, testing }) {
  const status = testing ? 'testing' : result?.status || 'untested'
  return (
    <div className="connection-result">
      <span className="connection-label">{label}</span>
      <span className={`connection-status ${status}`}>{testing ? '测试中' : connectionStatusText(status)}</span>
      {result?.error && <p title={result.error}>{result.error}</p>}
    </div>
  )
}

function defaultRequestMode(sourceType) {
  return sourceType === 'deepseek_balance' || sourceType === 'openai_gateway' ? 'chat_completions' : 'responses'
}

function defaultTestModel(sourceType) {
  return sourceType === 'deepseek_balance' || sourceType === 'openai_gateway' ? 'deepseek-chat' : ''
}

function requestModeText(requestMode) {
  return requestMode === 'chat_completions' ? 'Chat Completions' : 'Responses'
}

function newApiAdminEndpointText(item) {
  const base = normalizedNewApiBase(item.base_url)
  return base ? `${base}/api/user/self` : '未配置接口'
}

function modelEndpointText(item) {
  const base = modelBaseUrl(item)
  if (!base) return '未配置接口'
  const resource = (item.request_mode || defaultRequestMode(item.source_type)) === 'chat_completions'
    ? 'chat/completions'
    : 'responses'
  return `${base}/${resource}`
}

function modelBaseUrl(item) {
  if (item.source_type === 'deepseek_balance') {
    const deepseekBase = String(item.base_url || 'https://api.deepseek.com').trim().replace(/\/+$/, '')
    return deepseekBase.endsWith('/v1') ? deepseekBase : `${deepseekBase}/v1`
  }
  const baseUrl = String(item.base_url || '').trim().replace(/\/+$/, '')
  if (!baseUrl) return ''
  return baseUrl.endsWith('/v1') ? baseUrl : `${baseUrl}/v1`
}

function providerUsesBaseUrl(sourceType) {
  return sourceType === 'newapi_admin' || sourceType === 'openai_gateway'
}

function normalizedNewApiBase(baseUrl) {
  const normalized = String(baseUrl || '').trim().replace(/\/+$/, '')
  if (!normalized) return ''
  return normalized.endsWith('/v1') ? normalized.slice(0, -3) : normalized
}

function deepseekBalanceEndpointText() {
  return 'https://api.deepseek.com/user/balance'
}

function requestConfigText(item) {
  return `${requestModeText(item.request_mode || defaultRequestMode(item.source_type))} · ${item.test_model || '未配置模型'}`
}

function editorTitle(editor) {
  if (editor.mode === 'edit-provider') return `编辑${editor.provider_name}`
  if (editor.mode === 'edit-key') return `编辑${editor.display_name}`
  if (editor.mode === 'create-key') return `为${editor.provider_name}添加Key`
  return '新增供应商'
}
