# =====================================================================================
#  API image - FastAPI + the ETL package (used by `docker compose up api`)
# =====================================================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/srv/app

WORKDIR /srv/app

# curl is used by the container health check, the rest keeps the image small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# ---- dependency layer (cached until pyproject.toml changes) --------------------------
FROM base AS builder
COPY pyproject.toml README.md ./
COPY app/__init__.py app/__init__.py
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip wheel \
 && /opt/venv/bin/pip install "psycopg2-binary>=2.9" "PyMySQL>=1.1" "cryptography>=42.0" \
 && /opt/venv/bin/pip install "fastapi>=0.115" "uvicorn[standard]" "sqlalchemy>=2.0.30" pydantic pydantic-settings \
      httpx beautifulsoup4 lxml lxml-html-clean pandas numpy plotly python-dateutil python-multipart \
      PyJWT argon2-cffi email-validator orjson tenacity structlog typer rich

# ---- runtime ------------------------------------------------------------------------
FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app /srv/app/app
COPY db /srv/app/db
COPY dags /srv/app/dags

RUN useradd --create-home --uid 10001 pipeline \
 && mkdir -p /srv/app/var && chown -R pipeline:pipeline /srv/app
USER pipeline

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]