# Render PostgreSQL deployment

The `food-safety-ai-agent` Render backend is configured with a private
`DATABASE_URL` for `guiltless-postgres` in Oregon. Credentials exist only in Render;
no database password is stored in this repository. The free database expires on
October 9, 2026, unless upgraded. Export or upgrade before expiry.

The backend initializes additive SQLAlchemy tables at startup, uses a small
Postgres pool (3 connections plus at most 2 overflow connections per process),
and checks stale connections before reuse. `/ready` executes `SELECT 1` and
returns `{"ready":true,"database":"postgresql"}` only after a successful query.
Failures return 503 without connection details. `/health` remains compatible.

Render should use `backend` as both root/build context, `./Dockerfile`, and
`/ready` as the health-check path. The Docker entry point respects `PORT`.
The PostgreSQL driver is installed through backend requirements.

This is a fresh database. Local SQLite plans, profiles, USDA imports and
embeddings are not automatically migrated. Demo catalog products seed on demand.
Current profile/bag APIs are demo APIs and do not yet enforce account authentication;
do not store real sensitive client data or treat them as production multi-tenant APIs.
