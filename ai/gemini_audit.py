"""
Gemini Audit Layer - Fast AI-auditing-AI quality control.

Uses Gemini Flash for speed:
1. Primary Gemini generates initial analysis/routing
2. Audit Gemini reviews and catches errors

This is FAST because Gemini Flash is ~10x faster than Claude
and we use small, focused prompts.
"""

import os
import json
from typing import Optional, Dict, Any, List
from urllib.request import urlopen, Request
from urllib.error import URLError
import ssl

from ai.economic_knowledge import ANTI_PATTERNS, DISPLAY_RULES, DEMOGRAPHIC_SERIES_KNOWLEDGE, SECTOR_SERIES_KNOWLEDGE

# Gemini API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_FLASH_MODEL = "gemini-2.0-flash"  # Fastest model

# SSL context for API calls
_ssl_context = ssl.create_default_context()


def _call_gemini(prompt: str, model: str = GEMINI_FLASH_MODEL, max_tokens: int = 500) -> Optional[str]:
    """
    Call Gemini API directly via HTTP (no SDK needed).

    Args:
        prompt: The prompt to send
        model: Model to use (default: gemini-2.0-flash for speed)
        max_tokens: Maximum response tokens

    Returns:
        Response text or None on error
    """
    if not GEMINI_API_KEY:
        return None

    url = f"{GEMINI_API_URL}/{model}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3  # Lower temp for consistency
        }
    }

    try:
        req = Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urlopen(req, context=_ssl_context, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))

        # Extract text from response
        candidates = result.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            if parts:
                return parts[0].get('text', '')

    except Exception as e:
        print(f"[GeminiAudit] API error: {e}")

    return None


