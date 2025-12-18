import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import '../styles/Auth.css'

export default function LoginSimple() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [tempToken, setTempToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<'password' | 'totp'>('password')

  // Watch for token in localStorage and navigate when it appears
  useEffect(() => {
    const checkToken = setInterval(() => {
      const token = localStorage.getItem('accessToken')
      if (token) {
        console.log('✅ Token detected in localStorage, navigating to dashboard')
        clearInterval(checkToken)
        navigate('/dashboard')
      }
    }, 50)
    
    return () => clearInterval(checkToken)
  }, [navigate])

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('🔐 Password login submitted')
    setError('')
    setLoading(true)
    
    try {
      console.log('Fetching /api/admin/login')
      const response = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      
      console.log('Response status:', response.status)
      
      if (!response.ok) {
        const errData = await response.json()
        setError(errData.detail || 'Login failed')
        setLoading(false)
        return
      }

      const data = await response.json()
      console.log('Response data keys:', Object.keys(data))
      
      if (data.access_token) {
        console.log('✅ No 2FA needed, storing token in localStorage')
        localStorage.setItem('accessToken', data.access_token)
        localStorage.setItem('refreshToken', data.refresh_token)
        // Navigation will happen via the useEffect above
      } else if (data.temp_token) {
        console.log('🔑 2FA required, showing TOTP input')
        setTempToken(data.temp_token)
        setStep('totp')
        setLoading(false)
      } else {
        console.error('❌ No tokens in response:', data)
        setError('Invalid response from server')
        setLoading(false)
      }
    } catch (err: any) {
      console.error('Error:', err)
      setError(err.message || 'Network error')
      setLoading(false)
    }
  }

  const handleTotpSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('✅ TOTP code submitted:', totp)
    setError('')
    setLoading(true)
    
    try {
      console.log('Fetching /api/admin/2fa')
      const response = await fetch('/api/admin/2fa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken, totp_code: totp }),
      })
      
      console.log('Response status:', response.status)
      
      if (!response.ok) {
        const errData = await response.json()
        setError(errData.detail || '2FA verification failed')
        setLoading(false)
        return
      }

      const data = await response.json()
      console.log('✅ 2FA successful, storing tokens')
      localStorage.setItem('accessToken', data.access_token)
      localStorage.setItem('refreshToken', data.refresh_token)
      // Navigation will happen via the useEffect above
    } catch (err: any) {
      console.error('Error:', err)
      setError(err.message || 'Network error')
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
