/**
 * Application shell: fixed sidebar (desktop) + off-canvas drawer (mobile),
 * sticky top bar with search, notifications, theme switch and the account menu.
 *
 * Motion policy: only 120 ms colour/size transitions - no decorative animation and
 * no animated route transitions, so navigation and data reloads feel instant.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell,
  ChevronDown,
  Command,
  CornerDownLeft,
  Keyboard,
  LogOut,
  Menu,
  Moon,
  Package,
  Search,
  Sun,
} from 'lucide-react'

import { PAGE_TITLES, ALL_NAV_ITEMS } from '@/lib/nav'
import { cn } from '@/lib/cn'
import { useTheme } from '@/lib/theme'
import { endpoints, searchProducts, tokenStore } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import { Badge, IconButton } from './ui'
import { initials, formatRelative, titleCase, formatPrice } from '@/lib/format'
import { useAuth } from '@/hooks/useAuth'
import { NavDrawer, PhoneTabBar, Sidebar, usePhoneLayout, useRailState } from './Navigation'
import { useFocusHeading, useScrollRestoration } from '@/hooks/useScrollRestoration'

export default function AppShell() {
  const location = useLocation()
  const { isDark, toggle } = useTheme()
  const [paletteOpen, setPaletteOpen] = useState(false)

  const { collapsed, toggleRail, overlay, drawerOpen, setDrawerOpen, closeDrawer, drawerRef, onTouchStart, onTouchEnd } =
    useRailState()
  const isPhone = usePhoneLayout()
  useScrollRestoration()
  useFocusHeading()

  // Global shortcuts: Ctrl/Cmd-K or "/" opens the palette, Ctrl/Cmd-B toggles the
  // sidebar, "[" and "]" collapse or expand it, Escape closes any overlay.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName) || target?.isContentEditable
      const mod = event.ctrlKey || event.metaKey

      if (mod && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((value) => !value)
        return
      }
      if (event.key === '/' && !typing && !mod) {
        event.preventDefault()
        setPaletteOpen(true)
        return
      }
      if (mod && event.key.toLowerCase() === 'b') {
        event.preventDefault()
        if (overlay) setDrawerOpen((value) => !value)
        else toggleRail()
        return
      }
      if (event.key === '[' && !typing) {
        event.preventDefault()
        if (overlay) setDrawerOpen(false)
        else toggleRail()
        return
      }
      if (event.key === ']' && !typing) {
        event.preventDefault()
        if (overlay) setDrawerOpen(false)
        else toggleRail()
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false)
        setDrawerOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [overlay, toggleRail, setDrawerOpen])

  const page = useMemo(() => {
    if (PAGE_TITLES[location.pathname]) return PAGE_TITLES[location.pathname]
    const match = ALL_NAV_ITEMS.find((item) => location.pathname.startsWith(item.to) && item.to !== '/')
    return match ? { title: match.label, subtitle: match.description } : { title: 'Product Intelligence', subtitle: '' }
  }, [location.pathname])

  return (
    <div
      className="flex h-full min-h-[100dvh] bg-bg text-ink"
    >
      {/* ---------------------------------------------------------- desktop rail */}
      {!overlay ? <Sidebar collapsed={collapsed} onToggle={toggleRail} /> : null}

      {/* --------------------------------------------------------- overlay drawer */}
      {/* Swipe left on the drawer closes it; the handlers live on the wrapper so
          the gesture works from any drawer child, not just the nav list. */}
      <div className="lg:hidden" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
        <NavDrawer open={drawerOpen} onClose={closeDrawer} ref={drawerRef} />
      </div>

      {/* ---------------------------------------------------------------- content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-[var(--surface)]/95 px-3 pt-[env(safe-area-inset-top)] backdrop-blur sm:px-4">
          <IconButton
            label="Open menu"
            icon={<Menu className="h-5 w-5" />}
            onClick={() => setDrawerOpen(true)}
            className="lg:hidden"
          />
          <div className="min-w-0 flex-1">
            <h1
              data-page-heading
              tabIndex={-1}
              className="truncate text-sm font-semibold text-ink outline-none sm:text-base"
            >
              {page.title}
            </h1>
            {page.subtitle ? <p className="hidden truncate text-xs text-subtle sm:block">{page.subtitle}</p> : null}
          </div>

          {isPhone ? null : (
            <button
              onClick={() => setPaletteOpen(true)}
              className="hidden items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-subtle hover:border-line-strong md:flex"
            >
              <Search className="h-4 w-4" aria-hidden />
              <span>Search everything</span>
              <kbd className="ml-6 rounded border border-line bg-surface-3 px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
            </button>
          )}
          <IconButton label="Search" icon={<Search className="h-4 w-4" />} onClick={() => setPaletteOpen(true)} className="md:hidden" />

          <IconButton
            label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            icon={isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            onClick={toggle}
          />
          {isPhone ? null : <NotificationBell />}
          <UserMenu />
        </header>

        {/* pb-20 clears the fixed phone tab bar. */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className={cn('mx-auto w-full max-w-[1600px] p-3 sm:p-4 lg:p-5', isPhone && 'pb-24')}>
            <Outlet />
          </div>
        </main>
      </div>

      <PhoneTabBar />

      {/* ------------------------------------------------------------ command palette */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onToggleTheme={toggle}
        onToggleSidebar={overlay ? () => setDrawerOpen((value) => !value) : toggleRail}
        toggleSidebarLabel={overlay ? 'Open navigation' : collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      />
    </div>
  )
}

/* =====================================================================================
   Command palette: navigation + live product search + actions (Ctrl/Cmd-K or "/")
   ===================================================================================== */
type PaletteResult =
  | { kind: 'nav'; to: string; label: string; description: string; icon: React.ComponentType<{ className?: string }> }
  | { kind: 'product'; id: number; label: string; description: string; price: string }
  | { kind: 'action'; label: string; description: string; run: () => void }

function CommandPalette({
  open,
  onClose,
  onToggleTheme,
  onToggleSidebar,
  toggleSidebarLabel,
}: {
  open: boolean
  onClose: () => void
  onToggleTheme: () => void
  onToggleSidebar: () => void
  toggleSidebarLabel: string
}) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const [products, setProducts] = useState<Array<{ product_id: number; canonical_name: string; category_name: string | null; price_usd: number | null }>>([])
  const navigate = useNavigate()
  const { logout } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) {
      setQuery('')
      setCursor(0)
      setProducts([])
      return
    }
    inputRef.current?.focus()
  }, [open])

  // Live product search. The AbortSignal is passed all the way through so a
  // superseded keystroke is cancelled instead of racing the newer response.
  useEffect(() => {
    const term = query.trim()
    if (!open || term.length < 2) {
      setProducts([])
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      searchProducts(term, controller.signal)
        .then((response) => setProducts((response?.items ?? []) as typeof products))
        .catch((error) => {
          // An abort is the expected outcome of typing another character.
          if ((error as Error).name !== 'AbortError') setProducts([])
        })
    }, 220)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query, open])

  const results = useMemo<PaletteResult[]>(() => {
    const term = query.trim().toLowerCase()
    const nav: PaletteResult[] = ALL_NAV_ITEMS.filter(
      (item) => !term || item.label.toLowerCase().includes(term) || item.description.toLowerCase().includes(term),
    ).map((item) => ({ kind: 'nav' as const, to: item.to, label: item.label, description: item.description, icon: item.icon }))

    const productResults: PaletteResult[] = products.map((product) => ({
      kind: 'product' as const,
      id: product.product_id,
      label: product.canonical_name,
      description: product.category_name ?? 'Uncategorised',
      price: formatPrice(product.price_usd, 'USD'),
    }))

    const actions: PaletteResult[] = (
      [
        {
          kind: 'action' as const,
          label: 'Toggle light / dark mode',
          description: 'Theme switch',
          run: onToggleTheme,
        },
        {
          kind: 'action' as const,
          label: toggleSidebarLabel,
          description: 'Collapse or expand the navigation',
          run: onToggleSidebar,
        },
        {
          kind: 'action' as const,
          label: 'Sign out',
          description: 'End the current session',
          run: logout,
        },
      ] satisfies PaletteResult[]
    ).filter((action) => !term || action.label.toLowerCase().includes(term))

    return [...productResults, ...nav, ...actions].slice(0, 12)
  }, [query, products, onToggleTheme, onToggleSidebar, toggleSidebarLabel, logout])

  useEffect(() => setCursor(0), [results.length])

  function choose(result: PaletteResult) {
    onClose()
    if (result.kind === 'nav') navigate(result.to)
    if (result.kind === 'product') navigate(`/products/${result.id}`)
    if (result.kind === 'action') result.run()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[10vh]" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="absolute inset-0 bg-[var(--overlay)]" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-xl overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
        <div className="flex items-center gap-2 border-b border-line px-3">
          <Search className="h-4 w-4 text-subtle" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                setCursor((value) => Math.min(results.length - 1, value + 1))
              }
              if (event.key === 'ArrowUp') {
                event.preventDefault()
                setCursor((value) => Math.max(0, value - 1))
              }
              if (event.key === 'Enter' && results[cursor]) choose(results[cursor])
              if (event.key === 'Escape') onClose()
            }}
            placeholder="Search products, screens and actions…"
            aria-label="Command palette search"
            className="h-12 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-subtle"
          />
          <Badge tone="neutral">esc</Badge>
        </div>
        <div className="max-h-[52vh] overflow-auto p-2">
          {results.length ? (
            results.map((result, index) => {
              const isActive = index === cursor
              const Icon =
                result.kind === 'nav' ? result.icon : result.kind === 'product' ? Package : Command
              return (
                <button
                  key={result.kind === 'product' ? `p${result.id}` : result.label}
                  onClick={() => choose(result)}
                  onMouseEnter={() => setCursor(index)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left',
                    isActive ? 'bg-brand-50 dark:bg-brand-500/15' : 'hover:bg-surface-3',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">{result.label}</span>
                    <span className="block truncate text-xs text-subtle">{result.description}</span>
                  </span>
                  {result.kind === 'product' ? <Badge tone="success">{result.price}</Badge> : null}
                  {isActive ? <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-subtle" aria-hidden /> : null}
                </button>
              )
            })
          ) : (
            <div className="px-2 py-8 text-center text-xs text-subtle">No matches. Try a different term.</div>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-line px-3 py-1.5 text-[10px] text-subtle">
          <span className="flex items-center gap-1.5">
            <Keyboard className="h-3 w-3" aria-hidden /> ↑↓ navigate · ↵ open · / trigger
          </span>
          <span>{results.length} results</span>
        </div>
      </div>
    </div>
  )
}

/* =====================================================================================
    Notifications bell
    ===================================================================================== */
function NotificationBell() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const { data, refetch } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => endpoints.notifications(8, false),
    refetchInterval: 120_000,
    enabled: !!tokenStore.get(),
  })
  const unread = data?.items?.filter((item: any) => !item.is_read).length ?? 0

  // Dismiss on outside click or Escape, matching the account menu's behaviour.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="relative" ref={containerRef}>
      <IconButton
        label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
        icon={
          <span className="relative">
            <Bell className="h-4 w-4" />
            {unread ? (
              <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-danger px-0.5 text-[9px] font-bold text-white">
                {unread > 9 ? '9+' : unread}
              </span>
            ) : null}
          </span>
        }
        onClick={() => {
          setOpen((value) => !value)
          refetch()
        }}
      />
      {open ? (
        <div className="absolute right-0 top-11 z-40 w-80 overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
          <div className="flex items-center justify-between border-b border-line px-3 py-2">
            <p className="text-xs font-semibold">Notifications</p>
            <button
              className="text-[11px] text-brand-600 hover:underline dark:text-brand-300"
              onClick={async () => {
                await endpoints.markAllRead()
                refetch()
              }}
            >
              Mark all read
            </button>
          </div>
          <div className="max-h-80 overflow-auto">
            {data?.items?.length ? (
              data.items.map((item: any) => (
                <button
                  key={item.notification_id}
                  onClick={() => {
                    endpoints.markRead(item.notification_id)
                    setOpen(false)
                    refetch()
                  }}
                  className={cn('block w-full border-b border-line px-3 py-2.5 text-left hover:bg-surface-2', !item.is_read && 'bg-brand-50/60 dark:bg-brand-500/10')}
                >
                  <div className="flex items-start gap-2">
                    <Badge tone={item.level === 'critical' ? 'danger' : item.level === 'warning' ? 'warning' : 'info'}>
                      {titleCase(item.level)}
                    </Badge>
                    {!item.is_read ? <span className="mt-1 h-1.5 w-1.5 rounded-full bg-brand-500" /> : null}
                  </div>
                  <p className="mt-1 text-xs font-medium text-ink">{item.title}</p>
                  {item.body ? <p className="truncate text-[11px] text-subtle">{item.body}</p> : null}
                  <p className="mt-0.5 text-[10px] text-subtle">{formatRelative(item.created_at)}</p>
                </button>
              ))
            ) : (
              <p className="px-3 py-8 text-center text-xs text-subtle">No notifications yet.</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}

/* =====================================================================================
   User menu
   ===================================================================================== */
function UserMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!user) return null

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-surface-3"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white"
          style={{ backgroundColor: user.avatar_color ?? '#6366f1' }}
        >
          {initials(user.full_name)}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block max-w-[9rem] truncate text-xs font-medium leading-tight">{user.full_name}</span>
          <span className="block text-[10px] capitalize leading-tight text-subtle">{user.role}</span>
        </span>
        <ChevronDown className="hidden h-3.5 w-3.5 text-subtle sm:block" aria-hidden />
      </button>

      {open ? (
        <div className="absolute right-0 top-11 z-40 w-64 overflow-hidden rounded-xl border border-line bg-surface shadow-pop" role="menu">
          <div className="border-b border-line px-3 py-2.5">
            <p className="truncate text-sm font-medium text-ink">{user.full_name}</p>
            <p className="truncate text-xs text-subtle">{user.email}</p>
            <div className="mt-1.5 flex items-center gap-1.5">
              <Badge tone={user.role === 'admin' ? 'danger' : user.role === 'analyst' ? 'info' : 'neutral'}>{user.role}</Badge>
              {user.is_active ? <Badge tone="success" dot>active</Badge> : null}
            </div>
          </div>
          <div className="p-1">
            <button
              role="menuitem"
              onClick={() => {
                navigate('/account')
                setOpen(false)
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-3"
            >
              Account settings
            </button>
            <button
              role="menuitem"
              onClick={() => {
                logout()
                setOpen(false)
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-danger-soft"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </button>
          </div>
          <div className="border-t border-line px-3 py-2 text-[10px] text-subtle">
            Signed in {formatRelative(user.last_login_at ?? user.created_at)} · v1.3.0
          </div>
        </div>
      ) : null}
    </div>
  )
}
