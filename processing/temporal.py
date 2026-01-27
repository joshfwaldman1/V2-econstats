"""
Temporal Filtering - Extract date ranges from queries.

Handles:
- Year references: "inflation in 2022", "gdp during 2019"
- Relative references: "last year", "this year", "past 2 years"
- Period references: "pre-covid", "during the recession", "before 2020"
"""

import re
from datetime import datetime
from typing import Optional, Dict


def extract_temporal_filter(query: str) -> Optional[Dict]:
    """
    Extract temporal references from a query and return date filter parameters.

    Args:
        query: The user's query string

    Returns:
        Dict with filter params or None if no temporal reference found.
        Keys: temporal_focus, filter_start_date, filter_end_date, years_override, explanation
    """
    q = query.lower().strip()
    now = datetime.now()
    current_year = now.year

    # === "Since YYYY" - open-ended range from year to present ===
    if match := re.search(r'\bsince\s+((?:19|20)\d{2})\b', q):
        year = int(match.group(1))
        if 1950 <= year <= current_year:
            return {
                'temporal_focus': f'since {year}',
                'filter_start_date': f'{year}-01-01',
                # No end date - open-ended to present
                'years_override': current_year - year + 2,
                'explanation': f'Showing data from {year} to present.',
            }

    # === Specific year reference (in/during/for YYYY) ===
    if match := re.search(r'\b(?:in|during|for)\s+((?:19|20)\d{2})\b', q):
        year = int(match.group(1))
        if 1950 <= year <= current_year:
            return {
                'temporal_focus': f'{year}',
                'filter_start_date': f'{year}-01-01',
                'filter_end_date': f'{year}-12-31',
                'years_override': max(2, current_year - year + 2),
                'explanation': f'Showing data for {year}.',
            }
        elif year > current_year:
            return {
                'temporal_focus': f'{year} (future)',
                'invalid_temporal': True,
                'explanation': f'Note: {year} is in the future. Showing latest available data.',
            }

    # === Year range ===
    if match := re.search(r'\b(?:from|between)\s*((?:19|20)\d{2})\s*(?:to|and|-)\s*((?:19|20)\d{2})\b', q):
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        if start_year > end_year:
            start_year, end_year = end_year, start_year
        end_year = min(end_year, current_year)
        if 1950 <= start_year <= current_year:
            return {
                'temporal_focus': f'{start_year}-{end_year}',
                'filter_start_date': f'{start_year}-01-01',
                'filter_end_date': f'{end_year}-12-31',
                'years_override': max(2, current_year - start_year + 2),
                'explanation': f'Showing data from {start_year} to {end_year}.',
            }

    # === Relative year references ===
    if re.search(r'\blast\s+year\b', q):
        last_year = current_year - 1
        return {
            'temporal_focus': f'{last_year}',
            'filter_start_date': f'{last_year}-01-01',
            'filter_end_date': f'{last_year}-12-31',
            'years_override': 3,
            'explanation': f'Showing data for {last_year}.',
        }

    if re.search(r'\bthis\s+year\b', q):
        return {
            'temporal_focus': f'{current_year}',
            'filter_start_date': f'{current_year}-01-01',
            'years_override': 2,
            'explanation': f'Showing data for {current_year} so far.',
        }

    # "past/last N years"
    if match := re.search(r'\b(?:past|last)\s+(\d+)\s+years?\b', q):
        n_years = int(match.group(1))
        return {
            'temporal_focus': f'past {n_years} years',
            'years_override': n_years,
            'explanation': f'Showing data for the past {n_years} years.',
        }

    # === Period references ===
    if re.search(r'\b(pre[\s-]?(covid|pandemic|2020)|before\s+(covid|pandemic|the\s+pandemic|2020))\b', q):
        return {
            'temporal_focus': 'pre-COVID',
            'filter_end_date': '2020-02-29',
            'years_override': current_year - 2017 + 1,
            'explanation': 'Showing pre-COVID data (through February 2020).',
        }

    if re.search(r'\b(during\s+(covid|pandemic|the\s+pandemic)|covid\s+era|pandemic\s+period)\b', q):
        return {
            'temporal_focus': 'COVID period',
            'filter_start_date': '2020-03-01',
            'filter_end_date': '2021-12-31',
            'years_override': 5,
            'explanation': 'Showing COVID pandemic period (March 2020 - December 2021).',
        }

    if re.search(r'\b(post[\s-]?(covid|pandemic)|after\s+(covid|pandemic|the\s+pandemic)|recovery\s+period)\b', q):
        return {
            'temporal_focus': 'post-COVID',
            'filter_start_date': '2022-01-01',
            'years_override': 4,
            'explanation': 'Showing post-COVID recovery period (2022 onward).',
        }

    if re.search(r'\b(great\s+recession|during\s+(?:the\s+)?recession|2008\s+(?:recession|crisis)|financial\s+crisis)\b', q):
        return {
            'temporal_focus': 'Great Recession',
            'filter_start_date': '2007-12-01',
            'filter_end_date': '2009-06-30',
            'years_override': current_year - 2007 + 1,
            'explanation': 'Showing Great Recession period (December 2007 - June 2009).',
        }

    return None


def get_smart_date_range(query: str, default_years: int = 8) -> Optional[int]:
    """
    Determine smart date range based on query content.

    Queries about historical events need more data;
    most queries benefit from focused recent data.

    Args:
        query: The user's query string
        default_years: Default number of years if no special pattern

    Returns:
        Number of years to fetch, or None for all available data
    """
    q = query.lower()

    # Queries that should show ALL available data
    if any(pattern in q for pattern in [
        'all time', 'all data', 'full history', 'max data', 'complete history',
        'since 1950', 'since 1960', 'since 1970', 'since 1980',
        'historical trend', 'long-term trend', 'long term trend',
        'over the decades', 'over decades',
    ]):
        return None  # All data

    # Queries that need more context (15-20 years)
    if any(pattern in q for pattern in [
        'great recession', '2008', 'financial crisis', 'housing crisis',
        'compared to', 'comparison', 'vs pre-pandemic', 'before covid',
        'over the years', 'historically', 'history of',
        'long-run', 'long run', 'long-term', 'long term', 'secular trend',
    ]):
        return 20

    return default_years


def filter_data_by_dates(
    dates: list,
    values: list,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> tuple:
    """
    Filter data to a specific date range.

    Args:
        dates: List of date strings (YYYY-MM-DD)
        values: List of corresponding values
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        Tuple of (filtered_dates, filtered_values)
    """
    if not start_date and not end_date:
        return dates, values

    filtered_dates = []
    filtered_values = []

    for date, value in zip(dates, values):
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        filtered_dates.append(date)
        filtered_values.append(value)

    return filtered_dates, filtered_values
