"""
Dynamic AI Bullets - AI-generated chart insights.

Generates contextual, data-aware bullets that reference actual values
and are tailored to the user's specific question.

NOTE: All math is done with pandas in processing/analytics.py.
The LLM receives pre-computed values - it should NEVER calculate.

KNOWN ISSUE (fixed here): The LLM sometimes hallucinates numbers from
training data (e.g., citing "9.6% inflation" when current CPI is 2.65%).
Fix: We extract the EXACT current values from analytics and present them
in an unambiguous "GROUND TRUTH" block that the LLM must cite verbatim.
We also post-process the output to catch chain-of-thought leakage and
numbers that don't appear in the analytics.
"""

import json
import re
from typing import List, Optional
from datetime import datetime

from config import config
from cache import cache_manager
from registry import registry
from processing.analytics import compute_series_analytics, analytics_to_text
from ai.economic_knowledge import DISPLAY_RULES, ANTI_PATTERNS


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

    # Determine data_type from series info or registry
    data_type = info.get('data_type', '')
    if not data_type:
        series_info = registry.get_series(series_id)
        if series_info:
            data_type = series_info.data_type or ''

    # Compute all analytics with pandas (deterministic, no LLM math)
    analytics = compute_series_analytics(dates, values, series_id, frequency, data_type)

    if 'error' in analytics:
        return get_static_bullets(series_id)

    # Build context from pre-computed values
    name = info.get('name', info.get('title', series_id))

    # Use pandas-computed text summary
    analytics_text = analytics_to_text(analytics)

    # Build GROUND TRUTH block — explicit current values the LLM MUST use.
    # This prevents hallucination from training data (e.g., citing "9.6% inflation"
    # when current CPI YoY is actually 2.65%).
    ground_truth = _build_ground_truth(analytics, data_type)

    # Get static bullets for domain context
    static_bullets = get_static_bullets(series_id)
    static_guidance = "\n".join([f"- {b}" for b in static_bullets]) if static_bullets else ""

    prompt = f"""Generate 2 bullet points interpreting this economic data.

SERIES: {name} ({series_id})

=== GROUND TRUTH (you MUST use these exact numbers) ===
{ground_truth}
=== END GROUND TRUTH ===

FULL ANALYTICS: {analytics_text}

{f"DOMAIN CONTEXT:{chr(10)}{static_guidance}" if static_guidance else ""}
{f"USER QUESTION: {user_query}" if user_query else ""}

RULES:
- You MUST cite ONLY the numbers from GROUND TRUTH above. Do NOT use any numbers from your training data.
- If GROUND TRUTH says the current rate is 2.65%, you write 2.65%. Never substitute a different number.
- Each bullet = 1 sentence. Interpret what the trend MEANS for people/economy.
- Do NOT include caveats, corrections, or uncertainty markers (no "however", "it should be noted", etc.)
- Do NOT include any text in **bold** markers or reasoning about the data.

Return ONLY a JSON array: ["First bullet.", "Second bullet."]"""

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=config.anthropic_api_key)
        response = client.messages.create(
            model=config.default_model,
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        # Extract JSON array from response
        bullets = _extract_json_array(text)
        if bullets:
            # Post-process: clean chain-of-thought leakage
            cleaned = [_clean_bullet(b) for b in bullets[:2]]
            cleaned = [b for b in cleaned if b]  # Remove empty after cleaning

            if cleaned:
                cache_manager.set_bullets(series_id, latest_date, cleaned)
                return cleaned

    except Exception as e:
        print(f"[DynamicBullets] Error: {e}")

    return static_bullets[:2] if static_bullets else []


def _build_ground_truth(analytics: dict, data_type: str) -> str:
    """
    Build an explicit GROUND TRUTH block with the exact current values.

    This is the key defense against hallucination. Instead of burying
    the current value in a long analytics string, we state it loud and
    clear in a format the LLM can't miss.

    Example output:
        CURRENT VALUE: 2.65% (as of December 2025)
        YEAR-OVER-YEAR CHANGE: +2.65%
        TREND: decelerating
        DO NOT cite any other numbers for the current rate.
    """
    lines = []
    latest = analytics.get('latest_value')
    latest_date = analytics.get('latest_date_formatted', '')

    if data_type == 'index':
        # For indexes (CPI, PCE, home prices): the YoY % is the meaningful number
        if 'yoy' in analytics and analytics['yoy'].get('change_pct') is not None:
            yoy_pct = analytics['yoy']['change_pct']
            lines.append(f"CURRENT YEAR-OVER-YEAR RATE: {yoy_pct:+.1f}% (as of {latest_date})")
            lines.append(f"This means prices/values are changing at {abs(yoy_pct):.1f}% per year RIGHT NOW.")
            lines.append(f"DO NOT cite any other number for the current rate. It is {abs(yoy_pct):.1f}%, not higher, not lower.")
        else:
            lines.append(f"CURRENT VALUE: {latest} (as of {latest_date})")
    elif data_type == 'rate':
        lines.append(f"CURRENT RATE: {latest:.1f}% (as of {latest_date})")
        if 'yoy' in analytics:
            change = analytics['yoy']['change']
            direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
            lines.append(f"CHANGE FROM YEAR AGO: {direction} {abs(change):.2f} percentage points")
    elif data_type == 'growth_rate':
        lines.append(f"CURRENT GROWTH RATE: {latest:.1f}% (as of {latest_date})")
    else:
        lines.append(f"CURRENT VALUE: {latest} (as of {latest_date})")
        if 'yoy' in analytics and analytics['yoy'].get('change_pct') is not None:
            lines.append(f"YEAR-OVER-YEAR CHANGE: {analytics['yoy']['change_pct']:+.1f}%")

    # Add momentum
    if 'momentum' in analytics:
        lines.append(f"TREND: {analytics['momentum']['direction']}")

    return "\n".join(lines)


def _extract_json_array(text: str) -> Optional[List[str]]:
    """
    Extract a JSON array from LLM response text.

    Handles:
    - Clean JSON: ["a", "b"]
    - Markdown-fenced: ```json\n["a", "b"]\n```
    - Prefixed with reasoning text before the array

    Uses rfind for ']' (last bracket) and walks backward to find the
    matching '[', avoiding false matches from reasoning text.
    """
    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [str(b) for b in result]
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    cleaned = text
    if '```json' in cleaned:
        cleaned = cleaned.split('```json', 1)[1].split('```', 1)[0]
    elif '```' in cleaned:
        parts = cleaned.split('```')
        if len(parts) >= 3:
            cleaned = parts[1]

    try:
        result = json.loads(cleaned.strip())
        if isinstance(result, list):
            return [str(b) for b in result]
    except json.JSONDecodeError:
        pass

    # Last resort: find the LAST complete [...] in the text
    # (reasoning text may contain brackets, so search from the end)
    end = text.rfind(']')
    if end == -1:
        return None

    # Walk backward from ']' to find the matching '['
    depth = 0
    start = end
    for i in range(end, -1, -1):
        if text[i] == ']':
            depth += 1
        elif text[i] == '[':
            depth -= 1
            if depth == 0:
                start = i
                break

    if start < end:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return [str(b) for b in result]
        except json.JSONDecodeError:
            pass

    return None


def _clean_bullet(bullet: str) -> str:
    """
    Post-process a bullet to remove chain-of-thought leakage.

    Catches:
    - Bold markers with reasoning: **However, the data shows...**
    - Self-correction text: "This needs to be compared to..."
    - Verification requests: "Verify the accuracy of..."
    - Hedging caveats that add nothing
    """
    if not bullet or not isinstance(bullet, str):
        return ''

    # Strip bold markers but keep content: **text** → text
    # (Previously this removed the entire bold section including content,
    # which would wipe out bullets like "**Prices rising at 2.6%.**")
    bullet = re.sub(r'\*\*([^*]*)\*\*', r'\1', bullet)

    # Remove common chain-of-thought phrases
    cot_patterns = [
        r'However,?\s+the data shows.*?\.(?:\s|$)',
        r'This needs to be compared to.*?\.(?:\s|$)',
        r'Verify the accuracy.*?\.(?:\s|$)',
        r'This is based on an estimated.*?\.(?:\s|$)',
        r'Note:.*?\.(?:\s|$)',
        r'It should be noted.*?\.(?:\s|$)',
        r'It\'s worth noting.*?\.(?:\s|$)',
    ]
    for pattern in cot_patterns:
        bullet = re.sub(pattern, '', bullet, flags=re.IGNORECASE)

    # Clean up whitespace
    bullet = ' '.join(bullet.split()).strip()

    # Remove trailing/leading punctuation artifacts
    bullet = bullet.strip(' .,;-')

    # If bullet got too short after cleaning, it was mostly CoT
    if len(bullet) < 20:
        return ''

    # Ensure it ends with a period
    if bullet and not bullet.endswith('.'):
        bullet += '.'

    return bullet


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
