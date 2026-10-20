/**
 * Idle-time screen preloading.
 *
 * Routes are code-split so the first paint stays small. Without preloading, the
 * first visit to a screen has to fetch its chunk and shows the Suspense fallback
 * for a moment - which reads as a flicker. After the shell is mounted we warm the
 * chunks one at a time while the browser is idle, so every later navigation is
 * instant and silent. Failures are ignored on purpose: a missing chunk should
 * never break the app that is already running.
 */

const SCREEN_LOADERS: Array<() => Promise<unknown>> = [
  () => import('@/pages/Dashboard'),
  () => import('@/pages/Briefing'),
  () => import('@/pages/Analytics'),
  () => import('@/pages/Changes'),
  () => import('@/pages/Products'),
  () => import('@/pages/ProductDetail'),
  () => import('@/pages/Categories'),
  () => import('@/pages/Catalog'),
  () => import('@/pages/Pipeline'),
  () => import('@/pages/Quality'),
  () => import('@/pages/Sources'),
  () => import('@/pages/Forecast'),
  () => import('@/pages/Reports'),
  () => import('@/pages/QueryLab'),
  () => import('@/pages/Builder'),
  () => import('@/pages/Features'),
  () => import('@/pages/Alerts'),
  () => import('@/pages/Webhooks'),
  () => import('@/pages/Account'),
  () => import('@/pages/Settings'),
  () => import('@/pages/Users'),
  () => import('@/pages/Audit'),
]

let started = false

export function preloadScreens(): void {
  if (started || typeof window === 'undefined') return
  started = true

  const schedule: (callback: () => void) => void =
    'requestIdleCallback' in window
      ? (callback) => window.requestIdleCallback(callback, { timeout: 2500 })
      : (callback) => window.setTimeout(callback, 600)

  let index = 0
  const warmNext = () => {
    const loader = SCREEN_LOADERS[index]
    index += 1
    if (!loader) return
    loader()
      .catch(() => undefined)
      .finally(() => {
        if (index < SCREEN_LOADERS.length) schedule(warmNext)
      })
  }
  schedule(warmNext)
}
