"""
Economist reasoning module for EconStats.

This module implements real-time AI reasoning about what economic indicators
an analyst would need to answer a question - rather than relying on pre-computed
query-to-series mappings.

Flow:
1. Query comes in
2. Check for direct data requests (e.g., "What is the Fed funds rate?") - return the actual data
3. For analytical questions, AI reasons about what indicators are needed
4. Search FRED for those indicators
5. Return the series

This is the PRIMARY approach. Pre-computed plans are a fast-path cache/backstop.
"""

import json
import os
import re
from typing import Optional
from urllib.request import urlopen, Request

# API Keys - check both GEMINI_API_KEY and GOOGLE_API_KEY for compatibility
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

# =============================================================================
# DIRECT DATA MAPPINGS
# For unambiguous questions asking for specific data, return the data directly.
# This prevents over-interpretation (e.g., "What is the Fed rate?" should return
# FEDFUNDS, not inflation metrics that influence rates).
# =============================================================================

DIRECT_SERIES_MAPPINGS = {
    # Federal Reserve / Interest Rates
    'fed funds rate': ['FEDFUNDS', 'DFEDTARU'],
    'fed rate': ['FEDFUNDS', 'DGS2', 'DGS10'],
    'federal funds': ['FEDFUNDS'],
    'interest rate': ['FEDFUNDS', 'DGS10', 'DGS2'],
    'interest rates': ['FEDFUNDS', 'DGS10', 'DGS2'],
    'what is the fed doing': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y'],
    'what is the fed doing with interest rates': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y', 'MORTGAGE30US'],
    'fed doing': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y'],
    'fed doing with interest rates': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y', 'MORTGAGE30US'],
    'fed doing with rates': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y', 'MORTGAGE30US'],
    'fed policy': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y'],
    'fed interest rates': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y'],
    'monetary policy': ['FEDFUNDS', 'DGS2', 'DGS10', 'T10Y2Y', 'M2SL'],
    'treasury yield': ['DGS10', 'DGS2', 'DGS30'],
    'treasury yields': ['DGS10', 'DGS2', 'DGS30'],
    '10 year treasury': ['DGS10'],
    '10-year treasury': ['DGS10'],
    '2 year treasury': ['DGS2'],
    'yield curve': ['T10Y2Y', 'DGS10', 'DGS2'],
    'mortgage rate': ['MORTGAGE30US', 'MORTGAGE15US'],
    'mortgage rates': ['MORTGAGE30US', 'MORTGAGE15US'],
    '30 year mortgage': ['MORTGAGE30US'],
    '30-year mortgage': ['MORTGAGE30US'],

    # Inflation - specific measures
    'inflation': ['CPIAUCSL', 'PCEPILFE'],  # P0 FIX: Generic inflation query
    'headline inflation': ['CPIAUCSL', 'PCEPI'],  # P0 FIX: Non-core (headline) inflation
    'core inflation': ['CPILFESL', 'PCEPILFE'],
    'core cpi': ['CPILFESL'],
    'core pce': ['PCEPILFE'],
    'cpi': ['CPIAUCSL', 'CPILFESL'],
    'pce': ['PCEPI', 'PCEPILFE'],
    'inflation rate': ['CPIAUCSL', 'PCEPILFE'],
    'food prices': ['CPIUFDNS', 'CPIUFDSL'],
    'food inflation': ['CPIUFDNS', 'CPIUFDSL'],
    'grocery prices': ['CPIUFDNS'],
    'shelter inflation': ['CUSR0000SAH1', 'zillow_rent_yoy'],
    'rent inflation': ['CUSR0000SEHA', 'zillow_rent_yoy'],  # CPI rent + Zillow (both YoY %)
    'rent inflation coming down': ['CUSR0000SEHA', 'zillow_rent_yoy'],  # apples-to-apples comparison
    'rents coming down': ['CUSR0000SEHA', 'zillow_rent_yoy'],
    'rent cpi': ['CUSR0000SEHA'],
    'rental inflation': ['CUSR0000SEHA', 'zillow_rent_yoy'],
    'housing rent': ['CUSR0000SEHA', 'zillow_rent_yoy'],
    'rent prices': ['CUSR0000SEHA', 'zillow_zori_national'],  # levels, not YoY
    'owners equivalent rent': ['CUSR0000SEHC'],
    'oer': ['CUSR0000SEHC'],
    'market rent': ['zillow_zori_national', 'zillow_rent_yoy'],
    'zillow rent': ['zillow_zori_national', 'zillow_rent_yoy'],

    # GDP - specific measures (YoY primary, quarterly secondary)
    'gdp': ['A191RO1Q156NBEA', 'A191RL1Q225SBEA'],
    'real gdp': ['GDPC1'],
    'gdp growth': ['A191RO1Q156NBEA', 'A191RL1Q225SBEA'],
    'gdp now': ['GDPNOW', 'STLENI'],  # Only for explicit nowcast queries
    'gdpnow': ['GDPNOW', 'STLENI'],
    'nowcast': ['GDPNOW', 'STLENI'],
    'economic growth': ['A191RO1Q156NBEA', 'A191RL1Q225SBEA'],
    'recession': ['SAHMREALTIME', 'T10Y2Y', 'UNRATE', 'UMCSENT', 'A191RL1Q225SBEA'],
    'is a recession coming': ['SAHMREALTIME', 'T10Y2Y', 'UMCSENT', 'ICSA', 'USSLIND'],
    'recession risk': ['SAHMREALTIME', 'T10Y2Y', 'UMCSENT', 'ICSA', 'USSLIND'],
    'recession probability': ['SAHMREALTIME', 'RECPROUSM156N', 'T10Y2Y'],

    # Employment - specific measures
    'unemployment rate': ['UNRATE', 'U6RATE'],
    'unemployment': ['UNRATE', 'U6RATE'],
    'payrolls': ['PAYEMS'],
    'nonfarm payrolls': ['PAYEMS'],
    'jobs report': ['PAYEMS', 'UNRATE'],
    'job openings': ['JTSJOL'],
    'initial claims': ['ICSA'],
    'jobless claims': ['ICSA'],
    'layoffs': ['ICSA', 'JTSLDL'],
    'are there layoffs': ['ICSA', 'JTSLDL'],

    # Demographic-specific employment (must be before generic "unemployment")
    # Women
    'women unemployment': ['LNS14000002'],
    'women workers': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
    'womens employment': ['LNS14000002', 'LNS12300002'],
    'female unemployment': ['LNS14000002'],
    'women in the labor market': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
    'women labor market': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
    'how are women doing': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
    'women in the job market': ['LNS14000002', 'LNS11300002', 'LNS12300002'],
    # Black workers
    'black unemployment': ['LNS14000006', 'LNS14000003'],
    'black workers': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
    'african american unemployment': ['LNS14000006', 'LNS14000003'],
    'black in the labor market': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
    'black labor market': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
    'how are black workers doing': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
    'african american workers': ['LNS14000006', 'LNS11300006', 'LNS12300006'],
    # Hispanic/Latino workers
    'hispanic unemployment': ['LNS14000009'],
    'hispanic workers': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
    'latino unemployment': ['LNS14000009'],
    'hispanic in the labor market': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
    'hispanic labor market': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
    'latino workers': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
    'latino in the labor market': ['LNS14000009', 'LNS11300009', 'LNS12300009'],
    # Youth
    'youth unemployment': ['LNS14000012', 'LNS14000036'],
    'teen unemployment': ['LNS14000012'],
    'young workers': ['LNS14000012', 'LNS14000036'],

    # Housing - specific measures
    'home prices': ['CSUSHPINSA', 'MSPUS'],
    'house prices': ['CSUSHPINSA', 'MSPUS'],
    'housing prices': ['CSUSHPINSA', 'MSPUS'],
    'housing starts': ['HOUST', 'HOUST1F'],
    'building permits': ['PERMIT'],
    'housing market': ['CSUSHPINSA', 'HOUST', 'MORTGAGE30US', 'EXHOSLUSM495S'],
    'existing home sales': ['EXHOSLUSM495S'],
    'new home sales': ['HSN1F'],
    'housing affordability': ['FIXHAI', 'MORTGAGE30US', 'MSPUS', 'MDSP'],
    'is housing affordable': ['FIXHAI', 'MORTGAGE30US', 'MSPUS', 'HOUST'],
    'can i afford a house': ['FIXHAI', 'MORTGAGE30US', 'MSPUS', 'TDSP'],
    'housing costs': ['CUSR0000SAH1', 'MORTGAGE30US', 'MSPUS', 'FIXHAI'],

    # Consumer
    'consumer sentiment': ['UMCSENT'],
    'consumer confidence': ['UMCSENT'],
    'retail sales': ['RSXFS'],

    # Other common
    'oil price': ['DCOILWTICO'],
    'oil prices': ['DCOILWTICO'],
    'gas prices': ['GASREGW'],
    'dollar index': ['DTWEXBGS'],
    's&p 500': ['SP500'],
    'stock market': ['SP500', 'DJIA'],

    # Recession indicators
    'are we in a recession': ['A191RL1Q225SBEA', 'T10Y2Y', 'UNRATE', 'SAHMREALTIME'],
    'recession indicators': ['T10Y2Y', 'SAHMREALTIME', 'ICSA', 'UMCSENT'],
    'sahm rule': ['SAHMREALTIME'],

    # Economy overview (YoY GDP primary, quarterly secondary)
    'economy': ['PAYEMS', 'UNRATE', 'A191RO1Q156NBEA', 'A191RL1Q225SBEA', 'CPIAUCSL'],
    'how is the economy': ['PAYEMS', 'UNRATE', 'A191RO1Q156NBEA', 'A191RL1Q225SBEA', 'CPIAUCSL'],
    'economic outlook': ['A191RO1Q156NBEA', 'A191RL1Q225SBEA', 'UNRATE', 'CPIAUCSL', 'UMCSENT'],
    'american economy': ['PAYEMS', 'UNRATE', 'A191RO1Q156NBEA', 'A191RL1Q225SBEA'],

    # Bond market
    'bond yields': ['DGS2', 'DGS10', 'DGS30'],
    'treasury spread': ['T10Y2Y', 'DGS10', 'DGS2'],
    '10 year vs 2 year': ['DGS10', 'DGS2', 'T10Y2Y'],
    'breakeven inflation': ['T5YIE', 'T10YIE'],

    # Auto industry
    'auto sales': ['TOTALSA', 'ALTSALES'],
    'car sales': ['TOTALSA', 'ALTSALES'],
    'auto industry': ['TOTALSA', 'IPG3361T3S'],

    # Consumer behavior
    'consumer spending': ['PCE', 'RSXFS'],
    'are people spending': ['RSXFS', 'PCE', 'UMCSENT'],
    'personal income': ['PI', 'DSPIC96'],
    'savings rate': ['PSAVERT'],

    # Labor market detail
    'labor market': ['PAYEMS', 'UNRATE', 'LNS12300060', 'ICSA'],  # P0 FIX: Common query
    'jobs market': ['PAYEMS', 'UNRATE', 'LNS12300060', 'ICSA'],  # P0 FIX: Alias
    'job openings vs unemployed': ['JTSJOL', 'UNEMPLOY'],
    'labor force participation': ['CIVPART'],
    'prime age employment': ['LNS12300060'],
    'prime age workers': ['LNS12300060'],  # P0 FIX: Normalized from "prime-age"
    'quits rate': ['JTSQUR'],
    'hiring rate': ['JTSHIR'],

    # More demographics
    'asian unemployment': ['LNS14000004'],
    'black employment': ['LNS14000006', 'LNS12300006', 'LNS11300006'],
    'veteran unemployment': ['LNS14049526'],

    # Business/credit
    'small business': ['NFIBOPTIMISM', 'BUSLOANS'],
    'business loans': ['BUSLOANS', 'TOTCI'],
    'credit conditions': ['DRTSCILM', 'DRTSCLCC'],

    # Wages detail
    'real wages': ['CES0500000003', 'CPIAUCSL'],
    'wage growth': ['CES0500000003', 'ECIWAG'],
    'average hourly earnings': ['CES0500000003', 'AHETPI'],

    # Housing detail
    'apartment rents': ['CUSR0000SEHA', 'CUSR0000SEHC'],
    'home sales': ['EXHOSLUSM495S', 'HSN1F'],
    'median home price': ['MSPUS'],
    'average home price': ['ASPUS'],

    # =========================================================================
    # ZILLOW SERIES (market rents and home values)
    # =========================================================================
    'zillow rent': ['zillow_zori_national', 'zillow_rent_yoy'],
    'market rent': ['zillow_zori_national', 'zillow_rent_yoy'],
    'actual rent': ['zillow_zori_national'],
    'zillow home value': ['zillow_zhvi_national', 'zillow_home_value_yoy'],
    'zillow home prices': ['zillow_zhvi_national', 'zillow_home_value_yoy'],
    'zori': ['zillow_zori_national'],
    'zhvi': ['zillow_zhvi_national'],

    # =========================================================================
    # EIA SERIES (energy data)
    # =========================================================================
    'wti crude': ['eia_wti_crude'],
    'brent crude': ['eia_brent_crude'],
    'crude oil inventories': ['eia_crude_stocks'],
    'oil stocks': ['eia_crude_stocks'],
    'petroleum inventories': ['eia_crude_stocks', 'eia_gasoline_stocks'],
    'diesel prices': ['eia_diesel_retail'],
    'diesel fuel': ['eia_diesel_retail'],
    'henry hub': ['eia_natural_gas_henry_hub'],
    'electricity prices': ['eia_electricity_residential'],
    'electric bill': ['eia_electricity_residential'],
    'oil production': ['eia_crude_production'],

    # =========================================================================
    # ALPHA VANTAGE SERIES (stocks, forex, more economic data)
    # =========================================================================
    'spy': ['av_spy'],
    'qqq': ['av_qqq'],
    'nasdaq 100': ['av_qqq'],
    'tech stocks': ['av_qqq'],
    'dia': ['av_dia'],
    'russell 2000': ['av_iwm'],
    'small cap stocks': ['av_iwm'],
    'eur usd': ['av_eurusd'],
    'euro dollar': ['av_eurusd'],
    'usd jpy': ['av_usdjpy'],
    'dollar yen': ['av_usdjpy'],
    'gbp usd': ['av_gbpusd'],
    'pound dollar': ['av_gbpusd'],
    'dollar index': ['av_dollar_index', 'DTWEXBGS'],
}


