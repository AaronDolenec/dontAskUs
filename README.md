# AskUs Backend - Setup Guide

Complete guide to set up, configure, and run the AskUs backend locally and with Docker.

---

## 📋 Prerequisites

- **Python 3.11+** installed
- **Docker & Docker Compose** (optional, for containerized setup)
- **PostgreSQL** (local or Docker)
- **Git** (to clone the repository)

---

## 🚀 Quick Start (Local Development)

### 1. Clone the Repository

```bash
cd ~/coding/privat
git clone https://github.com/YOUR_USERNAME/dontAskUs.git
cd dontAskUs/backend
```

### 2. Create Python Virtual Environment

```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate.bat  # Windows CMD
# or
venv\Scripts\Activate.ps1  # Windows PowerShell
```

### 3. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install project requirements
pip install -r requirements.txt
```

### 4. Create `.env` Configuration File

```bash
cat > .env << 'EOF'
# Database (PostgreSQL)
DATABASE_URL=postgresql://qauser:securepassword123@localhost:5432/qadb

# Redis (optional, for WebSocket caching)
REDIS_URL=redis://localhost:6379/0

# Secret key (change in production!)
SECRET_KEY=your-super-secret-key-change-in-production-keep-this-very-secure

# Development settings
DEBUG=True
EOF
```

**For Windows (PowerShell):**
```powershell
@"
DATABASE_URL=postgresql://qauser:securepassword123@localhost:5432/qadb
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-super-secret-key-change-in-production-keep-this-very-secure
DEBUG=True
"@ | Out-File -Encoding UTF8 .env
```

### 5. Start PostgreSQL Database

**Option A: Using Docker**
```bash
docker run --name askus-postgres \
  -e POSTGRES_PASSWORD=securepassword123 \
  -e POSTGRES_DB=qadb \
  -e POSTGRES_USER=qauser \
  -p 5432:5432 \
  -d postgres:16-alpine
```

**Option B: Using Docker (with volume for persistence)**
```bash
docker run --name askus-postgres \
  -e POSTGRES_PASSWORD=securepassword123 \
  -e POSTGRES_DB=qadb \
  -e POSTGRES_USER=qauser \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  -d postgres:16-alpine
```

**Option C: Local PostgreSQL Installation**
```bash
# Ensure PostgreSQL is running
# Linux/macOS:
sudo systemctl start postgresql
# Windows: Start PostgreSQL service from Services
```

### 6. Verify Database Connection

```bash
# Install psql client if needed
sudo apt install postgresql-client  # Linux
brew install postgresql              # macOS

# Test connection
psql -h localhost -U qauser -d qadb -c "SELECT 1;"
```

### 7. Run Backend Server

```bash
# Make sure venv is activated
source venv/bin/activate

# Start backend with auto-reload
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 8. Access the API

- **Interactive API Docs:** `http://localhost:8000/docs`
- **Alternative API Docs:** `http://localhost:8000/redoc`
- **Health Check:** `http://localhost:8000/health`

---

## 🐳 Docker Compose Setup (Recommended for Production)

### Complete docker-compose.yml

Create `docker-compose.yml` in the **root directory** of your project:

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:16-alpine
    container_name: askus-postgres
    environment:
      POSTGRES_USER: qauser
      POSTGRES_PASSWORD: securepassword123
      POSTGRES_DB: qadb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qauser -d qadb"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - askus-network
    restart: unless-stopped

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: askus-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - askus-network
    restart: unless-stopped

  # FastAPI Backend
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: askus-backend
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://qauser:securepassword123@postgres:5432/qadb
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY:-your-super-secret-key-change-in-production}
      DEBUG: "False"
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    command: >
      sh -c "pip install -r requirements.txt &&
             uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
    networks:
      - askus-network
    restart: unless-stopped

  # React Admin UI (optional)
  frontend:
    build:
      context: ./frontend-web
      dockerfile: Dockerfile
    container_name: askus-frontend
    depends_on:
      - backend
    environment:
      VITE_API_URL: http://backend:8000
    ports:
      - "5173:5173"
    volumes:
      - ./frontend-web:/app
    command: npm run dev
    networks:
      - askus-network
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:

networks:
  askus-network:
    driver: bridge
```

### Backend Dockerfile

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend Dockerfile (Optional)

Create `frontend-web/Dockerfile`:

```dockerfile
FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy app code
COPY . .

# Expose port
EXPOSE 5173

# Start dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### .env File for Docker Compose

Create `.env` in **root directory**:

