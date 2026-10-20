import { useAuth } from '@/hooks/useAuth'

/** Server-synced default used by paginated table screens. */
export function useDefaultPageSize(fallback = 25): number {
  const { user } = useAuth()
  return user?.rows_per_page ?? fallback
}
