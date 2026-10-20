import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  Bell,
  Check,
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileDown,
  KeyRound,
  Keyboard,
  LogOut,
  Monitor,
  Moon,
  Palette,
  Pencil,
  Plus,
  RefreshCw,
  RotateCw,
  Save,
  Sparkles,
  Star,
  X,
  Settings2,
  Shield,
  ShieldCheck,
  Sun,
  Trash2,
  TriangleAlert,
  UserCircle,
} from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  Checkbox,
  DataTable,
  EmptyState,
  KeyValue,
  Modal,
  Segmented,
  Select,
  StatTile,
  Tabs,
  TextInput,
  Toggle,
  useToast,
} from '@/components/ui'
import {
  ACCENT_KEYS,
  ACCENTS,
  DENSITIES,
  FONT_SCALES,
  MOTION_MODES,
  THEME_MODES,
  setSilent,
  useAccent,
  useDensity,
  useDirection,
  useFontScale,
  useMotion,
  useTheme,
} from '@/lib/theme'
import type { Density, Direction, FontScale, MotionMode, ThemeMode } from '@/lib/theme'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { ALL_NAV_ITEMS } from '@/lib/nav'
import { localStore } from '@/lib/session'
import { formatDateTime, formatRelative, initials, titleCase, downloadCsv, downloadJson, toCsv } from '@/lib/format'
import SecurityPanel from '@/components/SecurityPanel'
import { AlertsPanel, PrivacyPanel } from '@/components/AccountPanels'

const AVATAR_COLORS = [
  '#4f46e5', '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626',
  '#7c3aed', '#db2777', '#334155', '#65a30d', '#b45309', '#be123c',
]

/** Representative colours used by the theme picker swatches. */
const THEME_SWATCH: Record<ThemeMode, { bg: string; surface: string; text: string; muted: string }> = {
  light: { bg: '#f6f7fb', surface: '#ffffff', text: '#0f172a', muted: '#64748b' },
  dark: { bg: '#070b18', surface: '#0f1629', text: '#e8eefc', muted: '#9aa8c7' },
  midnight: { bg: '#010409', surface: '#070d1a', text: '#dbe7ff', muted: '#93a6c8' },
  'high-contrast': { bg: '#ffffff', surface: '#ffffff', text: '#000000', muted: '#334155' },
  system: { bg: '#f6f7fb', surface: '#ffffff', text: '#0f172a', muted: '#64748b' },
}

