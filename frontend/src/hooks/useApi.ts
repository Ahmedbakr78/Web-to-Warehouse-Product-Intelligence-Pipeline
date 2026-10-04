/** Reusable TanStack Query hooks with app-wide defaults (silent background refresh). */

import { useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { endpoints } from '@/lib/api'

/** Product pages should feel instant: stale data is shown while revalidating. */
export const DEFAULT_OPTIONS = {
  staleTime: 30_000,
  gcTime: 5 * 60_000,
  refetchOnWindowFocus: false,
  refetchOnReconnect: true,
  retry: 1,
  placeholderData: (previous: unknown) => previous,
} as const

export function useApiQuery<T>(
  key: unknown[],
  fetcher: () => Promise<T>,
  options?: Partial<UseQueryOptions<T, Error, T, unknown[]>>,
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
