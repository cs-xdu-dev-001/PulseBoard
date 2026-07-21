const API_BASE = import.meta.env.VITE_API_BASE || ''

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }
  return response.json()
}

async function readErrorMessage(response) {
  try {
    const payload = await response.clone().json()
    if (typeof payload.detail === 'string') return payload.detail
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail.map((item) => item?.msg || item?.message).filter(Boolean)
      if (messages.length) return messages.join('；')
    }
    if (payload.detail) return JSON.stringify(payload.detail)
  } catch {
    // Non-JSON error bodies fall back to the HTTP status below.
  }
  return `HTTP ${response.status}`
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
    throw new Error(await readErrorMessage(response))
  }
  return response.json()
}

export async function deleteLlmConfig(sourceId) {
  const response = await fetch(`${API_BASE}/api/llm/usage/config/${encodeURIComponent(sourceId)}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }
  return response.json()
}

export async function testLlmConfig(sourceId) {
  const response = await fetch(`${API_BASE}/api/llm/usage/config/${encodeURIComponent(sourceId)}/test`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }
  return response.json()
}

export async function updateLlmProvider(providerId, payload) {
  const response = await fetch(`${API_BASE}/api/llm/usage/providers/${encodeURIComponent(providerId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }
  return response.json()
}

export async function deleteLlmProvider(providerId) {
  const response = await fetch(`${API_BASE}/api/llm/usage/providers/${encodeURIComponent(providerId)}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
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

export function fetchLlmActivity(year, source = '') {
  const params = new URLSearchParams({ year: String(year) })
  if (source) params.set('source', source)
  return getJson(`/api/llm/usage/activity?${params}`)
}

export async function refreshLlmUsage() {
  const response = await fetch(`${API_BASE}/api/llm/usage/refresh`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
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
    throw new Error(await readErrorMessage(response))
  }
  return response.json()
}
