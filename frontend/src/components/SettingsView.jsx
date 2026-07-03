import { useEffect, useState } from 'react'
import { fetchSettings, saveSettings } from '../api.js'

const sections = [
  {
    title: 'General',
    fields: [
      ['PULSEBOARD_DATABASE_URL', 'Database URL'],
      ['PULSEBOARD_COLLECTION_INTERVAL_SECONDS', 'GPU 采集间隔'],
      ['PULSEBOARD_RETENTION_DAYS', '数据保留天数'],
      ['PULSEBOARD_LAB_TIMEZONE', '实验室时区'],
    ],
  },
  {
    title: 'GPU',
    fields: [['PULSEBOARD_SOURCE_URL', '实验室 GPU API']],
  },
  {
    title: 'VPS',
    fields: [
      ['PULSEBOARD_NODE_EXPORTERS', 'node_exporter 节点'],
      ['PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS', 'VPS 采集间隔'],
      ['PULSEBOARD_TRAFFIC_QUOTA_NODE', '流量配额节点'],
      ['PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB', '流量总额 GB'],
      ['PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB', '周期初始已用 GB'],
      ['PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY', '每月重置日'],
    ],
  },
  {
    title: 'LLM',
    fields: [
      ['PULSEBOARD_LLM_USAGE_SOURCES', 'LLM 来源 ID'],
      ['PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS', 'LLM 采集间隔'],
    ],
  },
]

const secretFields = [
  ['PULSEBOARD_LLM_DEEPSEEK_API_KEY', 'DeepSeek API Key'],
  ['PULSEBOARD_LLM_ACADEMIC_ACCESS_TOKEN', 'Academic Gateway Access Token'],
]

export function SettingsView() {
  const [values, setValues] = useState({})
  const [secrets, setSecrets] = useState({})
  const [secretInputs, setSecretInputs] = useState({})
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  async function load() {
    try {
      const payload = await fetchSettings()
      setValues(payload.values || {})
      setSecrets(payload.secrets || {})
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    setStatus('保存中')
    try {
      await saveSettings({ values, secrets: secretInputs })
      setSecretInputs({})
      await load()
      setStatus('已保存，部分采集配置可能需要等待下一轮采集生效')
      setError('')
    } catch (err) {
      setError(err.message)
      setStatus('')
    }
  }

  return (
    <section className="settings-view">
      {error && <section className="notice danger">Settings 请求失败：{error}</section>}
      <form onSubmit={handleSubmit}>
        <section className="settings-header">
          <div>
            <p className="eyebrow">Settings</p>
            <h2>运行配置</h2>
          </div>
          <button className="glow-button" type="submit">保存配置</button>
        </section>

        <div className="settings-grid">
          {sections.map((section) => (
            <section className="settings-card" key={section.title}>
              <div className="table-title">{section.title}</div>
              <div className="settings-fields">
                {section.fields.map(([key, label]) => (
                  <label key={key}>
                    <span>{label}</span>
                    <input value={values[key] || ''} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />
                  </label>
                ))}
              </div>
            </section>
          ))}

          <section className="settings-card">
            <div className="table-title">Secrets</div>
            <div className="settings-fields">
              {secretFields.map(([key, label]) => (
                <label key={key}>
                  <span>{label} · {secrets[key]?.configured ? '已配置' : '未配置'}</span>
                  <input
                    type="password"
                    value={secretInputs[key] || ''}
                    onChange={(event) => setSecretInputs({ ...secretInputs, [key]: event.target.value })}
                    placeholder="留空则不修改"
                  />
                </label>
              ))}
            </div>
          </section>
        </div>
      </form>
      {status && <section className="notice">{status}</section>}
    </section>
  )
}
