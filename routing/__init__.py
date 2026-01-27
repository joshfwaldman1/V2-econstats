"""Routing module - Consolidated query routing."""

from .router import QueryRouter, RoutingResult, router
from .special_routes import SpecialRouter, SpecialRouteResult, special_router

__all__ = [
    'QueryRouter',
    'RoutingResult',
    'router',
    'SpecialRouter',
    'SpecialRouteResult',
    'special_router',
]
