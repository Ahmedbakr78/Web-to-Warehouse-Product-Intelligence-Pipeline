# Contributing

Thanks for contributing to the Web-to-Warehouse Product Intelligence Pipeline. This guide keeps
changes reviewable, the checks green and the crawler polite.

## Ground rules

1. **Compliance first.** Any new source must declare robots.txt friendly metadata (terms URL,
   license note, rate limit) and must never bypass the robots gate, rate limiter or audit log.
2. **Quality is measured.** Changes that alter loading behaviour should keep the 12 DQ rules green
   or consciously extend them.
3. **Two dialects or it is a bug.** SQL written for PostgreSQL must also work on MySQL; both load
   the same model and `make verify-dialects` must stay drift-free.
4. **No decorative motion.** The dashboard follows a silent-reload policy: 120 ms functional
   transitions only, no route animations, no spinners where skeletons suffice.

## Getting started

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[postgres,mysql,dev,scrapy]"
cd frontend && npm install
```

Run the whole verification gate before pushing:

```bash
make check          # ruff + mypy + pytest (no services required)
cd frontend && npm run lint && npm run typecheck && npm run build
```

For database work:

```bash
make up-db && make db-wait
make bootstrap && make demo-postgres
make verify-dialects
```

## Branches and commits

- Branch from `main` with a short, descriptive name: `feature/supplier-feed`,
  `fix/dedupe-threshold-cache`.
- Keep commits focused; use imperative subject lines ("Add sync-state backfill CLI", not
  "fixed some stuff").
- Every commit must pass `make check` and the frontend checks locally.

## Pull requests

1. Fill in the PR description: what changed, why, and how you verified it.
2. Reference the affected documentation (docs 08-19) when behaviour or design changes.
3. Add or update tests: unit tests in `tests/`, API checks in `scripts/api_smoke.py` when an
   endpoint contract changes.
4. The CI workflow must be green before review.

## Coding standards

- Python: ruff for lint and format (`ruff check --fix` then `ruff format`), mypy clean
  (`mypy app`). Prefer explicit types on public functions.
- SQL: written for both dialects; never rely on database-specific functions outside
  `app/etl/bootstrap.py` or the view file, which are the sanctioned places for dialect forks.
- TypeScript: ESLint runs with `--max-warnings 0`; strict tsc; pages stay declarative by using the
  shared components in `frontend/src/components/ui.tsx`.
- Comments explain why, not what.

## Adding a data source

1. Create `app/ingestion/sources/<name>.py`.
2. Subclass `ProductSource`, set the class variables (`code`, `name`, `kind`, `base_url`,
   `terms_url`, `license_note`, `default_currency`, `rate_limit_per_minute`,
   `min_delay_seconds`, `supports_paging`).
3. Implement `fetch(limit)` as a bound generator of `RawProduct`.
4. Decorate with `@register_source` (it lands in the registry and the Sources screen automatically).
5. Add unit tests for the parser plus at least one smoke check, and preview it:
   `make sources && make sources preview <name> -n 3`.

## Reporting issues

Open a GitHub issue with: the command you ran, the full traceback or screenshot, the database in
use (postgres / mysql / sqlite) and, for crawling problems, the relevant `ingestion_http_log` rows.
