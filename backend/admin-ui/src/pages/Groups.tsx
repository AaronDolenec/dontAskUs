import { useEffect, useState } from 'react'
import { useApi } from '../api/client'
import '../styles/Groups.css'

interface GroupRow {
  id: number
  group_id: string
  name: string
  invite_code: string
  member_count: number
  total_sets_created: number
  created_at: string
  updated_at: string
  instance_admin_notes?: string
}

export default function Groups() {
  const { request } = useApi()
  const [groups, setGroups] = useState<GroupRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showNewForm, setShowNewForm] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')

  async function load() {
    setLoading(true)
    try {
      const res = await request('/api/admin/groups?limit=50&offset=0')
      if (res.ok) {
        const data = await res.json()
        setGroups(data.groups)
        setTotal(data.total)
      }
    } catch (err) {
      console.error('Failed to load groups:', err)
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function updateNotes(g: GroupRow) {
    const notes = prompt('Set instance admin notes', g.instance_admin_notes || '')
    if (notes === null) return
    try {
      const res = await request(`/api/admin/groups/${g.id}/notes`, {
        method: 'PUT',
        body: { notes },
      })
      if (res.ok) load()
    } catch (err) {
      console.error('Error updating notes:', err)
    }
  }

  async function deleteGroup(groupId: number) {
    if (!confirm('Delete this group and ALL its users and data? This cannot be undone.')) return
    try {
      const res = await request(`/api/admin/groups/${groupId}`, { method: 'DELETE' })
      if (res.ok) {
        await load()
      } else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to delete group'))
      }
    } catch (err: any) {
      alert('Error: ' + err.message)
    }
  }

  async function createGroup() {
    if (!newGroupName.trim()) {
      alert('Please enter a group name')
      return
    }
    try {
      const res = await request('/api/admin/groups', {
        method: 'POST',
        body: { name: newGroupName },
      })
      if (res.ok) {
        setNewGroupName('')
        setShowNewForm(false)
        await load()
      } else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to create group'))
      }
    } catch (err: any) {
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
        <div style={{ marginBottom: 16, padding: 12, border: '1px solid var(--border-color)', borderRadius: 4, backgroundColor: 'var(--bg-primary)' }}>
          <input type="text" placeholder="Group name" value={newGroupName} onChange={e => setNewGroupName(e.target.value)} style={{ marginRight: 8, padding: 6 }} />
          <button onClick={createGroup} style={{ padding: '6px 12px' }}>Create</button>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table border={1} cellPadding={6} style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
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
                <td><code className="code-chip">{g.invite_code}</code></td>
                <td>{g.member_count}</td>
                <td>{g.total_sets_created}</td>
                <td>{new Date(g.created_at).toLocaleDateString()}</td>
                <td>{new Date(g.updated_at).toLocaleDateString()}</td>
                <td style={{ maxWidth: 200, fontSize: '11px' }}>
                  {g.instance_admin_notes || <span className="group-notes-empty">No notes</span>}
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => updateNotes(g)} style={{ marginRight: 4, padding: '4px 8px' }}>Notes</button>
                  <button onClick={() => deleteGroup(g.id)} style={{ color: 'red', padding: '4px 8px' }}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
