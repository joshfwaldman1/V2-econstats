"""
Smart Query Router for EconStats.

Handles complex queries that span multiple data sources:
- Domestic comparison queries (Black unemployment vs overall, inflation vs wages)
- International comparison queries (US vs Eurozone)
- Multi-region queries
- Indicator extraction

Uses a hybrid approach:
1. Rule-based detection for common patterns
2. LLM fallback for ambiguous queries
"""

import re
from typing import Optional, List, Dict, Tuple

# Region mappings to data sources
REGIONS = {
    # US - use FRED
    "us": {"source": "fred", "name": "United States", "aliases": ["usa", "america", "american", "united states", "u.s.", "u.s"]},

    # International - use DBnomics
    "eurozone": {"source": "dbnomics", "name": "Eurozone", "aliases": ["euro area", "euro zone", "eu", "europe", "european"]},
    "uk": {"source": "dbnomics", "name": "United Kingdom", "aliases": ["britain", "british", "england", "united kingdom"]},
    "japan": {"source": "dbnomics", "name": "Japan", "aliases": ["japanese"]},
    "china": {"source": "dbnomics", "name": "China", "aliases": ["chinese", "prc"]},
    "germany": {"source": "dbnomics", "name": "Germany", "aliases": ["german"]},
    "canada": {"source": "dbnomics", "name": "Canada", "aliases": ["canadian"]},
    "mexico": {"source": "dbnomics", "name": "Mexico", "aliases": ["mexican"]},
    "india": {"source": "dbnomics", "name": "India", "aliases": ["indian"]},
    "brazil": {"source": "dbnomics", "name": "Brazil", "aliases": ["brazilian"]},
}

# Indicator mappings to series
# CRITICAL: Metadata ensures apples-to-apples comparisons
#   - measure_type: "real" or "nominal" or "rate"
#   - change_type: "yoy", "qoq", "level"
#   - transform: what to do with FRED level data ("yoy_pct" = calculate YoY % change)
INDICATORS = {
    "gdp": {
        "keywords": ["gdp", "growth", "economic growth", "output", "economy"],
        "fred_series": ["GDPC1"],  # Real GDP (level in billions)
        # FRED metadata - GDPC1 is a level, must transform to YoY growth
        "fred_metadata": {
            "GDPC1": {
                "measure_type": "real",
                "change_type": "level",  # Raw data is level
                "transform": "yoy_pct",  # Transform to YoY % change for comparison
                "display_as": "yoy",     # After transform, it's YoY growth
            }
        },
        "dbnomics_series": {
            "eurozone": "eurozone_gdp",
            "uk": "uk_gdp",
            "japan": "japan_gdp",
            "china": "china_gdp",
            "germany": "germany_gdp",
            "canada": "canada_gdp",
            "mexico": "mexico_gdp",
            "india": "india_gdp",
            "brazil": "brazil_gdp",
        },
        # All DBnomics GDP series are already YoY real growth rates
        "comparison_type": "yoy_real",
    },
    "inflation": {
        "keywords": ["inflation", "cpi", "prices", "consumer prices"],
        "fred_series": ["CPIAUCSL"],  # CPI (level, index)
        "fred_metadata": {
            "CPIAUCSL": {
                "measure_type": "index",
                "change_type": "level",
                "transform": "yoy_pct",  # Transform to YoY % change
                "display_as": "yoy",
            }
        },
        "dbnomics_series": {
            "eurozone": "eurozone_inflation",
            "uk": "uk_inflation",
            "japan": "japan_inflation",
            "china": "china_inflation",
        },
        "comparison_type": "yoy_rate",
    },
    "unemployment": {
        "keywords": ["unemployment", "jobless", "jobs"],
        "fred_series": ["UNRATE"],  # Already a rate level
        "fred_metadata": {
            "UNRATE": {
                "measure_type": "rate",
                "change_type": "level",
                "transform": None,  # No transform needed, display as-is
                "display_as": "level",
            }
        },
        "dbnomics_series": {
            "eurozone": "eurozone_unemployment",
            "germany": "germany_unemployment",
        },
        "comparison_type": "level_rate",
    },
    "rates": {
        "keywords": ["interest rate", "rates", "fed", "central bank", "policy rate"],
        "fred_series": ["FEDFUNDS"],  # Already a rate level
        "fred_metadata": {
            "FEDFUNDS": {
                "measure_type": "rate",
                "change_type": "level",
                "transform": None,
                "display_as": "level",
            }
        },
        "dbnomics_series": {
            "eurozone": "ecb_rate",
            # Note: UK Bank rate not reliably available via DBnomics
        },
        "comparison_type": "level_rate",
    },
}

