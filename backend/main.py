"""
DontAskUs Backend — Main Application Entry Point.

All endpoint logic lives in routes/*.py modules.
Shared utilities live in utils.py and config.py.
Background scheduling lives in scheduler.py.
"""

import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.gzip import GZipMiddleware

from core import ALLOWED_ORIGINS, AVATAR_UPLOAD_DIR, SCHEDULE_INTERVAL_SECONDS, LOG_LEVEL, engine, Base, SessionLocal
from core.models import ApiRequestLog
from services import background_scheduler
from scripts import initialize_default_question_set, assign_default_set_to_unassigned_groups
from routes import auth, groups, questions, question_sets, push, avatars, websocket, admin, group_creator

load_dotenv()

# ============= Logging =============
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ============= Background Scheduler =============
_scheduler_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown."""
    global _scheduler_thread
    startup_tasks_failed = []

    try:
        Base.metadata.create_all(bind=engine)
        logging.info("Database tables created/verified")
    except Exception as e:
        startup_tasks_failed.append(f"Database table creation: {e}")
        logging.exception("Database table creation failed")

    try:
        initialize_default_question_set()
        logging.info("Default question set initialized")
    except Exception as e:
        startup_tasks_failed.append(f"Default question set initialization: {e}")
        logging.exception("initialize_default_question_set failed during startup")

    try:
        assign_default_set_to_unassigned_groups()
        logging.info("Unassigned groups assigned default set")
    except Exception as e:
        startup_tasks_failed.append(f"Default set assignment: {e}")
        logging.exception("assign_default_set_to_unassigned_groups failed during startup")

    try:
        _scheduler_thread = threading.Thread(
            target=background_scheduler, args=(SCHEDULE_INTERVAL_SECONDS,), daemon=True,
        )
        _scheduler_thread.start()
        logging.info("Background scheduler started (interval: %ds)", SCHEDULE_INTERVAL_SECONDS)
    except Exception as e:
        startup_tasks_failed.append(f"Background scheduler: {e}")
        logging.exception("Background scheduler failed to start")

    startup_msg = (
        "\n" + "=" * 80 + "\n"
        "🚀 DontAskUs Backend Started Successfully!\n"
        "=" * 80 + "\n"
        "📚 API Documentation: http://localhost:8000/docs\n"
        "🔐 Admin UI: http://localhost:5173/admin\n"
        "📊 API Base URL: http://localhost:8000/api\n"
    )
    if startup_tasks_failed:
        startup_msg += f"⚠️  {len(startup_tasks_failed)} startup tasks failed - see logs\n"
    startup_msg += "=" * 80 + "\n"
    print(startup_msg)
    logging.info(startup_msg)

    yield

    logging.info("DontAskUs Backend shutting down...")
    logging.info("DontAskUs Backend shutdown complete")


# ============= Application =============
app = FastAPI(
    title="DontAskUs - Real-Time Q&A Platform",
    version="1.0.0",
    description="A self-hosted alternative to AskUs with real-time voting",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# ============= Static Files =============
app.mount("/uploads", StaticFiles(directory=str(AVATAR_UPLOAD_DIR.parent)), name="uploads")

ui_dist_path = os.path.join(os.path.dirname(__file__), "admin_ui_dist")
if os.path.exists(ui_dist_path):
    app.mount("/admin", StaticFiles(directory=ui_dist_path, html=True), name="admin-ui")
    logging.info("Admin UI mounted at /admin from %s", ui_dist_path)
else:
    logging.warning("Admin UI dist directory not found at %s", ui_dist_path)

# ============= Middleware =============

# Paths to skip logging (high-frequency or static)
_SKIP_LOG_PATHS = {"/health", "/docs", "/openapi.json", "/swagger-ui-dark.css"}

@app.middleware("http")
async def api_request_logger(request: Request, call_next):
    """Log every API request to the database for admin monitoring."""
    import time as _time
    path = request.url.path

    # Skip static/health/docs paths
    if path in _SKIP_LOG_PATHS or path.startswith("/uploads/") or path.startswith("/admin"):
        return await call_next(request)

    start = _time.monotonic()

    # Resolve account from JWT (best effort, no DB call here)
    account_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import jwt as _jwt
            from core.config import USER_JWT_SECRET, USER_JWT_ALGO
            token = auth_header.split(" ", 1)[1]
            payload = _jwt.decode(token, USER_JWT_SECRET, algorithms=[USER_JWT_ALGO])
            account_id = int(payload.get("sub", 0)) or None
        except Exception:
            pass

    response = await call_next(request)
    duration_ms = int((_time.monotonic() - start) * 1000)

    # Log to DB (fire-and-forget)
    try:
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent", "")[:500]
        query_string = str(request.url.query)[:500] if request.url.query else None

        db = SessionLocal()
        try:
            log_entry = ApiRequestLog(
                method=request.method,
                path=path[:500],
                query_string=query_string,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
                account_id=account_id,
                response_size=int(response.headers.get("content-length", 0)) or None,
            )
            db.add(log_entry)
            db.commit()

            # Prune old logs if table exceeds 50k rows (keep newest 40k)
            count = db.query(ApiRequestLog).count()
            if count > 50000:
                cutoff_id = db.query(ApiRequestLog.id).order_by(
                    ApiRequestLog.id.desc()
                ).offset(40000).limit(1).scalar()
                if cutoff_id:
                    db.query(ApiRequestLog).filter(ApiRequestLog.id <= cutoff_id).delete()
                    db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass  # Never let logging break the response

    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Swagger UI needs 'unsafe-inline' for scripts because get_swagger_ui_html
    # injects inline <script> blocks to initialise SwaggerUIBundle.
    if request.url.path in ("/docs", "/openapi.json", "/swagger-ui-dark.css"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:"
        )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.add_middleware(GZipMiddleware, minimum_size=500)

allowed_origins_list = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]
logging.info("CORS allowed origins: %s", allowed_origins_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ============= Rate Limiting =============
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request: Request, _exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})


# ============= Swagger Dark Theme =============
SWAGGER_DARK_CSS = """
@import url('https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css');

