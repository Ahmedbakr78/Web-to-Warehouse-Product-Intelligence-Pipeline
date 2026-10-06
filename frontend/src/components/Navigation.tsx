/**
 * Responsive navigation: a persistent sidebar on desktop (expanded / collapsed /
 * hidden), an off-canvas drawer with swipe gestures on phones and tablets, and a
 * bottom tab bar for the five most-used destinations on small screens.
 *
 * Motion policy: the drawer and the rail change width without animating. Nothing
 * eases in or out, so opening the menu and switching screens feel instantaneous.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { PanelLeftClose, PanelLeftOpen, Wifi, WifiOff, X, AlertTriangle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import type { LucideIcon } from 'lucide-react'

import { NAV_GROUPS, type NavItem } from '@/lib/nav'
import { cn } from '@/lib/cn'
import { endpoints, tokenStore } from '@/lib/api'
import { IconButton } from './ui'
import { useAuth } from '@/hooks/useAuth'

const SIDEBAR_WIDTH_EXPANDED = '16rem'
const SIDEBAR_WIDTH_COLLAPED = '4.5rem'

/** Below this width the sidebar becomes an overlay drawer instead of a column. */
export const OVERLAY_BREAKPOINT = 1024
/** Below this width a bottom tab bar is shown instead of the header search field. */
export const PHONE_BREAKPOINT = 640

/** The destinations surfaced on the phone tab bar, in priority order. */
const PHONE_TABS: NavItem[] = [
  { to: '/', label: 'Home', icon: NavIcons.dashboard, description: 'Overview' },
  { to: '/products', label: 'Products', icon: NavIcons.products, description: 'Catalogue' },
  { to: '/changes', label: 'Changes', icon: NavIcons.changes, description: 'Change feed' },
  { to: '/analytics', label: 'Analytics', icon: NavIcons.analytics, description: 'Reports' },
  { to: '/pipeline', label: 'Pipeline', icon: NavIcons.pipeline, description: 'Runs' },
]

// Imported lazily as a namespace so the tab bar stays in sync with lib/nav.
import * as NavIcons from '@/lib/nav-icons'

type RailState = 'expanded' | 'collapsed'

function readRail(): RailState {
  return localStorage.getItem('pip.sidebar') === 'collapsed' ? 'collapsed' : 'expanded'
}

/** True when the viewport is narrower than the sidebar breakpoint. */
function useOverlayLayout(): boolean {
  const [overlay, setOverlay] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < OVERLAY_BREAKPOINT,
  )
  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${OVERLAY_BREAKPOINT - 1}px)`)
    const onChange = (event: MediaQueryListEvent) => setOverlay(event.matches)
    query.addEventListener('change', onChange)
    setOverlay(query.matches)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return overlay
}

/** True on phone-sized viewports, where a bottom tab bar replaces header controls. */
export function usePhoneLayout(): boolean {
  const [phone, setPhone] = useState(() => typeof window !== 'undefined' && window.innerWidth < PHONE_BREAKPOINT)
  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${PHONE_BREAKPOINT - 1}px)`)
    const onChange = (event: MediaQueryListEvent) => setPhone(event.matches)
    query.addEventListener('change', onChange)
    setPhone(query.matches)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return phone
}

/* =====================================================================================
   Navigation - the single component the shell mounts in three places
   ===================================================================================== */

export type NavProps = {
  /** Icon-only rail with `title` tooltips. */
  collapsed?: boolean
  /** Show the group headings. */
  showGroups?: boolean
  /** Mark the item matching the current path as active. */
  variant?: 'rail' | 'drawer' | 'tabbar'
  onNavigate?: () => void
}