def check_direct_mapping(query: str) -> Optional[list]:
    """
    Check if query is asking for specific data that has a direct answer.

    Returns list of series IDs if matched, None otherwise.
    """
    query_lower = query.lower().strip()

    # P0 FIX: Normalize apostrophes and hyphens for better matching
    # "women's" -> "womens", "prime-age" -> "prime age"
    query_lower = query_lower.replace("'s", "s").replace("'", "")
    query_lower = query_lower.replace("-", " ")

    # Remove common question words
    for prefix in ['what is the', 'what is', 'what are the', 'what are',
                   'show me the', 'show me', 'current', 'latest', 'today\'s',
                   'how is the', 'how is', 'how are the', 'how are',
                   'whats the', 'whats happening with', 'what about']:
        if query_lower.startswith(prefix):
            query_lower = query_lower[len(prefix):].strip()

    # Remove trailing question mark and common suffixes
    query_lower = query_lower.rstrip('?').strip()
    for suffix in ['right now', 'today', 'currently', 'now', 'doing', 'looking']:
        if query_lower.endswith(suffix):
            query_lower = query_lower[:-len(suffix)].strip()

    # Direct match
    if query_lower in DIRECT_SERIES_MAPPINGS:
        return DIRECT_SERIES_MAPPINGS[query_lower]

    # Check if query contains any direct mapping key
    # CRITICAL: Sort by length (longest first) so more specific matches win
    # e.g., "rent inflation" should match before "inflation"
    sorted_keys = sorted(DIRECT_SERIES_MAPPINGS.keys(), key=len, reverse=True)
    for key in sorted_keys:
        # Use word boundary matching to avoid partial matches
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, query_lower):
            return DIRECT_SERIES_MAPPINGS[key]

    return None

