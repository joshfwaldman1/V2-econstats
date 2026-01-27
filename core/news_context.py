"""
Fetch economic news context from trusted sources.

Source hierarchy (in order of trust):
1. Federal Reserve banks (FRED, regional Feds)
2. Government agencies (BLS, BEA, Treasury)
3. Academic/research economists
4. Major financial institutions (research arms)
5. Quality financial press

Uses SerpAPI for web search with source filtering.
"""

import json
import os
from datetime import datetime
from typing import Optional, List, Dict
from urllib.request import urlopen, Request
from urllib.parse import urlencode

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

# =============================================================================
# TRUSTED SOURCE HIERARCHY
# =============================================================================

# Tier 1: Federal Reserve (highest trust)
TIER1_FED = [
    'federalreserve.gov',
    'fred.stlouisfed.org',
    'stlouisfed.org',
    'newyorkfed.org',
    'atlantafed.org',
    'chicagofed.org',
    'clevelandfed.org',
    'dallasfed.org',
    'kansascityfed.org',
    'minneapolisfed.org',
    'philadelphiafed.org',
    'richmondfed.org',
    'sanfranciscofed.org',
    'bostonfed.org',
]

# Tier 2: Government agencies
TIER2_GOVT = [
    'bls.gov',           # Bureau of Labor Statistics
    'bea.gov',           # Bureau of Economic Analysis
    'treasury.gov',
    'census.gov',
    'whitehouse.gov',
    'cbo.gov',           # Congressional Budget Office
    'imf.org',
    'worldbank.org',
    'oecd.org',
]

# Tier 3: Academic economists and research
TIER3_ACADEMIC = [
    'nber.org',          # National Bureau of Economic Research
    'brookings.edu',
    'piie.com',          # Peterson Institute
    'aei.org',
    'cato.org',
    'epi.org',           # Economic Policy Institute
    'frbsf.org',
    'econbrowser.com',   # James Hamilton, Menzie Chinn
]

# Tier 4: Financial institutions (research)
TIER4_FINANCE = [
    'gsam.com',          # Goldman Sachs
    'jpmorgan.com',
    'morganstanley.com',
    'blackrock.com',
    'bridgewater.com',
    'pimco.com',
    'vanguard.com',
    'fidelity.com',
]

# Tier 5: Quality financial press
TIER5_PRESS = [
    'wsj.com',
    'ft.com',
    'bloomberg.com',
    'reuters.com',
    'economist.com',
    'barrons.com',
    'marketwatch.com',
]

# All trusted sources combined
ALL_TRUSTED_SOURCES = TIER1_FED + TIER2_GOVT + TIER3_ACADEMIC + TIER4_FINANCE + TIER5_PRESS

# Source tier for scoring
def get_source_tier(url: str) -> int:
    """Return tier (1-5) for a source, or 6 for untrusted."""
    url_lower = url.lower()
    for domain in TIER1_FED:
        if domain in url_lower:
            return 1
    for domain in TIER2_GOVT:
        if domain in url_lower:
            return 2
    for domain in TIER3_ACADEMIC:
        if domain in url_lower:
            return 3
    for domain in TIER4_FINANCE:
        if domain in url_lower:
            return 4
    for domain in TIER5_PRESS:
        if domain in url_lower:
            return 5
    return 6  # Untrusted


# =============================================================================
# TOPIC MAPPINGS
# =============================================================================

TOPIC_SEARCH_QUERIES = {
    'inflation': 'CPI inflation report Federal Reserve',
    'fed': 'FOMC Federal Reserve interest rate decision',
    'unemployment': 'jobs report employment BLS',
    'gdp': 'GDP growth economic output BEA',
    'recession': 'recession risk economic outlook Federal Reserve',
    'housing': 'housing market mortgage rates',
    'economy': 'US economy outlook Federal Reserve',
    'rates': 'interest rates Treasury yields Federal Reserve',
}


def extract_topic(query: str) -> str:
    """Extract the main economic topic from a query."""
    query_lower = query.lower()

    if any(w in query_lower for w in ['inflation', 'cpi', 'prices', 'cost of living']):
        return 'inflation'
    if any(w in query_lower for w in ['fed', 'fomc', 'powell', 'interest rate', 'rate cut', 'rate hike']):
        return 'fed'
    if any(w in query_lower for w in ['unemployment', 'jobless', 'labor market', 'jobs', 'payroll']):
        return 'unemployment'
    if any(w in query_lower for w in ['gdp', 'growth', 'output']):
        return 'gdp'
    if any(w in query_lower for w in ['recession', 'downturn', 'contraction', 'soft landing', 'hard landing']):
        return 'recession'
    if any(w in query_lower for w in ['housing', 'home', 'mortgage', 'rent']):
        return 'housing'
    if any(w in query_lower for w in ['rate', 'yield', 'treasury', 'bond']):
        return 'rates'

    return 'economy'


# =============================================================================
# SERPAPI SEARCH
# =============================================================================

