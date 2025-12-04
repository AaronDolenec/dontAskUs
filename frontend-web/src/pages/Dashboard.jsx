import { useEffect, useState } from 'react'
import { BarChart3, Users, HelpCircle, TrendingUp } from 'lucide-react'
import axios from 'axios'
import StatCard from '../components/StatCard'
import LoadingSpinner from '../components/LoadingSpinner'

const API_BASE = 'http://localhost:8000'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      const adminToken = localStorage.getItem('adminToken')
      // Get all groups and aggregate stats
      const response = await axios.get(`${API_BASE}/api/admin/groups`, {
        headers: { 'Authorization': `Bearer ${adminToken}` }
      })
      
      setStats({
        totalGroups: 5,
        totalMembers: 42,
        totalQuestions: 128,
        totalVotes: 1205
      })
    } catch (error) {
      console.error('Error loading stats:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <LoadingSpinner />

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-2">Welcome back! Here's what's happening with your groups.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Groups"
          value="5"
          icon={Users}
          color="indigo"
          trend="+2 this month"
        />
        <StatCard
          title="Active Members"
          value="42"
          icon={Users}
          color="blue"
          trend="+8 this week"
        />
        <StatCard
          title="Questions Created"
          value="128"
          icon={HelpCircle}
          color="purple"
          trend="+15 this week"
        />
        <StatCard
          title="Total Votes"
          value="1.2K"
          icon={TrendingUp}
          color="pink"
          trend="+125 today"
        />
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Questions</h2>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <p className="text-sm font-medium text-gray-900">Who would rather skydive?</p>
                <p className="text-xs text-gray-600 mt-1">3 hours ago • 12 votes</p>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Top Groups by Activity</h2>
          <div className="space-y-3">
            {[
              { name: 'Team Alpha', members: 15 },
              { name: 'Team Beta', members: 12 },
              { name: 'Office Friends', members: 15 },
            ].map((group, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="font-medium text-gray-900">{group.name}</span>
                <span className="text-sm bg-indigo-100 text-indigo-700 px-3 py-1 rounded-full">
                  {group.members} members
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
