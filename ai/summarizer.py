"""
AI Summarizer - Generate economic data summaries.

Wraps llm_client functions with additional logic.
"""

from typing import List, Optional

from .llm_client import get_ai_summary, build_data_context


def generate_summary(
    query: str,
    series_data: List[tuple],
    use_cache: bool = True
) -> str:
    """
    Generate a summary for the query and data.

    This is the main entry point for summary generation.

    Args:
        query: The user's question
        series_data: List of (series_id, dates, values, info) tuples
        use_cache: Whether to use caching

    Returns:
        Summary string
    """
    if not series_data:
        return "No data available to summarize."

    # Filter to series with actual data
    valid_data = [(sid, dates, values, info) for sid, dates, values, info in series_data
                  if dates and values]

    if not valid_data:
        return "Unable to fetch data for the requested series."

    return get_ai_summary(query, valid_data, cached=use_cache)


def generate_fallback_summary(
    query: str,
    series_data: List[tuple]
) -> str:
    """
    Generate a simple summary without LLM for fallback.

    Used when LLM is unavailable or for simple queries.
    """
    if not series_data:
        return "No data available."

    parts = []
    for series_id, dates, values, info in series_data:
        if not values:
            continue

        name = info.get('name', info.get('title', series_id))
        latest = values[-1]
        unit = info.get('unit', info.get('units', ''))

        parts.append(f"{name} is currently at {latest:.2f} {unit}")

    if parts:
        return ". ".join(parts) + "."
    return "Data retrieved successfully."
