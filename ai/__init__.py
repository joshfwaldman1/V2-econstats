"""AI module - All LLM interactions consolidated."""

from .llm_client import get_ai_summary, classify_query
from .summarizer import generate_summary

__all__ = ['get_ai_summary', 'classify_query', 'generate_summary']
