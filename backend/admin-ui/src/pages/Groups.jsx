import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'
import '../styles/Groups.css'

export default function Groups() {
  const [groups, setGroups] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showNewForm, setShowNewForm] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')

  async function load() {
    setLoading(true)
    const res = await api('/api/admin/groups?limit=50&offset=0')
    if (res.ok) {
      const data = await res.json()
      setGroups(data.groups)
      setTotal(data.total)
    }
    setLoading(false)
  }
  
  useEffect(() => { load() }, [])

  async function updateNotes(g) {
    const notes = prompt('Set instance admin notes', g.instance_admin_notes || '')
    if (notes === null) return
    const res = await api(`/api/admin/groups/${g.id}/notes`, {
      method: 'PUT',
      body: JSON.stringify({ notes })
    })
    if (res.ok) load()
  }

  async function deleteGroup(groupId) {
    if (!confirm('Delete this group and ALL its users and data? This cannot be undone.')) return
    try {
      const res = await api(`/api/admin/groups/${groupId}`, { method: 'DELETE' })
      if (res.ok) {
        console.log('Group deleted successfully')
        await load()
      } else {
        const errData = await res.json()
        console.error('Error deleting group:', errData)
        alert('Error: ' + (errData.detail || 'Failed to delete group'))
      }
    } catch (err) {
      console.error('Exception deleting group:', err)
      alert('Error: ' + err.message)
    }
  }

  async function createGroup() {
    if (!newGroupName.trim()) {
      alert('Please enter a group name')
      return
    }
    try {
      const res = await api('/api/admin/groups', {
        method: 'POST',
        body: JSON.stringify({ name: newGroupName })
      })
      if (res.ok) {
        const data = await res.json()
        console.log('Created group:', data)
        setNewGroupName('')
        setShowNewForm(false)
        await load()
      } else {
        const errData = await res.json()
        console.error('Error creating group:', errData)
        alert('Error: ' + (errData.detail || 'Failed to create group'))
      }
    } catch (err) {
      console.error('Exception creating group:', err)
      alert('Error: ' + err.message)
    }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading...</div>

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>Groups ({total})</h2>
        <button onClick={() => setShowNewForm(!showNewForm)} style={{ padding: '8px 16px' }}>
          {showNewForm ? 'Cancel' : 'New Group'}
        </button>
      </div>

      {showNewForm && (
        <div style={{ marginBottom: 16, padding: 12, border: '1px solid #ccc', borderRadius: 4 }}>
          <input
            type="text"
            placeholder="Group name"
            value={newGroupName}
            onChange={e => setNewGroupName(e.target.value)}
            style={{ marginRight: 8, padding: 6 }}
          />
          <button onClick={createGroup} style={{ padding: '6px 12px' }}>Create</button>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table border="1" cellPadding="6" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Group ID</th>
              <th>Name</th>
              <th>Invite Code</th>
              <th>Members</th>
              <th>Custom Sets</th>
              <th>Created</th>
              <th>Updated</th>
              <th>Notes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(g => (
              <tr key={g.id}>
                <td>{g.id}</td>
                <td style={{ fontSize: '10px' }}>{g.group_id}</td>
                <td><strong>{g.name}</strong></td>
                <td>
                  <code className="code-chip">{g.invite_code}</code>
                </td>
                <td>{g.member_count}</td>
                <td>{g.total_sets_created}</td>
                <td>{new Date(g.created_at).toLocaleDateString()}</td>
                <td>{new Date(g.updated_at).toLocaleDateString()}</td>
                <td style={{ maxWidth: 200, fontSize: '11px' }}>
                  {g.instance_admin_notes || <span className="group-notes-empty">No notes</span>}
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => updateNotes(g)} style={{ marginRight: 4, padding: '4px 8px' }}>
                    Notes
                  </button>
                  <button onClick={() => deleteGroup(g.id)} style={{ color: 'red', padding: '4px 8px' }}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
