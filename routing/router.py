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
    fed_guidance: Optional[dict] = None
    temporal_context: Optional[dict] = None


class QueryRouter:
    """
    Master router that consolidates all routing logic.

    Uses a single decision tree to route queries efficiently.
    """

    def __init__(self):
        self._special_patterns = self._build_special_patterns()

    def _build_special_patterns(self) -> Dict[str, List[str]]:
        """Build patterns for special route detection."""
        return {
            'fed': [
                'fed', 'federal reserve', 'fomc', 'rate decision', 'rate cut',
                'rate hike', 'sep projection', 'dot plot', 'powell', 'monetary policy'
            ],
            'recession': [
                'recession risk', 'recession indicator', 'recession scorecard',
                'recession probability', 'are we in a recession', 'recession warning'
            ],
            'cape': [
                'cape ratio', 'shiller pe', 'stock valuation', 'market valuation',
                'are stocks overvalued', 'stock bubble', 'market bubble'
            ],
        }

    def route(self, query: str) -> RoutingResult:
        """
        Route a query to appropriate data series.

        This is the main entry point for all query routing.
        """
        # 1. Check routing cache
        cached = cache_manager.get_routing(query)
        if cached:
            return RoutingResult(
                series=cached.get('series', []),
                show_yoy=cached.get('show_yoy', False),
                combine_chart=cached.get('combine', False),
                explanation=cached.get('explanation', ''),
                chart_groups=cached.get('chart_groups'),
                is_comparison=cached.get('is_comparison', False),
                route_type='cached',
                cached=True
            )

        # 2. Check special routes (Fed, recession, CAPE)
        special_result = self._check_special_routes(query)
        if special_result:
            self._cache_result(query, special_result)
            return special_result

        # 3. Exact plan match (O(1) lookup)
        plan = registry.get_plan(query)
        if plan:
            result = self._plan_to_result(plan, 'exact')
            self._cache_result(query, result)
            return result

        # 4. Fuzzy match (for typos, close variations)
        plan = registry.fuzzy_match(query, threshold=0.7)
        if plan:
            result = self._plan_to_result(plan, 'fuzzy')
            self._cache_result(query, result)
            return result

        # 5. LLM semantic routing (fallback)
        result = self._llm_route(query)
        if result and result.series:
            self._cache_result(query, result)
            return result

        # 6. No match found - return empty result
        return RoutingResult(
            series=[],
            route_type='none',
            explanation="No matching data series found for this query."
        )

    def _check_special_routes(self, query: str) -> Optional[RoutingResult]:
        """Check if query matches special patterns (Fed, recession, CAPE)."""
        q = query.lower()

        # Fed queries
        if any(p in q for p in self._special_patterns['fed']):
            return RoutingResult(
                series=['FEDFUNDS', 'DGS10', 'DGS2'],
                show_yoy=False,
                route_type='special_fed',
                explanation="Federal Reserve related data."
            )

        # Recession queries
        if any(p in q for p in self._special_patterns['recession']):
            return RoutingResult(
                series=['SAHMREALTIME', 'T10Y2Y', 'UNRATE'],
                show_yoy=False,
                route_type='special_recession',
                explanation="Recession indicators and risk metrics."
            )

        # CAPE/valuation queries
        if any(p in q for p in self._special_patterns['cape']):
            return RoutingResult(
                series=['SP500'],  # Will be supplemented with Shiller data
                show_yoy=False,
                route_type='special_cape',
                explanation="Stock market valuation metrics."
            )

        return None

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
        Only called for ~20% of queries that don't match patterns.
        """
        # Import here to avoid circular dependency
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


# Global router instance
router = QueryRouter()
