"""
FastAPI application entry point.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import health, jobs, pdf
from app.core.config import get_settings
from app.core.database import init_db

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure DB is initialized
    cfg = get_settings()
    init_db(cfg.DB_PATH)
    yield
    # Shutdown logic if any


app = FastAPI(
    title="PDF to Video AI",
    description=(
        "Lightweight PDF-to-video engine. Upload a PDF, review the extracted script, "
        "and generate a narrated video with B-roll footage and captions."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── IncuBrix Standard Error Handling ──────────────────────────────────────────
STATUS_TO_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "CAPACITY_EXCEEDED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    code = STATUS_TO_CODE.get(exc.status_code, "ERROR")
    retryable = exc.status_code in (429, 500, 502, 503, 504)
    message = str(exc.detail) if isinstance(exc.detail, str) else "An error occurred."
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": message,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": exc.detail if not isinstance(exc.detail, str) else None,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join(f"{e.get('loc', [])}: {e.get('msg', '')}" for e in errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": msg,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": msg,
                "retryable": False,
                "details": errors,
            },
        },
    )


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files & outputs ────────────────────────────────────────────────────
_static_dir = BASE_DIR / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_output_dir = BASE_DIR / "outputs"
_output_dir.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(_output_dir)), name="outputs")

_fixtures_dir = BASE_DIR / "fixtures"
if _fixtures_dir.exists():
    app.mount("/fixtures", StaticFiles(directory=str(_fixtures_dir)), name="fixtures")

# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(pdf.router)


# ── Web UI ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    html_path = BASE_DIR / "templates" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>PDF to Video AI</h1><p>Template not found.</p>")
