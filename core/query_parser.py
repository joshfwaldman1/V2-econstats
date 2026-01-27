"""
Query Parser - Single LLM call to understand user queries.

Replaces the 4 separate extractors (temporal, demographic, geographic, synonym)
with a single structured LLM call that extracts all context at once.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional
from urllib.request import urlopen, Request

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")


@dataclass
class QueryIntent:
    """Parsed query intent with all extracted context."""

    # Query type
    intent: str  # "single", "comparison", "holistic"
    indicator: str  # "gdp", "inflation", "unemployment", "housing", etc.

    # Extracted context
    regions: list[str]  # ["us"], ["us", "eurozone"], etc.
    demographic: Optional[str]  # "black", "hispanic", "women", None
    time_filter: Optional[dict]  # {"start": "2020-01", "end": None, "period": "covid"}

    # Suggested series (optional, from LLM)
    suggested_series: list[str]

    # Original query
    original_query: str

    @property
    def is_comparison(self) -> bool:
        return self.intent == "comparison" or len(self.regions) > 1

    @property
    def is_international(self) -> bool:
        return any(r != "us" for r in self.regions)


PARSE_PROMPT = """You are an economic data query parser. Analyze this query and extract structured information.

Query: "{query}"

Return ONLY valid JSON (no markdown, no explanation):
{{
    "intent": "single" | "comparison" | "holistic",
    "indicator": "gdp" | "inflation" | "unemployment" | "employment" | "housing" | "fed_rates" | "consumer" | "trade" | "stock_market" | "other",
    "regions": ["us"] | ["us", "eurozone"] | ["uk"] | etc,
    "demographic": "black" | "hispanic" | "women" | "men" | "youth" | "older" | null,
    "time_filter": {{"start": "YYYY-MM" or null, "end": "YYYY-MM" or null, "period": "covid" | "pre-covid" | "great-recession" | null}} or null,
    "suggested_series": ["SERIES_ID"] | []
}}

RULES:
- intent: "single" for specific metrics, "comparison" for vs/compared queries, "holistic" for "how is X doing"
- indicator: the main economic topic being asked about
- regions: default to ["us"] if no region mentioned. Include all mentioned regions.
- demographic: only set if query specifically asks about a demographic group
- time_filter: extract any date/period references. "covid" = 2020-03 to 2021-12, "pre-covid" = before 2020-03
- suggested_series: leave empty unless you're confident about specific FRED series IDs

Examples:
- "unemployment rate" → intent: "single", indicator: "unemployment", regions: ["us"]
- "US vs Eurozone GDP" → intent: "comparison", indicator: "gdp", regions: ["us", "eurozone"]
- "how is the economy doing" → intent: "holistic", indicator: "gdp", regions: ["us"]
- "Black unemployment" → intent: "single", indicator: "unemployment", demographic: "black"
- "inflation since COVID" → intent: "single", indicator: "inflation", time_filter: {{"start": "2020-03", "period": "covid"}}
"""


def call_gemini(prompt: str, timeout: int = 30) -> Optional[dict]:
    """Call Gemini Flash for fast, cheap query parsing."""
    if not GOOGLE_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
    }

    try:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["candidates"][0]["content"]["parts"][0]["text"]

            # Clean up response - remove markdown if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            return json.loads(content)
    except Exception as e:
        print(f"[QueryParser] Gemini error: {e}")
        return None


def parse_query(query: str) -> QueryIntent:
    """
    Parse a user query with a single LLM call.

    This replaces the 4 separate extractors:
    - extract_temporal_filter()
    - extract_demographic_group()
    - detect_geographic_scope()
    - apply_synonyms()

    Returns:
        QueryIntent with all extracted context
    """
    prompt = PARSE_PROMPT.format(query=query)
    result = call_gemini(prompt)

    if result:
        return QueryIntent(
            intent=result.get("intent", "single"),
            indicator=result.get("indicator", "other"),
            regions=result.get("regions", ["us"]),
            demographic=result.get("demographic"),
            time_filter=result.get("time_filter"),
            suggested_series=result.get("suggested_series", []),
            original_query=query,
        )

    # Fallback: return basic intent if LLM fails
    return QueryIntent(
        intent="single",
        indicator="other",
        regions=["us"],
        demographic=None,
        time_filter=None,
        suggested_series=[],
        original_query=query,
    )


# Quick test
if __name__ == "__main__":
    test_queries = [
        "unemployment rate",
        "US vs Eurozone GDP",
        "how is the economy doing",
        "Black unemployment since COVID",
        "inflation in 2022",
        "housing prices in California",
    ]

    print("Query Parser Test\n" + "=" * 50)
    for q in test_queries:
        print(f"\nQuery: '{q}'")
        intent = parse_query(q)
        print(f"  Intent: {intent.intent}")
        print(f"  Indicator: {intent.indicator}")
        print(f"  Regions: {intent.regions}")
        print(f"  Demographic: {intent.demographic}")
        print(f"  Time filter: {intent.time_filter}")
        print(f"  Is comparison: {intent.is_comparison}")
