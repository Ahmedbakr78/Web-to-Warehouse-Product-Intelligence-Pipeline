/**
 * Application shell: fixed sidebar (desktop) + off-canvas drawer (mobile),
 * sticky top bar with search, notifications, theme switch and the account menu.
 *
 * Motion policy: only 120 ms colour/size transitions - no decorative animation and
 * no animated route transitions, so navigation and data reloads feel instant.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell,
  ChevronDown,
  Database,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Sun,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react'

import { NAV_GROUPS, PAGE_TITLES, ALL_NAV_ITEMS } from '@/lib/nav'
import { cn } from '@/lib/cn'
import { useTheme } from '@/lib/theme'
import { endpoints, tokenStore } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import { Badge, Button, IconButton } from './ui'
import { initials, formatRelative, titleCase } from '@/lib/format'
import { useAuth } from '@/hooks/useAuth'

const SIDEBAR_WIDTH_EXPANDED = '16rem'
const SIDEBAR_WIDTH_COLLAPSED = '4.5rem'

export default function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const { can } = useAuth()
  const { isDark, toggle } = useTheme()

  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('pip.sidebar') === 'collapsed')
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: endpoints.health,
    refetchInterval: 60_000,
    retry: 1,
  })

  useEffect(() => {
    localStorage.setItem('pip.sidebar', collapsed ? 'collapsed' : 'expanded')
  }, [collapsed])

  // Close the mobile drawer on navigation (silent, instant).
  useEffect(() => setMobileOpen(false), [location.pathname])

  // Global shortcut: "/" focuses search, "g" then a key navigates (power-user friendly).
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName) || target?.isContentEditable
      if (event.key === '/' && !typing) {
        event.preventDefault()
        setSearchOpen(true)
      }
      if (event.key === 'Escape') {
        setSearchOpen(false)
        setMobileOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const page = useMemo(() => {
    if (PAGE_TITLES[location.pathname]) return PAGE_TITLES[location.pathname]
    const match = ALL_NAV_ITEMS.find((item) => location.pathname.startsWith(item.to) && item.to !== '/')
    return match ? { title: match.label, subtitle: match.description } : { title: 'Product Intelligence', subtitle: '' }
  }, [location.pathname])

  const suggestions = useMemo(() => {
    if (query.trim().length < 2) return []
    const needle = query.toLowerCase()
    return ALL_NAV_ITEMS.filter(
      (item) => item.label.toLowerCase().includes(needle) || item.description.toLowerCase().includes(needle),
    ).slice(0, 6)
  }, [query])

  const online = health?.status === 'ok'

  return (
    <div className="flex h-full min-h-screen bg-bg text-ink">
      {/* ---------------------------------------------------------------- sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 hidden shrink-0 border-r border-line bg-[var(--sidebar-bg)] lg:flex lg:flex-col',
          collapsed ? 'w-[var(--sidebar-w-collapsed)]' : 'w-[var(--sidebar-w-expanded)]',
        )}
        style={
          {
            '--sidebar-w-collapsed': SIDEBAR_WIDTH_COLLAPSED,
            '--sidebar-w-expanded': SIDEBAR_WIDTH_EXPANDED,
          } as React.CSSProperties
        }
      >
        <div className={cn('flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4', collapsed && 'justify-center px-0')}>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white">
            <Database className="h-4 w-4" aria-hidden />
          </div>
          {!collapsed ? (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold leading-tight">Product Intelligence</p>
              <p className="truncate text-[10px] leading-tight text-subtle">Web-to-Warehouse Pipeline</p>
            </div>
          ) : null}
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Main navigation">
          {NAV_GROUPS.map((group) => {
            const items = group.items.filter((item) => !item.permission || can(item.permission))
            if (!items.length) return null
            return (
              <div key={group.title} className="mb-4">
                {!collapsed ? <p className="section-title mb-1.5 px-3">{group.title}</p> : null}
                <ul className="space-y-0.5">
                  {items.map((item) => (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.to === '/'}
                        title={collapsed ? item.label : undefined}
                        className={({ isActive }) => cn('sidebar-link', isActive && 'active', collapsed && 'justify-center px-0')}
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
        </nav>

        <div className="shrink-0 border-t border-line p-2">
          <button
            onClick={() => setCollapsed((value) => !value)}
            className="sidebar-link hidden w-full lg:flex"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
            {!collapsed ? <span>Collapse</span> : null}
          </button>
          <div className={cn('mt-1 flex items-center gap-2 rounded-lg px-3 py-2', collapsed && 'justify-center px-0')}>
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
        </div>
      </aside>

      {/* ------------------------------------------------------------ mobile nav */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-[var(--overlay)]" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="relative flex h-full w-72 max-w-[82vw] flex-col border-r border-line bg-[var(--sidebar-bg)]">
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-line px-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
                  <Database className="h-4 w-4" aria-hidden />
                </div>
                <p className="text-sm font-semibold">Product Intelligence</p>
              </div>
              <IconButton label="Close menu" icon={<X className="h-4 w-4" />} onClick={() => setMobileOpen(false)} />
            </div>
            <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Mobile navigation">
              {NAV_GROUPS.map((group) => {
                const items = group.items.filter((item) => !item.permission || can(item.permission))
                if (!items.length) return null
                return (
                  <div key={group.title} className="mb-4">
                    <p className="section-title mb-1.5 px-3">{group.title}</p>
                    <ul className="space-y-0.5">
                      {items.map((item) => (
                        <li key={item.to}>
                          <NavLink
                            to={item.to}
                            end={item.to === '/'}
                            className={({ isActive }) => cn('sidebar-link py-2.5', isActive && 'active')}
                          >
                            <item.icon className="h-[18px] w-[18px]" aria-hidden />
                            <span className="truncate">{item.label}</span>
                          </NavLink>
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </nav>
          </aside>
        </div>
      ) : null}

      {/* ---------------------------------------------------------------- content */}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-0">
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-[var(--surface)]/95 px-3 backdrop-blur sm:px-4">
          <IconButton
            label="Open menu"
            icon={<Menu className="h-5 w-5" />}
            onClick={() => setMobileOpen(true)}
            className="lg:hidden"
          />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold text-ink sm:text-base">{page.title}</h1>
            {page.subtitle ? <p className="hidden truncate text-xs text-subtle sm:block">{page.subtitle}</p> : null}
          </div>

          <button
            onClick={() => setSearchOpen(true)}
            className="hidden items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-subtle hover:border-line-strong md:flex"
          >
            <Search className="h-4 w-4" aria-hidden />
            <span>Quick navigation</span>
            <kbd className="ml-6 rounded border border-line bg-surface-3 px-1.5 py-0.5 font-mono text-[10px]">/</kbd>
          </button>
          <IconButton label="Search" icon={<Search className="h-4 w-4" />} onClick={() => setSearchOpen(true)} className="md:hidden" />

          <IconButton
            label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            icon={isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            onClick={toggle}
          />
          <NotificationBell />
          <UserMenu />
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1600px] p-3 sm:p-4 lg:p-5">
            <Outlet />
          </div>
        </main>
      </div>

      {/* ------------------------------------------------------------ command search */}
      {searchOpen ? (
        <div className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[12vh]">
          <div className="absolute inset-0 bg-[var(--overlay)]" onClick={() => setSearchOpen(false)} aria-hidden />
          <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
            <div className="flex items-center gap-2 border-b border-line px-3">
              <Search className="h-4 w-4 text-subtle" aria-hidden />
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Jump to a screen…"
                aria-label="Search screens"
                className="h-11 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-subtle"
              />
              <kbd className="rounded border border-line bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] text-subtle">ESC</kbd>
            </div>
            <div className="max-h-72 overflow-auto p-2">
              {query.trim().length < 2 ? (
                <div className="px-2 py-6 text-center text-xs text-subtle">
                  Type at least two characters to search the navigation.
                </div>
              ) : suggestions.length ? (
                suggestions.map((item) => (
                  <button
                    key={item.to}
                    onClick={() => {
                      navigate(item.to)
                      setSearchOpen(false)
                      setQuery('')
                    }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-surface-3"
                  >
                    <item.icon className="h-4 w-4 text-brand-600 dark:text-brand-300" aria-hidden />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-ink">{item.label}</span>
                      <span className="block truncate text-xs text-subtle">{item.description}</span>
                    </span>
                  </button>
                ))
              ) : (
                <div className="px-2 py-6 text-center text-xs text-subtle">No matching screen.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

/* =====================================================================================
   Notifications bell
   ===================================================================================== */
function NotificationBell() {
  const [open, setOpen] = useState(false)
  const { data, refetch } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => endpoints.notifications(8, false),
    refetchInterval: 120_000,
    enabled: !!tokenStore.get(),
  })
  const unread = data?.items?.filter((item: any) => !item.is_read).length ?? 0

  return (
    <div className="relative">
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
            Signed in {formatRelative(user.last_login_at ?? user.created_at)} · v1.0.0
          </div>
        </div>
      ) : null}
    </div>
  )
}

/* =====================================================================================
   Error boundary + offline banner (exported for the router)
   ===================================================================================== */
export function ErrorBoundaryFallback({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <RefreshCw className="h-8 w-8 text-danger" aria-hidden />
      <h2 className="text-base font-semibold">This screen failed to render</h2>
      <p className="max-w-md text-sm text-muted">{error.message}</p>
      <Button variant="primary" onClick={reset} icon={<RefreshCw className="h-4 w-4" />}>
        Reload the screen
      </Button>
    </div>
  )
}