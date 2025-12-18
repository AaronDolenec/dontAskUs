import { getAccessToken, getRefreshToken, setTokens, clearTokens } from './auth'

const BASE = '' // same origin

async function refreshIfNeeded(res) {
  if (res.status !== 401) return res
  // attempt refresh
  const rt = getRefreshToken()
  if (!rt) return res
  const r = await fetch(`${BASE}/api/admin/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: rt })
  })
  if (!r.ok) return res
  const data = await r.json()
  setTokens({ access: data.access_token, refresh: data.refresh_token })
  // retry original request
  const orig = res._cfg
  return fetch(orig.url, {
    ...orig,
    headers: { ...(orig.headers || {}), 'Authorization': `Bearer ${getAccessToken()}` }
  })
}

export async function api(url, options = {}) {
  const headers = { 
    'Content-Type': 'application/json', 
    'Cache-Control': 'no-cache',
    ...(options.headers || {}) 
  }
  const token = getAccessToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const cfg = { ...options, headers }
  cfg._cfg = { ...cfg, url: `${BASE}${url}` }
  const res = await fetch(`${BASE}${url}`, cfg)
  res._cfg = cfg._cfg
  if (res.status === 401) {
    const retried = await refreshIfNeeded(res)
    if (retried !== res) return retried
    clearTokens()
  }
  return res
}
