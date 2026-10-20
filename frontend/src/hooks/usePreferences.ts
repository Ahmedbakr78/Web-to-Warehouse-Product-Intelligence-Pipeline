/**
 * Profile preferences.
 *
 * The account screen writes a set of preferences into the user profile. Every
 * one of them has to actually change the behaviour of the app - a control that
 * saves a value nobody reads is worse than no control at all. This module is
 * the single place that reads them back, so a preference can never be wired
 * to two different meanings.
 */

import { useEffect, useMemo } from 'react'

import { useAuth } from '@/hooks/useAuth'
import { setNumberFormat, type NumberFormat } from '@/lib/format'

export type ChartType = 'area' | 'line' | 'bar'
export type ExportFormat = 'csv' | 'xlsx' | 'json' | 'ndjson'

/** Auto-refresh intervals offered in the account screen. */
export const AUTO_REFRESH_OPTIONS: { id: string; label: string; ms: number }[] = [
  { id: 'off', label: 'Off', ms: 0 },
  { id: '15s', label: 'Every 15 seconds', ms: 15_000 },
  { id: '30s', label: 'Every 30 seconds', ms: 30_000 },
  { id: '1m', label: 'Every minute', ms: 60_000 },
  { id: '5m', label: 'Every 5 minutes', ms: 300_000 },
]

/** Read a nested preference value without losing type safety. */
function read<T>(source: unknown, key: string, fallback: T): T {
  if (!source || typeof source !== 'object') return fallback
  const value = (source as Record<string, unknown>)[key]
  return value === undefined || value === null ? fallback : (value as T)
}

export type ProfilePreferences = {
  /** "compact" abbreviates large counts, "full" always prints the exact figure. */
  numberFormat: NumberFormat
  /** Initial time window on the dashboard. */
  defaultRange: string
  /** Chart style used for the dashboard trend. */
  defaultChartType: ChartType
  /** Auto-refresh interval in milliseconds (0 disables it). */
  autoRefreshMs: number
  /** The export format highlighted as the default one. */
  defaultExportFormat: ExportFormat
  /** Copy code blocks to the clipboard on a single click. */
  copyCodeOnClick: boolean
  /** Reload data in place with no skeleton, spinner or transition. */
  silentReload: boolean
  /** The screen the app opens on. */
  startPage: string
}

export function useProfilePreferences(): ProfilePreferences {
  const { user } = useAuth()
  const prefs = user?.preferences ?? null
  const dashboard = read<Record<string, unknown>>(prefs, 'dashboard', {})

  const preferences = useMemo<ProfilePreferences>(() => {
    const autoRefresh = read<string>(prefs, 'auto_refresh', 'off')
    const known = AUTO_REFRESH_OPTIONS.find((option) => option.id === autoRefresh)
    return {
      numberFormat: read<NumberFormat>(prefs, 'number_format', 'compact'),
      defaultRange: read<string>(dashboard, 'default_range', '30d'),
      defaultChartType: read<ChartType>(dashboard, 'chart_type', 'area'),
      autoRefreshMs: known ? known.ms : 0,
      defaultExportFormat: read<ExportFormat>(prefs, 'default_export_format', 'csv'),
      copyCodeOnClick: Boolean(read<boolean>(prefs, 'copy_code_on_click', true)),
      silentReload: Boolean(read<boolean>(prefs, 'silent_reload', true)),
      startPage: read<string>(prefs, 'start_page', '/'),
    }
  }, [prefs])

  // The number format is a module-level switch (every screen formats through
  // the same helper), so it has to be pushed into the formatter whenever the
  // profile changes.
  useEffect(() => {
    setNumberFormat(preferences.numberFormat)
  }, [preferences.numberFormat])

  return preferences
}

/** Server-synced default used by paginated table screens. */
export function useDefaultPageSize(fallback = 25): number {
  const { user } = useAuth()
  return user?.rows_per_page ?? fallback
}
