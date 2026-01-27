"""
Unified LLM Client - All Claude API interactions.

Consolidates:
- AI summary generation with rich context (V1 parity)
- Query classification
- Optional streaming support
- Chart descriptions for each series
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import config
from cache import cache_manager

# Lazy import Anthropic to avoid startup issues
_client = None


def get_client():
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        if not config.anthropic_api_key:
            return None
        from anthropic import Anthropic
        _client = Anthropic(api_key=config.anthropic_api_key)
    return _client


def get_ai_summary(
    query: str,
    series_data: List[tuple],
    conversation_history: List[Dict] = None,
    cached: bool = True
) -> Dict[str, Any]:
    """
    Generate a rich AI summary with chart descriptions and suggestions.

    Args:
        query: The user's question
        series_data: List of (series_id, dates, values, info) tuples
        conversation_history: Optional list of previous exchanges
        cached: Whether to use/store in cache

    Returns:
        Dict with 'summary', 'suggestions', and 'chart_descriptions'
    """
    client = get_client()
    if not client:
        return {
            "summary": "Economic data summary not available.",
            "suggestions": [],
            "chart_descriptions": {}
        }

    # Check cache
    if cached:
        data_hash = cache_manager.hash_data(series_data)
        cached_summary = cache_manager.get_summary(query, data_hash)
        if cached_summary and isinstance(cached_summary, dict):
            return cached_summary

    # Build rich context from data
    data_context = build_rich_data_context(series_data)
    series_list = [s[0] for s in series_data if s[2]]  # series IDs with data

    # Build conversation context
    conv_context = ""
    if conversation_history:
        recent = conversation_history[-3:]  # Last 3 exchanges
        conv_context = "\n\nCONVERSATION HISTORY:\n"
        for exchange in recent:
            conv_context += f"User: {exchange.get('query', '')}\n"
            if exchange.get('summary'):
                conv_context += f"Assistant: {exchange['summary'][:200]}...\n"

    prompt = f"""You are an expert economist providing clear, insightful analysis of economic data.

USER QUESTION: "{query}"
{conv_context}

CURRENT DATA:
{data_context}

## TASK: Return a JSON object with three parts:

1. "summary": A 3-4 sentence expert summary that:
   - Directly answers the user's question with specific numbers
   - Explains what trends MEAN for workers, consumers, or the economy
   - Puts current values in context (vs historical average, pre-pandemic, etc.)
   - Uses plain language accessible to non-economists

2. "suggestions": Array of 3 follow-up questions the user might want to ask

3. "chart_descriptions": Object mapping series_id to a 1-sentence description for EACH chart

## CHART DESCRIPTION RULES (CRITICAL):
- NEVER reference ancient base periods (e.g., "CPI is 312" means nothing - say "up 3.2% from a year ago")
- For JOBS/PAYROLL data: NEVER use YoY percentage change. Say "added 175K jobs" not "up 1.2%"
- Put values in context of 1-5 years, NOT decades
- For rates, describe the trajectory with percentage POINT changes (e.g., "down 0.3 pp from peak")
- Good: "Gas prices are down 8% from a year ago, offering relief to consumers"
- Bad: "The gasoline index is 238.5"

Series to describe: {series_list}

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=config.default_model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        # Parse JSON response
        result = _parse_json_response(text, series_list)

        # Cache the result
        if cached:
            cache_manager.set_summary(query, data_hash, result)

        return result

    except Exception as e:
        print(f"[AI] Summary generation error: {e}")
        return {
            "summary": "Unable to generate summary at this time.",
            "suggestions": [],
            "chart_descriptions": {}
        }


def _parse_json_response(text: str, series_list: List[str]) -> Dict[str, Any]:
    """Parse JSON from LLM response, with fallbacks."""
    try:
        # Try to find JSON in response
        if '{' in text:
            start = text.index('{')
            end = text.rindex('}') + 1
            result = json.loads(text[start:end])

            # Ensure all required keys exist
            return {
                "summary": result.get("summary", ""),
                "suggestions": result.get("suggestions", [])[:3],
                "chart_descriptions": result.get("chart_descriptions", {})
            }
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[AI] JSON parse error: {e}")

    # Fallback: treat entire response as summary
    return {
        "summary": text[:500] if text else "",
        "suggestions": [],
        "chart_descriptions": {}
    }


