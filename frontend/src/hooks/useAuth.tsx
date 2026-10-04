/** Auth context: login, session, permission helpers and silent token restore. */

import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { endpoints, tokenStore } from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'

type User = {
  user_id: number
  email: string
  full_name: string
  role: 'admin' | 'analyst' | 'viewer'
  job_title?: string | null
  department?: string | null
  avatar_color?: string | null
  timezone: string
  locale: string
  theme: 'system' | 'light' | 'dark'
  accent: string
  density: 'compact' | 'comfortable' | 'spacious'
  rows_per_page: number
  default_currency: string
  price_change_alert_pct: number
  email_alerts_enabled: boolean
  weekly_digest_enabled: boolean
  two_factor_enabled: boolean
  is_active: boolean
  is_verified: boolean
  login_count: number
  last_login_at?: string | null
  created_at?: string | null
  permissions: string[]
}

type AuthState = {
  user: User | null
  ready: boolean
  authenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
  can: (permission: string) => boolean
}

const AuthContext = createContext<AuthState>({
  user: null,
  ready: false,
  authenticated: false,
  login: async () => {},
  logout: () => {},
  refresh: async () => {},
  can: () => false,
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const queryClient = useQueryClient()

  const loadUser = useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null)
      setReady(true)
      return
    }
    try {
      const profile = await endpoints.me()
      setUser(profile)
    } catch {
      tokenStore.clear()
      setUser(null)
    } finally {
      setReady(true)
    }
  }, [])

  // Silent session restore on boot + hard logout on an unrecoverable 401.
  useEffect(() => {
    void loadUser()
    const onUnauthorized = () => {
      tokenStore.clear()
      setUser(null)
      queryClient.clear()
    }
    window.addEventListener('pip:unauthorized', onUnauthorized)
    return () => window.removeEventListener('pip:unauthorized', onUnauthorized)
  }, [loadUser, queryClient])

  // Keep the appearance in sync with the server-side profile.
  useEffect(() => {
    if (!user) return
    if (user.theme) {
      localStorage.setItem('pip.theme', user.theme)
      document.documentElement.classList.toggle('dark', user.theme === 'dark')
    }
    if (user.density) {
      localStorage.setItem('pip.density', user.density)
      document.documentElement.dataset.density = user.density
    }
    if (user.accent) localStorage.setItem('pip.accent', user.accent)
  }, [user])

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await endpoints.login(email, password)
      tokenStore.set(response.access_token, response.refresh_token)
      setUser(response.user)
      setReady(true)
      queryClient.clear()
    },
    [queryClient],
  )

  const logout = useCallback(() => {
    void endpoints.logout().catch(() => undefined)
    tokenStore.clear()
    setUser(null)
    queryClient.clear()
  }, [queryClient])

  const can = useCallback(
    (permission: string) => Boolean(user?.permissions?.includes(permission)),
    [user],
  )

  const value = useMemo<AuthState>(
    () => ({ user, ready, authenticated: Boolean(user), login, logout, refresh: loadUser, can }),
    [user, ready, login, logout, loadUser, can],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}