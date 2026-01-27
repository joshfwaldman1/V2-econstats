"""
EconStats V2 - Modular Economic Data Explorer

A clean, fast, and maintainable economic data visualization app.

Key improvements over V1:
- Modular architecture (2,486 lines -> ~150 lines in main.py)
- Single routing decision tree (4 systems -> 1)
- Three-tier caching
- 80% fewer LLM calls for common queries

Features:
- 9 data sources: FRED, Alpha Vantage, Zillow, EIA, DBnomics, Shiller
- 608 pre-built query plans
- Special handlers: Fed SEP, recession scorecard, Polymarket, CAPE
- AI summaries with optional economist reviewer
- Dynamic or static chart bullets
- Temporal filtering ("in 2022", "during covid")
- Streaming SSE support
"""

import subprocess
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

# Templates
templates = Jinja2Templates(directory="templates")
app.state.templates = templates

# Static files (if exists)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except RuntimeError:
    pass  # No static directory

# Include routers
app.include_router(search_router)
app.include_router(health_router)


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
    print(f"  Google: {'SET' if config.google_api_key else 'NOT SET'}")
    print(f"  Alpha Vantage: {'SET' if config.alphavantage_api_key else 'NOT SET'}")

    print("-" * 60)
    print("Features:")
    print(f"  Economist reviewer: {'ON' if config.enable_economist_reviewer else 'OFF'}")
    print(f"  Dynamic bullets: {'ON' if config.enable_dynamic_bullets else 'OFF'}")

    # Data sources are initialized when source_manager is imported
    # Special routes are initialized when special_router is imported
    # These will print their own status messages

    print("=" * 60)
    print("Ready to serve requests")
    print("=" * 60)


# =============================================================================
# MAIN ROUTES
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with search interface."""
    # Get last update time
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