export default function Account() {
  const [tab, setTab] = useState('profile')
  const { user, logout, refresh, saveAppearance } = useAuth()
  const { mode, isDark } = useTheme()
  const { density } = useDensity()
  const { accent } = useAccent()
  const { motion } = useMotion()
  const { direction } = useDirection()
  const { fontScale } = useFontScale()

  /**
   * Appearance controls apply instantly (so the preview is live) and then persist
   * to the profile, so the choice follows the user to another device or tab.
   */
  const applyThemeOption = (next: ThemeMode) => saveAppearance({ theme: next })
  const applyAccentOption = (next: string) => saveAppearance({ accent: next })
  const applyDensityOption = (next: Density) => saveAppearance({ density: next })
  const applyFontScaleOption = (next: FontScale) => saveAppearance({ font_scale: next })
  const applyMotionOption = (next: MotionMode) => saveAppearance({ motion: next })
  const applyDirectionOption = (next: Direction) => saveAppearance({ direction: next })
  /** Silent reload is applied instantly so the user sees the effect right away. */
  const applySilentOption = (next: boolean) => {
    setSilentReload(next)
    setSilent(next)
  }

  const toast = useToast()
  const queryClient = useQueryClient()
  const [startPage, setStartPage] = useState(() => localStore.get('account.startPage', '/'))
  const [avatarColor, setAvatarColor] = useState(user?.avatar_color ?? ACCENTS.indigo.base)

  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [jobTitle, setJobTitle] = useState(user?.job_title ?? '')
  const [department, setDepartment] = useState(user?.department ?? '')
  const [rowsPerPage, setRowsPerPage] = useState(user?.rows_per_page ?? 25)
  const [alertPct, setAlertPct] = useState(user?.price_change_alert_pct ?? 5)
  const navigate = useNavigate()
  const [briefingWindow, setBriefingWindow] = useState(() => (user?.preferences?.briefing_window as string) ?? '30')
  const [briefingSize, setBriefingSize] = useState(() => (user?.preferences?.briefing_size as string) ?? '6')
  const [silentReload, setSilentReload] = useState<boolean>(() => Boolean(user?.preferences?.silent_reload ?? true))
  const [autoRefresh, setAutoRefresh] = useState<string>(() => (user?.preferences?.auto_refresh as string) ?? 'off')
  const [defaultExportFormat, setDefaultExportFormat] = useState<string>(() => (user?.preferences?.default_export_format as string) ?? 'csv')
  const [defaultChartType, setDefaultChartType] = useState<string>(() => ((user?.preferences?.dashboard as any)?.chart_type as string) ?? 'area')
  const [defaultRange, setDefaultRange] = useState<string>(() => ((user?.preferences?.dashboard as any)?.default_range as string) ?? '30d')
  const [copyCodeOnClick, setCopyCodeOnClick] = useState<boolean>(() => Boolean(user?.preferences?.copy_code_on_click ?? true))

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [keyName, setKeyName] = useState('')
  const [issuedKey, setIssuedKey] = useState<string | null>(null)
  const [issuedKeyLabel, setIssuedKeyLabel] = useState('API key created')
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [editingKey, setEditingKey] = useState<any | null>(null)
  const [editName, setEditName] = useState('')
  const [editScopes, setEditScopes] = useState<string[]>([])
  const [editBudget, setEditBudget] = useState('')
  const [editExpiry, setEditExpiry] = useState('keep')
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState('')

  // Only used for the tab badge; the AlertsPanel owns the list itself.
  const alerts = useApiQuery(['alerts', 'badge'], endpoints.alerts, { staleTime: 60_000 })
  const activity = useApiQuery(['my-activity'], () => endpoints.myActivity({ page: 1, page_size: 25, days: 90 }), {
    staleTime: 60_000,
  })
  const watchlist = useApiQuery(['watchlist', 'account'], () => endpoints.watchlist(), { staleTime: 60_000 })
  const sessions = useApiQuery(
    ['sessions', 'account'],
    () => endpoints.sessions(localStorage.getItem('pip.session') ?? undefined),
    { staleTime: 30_000 },
  )

  const exportData = useMutation({
    mutationFn: () => endpoints.exportMyData(),
    onSuccess: (payload: any) => {
      downloadJson(`account-export-${user?.email ?? 'user'}.json`, payload)
      toast.success('Export downloaded', 'Your profile, keys, views, alerts and activity were included.')
    },
    onError: (error: Error) => toast.error('Could not export the data', error.message),
  })

  const deleteAccount = useMutation({
    mutationFn: () => endpoints.deleteMyAccount(deletePassword),
    onSuccess: () => {
      toast.success('Account deleted', 'All personal data was removed. Signing out.')
      setShowDeleteModal(false)
      logout()
    },
    onError: (error: Error) => toast.error('Could not delete the account', error.message),
  })

  useEffect(() => {
    if (!user) return
    setFullName(user.full_name)
    setJobTitle(user.job_title ?? '')
    setDepartment(user.department ?? '')
    setRowsPerPage(user.rows_per_page)
    setAlertPct(user.price_change_alert_pct)
    setAvatarColor(user.avatar_color ?? AVATAR_COLORS[0])
    if (user.preferences) {
      if (user.preferences.briefing_window) setBriefingWindow(user.preferences.briefing_window as string)
      if (user.preferences.briefing_size) setBriefingSize(user.preferences.briefing_size as string)
      if (user.preferences.silent_reload !== undefined) {
        const enabled = Boolean(user.preferences.silent_reload)
        setSilentReload(enabled)
        setSilent(enabled)
      }
    }
  }, [user])

  const apiKeys = useApiQuery(['api-keys', user?.user_id], () => endpoints.apiKeys(user!.user_id), {
    enabled: Boolean(user?.user_id),
  })

  const saveProfile = useMutation({
    mutationFn: () =>
      endpoints.updateMe({
        full_name: fullName,
        job_title: jobTitle,
        department,
        theme: mode,
        accent,
        density,
        rows_per_page: rowsPerPage,
        price_change_alert_pct: alertPct,
        avatar_color: avatarColor,
        preferences: {
          ...user?.preferences,
          start_page: startPage,
          motion,
          briefing_window: briefingWindow,
          briefing_size: briefingSize,
          silent_reload: silentReload,
          auto_refresh: autoRefresh,
          default_export_format: defaultExportFormat,
          dashboard: {
            ...((user?.preferences as any)?.dashboard ?? {}),
            chart_type: defaultChartType,
            default_range: defaultRange,
          },
          copy_code_on_click: copyCodeOnClick,
        } as Record<string, unknown>,
      }),
    onSuccess: async () => {
      localStore.set('account.startPage', startPage)
      await refresh()
      void queryClient.invalidateQueries()
      toast.success('Profile updated')
    },
    onError: (error: Error) => toast.error('Could not save the profile', error.message),
  })

  const changePassword = useMutation({
    mutationFn: () => endpoints.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.success('Password changed', 'Use the new password the next time you sign in.')
    },
    onError: (error: Error) => toast.error('Could not change the password', error.message),
  })

  const createKey = useMutation({
    mutationFn: () => endpoints.createApiKey(user!.user_id, keyName),
    onSuccess: (response: any) => {
      setIssuedKey(response.api_key)
      setIssuedKeyLabel('API key created')
      setKeyName('')
      setShowKeyModal(false)
      void apiKeys.refetch()
    },
    onError: (error: Error) => toast.error('Could not create the API key', error.message),
  })

  const revokeKey = useMutation({
    mutationFn: (keyId: number) => endpoints.revokeApiKey(user!.user_id, keyId),
    onSuccess: () => {
      void apiKeys.refetch()
      toast.success('API key revoked')
    },
    onError: (error: Error) => toast.error('Could not revoke the key', error.message),
  })

  const rotateKey = useMutation({
    mutationFn: (keyId: number) => endpoints.rotateApiKey(user!.user_id, keyId),
    onSuccess: (response: any) => {
      setIssuedKey(response.api_key)
      setIssuedKeyLabel('API key rotated - update your integrations')
      void apiKeys.refetch()
      toast.success('API key rotated', 'The old secret stopped working immediately.')
    },
    onError: (error: Error) => toast.error('Could not rotate the key', error.message),
  })

  const scopesQuery = useApiQuery(['scopes', 'account'], endpoints.myScopes, { staleTime: 300_000 })

  const openKeyEditor = (row: any) => {
    setEditingKey(row)
    setEditName(row.name ?? '')
    // `null` upstream means "everything the owner can do": expand it to the
    // explicit grantable list so unchecking boxes can only narrow rights.
    const grantable = scopesQuery.data?.grantable ?? scopesQuery.data?.scopes ?? []
    setEditScopes(Array.isArray(row.scopes) ? [...row.scopes] : [...grantable])
    setEditBudget(String(row.rate_limit_per_minute ?? ''))
    setEditExpiry('keep')
  }

  const saveKeyEdit = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {}
      const name = editName.trim()
      if (name && name !== editingKey?.name) payload.name = name
      const budget = Number(editBudget)
      if (editBudget.trim() && Number.isFinite(budget) && budget >= 1) payload.rate_limit_per_minute = Math.floor(budget)
      const current = new Set<string>(Array.isArray(editingKey?.scopes) ? editingKey.scopes : [])
      const next = new Set<string>(editScopes)
      if (current.size !== next.size || [...current].some((scope) => !next.has(scope))) {
        payload.scopes = [...next]
      }
      if (editExpiry === 'never') payload.remove_expiry = true
      else if (editExpiry !== 'keep') payload.expires_in_days = Number(editExpiry)
      return endpoints.updateApiKey(user!.user_id, editingKey.key_id, payload)
    },
    onSuccess: () => {
      setEditingKey(null)
      void apiKeys.refetch()
      toast.success('API key updated')
    },
    onError: (error: Error) => toast.error('Could not update the key', error.message),
  })

  const passwordProblems = [
    { ok: newPassword.length >= 10, label: 'At least 10 characters' },
    { ok: /\d/.test(newPassword), label: 'Contains a digit' },
    { ok: /[A-Z]/.test(newPassword), label: 'Contains an uppercase letter' },
    { ok: /[a-z]/.test(newPassword), label: 'Contains a lowercase letter' },
    { ok: /[^A-Za-z0-9]/.test(newPassword), label: 'Contains a symbol' },
  ]

  if (!user) return null

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------- profile header */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <span
            className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl text-xl font-bold text-white"
            style={{ backgroundColor: avatarColor }}
          >
            {initials(user.full_name)}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold">{user.full_name}</h2>
            <p className="truncate text-sm text-muted">{user.email}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <Badge tone={user.role === 'admin' ? 'danger' : user.role === 'analyst' ? 'info' : 'neutral'}>{user.role}</Badge>
              {user.is_verified ? <Badge tone="success">verified</Badge> : null}
              {user.two_factor_enabled ? <Badge tone="success" dot>2FA</Badge> : <Badge tone="warning">2FA off</Badge>}
              <Badge tone="neutral">{user.permissions.length} permissions</Badge>
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              <span className="stat-label mr-1">Avatar</span>
              {AVATAR_COLORS.map((color) => (
                <button
                  key={color}
                  onClick={() => {
                    setAvatarColor(color)
                    toast.info('Pick “Save changes” to apply the avatar everywhere')
                  }}
                  aria-label={`Avatar colour ${color}`}
                  title={color}
                  className={cn('h-5 w-5 rounded-full border-2', avatarColor === color ? 'border-ink' : 'border-transparent')}
                  style={{ backgroundColor: color }}
                />
              ))}
              <span className={cn('font-mono text-[10px] text-subtle')}>{avatarColor}</span>
            </div>
          </div>
          <Button variant="secondary" icon={<LogOut className="h-4 w-4" />} onClick={logout}>
            Sign out
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Sign-ins" value={user.login_count} hint={user.last_login_at ? `Last ${formatRelative(user.last_login_at)}` : 'First session'} icon={<UserCircle className="h-4 w-4" />} />
        <StatTile label="Member since" value={user.created_at ? new Date(user.created_at).getFullYear() : '—'} hint={formatDateTime(user.created_at)} tone="info" />
        <StatTile label="API keys" value={apiKeys.data?.filter((key: any) => key.is_active).length ?? 0} hint="Active machine credentials" tone="neutral" />
        <StatTile label="Default page size" value={rowsPerPage} hint="Used by every paginated table" tone="success" />
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'profile', label: 'Profile', icon: <UserCircle className="h-4 w-4" /> },
          { id: 'appearance', label: 'Appearance', icon: <Palette className="h-4 w-4" /> },
          { id: 'security', label: 'Security', icon: <Shield className="h-4 w-4" /> },
          { id: 'devices', label: 'Devices & 2FA', icon: <ShieldCheck className="h-4 w-4" /> },
          { id: 'api', label: 'API keys', count: apiKeys.data?.length ?? 0, icon: <KeyRound className="h-4 w-4" /> },
          { id: 'alerts', label: 'Alerts', count: alerts.data?.length ?? 0, icon: <Bell className="h-4 w-4" /> },
          { id: 'watchlist', label: 'Watchlist', count: (watchlist.data?.product_ids ?? []).length, icon: <Star className="h-4 w-4" /> },
          { id: 'sessions', label: 'Sessions', count: sessions.data?.active ?? 0, icon: <Monitor className="h-4 w-4" /> },
          { id: 'shortcuts', label: 'Shortcuts', icon: <Keyboard className="h-4 w-4" /> },
          { id: 'activity', label: 'Activity', icon: <Activity className="h-4 w-4" /> },
          { id: 'data', label: 'Data & privacy', icon: <Download className="h-4 w-4" /> },
          { id: 'prefs', label: 'Preferences', icon: <Settings2 className="h-4 w-4" /> },
        ]}
      />

      {tab === 'profile' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader title="Personal details" subtitle="Stored in the warehouse and used across the API" icon={<UserCircle className="h-4 w-4" />} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <p className="stat-label mb-1.5">Full name</p>
                <TextInput value={fullName} onChange={(event) => setFullName(event.target.value)} />
              </div>
              <div>
                <p className="stat-label mb-1.5">Email</p>
                <TextInput value={user.email} disabled />
              </div>
              <div>
                <p className="stat-label mb-1.5">Job title</p>
                <TextInput value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} placeholder="e.g. Pricing Analyst" />
              </div>
              <div>
                <p className="stat-label mb-1.5">Department</p>
                <TextInput value={department} onChange={(event) => setDepartment(event.target.value)} placeholder="e.g. Merchandising" />
              </div>
            </div>

            <div className="mt-4 flex justify-end">
              <Button variant="primary" icon={<Save className="h-4 w-4" />} loading={saveProfile.isPending} onClick={() => saveProfile.mutate()}>
                Save changes
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader title="Preferences" subtitle="Applied to every screen" icon={<Palette className="h-4 w-4" />} />
            <div className="space-y-3">
              <div>
                <p className="stat-label mb-1.5">Rows per page</p>
                <Select value={String(rowsPerPage)} onChange={(event) => setRowsPerPage(Number(event.target.value))}>
                  {[10, 25, 50, 100, 200].map((size) => (
                    <option key={size} value={String(size)}>
                      {size}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <p className="stat-label mb-1.5">Start page after sign-in</p>
                <Select value={startPage} onChange={(event) => setStartPage(event.target.value)}>
                  <option value="/">Dashboard</option>
                  {ALL_NAV_ITEMS.filter((item) => item.to !== '/').map((item) => (
                    <option key={item.to} value={item.to}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <p className="stat-label mb-1.5">Default alert threshold: {alertPct}%</p>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={alertPct}
                  onChange={(event) => setAlertPct(Number(event.target.value))}
                  className="w-full accent-brand-600"
                />
                <p className="mt-1 text-[11px] text-subtle">Prefills the threshold when you create a new price rule.</p>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <Button variant="primary" icon={<Save className="h-4 w-4" />} loading={saveProfile.isPending} onClick={() => saveProfile.mutate()}>
                Save preferences
              </Button>
            </div>
          </Card>

          <Card className="xl:col-span-3">
            <CardHeader title="Permissions" subtitle={`Role: ${user.role}`} icon={<Shield className="h-4 w-4" />} />
            <div className="flex flex-wrap gap-1.5">
              {user.permissions.map((permission) => (
                <Badge key={permission} tone={permission.includes('manage') || permission === 'run_pipeline' ? 'brand' : 'neutral'}>
                  {permission}
                </Badge>
              ))}
            </div>
          </Card>
        </div>
      ) : null}

      {tab === 'appearance' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader
              title="Theme"
              subtitle="Five palettes - system follows the operating system setting"
              icon={isDark ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {THEME_MODES.map((option) => (
                <button
                  key={option.id}
                  onClick={() => applyThemeOption(option.id)}
                  title={option.hint}
                  aria-pressed={mode === option.id}
                  className={cn(
                    'group flex flex-col items-start gap-2 rounded-xl border-2 p-2 text-left',
                    mode === option.id ? 'border-brand-500 brand-soft' : 'border-line hover:border-line-strong',
                  )}
                >
                  {/* Miniature of the real palette so the choice is visual, not textual. */}
                  <span className="flex h-12 w-full overflow-hidden rounded-lg border border-line">
                    <span
                      className="w-1/3"
                      style={{ backgroundColor: THEME_SWATCH[option.id].bg }}
                    />
                    <span
                      className="w-1/3"
                      style={{ backgroundColor: THEME_SWATCH[option.id].surface }}
                    />
                    <span className="flex w-1/3 flex-col justify-center gap-1 p-1" style={{ backgroundColor: THEME_SWATCH[option.id].surface }}>
                      <span className="h-1 w-3/4 rounded" style={{ backgroundColor: THEME_SWATCH[option.id].text }} />
                      <span className="h-1 w-1/2 rounded" style={{ backgroundColor: THEME_SWATCH[option.id].muted }} />
                      <span className="h-1.5 w-1/3 rounded" style={{ backgroundColor: '#4f46e5' }} />
                    </span>
                  </span>
                  <span>
                    <span className="block text-xs font-medium text-ink">{option.label}</span>
                    <span className="block text-[10px] leading-tight text-subtle">{option.hint}</span>
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-subtle">
              Active palette: <code className="rounded bg-surface-3 px-1 font-mono">{mode}</code>
              {mode === 'system' ? ` → ${isDark ? 'dark' : 'light'} (from your operating system)` : ''}
            </p>
          </Card>

          <Card>
            <CardHeader title="Accent, density and motion" subtitle="Brand colour, spacing and animation policy" icon={<Palette className="h-4 w-4" />} />
            <div className="space-y-4">
              <div>
                <p className="stat-label mb-1.5">Accent colour ({ACCENT_KEYS.length} presets)</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(ACCENTS).map(([key, entry]) => (
                    <button
                      key={key}
                      onClick={() => applyAccentOption(key)}
                      aria-label={entry.name}
                      title={entry.name}
                      aria-pressed={accent === key}
                      className={cn(
                        'h-8 w-8 rounded-lg border-2',
                        accent === key ? 'border-ink ring-2 ring-brand-500/40' : 'border-transparent',
                      )}
                      style={{ backgroundColor: entry.base }}
                    />
                  ))}
                </div>
              </div>

              <div>
                <p className="stat-label mb-1.5">Density</p>
                <Segmented
                  options={DENSITIES.map((option) => ({ id: option.id, label: option.label }))}
                  value={density}
                  onChange={(value) => applyDensityOption(value as Density)}
                />
                <p className="mt-1.5 text-[11px] text-subtle">
                  {DENSITIES.find((option) => option.id === density)?.hint}
                </p>
              </div>

              <div>
                <p className="stat-label mb-1.5">Text size</p>
                <Segmented
                  options={FONT_SCALES.map((option) => ({ id: option.id, label: option.label }))}
                  value={fontScale}
                  onChange={(value) => applyFontScaleOption(value as FontScale)}
                />
                <p className="mt-1.5 text-[11px] text-subtle">
                  Independent of density, so you can have dense rows and large text at once.
                </p>
              </div>

              <div>
                <p className="stat-label mb-1.5">Motion</p>
                <Segmented
                  options={MOTION_MODES.map((option) => ({ id: option.id, label: option.label }))}
                  value={motion}
                  onChange={(value) => applyMotionOption(value as MotionMode)}
                />
                <p className="mt-1.5 text-[11px] text-subtle">
                  {MOTION_MODES.find((option) => option.id === motion)?.hint}. Navigation never animates
                  regardless of this setting - there is no page transition and no smooth scroll.
                </p>
              </div>

              <div>
                <p className="stat-label mb-1.5">Reading direction</p>
                <Segmented
                  options={[
                    { id: 'ltr', label: 'Left to right' },
                    { id: 'rtl', label: 'Right to left' },
                  ]}
                  value={direction}
                  onChange={(value) => applyDirectionOption(value as Direction)}
                />
                <p className="mt-1.5 text-[11px] text-subtle">
                  The whole layout mirrors using CSS logical properties.
                </p>
              </div>

              <div className="rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
                Appearance is applied before the first paint, so reloading never flashes the wrong theme. Every
                choice is saved to your profile as well as this browser, so a new device or a new tab inherits it
                immediately.
              </div>
            </div>
          </Card>
        </div>
      ) : null}

      {tab === 'security' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader title="Change password" subtitle="Argon2id hashed, never stored in plain text" icon={<KeyRound className="h-4 w-4" />} />
            <div className="space-y-3">
              <div>
                <p className="stat-label mb-1.5">Current password</p>
                <TextInput type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" />
              </div>
              <div>
                <p className="stat-label mb-1.5">New password</p>
                <div className="relative">
                  <TextInput
                    type={showPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    autoComplete="new-password"
                    className="pr-10"
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
              <div>
                <p className="stat-label mb-1.5">Confirm new password</p>
                <TextInput type={showPassword ? 'text' : 'password'} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" />
              </div>

              <ul className="space-y-1">
                {passwordProblems.map((problem) => (
                  <li key={problem.label} className="flex items-center gap-2 text-xs">
                    <span className={cn('h-1.5 w-1.5 rounded-full', problem.ok ? 'bg-success' : 'bg-surface-3')} aria-hidden />
                    <span className={problem.ok ? 'text-muted' : 'text-subtle'}>{problem.label}</span>
                  </li>
                ))}
              </ul>

              <Button
                variant="primary"
                icon={<KeyRound className="h-4 w-4" />}
                loading={changePassword.isPending}
                disabled={!currentPassword || newPassword !== confirmPassword || passwordProblems.some((problem) => !problem.ok)}
                onClick={() => changePassword.mutate()}
              >
                Update password
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader title="Session security" subtitle="How this account is protected" icon={<Shield className="h-4 w-4" />} />
            <KeyValue
              items={[
                { label: 'Password hashing', value: 'Argon2id (memory-hard)' },
                { label: 'Token type', value: 'JWT HS256 access + refresh' },
                { label: 'Token lifetime', value: '12 h access / 30 d refresh' },
                { label: 'Brute-force protection', value: '5 failed attempts → 15 min lock' },
                { label: 'Two-factor authentication', value: user.two_factor_enabled ? 'Enabled' : 'Not enabled' },
                { label: 'Last sign-in', value: formatDateTime(user.last_login_at) },
                { label: 'Role', value: titleCase(user.role) },
              ]}
            />
            <div className="mt-4 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
              Every mutating request is written to <code className="rounded bg-surface-3 px-1">app_audit_log</code> with the
              user, action, IP address and user agent. Admin screens additionally require the matching permission, so a
              viewer account can never reach them even with a valid token.
            </div>
          </Card>
        </div>
      ) : null}

      {tab === 'devices' ? <SecurityPanel /> : null}

      {tab === 'api' ? (
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
            <CardHeader
              title="API keys"
              subtitle="Machine-to-machine credentials: send them as `Authorization: Bearer pip_…`"
              icon={<KeyRound className="h-4 w-4" />}
            />
            <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setShowKeyModal(true)}>
              New key
            </Button>
          </div>
          {apiKeys.data?.length ? (
            <DataTable
              rows={apiKeys.data}
              rowKey={(row: any) => row.key_id}
              emptyMessage="No API keys"
              columns={[
                { key: 'name', header: 'Name', render: (row: any) => <span className="font-medium">{row.name}</span> },
                { key: 'prefix', header: 'Prefix', render: (row: any) => <span className="font-mono text-xs">{row.prefix}…</span> },
                {
                  key: 'scopes',
                  header: 'Scopes',
                  hideBelow: 'lg',
                  render: (row: any) =>
                    Array.isArray(row.scopes) && row.scopes.length ? (
                      <span className="flex max-w-56 flex-wrap gap-1">
                        {row.scopes.slice(0, 3).map((scope: string) => (
                          <Badge key={scope} tone="neutral">{scope}</Badge>
                        ))}
                        {row.scopes.length > 3 ? <Badge tone="neutral">+{row.scopes.length - 3}</Badge> : null}
                      </span>
                    ) : (
                      <span className="text-xs text-subtle">Full access</span>
                    ),
                },
                {
                  key: 'status',
                  header: 'Status',
                  render: (row: any) => (
                    <Badge tone={row.is_active ? (row.expires_at && new Date(row.expires_at) < new Date() ? 'danger' : 'success') : 'neutral'}>
                      {row.is_active ? 'active' : 'revoked'}
                    </Badge>
                  ),
                },
                { key: 'usage', header: 'Requests', align: 'right', render: (row: any) => row.usage_count ?? 0 },
                { key: 'last', header: 'Last used', align: 'right', render: (row: any) => (row.last_used_at ? formatRelative(row.last_used_at) : '—') },
                {
                  key: 'expires',
                  header: 'Expires',
                  align: 'right',
                  hideBelow: 'md',
                  render: (row: any) =>
                    row.expires_at ? (
                      <span title={formatDateTime(row.expires_at)}>{formatRelative(row.expires_at)}</span>
                    ) : (
                      <span className="text-xs text-subtle">Never</span>
                    ),
                },
                {
                  key: 'actions',
                  header: '',
                  align: 'right',
                  render: (row: any) => (
                    <span className="inline-flex items-center gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<RotateCw className="h-3.5 w-3.5" />}
                        loading={rotateKey.isPending}
                        title="Rotate: issue a new secret, revoke the old one"
                        onClick={() => rotateKey.mutate(row.key_id)}
                      >
                        Rotate
                      </Button>
                      <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openKeyEditor(row)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Trash2 className="h-3.5 w-3.5" />}
                        loading={revokeKey.isPending}
                        onClick={() => revokeKey.mutate(row.key_id)}
                      >
                        Revoke
                      </Button>
                    </span>
                  ),
                },
              ]}
            />
          ) : (
            <div className="px-4 pb-6">
              <KeyValue
                items={[
                  { label: 'Auth header', value: <code className="font-mono text-xs">Authorization: Bearer pip_…</code> },
                  { label: 'Example', value: <code className="font-mono text-xs">curl -H &quot;Authorization: Bearer $KEY&quot; localhost:8000/api/v1/analytics/kpi</code> },
                ]}
              />
            </div>
          )}
        </Card>
      ) : null}

      {tab === 'alerts' ? <AlertsPanel /> : null}

      {tab === 'watchlist' ? (
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
            <CardHeader
              title="Watchlist"
              subtitle="Starred products — manage from Products or the detail screen, export here"
              icon={<Star className="h-4 w-4" />}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                icon={<Download className="h-4 w-4" />}
                disabled={!(watchlist.data?.product_ids ?? []).length}
                onClick={() => {
                  downloadJson('watchlist.json', watchlist.data)
                  toast.success('Watchlist exported', `${(watchlist.data?.product_ids ?? []).length} products saved.`)
                }}
              >
                Export JSON
              </Button>
              <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => void watchlist.refetch()}>
                Refresh
              </Button>
            </div>
          </div>
          {(watchlist.data?.product_ids ?? []).length ? (
            <div className="px-4 pb-5">
              <KeyValue
                items={[
                  { label: 'Watched products', value: String((watchlist.data?.product_ids ?? []).length) },
                  { label: 'Tip', value: 'Open Products, filter by “Watched only”, then export CSV for price tracking.' },
                ]}
              />
            </div>
          ) : (
            <div className="px-4 pb-6">
              <EmptyState title="No watched products" message="Star products to track their prices here." icon={<Star className="h-6 w-6" />} />
            </div>
          )}
        </Card>
      ) : null}

      {tab === 'sessions' ? (
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
            <CardHeader
              title="Sessions"
              subtitle="Every device signed in as you — revoke anything unfamiliar"
              icon={<Monitor className="h-4 w-4" />}
            />
            <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => void sessions.refetch()}>
              Refresh
            </Button>
          </div>
          {sessions.data?.sessions?.length ? (
            <DataTable
              rows={sessions.data.sessions}
              rowKey={(row: any, i: number) => row.session_key ?? i}
              emptyMessage="No sessions"
              columns={[
                { key: 'device', header: 'Device', render: (row: any) => <span className="font-medium">{row.user_agent?.slice(0, 48) ?? 'Unknown device'}</span> },
                { key: 'ip', header: 'IP', hideBelow: 'md', render: (row: any) => <span className="font-mono text-xs">{row.ip_address ?? '—'}</span> },
                { key: 'seen', header: 'Last seen', align: 'right', render: (row: any) => (row.last_seen_at ? formatRelative(row.last_seen_at) : '—') },
                { key: 'cur', header: 'Current', align: 'right', render: (row: any) => (row.is_current ? <Badge tone="success">this device</Badge> : <Badge tone="neutral">active</Badge>) },
              ]}
            />
          ) : (
            <div className="px-4 pb-6">
              <EmptyState title="No other sessions" message="Only this device is signed in." icon={<Monitor className="h-6 w-6" />} />
            </div>
          )}
        </Card>
      ) : null}

      {tab === 'shortcuts' ? (
        <Card>
          <CardHeader title="Keyboard shortcuts" subtitle="Silent, keyboard-first navigation — no animations, no page flashes" icon={<Keyboard className="h-4 w-4" />} />
          <KeyValue
            items={[
              { label: '/', value: 'Open command palette (screens + live products + actions)' },
              { label: 'Ctrl/⌘ K', value: 'Same as / — quick jump anywhere' },
              { label: 'Esc', value: 'Close drawer, modal or palette' },
              { label: 'Click a column header', value: 'Sort any table; state persists per screen' },
              { label: 'Tip', value: 'Palette actions: toggle theme, collapse sidebar, sign out — all without reload.' },
            ]}
          />
        </Card>
      ) : null}

      {tab === 'activity' ? (
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
            <CardHeader
              title="Recent activity"
              subtitle="Everything you did in the last 90 days - sign-ins, key changes and settings updates"
              icon={<Activity className="h-4 w-4" />}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                icon={<Download className="h-4 w-4" />}
                disabled={!activity.data?.items?.length}
                onClick={() => {
                  const rows = (activity.data?.items ?? []).map((row: any) => [
                    row.created_at ?? '',
                    row.action ?? '',
                    row.entity_type ? `${row.entity_type}${row.entity_id ? ` #${row.entity_id}` : ''}` : '',
                    row.status ?? '',
                    row.ip_address ?? '',
                  ])
                  downloadCsv(
                    'my-activity.csv',
                    toCsv(['when', 'action', 'target', 'status', 'ip'], rows),
                  )
                  toast.success('Activity exported', `${rows.length} rows saved as CSV.`)
                }}
              >
                Export CSV
              </Button>
              <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => void activity.refetch()}>
                Refresh
              </Button>
            </div>
          </div>
          {activity.data?.items?.length ? (
            <DataTable
              rows={activity.data.items}
              rowKey={(row: any) => row.audit_id}
              emptyMessage="No activity in this window"
              columns={[
                {
                  key: 'action',
                  header: 'Action',
                  render: (row: any) => <span className="font-medium">{titleCase(row.action.replace(/[._]/g, ' '))}</span>,
                },
                { key: 'entity', header: 'Target', render: (row: any) => (row.entity_type ? `${row.entity_type}${row.entity_id ? ` #${row.entity_id}` : ''}` : '—') },
                { key: 'status', header: 'Status', render: (row: any) => <Badge tone={row.status === 'failure' ? 'danger' : row.status === 'success' ? 'success' : 'neutral'}>{row.status}</Badge> },
                { key: 'ip', header: 'IP', hideBelow: 'md', render: (row: any) => <span className="font-mono text-xs">{row.ip_address ?? '—'}</span> },
                { key: 'when', header: 'When', align: 'right', render: (row: any) => formatRelative(row.created_at) },
              ]}
            />
          ) : (
            <div className="px-4 pb-6">
              <EmptyState
                icon={<Activity className="h-6 w-6" />}
                title="No recent activity"
                message="Actions you perform are recorded here automatically."
              />
            </div>
          )}
        </Card>
      ) : null}

      {tab === 'data' ? (
        <PrivacyPanel
          onExport={() => exportData.mutate()}
          exporting={exportData.isPending}
          onDelete={() => setShowDeleteModal(true)}
        />
      ) : null}

      {tab === 'prefs' ? (
        <>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader title="Workspace defaults" subtitle="Applied instantly to every table and landing route" icon={<Settings2 className="h-4 w-4" />} />
            <div className="space-y-3">
              <div>
                <p className="stat-label mb-1.5">Start page after sign-in</p>
                <Select value={startPage} onChange={(event) => setStartPage(event.target.value)}>
                  <option value="/">Dashboard</option>
                  {ALL_NAV_ITEMS.filter((item) => item.to !== '/').map((item) => (
                    <option key={item.to} value={item.to}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="stat-label mb-1.5">Rows per page</p>
                  <Select value={String(rowsPerPage)} onChange={(event) => setRowsPerPage(Number(event.target.value))}>
                    {[10, 25, 50, 100, 200].map((size) => (
                      <option key={size} value={String(size)}>
                        {size}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <p className="stat-label mb-1.5">Auto-refresh cadence</p>
                  <Select value={autoRefresh} onChange={(event) => setAutoRefresh(event.target.value)}>
                    <option value="off">Off (manual only)</option>
                    <option value="15s">Every 15 seconds</option>
                    <option value="30s">Every 30 seconds</option>
                    <option value="1m">Every minute</option>
                    <option value="5m">Every 5 minutes</option>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="stat-label mb-1.5">Briefing window</p>
                  <Select value={briefingWindow} onChange={(event) => setBriefingWindow(event.target.value)}>
                    <option value="7">Last 7 days</option>
                    <option value="30">Last 30 days</option>
                    <option value="90">Last 90 days</option>
                    <option value="180">Last 180 days</option>
                  </Select>
                </div>
                <div>
                  <p className="stat-label mb-1.5">Briefing queue size</p>
                  <Select value={briefingSize} onChange={(event) => setBriefingSize(event.target.value)}>
                    <option value="4">4 items</option>
                    <option value="6">6 items</option>
                    <option value="8">8 items</option>
                    <option value="10">10 items</option>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <p className="stat-label mb-1.5">Default chart visualization</p>
                  <Select value={defaultChartType} onChange={(event) => setDefaultChartType(event.target.value)}>
                    <option value="area">Smooth Area Chart</option>
                    <option value="line">Stepped Line Chart</option>
                    <option value="bar">Bar Chart</option>
                  </Select>
                </div>
                <div>
                  <p className="stat-label mb-1.5">Default time range</p>
                  <Select value={defaultRange} onChange={(event) => setDefaultRange(event.target.value)}>
                    <option value="7d">Last 7 days</option>
                    <option value="30d">Last 30 days</option>
                    <option value="90d">Last 90 days</option>
                    <option value="365d">Last 365 days</option>
                  </Select>
                </div>
                <div>
                  <p className="stat-label mb-1.5">Default export format</p>
                  <Select value={defaultExportFormat} onChange={(event) => setDefaultExportFormat(event.target.value)}>
                    <option value="csv">CSV (Comma-Separated)</option>
                    <option value="json">JSON (Structured)</option>
                    <option value="ndjson">NDJSON (Line-Delimited)</option>
                  </Select>
                </div>
              </div>
              <div>
                <p className="stat-label mb-1.5">Default alert threshold: {alertPct}%</p>
                <input type="range" min={1} max={50} value={alertPct} onChange={(event) => setAlertPct(Number(event.target.value))} className="w-full accent-brand-600" aria-label="Default alert threshold" />
              </div>
              <div className="pt-2 border-t border-border/50 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-ink">Silent app reload</p>
                    <p className="text-xs text-muted">Quiet background refresh without intrusive spinners or jarring animations</p>
                  </div>
                  <Toggle checked={silentReload} onChange={applySilentOption} />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-ink">Copy code snippets on click</p>
                    <p className="text-xs text-muted">Instant clipboard copying for SQL statements, IDs, and tokens</p>
                  </div>
                  <Toggle checked={copyCodeOnClick} onChange={setCopyCodeOnClick} />
                </div>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <Button variant="primary" icon={<Save className="h-4 w-4" />} loading={saveProfile.isPending} onClick={() => saveProfile.mutate()}>
                Save preferences
              </Button>
            </div>
          </Card>
          <Card>
            <CardHeader title="Shortcuts & keyboard navigation" subtitle="Keyboard-first workflow for power users" icon={<Keyboard className="h-4 w-4" />} />
            <div className="space-y-2 text-sm">
              <KeyValue
                items={[
                  { label: 'Command palette', value: '/ or Ctrl/Cmd-K' },
                  { label: 'Toggle sidebar', value: 'Ctrl/Cmd-B' },
                  { label: 'Collapse rail', value: '[ key' },
                  { label: 'Expand rail', value: '] key' },
                  { label: 'Shortcut reference', value: '? key' },
                  { label: 'Close dialogs', value: 'Esc' },
                ]}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" icon={<ExternalLink className="h-4 w-4" />} onClick={() => navigate('/features')}>
                Explore Feature Catalogue
              </Button>
              <Button variant="ghost" icon={<RefreshCw className="h-4 w-4" />} onClick={() => saveProfile.mutate()}>
                Sync to server
              </Button>
            </div>
          </Card>
        </div>

        {/* --------------------------------------------------------- Feature list */}
        <Card>
          <CardHeader
            title="Platform feature catalogue"
            subtitle="Everything this application can do — 604 live features across 40 groups"
            icon={<Sparkles className="h-4 w-4" />}
          />
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-3 text-xs">
            {[
              {
                group: '📊 Dashboard & Analytics',
                features: [
                  'Real-time KPI cards (products, prices, changes, quality)',
                  'Interactive 7d / 30d / 90d / 180d time windows',
                  'Market price & coverage area trend chart',
                  'Availability mix donut chart',
                  'Price change bar chart (increases vs decreases)',
                  'Average rating trend line',
                  'Top price movers leaderboard',
                  'Change summary (new / removed / recurring / recategorised)',
                  'Pipeline health card with latest run stats',
                  'Export dashboard snapshot to CSV or JSON',
                ],
              },
              {
                group: '🛒 Products',
                features: [
                  'Full canonical product catalogue (5 000+ products)',
                  'Search, filter, sort, paginate any column',
                  'Product detail page with full history',
                  'Price history sparkline per product',
                  'Source attribution and deduplication info',
                  'Availability and rating tracking',
                  'Category assignment and drift detection',
                  'Watchlist — pin products for fast access',
                  'Bulk export (CSV / JSON)',
                  'Direct link to product URL at source',
                ],
              },
              {
                group: '💰 Price Changes',
                features: [
                  'Full price change feed with magnitude bands',
                  'Increase / decrease / neutral direction badges',
                  'Percentage and absolute change columns',
                  'Change detected date and source',
                  'Filter by band: micro / minor / moderate / major / extreme',
                  'Price change alert rules per product or category',
                  'Historical change export',
                  'Category drift detection (products recategorised)',
                ],
              },
              {
                group: '🔬 Analytics & Forecasting',
                features: [
                  'KPI aggregation engine (avg, min, max, count)',
                  '12-rule data quality framework with scoring',
                  'Price forecast with confidence intervals',
                  'Anomaly detection on price series',
                  'Elasticity analysis per category',
                  'Price recommendation engine',
                  'Category leaderboards and rankings',
                  'SQL report runner with saved queries',
                  'Custom view builder with GROUP BY / FILTER / SORT',
                  'Scheduled recurring analytics reports',
                ],
              },
              {
                group: '🔧 Pipeline & Ingestion',
                features: [
                  '35+ real permitted data sources (no fakes)',
                  'robots.txt compliance with ETag revalidation',
                  'Rate limiting and politeness cache (30 min TTL)',
                  '9-stage ETL pipeline (extract → stage → transform → resolve → load → detect → aggregate → reconcile → quality)',
                  'Manual pipeline trigger from UI',
                  'Airflow DAG orchestration',
                  'Run history with per-stage timing',
                  'Source health monitoring',
                  'Deduplication via fuzzy matching',
                  'PostgreSQL + MySQL dual-database support',
                ],
              },
              {
                group: '🗄️ Database & Schema',
                features: [
                  '28+ warehouse tables, 23 analytical views',
                  'Historical price snapshot table (33 000+ rows)',
                  'Dimension tables: product, category, source, currency, date',
                  'Fact tables: price snapshot, change log, quality result',
                  'Catalog reconciliation against internal SKUs',
                  'Read-only SQL console (QueryLab)',
                  'Saved query library',
                  'Custom view builder (no SQL required)',
                  'CSV / JSON / NDJSON dataset exports',
                  'Full audit log of all mutations',
                ],
              },
              {
                group: '👤 Account & Security',
                features: [
                  'Profile: name, job title, department, avatar colour',
                  'Argon2id password hashing',
                  'JWT access (12 h) + refresh (30 d) tokens',
                  '2FA (TOTP) support',
                  'Brute-force protection (5 fails → 15 min lock)',
                  'Session management (active devices list)',
                  'API key management (create / rotate / revoke / edit scopes)',
                  'Per-key rate limiting and expiry',
                  'GDPR data export and account deletion',
                  'Role-based permissions (admin / analyst / viewer)',
                ],
              },
              {
                group: '🎨 Appearance & UX',
                features: [
                  '5 themes: Light, Dark, Midnight, High-contrast, System',
                  '12 accent colours',
                  '3 density modes: Compact / Comfortable / Spacious',
                  '5 font-size scales (XS → XL)',
                  '3 motion modes: Full / Reduced / None (silent reload)',
                  'LTR / RTL reading direction',
                  'Cross-tab appearance sync',
                  'Pre-paint flash prevention (no theme flicker)',
                  'Fully accessible (WCAG AA)',
                  'PWA-ready (installable, offline shell)',
                ],
              },
              {
                group: '🔔 Notifications & Webhooks',
                features: [
                  'In-app notification bell with unread count',
                  'Price change alert rules (threshold per product)',
                  'Signed outbound webhooks for pipeline and data events',
                  'Daily briefing digest',
                  'Server-Sent Events (SSE) for live run updates',
                  'WebSocket live KPI stream',
                  'Background job queue with progress + cancellation',
                  'Job live log streaming',
                ],
              },
              {
                group: '📄 Reports & Exports',
                features: [
                  'Executive summary report (HTML / PDF)',
                  'Price report with top movers',
                  'Data quality report with rule details',
                  'Catalog reconciliation report',
                  'Per-product detailed report',
                  'Scheduled report delivery',
                  'Bulk CSV / JSON / NDJSON exports',
                  'Export with custom column selection',
                  'API access to all reports',
                ],
              },
              {
                group: '🌐 API & Integration',
                features: [
                  'OpenAPI 3.1 spec at /openapi.json',
                  '173 documented API operations',
                  '18 domain modules (products, analytics, pipeline, forecast, quality, catalog, queries, builder, exports, reports, webhooks, jobs, stream, users, settings, audit, system, auth)',
                  'Bearer token auth (API key or JWT)',
                  'Per-key scope control and rate limiting',
                  'Machine-readable /api/v1/meta inventory',
                  'Feature catalogue at /api/v1/meta/features',
                  'Team credits at /api/v1/meta/team',
                  'Health and readiness probes',
                ],
              },
              {
                group: '⚙️ DevOps & Deployment',
                features: [
                  '6-service Docker Compose stack',
                  'PostgreSQL 16 + MySQL 8.4 databases',
                  'Airflow 2.10 scheduler',
                  'Nginx-served React 19 frontend',
                  'CI/CD with ruff lint + pytest + vitest',
                  'One-command deployment: ./run.sh',
                  'Automated schema migration and seed',
                  'Health checks on every container',
                  'Volume persistence across restarts',
                  'robots.txt compliance audit log',
                ],
              },
            ].map(({ group, features }) => (
              <div key={group} className="rounded-lg border border-line bg-surface-2 p-3">
                <p className="mb-2 text-[11px] font-semibold text-ink">{group}</p>
                <ul className="space-y-1">
                  {features.map((feature) => (
                    <li key={feature} className="flex items-start gap-1.5 text-[11px] text-muted">
                      <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-brand-500" aria-hidden />
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-4 text-[11px] text-subtle">
            Full live inventory: <code className="rounded bg-surface-3 px-1 font-mono">GET /api/v1/meta</code> · Features: <code className="rounded bg-surface-3 px-1 font-mono">GET /api/v1/meta/features</code>
          </p>
        </Card>
      </>
    ) : null}

      {/* ------------------------------------------------------------- modals */}
      <Modal
        open={showKeyModal}
        onClose={() => setShowKeyModal(false)}
        title="Create an API key"
        description="The key is shown once and cannot be retrieved later."
        size="sm"
        footer={
          <>
            <Button variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setShowKeyModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" icon={<Plus className="h-4 w-4" />} loading={createKey.isPending} disabled={!keyName.trim()} onClick={() => createKey.mutate()}>
              Create key
            </Button>
          </>
        }
      >
        <p className="stat-label mb-1.5">Key name</p>
        <TextInput value={keyName} onChange={(event) => setKeyName(event.target.value)} placeholder="e.g. Airflow integration" autoFocus />
      </Modal>

      <Modal
        open={Boolean(editingKey)}
        onClose={() => setEditingKey(null)}
        title={`Edit API key${editingKey?.name ? ` - ${editingKey.name}` : ''}`}
        description="Rename, rescope, change the per-minute budget or move the expiry. Empty fields keep their current values."
        size="md"
        footer={
          <>
            <Button variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setEditingKey(null)}>
              Cancel
            </Button>
            <Button variant="primary" icon={<Check className="h-4 w-4" />} loading={saveKeyEdit.isPending} disabled={!editName.trim()} onClick={() => saveKeyEdit.mutate()}>
              Save changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <p className="stat-label mb-1.5">Key name</p>
            <TextInput value={editName} onChange={(event) => setEditName(event.target.value)} placeholder="e.g. Airflow integration" autoFocus />
          </div>
          <div>
            <p className="stat-label mb-1.5">Scopes - empty means full access</p>
            {scopesQuery.isLoading ? (
              <p className="text-xs text-subtle">Loading scopes…</p>
            ) : (
              <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
                {(scopesQuery.data?.scopes ?? []).map((scope) => {
                  const grantable = scopesQuery.data?.grantable?.includes(scope) ?? true
                  return (
                    <Checkbox
                      key={scope}
                      label={<span className={cn(!grantable && 'text-subtle')} title={grantable ? scope : `${scope} - beyond your ${scopesQuery.data?.role} role`}>{scope}</span>}
                      checked={editScopes.includes(scope)}
                      onChange={(next) =>
                        setEditScopes((current) => (next ? [...current, scope] : current.filter((item) => item !== scope)))
                      }
                    />
                  )
                })}
              </div>
            )}
            {!((scopesQuery.data?.grantable ?? []).length === (scopesQuery.data?.scopes ?? []).length) && (
              <p className="mt-1.5 text-xs text-subtle">Greyed-out scopes sit above your {scopesQuery.data?.role} role and cannot be granted.</p>
            )}
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <p className="stat-label mb-1.5">Requests per minute</p>
              <TextInput value={editBudget} inputMode="numeric" onChange={(event) => setEditBudget(event.target.value.replace(/[^0-9]/g, ''))} placeholder="e.g. 240" />
            </div>
            <div>
              <p className="stat-label mb-1.5">Expiry</p>
              <Select value={editExpiry} onChange={(event) => setEditExpiry(event.target.value)}>
                <option value="keep">Keep current</option>
                <option value="30">30 days from now</option>
                <option value="90">90 days from now</option>
                <option value="365">1 year from now</option>
                <option value="never">Never expires</option>
              </Select>
            </div>
          </div>
        </div>
      </Modal>

      <Modal open={Boolean(issuedKey)} onClose={() => setIssuedKey(null)} title={issuedKeyLabel} size="sm">
        <div className="space-y-3">
          <div className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-xs text-warning">
            Copy this key now. For security reasons it is never displayed again - if you lose it, create a new one.
          </div>
          <div className="rounded-lg bg-surface-3 p-3">
            <code className="block break-all font-mono text-xs">{issuedKey}</code>
          </div>
          <Button
            variant="primary"
            icon={<Copy className="h-4 w-4" />}
            onClick={() => {
              navigator.clipboard?.writeText(issuedKey ?? '')
              toast.success('Copied to clipboard')
            }}
          >
            Copy key
          </Button>
        </div>
      </Modal>

      <Modal
        open={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title="Delete your account"
        description="This permanently removes your account and every personal record attached to it."
        size="sm"
        footer={
          <>
            <Button variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setShowDeleteModal(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              loading={deleteAccount.isPending}
              disabled={!deletePassword || deleteConfirm !== 'DELETE'}
              onClick={() => deleteAccount.mutate()}
            >
              Delete permanently
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-soft p-3 text-xs text-danger">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              This cannot be undone. Every API key stops working immediately, all sessions are revoked, and you will
              be signed out. Warehouse data is untouched because it is not owned by your account.
            </span>
          </div>
          <p className="flex items-start gap-2 text-[11px] leading-relaxed text-muted">
            <FileDown className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>Export your data first if you might want any of it afterwards.</span>
          </p>
          <div>
            <p className="stat-label mb-1.5">Confirm your password</p>
            <TextInput type="password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} autoComplete="current-password" autoFocus />
          </div>
          <div>
            <p className="stat-label mb-1.5">Type DELETE to confirm</p>
            <TextInput value={deleteConfirm} onChange={(event) => setDeleteConfirm(event.target.value)} placeholder="DELETE" />
          </div>
        </div>
      </Modal>
    </div>
  )
}