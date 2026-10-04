/**
 * Typed API client.
 *
 * - one place that knows the base URL and the auth header
 * - automatic token refresh on 401 (single-flight, no request storms)
 * - typed helpers (`get`/`post`/`patch`/`del`) so pages never touch `fetch`
 * - a tiny in-memory cache so navigating back to a screen is instant (silent reload)
 */

export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'

const TOKEN_KEY = 'pip.token'
const REFRESH_KEY = 'pip.refresh'

/* ------------------------------------------------------------------ tokens */
export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh?: string) => {
    localStorage.setItem(TOKEN_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/* ------------------------------------------------------------------ errors */
export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  get isAuth() {
    return this.status === 401
  }
  get isForbidden() {
    return this.status === 403
  }
  get isNotFound() {
    return this.status === 404
  }
  get isOffline() {
    return this.status === 0
  }
}

/* ------------------------------------------------------------------ query string */
export type QueryValue = string | number | boolean | null | undefined | string[]

export function buildQuery(params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(','))
    } else {
      search.set(key, String(value))
    }
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

/* ------------------------------------------------------------------ core request */
let refreshInFlight: Promise<boolean> | null = null

async function refreshToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  const refresh = tokenStore.getRefresh()
  if (!refresh) return false
  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!response.ok) {
        tokenStore.clear()
        return false
      }
      const data = await response.json()
      tokenStore.set(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    } finally {
      refreshInFlight = null
    }
  })()
  return refreshInFlight
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
  retryOn401?: boolean
  raw?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, retryOn401 = true } = options
  const token = tokenStore.get()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Cannot reach the API. Is the server running?')
  }

  if (response.status === 401 && retryOn401 && token) {
    const refreshed = await refreshToken()
    if (refreshed) return request<T>(path, { ...options, retryOn401: false })
    tokenStore.clear()
    window.dispatchEvent(new CustomEvent('pip:unauthorized'))
  }

  if (options.raw) {
    if (!response.ok) throw new ApiError(response.status, 'http_error', response.statusText)
    return response as unknown as T
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  let payload: any = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = text
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error ?? 'http_error',
      payload?.message ?? `Request failed (${response.status})`,
      payload?.details ?? {},
    )
  }
  return payload as T
}

