"""
Query Understanding Module - "Thinking First" Layer for EconStats.

This module implements a deep query understanding step that runs BEFORE any routing
or plan matching. The goal is to truly understand what the user is asking before
deciding how to answer it.

Architecture:
1. Raw query comes in
2. Gemini deeply analyzes the query intent, entities, and requirements
3. Returns a structured understanding that guides all downstream routing

This prevents issues like:
- Matching "Black workers" to women's employment data
- Showing irrelevant data for specific questions
- Missing the true intent behind complex queries
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from urllib.request import urlopen, Request

# API Key - check both GEMINI_API_KEY and GOOGLE_API_KEY for compatibility
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

# Cache for query understanding results (1-hour TTL)
# This avoids repeated expensive Gemini calls for similar queries
_understanding_cache: dict = {}
_understanding_cache_ttl = timedelta(hours=1)

# =============================================================================
# QUERY UNDERSTANDING PROMPT
# The "thinking first" prompt that deeply analyzes user intent
# =============================================================================

UNDERSTANDING_PROMPT = """You are an expert economist and data analyst. Your job is to DEEPLY UNDERSTAND what the user is really asking before we fetch any data.

USER QUERY: "{query}"

## YOUR TASK: Analyze the query and return a structured understanding.

Think step by step:
1. What is the user REALLY asking? (Not just the literal words)
2. What ENTITIES are mentioned? (regions, demographics, sectors, time periods)
3. What TYPE of query is this? (factual, analytical, comparison, forecast)
4. What DATA SOURCES would best answer this? (FRED, Zillow, EIA, international data)
5. What are potential PITFALLS? (wrong data, misleading comparisons, etc.)

## ENTITY EXTRACTION

Extract ALL relevant entities:

**Demographics** (be VERY specific - these must match exactly):
- race: "black", "african american", "hispanic", "latino", "asian", "white"
- gender: "women", "men", "female", "male"
- age: "youth", "teen", "young", "older", "elderly", "prime age"
- other: "veteran", "immigrant", "foreign-born", "native-born", "disabled"

**Regions** (for routing to correct data source):
- US regions: specific states, "national", "american"
- International: "eurozone", "europe", "uk", "china", "japan", "germany", etc.

**Sectors/Industries**:
- "manufacturing", "construction", "retail", "restaurants", "tech", "healthcare", etc.

**Time references**:
- Specific: "2023", "last year", "Q3 2024"
- Relative: "recent", "currently", "trend"
- Periods: "pre-covid", "during covid", "post-pandemic", "great recession"

## QUERY TYPE CLASSIFICATION

Determine the query type:

1. **FACTUAL** - Asking for a specific number/rate
   - "What is the unemployment rate?"
   - "What's the Fed funds rate?"

2. **ANALYTICAL** - Asking for insight/interpretation
   - "How is the job market doing?"
   - "Is inflation coming down?"

3. **COMPARISON** - Asking to compare entities
   - "US vs Eurozone GDP"
   - "How does Black unemployment compare to overall?"

4. **FORECAST** - Asking about the future
   - "Will the Fed cut rates?"
   - "Is a recession coming?"

5. **CAUSAL** - Asking why something happened
   - "Why did inflation spike in 2022?"
   - "What caused the housing crash?"

## DATA SOURCE ROUTING

Based on the query, which sources should we use?

- **FRED** (default): US economic data
- **DBNOMICS** (international): Eurozone, UK, Japan, China, etc.
- **ZILLOW** (housing): Actual market rents, home values
- **EIA** (energy): Oil, gas, electricity prices
- **ALPHAVANTAGE** (markets): Stock indices, forex, daily data
- **POLYMARKET** (forecasts): Prediction markets for forward-looking
- **FED_SEP** (Fed): FOMC projections, dot plot

## RESPONSE FORMAT

Return JSON:
```json
{{
    "intent": {{
        "core_question": "What is the user fundamentally asking?",
        "query_type": "factual|analytical|comparison|forecast|causal",
        "complexity": "simple|moderate|complex",
        "requires_interpretation": true/false
    }},
    "entities": {{
        "demographics": ["black", "women", etc.] or [],
        "regions": ["us", "eurozone", etc.] or [],
        "sectors": ["restaurants", "manufacturing", etc.] or [],
        "time_period": {{
            "type": "specific|relative|period|none",
            "value": "2023" or "recent" or "pre-covid" or null
        }}
    }},
    "routing": {{
        "primary_source": "fred|dbnomics|zillow|eia|alphavantage",
        "secondary_sources": ["polymarket", "fed_sep"],
        "is_comparison": true/false,
        "is_international": true/false,
        "is_demographic_specific": true/false,
        "is_sector_specific": true/false
    }},
    "data_requirements": {{
        "indicators_needed": ["unemployment rate", "job growth", etc.],
        "must_be_group_specific": true/false,
        "notes": "Any special requirements or warnings"
    }},
    "pitfalls": [
        "Don't use overall unemployment for demographic queries",
        "Compare YoY to YoY, not YoY to QoQ"
    ]
}}
```

## EXAMPLES

Query: "How are Black workers doing?"
```json
{{
    "intent": {{
        "core_question": "Economic status of Black workers in the labor market",
        "query_type": "analytical",
        "complexity": "moderate",
        "requires_interpretation": true
    }},
    "entities": {{
        "demographics": ["black"],
        "regions": ["us"],
        "sectors": [],
        "time_period": {{"type": "relative", "value": "recent"}}
    }},
    "routing": {{
        "primary_source": "fred",
        "secondary_sources": [],
        "is_comparison": false,
        "is_international": false,
        "is_demographic_specific": true,
        "is_sector_specific": false
    }},
    "data_requirements": {{
        "indicators_needed": ["Black unemployment rate", "Black employment rate", "Black labor force participation"],
        "must_be_group_specific": true,
        "notes": "MUST use Black-specific series only - never use overall UNRATE or women's data"
    }},
    "pitfalls": [
        "Do NOT use overall unemployment rate (UNRATE)",
        "Do NOT use women's employment data",
        "Use LNS14000006 for Black unemployment, not LNS14000002 (women)"
    ]
}}
```

Query: "US vs Eurozone GDP growth"
```json
{{
    "intent": {{
        "core_question": "Compare economic growth rates between US and Eurozone",
        "query_type": "comparison",
        "complexity": "moderate",
        "requires_interpretation": true
    }},
    "entities": {{
        "demographics": [],
        "regions": ["us", "eurozone"],
        "sectors": [],
        "time_period": {{"type": "relative", "value": "recent"}}
    }},
    "routing": {{
        "primary_source": "fred",
        "secondary_sources": ["dbnomics"],
        "is_comparison": true,
        "is_international": true,
        "is_demographic_specific": false,
        "is_sector_specific": false
    }},
    "data_requirements": {{
        "indicators_needed": ["US real GDP growth YoY", "Eurozone real GDP growth YoY"],
        "must_be_group_specific": false,
        "notes": "MUST compare same measure type - both YoY real growth, not QoQ vs YoY"
    }},
    "pitfalls": [
        "Compare YoY to YoY, not YoY to QoQ",
        "Use real (inflation-adjusted) for both, not nominal vs real",
        "Eurozone data is from DBnomics, not FRED"
    ]
}}
```

