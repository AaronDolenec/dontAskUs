import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ReactNode, useEffect, useState } from 'react'

interface ProtectedRouteProps {
  children: ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { accessToken, logout } = useAuth()
  const [validating, setValidating] = useState(true)
  const [isValid, setIsValid] = useState(false)

  useEffect(() => {
    // Validate token on mount by calling profile endpoint
    const validateToken = async () => {
      if (!accessToken) {
        setValidating(false)
        setIsValid(false)
        return
      }

      try {
        const res = await fetch('/api/admin/profile', {
          headers: { Authorization: `Bearer ${accessToken}` }
        })
        if (res.ok) {
          setIsValid(true)
        } else {
          // Token invalid or expired - clear it
          console.log('🔒 Token invalid, clearing session')
          await logout()
          setIsValid(false)
        }
      } catch {
        // Network error - clear session to be safe
        await logout()
        setIsValid(false)
      } finally {
        setValidating(false)
      }
    }

    validateToken()
  }, [accessToken, logout])

  if (validating) {
    return <div className="loading-text" style={{ padding: 40, textAlign: 'center' }}>Validating session...</div>
  }

  if (!isValid) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
