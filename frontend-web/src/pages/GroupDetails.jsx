import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Users, Plus, Edit, Trash2, Copy } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

export default function GroupDetails({ adminToken }) {
  const { groupId } = useParams()
  const navigate = useNavigate()
  const [group, setGroup] = useState(null)
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadGroup()
    loadMembers()
  }, [groupId])

  const loadGroup = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/groups/${groupId}/info`, {
        headers: { 'Authorization': `Bearer ${adminToken}` }
      })
      setGroup(response.data)
    } catch (error) {
      console.error('Error loading group:', error)
    }
  }

  const loadMembers = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/groups/${groupId}/members`, {
        headers: { 'Authorization': `Bearer ${adminToken}` }
      })
      setMembers(response.data)
    } catch (error) {
      console.error('Error loading members:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div>Loading...</div>
  if (!group) return <div>Group not found</div>

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">{group.name}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => navigate(`/groups/${groupId}/question`)}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
          >
            Create Question
          </button>
          <button
            onClick={() => navigate(`/groups/${groupId}/analytics`)}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition"
          >
            Analytics
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Group Info</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Invite Code</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">
                  {group.invite_code}
                </span>
                <button
                  onClick={() => navigator.clipboard.writeText(group.invite_code)}
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
        </div>

        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Members</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {members.map((member) => (
              <div key={member.user_id} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                <div className="flex items-center gap-2">
                  <div
                    className="w-8 h-8 rounded-full"
                    style={{ backgroundColor: member.color_avatar }}
                  >
                    <span className="text-white text-xs font-bold">
                      {member.display_name[0].toUpperCase()}
                    </span>
                  </div>
                  <span className="font-medium">{member.display_name}</span>
                </div>
                <span className="text-sm text-gray-600">
                  Streak: {member.answer_streak}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
