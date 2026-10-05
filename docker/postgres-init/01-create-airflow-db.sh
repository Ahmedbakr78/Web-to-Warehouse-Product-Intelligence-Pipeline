#!/bin/bash
# =====================================================================================
#  Give Airflow its own metadata database.
#
#  Airflow's ~40 metadata tables (dag, task_instance, xcom, log, ...) used to live in
#  the same PostgreSQL database as the analytical warehouse. That put orchestration
#  state inside the data warehouse: every table count included it, Alembic's
#  autogenerate tried to DROP all of it, and a metadata migration could have taken the
#  warehouse with it. Separate databases, separate lifecycles.
#
#  Runs once, on first initialisation of the data directory.
# =====================================================================================
set -euo pipefail

AIRFLOW_DB="${AIRFLOW_DB:-airflow}"

echo "[init] creating the '${AIRFLOW_DB}' database for Airflow metadata"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${AIRFLOW_DB}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${AIRFLOW_DB}')\gexec

    -- Airflow's connections reference the analytical database by name, so that
    -- database has to be reachable from the Airflow metadata one.
    GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB} TO ${POSTGRES_USER};
EOSQL

echo "[init] '${AIRFLOW_DB}' is ready"
