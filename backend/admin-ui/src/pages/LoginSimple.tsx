import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import '../styles/Auth.css'

export default function LoginSimple() {
  const navigate = useNavigate()
  const { accessToken, login, verify2fa } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [tempToken, setTempToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<'password' | 'totp'>('password')

  // Navigate to dashboard once we have a valid access token
  useEffect(() => {
    if (accessToken) {
      navigate('/dashboard')
    }
  }, [accessToken, navigate])

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(username, password)
      // If 2FA is needed, AuthContext sets totpRequired and stores tempToken
      const storedTemp = localStorage.getItem('tempToken')
      if (storedTemp) {
        setTempToken(storedTemp)
        setStep('totp')
        setLoading(false)
      }
      // Otherwise accessToken will be set and useEffect navigates
    } catch (err: any) {
      setError(err.message || 'Login failed')
      setLoading(false)
    }
  }

  const handleTotpSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await verify2fa(tempToken, totp)
      // accessToken will be set and useEffect navigates
    } catch (err: any) {
      setError(err.message || '2FA verification failed')
      setLoading(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-box">
        <h1>dontAskUs Admin</h1>
        
        {step === 'password' ? (
          <form onSubmit={handlePasswordSubmit}>
            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                disabled={loading}
                required
                autoFocus
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                disabled={loading}
                required
              />
            </div>
            {error && <div className="error">{error}</div>}
            <button type="submit" disabled={loading}>
              {loading ? 'Logging in...' : 'Login'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleTotpSubmit}>
            <p>Enter the 6-digit code from your authenticator app</p>
            <div className="form-group">
              <label>2FA Code</label>
              <input
                type="text"
                maxLength={6}
                value={totp}
                onChange={e => setTotp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                disabled={loading}
                placeholder="000000"
                required
                autoFocus
              />
            </div>
            {error && <div className="error">{error}</div>}
            <button type="submit" disabled={loading || totp.length !== 6}>
              {loading ? 'Verifying...' : 'Verify'}
            </button>
            <button
              type="button"
              onClick={() => {
                setStep('password')
                setTotp('')
                setError('')
              }}
              disabled={loading}
              style={{ marginLeft: '8px' }}
            >
              Back
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
