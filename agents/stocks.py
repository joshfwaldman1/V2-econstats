"""
Stock market data integration for EconStats using FRED.

FRED provides reliable stock market indices that integrate seamlessly with economic data.
This module provides helper functions and curated market series.
"""

from datetime import datetime, timedelta
from typing import Optional

# Stock market series available in FRED
MARKET_SERIES = {
    # Major Indices
    "SP500": {
        "name": "S&P 500",
        "category": "index",
        "keywords": ["s&p", "sp500", "s&p 500", "stock market", "stocks", "equities", "market"],
        "description": "S&P 500 Index - broad measure of large-cap US stocks",
    },
    "DJIA": {
        "name": "Dow Jones Industrial Average",
        "category": "index",
        "keywords": ["dow", "dow jones", "djia", "industrials", "blue chip"],
        "description": "30 large-cap industrial stocks",
    },
    "NASDAQCOM": {
        "name": "NASDAQ Composite",
        "category": "index",
        "keywords": ["nasdaq", "tech stocks", "technology", "composite"],
        "description": "NASDAQ Composite Index - tech-heavy index",
    },
    "NASDAQ100": {
        "name": "NASDAQ 100",
        "category": "index",
        "keywords": ["nasdaq 100", "tech", "large cap tech"],
        "description": "100 largest non-financial NASDAQ stocks",
    },
    # Volatility
    "VIXCLS": {
        "name": "VIX (Volatility Index)",
        "category": "volatility",
        "keywords": ["vix", "volatility", "fear", "uncertainty", "risk", "fear index"],
        "description": "CBOE Volatility Index - market fear gauge",
    },
    # Treasury yields (already in plans_fed_rates.json, but relevant to stocks)
    "DGS10": {
        "name": "10-Year Treasury Yield",
        "category": "rates",
        "keywords": ["10 year", "treasury", "yield", "bonds"],
        "description": "10-Year Treasury Constant Maturity Rate",
    },
    "DGS2": {
        "name": "2-Year Treasury Yield",
        "category": "rates",
        "keywords": ["2 year", "treasury", "yield", "short term"],
        "description": "2-Year Treasury Constant Maturity Rate",
    },
    "T10Y2Y": {
        "name": "10Y-2Y Treasury Spread",
        "category": "rates",
        "keywords": ["yield curve", "spread", "inversion", "recession indicator"],
        "description": "10-Year minus 2-Year Treasury spread (yield curve)",
    },
    # Corporate bonds
    "BAMLH0A0HYM2": {
        "name": "High Yield Corporate Bond Spread",
        "category": "credit",
        "keywords": ["high yield", "junk bonds", "credit spread", "corporate bonds"],
        "description": "ICE BofA US High Yield Index Option-Adjusted Spread",
    },
    # Gold and commodities
    "GOLDAMGBD228NLBM": {
        "name": "Gold Price (London Fix)",
        "category": "commodities",
        "keywords": ["gold", "precious metals", "safe haven"],
        "description": "Gold Fixing Price in London Bullion Market",
    },
    "DCOILWTICO": {
        "name": "WTI Crude Oil Price",
        "category": "commodities",
        "keywords": ["oil", "crude", "wti", "petroleum"],
        "description": "Crude Oil Prices: West Texas Intermediate",
    },
    # Gas prices
    "GASREGW": {
        "name": "Regular Gasoline Price",
        "category": "commodities",
        "keywords": ["gas", "gasoline", "gas prices", "fuel", "pump prices"],
        "description": "US Regular All Formulations Gas Price",
    },
    # Energy CPI
    "CPIENGSL": {
        "name": "Energy CPI",
        "category": "inflation",
        "keywords": ["energy costs", "energy prices", "energy inflation"],
        "description": "Consumer Price Index: Energy",
    },
    "CUSR0000SEHF01": {
        "name": "Electricity Price Index",
        "category": "inflation",
        "keywords": ["electricity", "electric", "power prices", "utility"],
        "description": "Consumer Price Index: Electricity",
    },
    "MHHNGSP": {
        "name": "Natural Gas Price",
        "category": "commodities",
        "keywords": ["natural gas", "gas price", "heating"],
        "description": "Henry Hub Natural Gas Spot Price",
    },
}

