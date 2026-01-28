"""
Unified LLM Client - All Claude API interactions.

Consolidates:
- AI summary generation with rich context (V1 parity)
- Query classification
- Optional streaming support
- Chart descriptions for each series

NOTE: All math is done with pandas in processing/analytics.py.
The LLM receives pre-computed values - it should NEVER calculate.
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import config
from cache import cache_manager
from processing.analytics import compute_series_analytics, analytics_to_text
from ai.economic_knowledge import (
    get_compact_knowledge_prompt,
    get_series_catalog_text,
    get_full_knowledge_prompt,
    ANTI_PATTERNS,
    DISPLAY_RULES,
)

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

    # Use the master knowledge base for consistent rules across all prompts
    knowledge_rules = get_compact_knowledge_prompt()

    prompt = f"""You are an expert economist providing clear, insightful analysis of economic data for a general audience.

{knowledge_rules}

USER QUESTION: "{query}"
{conv_context}

CURRENT DATA:
{data_context}

## TASK: Return a JSON object with three parts:

1. "summary": A 3-4 sentence expert summary that:
   - Directly answers the user's question with specific numbers
   - Explains what trends MEAN for workers, consumers, or the economy
   - Puts current values in context (vs historical average, pre-pandemic, vs national average for state data)
   - Uses plain language accessible to non-economists
   - For STATE data: always compare to the national rate (e.g., "Minnesota's 3.2% is below the national 4.1%")

2. "suggestions": Array of 3 follow-up questions the user might want to ask

3. "chart_descriptions": Object mapping series_id to a 1-sentence description for EACH chart

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

    All math is computed by pandas in processing/analytics.py.
    The LLM receives pre-computed values - it should NEVER calculate.

    Includes:
    - Latest value with date
    - YoY change (absolute and percentage)
    - Short-term trend
    - 1-year and 5-year range
    - Momentum direction
    """
    lines = []
    for series_id, dates, values, info in series_data:
        if not values or len(values) < 2:
            continue

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
            continue

        # Build context from pre-computed values
        name = info.get('name', info.get('title', series_id))
        unit = info.get('unit', info.get('units', ''))

        context_parts = [
            f"{name} ({series_id}): {analytics['latest_value']:.2f} {unit} as of {analytics['latest_date_formatted']}"
        ]

        # YoY (pre-computed)
        if 'yoy' in analytics:
            yoy = analytics['yoy']
            if yoy.get('change_pct') is not None:
                context_parts.append(f"YoY: {yoy['change']:+.2f} ({yoy['change_pct']:+.1f}%)")
            else:
                context_parts.append(f"YoY: {yoy['change']:+.2f}")

        # Short-term trend (pre-computed)
        if 'short_term' in analytics:
            st = analytics['short_term']
            if st.get('change_pct') is not None:
                context_parts.append(f"Recent: {st['direction'].capitalize()} ({st['change_pct']:+.1f}%)")
            else:
                context_parts.append(f"Recent: {st['direction'].capitalize()}")

        # 1-year range (pre-computed)
        if 'range_1y' in analytics:
            r = analytics['range_1y']
            context_parts.append(f"1Y range: {r['low']:.2f} - {r['high']:.2f} ({r['pct_from_high']:+.1f}% from high)")

        # 5-year stats (pre-computed)
        if 'range_5y' in analytics:
            r5 = analytics['range_5y']
            context_parts.append(f"5Y avg: {r5['mean']:.2f}, std: {r5['std']:.2f}")

        # Momentum (pre-computed)
        if 'momentum' in analytics:
            m = analytics['momentum']
            context_parts.append(f"Momentum: {m['direction']}")

        # FRED notes (if available)
        notes = info.get('notes', '')
        if notes and len(notes) > 20:
            context_parts.append(f"Context: {notes[:300]}")

        lines.append(" | ".join(context_parts))

    return "\n".join(lines) if lines else "No data available."


def build_dynamic_plan(query: str, available_series: List[Dict]) -> Optional[Dict[str, Any]]:
    """
    Dynamically build a query plan when no pre-built plan matches.

    Instead of picking from existing plans (which may not cover the query),
    this selects appropriate series directly based on the query intent.

    Args:
        query: The user's question
        available_series: List of dicts with 'id', 'name', 'description'

    Returns:
        Dict with 'series', 'show_yoy', 'explanation' or None if can't build
    """
    client = get_client()
    if not client:
        return None

    # Use the master knowledge base for series catalog and rules
    knowledge_rules = get_compact_knowledge_prompt()
    series_catalog_from_kb = get_series_catalog_text()

    # Also include any additional series passed in (e.g., from registry)
    extra_series = "\n".join([
        f"- {s['id']}: {s['name']} - {s.get('description', '')[:100]}"
        for s in available_series[:50]
        if s['id'] not in series_catalog_from_kb  # Avoid duplicates
    ])

    prompt = f"""You are a senior economic analyst. A user asks a question, and you need to decide what data to show them.

{knowledge_rules}

USER QUESTION: "{query}"

Think: What charts would a smart analyst show to EXPLAIN THE ANSWER to this person?
- Don't just match keywords - think about what data actually answers their question
- Select 1-4 series that would help you EXPLAIN THE ANSWER

AVAILABLE FRED SERIES (organized by topic):
{series_catalog_from_kb}

{f"ADDITIONAL AVAILABLE SERIES:{chr(10)}{extra_series}" if extra_series else ""}

DISPLAY RULES:
- show_yoy=true for INDEXES (CPI, home prices) - raw index values are meaningless
- show_yoy=false for RATES (unemployment %, fed funds %) - already interpretable

Reply in JSON:
{{"series": ["SERIES_ID1", "SERIES_ID2"], "show_yoy": true/false, "explanation": "What this data shows"}}

If you can't answer with available data: {{"series": [], "explanation": "Why not"}}"""

    try:
        response = client.messages.create(
            model=config.default_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        print(f"[AI] Dynamic plan for '{query}': {text[:100]}...")

        # Parse JSON response
        if '{' in text:
            start = text.index('{')
            end = text.rindex('}') + 1
            result = json.loads(text[start:end])

            if result.get('series'):
                return {
                    'series': result['series'],
                    'show_yoy': result.get('show_yoy', False),
                    'explanation': result.get('explanation', ''),
                    'dynamic': True  # Flag that this was dynamically built
                }
    except Exception as e:
        print(f"[AI] Dynamic plan error: {e}")

    return None


def classify_query(query: str, available_topics: List[str]) -> Optional[Dict[str, Any]]:
    """
    Use LLM to understand query intent and route to appropriate topic.

    NOTE: This is the OLD approach - picks from existing plan names.
    Prefer build_dynamic_plan() which can select series directly.

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

{DISPLAY_RULES}

{ANTI_PATTERNS}

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

    # Use the master knowledge base for consistent display rules
    knowledge_rules = get_compact_knowledge_prompt()

    prompt = f"""You are an expert economist. Provide a 3-4 sentence summary.

{knowledge_rules}

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
