"""
Master Router - Single Decision Tree for Query Routing

Priority order (checked in sequence, stops at first match):
1. Special queries (Fed SEP, recession scorecard, CAPE valuation)
2. Exact plan match (against unified registry - O(1) lookup)
3. Keyword/pattern match (fast regex patterns)
4. LLM semantic routing (only if above fail)

Goal: 80%+ of queries resolve at steps 1-3 (no LLM call needed)
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from registry import registry
from cache import cache_manager
from .special_routes import special_router, SpecialRouteResult


@dataclass
class RoutingResult:
    """Result of routing a query."""

    series: List[str]
    show_yoy: bool = False
    combine_chart: bool = False
    explanation: str = ''
    chart_groups: Optional[List[dict]] = None
    is_comparison: bool = False

    # Metadata
    route_type: str = 'unknown'  # 'exact', 'fuzzy', 'llm', 'special'
    cached: bool = False

    # Special data for display boxes
    fed_guidance: Optional[dict] = None
    fed_sep_html: Optional[str] = None
    recession_html: Optional[str] = None
    cape_html: Optional[str] = None
    polymarket_html: Optional[str] = None
    temporal_context: Optional[dict] = None


class QueryRouter:
    """
    Master router that consolidates all routing logic.

    Uses a single decision tree to route queries efficiently.
    """

    def __init__(self):
        self._query_understanding = None
        self._query_router_module = None
        self._rag_module = None
        self._stocks_module = None
        self._load_advanced_modules()

    def _load_advanced_modules(self):
        """Load advanced routing modules."""
        # Query understanding
        try:
            from agents.query_understanding import understand_query, get_routing_recommendation
            self._query_understanding = {
                'understand': understand_query,
                'get_routing': get_routing_recommendation,
            }
            print("[Router] Query understanding: available")
        except Exception as e:
            print(f"[Router] Query understanding: not available - {e}")

        # Query router (comparisons)
        try:
            from agents.query_router import smart_route_query, is_comparison_query, route_comparison_query
            self._query_router_module = {
                'smart_route': smart_route_query,
                'is_comparison': is_comparison_query,
                'route_comparison': route_comparison_query,
            }
            print("[Router] Query router: available")
        except Exception as e:
            print(f"[Router] Query router: not available - {e}")

        # Series RAG
        try:
            from agents.series_rag import rag_query_plan, retrieve_relevant_series
            self._rag_module = {
                'query_plan': rag_query_plan,
                'retrieve': retrieve_relevant_series,
            }
            print("[Router] Series RAG: available")
        except Exception as e:
            print(f"[Router] Series RAG: not available - {e}")

        # Stocks module
        try:
            from agents.stocks import find_market_plan, is_market_query, MARKET_SERIES
            self._stocks_module = {
                'find_plan': find_market_plan,
                'is_market': is_market_query,
                'series': MARKET_SERIES,
            }
            print("[Router] Stocks: available")
        except Exception as e:
            print(f"[Router] Stocks: not available - {e}")

    def route(self, query: str) -> RoutingResult:
        """
        Route a query to appropriate data series.

        This is the main entry point for all query routing.
        """
        # 1. Check routing cache
        cached = cache_manager.get_routing(query)
        if cached:
            result = RoutingResult(
                series=cached.get('series', []),
                show_yoy=cached.get('show_yoy', False),
                combine_chart=cached.get('combine', False),
                explanation=cached.get('explanation', ''),
                chart_groups=cached.get('chart_groups'),
                is_comparison=cached.get('is_comparison', False),
                route_type='cached',
                cached=True
            )
            return result

        # 2. Check special routes (Fed SEP, recession, health check)
        special_result = special_router.check(query)
        if special_result and special_result.matched:
            result = self._special_to_routing_result(special_result)
            self._cache_result(query, result)
            return result

        # 3. Check market queries (stocks, indices)
        if self._stocks_module and self._stocks_module['is_market'](query):
            market_plan = self._stocks_module['find_plan'](query)
            if market_plan:
                result = self._plan_to_result(market_plan, 'market')
                self._cache_result(query, result)
                return result

        # 4. Check comparison queries (both domestic and international)
        if self._query_router_module and self._query_router_module['is_comparison'](query):
            # Use smart_route which handles both domestic and international comparisons
            comparison_plan = self._query_router_module['smart_route'](query)
            if comparison_plan and comparison_plan.get('series'):
                result = self._plan_to_result(comparison_plan, 'comparison')
                result.is_comparison = True
                self._cache_result(query, result)
                return result

        # 5. Exact plan match (O(1) lookup)
        plan = registry.get_plan(query)
        if plan:
            result = self._plan_to_result(plan, 'exact')
            self._cache_result(query, result)
            return result

        # 6. Deep query understanding (if available)
        if self._query_understanding:
            try:
                understanding = self._query_understanding['understand'](query)
                if understanding:
                    routing = self._query_understanding['get_routing'](understanding)
                    if routing and routing.get('suggested_topic'):
                        topic = routing['suggested_topic']
                        plan = registry.get_plan(topic)
                        if plan:
                            result = self._plan_to_result(plan, 'understanding')
                            if routing.get('show_yoy') is not None:
                                result.show_yoy = routing['show_yoy']
                            self._cache_result(query, result)
                            return result
            except Exception as e:
                print(f"[Router] Understanding error: {e}")

        # 7. RAG-based retrieval
        if self._rag_module:
            try:
                rag_plan = self._rag_module['query_plan'](query)
                if rag_plan and rag_plan.get('series'):
                    result = self._plan_to_result(rag_plan, 'rag')
                    self._cache_result(query, result)
                    return result
            except Exception as e:
                print(f"[Router] RAG error: {e}")

        # 8. Fuzzy match (for typos, close variations)
        plan = registry.fuzzy_match(query, threshold=0.7)
        if plan:
            result = self._plan_to_result(plan, 'fuzzy')
            self._cache_result(query, result)
            return result

        # 9. LLM semantic routing (fallback)
        result = self._llm_route(query)
        if result and result.series:
            self._cache_result(query, result)
            return result

        # 10. No match found - return empty result
        return RoutingResult(
            series=[],
            route_type='none',
            explanation="No matching economic data found for this query."
        )

    def _special_to_routing_result(self, special: SpecialRouteResult) -> RoutingResult:
        """Convert SpecialRouteResult to RoutingResult."""
        result = RoutingResult(
            series=special.series,
            show_yoy=special.show_yoy,
            route_type=f'special_{special.route_type}',
        )

        # Copy over special HTML boxes
        if 'fed_sep_html' in special.extra_data:
            result.fed_sep_html = special.extra_data['fed_sep_html']
        if 'fed_guidance' in special.extra_data:
            result.fed_guidance = special.extra_data['fed_guidance']
        if 'recession_html' in special.extra_data:
            result.recession_html = special.extra_data['recession_html']

        return result

    def _plan_to_result(self, plan: dict, route_type: str) -> RoutingResult:
        """Convert a query plan dict to RoutingResult."""
        # Handle both list and bool for show_yoy
        show_yoy = plan.get('show_yoy', False)
        if isinstance(show_yoy, list):
            show_yoy = show_yoy[0] if show_yoy else False

        return RoutingResult(
            series=plan.get('series', []),
            show_yoy=show_yoy,
            combine_chart=plan.get('combine', plan.get('combine_chart', False)),
            explanation=plan.get('explanation', ''),
            chart_groups=plan.get('chart_groups'),
            is_comparison=plan.get('is_comparison', False),
            route_type=route_type
        )

    def _llm_route(self, query: str) -> Optional[RoutingResult]:
        """
        Use LLM to route complex/novel queries.

        This is the fallback when pattern matching fails.
        """
        try:
            from ai import classify_query
            classification = classify_query(query, registry.all_plan_keys())

            if classification and classification.get('topic'):
                plan = registry.get_plan(classification['topic'])
                if plan:
                    result = self._plan_to_result(plan, 'llm')
                    if classification.get('show_yoy') is not None:
                        result.show_yoy = classification['show_yoy']
                    return result
        except ImportError:
            pass
        except Exception as e:
            print(f"[Router] LLM routing error: {e}")

        return None

    def _cache_result(self, query: str, result: RoutingResult) -> None:
        """Cache routing result."""
        plan_dict = {
            'series': result.series,
            'show_yoy': result.show_yoy,
            'combine': result.combine_chart,
            'explanation': result.explanation,
            'chart_groups': result.chart_groups,
            'is_comparison': result.is_comparison,
        }
        cache_manager.set_routing(query, plan_dict)

    def get_polymarket_html(self, query: str) -> Optional[str]:
        """Get Polymarket predictions for a query."""
        return special_router.get_polymarket_predictions(query)


# Global router instance
router = QueryRouter()
