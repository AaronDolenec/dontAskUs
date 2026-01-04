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
echo "Current directory: $(pwd)"
echo "Checking alembic.ini..."
ls -la alembic.ini || echo "alembic.ini not found!"
echo "Running alembic upgrade head..."
alembic upgrade head 2>&1
echo "Migrations completed!"

# Create initial admin user from env vars if none exists
echo "Ensuring initial admin user exists (env-driven)..."
python create_admin_user.py
echo "Admin user setup complete!"

# Start the application
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "Access the Admin UI at: http://localhost:5173/admin"
echo "API Documentation: http://localhost:8000/docs"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
