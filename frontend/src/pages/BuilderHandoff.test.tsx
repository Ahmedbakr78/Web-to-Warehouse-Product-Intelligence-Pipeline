/**
 * Builder to query-lab hand-off.
 *
 * The Builder can turn its current filters, sort and page size into a SQL
 * statement. That statement is handed to the Query Lab through the URL, which
 * means two things have to hold:
 *
 *   1. the Builder offers the hand-off and produces a statement, and
 *   2. the Query Lab reads the statement from the URL exactly once.
 *
 * The second point is the subtle one. If the parameter were read on every
 * render, a reload would re-apply the statement over whatever the user had
 * edited in the meantime - so the parameter is consumed and dropped.
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import Builder from '@/pages/Builder'
import QueryLab from '@/pages/QueryLab'

import { tokenStore } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    API_BASE: 'http://localhost:8000/api/v1',
    api: {
      get: vi.fn(async () => []),
      post: vi.fn(async () => ({})),
      patch: vi.fn(async () => ({})),
      del: vi.fn(async () => ({})),
    },
  }
})

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Records the current location so the navigation can be asserted. */
function LocationProbe({ onChange }: { onChange: (path: string, search: string) => void }) {
  const location = useLocation()
  onChange(location.pathname, location.search)
  return null
}

describe('builder to query lab hand-off', () => {
  it('offers the hand-off on the builder', async () => {
    tokenStore.set('test-token')
    renderWithClient(<Builder />)
    await waitFor(() => expect(screen.getByRole('button', { name: /run in query lab/i })).toBeTruthy())
  })

  it('navigates to the query lab with the generated statement', async () => {
    tokenStore.set('test-token')
    const seen: { path: string; search: string }[] = []
    renderWithClient(
      <>
        <LocationProbe
          onChange={(path, search) => {
            seen.push({ path, search })
          }}
        />
        <Builder />
      </>,
    )
    const button = await screen.findByRole('button', { name: /run in query lab/i })
    await act(async () => {
      button.click()
    })
    await waitFor(() => {
      const last = seen[seen.length - 1]
      expect(last?.path).toBe('/query')
      expect(decodeURIComponent(last?.search ?? '')).toContain('sql=')
      expect(decodeURIComponent(last?.search ?? '')).toContain('SELECT')
    })
  })

  it('takes the statement from the URL once and then drops the parameter', async () => {
    tokenStore.set('test-token')
    const statement = 'SELECT canonical_name FROM dim_product LIMIT 5;'
    const seen: { path: string; search: string }[] = []
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/query?sql=${encodeURIComponent(statement)}`]}>
          <LocationProbe
            onChange={(path, search) => {
              seen.push({ path, search })
            }}
          />
          <Routes>
            <Route path="/query" element={<QueryLab />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // The statement lands in the editor...
    await waitFor(() => {
      const editor = screen.getByLabelText('SQL statement') as HTMLTextAreaElement
      expect(editor.value).toBe(statement)
    })
    // ...and the parameter is consumed, so a reload cannot re-apply it.
    await waitFor(() => {
      const last = seen[seen.length - 1]
      expect(last?.path).toBe('/query')
      expect(last?.search).not.toContain('sql=')
    })
  })
})
