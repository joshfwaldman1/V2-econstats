"""
Unified Data Catalog for EconStats.

This module provides a comprehensive catalog of all economic data series
across all data sources (FRED, Zillow, EIA, Alpha Vantage, DBnomics, Polymarket).
It enables unified search, discovery, and embedding generation for semantic search.

Architecture:
1. CatalogEntry dataclass defines unified schema for all series
2. UNIFIED_CATALOG dict aggregates all series from all sources
3. Search functions enable keyword/category-based discovery
4. Export function generates text for embedding-based semantic search

Usage:
    from core.unified_catalog import (
        search_catalog,
        get_series_for_category,
        list_categories,
        get_all_entries,
        export_for_embeddings,
        UNIFIED_CATALOG
    )

    # Search by keyword
    results = search_catalog("inflation housing rent")

    # Get all series in a category
    housing_series = get_series_for_category("housing")

    # Export for embedding generation
    embedding_data = export_for_embeddings()
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
import re


# =============================================================================
# UNIFIED SCHEMA
# =============================================================================

@dataclass
class CatalogEntry:
    """
    Unified schema for all economic data series across all sources.

    Attributes:
        id: Series identifier (unique within source, e.g., "UNRATE", "zillow_zori_national")
        name: Human-readable name for display
        source: Data source ("fred", "zillow", "eia", "alphavantage", "dbnomics", "polymarket")
        description: 1-2 sentence description optimized for semantic/vector search
        category: High-level category (e.g., "employment", "housing", "inflation")
        subcategory: More specific subcategory (e.g., "prices", "starts", "rent")
        keywords: List of search keywords for matching user queries
        frequency: Data frequency ("daily", "weekly", "monthly", "quarterly", "annual")
        unit: Unit of measurement ("percent", "dollars", "thousands", "index", etc.)
        display_as: How to display the data ("level", "yoy_pct", "mom_change", "rate")
        measure_type: Type of measurement ("real", "nominal", "rate", "index")
        change_type: Type of change ("level", "yoy", "qoq", "mom")
        fred_equivalent: FRED series ID if this series has an equivalent in FRED (for deduplication)
    """
    id: str
    name: str
    source: str
    description: str
    category: str
    subcategory: str
    keywords: List[str]
    frequency: str
    unit: str
    display_as: str = "level"
    measure_type: str = "nominal"
    change_type: str = "level"
    fred_equivalent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def get_search_text(self) -> str:
        """
        Generate combined text for semantic search / embedding.
        Combines name, description, keywords, and category info.
        """
        keyword_text = " ".join(self.keywords)
        return f"{self.name}. {self.description} Category: {self.category}, {self.subcategory}. Keywords: {keyword_text}"


# =============================================================================
# CATEGORY AND SUBCATEGORY MAPPINGS
# =============================================================================

# Standard categories for organizing all series
CATEGORIES = {
    "employment": "Jobs, labor market, unemployment, payrolls, wages",
    "housing": "Home prices, rents, housing starts, building permits, mortgage rates",
    "inflation": "Consumer prices, CPI, PCE, producer prices, cost of living",
    "gdp": "Economic growth, output, production, GDP components",
    "interest_rates": "Fed funds, treasury yields, mortgage rates, bond yields",
    "financial_markets": "Stocks, bonds, commodities, forex, volatility",
    "consumer": "Consumer spending, sentiment, retail sales, savings",
    "trade": "Imports, exports, trade balance, dollar index",
    "energy": "Oil, gas, electricity, energy prices and production",
    "government": "Fiscal policy, debt, deficits, government spending",
    "international": "Foreign economies, global indicators, cross-country comparisons",
    "fed_policy": "Federal Reserve policy, projections, dot plot, FOMC",
    "recession": "Recession indicators, economic cycles, leading indicators",
    "predictions": "Forward-looking market expectations, prediction markets",
}


# =============================================================================
# BUILD CATALOG FROM ALL SOURCES
# =============================================================================

def _build_fred_entries() -> Dict[str, CatalogEntry]:
    """
    Build catalog entries from FRED series catalog.

    Imports from agents/series_rag.py and converts to unified schema.
    """
    try:
        from agents.series_rag import FRED_SERIES_CATALOG
    except ImportError:
        FRED_SERIES_CATALOG = []

    entries = {}

    # Category mapping based on series characteristics
    def infer_category(series_id: str, name: str, desc: str) -> tuple:
        """Infer category and subcategory from series metadata."""
        name_lower = name.lower()
        desc_lower = desc.lower()
        combined = f"{name_lower} {desc_lower}"

        # Employment-related
        if any(term in combined for term in ["unemployment", "payroll", "employment", "jobs", "labor", "wage", "earning", "claims"]):
            if "wage" in combined or "earning" in combined:
                return "employment", "wages"
            elif "claims" in combined:
                return "employment", "claims"
            elif "unemployment" in combined:
                return "employment", "unemployment"
            else:
                return "employment", "jobs"

        # Housing
        if any(term in combined for term in ["housing", "home", "house", "mortgage", "rent", "shelter", "permit", "construction"]):
            if "mortgage" in combined:
                return "housing", "mortgage"
            elif "rent" in combined or "shelter" in combined:
                return "housing", "rent"
            elif "price" in combined or "value" in combined:
                return "housing", "prices"
            elif "start" in combined or "permit" in combined:
                return "housing", "construction"
            else:
                return "housing", "general"

        # Inflation
        if any(term in combined for term in ["cpi", "inflation", "price index", "pce", "deflator"]):
            if "core" in combined:
                return "inflation", "core"
            elif "food" in combined:
                return "inflation", "food"
            elif "energy" in combined or "gas" in combined:
                return "inflation", "energy"
            elif "shelter" in combined:
                return "inflation", "shelter"
            else:
                return "inflation", "headline"

        # GDP
        if any(term in combined for term in ["gdp", "production", "industrial", "capacity"]):
            return "gdp", "growth"

        # Interest rates
        if any(term in combined for term in ["treasury", "yield", "fed fund", "interest rate"]):
            if "mortgage" in combined:
                return "interest_rates", "mortgage"
            elif "spread" in combined:
                return "interest_rates", "spread"
            else:
                return "interest_rates", "treasuries"

        # Financial markets
        if any(term in combined for term in ["s&p", "dow", "nasdaq", "stock", "vix", "volatility", "equity"]):
            return "financial_markets", "equities"

        # Consumer
        if any(term in combined for term in ["consumer", "retail", "spending", "sentiment", "saving"]):
            if "sentiment" in combined or "confidence" in combined:
                return "consumer", "sentiment"
            elif "retail" in combined:
                return "consumer", "retail"
            else:
                return "consumer", "spending"

        # Trade
        if any(term in combined for term in ["trade", "export", "import", "dollar index", "exchange"]):
            return "trade", "balance"

        # Energy
        if any(term in combined for term in ["oil", "crude", "gas", "energy", "coal", "petroleum"]):
            return "energy", "prices"

        # Government
        if any(term in combined for term in ["debt", "deficit", "government", "federal", "fiscal"]):
            if "debt" in combined:
                return "government", "debt"
            else:
                return "government", "spending"

        # Fed policy
        if any(term in combined for term in ["fomc", "projection", "dot plot", "sep"]):
            return "fed_policy", "projections"

        # Recession
        if any(term in combined for term in ["recession", "sahm", "leading"]):
            return "recession", "indicators"

        # Commodities
        if any(term in combined for term in ["gold", "silver", "commodity"]):
            return "financial_markets", "commodities"

        # Default
        return "other", "general"

    def infer_frequency(series_id: str, desc: str) -> str:
        """Infer frequency from series metadata."""
        desc_lower = desc.lower()
        if "daily" in desc_lower:
            return "daily"
        elif "weekly" in desc_lower:
            return "weekly"
        elif "quarterly" in desc_lower:
            return "quarterly"
        elif "annual" in desc_lower or "yearly" in desc_lower:
            return "annual"
        else:
            return "monthly"  # Default for most FRED series

    def infer_unit(name: str, desc: str) -> str:
        """Infer unit from series metadata."""
        combined = f"{name.lower()} {desc.lower()}"
        if "percent" in combined or "rate" in combined:
            return "percent"
        elif "dollar" in combined or "$" in combined or "price" in combined:
            return "dollars"
        elif "thousand" in combined:
            return "thousands"
        elif "million" in combined:
            return "millions"
        elif "billion" in combined:
            return "billions"
        elif "index" in combined:
            return "index"
        else:
            return "units"

    def infer_display(category: str, subcategory: str, name: str) -> str:
        """Infer how to display this series."""
        name_lower = name.lower()
        if "growth" in name_lower or "change" in name_lower:
            return "yoy_pct"
        elif category in ["employment", "gdp"] and "rate" not in name_lower:
            return "level"
        elif "rate" in name_lower or "percent" in name_lower:
            return "rate"
        else:
            return "level"

    def extract_keywords(name: str, desc: str) -> List[str]:
        """Extract keywords from series metadata."""
        combined = f"{name} {desc}".lower()
        # Remove common words
        stopwords = {"the", "a", "an", "of", "in", "for", "to", "and", "or", "is", "are", "was", "were", "be", "been", "has", "have", "had", "this", "that", "with"}
        words = re.findall(r'\b[a-z]+\b', combined)
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)
        return unique[:15]  # Limit to 15 keywords

    for series in FRED_SERIES_CATALOG:
        series_id = series.get("id", "")
        name = series.get("name", "")
        description = series.get("description", "")

        if not series_id or not name:
            continue

        category, subcategory = infer_category(series_id, name, description)
        frequency = infer_frequency(series_id, description)
        unit = infer_unit(name, description)
        display_as = infer_display(category, subcategory, name)
        keywords = extract_keywords(name, description)

        # Determine measure_type and change_type
        desc_lower = description.lower()
        name_lower = name.lower()

        if "real" in desc_lower or "inflation-adjusted" in desc_lower:
            measure_type = "real"
        elif "index" in desc_lower or "index" in name_lower:
            measure_type = "index"
        elif "rate" in name_lower:
            measure_type = "rate"
        else:
            measure_type = "nominal"

        if "year-over-year" in desc_lower or "yoy" in desc_lower:
            change_type = "yoy"
        elif "quarter-over-quarter" in desc_lower or "qoq" in desc_lower:
            change_type = "qoq"
        elif "month-over-month" in desc_lower or "mom" in desc_lower:
            change_type = "mom"
        else:
            change_type = "level"

        # Enhance description for better semantic search
        enhanced_desc = f"{description} This is a {frequency} {category} indicator from FRED (Federal Reserve Economic Data), published by BLS/BEA/Federal Reserve."

        entries[series_id] = CatalogEntry(
            id=series_id,
            name=name,
            source="fred",
            description=enhanced_desc,
            category=category,
            subcategory=subcategory,
            keywords=keywords,
            frequency=frequency,
            unit=unit,
            display_as=display_as,
            measure_type=measure_type,
            change_type=change_type,
        )

    return entries


def _build_zillow_entries() -> Dict[str, CatalogEntry]:
    """
    Build catalog entries from Zillow series catalog.

    Handles various Zillow series types:
    - National home values (ZHVI): prices
    - National rents (ZORI): rent
    - Regional home values/rents: regional_prices, regional_rent
    - Market metrics (inventory, days on market, etc.): inventory, market_speed, pricing
    - Property type splits (single family, condo): property_types
    - Price tiers (top/bottom tier): price_tiers
    - Affordability metrics: affordability
    """
    try:
        from agents.zillow import ZILLOW_SERIES
    except ImportError:
        ZILLOW_SERIES = {}

    entries = {}

    for series_id, info in ZILLOW_SERIES.items():
        name = info.get("name", series_id)
        description = info.get("description", "")
        frequency = info.get("frequency", "monthly")
        unit = info.get("units", "dollars")
        keywords = info.get("keywords", [])
        change_type = info.get("change_type", "level")
        measure_type = info.get("measure_type", "nominal")
        geography = info.get("geography", "national")

        # Determine category and subcategory based on series characteristics
        name_lower = name.lower()
        series_id_lower = series_id.lower()

        # All Zillow series are housing category
        category = "housing"

        # Determine subcategory based on series type
        if "inventory" in series_id_lower or "inventory" in name_lower:
            subcategory = "inventory"
        elif "new_listings" in series_id_lower or "new listings" in name_lower:
            subcategory = "inventory"
        elif "days_to_pending" in series_id_lower or "days to pending" in name_lower or "days on market" in name_lower:
            subcategory = "market_speed"
        elif "sale_to_list" in series_id_lower or "sale-to-list" in name_lower:
            subcategory = "pricing"
        elif "list_price" in series_id_lower or "list price" in name_lower:
            subcategory = "pricing"
        elif "sale_price" in series_id_lower or "sale price" in name_lower:
            subcategory = "pricing"
        elif "price_to_rent" in series_id_lower or "price-to-rent" in name_lower:
            subcategory = "affordability"
        elif "per_sqft" in series_id_lower or "per square foot" in name_lower:
            subcategory = "pricing"
        elif "top_tier" in series_id_lower or "top tier" in name_lower:
            subcategory = "price_tiers"
        elif "bottom_tier" in series_id_lower or "bottom tier" in name_lower:
            subcategory = "price_tiers"
        elif "_sfr" in series_id_lower or "single family" in name_lower:
            subcategory = "single_family"
        elif "_condo" in series_id_lower or "condo" in name_lower:
            subcategory = "condo"
        elif "zori" in series_id_lower or "rent" in name_lower:
            # Regional vs national rent
            if geography == "metro":
                subcategory = "regional_rent"
            else:
                subcategory = "rent"
        elif "zhvi" in series_id_lower or "home value" in name_lower:
            # Regional vs national home values
            if geography == "metro":
                subcategory = "regional_prices"
            else:
                subcategory = "prices"
        else:
            subcategory = "general"

        # Determine display_as
        if "yoy" in series_id_lower or change_type == "yoy":
            display_as = "yoy_pct"
        elif "ratio" in unit or "percent" in unit:
            display_as = "rate"
        else:
            display_as = "level"

        # Enhance description for semantic search with geography context
        if geography == "metro":
            region_filter = info.get("region_filter", "")
            geo_context = f"Metro-level data for {region_filter}."
        else:
            geo_context = "National-level data."

        enhanced_desc = f"{description} {geo_context} This is a {frequency} housing market indicator from Zillow Research, tracking actual market conditions. More timely than CPI shelter measures."

        entries[series_id] = CatalogEntry(
            id=series_id,
            name=name,
            source="zillow",
            description=enhanced_desc,
            category=category,
            subcategory=subcategory,
            keywords=keywords,
            frequency=frequency,
            unit=unit,
            display_as=display_as,
            measure_type=measure_type,
            change_type=change_type,
        )

    return entries


def _build_eia_entries() -> Dict[str, CatalogEntry]:
    """
    Build catalog entries from EIA series catalog.
    """
    try:
        from agents.eia import EIA_SERIES
    except ImportError:
        EIA_SERIES = {}

    entries = {}

    for series_id, info in EIA_SERIES.items():
        name = info.get("name", series_id)
        description = info.get("description", "")
        frequency = info.get("frequency", "weekly")
        unit = info.get("units", "units")
        keywords = info.get("keywords", [])
        change_type = info.get("change_type", "level")
        measure_type = info.get("measure_type", "nominal")
        fred_equivalent = info.get("fred_equivalent")

        # Determine subcategory based on name and keywords
        name_lower = name.lower()
        keywords_str = ' '.join(keywords).lower()
        combined = f"{name_lower} {keywords_str}"

        # Check specific categories first (order matters - more specific before general)
        if "natural gas" in name_lower or "lng" in name_lower or "henry hub" in name_lower:
            subcategory = "natural_gas"
        elif "coal" in name_lower:
            subcategory = "coal"
        elif "nuclear" in name_lower:
            subcategory = "nuclear"
        elif "solar" in name_lower or "photovoltaic" in combined:
            subcategory = "solar"
        elif "wind" in name_lower or "turbine" in combined:
            subcategory = "wind"
        elif "hydro" in name_lower or "hydroelectric" in name_lower:
            subcategory = "hydro"
        elif "ethanol" in name_lower or "biofuel" in combined:
            subcategory = "biofuels"
        elif "electricity" in name_lower or "generation" in name_lower:
            subcategory = "electricity"
        elif "crude" in name_lower or ("oil" in name_lower and "heating" not in name_lower):
            subcategory = "oil"
        elif "gasoline" in name_lower:
            subcategory = "gasoline"
        elif "diesel" in name_lower or "distillate" in name_lower:
            subcategory = "diesel"
        elif "heating oil" in name_lower or "propane" in name_lower:
            subcategory = "heating_fuels"
        elif "jet fuel" in name_lower or "aviation" in combined:
            subcategory = "jet_fuel"
        elif "refinery" in name_lower or "refining" in combined:
            subcategory = "refining"
        elif "stock" in name_lower or "inventory" in name_lower or "storage" in name_lower:
            subcategory = "inventories"
        elif "production" in name_lower:
            subcategory = "production"
        elif "import" in name_lower or "export" in name_lower:
            subcategory = "trade"
        elif "price" in name_lower:
            subcategory = "prices"
        else:
            subcategory = "general"

        # Enhance description for semantic search
        enhanced_desc = f"{description} This is a {frequency} energy indicator from the US Energy Information Administration (EIA). Provides timely data on US energy markets and prices."

        entries[series_id] = CatalogEntry(
            id=series_id,
            name=name,
            source="eia",
            description=enhanced_desc,
            category="energy",
            subcategory=subcategory,
            keywords=keywords,
            frequency=frequency,
            unit=unit,
            display_as="level",
            measure_type=measure_type,
            change_type=change_type,
            fred_equivalent=fred_equivalent,
        )

    return entries


def _build_alphavantage_entries() -> Dict[str, CatalogEntry]:
    """
    Build catalog entries from Alpha Vantage series catalog.
    """
    try:
        from agents.alphavantage import ALPHAVANTAGE_SERIES
    except ImportError:
        ALPHAVANTAGE_SERIES = {}

    entries = {}

    for series_id, info in ALPHAVANTAGE_SERIES.items():
        name = info.get("name", series_id)
        description = info.get("description", "")
        frequency = info.get("frequency", "daily")
        unit = info.get("units", "units")
        keywords = info.get("keywords", [])
        change_type = info.get("change_type", "level")
        measure_type = info.get("measure_type", "nominal")
        fred_equivalent = info.get("fred_equivalent")

        # Determine category and subcategory
        name_lower = name.lower()
        desc_lower = description.lower()

        # Sector ETFs - identify by sector keywords
        if any(term in name_lower for term in ["financial sector", "xlf"]):
            category = "financial_markets"
            subcategory = "sector_financials"
        elif any(term in name_lower for term in ["energy sector", "xle"]):
            category = "financial_markets"
            subcategory = "sector_energy"
        elif any(term in name_lower for term in ["healthcare sector", "xlv"]):
            category = "financial_markets"
            subcategory = "sector_healthcare"
        elif any(term in name_lower for term in ["technology sector", "xlk"]):
            category = "financial_markets"
            subcategory = "sector_technology"
        elif any(term in name_lower for term in ["industrial sector", "xli"]):
            category = "financial_markets"
            subcategory = "sector_industrials"
        elif any(term in name_lower for term in ["utilities sector", "xlu"]):
            category = "financial_markets"
            subcategory = "sector_utilities"
        elif any(term in name_lower for term in ["consumer staples", "xlp"]):
            category = "financial_markets"
            subcategory = "sector_staples"
        elif any(term in name_lower for term in ["consumer discretionary", "xly"]):
            category = "financial_markets"
            subcategory = "sector_discretionary"
        elif any(term in name_lower for term in ["materials sector", "xlb"]):
            category = "financial_markets"
            subcategory = "sector_materials"
        elif any(term in name_lower for term in ["real estate sector", "xlre"]):
            category = "financial_markets"
            subcategory = "sector_real_estate"
        elif any(term in name_lower for term in ["communications sector", "xlc"]):
            category = "financial_markets"
            subcategory = "sector_communications"

        # International ETFs
        elif any(term in name_lower for term in ["emerging markets", "eem", "vwo"]):
            category = "international"
            subcategory = "emerging_markets"
        elif any(term in name_lower for term in ["developed markets", "eafe", "efa"]):
            category = "international"
            subcategory = "developed_markets"
        elif any(term in name_lower for term in ["china", "fxi"]):
            category = "international"
            subcategory = "china"
        elif any(term in name_lower for term in ["japan", "ewj"]):
            category = "international"
            subcategory = "japan"
        elif any(term in name_lower for term in ["germany", "ewg"]):
            category = "international"
            subcategory = "germany"
        elif any(term in name_lower for term in ["united kingdom", "ewu"]) and "exchange" not in name_lower:
            category = "international"
            subcategory = "uk"

        # Bond ETFs
        elif any(term in name_lower for term in ["long-term treasuries", "tlt"]):
            category = "interest_rates"
            subcategory = "bonds_long"
        elif any(term in name_lower for term in ["short-term treasuries", "shy"]):
            category = "interest_rates"
            subcategory = "bonds_short"
        elif any(term in name_lower for term in ["intermediate treasuries", "ief"]):
            category = "interest_rates"
            subcategory = "bonds_intermediate"
        elif any(term in name_lower for term in ["high yield", "hyg", "junk"]):
            category = "interest_rates"
            subcategory = "bonds_high_yield"
        elif any(term in name_lower for term in ["investment grade", "lqd"]):
            category = "interest_rates"
            subcategory = "bonds_investment_grade"
        elif any(term in name_lower for term in ["aggregate bond", "agg"]):
            category = "interest_rates"
            subcategory = "bonds_aggregate"
        elif any(term in name_lower for term in ["tips", "inflation-protected"]):
            category = "interest_rates"
            subcategory = "bonds_tips"

        # Commodity ETFs
        elif any(term in name_lower for term in ["gold", "gld"]) and "exchange" not in name_lower:
            category = "financial_markets"
            subcategory = "commodities_gold"
        elif any(term in name_lower for term in ["silver", "slv"]):
            category = "financial_markets"
            subcategory = "commodities_silver"
        elif any(term in name_lower for term in ["crude oil", "uso"]) and "etf" in name_lower:
            category = "financial_markets"
            subcategory = "commodities_oil"
        elif any(term in name_lower for term in ["natural gas", "ung"]) and "etf" in name_lower:
            category = "financial_markets"
            subcategory = "commodities_gas"
        elif any(term in name_lower for term in ["agriculture", "dba"]):
            category = "financial_markets"
            subcategory = "commodities_agriculture"
        elif any(term in name_lower for term in ["commodities broad", "dbc"]):
            category = "financial_markets"
            subcategory = "commodities_broad"

        # Volatility ETFs
        elif any(term in name_lower for term in ["vix", "vixy", "uvxy", "vxx", "volatility"]):
            category = "financial_markets"
            subcategory = "volatility"

        # Major US equity indices
        elif any(term in name_lower for term in ["spy", "qqq", "dia", "iwm", "s&p", "nasdaq", "dow", "russell"]):
            category = "financial_markets"
            subcategory = "equities"

        # Treasury yields (individual yields, not bond ETFs)
        elif "treasury" in name_lower and "yield" in name_lower:
            category = "interest_rates"
            subcategory = "treasuries"

        # Economic indicators
        elif "gdp" in name_lower:
            category = "gdp"
            subcategory = "growth"
        elif "cpi" in name_lower or "inflation" in name_lower:
            category = "inflation"
            subcategory = "headline"
        elif "unemployment" in name_lower:
            category = "employment"
            subcategory = "unemployment"
        elif "fed" in name_lower and "fund" in name_lower:
            category = "interest_rates"
            subcategory = "fed_funds"
        elif "sentiment" in name_lower:
            category = "consumer"
            subcategory = "sentiment"
        elif "retail" in name_lower:
            category = "consumer"
            subcategory = "retail"
        elif "payroll" in name_lower:
            category = "employment"
            subcategory = "jobs"

        # Energy commodities (spot prices, not ETFs)
        elif "oil" in name_lower or "crude" in name_lower or "brent" in name_lower:
            category = "energy"
            subcategory = "oil"
        elif "natural gas" in name_lower:
            category = "energy"
            subcategory = "natural_gas"

        # Forex - check for exchange rate pattern
        elif "exchange rate" in name_lower or any(pair in series_id.lower() for pair in ["usd", "eur", "jpy", "gbp", "cad", "chf", "aud", "nzd", "mxn", "cny"]):
            category = "trade"
            subcategory = "forex"
        elif "dollar" in name_lower and "index" in name_lower:
            category = "trade"
            subcategory = "forex"

        else:
            category = "financial_markets"
            subcategory = "general"

        # Enhance description for semantic search
        enhanced_desc = f"{description} This is a {frequency} financial market indicator from Alpha Vantage, providing real-time and historical market data."

        entries[series_id] = CatalogEntry(
            id=series_id,
            name=name,
            source="alphavantage",
            description=enhanced_desc,
            category=category,
            subcategory=subcategory,
            keywords=keywords,
            frequency=frequency,
            unit=unit,
            display_as="level",
            measure_type=measure_type,
            change_type=change_type,
            fred_equivalent=fred_equivalent,
        )

    return entries


def _build_dbnomics_entries() -> Dict[str, CatalogEntry]:
    """
    Build catalog entries from DBnomics international series catalog.
    """
    try:
        from agents.dbnomics import INTERNATIONAL_SERIES
    except ImportError:
        INTERNATIONAL_SERIES = {}

    entries = {}

    for series_id, info in INTERNATIONAL_SERIES.items():
        name = info.get("name", series_id)
        description = info.get("description", "")
        frequency = info.get("frequency", "annual")
        keywords = info.get("keywords", [])
        change_type = info.get("change_type", "level")
        measure_type = info.get("measure_type", "nominal")
        provider = info.get("provider", "DBnomics")

        # Determine category and subcategory
        if "gdp" in series_id or "gdp" in name.lower():
            category = "international"
            subcategory = "gdp"
            unit = "percent"
        elif "inflation" in series_id or "inflation" in name.lower() or "cpi" in name.lower():
            category = "international"
            subcategory = "inflation"
            unit = "percent"
        elif "unemployment" in series_id or "unemployment" in name.lower():
            category = "international"
            subcategory = "unemployment"
            unit = "percent"
        elif "rate" in series_id or "rate" in name.lower():
            category = "interest_rates"
            subcategory = "policy_rates"
            unit = "percent"
        else:
            category = "international"
            subcategory = "general"
            unit = "units"

        # Determine display_as
        if change_type == "yoy":
            display_as = "yoy_pct"
        else:
            display_as = "level"

        # Enhance description for semantic search with country/region context
        country_keywords = ["eurozone", "euro area", "uk", "britain", "japan", "china", "germany", "canada", "mexico", "india", "brazil", "ecb"]
        country_match = [kw for kw in country_keywords if kw in series_id.lower() or kw in name.lower()]
        country_context = country_match[0].title() if country_match else "International"

        enhanced_desc = f"{description} This is {country_context} economic data from {provider} via DBnomics. Enables cross-country economic comparisons."

        entries[series_id] = CatalogEntry(
            id=series_id,
            name=name,
            source="dbnomics",
            description=enhanced_desc,
            category=category,
            subcategory=subcategory,
            keywords=keywords,
            frequency=frequency,
            unit=unit,
            display_as=display_as,
            measure_type=measure_type,
            change_type=change_type,
        )

    return entries


def _build_polymarket_entries() -> Dict[str, CatalogEntry]:
    """
    Build catalog entries from Polymarket prediction markets.

    Note: Polymarket provides forward-looking predictions, not historical data.
    """
    try:
        from agents.polymarket import ECONOMIC_EVENTS
    except ImportError:
        ECONOMIC_EVENTS = {}

    entries = {}

    for slug, info in ECONOMIC_EVENTS.items():
        display_name = info.get("display_name", slug)
        category_type = info.get("category", "predictions")
        keywords = info.get("keywords", [])
        market_type = info.get("market_type", "binary")

        # Determine category and subcategory based on market category
        if category_type == "recession":
            category = "recession"
            subcategory = "predictions"
            description = f"Polymarket prediction market for US recession probability. Forward-looking indicator based on trader sentiment and betting activity. Market type: {market_type}."
        elif category_type == "gdp":
            category = "gdp"
            subcategory = "predictions"
            description = f"Polymarket prediction market for GDP growth. Forward-looking indicator based on trader sentiment. Market type: {market_type}."
        elif category_type == "fed":
            category = "fed_policy"
            subcategory = "predictions"
            description = f"Polymarket prediction market for Federal Reserve rate decisions. Forward-looking indicator for Fed policy. Market type: {market_type}."
        elif category_type == "tariffs":
            category = "trade"
            subcategory = "predictions"
            description = f"Polymarket prediction market for tariff policy outcomes. Forward-looking indicator for trade policy. Market type: {market_type}."
        else:
            category = "predictions"
            subcategory = category_type
            description = f"Polymarket prediction market: {display_name}. Forward-looking market-based forecast. Market type: {market_type}."

        entries[f"polymarket_{slug}"] = CatalogEntry(
            id=f"polymarket_{slug}",
            name=display_name,
            source="polymarket",
            description=description,
            category=category,
            subcategory=subcategory,
            keywords=keywords + ["polymarket", "prediction", "forecast", "betting", "odds"],
            frequency="real-time",
            unit="probability",
            display_as="probability",
            measure_type="probability",
            change_type="level",
        )

    return entries


# =============================================================================
# BUILD THE UNIFIED CATALOG
# =============================================================================

def _build_unified_catalog() -> Dict[str, CatalogEntry]:
    """
    Build the complete unified catalog by aggregating all sources.

    Returns:
        Dictionary mapping series_id to CatalogEntry for all sources.
    """
    catalog = {}

    # Add entries from each source
    # Order matters for deduplication - FRED first as primary source
    fred_entries = _build_fred_entries()
    catalog.update(fred_entries)

    zillow_entries = _build_zillow_entries()
    catalog.update(zillow_entries)

    eia_entries = _build_eia_entries()
    catalog.update(eia_entries)

    alphavantage_entries = _build_alphavantage_entries()
    catalog.update(alphavantage_entries)

    dbnomics_entries = _build_dbnomics_entries()
    catalog.update(dbnomics_entries)

    polymarket_entries = _build_polymarket_entries()
    catalog.update(polymarket_entries)

    return catalog


# Build the catalog at module load time
UNIFIED_CATALOG: Dict[str, CatalogEntry] = _build_unified_catalog()


# =============================================================================
# SEARCH FUNCTIONS
# =============================================================================

def search_catalog(query: str, max_results: int = 20) -> List[CatalogEntry]:
    """
    Search the unified catalog by keyword.

    Performs case-insensitive keyword matching across:
    - Series name
    - Description
    - Keywords
    - Category and subcategory

    Args:
        query: Search query string (can contain multiple words)
        max_results: Maximum number of results to return

    Returns:
        List of matching CatalogEntry objects, sorted by relevance score

    Example:
        >>> results = search_catalog("unemployment rate")
        >>> for entry in results[:5]:
        ...     print(f"{entry.source}: {entry.name}")
    """
    query_lower = query.lower()
    query_terms = query_lower.split()

    results = []

    for series_id, entry in UNIFIED_CATALOG.items():
        # Build searchable text
        searchable = (
            f"{entry.name} {entry.description} "
            f"{' '.join(entry.keywords)} "
            f"{entry.category} {entry.subcategory}"
        ).lower()

        # Score based on term matches
        score = 0
        for term in query_terms:
            if term in searchable:
                # Boost for exact matches in name or keywords
                if term in entry.name.lower():
                    score += 5
                elif term in entry.keywords:
                    score += 3
                else:
                    score += 1

        # Boost for category/subcategory match
        if query_lower in entry.category or query_lower in entry.subcategory:
            score += 2

        if score > 0:
            results.append((entry, score))

    # Sort by score descending, then by name
    results.sort(key=lambda x: (-x[1], x[0].name))

    return [entry for entry, score in results[:max_results]]


def get_series_for_category(category: str, subcategory: Optional[str] = None) -> List[CatalogEntry]:
    """
    Get all series in a specific category (and optionally subcategory).

    Args:
        category: Category name (e.g., "employment", "housing", "inflation")
        subcategory: Optional subcategory name (e.g., "wages", "rent", "core")

    Returns:
        List of CatalogEntry objects in the category

    Example:
        >>> housing_series = get_series_for_category("housing")
        >>> rent_series = get_series_for_category("housing", "rent")
    """
    results = []
    category_lower = category.lower()
    subcategory_lower = subcategory.lower() if subcategory else None

    for series_id, entry in UNIFIED_CATALOG.items():
        if entry.category.lower() == category_lower:
            if subcategory_lower is None or entry.subcategory.lower() == subcategory_lower:
                results.append(entry)

    # Sort by source (FRED first), then name
    source_order = {"fred": 0, "zillow": 1, "eia": 2, "alphavantage": 3, "dbnomics": 4, "polymarket": 5}
    results.sort(key=lambda x: (source_order.get(x.source, 99), x.name))

    return results


def list_categories() -> List[str]:
    """
    List all available categories in the catalog.

    Returns:
        Sorted list of unique category names

    Example:
        >>> categories = list_categories()
        >>> print(categories)
        ['consumer', 'employment', 'energy', 'financial_markets', ...]
    """
    categories = set()
    for entry in UNIFIED_CATALOG.values():
        categories.add(entry.category)
    return sorted(categories)


def list_subcategories(category: str) -> List[str]:
    """
    List all subcategories within a category.

    Args:
        category: Category name

    Returns:
        Sorted list of unique subcategory names in that category

    Example:
        >>> subcats = list_subcategories("employment")
        >>> print(subcats)
        ['claims', 'jobs', 'unemployment', 'wages']
    """
    subcategories = set()
    category_lower = category.lower()
    for entry in UNIFIED_CATALOG.values():
        if entry.category.lower() == category_lower:
            subcategories.add(entry.subcategory)
    return sorted(subcategories)


def get_all_entries() -> List[CatalogEntry]:
    """
    Get all entries in the catalog.

    Returns:
        List of all CatalogEntry objects

    Example:
        >>> all_entries = get_all_entries()
        >>> print(f"Total series: {len(all_entries)}")
    """
    return list(UNIFIED_CATALOG.values())


def get_entry_by_id(series_id: str) -> Optional[CatalogEntry]:
    """
    Get a specific catalog entry by series ID.

    Args:
        series_id: The series identifier

    Returns:
        CatalogEntry if found, None otherwise

    Example:
        >>> entry = get_entry_by_id("UNRATE")
        >>> print(entry.description)
    """
    return UNIFIED_CATALOG.get(series_id)


def get_entries_by_source(source: str) -> List[CatalogEntry]:
    """
    Get all entries from a specific data source.

    Args:
        source: Data source name ("fred", "zillow", "eia", "alphavantage", "dbnomics", "polymarket")

    Returns:
        List of CatalogEntry objects from that source

    Example:
        >>> zillow_entries = get_entries_by_source("zillow")
        >>> print(f"Zillow series: {len(zillow_entries)}")
    """
    source_lower = source.lower()
    return [entry for entry in UNIFIED_CATALOG.values() if entry.source.lower() == source_lower]


def get_series_with_fred_equivalent() -> Dict[str, str]:
    """
    Get mapping of non-FRED series to their FRED equivalents.

    Useful for deduplication or preferring FRED data when available.

    Returns:
        Dictionary mapping source series ID to FRED series ID

    Example:
        >>> equivalents = get_series_with_fred_equivalent()
        >>> print(equivalents.get("eia_wti_crude"))  # "DCOILWTICO"
    """
    equivalents = {}
    for series_id, entry in UNIFIED_CATALOG.items():
        if entry.fred_equivalent and entry.source != "fred":
            equivalents[series_id] = entry.fred_equivalent
    return equivalents


# =============================================================================
# EMBEDDING EXPORT
# =============================================================================

def export_for_embeddings() -> List[Dict[str, str]]:
    """
    Export catalog entries in format suitable for embedding generation.

    Returns list of dicts with:
    - id: Series identifier
    - text_for_embedding: Combined text optimized for semantic search

    The text_for_embedding combines:
    - Series name
    - Enhanced description
    - Keywords
    - Category and subcategory context

    Returns:
        List of dicts ready for embedding API calls

    Example:
        >>> embedding_data = export_for_embeddings()
        >>> for item in embedding_data[:3]:
        ...     print(f"{item['id']}: {item['text_for_embedding'][:100]}...")
    """
    results = []

    for series_id, entry in UNIFIED_CATALOG.items():
        # Build comprehensive text for embedding
        keyword_text = ", ".join(entry.keywords)

        text_for_embedding = (
            f"{entry.name}. "
            f"{entry.description} "
            f"Category: {entry.category}, subcategory: {entry.subcategory}. "
            f"Data source: {entry.source}. "
            f"Frequency: {entry.frequency}. "
            f"Keywords: {keyword_text}."
        )

        results.append({
            "id": series_id,
            "source": entry.source,
            "text_for_embedding": text_for_embedding,
        })

    return results


def check_query_coverage(query: str, search_fred: bool = True) -> Dict[str, Any]:
    """
    Check how well we can answer a query with our available data.

    This is a safeguard against showing wrong data for out-of-left-field queries.
    If we don't have good coverage, we should tell the user rather than
    showing misleading data.

    IMPORTANT: FRED has 800,000+ series covering almost anything economic.
    When our curated catalog doesn't have a match, we search FRED's API
    to see if they have relevant data we haven't curated.

    Args:
        query: User's query string
        search_fred: Whether to search FRED API for uncurated series

    Returns:
        Dict with:
            - coverage: "strong", "partial", "fred_available", or "none"
            - confidence: float 0-1
            - best_matches: List of best matching series from catalog
            - fred_matches: List of FRED API search results (if searched)
            - suggested_proxy: What we could show as a proxy
            - message: User-facing message about coverage
            - search_terms: Suggested FRED search terms

    Example:
        >>> result = check_query_coverage("semiconductor production")
        >>> print(result['coverage'])  # "fred_available"
        >>> print(result['fred_matches'])  # [{'id': 'IPG3344S', 'title': 'Semiconductor...'}]
    """
    query_lower = query.lower()
    catalog_matches = search_catalog(query, max_results=10)

    # Extract key terms from query (nouns/concepts)
    stop_words = {
        'how', 'are', 'the', 'what', 'about', 'doing', 'with', 'for', 'and',
        'does', 'can', 'will', 'would', 'should', 'have', 'has', 'been',
        'being', 'were', 'was', 'this', 'that', 'these', 'those', 'from',
        'into', 'over', 'under', 'between', 'during', 'before', 'after',
        'above', 'below', 'there', 'here', 'where', 'when', 'why', 'which',
        'companies', 'company', 'firms', 'firm', 'doing', 'going', 'looking',
        'performing', 'rate', 'rates', 'level', 'levels', 'trend', 'trends',
    }
    query_terms = [
        w for w in query_lower.split()
        if len(w) > 3 and w not in stop_words
    ]

    # Check if any query term directly matches a keyword in our catalog
    direct_keyword_matches = []
    for term in query_terms:
        for entry in UNIFIED_CATALOG.values():
            if term in [k.lower() for k in entry.keywords]:
                direct_keyword_matches.append((term, entry))
                break

    # Search FRED API if we don't have strong catalog matches
    fred_matches = []
    if search_fred and len(direct_keyword_matches) == 0:
        try:
            # Import here to avoid circular imports
            import os
            from urllib.request import urlopen
            import json

            api_key = os.environ.get('FRED_API_KEY', '')
            if api_key and query_terms:
                # Build FRED search query
                search_query = ' '.join(query_terms[:3])  # Use top 3 terms
                url = f"https://api.stlouisfed.org/fred/series/search?search_text={search_query}&api_key={api_key}&file_type=json&limit=5"
                with urlopen(url, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    if 'seriess' in data:
                        fred_matches = [
                            {
                                'id': s['id'],
                                'title': s.get('title', ''),
                                'frequency': s.get('frequency_short', ''),
                                'units': s.get('units_short', ''),
                                'popularity': s.get('popularity', 0),
                            }
                            for s in data['seriess'][:5]
                        ]
        except Exception as e:
            # FRED search failed, continue without it
            pass

    # Calculate coverage based on catalog + FRED results
    if direct_keyword_matches:
        coverage = "strong"
        confidence = 0.9
        message = None  # No disclaimer needed
        suggested_proxy = None
    elif catalog_matches and len(catalog_matches) >= 3:
        # Check for known proxy situations
        proxy_situations = {
            'fintech': ('NASDAQCOM', 'tech sector metrics (NASDAQ, tech employment)'),
            'crypto': ('NASDAQCOM', 'tech sector as a proxy (no direct crypto data)'),
            'startups': ('BUSLOANS', 'small business indicators'),
            'venture': ('NASDAQCOM', 'tech stocks as a proxy'),
            'private equity': ('SP500', 'public market indicators'),
            'hedge fund': ('SP500', 'public market indicators'),
            'banks': ('USFIRE', 'financial sector employment and rates'),
            'insurance': ('USFIRE', 'financial sector data'),
            'real estate investment': ('HOUST', 'housing market indicators'),
        }

        proxy_match = None
        for term, (series, proxy_name) in proxy_situations.items():
            if term in query_lower:
                proxy_match = (term, series, proxy_name)
                break

        if proxy_match:
            term, series, proxy_name = proxy_match
            coverage = "partial"
            confidence = 0.5
            message = f"We don't have {term}-specific data. Showing {proxy_name}."
            suggested_proxy = series
        else:
            coverage = "partial"
            confidence = 0.6
            message = None
            suggested_proxy = None
    elif fred_matches:
        # We found data in FRED that's not in our catalog!
        coverage = "fred_available"
        confidence = 0.7
        top_fred = fred_matches[0]
        message = f"Found in FRED: {top_fred['title']} ({top_fred['id']})"
        suggested_proxy = top_fred['id']
    else:
        coverage = "none"
        confidence = 0.1
        message = f"No economic data found for this query. Try rephrasing with economic terms."
        suggested_proxy = None

    return {
        "coverage": coverage,
        "confidence": confidence,
        "best_matches": catalog_matches[:5],
        "fred_matches": fred_matches,
        "suggested_proxy": suggested_proxy,
        "message": message,
        "query_terms": query_terms,
        "direct_matches": len(direct_keyword_matches),
        "search_terms_for_fred": ' '.join(query_terms[:3]) if query_terms else query,
    }


def get_coverage_disclaimer(query: str) -> Optional[str]:
    """
    Get a user-facing disclaimer if we don't have strong coverage for a query.

    This is a simple wrapper around check_query_coverage for easy integration.

    Args:
        query: User's query string

    Returns:
        Disclaimer message string, or None if coverage is strong

    Example:
        >>> disclaimer = get_coverage_disclaimer("how are fintech companies doing?")
        >>> if disclaimer:
        ...     print(f"Note: {disclaimer}")
    """
    result = check_query_coverage(query)
    return result.get("message")


def get_catalog_stats() -> Dict[str, Any]:
    """
    Get statistics about the unified catalog.

    Returns:
        Dictionary with catalog statistics

    Example:
        >>> stats = get_catalog_stats()
        >>> print(f"Total series: {stats['total_series']}")
        >>> print(f"Sources: {stats['by_source']}")
    """
    stats = {
        "total_series": len(UNIFIED_CATALOG),
        "by_source": {},
        "by_category": {},
        "by_frequency": {},
    }

    for entry in UNIFIED_CATALOG.values():
        # Count by source
        stats["by_source"][entry.source] = stats["by_source"].get(entry.source, 0) + 1

        # Count by category
        stats["by_category"][entry.category] = stats["by_category"].get(entry.category, 0) + 1

        # Count by frequency
        stats["by_frequency"][entry.frequency] = stats["by_frequency"].get(entry.frequency, 0) + 1

    return stats


# =============================================================================
# MAIN / TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("EconStats Unified Data Catalog")
    print("=" * 70)

    # Get catalog stats
    stats = get_catalog_stats()
    print(f"\nTotal series in catalog: {stats['total_series']}")

    print("\nSeries by source:")
    for source, count in sorted(stats['by_source'].items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")

    print("\nSeries by category:")
    for category, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
        print(f"  {category}: {count}")

    print("\n" + "-" * 70)
    print("Search Test: 'inflation housing rent'")
    print("-" * 70)
    results = search_catalog("inflation housing rent", max_results=10)
    for entry in results:
        print(f"  [{entry.source}] {entry.id}: {entry.name}")

    print("\n" + "-" * 70)
    print("Category Test: 'employment' series")
    print("-" * 70)
    employment_series = get_series_for_category("employment")
    print(f"  Found {len(employment_series)} employment series")
    for entry in employment_series[:5]:
        print(f"    [{entry.source}] {entry.id}: {entry.name}")

    print("\n" + "-" * 70)
    print("Embedding Export Sample")
    print("-" * 70)
    embedding_data = export_for_embeddings()
    print(f"  Total entries for embedding: {len(embedding_data)}")
    if embedding_data:
        sample = embedding_data[0]
        print(f"\n  Sample entry:")
        print(f"    ID: {sample['id']}")
        print(f"    Text: {sample['text_for_embedding'][:200]}...")

    print("\n" + "=" * 70)
    print("Catalog build complete!")
    print("=" * 70)
