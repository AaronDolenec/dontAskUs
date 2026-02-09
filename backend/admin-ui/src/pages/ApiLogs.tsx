import { useState, useEffect } from 'react'
import { getLogs, clearLogs, getLogsSize, ApiLogEntry } from '../api/apiLogger'
import '../styles/Management.css'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}

function statusColor(status: number | null): string {
  if (status === null) return '#ef4444'
  if (status >= 200 && status < 300) return '#22c55e'
  if (status >= 400 && status < 500) return '#f59e0b'
  if (status >= 500) return '#ef4444'
  return 'inherit'
}

export default function ApiLogs() {
  const [logs, setLogs] = useState<ApiLogEntry[]>([])
  const [size, setSize] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [filter, setFilter] = useState('')

  function refresh() {
    setLogs(getLogs().reverse()) // newest first
    setSize(getLogsSize())
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 3000) // auto-refresh every 3s
    return () => clearInterval(interval)
  }, [])

  function handleClear() {
    if (!confirm('Clear all API logs?')) return
    clearLogs()
    refresh()
  }

  const filtered = filter
    ? logs.filter(l =>
        l.url.toLowerCase().includes(filter.toLowerCase()) ||
        l.method.toLowerCase().includes(filter.toLowerCase()) ||
        String(l.status).includes(filter)
      )
    : logs

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 8, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>API Logs ({filtered.length})</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {formatBytes(size)} / 10 MB
          </span>
          <input type="text" placeholder="Filter by URL, method, status..." value={filter} onChange={e => setFilter(e.target.value)} style={{ padding: 6, width: 220 }} />
          <button onClick={refresh} style={{ padding: '6px 12px' }}>Refresh</button>
          <button onClick={handleClear} style={{ padding: '6px 12px', color: 'red' }}>Clear</button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="management-table" style={{ fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>Time</th>
              <th style={{ width: 70 }}>Method</th>
              <th>URL</th>
              <th style={{ width: 70 }}>Status</th>
              <th style={{ width: 80 }}>Duration</th>
              <th style={{ width: 50 }}></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(l => (
              <>
                <tr key={l.id} style={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === l.id ? null : l.id)}>
                  <td style={{ fontSize: 11, whiteSpace: 'nowrap' }}>{new Date(l.timestamp).toLocaleString()}</td>
                  <td>
                    <span style={{ fontWeight: 600, color: l.method === 'GET' ? '#60a5fa' : l.method === 'POST' ? '#22c55e' : l.method === 'DELETE' ? '#ef4444' : '#f59e0b' }}>
                      {l.method}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, wordBreak: 'break-all' }}>{l.url}</td>
                  <td style={{ fontWeight: 600, color: statusColor(l.status) }}>
                    {l.status ?? 'ERR'}
                  </td>
                  <td>{l.durationMs} ms</td>
                  <td style={{ textAlign: 'center' }}>{expanded === l.id ? '▼' : '▶'}</td>
                </tr>
                {expanded === l.id && (
                  <tr key={l.id + '-detail'}>
                    <td colSpan={6} style={{ padding: '8px 16px', backgroundColor: 'var(--bg-primary)' }}>
                      {l.error && (
                        <div style={{ marginBottom: 8 }}>
                          <strong style={{ color: '#ef4444' }}>Error: </strong>{l.error}
                        </div>
                      )}
                      {l.requestBody && (
                        <div style={{ marginBottom: 8 }}>
                          <strong>Request Body:</strong>
                          <pre style={{ margin: '4px 0', padding: 8, backgroundColor: 'var(--bg-secondary, #1e1e1e)', borderRadius: 4, overflow: 'auto', maxHeight: 200, fontSize: 11 }}>
                            {typeof l.requestBody === 'string' ? l.requestBody : JSON.stringify(l.requestBody, null, 2)}
                          </pre>
                        </div>
                      )}
                      <div>
                        <strong>Response Body:</strong>
                        <pre style={{ margin: '4px 0', padding: 8, backgroundColor: 'var(--bg-secondary, #1e1e1e)', borderRadius: 4, overflow: 'auto', maxHeight: 300, fontSize: 11 }}>
                          {l.responseBody === undefined ? '(empty)' : typeof l.responseBody === 'string' ? l.responseBody : JSON.stringify(l.responseBody, null, 2)}
                        </pre>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-secondary)' }}>
            No API logs yet. Navigate around the admin panel to generate logs.
          </div>
        )}
      </div>
    </div>
  )
}
