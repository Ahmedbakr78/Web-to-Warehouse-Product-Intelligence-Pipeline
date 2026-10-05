/**
 * Appearance engine - themes, accent, density, font scale, motion and direction.
 *
 * Single source of truth. Every preference is persisted to `localStorage` under a
 * `pip.*` key AND mirrored into the DOM as a `data-*` attribute on `<html>`, so the
 * Tailwind/CSS layer can react without React re-rendering the whole tree.
 *
 * The inline pre-paint script in `index.html` reads the same keys so there is never
 * a flash of the wrong theme; it intentionally mirrors this module's logic.
 */

import { useCallback, useEffect, useSyncExternalStore } from 'react'

/* -------------------------------------------------------------------- types */

export type ThemeMode = 'system' | 'light' | 'dark' | 'midnight' | 'high-contrast'
export type Density = 'compact' | 'comfortable' | 'spacious'
export type MotionMode = 'full' | 'reduced' | 'none'
export type Direction = 'ltr' | 'rtl'
export type FontScale = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

export const THEME_MODES: { id: ThemeMode; label: string; hint: string }[] = [
  { id: 'light', label: 'Light', hint: 'Bright, high-contrast daylight UI' },
  { id: 'dark', label: 'Dark', hint: 'Neutral charcoal, the default night UI' },
  { id: 'midnight', label: 'Midnight', hint: 'Deep navy, OLED-friendly pure black' },
  { id: 'high-contrast', label: 'High contrast', hint: 'Maximum WCAG contrast, heavier borders' },
  { id: 'system', label: 'System', hint: 'Follow the operating system setting' },
]

export const DENSITIES: { id: Density; label: string; hint: string }[] = [
  { id: 'compact', label: 'Compact', hint: '14px base - fit the most rows on screen' },
  { id: 'comfortable', label: 'Comfortable', hint: '16px base - the balanced default' },
  { id: 'spacious', label: 'Spacious', hint: '17px base - generous line height' },
]

export const MOTION_MODES: { id: MotionMode; label: string; hint: string }[] = [
  { id: 'full', label: 'Full', hint: 'Short, subtle transitions everywhere' },
  { id: 'reduced', label: 'Reduced', hint: 'Colour only, no movement' },
  { id: 'none', label: 'None', hint: 'Every transition and animation disabled' },
]

export const FONT_SCALES: { id: FontScale; label: string; px: string }[] = [
  { id: 'xs', label: 'XS', px: '13px' },
  { id: 'sm', label: 'S', px: '15px' },
  { id: 'md', label: 'M', px: '16px' },
  { id: 'lg', label: 'L', px: '17.5px' },
  { id: 'xl', label: 'XL', px: '19px' },
]

export type Accent = {
  name: string
  /** 600-ish shade used for solid buttons and active states. */
  base: string
  /** Translucent version for chips, active rails and soft badges. */
  soft: string
}

/* ------------------------------------------------------------------- keys */

const KEY = {
  theme: 'pip.theme',
  density: 'pip.density',
  accent: 'pip.accent',
  motion: 'pip.motion',
  direction: 'pip.direction',
  fontScale: 'pip.fontScale',
} as const

export const THEME_KEY = KEY.theme
export const DENSITY_KEY = KEY.density
export const ACCENT_KEY = KEY.accent
export const MOTION_KEY = KEY.motion

/* ---------------------------------------------------------------- accents */

export const ACCENTS: Record<string, Accent> = {
  indigo: { name: 'Indigo', base: '#4f46e5', soft: 'rgb(99 102 241 / 0.12)' },
  blue: { name: 'Blue', base: '#2563eb', soft: 'rgb(37 99 235 / 0.12)' },
  sky: { name: 'Sky', base: '#0284c7', soft: 'rgb(2 132 199 / 0.12)' },
  cyan: { name: 'Cyan', base: '#0891b2', soft: 'rgb(8 145 178 / 0.12)' },
  teal: { name: 'Teal', base: '#0d9488', soft: 'rgb(13 148 136 / 0.12)' },
  emerald: { name: 'Emerald', base: '#059669', soft: 'rgb(5 150 105 / 0.12)' },
  green: { name: 'Green', base: '#16a34a', soft: 'rgb(22 163 74 / 0.12)' },
  amber: { name: 'Amber', base: '#d97706', soft: 'rgb(217 119 6 / 0.12)' },
  orange: { name: 'Orange', base: '#ea580c', soft: 'rgb(234 88 12 / 0.12)' },
  rose: { name: 'Rose', base: '#e11d48', soft: 'rgb(225 29 72 / 0.12)' },
  pink: { name: 'Pink', base: '#db2777', soft: 'rgb(219 39 119 / 0.12)' },
  violet: { name: 'Violet', base: '#7c3aed', soft: 'rgb(124 58 237 / 0.12)' },
}

export const ACCENT_KEYS = Object.keys(ACCENTS)

/* --------------------------------------------------------------- utilities */

