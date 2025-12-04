import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Plus, Edit, Trash2, Copy } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

export default function GroupManagement({ adminToken }) {
  const navigate = useNavigate()
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/admin/groups`, {
        headers: { 'Authorization': `Bearer ${adminToken}` }
      })
      setGroups(response.data)
    } catch (error) {
      console.error('Error loading groups:', error)
    } finally {
      setLoading(false)
    }
  }

  const copyInviteCode = (code) => {
    navigator.clipboard.writeText(code)
    alert('Invite code copied!')
  }

  if (loading) return <div>Loading...</div>

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Groups</h1>
        <button
          onClick={() => navigate('/groups/create')}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
        >
          <Plus size={20} />
          Create Group
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {groups.map((group) => (
          <div key={group.id} className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">{group.name}</h2>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Invite Code</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">
                    {group.invite_code}
                  </span>
                  <button
                    onClick={() => copyInviteCode(group.invite_code)}
                    className="p-1 hover:bg-gray-200 rounded"
                  >
                    <Copy size={16} />
                  </button>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Members</span>
                <span className="font-medium">{group.member_count}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Created</span>
                <span className="font-medium">
                  {new Date(group.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => navigate(`/groups/${group.group_id}/question`)}
                className="flex-1 px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
              >
                Create Question
              </button>
              <button
                onClick={() => navigate(`/groups/${group.group_id}/analytics`)}
                className="flex-1 px-3 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition"
              >
                Analytics
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
