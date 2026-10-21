/**
 * jsdom does not implement `matchMedia`, which the appearance module uses to resolve
 * `system` against the OS preference. A minimal stub is enough: the theme code only
 * ever reads `.matches` and subscribes to changes.
 */

import { afterEach, beforeEach, vi } from 'vitest'

function stubMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  })
}

/**
 * jsdom implements neither `ResizeObserver` nor `matchMedia`'s media queries, and the
 * chart library observes its container. A no-op observer is enough for a render test.
 */
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

/**
 * A permanent network block.
 *
 * A test file stubs `fetch` in its own `beforeEach` and removes the stub in
 * `afterEach`. Anything that fires *after* that - a debounced search, a polling
 * refetch, a reconnect timer - would then reach the real network, and a rejected
 * request surfaces as an unhandled error with no failing test to explain it.
 *
 * This assignment is deliberately direct rather than `vi.stubGlobal`: a file's
 * `vi.unstubAllGlobals()` restores whatever was in place when *it* stubbed, which
 * is this block, not the network. The block answers every request with an empty
 * JSON payload, so a late callback can never leave the process.
 */
const NETWORK_BLOCK = () =>
  Promise.resolve(
    new Response(JSON.stringify({ items: [], total: 0 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )

globalThis.fetch = NETWORK_BLOCK as unknown as typeof fetch

/**
 * jsdom has no `EventSource`. The realtime hook opens one on mount, so without
 * this the constructor throws and takes the surrounding render down.
 */
class NoopEventSource {
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  readonly url = ''
  readonly readyState = 0
  constructor(_url: string) {}
  addEventListener() {}
  removeEventListener() {}
  close() {}
  dispatchEvent(): boolean {
    return true
  }
}

if (!('EventSource' in globalThis)) {
  Object.defineProperty(globalThis, 'EventSource', {
    writable: true,
    configurable: true,
    value: NoopEventSource,
  })
}

beforeEach(() => {
  stubMatchMedia(false)
  if (!('ResizeObserver' in globalThis)) {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver)
  }
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})