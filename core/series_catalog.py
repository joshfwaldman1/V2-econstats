"""
Unified Series Catalog - Single source of truth for all economic series.

Consolidates metadata from:
- 9 plan JSON files (query → series mappings)
- series_rag.py (115 curated series)
- dbnomics.py (international series)
- stocks.py (market series)
- QUERY_SERIES_ALIGNMENT in app.py
"""

import json
import os
from typing import Optional
from dataclasses import dataclass

# Get the agents directory path
AGENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents")


@dataclass
class SeriesMetadata:
    """Metadata for a single economic series."""

    id: str
    name: str
    source: str  # "fred", "dbnomics", "polymarket"
    category: str  # "employment", "inflation", "gdp", etc.
    display: str  # "rate" (show as-is), "yoy_pct" (transform to YoY), "level"

    # Optional fields
    description: str = ""
    keywords: list = None
    demographic: str = None  # For demographic-specific series
    dbnomics_id: str = None  # For DBnomics series
    measure_type: str = None  # "real", "nominal", "rate", "index"
    change_type: str = None  # "yoy", "qoq", "mom", "level"
    frequency: str = None  # "daily", "weekly", "monthly", "quarterly", "annual"


# Core US series with metadata
CORE_SERIES = {
    # Employment
    "UNRATE": SeriesMetadata(
        id="UNRATE",
        name="Unemployment Rate",
        source="fred",
        category="employment",
        display="rate",
        keywords=["unemployment", "jobless", "labor market"],
    ),
    "PAYEMS": SeriesMetadata(
        id="PAYEMS",
        name="Total Nonfarm Payrolls",
        source="fred",
        category="employment",
        display="change",  # Show MoM change
        keywords=["jobs", "payrolls", "employment"],
    ),
    # GDP
    "GDPC1": SeriesMetadata(
        id="GDPC1",
        name="Real GDP",
        source="fred",
        category="gdp",
        display="yoy_pct",  # Transform level to YoY growth
        measure_type="real",
        change_type="level",
        keywords=["gdp", "growth", "economy", "output"],
    ),
    "A191RL1Q225SBEA": SeriesMetadata(
        id="A191RL1Q225SBEA",
        name="Real GDP Growth (SAAR)",
        source="fred",
        category="gdp",
        display="rate",  # Already a growth rate
        keywords=["gdp growth", "quarterly gdp"],
    ),
    # Inflation
    "CPIAUCSL": SeriesMetadata(
        id="CPIAUCSL",
        name="Consumer Price Index",
        source="fred",
        category="inflation",
        display="yoy_pct",  # Transform index to YoY inflation
        measure_type="index",
        change_type="level",
        keywords=["inflation", "cpi", "prices"],
    ),
    "CPILFESL": SeriesMetadata(
        id="CPILFESL",
        name="Core CPI (Ex Food & Energy)",
        source="fred",
        category="inflation",
        display="yoy_pct",
        keywords=["core inflation", "core cpi"],
    ),
    "PCEPILFE": SeriesMetadata(
        id="PCEPILFE",
        name="Core PCE (Fed's Target)",
        source="fred",
        category="inflation",
        display="yoy_pct",
        keywords=["pce", "fed target", "core pce"],
    ),
    # Interest Rates
    "FEDFUNDS": SeriesMetadata(
        id="FEDFUNDS",
        name="Federal Funds Rate",
        source="fred",
        category="fed_rates",
        display="rate",
        keywords=["fed", "interest rates", "monetary policy"],
    ),
    "DGS10": SeriesMetadata(
        id="DGS10",
        name="10-Year Treasury Yield",
        source="fred",
        category="fed_rates",
        display="rate",
        keywords=["treasury", "yields", "bonds"],
    ),
    "MORTGAGE30US": SeriesMetadata(
        id="MORTGAGE30US",
        name="30-Year Mortgage Rate",
        source="fred",
        category="housing",
        display="rate",
        keywords=["mortgage", "housing", "rates"],
    ),
    # Housing
    "CSUSHPINSA": SeriesMetadata(
        id="CSUSHPINSA",
        name="Case-Shiller Home Price Index",
        source="fred",
        category="housing",
        display="yoy_pct",
        keywords=["home prices", "housing", "real estate"],
    ),
    "HOUST": SeriesMetadata(
        id="HOUST",
        name="Housing Starts",
        source="fred",
        category="housing",
        display="level",
        keywords=["housing starts", "construction", "new homes"],
    ),
    # Consumer Prices (detailed)
    "CUSR0000SAF1": SeriesMetadata(
        id="CUSR0000SAF1",
        name="CPI: Food at Home",
        source="fred",
        category="inflation",
        display="yoy_pct",
        measure_type="index",
        change_type="level",
        keywords=["food prices", "grocery prices", "food inflation", "food cpi"],
    ),
    "CUSR0000SETB01": SeriesMetadata(
        id="CUSR0000SETB01",
        name="CPI: Gasoline",
        source="fred",
        category="inflation",
        display="yoy_pct",
        measure_type="index",
        change_type="level",
        keywords=["gas prices", "gasoline", "fuel prices", "energy prices"],
    ),
    "CUSR0000SEHA": SeriesMetadata(
        id="CUSR0000SEHA",
        name="CPI: Rent of Primary Residence",
        source="fred",
        category="inflation",
        display="yoy_pct",
        measure_type="index",
        change_type="level",
        keywords=["rent", "rental prices", "shelter inflation", "housing costs"],
    ),
    # Labor Market
    "JTSJOL": SeriesMetadata(
        id="JTSJOL",
        name="Job Openings (JOLTS)",
        source="fred",
        category="employment",
        display="level",
        keywords=["job openings", "jolts", "labor demand", "vacancies"],
    ),
    "ICSA": SeriesMetadata(
        id="ICSA",
        name="Initial Jobless Claims",
        source="fred",
        category="employment",
        display="level",
        frequency="weekly",
        keywords=["jobless claims", "initial claims", "unemployment claims", "layoffs"],
    ),
    "LNS12300060": SeriesMetadata(
        id="LNS12300060",
        name="Prime-Age Employment-Population Ratio",
        source="fred",
        category="employment",
        display="rate",
        keywords=["prime age employment", "employment ratio", "25-54", "working age"],
    ),
    "CIVPART": SeriesMetadata(
        id="CIVPART",
        name="Labor Force Participation Rate",
        source="fred",
        category="employment",
        display="rate",
        keywords=["labor force participation", "lfpr", "workforce participation"],
    ),
    # Wages and Earnings
    "CES0500000003": SeriesMetadata(
        id="CES0500000003",
        name="Average Hourly Earnings (Private)",
        source="fred",
        category="wages",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["wages", "hourly earnings", "pay", "wage growth"],
    ),
    "LES1252881600Q": SeriesMetadata(
        id="LES1252881600Q",
        name="Real Median Weekly Earnings",
        source="fred",
        category="wages",
        display="yoy_pct",
        measure_type="real",
        change_type="level",
        frequency="quarterly",
        keywords=["real wages", "median earnings", "real income", "purchasing power"],
    ),
    "AHETPI": SeriesMetadata(
        id="AHETPI",
        name="Average Hourly Earnings (Production Workers)",
        source="fred",
        category="wages",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["production wages", "worker pay", "blue collar wages"],
    ),
    # Business Activity
    "BUSLOANS": SeriesMetadata(
        id="BUSLOANS",
        name="Commercial and Industrial Loans",
        source="fred",
        category="business",
        display="yoy_pct",
        keywords=["business loans", "commercial loans", "bank lending", "credit"],
    ),
    "RSXFS": SeriesMetadata(
        id="RSXFS",
        name="Retail Sales (Ex Food Services)",
        source="fred",
        category="business",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["retail sales", "consumer spending", "retail", "shopping"],
    ),
    "INDPRO": SeriesMetadata(
        id="INDPRO",
        name="Industrial Production Index",
        source="fred",
        category="business",
        display="yoy_pct",
        measure_type="index",
        change_type="level",
        keywords=["industrial production", "manufacturing output", "factory output"],
    ),
    # Consumer Indicators
    "UMCSENT": SeriesMetadata(
        id="UMCSENT",
        name="Consumer Sentiment (U of Michigan)",
        source="fred",
        category="consumer",
        display="level",
        measure_type="index",
        keywords=["consumer sentiment", "consumer confidence", "michigan sentiment"],
    ),
    "PCE": SeriesMetadata(
        id="PCE",
        name="Personal Consumption Expenditures",
        source="fred",
        category="consumer",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["consumer spending", "pce", "personal consumption", "expenditures"],
    ),
    "PCEC96": SeriesMetadata(
        id="PCEC96",
        name="Real Personal Consumption Expenditures",
        source="fred",
        category="consumer",
        display="yoy_pct",
        measure_type="real",
        change_type="level",
        keywords=["real consumer spending", "real pce", "inflation-adjusted spending"],
    ),
    "PSAVERT": SeriesMetadata(
        id="PSAVERT",
        name="Personal Saving Rate",
        source="fred",
        category="consumer",
        display="rate",
        keywords=["saving rate", "savings", "personal savings"],
    ),
    # Manufacturing
    "IPMAN": SeriesMetadata(
        id="IPMAN",
        name="Industrial Production: Manufacturing",
        source="fred",
        category="manufacturing",
        display="yoy_pct",
        measure_type="index",
        change_type="level",
        keywords=["manufacturing production", "factory output", "manufacturing index"],
    ),
    "DGORDER": SeriesMetadata(
        id="DGORDER",
        name="Durable Goods Orders",
        source="fred",
        category="manufacturing",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["durable goods", "manufacturing orders", "capital goods", "equipment orders"],
    ),
    "NEWORDER": SeriesMetadata(
        id="NEWORDER",
        name="Manufacturers' New Orders",
        source="fred",
        category="manufacturing",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["manufacturing orders", "new orders", "factory orders"],
    ),
    "AMTMNO": SeriesMetadata(
        id="AMTMNO",
        name="Value of Manufacturers' New Orders",
        source="fred",
        category="manufacturing",
        display="yoy_pct",
        measure_type="nominal",
        change_type="level",
        keywords=["manufacturing orders", "new orders total", "factory orders value"],
    ),
}

