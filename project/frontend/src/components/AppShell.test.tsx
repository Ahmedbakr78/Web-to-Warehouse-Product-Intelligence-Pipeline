/**
 * Application shell behaviour.
 *
 * Two controls users asked for explicitly: a collapse switch in the header (not just
 * the sidebar footer) that persists the rail choice, and a shortcut reference
 * dialog on "?". Both are easy to break silently - a dead button still renders -
 * so this pins the behaviour: clicking toggles the persisted state, and "?"
 * opens a dialog listing the real shortcuts.
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it } from 'vitest'

import AppShell from '@/components/AppShell'

const DESKTOP = 1440

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
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }
    },
  })
}

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  setViewport(DESKTOP)
})

describe('app shell header', () => {
  it('toggles and persists the sidebar rail from the header', () => {
    renderShell()

    // The header carries its own collapse switch (with the "[" hint) next to
    // the long-standing one in the sidebar footer.
    const collapse = screen.getByRole('button', { name: 'Collapse sidebar ( ] )' })
    fireEvent.click(collapse)

    expect(localStorage.getItem('pip.sidebar')).toBe('collapsed')
    expect(screen.getByRole('button', { name: 'Expand sidebar ( [ )' })).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar ( [ )' }))
    expect(localStorage.getItem('pip.sidebar')).toBe('expanded')
  })

  it('opens the shortcut reference on "?" and closes it on Escape', () => {
    renderShell()
    expect(screen.queryByText('Keyboard shortcuts')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /keyboard shortcuts/i }))
    expect(screen.getByText('Keyboard shortcuts')).not.toBeNull()
    // The dialog lists the actual bindings, not placeholder text.
    expect(screen.getByText(/command palette/i)).not.toBeNull()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('Keyboard shortcuts')).toBeNull()
  })
})
