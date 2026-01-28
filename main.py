"""
EconStats V2 - Modular Economic Data Explorer

A clean, fast, and maintainable economic data visualization app.

Key improvements over V1:
- Modular architecture (2,486 lines -> ~150 lines in main.py)
- Single routing decision tree (4 systems -> 1)
- Three-tier caching
- 80% fewer LLM calls for common queries
- React + Radix UI frontend

Features:
- 9 data sources: FRED, Alpha Vantage, Zillow, EIA, DBnomics, Shiller
- 608 pre-built query plans
- Special handlers: Fed SEP, recession scorecard, Polymarket, CAPE
- AI summaries with Gemini audit layer
- Dynamic or static chart bullets
- Temporal filtering ("in 2022", "during covid")
- Streaming SSE support
"""

import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# Import modules
from config import config
from registry import registry
from api import search_router, health_router


# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title="EconStats",
    description="Economic data exploration powered by AI",
    version="2.0.0"
)

# CORS for development (React runs on different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates (legacy, for HTMX fallback)
templates = Jinja2Templates(directory="templates")
app.state.templates = templates

# Include routers
app.include_router(search_router)
app.include_router(health_router)


# Exception handler for debugging
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    import traceback
    print("=" * 60)
    print("UNHANDLED EXCEPTION:")
    print("=" * 60)
    traceback.print_exc()
    print("=" * 60)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )


# =============================================================================
# REACT STATIC FILE SERVING
# =============================================================================

# Path to React build
REACT_BUILD_PATH = Path(__file__).parent / "frontend" / "dist"


def is_production() -> bool:
    """Check if we're in production (React build exists)."""
    return (REACT_BUILD_PATH / "index.html").exists()


# Serve React static files in production
if is_production():
    # Mount assets directory
    app.mount("/assets", StaticFiles(directory=REACT_BUILD_PATH / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """Serve React SPA - all non-API routes go to index.html."""
        # Check if it's a static file
        file_path = REACT_BUILD_PATH / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html for client-side routing
        return FileResponse(REACT_BUILD_PATH / "index.html")


# =============================================================================
# STARTUP
# =============================================================================

@app.on_event("startup")
async def startup():
    """Initialize the application."""
    print("=" * 60)
    print("EconStats V2 Starting Up")
    print("=" * 60)

    # Load registry (query plans, series metadata)
    registry.load()

    # Log configuration
    print("-" * 60)
    print("API Keys:")
    print(f"  FRED: {'SET' if config.fred_api_key else 'NOT SET'}")
    print(f"  Anthropic: {'SET' if config.anthropic_api_key else 'NOT SET'}")
    print(f"  Google/Gemini: {'SET' if config.google_api_key else 'NOT SET'}")
    print(f"  Alpha Vantage: {'SET' if config.alphavantage_api_key else 'NOT SET'}")

    print("-" * 60)
    print("Features:")
    print(f"  Economist reviewer: {'ON' if config.enable_economist_reviewer else 'OFF'}")
    print(f"  Dynamic bullets: {'ON' if config.enable_dynamic_bullets else 'OFF'}")
    print(f"  Gemini audit: {'ON' if config.enable_gemini_audit else 'OFF'}")

    print("-" * 60)
    print("Frontend:")
    if is_production():
        print(f"  Mode: Production (React build at {REACT_BUILD_PATH})")
    else:
        print("  Mode: Development (use 'npm run dev' in frontend/)")
        print("  React dev server: http://localhost:3000")
        print("  API server: http://localhost:8000")

    print("=" * 60)
    print("Ready to serve requests")
    print("=" * 60)


# =============================================================================
# LEGACY HTML ROUTES (for HTMX frontend)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Home page.

    In production: Serve React app
    In development: Serve Jinja template (HTMX fallback)
    """
    if is_production():
        return FileResponse(REACT_BUILD_PATH / "index.html")

    # Development fallback - serve Jinja template
    last_updated = None
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%cd', '--date=format:%b %d, %Y %H:%M UTC'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            last_updated = result.stdout.strip()
    except Exception:
        pass

    return templates.TemplateResponse("index.html", {
        "request": request,
        "last_updated": last_updated,
    })


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    if is_production():
        return FileResponse(REACT_BUILD_PATH / "index.html")

    return templates.TemplateResponse("about.html", {
        "request": request,
    })


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
