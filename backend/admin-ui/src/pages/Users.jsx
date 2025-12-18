import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function Users() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [groups, setGroups] = useState([])
  const [showNewForm, setShowNewForm] = useState(false)
  const [newUserName, setNewUserName] = useState('')
  const [newUserGroupId, setNewUserGroupId] = useState('')

  async function load() {
    setLoading(true)
    const res = await api('/api/admin/users?limit=50&offset=0')
    if (res.ok) {
      const data = await res.json()
      setUsers(data.users)
      setTotal(data.total)
    }
    setLoading(false)
  }

  async function loadGroups() {
    const res = await api('/api/admin/groups?limit=100&offset=0')
    if (res.ok) {
      const data = await res.json()
      setGroups(data.groups)
    }
  }

  useEffect(() => { 
    load()
    loadGroups()
  }, [])

  async function toggleSuspend(u) {
    const res = await api(`/api/admin/users/${u.id}/suspension`, {
      method: 'PUT',
      body: JSON.stringify({ is_suspended: !u.is_suspended, suspension_reason: !u.is_suspended ? 'By admin' : null })
    })
    if (res.ok) load()
  }

  async function recoverToken(u) {
    const reason = prompt('Reason for token recovery:')
    if (!reason) return
    try {
      const res = await api(`/api/admin/users/${u.id}/recover-token`, {
        method: 'POST',
        body: JSON.stringify({ reason })
      })
      if (res.ok) {
        const data = await res.json()
        alert(`New session token for ${u.display_name}:\n\n${data.session_token}\n\nSave this token - it won't be shown again!`)
      } else {
        const errData = await res.json()
        console.error('Error recovering token:', errData)
        alert('Error: ' + (errData.detail || 'Failed to recover token'))
      }
    } catch (err) {
      console.error('Exception recovering token:', err)
      alert('Error: ' + err.message)
    }
  }

  async function deleteUser(u) {
    if (!confirm(`Delete user "${u.name}"? All their answers will be deleted too. This cannot be undone.`)) return
    try {
      const res = await api(`/api/admin/users/${u.id}`, { method: 'DELETE' })
      if (res.ok) {
        console.log('User deleted successfully')
        await load()
      } else {
        const errData = await res.json()
        console.error('Error deleting user:', errData)
        alert('Error: ' + (errData.detail || 'Failed to delete user'))
      }
    } catch (err) {
      console.error('Exception deleting user:', err)
      alert('Error: ' + err.message)
    }
  }

  async function createUser() {
    if (!newUserName.trim()) {
      alert('Please enter a display name')
      return
    }
    if (!newUserGroupId) {
      alert('Please select a group')
      return
    }
    try {
      const res = await api('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({ 
          display_name: newUserName,
          group_id: parseInt(newUserGroupId)
        })
      })
      if (res.ok) {
        const data = await res.json()
        console.log('Created user:', data)
        alert(`User created! Session token: ${data.session_token}\n\nSave this token - it won't be shown again.`)
        setNewUserName('')
        setNewUserGroupId('')
        setShowNewForm(false)
        await load()
      } else {
        const errData = await res.json()
        console.error('Error creating user:', errData)
        alert('Error: ' + (errData.detail || 'Failed to create user'))
      }
    } catch (err) {
      console.error('Exception creating user:', err)
      alert('Error: ' + err.message)
    }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading users...</div>

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>Users ({total})</h2>
        <button onClick={() => setShowNewForm(!showNewForm)} style={{ padding: '8px 16px' }}>
          {showNewForm ? 'Cancel' : 'New User'}
        </button>
      </div>

      {showNewForm && (
        <div style={{ marginBottom: 16, padding: 12, border: '1px solid #ccc', borderRadius: 4 }}>
          <input
            type="text"
            placeholder="Display name"
            value={newUserName}
            onChange={e => setNewUserName(e.target.value)}
            style={{ marginRight: 8, padding: 6 }}
          />
          <select
            value={newUserGroupId}
            onChange={e => setNewUserGroupId(e.target.value)}
            style={{ marginRight: 8, padding: 6 }}
          >
            <option value="">Select group...</option>
            {groups.map(g => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
          <button onClick={createUser} style={{ padding: '6px 12px' }}>Create</button>
        </div>
      )}
      <div style={{ overflowX: 'auto' }}>
        <table border="1" cellPadding="6" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>User ID</th>
              <th>Display Name</th>
              <th>Group</th>
              <th>Avatar</th>
              <th>Streak</th>
              <th>Best Streak</th>
              <th>Last Answer</th>
              <th>Token Expires</th>
              <th>Suspended</th>
              <th>Last IP</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td style={{ fontSize: '10px' }}>{u.user_id}</td>
                <td>{u.display_name}</td>
                <td>{u.group_name || `Group ${u.group_id}`}</td>
                <td>
                  <div style={{ 
                    width: 20, 
                    height: 20, 
                    backgroundColor: u.color_avatar, 
                    borderRadius: '50%',
                    margin: 'auto'
                  }}></div>
                </td>
                <td>{u.answer_streak}</td>
                <td>{u.longest_answer_streak}</td>
                <td>{u.last_answer_date ? new Date(u.last_answer_date).toLocaleDateString() : 'Never'}</td>
                <td>{u.session_token_expires_at ? new Date(u.session_token_expires_at).toLocaleDateString() : 'N/A'}</td>
                <td style={{ color: u.is_suspended ? 'red' : 'green' }}>
                  {u.is_suspended ? 'Yes' : 'No'}
                </td>
                <td>{u.last_known_ip || 'N/A'}</td>
                <td>{new Date(u.created_at).toLocaleDateString()}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => toggleSuspend(u)} style={{ marginRight: 4, padding: '4px 8px' }}>
                    {u.is_suspended ? 'Unsuspend' : 'Suspend'}
                  </button>
                  <button onClick={() => recoverToken(u)} style={{ marginRight: 4, padding: '4px 8px' }}>Token</button>
                  <button onClick={() => deleteUser(u)} style={{ color: 'red', padding: '4px 8px' }}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
