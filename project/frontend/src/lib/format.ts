/** Formatting helpers shared by every screen (one source of truth for display rules). */

const currencySymbols: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CNY: '¥',
  INR: '₹',
  AUD: 'A$',
  CAD: 'C$',
  TRY: '₺',
  RUB: '₽',
  BRL: 'R$',
  PLN: 'zł',
  SEK: 'kr',
  CHF: 'CHF',
  EGP: 'E£',
  AED: 'AED',
  SAR: 'SAR',
}

export function formatPrice(value: number | string | null | undefined, currency = 'USD'): string {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(numeric)) return String(value)
  const symbol = currencySymbols[currency?.toUpperCase()] ?? `${currency?.toUpperCase() ?? ''} `
  const abs = Math.abs(numeric)
  if (abs >= 1000) return `${symbol}${numeric.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
  if (Number.isInteger(numeric)) return `${symbol}${numeric.toLocaleString()}`
  return `${symbol}${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatNumber(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return '—'
  const abs = Math.abs(numeric)
  if (abs >= 1_000_000_000) return `${(numeric / 1_000_000_000).toFixed(1)}B`
  if (abs >= 1_000_000) return `${(numeric / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `${(numeric / 1000).toFixed(1)}k`
  return formatNumber(numeric)
}

export function formatPercent(value: number | string | null | undefined, digits = 2, withSign = true): string {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(numeric)) return String(value)
  const sign = withSign && numeric > 0 ? '+' : ''
  return `${sign}${numeric.toFixed(digits)}%`
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return '—'
  const diffMs = Date.now() - date.getTime()
  const seconds = Math.round(diffMs / 1000)
  const future = diffMs < 0
  const abs = Math.abs(seconds)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (abs < 45) return future ? 'in a moment' : 'just now'
  if (abs < 90) return rtf.format(future ? seconds : -seconds, 'second')
  if (abs < 3600) return rtf.format(Math.round(seconds / 60) * (future ? 1 : -1), 'minute')
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600) * (future ? 1 : -1), 'hour')
  if (abs < 2592000) return rtf.format(Math.round(seconds / 86400) * (future ? 1 : -1), 'day')
  if (abs < 31536000) return rtf.format(Math.round(seconds / 2592000) * (future ? 1 : -1), 'month')
  return rtf.format(Math.round(seconds / 31536000) * (future ? 1 : -1), 'year')
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${Math.round(seconds % 60)}s`
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

export type AvailabilityTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

export function formatAvailability(value: string | null | undefined): { label: string; tone: AvailabilityTone } {
  switch ((value ?? '').toLowerCase()) {
    case 'in_stock':
      return { label: 'In stock', tone: 'success' }
    case 'limited_stock':
      return { label: 'Low stock', tone: 'warning' }
    case 'preorder':
      return { label: 'Pre-order', tone: 'info' }
    case 'out_of_stock':
      return { label: 'Out of stock', tone: 'danger' }
    default:
      return { label: 'Unknown', tone: 'neutral' }
  }
}

export function statusTone(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  switch ((status ?? '').toLowerCase()) {
    case 'success':
    case 'passed':
    case 'pass':
    case 'active':
    case 'matched':
    case 'healthy':
      return 'success'
    case 'partial':
    case 'warn':
    case 'warning':
    case 'degraded':
      return 'warning'
    case 'failed':
    case 'fail':
    case 'error':
    case 'critical':
    case 'discontinued':
      return 'danger'
    case 'running':
    case 'pending':
    case 'queued':
      return 'info'
    default:
      return 'neutral'
  }
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return ''
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .trim()
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export function truncate(value: string | null | undefined, length = 60): string {
  if (!value) return '—'
  return value.length > length ? `${value.slice(0, length - 1)}…` : value
}

export function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/** Escape a single CSV cell (quotes, commas, newlines). */
export function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  return `"${text.replace(/"/g, '""')}"`
}

/** Build an RFC-4180 compliant CSV from tabular rows. */
export function toCsv(header: string[], rows: Array<Array<unknown>>): string {
  const lines = [header.map(csvCell).join(',')]
  for (const row of rows) lines.push(row.map(csvCell).join(','))
  return lines.join('\n')
}