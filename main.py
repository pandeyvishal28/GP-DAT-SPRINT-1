"""
main.py
FastAPI application entry point for BI MVP-1.

Starts the server, registers routers, and initialises the Orchestrator
(which in turn sets up the LLM service and compiles LangGraph pipelines).

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from db.database import Database
from repositories.sop_repository import SopRepository
from repositories.glossary_repository import GlossaryRepository
from routers import glossary_router, sop_router, template_router, writing_guide_router
from services.glossary_service import GlossaryService
from services.sop_service import SopService
from repositories.template_repository import TemplateRepository
from repositories.writing_guide_repository import WritingGuideRepository
from services.template_service import TemplateService
from services.writing_guide_service import WritingGuideService
from utils.correlation import generate_correlation_id, set_correlation_id



# ── Logging setup ───────────────────────────────────────────────────────



app = FastAPI()


origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  
)


@app.get("/")
def read_root():
    return {"status": "CORS is synced!"}

def _configure_logging() -> None:
    from utils.logger import setup_logger

    setup_logger()


_ALLOWED_SOP_EXTENSIONS = (".pdf", ".docx", ".txt", ".doc")


def _scan_and_register_sops(db: Database) -> None:
    """
    Scan the sample_inputs directory and register any SOP documents
    that aren't already in the database.
    """
    sop_dir = Path("data/sample_inputs")
    logger = logging.getLogger("main.startup")

    sop_dir.mkdir(parents=True, exist_ok=True)

    existing = {s["id"] for s in db.list_sops()}
    registered_count = 0

    for path in sorted(sop_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _ALLOWED_SOP_EXTENSIONS:
            continue

        sop_id = path.stem
        if sop_id in existing:
            logger.info("  SOP already registered: %s", sop_id)
            continue

        db.register_sop(
            sop_id=sop_id,
            filename=path.name,
            filepath=str(path),
        )
        existing.add(sop_id)
        registered_count += 1
        logger.info("  Registered SOP: %s", path.name)

    total = len(db.list_sops())
    logger.info(
        "SOP scan complete — %d new, %d total SOP(s) in registry",
        registered_count, total,
    )

# ── Lifespan (startup / shutdown) ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan hook.

    On startup:
      - Configure logging
      - Initialize SQLite3 database (create tables)
      - Initialise the Orchestrator (LLM + pipelines)
      - Initialize Template Library and Writing Guide
      - Inject shared resources into all routers

    On shutdown:
      - Clean up resources
    """
    _configure_logging()
    logger = logging.getLogger("main")
    logger.info("Starting GP-DAT...")

    # 1. Initialize database
    db = Database()
    db.init_tables()
    logger.info("Database initialized at %s", db._db_path)

    # 2. Scan and register SOP documents
    _scan_and_register_sops(db)



    # 4. Initialize Template Library (Repository -> Service -> Router)
    template_repo = TemplateRepository(db=db)
    template_service = TemplateService(repository=template_repo)
    template_router.set_service(template_service)
    logger.info("Template Library initialized")

    # 5. Initialize Writing Guide (Repository -> Service -> Router)
    writing_guide_repo = WritingGuideRepository(db=db)
    writing_guide_service = WritingGuideService(repository=writing_guide_repo)
    writing_guide_router.set_service(writing_guide_service)
    logger.info("Writing Guide service initialized")

    # 6. Inject into routers
    sop_repo = SopRepository(db)
    sop_service = SopService(sop_repo)
    sop_router.set_service(sop_service)

    # 7. Initialize Glossary (Repository -> Service -> Router)
    glossary_repo = GlossaryRepository(db)
    glossary_service = GlossaryService(repository=glossary_repo)
    glossary_router.set_service(glossary_service)
    logger.info("Glossary service initialized")

    logger.info("GP-DAT ready — all pipelines compiled")

    yield  # App is running

    logger.info("Shutting down GP-DAT...")


# ── App creation ────────────────────────────────────────────────────────

app = FastAPI(
    title="GP-DAT — GP Document Processing",
    description=(
        "Agentic document-processing system MVP focusing on:\n"
        "1. **Template Library** — Manage structured GP templates\n"
        "2. **Writing Guides** — Centralized style rules\n"
        "3. **SOP Management** — Track and query source material\n"
        "4. **Glossary** — Domain term translations"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── Correlation ID + request/response logging middleware ────────────────

# Paths to skip verbose request logging (reduce noise)
_SKIP_LOG_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


@app.middleware("http")
async def correlation_and_logging_middleware(request: Request, call_next) -> Response:
    """
    Middleware that:
    1. Reads or generates a correlation ID and sets it in contextvars.
    2. Logs the incoming request and outgoing response with timing.
    """
    # 1. Correlation ID
    corr_id = request.headers.get("X-Request-ID") or generate_correlation_id()
    set_correlation_id(corr_id)

    # 2. Request logging
    _logger = logging.getLogger("middleware")
    path = request.url.path
    skip = path in _SKIP_LOG_PATHS

    if not skip:
        _logger.info(
            "Incoming %s %s (client=%s)",
            request.method,
            path,
            request.client.host if request.client else "unknown",
        )

    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed = time.perf_counter() - start

    # 3. Response logging
    if not skip:
        _logger.info(
            "Completed %s %s → %d in %.3fs",
            request.method,
            path,
            response.status_code,
            elapsed,
        )

    # 4. Propagate correlation ID in response headers
    response.headers["X-Request-ID"] = corr_id
    return response


# ── CORS ────────────────────────────────────────────────────────────────

settings = get_settings()
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ───────────────────────────────────────────────────


app.include_router(sop_router.router)
app.include_router(template_router.router)
app.include_router(glossary_router.router)
app.include_router(writing_guide_router.router)


# ── Health check ────────────────────────────────────────────────────────


@app.get("/health", tags=["System"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "gp-dat"}


@app.get("/", tags=["System"])
async def root():
    """Root endpoint with API info."""
    return {
        "service": "GP-DAT — GP Document Processing",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {

            "templates": "/api/v1/templates",
            "writing_guides": "/api/v1/writing-guides",
            "health": "/health",
        },
    }