# Pre-computed query plans for stock market queries
MARKET_QUERY_PLANS = {
    "how is the stock market doing": {
        "series": ["SP500", "DJIA", "NASDAQCOM", "VIXCLS"],
        "explanation": "Major US stock indices and volatility measure.",
    },
    "stock market": {
        "series": ["SP500", "NASDAQCOM", "DJIA"],
        "explanation": "Major US stock market indices.",
    },
    "s&p 500": {
        "series": ["SP500"],
        "explanation": "S&P 500 Index - benchmark for large-cap US stocks.",
    },
    "dow jones": {
        "series": ["DJIA"],
        "explanation": "Dow Jones Industrial Average.",
    },
    "nasdaq": {
        "series": ["NASDAQCOM"],
        "explanation": "NASDAQ Composite Index.",
    },
    "market volatility": {
        "series": ["VIXCLS", "SP500"],
        "explanation": "VIX volatility index and S&P 500 for context.",
    },
    "vix": {
        "series": ["VIXCLS"],
        "explanation": "CBOE Volatility Index - measures expected market volatility.",
    },
    "fear index": {
        "series": ["VIXCLS"],
        "explanation": "VIX, often called the 'fear index'.",
    },
    "yield curve": {
        "series": ["T10Y2Y", "DGS10", "DGS2"],
        "explanation": "Treasury yield curve: 10Y-2Y spread and underlying rates.",
    },
    "gold price": {
        "series": ["GOLDAMGBD228NLBM"],
        "explanation": "Gold fixing price from London Bullion Market.",
    },
    "oil price": {
        "series": ["DCOILWTICO"],
        "explanation": "WTI Crude Oil spot price.",
    },
    "credit spreads": {
        "series": ["BAMLH0A0HYM2", "T10Y2Y"],
        "explanation": "High yield corporate bond spread and Treasury spread.",
    },
    "stocks vs bonds": {
        "series": ["SP500", "DGS10"],
        "explanation": "S&P 500 vs 10-Year Treasury yield.",
    },
    "market risk": {
        "series": ["VIXCLS", "BAMLH0A0HYM2", "T10Y2Y"],
        "explanation": "Risk indicators: VIX, credit spreads, yield curve.",
    },
    # Energy prices
    "gas prices": {
        "series": ["GASREGW"],
        "explanation": "US Regular Gasoline Prices (weekly).",
    },
    "gasoline prices": {
        "series": ["GASREGW"],
        "explanation": "US Regular Gasoline Prices (weekly).",
    },
    "gasoline": {
        "series": ["GASREGW"],
        "explanation": "US Regular Gasoline Prices (weekly).",
    },
    "energy costs": {
        "series": ["CPIENGSL", "GASREGW", "DCOILWTICO"],
        "explanation": "Energy CPI, gas prices, and oil prices.",
    },
    "energy prices": {
        "series": ["CPIENGSL", "GASREGW", "DCOILWTICO"],
        "explanation": "Energy CPI, gas prices, and oil prices.",
    },
    "electricity prices": {
        "series": ["CUSR0000SEHF01"],
        "explanation": "Consumer Price Index for Electricity.",
    },
    "natural gas": {
        "series": ["MHHNGSP"],
        "explanation": "Henry Hub Natural Gas Spot Price.",
    },
}


def find_market_plan(query: str) -> Optional[dict]:
    """
    Find a pre-computed plan for stock market queries.

    Args:
        query: User's question

    Returns:
        Dict with 'series' and 'explanation' if found, else None
    """
    query_lower = query.lower().strip()

    # Exact match first
    if query_lower in MARKET_QUERY_PLANS:
        return MARKET_QUERY_PLANS[query_lower]

    # Partial match
    for plan_query, plan in MARKET_QUERY_PLANS.items():
        if plan_query in query_lower or query_lower in plan_query:
            return plan

    # Keyword match
    for series_id, meta in MARKET_SERIES.items():
        keywords = meta.get("keywords", [])
        for kw in keywords:
            if kw in query_lower:
                return {
                    "series": [series_id],
                    "explanation": meta.get("description", meta.get("name")),
                }

    return None


def get_market_series_info(series_id: str) -> Optional[dict]:
    """Get metadata for a market series."""
    return MARKET_SERIES.get(series_id)


def is_market_query(query: str) -> bool:
    """Check if query is about stock markets."""
    query_lower = query.lower()

    # Exclude non-stock-market uses of "market"
    non_stock_markets = [
        "housing market", "job market", "labor market", "bond market",
        "real estate market", "mortgage market", "credit market",
    ]
    if any(term in query_lower for term in non_stock_markets):
        return False

    market_indicators = [
        "stock", "stock market", "s&p", "sp500", "dow", "nasdaq", "vix",
        "volatility", "equities", "wall street", "trading",
        "yield curve", "treasury", "gold", "oil price", "crude",
        "gas prices", "gasoline", "energy costs", "energy prices",
        "electricity prices", "natural gas",
    ]
    return any(indicator in query_lower for indicator in market_indicators)


# Quick test
if __name__ == "__main__":
    print("Stock Market Series in FRED:\n")
    for sid, info in MARKET_SERIES.items():
        print(f"{sid}: {info['name']}")
        print(f"  Keywords: {', '.join(info['keywords'][:4])}")
        print()

    print("=" * 50)
    print("\nQuery Plan Tests:\n")

    test_queries = [
        "how is the stock market doing?",
        "what's the VIX at?",
        "show me the yield curve",
        "nasdaq performance",
    ]

    for q in test_queries:
        plan = find_market_plan(q)
        if plan:
            print(f"Query: '{q}'")
            print(f"  Series: {plan['series']}")
            print(f"  Explanation: {plan['explanation']}")
        else:
            print(f"Query: '{q}' - No plan found")
        print()
