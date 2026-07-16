import { useEffect, useMemo, useState } from 'react'

import { fetchLlmConfig, saveLlmConfig } from '../api.js'

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
    } catch (err) {
      setError(err.message)
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

  function openNewKey(group) {
    const template = group.items[0] || {}
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

  function openEdit(item) {
    const providerId = item.provider_id || item.source_id
    setEditor({
      ...emptyForm,
      mode: 'edit',
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

  async function handleSave(event) {
    event.preventDefault()
    const providerId = normalizeIdPart(editor.provider_id)
    const keyId = normalizeIdPart(editor.key_id)
    if (!providerId || !keyId) {
      setError('供应商ID和Key ID只能使用小写字母、数字、-、_。')
      return
    }

    const payload = {
      provider_id: providerId,
      provider_name: editor.provider_name.trim() || providerId,
      source_id: editor.original_source_id || `${providerId}-${keyId}`,
      display_name: editor.display_name.trim() || keyId,
      source_type: editor.source_type,
      base_url: editor.source_type === 'newapi_admin' ? editor.base_url.trim() : '',
      api_key: editor.source_type === 'deepseek_balance' ? editor.api_key.trim() : '',
      access_token: editor.source_type === 'newapi_admin' ? editor.access_token.trim() : '',
      user_id: editor.source_type === 'newapi_admin' ? editor.user_id.trim() || '1' : '',
    }

    setSaving(true)
    try {
      await saveLlmConfig(payload)
      await load()
      setEditor(null)
      setStatus(`已保存${payload.display_name}`)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const sourceIdPreview = editor
    ? editor.original_source_id || `${normalizeIdPart(editor.provider_id) || 'provider'}-${normalizeIdPart(editor.key_id) || 'key'}`
    : ''

  return (
    <section className="llm-settings-panel">
      <header className="llm-settings-header">
        <div>
          <h2>LLM供应商</h2>
          <span>{configs.length}个API Key</span>
        </div>
        <button className="glow-button" type="button" onClick={openNewProvider}>新增供应商</button>
      </header>

      {error && <div className="settings-inline-message danger">配置请求失败：{error}</div>}
      {status && <div className="settings-inline-message">{status}</div>}

      {editor && (
        <form className="llm-key-editor" onSubmit={handleSave}>
          <div className="llm-key-editor-title">
            <h3>{editor.mode === 'edit' ? `编辑${editor.display_name}` : editor.mode === 'create-key' ? `为${editor.provider_name}添加Key` : '新增供应商'}</h3>
            <button className="subtle-button" type="button" onClick={() => setEditor(null)}>取消</button>
          </div>
          <div className="llm-key-editor-grid">
            <label>
              <span>供应商ID</span>
              <input
                value={editor.provider_id}
                onChange={(event) => setEditor({ ...editor, provider_id: event.target.value })}
                placeholder="deepseek"
                readOnly={editor.mode !== 'create-provider'}
              />
            </label>
            <label>
              <span>供应商名称</span>
              <input value={editor.provider_name} onChange={(event) => setEditor({ ...editor, provider_name: event.target.value })} placeholder="DeepSeek" />
            </label>
            <label>
              <span>Key ID</span>
              <input
                value={editor.key_id}
                onChange={(event) => setEditor({ ...editor, key_id: event.target.value })}
                placeholder="main"
                readOnly={editor.mode === 'edit'}
              />
            </label>
            <label>
              <span>Key展示名</span>
              <input value={editor.display_name} onChange={(event) => setEditor({ ...editor, display_name: event.target.value })} placeholder="主Key" />
            </label>
            <label>
              <span>接入类型</span>
              <select value={editor.source_type} onChange={(event) => setEditor({ ...editor, source_type: event.target.value })}>
                <option value="deepseek_balance">DeepSeek官方余额</option>
                <option value="newapi_admin">New API管理统计</option>
              </select>
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
                  placeholder={editor.mode === 'edit' ? '留空则保留原密钥' : 'sk-...'}
                />
              </label>
            ) : (
              <>
                <label>
                  <span>Base URL</span>
                  <input value={editor.base_url} onChange={(event) => setEditor({ ...editor, base_url: event.target.value })} placeholder="https://your-new-api.example.com" />
                </label>
                <label>
                  <span>访问令牌</span>
                  <input
                    type="password"
                    value={editor.access_token}
                    onChange={(event) => setEditor({ ...editor, access_token: event.target.value })}
                    placeholder={editor.mode === 'edit' ? '留空则保留原密钥' : 'New API access token'}
                  />
                </label>
                <label>
                  <span>User ID</span>
                  <input value={editor.user_id} onChange={(event) => setEditor({ ...editor, user_id: event.target.value })} placeholder="1" />
                </label>
              </>
            )}
          </div>
          <footer className="llm-key-editor-actions">
            <span>密钥只写入服务器.env，页面不会回显。</span>
            <button className="glow-button" type="submit" disabled={saving}>{saving ? '保存中' : '保存API Key'}</button>
          </footer>
        </form>
      )}

      <div className="provider-settings-list">
        {groups.map((group) => (
          <article className="provider-settings-row" data-testid={`llm-provider-${group.provider_id}`} key={group.provider_id}>
            <header>
              <div className="provider-settings-identity">
                <h3>{group.provider_name}</h3>
                <code>{group.provider_id}</code>
                <span>{group.items.length}个Key</span>
              </div>
              <button className="subtle-button" type="button" onClick={() => openNewKey(group)}>添加Key</button>
            </header>
            <div className="provider-key-list">
              {group.items.map((item) => (
                <div className="provider-key-row" key={item.source_id}>
                  <div className="provider-key-name">
                    <strong>{item.display_name}</strong>
                    <code>{item.source_id}</code>
                  </div>
                  <span>{sourceTypeText(item.source_type)}</span>
                  <span>{item.base_url || '官方接口'}</span>
                  <span className={item.has_api_key || item.has_access_token ? 'secret-status configured' : 'secret-status'}>
                    {item.has_api_key || item.has_access_token ? '密钥已配置' : '密钥未配置'}
                  </span>
                  <button className="subtle-button" type="button" aria-label={`编辑 ${item.display_name}`} onClick={() => openEdit(item)}>编辑</button>
                </div>
              ))}
            </div>
          </article>
        ))}
        {!loading && groups.length === 0 && <div className="settings-empty">尚未配置LLM供应商。</div>}
        {loading && <div className="settings-empty">正在读取LLM配置</div>}
      </div>
    </section>
  )
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
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64)
}

function keyIdFromSource(sourceId, providerId) {
  const prefix = `${providerId}-`
  return sourceId.startsWith(prefix) ? sourceId.slice(prefix.length) : 'main'
}

function sourceTypeText(sourceType) {
  return sourceType === 'newapi_admin' ? 'New API' : 'DeepSeek'
}
