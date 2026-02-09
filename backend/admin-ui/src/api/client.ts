import { useAuth } from '../context/AuthContext'
import { useCallback } from 'react'
import { addLogEntry } from './apiLogger'

/**
 * Unified admin-UI API client.
 *
 * Every page must call the `useApi()` hook which returns a single `request()`
 * function.  It automatically attaches the current Bearer token, retries once
 * on 401 via the refresh-token flow, and logs the user out when the session
 * is truly expired.
 *
 * All requests and responses are automatically logged to localStorage via apiLogger.
 */
export function useApi() {
  const { accessToken, refreshAccessToken, logout } = useAuth()

  const request = useCallback(
    async (url: string, options: { method?: string; body?: any; headers?: Record<string, string> } = {}) => {
      const method = options.method || 'GET'
      const startTime = performance.now()

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
        ...options.headers,
      }

      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
      }

      const fetchOpts: RequestInit = {
        method,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
      }

      let response: Response
      try {
        response = await fetch(url, fetchOpts)

        // Auto-refresh on 401
        if (response.status === 401 && accessToken) {
          try {
            await refreshAccessToken()
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
      } catch (err: any) {
        // Log network errors
        addLogEntry({
          method, url,
          requestBody: options.body,
          status: null,
          statusText: 'Network Error',
          responseBody: undefined,
          durationMs: Math.round(performance.now() - startTime),
          error: err.message,
        })
        throw err
      }

      // Clone the response so we can read the body for logging without consuming it
      const cloned = response.clone()
      let responseBody: any
      try {
        responseBody = await cloned.json()
      } catch {
        try { responseBody = await cloned.text() } catch { responseBody = undefined }
      }

      addLogEntry({
        method, url,
        requestBody: options.body,
        status: response.status,
        statusText: response.statusText,
        responseBody,
        durationMs: Math.round(performance.now() - startTime),
      })

      return response
    },
    [accessToken, refreshAccessToken, logout],
  )

  return { request }
}