export function NavContent({ collapsed = false, showGroups = true, variant = 'drawer', onNavigate }: NavProps) {
  const { can } = useAuth()

  return (
    <div className={cn('flex flex-col', variant === 'rail' ? 'gap-4' : 'gap-0.5')}>
      {NAV_GROUPS.map((group) => {
        const items = group.items.filter((item) => !item.permission || can(item.permission))
        if (!items.length) return null
        return (
          <div key={group.title} className={variant === 'rail' ? '' : 'mb-4'}>
            {showGroups && !collapsed ? <p className="section-title mb-1.5 px-3">{group.title}</p> : null}
            <ul className="space-y-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    title={collapsed ? item.label : undefined}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'sidebar-link',
                        isActive && 'active',
                        collapsed && 'justify-center px-0',
                        variant === 'drawer' && 'py-2.5',
                      )
                    }
                  >
                    <item.icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
                    {!collapsed ? <span className="truncate">{item.label}</span> : null}
                    {!collapsed && item.badge ? (
                      <span className="ml-auto rounded bg-brand-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-brand-700 dark:bg-brand-500/20 dark:text-brand-300">
                        {item.badge}
                      </span>
                    ) : null}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

/* =====================================================================================
   Mobile bottom tab bar
   ===================================================================================== */

export function PhoneTabBar() {
  const { can } = useAuth()
  const tabs = PHONE_TABS.filter((tab) => {
    const match = NAV_GROUPS.flatMap((group) => group.items).find((item) => item.to === tab.to)
    return !match?.permission || can(match.permission)
  })

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-[var(--surface)]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
      aria-label="Primary"
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/'}
          className={({ isActive }) =>
            cn(
              'flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 px-1 py-2 text-[10px] font-medium',
              isActive ? 'text-brand-600 dark:text-brand-300' : 'text-subtle',
            )
          }
        >
          <tab.icon className="h-5 w-5" aria-hidden />
          <span className="truncate">{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

/* =====================================================================================
   Connection indicator
   ===================================================================================== */

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: endpoints.health,
    refetchInterval: 60_000,
    retry: 1,
    enabled: Boolean(tokenStore.get()),
  })
}

export function ConnectionStrip({ collapsed }: { collapsed: boolean }) {
  const { data: health } = useHealth()
  const online = health?.status === 'ok'
  return (
    <div className={cn('flex items-center gap-2 rounded-lg px-3 py-2', collapsed && 'justify-center px-0')}>
      {online ? <Wifi className="h-4 w-4 text-success" aria-hidden /> : <WifiOff className="h-4 w-4 text-danger" aria-hidden />}
      {!collapsed ? (
        <div className="min-w-0 text-[11px] leading-tight">
          <p className="font-medium text-ink">{online ? 'Connected' : 'Degraded'}</p>
          <p className="truncate text-subtle">
            {health?.database?.database ?? 'db'} · {health?.database?.dialect ?? '—'}
          </p>
        </div>
      ) : null}
    </div>
  )
}

/* =====================================================================================
   Brand mark
   ===================================================================================== */

export function BrandMark({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn('flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4', collapsed && 'justify-center px-0')}>
      <img src="/logo.png" alt="Product Intelligence logo" className="h-8 w-8 shrink-0 rounded-lg" />
      {!collapsed ? (
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold leading-tight">Product Intelligence</p>
          <p className="truncate text-[10px] leading-tight text-subtle">Web-to-Warehouse Pipeline</p>
        </div>
      ) : null}
    </div>
  )
}

/* =====================================================================================
   Hooks the shell uses to drive the drawer and the rail
   ===================================================================================== */

export function useRailState() {
  const [rail, setRail] = useState<RailState>(readRail)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const overlay = useOverlayLayout()
  const location = useLocation()

  // Persist the desktop rail preference and mirror it to other open tabs.
  useEffect(() => {
    localStorage.setItem('pip.sidebar', rail)
  }, [rail])

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'pip.sidebar') setRail(readRail())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // Close the drawer on navigation.
  useEffect(() => setDrawerOpen(false), [location.pathname])

  // Lock the page behind an open drawer and trap focus inside it.
  const drawerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!drawerOpen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    drawerRef.current?.querySelector<HTMLElement>('a, button')?.focus()
    return () => {
      document.body.style.overflow = previous
    }
  }, [drawerOpen])

  // Swipe left from the left edge to open the drawer; swipe left on the drawer to close.
  const touchStart = useRef<{ x: number; y: number } | null>(null)
  const onTouchStart = useCallback((event: React.TouchEvent) => {
    const touch = event.touches[0]
    touchStart.current = { x: touch.clientX, y: touch.clientY }
  }, [])
  const onTouchEnd = useCallback(
    (event: React.TouchEvent) => {
      const start = touchStart.current
      touchStart.current = null
      if (!start) return
      const touch = event.changedTouches[0]
      const dx = touch.clientX - start.x
      const dy = touch.clientY - start.y
      // Horizontal intent only, so vertical scrolling is never hijacked.
      if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return
      if (drawerOpen && dx < 0) setDrawerOpen(false)
    },
    [drawerOpen],
  )

  return {
    rail,
    collapsed: rail === 'collapsed',
    toggleRail: useCallback(() => setRail((value) => (value === 'expanded' ? 'collapsed' : 'expanded')), []),
    overlay,
    drawerOpen,
    setDrawerOpen,
    closeDrawer: useCallback(() => setDrawerOpen(false), []),
    drawerRef,
    onTouchStart,
    onTouchEnd,
    edgeSwipe: useCallback(
      (event: React.TouchEvent) => {
        const touch = event.touches[0]
        touchStart.current = { x: touch.clientX, y: touch.clientY }
      },
      [],
    ),
  }
}

