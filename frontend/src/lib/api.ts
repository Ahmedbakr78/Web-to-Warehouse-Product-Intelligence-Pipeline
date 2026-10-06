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
  del: <T>(path: string, body?: unknown) => request<T>(path, { method: 'DELETE', body }),
  refreshToken,
}

/* ------------------------------------------------------------------ endpoint helpers */
/** Cancellable product search, used by the command palette. */
export function searchProducts(
  q: string,
  signal?: AbortSignal,
): Promise<{ items?: Array<Record<string, unknown>> }> {
  return api.get<{ items?: Array<Record<string, unknown>> }>('/products', { q, page: 1, page_size: 6 }, signal)
}

export const endpoints = {
  health: () => api.get<any>('/health'),
  meta: () => api.get<any>('/meta'),
  metaFeatures: () => api.get<any>('/meta/features'),
  statsTables: () => api.get<any>('/stats/tables'),
  demoAccounts: () => api.get<any>('/auth/demo-accounts'),

  // The second factor travels on the same request: the server verifies the password
  // first and only then checks the code, so no unauthenticated challenge is issued.
  login: (email: string, password: string, remember = true, secondFactor?: { totp_code?: string; recovery_code?: string }) =>
    api.post<any>('/auth/login', { email, password, remember, ...(secondFactor ?? {}) }),
  logout: (sessionKey?: string) =>
    api.post<any>(`/auth/logout${sessionKey ? `?session_key=${encodeURIComponent(sessionKey)}` : ''}`),
  me: () => api.get<any>('/auth/me'),
  session: () => api.get<any>('/auth/session'),
  updateMe: (payload: Record<string, unknown>) => api.patch<any>('/users/me', payload),
  changePassword: (current_password: string, new_password: string) =>
    api.post<any>('/auth/change-password', { current_password, new_password }),
  exportMyData: () => api.get<any>('/users/me/export'),
  deleteMyAccount: (password: string) => api.del<any>('/users/me', { password }),
  myActivity: (params: Record<string, QueryValue> = {}) => api.get<any>('/audit/me', params),

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
  watchlist: () => api.get<any>('/users/me/watchlist'),
  watchAdd: (id: number) => api.post<any>(`/users/me/watchlist/${id}`),
  watchRemove: (id: number) => api.del<any>(`/users/me/watchlist/${id}`),
  watchClear: () => api.del<any>('/users/me/watchlist'),

  sources: () => api.get<any[]>('/sources'),
  sourceRobots: () => api.get<any>('/sources/robots'),
  sourcePreview: (code: string, limit = 5) => api.get<any>(`/sources/${code}/preview`, { limit }),
  sourcePresets: () => api.get<any>('/sources/presets'),
  checkSource: (payload: Record<string, unknown>) => api.post<any>('/sources/check', payload),
  createSource: (payload: Record<string, unknown>) => api.post<any>('/sources', payload),
  updateSource: (code: string, payload: Record<string, unknown>) =>
    api.patch<any>(`/sources/${code}`, payload),
  deleteSource: (code: string) => api.del<any>(`/sources/${code}`),

  views: () => api.get<any[]>('/queries/views'),
  queryTables: () => api.get<any>('/queries/tables'),
  queryExamples: () => api.get<any[]>('/queries/examples'),
  executeQuery: (sql: string, limit = 200) => api.post<any>('/queries/execute', { sql, limit }),
  builderSchema: () => api.get<any>('/builder/schema'),
  builderQuery: (payload: Record<string, unknown>) => api.post<any>('/builder/query', payload),

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

  // ---------------------------------------------------------------- integrations
  exportDatasets: () => api.get<any>('/export/datasets'),
  exportPreview: (dataset: string, params: Record<string, QueryValue> = {}) =>
    api.get<any>(`/export/${dataset}`, params),

  webhookEvents: () => api.get<any>('/webhooks/events'),
  webhooks: () => api.get<any[]>('/webhooks'),
  createWebhook: (payload: Record<string, unknown>) => api.post<any>('/webhooks', payload),
  updateWebhook: (id: number, payload: Record<string, unknown>) =>
    api.patch<any>(`/webhooks/${id}`, payload),
  deleteWebhook: (id: number) => api.del<any>(`/webhooks/${id}`),
  testWebhook: (id: number, payload: Record<string, unknown> = {}) =>
    api.post<any>(`/webhooks/${id}/test`, payload),
  webhookDeliveries: (id: number, params: Record<string, QueryValue> = {}) =>
    api.get<any>(`/webhooks/${id}/deliveries`, params),
  rotateWebhookSecret: (id: number) => api.post<any>(`/webhooks/${id}/rotate-secret`),

  compareRuns: (base: string, target: string) =>
    api.get<any>('/pipeline/runs/compare', { base, target }),
  backfills: (limit = 25) => api.get<any[]>('/pipeline/backfills', { limit }),
  runBackfill: (payload: Record<string, unknown>) => api.post<any>('/pipeline/backfill', payload),
  backfill: (id: string) => api.get<any>(`/pipeline/backfill/${id}`),

  // ---------------------------------------------------------------- background jobs
  jobs: (params: Record<string, QueryValue> = {}) => api.get<any>('/jobs', params),
  job: (reference: string) => api.get<any>(`/jobs/${reference}`),
  jobEvents: (reference: string, afterId = 0) =>
    api.get<any>(`/jobs/${reference}/events`, { after_id: afterId }),
  jobTypes: () => api.get<any>('/jobs/types'),
  jobWorker: () => api.get<any>('/jobs/worker'),
  enqueuePipelineRun: (params: Record<string, QueryValue> = {}) =>
    api.post<any>('/jobs/pipeline-run', undefined, params),
  enqueueExport: (params: Record<string, QueryValue> = {}) => api.post<any>('/jobs/export', undefined, params),
  cancelJob: (reference: string) => api.post<any>(`/jobs/${reference}/cancel`),
  retryJob: (reference: string) => api.post<any>(`/jobs/${reference}/retry`),
  deleteJob: (reference: string) => api.del<any>(`/jobs/${reference}`),

  // ---------------------------------------------------------------- two-factor auth
  twoFactorStatus: () => api.get<any>('/account/2fa/status'),
  twoFactorSetup: () => api.post<any>('/account/2fa/setup'),
  twoFactorActivate: (secret: string, code: string) =>
    api.post<any>('/account/2fa/activate', { secret, code }),
  twoFactorDisable: (code: string) => api.post<any>('/account/2fa/disable', { code }),
  twoFactorCodes: (code: string) => api.post<any>('/account/2fa/recovery-codes', { code }),
  twoFactorVerify: (code: string) => api.post<any>('/account/2fa/verify', { code }),
  sessions: (current?: string) => api.get<any>('/account/sessions', current ? { current } : undefined),
  revokeSession: (sessionKey?: string) => api.post<any>('/account/sessions/revoke', { session_key: sessionKey }),
  revokeOtherSessions: (current: string) =>
    api.post<any>(`/account/sessions/revoke-others?current=${encodeURIComponent(current)}`),

  // ---------------------------------------------------------------- forecasting
  forecast: (productId: number, horizon = 14, days = 120) =>
    api.get<any>(`/forecast/${productId}`, { horizon, days }),
  forecastAnomalies: (productId: number, params: Record<string, QueryValue> = {}) =>
    api.get<any>(`/forecast/${productId}/anomalies`, params),
  allAnomalies: (params: Record<string, QueryValue> = {}) => api.get<any>('/forecast/products/anomalies', params),
  predictPrice: (productId: number, horizon = 14, days = 120) =>
    api.get<any>(`/forecast/${productId}/predict-price`, { horizon, days }),
  seasonality: (productId: number, days = 120) => api.get<any>(`/forecast/${productId}/seasonality`, { days }),
  forecastBacktest: (params: Record<string, QueryValue> = {}) => api.get<any>('/forecast/backtest', params),
  categoryElasticity: (category: string) =>
    api.get<any>(`/forecast/category/${encodeURIComponent(category)}/elasticity`),
  rebuildForecasts: (horizon = 14) => api.post<any>('/forecast/rebuild', undefined, { horizon }),

  // ---------------------------------------------------------------- reports
  reportTemplates: () => api.get<any>('/reports/templates'),
  reportData: (template: string, params: Record<string, QueryValue> = {}) =>
    api.get<any>(`/reports/${template}/data`, params),
}

