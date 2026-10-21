/**
 * Normalising API payloads.
 *
 * The API returns two shapes for a list: a bare JSON array for the endpoints
 * that have no pagination, and a `{ items, total }` envelope for the ones that
 * do. A screen that consumes both has to cope with both - and, more
 * importantly, a screen must not white-screen because a proxy, a version skew
 * or an error envelope changed the shape.
 *
 * `toArray` is the single place that decides what a list is.
 */

/** The paginated envelope the API returns for paged collections. */
type Paged<T> = { items?: T[]; total?: number }

/**
 * Read a list out of a payload, whatever shape it arrived in.
 *
 * - an array is returned as it is;
 * - a `{ items: [...] }` envelope is unwrapped;
 * - anything else (null, undefined, an error object) becomes an empty list.
 */
export function toArray<T = any>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object') {
    const items = (payload as Paged<T>).items
    if (Array.isArray(items)) return items
  }
  return []
}

/**
 * Read a list out of a payload, or a fallback when the payload carries none.
 */
export function toArrayOr<T = any>(payload: unknown, fallback: T[]): T[] {
  const list = toArray<T>(payload)
  return list.length ? list : fallback
}

/**
 * Read a single object out of a payload, or `null`.
 *
 * Some endpoints answer with a bare object and some with an envelope around
 * one; this reads both without the caller having to know which.
 */
export function toObject<T = any>(payload: unknown): T | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  return payload as T
}

export default toArray
