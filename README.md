# DontAskUs — Self-Hosted Real-Time Q&A Platform

A self-hosted alternative to AskUs with real-time voting, streaks, push notifications, and group
management.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration Reference](#configuration-reference)
  - [Database & Redis](#database--redis)
  - [Security & JWT](#security--jwt)
  - [Admin User](#admin-user)
  - [CORS](#cors)
  - [Email (SMTP)](#email-smtp)
  - [Push Notifications (Firebase)](#push-notifications-firebase)
  - [Reverse Proxy](#reverse-proxy)
  - [Avatar Uploads](#avatar-uploads)
  - [Scheduler](#scheduler)
  - [Logging](#logging)
- [API Documentation](#api-documentation)
- [WebSocket Events](#websocket-events)
- [Production Deployment](#production-deployment)
- [Development](#development)
- [License](#license)

---

## Quick Start

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

Edit `docker-compose.yml` and update **all** `CHANGE_ME` values:

```bash
# Generate secure secrets
openssl rand -base64 32   # → SECRET_KEY
openssl rand -base64 32   # → ADMIN_JWT_SECRET
openssl rand -base64 16   # → Database password
```

At minimum you must set:

| Value                    | Where                                             |
| ------------------------ | ------------------------------------------------- |
| Database password        | `POSTGRES_PASSWORD` **and** inside `DATABASE_URL` |
| `SECRET_KEY`             | JWT secret for admin sessions                     |
| `ADMIN_JWT_SECRET`       | JWT secret for admin panel                        |
| `ADMIN_INITIAL_PASSWORD` | First admin account password                      |
| `ALLOWED_ORIGINS`        | Your domain(s) for CORS                           |

> **Tip:** If your database password contains special characters, URL-encode them in `DATABASE_URL`
> (e.g. `@` → `%40`, `!` → `%21`).

### 3. Start the stack

```bash
docker compose up -d
```

This starts four containers:

| Container  | Port | Description                    |
| ---------- | ---- | ------------------------------ |
| `db`       | 5432 | PostgreSQL 15                  |
| `redis`    | 6379 | Redis 7 (rate limiting, cache) |
| `backend`  | 8000 | FastAPI backend + Uvicorn      |
| `admin-ui` | 5173 | Admin dashboard (Nginx)        |

### 4. Access your instance

| URL                          | Description                  |
| ---------------------------- | ---------------------------- |
| `http://localhost:5173`      | Admin UI                     |
| `http://localhost:8000/docs` | Interactive Swagger API docs |
| `http://localhost:8000/api`  | API base URL                 |

Login with the `ADMIN_INITIAL_USERNAME` and `ADMIN_INITIAL_PASSWORD` you configured.

> **Important:** Change your password and enable 2FA in **Account Settings** after first login!

### 5. What happens on first startup

1. Database tables are created and migrations run (`alembic upgrade head`)
2. An initial admin account is created from `ADMIN_INITIAL_USERNAME` / `ADMIN_INITIAL_PASSWORD`
3. The default question set (93 questions) is seeded
4. The background scheduler starts (creates daily questions for each group)

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Admin UI   │     │   Mobile    │     │   Client    │
│  (React)    │     │    App      │     │   App       │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │          HTTP / WebSocket             │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────┴──────┐
                    │   Backend   │  FastAPI + Uvicorn
                    │  (Port 8000)│
                    └──┬─────┬───┘
                       │     │
              ┌────────┘     └────────┐
              │                       │
       ┌──────┴──────┐       ┌───────┴───────┐
       │ PostgreSQL  │       │     Redis     │
       │  (Port 5432)│       │  (Port 6379)  │
       └─────────────┘       └───────────────┘
```

---

## Configuration Reference

All configuration is done via environment variables on the `backend` service.

### Database & Redis

| Variable       | Description                  | Default                                                 | Required |
| -------------- | ---------------------------- | ------------------------------------------------------- | -------- |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://qauser:securepassword@postgres:5432/qadb` | Yes      |
| `REDIS_URL`    | Redis connection string      | `redis://redis:6379`                                    | No       |

### Security & JWT

| Variable                         | Description                          | Default     | Required |
| -------------------------------- | ------------------------------------ | ----------- | -------- |
| `SECRET_KEY`                     | JWT signing secret for admin panel   | ⚠️ insecure | **Yes**  |
| `ADMIN_JWT_SECRET`               | JWT signing secret for admin tokens  | ⚠️ insecure | **Yes**  |
| `USER_JWT_SECRET`                | JWT signing secret for user tokens   | ⚠️ insecure | **Yes**  |
| `USER_JWT_ACCESS_EXPIRE_MINUTES` | User access token lifetime (minutes) | `30`        | No       |
| `USER_JWT_REFRESH_EXPIRE_DAYS`   | User refresh token lifetime (days)   | `30`        | No       |

**Security defaults:**

| Setting                       | Value      |
| ----------------------------- | ---------- |
| Max login attempts (user)     | 10         |
| User lockout duration         | 15 minutes |
| Max login attempts (admin)    | 5          |
| Admin lockout duration        | 30 minutes |
| Admin session length          | 8 hours    |
| Admin refresh token lifetime  | 7 days     |
| Password reset token lifetime | 15 minutes |

### Admin User

| Variable                 | Description                                 | Default       | Required |
| ------------------------ | ------------------------------------------- | ------------- | -------- |
| `ADMIN_INITIAL_USERNAME` | Username for the auto-created admin account | `admin`       | No       |
| `ADMIN_INITIAL_PASSWORD` | Password for the auto-created admin account | `changeme123` | **Yes**  |

The admin account is created automatically on first startup. If an admin already exists, this is
skipped.

### CORS

| Variable          | Description                                  | Default                                       | Required |
| ----------------- | -------------------------------------------- | --------------------------------------------- | -------- |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:5173,http://localhost:3000` | Yes      |

Example:

```yaml
ALLOWED_ORIGINS: https://app.yourdomain.com,https://admin.yourdomain.com
```

### Email (SMTP)

Email is **optional**. When configured, it enables self-service password resets. Without it, the
forgot-password endpoint still works (generates a token) but no email is sent — an admin can
manually relay the token.

| Variable          | Description                                                | Default     | Required |
| ----------------- | ---------------------------------------------------------- | ----------- | -------- |
| `SMTP_HOST`       | SMTP server hostname                                       | _(empty)_   | No       |
| `SMTP_PORT`       | SMTP server port                                           | `587`       | No       |
| `SMTP_USER`       | SMTP username / email for authentication                   | _(empty)_   | No       |
| `SMTP_PASSWORD`   | SMTP password                                              | _(empty)_   | No       |
| `SMTP_FROM_EMAIL` | Sender email address ("From" field)                        | _(empty)_   | No       |
| `SMTP_FROM_NAME`  | Sender display name                                        | `DontAskUs` | No       |
| `SMTP_USE_TLS`    | `true` for SSL (port 465), `false` for STARTTLS (port 587) | `false`     | No       |

**Example — Gmail:**

```yaml
SMTP_HOST: smtp.gmail.com
SMTP_PORT: "465"
SMTP_USER: your-email@gmail.com
SMTP_PASSWORD: your-app-password # Use an App Password, not your account password
SMTP_FROM_EMAIL: your-email@gmail.com
SMTP_FROM_NAME: DontAskUs
SMTP_USE_TLS: "true"
```

**Example — Generic SMTP (STARTTLS):**

```yaml
SMTP_HOST: mail.example.com
SMTP_PORT: "587"
SMTP_USER: noreply@example.com
SMTP_PASSWORD: your-smtp-password
SMTP_FROM_EMAIL: noreply@example.com
SMTP_FROM_NAME: DontAskUs
SMTP_USE_TLS: "false" # Uses STARTTLS on port 587
```

### Push Notifications (Firebase)

Push notifications are **optional** and **disabled by default**. They use the Firebase Cloud
Messaging (FCM) HTTP v1 API to send notifications to mobile devices (new questions, daily reminders,
streak warnings, results available).

#### Setup

1. Go to [Firebase Console](https://console.firebase.google.com/) → your project → **Project
   Settings** → **Service accounts**
2. Click **Generate new private key** to download a JSON file
3. Configure using one of the two options below

#### Option 1 — Service Account JSON as environment variable (recommended for Docker)

```yaml
FCM_PROJECT_ID: your-firebase-project-id
FCM_SERVICE_ACCOUNT_JSON:
  '{"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE
  KEY-----\n...\n-----END PRIVATE
  KEY-----\n","client_email":"firebase-adminsdk-...@....iam.gserviceaccount.com"}'
```

#### Option 2 — Service Account JSON file (recommended for bare-metal)

```yaml
FCM_PROJECT_ID: your-firebase-project-id
GOOGLE_APPLICATION_CREDENTIALS: /path/to/service-account.json
```

Mount the file into the container:

```yaml
volumes:
  - ./service-account.json:/app/service-account.json:ro
```

| Variable                         | Description                                | Default     | Required |
| -------------------------------- | ------------------------------------------ | ----------- | -------- |
| `FCM_PROJECT_ID`                 | Firebase project ID                        | _(empty)_   | No       |
| `FCM_SERVICE_ACCOUNT_JSON`       | Full service account JSON as a string      | _(empty)_   | No       |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON file          | _(empty)_   | No       |
| `FCM_ENABLED`                    | Explicitly enable/disable (`true`/`false`) | auto-detect | No       |

Push is auto-enabled when `FCM_PROJECT_ID` is set **and** either `FCM_SERVICE_ACCOUNT_JSON` or
`GOOGLE_APPLICATION_CREDENTIALS` is provided.

#### Notification types

| Type                | Trigger                                       |
| ------------------- | --------------------------------------------- |
| `new_question`      | A new daily question is generated for a group |
| `daily_reminder`    | Reminder to answer today's question           |
| `results_available` | Voting results are ready                      |
| `streak_warning`    | User's streak is about to break               |

### Reverse Proxy

If the backend runs behind nginx, Caddy, Traefik, or similar, configure trusted proxies so real
client IPs are logged correctly instead of the proxy IP.

| Variable          | Description                                          | Default   | Required |
| ----------------- | ---------------------------------------------------- | --------- | -------- |
| `TRUSTED_PROXIES` | Comma-separated proxy IPs/CIDRs, or `*` to trust all | _(empty)_ | No       |

Examples:

```yaml
# Trust Docker's default bridge network
TRUSTED_PROXIES: "172.16.0.0/12"

# Trust specific proxy + Docker network
TRUSTED_PROXIES: "10.0.0.1,172.18.0.0/16"

# Trust all (only if behind a known reverse proxy)
TRUSTED_PROXIES: "*"
```

When `TRUSTED_PROXIES` is set, the entrypoint automatically starts Uvicorn with
`--proxy-headers --forwarded-allow-ips`.

### Avatar Uploads

Avatar uploads work out of the box. Uploaded avatars are stored in a Docker volume mounted at
`/app/uploads/avatars`.

| Setting           | Value                                                       |
| ----------------- | ----------------------------------------------------------- |
| Max file size     | 2 MB                                                        |
| Max dimension     | 256 × 256 px (auto-resized)                                 |
| Supported formats | JPEG, PNG, GIF, WebP, BMP, TIFF, ICO, HEIC, HEIF, AVIF, SVG |
| Storage volume    | `avatar_uploads` → `/app/uploads/avatars`                   |

Make sure to include the volume in your compose file:

```yaml
volumes:
  - avatar_uploads:/app/uploads/avatars
```

### Scheduler

The background scheduler automatically generates daily questions for each group at their designated
rollover hour (assigned on group creation with ±3h random jitter). A 20-hour minimum gap between
questions is enforced.

| Variable                    | Description                         | Default | Required |
| --------------------------- | ----------------------------------- | ------- | -------- |
| `SCHEDULE_INTERVAL_SECONDS` | How often the scheduler runs (secs) | `86400` | No       |

### Logging

| Variable    | Description                                                | Default | Required |
| ----------- | ---------------------------------------------------------- | ------- | -------- |
| `LOG_LEVEL` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO`  | No       |

All API requests (except `/health`, `/docs`, `/openapi.json`, static files) are logged to the
database and visible in the Admin UI under **API Logs**.

---

## API Documentation

Once running, visit **`http://localhost:8000/docs`** for interactive Swagger documentation.

Full API documentation is available in
[`COMPLETE_API_DOCUMENTATION.md`](./COMPLETE_API_DOCUMENTATION.md).

### Key Endpoints

| Method   | Endpoint                             | Description                   |
| -------- | ------------------------------------ | ----------------------------- |
| `POST`   | `/api/auth/register`                 | Register a new user account   |
| `POST`   | `/api/auth/login`                    | Login and receive JWT tokens  |
| `POST`   | `/api/auth/refresh`                  | Refresh an access token       |
| `GET`    | `/api/auth/me`                       | Get current user profile      |
| `POST`   | `/api/auth/groups`                   | Create a new group            |
| `POST`   | `/api/auth/groups/{group_id}/join`   | Join a group with invite code |
| `DELETE` | `/api/auth/groups/{group_id}`        | Delete a group (owner only)   |
| `GET`    | `/api/groups/{group_id}/question`    | Get today's question          |
| `POST`   | `/api/groups/{group_id}/vote`        | Submit or change a vote       |
| `GET`    | `/api/groups/{group_id}/members`     | List group members + streaks  |
| `GET`    | `/api/groups/{group_id}/leaderboard` | Group leaderboard             |
| `POST`   | `/api/auth/forgot-password`          | Request password reset        |
| `POST`   | `/api/auth/reset-password`           | Reset password with token     |
| `POST`   | `/api/avatars/upload`                | Upload user avatar            |
| `POST`   | `/api/push/register`                 | Register device for push      |

### Admin Endpoints

All admin endpoints require admin JWT authentication.

| Method | Endpoint                     | Description            |
| ------ | ---------------------------- | ---------------------- |
| `POST` | `/api/admin/login`           | Admin login            |
| `GET`  | `/api/admin/users`           | List all users         |
| `GET`  | `/api/admin/groups`          | List all groups        |
| `GET`  | `/api/admin/question-sets`   | List question sets     |
| `GET`  | `/api/admin/audit-log`       | View audit log         |
| `GET`  | `/api/admin/api-logs`        | View API request logs  |
| `GET`  | `/api/admin/dashboard`       | Dashboard statistics   |
| `GET`  | `/api/admin/db/{table_name}` | Browse database tables |

---

## WebSocket Events

Connect to real-time group events at:

```
ws://localhost:8000/ws/groups/{group_id}?token=<JWT>
```

| Event           | Description                          |
| --------------- | ------------------------------------ |
| `vote_update`   | A member voted or changed their vote |
| `new_question`  | The daily question rolled over       |
| `streak_update` | A member's streak changed            |
| `member_joined` | A new member joined the group        |
| `member_left`   | A member left the group              |
| `group_deleted` | The group was deleted by its owner   |
| `ping` / `pong` | Keepalive heartbeat                  |

---

## Production Deployment

### Checklist

1. **Use strong secrets** — generate with `openssl rand -base64 32`
2. **Use HTTPS** — put a reverse proxy (nginx, Caddy, Traefik) in front
3. **Set proper CORS origins** — update `ALLOWED_ORIGINS` to your domain(s)
4. **Set `TRUSTED_PROXIES`** — so real client IPs are logged
5. **Backup your database** — set up regular PostgreSQL backups
6. **Change admin password** — immediately after first login, enable 2FA

### Example with Traefik

```yaml
services:
  backend:
    image: ghcr.io/aarondolenec/dontaskus-backend:latest
    environment:
      TRUSTED_PROXIES: "*"
      ALLOWED_ORIGINS: https://app.yourdomain.com
      # ... other env vars
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.yourdomain.com`)"
      - "traefik.http.routers.api.tls.certresolver=letsencrypt"
      - "traefik.http.services.api.loadbalancer.server.port=8000"
```

### Updating

```bash
docker compose pull
docker compose up -d
```

Database migrations run automatically on each startup via `alembic upgrade head`.

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

### Running Tests

```bash
# Run the full endpoint test suite
bash test_all_endpoints.sh
```

### Project Structure

```
backend/
├── main.py                 # FastAPI app, middleware, lifespan
├── core/
│   ├── config.py           # All environment variable configuration
│   ├── database.py         # SQLAlchemy engine & session
│   ├── models.py           # All database models
│   └── schemas.py          # Pydantic request/response schemas
├── routes/
│   ├── auth.py             # User auth (register, login, groups)
│   ├── groups.py           # Group members, leaderboard
│   ├── questions.py        # Daily questions, voting
│   ├── avatars.py          # Avatar upload/retrieval
│   ├── push.py             # Push notification registration
│   ├── question_sets.py    # Question set management
│   ├── websocket.py        # WebSocket connections
│   └── admin.py            # Admin panel endpoints
├── services/
│   ├── scheduler.py        # Background daily question generation
│   ├── push_notifications.py  # Firebase FCM service
│   ├── email.py            # SMTP email service
│   └── ws_manager.py       # WebSocket connection manager
├── alembic/                # Database migrations
├── admin-ui/               # React admin dashboard (Vite + TypeScript)
└── scripts/                # Setup & seed scripts
```

---

## License

MIT License — see LICENSE file for details.
