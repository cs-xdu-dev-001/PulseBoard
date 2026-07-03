const API_BASE = import.meta.env.VITE_API_BASE || ''

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export function fetchCurrentDashboard() {
  return getJson('/api/dashboard/current')
}

export function fetchGpuHistory(range) {
  return getJson(`/api/history/gpus?range=${range}`)
}

export function fetchMachineHistory(range) {
  return getJson(`/api/history/machines?range=${range}`)
}

export function fetchVpsHistory(range) {
  return getJson(`/api/history/vps?range=${range}`)
}

export function fetchLlmSources() {
  return getJson('/api/llm/usage/sources')
}

export function fetchLlmConfig() {
  return getJson('/api/llm/usage/config')
}

export async function saveLlmConfig(payload) {
  const response = await fetch(`${API_BASE}/api/llm/usage/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export function fetchLlmSummary(range, source = '') {
  const params = new URLSearchParams({ range })
  if (source) params.set('source', source)
  return getJson(`/api/llm/usage/summary?${params}`)
}

export function fetchLlmSeries(range, source = '') {
  const params = new URLSearchParams({ range })
  if (source) params.set('source', source)
  return getJson(`/api/llm/usage/series?${params}`)
}

export function fetchLlmModels(range, source = '') {
  const params = new URLSearchParams({ range })
  if (source) params.set('source', source)
  return getJson(`/api/llm/usage/models?${params}`)
}

export async function refreshLlmUsage() {
  const response = await fetch(`${API_BASE}/api/llm/usage/refresh`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export function fetchSettings() {
  return getJson('/api/settings')
}

export async function saveSettings(payload) {
  const response = await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}
