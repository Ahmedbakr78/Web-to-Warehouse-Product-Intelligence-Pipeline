import { useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Compass, Database, House } from 'lucide-react'

import { Badge, Card } from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { NAV_GROUPS } from '@/lib/nav'
import { useAuth } from '@/hooks/useAuth'

export default function NotFound() {
  const location = useLocation()
  const { can } = useAuth()
  const { data: meta } = useApiQuery(['meta'], endpoints.meta, { staleTime: 900_000 })

  const groups = useMemo(
    () =>
      NAV_GROUPS.map((group) => ({
        title: group.title,
        items: group.items.filter((item) => !item.permission || can(item.permission)),
      })).filter((group) => group.items.length > 0),
    [can],
  )

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 py-4">
      <Card className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              'radial-gradient(55% 60% at 12% 0%, color-mix(in srgb, var(--chart-1) 20%, transparent), transparent 70%), radial-gradient(45% 55% at 95% 100%, color-mix(in srgb, var(--chart-2) 18%, transparent), transparent 70%)',
          }}
          aria-hidden
        />
        <div className="relative flex flex-col items-start gap-4 p-6 sm:p-8">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white">
            <Compass className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-3xl font-semibold tracking-tight text-ink">404</p>
              <Badge tone="warning">screen not found</Badge>
            </div>
            <h2 className="mt-2 text-lg font-semibold text-ink">This address is not part of the dashboard</h2>
            <p className="mt-1 max-w-xl text-sm text-muted">
              Nothing is registered at{' '}
              <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-ink">{location.pathname}</code>. It may
              have been renamed, or the link that brought you here is out of date.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/" className="btn btn-primary">
              <House className="h-4 w-4" aria-hidden />
              Back to the dashboard
            </Link>
            <Link to="/products" className="btn btn-secondary">
              <Database className="h-4 w-4" aria-hidden />
              Browse products
            </Link>
          </div>
        </div>
      </Card>

      <Card>
        <p className="section-title mb-3">Jump back in</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {groups.map((group) => (
            <div key={group.title}>
              <p className="stat-label mb-1.5">{group.title}</p>
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-surface-3 hover:text-ink"
                    >
                      <item.icon className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" aria-hidden />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-subtle">
        <span>
          {meta?.name ?? 'Product Intelligence Pipeline'} {'\u00b7'} v{meta?.version ?? '1.0.0'} {'\u00b7'}{' '}
          {meta?.environment ?? 'local'}
        </span>
        <span>
          {meta?.dialect ?? meta?.active_database ?? 'warehouse'}
        </span>
      </div>
    </div>
  )
}
