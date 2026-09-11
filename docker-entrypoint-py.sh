#!/bin/sh
set -e

# Only the API service sets RUN_MIGRATIONS=true. Leaving it off for the
# worker keeps two replicas from racing each other into the same migration
# table - same rationale as docker-entrypoint.sh for the TS backend.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "[entrypoint] applying database migrations..."
  python -m alembic upgrade head
fi

exec "$@"
