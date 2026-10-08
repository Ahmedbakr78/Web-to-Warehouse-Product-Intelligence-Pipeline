/**
 * Regression test for the appearance store.
 *
 * `useAppearance` is backed by `useSyncExternalStore`, which compares successive
 * snapshots with `Object.is`. The snapshot used to be a fresh object literal on every
 * call, so every render looked like a store change and React re-rendered forever —
 * React error #185, "maximum update depth exceeded", which took down the dashboard.
 *
 * The invariant is `Object.is(a, b)`: no store change means the *same* object back.
 */

import { beforeEach, describe, expect, it } from 'vitest'

describe('appearance store snapshot stability', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
    document.documentElement.removeAttribute('data-direction')
  })

  it('returns the identical object when nothing has changed', async () => {
    const { initAppearance, __snapshotForTest } = await import('@/lib/theme')
    initAppearance()

    const first = __snapshotForTest()
    const second = __snapshotForTest()
    const third = __snapshotForTest()

    // Reference equality is the whole point: `Object.is(first, second)` is what
    // `useSyncExternalStore` checks before deciding to re-render.
    expect(Object.is(first, second)).toBe(true)
    expect(Object.is(second, third)).toBe(true)
  })

  it('returns a new object only after a real change', async () => {
    const { initAppearance, setTheme, __snapshotForTest } = await import('@/lib/theme')
    initAppearance()

    const before = __snapshotForTest()
    setTheme('dark')
    const after = __snapshotForTest()

    expect(Object.is(before, after)).toBe(false)
    expect(after.theme).toBe('dark')
    // And it stabilises again immediately afterwards.
    expect(Object.is(after, __snapshotForTest())).toBe(true)
  })

  it('does not invalidate the snapshot for a no-op set', async () => {
    const { initAppearance, setTheme, __snapshotForTest } = await import('@/lib/theme')
    initAppearance()
    setTheme('dark')

    const before = __snapshotForTest()
    setTheme('dark') // same value again
    const after = __snapshotForTest()

    expect(Object.is(before, after)).toBe(true)
  })

  it('reflects every appearance axis', async () => {
    const { initAppearance, setTheme, setDensity, setAccent, setMotion, setDirection, setFontScale, setScrollbars, __snapshotForTest } =
      await import('@/lib/theme')
    initAppearance()

    setTheme('midnight')
    setDensity('compact')
    setAccent('emerald')
    setMotion('none')
    setDirection('rtl')
    setFontScale('lg')
    setScrollbars('auto')

    const snapshot = __snapshotForTest()
    expect(snapshot.theme).toBe('midnight')
    expect(snapshot.density).toBe('compact')
    expect(snapshot.accent).toBe('emerald')
    expect(snapshot.motion).toBe('none')
    expect(snapshot.direction).toBe('rtl')
    expect(snapshot.fontScale).toBe('lg')
    expect(snapshot.scrollbars).toBe('auto')
    expect(document.documentElement.dataset.scrollbars).toBe('auto')
  })

  it('defaults scrollbars to modern and persists the choice', async () => {
    const { initAppearance, setScrollbars, getStoredScrollbars, __snapshotForTest } = await import('@/lib/theme')
    initAppearance()

    expect(getStoredScrollbars()).toBe('modern')
    expect(__snapshotForTest().scrollbars).toBe('modern')

    const before = __snapshotForTest()
    setScrollbars('hidden')
    expect(getStoredScrollbars()).toBe('hidden')
    expect(document.documentElement.dataset.scrollbars).toBe('hidden')
    expect(Object.is(before, __snapshotForTest())).toBe(false)

    // A no-op set keeps the snapshot reference stable.
    const stable = __snapshotForTest()
    setScrollbars('hidden')
    expect(Object.is(stable, __snapshotForTest())).toBe(true)
  })
})