# Comparison keywords
COMPARISON_KEYWORDS = [
    "compared to", "vs", "versus", "compare", "comparison",
    "relative to", "against", "and", "between", "than"
]


# =============================================================================
# DOMESTIC COMPARISON PATTERNS
# =============================================================================
# These map common domestic comparison queries to pairs of FRED series.
# Each pattern has:
#   - keywords: list of terms that trigger this comparison
#   - series: list of FRED series IDs to return
#   - explanation: human-readable description
#   - units_compatible: whether series can be displayed on same Y-axis
# =============================================================================

DOMESTIC_COMPARISONS = [
    # === UNEMPLOYMENT COMPARISONS ===
    {
        "keywords": [
            "black unemployment vs overall", "black vs overall unemployment",
            "black unemployment versus overall", "black vs total unemployment",
            "black unemployment compared to overall", "black unemployment rate vs overall",
            "african american unemployment vs overall", "black vs white unemployment",
            "black unemployment and overall", "compare black unemployment"
        ],
        "series": ["LNS14000006", "UNRATE"],  # Black unemployment, Overall unemployment
        "explanation": "Comparing Black unemployment rate to overall unemployment rate.",
        "units_compatible": True,  # Both are percentages
    },
    {
        "keywords": [
            "hispanic unemployment vs overall", "hispanic vs overall unemployment",
            "latino unemployment vs overall", "hispanic unemployment rate vs overall",
            "hispanic vs total unemployment", "hispanic unemployment and overall"
        ],
        "series": ["LNS14000009", "UNRATE"],  # Hispanic unemployment, Overall
        "explanation": "Comparing Hispanic unemployment rate to overall unemployment rate.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "women unemployment vs men", "women vs men unemployment",
            "female unemployment vs male", "female vs male unemployment",
            "men vs women unemployment", "male vs female unemployment",
            "unemployment by gender", "unemployment men women"
        ],
        "series": ["LNS14000002", "LNS14000001"],  # Women, Men
        "explanation": "Comparing unemployment rates by gender.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "youth unemployment vs overall", "youth vs overall unemployment",
            "teen unemployment vs overall", "young unemployment vs overall",
            "youth unemployment rate vs", "teen unemployment rate vs"
        ],
        "series": ["LNS14000012", "UNRATE"],  # 16-19 year olds, Overall
        "explanation": "Comparing youth unemployment rate to overall unemployment rate.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "immigrant unemployment vs native", "foreign born unemployment vs native",
            "immigrant vs native born unemployment", "foreign born vs native unemployment",
            "immigrant unemployment rate vs"
        ],
        "series": ["LNU04073395", "LNU04073413"],  # Foreign born, Native born
        "explanation": "Comparing foreign-born and native-born unemployment rates.",
        "units_compatible": True,
    },

    # === INFLATION COMPARISONS ===
    {
        "keywords": [
            "inflation vs wage", "inflation vs wages", "inflation versus wages",
            "inflation and wage growth", "wages vs inflation", "wage growth vs inflation",
            "wages and inflation", "inflation compared to wages", "real wage",
            "wage growth and inflation", "wages versus inflation", "inflation wages"
        ],
        "series": ["CPIAUCSL", "CES0500000003"],  # CPI, Average Hourly Earnings
        "explanation": "Comparing inflation (CPI) to wage growth (Average Hourly Earnings).",
        "units_compatible": False,  # Both YoY % but typically shown separately
        "show_yoy": True,  # Both need YoY transformation
    },
    {
        "keywords": [
            "core vs headline inflation", "core inflation vs headline",
            "core vs total inflation", "headline vs core inflation",
            "headline inflation vs core", "core cpi vs headline cpi",
            "core and headline inflation", "compare core headline inflation"
        ],
        "series": ["CPILFESL", "CPIAUCSL"],  # Core CPI, Headline CPI
        "explanation": "Comparing core inflation (excluding food and energy) to headline inflation.",
        "units_compatible": True,  # Both are indexes, show YoY %
        "show_yoy": True,
    },
    {
        "keywords": [
            "cpi vs pce", "cpi versus pce", "cpi and pce inflation",
            "pce vs cpi", "pce inflation vs cpi", "compare cpi pce"
        ],
        "series": ["CPIAUCSL", "PCEPI"],  # CPI, PCE
        "explanation": "Comparing CPI and PCE inflation measures.",
        "units_compatible": True,
        "show_yoy": True,
    },
    {
        "keywords": [
            "food vs shelter inflation", "food inflation vs shelter",
            "housing vs food inflation", "rent vs food inflation",
            "shelter inflation vs food"
        ],
        "series": ["CUSR0000SAH1", "CUSR0000SAF11"],  # Shelter, Food at home
        "explanation": "Comparing shelter inflation to food inflation.",
        "units_compatible": True,
        "show_yoy": True,
    },

    # === LABOR MARKET COMPARISONS ===
    {
        "keywords": [
            "job openings vs unemployed", "job openings vs unemployment",
            "job openings versus unemployment", "jolts vs unemployment",
            "openings vs unemployed", "vacancies vs unemployed",
            "job openings and unemployed", "openings per unemployed"
        ],
        "series": ["JTSJOL", "LNS13000000"],  # Job openings (JOLTS), Unemployment Level
        "explanation": "Comparing job openings to number of unemployed persons.",
        "units_compatible": True,  # Both are thousands of persons
    },
    {
        "keywords": [
            "quits vs layoffs", "quits rate vs layoffs",
            "quits versus layoffs", "layoffs vs quits",
            "quit rate vs layoff rate"
        ],
        "series": ["JTSQUR", "JTSLDR"],  # Quits rate, Layoffs rate (both as rates for apples-to-apples)
        "explanation": "Comparing quits rate to layoffs rate from JOLTS data.",
        "units_compatible": True,  # Both are rates (percent)
    },
    {
        "keywords": [
            "hires vs separations", "hiring vs separations",
            "hires rate vs separations", "new hires vs quits"
        ],
        "series": ["JTSHIR", "JTSTSR"],  # Hires rate, Total separations rate (both as rates)
        "explanation": "Comparing hires rate to total separations rate.",
        "units_compatible": True,  # Both are rates (percent)
    },
    {
        "keywords": [
            "initial claims vs continuing claims", "initial vs continuing claims",
            "new claims vs continuing", "jobless claims initial vs continuing"
        ],
        "series": ["ICSA", "CCSA"],  # Initial claims, Continuing claims
        "explanation": "Comparing initial jobless claims to continuing claims.",
        "units_compatible": False,  # Different scales (weekly vs total)
    },

    # === SECTOR COMPARISONS ===
    {
        "keywords": [
            "manufacturing vs services", "manufacturing vs service",
            "manufacturing employment vs services", "goods vs services employment",
            "factory jobs vs service jobs"
        ],
        "series": ["MANEMP", "USPBS"],  # Manufacturing, Professional/Business Services
        "explanation": "Comparing manufacturing employment to professional services employment.",
        "units_compatible": True,  # Both thousands of jobs
    },
    {
        "keywords": [
            "construction vs manufacturing", "construction jobs vs manufacturing",
            "construction employment vs manufacturing"
        ],
        "series": ["USCONS", "MANEMP"],  # Construction, Manufacturing
        "explanation": "Comparing construction employment to manufacturing employment.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "healthcare vs manufacturing", "healthcare jobs vs factory",
            "health services vs manufacturing"
        ],
        "series": ["USEHS", "MANEMP"],  # Education & Health, Manufacturing
        "explanation": "Comparing healthcare/education employment to manufacturing employment.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "tech vs manufacturing", "tech jobs vs manufacturing",
            "information sector vs manufacturing", "tech employment vs factory"
        ],
        "series": ["USINFO", "MANEMP"],  # Information, Manufacturing
        "explanation": "Comparing tech/information sector employment to manufacturing.",
        "units_compatible": True,
    },

    # === INTEREST RATE COMPARISONS ===
    {
        "keywords": [
            "2 year vs 10 year", "2yr vs 10yr", "2 vs 10 year treasury",
            "short term vs long term rates", "2 year treasury vs 10 year",
            "10 year vs 2 year", "10yr vs 2yr"
        ],
        "series": ["DGS2", "DGS10"],  # 2-year, 10-year Treasury
        "explanation": "Comparing 2-year and 10-year Treasury yields.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "fed funds vs 10 year", "fed rate vs 10 year treasury",
            "federal funds vs treasury", "short rate vs long rate"
        ],
        "series": ["FEDFUNDS", "DGS10"],  # Fed funds, 10-year
        "explanation": "Comparing Federal Funds rate to 10-year Treasury yield.",
        "units_compatible": True,
    },
    {
        "keywords": [
            "mortgage rate vs 10 year", "mortgage vs treasury",
            "30 year mortgage vs 10 year", "mortgage rate vs treasury"
        ],
        "series": ["MORTGAGE30US", "DGS10"],  # 30-year mortgage, 10-year Treasury
        "explanation": "Comparing 30-year mortgage rate to 10-year Treasury yield.",
        "units_compatible": True,
    },

    # === HOUSING COMPARISONS ===
    {
        "keywords": [
            "housing starts vs permits", "starts vs permits",
            "housing starts versus permits", "building permits vs starts",
            "new construction starts vs permits"
        ],
        "series": ["HOUST", "PERMIT"],  # Housing starts, Building permits
        "explanation": "Comparing housing starts to building permits.",
        "units_compatible": True,  # Both thousands of units
    },
    {
        "keywords": [
            "new home sales vs existing", "new vs existing home sales",
            "new home vs existing home", "existing vs new home sales"
        ],
        "series": ["NHSUSSPT", "EXHOSLUSM495S"],  # New home sales, Existing home sales
        "explanation": "Comparing new home sales to existing home sales.",
        "units_compatible": False,  # Different scales
    },
    {
        "keywords": [
            "home prices vs rent", "home prices vs rents",
            "house prices vs rent", "housing prices vs rent inflation"
        ],
        "series": ["CSUSHPINSA", "CUSR0000SAH1"],  # Case-Shiller, Shelter CPI
        "explanation": "Comparing home price growth to rent inflation.",
        "units_compatible": False,  # Index vs CPI component
        "show_yoy": True,
    },

    # === CONSUMER/SPENDING COMPARISONS ===
    {
        "keywords": [
            "income vs spending", "income vs consumption",
            "personal income vs spending", "income and spending",
            "disposable income vs spending"
        ],
        "series": ["DSPIC96", "PCE"],  # Real disposable income, Personal consumption
        "explanation": "Comparing real disposable income to personal consumption spending.",
        "units_compatible": False,  # Both $ but different scales
        "show_yoy": True,
    },
    {
        "keywords": [
            "savings vs spending", "saving rate vs spending",
            "savings rate and spending"
        ],
        "series": ["PSAVERT", "PCE"],  # Saving rate, PCE
        "explanation": "Comparing personal saving rate to consumer spending.",
        "units_compatible": False,
    },
    {
        "keywords": [
            "retail sales vs consumer spending", "retail vs consumption",
            "retail sales and consumer spending"
        ],
        "series": ["RSAFS", "PCE"],  # Retail sales, PCE
        "explanation": "Comparing retail sales to total personal consumption.",
        "units_compatible": False,
        "show_yoy": True,
    },

    # === GDP/OUTPUT COMPARISONS ===
    {
        "keywords": [
            "gdp vs industrial production", "gdp and industrial production",
            "output vs industrial production", "gdp vs manufacturing output"
        ],
        "series": ["GDPC1", "INDPRO"],  # Real GDP, Industrial production
        "explanation": "Comparing GDP growth to industrial production.",
        "units_compatible": False,
        "show_yoy": True,
    },
]


