# Backend Code Organization

The backend has been reorganized into a clean, modular structure for better maintainability and
clarity.

## Directory Structure

```
backend/
├── core/                   # Core infrastructure
│   ├── __init__.py        # Exports all core components
│   ├── config.py          # Configuration and environment variables
│   ├── database.py        # SQLAlchemy setup and database session management
│   ├── models.py          # Database models (ORM)
│   └── schemas.py         # Pydantic schemas for request/response validation
│
├── auth/                   # Authentication and authorization
│   ├── __init__.py        # Exports auth utilities
│   ├── admin_auth.py      # Admin user authentication (JWT, TOTP)
│   ├── admin_schemas.py   # Pydantic schemas for admin endpoints
│   └── utils.py           # User auth helpers, password hashing, JWT, avatars
│
├── services/               # Background services and real-time features
│   ├── __init__.py        # Exports services
│   ├── scheduler.py       # Background question scheduler
│   ├── push_notifications.py  # Firebase Cloud Messaging (FCM) push notifications
│   └── ws_manager.py      # WebSocket connection manager
│
├── scripts/                # Operational scripts and CLI tools
│   ├── __init__.py        # Exports script utilities
│   ├── create_admin_user.py   # Creates initial admin user from env vars
│   ├── setup_admin.py     # Interactive admin setup with TOTP
│   ├── check_admin.py     # Checks if admin user exists
│   └── seed_defaults.py   # Seeds default question sets
│
├── routes/                 # API endpoint modules
│   ├── __init__.py        # Routes package marker
│   ├── admin.py           # Instance admin routes (login, 2FA, CRUD, dashboard)
│   ├── auth.py            # User authentication (register, login, refresh)
│   ├── avatars.py         # Avatar upload/delete endpoints
│   ├── group_creator.py   # Group creator custom question sets
│   ├── groups.py          # Group CRUD and member listing
│   ├── push.py            # Push notification device token management
│   ├── question_sets.py   # Question set CRUD and group assignment
│   ├── questions.py       # Daily questions, voting, answer submission
│   └── websocket.py       # Real-time voting WebSocket endpoint
│
├── alembic/                # Database migrations
│   ├── env.py             # Alembic environment configuration
│   └── versions/          # Migration scripts
│
├── admin-ui/               # Admin frontend (React + Vite + TypeScript)
│   ├── src/
│   │   ├── api/           # Unified API client (useApi hook)
│   │   ├── components/    # Reusable React components
│   │   ├── context/       # Auth and theme context providers
│   │   ├── pages/         # Page components (Dashboard, Users, etc.)
│   │   ├── styles/        # CSS stylesheets
│   │   ├── App.tsx        # Main app and routing
│   │   └── main.tsx       # Entry point
│   └── ...
│
├── uploads/                # Uploaded files (avatars, etc.)
│
├── main.py                 # FastAPI app entry point
├── entrypoint.sh          # Docker container startup script
├── Dockerfile             # Multi-stage build (admin-ui + backend)
├── docker-compose.yml     # Docker Compose orchestration
├── requirements.txt       # Python dependencies
└── alembic.ini            # Alembic configuration
```

## Module Responsibilities

### Core (`core/`)

**Purpose**: Foundational infrastructure that everything else depends on.

- **config.py**: Environment variables, JWT secrets, database URL, avatar settings, CORS origins
- **database.py**: SQLAlchemy engine, `Base`, `SessionLocal`, `get_db` dependency
- **models.py**: ORM models (`AdminUser`, `Account`, `User`, `Group`, `DailyQuestion`, `Vote`, etc.)
- **schemas.py**: Pydantic request/response schemas for validation

**Import pattern**:

```python
from core import get_db, Account, User, DATABASE_URL, AuthLoginRequest
from core.database import SessionLocal
from core.models import Group
from core.config import USER_JWT_SECRET
```

### Auth (`auth/`)

**Purpose**: All authentication and authorization logic.

- **admin_auth.py**: Admin user authentication (login, 2FA/TOTP, JWT generation, rate limiting)
- **admin_schemas.py**: Pydantic schemas for admin API endpoints
- **utils.py**: User authentication helpers (password hashing, JWT creation/verification, avatar
  utilities, group permissions)

**Import pattern**:

```python
from auth import get_current_account, hash_password, verify_password
from auth.admin_auth import authenticate_admin, get_current_admin
from auth.utils import generate_invite_code, get_avatar_url
```

### Services (`services/`)

**Purpose**: Background processes and real-time features.

- **scheduler.py**: Background thread that generates daily questions at intervals
- **push_notifications.py**: Firebase Cloud Messaging (FCM) integration for push notifications
- **ws_manager.py**: WebSocket connection manager for real-time voting

**Import pattern**:

```python
from services import background_scheduler, push_service, manager
from services.scheduler import background_scheduler
from services.ws_manager import manager
```

### Scripts (`scripts/`)

**Purpose**: Operational scripts, CLI tools, database seeding.

- **create_admin_user.py**: Creates initial admin user from `ADMIN_INITIAL_USERNAME` and
  `ADMIN_INITIAL_PASSWORD` env vars
- **setup_admin.py**: Interactive CLI for creating admin with TOTP
- **check_admin.py**: Checks if admin user exists
- **seed_defaults.py**: Creates default question set and assigns it to groups

**Import pattern**:

```python
from scripts import initialize_default_question_set, assign_default_set_to_unassigned_groups
```

**Running scripts**:

```bash
# Inside container or with proper PYTHONPATH
python -m scripts.create_admin_user
python -m scripts.setup_admin
```

### Routes (`routes/`)

**Purpose**: API endpoint definitions grouped by domain.

Each route module:

- Defines an `APIRouter` with a specific prefix
- Implements endpoint logic
- Uses dependencies from `core`, `auth`, and `services`

**Import pattern** (in route files):

```python
from core.database import get_db
from core.models import Account, User, Group
from core.schemas import AuthLoginRequest
from auth.utils import get_current_account, verify_password
from services.push_notifications import push_service
```

## Design Principles

1. **Separation of Concerns**: Each module has a single, clear responsibility
2. **Dependency Direction**: Routes depend on core/auth/services, never the reverse
3. **No Circular Imports**: Proper package structure prevents circular dependencies
4. **Clean Public APIs**: `__init__.py` files export only what's needed
5. **Testability**: Modular structure makes unit testing easier

## Import Guidelines

- **Always use absolute imports** from package roots (`from core import ...`, not
  `from ..core import ...`)
- **Import from `__init__.py`** when possible for cleaner code
- **Specific imports** when you need to be explicit (`from core.database import SessionLocal`)
- **Avoid `import *`** except in specific cases like alembic migrations

## Running the Application

```bash
# Start all services
docker compose up -d --build

# View logs
docker compose logs -f backend

# Run migrations
docker compose exec backend alembic upgrade head

# Create admin user
docker compose exec backend python -m scripts.create_admin_user
```

## Key Entry Points

- **HTTP API**: `main.py` → routes defined in `routes/`
- **WebSocket**: `routes/websocket.py` → uses `services/ws_manager.py`
- **Background Scheduler**: `services/scheduler.py` (started in `main.py` lifespan)
- **Admin UI**: `admin-ui/` (React SPA, built and served by nginx in Docker)

## Migration Notes

This reorganization maintains **100% backward compatibility** with the API. All endpoint paths,
request/response formats, and authentication mechanisms remain unchanged. Only the internal code
organization has been improved.
