"""
Query logging for EconStats.

Logs every search to learn what users are asking and how well we're answering.
Data is stored locally and can be analyzed to improve the system.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import hashlib

# Log file location
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "query_log.jsonl"

# Ensure log directory exists
LOG_DIR.mkdir(exist_ok=True)


def _get_session_id() -> str:
    """Generate a simple session ID based on current hour (groups related searches)."""
    return datetime.now().strftime("%Y%m%d_%H")


def _hash_query(query: str) -> str:
    """Create a short hash of the query for grouping similar searches."""
    return hashlib.md5(query.lower().strip().encode()).hexdigest()[:8]


def log_query(
    query: str,
    series: list,
    method: str,
    explanation: str = "",
    reasoning_indicators: list = None,
    is_comparison: bool = False,
    sources: dict = None,
    response_time_ms: int = None,
    previous_query: str = None,
):
    """
    Log a query and its results.

    Args:
        query: The user's search query
        series: List of series IDs returned
        method: How the query was resolved (direct, reasoning, precomputed, hybrid, etc.)
        explanation: The explanation shown to user
        reasoning_indicators: If reasoning was used, what indicators were identified
        is_comparison: Whether this was a comparison query
        sources: Dict of sources used (fred, dbnomics, etc.)
        response_time_ms: How long the query took
        previous_query: If this looks like a retry, what was the previous query
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": _get_session_id(),
        "query": query,
        "query_hash": _hash_query(query),
        "series": series,
        "series_count": len(series),
        "method": method,
        "is_comparison": is_comparison,
    }

    # Optional fields
    if explanation:
        entry["explanation"] = explanation[:200]  # Truncate long explanations
    if reasoning_indicators:
        entry["reasoning_indicators"] = reasoning_indicators
    if sources:
        entry["sources"] = sources
    if response_time_ms:
        entry["response_time_ms"] = response_time_ms
    if previous_query:
        entry["previous_query"] = previous_query
        entry["is_retry"] = True

    # Detect potential issues
    entry["flags"] = []
    if not series:
        entry["flags"].append("no_results")
    if method == "reasoning" and not reasoning_indicators:
        entry["flags"].append("reasoning_no_indicators")
    if len(series) == 1 and method != "direct":
        entry["flags"].append("single_series")

    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[QueryLogger] Error writing log: {e}")


def get_recent_queries(hours: int = 24) -> list:
    """Get queries from the last N hours."""
    if not LOG_FILE.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    recent = []

    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if ts >= cutoff:
                        recent.append(entry)
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as e:
        print(f"[QueryLogger] Error reading log: {e}")

    return recent


def get_query_stats(hours: int = 24) -> dict:
    """Get statistics on recent queries."""
    queries = get_recent_queries(hours)

    if not queries:
        return {"total": 0, "message": "No queries logged yet"}

    stats = {
        "total": len(queries),
        "period_hours": hours,
        "methods": {},
        "flags": {},
        "unique_queries": len(set(q["query_hash"] for q in queries)),
        "avg_series_count": sum(q["series_count"] for q in queries) / len(queries),
    }

    # Count by method
    for q in queries:
        method = q.get("method", "unknown")
        stats["methods"][method] = stats["methods"].get(method, 0) + 1

    # Count flags (issues)
    for q in queries:
        for flag in q.get("flags", []):
            stats["flags"][flag] = stats["flags"].get(flag, 0) + 1

    # Find retries (potential dissatisfaction)
    stats["retries"] = sum(1 for q in queries if q.get("is_retry"))

    # Most common queries
    query_counts = {}
    for q in queries:
        qtext = q["query"].lower().strip()
        query_counts[qtext] = query_counts.get(qtext, 0) + 1
    stats["top_queries"] = sorted(query_counts.items(), key=lambda x: -x[1])[:10]

    # Queries with no results
    stats["no_result_queries"] = [
        q["query"] for q in queries if "no_results" in q.get("flags", [])
    ]

    return stats


def get_improvement_suggestions() -> list:
    """Analyze logs and suggest improvements."""
    stats = get_query_stats(hours=168)  # Last week
    suggestions = []

    if stats.get("total", 0) < 10:
        return ["Not enough data yet. Need more queries to analyze."]

    # Queries with no results should be added
    no_results = stats.get("no_result_queries", [])
    if no_results:
        unique_no_results = list(set(no_results))[:5]
        suggestions.append(f"Add coverage for: {unique_no_results}")

    # High retry rate suggests poor results
    retry_rate = stats.get("retries", 0) / stats["total"]
    if retry_rate > 0.2:
        suggestions.append(f"High retry rate ({retry_rate:.0%}) - users are re-searching")

    # Top queries not using direct mapping should be added
    top_queries = stats.get("top_queries", [])
    queries = get_recent_queries(168)
    for query_text, count in top_queries[:5]:
        if count >= 3:
            # Check if this query uses direct mapping
            matching = [q for q in queries if q["query"].lower().strip() == query_text]
            if matching and matching[0].get("method") != "direct":
                suggestions.append(f"Add direct mapping for '{query_text}' (asked {count}x)")

    # Low average series count might indicate incomplete answers
    avg_series = stats.get("avg_series_count", 0)
    if avg_series < 2:
        suggestions.append(f"Low avg series count ({avg_series:.1f}) - answers may be incomplete")

    return suggestions if suggestions else ["No immediate improvements identified."]


def print_daily_report():
    """Print a daily report of query activity."""
    stats = get_query_stats(hours=24)

    print("\n" + "=" * 60)
    print("ECONSTATS DAILY QUERY REPORT")
    print("=" * 60)

    print(f"\nTotal queries: {stats.get('total', 0)}")
    print(f"Unique queries: {stats.get('unique_queries', 0)}")
    print(f"Avg series per query: {stats.get('avg_series_count', 0):.1f}")
    print(f"Retries: {stats.get('retries', 0)}")

    print("\nMethods used:")
    for method, count in sorted(stats.get("methods", {}).items(), key=lambda x: -x[1]):
        print(f"  {method}: {count}")

    print("\nIssues flagged:")
    for flag, count in sorted(stats.get("flags", {}).items(), key=lambda x: -x[1]):
        print(f"  {flag}: {count}")

    print("\nTop queries:")
    for query, count in stats.get("top_queries", [])[:5]:
        print(f"  [{count}x] {query}")

    no_results = stats.get("no_result_queries", [])
    if no_results:
        print("\nQueries with no results:")
        for q in list(set(no_results))[:5]:
            print(f"  - {q}")

    print("\nSuggested improvements:")
    for suggestion in get_improvement_suggestions():
        print(f"  → {suggestion}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    print_daily_report()
