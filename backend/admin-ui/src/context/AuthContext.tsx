import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

interface AuthContextType {
  accessToken: string | null
  refreshToken: string | null
  totpRequired: boolean
  username: string | null
  login: (username: string, password: string, ip?: string) => Promise<void>
  verify2fa: (tempToken: string, code: string, ip?: string) => Promise<void>
  logout: () => Promise<void>
  refreshAccessToken: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(
    localStorage.getItem('accessToken')
  )
  const [refreshToken, setRefreshToken] = useState<string | null>(
    localStorage.getItem('refreshToken')
  )
  const [totpRequired, setTotpRequired] = useState(false)
  const [username, setUsername] = useState<string | null>(
    localStorage.getItem('username')
  )

  const login = useCallback(async (user: string, password: string, ip?: string) => {
    const headers: any = { 'Content-Type': 'application/json' }
    if (ip) {
      headers['X-Forwarded-For'] = ip
    }
    
    const response = await fetch('/api/admin/login', {
      method: 'POST',
      headers,
      body: JSON.stringify({ username: user, password }),
    })

    if (!response.ok) {
      let errData
      try {
        errData = await response.json()
      } catch {
        errData = { detail: response.statusText }
      }
      throw new Error(errData.detail || 'Login failed')
    }

    const data = await response.json()

    setUsername(user)
    localStorage.setItem('username', user)

    if (data.temp_token) {
      setTotpRequired(true)
      localStorage.setItem('tempToken', data.temp_token)
    } else if (data.access_token) {
      setAccessToken(data.access_token)
      setRefreshToken(data.refresh_token)
      setTotpRequired(false)
      localStorage.setItem('accessToken', data.access_token)
      localStorage.setItem('refreshToken', data.refresh_token)
    } else {
      throw new Error('No tokens in response')
    }
  }, [])

  const verify2fa = useCallback(async (tempToken: string, code: string, ip?: string) => {
    const headers: any = { 'Content-Type': 'application/json' }
    if (ip) {
      headers['X-Forwarded-For'] = ip
    }
    
    const response = await fetch('/api/admin/2fa', {
      method: 'POST',
      headers,
      body: JSON.stringify({ temp_token: tempToken, totp_code: code }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '2FA verification failed')
    }

    const data = await response.json()
    setAccessToken(data.access_token)
    setRefreshToken(data.refresh_token)
    setTotpRequired(false)
    localStorage.setItem('accessToken', data.access_token)
    localStorage.setItem('refreshToken', data.refresh_token)
    localStorage.removeItem('tempToken')
  }, [])

  const logout = useCallback(async () => {
    if (accessToken) {
      await fetch('/api/admin/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      }).catch(() => {})
    }
    setAccessToken(null)
    setRefreshToken(null)
    setTotpRequired(false)
    setUsername(null)
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('username')
    localStorage.removeItem('tempToken')
  }, [accessToken])

  const refreshAccessToken = useCallback(async () => {
    if (!refreshToken) throw new Error('No refresh token')

    const response = await fetch('/api/admin/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!response.ok) {
      await logout()
      throw new Error('Token refresh failed')
    }

    const data = await response.json()
    setAccessToken(data.access_token)
    setRefreshToken(data.refresh_token)
    localStorage.setItem('accessToken', data.access_token)
    localStorage.setItem('refreshToken', data.refresh_token)
  }, [refreshToken, logout])

  return (
    <AuthContext.Provider
      value={{
        accessToken,
        refreshToken,
        totpRequired,
        username,
        login,
        verify2fa,
        logout,
        refreshAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
