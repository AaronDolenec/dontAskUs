# Deployment Guide

## Quick Start

### 1. Start Services (Docker)
```bash
cd /root/coding/privat/dontAskUs
docker-compose down -v  # Clean start (optional)
docker-compose up -d    # Start PostgreSQL, Redis, Backend
```

### 2. Apply Migrations
```bash
cd backend
alembic upgrade head
```

### 3. Verify
```bash
# Check API health
curl http://localhost:8000/api/health

# Check Docker services
docker-compose ps
```

---

## What's Deployed

### Backend Changes
- ✅ **CORS Hardening** - Whitelist-based origin control
- ✅ **Token Hashing** - Bcrypt-secured tokens (not plaintext)
- ✅ **Token Expiry** - 7-day TTL on session tokens
- ✅ **Input Validation** - All user input sanitized against XSS
- ✅ **Environment Config** - All secrets from `.env`, not hardcoded
- ✅ **Database Migrations** - Alembic version control for schema

### Environment Variables (.env)
```
DATABASE_URL=postgresql://qauser:pass@localhost:5432/qadb
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
SESSION_TOKEN_EXPIRY_DAYS=7
SECRET_KEY=your-super-secret-key-change-in-production-keep-this-very-secure
DEBUG=True
```

---

## Database Schema

### Initial Migration (000_initial_schema)
Creates all tables:
- `question_templates` - Question library
- `groups` - User groups
- `users` - Users with `session_token_expires_at` field
- `daily_questions` - Daily Q&A
- `votes` - User votes
- `question_sets` - Reusable sets
- `group_analytics` - Statistics
- And more...

### Security Migration (001_add_token_security)
Verifies token security fields are present (already included in initial schema).

---

## Common Issues

### PostgreSQL Connection Refused
```bash
# Start Docker services
docker-compose up -d

# Check if running
docker-compose ps db

# View logs
docker-compose logs db
```

### Migration Fails
```bash
# Reset database
docker-compose down -v
docker-compose up -d db
alembic upgrade head
```

### Port Already in Use
```bash
# Find and kill process on port 5432
lsof -i :5432
kill -9 <PID>

# Or change port in docker-compose.yml
```

---

## Verify Security Implementation

### Test CORS Protection
```bash
# Should fail - origin not whitelisted
curl -H "Origin: http://evil.com" http://localhost:8000/api/health
# No "Access-Control-Allow-Origin" header

# Should succeed - origin whitelisted
curl -H "Origin: http://localhost:5173" http://localhost:8000/api/health
# Has "Access-Control-Allow-Origin: http://localhost:5173"
```

### Test Token Hashing
```bash
# Check database - tokens should be hashed (start with $2b$)
psql -h localhost -U qauser -d qadb \
  -c "SELECT user_id, session_token FROM users LIMIT 1;"
# Output: session_token should be like: $2b$12$...
```

### Test Input Validation
```bash
# Create group with XSS attempt - should be sanitized
curl -X POST http://localhost:8000/api/groups \
  -H "Content-Type: application/json" \
  -d '{"name":"<script>alert(1)</script>Test"}'
# Check response - script tag should be removed
```

### Test Token Expiry
```bash
# Get user session token
curl http://localhost:8000/api/users/me -H "X-Session-Token: token_here"

# Wait 7 days (or modify SESSION_TOKEN_EXPIRY_DAYS=1 for testing)
# Token should no longer work after expiry
```

---

## Production Checklist

- [ ] Update `.env` with secure passwords
- [ ] Set `DEBUG=False` in `.env`
- [ ] Change `SECRET_KEY` to a strong random value
- [ ] Update `ALLOWED_ORIGINS` to production domain(s)
- [ ] Setup HTTPS reverse proxy (Nginx, Caddy)
- [ ] Configure database backups
- [ ] Setup error tracking (Sentry)
- [ ] Enable rate limiting
- [ ] Update frontend to use httpOnly cookies
- [ ] Security audit/penetration testing

---

## Useful Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f backend
docker-compose logs -f db

# Connect to database
psql -h localhost -U qauser -d qadb

# Run migrations
alembic upgrade head
alembic downgrade base
alembic history

# Check migration status
alembic current
```

---

## Database Credentials (Local)

- **Host:** localhost
- **Port:** 5432
- **User:** qauser
- **Password:** (from `.env` DATABASE_URL)
- **Database:** qadb

---

## Support

For errors during deployment, check:
1. Docker is running: `docker-compose ps`
2. Database is accessible: `psql -h localhost -U qauser -d qadb`
3. Python dependencies: `pip install -r requirements.txt`
4. Environment variables: `cat .env`
5. Logs: `docker-compose logs backend`
