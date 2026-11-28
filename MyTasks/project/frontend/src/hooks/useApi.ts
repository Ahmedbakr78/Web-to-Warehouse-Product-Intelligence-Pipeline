/** Reusable TanStack Query hooks with app-wide defaults (silent background refresh). */

import { useQuery, useQueryClient, type QueryKey, type UseQueryOptions } from '@tanstack/react-query'
import { endpoints } from '@/lib/api'

/** Product pages should feel instant: stale data is shown while revalidating. */
export const DEFAULT_OPTIONS = {
  staleTime: 30_000,
  gcTime: 5 * 60_000,
  refetchOnWindowFocus: false,
  refetchOnReconnect: true,
  // A 401 is final: the token layer already refreshed-and-retried once, so a
  // second attempt would only double the `401 (Unauthorized)` console lines
  // that background pollers emit when a session lapses.
  retry: (count: number, error: unknown) =>
    (error as { status?: number } | undefined)?.status === 401 ? false : count < 1,
  placeholderData: (previous: unknown): any => previous,
} as const

export function useApiQuery<T>(
  key: QueryKey,
  fetcher: () => Promise<T>,
  options?: Partial<UseQueryOptions<T, Error, T, QueryKey>>,
) {
  return useQuery<T, Error>({ queryKey: key, queryFn: fetcher, ...DEFAULT_OPTIONS, ...options })
}

export function useInvalidate() {
  const client = useQueryClient()
  return (keys: unknown[][]) => keys.forEach((key) => void client.invalidateQueries({ queryKey: key }))
}

export const queryKeys = {
  kpi: (days: number) => ['kpi', days],
  trend: (days: number) => ['trend', days],
  products: (params: Record<string, unknown>) => ['products', params],
  product: (id: number) => ['product', id],
  facets: () => ['facets'],
  categories: () => ['categories'],
  changes: (params: Record<string, unknown>) => ['price-changes', params],
  events: (params: Record<string, unknown>) => ['events', params],
  runs: (params: Record<string, unknown>) => ['runs', params],
  run: (id: string) => ['run', id],
  quality: () => ['quality-latest'],
  qualityResults: (params: Record<string, unknown>) => ['quality-results', params],
  sources: () => ['sources'],
  catalog: (params: Record<string, unknown>) => ['catalog-reconciliation', params],
  alerts: () => ['alerts'],
  notifications: () => ['notifications'],
  settings: () => ['settings'],
  savedViews: () => ['saved-views'],
}

export { endpoints }
