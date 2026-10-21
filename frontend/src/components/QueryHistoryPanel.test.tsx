/**
 * Regression test: a list endpoint that answers with a non-list.
 *
 * `QueryHistoryPanel` read `history.data ?? []` and then called `.some` on it.
 * `??` only covers null and undefined, so a paginated envelope
 * (`{items: [...]}`) or a non-JSON body reached `.some` and threw *during
 * render* - which blanks the whole screen rather than one panel.
 *
 * The panel has to be given time to resolve the query: asserting while the
 * request is still in flight would pass with or without the guard.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import QueryHistoryPanel from '@/components/QueryHistoryPanel'
import { endpoints, tokenStore } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    // The endpoint under test is mocked directly: `endpoints` closes over the
    // real `api` object, so mocking `api` alone would never be reached.
    endpoints: {
      ...actual.endpoints,
      queryHistory: vi.fn(async () => ({ items: [], total: 0 })),
    },
  }
})

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <QueryHistoryPanel onLoad={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('QueryHistoryPanel tolerates a non-list payload', () => {
  it('renders instead of throwing during render', async () => {
    tokenStore.set('test-token')
    const { container } = renderPanel()

    // Wait until the (non-list) payload has actually arrived and been rendered.
    await waitFor(() => {
      expect(endpoints.queryHistory).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(container.textContent).toContain('History')
    })

    // The panel rendered with the envelope instead of a list: no crash, and the
    // clear button is present rather than the component having thrown.
    expect(screen.getByRole('button', { name: /clear/i })).toBeTruthy()
  })
})