Be thorough. This understanding drives all downstream decisions.
"""


def _get_understanding_cache_key(query: str) -> str:
    """Generate cache key for query understanding."""
    # Normalize query for better cache hits
    normalized = query.lower().strip().rstrip('?').strip()
    return f"understanding:{normalized}"


def _get_cached_understanding(cache_key: str) -> Optional[Dict]:
    """Get cached understanding result if still valid."""
    if cache_key in _understanding_cache:
        result, timestamp = _understanding_cache[cache_key]
        if datetime.now() - timestamp < _understanding_cache_ttl:
            return result
        else:
            del _understanding_cache[cache_key]
    return None


def _set_understanding_cache(cache_key: str, result: Dict) -> None:
    """Cache an understanding result."""
    _understanding_cache[cache_key] = (result, datetime.now())
    # Limit cache size to prevent unbounded growth
    if len(_understanding_cache) > 200:
        # Remove oldest 50 entries
        oldest_keys = sorted(
            _understanding_cache.keys(),
            key=lambda k: _understanding_cache[k][1]
        )[:50]
        for k in oldest_keys:
            del _understanding_cache[k]


def understand_query(query: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Deeply understand a query before any routing or data fetching.

    OPTIMIZED: Results are cached for 1 hour to avoid repeated Gemini calls.
    Cache hit rate expected: 50-70% in typical sessions.

    This is the "thinking first" step that should run before:
    - Checking pre-computed plans
    - Running economist reasoning
    - Routing to data sources

    Args:
        query: The user's raw query string
        verbose: Whether to print debug output

    Returns:
        A structured understanding dict with:
        - intent: What the user is really asking
        - entities: Demographics, regions, sectors, time periods mentioned
        - routing: What data sources and paths to use
        - data_requirements: What indicators are needed
        - pitfalls: Potential issues to avoid
    """
    # Check cache first (saves 5-8s per cache hit)
    cache_key = _get_understanding_cache_key(query)
    cached_result = _get_cached_understanding(cache_key)
    if cached_result:
        if verbose:
            print(f"  [QueryUnderstanding] Cache hit for: {query}")
        return cached_result

    if verbose:
        print(f"  [QueryUnderstanding] Analyzing: {query}")

    # Call Gemini for deep understanding
    result = _call_gemini_understanding(query)

    if not result:
        # Fallback to rule-based understanding
        if verbose:
            print(f"  [QueryUnderstanding] Gemini failed, using rule-based fallback")
        # IMPORTANT: Still validate the rule-based result to add secondary sources
        result = _rule_based_understanding(query)
        result = _validate_understanding(result, query)
        # Cache the fallback result too
        _set_understanding_cache(cache_key, result)
        return result

    # Validate and enrich the result
    result = _validate_understanding(result, query)

    if verbose:
        print(f"  [QueryUnderstanding] Intent: {result.get('intent', {}).get('core_question', 'Unknown')}")
        print(f"  [QueryUnderstanding] Type: {result.get('intent', {}).get('query_type', 'Unknown')}")
        print(f"  [QueryUnderstanding] Primary source: {result.get('routing', {}).get('primary_source', 'fred')}")
        if result.get('entities', {}).get('demographics'):
            print(f"  [QueryUnderstanding] Demographics: {result['entities']['demographics']}")

    # Cache the result before returning
    _set_understanding_cache(cache_key, result)
    return result


def _call_gemini_understanding(query: str, retries: int = 2) -> Optional[Dict]:
    """
    Call Gemini to deeply understand the query.

    Uses Gemini 2.0 Flash for speed while maintaining quality.
    """
    if not GEMINI_API_KEY:
        return None

    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'

    prompt = UNDERSTANDING_PROMPT.format(query=query)

    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.2,  # Low temperature for consistent analysis
            'maxOutputTokens': 1200
        }
    }
    headers = {'Content-Type': 'application/json'}

    for attempt in range(retries):
        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=20) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result['candidates'][0]['content']['parts'][0]['text']
                return _extract_json(content)
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [QueryUnderstanding] Gemini ERROR: {e}")
                return None
    return None