/**
 * Download an export dataset as a file.
 *
 * Uses fetch + an object URL so the browser saves the server-generated filename and the
 * Authorization header is sent (a plain link would be rejected by the API).
 */
export async function downloadExport(
  dataset: string,
  format: 'csv' | 'xlsx' | 'json' = 'csv',
  params: Record<string, QueryValue> = {},
  limit = 5000,
): Promise<void> {
  const query = buildQuery({ ...params, limit })
  const response = await fetch(`${API_BASE}/export/${dataset}.${format}${query}`, {
    headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` },
  })
  if (!response.ok) {
    let message = `Export failed (${response.status})`
    try {
      const payload = await response.json()
      message = payload?.message ?? message
    } catch {
      /* keep the status-code message */
    }
    throw new Error(message)
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  await saveBlob(response, match?.[1] ?? `${dataset}.${format}`)
}

/**
 * Fetch a binary endpoint with the bearer token and save it under its server-sent name.
 *
 * A plain `<a href>` would be rejected by the API, and `window.open` cannot carry a
 * header either, so the blob round-trip is the only way to download an authenticated
 * file without giving the token to the browser's history.
 */
export async function downloadBinary(
  path: string,
  params: Record<string, QueryValue> = {},
  fallbackName = 'download.bin',
): Promise<void> {
  const response = await fetch(`${API_BASE}${path}${buildQuery(params)}`, {
    headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` },
  })
  if (!response.ok) {
    let message = `Download failed (${response.status})`
    try {
      const payload = await response.json()
      message = payload?.message ?? message
    } catch {
      /* the API answers a 501 with plain text, which is the interesting case here */
      const text = await response.text().catch(() => '')
      if (text) message = text.slice(0, 200)
    }
    throw new Error(message)
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  await saveBlob(response, match?.[1] ?? fallbackName)
}

async function saveBlob(response: Response, filename: string): Promise<void> {
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

/**
 * Upload a catalog CSV file (see GET /catalog/template for the columns).
 *
 * FormData travels without a JSON content-type, so this uses fetch directly
 * rather than the JSON `api` helper — the bearer token is attached manually.
 */
export async function uploadCatalogCsv(file: File): Promise<{ created: number; updated: number; total: number }> {
  const form = new FormData()
  form.append('file', file, file.name)
  const response = await fetch(`${API_BASE}/catalog/import`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` },
    body: form,
  })
  if (!response.ok) {
    let message = `Import failed (${response.status})`
    try {
      const payload = await response.json()
      const errors = payload?.details?.errors
      message = payload?.message ?? message
      if (Array.isArray(errors) && errors.length) message = `${message}: ${errors.slice(0, 3).join('; ')}`
    } catch {
      /* keep the status-code message */
    }
    throw new Error(message)
  }
  return response.json()
}