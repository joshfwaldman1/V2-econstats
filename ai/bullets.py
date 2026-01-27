"""
Dynamic AI Bullets - AI-generated chart insights.

Generates contextual, data-aware bullets that reference actual values
and are tailored to the user's specific question.

NOTE: All math is done with pandas in processing/analytics.py.
The LLM receives pre-computed values - it should NEVER calculate.
"""

import json
from typing import List, Optional
from datetime import datetime

from config import config
from cache import cache_manager
from registry import registry
from processing.analytics import compute_series_analytics, analytics_to_text


def generate_dynamic_bullets(
    series_id: str,
    dates: List[str],
    values: List[float],
    info: dict,
    user_query: str = ''
) -> List[str]:
    """
    Generate AI-powered bullets using Claude.

    All math is computed by pandas in processing/analytics.py.
    The LLM receives pre-computed values - it should NEVER calculate.

    Args:
        series_id: The series identifier
        dates: List of date strings
        values: List of values
        info: Series metadata
        user_query: Optional user query for context

    Returns:
        List of 2 bullet strings
    """
    # Check if dynamic bullets are enabled
    if not config.enable_dynamic_bullets:
        return get_static_bullets(series_id)

    if not config.anthropic_api_key or not values or len(values) < 2:
        return get_static_bullets(series_id)

    # Check cache
    latest_date = dates[-1] if dates else 'unknown'
    cached = cache_manager.get_bullets(series_id, latest_date)
    if cached:
        return cached

    # Determine frequency from metadata
    freq = info.get('frequency', 'monthly').lower()
    if 'quarter' in freq:
        frequency = 'quarterly'
    elif 'daily' in freq or 'day' in freq:
        frequency = 'daily'
    elif 'week' in freq:
        frequency = 'weekly'
    else:
        frequency = 'monthly'

    # Compute all analytics with pandas (deterministic, no LLM math)
    analytics = compute_series_analytics(dates, values, series_id, frequency)

    if 'error' in analytics:
        return get_static_bullets(series_id)

    # Build context from pre-computed values
    name = info.get('name', info.get('title', series_id))
    unit = info.get('unit', info.get('units', ''))

    # Use pandas-computed text summary
    analytics_text = analytics_to_text(analytics)

    # Get 5-year context from pre-computed values
    historical_context = ""
    if 'range_5y' in analytics:
        r5 = analytics['range_5y']
        historical_context = f"5-year range: {r5['low']:.2f} to {r5['high']:.2f} (mean: {r5['mean']:.2f})"

    # Get static bullets for context
    static_bullets = get_static_bullets(series_id)
    static_guidance = "\n".join([f"- {b}" for b in static_bullets]) if static_bullets else ""

    prompt = f"""Generate 2 insightful bullet points that INTERPRET what this economic data means.

SERIES: {name} ({series_id})
PRE-COMPUTED ANALYTICS: {analytics_text}
{historical_context}

{f"DOMAIN CONTEXT: {static_guidance}" if static_guidance else ""}
{f"USER QUESTION: {user_query}" if user_query else ""}

Write 2 bullets that:
1. INTERPRET what the trend means (e.g., "wages rising faster than inflation means workers gaining purchasing power")
2. Explain the "SO WHAT" - what this means for workers, consumers, or the economy
3. Keep each bullet to 1 sentence max

IMPORTANT: Use the pre-computed values above. DO NOT calculate any numbers yourself.

Format: Return ONLY a JSON array of strings, like: ["First bullet.", "Second bullet."]"""

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=config.anthropic_api_key)
        response = client.messages.create(
            model=config.default_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text

        if '[' in text and ']' in text:
            start = text.index('[')
            end = text.rindex(']') + 1
            bullets = json.loads(text[start:end])
            if isinstance(bullets, list) and len(bullets) > 0:
                result = bullets[:2]
                # Cache the result
                cache_manager.set_bullets(series_id, latest_date, result)
                return result

    except Exception as e:
        print(f"[DynamicBullets] Error: {e}")

    return static_bullets[:2] if static_bullets else []


def get_static_bullets(series_id: str) -> List[str]:
    """Get static bullets from the registry."""
    series_info = registry.get_series(series_id)
    if series_info:
        return series_info.bullets[:2]
    return []


def get_bullets(
    series_id: str,
    dates: List[str],
    values: List[float],
    info: dict,
    user_query: str = '',
    use_ai: bool = None
) -> List[str]:
    """
    Get bullets for a chart.

    Uses AI if enabled and available, otherwise falls back to static.

    Args:
        series_id: The series identifier
        dates: List of date strings
        values: List of values
        info: Series metadata
        user_query: Optional user query
        use_ai: Override for AI usage (None = use config)

    Returns:
        List of bullet strings
    """
    if use_ai is None:
        use_ai = config.enable_dynamic_bullets

    if use_ai:
        return generate_dynamic_bullets(series_id, dates, values, info, user_query)
    else:
        return get_static_bullets(series_id)
