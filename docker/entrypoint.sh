#!/bin/sh
set -e

if [ "$DB_ENGINE" = "postgres" ]; then
  echo "Waiting for PostgreSQL at $POSTGRES_HOST:$POSTGRES_PORT..."
  until nc -z "$POSTGRES_HOST" "$POSTGRES_PORT"; do
    sleep 1
  done
  echo "PostgreSQL is available."
fi

# Only run migrations and collectstatic for the web service
if [ "${ROLE:-web}" = "web" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
elif [ "${ROLE}" = "beat" ]; then
  # Beat needs tables to exist before starting; migrate without collectstatic
  python manage.py migrate --noinput
fi

exec "$@"