:root { color-scheme: dark; }
body { background: #0b1220; }
.swagger-ui, .swagger-ui p, .swagger-ui li, .swagger-ui span,
.swagger-ui h1, .swagger-ui h2, .swagger-ui h3, .swagger-ui h4,
.swagger-ui td, .swagger-ui th, .swagger-ui label,
.swagger-ui .info, .swagger-ui .opblock-tag, .swagger-ui .parameter__name,
.swagger-ui .parameter__type, .swagger-ui .response__status,
.swagger-ui .parameters-col_description, .swagger-ui .response-col_description,
.swagger-ui .opblock-summary-description, .swagger-ui .model-title {
    color: #f8fafc !important;
}
.swagger-ui a { color: #67e8f9 !important; }
.swagger-ui .topbar { background: #0b1220; border-bottom: 1px solid #1f2937; }
.swagger-ui .topbar .download-url-wrapper { display: none; }
.swagger-ui .topbar .link span { color: #e2e8f0; }
.swagger-ui .scheme-container { background: #0f172a; border: 1px solid #1f2937; }
.swagger-ui .opblock { background: #0f172a; border: 1px solid #1f2937; }
.swagger-ui .opblock .opblock-summary { background: #0f172a; }
.swagger-ui .opblock .opblock-section-header { background: #111827; border-color: #1f2937; }
.swagger-ui table thead tr th { background: #111827; border-color: #1f2937; }
.swagger-ui table tbody tr td { border-color: #1f2937; }
.swagger-ui .model-box { background: #0b1220; border-color: #1f2937; }
.swagger-ui .prop-type { color: #67e8f9 !important; }
.swagger-ui .opblock-description-wrapper p { color: #cbd5e1 !important; }
.swagger-ui .btn { background: #22d3ee; color: #0b1220; border: none; }
.swagger-ui .btn:hover { background: #0ea5e9; }
.swagger-ui .btn.authorize { background: #22c55e; color: #0b1220; }
.swagger-ui .btn.authorize:hover { background: #16a34a; }
.swagger-ui .btn.authorize svg { fill: #0b1220; }
.swagger-ui .authorization__btn svg { fill: #f8fafc !important; }
.swagger-ui .locked svg, .swagger-ui .unlocked svg { fill: #f8fafc !important; }
.swagger-ui .opblock-summary-operation-id svg,
.swagger-ui .opblock-summary svg,
.swagger-ui .authorization__btn.locked svg,
.swagger-ui .authorization__btn.unlocked svg,
.swagger-ui .opblock .authorization__btn svg { fill: #f8fafc !important; }
.swagger-ui .copy-to-clipboard { color: #22d3ee; }
.swagger-ui .markdown code, .swagger-ui .code code { background: #111827; color: #e2e8f0; }
.swagger-ui .response-control-media-range { color: #e2e8f0; }
.swagger-ui textarea, .swagger-ui input[type="text"], .swagger-ui select {
    background: #0b1220; color: #e2e8f0; border: 1px solid #1f2937;
}
.swagger-ui input::placeholder, .swagger-ui textarea::placeholder { color: #94a3b8; }
"""


@app.get("/swagger-ui-dark.css", include_in_schema=False)
async def swagger_dark_css():
    return Response(content=SWAGGER_DARK_CSS, media_type="text/css")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="DontAskUs API Docs",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui-dark.css",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "displayRequestDuration": True,
            "persistAuthorization": True,
            "syntaxHighlight.theme": "monokai",
        },
    )


# ============= Register Routers =============
app.include_router(auth.router)
app.include_router(groups.router)
app.include_router(questions.router)
app.include_router(question_sets.router)
app.include_router(push.router)
app.include_router(avatars.router)
app.include_router(websocket.router)
app.include_router(admin.router)
app.include_router(group_creator.router)


# ============= Health Check =============
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