def _extract_json(text: str) -> Optional[Dict]:
    """Extract JSON from Gemini response."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0]
    elif '```' in text:
        text = text.split('```')[1].split('```')[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _validate_understanding(understanding: Dict, query: str) -> Dict:
    """
    Validate and enrich the understanding result.

    Ensures required fields exist and applies additional rules.
    """
    # Ensure required structure
    if 'intent' not in understanding:
        understanding['intent'] = {
            'core_question': query,
            'query_type': 'analytical',
            'complexity': 'moderate',
            'requires_interpretation': True
        }

    if 'entities' not in understanding:
        understanding['entities'] = {
            'demographics': [],
            'regions': [],
            'sectors': [],
            'time_period': {'type': 'none', 'value': None}
        }

    if 'routing' not in understanding:
        understanding['routing'] = {
            'primary_source': 'fred',
            'secondary_sources': [],
            'is_comparison': False,
            'is_international': False,
            'is_demographic_specific': False,
            'is_sector_specific': False
        }

    if 'data_requirements' not in understanding:
        understanding['data_requirements'] = {
            'indicators_needed': [],
            'must_be_group_specific': False,
            'notes': ''
        }

    if 'pitfalls' not in understanding:
        understanding['pitfalls'] = []

    # Apply additional validation rules
    query_lower = query.lower()

    # If demographics are mentioned, enforce demographic-specific requirement
    demographics = understanding['entities'].get('demographics', [])
    if demographics:
        understanding['routing']['is_demographic_specific'] = True
        understanding['data_requirements']['must_be_group_specific'] = True

        # Add pitfall warnings based on demographics
        if 'black' in demographics or 'african american' in demographics:
            if "Do NOT use women's employment data" not in understanding['pitfalls']:
                understanding['pitfalls'].append("Do NOT use women's employment data for Black workers query")
        if 'women' in demographics or 'female' in demographics:
            if "Do NOT use Black/Hispanic employment data" not in understanding['pitfalls']:
                understanding['pitfalls'].append("Do NOT use Black/Hispanic employment data for women's query")

    # Check for comparison keywords
    comparison_keywords = ['vs', 'versus', 'compared to', 'compare', 'relative to']
    if any(kw in query_lower for kw in comparison_keywords):
        understanding['routing']['is_comparison'] = True
        understanding['intent']['query_type'] = 'comparison'

    # Check for international regions
    intl_regions = ['eurozone', 'europe', 'uk', 'china', 'japan', 'germany', 'canada', 'mexico', 'india', 'brazil']
    if any(region in query_lower for region in intl_regions):
        understanding['routing']['is_international'] = True
        if 'dbnomics' not in understanding['routing'].get('secondary_sources', []):
            understanding['routing']['secondary_sources'] = understanding['routing'].get('secondary_sources', []) + ['dbnomics']

    # Check for housing/rent queries -> Zillow might be better
    housing_keywords = ['rent', 'market rent', 'actual rent', 'zillow', 'home value', 'home price']
    if any(kw in query_lower for kw in housing_keywords):
        if 'zillow' not in understanding['routing'].get('secondary_sources', []):
            understanding['routing']['secondary_sources'] = understanding['routing'].get('secondary_sources', []) + ['zillow']

    # Check for forecast queries -> Polymarket/Fed SEP might help
    forecast_keywords = ['will', 'going to', 'predict', 'forecast', 'future', 'expect', 'coming']
    if any(kw in query_lower for kw in forecast_keywords):
        understanding['intent']['query_type'] = 'forecast'
        if 'polymarket' not in understanding['routing'].get('secondary_sources', []):
            understanding['routing']['secondary_sources'] = understanding['routing'].get('secondary_sources', []) + ['polymarket']

    # Check for Fed-related queries
    fed_keywords = ['fed', 'fomc', 'dot plot', 'rate path', 'powell', 'federal reserve']
    if any(kw in query_lower for kw in fed_keywords):
        if 'fed_sep' not in understanding['routing'].get('secondary_sources', []):
            understanding['routing']['secondary_sources'] = understanding['routing'].get('secondary_sources', []) + ['fed_sep']

    return understanding


def _rule_based_understanding(query: str) -> Dict:
    """
    Fallback rule-based understanding when Gemini is unavailable.

    Uses pattern matching to extract basic understanding.
    """
    query_lower = query.lower()

    # Initialize result structure
    result = {
        'intent': {
            'core_question': query,
            'query_type': 'analytical',
            'complexity': 'moderate',
            'requires_interpretation': True
        },
        'entities': {
            'demographics': [],
            'regions': ['us'],
            'sectors': [],
            'time_period': {'type': 'relative', 'value': 'recent'}
        },
        'routing': {
            'primary_source': 'fred',
            'secondary_sources': [],
            'is_comparison': False,
            'is_international': False,
            'is_demographic_specific': False,
            'is_sector_specific': False
        },
        'data_requirements': {
            'indicators_needed': [],
            'must_be_group_specific': False,
            'notes': 'Rule-based fallback - may be less accurate'
        },
        'pitfalls': []
    }

    # Detect demographics - use word boundaries to avoid false matches
    # e.g., "men" should not match "unemployment"
    import re
    demographic_patterns = {
        'black': [r'\bblack\b', r'\bafrican american\b', r'\bafrican-american\b'],
        'hispanic': [r'\bhispanic\b', r'\blatino\b', r'\blatina\b'],
        'asian': [r'\basian\b', r'\basian american\b'],
        'white': [r'\bwhite\b', r'\bcaucasian\b'],
        'women': [r'\bwomen\b', r'\bfemale\b', r'\bwoman\b'],
        'men': [r'\bmen\b', r'\bmale\b', r'\bman\b'],
        'youth': [r'\byouth\b', r'\byoung workers\b', r'\bteen\b', r'\bteenage\b'],
        'veteran': [r'\bveteran\b'],
        'immigrant': [r'\bimmigrant\b', r'\bforeign-born\b', r'\bforeign born\b']
    }

    for demo_key, patterns in demographic_patterns.items():
        if any(re.search(p, query_lower) for p in patterns):
            result['entities']['demographics'].append(demo_key)
            result['routing']['is_demographic_specific'] = True
            result['data_requirements']['must_be_group_specific'] = True

    # Detect regions
    intl_regions = {
        'eurozone': ['eurozone', 'euro zone', 'euro area', 'europe'],
        'uk': ['uk', 'britain', 'united kingdom', 'england'],
        'china': ['china', 'chinese'],
        'japan': ['japan', 'japanese'],
        'germany': ['germany', 'german']
    }

    for region, patterns in intl_regions.items():
        if any(p in query_lower for p in patterns):
            result['entities']['regions'].append(region)
            result['routing']['is_international'] = True
            result['routing']['secondary_sources'].append('dbnomics')

    # Detect sectors - expanded to cover more industry/company queries
    sector_patterns = {
        'manufacturing': ['manufacturing', 'factory', 'factories', 'industrial'],
        'construction': ['construction', 'building', 'homebuilders'],
        'restaurants': ['restaurant', 'food service', 'dining'],
        'retail': ['retail', 'store', 'shops', 'retail stocks', 'consumer retail'],
        'tech': ['tech', 'technology', 'software', 'semiconductor', 'tech companies', 'tech sector'],
        'healthcare': ['healthcare', 'health care', 'medical', 'hospital', 'pharma', 'biotech'],
        'energy': ['oil companies', 'energy companies', 'energy sector', 'oil stocks', 'energy stocks'],
        'financials': ['banks', 'banking', 'financial sector', 'regional banks', 'financial stocks'],
        'industrials': ['industrial companies', 'industrial sector', 'aerospace', 'defense'],
        'utilities': ['utilities', 'utility companies', 'electric utilities'],
        'materials': ['materials', 'mining', 'chemicals', 'metals'],
        'communications': ['telecom', 'communications', 'media companies'],
        'consumer_discretionary': ['consumer discretionary', 'consumer stocks', 'luxury'],
        'consumer_staples': ['consumer staples', 'grocery', 'household products'],
        'real_estate': ['real estate', 'reits', 'property', 'commercial real estate'],
    }

    for sector, patterns in sector_patterns.items():
        if any(p in query_lower for p in patterns):
            result['entities']['sectors'].append(sector)
            result['routing']['is_sector_specific'] = True

    # Detect energy queries -> add EIA (keeps FRED as primary for broader context)
    # Queries like "oil prices and inflation" get BOTH EIA oil data + FRED CPI
    energy_keywords = [
        'oil', 'crude', 'petroleum', 'gasoline', 'gas prices', 'diesel',
        'natural gas', 'henry hub', 'wti', 'brent', 'energy prices',
        'fuel', 'electricity', 'power prices', 'oil inventory', 'oil stocks',
        'crude stocks', 'oil production'
    ]
    if any(kw in query_lower for kw in energy_keywords):
        # Add EIA as secondary - FRED stays primary for related economic context
        if 'eia' not in result['routing']['secondary_sources']:
            result['routing']['secondary_sources'].append('eia')

    # Detect stock market queries -> add Alpha Vantage (keeps FRED for context)
    # Queries like "stock market and unemployment" get BOTH sources
    market_keywords = [
        'stock market', 'stocks', 's&p', 's&p 500', 'sp500', 'nasdaq',
        'dow jones', 'dow', 'djia', 'russell', 'small cap', 'spy', 'qqq',
        'vix', 'volatility index', 'stock index', 'equity market', 'equities',
        # Magnificent 7 / Big Tech
        'mag7', 'mag 7', 'magnificent 7', 'magnificent seven', 'big tech',
        'faang', 'tech stocks', 'tech giants', 'megacap', 'mega cap',
        'apple stock', 'microsoft stock', 'google stock', 'nvidia stock',
        'tesla stock', 'amazon stock', 'meta stock',
        # Bubble/valuation questions (market-related)
        'bubble', 'overvalued', 'valuation', 'valuations', 'p/e', 'pe ratio',
        'market correction', 'crash', 'rally', 'bull market', 'bear market',
        'ai bubble', 'tech bubble', 'dot-com', 'dotcom',
    ]
    if any(kw in query_lower for kw in market_keywords):
        # Add Alpha Vantage as secondary - FRED has SP500, DJIA too
        if 'alphavantage' not in result['routing']['secondary_sources']:
            result['routing']['secondary_sources'].append('alphavantage')
        # Mark as stock-related for validation layer
        result['routing']['is_stock_query'] = True

    # Detect housing/rent queries -> add Zillow (FRED has CPI shelter, permits, etc.)
    housing_keywords = [
        'rent', 'rents', 'rental', 'market rent', 'actual rent', 'zillow',
        'home value', 'home price', 'house price', 'zori', 'zhvi'
    ]
    if any(kw in query_lower for kw in housing_keywords):
        if 'zillow' not in result['routing']['secondary_sources']:
            result['routing']['secondary_sources'].append('zillow')

    # Detect query type
    if any(kw in query_lower for kw in ['vs', 'versus', 'compared to', 'compare']):
        result['intent']['query_type'] = 'comparison'
        result['routing']['is_comparison'] = True
    elif any(kw in query_lower for kw in ['what is', 'what\'s the', 'current']):
        result['intent']['query_type'] = 'factual'
    elif any(kw in query_lower for kw in ['will', 'going to', 'coming', 'predict']):
        result['intent']['query_type'] = 'forecast'
        result['routing']['secondary_sources'].append('polymarket')

    return result


def validate_series_for_query(query_understanding: Dict, proposed_series: list) -> Dict:
    """
    Validate that proposed series match the query intent.

    This is the "gut check" layer - if Gemini detected specific entities
    (demographics, sectors, regions) but the routing returned generic series,
    we override with the correct specific series.

    Args:
        query_understanding: The Gemini analysis of the query
        proposed_series: List of FRED series IDs from routing

    Returns:
        Dict with:
        - valid: bool - whether the series are appropriate
        - corrected_series: list - correct series if invalid
        - reason: str - explanation of why correction was needed
        - entity_type: str - type of entity (demographic, sector, region)
        - entity_name: str - name of the specific entity
    """
    if not query_understanding:
        return {'valid': True, 'corrected_series': None, 'reason': None}

    routing = query_understanding.get('routing', {})
    entities = query_understanding.get('entities', {})
    demographics = entities.get('demographics', [])
    sectors = entities.get('sectors', [])
    regions = entities.get('regions', [])

    # =================================================================
    # DEMOGRAPHIC SERIES MAPPING
    # =================================================================
    DEMOGRAPHIC_SERIES = {
        'women': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
        'female': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
        'men': ['LNS14000001', 'LNS11300001', 'LNS12300001'],
        'male': ['LNS14000001', 'LNS11300001', 'LNS12300001'],
        'black': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
        'african american': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
        'hispanic': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
        'latino': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
        'latina': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
        'asian': ['LNS14000004', 'LNS11300004', 'LNS12300004'],
        'white': ['LNS14000003', 'LNS11300003', 'LNS12300003'],
        'youth': ['LNS14000012', 'LNS14000036'],
        'teen': ['LNS14000012'],
        'veteran': ['LNS14049526'],
    }

    # =================================================================
    # SECTOR SERIES MAPPING
    # =================================================================
    SECTOR_SERIES = {
        'manufacturing': ['MANEMP', 'IPMAN', 'AWHMAN', 'CES3000000001'],
        'construction': ['USCONS', 'HOUST', 'PERMIT', 'CES2000000001'],
        'retail': ['USTRADE', 'RSXFS', 'RETAILSMNSA', 'CES4200000001'],
        'restaurants': ['CES7072200001', 'USHOSLEMPL'],
        'hospitality': ['USLAH', 'CES7000000001'],
        'leisure': ['USLAH', 'CES7000000001'],
        'healthcare': ['USHEALTHEMPL', 'CES6562000001'],
        'tech': ['USINFO', 'CES5000000001'],
        'technology': ['USINFO', 'CES5000000001'],
        'information': ['USINFO', 'CES5000000001'],
        'finance': ['USFIRE', 'CES5500000001'],
        'financial': ['USFIRE', 'CES5500000001'],
        'financials': ['av_xlf', 'av_spy', 'DGS10'],  # Financial sector ETF + rates
        'government': ['USGOVT', 'CES9000000001'],
        'education': ['CES6561000001', 'CES9091000001'],
        'mining': ['USMINE', 'CES1000000001'],
        'energy': ['av_xle', 'av_crude_oil', 'eia_wti_crude'],  # Energy sector ETF + oil prices
        'transportation': ['USTPU', 'CES4300000001'],
        'professional services': ['USPBS', 'CES6000000001'],
        'business services': ['USPBS', 'CES6000000001'],
        # Alpha Vantage sector ETFs for stock-focused queries
        'industrials': ['av_xli', 'av_spy', 'INDPRO'],  # Industrial sector ETF + production
        'utilities': ['av_xlu', 'INDPRO'],  # Utilities ETF
        'materials': ['av_xlb', 'INDPRO'],  # Materials ETF
        'communications': ['av_xlc', 'USINFO'],  # Communications ETF
        'consumer_discretionary': ['av_xly', 'RSXFS'],  # Consumer discretionary + retail sales
        'consumer_staples': ['av_xlp', 'PCE'],  # Consumer staples + consumption
        'real_estate': ['av_xlre', 'HOUST', 'MORTGAGE30US'],  # Real estate ETF + housing
    }

    # =================================================================
    # TOPIC-SPECIFIC SERIES MAPPING
    # =================================================================
    TOPIC_SERIES = {
        'housing': ['CSUSHPINSA', 'HOUST', 'MORTGAGE30US', 'EXHOSLUSM495S'],
        'rent': ['CUSR0000SEHA', 'CUUR0000SEHA'],
        'inflation': ['CPIAUCSL', 'CPILFESL', 'PCEPI', 'PCEPILFE'],
        'wages': ['CES0500000003', 'AHETPI', 'ECIWAG'],
        'gas': ['GASREGW', 'GASREGCOVW'],
        'oil': ['DCOILWTICO', 'DCOILBRENTEU'],
        'interest rates': ['FEDFUNDS', 'DFF', 'DGS10', 'DGS2'],
        'fed': ['FEDFUNDS', 'DFF', 'WALCL'],
        'savings': ['PSAVERT', 'PMSAVE'],
        'consumer': ['UMCSENT', 'PCE', 'RSXFS'],
        'credit': ['TOTALSL', 'REVOLSL', 'NONREVSL'],
        'debt': ['GFDEBTN', 'HDTGPDUSQ163N', 'TDSP'],
        # Stock market / Mag7 - prefer Alpha Vantage for daily data
        'stocks': ['av_spy', 'av_qqq', 'av_dia', 'av_vix'],
        'mag7': ['av_qqq', 'av_xlk', 'av_nvda', 'av_aapl', 'av_msft'],
        'tech stocks': ['av_qqq', 'av_xlk', 'av_nvda'],
        # Sector/industry stock queries - use Alpha Vantage ETFs
        'oil companies': ['av_xle', 'av_crude_oil', 'eia_wti_crude'],
        'energy stocks': ['av_xle', 'av_crude_oil', 'av_natural_gas'],
        'bank stocks': ['av_xlf', 'FEDFUNDS', 'DGS10'],
        'regional banks': ['av_xlf', 'FEDFUNDS', 'T10Y2Y'],
        'financial stocks': ['av_xlf', 'av_spy', 'DGS10'],
        'healthcare stocks': ['av_xlv', 'USHEALTHEMPL'],
        'industrial stocks': ['av_xli', 'INDPRO', 'DGORDER'],
        'retail stocks': ['av_xly', 'RSXFS', 'UMCSENT'],
        'utility stocks': ['av_xlu', 'INDPRO'],
        'real estate stocks': ['av_xlre', 'HOUST', 'MORTGAGE30US'],
        'defense stocks': ['av_xli', 'USGOVT'],  # Defense is in industrials
        'semiconductor': ['av_nvda', 'av_xlk', 'av_qqq'],
        'emerging markets': ['av_eem', 'av_fxi', 'av_vwo'],
        'international stocks': ['av_efa', 'av_eem', 'av_ewj'],
        'bonds': ['av_tlt', 'av_lqd', 'DGS10'],
        'treasury bonds': ['av_tlt', 'av_shy', 'DGS10', 'DGS2'],
        'corporate bonds': ['av_lqd', 'av_hyg', 'BAMLH0A0HYM2'],
        # Bubble/valuation questions - need P/E, market indices, and comparison to dot-com
        'bubble': ['av_qqq', 'av_spy', 'SP500', 'NASDAQCOM'],  # Long history for comparison
        'ai bubble': ['av_qqq', 'av_xlk', 'av_nvda', 'NASDAQCOM'],  # AI/tech focused
        'tech bubble': ['av_qqq', 'av_xlk', 'NASDAQCOM'],
        'overvalued': ['av_spy', 'av_qqq', 'SP500', 'NASDAQCOM'],
        'valuation': ['av_spy', 'av_qqq', 'SP500'],
        'market correction': ['av_spy', 'av_vix', 'SP500', 'T10Y2Y'],
        'crash': ['av_spy', 'av_vix', 'ICSA', 'T10Y2Y'],  # Include recession indicators
    }

    # Generic series that should NOT be used for specific queries
    GENERIC_LABOR_SERIES = {'UNRATE', 'PAYEMS', 'LNS12300060', 'CIVPART', 'EMRATIO'}

    proposed_set = set(proposed_series) if proposed_series else set()

    # =================================================================
    # CHECK DEMOGRAPHICS
    # =================================================================
    if demographics:
        for demo in demographics:
            demo_lower = demo.lower()
            if demo_lower in DEMOGRAPHIC_SERIES:
                expected = set(DEMOGRAPHIC_SERIES[demo_lower])
                has_specific = bool(expected & proposed_set)
                has_generic = bool(GENERIC_LABOR_SERIES & proposed_set)

                if not has_specific and (has_generic or not proposed_set):
                    return {
                        'valid': False,
                        'corrected_series': DEMOGRAPHIC_SERIES[demo_lower],
                        'reason': f"Query is about {demo} but routing returned generic labor data. Using {demo}-specific series.",
                        'entity_type': 'demographic',
                        'entity_name': demo
                    }

    # =================================================================
    # CHECK SECTORS
    # =================================================================
    # Trigger when sectors detected - don't require is_sector_specific flag
    # If query mentions "stocks" or "companies", prefer market data (ETFs) over employment

    # Sector to Alpha Vantage ETF mapping for stock-focused queries
    SECTOR_TO_ETF = {
        'tech': ['av_xlk', 'av_qqq', 'av_nvda'],
        'technology': ['av_xlk', 'av_qqq', 'av_nvda'],
        'healthcare': ['av_xlv', 'USHEALTHEMPL'],
        'financials': ['av_xlf', 'DGS10', 'FEDFUNDS'],
        'energy': ['av_xle', 'av_crude_oil', 'eia_wti_crude'],
        'industrials': ['av_xli', 'INDPRO'],
        'consumer_discretionary': ['av_xly', 'RSXFS'],
        'consumer_staples': ['av_xlp', 'PCE'],
        'utilities': ['av_xlu'],
        'materials': ['av_xlb'],
        'real_estate': ['av_xlre', 'HOUST'],
        'communications': ['av_xlc', 'USINFO'],
    }

    query_lower_check = query_understanding.get('intent', {}).get('core_question', '').lower()
    is_stock_focused = any(kw in query_lower_check for kw in ['stock', 'stocks', 'companies', 'company', 'etf'])

    if sectors:
        for sector in sectors:
            sector_lower = sector.lower()

            # If query is about stocks/companies, prefer ETF data over employment
            if is_stock_focused and sector_lower in SECTOR_TO_ETF:
                etf_series = SECTOR_TO_ETF[sector_lower]
                etf_set = set(etf_series)
                has_etf = bool(etf_set & proposed_set)

                if not has_etf and (GENERIC_LABOR_SERIES & proposed_set or not proposed_set):
                    return {
                        'valid': False,
                        'corrected_series': etf_series,
                        'reason': f"Query is about {sector} stocks/companies. Using sector ETF and market data.",
                        'entity_type': 'sector_market',
                        'entity_name': sector
                    }

            # Otherwise use employment/activity data
            elif sector_lower in SECTOR_SERIES:
                expected = set(SECTOR_SERIES[sector_lower])
                has_specific = bool(expected & proposed_set)
                has_generic = bool(GENERIC_LABOR_SERIES & proposed_set)

                # Override if we have generic labor series but not sector-specific
                if not has_specific and (has_generic or not proposed_set):
                    return {
                        'valid': False,
                        'corrected_series': SECTOR_SERIES[sector_lower],
                        'reason': f"Query is about {sector} sector but routing returned generic data. Using {sector}-specific series.",
                        'entity_type': 'sector',
                        'entity_name': sector
                    }

    # =================================================================
    # CHECK STOCK/MARKET QUERIES
    # =================================================================
    # If query is about stocks/Mag7 but we're returning employment data, override
    # Use Alpha Vantage series for daily real-time data (FRED is lagged monthly)
    STOCK_SERIES_FRED = {'SP500', 'NASDAQCOM', 'DJIA', 'VIXCLS', 'CP'}
    STOCK_SERIES_AV = {'av_spy', 'av_qqq', 'av_dia', 'av_vix', 'av_xlk',
                       'av_aapl', 'av_msft', 'av_googl', 'av_amzn', 'av_nvda', 'av_meta', 'av_tsla'}
    STOCK_SERIES = STOCK_SERIES_FRED | STOCK_SERIES_AV

    MAG7_KEYWORDS = ['mag7', 'mag 7', 'magnificent 7', 'magnificent seven', 'big tech', 'faang', 'megacap']
    STOCK_KEYWORDS = MAG7_KEYWORDS + ['stock', 'stocks', 'nasdaq', 's&p', 'sp500', 'tech stock', 'market index', 'companies']

    query_lower_check = query_understanding.get('intent', {}).get('core_question', '').lower()
    is_stock_query = routing.get('is_stock_query', False) or any(kw in query_lower_check for kw in STOCK_KEYWORDS)
    is_mag7_query = any(kw in query_lower_check for kw in MAG7_KEYWORDS)

    if is_stock_query:
        has_stock_series = bool(STOCK_SERIES & proposed_set)
        has_employment = bool({'USINFO', 'CES5000000001', 'PAYEMS'} & proposed_set)

        if not has_stock_series and (has_employment or not proposed_set):
            # Use Alpha Vantage for real-time daily data
            if is_mag7_query:
                # Mag7 query: Use QQQ (NASDAQ-100) as primary proxy (~50% Mag7 by weight)
                # Plus XLK (tech sector ETF) and individual Mag7 stocks
                return {
                    'valid': False,
                    'corrected_series': ['av_qqq', 'av_xlk', 'av_nvda', 'av_aapl', 'av_msft'],
                    'reason': "Query is about Mag7. Using Alpha Vantage daily data: QQQ (~50% Mag7), XLK (tech sector), and top Mag7 stocks.",
                    'entity_type': 'market',
                    'entity_name': 'mag7'
                }
            else:
                # General stock/market query: Use broad indices
                return {
                    'valid': False,
                    'corrected_series': ['av_spy', 'av_qqq', 'av_dia'],
                    'reason': "Query is about stock market. Using Alpha Vantage daily data: S&P 500, NASDAQ-100, and Dow Jones ETFs.",
                    'entity_type': 'market',
                    'entity_name': 'stocks'
                }

    # =================================================================
    # CHECK TOPIC-SPECIFIC QUERIES (oil companies, banks, etc.)
    # =================================================================
    # Match query against TOPIC_SERIES for industry/topic specific overrides
    for topic, topic_series in TOPIC_SERIES.items():
        if topic in query_lower_check:
            # Found a topic match - check if we have appropriate series
            topic_series_set = set(topic_series)
            has_topic_series = bool(topic_series_set & proposed_set)

            if not has_topic_series and (GENERIC_LABOR_SERIES & proposed_set or not proposed_set):
                # We have generic data but query is about a specific topic
                return {
                    'valid': False,
                    'corrected_series': topic_series,
                    'reason': f"Query is about {topic}. Using relevant market data and indicators.",
                    'entity_type': 'topic',
                    'entity_name': topic
                }

    # =================================================================
    # CHECK DATA REQUIREMENTS FROM GEMINI
    # =================================================================
    data_reqs = query_understanding.get('data_requirements', {})
    indicators_needed = data_reqs.get('indicators_needed', [])

    # If Gemini explicitly said what indicators are needed, check if we have them
    if indicators_needed and data_reqs.get('must_be_group_specific'):
        # This is a strong signal that generic data won't work
        if proposed_set and proposed_set.issubset(GENERIC_LABOR_SERIES):
            # We're returning only generic data but Gemini said we need specific
            # Try to infer what's needed from the indicators list
            for indicator in indicators_needed:
                indicator_lower = indicator.lower()
                # Check if indicator mentions a demographic
                for demo, series in DEMOGRAPHIC_SERIES.items():
                    if demo in indicator_lower:
                        return {
                            'valid': False,
                            'corrected_series': series,
                            'reason': f"Query requires '{indicator}' but got generic data. Using {demo}-specific series.",
                            'entity_type': 'demographic',
                            'entity_name': demo
                        }
                # Check if indicator mentions a sector
                for sector, series in SECTOR_SERIES.items():
                    if sector in indicator_lower:
                        return {
                            'valid': False,
                            'corrected_series': series,
                            'reason': f"Query requires '{indicator}' but got generic data. Using {sector} sector series.",
                            'entity_type': 'sector',
                            'entity_name': sector
                        }

    return {'valid': True, 'corrected_series': None, 'reason': None}


def get_routing_recommendation(understanding: Dict) -> Dict:
    """
    Based on the query understanding, recommend the routing path.

    This helps app.py decide:
    - Should we use pre-computed plans?
    - Should we use comparison routing?
    - Should we use international data?
    - Should we add supplementary sources?

    Returns:
        Dict with routing recommendations
    """
    routing = understanding.get('routing', {})
    entities = understanding.get('entities', {})
    intent = understanding.get('intent', {})

    recommendations = {
        # Primary routing decisions
        'use_comparison_router': routing.get('is_comparison', False),
        'use_international_data': routing.get('is_international', False),
        'require_demographic_filter': routing.get('is_demographic_specific', False),
        'require_sector_filter': routing.get('is_sector_specific', False),

        # Data sources to query
        'data_sources': {
            'primary': routing.get('primary_source', 'fred'),
            'secondary': routing.get('secondary_sources', [])
        },

        # Filters to apply
        'demographic_filter': entities.get('demographics', []),
        'sector_filter': entities.get('sectors', []),
        'region_filter': entities.get('regions', []),

        # Query metadata
        'query_type': intent.get('query_type', 'analytical'),
        'complexity': intent.get('complexity', 'moderate'),

        # Warnings
        'pitfalls': understanding.get('pitfalls', [])
    }

    return recommendations


# =============================================================================
# DYNAMIC SERIES SELECTION - LLM-Powered Data Routing
# =============================================================================

# Condensed catalog of available data for Gemini to reason about
# This is a summary - Gemini picks from these categories and we map to actual series
DATA_CATALOG_SUMMARY = """
## AVAILABLE DATA SOURCES

