import { type FormEvent, useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Database, Eye, EyeOff, KeyRound, Loader2, Moon, ShieldCheck, Sun, Zap } from 'lucide-react'

import { useAuth } from '@/hooks/useAuth'
import { endpoints } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import { Button, IconButton } from '@/components/ui'
import { useTheme } from '@/lib/theme'
import { localStore } from '@/lib/session'

const FEATURES = [
  { icon: Database, title: '20 analytical views', copy: 'Kimball star schema over PostgreSQL and MySQL' },
  { icon: ShieldCheck, title: '12 DQ rules', copy: 'Completeness, validity, uniqueness, accuracy, timeliness' },
  { icon: Zap, title: 'Change detection', copy: 'Price changes, new arrivals, removals, recategorisations' },
]

export default function LoginPage() {
  const { authenticated, login, ready } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { isDark, toggle } = useTheme()

  const [email, setEmail] = useState('admin@example.com')
  const [password, setPassword] = useState('Admin@12345')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: endpoints.meta, retry: 0 })
  const { data: demo } = useQuery({ queryKey: ['demo-accounts'], queryFn: endpoints.demoAccounts, retry: 0 })

  useEffect(() => {
    document.title = 'Sign in · Product Intelligence Pipeline'
  }, [])

  if (ready && authenticated) {
    const remembered = localStore.get<string>('account.startPage', '/')
    const target = (location.state as { from?: string } | null)?.from ?? remembered
    return <Navigate to={target} replace />
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(localStore.get<string>('account.startPage', '/'), { replace: true })
    } catch (exception) {
      const message = exception instanceof Error ? exception.message : 'Sign in failed'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-bg text-ink">
      {/* ------------------------------------------------------------- brand panel */}
      <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-line bg-[var(--surface-2)] p-10 lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.55]"
          style={{
            background:
              'radial-gradient(60% 50% at 15% 0%, color-mix(in srgb, var(--chart-1) 22%, transparent), transparent 70%), radial-gradient(50% 45% at 90% 100%, color-mix(in srgb, var(--chart-2) 20%, transparent), transparent 70%)',
          }}
          aria-hidden
        />
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white">
              <Database className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <p className="text-base font-semibold leading-tight">Product Intelligence Pipeline</p>
              <p className="text-xs text-subtle">Web-to-Warehouse · DEPI Data Engineering</p>
            </div>
          </div>

          <h1 className="mt-14 max-w-lg text-3xl font-semibold leading-tight tracking-tight">
            Turn permitted public product data into a trustworthy analytical warehouse.
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-muted">
            Compliant ingestion with robots.txt enforcement, product-name cleaning, currency normalisation,
            fuzzy duplicate detection, historical price snapshots, catalog reconciliation and a measured data-quality
            score - exposed through this dashboard.
          </p>
        </div>

        <div className="relative grid gap-3">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="flex items-start gap-3 rounded-xl border border-line bg-surface/70 p-3.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-300">
                <feature.icon className="h-4 w-4" aria-hidden />
              </span>
              <div>
                <p className="text-sm font-medium">{feature.title}</p>
                <p className="text-xs text-subtle">{feature.copy}</p>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ------------------------------------------------------------------- form */}
      <main className="flex w-full flex-col lg:w-1/2">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2 lg:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
              <Database className="h-4 w-4" aria-hidden />
            </div>
            <p className="text-sm font-semibold">Product Intelligence</p>
          </div>
          <IconButton
            label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            icon={isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            onClick={toggle}
          />
        </div>

        <div className="flex flex-1 items-center justify-center px-4 pb-10">
          <div className="w-full max-w-sm">
            <h2 className="text-xl font-semibold">Sign in</h2>
            <p className="mt-1 text-sm text-muted">Use one of the documented demo accounts.</p>

            <form onSubmit={submit} className="mt-6 space-y-3.5" noValidate>
              <div>
                <label htmlFor="email" className="stat-label mb-1.5 block">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="input"
                  required
                />
              </div>

              <div>
                <label htmlFor="password" className="stat-label mb-1.5 block">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="input pr-10"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1.5 text-subtle hover:bg-surface-3"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error ? (
                <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3 py-2 text-xs text-danger">
                  {error}
                </div>
              ) : null}

              <Button type="submit" variant="primary" loading={submitting} className="w-full" icon={<KeyRound className="h-4 w-4" />}>
                Sign in
              </Button>
            </form>

            {demo?.accounts?.length ? (
              <div className="mt-6 rounded-xl border border-line bg-surface p-3">
                <p className="stat-label mb-2">Demo accounts</p>
                <ul className="space-y-1">
                  {demo.accounts.map((account: any) => (
                    <li key={account.email}>
                      <button
                        onClick={() => {
                          setEmail(account.email)
                          setPassword(account.password)
                        }}
                        className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-surface-3"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-xs font-medium">{account.role}</span>
                          <span className="block truncate text-[11px] text-subtle">{account.email}</span>
                        </span>
                        <span className="text-[10px] uppercase tracking-wide text-brand-600 dark:text-brand-300">use</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-subtle">
              <span>{meta?.name ?? 'Product Intelligence Pipeline'}</span>
              <span>· v{meta?.version ?? '1.0.0'}</span>
              <span>· {meta?.database ?? 'warehouse'}</span>
              {meta?.compliance?.respect_robots_txt ? <span>· robots.txt respected</span> : null}
            </div>

            {meta?.limits ? (
              <p className="mt-3 text-[10px] leading-relaxed text-subtle">
                Limits: max {meta.limits.max_page_size} rows per page ·{' '}
                {String(meta.limits.pipeline_limit_per_source ?? '—')} records per source · dedupe threshold{' '}
                {meta.limits.dedupe_threshold ?? '—'}
              </p>
            ) : null}

            {submitting ? (
              <p className="mt-4 flex items-center gap-2 text-xs text-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> Verifying credentials…
              </p>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  )
}