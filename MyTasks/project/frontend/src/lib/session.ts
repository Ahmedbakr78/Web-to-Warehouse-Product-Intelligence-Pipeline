/** Lightweight local preferences (table state, layout) persisted per browser. */

const PREFIX = 'pip.'

export const localStore = {
  get<T>(key: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(PREFIX + key)
      return raw ? (JSON.parse(raw) as T) : fallback
    } catch {
      return fallback
    }
  },
  set(key: string, value: unknown) {
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(value))
    } catch {
      /* quota or private mode - ignore */
    }
  },
  remove(key: string) {
    localStorage.removeItem(PREFIX + key)
  },
}

export interface ColumnPreference {
  key: string
  visible: boolean
}
