import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'
import '../styles/Dashboard.css'

export default function Dashboard() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    (async () => {
      const res = await api('/api/admin/dashboard/stats')
      if (res.ok) setStats(await res.json())
    })()
  }, [])

  if (!stats) return <div className="dash-loading">Loading dashboard...</div>

  const statItems = [
    { label: 'Groups', value: stats.total_groups },
    { label: 'Users', value: stats.total_users },
    { label: 'Question Sets', value: stats.total_question_sets },
    { label: 'Public Sets', value: stats.public_sets },
    { label: 'Private Sets', value: stats.private_sets },
    { label: 'Active Sessions Today', value: stats.active_sessions_today }
  ]

  return (
    <div className="dashboard-shell">
      <div className="dash-hero">
        <div>
          <p className="eyebrow">Operational Overview</p>
          <h1>Admin Control Center</h1>
          <p className="subhead">Quick stats, health, and latest audit signals.</p>
        </div>
        <div className="hero-chip">Live · {new Date().toLocaleDateString()}</div>
      </div>

      <div className="stats-grid">
        {statItems.map(item => (
          <div key={item.label} className="stat-card">
            <p className="stat-label">{item.label}</p>
            <p className="stat-value">{item.value}</p>
          </div>
        ))}
      </div>

      <div className="panels">
        <div className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Signals</p>
              <h3>Recent Audit Logs</h3>
            </div>
          </div>
          {(!stats.recent_audit_logs || stats.recent_audit_logs.length === 0) ? (
            <div className="empty">No audit entries yet.</div>
          ) : (
            <ul className="audit-list">
              {stats.recent_audit_logs.map(l => (
                <li key={l.id}>
                  <div className="audit-row">
                    <div>
                      <div className="audit-action">{l.action}</div>
                      <div className="audit-meta">{l.timestamp} · IP {l.ip_address || 'N/A'}</div>
                    </div>
                    <span className="pill">{l.target_type || 'N/A'}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel secondary">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Snapshot</p>
              <h3>System Notes</h3>
            </div>
          </div>
          <ul className="bullets">
            <li>Monitor active sessions to detect spikes.</li>
            <li>Review audit logs for unusual actions.</li>
            <li>Keep Default question set intact for new groups.</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
