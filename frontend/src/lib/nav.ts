import {
  Activity,
  AlertTriangle,
  BarChart3,
  Boxes,
  Building2,
  Database,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  ListFilter,
  Package,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  Terminal,
  Tags,
  UserCircle,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  description: string
  permission?: string
  badge?: 'new' | 'beta'
}

export type NavGroup = { title: string; items: NavItem[] }

export const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, description: 'KPIs, trends and pipeline health' },
      { to: '/analytics', label: 'Analytics', icon: BarChart3, description: 'Category, brand and price analysis' },
      { to: '/changes', label: 'Changes', icon: Activity, description: 'Price changes, new and removed products', badge: 'new' },
    ],
  },
  {
    title: 'Catalogue',
    items: [
      { to: '/products', label: 'Products', icon: Package, description: 'Deduplicated product catalogue' },
      { to: '/categories', label: 'Categories', icon: Tags, description: 'Taxonomy explorer with counts' },
      { to: '/catalog', label: 'Catalog match', icon: Building2, description: 'Internal catalog reconciliation' },
    ],
  },
  {
    title: 'Pipeline',
    items: [
      { to: '/pipeline', label: 'Runs', icon: Gauge, description: 'Run history and stage timings' },
      { to: '/quality', label: 'Data quality', icon: ShieldCheck, description: '12 rules across 6 dimensions' },
      { to: '/sources', label: 'Sources', icon: Boxes, description: 'Ingestion sources and compliance' },
    ],
  },
  {
    title: 'Explore',
    items: [
      { to: '/query', label: 'Query lab', icon: Terminal, description: 'Read-only SQL over 20 views', permission: 'query' },
      { to: '/builder', label: 'Builder', icon: Sparkles, description: 'Compose and save custom views', badge: 'beta' },
    ],
  },
  {
    title: 'Workspace',
    items: [
      { to: '/alerts', label: 'Alerts', icon: AlertTriangle, description: 'Alert rules and notifications' },
      { to: '/account', label: 'Account', icon: UserCircle, description: 'Profile, appearance and security' },
      { to: '/settings', label: 'Settings', icon: SettingsIcon, description: 'Application settings', permission: 'manage_settings' },
      { to: '/users', label: 'Users', icon: Users, description: 'Roles and access control', permission: 'manage_users' },
      { to: '/audit', label: 'Audit', icon: ListFilter, description: 'Audit trail and HTTP log', permission: 'view_audit' },
    ],
  },
]

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items)

export const PAGE_TITLES: Record<string, { title: string; subtitle: string }> = {
  '/': { title: 'Dashboard', subtitle: 'Live overview of the product intelligence pipeline' },
  '/analytics': { title: 'Analytics', subtitle: 'Price, category and brand intelligence from SQL' },
  '/changes': { title: 'Change feed', subtitle: 'Price changes, new arrivals, removals and recategorisations' },
  '/products': { title: 'Products', subtitle: 'Canonical, deduplicated product catalogue' },
  '/categories': { title: 'Categories', subtitle: 'Normalised taxonomy with live counts and pricing' },
  '/catalog': { title: 'Catalog reconciliation', subtitle: 'Scraped market data versus the internal catalog' },
  '/pipeline': { title: 'Pipeline runs', subtitle: 'Execution history, stage timings and manual triggers' },
  '/quality': { title: 'Data quality', subtitle: 'Rule catalogue, results and quality score trend' },
  '/sources': { title: 'Ingestion sources', subtitle: 'Registered sources, robots.txt and rate limits' },
  '/query': { title: 'Query lab', subtitle: 'Read-only SQL console over the analytical views' },
  '/builder': { title: 'View builder', subtitle: 'Compose, save and share custom list views' },
  '/alerts': { title: 'Alerts', subtitle: 'Rules, thresholds and in-app notifications' },
  '/account': { title: 'Account', subtitle: 'Profile, appearance, security and API keys' },
  '/settings': { title: 'Settings', subtitle: 'Global application configuration' },
  '/users': { title: 'Users & roles', subtitle: 'Accounts, roles and API key management' },
  '/audit': { title: 'Audit & compliance', subtitle: 'Application audit trail and outbound HTTP evidence' },
  '/login': { title: 'Sign in', subtitle: 'Access the analytics dashboard' },
}
