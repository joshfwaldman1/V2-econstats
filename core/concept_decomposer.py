"""
Concept Decomposer for EconStats.

Breaks natural language queries into structured economic concepts,
then maps those concepts to appropriate data series.

The key insight: "megacap US firms" doesn't match any keyword, but if we
decompose it into concepts [stock_market, corporate_health], we can find
the right data (SP500, NASDAQCOM, corporate profits).

Usage:
    from core.concept_decomposer import (
        decompose_query,
        get_data_for_concepts,
        DecomposedQuery,
    )

    # Decompose a query
    result = decompose_query("how are megacap US firms doing?")
    # result.concepts = ["stock_market", "corporate_health"]
    # result.series = ["SP500", "NASDAQCOM", "CP", "INDPRO"]

    # Get series for specific concepts
    series = get_data_for_concepts(["stock_market", "corporate_health"])
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

# Import from data_inventory
from core.data_inventory import (
    get_series_for_concept,
    get_primary_series_for_concept,
    find_series_by_keyword,
    get_concept_for_query,
    CONCEPT_ALIASES,
    DATA_INVENTORY,
    SeriesInfo,
)


# =============================================================================
# ECONOMIC CONCEPT VOCABULARY
# =============================================================================

class EconomicConcept(Enum):
    """
    Standardized economic concepts that queries can decompose into.

    These are higher-level than data categories - they represent
    what the user is conceptually asking about.
    """
    # Market & Corporate
    STOCK_MARKET = "stock_market"
    CORPORATE_HEALTH = "corporate_health"
    CORPORATE_PROFITS = "corporate_profits"
    BUSINESS_INVESTMENT = "business_investment"

    # Employment
    EMPLOYMENT = "employment"
    UNEMPLOYMENT = "unemployment"
    WAGE_GROWTH = "wage_growth"
    JOB_CREATION = "job_creation"
    LABOR_MARKET = "labor_market"

    # Prices
    INFLATION = "inflation"
    CORE_INFLATION = "core_inflation"
    SHELTER_INFLATION = "shelter_inflation"
    FOOD_PRICES = "food_prices"
    ENERGY_PRICES = "energy_prices"

    # Growth
    GDP_GROWTH = "gdp_growth"
    ECONOMIC_GROWTH = "economic_growth"
    PRODUCTION = "production"

    # Housing
    HOME_PRICES = "home_prices"
    RENTS = "rents"
    HOUSING_ACTIVITY = "housing_activity"
    MORTGAGE_RATES = "mortgage_rates"

    # Consumer
    CONSUMER_SENTIMENT = "consumer_sentiment"
    CONSUMER_SPENDING = "consumer_spending"
    PERSONAL_INCOME = "personal_income"

    # Fed & Rates
    FED_POLICY = "fed_policy"
    INTEREST_RATES = "interest_rates"
    YIELD_CURVE = "yield_curve"

    # Recession
    RECESSION_RISK = "recession_risk"

    # Energy
    OIL_PRICES = "oil_prices"
    GAS_PRICES = "gas_prices"


# Map concepts to data inventory paths
CONCEPT_TO_INVENTORY: Dict[EconomicConcept, List[str]] = {
    # Market & Corporate
    EconomicConcept.STOCK_MARKET: ["markets.equities"],
    EconomicConcept.CORPORATE_HEALTH: ["markets.equities", "markets.corporate"],
    EconomicConcept.CORPORATE_PROFITS: ["markets.corporate"],
    EconomicConcept.BUSINESS_INVESTMENT: ["markets.corporate"],

    # Employment
    EconomicConcept.EMPLOYMENT: ["employment"],
    EconomicConcept.UNEMPLOYMENT: ["employment.unemployment"],
    EconomicConcept.WAGE_GROWTH: ["employment.wages"],
    EconomicConcept.JOB_CREATION: ["employment.job_creation"],
    EconomicConcept.LABOR_MARKET: ["employment.unemployment", "employment.job_creation"],

    # Prices
    EconomicConcept.INFLATION: ["inflation.headline", "inflation.core"],
    EconomicConcept.CORE_INFLATION: ["inflation.core"],
    EconomicConcept.SHELTER_INFLATION: ["inflation.shelter"],
    EconomicConcept.FOOD_PRICES: ["inflation.food"],
    EconomicConcept.ENERGY_PRICES: ["energy"],

    # Growth
    EconomicConcept.GDP_GROWTH: ["growth.gdp"],
    EconomicConcept.ECONOMIC_GROWTH: ["growth"],
    EconomicConcept.PRODUCTION: ["growth.production"],

    # Housing
    EconomicConcept.HOME_PRICES: ["housing.prices"],
    EconomicConcept.RENTS: ["housing.rents"],
    EconomicConcept.HOUSING_ACTIVITY: ["housing.construction", "housing.sales"],
    EconomicConcept.MORTGAGE_RATES: ["housing.affordability"],

    # Consumer
    EconomicConcept.CONSUMER_SENTIMENT: ["consumer.sentiment"],
    EconomicConcept.CONSUMER_SPENDING: ["consumer.spending"],
    EconomicConcept.PERSONAL_INCOME: ["consumer.income"],

    # Fed & Rates
    EconomicConcept.FED_POLICY: ["fed.rates"],
    EconomicConcept.INTEREST_RATES: ["fed.rates", "markets.bonds"],
    EconomicConcept.YIELD_CURVE: ["markets.bonds"],

    # Recession
    EconomicConcept.RECESSION_RISK: ["recession.indicators"],

    # Energy
    EconomicConcept.OIL_PRICES: ["energy.oil"],
    EconomicConcept.GAS_PRICES: ["energy.gasoline"],
}


# Natural language patterns that map to concepts
CONCEPT_PATTERNS: Dict[EconomicConcept, List[str]] = {
    # Market & Corporate
    EconomicConcept.STOCK_MARKET: [
        r"stock market", r"stocks", r"equities", r"s&p", r"nasdaq", r"dow",
        r"wall street", r"shares", r"indices", r"index",
    ],
    EconomicConcept.CORPORATE_HEALTH: [
        r"megacap", r"mega cap", r"large cap", r"corporations", r"corporate",
        r"big (companies|firms|business)", r"large (companies|firms)",
        r"us firms", r"american (companies|firms)", r"fortune 500", r"blue chip",
    ],
    EconomicConcept.CORPORATE_PROFITS: [
        r"corporate profits", r"company profits", r"business profits",
        r"earnings", r"profitability",
    ],

    # Employment
    EconomicConcept.UNEMPLOYMENT: [
        r"unemployment", r"jobless", r"out of work",
    ],
    EconomicConcept.EMPLOYMENT: [
        r"employment", r"jobs", r"workers", r"workforce",
    ],
    EconomicConcept.WAGE_GROWTH: [
        r"wages?", r"salary", r"salaries", r"pay", r"compensation",
        r"earnings", r"hourly",
    ],
    EconomicConcept.JOB_CREATION: [
        r"job (creation|growth|gains)", r"payrolls?", r"hiring",
        r"new jobs", r"job openings",
    ],
    EconomicConcept.LABOR_MARKET: [
        r"labor market", r"job market", r"employment situation",
    ],

    # Prices
    EconomicConcept.INFLATION: [
        r"inflation", r"prices", r"cpi", r"pce", r"cost of living",
    ],
    EconomicConcept.CORE_INFLATION: [
        r"core inflation", r"core cpi", r"core pce", r"underlying inflation",
    ],
    EconomicConcept.SHELTER_INFLATION: [
        r"shelter", r"rent inflation", r"housing inflation", r"oer",
    ],
    EconomicConcept.FOOD_PRICES: [
        r"food prices", r"grocery", r"groceries", r"food costs",
    ],

    # Growth
    EconomicConcept.GDP_GROWTH: [
        r"gdp", r"gross domestic product",
    ],
    EconomicConcept.ECONOMIC_GROWTH: [
        r"economy", r"economic growth", r"growth", r"expansion",
    ],
    EconomicConcept.PRODUCTION: [
        r"production", r"industrial", r"manufacturing", r"factory",
        r"factories", r"output",
    ],

    # Housing
    EconomicConcept.HOME_PRICES: [
        r"home prices", r"house prices", r"housing prices",
        r"home values", r"real estate prices",
    ],
    EconomicConcept.RENTS: [
        r"rents?", r"rental", r"renters?", r"leasing",
    ],
    EconomicConcept.HOUSING_ACTIVITY: [
        r"housing (starts|construction|sales|market)",
        r"home (sales|building)", r"real estate",
    ],
    EconomicConcept.MORTGAGE_RATES: [
        r"mortgage", r"home loan",
    ],

    # Consumer
    EconomicConcept.CONSUMER_SENTIMENT: [
        r"consumer (sentiment|confidence)", r"confidence",
        r"how (consumers|people) feel",
    ],
    EconomicConcept.CONSUMER_SPENDING: [
        r"consumer spending", r"spending", r"consumption",
        r"retail( sales)?", r"shopping",
    ],
    EconomicConcept.PERSONAL_INCOME: [
        r"income", r"disposable income", r"savings",
    ],

    # Fed & Rates
    EconomicConcept.FED_POLICY: [
        r"fed", r"federal reserve", r"fomc", r"powell", r"monetary policy",
        r"rate (cut|hike|decision)", r"fed (rate|funds)",
    ],
    EconomicConcept.INTEREST_RATES: [
        r"interest rates?", r"rates", r"borrowing costs",
    ],
    EconomicConcept.YIELD_CURVE: [
        r"yield curve", r"treasury", r"10.?year", r"2.?year", r"spread",
    ],

    # Recession
    EconomicConcept.RECESSION_RISK: [
        r"recession", r"downturn", r"contraction", r"crisis",
        r"soft landing", r"hard landing", r"sahm",
    ],

    # Energy
    EconomicConcept.OIL_PRICES: [
        r"oil", r"crude", r"petroleum", r"wti", r"brent",
    ],
    EconomicConcept.GAS_PRICES: [
        r"gas prices?", r"gasoline", r"fuel( prices)?", r"pump prices?",
    ],
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ConceptMatch:
    """A matched concept with confidence score."""
    concept: EconomicConcept
    confidence: float  # 0.0 - 1.0
    matched_pattern: str  # What pattern triggered this match
    reasoning: str  # Why this concept was identified


@dataclass
class DecomposedQuery:
    """Result of query decomposition."""
    original_query: str
    concepts: List[ConceptMatch]
    inventory_paths: List[str]  # Paths into DATA_INVENTORY
    series: List[SeriesInfo]
    series_ids: List[str]
    show_yoy: List[bool]
    explanation: str


# =============================================================================
# CORE DECOMPOSITION LOGIC
# =============================================================================

def extract_concepts(query: str) -> List[ConceptMatch]:
    """
    Extract economic concepts from a query using pattern matching.

    Args:
        query: Natural language query

    Returns:
        List of ConceptMatch objects sorted by confidence
    """
    query_lower = query.lower()
    matches = []

    for concept, patterns in CONCEPT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                # Longer matches get higher confidence
                match_len = len(pattern.replace(r"(", "").replace(r")", "").replace(r"|", ""))
                confidence = min(0.95, 0.5 + match_len / 30)

                matches.append(ConceptMatch(
                    concept=concept,
                    confidence=confidence,
                    matched_pattern=pattern,
                    reasoning=f"Pattern '{pattern}' matched in query"
                ))
                break  # One match per concept is enough

    # Sort by confidence descending
    matches.sort(key=lambda m: m.confidence, reverse=True)

    # Dedupe (keep highest confidence per concept)
    seen = set()
    deduped = []
    for m in matches:
        if m.concept not in seen:
            seen.add(m.concept)
            deduped.append(m)

    return deduped


def get_inventory_paths_for_concepts(concepts: List[EconomicConcept]) -> List[str]:
    """
    Map concepts to data inventory paths.

    Args:
        concepts: List of EconomicConcept

    Returns:
        List of unique inventory paths
    """
    paths = []
    for concept in concepts:
        if concept in CONCEPT_TO_INVENTORY:
            paths.extend(CONCEPT_TO_INVENTORY[concept])

    # Dedupe while preserving order
    seen = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


def get_series_for_paths(paths: List[str], max_series: int = 5) -> Tuple[List[SeriesInfo], List[str]]:
    """
    Get series from inventory paths, limiting to primary series.

    Args:
        paths: List of inventory paths
        max_series: Maximum number of series to return

    Returns:
        Tuple of (series list, series IDs)
    """
    all_series = []

    for path in paths:
        series = get_primary_series_for_concept(path)
        all_series.extend(series)

    # Dedupe by ID
    seen = set()
    unique = []
    for s in all_series:
        if s.id not in seen:
            seen.add(s.id)
            unique.append(s)

    # Limit
    limited = unique[:max_series]
    ids = [s.id for s in limited]

    return limited, ids


def determine_yoy_flags(series: List[SeriesInfo]) -> List[bool]:
    """
    Determine which series should be displayed as YoY changes.

    Args:
        series: List of SeriesInfo

    Returns:
        List of boolean flags (True = show as YoY)
    """
    from core.data_inventory import DisplayTransform

    return [s.display_transform == DisplayTransform.YOY_PCT for s in series]


def decompose_query(query: str, max_concepts: int = 3, max_series: int = 5) -> DecomposedQuery:
    """
    Main entry point: Decompose a query into concepts and get relevant data.

    This is the primary function for the concept decomposition system.

    Args:
        query: Natural language query
        max_concepts: Maximum concepts to consider
        max_series: Maximum series to return

    Returns:
        DecomposedQuery with concepts, series, and metadata

    Example:
        >>> result = decompose_query("how are megacap US firms doing?")
        >>> result.concepts  # [ConceptMatch(CORPORATE_HEALTH, 0.9, ...)]
        >>> result.series_ids  # ["SP500", "NASDAQCOM", "CP", "INDPRO"]
    """
    # Step 1: Extract concepts from query
    concept_matches = extract_concepts(query)[:max_concepts]

    if not concept_matches:
        # Fallback: try the simpler concept_for_query approach
        simple_concept = get_concept_for_query(query)
        if simple_concept:
            # Create a synthetic match
            concept_matches = [ConceptMatch(
                concept=EconomicConcept.ECONOMIC_GROWTH,  # Default
                confidence=0.5,
                matched_pattern="fallback",
                reasoning=f"Fallback to inventory concept: {simple_concept}"
            )]
            # Use the simple concept path directly
            paths = [simple_concept]
        else:
            # No matches at all
            return DecomposedQuery(
                original_query=query,
                concepts=[],
                inventory_paths=[],
                series=[],
                series_ids=[],
                show_yoy=[],
                explanation="Could not identify economic concepts in query"
            )
    else:
        # Step 2: Map concepts to inventory paths
        concepts = [m.concept for m in concept_matches]
        paths = get_inventory_paths_for_concepts(concepts)

    # Step 3: Get series from paths
    series, series_ids = get_series_for_paths(paths, max_series)

    # Step 4: Determine display transformations
    show_yoy = determine_yoy_flags(series)

    # Step 5: Build explanation
    concept_names = [m.concept.value for m in concept_matches]
    explanation = f"Identified concepts: {', '.join(concept_names)}. " \
                  f"Data from: {', '.join(paths[:3])}."

    return DecomposedQuery(
        original_query=query,
        concepts=concept_matches,
        inventory_paths=paths,
        series=series,
        series_ids=series_ids,
        show_yoy=show_yoy,
        explanation=explanation
    )


def get_data_for_concepts(concept_names: List[str]) -> Dict:
    """
    Get data for a list of concept names (string form).

    Args:
        concept_names: List like ["stock_market", "corporate_health"]

    Returns:
        Dict with series_ids, show_yoy, explanation
    """
    # Convert strings to enums
    concepts = []
    for name in concept_names:
        try:
            concept = EconomicConcept(name)
            concepts.append(concept)
        except ValueError:
            pass

    if not concepts:
        return {"series_ids": [], "show_yoy": [], "explanation": "Unknown concepts"}

    paths = get_inventory_paths_for_concepts(concepts)
    series, series_ids = get_series_for_paths(paths)
    show_yoy = determine_yoy_flags(series)

    return {
        "series_ids": series_ids,
        "show_yoy": show_yoy,
        "explanation": f"Data for concepts: {concept_names}"
    }


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def should_use_decomposer(query: str) -> bool:
    """
    Determine if this query should go through the decomposer.

    Some queries are better handled by direct routing (e.g., "UNRATE").

    Args:
        query: The query to check

    Returns:
        True if decomposer should be used
    """
    query_lower = query.lower().strip()

    # Direct series ID requests - don't decompose
    if query_lower.upper() in ["UNRATE", "PAYEMS", "CPIAUCSL", "SP500", "GDPC1"]:
        return False

    # Very short queries might be direct lookups
    if len(query_lower.split()) <= 2:
        return False

    # "How is X doing?" type queries - definitely decompose
    if re.search(r"how (is|are) .+ doing", query_lower):
        return True

    # Questions with multiple words - decompose
    if "?" in query and len(query_lower.split()) > 3:
        return True

    return True


def decompose_if_needed(query: str) -> Optional[DecomposedQuery]:
    """
    Conditionally decompose a query.

    Args:
        query: The query

    Returns:
        DecomposedQuery if decomposition was performed, None otherwise
    """
    if should_use_decomposer(query):
        result = decompose_query(query)
        if result.series_ids:  # Only return if we found something
            return result
    return None


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=== Concept Decomposer Test ===\n")

    test_queries = [
        "how are megacap US firms doing?",
        "how is the labor market?",
        "what about inflation?",
        "is a recession coming?",
        "how is the housing market?",
        "what's happening with the Fed?",
        "how are consumers doing?",
        "oil prices",
    ]

    for query in test_queries:
        print(f"Query: \"{query}\"")
        result = decompose_query(query)

        if result.concepts:
            concepts_str = ", ".join([f"{m.concept.value} ({m.confidence:.2f})" for m in result.concepts])
            print(f"  Concepts: {concepts_str}")
            print(f"  Paths: {result.inventory_paths}")
            print(f"  Series: {result.series_ids}")
            print(f"  YoY: {result.show_yoy}")
        else:
            print(f"  No concepts found")
        print()