# International series (DBnomics)
INTERNATIONAL_SERIES = {
    "eurozone_gdp": SeriesMetadata(
        id="eurozone_gdp",
        name="Eurozone GDP Growth (YoY)",
        source="dbnomics",
        category="gdp",
        display="rate",  # Already YoY growth
        dbnomics_id="Eurostat/namq_10_gdp/Q.CLV_PCH_SM.SCA.B1GQ.EA20",
        measure_type="real",
        change_type="yoy",
        keywords=["eurozone", "europe", "eu", "gdp"],
    ),
    "eurozone_inflation": SeriesMetadata(
        id="eurozone_inflation",
        name="Eurozone Inflation (HICP)",
        source="dbnomics",
        category="inflation",
        display="rate",
        dbnomics_id="Eurostat/prc_hicp_manr/M.RCH_A.CP00.EA",
        change_type="yoy",
        keywords=["eurozone", "europe", "inflation", "hicp"],
    ),
    "uk_gdp": SeriesMetadata(
        id="uk_gdp",
        name="UK GDP Growth (YoY)",
        source="dbnomics",
        category="gdp",
        display="rate",
        dbnomics_id="BOE/GDP/IHYR.Q",
        measure_type="real",
        change_type="yoy",
        keywords=["uk", "britain", "gdp"],
    ),
    "china_gdp": SeriesMetadata(
        id="china_gdp",
        name="China GDP Growth (YoY)",
        source="dbnomics",
        category="gdp",
        display="rate",
        dbnomics_id="IMF/WEO:2024-10/CHN.NGDP_RPCH.pcent_change",
        measure_type="real",
        change_type="yoy",
        keywords=["china", "gdp", "asia"],
    ),
}

