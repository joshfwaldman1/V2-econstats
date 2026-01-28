"""
LLM Router - Single Gemini call for query understanding + plan selection.

Replaces the old 12-step cascade (understanding → special → market →
comparison → deep understanding → RAG → fuzzy → LLM fallback) with
ONE Gemini 2.0 Flash call that both understands the query and picks
the best pre-built plan from the catalog.

Architecture:
  1. Build a prompt with the compact plan catalog (~3,500 tokens)
  2. Send query + catalog to Gemini 2.0 Flash
  3. Get back: plan_key, custom_series, show_yoy, special flags
  4. Resolve plan_key to a full RoutingResult

Falls back gracefully: if Gemini is down, returns None and the
router uses fuzzy match + old Claude fallback.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from urllib.request import urlopen, Request

from .plan_catalog import PlanCatalog

# API Key - check both GEMINI_API_KEY and GOOGLE_API_KEY
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

# Cache for LLM routing results (avoid repeated calls for the same query)
_routing_cache: Dict[str, tuple] = {}
_routing_cache_ttl = timedelta(hours=1)


# =============================================================================
# ROUTING PROMPT
# =============================================================================

ROUTING_PROMPT = """You are the query router for an economics data dashboard. Given a user query, select the best pre-built data plan from the catalog below.

USER QUERY: "{query}"

## PLAN CATALOG
{catalog}

## INSTRUCTIONS

1. Pick the PLAN KEY that best answers the user's question.
   - Plan keys are the exact strings listed in the catalog (e.g., "job market", "inflation", "black unemployment").
   - Match semantics, not just keywords. "How are jobs doing?" → "job market". "What's happening with prices?" → "inflation".
   - For state queries, construct the key as "{{state name}} {{topic}}" (e.g., "california economy", "texas unemployment").

2. For COMPARISON queries ("vs", "compared to", "relative to"):
   - Look for a comparison plan first (e.g., "us vs eurozone", "cpi vs pce").
   - If no comparison plan exists, return two plan keys in "secondary_plan_key".

3. If NO plan matches, set plan_key to null and return 1-4 FRED series IDs in custom_series.
   Common FRED series: UNRATE, PAYEMS, CPIAUCSL, CPILFESL, FEDFUNDS, DGS10, GDPC1, HOUST, MORTGAGE30US, SP500, ICSA, JTSJOL, T10Y2Y, SAHMREALTIME, PCEPILFE

4. Set special flags when applicable:
   - needs_fed_sep: query asks about Fed projections, dot plot, rate path, FOMC
   - needs_recession_scorecard: query asks about recession risk/probability/indicators
   - needs_cape: query asks about market valuation, P/E ratio, bubble, overvalued
   - is_market_query: query asks about stock market, commodities, gold, VIX

5. show_yoy: Set true only for index series (CPI, PCE, home prices) that need year-over-year transformation. Most plans already have the correct show_yoy setting; only override when the user explicitly asks for "year over year" or "percent change".

## RESPONSE FORMAT (JSON only, no markdown fences)

{{
  "plan_key": "the best matching plan key" or null,
  "secondary_plan_key": null or "second plan key for comparisons",
  "custom_series": null or ["SERIES1", "SERIES2"],
  "show_yoy": false,
  "is_comparison": false,
  "needs_fed_sep": false,
  "needs_recession_scorecard": false,
  "needs_cape": false,
  "is_market_query": false,
  "explanation": "one sentence why this plan matches"
}}"""


class LLMRouter:
    """
    Single-call LLM router using Gemini 2.0 Flash.

    Merges query understanding + plan selection into one fast call.
    """

    def __init__(self, catalog: PlanCatalog):
        self.catalog = catalog
        self._available = bool(GEMINI_API_KEY)
        if self._available:
            print("[LLMRouter] Initialized with Gemini 2.0 Flash")
        else:
            print("[LLMRouter] No API key — LLM routing disabled")

    @property
    def available(self) -> bool:
        """Whether the LLM router has an API key and can be used."""
        return self._available

    def route(self, query: str) -> Optional[Dict]:
        """
        Route a query using a single Gemini call.

        Args:
            query: The user's query string.

        Returns:
            Dict with routing info (plan_key, custom_series, flags) or None on failure.
            Keys:
              - plan_key: str or None
              - secondary_plan_key: str or None
              - custom_series: list or None
              - show_yoy: bool
              - is_comparison: bool
              - needs_fed_sep: bool
              - needs_recession_scorecard: bool
              - needs_cape: bool
              - is_market_query: bool
              - explanation: str
        """
        if not self._available:
            return None

        # Check routing cache
        cache_key = self._cache_key(query)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Build prompt
        prompt = ROUTING_PROMPT.format(
            query=query,
            catalog=self.catalog.catalog_text
        )

        # Call Gemini
        result = self._call_gemini(prompt)
        if result is None:
            return None

        # Parse the response
        parsed = self._parse_response(result)
        if parsed is None:
            return None

        # Cache and return
        self._set_cache(cache_key, parsed)
        return parsed

    def _call_gemini(self, prompt: str, retries: int = 2) -> Optional[str]:
        """
        Call Gemini 2.0 Flash and return the raw text response.

        Uses low temperature (0.1) for consistent routing decisions.
        """
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
        )

        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature': 0.1,  # Very low for deterministic routing
                'maxOutputTokens': 400,
            },
        }
        headers = {'Content-Type': 'application/json'}

        for attempt in range(retries):
            try:
                req = Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers=headers,
                    method='POST',
                )
                with urlopen(req, timeout=15) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    return text
            except Exception as e:
                if attempt == retries - 1:
                    print(f"[LLMRouter] Gemini error after {retries} attempts: {e}")
                    return None
        return None

    def _parse_response(self, text: str) -> Optional[Dict]:
        """
        Parse the JSON response from Gemini.

        Handles both raw JSON and markdown-fenced JSON.
        """
        # Try direct JSON parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]

        try:
            parsed = json.loads(text.strip())
            return parsed
        except json.JSONDecodeError:
            print(f"[LLMRouter] Failed to parse response: {text[:200]}")
            return None

    # =========================================================================
    # CACHE
    # =========================================================================

    def _cache_key(self, query: str) -> str:
        """Generate a cache key for the query."""
        return query.lower().strip().rstrip('?').strip()

    def _get_cached(self, cache_key: str) -> Optional[Dict]:
        """Get cached routing result if still valid."""
        if cache_key in _routing_cache:
            result, timestamp = _routing_cache[cache_key]
            if datetime.now() - timestamp < _routing_cache_ttl:
                return result
            else:
                del _routing_cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, result: Dict) -> None:
        """Cache a routing result."""
        _routing_cache[cache_key] = (result, datetime.now())
        # Limit cache size
        if len(_routing_cache) > 300:
            oldest_keys = sorted(
                _routing_cache.keys(),
                key=lambda k: _routing_cache[k][1]
            )[:75]
            for k in oldest_keys:
                del _routing_cache[k]