def route_domestic_comparison(query: str) -> Optional[Dict]:
    """
    Check if query matches a domestic comparison pattern.

    Domestic comparisons compare two US indicators (both from FRED),
    such as "Black unemployment vs overall" or "inflation vs wages".

    Args:
        query: The user's query string

    Returns:
        Dict with comparison info if matched, None otherwise:
        {
            "is_domestic_comparison": True,
            "series": ["ID1", "ID2"],
            "explanation": "...",
            "combine_chart": True,
            "units_compatible": True/False,
            "show_yoy": True/False
        }
    """
    query_lower = query.lower().strip()

    # Check each domestic comparison pattern
    for pattern in DOMESTIC_COMPARISONS:
        for keyword in pattern["keywords"]:
            if keyword in query_lower:
                return {
                    "is_domestic_comparison": True,
                    "series": pattern["series"],
                    "explanation": pattern["explanation"],
                    "combine_chart": True,  # Always combine domestic comparisons
                    "units_compatible": pattern.get("units_compatible", True),
                    "show_yoy": pattern.get("show_yoy", False),
                }

    return None


def is_comparison_query(query: str) -> bool:
    """Check if query is asking for a comparison between regions."""
    query_lower = query.lower()

    # Check for comparison keywords
    has_comparison_word = any(kw in query_lower for kw in COMPARISON_KEYWORDS)

    # Check if multiple regions mentioned
    regions_found = extract_regions(query)
    has_multiple_regions = len(regions_found) >= 2

    # Also treat "US and X" as comparison even without explicit comparison words
    return has_comparison_word or has_multiple_regions


