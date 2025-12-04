import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import LoadingSpinner from '../components/LoadingSpinner'

const API_BASE = 'http://localhost:8000'

export default function Analytics({ adminToken }) {
  const { groupId } = useParams()
  const [analytics, setAnalytics] = useState(null)
  const [leaderboard, setLeaderboard] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAnalytics()
    loadLeaderboard()
  }, [groupId])

  const loadAnalytics = async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/api/admin/groups/${adminToken}/analytics`,
        { params: { days: 30 } }
      )
      setAnalytics(response.data)
    } catch (error) {
      console.error('Error loading analytics:', error)
    }
  }

  const loadLeaderboard = async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/api/admin/groups/${adminToken}/leaderboard`
      )
      setLeaderboard(response.data)
    } catch (error) {
      console.error('Error loading leaderboard:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <LoadingSpinner />
  if (!analytics) return <div>No analytics data available</div>

  const chartData = analytics.questions_history.map(q => ({
    name: new Date(q.created_at).toLocaleDateString(),
    optionA: q.vote_count_a,
    optionB: q.vote_count_b,
    participation: q.participation_rate,
  }))

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-4xl font-bold text-gray-900">{analytics.group_name} Analytics</h1>
        <p className="text-gray-600 mt-2">Detailed performance metrics and insights</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Members', value: analytics.total_members },
          { label: 'Questions Created', value: analytics.total_questions },
          { label: 'Total Votes', value: analytics.total_votes },
          { label: 'Avg Participation', value: `${analytics.average_participation_rate}%` },
        ].map((stat, i) => (
          <div key={i} className="bg-white rounded-lg shadow p-6 border border-gray-200">
            <p className="text-sm text-gray-600 font-semibold">{stat.label}</p>
            <p className="text-3xl font-bold text-indigo-600 mt-2">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Votes per Question</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="optionA" fill="#6366f1" name="Option A" />
              <Bar dataKey="optionB" fill="#ec4899" name="Option B" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Participation Rate</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="participation"
                stroke="#10b981"
                strokeWidth={2}
                name="Participation %"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent Questions */}
      <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Questions</h2>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {analytics.questions_history.map((question, i) => (
            <div key={i} className="p-4 bg-gray-50 rounded-lg border border-gray-200">
              <p className="font-medium text-gray-900">{question.question_text}</p>
              <div className="mt-3 grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-600">Option A: {question.option_a || 'N/A'}</p>
                  <p className="text-lg font-bold text-indigo-600">{question.vote_count_a} votes</p>
                </div>
                <div>
                  <p className="text-xs text-gray-600">Option B: {question.option_b || 'N/A'}</p>
                  <p className="text-lg font-bold text-pink-600">{question.vote_count_b} votes</p>
                </div>
              </div>
              <p className="text-xs text-gray-600 mt-2">{question.participation}% participation</p>
            </div>
          ))}
        </div>
      </div>

      {/* Leaderboard */}
      <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Leaderboard</h2>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {leaderboard?.map((member, i) => (
            <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-full"
                  style={{ backgroundColor: member.color_avatar }}
                >
                  <span className="text-white text-xs font-bold">
                    {member.display_name[0].toUpperCase()}
                  </span>
                </div>
                <span className="font-medium text-gray-900">{member.display_name}</span>
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold text-indigo-600">
                  Streak: {member.answer_streak}
                </div>
                <div className="text-xs text-gray-600">
                  Best: {member.longest_answer_streak}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
