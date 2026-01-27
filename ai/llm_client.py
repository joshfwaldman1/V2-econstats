"""
Unified LLM Client - All Claude API interactions.

Consolidates:
- AI summary generation
- Query classification
- Optional streaming support
"""

import json
from typing import Optional, List, Dict, Any

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
    cached: bool = True
) -> str:
    """
    Generate an AI summary for the query and data.

    Args:
        query: The user's question
        series_data: List of (series_id, dates, values, info) tuples
        cached: Whether to use/store in cache

    Returns:
        AI-generated summary string
    """
    client = get_client()
    if not client:
        return "Economic data summary not available."

    # Check cache
    if cached:
        data_hash = cache_manager.hash_data(series_data)
        cached_summary = cache_manager.get_summary(query, data_hash)
        if cached_summary:
            return cached_summary

    # Build context from data
    data_context = build_data_context(series_data)

    prompt = f"""You are an expert economist providing clear, insightful explanations of economic data.

USER QUESTION: "{query}"

CURRENT DATA:
{data_context}

Provide a 2-3 sentence summary that:
1. Directly answers the user's question
2. References specific numbers from the data
3. Explains what the trends MEAN (not just describe them)
4. Uses plain language accessible to non-economists

Be concise and informative. Do not use bullet points."""

    try:
        response = client.messages.create(
            model=config.default_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response.content[0].text.strip()

        # Cache the result
        if cached:
            cache_manager.set_summary(query, data_hash, summary)

        return summary

    except Exception as e:
        print(f"[AI] Summary generation error: {e}")
        return "Unable to generate summary at this time."


def build_data_context(series_data: List[tuple]) -> str:
    """Build a data context string for the LLM."""
    lines = []
    for series_id, dates, values, info in series_data:
        if not values:
            continue

        name = info.get('name', info.get('title', series_id))
        unit = info.get('unit', info.get('units', ''))
        latest = values[-1]
        latest_date = dates[-1] if dates else 'N/A'

        # Calculate YoY change
        yoy_info = ""
        if len(values) >= 13:
            yoy_change = latest - values[-13]
            if values[-13] != 0:
                yoy_pct = ((latest - values[-13]) / abs(values[-13])) * 100
                yoy_info = f" | YoY: {yoy_change:+.2f} ({yoy_pct:+.1f}%)"

        lines.append(f"- {name}: {latest:.2f} {unit} (as of {latest_date}){yoy_info}")

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

    data_context = build_data_context(series_data)

    prompt = f"""You are an expert economist. Provide a 2-3 sentence summary.

USER QUESTION: "{query}"

DATA:
{data_context}

Be concise, reference specific numbers, explain what trends mean."""

    try:
        with client.messages.stream(
            model=config.default_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                yield text

    except Exception as e:
        print(f"[AI] Streaming error: {e}")
        yield "Unable to generate summary."
