/** Auth context: login, session, permission helpers and silent token restore. */

import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { endpoints, tokenStore } from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'
import {
  ACCENT_KEYS,
  applyAccent,
  applyDensity,
  applyDirection,
  applyFontScale,
  applyMotion,
  applyTheme,
  DENSITIES,
  FONT_SCALES,
  MOTION_MODES,
  setAccent,
  setDensity,
  setDirection,
  setFontScale,
  setMotion,
  setTheme,
  THEME_MODES,
  useAppearanceSync,
} from '@/lib/theme'
import type { Density, Direction, FontScale, MotionMode, ThemeMode } from '@/lib/theme'

/** Narrow an untrusted string against a list of allowed values. */
function isOneOf(value: string | null | undefined, allowed: readonly string[]): value is string {
  return Boolean(value && allowed.includes(value))
}

type User = {
  user_id: number
  email: string
  full_name: string
  role: 'admin' | 'analyst' | 'viewer'
  job_title?: string | null
  department?: string | null
  timezone: string
  locale: string
  theme: string
  accent: string
  density: string
  motion?: string | null
  direction?: string | null
  font_scale?: string | null
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
  avatar_color?: string | null
  preferences?: Record<string, unknown> | null
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
  saveAppearance: (patch: Partial<Pick<User, 'theme' | 'accent' | 'density' | 'motion' | 'direction' | 'font_scale'>>) => void
}

const AuthContext = createContext<AuthState>({
  user: null,
  ready: false,
  authenticated: false,
  login: async () => {},
  logout: () => {},
  refresh: async () => {},
  can: () => false,
  saveAppearance: () => {},
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

  // Keep two open tabs visually identical, and follow OS theme changes.
  useAppearanceSync()

  /**
   * Reconcile the server-side profile with the local appearance store.
   *
   * The profile wins on sign-in so a preference follows the user across devices,
   * but every value is pushed through the theme module's own setters so that
   * `system` resolves against the OS instead of being coerced to a hard class.
   */
  useEffect(() => {
    if (!user) return

    // Narrow the loosely-typed profile strings against the allowed value sets.
    if (isOneOf(user.theme, THEME_MODES.map((mode) => mode.id))) setTheme(user.theme as ThemeMode)
    if (user.accent && ACCENT_KEYS.includes(user.accent)) setAccent(user.accent)
    if (isOneOf(user.density, DENSITIES.map((item) => item.id))) setDensity(user.density as Density)
    if (isOneOf(user.motion, MOTION_MODES.map((item) => item.id))) setMotion(user.motion as MotionMode)
    if (user.direction === 'rtl' || user.direction === 'ltr') setDirection(user.direction)
    if (isOneOf(user.font_scale, FONT_SCALES.map((item) => item.id))) setFontScale(user.font_scale as FontScale)
  }, [user])

  /**
   * Two-way binding for the appearance controls.
   *
   * Controls call these; the change is applied instantly (so the preview is live)
   * and persisted to the profile in the background so it survives a device change.
   */
  const saveAppearance = useCallback(
    (patch: Partial<Pick<User, 'theme' | 'accent' | 'density' | 'motion' | 'direction' | 'font_scale'>>) => {
      if (patch.theme) {
        applyTheme(patch.theme as ThemeMode)
        localStorage.setItem('pip.theme', patch.theme)
      }
      if (patch.accent) {
        applyAccent(patch.accent)
        localStorage.setItem('pip.accent', patch.accent)
      }
      if (patch.density) {
        applyDensity(patch.density as Density)
        localStorage.setItem('pip.density', patch.density)
      }
      if (patch.motion) {
        applyMotion(patch.motion as MotionMode)
        localStorage.setItem('pip.motion', patch.motion)
      }
      if (patch.direction) {
        applyDirection(patch.direction)
        localStorage.setItem('pip.direction', patch.direction)
      }
      if (patch.font_scale) {
        applyFontScale(patch.font_scale as FontScale)
        localStorage.setItem('pip.fontScale', patch.font_scale)
      }
      void endpoints
        .updateMe(patch as Record<string, unknown>)
        .then(setUser)
        .catch(() => undefined)
    },
    [],
  )

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
    () => ({ user, ready, authenticated: Boolean(user), login, logout, refresh: loadUser, can, saveAppearance }),
    [user, ready, login, logout, loadUser, can, saveAppearance],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}