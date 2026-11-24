/** Recently visited screens, persisted locally and surfaced in the command palette. */

import { useCallback, useEffect, useState } from 'react'

export type RecentPage = { to: string; label: string }

const KEY = 'pip.recent-pages'
const LIMIT = 6

function read(): RecentPage[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? '[]') as unknown
    if (!Array.isArray(value)) return []
    return value
      .filter(
        (item): item is RecentPage =>
          Boolean(item) && typeof item === 'object' && typeof (item as RecentPage).to === 'string' && typeof (item as RecentPage).label === 'string',
      )
      .slice(0, LIMIT)
  } catch {
    return []
  }
}

export function useRecentPages() {
  const [recent, setRecent] = useState<RecentPage[]>(read)

  const record = useCallback((to: string, label: string) => {
    if (!to || to === '/login' || to.startsWith('/products/')) return
    setRecent((current) => {
      const next = [{ to, label }, ...current.filter((item) => item.to !== to)].slice(0, LIMIT)
      try {
        localStorage.setItem(KEY, JSON.stringify(next))
      } catch {
        // A full or disabled storage must never break navigation.
      }
      return next
    })
  }, [])

  const clear = useCallback(() => {
    try {
      localStorage.removeItem(KEY)
    } catch {
      // Ignore storage failures.
    }
    setRecent([])
  }, [])

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === KEY) setRecent(read())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  return { recent, record, clear }
}