### ALPHA VANTAGE (Real-time daily market data)
**Stock Indices (ETFs)**:
- av_spy: S&P 500 (SPY ETF) - broad US market
- av_qqq: NASDAQ-100 (QQQ ETF) - tech-heavy, ~50% Mag7
- av_dia: Dow Jones (DIA ETF) - blue chip industrials
- av_iwm: Russell 2000 (IWM ETF) - small caps
- av_vix: VIX volatility (VXX) - fear gauge

**Magnificent 7 Individual Stocks**:
- av_aapl: Apple - consumer electronics, services
- av_msft: Microsoft - enterprise software, cloud, AI
- av_googl: Alphabet/Google - search, ads, cloud, AI
- av_amzn: Amazon - e-commerce, AWS cloud
- av_nvda: NVIDIA - GPUs, AI chips (AI infrastructure leader)
- av_meta: Meta - social media (Facebook, Instagram)
- av_tsla: Tesla - EVs, energy, autonomous driving

**Sector ETFs (S&P 500 sectors)**:
- av_xlk: Technology (Apple, Microsoft, NVIDIA)
- av_xlf: Financials (banks, insurance - JPMorgan, BofA)
- av_xle: Energy (oil/gas - Exxon, Chevron)
- av_xlv: Healthcare (pharma, biotech - UnitedHealth, Lilly)
- av_xli: Industrials (aerospace, machinery - GE, Caterpillar)
- av_xly: Consumer Discretionary (retail - Amazon, Tesla, Home Depot)
- av_xlp: Consumer Staples (food, household - P&G, Costco, Walmart)
- av_xlu: Utilities (electric, defensive)
- av_xlb: Materials (chemicals, mining)
- av_xlre: Real Estate (REITs, data centers)
- av_xlc: Communications (Meta, Alphabet, Netflix)

