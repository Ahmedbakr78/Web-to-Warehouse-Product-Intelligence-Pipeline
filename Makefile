# =====================================================================
#  Web-to-Warehouse Product Intelligence Pipeline
#  Makefile - one-command workflows for the whole system
#  Usage: make help
# =====================================================================
SHELL := /bin/bash
.DEFAULT_GOAL := help
PY ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYBIN := $(VENV)/bin/python
COMPOSE ?= docker compose
ALEMBIC ?= $(VENV)/bin/alembic
REVISION ?= head

GREEN  := \033[0;32m
BLUE   := \033[0;34m
YELLOW := \033[0;33m
RED    := \033[0;31m
NC     := \033[0m

.PHONY: help
help: ## Show this help
	@printf "$(BLUE)=== Product Intelligence Pipeline ===$(NC)\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[0;36m%-22s\033[0m %s\n", $$1, $$2}'
	@printf "\n$(GREEN)Tip:$(NC) run 'make install' then 'make up-db' then 'make bootstrap'\n"

# ---------------------------------------------------------------- setup
$(VENV):
	$(PY) -m venv $(VENV)

.PHONY: install
install: $(VENV) ## Create venv + install all dependencies (postgres, mysql, dev, airflow, scrapy)
	$(PIP) install --upgrade pip wheel
	$(PIP) install -e ".[postgres,mysql,dev,scrapy]"
	@printf "$(GREEN)✔ Dependencies installed.$(NC)\n"

.PHONY: install-airflow
install-airflow: $(VENV) ## Install Apache Airflow with constraints (run in a dedicated venv ideally)
	$(PIP) install "apache-airflow==2.10.5" \
		--constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt"

.PHONY: env
env: ## Create .env from template if missing
	@[ -f .env ] || (cp .env.example .env && printf "$(YELLOW).env created - edit secrets$(NC)\n")

# ---------------------------------------------------------------- docker
.PHONY: up-db
up-db: ## Start PostgreSQL + MySQL only (both required targets)
	$(COMPOSE) up -d postgres mysql
	@printf "$(GREEN)✔ Databases starting on 5432 (postgres) and 3306 (mysql)$(NC)\n"

.PHONY: up
up: ## Start the full stack (db + api + airflow + frontend)
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete volumes (destructive)
	$(COMPOSE) down -v

.PHONY: db-wait
db-wait: ## Block until both databases report healthy
	@$(COMPOSE) up -d postgres mysql >/dev/null
	@printf "$(YELLOW)Waiting for databases$(NC)"
	@until [ "$$($(COMPOSE) ps --format json postgres 2>/dev/null | grep -c healthy)" -ge 1 ]; do printf "."; sleep 2; done
	@until [ "$$($(COMPOSE) ps --format json mysql 2>/dev/null | grep -c healthy)" -ge 1 ]; do printf "."; sleep 2; done
	@printf "\n$(GREEN)✔ Databases healthy$(NC)\n"

.PHONY: ps
ps: ## Show service status
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail all service logs
	$(COMPOSE) logs -f --tail=100

# ---------------------------------------------------------------- database
.PHONY: bootstrap
bootstrap: ## Create schema + views + seed users/demo data (postgres)
	$(PYBIN) -m app.cli.main bootstrap

.PHONY: bootstrap-mysql
bootstrap-mysql: ## Same bootstrap against MySQL (cross-dialect verification)
	$(PYBIN) -m app.cli.main bootstrap --database mysql

.PHONY: migrate
migrate: ## Apply schema migrations with Alembic (to a revision, default head)
	$(PYBIN) -m app.cli.main migrate $(REVISION)

.PHONY: migrate-status
migrate-status: ## Show the applied revision and any pending ORM drift
	$(PYBIN) -m app.cli.main migration-status

.PHONY: migrate-new
migrate-new: ## Autogenerate a migration from the ORM diff (MSG="what changed")
	@test -n "$(MSG)" || (echo "usage: make migrate-new MSG=\"add x\"" && exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

.PHONY: migrate-check
migrate-check: ## Fail if the ORM has drifted from the applied migration
	$(ALEMBIC) check

.PHONY: migrate-sql
migrate-sql: ## Print the migration SQL without executing it (REVISION=head)
	$(PYBIN) -m app.cli.main migrate $(REVISION) --sql

.PHONY: init-db
init-db: ## Create tables + views + reference data without Alembic (first-time bootstrap)
	$(PYBIN) -m app.cli.main init-db

.PHONY: demo-postgres
demo-postgres: ## Seed a realistic demo dataset into PostgreSQL
	$(PYBIN) -m app.cli.main seed-demo --database postgres --days 120

.PHONY: demo-mysql
demo-mysql: ## Seed a realistic demo dataset into MySQL
	$(PYBIN) -m app.cli.main seed-demo --database mysql --days 120

# ---------------------------------------------------------------- pipeline
.PHONY: run-pipeline
run-pipeline: ## Execute one full ingestion -> DQ -> analytics pipeline run
	$(PYBIN) -m app.cli.main run-pipeline

.PHONY: run-pipeline-mysql
run-pipeline-mysql: ## Execute the pipeline against MySQL
	$(PYBIN) -m app.cli.main run-pipeline --database mysql

.PHONY: run-all-sources
run-all-sources: ## Run every registered source once
	$(PYBIN) -m app.cli.main run-pipeline --all-sources

.PHONY: sources
sources: ## List registered ingestion sources and their compliance settings
	$(PYBIN) -m app.cli.main sources list

.PHONY: analytics
analytics: ## Print the SQL analytics report to stdout
	$(PYBIN) -m app.cli.main report

.PHONY: verify-dialects
verify-dialects: ## Compare row counts / DQ between PostgreSQL and MySQL
	$(PYBIN) -m app.cli.main verify

# ---------------------------------------------------------------- api / ui
.PHONY: serve
serve: ## Run the FastAPI server locally (hot reload)
	$(PYBIN) -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

.PHONY: serve-prod
serve-prod: ## Run the FastAPI server without reload
	$(PYBIN) -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 2

.PHONY: api-docs
api-docs: ## Open interactive API docs
	@printf "$(GREEN)Swagger UI:$(NC) http://localhost:8000/docs  \nReDoc:http://localhost:8000/redoc\n"

# ---------------------------------------------------------------- frontend
.PHONY: frontend-install
frontend-install: ## Install frontend dependencies
	cd frontend && npm install

.PHONY: frontend-dev
frontend-dev: ## Start the Vite dev server
	cd frontend && npm run dev

.PHONY: frontend-build
frontend-build: ## Type-check and build the production bundle
	cd frontend && npm run build

.PHONY: frontend-preview
frontend-preview: ## Preview the production bundle locally
	cd frontend && npm run preview

# ---------------------------------------------------------------- analysis
.PHONY: analysis
analysis: ## Run the SQL analysis scripts in db/analysis (ANALYSIS=<prefix> runs one)
	$(PYBIN) scripts/run_analysis.py $(ANALYSIS)

.PHONY: analysis-mysql
analysis-mysql: ## Same analysis scripts against MySQL
	$(PYBIN) scripts/run_analysis.py --database mysql $(ANALYSIS)

# ---------------------------------------------------------------- quality
.PHONY: test
test: ## Run the test suite
	$(PYBIN) -m pytest -q

.PHONY: test-cov
test-cov: ## Run tests with a coverage report
	$(PYBIN) -m pytest -q --cov=app --cov-report=term-missing --cov-report=html

.PHONY: lint
lint: ## Lint and format-check the Python code
	$(PYBIN) -m ruff check app tests scripts dags
	$(PYBIN) -m ruff format --check app tests scripts

.PHONY: format
format: ## Auto-format the Python code
	$(PYBIN) -m ruff check --fix app tests scripts
	$(PYBIN) -m ruff format app tests scripts

.PHONY: typecheck
typecheck: ## Static type check
	$(PYBIN) -m mypy app

.PHONY: frontend-lint
frontend-lint: ## ESLint + tsc for the frontend
	cd frontend && npm run lint && npm run typecheck

.PHONY: frontend-test
frontend-test: ## Frontend unit tests (vitest)
	cd frontend && npm run test

# ---------------------------------------------------------------- airflow
.PHONY: airflow-init
airflow-init: ## Initialise Airflow metadata DB + admin user locally
	export AIRFLOW_HOME=$${AIRFLOW_HOME:-$$PWD/.airflow}
	airflow db migrate
	airflow users create --username admin --password admin --firstname DEPI --lastname Admin --role Admin --email admin@pipeline.local || true

.PHONY: airflow-test
airflow-test: ## Run the product intelligence DAG once for a fixed date
	export AIRFLOW_HOME=$${AIRFLOW_HOME:-$$PWD/.airflow}
	airflow dags test product_intelligence_pipeline 2026-01-01

# ---------------------------------------------------------------- docs
MMDC_BIN ?= $(shell command -v mmdc 2>/dev/null || echo /tmp/mmdc/node_modules/.bin/mmdc)
export MMDC_BIN

.PHONY: mermaid-install
mermaid-install: ## Install the Mermaid CLI into /tmp/mmdc (no global permissions needed)
	npm install --prefix /tmp/mmdc @mermaid-js/mermaid-cli

.PHONY: docs-render
docs-render: ## Render every Mermaid diagram to SVG (MMDC_BIN=... to point at the CLI)
	$(PYBIN) scripts/diagrams.py render

.PHONY: docs-diagrams
docs-diagrams: ## Extract every Mermaid block into docs/diagrams/out with an index
	$(PYBIN) scripts/diagrams.py extract

.PHONY: docs-site
docs-site: ## Render the diagrams, then build the documentation website
	$(MAKE) docs-render
	$(PYBIN) scripts/build_site.py --out site --diagrams docs/diagrams/out

.PHONY: docs-validate
docs-validate: ## Parse-check every Mermaid diagram (requires the mermaid CLI)
	$(PYBIN) scripts/diagrams.py validate

.PHONY: docs-serve
docs-serve: ## Serve the raw documentation markdown locally
	$(PYBIN) -m http.server 8001 --directory docs

.PHONY: site
site: ## Build the documentation website into ./site (no dependencies)
	$(PYBIN) scripts/build_site.py

.PHONY: site-serve
site-serve: ## Build the documentation website and serve it on :8001
	$(PYBIN) scripts/build_site.py --serve

.PHONY: site-clean
site-clean: ## Remove the built website
	rm -rf site

.PHONY: stats
stats: ## Print the measured structural counts (tables, routes, tests, diagrams)
	$(PYBIN) scripts/project_stats.py

.PHONY: stats-sync
stats-sync: ## Rewrite the generated statistics block in README.md
	$(PYBIN) scripts/project_stats.py --sync-readme

.PHONY: stats-check
stats-check: ## Fail if a documented structural figure no longer matches reality
	$(PYBIN) scripts/check_stats.py docs/stats.json

.PHONY: stats-update
stats-update: ## Re-measure and rewrite docs/stats.json (run after updating the prose)
	$(PYBIN) scripts/check_stats.py docs/stats.json --write

.PHONY: docs-check
docs-check: docs-validate stats-check ## Validate diagrams and check documentation figures
	$(PYBIN) scripts/build_site.py --out /tmp/pip-site-check
	$(PYBIN) scripts/check_links.py /tmp/pip-site-check
	$(PYBIN) scripts/check_slugify.py

.PHONY: infographic
infographic: ## Generate the DEPI project roadmap infographic (HTML + PNG)
	$(PYBIN) scripts/make_infographic.py

.PHONY: deck
deck: ## Generate the 12-slide project presentation deck (HTML + PDF)
	$(PYBIN) scripts/make_deck.py

# ---------------------------------------------------------------- housekeeping
.PHONY: check
check: lint typecheck test ## Full static + unit verification (no services required)

.PHONY: check-migrations
check-migrations: ## Fail if a migration is missing for a model change
	$(ALEMBIC) check

.PHONY: verify-all
verify-all: bootstrap run-pipeline test ## Bootstrap, run the pipeline and test

.PHONY: everything
everything: install env up-db db-wait bootstrap demo-postgres run-pipeline test frontend-install frontend-build ## Full end-to-end verification

.PHONY: clean-cache
clean-cache: ## Remove caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml