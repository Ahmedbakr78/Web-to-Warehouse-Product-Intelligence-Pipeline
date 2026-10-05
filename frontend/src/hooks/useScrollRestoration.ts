/**
 * Scroll restoration and focus management.
 *
 * The dashboard must feel silent when you navigate: no smooth-scroll animation,
 * no jump to the top when you go "back", and keyboard focus moved to the new
 * screen's heading so a screen-reader or keyboard user lands in the right place.
 *
 * Back/forward restores the previous offset. Forward navigation starts at the top.
 */

import { useEffect, useRef } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

const OFFSETS = new Map<string, number>()
let lastPath: string | null = null

export function useScrollRestoration() {
  const location = useLocation()
  const navigationType = useNavigationType()
  const containerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const path = location.pathname
    const search = location.search
    const key = `${path}${search}`

    // Save where the previous screen was scrolled to before leaving it.
    if (lastPath !== null && lastPath !== key) {
      OFFSETS.set(lastPath, window.scrollY)
    }
    lastPath = key

    // Defer one frame so the new content has laid out before we measure.
    const frame = window.requestAnimationFrame(() => {
      const target = navigationType === 'POP' ? (OFFSETS.get(key) ?? 0) : 0

      // The shell scrolls <main>, not the document, when it overflows.
      const main = document.querySelector<HTMLElement>('main')
      if (main && main.scrollHeight > main.clientHeight) {
        main.scrollTop = target
      } else {
        window.scrollTo({ top: target, behavior: 'auto' })
      }
    })

    return () => window.cancelAnimationFrame(frame)
  }, [location.pathname, location.search, navigationType])

  return containerRef
}

/**
 * Move focus to the page heading after a route change. The heading is given a
 * `tabIndex={-1}` in AppShell so it can receive programmatic focus.
 */
export function useFocusHeading() {
  const location = useLocation()

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const heading = document.querySelector<HTMLElement>('[data-page-heading]')
      if (heading && document.activeElement !== heading) heading.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [location.pathname])
}

/** Forget every stored offset (used when the user changes account). */
export function clearScrollOffsets() {
  OFFSETS.clear()
  lastPath = null
}
