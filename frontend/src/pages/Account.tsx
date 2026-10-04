import { useEffect, useState } from 'react'
import {
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  LogOut,
  Moon,
  Palette,
  Save,
  Shield,
  Sun,
  Trash2,
  UserCircle,
} from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
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
import { ACCENTS, useAccent, useDensity, useMotion, useTheme } from '@/lib/theme'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { ALL_NAV_ITEMS } from '@/lib/nav'
import { localStore } from '@/lib/session'
import { formatDateTime, formatRelative, initials, titleCase } from '@/lib/format'

const AVATAR_COLORS = [
  '#4f46e5', '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626',
  '#7c3aed', '#db2777', '#334155', '#65a30d', '#b45309', '#be123c',
]

export default function Account() {
  const [tab, setTab] = useState('profile')
  const { user, logout, refresh } = useAuth()
  const { mode, setMode, isDark } = useTheme()
  const { density, setDensity } = useDensity()
  const { accent, setAccent } = useAccent()
  const { motion, setMotion } = useMotion()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [startPage, setStartPage] = useState(() => localStore.get('account.startPage', '/'))
  const [avatarColor, setAvatarColor] = useState(user?.avatar_color ?? ACCENTS.indigo.base)

  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [jobTitle, setJobTitle] = useState(user?.job_title ?? '')
  const [department, setDepartment] = useState(user?.department ?? '')
  const [timezone, setTimezone] = useState(user?.timezone ?? 'UTC')
  const [locale, setLocale] = useState(user?.locale ?? 'en')
  const [currency, setCurrency] = useState(user?.default_currency ?? 'USD')
  const [rowsPerPage, setRowsPerPage] = useState(user?.rows_per_page ?? 25)
  const [alertPct, setAlertPct] = useState(user?.price_change_alert_pct ?? 5)
  const [emailAlerts, setEmailAlerts] = useState(user?.email_alerts_enabled ?? false)
  const [weeklyDigest, setWeeklyDigest] = useState(user?.weekly_digest_enabled ?? false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [keyName, setKeyName] = useState('')
  const [issuedKey, setIssuedKey] = useState<string | null>(null)
  const [showKeyModal, setShowKeyModal] = useState(false)

  useEffect(() => {
    if (!user) return
    setFullName(user.full_name)
    setJobTitle(user.job_title ?? '')
    setDepartment(user.department ?? '')
    setTimezone(user.timezone)
    setLocale(user.locale)
    setCurrency(user.default_currency)
    setRowsPerPage(user.rows_per_page)
    setAlertPct(user.price_change_alert_pct)
    setEmailAlerts(user.email_alerts_enabled)
    setWeeklyDigest(user.weekly_digest_enabled)
    setAvatarColor(user.avatar_color ?? AVATAR_COLORS[0])
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
        timezone,
        locale,
        theme: mode,
        accent,
        density,
        rows_per_page: rowsPerPage,
        default_currency: currency,
        price_change_alert_pct: alertPct,
        email_alerts_enabled: emailAlerts,
        weekly_digest_enabled: weeklyDigest,
        avatar_color: avatarColor,
        preferences: {
          ...user?.preferences,
          start_page: startPage,
          motion,
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
        <StatTile label="Default page size" value={rowsPerPage} hint={`Alerts above ${alertPct}% movement`} tone="success" />
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'profile', label: 'Profile', icon: <UserCircle className="h-4 w-4" /> },
          { id: 'appearance', label: 'Appearance', icon: <Palette className="h-4 w-4" /> },
          { id: 'security', label: 'Security', icon: <Shield className="h-4 w-4" /> },
          { id: 'api', label: 'API keys', count: apiKeys.data?.length ?? 0, icon: <KeyRound className="h-4 w-4" /> },
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
              <div>
                <p className="stat-label mb-1.5">Timezone</p>
                <Select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                  {['UTC', 'Africa/Cairo', 'Europe/London', 'Europe/Berlin', 'Asia/Dubai', 'Asia/Kolkata', 'America/New_York'].map((zone) => (
                    <option key={zone} value={zone}>
                      {zone}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <p className="stat-label mb-1.5">Locale</p>
                <Select value={locale} onChange={(event) => setLocale(event.target.value)}>
                  <option value="en">English</option>
                  <option value="ar">العربية</option>
                  <option value="fr">Français</option>
                </Select>
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
                <p className="stat-label mb-1.5">Display currency</p>
                <Select value={currency} onChange={(event) => setCurrency(event.target.value)}>
                  {['USD', 'EUR', 'GBP', 'EGP', 'AED', 'SAR'].map((code) => (
                    <option key={code} value={code}>
                      {code}
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
                <p className="stat-label mb-1.5">Price alert threshold: {alertPct}%</p>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={alertPct}
                  onChange={(event) => setAlertPct(Number(event.target.value))}
                  className="w-full accent-brand-600"
                />
              </div>
              <Toggle checked={emailAlerts} onChange={setEmailAlerts} label="Email alerts" description="Send an email when an alert rule fires" />
              <Toggle checked={weeklyDigest} onChange={setWeeklyDigest} label="Weekly digest" description="Monday summary of price movements" />
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
            <CardHeader title="Theme" subtitle="system follows the operating system setting" icon={isDark ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />} />
            <Segmented
              options={[
                { id: 'light', label: 'Light' },
                { id: 'dark', label: 'Dark' },
                { id: 'system', label: 'System' },
              ]}
              value={mode}
              onChange={(value) => setMode(value as 'light' | 'dark' | 'system')}
            />
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-line bg-surface p-3">
                <p className="stat-label mb-2">Light</p>
                <div className="space-y-1.5">
                  <div className="h-4 w-3/4 rounded bg-surface-3" />
                  <div className="h-4 w-1/2 rounded bg-surface-3" />
                  <div className="h-6 w-20 rounded bg-brand-600" />
                </div>
              </div>
              <div className="rounded-xl border border-line bg-[#070b18] p-3">
                <p className="stat-label mb-2 text-[#e8eefc]">Dark</p>
                <div className="space-y-1.5">
                  <div className="h-4 w-3/4 rounded bg-[#1b2540]" />
                  <div className="h-4 w-1/2 rounded bg-[#1b2540]" />
                  <div className="h-6 w-20 rounded bg-brand-500" />
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Density and accent" subtitle="Comfortable spacing, custom brand colour" icon={<Palette className="h-4 w-4" />} />
            <div className="space-y-4">
              <div>
                <p className="stat-label mb-1.5">Density</p>
                <Segmented
                  options={[
                    { id: 'compact', label: 'Compact' },
                    { id: 'comfortable', label: 'Comfortable' },
                    { id: 'spacious', label: 'Spacious' },
                  ]}
                  value={density}
                  onChange={(value) => setDensity(value as 'compact' | 'comfortable' | 'spacious')}
                />
              </div>
              <div>
                <p className="stat-label mb-2">Accent colour</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(ACCENTS).map(([key, entry]) => (
                    <button
                      key={key}
                      onClick={() => setAccent(key)}
                      aria-label={entry.name}
                      title={entry.name}
                      className={cn(
                        'h-8 w-8 rounded-lg border-2',
                        accent === key ? 'border-ink' : 'border-transparent',
                      )}
                      style={{ backgroundColor: entry.base }}
                    />
                  ))}
                </div>
              </div>
              <div>
                <p className="stat-label mb-1.5">Motion</p>
                <Segmented
                  options={[
                    { id: 'auto', label: 'System' },
                    { id: 'reduced', label: 'Reduce motion' },
                  ]}
                  value={motion}
                  onChange={(value) => setMotion(value as 'auto' | 'reduced')}
                />
                <p className="mt-1.5 text-[11px] text-subtle">
                  Reduced keeps every transition instant, regardless of the operating system setting.
                </p>
              </div>
              <div className="rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
                Appearance is stored locally in <code className="rounded bg-surface-3 px-1">localStorage</code> and applied
                before the first paint, so there is no flash of the wrong theme on reload. Saving the profile also
                syncs the server-side preference so a new device inherits it.
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

      {tab === 'api' ? (
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
            <CardHeader
              title="API keys"
              subtitle="Machine-to-machine credentials: send them as `Authorization: Bearer pip_…`"
              icon={<KeyRound className="h-4 w-4" />}
            />
            <Button size="sm" variant="primary" onClick={() => setShowKeyModal(true)}>
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
                { key: 'expires', header: 'Expires', align: 'right', hideBelow: 'md', render: (row: any) => formatDateTime(row.expires_at) },
                {
                  key: 'actions',
                  header: '',
                  align: 'right',
                  render: (row: any) => (
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                      loading={revokeKey.isPending}
                      onClick={() => revokeKey.mutate(row.key_id)}
                    >
                      Revoke
                    </Button>
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

      {/* ------------------------------------------------------------- modals */}
      <Modal
        open={showKeyModal}
        onClose={() => setShowKeyModal(false)}
        title="Create an API key"
        description="The key is shown once and cannot be retrieved later."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowKeyModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={createKey.isPending} disabled={!keyName.trim()} onClick={() => createKey.mutate()}>
              Create key
            </Button>
          </>
        }
      >
        <p className="stat-label mb-1.5">Key name</p>
        <TextInput value={keyName} onChange={(event) => setKeyName(event.target.value)} placeholder="e.g. Airflow integration" autoFocus />
      </Modal>

      <Modal open={Boolean(issuedKey)} onClose={() => setIssuedKey(null)} title="API key created" size="sm">
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
    </div>
  )
}