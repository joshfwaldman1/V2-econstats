"""AI module - All LLM interactions consolidated."""

from .llm_client import get_ai_summary, classify_query, stream_summary
from .summarizer import generate_summary, generate_fallback_summary
from .bullets import generate_dynamic_bullets, get_static_bullets, get_bullets
from .economist_reviewer import review_summary

__all__ = [
    'get_ai_summary',
    'classify_query',
    'stream_summary',
    'generate_summary',
    'generate_fallback_summary',
    'generate_dynamic_bullets',
    'get_static_bullets',
    'get_bullets',
    'review_summary',
]