def build_rich_data_context(series_data: List[tuple]) -> str:
    """
    Build a rich data context string for the LLM.

    Includes:
    - Latest value with date
    - YoY change (absolute and percentage)
    - 3-month trend
    - 52-week high/low
    """
    lines = []
    for series_id, dates, values, info in series_data:
        if not values or len(values) < 2:
            continue

        name = info.get('name', info.get('title', series_id))
        unit = info.get('unit', info.get('units', ''))
        latest = values[-1]
        latest_date = dates[-1] if dates else 'N/A'

        # Format latest date
        try:
            dt = datetime.strptime(latest_date, '%Y-%m-%d')
            date_str = dt.strftime('%B %Y')
        except:
            date_str = latest_date

        context_parts = [f"{name} ({series_id}): {latest:.2f} {unit} as of {date_str}"]

        # YoY change (if enough data)
        if len(values) >= 13:
            year_ago = values[-13]
            yoy_change = latest - year_ago
            if year_ago != 0:
                yoy_pct = ((latest - year_ago) / abs(year_ago)) * 100
                context_parts.append(f"YoY: {yoy_change:+.2f} ({yoy_pct:+.1f}%)")

        # 3-month trend (if enough data)
        if len(values) >= 4:
            three_mo_ago = values[-4]
            if three_mo_ago != 0:
                three_mo_change = ((latest - three_mo_ago) / abs(three_mo_ago)) * 100
                if three_mo_change > 2:
                    trend = "Rising"
                elif three_mo_change < -2:
                    trend = "Falling"
                else:
                    trend = "Flat"
                context_parts.append(f"3-month: {trend} ({three_mo_change:+.1f}%)")

        # 52-week high/low (if enough data)
        if len(values) >= 52:
            recent_52 = values[-52:]
            high_52 = max(recent_52)
            low_52 = min(recent_52)
            pct_from_high = ((latest - high_52) / high_52) * 100 if high_52 != 0 else 0
            pct_from_low = ((latest - low_52) / low_52) * 100 if low_52 != 0 else 0
            context_parts.append(f"52-wk range: {low_52:.2f} - {high_52:.2f} ({pct_from_high:+.1f}% from high)")

        # FRED notes (if available)
        notes = info.get('notes', '')
        if notes and len(notes) > 20:
            context_parts.append(f"Context: {notes[:300]}")

        lines.append(" | ".join(context_parts))

    return "\n".join(lines) if lines else "No data available."


def classify_query(query: str, available_topics: List[str]) -> Optional[Dict[str, Any]]:
    """
    Use LLM to understand query intent and route to appropriate topic.

    Args:
        query: The user's question
        available_topics: List of available query plan keys

    Returns:
        Dict with 'topic' and optional 'show_yoy' recommendation
    """
    client = get_client()
    if not client:
        return None

    # Limit topics to avoid context overflow
    topics_str = ", ".join(sorted(set(available_topics))[:150])

    prompt = f"""You route economic data queries. Pick the best topic AND decide how to display data.

Question: "{query}"

Available topics: {topics_str}

DISPLAY RULES (show_yoy):
- RATES (unemployment %, interest rates, P/E ratios) → show_yoy: false (already meaningful)
- INDEXES (CPI, home price index) → show_yoy: true (raw index meaningless, show inflation rate)
- LEVELS (GDP dollars, employment count) → show_yoy: false usually
- GROWTH questions ("how fast", "growth rate") → show_yoy: true

Reply in format: topic_name|show_yoy
Examples: "inflation|true" or "unemployment|false" or "none|false" """

    try:
        response = client.messages.create(
            model=config.default_model,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )

        result = response.content[0].text.strip().lower()
        print(f"[AI] Query '{query}' -> '{result}'")

        # Parse response
        if "|" in result:
            parts = result.split("|")
            topic = parts[0].strip()
            show_yoy = parts[1].strip() == "true" if len(parts) > 1 else None
        else:
            topic = result.strip()
            show_yoy = None

        if topic != "none":
            # Find original casing
            topic_lower = topic.lower()
            for t in available_topics:
                if t.lower() == topic_lower:
                    return {"topic": t, "show_yoy": show_yoy}

        return None

    except Exception as e:
        print(f"[AI] Classification error: {e}")
        return None


async def stream_summary(
    query: str,
    series_data: List[tuple]
):
    """
    Stream AI summary generation.

    Yields text chunks as they are generated.
    Use for SSE responses.
    """
    client = get_client()
    if not client:
        yield "Economic data summary not available."
        return

    data_context = build_rich_data_context(series_data)

    prompt = f"""You are an expert economist. Provide a 3-4 sentence summary.

USER QUESTION: "{query}"

DATA:
{data_context}

Be concise, reference specific numbers, explain what trends mean for the economy.
Put values in context (vs year ago, pre-pandemic, historical average)."""

    try:
        with client.messages.stream(
            model=config.default_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                yield text

    except Exception as e:
        print(f"[AI] Streaming error: {e}")
        yield "Unable to generate summary."