def extract_regions(query: str) -> list[dict]:
    """
    Extract all regions mentioned in query.

    Returns list of dicts: [{"key": "us", "source": "fred", "name": "United States"}, ...]
    """
    query_lower = query.lower()
    found = []

    for region_key, info in REGIONS.items():
        # Check region key itself
        if region_key in query_lower:
            found.append({"key": region_key, **info})
            continue

        # Check aliases
        for alias in info.get("aliases", []):
            if alias in query_lower:
                found.append({"key": region_key, **info})
                break

    # Dedupe while preserving order
    seen = set()
    unique = []
    for r in found:
        if r["key"] not in seen:
            seen.add(r["key"])
            unique.append(r)

    return unique


def extract_indicator(query: str) -> Optional[dict]:
    """
    Extract the economic indicator being asked about.

    Returns dict with indicator info or None.
    """
    query_lower = query.lower()

    best_match = None
    best_score = 0

    for indicator_key, info in INDICATORS.items():
        score = 0
        for kw in info["keywords"]:
            if kw in query_lower:
                score += len(kw)  # Longer matches score higher

        if score > best_score:
            best_score = score
            best_match = {"key": indicator_key, **info}

    return best_match


def route_comparison_query(query: str) -> Optional[dict]:
    """
    Route a comparison query to appropriate data sources.

    Returns:
        {
            "is_comparison": True,
            "regions": [{"key": "us", ...}, {"key": "eurozone", ...}],
            "indicator": {"key": "gdp", ...},
            "series_to_fetch": {
                "fred": ["GDPC1"],
                "dbnomics": ["eurozone_gdp"]
            },
            "explanation": "Comparing US and Eurozone GDP growth."
        }
    """
    if not is_comparison_query(query):
        return None

    regions = extract_regions(query)
    indicator = extract_indicator(query)

    if len(regions) < 2:
        # If only one region mentioned, assume US is the other
        us_mentioned = any(r["key"] == "us" for r in regions)
        if not us_mentioned and regions:
            regions.insert(0, {"key": "us", **REGIONS["us"]})

    if not indicator:
        # Default to GDP for general economy comparisons
        indicator = {"key": "gdp", **INDICATORS["gdp"]}

    # Build series to fetch from each source
    fred_series = []
    dbnomics_series = []

    for region in regions:
        if region["source"] == "fred":
            fred_series.extend(indicator.get("fred_series", []))
        else:
            series_key = indicator.get("dbnomics_series", {}).get(region["key"])
            if series_key:
                dbnomics_series.append(series_key)

    if not fred_series and not dbnomics_series:
        return None

    region_names = [r["name"] for r in regions]
    indicator_name = indicator["key"].upper()

    return {
        "is_comparison": True,
        "regions": regions,
        "indicator": indicator,
        "series_to_fetch": {
            "fred": fred_series,
            "dbnomics": dbnomics_series,
        },
        "explanation": f"Comparing {' and '.join(region_names)} {indicator_name}.",
    }


