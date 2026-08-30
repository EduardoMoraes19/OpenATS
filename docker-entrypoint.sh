#!/bin/sh
set -e

# Only the API service sets RUN_MIGRATIONS=true. Leaving it off for the worker
# keeps two replicas from racing each other into the same migration table.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "[entrypoint] applying database migrations..."
  node dist/src/db/migrate.js
fi

exec "$@"
