import { useEffect, useState } from 'react'
import { useApi } from '../api/client'
import '../styles/Management.css'

interface UserRow {
  id: number
  user_id: string
  display_name: string
  group_id: number
  group_name?: string
  account_email?: string
  color_avatar?: string
  answer_streak: number
  longest_answer_streak: number
  last_answer_date?: string
  is_suspended: boolean
  last_known_ip?: string
  created_at: string
}

interface GroupRow {
  id: number
  name: string
}

export default function Users() {
  const { request } = useApi()
  const [users, setUsers] = useState<UserRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [groups, setGroups] = useState<GroupRow[]>([])
  const [showNewForm, setShowNewForm] = useState(false)
  const [newUserName, setNewUserName] = useState('')
  const [newUserGroupId, setNewUserGroupId] = useState('')
  const [newUserEmail, setNewUserEmail] = useState('')

  async function load() {
    setLoading(true)
    try {
      const res = await request('/api/admin/users?limit=50&offset=0')
      if (res.ok) {
        const data = await res.json()
        setUsers(data.users)
        setTotal(data.total)
      }
    } catch (err) {
      console.error('Failed to load users:', err)
    }
    setLoading(false)
  }

  async function loadGroups() {
    try {
      const res = await request('/api/admin/groups?limit=100&offset=0')
      if (res.ok) {
        const data = await res.json()
        setGroups(data.groups)
      }
    } catch (err) {
      console.error('Failed to load groups:', err)
    }
  }

  useEffect(() => {
    load()
    loadGroups()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleSuspend(u: UserRow) {
    try {
      const res = await request(`/api/admin/users/${u.id}/suspension`, {
        method: 'PUT',
        body: { is_suspended: !u.is_suspended, suspension_reason: u.is_suspended ? null : 'By admin' },
      })
      if (res.ok) load()
    } catch (err) {
      console.error('Error toggling suspension:', err)
    }
  }

  async function resetPassword(u: UserRow) {
    const newPassword = prompt(
      `Enter new password for ${u.display_name} (${u.account_email || 'no account'}):\n\nRequirements: min 8 chars, uppercase, lowercase, digit`,
    )
    if (!newPassword) return
    if (newPassword.length < 8) {
      alert('Password must be at least 8 characters')
      return
    }
    const reason = prompt('Reason for password reset:')
    if (!reason) return
    try {
      const res = await request(`/api/admin/users/${u.id}/reset-password`, {
        method: 'POST',
        body: { new_password: newPassword, reason },
      })
      if (res.ok) {
        const data = await res.json()
        alert(`Password reset successfully for ${data.account_email}`)
      } else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to reset password'))
      }
    } catch (err: any) {
      alert('Error: ' + err.message)
    }
  }

  async function deleteUser(u: UserRow) {
    if (!confirm(`Delete user "${u.display_name}"? All their answers will be deleted too. This cannot be undone.`)) return
    try {
      const res = await request(`/api/admin/users/${u.id}`, { method: 'DELETE' })
      if (res.ok) {
        await load()
      } else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to delete user'))
      }
    } catch (err: any) {
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
      const body: any = { display_name: newUserName, group_id: parseInt(newUserGroupId) }
      if (newUserEmail.trim()) body.account_email = newUserEmail.trim()
      const res = await request('/api/admin/users', { method: 'POST', body })
      if (res.ok) {
        const data = await res.json()
        alert(`User created!${data.account_email ? ` Linked to account: ${data.account_email}` : ' No account linked.'}`)
        setNewUserName('')
        setNewUserGroupId('')
        setNewUserEmail('')
        setShowNewForm(false)
        await load()
      } else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to create user'))
      }
    } catch (err: any) {
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
        <div style={{ marginBottom: 16, padding: 12, border: '1px solid var(--border-color)', borderRadius: 4, backgroundColor: 'var(--bg-primary)' }}>
          <input type="text" placeholder="Display name" value={newUserName} onChange={e => setNewUserName(e.target.value)} style={{ marginRight: 8, padding: 6 }} />
          <input type="email" placeholder="Account email (optional)" value={newUserEmail} onChange={e => setNewUserEmail(e.target.value)} style={{ marginRight: 8, padding: 6 }} />
          <select value={newUserGroupId} onChange={e => setNewUserGroupId(e.target.value)} style={{ marginRight: 8, padding: 6 }}>
            <option value="">Select group...</option>
            {groups.map(g => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
          <button onClick={createUser} style={{ padding: '6px 12px' }}>Create</button>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="management-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>User ID</th>
              <th>Display Name</th>
              <th>Group</th>
              <th>Account Email</th>
              <th>Avatar</th>
              <th>Streak</th>
              <th>Best Streak</th>
              <th>Last Answer</th>
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
                <td style={{ fontSize: '11px' }}>{u.account_email || <span style={{ color: 'var(--text-secondary)' }}>No account</span>}</td>
                <td>
                  <div style={{ width: 20, height: 20, backgroundColor: u.color_avatar, borderRadius: '50%', margin: 'auto' }} />
                </td>
                <td>{u.answer_streak}</td>
                <td>{u.longest_answer_streak}</td>
                <td>{u.last_answer_date ? new Date(u.last_answer_date).toLocaleDateString() : 'Never'}</td>
                <td style={{ color: u.is_suspended ? 'red' : 'green' }}>{u.is_suspended ? 'Yes' : 'No'}</td>
                <td>{u.last_known_ip || 'N/A'}</td>
                <td>{new Date(u.created_at).toLocaleDateString()}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => toggleSuspend(u)} style={{ marginRight: 4, padding: '4px 8px' }}>
                    {u.is_suspended ? 'Unsuspend' : 'Suspend'}
                  </button>
                  {u.account_email && (
                    <button onClick={() => resetPassword(u)} style={{ marginRight: 4, padding: '4px 8px' }}>Reset PW</button>
                  )}
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