def audit_summary(
    query: str,
    summary: str,
    series_data: List[tuple],
    chart_descriptions: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Audit an AI-generated summary for accuracy and quality.

    Fast check using Gemini Flash to catch:
    - Factual errors (wrong numbers)
    - Misleading interpretations
    - Missing key context
    - Poor chart descriptions

    Args:
        query: Original user query
        summary: Generated summary to audit
        series_data: Data used to generate summary
        chart_descriptions: Optional chart descriptions to audit

    Returns:
        Dict with 'approved', 'issues', 'suggested_fix'
    """
    if not GEMINI_API_KEY:
        return {"approved": True, "issues": [], "suggested_fix": None}

    # Build data context for verification
    data_points = []
    for series_id, dates, values, info in series_data:
        if values:
            name = info.get('name', series_id)
            latest = values[-1]
            data_points.append(f"- {name}: {latest:.2f}")
            if len(values) >= 13:
                yoy = latest - values[-13]
                data_points.append(f"  (YoY change: {yoy:+.2f})")

    data_context = "\n".join(data_points[:10])  # Limit for speed

    prompt = f"""AUDIT this economic summary for accuracy. Be FAST and focused.

USER QUESTION: "{query}"

ACTUAL DATA:
{data_context}

SUMMARY TO AUDIT:
"{summary}"

{f'CHART DESCRIPTIONS: {json.dumps(chart_descriptions)}' if chart_descriptions else ''}

{DISPLAY_RULES}

{ANTI_PATTERNS}

CHECK FOR:
1. Wrong numbers (does summary match actual data?)
2. Misleading claims (overstating/understating trends?)
3. Missing critical context
4. Violations of the display rules and anti-patterns above
5. Chart descriptions that reference meaningless raw index values

Reply in JSON format:
{{"approved": true/false, "issues": ["issue1", "issue2"], "suggested_fix": "brief fix or null"}}

Be FAST - only flag clear errors, not style preferences."""

    response = _call_gemini(prompt, max_tokens=300)

    if response:
        try:
            # Parse JSON from response
            if '{' in response:
                start = response.index('{')
                end = response.rindex('}') + 1
                result = json.loads(response[start:end])
                return {
                    "approved": result.get("approved", True),
                    "issues": result.get("issues", []),
                    "suggested_fix": result.get("suggested_fix")
                }
        except (json.JSONDecodeError, ValueError):
            pass

    # Default: approve if audit fails
    return {"approved": True, "issues": [], "suggested_fix": None}


def audit_routing(
    query: str,
    selected_topic: str,
    selected_series: List[str],
    available_topics: List[str] = None
) -> Dict[str, Any]:
    """
    Audit query routing decision.

    Catches routing mistakes like:
    - "Black unemployment" routed to general unemployment
    - "Women's wages" routed to overall wages
    - Demographic/sector mismatches

    Args:
        query: Original user query
        selected_topic: Topic that was selected
        selected_series: Series that were selected
        available_topics: Optional list of available topics

    Returns:
        Dict with 'approved', 'better_topic', 'reason'
    """
    if not GEMINI_API_KEY:
        return {"approved": True, "better_topic": None, "reason": None}

    prompt = f"""AUDIT this query routing. Be FAST.

USER QUERY: "{query}"
ROUTED TO: "{selected_topic}"
SERIES: {selected_series[:5]}

{DEMOGRAPHIC_SERIES_KNOWLEDGE}

{SECTOR_SERIES_KNOWLEDGE}

COMMON ROUTING ERRORS TO CHECK:
- Demographics ignored ("Black workers" → general data instead of LNS14000006)
- Sector ignored ("manufacturing jobs" → all jobs instead of MANEMP)
- Geographic ignored ("California housing" → national data instead of CAUR)
- Comparison missed ("vs" or "compared to" in query)
- U-6 returned when U-3 (UNRATE) was appropriate

Is this routing correct?

Reply JSON: {{"approved": true/false, "better_topic": "topic_name or null", "reason": "brief reason or null"}}"""

    response = _call_gemini(prompt, max_tokens=200)

    if response:
        try:
            if '{' in response:
                start = response.index('{')
                end = response.rindex('}') + 1
                result = json.loads(response[start:end])
                return {
                    "approved": result.get("approved", True),
                    "better_topic": result.get("better_topic"),
                    "reason": result.get("reason")
                }
        except (json.JSONDecodeError, ValueError):
            pass

    return {"approved": True, "better_topic": None, "reason": None}


def quick_fact_check(claim: str, data_value: float, tolerance: float = 0.1) -> bool:
    """
    Ultra-fast fact check for a single claim.

    Args:
        claim: Text claim to check (e.g., "unemployment is at 4.2%")
        data_value: Actual data value
        tolerance: Acceptable error margin (default 10%)

    Returns:
        True if claim appears accurate, False if suspicious
    """
    if not GEMINI_API_KEY:
        return True  # Assume accurate if no API

    prompt = f"""FACT CHECK (reply only "yes" or "no"):

Claim: "{claim}"
Actual value: {data_value:.2f}
Tolerance: ±{tolerance*100:.0f}%

Is the claim approximately accurate?"""

    response = _call_gemini(prompt, max_tokens=10)

    if response:
        return "yes" in response.lower()

    return True  # Default to trust


def audit_bullets(
    query: str,
    charts: List[Dict[str, Any]],
    series_data: List[tuple]
) -> List[Dict[str, Any]]:
    """
    Audit chart bullets for accuracy using Gemini Flash.

    Reviews each chart's bullets against the actual data to catch:
    - Numbers that don't match the data
    - Percentage-point vs percent confusion on rates
    - Misleading interpretations
    - Anti-pattern violations (e.g., "rising 4.8% YoY" for a 4.2% rate)

    Args:
        query: Original user query
        charts: List of chart dicts (each with 'bullets', 'series_id', 'name')
        series_data: List of (series_id, dates, values, info) tuples

    Returns:
        List of charts with corrected bullets (bullets replaced if issues found)
    """
    if not GEMINI_API_KEY:
        return charts

    # Build data lookup for verification
    data_lookup = {}
    for sid, dates, values, info in series_data:
        if values:
            data_lookup[sid] = {
                'name': info.get('name', info.get('title', sid)),
                'latest': values[-1],
                'latest_date': dates[-1] if dates else 'unknown',
                'yoy_change': (values[-1] - values[-13]) if len(values) >= 13 else None,
            }

    # Review each chart's bullets
    for chart in charts:
        bullets = chart.get('bullets', [])
        if not bullets:
            continue

        series_id = chart.get('series_id', '')

        # For combined charts, gather data for all traces
        chart_data_context = []
        if chart.get('is_combined') and chart.get('traces'):
            for trace in chart['traces']:
                tid = trace.get('series_id', '')
                if tid in data_lookup:
                    d = data_lookup[tid]
                    chart_data_context.append(
                        f"- {d['name']}: latest={d['latest']:.2f}"
                        + (f", YoY change={d['yoy_change']:+.2f}" if d['yoy_change'] is not None else "")
                    )
        elif series_id in data_lookup:
            d = data_lookup[series_id]
            chart_data_context.append(
                f"- {d['name']}: latest={d['latest']:.2f}"
                + (f", YoY change={d['yoy_change']:+.2f}" if d['yoy_change'] is not None else "")
            )

        if not chart_data_context:
            continue

        prompt = f"""FAST REVIEW of chart bullets for accuracy.

QUERY: "{query}"
CHART: "{chart.get('name', series_id)}"

ACTUAL DATA:
{chr(10).join(chart_data_context)}

BULLETS TO REVIEW:
{chr(10).join(f'- "{b}"' for b in bullets)}

{ANTI_PATTERNS}

Are these bullets accurate? Check:
1. Numbers match the actual data above?
2. No percentage-of-a-percentage errors (e.g., "unemployment rising 5% YoY" when rate went from 3.5% to 3.7%)?
3. Clear and insightful?

Reply JSON: {{"approved": true/false, "fixed_bullets": ["bullet1", "bullet2"] or null}}
Only provide fixed_bullets if you found actual errors. Keep fixes minimal."""

        response = _call_gemini(prompt, max_tokens=300)

        if response:
            try:
                if '{' in response:
                    start = response.index('{')
                    end = response.rindex('}') + 1
                    result = json.loads(response[start:end])

                    if not result.get('approved', True) and result.get('fixed_bullets'):
                        fixed = result['fixed_bullets']
                        if isinstance(fixed, list) and len(fixed) > 0:
                            print(f"[GeminiAudit] Fixed bullets for {series_id}: {result.get('approved')}")
                            chart['bullets'] = fixed[:3]
            except (json.JSONDecodeError, ValueError):
                pass

    return charts


def is_available() -> bool:
    """Check if Gemini audit is available."""
    return bool(GEMINI_API_KEY)


# Convenience function for full audit pipeline
def full_audit(
    query: str,
    summary: str,
    series_data: List[tuple],
    selected_topic: str = None,
    chart_descriptions: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Run full audit pipeline on AI output.

    Runs both summary audit and routing audit in sequence.
    Fast because each uses Gemini Flash with small prompts.

    Args:
        query: Original user query
        summary: Generated summary
        series_data: Data used for summary
        selected_topic: Topic that was routed to
        chart_descriptions: Optional chart descriptions

    Returns:
        Combined audit results
    """
    results = {
        "overall_approved": True,
        "summary_audit": None,
        "routing_audit": None,
        "needs_regeneration": False
    }

    # Audit summary
    summary_result = audit_summary(query, summary, series_data, chart_descriptions)
    results["summary_audit"] = summary_result

    if not summary_result["approved"]:
        results["overall_approved"] = False
        results["needs_regeneration"] = bool(summary_result.get("suggested_fix"))

    # Audit routing if topic provided
    if selected_topic:
        series_ids = [s[0] for s in series_data]
        routing_result = audit_routing(query, selected_topic, series_ids)
        results["routing_audit"] = routing_result

        if not routing_result["approved"]:
            results["overall_approved"] = False
            # Routing errors are more serious
            results["needs_regeneration"] = True

    return results
