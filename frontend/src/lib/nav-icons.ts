/**
 * Icon registry.
 *
 * Navigation entries and the feature catalogue reference icons by name so that
 * data (nav config, `/meta/features` payloads, docs) stays serialisable. Keeping
 * the mapping in one module means an icon is registered exactly once and a typo
 * is a type error rather than a blank square on screen.
 */

import {
  Activity,
  AlertTriangle,
  AreaChart,
  Award,
  BarChart3,
  Blocks,
  BookOpen,
  Boxes,
  Braces,
  Building2,
  CalendarClock,
  ChartNoAxesCombined,
  CheckCircle2,
  ClipboardCheck,
  Cloud,
  Code2,
  Compass,
  Copy,
  Database,
  DatabaseZap,
  FileSearch,
  Filter,
  Fingerprint,
  FlaskConical,
  FolderTree,
  Gauge,
  GitCompare,
  GitCompareArrows,
  Globe,
  HardDriveDownload,
  History,
  KeyRound,
  Layers,
  LayoutDashboard,
  LayoutGrid,
  ListChecks,
  Lock,
  Mail,
  Monitor,
  Network,
  Package,
  Palette,
  PanelsTopLeft,
  Plug,
  PlugZap,
  Radar,
  RefreshCw,
  Repeat,
  Rocket,
  Save,
  ScanSearch,
  ScrollText,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Sparkles,
  Star,
  Sunrise,
  Table2,
  Terminal,
  Timer,
  TrendingUp,
  UserCog,
  UserCircle,
  Users,
  Wand2,
  Workflow,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export const ICONS = {
  activity: Activity,
  alert: AlertTriangle,
  'area-chart': AreaChart,
  award: Award,
  'bar-chart': BarChart3,
  'bar-chart-3': BarChart3,
  blocks: Blocks,
  book: BookOpen,
  boxes: Boxes,
  braces: Braces,
  building: Building2,
  calendar: CalendarClock,
  'chart-combined': ChartNoAxesCombined,
  'check-circle': CheckCircle2,
  clipboard: ClipboardCheck,
  cloud: Cloud,
  code: Code2,
  compass: Compass,
  copy: Copy,
  database: Database,
  'database-zap': DatabaseZap,
  'file-search': FileSearch,
  filter: Filter,
  fingerprint: Fingerprint,
  flask: FlaskConical,
  'folder-tree': FolderTree,
  gauge: Gauge,
  compare: GitCompare,
  'git-compare': GitCompare,
  'git-compare-arrows': GitCompareArrows,
  globe: Globe,
  download: HardDriveDownload,
  history: History,
  key: KeyRound,
  layers: Layers,
  dashboard: LayoutDashboard,
  'layout-dashboard': LayoutDashboard,
  grid: LayoutGrid,
  checklist: ListChecks,
  lock: Lock,
  mail: Mail,
  monitor: Monitor,
  network: Network,
  package: Package,
  palette: Palette,
  'panels-top-left': PanelsTopLeft,
  plug: Plug,
  'plug-zap': PlugZap,
  radar: Radar,
  refresh: RefreshCw,
  repeat: Repeat,
  rocket: Rocket,
  save: Save,
  scan: ScanSearch,
  scroll: ScrollText,
  server: Server,
  settings: Settings,
  shield: ShieldCheck,
  'shield-check': ShieldCheck,
  sliders: SlidersHorizontal,
  smartphone: Smartphone,
  sparkles: Sparkles,
  star: Star,
  sunrise: Sunrise,
  table: Table2,
  terminal: Terminal,
  timer: Timer,
  'trending-up': TrendingUp,
  'user-cog': UserCog,
  user: UserCircle,
  users: Users,
  wand: Wand2,
  'wand-2': Wand2,
  workflow: Workflow,
  zap: Zap,
} satisfies Record<string, LucideIcon>

export type IconName = keyof typeof ICONS

/** Resolve an icon by name, falling back to the checklist glyph (warns in dev). */
export function iconFor(name: string): LucideIcon {
  const found = ICONS[name as IconName]
  if (!found && typeof console !== 'undefined' && process.env.NODE_ENV !== 'production') {
    console.warn(`[icons] unknown icon "${name}", falling back to checklist`)
  }
  return found ?? ListChecks
}

/** Names used directly by the navigation config and feature payloads. */
export const dashboard = LayoutDashboard
export const products = Package
export const changes = Activity
export const analytics = BarChart3
export const pipeline = Gauge
export const categories = FolderTree
export const catalog = Building2
export const quality = ShieldCheck
export const sources = Boxes
export const query = Terminal
export const features = ListChecks
export const alerts = AlertTriangle
export const account = UserCircle
export const settingsIcon = Settings
export const users = Users
export const audit = Filter
