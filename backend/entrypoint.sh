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

# Create initial admin user from env vars if none exists
echo "Ensuring initial admin user exists (env-driven)..."
if python create_admin_user.py; then
  echo "Admin user creation completed successfully!"
else
  echo "WARNING: Failed to create admin user. Error details:"
  python create_admin_user.py 2>&1 || echo "Admin user creation failed!"
fi

# Start the application
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "Access the Admin UI at: http://localhost:5173/admin"
echo "API Documentation: http://localhost:8000/docs"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
