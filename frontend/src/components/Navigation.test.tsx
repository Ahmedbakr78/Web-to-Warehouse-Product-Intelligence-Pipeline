/**
 * Responsive shell behaviour.
 *
 * Three things the user depends on daily and that are easy to break silently:
 * the sidebar becomes an off-canvas drawer on a phone and a rail on a desktop, the
 * drawer closes on Escape, and the layout re-measures when the viewport changes.
 *
 * jsdom has no layout engine, so width is set directly and asserted through the
 * hook and the rendered markup rather than through computed geometry.
 */

import { act, render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NavDrawer, Sidebar, usePhoneLayout } from '@/components/Navigation'
import { useRailState } from '@/components/Navigation'

import { tokenStore } from '@/lib/api'

const PHONE = 390
const DESKTOP = 1440

/** Fires a media-query change so `usePhoneLayout` re-evaluates. */
function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: width })
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => {
      const max = /max-width:\s*(\d+)px/.exec(query)
      const matches = max ? width <= Number(max[1]) : false
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: (_: string, handler: (event: MediaQueryListEvent) => void) => {
          listeners.push(handler)
        },
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }
    },
  })
}

/** Every media-query listener registered, so a resize can notify all of them. */
const listeners: Array<(event: MediaQueryListEvent) => void> = []

function Harness() {
  const phone = usePhoneLayout()
  const rail = useRailState()
  return (
    <div>
      <span data-testid="layout">{phone ? 'phone' : 'desktop'}</span>
      <Sidebar collapsed={rail.collapsed} onToggle={rail.toggleRail} />
      {phone ? (
        <>
          <button type="button" onClick={() => rail.setDrawerOpen(true)}>
            Open navigation
          </button>
          <NavDrawer open={rail.drawerOpen} onClose={rail.closeDrawer} />
        </>
      ) : null}
    </div>
  )
}

function renderHarness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Harness />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  tokenStore.set('nav-token')
  listeners.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('responsive shell', () => {
  it('reports a phone layout below the breakpoint', () => {
    setViewport(PHONE)
    renderHarness()
    expect(screen.getByTestId('layout').textContent).toBe('phone')
  })

  it('reports a desktop layout above it', () => {
    setViewport(DESKTOP)
    renderHarness()
    expect(screen.getByTestId('layout').textContent).toBe('desktop')
  })

  it('re-measures when the viewport changes', () => {
    setViewport(DESKTOP)
    renderHarness()
    expect(screen.getByTestId('layout').textContent).toBe('desktop')

    // Rotating the device, or resizing a desktop window down to a phone.
    act(() => {
      setViewport(PHONE)
      for (const handler of listeners) handler({ matches: true } as MediaQueryListEvent)
    })

    expect(screen.getByTestId('layout').textContent).toBe('phone')
  })

  it('closes the off-canvas drawer on Escape', () => {
    setViewport(PHONE)
    renderHarness()

    // Open it the way a user does, from the phone header's menu button.
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))

    const drawer = screen.queryByRole('dialog')
    expect(drawer).not.toBeNull()

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).toBeNull()
  })
})