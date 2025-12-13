#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL on db:5432..."
for i in {1..60}; do
  if nc -z db 5432 2>/dev/null; then
    echo "PostgreSQL is reachable!"
    break
  fi
  echo "Attempt $i/60: PostgreSQL not ready yet..."
  sleep 1
done

# Wait extra time for PostgreSQL to fully initialize database
echo "Waiting for PostgreSQL to fully initialize..."
sleep 5

# Run migrations
echo "Running database migrations..."
if alembic upgrade head; then
  echo "Migrations completed successfully!"
else
  echo "Migrations completed or already applied!"
fi

# Start the application
echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
