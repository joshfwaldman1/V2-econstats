"""
Health Check Indicators for EconStats.

Provides curated multi-dimensional indicator sets for "How is X doing?" queries.
These queries need 3-5 indicators covering different aspects to give a complete picture.

The Problem:
    "How are megacap US firms doing?" returned consumer sentiment data
    instead of stock market data (SP500) which we actually have.

The Solution:
    Pre-defined indicator sets that map entities to the RIGHT data:
    - megacap_firms → [SP500, corporate_profits, business_investment]
    - labor_market → [unemployment, payrolls, job_openings, claims]
    - economy → [GDP, unemployment, inflation, payrolls]

Usage:
    from core.health_check_indicators import (
        get_health_check_series,
        detect_health_check_entity,
        is_health_check_query,
        HEALTH_CHECK_ENTITIES,
    )

    # Check if query is a health check
    if is_health_check_query("how are megacap firms doing?"):
        entity = detect_health_check_entity(query)  # "megacap_firms"
        series = get_health_check_series(entity)    # ["SP500", "CP", ...]
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class HealthCheckConfig:
    """Configuration for a health check entity."""
    name: str                      # Display name (e.g., "Large US Corporations")
    description: str               # What this entity represents
    primary_series: List[str]      # Main series to fetch (3-5)
    secondary_series: List[str]    # Additional context if needed
    show_yoy: List[bool]           # Which series need YoY transformation
    keywords: List[str]            # Keywords that trigger this entity
    explanation: str               # Why these indicators were chosen


# =============================================================================
# HEALTH CHECK INDICATOR SETS
# =============================================================================
# Each entity has curated indicators covering multiple dimensions.
# The goal is 3-5 indicators that together give a complete picture.
# =============================================================================

HEALTH_CHECK_ENTITIES: Dict[str, HealthCheckConfig] = {
    # =========================================================================
    # CORPORATE / BUSINESS
    # =========================================================================
    "megacap_firms": HealthCheckConfig(
        name="Magnificent 7 / Big Tech",
        description="Performance of megacap tech stocks (Apple, Microsoft, Google, Amazon, Nvidia, Meta, Tesla)",
        # Alpha Vantage series for real-time daily data
        primary_series=["av_qqq", "av_xlk", "av_nvda", "av_aapl", "av_msft"],
        secondary_series=["av_spy", "av_googl", "av_amzn", "av_meta", "av_tsla"],
        show_yoy=[False, False, False, False, False],  # Stock prices as levels
        keywords=[
            # Magnificent 7 / Big Tech (primary use case)
            "mag7", "mag 7", "magnificent 7", "magnificent seven", "big tech",
            "faang", "tech stocks", "tech giants",
            # General megacap
            "megacap", "mega cap", "large cap", "big companies", "large companies",
            "corporations", "corporate", "big firms", "large firms", "us firms",
            "american companies", "fortune 500", "blue chip",
        ],
        explanation="Using Alpha Vantage for real-time daily data. QQQ (NASDAQ-100) is ~50% Mag7 by weight. XLK is the tech sector ETF. Showing top Mag7 stocks: NVDA (AI leader), AAPL, MSFT. The Mag7 make up ~30% of S&P 500."
    ),

    "small_business": HealthCheckConfig(
        name="Small Business",
        description="Health of small and medium enterprises",
        primary_series=["BUSLOANS", "DRTSCLCC", "RSXFS", "ICSA"],
        secondary_series=["FEDFUNDS", "MPRIME"],
        show_yoy=[True, False, True, False],
        keywords=[
            "small business", "small businesses", "sme", "smb", "entrepreneurs",
            "mom and pop", "main street", "local business",
        ],
        explanation="Business loans show credit access; lending standards show credit availability; retail sales proxy demand; initial claims show labor stress."
    ),

    # =========================================================================
    # LABOR MARKET
    # =========================================================================
    "labor_market": HealthCheckConfig(
        name="Labor Market",
        description="Overall job market health",
        primary_series=["UNRATE", "PAYEMS", "JTSJOL", "ICSA"],
        secondary_series=["CIVPART", "CES0500000003", "U6RATE"],
        show_yoy=[False, False, False, False],  # Rates and levels, not YoY
        keywords=[
            "labor market", "job market", "jobs", "employment", "workers",
            "workforce", "hiring", "layoffs",
        ],
        explanation="Unemployment rate shows slack; payrolls show job creation; JOLTS shows demand; initial claims show emerging weakness."
    ),

    "black_workers": HealthCheckConfig(
        name="Black Workers",
        description="Labor market outcomes for Black Americans",
        primary_series=["LNS14000006", "LNS11300006", "LNS12300006"],
        secondary_series=["UNRATE", "LNS14000003"],
        show_yoy=[False, False, False],
        keywords=[
            "black workers", "black employment", "black unemployment",
            "african american workers", "african american employment",
            "black in the labor", "black labor market", "black doing",
            "african american in the labor", "black americans",
        ],
        explanation="Black unemployment, participation, and employment-population ratio compared to overall rate for context."
    ),

    "hispanic_workers": HealthCheckConfig(
        name="Hispanic Workers",
        description="Labor market outcomes for Hispanic/Latino Americans",
        primary_series=["LNS14000009", "LNS11300009", "LNS12300009"],
        secondary_series=["UNRATE"],
        show_yoy=[False, False, False],
        keywords=[
            "hispanic workers", "latino workers", "hispanic employment",
            "latino employment", "hispanic unemployment",
            "hispanic in the labor", "hispanic labor market", "hispanic doing",
            "latino in the labor", "latino labor market", "latino doing",
            "hispanic americans", "latino americans",
        ],
        explanation="Hispanic unemployment, participation, and employment-population ratio compared to overall rate."
    ),

    "women_workers": HealthCheckConfig(
        name="Women in the Workforce",
        description="Labor market outcomes for women",
        primary_series=["LNS14000002", "LNS11300002", "LNS12300002"],
        secondary_series=["LNS14000001", "UNRATE"],
        show_yoy=[False, False, False],
        keywords=[
            "women workers", "female workers", "women employment",
            "women in workforce", "working women", "gender gap",
            "women in the labor", "women labor market", "women doing",
            "women in the job", "women jobs",
        ],
        explanation="Women's unemployment, participation, and employment-population ratio vs men and overall."
    ),

    # =========================================================================
    # ECONOMY OVERALL
    # =========================================================================
    "economy": HealthCheckConfig(
        name="US Economy",
        description="Overall economic health",
        primary_series=["A191RO1Q156NBEA", "UNRATE", "CPIAUCSL", "PAYEMS"],
        secondary_series=["UMCSENT", "FEDFUNDS", "T10Y2Y"],
        show_yoy=[False, False, True, False],  # GDP already YoY, CPI needs YoY
        keywords=[
            "economy", "economic", "us economy", "american economy",
            "economic health", "economic conditions", "how is the economy",
        ],
        explanation="The 'Four Horsemen': GDP growth, unemployment, inflation, and job creation together capture overall economic health."
    ),

    # =========================================================================
    # CONSUMERS
    # =========================================================================
    "consumers": HealthCheckConfig(
        name="US Consumers",
        description="Consumer financial health and spending",
        primary_series=["UMCSENT", "RSXFS", "DSPIC96", "PSAVERT"],
        secondary_series=["PCE", "TOTALSL"],
        show_yoy=[False, True, True, False],
        keywords=[
            "consumers", "consumer", "households", "consumer spending",
            "consumer health", "american consumers", "household finances",
        ],
        explanation="Sentiment shows confidence; retail sales shows spending; real income shows purchasing power; savings rate shows financial cushion."
    ),

    # =========================================================================
    # HOUSING
    # =========================================================================
    "housing_market": HealthCheckConfig(
        name="Housing Market",
        description="Residential real estate conditions",
        primary_series=["CSUSHPINSA", "HOUST", "MORTGAGE30US", "EXHOSLUSM495S"],
        secondary_series=["PERMIT", "MSPUS"],
        show_yoy=[True, False, False, False],  # Home prices as YoY
        keywords=[
            "housing", "housing market", "real estate", "home prices",
            "homes", "residential", "homeowners",
        ],
        explanation="Case-Shiller shows prices; housing starts shows construction; mortgage rates show affordability; existing sales shows activity."
    ),

    "renters": HealthCheckConfig(
        name="Rental Market",
        description="Conditions for renters",
        primary_series=["CUSR0000SAH1", "CPIHOSSL", "DSPIC96", "RRVRUSQ156N"],
        secondary_series=[],
        show_yoy=[True, True, True, False],
        keywords=[
            "renters", "renting", "rent", "rental market", "tenants",
            "apartment", "rent prices",
        ],
        explanation="Shelter CPI and rent CPI show rent inflation; real income shows affordability; rental vacancy shows supply."
    ),

    # =========================================================================
    # INFLATION
    # =========================================================================
    "inflation": HealthCheckConfig(
        name="Inflation",
        description="Price pressures in the economy",
        primary_series=["CPIAUCSL", "PCEPILFE", "CUSR0000SAH1", "T5YIE"],
        secondary_series=["CPILFESL", "PCEPI"],
        show_yoy=[True, True, True, False],  # All as YoY except expectations
        keywords=[
            "inflation", "prices", "cost of living", "price pressures",
            "cpi", "pce", "price increases",
        ],
        explanation="Headline CPI, core PCE (Fed's preferred), shelter (biggest component), and market expectations give complete inflation picture."
    ),

    # =========================================================================
    # SECTORS / INDUSTRIES
    # =========================================================================
    "manufacturing": HealthCheckConfig(
        name="Manufacturing Sector",
        description="US manufacturing and industrial activity",
        primary_series=["INDPRO", "MANEMP", "NEWORDER", "TCU"],
        secondary_series=["IPMAN", "DGORDER"],
        show_yoy=[True, False, True, False],
        keywords=[
            "manufacturing", "factories", "industrial", "factory",
            "manufacturers", "made in america", "industrial production",
        ],
        explanation="Industrial production shows output; manufacturing employment shows jobs; new orders shows demand; capacity utilization shows slack."
    ),

    "tech_sector": HealthCheckConfig(
        name="Technology Sector",
        description="Tech industry health",
        primary_series=["NASDAQCOM", "USINFO", "DGORDER", "ICSA"],
        secondary_series=["INDPRO"],
        show_yoy=[False, False, True, False],
        keywords=[
            "tech", "technology", "tech sector", "software", "silicon valley",
            "tech industry", "tech companies",
        ],
        explanation="NASDAQ shows tech valuations; information sector employment; durable goods orders (includes tech); initial claims for layoffs."
    ),

    "restaurants": HealthCheckConfig(
        name="Restaurant Industry",
        description="Food service and hospitality",
        primary_series=["CES7072200001", "RSFSDP", "CUSR0000SEFV", "UMCSENT"],
        secondary_series=["USLAH"],
        show_yoy=[False, True, True, False],
        keywords=[
            "restaurants", "dining", "food service", "hospitality",
            "bars", "eateries",
        ],
        explanation="Food services employment, spending, prices, and consumer sentiment (drives discretionary dining)."
    ),

    # =========================================================================
    # FINANCIAL / MONETARY
    # =========================================================================
    "fed_policy": HealthCheckConfig(
        name="Federal Reserve Policy",
        description="Monetary policy stance and expectations",
        primary_series=["FEDFUNDS", "DGS10", "DGS2", "T10Y2Y"],
        secondary_series=["MORTGAGE30US", "BAMLH0A0HYM2"],
        show_yoy=[False, False, False, False],
        keywords=[
            "fed", "federal reserve", "monetary policy", "interest rates",
            "fomc", "powell", "rate cuts", "rate hikes",
        ],
        explanation="Fed funds rate shows current policy; 10Y and 2Y treasuries show term structure; 10Y-2Y spread shows yield curve inversion risk."
    ),

    "recession_risk": HealthCheckConfig(
        name="Recession Risk",
        description="Indicators of potential economic downturn",
        primary_series=["SAHMREALTIME", "T10Y2Y", "UMCSENT", "ICSA"],
        secondary_series=["USREC", "INDPRO"],
        show_yoy=[False, False, False, False],
        keywords=[
            "recession", "recession risk", "downturn", "economic slowdown",
            "hard landing", "soft landing", "recession coming",
        ],
        explanation="Sahm Rule, yield curve, consumer sentiment, and initial claims are leading recession indicators."
    ),
}


# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================

def is_health_check_query(query: str) -> bool:
    """
    Detect if a query is asking about the health/status of something.

    Health check queries typically start with:
    - "How is X doing?"
    - "How are X?"
    - "What about X?"
    - "State of X"
    - "Is X healthy/struggling?"

    Args:
        query: User's query string

    Returns:
        True if this looks like a health check query
    """
    query_lower = query.lower().strip()

    # Exclude comparison queries — these should go to the comparison router,
    # not the health check handler. Without this guard, "How is US growth
    # compared to Europe?" matches the broad "^how (is|are) .+\??$" pattern
    # and returns US-only health check data instead of a US vs Europe comparison.
    comparison_keywords = [
        "compared to", "vs", "versus", "compare", "comparison",
        "relative to", "against", "between",
    ]
    if any(kw in query_lower for kw in comparison_keywords):
        return False

    health_check_patterns = [
        r"^how (is|are) .+ doing\??$",
        r"^how('s| is) .+ (looking|performing|faring)\??$",
        r"^what about .+\??$",
        r"^(state|status|health|condition) of .+",
        r"^how (is|are) .+ (right now|today|currently|lately)\??$",
        r"^is .+ (doing )?(good|bad|okay|well|poorly|healthy|struggling)\??$",
        r"^are .+ (doing )?(good|bad|okay|well|poorly|healthy|struggling)\??$",
        r".+ outlook\??$",
        r"^how .+ (holding up|looking)\??$",
        # Simple "how is/are X?" patterns - catch queries like "how is the economy?" or "how are consumers?"
        r"^how (is|are) the .+\??$",
        r"^how (is|are) .+\??$",  # Catch "how are consumers?" without "the"
        r"^how('s| is) .+\??$",
    ]

    for pattern in health_check_patterns:
        if re.search(pattern, query_lower):
            return True

    return False


def detect_health_check_entity(query: str) -> Optional[str]:
    """
    Detect which entity the health check query is asking about.

    Args:
        query: User's query string

    Returns:
        Entity key (e.g., "megacap_firms", "labor_market") or None if not detected
    """
    query_lower = query.lower()

    # Score each entity by keyword matches
    best_match = None
    best_score = 0

    for entity_key, config in HEALTH_CHECK_ENTITIES.items():
        score = 0
        for keyword in config.keywords:
            if keyword in query_lower:
                # Longer keywords get higher scores (more specific)
                score += len(keyword.split())

        if score > best_score:
            best_score = score
            best_match = entity_key

    # Require at least one keyword match
    if best_score > 0:
        return best_match

    # Default to "economy" for generic health check queries
    if is_health_check_query(query):
        return "economy"

    return None


def get_health_check_series(entity: str) -> Tuple[List[str], List[bool], str]:
    """
    Get the series to fetch for a health check entity.

    Args:
        entity: Entity key (e.g., "megacap_firms")

    Returns:
        Tuple of (series_ids, show_yoy_flags, explanation)
    """
    if entity not in HEALTH_CHECK_ENTITIES:
        # Fallback to economy
        entity = "economy"

    config = HEALTH_CHECK_ENTITIES[entity]
    return (config.primary_series, config.show_yoy, config.explanation)


def get_health_check_config(entity: str) -> Optional[HealthCheckConfig]:
    """
    Get the full configuration for a health check entity.

    Args:
        entity: Entity key

    Returns:
        HealthCheckConfig or None if not found
    """
    return HEALTH_CHECK_ENTITIES.get(entity)


def list_health_check_entities() -> List[str]:
    """Return list of all available health check entities."""
    return list(HEALTH_CHECK_ENTITIES.keys())


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def route_health_check_query(query: str) -> Optional[Dict]:
    """
    Full routing for health check queries.

    This is the main integration point - call this from the query router.

    Args:
        query: User's query string

    Returns:
        Dict with routing info or None if not a health check query

    Example:
        result = route_health_check_query("how are megacap firms doing?")
        # Returns:
        # {
        #     "is_health_check": True,
        #     "entity": "megacap_firms",
        #     "entity_name": "Large US Corporations",
        #     "series": ["SP500", "NASDAQCOM", "CP", "INDPRO"],
        #     "show_yoy": [False, False, True, True],
        #     "explanation": "Stock indices show valuation...",
        # }
    """
    if not is_health_check_query(query):
        return None

    entity = detect_health_check_entity(query)
    if not entity:
        return None

    config = HEALTH_CHECK_ENTITIES[entity]

    return {
        "is_health_check": True,
        "entity": entity,
        "entity_name": config.name,
        "series": config.primary_series,
        "secondary_series": config.secondary_series,
        "show_yoy": config.show_yoy,
        "explanation": config.explanation,
        "description": config.description,
    }


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test queries
    test_queries = [
        "how are megacap US firms doing?",
        "how is the labor market?",
        "what about inflation?",
        "how are consumers doing?",
        "how is the housing market?",
        "how are black workers doing?",
        "state of the economy",
        "how is manufacturing?",
        "are small businesses struggling?",
        "how's the fed policy looking?",
    ]

    print("Health Check Query Detection Tests\n" + "=" * 50)

    for query in test_queries:
        result = route_health_check_query(query)
        if result:
            print(f"\nQuery: {query}")
            print(f"  Entity: {result['entity']} ({result['entity_name']})")
            print(f"  Series: {result['series']}")
            print(f"  Explanation: {result['explanation'][:80]}...")
        else:
            print(f"\nQuery: {query}")
            print(f"  Not detected as health check")
