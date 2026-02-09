import { useEffect, useState } from 'react'
import { useApi } from '../api/client'
import '../styles/Management.css'

interface AccountGroupMembership {
  user_id: number
  group_id: number
  group_name?: string
  display_name: string
}

interface AccountRow {
  id: number
  account_id: string
  email: string
  display_name: string
  is_active: boolean
  created_at: string
  last_login?: string
  group_count: number
  groups: AccountGroupMembership[]
}

interface GroupRow {
  id: number
  name: string
}

export default function Users() {
  const { request } = useApi()
  const [accounts, setAccounts] = useState<AccountRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [groups, setGroups] = useState<GroupRow[]>([])
  const [showNewForm, setShowNewForm] = useState(false)
  const [newUserName, setNewUserName] = useState('')
  const [newUserGroupId, setNewUserGroupId] = useState('')
  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserPassword, setNewUserPassword] = useState('')
  const [search, setSearch] = useState('')

  async function load() {
    setLoading(true)
    try {
      const searchParam = search ? `&search=${encodeURIComponent(search)}` : ''
      const res = await request(`/api/admin/accounts?limit=50&offset=0${searchParam}`)
      if (res.ok) {
        const data = await res.json()
        setAccounts(data.accounts)
        setTotal(data.total)
      }
    } catch (err) {
      console.error('Failed to load accounts:', err)
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

  useEffect(() => { loadGroups() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const t = setTimeout(() => load(), 300)
    return () => clearTimeout(t)
  }, [search]) // eslint-disable-line react-hooks/exhaustive-deps

  async function deleteAccount(a: AccountRow) {
    if (!confirm(`Delete account "${a.email}"?\n\nThis will also remove all group memberships and answers. Cannot be undone.`)) return
    try {
      const res = await request(`/api/admin/accounts/${a.id}`, { method: 'DELETE' })
      if (res.ok) await load()
      else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to delete account'))
      }
    } catch (err: any) { alert('Error: ' + err.message) }
  }

  async function resetPassword(a: AccountRow) {
    if (a.groups.length === 0) return alert('Cannot reset password — this account has no group membership yet (endpoint requires a user ID).')
    const newPassword = prompt(`Enter new password for ${a.email}:\n\nRequirements: min 8 chars, uppercase, lowercase, digit`)
    if (!newPassword) return
    if (newPassword.length < 8) return alert('Password must be at least 8 characters')
    const reason = prompt('Reason for password reset:')
    if (!reason) return
    try {
      const res = await request(`/api/admin/users/${a.groups[0].user_id}/reset-password`, {
        method: 'POST',
        body: { new_password: newPassword, reason },
      })
      if (res.ok) alert(`Password reset successfully for ${a.email}`)
      else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to reset password'))
      }
    } catch (err: any) { alert('Error: ' + err.message) }
  }

  async function createUser() {
    if (!newUserName.trim()) return alert('Please enter a display name')
    if (!newUserEmail.trim()) return alert('Please enter an email')
    if (!newUserPassword || newUserPassword.length < 8) return alert('Password must be at least 8 characters')
    try {
      const body: any = { email: newUserEmail.trim(), password: newUserPassword, display_name: newUserName.trim() }
      if (newUserGroupId) body.group_id = parseInt(newUserGroupId)
      const res = await request('/api/admin/accounts', { method: 'POST', body })
      if (res.ok) {
        const data = await res.json()
        alert(data.group_membership
          ? `Account created and added to group "${data.group_membership.group_name}"`
          : 'Account created (no group assigned)')
        setNewUserName(''); setNewUserEmail(''); setNewUserPassword(''); setNewUserGroupId('')
        setShowNewForm(false)
        await load()
      } else {
        const errData = await res.json()
        alert('Error: ' + (errData.detail || 'Failed to create user'))
      }
    } catch (err: any) { alert('Error: ' + err.message) }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading users...</div>

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 8, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>Users ({total})</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="text" placeholder="Search email or name..." value={search} onChange={e => setSearch(e.target.value)} style={{ padding: 6, width: 200 }} />
          <button onClick={() => setShowNewForm(!showNewForm)} style={{ padding: '8px 16px' }}>
            {showNewForm ? 'Cancel' : 'New User'}
          </button>
        </div>
      </div>

      {showNewForm && (
        <div style={{ marginBottom: 16, padding: 12, border: '1px solid var(--border-color)', borderRadius: 4, backgroundColor: 'var(--bg-primary)' }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input type="text" placeholder="Display name *" value={newUserName} onChange={e => setNewUserName(e.target.value)} style={{ padding: 6 }} />
            <input type="email" placeholder="Email *" value={newUserEmail} onChange={e => setNewUserEmail(e.target.value)} style={{ padding: 6 }} />
            <input type="password" placeholder="Password * (min 8)" value={newUserPassword} onChange={e => setNewUserPassword(e.target.value)} style={{ padding: 6 }} />
            <select value={newUserGroupId} onChange={e => setNewUserGroupId(e.target.value)} style={{ padding: 6 }}>
              <option value="">No group (account only)</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
            <button onClick={createUser} style={{ padding: '6px 12px' }}>Create</button>
          </div>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="management-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Email</th>
              <th>Display Name</th>
              <th>Groups</th>
              <th>Active</th>
              <th>Last Login</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map(a => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td style={{ fontSize: '12px' }}>{a.email}</td>
                <td>{a.display_name}</td>
                <td>
                  {a.group_count === 0
                    ? <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>No groups</span>
                    : <span title={a.groups.map(g => g.group_name || `Group ${g.group_id}`).join(', ')}>{a.group_count} group{a.group_count !== 1 ? 's' : ''}</span>
                  }
                </td>
                <td style={{ color: a.is_active ? 'green' : 'red' }}>{a.is_active ? 'Yes' : 'No'}</td>
                <td>{a.last_login ? new Date(a.last_login).toLocaleDateString() : 'Never'}</td>
                <td>{new Date(a.created_at).toLocaleDateString()}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => resetPassword(a)} style={{ marginRight: 4, padding: '4px 8px' }}>Reset PW</button>
                  <button onClick={() => deleteAccount(a)} style={{ color: 'red', padding: '4px 8px' }}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
