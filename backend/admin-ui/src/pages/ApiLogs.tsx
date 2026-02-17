import { useState, useEffect } from 'react'
import { useApi } from '../api/client'
import '../styles/Management.css'

interface ApiLogEntry {
  id: number
  timestamp: string
  method: string
  path: string
  query_string: string | null
  status_code: number | null
  duration_ms: number | null
  client_ip: string | null
  user_agent: string | null
  account_id: number | null
  request_body_preview: string | null
  response_size: number | null
}

function statusColor(status: number | null): string {
  if (status === null) return '#ef4444'
  if (status >= 200 && status < 300) return '#22c55e'
  if (status >= 400 && status < 500) return '#f59e0b'
  if (status >= 500) return '#ef4444'
  return 'inherit'
}

function methodColor(method: string): string {
  switch (method) {
    case 'GET': return '#60a5fa'
    case 'POST': return '#22c55e'
    case 'PUT': return '#f59e0b'
    case 'DELETE': return '#ef4444'
    default: return 'inherit'
  }
}

export default function ApiLogs() {
  const { request } = useApi()
  const [logs, setLogs] = useState<ApiLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const [methodFilter, setMethodFilter] = useState('')
  const [limit] = useState(100)
  const [offset, setOffset] = useState(0)

  async function load(newOffset = offset) {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(limit))
      params.set('offset', String(newOffset))
      if (filter) params.set('path_filter', filter)
      if (methodFilter) params.set('method', methodFilter)

      const res = await request(`/api/admin/api-logs?${params.toString()}`)
      if (res.ok) {
        const data = await res.json()
        setLogs(data.logs)
        setTotal(data.total)
      }
    } catch (err) {
      console.error('Failed to load API logs:', err)
    }
    setLoading(false)
  }

  useEffect(() => {
    load(0)
    setOffset(0)
  }, [filter, methodFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const interval = setInterval(() => load(), 5000)
    return () => clearInterval(interval)
  }, [offset, filter, methodFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleClear() {
    if (!confirm('Clear ALL server-side API logs? This cannot be undone.')) return
    try {
      const res = await request('/api/admin/api-logs', { method: 'DELETE' })
      if (res.ok) {
        setOffset(0)
        await load(0)
      }
    } catch (err) {
      console.error('Error clearing logs:', err)
    }
  }

  function nextPage() {
    const next = offset + limit
    setOffset(next)
    load(next)
  }

  function prevPage() {
    const prev = Math.max(0, offset - limit)
    setOffset(prev)
    load(prev)
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 8, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>API Logs ({total} total)</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={methodFilter} onChange={e => setMethodFilter(e.target.value)} style={{ padding: 6 }}>
            <option value="">All Methods</option>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
            <option value="DELETE">DELETE</option>
          </select>
          <input type="text" placeholder="Filter by path..." value={filter} onChange={e => setFilter(e.target.value)} style={{ padding: 6, width: 200 }} />
          <button onClick={() => load()} style={{ padding: '6px 12px' }}>Refresh</button>
          <button onClick={handleClear} style={{ padding: '6px 12px', color: 'red' }}>Clear All</button>
        </div>
      </div>

      {loading && logs.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center' }}>Loading...</div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table className="management-table" style={{ fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ width: 180 }}>Time</th>
                  <th style={{ width: 70 }}>Method</th>
                  <th>Path</th>
                  <th style={{ width: 70 }}>Status</th>
                  <th style={{ width: 80 }}>Duration</th>
                  <th style={{ width: 120 }}>Client IP</th>
                  <th style={{ width: 80 }}>Account</th>
                  <th style={{ width: 50 }}></th>
                </tr>
              </thead>
              <tbody>
                {logs.map(l => (
                  <>
                    <tr key={l.id} style={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === l.id ? null : l.id)}>
                      <td style={{ fontSize: 11, whiteSpace: 'nowrap' }}>{new Date(l.timestamp).toLocaleString()}</td>
                      <td>
                        <span style={{ fontWeight: 600, color: methodColor(l.method) }}>
                          {l.method}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, wordBreak: 'break-all' }}>
                        {l.path}{l.query_string ? `?${l.query_string}` : ''}
                      </td>
                      <td style={{ fontWeight: 600, color: statusColor(l.status_code) }}>
                        {l.status_code ?? 'ERR'}
                      </td>
                      <td>{l.duration_ms != null ? `${l.duration_ms} ms` : '-'}</td>
                      <td style={{ fontSize: 11 }}>{l.client_ip || '-'}</td>
                      <td style={{ fontSize: 11 }}>{l.account_id || '-'}</td>
                      <td style={{ textAlign: 'center' }}>{expanded === l.id ? '▼' : '▶'}</td>
                    </tr>
                    {expanded === l.id && (
                      <tr key={`${l.id}-detail`}>
                        <td colSpan={8} style={{ padding: '8px 16px', backgroundColor: 'var(--bg-primary)' }}>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
                            <div><strong>User Agent:</strong> <span style={{ fontSize: 11 }}>{l.user_agent || '-'}</span></div>
                            <div><strong>Response Size:</strong> {l.response_size ? `${l.response_size} bytes` : '-'}</div>
                          </div>
                          {l.request_body_preview && (
                            <div style={{ marginTop: 8 }}>
                              <strong>Request Body:</strong>
                              <pre style={{ margin: '4px 0', padding: 8, backgroundColor: 'var(--bg-secondary, #1e1e1e)', borderRadius: 4, overflow: 'auto', maxHeight: 200, fontSize: 11 }}>
                                {l.request_body_preview}
                              </pre>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            {logs.length === 0 && (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-secondary)' }}>
                No API logs found. Make some API requests to generate logs.
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={prevPage} disabled={offset === 0} style={{ padding: '6px 12px' }}>← Prev</button>
              <button onClick={nextPage} disabled={offset + limit >= total} style={{ padding: '6px 12px' }}>Next →</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
