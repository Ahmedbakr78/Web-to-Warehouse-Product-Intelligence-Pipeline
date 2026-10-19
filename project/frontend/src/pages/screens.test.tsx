/**
 * Render smoke test for every screen.
 *
 * This exists because of a real incident: the appearance store returned a new
 * snapshot object on each call, `useSyncExternalStore` saw a change every render, and
 * React threw error #185 — "maximum update depth exceeded" — on every route. Static
 * checks, TypeScript, ESLint and the production build all passed while the entire
 * application was unusable.
 *
 * Each page is mounted with stubbed API responses and an error boundary that records
 * the failure. A page that throws during render, or spins without settling, fails
 * here rather than in front of a user.
 */

import { Component, type ErrorInfo, type ReactElement, type ReactNode } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Account from '@/pages/Account'
import AggregateBuilder from '@/pages/AggregateBuilder'
import Alerts from '@/pages/Alerts'
import Analytics from '@/pages/Analytics'
import Audit from '@/pages/Audit'
import Builder from '@/pages/Builder'
import Catalog from '@/pages/Catalog'
import Categories from '@/pages/Categories'
import Changes from '@/pages/Changes'
import Dashboard from '@/pages/Dashboard'
import Features from '@/pages/Features'
import Forecast from '@/pages/Forecast'
import NotFound from '@/pages/NotFound'
import Pipeline from '@/pages/Pipeline'
import ProductDetail from '@/pages/ProductDetail'
import Products from '@/pages/Products'
import Quality from '@/pages/Quality'
import QueryLab from '@/pages/QueryLab'
import Reports from '@/pages/Reports'
import Settings from '@/pages/Settings'
import Sources from '@/pages/Sources'
import Users from '@/pages/Users'
import Webhooks from '@/pages/Webhooks'

import { tokenStore } from '@/lib/api'

/** Collects render failures instead of letting them reach the console. */
class Boundary extends Component<{ children: ReactNode; onError: (error: Error) => void }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, _info: ErrorInfo) {
    this.props.onError(error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

const PAGES: Array<[string, () => ReactElement]> = [
  ['Dashboard', () => <Dashboard />],
  ['Products', () => <Products />],
  ['Product detail', () => <ProductDetail />],
  ['Changes', () => <Changes />],
  ['Categories', () => <Categories />],
  ['Catalog', () => <Catalog />],
  ['Quality', () => <Quality />],
  ['Sources', () => <Sources />],
  ['Analytics', () => <Analytics />],
  ['Query lab', () => <QueryLab />],
  ['Builder', () => <Builder />],
  ['Aggregate builder', () => <AggregateBuilder />],
  ['Pipeline', () => <Pipeline />],
  ['Alerts', () => <Alerts />],
  ['Forecast', () => <Forecast />],
  ['Reports', () => <Reports />],
  ['Features', () => <Features />],
  ['Webhooks', () => <Webhooks />],
  ['Users', () => <Users />],
  ['Audit', () => <Audit />],
  ['Settings', () => <Settings />],
  ['Account', () => <Account />],
  ['Not found', () => <NotFound />],
]

/**
 * Responses shaped the way the real API shapes them.
 *
 * A uniform `{}` would be a strawman: it crashes pages that call `(data ?? []).map`,
 * which is not a real-world failure because the API always returns an array there.
 * What this test exists to catch is the *crash class* — a render loop, or a throw
 * during render — with well-formed data.
 */
const KPI = {
  window_days: 30,
  counts: { dim_product: 263, dim_category: 43 },
  latest: { products: 263, in_stock_count: 244, avg_price: '333.05', min_price: '0.79', max_price: '1404.52', avg_rating: '3.86' },
  changes: { total_changes: 1555, increases: 700, decreases: 855 },
  events: { total_events: 10929 },
}

function payloadFor(url: string): unknown {
  if (url.includes('/analytics/kpi')) return KPI
  if (url.includes('/quality/')) return { score: 100, pass: 12, warn: 0, fail: 0, total: 12, rules: [], results: [] }
  if (url.includes('/reports/')) return { templates: [], formats: ['html'], pdf_available: true, blocks: [], sections: [] }
  if (url.includes('/jobs')) return { items: [], total: 0, worker: {}, types: [], cancellable: [], sessions: [] }
  if (url.includes('/account/2fa')) return { enabled: false, recovery_codes_remaining: 8, attempts_remaining: 3 }
  if (url.includes('/account/sessions')) return { total: 0, active: 0, sessions: [] }
  if (url.includes('/users/me')) return { user_id: 1, email: 'a@example.com', full_name: 'Admin', role: 'admin', permissions: ['read', 'write', 'query', 'run_pipeline', 'manage_users'], theme: 'system', accent: 'indigo', density: 'comfortable', motion: 'full', direction: 'ltr', font_scale: 'md' }
  if (url.includes('/meta/features')) return { total_features: 0, total_groups: 0, groups: [] }
  if (url.includes('/builder/schema'))
    // Shapes copied from the live endpoint: `aggregates` is a list of function names,
    // `operators` a list of objects.
    return {
      entities: [],
      aggregates: ['count', 'count_distinct', 'sum', 'avg', 'min', 'max'],
      operators: [{ operator: 'eq', sql: '=', value_type: 'scalar' }],
      max_limit: 1000,
    }
  // Everything else is a list endpoint.
  return []
}

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      const body = JSON.stringify(payloadFor(url))
      return Promise.resolve(
        new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } }),
      )
    }),
  )
}

function freshClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
}

beforeEach(() => {
  localStorage.clear()
  tokenStore.set('smoke-token')
  stubApi()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('every screen renders', () => {
  it.each(PAGES)('%s mounts without throwing and settles', async (name, Page) => {
    const failures: Error[] = []
    const renders = { count: 0 }

    function Counting() {
      renders.count += 1
      return Page()
    }

    render(
      <Boundary onError={(error) => failures.push(error)}>
        <QueryClientProvider client={freshClient()}>
          <MemoryRouter initialEntries={['/']}>
            <Counting />
          </MemoryRouter>
        </QueryClientProvider>
      </Boundary>,
    )

    // Let effects, queries and any re-render loop run.
    await new Promise((resolve) => setTimeout(resolve, 120))
    const settled = renders.count
    await new Promise((resolve) => setTimeout(resolve, 120))

    if (failures.length) {
      throw new Error(
        `${name} threw during render: ${failures[0].message}\n${failures[0].stack?.split('\n').slice(1, 5).join('\n')}`,
      )
    }
    expect(failures.map((error) => `${name}: ${error.message}`)).toEqual([])
    // Convergence: a re-render loop keeps incrementing, a settled page does not.
    expect(renders.count).toBe(settled)
  })
})