function read<T extends string>(key: string, allowed: readonly string[], fallback: T): T {
  try {
    const stored = localStorage.getItem(key)
    return stored && allowed.includes(stored) ? (stored as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* private mode / quota - appearance still applies for this session */
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** "midnight" and "high-contrast" are dark; everything else resolves by mode. */
export function resolveDark(mode: ThemeMode): boolean {
  if (mode === 'dark' || mode === 'midnight' || mode === 'high-contrast') return true
  if (mode === 'system') return systemPrefersDark()
  return false
}

export function getStoredTheme(): ThemeMode {
  return read<ThemeMode>(KEY.theme, THEME_MODES.map((m) => m.id), 'system')
}

/* ------------------------------------------------------------ apply (DOM) */

export function applyTheme(mode: ThemeMode): boolean {
  const root = document.documentElement
  const dark = resolveDark(mode)
  root.classList.toggle('dark', dark)
  root.classList.toggle('theme-midnight', mode === 'midnight')
  root.classList.toggle('theme-high-contrast', mode === 'high-contrast')
  root.dataset.theme = mode
  root.style.colorScheme = dark ? 'dark' : 'light'
  syncThemeColorMeta(dark)
  return dark
}

function syncThemeColorMeta(dark: boolean): void {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (meta) meta.content = dark ? '#0b0f19' : '#ffffff'
}

export function applyDensity(density: Density): void {
  document.documentElement.dataset.density = density
}

export function applyFontScale(scale: FontScale): void {
  const entry = FONT_SCALES.find((item) => item.id === scale) ?? FONT_SCALES[2]
  document.documentElement.dataset.fontScale = scale
  document.documentElement.style.setProperty('--app-font-size', entry.px)
}

export function applyAccent(accent: string): void {
  const entry = ACCENTS[accent] ?? ACCENTS.indigo
  const root = document.documentElement.style
  root.setProperty('--brand-500', entry.base)
  root.setProperty('--brand-600', entry.base)
  root.setProperty('--brand-500-soft', entry.soft)
  document.documentElement.dataset.accent = ACCENTS[accent] ? accent : 'indigo'
}

export function applyMotion(mode: MotionMode): void {
  document.documentElement.dataset.motion = mode
}

export function applyDirection(direction: Direction): void {
  const root = document.documentElement
  root.dataset.direction = direction
  root.setAttribute('dir', direction)
}

/* ----------------------------------------------------------- apply (store) */

export function setTheme(mode: ThemeMode): void {
  write(KEY.theme, mode)
  applyTheme(mode)
  emit()
}

export function setDensity(density: Density): void {
  write(KEY.density, density)
  applyDensity(density)
  emit()
}

export function setAccent(accent: string): void {
  write(KEY.accent, ACCENTS[accent] ? accent : 'indigo')
  applyAccent(accent)
  emit()
}

export function setMotion(mode: MotionMode): void {
  write(KEY.motion, mode)
  applyMotion(mode)
  emit()
}

export function setDirection(direction: Direction): void {
  write(KEY.direction, direction)
  applyDirection(direction)
  emit()
}

export function setFontScale(scale: FontScale): void {
  write(KEY.fontScale, scale)
  applyFontScale(scale)
  emit()
}

/** Apply every stored preference. Called once before React mounts, and on boot. */
export function initAppearance(): void {
  applyTheme(getStoredTheme())
  applyDensity(read<Density>(KEY.density, DENSITIES.map((d) => d.id), 'comfortable'))
  applyAccent(read(KEY.accent, ACCENT_KEYS, 'indigo'))
  applyMotion(read<MotionMode>(KEY.motion, MOTION_MODES.map((m) => m.id), 'full'))
  applyDirection(read<Direction>(KEY.direction, ['ltr', 'rtl'], 'ltr'))
  applyFontScale(read<FontScale>(KEY.fontScale, FONT_SCALES.map((f) => f.id), 'md'))
}

/* -------------------------------------------------------- change broadcast */

/**
 * A tiny external store so appearance state is shared by every component without
 * putting it in a React context (which would re-render the entire tree on a
 * theme click). Components subscribe with `useSyncExternalStore`.
 */
type Snapshot = {
  theme: ThemeMode
  isDark: boolean
  density: Density
  accent: string
  motion: MotionMode
  direction: Direction
  fontScale: FontScale
}

const listeners = new Set<() => void>()

function currentSnapshot(): Snapshot {
  return {
    theme: getStoredTheme(),
    isDark: document.documentElement.classList.contains('dark'),
    density: read<Density>(KEY.density, DENSITIES.map((d) => d.id), 'comfortable'),
    accent: read(KEY.accent, ACCENT_KEYS, 'indigo'),
    motion: read<MotionMode>(KEY.motion, MOTION_MODES.map((m) => m.id), 'full'),
    direction: document.documentElement.dataset.direction === 'rtl' ? 'rtl' : 'ltr',
    fontScale: read<FontScale>(KEY.fontScale, FONT_SCALES.map((f) => f.id), 'md'),
  }
}

function emit(): void {
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/* ------------------------------------------------------------------ hooks */

export function useAppearance() {
  return useSyncExternalStore(subscribe, currentSnapshot, currentSnapshot)
}

export function useTheme() {
  const snapshot = useAppearance()
  const update = useCallback((next: ThemeMode) => setTheme(next), [])
  const toggle = useCallback(() => {
    setTheme(resolveDark(snapshot.theme) ? 'light' : 'dark')
  }, [snapshot.theme])
  return { mode: snapshot.theme, isDark: snapshot.isDark, setMode: update, toggle }
}

export function useDensity() {
  const { density } = useAppearance()
  return { density, setDensity: setDensity }
}

export function useAccent() {
  const { accent } = useAppearance()
  return { accent, setAccent, accents: ACCENTS, accentKeys: ACCENT_KEYS }
}

export function useMotion() {
  const { motion } = useAppearance()
  return { motion, setMotion }
}

export function useDirection() {
  const { direction } = useAppearance()
  return { direction, setDirection }
}

export function useFontScale() {
  const { fontScale } = useAppearance()
  return { fontScale, setFontScale }
}

/* -------------------------------------------------------- cross-tab sync */

/** Keeps two open tabs of the dashboard visually identical. */
export function useAppearanceSync(): void {
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key && event.key.startsWith('pip.')) {
        initAppearance()
        emit()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      if (getStoredTheme() === 'system') {
        applyTheme('system')
        emit()
      }
    }
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
}