def smart_route_query(query: str) -> dict:
    """
    Main entry point for smart query routing.

    Returns routing instructions for the query.

    Routing priority:
    1. Domestic comparisons (Black unemployment vs overall, inflation vs wages)
    2. International comparisons (US vs Eurozone, etc.)
    3. Single international region queries
    4. Default (let existing logic handle it)
    """
    # 1. Check for DOMESTIC comparison queries FIRST
    # These compare two US indicators (both from FRED)
    # Examples: "Black unemployment vs overall", "inflation vs wages"
    domestic = route_domestic_comparison(query)
    if domestic:
        # Return in a format compatible with the app's comparison handling
        return {
            "is_comparison": True,
            "is_domestic_comparison": True,
            "series_to_fetch": {
                "fred": domestic["series"],
                "dbnomics": [],  # No international data needed
            },
            "explanation": domestic["explanation"],
            "combine_chart": domestic["combine_chart"],
            "units_compatible": domestic.get("units_compatible", True),
            "show_yoy": domestic.get("show_yoy", False),
        }

    # 2. Check for INTERNATIONAL comparison queries
    # These compare US to other countries (FRED + DBnomics)
    comparison = route_comparison_query(query)
    if comparison:
        return comparison

    # 3. Check for single international region
    regions = extract_regions(query)
    intl_regions = [r for r in regions if r["source"] == "dbnomics"]

    if intl_regions and not any(r["key"] == "us" for r in regions):
        # Pure international query
        indicator = extract_indicator(query)
        if indicator:
            dbnomics_series = []
            for region in intl_regions:
                series_key = indicator.get("dbnomics_series", {}).get(region["key"])
                if series_key:
                    dbnomics_series.append(series_key)

            if dbnomics_series:
                return {
                    "is_comparison": False,
                    "source": "dbnomics",
                    "series": dbnomics_series,
                    "explanation": f"{intl_regions[0]['name']} {indicator['key']}.",
                }

    # 4. Default: let existing logic handle it
    return {
        "is_comparison": False,
        "source": "default",
        "series": [],
        "explanation": None,
    }