# Combined catalog
SERIES_CATALOG = {**CORE_SERIES, **INTERNATIONAL_SERIES}


def get_series_metadata(series_id: str) -> Optional[SeriesMetadata]:
    """Get metadata for a series by ID."""
    return SERIES_CATALOG.get(series_id)


def find_series_by_keyword(keyword: str) -> list[SeriesMetadata]:
    """Find series matching a keyword."""
    keyword_lower = keyword.lower()
    matches = []
    for series in SERIES_CATALOG.values():
        if series.keywords:
            if any(keyword_lower in kw.lower() for kw in series.keywords):
                matches.append(series)
    return matches


def find_series_by_category(category: str) -> list[SeriesMetadata]:
    """Find all series in a category."""
    return [s for s in SERIES_CATALOG.values() if s.category == category]


def load_query_plans() -> dict:
    """Load all pre-computed query plans from JSON files."""
    plans = {}
    plan_files = [
        "plans_employment.json",
        "plans_inflation.json",
        "plans_gdp.json",
        "plans_housing.json",
        "plans_fed_rates.json",
        "plans_consumer.json",
        "plans_demographics.json",
        "plans_economy_overview.json",
        "plans_trade_markets.json",
    ]

    for filename in plan_files:
        filepath = os.path.join(AGENTS_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                file_plans = json.load(f)
                plans.update(file_plans)

    return plans


# Load plans at module import
QUERY_PLANS = load_query_plans()


def find_plan_for_query(query: str) -> Optional[dict]:
    """Find a pre-computed plan for a query."""
    query_lower = query.lower().strip()

    # Exact match
    if query_lower in QUERY_PLANS:
        return QUERY_PLANS[query_lower]

    # Partial match
    for plan_query, plan in QUERY_PLANS.items():
        if plan_query in query_lower or query_lower in plan_query:
            return plan

    return None


# Quick test
if __name__ == "__main__":
    print(f"Loaded {len(SERIES_CATALOG)} series")
    print(f"Loaded {len(QUERY_PLANS)} query plans")

    print("\n=== Sample Series ===")
    for sid, meta in list(SERIES_CATALOG.items())[:5]:
        print(f"{sid}: {meta.name} ({meta.source}, {meta.display})")

    print("\n=== Sample Plans ===")
    for query in ["unemployment rate", "inflation", "gdp growth"]:
        plan = find_plan_for_query(query)
        if plan:
            print(f"'{query}' → {plan.get('series', [])}")
