# DontAskUs - Self-Hosted Real-Time Q&A Platform

A self-hosted alternative to AskUs with real-time voting and group management.

## Quick Start (Docker Compose)

### Prerequisites

- Docker and Docker Compose installed
- A server or local machine

### 1. Create project directory

```bash
mkdir dontaskus && cd dontaskus
```

### 2. Create `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: dontaskus
      POSTGRES_PASSWORD: changeme_db_password
      POSTGRES_DB: dontaskus
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dontaskus"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    image: ghcr.io/aarondolenec/dontaskus-backend:latest
    environment:
      DATABASE_URL: postgresql://dontaskus:changeme_db_password@db:5432/dontaskus
      REDIS_URL: redis://redis:6379
      SECRET_KEY: changeme_generate_a_secure_random_string
      ADMIN_JWT_SECRET: changeme_another_secure_random_string
      ALLOWED_ORIGINS: http://localhost:3000,http://localhost:5173
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  admin-ui:
    image: ghcr.io/aarondolenec/dontaskus-admin-ui:latest
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  redis_data:
```

### 3. Create `.env` file (optional, for customization)

```bash
# Generate secure secrets
SECRET_KEY=$(openssl rand -base64 32)
ADMIN_JWT_SECRET=$(openssl rand -base64 32)
DB_PASSWORD=$(openssl rand -base64 16)

cat > .env << EOF
SECRET_KEY=${SECRET_KEY}
ADMIN_JWT_SECRET=${ADMIN_JWT_SECRET}
POSTGRES_PASSWORD=${DB_PASSWORD}
DATABASE_URL=postgresql://dontaskus:${DB_PASSWORD}@db:5432/dontaskus
EOF
```

### 4. Start the stack

```bash
docker compose up -d
```

### 5. Create admin user

```bash
docker compose exec backend python create_admin_user.py
```

Follow the prompts to create your admin account.

### 6. Access the application

- **API Docs**: http://localhost:8000/docs
- **Admin UI**: http://localhost:5173

---

## Configuration

### Environment Variables

| Variable                    | Description                            | Default                 |
| --------------------------- | -------------------------------------- | ----------------------- |
| `DATABASE_URL`              | PostgreSQL connection string           | Required                |
| `REDIS_URL`                 | Redis connection string                | `redis://redis:6379`    |
| `SECRET_KEY`                | JWT signing secret for user sessions   | Required                |
| `ADMIN_JWT_SECRET`          | JWT signing secret for admin sessions  | Required                |
| `ALLOWED_ORIGINS`           | CORS allowed origins (comma-separated) | `http://localhost:5173` |
| `LOG_LEVEL`                 | Logging level                          | `INFO`                  |
| `SESSION_TOKEN_EXPIRY_DAYS` | User session token expiry              | `7`                     |

### Production Deployment

For production, ensure you:

1. **Use strong secrets**: Generate with `openssl rand -base64 32`
2. **Use HTTPS**: Put a reverse proxy (nginx, Caddy, Traefik) in front
3. **Set proper CORS origins**: Update `ALLOWED_ORIGINS` to your domain
4. **Backup your database**: Set up regular PostgreSQL backups

Example production compose with Traefik:

```yaml
services:
  backend:
    image: ghcr.io/aarondolenec/dontaskus-backend:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.yourdomain.com`)"
      - "traefik.http.routers.api.tls.certresolver=letsencrypt"
    # ... rest of config
```

---

## API Documentation

Once running, visit `/docs` for interactive Swagger documentation.

### Main Endpoints

- `POST /api/groups` - Create a group
- `POST /api/groups/{group_id}/join` - Join a group with invite code
- `GET /api/groups/{group_id}/question` - Get today's question
- `POST /api/groups/{group_id}/vote` - Submit a vote
- WebSocket `/ws/{group_id}/{user_id}` - Real-time updates

---

## Development

### Local Setup

```bash
# Clone the repo
git clone https://github.com/AaronDolenec/dontAskUs.git
cd dontAskUs/backend

# Start with docker compose (includes hot reload)
docker compose up --build
```

### Admin UI Development

```bash
cd backend/admin-ui
npm install
npm run dev
```

---

## License

MIT License - see LICENSE file for details.
