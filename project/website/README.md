# Project website

A single, dependency-free landing page for the pipeline: **open `index.html` in any browser**, no build
step, no bundler, no network calls.

- `light` / `dark` / `system` themes via the button in the top-right (persisted in `localStorage`,
  applied before the first paint so there is no flash of the wrong theme).
- Responsive from 320 px; the nav collapses on small screens.
- Fully self-contained: the icons are inline SVG and the fonts are system fonts.

## Publish it with GitHub Pages

The repository is **private**, and GitHub Pages is only served for public repositories on free plans.
To publish the site:

1. **Recommended** — make the repository public (`gh repo edit --visibility public`) and enable Pages:
   ```bash
   gh api -X POST repos/:owner/:repo/pages -f source[branch]=main -f source[path]/website
   ```
   The site becomes available at `https://<owner>.github.io/<repo>/`.
2. **Keep it private** — serve the file from anywhere that can host a static file (GitLab Pages, a
   bucket, Netlify/Vercel drop-in, or `python -m http.server` on a host that can reach it). The file is
   plain HTML, so no build configuration is needed.