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

beforeEach(() => {
  stubMatchMedia(false)
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})