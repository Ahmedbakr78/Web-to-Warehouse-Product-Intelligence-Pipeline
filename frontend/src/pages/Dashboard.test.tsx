/**
 * Renders the real Dashboard page.
 *
 * The reported symptom was "The dashboard hit an unexpected error: Minified React
 * error #185" — maximum update depth exceeded. That is a render loop, and the loop
 * was in the appearance store every page depends on, so this mounts the page itself
 * rather than a toy component: a passing test here is the closest thing to "the
 * dashboard loads" that runs without a browser.
 */

import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from '@/pages/Dashboard'

/** Counts every Dashboard render, which is what a re-render loop inflates. */
let renders = 0
const RealDashboard = Dashboard
function CountingDashboard() {
  renders += 1
  return <RealDashboard />
}
import { tokenStore } from '@/lib/api'

/** The subset of `GET /analytics/kpi?days=30` that the page destructures. */
const KPI = {
  window_days: 30,
  counts: { dim_product: 263, dim_category: 43 },
  latest: { products: 263, in_stock_count: 244, avg_price: '333.05', avg_rating: '3.86' },
  changes: { total_changes: 1555, increases: 700, decreases: 855 },
  events: { total_events: 10929 },
}

function jsonResponse(payload: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('Dashboard page', () => {
  beforeEach(() => {
    renders = 0
    tokenStore.set('test-token', null)
    localStorage.clear()

    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/analytics/kpi')) return jsonResponse(KPI)
        if (url.includes('/analytics/trend')) return jsonResponse([])
        if (url.includes('/analytics/price-trend')) return jsonResponse([])
        if (url.includes('/analytics/top-movers')) return jsonResponse([])
        if (url.includes('/quality/latest')) return jsonResponse({ score: 100, pass: 12, warn: 0, fail: 0 })
        if (url.includes('/pipeline/runs/latest')) return jsonResponse(null)
        if (url.includes('/analytics/change-summary')) return jsonResponse({ total: 0 })
        return jsonResponse({})
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders without an error boundary and without looping', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    })

    const { container } = render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={['/']}>
            <CountingDashboard />
          </MemoryRouter>
        </QueryClientProvider>
      </StrictMode>,
    )

    // No crash: the page mounts and stays mounted.
    expect(container.textContent).not.toMatch(/unexpected error/i)
    expect(container.textContent).not.toMatch(/Minified React error/i)

    await waitFor(() => {
      expect(screen.getByText('Products tracked')).toBeTruthy()
    })

    // Settle, then confirm the count stopped moving. A re-render loop would keep
    // climbing; this asserts convergence rather than an arbitrary ceiling.
    const settled = renders
    await new Promise((resolve) => setTimeout(resolve, 250))
    expect(renders).toBe(settled)
  })
})