REASONING_PROMPT = """You are a credible economic analyst (think Jason Furman, Claudia Sahm, or a Fed economist).

A user asked: "{query}"

Think through what data you would NEED to answer this question properly. Reason about what economic CONCEPTS and INDICATORS an analyst would examine.

Return JSON:
{{
    "reasoning": "Brief explanation of your analytical approach (1-2 sentences)",
    "indicators": [
        {{
            "concept": "unemployment rate",
            "why": "Direct measure of labor market slack",
            "search_terms": ["unemployment rate", "civilian unemployment"]
        }},
        {{
            "concept": "job openings",
            "why": "Shows labor demand - tight market has high openings vs unemployed",
            "search_terms": ["job openings total nonfarm", "JOLTS job openings"]
        }}
    ],
    "time_context": "recent" | "historical" | "comparison",
    "display_suggestion": "line chart showing trends" | "compare side by side" | etc.
}}

## SEARCH TERM QUALITY IS CRITICAL

Your search_terms will be used to search FRED. Be SPECIFIC:

GOOD search terms (will find the right series):
- "civilian unemployment rate" → finds UNRATE
- "nonfarm payrolls total" → finds PAYEMS
- "consumer price index all items" → finds CPIAUCSL
- "initial claims unemployment insurance" → finds ICSA
- "30-year fixed mortgage rate" → finds MORTGAGE30US
- "real gross domestic product" → finds GDPC1
- "job openings total nonfarm" → finds JTSJOL

HOUSING & RENT search terms (FRED has these):
- "rent of primary residence" → finds CUSR0000SEHA (rent CPI)
- "owners equivalent rent" → finds CUSR0000SEHC (OER)
- "consumer price index shelter" → finds CUSR0000SAH1 (shelter CPI)
- "housing starts" → finds HOUST
- "case shiller home price" → finds CSUSHPINSA

BAD search terms (too generic or not in FRED):
- "rate" → matches everything
- "unemployment" alone → too broad
- "inflation" alone → too broad
- "jobs" alone → too many matches
- "index" alone → matches everything

## ALTERNATIVE DATA SOURCES (beyond FRED)

For some topics, we have BETTER data from specialized sources. Use these series IDs directly:

**ZILLOW (actual market rents & home values):**
- zillow_zori_national → Zillow Observed Rent Index (actual market rents, not CPI)
- zillow_rent_yoy → Rent growth year-over-year
- zillow_zhvi_national → Zillow Home Value Index
- zillow_home_value_yoy → Home value growth year-over-year
USE THESE when user asks about "actual rents", "market rents", "Zillow", or real-time housing market

**EIA (detailed energy data):**
- eia_wti_crude → WTI crude oil spot price
- eia_brent_crude → Brent crude oil price
- eia_gasoline_retail → Retail gasoline prices
- eia_diesel_retail → Diesel fuel prices
- eia_natural_gas_henry_hub → Henry Hub natural gas
- eia_crude_stocks → US crude oil inventories
- eia_crude_production → US oil production
- eia_electricity_residential → Residential electricity prices
USE THESE for detailed energy analysis beyond what's in FRED

**ALPHA VANTAGE (real-time markets):**
- av_spy → S&P 500 (SPY ETF) - daily
- av_qqq → Nasdaq 100 (QQQ ETF) - daily
- av_dia → Dow Jones (DIA ETF) - daily
- av_iwm → Russell 2000 small caps
- av_treasury_10y → 10-year Treasury yield (daily)
- av_treasury_2y → 2-year Treasury yield (daily)
- av_eurusd → EUR/USD exchange rate
- av_crude_oil → WTI crude oil (daily)
USE THESE for daily market data or when FRED data is too slow

## DEMOGRAPHIC QUERIES

If the query mentions a specific demographic group, your search_terms MUST include that group:
- "Black workers" → search "black unemployment rate", "black employment"
- "Hispanic employment" → search "hispanic unemployment rate", "hispanic labor force"
- "Women in workforce" → search "women unemployment rate", "women labor force"
- "Youth jobs" → search "teenage unemployment", "youth employment 16-24"

NEVER return general population data for demographic-specific queries!

## RULES

1. Think like an economist writing a briefing - what would you NEED to know?
2. Include 2-4 indicators that tell different parts of the story
3. Each indicator should add UNIQUE insight (no redundant measures)
4. search_terms must be specific enough to find the exact series
5. Consider: Is this about levels, changes, or comparisons?

IMPORTANT: Your job is to REASON about what's needed, then provide search terms specific enough to find it.
"""


