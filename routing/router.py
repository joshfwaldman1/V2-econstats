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

    Architecture (V2 "Thinking First"):
    1. Query understanding - deeply analyze query BEFORE routing
    2. Special routes - Fed SEP, recession scorecard, CAPE
    3. Exact plan match - O(1) lookup
    4. Validation layer - gut check that proposed series match query
    5. Fuzzy match - for typos
    6. LLM semantic routing - fallback with dynamic plan building
    """

    def __init__(self):
        self._query_understanding = None
        self._query_router_module = None
        self._rag_module = None
        self._stocks_module = None
        self._validation_module = None  # New: validation layer
        self._load_advanced_modules()

    def _load_advanced_modules(self):
        """Load advanced routing modules."""
        # Query understanding ("thinking first" layer)
        try:
            from agents.query_understanding import understand_query, get_routing_recommendation, validate_series_for_query
            self._query_understanding = {
                'understand': understand_query,
                'get_routing': get_routing_recommendation,
            }
            self._validation_module = {
                'validate': validate_series_for_query
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

        V2 "Thinking First" Architecture:
        1. Check cache
        2. Run query understanding (Gemini analyzes query BEFORE routing)
        3. Check special routes
        4. Check market queries
        5. Check comparison queries
        6. Exact plan match
        7. Deep understanding routing
        8. RAG-based retrieval
        9. Fuzzy match
        10. LLM fallback with dynamic plan building
        11. VALIDATION LAYER - gut check that series match query intent
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

        # 2. Run query understanding FIRST ("thinking first" layer)
        # This deeply analyzes the query to understand demographics, sectors, etc.
        query_understanding = None
        if self._query_understanding:
            try:
                query_understanding = self._query_understanding['understand'](query)
            except Exception as e:
                print(f"[Router] Query understanding error: {e}")

        # 3. EXACT PLAN MATCH FIRST (O(1) lookup) - before special routes!
        # This ensures specific plans like "fed rates" take precedence over generic routes
        plan = registry.get_plan(query)
        if plan:
            result = self._plan_to_result(plan, 'exact')
            result = self._validate_and_correct(result, query_understanding)
            self._cache_result(query, result)
            return result

        # 4. Check special routes (Fed SEP, recession, health check)
        # Only runs if no exact plan match - special routes are broader/generic
        special_result = special_router.check(query)
        if special_result and special_result.matched:
            result = self._special_to_routing_result(special_result)
            self._cache_result(query, result)
            return result

        # 5. Check market queries (stocks, indices)
        if self._stocks_module and self._stocks_module['is_market'](query):
            market_plan = self._stocks_module['find_plan'](query)
            if market_plan:
                result = self._plan_to_result(market_plan, 'market')
                result = self._validate_and_correct(result, query_understanding)
                self._cache_result(query, result)
                return result

        # 6. Check comparison queries (both domestic and international)
        if self._query_router_module and self._query_router_module['is_comparison'](query):
            # Use smart_route which handles both domestic and international comparisons
            comparison_plan = self._query_router_module['smart_route'](query)
            if comparison_plan and comparison_plan.get('series'):
                result = self._plan_to_result(comparison_plan, 'comparison')
                result.is_comparison = True
                result = self._validate_and_correct(result, query_understanding)
                self._cache_result(query, result)
                return result

        # 7. Deep query understanding routing (if available)
        if query_understanding:
            try:
                routing = self._query_understanding['get_routing'](query_understanding)
                if routing and routing.get('suggested_topic'):
                    topic = routing['suggested_topic']
                    plan = registry.get_plan(topic)
                    if plan:
                        result = self._plan_to_result(plan, 'understanding')
                        if routing.get('show_yoy') is not None:
                            result.show_yoy = routing['show_yoy']
                        result = self._validate_and_correct(result, query_understanding)
                        self._cache_result(query, result)
                        return result
            except Exception as e:
                print(f"[Router] Understanding error: {e}")

        # 8. RAG-based retrieval
        if self._rag_module:
            try:
                rag_plan = self._rag_module['query_plan'](query)
                if rag_plan and rag_plan.get('series'):
                    result = self._plan_to_result(rag_plan, 'rag')
                    result = self._validate_and_correct(result, query_understanding)
                    self._cache_result(query, result)
                    return result
            except Exception as e:
                print(f"[Router] RAG error: {e}")

        # 9. Fuzzy match (for typos, close variations)
        plan = registry.fuzzy_match(query, threshold=0.7)
        if plan:
            result = self._plan_to_result(plan, 'fuzzy')
            result = self._validate_and_correct(result, query_understanding)
            self._cache_result(query, result)
            return result

        # 10. LLM semantic routing (fallback with dynamic plan building)
        result = self._llm_route(query)
        if result and result.series:
            result = self._validate_and_correct(result, query_understanding)
            self._cache_result(query, result)
            return result

        # 11. FINAL FALLBACK: Use validation layer to override with correct series
        # This catches cases where routing failed but we know what data is needed
        if self._validation_module and query_understanding:
            validation = self._validation_module['validate'](query_understanding, [])
            if not validation.get('valid') and validation.get('corrected_series'):
                print(f"[Router] Validation override: {validation['reason']}")
                result = RoutingResult(
                    series=validation['corrected_series'],
                    route_type='validation_override',
                    explanation=validation.get('reason', '')
                )
                self._cache_result(query, result)
                return result

        # 12. No match found - return empty result
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
        if 'cape_html' in special.extra_data:
            result.cape_html = special.extra_data['cape_html']

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

    def _validate_and_correct(self, result: RoutingResult, query_understanding: dict) -> RoutingResult:
        """
        Validate that proposed series match the query intent.

        This is the "gut check" layer - if query understanding detected specific
        entities (demographics, sectors, regions) but routing returned generic
        series, we override with the correct specific series.

        IMPORTANT: Only overrides when routing returned GENERIC series for a
        SPECIFIC query. Does NOT override when routing already has specific
        series (e.g., state-level MNUR, demographic LNS14000006, sector MANEMP).

        Args:
            result: The routing result to validate
            query_understanding: The Gemini analysis of the query

        Returns:
            Corrected RoutingResult if validation failed, otherwise original
        """
        if not self._validation_module or not query_understanding:
            return result

        # Skip validation for exact plan matches that already have specific series.
        # The validation layer is designed to catch GENERIC data returned for SPECIFIC
        # queries — not to override already-specific series from curated plans.
        if result.route_type == 'exact' and result.series:
            # Check if the plan already has specific (non-generic) series.
            # Generic series are things like UNRATE, PAYEMS, CPIAUCSL etc.
            # Specific series are state-level (e.g., MNUR), demographic (LNS14000006),
            # or sector-specific (MANEMP, USCONS, etc.)
            GENERIC_NATIONAL = {'UNRATE', 'PAYEMS', 'CPIAUCSL', 'CPILFESL', 'GDPC1',
                                'A191RL1Q225SBEA', 'FEDFUNDS', 'DGS10', 'CIVPART',
                                'LNS12300060', 'EMRATIO', 'PCE', 'PCEPILFE'}
            series_set = set(result.series)
            has_specific = bool(series_set - GENERIC_NATIONAL)
            if has_specific:
                # Plan already has specific series — trust it
                return result

        try:
            validation = self._validation_module['validate'](query_understanding, result.series)

            if not validation.get('valid') and validation.get('corrected_series'):
                print(f"[Router] Validation correction: {validation['reason']}")
                # Create corrected result
                return RoutingResult(
                    series=validation['corrected_series'],
                    show_yoy=result.show_yoy,
                    combine_chart=result.combine_chart,
                    explanation=validation.get('reason', result.explanation),
                    chart_groups=result.chart_groups,
                    is_comparison=result.is_comparison,
                    route_type=f"{result.route_type}_validated",
                    fed_guidance=result.fed_guidance,
                    fed_sep_html=result.fed_sep_html,
                    recession_html=result.recession_html,
                    cape_html=result.cape_html,
                    polymarket_html=result.polymarket_html,
                    temporal_context=result.temporal_context,
                )
        except Exception as e:
            print(f"[Router] Validation error: {e}")

        return result

    def _llm_route(self, query: str) -> Optional[RoutingResult]:
        """
        Use LLM to route complex/novel queries.

        This is the fallback when pattern matching fails.
        Uses build_dynamic_plan to select series directly (not from plan names).
        """
        try:
            from ai import build_dynamic_plan

            # Get all available series with descriptions for the LLM
            available_series = self._get_series_catalog()

            # Build a dynamic plan based on available series
            plan = build_dynamic_plan(query, available_series)

            if plan and plan.get('series'):
                return RoutingResult(
                    series=plan['series'],
                    show_yoy=plan.get('show_yoy', False),
                    explanation=plan.get('explanation', ''),
                    route_type='dynamic_llm'
                )
        except ImportError as e:
            print(f"[Router] LLM import error: {e}")
        except Exception as e:
            print(f"[Router] LLM routing error: {e}")

        # Fallback to old classify_query if dynamic fails
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
        except Exception as e:
            print(f"[Router] Fallback LLM error: {e}")

        return None

    def _get_series_catalog(self) -> List[Dict]:
        """Get catalog of all available series for dynamic routing."""
        # Start with registered series (high-quality descriptions)
        catalog = []
        for sid, info in registry._series.items():
            catalog.append({
                'id': sid,
                'name': info.name,
                'description': info.short_description or info.bullets[0] if info.bullets else ''
            })

        # Add common FRED series that may not be in registry
        # This ensures LLM can route to important series even without plans
        common_series = [
            {'id': 'CUSR0000SEHA', 'name': 'CPI: Rent of Primary Residence', 'description': 'What renters actually pay for rent'},
            {'id': 'CUSR0000SEHC', 'name': 'CPI: Owners Equivalent Rent', 'description': 'Imputed rent for homeowners'},
            {'id': 'CUSR0000SAF1', 'name': 'CPI: Food', 'description': 'Food price inflation'},
            {'id': 'CUSR0000SETB01', 'name': 'CPI: Gasoline', 'description': 'Gas price changes'},
            {'id': 'CUSR0000SAM', 'name': 'CPI: Medical Care', 'description': 'Healthcare cost inflation'},
            {'id': 'DSPIC96', 'name': 'Real Disposable Income', 'description': 'Income after taxes, adjusted for inflation'},
            {'id': 'CES0500000003', 'name': 'Average Hourly Earnings', 'description': 'Average wages for private workers'},
            {'id': 'LES1252881600Q', 'name': 'Real Median Weekly Earnings', 'description': 'Middle-class wages adjusted for inflation'},
            {'id': 'JTSJOL', 'name': 'Job Openings', 'description': 'Unfilled job positions (JOLTS)'},
            {'id': 'JTSQUR', 'name': 'Quits Rate', 'description': 'Workers voluntarily leaving jobs'},
            {'id': 'PCE', 'name': 'Personal Consumption Expenditures', 'description': 'Consumer spending'},
            {'id': 'DGORDER', 'name': 'Durable Goods Orders', 'description': 'Orders for long-lasting manufactured goods'},
            {'id': 'INDPRO', 'name': 'Industrial Production', 'description': 'Factory output'},
            {'id': 'TOTALSA', 'name': 'Total Vehicle Sales', 'description': 'Car and truck sales'},
            {'id': 'RRVRUSQ156N', 'name': 'Rental Vacancy Rate', 'description': 'Percent of rentals vacant'},
            {'id': 'MSPUS', 'name': 'Median Home Sale Price', 'description': 'Typical home selling price'},
            {'id': 'PERMIT', 'name': 'Building Permits', 'description': 'Future construction activity'},
            {'id': 'VIXCLS', 'name': 'VIX Volatility Index', 'description': 'Stock market fear gauge'},
            {'id': 'DTWEXBGS', 'name': 'US Dollar Index', 'description': 'Dollar strength vs other currencies'},
            {'id': 'T10YIE', 'name': '10-Year Breakeven Inflation', 'description': 'Market inflation expectations'},
        ]

        # Add common series if not already in catalog
        existing_ids = {s['id'] for s in catalog}
        for series in common_series:
            if series['id'] not in existing_ids:
                catalog.append(series)

        return catalog

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
