"""
Unified Data Inventory for EconStats.

This module provides a single source of truth for all available data series
across all sources (FRED, Zillow, EIA, Alpha Vantage, DBnomics, Polymarket).

The key insight: organize by CONCEPT (what the data measures), not by SOURCE.
This enables queries like "What do we have for housing?" to return series from
FRED, Zillow, and Alpha Vantage together.

Usage:
    from core.data_inventory import (
        get_series_for_concept,
        find_series_by_keyword,
        get_concept_for_query,
        DATA_INVENTORY,
    )

    # Get all housing-related series
    housing_series = get_series_for_concept("housing")

    # Find series matching a keyword
    matches = find_series_by_keyword("unemployment")

    # Get concept from natural language
    concept = get_concept_for_query("how are home prices?")  # -> "housing.prices"
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class DataSource(Enum):
    """Available data sources."""
    FRED = "fred"
    DBNOMICS = "dbnomics"
    ZILLOW = "zillow"
    EIA = "eia"
    ALPHAVANTAGE = "alphavantage"
    POLYMARKET = "polymarket"


class MeasureType(Enum):
    """How the series is measured."""
    RATE = "rate"           # Percentages (unemployment rate)
    INDEX = "index"         # Index values (CPI, S&P 500)
    LEVEL = "level"         # Absolute levels (GDP in dollars)
    COUNT = "count"         # Counts (payrolls in thousands)
    RATIO = "ratio"         # Ratios (job openings per unemployed)


class DisplayTransform(Enum):
    """How to transform for display."""
    AS_IS = "as_is"         # Show raw value
    YOY_PCT = "yoy_pct"     # Year-over-year percent change
    MOM_PCT = "mom_pct"     # Month-over-month percent change
    QOQ_PCT = "qoq_pct"     # Quarter-over-quarter percent change


@dataclass
class SeriesInfo:
    """Metadata for a single data series."""
    id: str                              # Series ID (e.g., "UNRATE", "SP500")
    name: str                            # Human-readable name
    source: DataSource                   # Where to fetch from
    measure_type: MeasureType            # How it's measured
    display_transform: DisplayTransform  # How to show it
    frequency: str                       # "daily", "weekly", "monthly", "quarterly"
    keywords: List[str] = field(default_factory=list)  # Search keywords
    description: str = ""                # Longer description
    unit: str = ""                       # Unit of measurement
    is_primary: bool = True              # Is this the preferred source for this concept?


# =============================================================================
# THE DATA INVENTORY
# Organized by economic CONCEPT, not by data source.
# =============================================================================

DATA_INVENTORY: Dict[str, Dict] = {
    # =========================================================================
    # EMPLOYMENT & LABOR MARKET
    # =========================================================================
    "employment": {
        "description": "Jobs, unemployment, and labor market conditions",
        "keywords": ["jobs", "labor", "workers", "workforce", "employment"],
        "subcategories": {
            "unemployment": {
                "description": "Unemployment rates",
                "keywords": ["unemployment", "jobless", "unemployed"],
                "series": {
                    "UNRATE": SeriesInfo(
                        id="UNRATE", name="Unemployment Rate (U-3)",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["unemployment", "jobless", "u3"],
                        unit="Percent"
                    ),
                    "U6RATE": SeriesInfo(
                        id="U6RATE", name="Unemployment Rate (U-6)",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["unemployment", "underemployment", "u6"],
                        unit="Percent"
                    ),
                    "ICSA": SeriesInfo(
                        id="ICSA", name="Initial Jobless Claims",
                        source=DataSource.FRED, measure_type=MeasureType.COUNT,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["claims", "layoffs", "jobless"],
                        unit="Thousands"
                    ),
                },
            },
            "job_creation": {
                "description": "Payrolls and job growth",
                "keywords": ["payrolls", "jobs", "hiring", "employment"],
                "series": {
                    "PAYEMS": SeriesInfo(
                        id="PAYEMS", name="Total Nonfarm Payrolls",
                        source=DataSource.FRED, measure_type=MeasureType.COUNT,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["payrolls", "jobs", "employment", "nonfarm"],
                        unit="Thousands"
                    ),
                    "JTSJOL": SeriesInfo(
                        id="JTSJOL", name="Job Openings",
                        source=DataSource.FRED, measure_type=MeasureType.COUNT,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["openings", "jolts", "vacancies"],
                        unit="Thousands"
                    ),
                },
            },
            "wages": {
                "description": "Earnings and compensation",
                "keywords": ["wages", "earnings", "pay", "compensation", "salary"],
                "series": {
                    "CES0500000003": SeriesInfo(
                        id="CES0500000003", name="Average Hourly Earnings",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["wages", "earnings", "hourly", "pay"],
                        unit="Dollars per Hour"
                    ),
                    "AHETPI": SeriesInfo(
                        id="AHETPI", name="Avg Hourly Earnings (Production Workers)",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["wages", "production", "workers"],
                        unit="Dollars per Hour"
                    ),
                },
            },
            "participation": {
                "description": "Labor force participation",
                "keywords": ["participation", "labor force", "workforce"],
                "series": {
                    "CIVPART": SeriesInfo(
                        id="CIVPART", name="Labor Force Participation Rate",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["participation", "labor force"],
                        unit="Percent"
                    ),
                    "LNS12300060": SeriesInfo(
                        id="LNS12300060", name="Prime-Age Employment-Population Ratio",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["prime age", "epop", "employment ratio"],
                        unit="Percent"
                    ),
                },
            },
            "demographics": {
                "description": "Employment by demographic group",
                "keywords": ["black", "hispanic", "women", "men", "demographic"],
                "series": {
                    "LNS14000006": SeriesInfo(
                        id="LNS14000006", name="Unemployment Rate - Black",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["black", "african american", "unemployment"],
                        unit="Percent"
                    ),
                    "LNS14000009": SeriesInfo(
                        id="LNS14000009", name="Unemployment Rate - Hispanic",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["hispanic", "latino", "unemployment"],
                        unit="Percent"
                    ),
                    "LNS14000002": SeriesInfo(
                        id="LNS14000002", name="Unemployment Rate - Women",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["women", "female", "unemployment"],
                        unit="Percent"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # INFLATION & PRICES
    # =========================================================================
    "inflation": {
        "description": "Consumer prices and inflation measures",
        "keywords": ["inflation", "prices", "cpi", "pce", "cost of living"],
        "subcategories": {
            "headline": {
                "description": "Overall inflation measures",
                "keywords": ["headline", "overall", "total"],
                "series": {
                    "CPIAUCSL": SeriesInfo(
                        id="CPIAUCSL", name="Consumer Price Index (CPI)",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["cpi", "inflation", "consumer prices"],
                        unit="Index 1982-84=100"
                    ),
                    "PCEPI": SeriesInfo(
                        id="PCEPI", name="PCE Price Index",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["pce", "inflation", "fed preferred"],
                        unit="Index 2017=100"
                    ),
                },
            },
            "core": {
                "description": "Core inflation (ex food & energy)",
                "keywords": ["core", "underlying", "ex food energy"],
                "series": {
                    "CPILFESL": SeriesInfo(
                        id="CPILFESL", name="Core CPI (ex Food & Energy)",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["core", "cpi", "ex food energy"],
                        unit="Index 1982-84=100"
                    ),
                    "PCEPILFE": SeriesInfo(
                        id="PCEPILFE", name="Core PCE (ex Food & Energy)",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["core", "pce", "fed target"],
                        unit="Index 2017=100"
                    ),
                },
            },
            "shelter": {
                "description": "Housing and rent inflation",
                "keywords": ["shelter", "rent", "housing", "oer"],
                "series": {
                    "CUSR0000SAH1": SeriesInfo(
                        id="CUSR0000SAH1", name="Shelter CPI",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["shelter", "housing", "rent", "oer"],
                        unit="Index"
                    ),
                    "CPIHOSSL": SeriesInfo(
                        id="CPIHOSSL", name="CPI Housing",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["housing", "shelter"],
                        unit="Index"
                    ),
                },
            },
            "food": {
                "description": "Food prices",
                "keywords": ["food", "groceries", "dining"],
                "series": {
                    "CUSR0000SAF11": SeriesInfo(
                        id="CUSR0000SAF11", name="Food at Home CPI",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["food", "groceries", "supermarket"],
                        unit="Index"
                    ),
                    "CUSR0000SEFV": SeriesInfo(
                        id="CUSR0000SEFV", name="Food Away from Home CPI",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["restaurants", "dining", "food away"],
                        unit="Index"
                    ),
                },
            },
            "expectations": {
                "description": "Inflation expectations",
                "keywords": ["expectations", "breakeven", "tips"],
                "series": {
                    "T5YIE": SeriesInfo(
                        id="T5YIE", name="5-Year Breakeven Inflation",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["breakeven", "expectations", "tips"],
                        unit="Percent"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # GDP & ECONOMIC GROWTH
    # =========================================================================
    "growth": {
        "description": "Economic output and growth",
        "keywords": ["gdp", "growth", "economy", "output", "production"],
        "subcategories": {
            "gdp": {
                "description": "Gross Domestic Product",
                "keywords": ["gdp", "gross domestic product"],
                "series": {
                    "A191RO1Q156NBEA": SeriesInfo(
                        id="A191RO1Q156NBEA", name="Real GDP Growth (YoY)",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="quarterly",
                        keywords=["gdp", "growth", "yoy"],
                        unit="Percent"
                    ),
                    "A191RL1Q225SBEA": SeriesInfo(
                        id="A191RL1Q225SBEA", name="Real GDP Growth (Quarterly)",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="quarterly",
                        keywords=["gdp", "growth", "quarterly", "annualized"],
                        unit="Percent"
                    ),
                    "GDPC1": SeriesInfo(
                        id="GDPC1", name="Real GDP Level",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="quarterly",
                        keywords=["gdp", "real", "level"],
                        unit="Billions of Chained 2017 Dollars"
                    ),
                },
            },
            "production": {
                "description": "Industrial production",
                "keywords": ["production", "industrial", "manufacturing", "output"],
                "series": {
                    "INDPRO": SeriesInfo(
                        id="INDPRO", name="Industrial Production Index",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["industrial", "production", "manufacturing"],
                        unit="Index 2017=100"
                    ),
                    "TCU": SeriesInfo(
                        id="TCU", name="Capacity Utilization",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["capacity", "utilization", "slack"],
                        unit="Percent"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # HOUSING MARKET
    # =========================================================================
    "housing": {
        "description": "Housing market data",
        "keywords": ["housing", "home", "house", "real estate", "property"],
        "subcategories": {
            "prices": {
                "description": "Home prices and values",
                "keywords": ["prices", "values", "appreciation"],
                "series": {
                    "CSUSHPINSA": SeriesInfo(
                        id="CSUSHPINSA", name="Case-Shiller Home Price Index",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["case shiller", "home prices", "appreciation"],
                        unit="Index"
                    ),
                    "MSPUS": SeriesInfo(
                        id="MSPUS", name="Median Home Sale Price",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="quarterly",
                        keywords=["median", "home price", "sale price"],
                        unit="Dollars"
                    ),
                    "zillow_zhvi_national": SeriesInfo(
                        id="zillow_zhvi_national", name="Zillow Home Value Index",
                        source=DataSource.ZILLOW, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["zillow", "home value", "zhvi"],
                        unit="Dollars"
                    ),
                },
            },
            "rents": {
                "description": "Rental market",
                "keywords": ["rent", "rental", "lease", "tenant"],
                "series": {
                    "zillow_zori_national": SeriesInfo(
                        id="zillow_zori_national", name="Zillow Observed Rent Index",
                        source=DataSource.ZILLOW, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["zillow", "rent", "zori", "market rent"],
                        unit="Dollars"
                    ),
                    "CUSR0000SAH1": SeriesInfo(
                        id="CUSR0000SAH1", name="Shelter CPI (Rent Proxy)",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["rent", "shelter", "cpi"],
                        unit="Index",
                        is_primary=False
                    ),
                },
            },
            "construction": {
                "description": "Housing construction",
                "keywords": ["construction", "building", "starts", "permits"],
                "series": {
                    "HOUST": SeriesInfo(
                        id="HOUST", name="Housing Starts",
                        source=DataSource.FRED, measure_type=MeasureType.COUNT,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["starts", "construction", "new homes"],
                        unit="Thousands of Units"
                    ),
                    "PERMIT": SeriesInfo(
                        id="PERMIT", name="Building Permits",
                        source=DataSource.FRED, measure_type=MeasureType.COUNT,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["permits", "construction", "building"],
                        unit="Thousands of Units"
                    ),
                },
            },
            "sales": {
                "description": "Home sales",
                "keywords": ["sales", "transactions", "closings"],
                "series": {
                    "EXHOSLUSM495S": SeriesInfo(
                        id="EXHOSLUSM495S", name="Existing Home Sales",
                        source=DataSource.FRED, measure_type=MeasureType.COUNT,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["existing", "sales", "resale"],
                        unit="Thousands of Units"
                    ),
                },
            },
            "affordability": {
                "description": "Housing affordability",
                "keywords": ["affordability", "mortgage", "rates"],
                "series": {
                    "MORTGAGE30US": SeriesInfo(
                        id="MORTGAGE30US", name="30-Year Mortgage Rate",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["mortgage", "30 year", "rate"],
                        unit="Percent"
                    ),
                    "MORTGAGE15US": SeriesInfo(
                        id="MORTGAGE15US", name="15-Year Mortgage Rate",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["mortgage", "15 year", "rate"],
                        unit="Percent"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # FINANCIAL MARKETS & STOCKS
    # =========================================================================
    "markets": {
        "description": "Stock market and financial indicators",
        "keywords": ["stocks", "market", "equities", "wall street", "shares"],
        "subcategories": {
            "equities": {
                "description": "Stock market indices",
                "keywords": ["stocks", "equities", "indices", "s&p", "nasdaq", "dow"],
                "series": {
                    "SP500": SeriesInfo(
                        id="SP500", name="S&P 500 Index",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["sp500", "s&p", "stocks", "large cap"],
                        unit="Index"
                    ),
                    "NASDAQCOM": SeriesInfo(
                        id="NASDAQCOM", name="NASDAQ Composite",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["nasdaq", "tech", "stocks"],
                        unit="Index"
                    ),
                    "DJIA": SeriesInfo(
                        id="DJIA", name="Dow Jones Industrial Average",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["dow", "djia", "blue chip"],
                        unit="Index"
                    ),
                },
            },
            "volatility": {
                "description": "Market volatility",
                "keywords": ["volatility", "vix", "fear"],
                "series": {
                    "VIXCLS": SeriesInfo(
                        id="VIXCLS", name="VIX (Volatility Index)",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["vix", "volatility", "fear"],
                        unit="Index"
                    ),
                },
            },
            "bonds": {
                "description": "Treasury yields and spreads",
                "keywords": ["treasury", "yields", "bonds", "rates"],
                "series": {
                    "DGS10": SeriesInfo(
                        id="DGS10", name="10-Year Treasury Yield",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["10 year", "treasury", "yield"],
                        unit="Percent"
                    ),
                    "DGS2": SeriesInfo(
                        id="DGS2", name="2-Year Treasury Yield",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["2 year", "treasury", "yield"],
                        unit="Percent"
                    ),
                    "T10Y2Y": SeriesInfo(
                        id="T10Y2Y", name="10Y-2Y Treasury Spread",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["yield curve", "spread", "inversion"],
                        unit="Percent"
                    ),
                },
            },
            "corporate": {
                "description": "Corporate indicators",
                "keywords": ["corporate", "profits", "business", "earnings"],
                "series": {
                    "CP": SeriesInfo(
                        id="CP", name="Corporate Profits",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="quarterly",
                        keywords=["profits", "earnings", "corporate"],
                        unit="Billions of Dollars"
                    ),
                    "BUSLOANS": SeriesInfo(
                        id="BUSLOANS", name="Commercial & Industrial Loans",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="weekly",
                        keywords=["business loans", "credit", "lending"],
                        unit="Billions of Dollars"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # FED & MONETARY POLICY
    # =========================================================================
    "fed": {
        "description": "Federal Reserve and monetary policy",
        "keywords": ["fed", "federal reserve", "fomc", "powell", "monetary policy"],
        "subcategories": {
            "rates": {
                "description": "Policy rates",
                "keywords": ["fed funds", "interest rate", "policy rate"],
                "series": {
                    "FEDFUNDS": SeriesInfo(
                        id="FEDFUNDS", name="Federal Funds Rate",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["fed funds", "policy rate", "fomc"],
                        unit="Percent"
                    ),
                    "DFEDTARU": SeriesInfo(
                        id="DFEDTARU", name="Fed Funds Target (Upper)",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["target", "fed funds", "upper"],
                        unit="Percent"
                    ),
                },
            },
            "balance_sheet": {
                "description": "Fed balance sheet",
                "keywords": ["balance sheet", "assets", "qe", "qt"],
                "series": {
                    "WALCL": SeriesInfo(
                        id="WALCL", name="Fed Total Assets",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["balance sheet", "assets", "qe"],
                        unit="Millions of Dollars"
                    ),
                    "M2SL": SeriesInfo(
                        id="M2SL", name="M2 Money Supply",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["money supply", "m2", "liquidity"],
                        unit="Billions of Dollars"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # CONSUMER
    # =========================================================================
    "consumer": {
        "description": "Consumer spending and sentiment",
        "keywords": ["consumer", "spending", "sentiment", "confidence", "retail"],
        "subcategories": {
            "sentiment": {
                "description": "Consumer confidence",
                "keywords": ["sentiment", "confidence", "mood"],
                "series": {
                    "UMCSENT": SeriesInfo(
                        id="UMCSENT", name="Consumer Sentiment (U of M)",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["sentiment", "confidence", "michigan"],
                        unit="Index"
                    ),
                },
            },
            "spending": {
                "description": "Consumer spending",
                "keywords": ["spending", "consumption", "retail", "purchases"],
                "series": {
                    "PCE": SeriesInfo(
                        id="PCE", name="Personal Consumption Expenditures",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["pce", "consumption", "spending"],
                        unit="Billions of Dollars"
                    ),
                    "RSXFS": SeriesInfo(
                        id="RSXFS", name="Retail Sales (ex Food Services)",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["retail", "sales", "shopping"],
                        unit="Millions of Dollars"
                    ),
                },
            },
            "income": {
                "description": "Personal income",
                "keywords": ["income", "earnings", "disposable"],
                "series": {
                    "DSPIC96": SeriesInfo(
                        id="DSPIC96", name="Real Disposable Personal Income",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.YOY_PCT, frequency="monthly",
                        keywords=["income", "disposable", "real"],
                        unit="Billions of Chained 2017 Dollars"
                    ),
                    "PSAVERT": SeriesInfo(
                        id="PSAVERT", name="Personal Saving Rate",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["savings", "saving rate"],
                        unit="Percent"
                    ),
                },
            },
        },
    },

    # =========================================================================
    # ENERGY
    # =========================================================================
    "energy": {
        "description": "Energy prices and production",
        "keywords": ["energy", "oil", "gas", "fuel", "petroleum"],
        "subcategories": {
            "oil": {
                "description": "Crude oil",
                "keywords": ["oil", "crude", "wti", "brent"],
                "series": {
                    "DCOILWTICO": SeriesInfo(
                        id="DCOILWTICO", name="WTI Crude Oil Price",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["oil", "wti", "crude"],
                        unit="Dollars per Barrel"
                    ),
                    "eia_wti_crude": SeriesInfo(
                        id="eia_wti_crude", name="WTI Crude (EIA)",
                        source=DataSource.EIA, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["oil", "wti", "eia"],
                        unit="Dollars per Barrel",
                        is_primary=False
                    ),
                },
            },
            "gasoline": {
                "description": "Gasoline prices",
                "keywords": ["gas", "gasoline", "fuel", "pump"],
                "series": {
                    "GASREGW": SeriesInfo(
                        id="GASREGW", name="Regular Gas Price",
                        source=DataSource.FRED, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["gas", "gasoline", "pump"],
                        unit="Dollars per Gallon"
                    ),
                    "eia_gasoline_retail": SeriesInfo(
                        id="eia_gasoline_retail", name="Retail Gasoline (EIA)",
                        source=DataSource.EIA, measure_type=MeasureType.LEVEL,
                        display_transform=DisplayTransform.AS_IS, frequency="weekly",
                        keywords=["gas", "gasoline", "retail"],
                        unit="Dollars per Gallon",
                        is_primary=False
                    ),
                },
            },
        },
    },

    # =========================================================================
    # RECESSION INDICATORS
    # =========================================================================
    "recession": {
        "description": "Recession risk indicators",
        "keywords": ["recession", "downturn", "contraction", "crisis"],
        "subcategories": {
            "indicators": {
                "description": "Leading recession indicators",
                "keywords": ["sahm", "yield curve", "leading"],
                "series": {
                    "SAHMREALTIME": SeriesInfo(
                        id="SAHMREALTIME", name="Sahm Rule Recession Indicator",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["sahm", "recession", "trigger"],
                        unit="Percentage Points"
                    ),
                    "T10Y2Y": SeriesInfo(
                        id="T10Y2Y", name="Yield Curve (10Y-2Y)",
                        source=DataSource.FRED, measure_type=MeasureType.RATE,
                        display_transform=DisplayTransform.AS_IS, frequency="daily",
                        keywords=["yield curve", "inversion", "recession"],
                        unit="Percent"
                    ),
                    "USREC": SeriesInfo(
                        id="USREC", name="NBER Recession Indicator",
                        source=DataSource.FRED, measure_type=MeasureType.INDEX,
                        display_transform=DisplayTransform.AS_IS, frequency="monthly",
                        keywords=["nber", "recession", "official"],
                        unit="Binary"
                    ),
                },
            },
        },
    },
}


# =============================================================================
# QUERY FUNCTIONS
# =============================================================================

def _collect_series_from_node(node: dict) -> List[SeriesInfo]:
    """Recursively collect all series from a node."""
    series = []
    if "series" in node:
        series.extend(node["series"].values())
    if "subcategories" in node:
        for sub in node["subcategories"].values():
            series.extend(_collect_series_from_node(sub))
    return series


def _all_series() -> List[SeriesInfo]:
    """Get all series across the entire inventory."""
    all_series = []
    for category in DATA_INVENTORY.values():
        all_series.extend(_collect_series_from_node(category))
    return all_series


def get_series_for_concept(concept: str) -> List[SeriesInfo]:
    """
    Get all series for a concept path like "housing" or "housing.prices".

    Args:
        concept: Dot-separated concept path (e.g., "housing.rents")

    Returns:
        List of SeriesInfo for all matching series
    """
    parts = concept.lower().split(".")
    node = DATA_INVENTORY

    for part in parts:
        if part in node:
            node = node[part]
        elif "subcategories" in node and part in node["subcategories"]:
            node = node["subcategories"][part]
        else:
            return []

    return _collect_series_from_node(node)


def get_primary_series_for_concept(concept: str) -> List[SeriesInfo]:
    """Get only the primary (preferred) series for a concept."""
    all_series = get_series_for_concept(concept)
    return [s for s in all_series if s.is_primary]


def find_series_by_keyword(keyword: str) -> List[SeriesInfo]:
    """Find series matching a keyword across all concepts."""
    keyword_lower = keyword.lower()
    matches = []

    for series_info in _all_series():
        if (keyword_lower in series_info.keywords or
            keyword_lower in series_info.name.lower() or
            keyword_lower in series_info.description.lower()):
            matches.append(series_info)

    return matches


def get_series_by_id(series_id: str) -> Optional[SeriesInfo]:
    """Get a specific series by its ID."""
    for series_info in _all_series():
        if series_info.id == series_id:
            return series_info
    return None


def list_all_concepts() -> List[str]:
    """List all top-level concepts."""
    return list(DATA_INVENTORY.keys())


def list_subconcepts(concept: str) -> List[str]:
    """List subconcepts for a given concept."""
    if concept in DATA_INVENTORY:
        node = DATA_INVENTORY[concept]
        if "subcategories" in node:
            return list(node["subcategories"].keys())
    return []


def get_concept_keywords(concept: str) -> List[str]:
    """Get all keywords associated with a concept."""
    parts = concept.lower().split(".")
    node = DATA_INVENTORY
    keywords = []

    for part in parts:
        if part in node:
            node = node[part]
            keywords.extend(node.get("keywords", []))
        elif "subcategories" in node and part in node["subcategories"]:
            node = node["subcategories"][part]
            keywords.extend(node.get("keywords", []))

    return keywords


def what_do_we_have(topic: str) -> str:
    """
    Natural language answer to "What data do we have for X?"

    Args:
        topic: Topic to search for

    Returns:
        Human-readable summary of available data
    """
    series_list = get_series_for_concept(topic)
    if not series_list:
        # Try keyword search
        series_list = find_series_by_keyword(topic)

    if not series_list:
        return f"No data found for '{topic}'"

    # Group by source
    by_source = {}
    for s in series_list:
        source_name = s.source.value.upper()
        if source_name not in by_source:
            by_source[source_name] = []
        by_source[source_name].append(s.name)

    lines = [f"For {topic}, we have:"]
    for source, names in by_source.items():
        names_str = ", ".join(names[:4])
        if len(names) > 4:
            names_str += f"... (+{len(names)-4} more)"
        lines.append(f"  {source}: {names_str}")

    return "\n".join(lines)


# =============================================================================
# CONCEPT MATCHING FROM NATURAL LANGUAGE
# =============================================================================

# Mapping of natural language terms to concept paths
CONCEPT_ALIASES = {
    # Employment
    "jobs": "employment",
    "labor": "employment",
    "workers": "employment",
    "workforce": "employment",
    "unemployment": "employment.unemployment",
    "jobless": "employment.unemployment",
    "payrolls": "employment.job_creation",
    "hiring": "employment.job_creation",
    "wages": "employment.wages",
    "earnings": "employment.wages",
    "pay": "employment.wages",
    "salary": "employment.wages",
    "participation": "employment.participation",

    # Inflation
    "inflation": "inflation",
    "prices": "inflation",
    "cpi": "inflation.headline",
    "pce": "inflation.headline",
    "core inflation": "inflation.core",
    "shelter": "inflation.shelter",
    "rent inflation": "inflation.shelter",
    "food prices": "inflation.food",

    # Growth
    "gdp": "growth.gdp",
    "growth": "growth",
    "economy": "growth",
    "production": "growth.production",
    "industrial": "growth.production",
    "manufacturing": "growth.production",

    # Housing
    "housing": "housing",
    "home prices": "housing.prices",
    "house prices": "housing.prices",
    "real estate": "housing",
    "rents": "housing.rents",
    "rental": "housing.rents",
    "mortgage": "housing.affordability",
    "housing starts": "housing.construction",
    "construction": "housing.construction",

    # Markets
    "stocks": "markets.equities",
    "stock market": "markets.equities",
    "equities": "markets.equities",
    "s&p": "markets.equities",
    "nasdaq": "markets.equities",
    "dow": "markets.equities",
    "wall street": "markets.equities",
    "vix": "markets.volatility",
    "volatility": "markets.volatility",
    "treasury": "markets.bonds",
    "yields": "markets.bonds",
    "bonds": "markets.bonds",
    "yield curve": "markets.bonds",
    "corporate profits": "markets.corporate",
    "profits": "markets.corporate",

    # Corporate / Business
    "megacap": "markets.equities",
    "large cap": "markets.equities",
    "corporations": "markets.equities",
    "corporate": "markets.corporate",
    "big companies": "markets.equities",
    "large firms": "markets.equities",
    "firms": "markets.equities",
    "business": "markets.corporate",
    "small business": "consumer",  # Will need dedicated section

    # Fed
    "fed": "fed",
    "federal reserve": "fed",
    "fomc": "fed",
    "interest rates": "fed.rates",
    "fed funds": "fed.rates",
    "monetary policy": "fed",

    # Consumer
    "consumer": "consumer",
    "spending": "consumer.spending",
    "retail": "consumer.spending",
    "sentiment": "consumer.sentiment",
    "confidence": "consumer.sentiment",
    "income": "consumer.income",
    "savings": "consumer.income",

    # Energy
    "energy": "energy",
    "oil": "energy.oil",
    "crude": "energy.oil",
    "gas": "energy.gasoline",
    "gasoline": "energy.gasoline",
    "fuel": "energy.gasoline",

    # Recession
    "recession": "recession",
    "downturn": "recession",
    "contraction": "recession",
    "sahm": "recession.indicators",
}


def get_concept_for_query(query: str) -> Optional[str]:
    """
    Extract the most relevant concept from a natural language query.

    Args:
        query: Natural language query

    Returns:
        Concept path (e.g., "housing.prices") or None
    """
    query_lower = query.lower()

    # Check aliases from longest to shortest (more specific first)
    sorted_aliases = sorted(CONCEPT_ALIASES.keys(), key=len, reverse=True)

    for alias in sorted_aliases:
        if alias in query_lower:
            return CONCEPT_ALIASES[alias]

    return None


def get_series_ids_for_query(query: str) -> List[str]:
    """
    Get series IDs that are relevant to a query.

    Args:
        query: Natural language query

    Returns:
        List of series IDs
    """
    concept = get_concept_for_query(query)
    if concept:
        series = get_primary_series_for_concept(concept)
        return [s.id for s in series]

    # Fallback to keyword search
    keywords = query.lower().split()
    all_matches = []
    for kw in keywords:
        if len(kw) > 3:  # Skip short words
            matches = find_series_by_keyword(kw)
            all_matches.extend(matches)

    # Dedupe and return IDs
    seen = set()
    result = []
    for s in all_matches:
        if s.id not in seen:
            seen.add(s.id)
            result.append(s.id)

    return result[:5]  # Limit to 5


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=== Data Inventory Test ===\n")

    # Test concept lookup
    print("Housing series:")
    for s in get_series_for_concept("housing")[:5]:
        print(f"  {s.id}: {s.name} ({s.source.value})")

    print("\nEmployment.unemployment series:")
    for s in get_series_for_concept("employment.unemployment"):
        print(f"  {s.id}: {s.name}")

    # Test keyword search
    print("\nKeyword 'inflation':")
    for s in find_series_by_keyword("inflation")[:5]:
        print(f"  {s.id}: {s.name}")

    # Test query matching
    print("\nQuery: 'how are megacap firms doing?'")
    print(f"  Concept: {get_concept_for_query('how are megacap firms doing?')}")
    print(f"  Series: {get_series_ids_for_query('how are megacap firms doing?')}")

    print("\nQuery: 'what is inflation?'")
    print(f"  Concept: {get_concept_for_query('what is inflation?')}")
    print(f"  Series: {get_series_ids_for_query('what is inflation?')}")

    # Test what_do_we_have
    print("\n" + what_do_we_have("housing"))
