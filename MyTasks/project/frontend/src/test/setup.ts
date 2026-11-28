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