**International ETFs**:
- av_eem: Emerging Markets (China, India, Brazil)
- av_efa: Developed ex-US (Europe, Japan)
- av_fxi: China large-cap (Alibaba, Tencent)
- av_ewj: Japan (Toyota, Sony)
- av_ewg: Germany (Siemens, SAP)

**Bonds & Treasuries**:
- av_tlt: Long-term Treasury (TLT ETF, 20+ year)
- av_shy: Short-term Treasury (SHY ETF, 1-3 year)
- av_lqd: Investment Grade Corporate Bonds
- av_hyg: High Yield Corporate Bonds (junk bonds)
- av_treasury_10y: 10-Year Treasury Yield
- av_treasury_2y: 2-Year Treasury Yield
- av_treasury_30y: 30-Year Treasury Yield

**Commodities**:
- av_crude_oil: WTI Crude Oil price
- av_brent: Brent Crude Oil price
- av_natural_gas: Natural Gas (Henry Hub)
- av_gold: Gold price (safe haven)

**Forex**:
- av_eurusd: Euro/Dollar
- av_usdjpy: Dollar/Yen
- av_gbpusd: Pound/Dollar
- av_dollar_index: US Dollar Index

### FRED (Federal Reserve Economic Data - comprehensive US economic data)
**Labor Market**:
- UNRATE: Overall unemployment rate
- PAYEMS: Total nonfarm payrolls (job growth)
- CIVPART: Labor force participation rate
- ICSA: Initial jobless claims (weekly)
- JTS1000JOL: Job openings (JOLTS)
- CES0500000003: Average hourly earnings

