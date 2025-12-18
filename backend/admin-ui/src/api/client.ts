import { useAuth } from '../context/AuthContext'
import { useCallback } from 'react'

interface ApiOptions {
  method?: string
  body?: any
  headers?: Record<string, string>
}

export function useApi() {
  const { accessToken, refreshAccessToken, logout } = useAuth()

  const request = useCallback(
    async (url: string, options: ApiOptions = {}) => {
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      }

      if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`
      }

      let response = await fetch(url, {
        ...options,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
      })

      // Auto-refresh on 401
      if (response.status === 401 && accessToken) {
        try {
          await refreshAccessToken()
          // Retry request
          headers.Authorization = `Bearer ${accessToken}`
          response = await fetch(url, {
            ...options,
            headers,
            body: options.body ? JSON.stringify(options.body) : undefined,
          })
        } catch {
          await logout()
          throw new Error('Session expired')
        }
      }

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${response.status}`)
      }

      return await response.json()
    },
    [accessToken, refreshAccessToken, logout]
  )

  return { request }
}

export const api = {
  async dashboard(accessToken: string) {
    return fetch('/api/admin/dashboard/stats', {
      headers: { Authorization: `Bearer ${accessToken}`, 'Cache-Control': 'no-cache' },
    }).then(r => r.json())
  },

  async users(accessToken: string, limit = 50, offset = 0, suspendedOnly = false) {
    return fetch(
      `/api/admin/users?limit=${limit}&offset=${offset}&suspended_only=${suspendedOnly}`,
      { headers: { Authorization: `Bearer ${accessToken}`, 'Cache-Control': 'no-cache' } }
    ).then(r => r.json())
  },

  async suspendUser(accessToken: string, userId: number, isSuspended: boolean, reason?: string) {
    return fetch(`/api/admin/users/${userId}/suspension`, {
      method: 'PUT',
      headers: { 
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ is_suspended: isSuspended, suspension_reason: reason }),
    }).then(r => r.json())
  },

  async recoverUserToken(accessToken: string, userId: number, reason: string) {
    return fetch(`/api/admin/users/${userId}/recover-token`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ reason }),
    }).then(r => r.json())
  },

  async groups(accessToken: string, limit = 50, offset = 0) {
    return fetch(
      `/api/admin/groups?limit=${limit}&offset=${offset}`,
      { headers: { Authorization: `Bearer ${accessToken}`, 'Cache-Control': 'no-cache' } }
    ).then(r => r.json())
  },

  async updateGroupNotes(accessToken: string, groupId: number, notes: string) {
    return fetch(`/api/admin/groups/${groupId}/notes`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ notes }),
    }).then(r => r.json())
  },

  async questionSets(
    accessToken: string,
    limit = 50,
    offset = 0,
    publicOnly = false,
    privateOnly = false
  ) {
    return fetch(
      `/api/admin/question-sets?limit=${limit}&offset=${offset}&public_only=${publicOnly}&private_only=${privateOnly}`,
      { headers: { Authorization: `Bearer ${accessToken}`, 'Cache-Control': 'no-cache' } }
    ).then(r => r.json())
  },

  async auditLogs(accessToken: string, limit = 50, offset = 0) {
    return fetch(
      `/api/admin/audit-logs?limit=${limit}&offset=${offset}`,
      { headers: { Authorization: `Bearer ${accessToken}`, 'Cache-Control': 'no-cache' } }
    ).then(r => r.json())
  },

  async profile(accessToken: string) {
    return fetch('/api/admin/profile', {
      headers: { Authorization: `Bearer ${accessToken}`, 'Cache-Control': 'no-cache' },
    }).then(r => r.json())
  },

  async changePassword(accessToken: string, currentPassword: string, newPassword: string) {
    console.log('📡 changePassword API call')
    const response = await fetch('/api/admin/account/change-password', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
    
    console.log('Response status:', response.status)
    const data = await response.json()
    console.log('Response data:', data)
    
    if (!response.ok) {
      throw new Error(data.detail || 'Password change failed')
    }
    
    return data
  },

  async initiateTotpSetup(accessToken: string) {
    console.log('📡 initiateTotpSetup API call')
    const response = await fetch('/api/admin/account/totp/setup-initiate', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    
    console.log('Response status:', response.status)
    const data = await response.json()
    console.log('Response data:', data)
    
    if (!response.ok) {
      throw new Error(data.detail || 'TOTP setup failed')
    }
    
    return data
  },

  async verifyTotpSetup(accessToken: string, code: string) {
    console.log('📡 verifyTotpSetup API call with code:', code)
    const response = await fetch('/api/admin/account/totp/setup-verify', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ code }),
    })
    
    console.log('Response status:', response.status)
    const data = await response.json()
    console.log('Response data:', data)
    
    if (!response.ok) {
      throw new Error(data.detail || 'TOTP verification failed')
    }
    
    return data
  },
}
