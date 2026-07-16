import { useEffect, useMemo, useState } from 'react'

import { deleteLlmConfig, deleteLlmProvider, fetchLlmConfig, saveLlmConfig, updateLlmProvider } from '../api.js'

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
}

export function LlmProviderSettings() {
  const [configs, setConfigs] = useState([])
  const [editor, setEditor] = useState(null)
  const [expandedProviders, setExpandedProviders] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const groups = useMemo(() => groupConfigs(configs), [configs])

  async function load() {
    setLoading(true)
    try {
      const payload = await fetchLlmConfig()
      setConfigs(payload.sources || [])
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
    })
    setStatus('')
    setError('')
  }

  async function refreshAfterMutation(message) {
    const refreshed = await load()
    if (!refreshed) return false
    setEditor(null)
    setStatus(message)
    setError('')
    return true
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
                    <select value={editor.source_type} onChange={(event) => setEditor({ ...editor, source_type: event.target.value })}>
                      <option value="deepseek_balance">DeepSeek官方余额</option>
                      <option value="newapi_admin">New API管理统计</option>
                    </select>
                  </label>
                  {editor.source_type === 'newapi_admin' && (
                    <>
                      <label>
                        <span>Base URL</span>
                        <input value={editor.base_url} onChange={(event) => setEditor({ ...editor, base_url: event.target.value })} placeholder="https://your-new-api.example.com" />
                      </label>
                      <label>
                        <span>User ID</span>
                        <input value={editor.user_id} onChange={(event) => setEditor({ ...editor, user_id: event.target.value })} placeholder="1" />
                      </label>
                    </>
                  )}
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
                  ) : (
                    <label className="llm-secret-field">
                      <span>访问令牌</span>
                      <input
                        type="password"
                        value={editor.access_token}
                        onChange={(event) => setEditor({ ...editor, access_token: event.target.value })}
                        placeholder={isExistingKey ? '留空则保留原密钥' : 'New API access token'}
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
          const unconfiguredCount = group.items.filter((item) => !isSecretConfigured(item)).length
          const providerMeta = providerMetadata(group)
          return (
            <article className="provider-settings-row" data-testid={`llm-provider-${group.provider_id}`} key={group.provider_id}>
              <header>
                <div className="provider-settings-identity">
                  <h3>{group.provider_name}</h3>
                  <code>{group.provider_id}</code>
                  <div className="provider-settings-summary">
                    <span className="provider-source-type">{sourceTypeText(providerMeta.source_type)}</span>
                    <span className="provider-endpoint">{providerEndpointText(providerMeta)}</span>
                    <span className="provider-key-count">{group.items.length}个Key</span>
                    <span className={`provider-secret-summary ${unconfiguredCount ? 'warning' : 'configured'}`}>
                      {unconfiguredCount ? `${unconfiguredCount}个未配置` : '全部已配置'}
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
                <div className="provider-key-list">
                  <div className="provider-key-columns" aria-hidden="true">
                    <span>API Key</span>
                    <span>密钥状态</span>
                    <span>操作</span>
                  </div>
                  {group.items.map((item) => (
                    <div className="provider-key-row" key={item.source_id}>
                      <div className="provider-key-name">
                        <strong>{item.display_name}</strong>
                        <code>{item.source_id}</code>
                      </div>
                      <span className={isSecretConfigured(item) ? 'secret-status configured' : 'secret-status'}>
                        {isSecretConfigured(item) ? '密钥已配置' : '密钥未配置'}
                      </span>
                      <div className="provider-key-actions">
                        <button className="subtle-button" type="button" aria-label={`编辑 ${item.display_name}`} onClick={() => openEditKey(item)}>编辑</button>
                        <button className="subtle-button danger-button" type="button" aria-label={`删除Key ${item.display_name}`} onClick={() => handleDeleteKey(item)}>删除Key</button>
                      </div>
                    </div>
                  ))}
                </div>
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

function keyPayload(editor, providerId, keyId, sourceId) {
  return {
    provider_id: providerId,
    provider_name: editor.provider_name.trim() || providerId,
    source_id: sourceId,
    display_name: editor.display_name.trim() || keyId,
    source_type: editor.source_type,
    base_url: editor.source_type === 'newapi_admin' ? editor.base_url.trim() : '',
    api_key: editor.source_type === 'deepseek_balance' ? editor.api_key.trim() : '',
    access_token: editor.source_type === 'newapi_admin' ? editor.access_token.trim() : '',
    user_id: editor.source_type === 'newapi_admin' ? editor.user_id.trim() || '1' : '',
  }
}

function providerPayload(editor) {
  return {
    provider_name: editor.provider_name.trim() || editor.provider_id,
    source_type: editor.source_type,
    base_url: editor.source_type === 'newapi_admin' ? editor.base_url.trim() : '',
    user_id: editor.source_type === 'newapi_admin' ? editor.user_id.trim() || '1' : '',
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
  return sourceType === 'newapi_admin' ? 'New API' : 'DeepSeek'
}

function providerMetadata(group) {
  return group.items[0] || {}
}

function providerEndpointText(item) {
  return item.source_type === 'newapi_admin' ? item.base_url || '未配置接口' : '官方接口'
}

function isSecretConfigured(item) {
  return item.source_type === 'newapi_admin' ? item.has_access_token : item.has_api_key
}

function editorTitle(editor) {
  if (editor.mode === 'edit-provider') return `编辑${editor.provider_name}`
  if (editor.mode === 'edit-key') return `编辑${editor.display_name}`
  if (editor.mode === 'create-key') return `为${editor.provider_name}添加Key`
  return '新增供应商'
}
