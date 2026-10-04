/** Theme, density and accent management (system / light / dark, persisted instantly). */

import { useCallback, useEffect, useState } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'
export type Density = 'compact' | 'comfortable' | 'spacious'

const THEME_KEY = 'pip.theme'
const DENSITY_KEY = 'pip.density'
const ACCENT_KEY = 'pip.accent'

const ACCENTS: Record<string, { name: string; base: string; soft: string }> = {
  indigo: { name: 'Indigo', base: '#4f46e5', soft: 'rgb(99 102 241 / 0.12)' },
  blue: { name: 'Blue', base: '#2563eb', soft: 'rgb(37 99 235 / 0.12)' },
  emerald: { name: 'Emerald', base: '#059669', soft: 'rgb(5 150 105 / 0.12)' },
  violet: { name: 'Violet', base: '#7c3aed', soft: 'rgb(124 58 237 / 0.12)' },
  rose: { name: 'Rose', base: '#e11d48', soft: 'rgb(225 29 72 / 0.12)' },
  amber: { name: 'Amber', base: '#d97706', soft: 'rgb(217 119 6 / 0.12)' },
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyTheme(mode: ThemeMode): boolean {
  const dark = mode === 'dark' || (mode === 'system' && systemPrefersDark())
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  return dark
}

export function applyDensity(density: Density): void {
  document.documentElement.dataset.density = density
}

export function applyAccent(accent: string): void {
  const entry = ACCENTS[accent] ?? ACCENTS.indigo
  const root = document.documentElement.style
  root.setProperty('--brand-500', entry.base)
  root.setProperty('--brand-600', entry.base)
  root.setProperty('--brand-500-soft', entry.soft)
}

/* ------------------------------------------------------------------ hooks */
export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => (localStorage.getItem(THEME_KEY) as ThemeMode) || 'system')
  const [isDark, setIsDark] = useState<boolean>(() => document.documentElement.classList.contains('dark'))

  const update = useCallback((next: ThemeMode) => {
    localStorage.setItem(THEME_KEY, next)
    setMode(next)
    setIsDark(applyTheme(next))
  }, [])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const listener = () => {
      if ((localStorage.getItem(THEME_KEY) as ThemeMode) === 'system' || !localStorage.getItem(THEME_KEY)) {
        setIsDark(applyTheme('system'))
      }
    }
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])

  const toggle = useCallback(() => {
    const next: ThemeMode = isDark ? 'light' : 'dark'
    update(next)
  }, [isDark, update])

  return { mode, isDark, setMode: update, toggle }
}

export function useDensity() {
  const [density, setDensityState] = useState<Density>(
    () => (localStorage.getItem(DENSITY_KEY) as Density) || 'comfortable',
  )
  const setDensity = useCallback((next: Density) => {
    localStorage.setItem(DENSITY_KEY, next)
    applyDensity(next)
    setDensityState(next)
  }, [])
  return { density, setDensity }
}

export function useAccent() {
  const [accent, setAccentState] = useState<string>(() => localStorage.getItem(ACCENT_KEY) || 'indigo')
  const setAccent = useCallback((next: string) => {
    localStorage.setItem(ACCENT_KEY, next)
    applyAccent(next)
    setAccentState(next)
  }, [])
  return { accent, setAccent, accents: ACCENTS }
}

export function initAppearance() {
  applyTheme((localStorage.getItem(THEME_KEY) as ThemeMode) || 'system')
  applyDensity((localStorage.getItem(DENSITY_KEY) as Density) || 'comfortable')
  applyAccent(localStorage.getItem(ACCENT_KEY) || 'indigo')
}

export { ACCENTS }