# Quick test
if __name__ == "__main__":
    print("Query Router Tests\n" + "=" * 50)

    # DOMESTIC COMPARISON TESTS (NEW)
    print("\n--- DOMESTIC COMPARISONS ---")
    domestic_test_queries = [
        "Black unemployment vs overall",
        "inflation vs wage growth",
        "job openings vs unemployed",
        "core vs headline inflation",
        "women unemployment vs men",
        "2 year vs 10 year treasury",
        "housing starts vs permits",
    ]

    for q in domestic_test_queries:
        print(f"\nQuery: '{q}'")
        result = smart_route_query(q)
        print(f"  Is Comparison: {result.get('is_comparison')}")
        print(f"  Is Domestic: {result.get('is_domestic_comparison', False)}")
        if result.get('series_to_fetch'):
            print(f"  FRED Series: {result['series_to_fetch'].get('fred', [])}")
            print(f"  Combine Chart: {result.get('combine_chart', False)}")
            print(f"  Show YoY: {result.get('show_yoy', False)}")
        print(f"  Explanation: {result.get('explanation')}")

    # INTERNATIONAL COMPARISON TESTS (EXISTING)
    print("\n\n--- INTERNATIONAL COMPARISONS ---")
    intl_test_queries = [
        "how has growth in the US compared to Eurozone?",
        "US vs China GDP",
        "compare US and UK inflation",
        "how is the eurozone doing?",
        "Japan unemployment rate",
        "Fed rate vs ECB rate",
        "how is the economy?",  # Should fall through to default
    ]

    for q in intl_test_queries:
        print(f"\nQuery: '{q}'")
        result = smart_route_query(q)
        print(f"  Comparison: {result.get('is_comparison')}")
        if result.get('series_to_fetch'):
            print(f"  FRED: {result['series_to_fetch'].get('fred', [])}")
            print(f"  DBnomics: {result['series_to_fetch'].get('dbnomics', [])}")
        elif result.get('series'):
            print(f"  Series: {result['series']}")
        print(f"  Explanation: {result.get('explanation')}")
