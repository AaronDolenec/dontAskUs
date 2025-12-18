# DontAskUs - Self-Hosted Real-Time Q&A Platform

A self-hosted alternative to AskUs with real-time voting and group management.

## Quick Start (Docker Compose)

### Prerequisites

- Docker and Docker Compose installed
- A server or local machine

### 1. Download the example compose file

```bash
mkdir dontaskus && cd dontaskus
curl -O https://raw.githubusercontent.com/AaronDolenec/dontAskUs/main/docker-compose.example.yml
mv docker-compose.example.yml docker-compose.yml
```

### 2. Configure your instance

Edit `docker-compose.yml` and update all `CHANGE_ME` values:

```bash
# Generate secure secrets
openssl rand -base64 32  # Use for SECRET_KEY
openssl rand -base64 32  # Use for ADMIN_JWT_SECRET
openssl rand -base64 16  # Use for database password
```

Key settings to change:

- `POSTGRES_PASSWORD` and matching password in `DATABASE_URL`
- `SECRET_KEY` - JWT secret for user sessions
- `ADMIN_JWT_SECRET` - JWT secret for admin sessions
- `ADMIN_INITIAL_USERNAME` - Initial admin username (default: admin)
- `ADMIN_INITIAL_PASSWORD` - Initial admin password
- `ALLOWED_ORIGINS` - Your domain(s) for CORS

### 3. Start the stack

```bash
docker compose up -d
```

### 4. Access your instance

- **Admin UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs

Login with the `ADMIN_INITIAL_USERNAME` and `ADMIN_INITIAL_PASSWORD` you configured.

> **Important**: Change your password and enable 2FA in Account Settings after first login!

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

---

## Configuration Reference

| Variable                    | Description                            | Required              |
| --------------------------- | -------------------------------------- | --------------------- |
| `DATABASE_URL`              | PostgreSQL connection string           | Yes                   |
| `REDIS_URL`                 | Redis connection string                | Yes                   |
| `SECRET_KEY`                | JWT signing secret for user sessions   | Yes                   |
| `ADMIN_JWT_SECRET`          | JWT signing secret for admin sessions  | Yes                   |
| `ADMIN_INITIAL_USERNAME`    | Initial admin username                 | No (default: `admin`) |
| `ADMIN_INITIAL_PASSWORD`    | Initial admin password                 | Yes                   |
| `ALLOWED_ORIGINS`           | CORS allowed origins (comma-separated) | Yes                   |
| `LOG_LEVEL`                 | Logging level                          | No (default: `INFO`)  |
| `SESSION_TOKEN_EXPIRY_DAYS` | User session token expiry              | No (default: `7`)     |

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
