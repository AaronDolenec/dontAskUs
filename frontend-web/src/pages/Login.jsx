import { useState } from 'react'
import { Lock } from 'lucide-react'

export default function Login({ setAdminToken }) {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')

  const handleLogin = (e) => {
    e.preventDefault()
    if (!token.trim()) {
      setError('Please enter an admin token')
      return
    }
    setAdminToken(token)
    setError('')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-600 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Lock size={32} className="text-indigo-600" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900">AskUs Admin</h1>
          <p className="text-gray-600 mt-2">Sign in to your dashboard</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-gray-900 mb-2">Admin Token</label>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Enter your admin token"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            className="w-full px-4 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:shadow-lg transition"
          >
            Sign In
          </button>
        </form>

        <p className="text-center text-xs text-gray-600 mt-6">
          Lost your admin token? Contact your system administrator
        </p>
      </div>
    </div>
  )
}
