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

from core import ALLOWED_ORIGINS, AVATAR_UPLOAD_DIR, SCHEDULE_INTERVAL_SECONDS, LOG_LEVEL, engine, Base
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
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
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
