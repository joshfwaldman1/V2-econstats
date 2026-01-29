"""
Master Router - Unified LLM Router Architecture (V3)

Replaces the old 12-step cascade with a streamlined 5-step flow:
  1. Cache hit
  2. Exact plan match (O(1) lookup)
  3. LLM Router (single Gemini call — understands + picks plan)
  4. Special enrichment (additive HTML boxes, not exclusive replacement)
  5. Deterministic validation (keyword-based gut check, no LLM)

Fallback chain when Gemini is down:
  3b. Fuzzy match (difflib)
  3c. Old LLM fallback (Claude dynamic plan + classify_query)

The key insight: curated plans are excellent — the problem was FINDING
the right one. One Gemini call replaces the old understanding → RAG →
fuzzy → LLM fallback chain, cutting latency from 1.5-6.5s to 0.5-1.2s
for non-cached, non-exact queries.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from registry import registry
from cache import cache_manager
from .special_routes import special_router, SpecialRouteResult
from .plan_catalog import plan_catalog, PlanCatalog
from .llm_router import LLMRouter


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
    route_type: str = 'unknown'  # 'exact', 'fuzzy', 'llm_v3', 'special', 'fallback'
    cached: bool = False

    # Special data for display boxes (additive enrichment)
    fed_guidance: Optional[dict] = None
    fed_sep_html: Optional[str] = None
    recession_html: Optional[str] = None
    cape_html: Optional[str] = None
    polymarket_html: Optional[str] = None
    temporal_context: Optional[dict] = None


# =============================================================================
# DETERMINISTIC VALIDATION
# =============================================================================
# Keyword-based checks that catch obvious routing mistakes.
# No LLM needed — just pattern matching on query vs series IDs.

# Generic national series that should NOT be the sole answer
# for queries about specific demographics, sectors, or regions.
GENERIC_NATIONAL = {
    'UNRATE', 'PAYEMS', 'CPIAUCSL', 'CPILFESL', 'GDPC1',
    'A191RL1Q225SBEA', 'FEDFUNDS', 'DGS10', 'CIVPART',
    'LNS12300060', 'EMRATIO', 'PCE', 'PCEPILFE',
}

# Demographic keyword → correct FRED series
DEMOGRAPHIC_OVERRIDES = {
    'black': ['LNS14000006', 'LNS12300006', 'LNS11300006'],
    'african american': ['LNS14000006', 'LNS12300006', 'LNS11300006'],
    'hispanic': ['LNS14000009', 'LNS12300009', 'LNS11300009'],
    'latino': ['LNS14000009', 'LNS12300009', 'LNS11300009'],
    'latina': ['LNS14000009', 'LNS12300009', 'LNS11300009'],
    'women': ['LNS14000002', 'LNS12300002', 'LNS11300002'],
    'asian': ['LNS14000004', 'LNS12300004', 'LNS11300004'],
    'youth': ['LNS14000012', 'LNS14000036'],
    'teen': ['LNS14000012'],
    'veteran': ['LNS14049526'],
}

# Sector keyword → correct FRED series
SECTOR_OVERRIDES = {
    'manufacturing': ['MANEMP', 'IPMAN'],
    'construction': ['USCONS', 'HOUST', 'PERMIT'],
    'restaurant': ['CES7072200001'],
    'healthcare': ['CES6562000001'],
    'tech': ['USINFO', 'CES5000000001'],
    'retail': ['USTRADE', 'RSXFS'],
    'government': ['USGOVT', 'CES9000000001'],
    'hospitality': ['USLAH', 'CES7000000001'],
    'finance': ['USFIRE', 'CES5500000001'],
}

# State name → FRED series codes (unemployment rate + nonfarm payrolls)
# FRED convention: {STATE_CODE}UR = unemployment rate, {STATE_CODE}NA = nonfarm payrolls
STATE_OVERRIDES = {
    'alabama': ['ALUR', 'ALNA'], 'alaska': ['AKUR', 'AKNA'],
    'arizona': ['AZUR', 'AZNA'], 'arkansas': ['ARUR', 'ARNA'],
    'california': ['CAUR', 'CANA'], 'colorado': ['COUR', 'CONA'],
    'connecticut': ['CTUR', 'CTNA'], 'delaware': ['DEUR', 'DENA'],
    'florida': ['FLUR', 'FLNA'], 'georgia': ['GAUR', 'GANA'],
    'hawaii': ['HIUR', 'HINA'], 'idaho': ['IDUR', 'IDNA'],
    'illinois': ['ILUR', 'ILNA'], 'indiana': ['INUR', 'INNA'],
    'iowa': ['IAUR', 'IANA'], 'kansas': ['KSUR', 'KSNA'],
    'kentucky': ['KYUR', 'KYNA'], 'louisiana': ['LAUR', 'LANA'],
    'maine': ['MEUR', 'MENA'], 'maryland': ['MDUR', 'MDNA'],
    'massachusetts': ['MAUR', 'MANA'], 'michigan': ['MIUR', 'MINA'],
    'minnesota': ['MNUR', 'MNNA'], 'mississippi': ['MSUR', 'MSNA'],
    'missouri': ['MOUR', 'MONA'], 'montana': ['MTUR', 'MTNA'],
    'nebraska': ['NEUR', 'NENA'], 'nevada': ['NVUR', 'NVNA'],
    'new hampshire': ['NHUR', 'NHNA'], 'new jersey': ['NJUR', 'NJNA'],
    'new mexico': ['NMUR', 'NMNA'], 'new york': ['NYUR', 'NYNA'],
    'north carolina': ['NCUR', 'NCNA'], 'north dakota': ['NDUR', 'NDNA'],
    'ohio': ['OHUR', 'OHNA'], 'oklahoma': ['OKUR', 'OKNA'],
    'oregon': ['ORUR', 'ORNA'], 'pennsylvania': ['PAUR', 'PANA'],
    'rhode island': ['RIUR', 'RINA'], 'south carolina': ['SCUR', 'SCNA'],
    'south dakota': ['SDUR', 'SDNA'], 'tennessee': ['TNUR', 'TNNA'],
    'texas': ['TXUR', 'TXNA'], 'utah': ['UTUR', 'UTNA'],
    'vermont': ['VTUR', 'VTNA'], 'virginia': ['VAUR', 'VANA'],
    'washington': ['WAUR', 'WANA'], 'west virginia': ['WVUR', 'WVNA'],
    'wisconsin': ['WIUR', 'WINA'], 'wyoming': ['WYUR', 'WYNA'],
    'district of columbia': ['DCUR', 'DCNA'], 'dc': ['DCUR', 'DCNA'],
}

# Topic keyword sets → expected series families
TOPIC_KEYWORDS = {
    'employment': {'job', 'jobs', 'employment', 'labor', 'hiring',
                   'unemployment', 'payroll', 'workforce'},
    'inflation': {'inflation', 'cpi', 'prices', 'pce', 'deflation'},
    'housing': {'housing', 'home', 'mortgage', 'rent', 'rents'},
    'gdp': {'gdp', 'growth', 'output', 'economy'},
}

TOPIC_SERIES = {
    'employment': {'PAYEMS', 'UNRATE', 'JTSJOL', 'LNS12300060', 'ICSA',
                   'MANEMP', 'CIVPART', 'U6RATE'},
    'inflation': {'CPIAUCSL', 'CPILFESL', 'PCEPI', 'PCEPILFE',
                  'CUSR0000SAH1', 'CUSR0000SEHA'},
    'housing': {'CSUSHPINSA', 'HOUST', 'MORTGAGE30US', 'PERMIT',
                'EXHOSLUSM495S'},
    'gdp': {'GDPC1', 'A191RL1Q225SBEA', 'A191RO1Q156NBEA', 'INDPRO',
            'PB0000031Q225SBEA', 'GDPNOW'},
}


class QueryRouter:
    """
    Master router — unified 5-step architecture.

    Steps:
      1. Cache → 2. Exact match → 3. LLM Router → 4. Enrichment → 5. Validate

    The LLM router (step 3) is ONE Gemini call that replaces the old chain of:
    query understanding → special routes → market → comparison → deep
    understanding → RAG → fuzzy → LLM fallback.

    Fallbacks (steps 3b, 3c) only run if Gemini is down.
    """

    def __init__(self):
        # LLM router is lazily initialized after registry.load() completes.
        # This avoids a boot-order issue: the global router instance is created
        # at module import time, but registry.load() runs in FastAPI startup().
        self._llm_router: Optional[LLMRouter] = None
        self._catalog_built = False

        # Load fallback modules (only used when Gemini is down)
        self._old_llm_fallback = None
        self._load_fallback_modules()

        print("[Router] Unified V3 router created (catalog deferred)")

    def _ensure_catalog(self):
        """
        Build the plan catalog on first use (lazy init).

        Deferred because the registry JSON files are loaded in FastAPI
        startup(), which runs after module-level imports. Building the
        catalog here ensures we have all 1,355 plans, not just the
        ~97 QUERY_MAP entries available at import time.
        """
        if self._catalog_built:
            return
        plan_catalog.build(registry)
        self._llm_router = LLMRouter(plan_catalog)
        self._catalog_built = True
        print("[Router] Catalog built, LLM router initialized")

    def _load_fallback_modules(self):
        """Load modules for fallback routing when Gemini is down."""
        try:
            from ai import build_dynamic_plan, classify_query
            self._old_llm_fallback = {
                'build_dynamic_plan': build_dynamic_plan,
                'classify_query': classify_query,
            }
            print("[Router] Fallback LLM (Claude): available")
        except Exception as e:
            print(f"[Router] Fallback LLM: not available - {e}")

    def route(self, query: str) -> RoutingResult:
        """
        Route a query to appropriate data series.

        5-step unified architecture:
          1. Cache hit
          2. Exact plan match (O(1) lookup)
          3. LLM Router (single Gemini call)
             3b. Fuzzy match fallback
             3c. Old LLM fallback (Claude)
          4. Special enrichment (additive HTML boxes)
          5. Deterministic validation
        """
        # Lazy-init: build catalog on first route() call
        self._ensure_catalog()

        # =====================================================================
        # STEP 1: Cache hit
        # =====================================================================
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
                cached=True,
            )

        # =====================================================================
        # STEP 2: Exact plan match (O(1) lookup)
        # =====================================================================
        plan = registry.get_plan(query)
        if plan:
            result = self._plan_to_result(plan, 'exact')
            result = self._enrich_special(result, query)
            result = self._validate(result, query)
            self._cache_result(query, result)
            return result

        # =====================================================================
        # STEP 2b: Health check queries (curated multi-indicator sets)
        # Health checks map "how is X doing?" to the RIGHT indicators.
        # Priority over LLM router because the curated sets are more
        # reliable than LLM selection for these entity-specific queries.
        # =====================================================================
        if (special_router._health_check
                and special_router._health_check['is_query'](query)):
            hc_result = self._handle_health_check(query)
            if hc_result:
                hc_result = self._enrich_special(hc_result, query)
                hc_result = self._validate(hc_result, query)
                self._cache_result(query, hc_result)
                return hc_result

        # =====================================================================
        # STEP 3: LLM Router (single Gemini call)
        # =====================================================================
        if self._llm_router and self._llm_router.available:
            try:
                llm_result = self._llm_router.route(query)
                if llm_result:
                    result = self._resolve_llm_result(llm_result, query)
                    if result and result.series:
                        result = self._enrich_special(result, query, llm_result)
                        result = self._validate(result, query)
                        self._cache_result(query, result)
                        return result
            except Exception as e:
                print(f"[Router] LLM router error: {e}")

        # =====================================================================
        # STEP 3b: Fuzzy match fallback (Gemini missed or unavailable)
        # =====================================================================
        plan = registry.fuzzy_match(query, threshold=0.7)
        if plan:
            result = self._plan_to_result(plan, 'fuzzy_fallback')
            result = self._enrich_special(result, query)
            result = self._validate(result, query)
            self._cache_result(query, result)
            return result

        # =====================================================================
        # STEP 3c: Old LLM fallback (Claude — only when Gemini is down)
        # =====================================================================
        result = self._old_llm_route(query)
        if result and result.series:
            result = self._enrich_special(result, query)
            result = self._validate(result, query)
            self._cache_result(query, result)
            return result

        # =====================================================================
        # STEP 3d: Special routes as last-resort routing
        # When Gemini is down and all other fallbacks fail, use special routes
        # (Fed SEP, recession, health check, CAPE) for BOTH routing and enrichment.
        # This preserves backward compatibility for queries like "dot plot" that
        # special routes always handled.
        # =====================================================================
        special_result = special_router.check(query)
        if special_result and special_result.matched and special_result.series:
            result = self._special_to_routing_result(special_result)
            result = self._validate(result, query)
            self._cache_result(query, result)
            return result

        # =====================================================================
        # STEP: No match
        # =====================================================================
        return RoutingResult(
            series=[],
            route_type='none',
            explanation="No matching economic data found for this query.",
        )

    # =========================================================================
    # STEP 2b HELPER: Health check routing
    # =========================================================================

    def _handle_health_check(self, query: str) -> Optional[RoutingResult]:
        """
        Route health check queries to curated indicator sets.

        Uses the health check module's entity detection to map queries
        like "how are consumers doing?" to the right set of indicators
        (e.g., sentiment, retail sales, real income, savings rate).

        Returns None if the query is a health check but no entity matches.
        """
        if not special_router._health_check:
            return None

        entity = special_router._health_check['detect_entity'](query)
        if not entity:
            return None

        config = special_router._health_check['get_config'](entity)
        if not config:
            return None

        # HealthCheckConfig is a dataclass with primary_series, show_yoy, etc.
        series = getattr(config, 'primary_series', [])
        show_yoy = getattr(config, 'show_yoy', [False])
        # Use the first show_yoy value as the overall flag
        show_yoy_flag = show_yoy[0] if isinstance(show_yoy, list) and show_yoy else False

        return RoutingResult(
            series=series,
            show_yoy=show_yoy_flag,
            route_type='health_check',
            explanation=getattr(config, 'explanation', ''),
        )

    # =========================================================================
    # STEP 3 HELPERS: LLM result → RoutingResult
    # =========================================================================

    def _resolve_llm_result(self, llm_result: Dict, query: str) -> Optional[RoutingResult]:
        """
        Convert the LLM router's JSON response into a RoutingResult.

        The LLM returns either a plan_key (which we resolve via registry)
        or custom_series (FRED IDs for novel queries).
        """
        plan_key = llm_result.get('plan_key')
        secondary_key = llm_result.get('secondary_plan_key')
        custom_series = llm_result.get('custom_series')
        is_comparison = llm_result.get('is_comparison', False)

        # Case 1: LLM picked a plan key
        if plan_key:
            plan = registry.get_plan(plan_key)
            if plan:
                result = self._plan_to_result(plan, 'llm_v3')

                # If comparison, merge secondary plan's series
                if is_comparison and secondary_key:
                    secondary_plan = registry.get_plan(secondary_key)
                    if secondary_plan:
                        extra_series = secondary_plan.get('series', [])
                        # Add any series not already in the result
                        for s in extra_series:
                            if s not in result.series:
                                result.series.append(s)
                        result.is_comparison = True

                # Override show_yoy if LLM explicitly set it
                if llm_result.get('show_yoy'):
                    result.show_yoy = True

                result.is_comparison = is_comparison or result.is_comparison
                return result
            else:
                # Plan key didn't resolve — log and try fuzzy
                print(f"[Router] LLM picked plan_key '{plan_key}' but it's not in registry")
                # Try fuzzy match on the plan key itself
                plan = registry.fuzzy_match(plan_key, threshold=0.6)
                if plan:
                    result = self._plan_to_result(plan, 'llm_v3_fuzzy')
                    result.is_comparison = is_comparison
                    return result

        # Case 2: LLM returned custom series
        if custom_series and isinstance(custom_series, list) and len(custom_series) > 0:
            return RoutingResult(
                series=custom_series,
                show_yoy=llm_result.get('show_yoy', False),
                is_comparison=is_comparison,
                route_type='llm_v3_custom',
                explanation=llm_result.get('explanation', ''),
            )

        return None

    # =========================================================================
    # STEP 4: Special Enrichment (additive, not exclusive)
    # =========================================================================

    def _enrich_special(self, result: RoutingResult, query: str,
                        llm_flags: Optional[Dict] = None) -> RoutingResult:
        """
        Add Fed SEP / recession / CAPE HTML boxes WITHOUT replacing series.

        This is the key architectural change: special routes used to
        REPLACE the routing result entirely. Now they ADD HTML boxes
        on top of whatever series the LLM selected.

        Args:
            result: The existing RoutingResult with correct series.
            query: The user's query string.
            llm_flags: Optional flags from the LLM router (needs_fed_sep, etc.)
        """
        flags = {}
        if llm_flags:
            flags = {
                'needs_fed_sep': llm_flags.get('needs_fed_sep', False),
                'needs_recession_scorecard': llm_flags.get('needs_recession_scorecard', False),
                'needs_cape': llm_flags.get('needs_cape', False),
            }

        enrichment = special_router.get_enrichment(query, flags)

        if enrichment.get('fed_guidance'):
            result.fed_guidance = enrichment['fed_guidance']
        if enrichment.get('fed_sep_html'):
            result.fed_sep_html = enrichment['fed_sep_html']
        if enrichment.get('recession_html'):
            result.recession_html = enrichment['recession_html']
        if enrichment.get('cape_html'):
            result.cape_html = enrichment['cape_html']

        return result

    # =========================================================================
    # STEP 5: Deterministic Validation (no LLM needed)
    # =========================================================================

    def _validate(self, result: RoutingResult, query: str) -> RoutingResult:
        """
        Check that series match query intent. Override if clearly wrong.

        Uses keyword matching only — no LLM call. Catches:
        1. Demographic mismatch: query about "Black workers" but series are generic UNRATE
        2. Sector mismatch: query about "restaurants" but series are generic PAYEMS
        3. Topic mismatch: query about "jobs" but series are rent/housing (logged only)

        Does NOT override when:
        - Exact plan match with specific series (already curated)
        - Series already contain the expected demographic/sector data
        """
        if not result.series:
            return result

        q = query.lower()
        series_set = set(result.series)

        # Skip validation for exact matches that already have specific series
        if result.route_type == 'exact':
            has_specific = bool(series_set - GENERIC_NATIONAL)
            if has_specific:
                return result

        # -----------------------------------------------------------------
        # 1. Demographic check
        # -----------------------------------------------------------------
        for demo_keyword, expected_series in DEMOGRAPHIC_OVERRIDES.items():
            # Use word boundary check to avoid false positives
            # (e.g., "blackout" should not trigger "black")
            if re.search(rf'\b{re.escape(demo_keyword)}\b', q):
                # Query mentions this demographic — do we have the right series?
                has_demo_series = any(s in series_set for s in expected_series)
                if not has_demo_series:
                    print(f"[Validate] Demographic override: '{demo_keyword}' → {expected_series[:3]}")
                    return RoutingResult(
                        series=expected_series,
                        route_type=f'{result.route_type}_validated',
                        combine_chart=True,
                        explanation=f'{demo_keyword.title()} labor market data.',
                        # Preserve enrichment
                        fed_guidance=result.fed_guidance,
                        fed_sep_html=result.fed_sep_html,
                        recession_html=result.recession_html,
                        cape_html=result.cape_html,
                        polymarket_html=result.polymarket_html,
                        temporal_context=result.temporal_context,
                    )

        # -----------------------------------------------------------------
        # 2. Sector check
        # -----------------------------------------------------------------
        for sector_keyword, expected_series in SECTOR_OVERRIDES.items():
            if sector_keyword in q:
                has_sector_series = any(s in series_set for s in expected_series)
                if not has_sector_series and series_set.issubset(GENERIC_NATIONAL):
                    print(f"[Validate] Sector override: '{sector_keyword}' → {expected_series}")
                    return RoutingResult(
                        series=expected_series,
                        route_type=f'{result.route_type}_validated',
                        explanation=f'{sector_keyword.title()} sector data.',
                        fed_guidance=result.fed_guidance,
                        fed_sep_html=result.fed_sep_html,
                        recession_html=result.recession_html,
                        cape_html=result.cape_html,
                        polymarket_html=result.polymarket_html,
                        temporal_context=result.temporal_context,
                    )

        # -----------------------------------------------------------------
        # 3. State check — query about a specific US state but got national data
        # -----------------------------------------------------------------
        for state_keyword, expected_series in STATE_OVERRIDES.items():
            if state_keyword in q:
                # Check that we have state-specific series, not just generic national
                has_state_series = any(s in series_set for s in expected_series)
                if not has_state_series and series_set.issubset(GENERIC_NATIONAL):
                    # Add national comparison series alongside state data
                    state_with_national = expected_series + ['UNRATE', 'PAYEMS']
                    print(f"[Validate] State override: '{state_keyword}' → {expected_series}")
                    return RoutingResult(
                        series=state_with_national,
                        route_type=f'{result.route_type}_validated',
                        explanation=f'{state_keyword.title()} economic data vs national benchmarks.',
                        fed_guidance=result.fed_guidance,
                        fed_sep_html=result.fed_sep_html,
                        recession_html=result.recession_html,
                        cape_html=result.cape_html,
                        polymarket_html=result.polymarket_html,
                        temporal_context=result.temporal_context,
                    )

        # -----------------------------------------------------------------
        # 4. Topic mismatch check (log only — not aggressive enough to override)
        # -----------------------------------------------------------------
        query_topic = None
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in q for kw in keywords):
                query_topic = topic
                break

        if query_topic:
            expected = TOPIC_SERIES.get(query_topic, set())
            if expected and not any(s in expected for s in result.series):
                print(f"[Validate] Topic mismatch (logged): query={query_topic}, "
                      f"series={result.series[:3]}")

        return result

    # =========================================================================
    # HELPERS
    # =========================================================================

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
            route_type=route_type,
        )

    def _old_llm_route(self, query: str) -> Optional[RoutingResult]:
        """
        Old LLM routing fallback (Claude).

        Only used when Gemini LLM router is unavailable.
        """
        if not self._old_llm_fallback:
            return None

        try:
            # Try dynamic plan building with Claude
            from registry import registry as reg
            catalog = self._get_series_catalog()
            plan = self._old_llm_fallback['build_dynamic_plan'](query, catalog)
            if plan and plan.get('series'):
                return RoutingResult(
                    series=plan['series'],
                    show_yoy=plan.get('show_yoy', False),
                    explanation=plan.get('explanation', ''),
                    route_type='fallback_dynamic',
                )
        except Exception as e:
            print(f"[Router] Dynamic plan fallback error: {e}")

        try:
            # Try classify_query fallback
            classification = self._old_llm_fallback['classify_query'](
                query, registry.all_plan_keys()
            )
            if classification and classification.get('topic'):
                plan = registry.get_plan(classification['topic'])
                if plan:
                    result = self._plan_to_result(plan, 'fallback_classify')
                    if classification.get('show_yoy') is not None:
                        result.show_yoy = classification['show_yoy']
                    return result
        except Exception as e:
            print(f"[Router] classify_query fallback error: {e}")

        return None

    def _get_series_catalog(self) -> List[Dict]:
        """Get catalog of all available series for dynamic routing."""
        catalog = []
        for sid, info in registry._series.items():
            catalog.append({
                'id': sid,
                'name': info.name,
                'description': info.short_description or (info.bullets[0] if info.bullets else ''),
            })

        # Add common FRED series not in registry
        common_series = [
            {'id': 'CUSR0000SEHA', 'name': 'CPI: Rent of Primary Residence', 'description': 'Rent inflation'},
            {'id': 'CUSR0000SAF1', 'name': 'CPI: Food', 'description': 'Food price inflation'},
            {'id': 'CUSR0000SETB01', 'name': 'CPI: Gasoline', 'description': 'Gas price changes'},
            {'id': 'JTSJOL', 'name': 'Job Openings', 'description': 'Unfilled job positions (JOLTS)'},
            {'id': 'JTSQUR', 'name': 'Quits Rate', 'description': 'Workers voluntarily leaving jobs'},
            {'id': 'DGORDER', 'name': 'Durable Goods Orders', 'description': 'Long-lasting manufactured goods orders'},
            {'id': 'INDPRO', 'name': 'Industrial Production', 'description': 'Factory output'},
            {'id': 'PERMIT', 'name': 'Building Permits', 'description': 'Future construction activity'},
            {'id': 'VIXCLS', 'name': 'VIX Volatility Index', 'description': 'Stock market fear gauge'},
            {'id': 'T10YIE', 'name': '10-Year Breakeven Inflation', 'description': 'Market inflation expectations'},
        ]
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
