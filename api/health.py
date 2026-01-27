"""
Health Check and Utility Endpoints
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from cache import cache_manager
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
    """Detailed API status with cache stats."""
    return JSONResponse({
        "status": "healthy",
        "version": "2.0.0",
        "config": {
            "fred_api_configured": bool(config.fred_api_key),
            "anthropic_api_configured": bool(config.anthropic_api_key),
            "economist_reviewer_enabled": config.enable_economist_reviewer,
            "dynamic_bullets_enabled": config.enable_dynamic_bullets,
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
