/**
 * The appearance store must not put React into a re-render loop.
 *
 * React error #185 is "maximum update depth exceeded", and it took down every screen
 * because `AppShell` calls `useTheme`. The cause was `useAppearance` returning a
 * fresh snapshot object on every call: `useSyncExternalStore` compares snapshots with
 * `Object.is`, so each render looked like a store change and React re-rendered
 * forever.
 *
 * This renders a real component rather than inspecting the snapshot function, because
 * the symptom is a render loop and only a render can demonstrate it.
 */

import { StrictMode, useState } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useAppearance, useTheme } from '@/lib/theme'

let renders = 0

function ThemeConsumer() {
  renders += 1
  const { mode, isDark, toggle } = useTheme()
  const [count, setCount] = useState(0)

  if (count === 0) setCount(1) // a deliberate state update, to prove renders converge

  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="dark">{String(isDark)}</span>
      <span data-testid="renders">{renders}</span>
      <button type="button" onClick={toggle}>
        toggle
      </button>
    </div>
  )
}

describe('appearance store integration', () => {
  it('renders a bounded number of times instead of looping', async () => {
    renders = 0
    render(
      <StrictMode>
        <ThemeConsumer />
      </StrictMode>,
    )

    // StrictMode double-invokes in development, so allow a small multiple. The point
    // is that this number is finite and small, not that it is exactly one.
    expect(renders).toBeGreaterThan(0)
    expect(renders).toBeLessThan(10)

    await screen.findByTestId('mode')
    expect(screen.getByTestId('mode').textContent).toBeTruthy()
  })

})

describe('useAppearance', () => {
  it('is exported for the store consumers', () => {
    expect(useAppearance).toBeTypeOf('function')
  })
})

describe('useAppearance', () => {
  it('is the store hook the shell depends on', () => {
    expect(useAppearance).toBeTypeOf('function')
  })
})