**Demographic Employment** (use these for demographic-specific queries):
- LNS14000002: Women unemployment rate
- LNS14000001: Men unemployment rate
- LNS14000006: Black unemployment rate
- LNS14000009: Hispanic unemployment rate
- LNS14000003: White unemployment rate
- LNS14000012: Youth (16-19) unemployment rate

**Sector Employment**:
- MANEMP: Manufacturing employment
- USCONS: Construction employment
- USTRADE: Retail trade employment
- USLAH: Leisure & hospitality employment
- USINFO: Information/tech sector employment
- USFIRE: Finance/insurance employment
- USHEALTHEMPL: Healthcare employment
- CES7072200001: Restaurants/bars employment

**Inflation & Prices**:
- CPIAUCSL: Consumer Price Index (headline inflation)
- CPILFESL: Core CPI (ex food & energy)
- PCEPI: PCE Price Index (Fed's preferred measure)
- PCEPILFE: Core PCE

**GDP & Output**:
- GDPC1: Real GDP
- A191RL1Q225SBEA: Real GDP growth rate
- INDPRO: Industrial production
- DGORDER: Durable goods orders

**Interest Rates & Fed**:
- FEDFUNDS: Federal funds rate
- DGS10: 10-year Treasury yield
- DGS2: 2-year Treasury yield
- T10Y2Y: Yield curve (10Y-2Y spread)
- MORTGAGE30US: 30-year mortgage rate

**Housing**:
- HOUST: Housing starts
- PERMIT: Building permits
- CSUSHPINSA: Case-Shiller home price index
- EXHOSLUSM495S: Existing home sales

**Consumer & Business**:
- RSXFS: Retail sales
- UMCSENT: Consumer sentiment
- PCE: Personal consumption expenditures
- BUSLOANS: Commercial & industrial loans
- CP: Corporate profits

**Financial Conditions**:
- SP500: S&P 500 index (monthly, lagged)
- NASDAQCOM: NASDAQ Composite (monthly, lagged)
- VIXCLS: VIX volatility index
- BAMLH0A0HYM2: High yield bond spread

### EIA (Energy Information Administration)
- eia_wti_crude: WTI crude oil price
- eia_gasoline_retail: Retail gasoline price
- eia_natural_gas_henry_hub: Natural gas spot price
- eia_crude_production: US crude oil production
- eia_crude_stocks: US crude oil inventories

### ZILLOW (Real estate market data)
- zillow_rent_national: National median rent (ZORI)
- zillow_home_value_national: National home values (ZHVI)
- zillow_rent_* / zillow_home_*: Metro-level data available

### DBNOMICS (International economic data)
- Eurozone GDP, inflation, unemployment
- UK, Japan, China, Germany data
- Use for international comparisons
"""

SERIES_SELECTION_PROMPT = """You are an expert economist selecting data series to answer a user's question.

USER QUERY: "{query}"

{catalog}

## YOUR TASK

Based on the query, select 3-6 data series that would BEST answer this question.

Think step by step:
1. What is the user really asking about?
2. What data would an economist look at to answer this?
3. Which specific series from the catalog match?

## IMPORTANT RULES
- Return ONLY series IDs from the catalog above (e.g., "av_xle", "UNRATE", "eia_wti_crude")
- For stock/market queries, prefer Alpha Vantage (av_*) for real-time daily data
- For economic indicators, use FRED
- For demographic questions, use the demographic-specific FRED series
- For energy/oil, combine EIA data with relevant ETFs
- Pick 3-6 most relevant series - quality over quantity

## RESPONSE FORMAT

Return JSON only:
```json
{{
    "reasoning": "Brief explanation of why these series answer the query",
    "series": ["series_id_1", "series_id_2", "series_id_3"],
    "explanation": "One sentence explaining what these series show together"
}}
```

RESPOND WITH JSON ONLY."""


def get_dynamic_series(query: str, verbose: bool = False) -> Dict:
    """
    Use Gemini to dynamically select series for ANY query.

    This is the "on your feet" function - instead of hard-coded keyword mappings,
    Gemini reasons about the query and the available data catalog to decide
    what series to fetch.

    Args:
        query: User's natural language query
        verbose: Print debug info

    Returns:
        Dict with:
        - series: List of series IDs to fetch
        - reasoning: Why these series were chosen
        - explanation: What the series show together
        - success: Whether dynamic selection worked
    """
    if not GEMINI_API_KEY:
        if verbose:
            print("  [DynamicSeries] No Gemini API key, falling back to validation layer")
        return {'series': [], 'reasoning': None, 'explanation': None, 'success': False}

    # Check cache first
    cache_key = f"dynamic_{query.lower().strip()}"
    cached = _get_understanding_cache(cache_key)
    if cached:
        if verbose:
            print("  [DynamicSeries] Using cached result")
        return cached

    if verbose:
        print(f"  [DynamicSeries] Asking Gemini to select series for: {query}")

    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'

    prompt = SERIES_SELECTION_PROMPT.format(query=query, catalog=DATA_CATALOG_SUMMARY)

    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.3,  # Slightly higher for creative reasoning
            'maxOutputTokens': 800
        }
    }
    headers = {'Content-Type': 'application/json'}

    try:
        req = Request(url, data=json.dumps(payload).encode('utf-8'),
                     headers=headers, method='POST')
        with urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode('utf-8'))
            content = result['candidates'][0]['content']['parts'][0]['text']

            # Extract JSON from response
            parsed = _extract_json(content)

            if parsed and 'series' in parsed:
                series_list = parsed['series']

                # Validate that series exist in our catalogs
                valid_series = _validate_series_exist(series_list)

                result = {
                    'series': valid_series,
                    'reasoning': parsed.get('reasoning', ''),
                    'explanation': parsed.get('explanation', ''),
                    'success': len(valid_series) > 0
                }

                if verbose:
                    print(f"  [DynamicSeries] Selected: {valid_series}")
                    print(f"  [DynamicSeries] Reasoning: {parsed.get('reasoning', '')[:100]}...")

                # Cache the result
                _set_understanding_cache(cache_key, result)
                return result

    except Exception as e:
        if verbose:
            print(f"  [DynamicSeries] Error: {e}")

    return {'series': [], 'reasoning': None, 'explanation': None, 'success': False}


def _validate_series_exist(series_list: List[str]) -> List[str]:
    """
    Validate that the series Gemini selected actually exist in our catalogs.

    Returns only the valid series IDs.
    """
    valid = []

    # Import catalogs lazily to avoid circular imports
    try:
        from agents.alphavantage import ALPHAVANTAGE_SERIES
        av_series = set(ALPHAVANTAGE_SERIES.keys())
    except:
        av_series = set()

    try:
        from agents.eia import EIA_SERIES
        eia_series = set(EIA_SERIES.keys())
    except:
        eia_series = set()

    try:
        from agents.zillow import ZILLOW_METROS
        zillow_series = set(ZILLOW_METROS.keys())
    except:
        zillow_series = set()

    # Known FRED series (we don't import all, just validate format)
    # FRED series are typically uppercase alphanumeric

    for series_id in series_list:
        series_id = series_id.strip()

        # Check Alpha Vantage
        if series_id in av_series:
            valid.append(series_id)
            continue

        # Check EIA
        if series_id in eia_series:
            valid.append(series_id)
            continue

        # Check Zillow
        if series_id.startswith('zillow_') and series_id in zillow_series:
            valid.append(series_id)
            continue

        # Assume FRED series are valid if they match the pattern
        # (uppercase, possibly with numbers, common prefixes)
        if series_id.isupper() or series_id.startswith('LNS') or series_id.startswith('CES'):
            valid.append(series_id)
            continue

        # Check for av_ prefix even if not in catalog (might be valid)
        if series_id.startswith('av_'):
            valid.append(series_id)
            continue

        if series_id.startswith('eia_'):
            valid.append(series_id)
            continue

    return valid


def get_series_for_query(query: str, verbose: bool = False) -> Dict:
    """
    Main entry point for getting series to answer a query.

    This combines:
    1. Dynamic Gemini reasoning (tries first)
    2. Validation layer fallback (hard-coded mappings)
    3. Health check routing (for "how is X doing" queries)

    Args:
        query: User's natural language query
        verbose: Print debug info

    Returns:
        Dict with:
        - series: List of series IDs to fetch
        - source: How the series were determined ('dynamic', 'validation', 'health_check')
        - explanation: What the series show
    """
    # Try dynamic Gemini reasoning first
    dynamic_result = get_dynamic_series(query, verbose=verbose)

    if dynamic_result['success'] and len(dynamic_result['series']) >= 2:
        return {
            'series': dynamic_result['series'],
            'source': 'dynamic',
            'explanation': dynamic_result['explanation'],
            'reasoning': dynamic_result['reasoning']
        }

    # Fallback to validation layer (which uses understand_query + validate_series_for_query)
    if verbose:
        print("  [SeriesSelection] Dynamic failed, using validation layer fallback")

    understanding = understand_query(query, verbose=verbose)

    # Use validation layer FIRST for demographic/sector/topic overrides
    # This takes priority over generic health check routing
    validation = validate_series_for_query(understanding, [])
    if not validation['valid'] and validation.get('corrected_series'):
        return {
            'series': validation['corrected_series'],
            'source': 'validation',
            'explanation': validation.get('reason', ''),
            'entity_type': validation.get('entity_type', ''),
            'entity_name': validation.get('entity_name', '')
        }

    # Check health check routing (only if validation didn't override)
    try:
        from core.health_check_indicators import route_health_check_query
        health_result = route_health_check_query(query)
        if health_result and health_result.get('series'):
            return {
                'series': health_result['series'],
                'source': 'health_check',
                'explanation': health_result.get('explanation', ''),
                'entity': health_result.get('entity', '')
            }
    except:
        pass

    # Last resort: return empty (let app.py handle default routing)
    return {
        'series': [],
        'source': 'none',
        'explanation': 'Could not determine specific series'
    }


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    test_queries = [
        "How are Black workers doing?",
        "US vs Eurozone GDP",
        "What is the Fed funds rate?",
        "Is a recession coming?",
        "How is the restaurant industry doing?",
        "Women's employment trends",
        "Compare China and US growth",
        "What's happening with market rents?",
    ]

    print("=" * 70)
    print("QUERY UNDERSTANDING TEST")
    print("=" * 70)

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print("-" * 40)

        understanding = understand_query(query, verbose=True)

        # Print key insights
        print(f"\nKey Insights:")
        print(f"  Query Type: {understanding.get('intent', {}).get('query_type')}")
        print(f"  Demographics: {understanding.get('entities', {}).get('demographics', [])}")
        print(f"  Regions: {understanding.get('entities', {}).get('regions', [])}")
        print(f"  Sectors: {understanding.get('entities', {}).get('sectors', [])}")
        print(f"  Is Comparison: {understanding.get('routing', {}).get('is_comparison')}")
        print(f"  Pitfalls: {understanding.get('pitfalls', [])[:2]}")
