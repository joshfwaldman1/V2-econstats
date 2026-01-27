"""
AI Summarizer - Generate economic data summaries with audit layer.

Wraps llm_client functions with:
- Rich context generation
- Gemini audit layer (optional, fast)
- Conversation history support
"""

from typing import List, Optional, Dict, Any

from .llm_client import get_ai_summary, build_rich_data_context
from config import config


def generate_summary(
    query: str,
    series_data: List[tuple],
    conversation_history: List[Dict] = None,
    use_cache: bool = True,
    enable_audit: bool = None
) -> Dict[str, Any]:
    """
    Generate a rich summary with chart descriptions and suggestions.

    This is the main entry point for summary generation.

    Args:
        query: The user's question
        series_data: List of (series_id, dates, values, info) tuples
        conversation_history: Optional list of previous exchanges
        use_cache: Whether to use caching
        enable_audit: Whether to run Gemini audit (None = use config)

    Returns:
        Dict with 'summary', 'suggestions', 'chart_descriptions', and audit info
    """
    if not series_data:
        return {
            "summary": "No data available to summarize.",
            "suggestions": [],
            "chart_descriptions": {},
            "audit": None
        }

    # Filter to series with actual data
    valid_data = [(sid, dates, values, info) for sid, dates, values, info in series_data
                  if dates and values]

    if not valid_data:
        return {
            "summary": "Unable to fetch data for the requested series.",
            "suggestions": [],
            "chart_descriptions": {},
            "audit": None
        }

    # Generate rich summary
    result = get_ai_summary(
        query,
        valid_data,
        conversation_history=conversation_history,
        cached=use_cache
    )

    # Run Gemini audit if enabled
    if enable_audit is None:
        enable_audit = config.enable_gemini_audit if hasattr(config, 'enable_gemini_audit') else False

    if enable_audit:
        try:
            from .gemini_audit import full_audit, is_available

            if is_available():
                audit_result = full_audit(
                    query=query,
                    summary=result.get("summary", ""),
                    series_data=valid_data,
                    chart_descriptions=result.get("chart_descriptions", {})
                )
                result["audit"] = audit_result

                # If audit found issues and suggests regeneration, try once more
                if audit_result.get("needs_regeneration") and audit_result.get("summary_audit", {}).get("suggested_fix"):
                    print(f"[Summarizer] Audit found issues, regenerating...")
                    # Don't use cache for regeneration
                    result = get_ai_summary(query, valid_data, conversation_history, cached=False)
                    result["audit"] = {"regenerated": True, "original_issues": audit_result}
            else:
                result["audit"] = None
        except ImportError:
            result["audit"] = None
    else:
        result["audit"] = None

    return result


def generate_fallback_summary(
    query: str,
    series_data: List[tuple]
) -> Dict[str, Any]:
    """
    Generate a simple summary without LLM for fallback.

    Used when LLM is unavailable or for simple queries.
    """
    if not series_data:
        return {
            "summary": "No data available.",
            "suggestions": [],
            "chart_descriptions": {}
        }

    parts = []
    chart_descriptions = {}

    for series_id, dates, values, info in series_data:
        if not values:
            continue

        name = info.get('name', info.get('title', series_id))
        latest = values[-1]
        unit = info.get('unit', info.get('units', ''))

        desc = f"{name} is currently at {latest:.2f} {unit}"
        parts.append(desc)
        chart_descriptions[series_id] = desc

    return {
        "summary": ". ".join(parts) + "." if parts else "Data retrieved successfully.",
        "suggestions": ["What's the trend?", "Compare to last year", "Historical context"],
        "chart_descriptions": chart_descriptions
    }


def get_summary_text(result: Dict[str, Any]) -> str:
    """Extract just the summary text from a result dict."""
    if isinstance(result, dict):
        return result.get("summary", "")
    return str(result)


def get_suggestions(result: Dict[str, Any]) -> List[str]:
    """Extract suggestions from a result dict."""
    if isinstance(result, dict):
        return result.get("suggestions", [])
    return []


def get_chart_descriptions(result: Dict[str, Any]) -> Dict[str, str]:
    """Extract chart descriptions from a result dict."""
    if isinstance(result, dict):
        return result.get("chart_descriptions", {})
    return {}
