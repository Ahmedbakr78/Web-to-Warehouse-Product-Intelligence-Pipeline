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
  BarChart3,
  Blocks,
  BookOpen,
  Boxes,
  Braces,
  Building2,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Cloud,
  Code2,
  Compass,
  Database,
  FileSearch,
  Filter,
  Fingerprint,
  FlaskConical,
  FolderTree,
  Gauge,
  GitCompare,
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
  Plug,
  Radar,
  RefreshCw,
  Repeat,
  Save,
  ScanSearch,
  ScrollText,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  Table2,
  Terminal,
  Timer,
  TrendingUp,
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
  'bar-chart': BarChart3,
  blocks: Blocks,
  book: BookOpen,
  boxes: Boxes,
  braces: Braces,
  building: Building2,
  calendar: CalendarClock,
  'check-circle': CheckCircle2,
  clipboard: ClipboardCheck,
  cloud: Cloud,
  code: Code2,
  compass: Compass,
  database: Database,
  'file-search': FileSearch,
  filter: Filter,
  fingerprint: Fingerprint,
  flask: FlaskConical,
  'folder-tree': FolderTree,
  gauge: Gauge,
  compare: GitCompare,
  globe: Globe,
  download: HardDriveDownload,
  history: History,
  key: KeyRound,
  layers: Layers,
  dashboard: LayoutDashboard,
  grid: LayoutGrid,
  checklist: ListChecks,
  lock: Lock,
  mail: Mail,
  monitor: Monitor,
  network: Network,
  package: Package,
  palette: Palette,
  plug: Plug,
  radar: Radar,
  refresh: RefreshCw,
  repeat: Repeat,
  save: Save,
  scan: ScanSearch,
  scroll: ScrollText,
  server: Server,
  settings: Settings,
  shield: ShieldCheck,
  sliders: SlidersHorizontal,
  sparkles: Sparkles,
  star: Star,
  table: Table2,
  terminal: Terminal,
  timer: Timer,
  'trending-up': TrendingUp,
  user: UserCircle,
  users: Users,
  wand: Wand2,
  workflow: Workflow,
  zap: Zap,
} satisfies Record<string, LucideIcon>

export type IconName = keyof typeof ICONS

/** Resolve an icon by name, falling back to the checklist glyph. */
export function iconFor(name: string): LucideIcon {
  return ICONS[name as IconName] ?? ListChecks
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
