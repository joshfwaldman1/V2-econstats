"""
EconStats V2 - Modular Economic Data Explorer

A clean, fast, and maintainable economic data visualization app.

Key improvements over V1:
- Modular architecture (2,486 lines -> ~200 lines in main.py)
- Single routing decision tree (4 systems -> 1)
- Three-tier caching
- 80% fewer LLM calls for common queries
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

    # Load registry
    registry.load()

    # Log configuration
    print(f"FRED_API_KEY: {'SET' if config.fred_api_key else 'NOT SET'}")
    print(f"ANTHROPIC_API_KEY: {'SET' if config.anthropic_api_key else 'NOT SET'}")
    print(f"Economist reviewer: {'ON' if config.enable_economist_reviewer else 'OFF'}")
    print(f"Dynamic bullets: {'ON' if config.enable_dynamic_bullets else 'OFF'}")
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
