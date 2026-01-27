"""
Health Check and Utility Endpoints
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from cache import cache_manager
from sources import source_manager
from routing import special_router
from config import config

health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "version": "2.0.0"
    })


@health_router.get("/api/status")
async def api_status():
    """Detailed API status with all module availability."""
    return JSONResponse({
        "status": "healthy",
        "version": "2.0.0",
        "config": {
            "fred_api_configured": bool(config.fred_api_key),
            "anthropic_api_configured": bool(config.anthropic_api_key),
            "google_api_configured": bool(config.google_api_key),
            "alphavantage_api_configured": bool(config.alphavantage_api_key),
            "economist_reviewer_enabled": config.enable_economist_reviewer,
            "dynamic_bullets_enabled": config.enable_dynamic_bullets,
        },
        "data_sources": source_manager.available_sources(),
        "special_routes": {
            "fed_sep": special_router.fed_available,
            "recession_scorecard": special_router.recession_available,
            "polymarket": special_router.polymarket_available,
        },
        "cache": cache_manager.stats(),
    })


@health_router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    templates = request.app.state.templates
    return templates.TemplateResponse("about.html", {
        "request": request,
        "version": "2.0.0",
    })


@health_router.get("/api/cache/clear")
async def clear_cache():
    """Clear all caches (admin endpoint)."""
    cache_manager.clear_all()
    return JSONResponse({
        "status": "success",
        "message": "All caches cleared"
    })


@health_router.get("/api/sources")
async def list_sources():
    """List all available data sources."""
    return JSONResponse({
        "sources": source_manager.available_sources()
    })