export const api = {
  get: <T>(path: string, params?: Record<string, QueryValue>, signal?: AbortSignal) =>
    request<T>(`${path}${buildQuery(params)}`, { signal }),
  post: <T>(path: string, body?: unknown, params?: Record<string, QueryValue>) =>
    request<T>(`${path}${buildQuery(params)}`, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  refreshToken,
}

/* ------------------------------------------------------------------ endpoint helpers */
export const endpoints = {
  health: () => api.get<any>('/health'),
  meta: () => api.get<any>('/meta'),
  statsTables: () => api.get<any>('/stats/tables'),
  demoAccounts: () => api.get<any>('/auth/demo-accounts'),

  login: (email: string, password: string, remember = true) =>
    api.post<any>('/auth/login', { email, password, remember }),
  logout: () => api.post<any>('/auth/logout'),
  me: () => api.get<any>('/auth/me'),
  session: () => api.get<any>('/auth/session'),
  updateMe: (payload: Record<string, unknown>) => api.patch<any>('/users/me', payload),
  changePassword: (current_password: string, new_password: string) =>
    api.post<any>('/auth/change-password', { current_password, new_password }),

  kpi: (days = 30) => api.get<any>('/analytics/kpi', { days }),
  trend: (days = 90) => api.get<any[]>('/analytics/trend', { days }),
  priceTrend: (days = 90) => api.get<any[]>('/analytics/price-trend', { days }),
  categories: (limit = 20) => api.get<any[]>('/analytics/categories', { limit }),
  brands: (limit = 20) => api.get<any[]>('/analytics/brands', { limit }),
  availability: () => api.get<any[]>('/analytics/availability'),
  sourceCoverage: () => api.get<any[]>('/analytics/sources'),
  categoryIndex: (days = 60, category?: string) => api.get<any[]>('/analytics/category-index', { days, category }),
  compliance: (days = 30) => api.get<any>('/analytics/report/compliance', { days }),
  sourceMatrix: () => api.get<any[]>('/analytics/report/source-matrix'),

  products: (params: Record<string, QueryValue>) => api.get<any>('/products', params),
  product: (id: number, historyLimit = 400) => api.get<any>(`/products/${id}`, { history_limit: historyLimit }),
  productHistory: (id: number, limit = 500) => api.get<any>(`/products/${id}/history`, { limit }),
  productDuplicates: (id: number) => api.get<any>(`/products/${id}/duplicates`),
  facets: () => api.get<any>('/products/facets'),
  categoriesTree: () => api.get<any[]>('/products/categories'),
  suggest: (q: string) => api.get<any[]>('/products/search/suggest', { q, limit: 8 }),
  compare: (ids: number[]) => api.get<any[]>('/products/compare/ids', { ids: ids.join(',') }),

  priceChanges: (params: Record<string, QueryValue>) => api.get<any>('/changes/price', params),
  topMovers: (limit = 20, direction?: string) => api.get<any[]>('/changes/top-movers', { limit, direction }),
  events: (params: Record<string, QueryValue>) => api.get<any>('/changes/events', params),
  newProducts: (days = 30, limit = 50) => api.get<any[]>('/changes/new', { days, limit }),
  removedProducts: (days = 180, limit = 50) => api.get<any[]>('/changes/removed', { days, limit }),
  categoryChanges: (days = 180, limit = 50) => api.get<any[]>('/changes/categories', { days, limit }),
  categoryDrift: (days = 90) => api.get<any[]>('/changes/category-drift', { days }),
  changeSummary: (days = 30) => api.get<any>('/changes/summary', { days }),

  runs: (params: Record<string, QueryValue>) => api.get<any>('/pipeline/runs', params),
  runLatest: () => api.get<any>('/pipeline/runs/latest'),
  run: (runId: string) => api.get<any>(`/pipeline/runs/${runId}`),
  runDq: (runId: string) => api.get<any[]>(`/pipeline/runs/${runId}/dq`),
  runHttp: (runId: string, limit = 200) => api.get<any[]>(`/pipeline/runs/${runId}/http`, { limit }),
  sourceStatus: () => api.get<any[]>('/pipeline/sources/status'),
  stages: () => api.get<any>('/pipeline/stages'),
  schedule: () => api.get<any>('/pipeline/schedule'),
  triggerRun: (payload: Record<string, unknown>) => api.post<any>('/pipeline/run', payload),
  triggerRunSync: (payload: Record<string, unknown>) => api.post<any>('/pipeline/run/sync', payload),

  qualityLatest: () => api.get<any>('/quality/latest'),
  qualityRules: () => api.get<any[]>('/quality/rules'),
  qualityResults: (params: Record<string, QueryValue>) => api.get<any>('/quality/results', params),
  qualityTrend: (days = 90) => api.get<any[]>('/quality/trend', { days }),
  qualitySummary: () => api.get<any>('/quality/summary'),

  catalogProducts: (params: Record<string, QueryValue>) => api.get<any>('/catalog/products', params),
  catalogReconciliation: (params: Record<string, QueryValue>) => api.get<any>('/catalog/reconciliation', params),
  catalogSummary: (runId?: string) => api.get<any>('/catalog/summary', { run_id: runId }),
  catalogOpportunities: (limit = 20) => api.get<any[]>('/catalog/opportunities', { limit }),

  sources: () => api.get<any[]>('/sources'),
  sourceRobots: () => api.get<any>('/sources/robots'),
  sourcePreview: (code: string, limit = 5) => api.get<any>(`/sources/${code}/preview`, { limit }),

  views: () => api.get<any[]>('/queries/views'),
  queryTables: () => api.get<any>('/queries/tables'),
  queryExamples: () => api.get<any[]>('/queries/examples'),
  executeQuery: (sql: string, limit = 200) => api.post<any>('/queries/execute', { sql, limit }),

  users: (params: Record<string, QueryValue>) => api.get<any>('/users', params),
  userStats: () => api.get<any>('/users/stats'),
  createUser: (payload: Record<string, unknown>) => api.post<any>('/users', payload),
  updateUser: (id: number, payload: Record<string, unknown>) => api.patch<any>(`/users/${id}`, payload),
  deactivateUser: (id: number) => api.del<any>(`/users/${id}`),
  apiKeys: (userId: number) => api.get<any[]>(`/users/${userId}/api-keys`),
  createApiKey: (userId: number, name: string) => api.post<any>(`/users/${userId}/api-keys`, { name }),
  revokeApiKey: (userId: number, keyId: number) => api.del<any>(`/users/${userId}/api-keys/${keyId}`),

  savedViews: (entity?: string) => api.get<any[]>('/saved-views', { entity }),
  createSavedView: (payload: Record<string, unknown>) => api.post<any>('/saved-views', payload),
  deleteSavedView: (id: number) => api.del<any>(`/saved-views/${id}`),
  favoriteView: (id: number) => api.post<any>(`/saved-views/${id}/favorite`),

  notifications: (pageSize = 25, unreadOnly = false) =>
    api.get<any>('/notifications', { page_size: pageSize, unread_only: unreadOnly }),
  markRead: (id: number) => api.post<any>(`/notifications/${id}/read`),
  markAllRead: () => api.post<any>('/notifications/read-all'),

  alerts: () => api.get<any[]>('/alerts'),
  createAlert: (payload: Record<string, unknown>) => api.post<any>('/alerts', payload),
  updateAlert: (id: number, payload: Record<string, unknown>) => api.patch<any>(`/alerts/${id}`, payload),
  deleteAlert: (id: number) => api.del<any>(`/alerts/${id}`),
  evaluateAlerts: () => api.post<any>('/alerts/evaluate'),

  settings: () => api.get<any[]>('/settings'),
  updateSetting: (key: string, value: string) => api.put<any>(`/settings/${key}`, { value }),

  auditLog: (params: Record<string, QueryValue>) => api.get<any>('/audit', params),
  httpLog: (limit = 100, sourceCode?: string) => api.get<any[]>('/audit/http', { limit, source_code: sourceCode }),
  auditActions: () => api.get<any[]>('/audit/actions'),
}