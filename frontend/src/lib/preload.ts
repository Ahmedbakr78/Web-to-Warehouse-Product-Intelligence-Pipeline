/**
 * Idle-time screen preloading.
 *
 * Routes are code-split so the first paint stays small. Without preloading, the
 * first visit to a screen has to fetch its chunk and shows the Suspense fallback
 * for a moment - which reads as a flicker. After the shell is mounted we warm the
 * chunks one at a time while the browser is idle, so every later navigation is
 * instant and silent. Failures are ignored on purpose: a missing chunk should
 * never break the app that is already running.
 *
 * The chain of idle callbacks is *cancellable*. The shell cancels it on
 * unmount, so a page that is torn down does not leave a timer behind that
 * fires afterwards - which is how a stray `window is not defined` ends up in
 * a test report long after the test that caused it has finished.
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

/** The pending idle/timeout callback, so it can be cancelled. */
let pending: { kind: 'idle' | 'timeout'; id: number } | null = null
let started = false

/**
 * Warm every route chunk, one at a time, while the browser is idle.
 *
 * Returns a function that stops the chain. Calling it cancels the pending
 * callback; calling it twice is harmless.
 */
export function preloadScreens(): () => void {
  const stop = () => {
    if (!pending) return
    if (pending.kind === 'idle' && typeof window !== 'undefined') {
      window.cancelIdleCallback?.(pending.id)
    } else if (pending.kind === 'timeout' && typeof window !== 'undefined') {
      window.clearTimeout(pending.id)
    }
    pending = null
  }

  if (started || typeof window === 'undefined') return stop
  started = true

  const schedule = (callback: () => void) => {
    // The environment can disappear between two chunks - a torn-down test
    // page, a closed tab. Nothing is left to preload into, so stop here rather
    // than schedule work that will throw.
    if (typeof window === 'undefined') return
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(callback, { timeout: 2500 })
      pending = { kind: 'idle', id }
    } else {
      const id = window.setTimeout(callback, 600)
      pending = { kind: 'timeout', id }
    }
  }

  let index = 0
  const warmNext = () => {
    pending = null
    if (typeof window === 'undefined') return
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

  return stop
}

/** Reset the one-shot guard. Used by the tests between cases. */
export function resetPreloadForTests(): void {
  started = false
  pending = null
}
