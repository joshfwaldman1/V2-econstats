"""AI module - All LLM interactions consolidated."""

from .llm_client import get_ai_summary, classify_query, stream_summary, build_rich_data_context
from .summarizer import (
    generate_summary,
    generate_fallback_summary,
    get_summary_text,
    get_suggestions,
    get_chart_descriptions
)
from .bullets import generate_dynamic_bullets, get_static_bullets, get_bullets
from .economist_reviewer import review_summary

# Gemini audit layer (optional - requires GEMINI_API_KEY)
try:
    from .gemini_audit import (
        audit_summary,
        audit_routing,
        quick_fact_check,
        full_audit,
        is_available as gemini_audit_available
    )
except ImportError:
    audit_summary = None
    audit_routing = None
    quick_fact_check = None
    full_audit = None
    gemini_audit_available = lambda: False

__all__ = [
    'get_ai_summary',
    'classify_query',
    'stream_summary',
    'build_rich_data_context',
    'generate_summary',
    'generate_fallback_summary',
    'get_summary_text',
    'get_suggestions',
    'get_chart_descriptions',
    'generate_dynamic_bullets',
    'get_static_bullets',
    'get_bullets',
    'review_summary',
    # Gemini audit
    'audit_summary',
    'audit_routing',
    'quick_fact_check',
    'full_audit',
    'gemini_audit_available',
]
