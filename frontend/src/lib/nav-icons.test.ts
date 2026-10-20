/**
 * Icon registry parity.
 *
 * The feature catalogue is served by the API, which references icons by name.
 * When the API emits a name the frontend registry does not know, the glyph
 * silently falls back to the checklist icon - a blank square on the screen that
 * nobody notices until the presentation. This test reads the backend catalogue
 * straight from disk and asserts every name resolves to a real icon.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { ICONS, iconFor } from '@/lib/nav-icons'

const FEATURES_SOURCE = resolve(__dirname, '../../../app/core/features.py')

function backendIconNames(): string[] {
  const source = readFileSync(FEATURES_SOURCE, 'utf8')
  const names = new Set<string>()
  for (const match of source.matchAll(/"icon"\s*:\s*"([a-z0-9-]+)"/g)) {
    names.add(match[1])
  }
  return [...names].sort()
}

describe('icon registry', () => {
  it('resolves every icon name emitted by the backend feature catalogue', () => {
    const missing = backendIconNames().filter((name) => !(name in ICONS))
    expect(missing).toEqual([])
  })

  it('never returns a blank glyph for a known name', () => {
    const names = backendIconNames()
    expect(names.length).toBeGreaterThan(20)
    for (const name of names) {
      // Lucide components are forwardRef objects; the fallback is a different
      // component, so identity against the checklist glyph is the real check.
      expect(iconFor(name)).not.toBe(ICONS.checklist)
    }
  })

  it('falls back to the checklist glyph for an unknown name', () => {
    expect(iconFor('definitely-not-a-real-icon')).toBe(ICONS.checklist)
  })
})
