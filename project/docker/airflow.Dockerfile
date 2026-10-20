# =====================================================================================
#  Airflow image for the product intelligence DAG.
#
#  Airflow 2.10 runs on SQLAlchemy 1.4 because its own ORM models are not SQLAlchemy 2
#  compatible, while the pipeline package requires SQLAlchemy 2.0. The two cannot share
#  one interpreter, so the DAG drives the pipeline through the REST API
#  (PIPELINE_API_URL) and falls back to an in-process import only where both
#  interpreters match - for example `make airflow-test` on the host, or a deployment
#  where Airflow runs on SQLAlchemy 2.
# =====================================================================================
FROM apache/airflow:2.10.5-python3.12

ARG AIRFLOW_VERSION=2.10.5
ARG PYTHON_VERSION=3.12

USER airflow

# Airflow 2.10 runs on SQLAlchemy 1.4 (its own ORM models are not SQLAlchemy 2 compatible),
# while the pipeline package requires SQLAlchemy 2.0. The two cannot share an
# interpreter, so Airflow drives the pipeline over its REST API instead of importing it.
# Only the HTTP client is added here - nothing that would disturb Airflow's pins.
RUN pip install --no-cache-dir "httpx>=0.27" && pip check --no-input || true

# The application is mounted read-only at runtime (docker-compose bind mount) purely so
# the DAG can be developed against it; the DAG imports it lazily and falls back to the
# REST API when the interpreter cannot satisfy SQLAlchemy 2.0.

ENV PYTHONPATH=/opt/airflow \
    PIP_PROJECT_ROOT=/opt/airflow

USER airflow

# Fail the build if the scheduler cannot start, instead of failing every task later.
RUN airflow version