# Schema migrations

Alembic owns the schema. `db/views.sql` owns the 20 analytical views, and the initial
migration applies them at the end of `upgrade()` because the whole analytics layer
reads through them.

## Everyday use

```bash
make migrate-status              # applied revision + any ORM drift
make migrate-new MSG="add x"     # autogenerate a migration from the model diff
make migrate                     # apply everything pending
make migrate REVISION=-1         # undo the last one
make migrate-sql REVISION=head   # print the SQL without running it
make migrate-check               # CI gate: fail if a migration is missing
```

## How it is wired

`migrations/env.py` reads the target from the application's own `Settings`
(`ACTIVE_DATABASE` / `DATABASE_URL`), so there is exactly one place to configure a
database and a migration cannot drift from the application.

Portability is handled in three places:

* `render_as_batch` is enabled on SQLite, which rewrites a table instead of issuing
  the `ALTER` statements SQLite cannot run.
* The PostgreSQL schema name (`DB_SCHEMA`, default `public`) is passed only on
  PostgreSQL; MySQL has no schemas and SQLite ignores it.
* `include_object` excludes anything that is not ours - the `vw_*` views, Alembic's
  own tables, and any foreign service's tables - so autogenerate never proposes
  dropping them.

## Autogenerating the initial revision

The first revision was generated against an empty database, because against the live
warehouse Alembic correctly finds nothing to do:

```bash
DATABASE_URL="sqlite:////tmp/scratch.sqlite3" ACTIVE_DATABASE=sqlite \
  alembic revision --autogenerate -m "initial warehouse schema" --rev-id 0001_initial
```

An existing deployment adopts it with `alembic stamp head`, which records the
revision without running it.

## Airflow

Airflow keeps its orchestration metadata in its own database (`AIRFLOW_DB`, default
`airflow`) rather than inside the analytical warehouse. See
`docker/postgres-init/01-create-airflow-db.sh`.
