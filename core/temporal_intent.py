"""
Temporal Intent Detection Module

Detects the user's temporal intent for queries, distinguishing between:
- COMPARE: "since pre-pandemic" -> need BOTH current AND reference periods
- FILTER: "in 2022" -> only show that period
- CURRENT: "what is inflation" -> show recent data

This is critical for fixing queries like "Compare to pre-pandemic" which were
incorrectly filtering TO Feb 2020 instead of comparing CURRENT data AGAINST Feb 2020.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class TemporalIntent:
    """
    Represents the user's temporal intent for a query.

    Distinguishes between:
    - COMPARE: "how has X changed since Y" -> need both current AND reference
    - FILTER: "show me X in 2022" -> filter to that period only
    - CURRENT: "what is X" -> just show current/recent data
    """
    intent_type: str  # "compare", "filter", "current"

    # For COMPARE intents - need both periods
    primary_period: Optional[dict] = None    # {"start": date, "end": date, "label": "Current"}
    reference_period: Optional[dict] = None  # {"start": date, "end": date, "label": "Pre-pandemic"}

    # For FILTER intents - single period
    filter_start: Optional[str] = None
    filter_end: Optional[str] = None

    # Metadata
    comparison_type: str = "level"  # "level", "change", "percent_change"
    original_query: str = ""
    confidence: float = 1.0
    explanation: str = ""

    @property
    def is_comparison(self) -> bool:
        """Is this a temporal comparison query?"""
        return self.intent_type == "compare"

    @property
    def needs_multi_period(self) -> bool:
        """Does this query need data from multiple time periods?"""
        return self.intent_type == "compare"

    @property
    def reference_label(self) -> str:
        """Human-readable label for reference period."""
        if self.reference_period:
            return self.reference_period.get("label", "Reference period")
        return ""


# Named period definitions
NAMED_PERIODS = {
    # Pre-pandemic variations
    "pre-pandemic": {"end": "2020-02-29", "label": "Pre-pandemic (Feb 2020)"},
    "pre-covid": {"end": "2020-02-29", "label": "Pre-COVID (Feb 2020)"},
    "before covid": {"end": "2020-02-29", "label": "Pre-COVID (Feb 2020)"},
    "before the pandemic": {"end": "2020-02-29", "label": "Pre-pandemic (Feb 2020)"},
    "before 2020": {"end": "2019-12-31", "label": "Before 2020"},

    # COVID period variations
    "covid": {"start": "2020-03-01", "end": "2021-12-31", "label": "COVID period (Mar 2020 - Dec 2021)"},
    "pandemic": {"start": "2020-03-01", "end": "2021-12-31", "label": "Pandemic period"},
    "during covid": {"start": "2020-03-01", "end": "2021-12-31", "label": "During COVID"},
    "during the pandemic": {"start": "2020-03-01", "end": "2021-12-31", "label": "During pandemic"},

    # Post-pandemic variations
    "post-pandemic": {"start": "2022-01-01", "label": "Post-pandemic (2022+)"},
    "post-covid": {"start": "2022-01-01", "label": "Post-COVID (2022+)"},
    "after covid": {"start": "2022-01-01", "label": "After COVID"},
    "since covid": {"start": "2020-03-01", "label": "Since COVID began"},

    # Great Recession (2007-2009)
    "great recession": {"start": "2007-12-01", "end": "2009-06-30", "label": "Great Recession (Dec 2007 - Jun 2009)"},
    "2008 crisis": {"start": "2007-12-01", "end": "2009-06-30", "label": "2008 Financial Crisis"},
    "2008 recession": {"start": "2007-12-01", "end": "2009-06-30", "label": "2008 Recession"},
    "financial crisis": {"start": "2007-12-01", "end": "2009-06-30", "label": "Financial Crisis"},
    "housing crisis": {"start": "2007-12-01", "end": "2009-06-30", "label": "Housing Crisis (2007-2009)"},
    "subprime crisis": {"start": "2007-12-01", "end": "2009-06-30", "label": "Subprime Crisis"},

    # 1970s Stagflation Era (high inflation + high unemployment)
    "1970s": {"start": "1970-01-01", "end": "1979-12-31", "label": "The 1970s"},
    "the 1970s": {"start": "1970-01-01", "end": "1979-12-31", "label": "The 1970s"},
    "stagflation": {"start": "1970-01-01", "end": "1982-12-31", "label": "Stagflation Era (1970-1982)"},
    "stagflation era": {"start": "1970-01-01", "end": "1982-12-31", "label": "Stagflation Era (1970-1982)"},
    "volcker era": {"start": "1979-08-01", "end": "1987-08-11", "label": "Volcker Era (1979-1987)"},
    "volcker shock": {"start": "1980-01-01", "end": "1982-12-31", "label": "Volcker Shock (1980-1982)"},

    # Other decades for historical comparison
    "the 1980s": {"start": "1980-01-01", "end": "1989-12-31", "label": "The 1980s"},
    "1980s": {"start": "1980-01-01", "end": "1989-12-31", "label": "The 1980s"},
    "the 1990s": {"start": "1990-01-01", "end": "1999-12-31", "label": "The 1990s"},
    "1990s": {"start": "1990-01-01", "end": "1999-12-31", "label": "The 1990s"},
    "the 2000s": {"start": "2000-01-01", "end": "2009-12-31", "label": "The 2000s"},
    "2000s": {"start": "2000-01-01", "end": "2009-12-31", "label": "The 2000s"},
    "the 2010s": {"start": "2010-01-01", "end": "2019-12-31", "label": "The 2010s"},
    "2010s": {"start": "2010-01-01", "end": "2019-12-31", "label": "The 2010s"},

    # Dot-com bubble and recession
    "dot-com bubble": {"start": "1997-01-01", "end": "2000-03-31", "label": "Dot-com Bubble (1997-2000)"},
    "dot-com crash": {"start": "2000-03-01", "end": "2002-10-31", "label": "Dot-com Crash (2000-2002)"},
    "2001 recession": {"start": "2001-03-01", "end": "2001-11-30", "label": "2001 Recession"},
    "tech bubble": {"start": "1997-01-01", "end": "2000-03-31", "label": "Tech Bubble (1997-2000)"},

    # Early 1990s recession
    "1990 recession": {"start": "1990-07-01", "end": "1991-03-31", "label": "1990-1991 Recession"},
    "1991 recession": {"start": "1990-07-01", "end": "1991-03-31", "label": "1990-1991 Recession"},
    "gulf war recession": {"start": "1990-07-01", "end": "1991-03-31", "label": "Gulf War Recession (1990-1991)"},

    # Early 1980s recession (double-dip)
    "1981 recession": {"start": "1981-07-01", "end": "1982-11-30", "label": "1981-1982 Recession"},
    "1982 recession": {"start": "1981-07-01", "end": "1982-11-30", "label": "1981-1982 Recession"},
    "double-dip recession": {"start": "1980-01-01", "end": "1982-11-30", "label": "Double-Dip Recession (1980-1982)"},

    # Oil crises
    "oil crisis": {"start": "1973-10-01", "end": "1974-03-31", "label": "Oil Crisis (1973-1974)"},
    "1973 oil crisis": {"start": "1973-10-01", "end": "1974-03-31", "label": "1973 Oil Crisis"},
    "1979 oil crisis": {"start": "1979-01-01", "end": "1980-12-31", "label": "1979 Oil Crisis"},
    "energy crisis": {"start": "1973-10-01", "end": "1974-03-31", "label": "Energy Crisis (1973-1974)"},

    # Great Moderation
    "great moderation": {"start": "1985-01-01", "end": "2007-12-01", "label": "Great Moderation (1985-2007)"},

    # Special keyword - maps to Great Recession if not more specific
    "recession": {"start": "2007-12-01", "end": "2009-06-30", "label": "Great Recession"},
}


# Patterns that indicate COMPARISON intent (need both periods)
COMPARISON_PATTERNS = [
    # "since X" - comparing current to when X started/ended
    r'\b(since|from)\s+(the\s+)?(pre-?(?:pandemic|covid)|post-?(?:pandemic|covid)|covid|pandemic|great\s+recession|stagflation|1970s|1980s|1990s|2000s|2010s|\d{4})',

    # "compared to X" / "vs X" - includes decades and historical periods
    r'\b(compared?\s+to|versus|vs\.?)\s+(the\s+)?(pre-?(?:pandemic|covid)|post-?(?:pandemic|covid)|covid|pandemic|great\s+recession|stagflation|1970s|1980s|1990s|2000s|2010s|\d{4}|last\s+year|a\s+year\s+ago)',

    # "like X" - comparing to historical periods ("like the 1970s", "like 2008")
    r'\b(like|similar\s+to|reminds?\s+(me\s+)?of|echoes?|mirrors?|resembles?)\s+(the\s+)?(pre-?(?:pandemic|covid)|covid|pandemic|great\s+recession|stagflation|1970s|1980s|1990s|2000s|2010s|\d{4})',

    # "now vs X" / "today vs X" / "current vs X"
    r'\b(now|today|current(?:ly)?)\s+(vs\.?|versus|compared\s+to)\s+',

    # "how has X changed since Y"
    r'\bhow\s+(?:has|have|did)\s+.+\s+(changed?|evolved?|moved?|shifted?)\s+(since|from|compared)',

    # "how does X compare to Y" - direct comparison question
    r'\bhow\s+(?:does|do|did)\s+.+\s+compare\s+to\s+(the\s+)?(pre-?(?:pandemic|covid)|covid|pandemic|great\s+recession|stagflation|1970s|1980s|1990s|2000s|2010s|\d{4})',

    # "higher/lower than X period"
    r'\b(higher|lower|more|less|better|worse|stronger|weaker)\s+than\s+(the\s+)?(pre-?(?:pandemic|covid)|stagflation|1970s|1980s|before|in\s+\d{4})',

    # "recovery from X"
    r'\brecovery\s+(from|since)\s+',

    # "X vs Y" where both are temporal (years or decades)
    r'\b(\d{4}s?)\s+(vs\.?|versus|compared\s+to)\s+(\d{4}s?)',

    # "before and after X"
    r'\bbefore\s+and\s+after\s+',

    # "change from X to Y"
    r'\bchange\s+from\s+.+\s+to\s+',

    # "compare X to Y" with temporal reference
    r'\bcompare\s+.+\s+to\s+(the\s+)?(pre-?(?:pandemic|covid)|post-?(?:pandemic|covid)|stagflation|1970s|1980s|1990s|2000s|2010s|\d{4})',

    # "this recession vs" / "this crisis vs" comparisons
    r'\b(this|current)\s+(recession|crisis|downturn)\s+(vs\.?|versus|compared\s+to|like)\s+',

    # Historical period comparisons with specific eras
    r'\b(2008|financial\s+crisis|great\s+recession)\s+(vs\.?|versus|compared\s+to)\s+',

    # Decade comparisons
    r'\b(the\s+)?(19[789]0s|20[012]0s)\s+(vs\.?|versus|compared\s+to|inflation|unemployment|economy)',
]


# Patterns that indicate FILTER intent (only show that period)
FILTER_PATTERNS = [
    # "in YYYY" - specific year
    r'\bin\s+(\d{4})\b(?!\s+(vs|versus|compared))',

    # "during X period" without comparison words
    r'\bduring\s+(the\s+)?(covid|pandemic|great\s+recession|stagflation|1970s|1980s|\d{4})(?!\s+(vs|versus|compared))',

    # "from YYYY to YYYY" - date range
    r'\bfrom\s+(\d{4})\s+to\s+(\d{4})\b',

    # "YYYY-YYYY" - date range shorthand
    r'\b(\d{4})\s*[-–]\s*(\d{4})\b',

    # "pre-pandemic X" without comparison words (showing just that era)
    r'^(pre-?(?:pandemic|covid)|post-?(?:pandemic|covid))\s+\w+(?!\s+(vs|versus|compared|since|from))',

    # "X in YYYY" - specific metric in specific year
    r'\b\w+\s+in\s+(\d{4})\b(?!\s+(vs|versus|compared))',

    # "in the YYYYs" - decade filter (showing just that decade)
    r'\bin\s+the\s+(19[789]0s|20[012]0s)\b(?!\s+(vs|versus|compared))',
]


def detect_temporal_intent(query: str) -> TemporalIntent:
    """
    Main entry point - detects whether query is comparing, filtering, or current.

    Args:
        query: User's query string

    Returns:
        TemporalIntent with detected intent type and period information
    """
    query_lower = query.lower().strip()

    # Try comparison detection first (higher priority)
    comparison_result = _detect_comparison_intent(query_lower, query)
    if comparison_result:
        return comparison_result

    # Try filter detection
    filter_result = _detect_filter_intent(query_lower, query)
    if filter_result:
        return filter_result

    # Default to CURRENT intent (no temporal reference)
    return TemporalIntent(
        intent_type="current",
        original_query=query,
        explanation="Showing current/recent data."
    )


def _detect_comparison_intent(query_lower: str, original_query: str) -> Optional[TemporalIntent]:
    """
    Detect if query is asking for a temporal comparison.

    Patterns like:
    - "since pre-pandemic"
    - "compared to 2019"
    - "how has X changed since Y"
    """
    for pattern in COMPARISON_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            # Extract the reference period from the match
            reference_period = _extract_reference_period(query_lower)

            if reference_period:
                # For comparison, primary is "current" and reference is the historical period
                # Primary period starts AFTER the reference period ends (to avoid overlap)
                # Use reference end date + 1 day as start, or a reasonable recent period
                ref_end = reference_period.get("end")
                if ref_end:
                    # Start primary period after reference ends
                    primary_start = ref_end  # Will get data from dates > ref_end
                else:
                    # If reference has no end, use last 2 years
                    current_year = datetime.now().year
                    primary_start = f"{current_year - 2}-01-01"

                primary_period = {
                    "start": primary_start,
                    "end": None,  # Through present
                    "label": "Current"
                }

                return TemporalIntent(
                    intent_type="compare",
                    primary_period=primary_period,
                    reference_period=reference_period,
                    comparison_type=_detect_comparison_type(query_lower),
                    original_query=original_query,
                    explanation=f"Comparing current data to {reference_period.get('label', 'reference period')}."
                )

    return None


def _detect_filter_intent(query_lower: str, original_query: str) -> Optional[TemporalIntent]:
    """
    Detect if query is asking to filter to a specific time period.

    Patterns like:
    - "in 2022"
    - "during the recession"
    - "from 2018 to 2020"
    """
    # Check for year range patterns first
    year_range_match = re.search(r'\bfrom\s+(\d{4})\s+to\s+(\d{4})\b', query_lower)
    if year_range_match:
        start_year, end_year = year_range_match.groups()
        # Validate and potentially swap if inverted
        if int(start_year) > int(end_year):
            start_year, end_year = end_year, start_year
        return TemporalIntent(
            intent_type="filter",
            filter_start=f"{start_year}-01-01",
            filter_end=f"{end_year}-12-31",
            original_query=original_query,
            explanation=f"Showing data from {start_year} to {end_year}."
        )

    # Check for "in YYYY" pattern
    year_match = re.search(r'\bin\s+(\d{4})\b', query_lower)
    if year_match:
        year = year_match.group(1)
        # Make sure this isn't part of a comparison
        if not re.search(r'(vs|versus|compared|since|from).+' + year, query_lower):
            return TemporalIntent(
                intent_type="filter",
                filter_start=f"{year}-01-01",
                filter_end=f"{year}-12-31",
                original_query=original_query,
                explanation=f"Showing data for {year}."
            )

    # Check for named periods (when not in comparison context)
    for period_name, bounds in NAMED_PERIODS.items():
        if period_name in query_lower:
            # Make sure this isn't a comparison pattern
            is_comparison = any(re.search(p, query_lower) for p in COMPARISON_PATTERNS)
            if not is_comparison:
                return TemporalIntent(
                    intent_type="filter",
                    filter_start=bounds.get("start"),
                    filter_end=bounds.get("end"),
                    original_query=original_query,
                    explanation=f"Showing data for {bounds.get('label', period_name)}."
                )

    return None


def _extract_reference_period(query_lower: str) -> Optional[dict]:
    """
    Extract the reference period from a comparison query.

    Returns period bounds dict with start, end, and label.
    """
    # Check named periods first (this includes decades, stagflation era, etc.)
    for period_name, bounds in NAMED_PERIODS.items():
        if period_name in query_lower:
            return bounds.copy()

    # Check for decade references like "the 1970s", "1980s"
    decade_patterns = [
        r'(?:the\s+)?(19[0-9]0)s',
        r'(?:the\s+)?(20[0-2]0)s',
    ]
    for pattern in decade_patterns:
        match = re.search(pattern, query_lower)
        if match:
            decade_start = int(match.group(1))
            return {
                "start": f"{decade_start}-01-01",
                "end": f"{decade_start + 9}-12-31",
                "label": f"The {decade_start}s"
            }

    # Check for specific year references
    year_patterns = [
        r'(?:since|from|compared\s+to|vs\.?|versus|like|similar\s+to)\s+(\d{4})',
        r'(\d{4})\s+levels?',
        r'in\s+(\d{4})\s+(?:vs|versus|compared)',
    ]

    for pattern in year_patterns:
        match = re.search(pattern, query_lower)
        if match:
            year = match.group(1)
            return {
                "start": f"{year}-01-01",
                "end": f"{year}-12-31",
                "label": f"{year}"
            }

    # Check for "last year" / "a year ago"
    if re.search(r'\b(last\s+year|a\s+year\s+ago)\b', query_lower):
        last_year = datetime.now().year - 1
        return {
            "start": f"{last_year}-01-01",
            "end": f"{last_year}-12-31",
            "label": f"Last year ({last_year})"
        }

    return None


def _detect_comparison_type(query_lower: str) -> str:
    """
    Detect what kind of comparison the user wants.

    Returns: "level", "change", or "percent_change"
    """
    # Look for change-related keywords
    if re.search(r'\b(change|changed|difference|delta|moved?|shifted?)\b', query_lower):
        return "change"

    # Look for percentage-related keywords
    if re.search(r'\b(percent|%|growth|rate\s+of\s+change)\b', query_lower):
        return "percent_change"

    # Default to level comparison
    return "level"


def get_reference_period_bounds(period_name: str) -> Optional[dict]:
    """
    Get the date bounds for a named period.

    Args:
        period_name: Name like "pre-pandemic", "covid", "great-recession", "1970s", or a year

    Returns:
        Dict with "start", "end", and "label" keys, or None if not found
    """
    period_name_lower = period_name.lower().strip()

    # Check named periods
    if period_name_lower in NAMED_PERIODS:
        return NAMED_PERIODS[period_name_lower].copy()

    # Check if it's a year
    if re.match(r'^\d{4}$', period_name):
        return {
            "start": f"{period_name}-01-01",
            "end": f"{period_name}-12-31",
            "label": period_name
        }

    # Check if it's a decade (e.g., "1970s", "the 1980s")
    decade_match = re.match(r'^(?:the\s+)?(\d{3})0s$', period_name_lower)
    if decade_match:
        decade_start = int(decade_match.group(1) + "0")
        return {
            "start": f"{decade_start}-01-01",
            "end": f"{decade_start + 9}-12-31",
            "label": f"The {decade_start}s"
        }

    return None


def get_comparison_baseline_date(intent: TemporalIntent) -> Optional[str]:
    """
    Get the key date to use as comparison baseline.

    For pre-pandemic comparisons, this would be "2020-02-01".
    For year comparisons, this would be mid-year or end of year.

    Returns: ISO date string or None
    """
    if not intent.reference_period:
        return None

    # If reference has an end date, use that as baseline (e.g., Feb 2020 for pre-pandemic)
    if intent.reference_period.get("end"):
        return intent.reference_period["end"]

    # If reference has a start date, use that (e.g., for "since COVID started")
    if intent.reference_period.get("start"):
        return intent.reference_period["start"]

    return None
