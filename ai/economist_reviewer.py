"""
Economist Reviewer - Second-pass AI review of explanations.

Sees actual data values to explain not just WHAT is happening but WHY.
"""

import json
from typing import List, Optional

from config import config


def review_summary(
    query: str,
    series_data: List[tuple],
    original_summary: str
) -> str:
    """
    Review and improve an economic data explanation.

    This agent sees actual data values to provide deeper insights.

    Args:
        query: The user's question
        series_data: List of (series_id, dates, values, info) tuples
        original_summary: The initial summary to improve

    Returns:
        Improved summary string
    """
    # Check if reviewer is enabled
    if not config.enable_economist_reviewer:
        return original_summary

    if not config.anthropic_api_key or not series_data:
        return original_summary

    # Build data summary for the reviewer
    data_summary = []
    for series_id, dates, values, info in series_data:
        if not values:
            continue

        name = info.get('name', info.get('title', series_id))
        unit = info.get('unit', info.get('units', ''))
        latest = values[-1]
        latest_date = dates[-1]

        yoy_change = None
        if len(values) >= 12:
            yoy_change = latest - values[-12]

        recent_vals = values[-60:] if len(values) >= 60 else values

        summary = {
            'name': name,
            'latest_value': round(latest, 2),
            'latest_date': latest_date,
            'unit': unit,
            'yoy_change': round(yoy_change, 2) if yoy_change else None,
            'recent_min': round(min(recent_vals), 2),
            'recent_max': round(max(recent_vals), 2),
        }

        if yoy_change is not None:
            if yoy_change > 0.01:
                summary['yoy_direction'] = 'UP from year ago'
            elif yoy_change < -0.01:
                summary['yoy_direction'] = 'DOWN from year ago'
            else:
                summary['yoy_direction'] = 'UNCHANGED from year ago'

        data_summary.append(summary)

    if not data_summary:
        return original_summary

    prompt = f"""You are reviewing an economic data explanation. Improve it to be clearer and more insightful.

USER'S QUESTION: "{query}"

ACTUAL DATA:
{json.dumps(data_summary, indent=2)}

ORIGINAL EXPLANATION:
{original_summary}

Improve the explanation to:
1. Reference specific numbers from the data
2. Explain what the trends MEAN (not just describe them)
3. Connect to broader economic context
4. Keep it concise (2-3 sentences max)
5. Use plain language, avoid jargon

Return ONLY the improved explanation, no preamble."""

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=config.anthropic_api_key)
        response = client.messages.create(
            model=config.default_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        improved = response.content[0].text.strip()
        if len(improved) > 50:  # Sanity check
            return improved

    except Exception as e:
        print(f"[EconomistReviewer] Error: {e}")

    return original_summary