```bash
# Backend secrets
SECRET_KEY=your-super-secret-key-change-in-production-keep-this-very-secure

# Database
DATABASE_URL=postgresql://qauser:securepassword123@postgres:5432/qadb

# Redis
REDIS_URL=redis://redis:6379/0

# Debug mode
DEBUG=False
```

---

## 🚀 Running with Docker Compose

### Start All Services

```bash
# From project root directory
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
docker-compose logs -f postgres
```

### Stop All Services

```bash
docker-compose down
```

### Stop and Remove Volumes (Clean Slate)

```bash
docker-compose down -v
```

### Rebuild Services

```bash
docker-compose up -d --build
```

---

## 📊 Access Services

| Service | URL | Notes |
|---------|-----|-------|
| **Backend API** | `http://localhost:8000` | FastAPI docs at `/docs` |
| **API Interactive Docs** | `http://localhost:8000/docs` | Swagger UI |
| **Alternative Docs** | `http://localhost:8000/redoc` | ReDoc |
| **Frontend UI** | `http://localhost:5173` | React dev server |
| **PostgreSQL** | `localhost:5432` | Connection from backend |
| **Redis** | `localhost:6379` | Cache layer |

---

## 🔧 Configuration Explained

### .env Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | `postgresql://qauser:securepassword123@localhost:5432/qadb` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache connection |
| `SECRET_KEY` | (random string) | JWT/session encryption key |
| `DEBUG` | `True` / `False` | Development vs production mode |

**Important:** Change `SECRET_KEY` in production!

### Docker Compose Services

| Service | Port | Purpose |
|---------|------|---------|
| **postgres** | 5432 | Main database |
| **redis** | 6379 | Cache/session store |
| **backend** | 8000 | FastAPI REST API |
| **frontend** | 5173 | React web UI |

---

## 🐛 Troubleshooting

### Backend Won't Start

```bash
# Check database connection
psql -h localhost -U qauser -d qadb -c "SELECT 1;"

# Verify .env file exists
cat backend/.env

# Check logs
docker-compose logs backend
```

### Database Connection Error

```
Error: could not translate host name "postgres" to address

# Solution: Use "localhost" if running backend outside Docker
# Or ensure postgres container is running and healthy
docker-compose ps
```

### Port Already in Use

```bash
# Kill process on port 8000
lsof -i :8000
kill -9 <PID>

# Or change port in docker-compose.yml
```

### Clear Everything and Start Fresh

```bash
docker-compose down -v
docker system prune -a
docker-compose up -d --build
```

---

## 📝 Development Workflow

### Local Development (Recommended)

```bash
# Terminal 1: Database
docker run --name askus-postgres -e POSTGRES_PASSWORD=securepassword123 -e POSTGRES_DB=qadb -e POSTGRES_USER=qauser -p 5432:5432 -d postgres:16-alpine

# Terminal 2: Backend
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Frontend
cd frontend-web
npm install
npm run dev
```

### Production Deployment (Docker Compose)

```bash
# Single command
docker-compose -f docker-compose.yml up -d

# View status
docker-compose ps

# View logs
docker-compose logs -f
```

---

## 🔐 Security Checklist

- [ ] Change `SECRET_KEY` to a random secure string
- [ ] Change PostgreSQL password in production
- [ ] Use HTTPS in production (add SSL/TLS)
- [ ] Set `DEBUG=False` in production
- [ ] Use environment variables for sensitive data
- [ ] Restrict database access to internal network only
- [ ] Enable CORS only for allowed origins

---

## 📚 Useful Commands

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs -f backend

# Access database
psql -h localhost -U qauser -d qadb

# Restart services
docker-compose restart

# Stop without removing
docker-compose stop

# Start stopped services
docker-compose start

# Remove everything
docker-compose down -v
```

---

## 🚀 Next Steps

1. ✅ Set up `.env` file
2. ✅ Start PostgreSQL and Redis
3. ✅ Install Python dependencies
4. ✅ Run `uvicorn main:app --reload`
5. ⏭️ Build React frontend
6. ⏭️ Deploy with Docker Compose
7. ⏭️ Set up CI/CD pipeline

---

## 📖 API Documentation

Once backend is running, visit:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

---

## 💡 Tips

- Use `--reload` flag during development for auto-restart on file changes
- Keep `.env` file out of Git (add to `.gitignore`)
- Always test database connection before starting backend
- Use `docker-compose logs -f` to debug issues
- Store production `.env` securely (use secrets management)

---

## 📞 Support

For issues or questions:
1. Check logs: `docker-compose logs backend`
2. Verify `.env` configuration
3. Ensure all services are healthy: `docker-compose ps`
4. Check database connectivity: `psql -h localhost -U qauser -d qadb`

