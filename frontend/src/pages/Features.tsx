/**
 * Feature catalogue - the single place where the whole platform is described.
 *
 * The data comes from `GET /meta/features` (app/core/features.py), which is also the
 * source used by the README and the website, so the UI can never drift from reality.
 * Search matches feature names, details and group titles; group chips filter instantly.
 */

import { useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Check,
  Copy,
  Database,
  GitCompare,
  Globe,
  LayoutDashboard,
  ListChecks,
  Lock,
  Plug,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Workflow,
  Copy as CopyIcon,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Badge, Card, CardHeader, ChipGroup, EmptyState, LoadingState, SearchInput, StatTile, useToast } from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'

const ICONS: Record<string, LucideIcon> = {
  activity: Activity,
  'bar-chart-3': BarChart3,
  copy: Copy,
  database: Database,
  'git-compare': GitCompare,
  globe: Globe,
  'layout-dashboard': LayoutDashboard,
  lock: Lock,
  plug: Plug,
  settings: Settings,
  'shield-check': ShieldCheck,
  sparkles: Sparkles,
  'trending-up': TrendingUp,
  workflow: Workflow,
}

function iconFor(name: string): LucideIcon {
  return ICONS[name] ?? ListChecks
}

type Feature = { name: string; detail?: string }
type Group = {
  key: string
  title: string
  icon: string
  summary: string
  feature_count: number
  features: Feature[]
}
type Catalogue = { total_features: number; total_groups: number; groups: Group[] }

export default function Features() {
  const [term, setTerm] = useState('')
  const [groupKey, setGroupKey] = useState<string>('all')
  const toast = useToast()
  const catalogue = useApiQuery(['meta-features'], endpoints.metaFeatures, { staleTime: 900_000 })

  const data = catalogue.data as Catalogue | undefined

  const groups = useMemo(() => {
    if (!data) return []
    const needle = term.trim().toLowerCase()
    return data.groups
      .filter((group) => groupKey === 'all' || group.key === groupKey)
      .map((group) => {
        if (!needle) return { ...group, features: group.features, matches: group.feature_count }
        const features = group.features.filter(
          (feature) =>
            feature.name.toLowerCase().includes(needle) ||
            (feature.detail ?? '').toLowerCase().includes(needle) ||
            group.title.toLowerCase().includes(needle),
        )
        return { ...group, features, matches: features.length }
      })
      .filter((group) => group.matches > 0)
  }, [data, term, groupKey])

  const visibleFeatures = groups.reduce((total, group) => total + group.matches, 0)

  function copyFeature(name: string) {
    navigator.clipboard?.writeText(name).then(
      () => toast.success('Copied', name),
      () => toast.error('Clipboard unavailable'),
    )
  }

  if (catalogue.isLoading) return <LoadingState label="Loading the feature catalogue…" rows={6} />

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------- header */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <CardHeader
              title="What this platform does"
              subtitle="Every capability below is implemented, tested and documented - grouped by area and searchable"
              icon={<ListChecks className="h-4 w-4" />}
            />
            <div className="mt-3 max-w-xl">
              <SearchInput value={term} onChange={setTerm} placeholder="Search features, e.g. robots, dedupe, dark mode…" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <ChipGroup
              options={[{ id: 'all', label: 'All areas' }, ...(data?.groups ?? []).map((group) => ({ id: group.key, label: group.title.split(' ')[0] }))]}
              value={groupKey}
              onChange={setGroupKey}
            />
          </div>
        </div>
        <p className="mt-3 text-xs text-subtle">
          Showing <span className="font-semibold text-ink">{visibleFeatures}</span> of {data?.total_features} features
          across {data?.total_groups} areas.
        </p>
      </Card>

      {/* ------------------------------------------------------------- tiles */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Features shipped" value={data?.total_features ?? 0} hint="Implemented and tested" icon={<ListChecks className="h-4 w-4" />} />
        <StatTile label="Capability areas" value={data?.total_groups ?? 0} hint="From ingestion to UX" tone="info" />
        <StatTile label="REST operations" value="110+" hint="Documented in OpenAPI" tone="success" />
        <StatTile label="Warehouse objects" value="43" hint="23 tables + 20 views" tone="neutral" />
      </div>

      {/* ------------------------------------------------------------- groups */}
      {groups.length ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
          {groups.map((group) => {
            const Icon = iconFor(group.icon)
            return (
              <Card key={group.key} className="flex flex-col">
                <div className="flex items-start gap-3 border-b border-line p-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate text-sm font-semibold text-ink">{group.title}</h3>
                      <Badge tone="neutral">{group.matches}</Badge>
                    </div>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{group.summary}</p>
                  </div>
                </div>
                <ul className="flex-1 space-y-1.5 p-3">
                  {group.features.map((feature) => (
                    <li key={feature.name} className="group/feature flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-2">
                      <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-medium leading-tight text-ink">{feature.name}</p>
                        {feature.detail ? <p className="mt-0.5 text-[11px] leading-snug text-subtle">{feature.detail}</p> : null}
                      </div>
                      <button
                        onClick={() => copyFeature(feature.name)}
                        aria-label={`Copy “${feature.name}”`}
                        className="mt-0.5 shrink-0 rounded p-1 text-subtle opacity-0 hover:bg-surface-3 hover:text-ink focus-visible:opacity-100 group-hover/feature:opacity-100"
                      >
                        <CopyIcon className="h-3 w-3" />
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            )
          })}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Search className="h-5 w-5" />}
            title="No feature matches that search"
            message="Try a broader term such as price, robots, export, auth or dark mode."
          />
        </Card>
      )}

      {/* ------------------------------------------------------------- footer */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">Catalogue source of truth</p>
            <p className="mt-0.5 text-xs text-muted">
              Served by <code className="rounded bg-surface-3 px-1 font-mono text-[11px]">GET /api/v1/meta/features</code> and
              generated from <code className="rounded bg-surface-3 px-1 font-mono text-[11px]">app/core/features.py</code>.
            </p>
          </div>
          <a className="btn btn-secondary" href="/docs/19_feature_list.md" target="_blank" rel="noreferrer">
            Full feature list in the docs
          </a>
        </div>
      </Card>
    </div>
  )
}