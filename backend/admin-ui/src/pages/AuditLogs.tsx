import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import '../styles/Management.css'

export default function AuditLogs() {
  const { accessToken } = useAuth()
  const [logs, setLogs] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const pageSize = 50

  useEffect(() => {
    if (!accessToken) return

    const fetchLogs = async () => {
      try {
        const data = await api.auditLogs(accessToken, pageSize, page * pageSize)
        setLogs(data.logs)
        setTotal(data.total)
        setError('')
      } catch (err: any) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchLogs()
  }, [accessToken, page])

  if (error) return <div className="error">Error: {error}</div>

  return (
    <div className="management">
      <h1>Audit Logs</h1>

      {loading ? (
        <div className="loading-text">Loading audit logs...</div>
      ) : (
        <>
          <table className="logs-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Admin ID</th>
                <th>Action</th>
                <th>Target</th>
                <th>Timestamp</th>
                <th>IP Address</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id}>
                  <td>{log.id}</td>
                  <td>{log.admin_id}</td>
                  <td>{log.action}</td>
                  <td>{log.target_type}</td>
                  <td>{new Date(log.timestamp).toLocaleString()}</td>
                  <td>{log.ip_address || 'N/A'}</td>
                  <td>{log.reason || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="pagination">
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>
              ← Previous
            </button>
            <span>Page {page + 1} of {Math.ceil(total / pageSize)}</span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={(page + 1) * pageSize >= total}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  )
}