def search_news(query: str, num_results: int = 10) -> List[Dict]:
    """
    Search for news using SerpAPI, filtered to trusted sources.

    Returns list of {title, link, snippet, source, tier} dicts.
    """
    if not SERPAPI_KEY:
        return []

    # Build site: filter for trusted sources (top tiers)
    priority_sites = TIER1_FED + TIER2_GOVT + TIER3_ACADEMIC[:3]
    site_filter = ' OR '.join([f'site:{s}' for s in priority_sites[:10]])

    search_query = f'{query} ({site_filter})'

    params = {
        'q': search_query,
        'api_key': SERPAPI_KEY,
        'engine': 'google',
        'num': num_results,
        'tbm': 'nws',  # News search
    }

    url = f'https://serpapi.com/search?{urlencode(params)}'

    try:
        req = Request(url, headers={'Accept': 'application/json'})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            results = []
            for item in data.get('news_results', [])[:num_results]:
                link = item.get('link', '')
                results.append({
                    'title': item.get('title', ''),
                    'link': link,
                    'snippet': item.get('snippet', ''),
                    'source': item.get('source', ''),
                    'date': item.get('date', ''),
                    'tier': get_source_tier(link),
                })

            # Sort by tier (most trusted first)
            results.sort(key=lambda x: x['tier'])
            return results

    except Exception as e:
        print(f'[NewsContext] SerpAPI error: {e}')
        return []


def search_general(query: str, num_results: int = 5) -> List[Dict]:
    """
    General web search (not just news) for Fed statements, research papers, etc.
    """
    if not SERPAPI_KEY:
        return []

    params = {
        'q': query,
        'api_key': SERPAPI_KEY,
        'engine': 'google',
        'num': num_results,
    }

    url = f'https://serpapi.com/search?{urlencode(params)}'

    try:
        req = Request(url, headers={'Accept': 'application/json'})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            results = []
            for item in data.get('organic_results', [])[:num_results]:
                link = item.get('link', '')
                tier = get_source_tier(link)
                # Only include trusted sources
                if tier <= 5:
                    results.append({
                        'title': item.get('title', ''),
                        'link': link,
                        'snippet': item.get('snippet', ''),
                        'tier': tier,
                    })

            results.sort(key=lambda x: x['tier'])
            return results

    except Exception as e:
        print(f'[NewsContext] SerpAPI error: {e}')
        return []


# =============================================================================
# CONTEXT GENERATION
# =============================================================================

def get_economic_context(query: str) -> str:
    """
    Get economic context for a query from trusted sources.

    Searches for recent news and Fed statements, filters to trusted sources,
    and formats for inclusion in the LLM prompt.
    """
    topic = extract_topic(query)
    search_query = TOPIC_SEARCH_QUERIES.get(topic, TOPIC_SEARCH_QUERIES['economy'])

    context_parts = []

    # Search news
    news = search_news(search_query, num_results=5)
    if news:
        news_lines = []
        for item in news[:3]:  # Top 3 results
            tier_label = {1: 'Fed', 2: 'Govt', 3: 'Research', 4: 'Finance', 5: 'Press'}.get(item['tier'], '')
            news_lines.append(f"• [{tier_label}] {item['title']}: {item['snippet'][:150]}...")

        if news_lines:
            context_parts.append("RECENT NEWS (from trusted sources):\n" + '\n'.join(news_lines))

    # For Fed-related queries, also search for FOMC statements
    if topic in ['fed', 'rates', 'inflation', 'economy']:
        fed_results = search_general('site:federalreserve.gov FOMC statement 2024 2025', num_results=3)
        if fed_results:
            fed_lines = [f"• {item['title']}" for item in fed_results[:2]]
            if fed_lines:
                context_parts.append("FED COMMUNICATIONS:\n" + '\n'.join(fed_lines))

    # Add timestamp
    if context_parts:
        current_date = datetime.now().strftime("%B %d, %Y")
        return f"[Context as of {current_date}]\n\n" + '\n\n'.join(context_parts)

    # Fallback to static context if search fails
    return get_static_context(topic)


def get_static_context(topic: str) -> str:
    """Fallback static context when search is unavailable."""

    STATIC_CONTEXT = {
        'inflation': """[Static context - search unavailable]
• CPI has fallen from 9% peak (June 2022) to ~2.7%
• Shelter inflation remains sticky at ~4-5%
• Fed has begun cutting rates but remains data-dependent""",

        'fed': """[Static context - search unavailable]
• Fed funds rate: 4.25-4.50% (after cutting 100bps in late 2024)
• Stance: Gradual easing, data-dependent
• Watching: Core PCE, labor market, inflation expectations""",

        'unemployment': """[Static context - search unavailable]
• Unemployment ~4.1%, up from 3.4% low
• Job gains ~150-200K/month
• Labor market rebalancing without major layoffs""",

        'economy': """[Static context - search unavailable]
• GDP growth ~2.5-3% annualized
• Soft landing scenario playing out
• Fed cutting rates as inflation moderates""",
    }

    return STATIC_CONTEXT.get(topic, STATIC_CONTEXT['economy'])


def get_fed_context() -> str:
    """Get current Fed policy context from search."""
    results = search_general('site:federalreserve.gov FOMC statement federal funds rate', num_results=3)
    if results:
        return '\n'.join([f"• {r['title']}" for r in results])
    return "Fed context unavailable"