/* =====================================================================================
   Sidebar (desktop) and drawer (overlay)
   ===================================================================================== */

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside
      className={cn(
        'fixed bottom-3 left-3 top-3 z-40 hidden shrink-0 flex-col overflow-hidden rounded-2xl border border-line bg-[var(--sidebar-bg)] shadow-lg lg:flex',
        collapsed ? 'w-[var(--sidebar-w-collapsed)]' : 'w-[var(--sidebar-w-expanded)]',
      )}
      style={
        {
          '--sidebar-w-collapsed': SIDEBAR_WIDTH_COLLAPED,
          '--sidebar-w-expanded': SIDEBAR_WIDTH_EXPANDED,
        } as React.CSSProperties
      }
    >
      <BrandMark collapsed={collapsed} />
      <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Main navigation">
        <NavContent collapsed={collapsed} variant="rail" />
      </nav>
      <div className="shrink-0 border-t border-line p-2">
        <button onClick={onToggle} className="sidebar-link hidden w-full lg:flex" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
          {!collapsed ? <span>Collapse</span> : null}
        </button>
        <ConnectionStrip collapsed={collapsed} />
      </div>
    </aside>
  )
}

export function NavDrawer({ open, onClose, ref }: { open: boolean; onClose: () => void; ref?: React.Ref<HTMLDivElement> }) {
  const localRef = useRef<HTMLDivElement | null>(null)
  const attachRef = useCallback(
    (node: HTMLDivElement | null) => {
      localRef.current = node
      if (typeof ref === 'function') ref(node)
      else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node
    },
    [ref],
  )

  /**
   * Escape closes the drawer, and focus moves into it while it is open.
   *
   * `AppShell` also handles Escape globally, but a modal dialog that only closes when
   * some ancestor happens to handle the key is not really modal: keyboard users would
   * be stranded if this component were ever mounted on its own. Returning focus to
   * whatever opened it is the other half of that contract.
   */
  useEffect(() => {
    if (!open) return
    const previouslyFocused = document.activeElement as HTMLElement | null
    localRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 outline-none lg:hidden"
      role="dialog"
      aria-modal="true"
      aria-label="Navigation"
      ref={attachRef}
      tabIndex={-1}
    >
      <div className="absolute inset-0 bg-[var(--overlay)]" onClick={onClose} aria-hidden />
      <aside className="relative m-3 flex h-[calc(100%-1.5rem)] w-72 max-w-[calc(82vw-1.5rem)] flex-col overflow-hidden rounded-2xl border border-line bg-[var(--sidebar-bg)] shadow-xl pb-[env(safe-area-inset-bottom)]">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-line px-4">
          <div className="flex items-center gap-2.5">
            <img src="/logo.png" alt="Product Intelligence logo" className="h-8 w-8 rounded-lg" />
            <p className="text-sm font-semibold">Product Intelligence</p>
          </div>
          <IconButton label="Close menu" icon={<X className="h-4 w-4" />} onClick={onClose} />
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Mobile navigation">
          <NavContent variant="drawer" onNavigate={onClose} />
        </nav>
      </aside>
    </div>
  )
}

export type { LucideIcon, AlertTriangle }
