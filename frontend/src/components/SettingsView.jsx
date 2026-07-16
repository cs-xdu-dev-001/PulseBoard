import { useEffect, useState } from 'react'
import { fetchSettings, saveSettings } from '../api.js'
import { LlmProviderSettings } from './LlmProviderSettings.jsx'

const sections = [
  {
    title: '基础运行',
    fields: [
      ['PULSEBOARD_DATABASE_URL', 'Database URL'],
      ['PULSEBOARD_RETENTION_DAYS', '数据保留天数'],
      ['PULSEBOARD_LAB_TIMEZONE', '实验室时区'],
    ],
  },
  {
    title: '采集频率',
    fields: [
      ['PULSEBOARD_COLLECTION_INTERVAL_SECONDS', 'GPU采集间隔（秒）'],
      ['PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS', 'VPS采集间隔（秒）'],
      ['PULSEBOARD_LLM_USAGE_INTERVAL_SECONDS', 'LLM采集间隔（秒）'],
    ],
  },
  {
    title: 'GPU来源',
    fields: [['PULSEBOARD_SOURCE_URL', '实验室GPU API']],
  },
  {
    title: 'VPS与流量',
    fields: [
      ['PULSEBOARD_NODE_EXPORTERS', 'node_exporter 节点'],
      ['PULSEBOARD_TRAFFIC_QUOTA_NODE', '流量配额节点'],
      ['PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB', '流量总额（GB）'],
      ['PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB', '周期初始已用（GB）'],
      ['PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY', '每月重置日'],
    ],
  },
]

export function SettingsView() {
  const [values, setValues] = useState({})
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  async function load() {
    try {
      const payload = await fetchSettings()
      setValues(payload.values || {})
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
      await saveSettings({ values, secrets: {} })
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
      <LlmProviderSettings />
      <form onSubmit={handleSubmit}>
        <section className="settings-header">
          <h2>运行参数</h2>
          <button className="glow-button" type="submit">保存运行参数</button>
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

        </div>
      </form>
      {status && <section className="notice">{status}</section>}
    </section>
  )
}