def call_gemini_reasoning(query: str, retries: int = 2) -> Optional[dict]:
    """
    Call Gemini to reason about what an economist would need.

    Uses Gemini Flash for speed - this is the fast thinking step.
    """
    if not GEMINI_API_KEY:
        return None

    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'

    prompt = REASONING_PROMPT.format(query=query)

    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.3,  # Lower temp for more consistent reasoning
            'maxOutputTokens': 800
        }
    }
    headers = {'Content-Type': 'application/json'}

    for attempt in range(retries):
        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result['candidates'][0]['content']['parts'][0]['text']
                return _extract_json(content)
        except Exception as e:
            if attempt == retries - 1:
                print(f"  Reasoning ERROR: {e}")
                return None
    return None


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response."""
    try:
        # Try direct parse
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


def reason_about_query(query: str, verbose: bool = False) -> dict:
    """
    Main entry point: Reason about what economic data is needed.

    Returns:
        {
            "reasoning": "To assess labor market health, we need...",
            "indicators": [
                {"concept": "...", "why": "...", "search_terms": [...]}
            ],
            "search_terms": ["term1", "term2", ...],  # Flattened for easy use
            "direct_series": ["FEDFUNDS", ...],  # If direct mapping found
            "time_context": "recent",
            "display_suggestion": "..."
        }
    """
    if verbose:
        print(f"  Reasoning about: {query}")

    # FIRST: Check for direct data requests
    # Questions like "What is the Fed funds rate?" should return the actual rate,
    # not factors that influence rates.
    direct_series = check_direct_mapping(query)
    if direct_series:
        if verbose:
            print(f"  Direct mapping found: {direct_series}")
        return {
            "reasoning": f"Showing the requested data directly.",
            "indicators": [],
            "search_terms": [],
            "direct_series": direct_series,
            "time_context": "recent",
            "display_suggestion": "line chart"
        }

    # For analytical questions, use AI reasoning
    result = call_gemini_reasoning(query)

    if not result:
        # Fallback: extract basic search terms from query
        return {
            "reasoning": "Using keyword extraction (AI reasoning unavailable)",
            "indicators": [],
            "search_terms": _extract_keywords(query),
            "time_context": "recent",
            "display_suggestion": "line chart"
        }

    # Flatten search terms from all indicators
    all_search_terms = []
    for indicator in result.get("indicators", []):
        all_search_terms.extend(indicator.get("search_terms", []))

    result["search_terms"] = all_search_terms

    if verbose:
        print(f"  Reasoning: {result.get('reasoning', 'N/A')}")
        print(f"  Indicators: {[i.get('concept') for i in result.get('indicators', [])]}")

    return result


def _extract_keywords(query: str) -> list:
    """Basic keyword extraction as fallback."""
    # Remove common words
    stopwords = {'what', 'is', 'the', 'how', 'are', 'doing', 'with', 'in', 'of',
                 'to', 'a', 'an', 'and', 'or', 'for', 'on', 'at', 'by', 'about',
                 'does', 'do', 'did', 'has', 'have', 'been', 'be', 'will', 'would',
                 'could', 'should', 'can', 'may', 'might', 'current', 'currently',
                 'right', 'now', 'today', 'recently', 'latest', 'recent'}

    words = query.lower().replace('?', '').replace(',', '').split()
    keywords = [w for w in words if w not in stopwords and len(w) > 2]

    return keywords[:4]


# Quick test
if __name__ == "__main__":
    test_queries = [
        "How is the job market doing?",
        "Is inflation coming down?",
        "Are wages keeping up with prices?",
        "What's happening with housing?",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        result = reason_about_query(q, verbose=True)
        print(f"Search terms: {result.get('search_terms', [])}")
