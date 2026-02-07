import { useAuth } from '../context/AuthContext'
import { useCallback } from 'react'

/**
 * Unified admin-UI API client.
 *
 * Every page must call the `useApi()` hook which returns a single `request()`
 * function.  It automatically attaches the current Bearer token, retries once
 * on 401 via the refresh-token flow, and logs the user out when the session
 * is truly expired.
 */
export function useApi() {
  const { accessToken, refreshAccessToken, logout } = useAuth()

  const request = useCallback(
    async (url: string, options: { method?: string; body?: any; headers?: Record<string, string> } = {}) => {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
        ...options.headers,
      }

      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
      }

      const fetchOpts: RequestInit = {
        method: options.method || 'GET',
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
      }

      let response = await fetch(url, fetchOpts)

      // Auto-refresh on 401
      if (response.status === 401 && accessToken) {
        try {
          await refreshAccessToken()
          // After refresh the new token is in localStorage
          const newToken = localStorage.getItem('accessToken')
          if (newToken) {
            headers['Authorization'] = `Bearer ${newToken}`
          }
          response = await fetch(url, { ...fetchOpts, headers })
        } catch {
          await logout()
          throw new Error('Session expired')
        }
      }

      return response
    },
    [accessToken, refreshAccessToken, logout],
  )

  return { request }
}
