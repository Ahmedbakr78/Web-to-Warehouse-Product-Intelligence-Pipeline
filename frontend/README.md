# Product Intelligence Dashboard

The React 19 + TypeScript analytics front-end for the Web-to-Warehouse Product Intelligence
Pipeline: 20 screens over a FastAPI REST API, with a light and dark design system, a command
palette, CSV/JSON exports and an installable PWA shell.

## Stack

| Layer | Choice |
| --- | --- |
| Framework | React 19, react-router 7, path alias `@/ -> src/` |
| State and data | TanStack Query v5 (stale-while-revalidate, silent background refresh) |
| Styling | Tailwind CSS 3 over CSS custom properties (light/dark/system, 3 densities, 6 accents) |
| Charts | Recharts 2 with CSS-variable theming and a custom tooltip |
| Icons | lucide-react, used on every action and empty state |
| Tooling | Vite 6, ESLint 9 flat config at `--max-warnings 0`, strict TypeScript |
| Deployment | `npm run build` produces the bundle served by Nginx (`Dockerfile`, `nginx.conf`) |

## Getting started

```bash
npm install

# API on :8000 first (see the repository root README), then:
npm run dev          # http://localhost:5173, /api proxied to 127.0.0.1:8000
npm run build        # typecheck + production bundle into dist/
npm run preview      # serve the production bundle locally
```

Environment variables (`.env`):

| Variable | Meaning |
| --- | --- |
| `VITE_API_BASE_URL` | REST base, defaults to `/api/v1` (proxied by Vite and Nginx) |
| `VITE_PROXY_TARGET` | dev-server proxy target, defaults to `http://127.0.0.1:8000` |

Demo credentials (seeded defaults):

| Role | Email | Password |
| --- | --- | --- |
| Admin | admin@example.com | Admin@12345 |
| Analyst | analyst@example.com | Analyst@12345 |
| Viewer | viewer@example.com | Viewer@12345 |

## Screens

Dashboard, Products, Product detail, Changes (six tabs), Analytics, Pipeline (runs, trigger dialog,
source health), Quality, Catalog reconciliation, Sources, Query Lab (read-only SQL), Builder
(custom view composer), Alerts, Account, Settings, Users, Audit, plus Login and a 404 screen.

## Experience rules

1. **Silent reload.** Data refreshes in the background and renders from cache first; there are no
   route transitions and no decorative animation. Transitions are at most 120 ms and only for
   colour or size; `prefers-reduced-motion` is honoured globally.
2. **Theme without flash.** The persisted theme is applied by an inline script in `index.html`
   before the first paint; the same preference syncs to the server profile.
3. **Keyboard first.** `/` or `Ctrl/Cmd-K` opens the command palette (screens, actions and live
   product search); `Esc` closes overlays; every table header sorts when sortable.
4. **Responsive to 320 px.** The sidebar becomes an off-canvas drawer, grids collapse to cards and
   secondary table columns hide instead of breaking the layout.
5. **Accessibility.** Focus-visible rings, ARIA labels on icon-only controls, semantic buttons and
   roles, WCAG-mindful contrast in both themes.

## Project layout

```text
src/
  components/   AppShell (sidebar, topbar, palette, notification bell), ui primitives, charts
  pages/        one file per screen, lazy-loaded routes
  hooks/        useApi (query defaults), useAuth (session + permissions), useDebounce
  lib/          api client (typed fetch + refresh), theme, format, navigation model, session store
  styles/       design tokens, component layer, scrollbar and motion policy
public/         manifest.webmanifest, icon.svg, icon-maskable.svg
```

## Quality gates

```bash
npm run lint        # eslint . --max-warnings 0
npm run typecheck   # tsc --noEmit, strict
npm run build       # production bundle
```

All three run in CI (`.github/workflows/ci.yml`), and every commit is expected to keep them green.
