"""
Search API Endpoint

The main endpoint for economic data queries.
Supports both JSON API (for React) and HTML (legacy).
"""

import json
from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, Form, Request, Body
from fastapi.responses import HTMLResponse, JSONResponse

from routing import router as query_router
from sources import source_manager
from processing import format_chart_data, format_combined_chart, extract_temporal_filter, get_smart_date_range, auto_group_series
from processing.temporal import filter_data_by_dates
from ai import generate_summary, get_bullets, review_summary, get_summary_text, get_suggestions as get_ai_suggestions, get_chart_descriptions
from config import config
from registry import registry

# Gemini Flash audit layer for bullet/summary review
try:
    from ai.gemini_audit import audit_bullets, is_available as gemini_available
    GEMINI_AUDIT_AVAILABLE = gemini_available()
except ImportError:
    audit_bullets = None
    GEMINI_AUDIT_AVAILABLE = False
    print("[Search] Gemini audit not available")

# Judgment layer for interpretive queries (adds expert quotes, thresholds, web search)
try:
    from agents.judgment_layer import is_judgment_query, process_judgment_query
    JUDGMENT_AVAILABLE = True
except ImportError:
    JUDGMENT_AVAILABLE = False
    print("[Search] Judgment layer not available")

# Recession scorecard — built from live FRED data after fetching
try:
    from agents.recession_scorecard import (
        is_recession_query, build_recession_scorecard, format_scorecard_for_display
    )
    RECESSION_SCORECARD_AVAILABLE = True
except ImportError:
    RECESSION_SCORECARD_AVAILABLE = False
    print("[Search] Recession scorecard not available")

search_router = APIRouter()


# =============================================================================
# RECESSION SCORECARD HELPER
# =============================================================================
# The recession scorecard needs LIVE indicator values to show meaningful
# red/yellow/green status lights. The routing layer can flag that a recession
# scorecard is needed, but the actual scorecard must be built AFTER FRED data
# is fetched so the indicator values are real.

# Mapping of FRED series IDs to recession scorecard parameter names
_SCORECARD_SERIES_MAP = {
    'SAHMREALTIME': 'sahm_value',
    'T10Y2Y': 'yield_curve_value',
    'UMCSENT': 'sentiment_value',
    'ICSA': 'claims_value',
    'USSLIND': 'lei_value',
    'NAPM': 'pmi_value',
    'BAMLH0A0HYM2': 'credit_spread_value',
}


def _build_live_recession_scorecard(series_data: list) -> Optional[str]:
    """
    Build a recession scorecard HTML box from live FRED data.

    Extracts the latest values from fetched series_data for any recession
    indicator series present, then builds the scorecard with real values
    instead of empty/unknown.

    Args:
        series_data: List of (series_id, dates, values, info) tuples from FRED.

    Returns:
        HTML string for the scorecard, or None if no recession indicators found
        or the scorecard module is unavailable.
    """
    if not RECESSION_SCORECARD_AVAILABLE:
        return None

    # Extract latest values for each recession indicator from fetched data
    scorecard_kwargs = {}
    for sid, dates, values, info in series_data:
        param_name = _SCORECARD_SERIES_MAP.get(sid)
        if param_name and values:
            scorecard_kwargs[param_name] = values[-1]  # Latest value

    if not scorecard_kwargs:
        return None

    # Build the scorecard with real values
    scorecard = build_recession_scorecard(**scorecard_kwargs)
    if scorecard and scorecard.get('indicators'):
        return format_scorecard_for_display(scorecard)

    return None


# =============================================================================
# PYDANTIC MODELS FOR JSON API
# =============================================================================

class SearchRequest(BaseModel):
    """JSON search request body."""
    query: str
    history: List[str] = []


class MetricResponse(BaseModel):
    """Metric card data."""
    label: str
    value: str
    change: Optional[str] = None
    changeType: Optional[str] = None  # 'positive', 'negative', 'neutral'
    description: Optional[str] = None  # Short description of what this metric measures


class ChartResponse(BaseModel):
    """Chart data for frontend."""
    series_id: str
    name: str
    unit: str
    source: str
    dates: List[str]
    values: List[float]
    latest: Optional[float]
    latest_date: str
    is_job_change: bool
    is_payems_level: bool
    three_mo_avg: Optional[float]
    yoy_change: Optional[float]
    yoy_type: Optional[str]
    bullets: List[str]
    sa: bool
    recessions: List[dict]
    description: str


class SourceInfo(BaseModel):
    """Source citation for a data series."""
    series_id: str
    name: str
    url: str


class SearchResponse(BaseModel):
    """JSON search response."""
    query: str
    summary: str
    suggestions: List[str]
    chart_descriptions: dict
    charts: List[dict]
    metrics: List[MetricResponse]
    sources: List[SourceInfo] = []
    temporal_context: Optional[str]
    fed_sep_html: Optional[str]
    recession_html: Optional[str]
    cape_html: Optional[str]
    polymarket_html: Optional[str]
    error: Optional[str]


# =============================================================================
# JSON API ENDPOINTS (for React frontend)
# =============================================================================

@search_router.post("/api/search", response_model=SearchResponse)
async def api_search(body: SearchRequest):
    """
    JSON API endpoint for React frontend.

    Returns structured JSON with all data needed for rendering.
    """
    query = body.query
    history = body.history

    # 1. Route the query
    routing_result = query_router.route(query)

    if not routing_result.series:
        return SearchResponse(
            query=query,
            summary="",
            suggestions=["How is inflation?", "Job market health", "GDP growth"],
            chart_descriptions={},
            charts=[],
            metrics=[],
            temporal_context=None,
            fed_sep_html=None,
            recession_html=None,
            cape_html=None,
            polymarket_html=None,
            error="No matching economic data found for your query. Try rephrasing or asking about specific topics like inflation, jobs, or GDP."
        )

    # 2. Extract temporal context
    temporal = extract_temporal_filter(query)
    years = get_smart_date_range(query, config.default_years)
    if temporal and temporal.get('years_override'):
        years = temporal['years_override']

    # 3. Fetch data for all series IN PARALLEL (major performance improvement)
    results = await source_manager.fetch_many(routing_result.series, years)

    series_data = []
    fetch_errors = []
    for result in results:
        if result.is_valid:
            dates = result.dates
            values = result.values

            # Apply temporal filtering if specified
            if temporal:
                start_date = temporal.get('filter_start_date')
                end_date = temporal.get('filter_end_date')
                if start_date or end_date:
                    dates, values = filter_data_by_dates(dates, values, start_date, end_date)

            if dates and values:
                series_data.append((result.id, dates, values, result.info))
        elif result.error:
            fetch_errors.append(f"{result.id}: {result.error}")

    if not series_data:
        # Build a specific error message from individual series failures
        if fetch_errors:
            # Show the first 3 specific errors so users know what went wrong
            error_detail = "; ".join(fetch_errors[:3])
            if "rate limit" in error_detail.lower():
                error_msg = f"FRED API rate limit reached. Please wait a moment and try again. ({error_detail})"
            elif "not exist" in error_detail.lower() or "Bad request" in error_detail.lower():
                error_msg = f"Series not found: {error_detail}"
            else:
                error_msg = f"Unable to fetch data: {error_detail}"
        else:
            error_msg = "Unable to fetch data for the requested series. Please try again."

        return SearchResponse(
            query=query,
            summary="",
            suggestions=["How is inflation?", "Job market health", "GDP growth"],
            chart_descriptions={},
            charts=[],
            metrics=[],
            temporal_context=None,
            fed_sep_html=None,
            recession_html=None,
            cape_html=None,
            polymarket_html=None,
            error=error_msg
        )

    # 4. Format chart data using auto-grouping
    charts = []
    groups = auto_group_series(series_data, routing_result)

    for group in groups:
        if len(group.series_data) > 1:
            # Multi-series group → combined chart with multiple traces
            combined = format_combined_chart(
                group.series_data,
                show_yoy=group.show_yoy,
                user_query=query,
                chart_title=group.title,
            )
            if combined:
                # Generate AI bullets for each series in the combined chart
                combined_bullets = []
                for sid, d, v, inf in group.series_data:
                    b = get_bullets(sid, d, v, inf, user_query=query)
                    if b:
                        combined_bullets.append(b[0])  # 1 bullet per series
                combined['bullets'] = combined_bullets[:3]  # Max 3 for combined
                charts.append(combined)
            else:
                # Combination refused by chart crime prevention → separate charts
                for sid, d, v, inf in group.series_data:
                    chart = format_chart_data(sid, d, v, inf, show_yoy=group.show_yoy, user_query=query)
                    chart['bullets'] = get_bullets(sid, d, v, inf, user_query=query)
                    charts.append(chart)
        else:
            # Single series → individual chart
            sid, d, v, inf = group.series_data[0]
            chart = format_chart_data(sid, d, v, inf, show_yoy=group.show_yoy, user_query=query)
            chart['bullets'] = get_bullets(sid, d, v, inf, user_query=query)
            charts.append(chart)

    # 4b. Gemini Flash review of chart bullets
    if GEMINI_AUDIT_AVAILABLE and config.enable_gemini_audit and audit_bullets:
        try:
            charts = audit_bullets(query, charts, series_data)
        except Exception as e:
            print(f"[Search] Bullet audit error: {e}")

    # 5. Generate AI summary (returns dict with summary, suggestions, chart_descriptions)
    # Build conversation history from request history for context
    conversation_history = [{"query": q} for q in history] if history else None
    summary_result = generate_summary(query, series_data, conversation_history=conversation_history)

    # Handle both dict and string returns
    if isinstance(summary_result, dict):
        summary_text = summary_result.get('summary', '')
        ai_suggestions = summary_result.get('suggestions', [])
        chart_descriptions = summary_result.get('chart_descriptions', {})
    else:
        summary_text = str(summary_result)
        ai_suggestions = []
        chart_descriptions = {}

    # 5b. Judgment layer for interpretive queries (adds expert quotes, thresholds, web search)
    if JUDGMENT_AVAILABLE and is_judgment_query(query):
        try:
            judgment_result, was_judgment = process_judgment_query(
                query=query,
                series_data=series_data,
                original_explanation=summary_text
            )
            if judgment_result and was_judgment:
                summary_text = judgment_result
                print(f"[Search] Enhanced with judgment layer")
        except Exception as e:
            print(f"[Search] Judgment error: {e}")

    # Apply economist reviewer if enabled
    if config.enable_economist_reviewer and summary_text:
        summary_text = review_summary(query, series_data, summary_text)

    # 6. Get Polymarket predictions if relevant
    polymarket_html = query_router.get_polymarket_html(query)

    # 7. Build metrics from chart data (deduplicate by series_id to avoid
    #    duplicate metric cards when the same series appears in multiple chart groups)
    metrics = []
    seen_metric_ids = set()
    for chart in charts[:8]:  # Check more charts but cap metrics at 4
        series_id = chart.get('series_id', '')
        if series_id in seen_metric_ids:
            continue
        seen_metric_ids.add(series_id)
        if len(metrics) >= 4:
            break
        series_info = registry.get_series(series_id)
        latest = chart.get('latest', 0)
        unit = chart.get('unit', '')

        # Format the value with unit awareness
        # FRED series with "Thousands" unit: values are already in thousands,
        # so 7000 = 7,000 thousands = 7 million, NOT 7 thousand.
        if chart.get('is_job_change'):
            formatted_value = f"{latest:+.0f}K/mo"
        elif chart.get('is_payems_level'):
            formatted_value = f"{latest / 1000:.1f}M"
        elif 'Percent' in unit or '%' in unit:
            formatted_value = f"{latest:.1f}%"
        elif 'Thousand' in unit:
            if latest >= 1000:
                formatted_value = f"{latest / 1000:.1f}M"
            else:
                formatted_value = f"{latest:.0f}K"
        elif latest > 1000000:
            formatted_value = f"{latest / 1000000:.1f}M"
        elif latest > 1000:
            formatted_value = f"{latest / 1000:.0f}K"
        else:
            formatted_value = f"{latest:.1f}"

        metric = MetricResponse(
            label=chart.get('name', chart.get('series_id', 'Unknown')),
            value=formatted_value if latest else 'N/A',
            description=series_info.short_description if series_info and series_info.short_description else None,
        )
        if chart.get('yoy_change') is not None:
            yoy = chart['yoy_change']
            if chart.get('yoy_type') == 'pp':
                metric.change = f"{yoy:+.1f} pp"
            elif chart.get('yoy_type') == 'jobs':
                if chart.get('is_job_change'):
                    # 12-month average monthly change (already divided by 12 in formatter)
                    metric.change = f"{yoy:+.0f}K/mo avg"
                else:
                    metric.change = f"{yoy/1000:+.0f}K"
            else:
                metric.change = f"{yoy:+.1f}%"
            metric.changeType = 'positive' if yoy > 0 else 'negative' if yoy < 0 else 'neutral'
        metrics.append(metric)

    # Use AI suggestions if available, otherwise generate static ones
    suggestions = ai_suggestions if ai_suggestions else generate_suggestions(query, routing_result.series)

    # 8. Build source citations
    sources = []
    for sid, dates, values, info in series_data:
        sources.append(SourceInfo(
            series_id=sid,
            name=info.get('title', info.get('name', sid)),
            url=f"https://fred.stlouisfed.org/series/{sid}"
        ))

    # 9. Build live recession scorecard from fetched data if applicable
    # The routing layer may have set recession_html, but it was built without
    # actual data values. Rebuild it with the live FRED data we just fetched.
    recession_html = routing_result.recession_html
    if RECESSION_SCORECARD_AVAILABLE and is_recession_query(query):
        live_scorecard = _build_live_recession_scorecard(series_data)
        if live_scorecard:
            recession_html = live_scorecard

    return SearchResponse(
        query=query,
        summary=summary_text,
        suggestions=suggestions,
        chart_descriptions=chart_descriptions,
        charts=charts,
        metrics=metrics,
        sources=sources,
        temporal_context=temporal.get('explanation') if temporal else None,
        fed_sep_html=routing_result.fed_sep_html,
        recession_html=recession_html,
        cape_html=routing_result.cape_html,
        polymarket_html=polymarket_html,
        error=None
    )


@search_router.post("/api/search/stream")
async def api_search_stream(body: SearchRequest):
    """
    Streaming search endpoint using Server-Sent Events.

    Sends charts/metrics/sources immediately, then streams the AI summary
    token-by-token. This gives users visual feedback within ~500ms instead of
    waiting 2-5 seconds for the full response.

    Event sequence:
        1. charts   — formatted chart data + metric cards
        2. special  — Fed SEP / recession / CAPE / Polymarket HTML boxes
        3. sources  — FRED source citations with URLs
        4. summary_chunk (repeated) — streaming summary text
        5. done     — suggestions + chart_descriptions
    """
    from fastapi.responses import StreamingResponse
    from ai import stream_summary

    query = body.query
    history = body.history

    async def event_generator():
        # 1. Route query
        routing_result = query_router.route(query)

        if not routing_result.series:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No matching economic data found for your query.'})}\n\n"
            return

        # 2. Extract temporal context and determine date range
        temporal = extract_temporal_filter(query)
        years = get_smart_date_range(query, config.default_years)
        if temporal and temporal.get('years_override'):
            years = temporal['years_override']

        # 3. Fetch data for all series in parallel
        results = await source_manager.fetch_many(routing_result.series, years)

        series_data = []
        fetch_errors = []
        for result in results:
            if result.is_valid:
                dates = result.dates
                values = result.values

                # Apply temporal filtering if specified
                if temporal:
                    start_date = temporal.get('filter_start_date')
                    end_date = temporal.get('filter_end_date')
                    if start_date or end_date:
                        dates, values = filter_data_by_dates(dates, values, start_date, end_date)

                if dates and values:
                    series_data.append((result.id, dates, values, result.info))
            elif result.error:
                fetch_errors.append(f"{result.id}: {result.error}")

        if not series_data:
            if fetch_errors:
                error_detail = "; ".join(fetch_errors[:3])
                if "rate limit" in error_detail.lower():
                    error_msg = f"FRED API rate limit reached. Please wait a moment and try again. ({error_detail})"
                elif "not exist" in error_detail.lower() or "Bad request" in error_detail.lower():
                    error_msg = f"Series not found: {error_detail}"
                else:
                    error_msg = f"Unable to fetch data: {error_detail}"
            else:
                error_msg = "Unable to fetch data for the requested series. Please try again."
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            return

        # 4. Format chart data using auto-grouping (same logic as non-streaming)
        charts = []
        groups = auto_group_series(series_data, routing_result)

        for group in groups:
            if len(group.series_data) > 1:
                combined = format_combined_chart(
                    group.series_data,
                    show_yoy=group.show_yoy,
                    user_query=query,
                    chart_title=group.title,
                )
                if combined:
                    combined_bullets = []
                    for sid, d, v, inf in group.series_data:
                        b = get_bullets(sid, d, v, inf, user_query=query)
                        if b:
                            combined_bullets.append(b[0])
                    combined['bullets'] = combined_bullets[:3]
                    charts.append(combined)
                else:
                    for sid, d, v, inf in group.series_data:
                        chart = format_chart_data(sid, d, v, inf, show_yoy=group.show_yoy, user_query=query)
                        chart['bullets'] = get_bullets(sid, d, v, inf, user_query=query)
                        charts.append(chart)
            else:
                sid, d, v, inf = group.series_data[0]
                chart = format_chart_data(sid, d, v, inf, show_yoy=group.show_yoy, user_query=query)
                chart['bullets'] = get_bullets(sid, d, v, inf, user_query=query)
                charts.append(chart)

        # 4b. Gemini Flash review of chart bullets
        if GEMINI_AUDIT_AVAILABLE and config.enable_gemini_audit and audit_bullets:
            try:
                charts = audit_bullets(query, charts, series_data)
            except Exception as e:
                print(f"[Stream] Bullet audit error: {e}")

        # 5. Build metrics from chart data (deduplicate by series_id)
        metrics = []
        seen_metric_ids = set()
        for chart in charts[:8]:
            series_id = chart.get('series_id', '')
            if series_id in seen_metric_ids:
                continue
            seen_metric_ids.add(series_id)
            if len(metrics) >= 4:
                break
            series_info = registry.get_series(series_id)

            latest = chart.get('latest', 0)
            unit = chart.get('unit', '')

            # Format the value with unit awareness
            if chart.get('is_job_change'):
                formatted_value = f"{latest:+.0f}K/mo"
            elif chart.get('is_payems_level'):
                formatted_value = f"{latest / 1000:.1f}M"
            elif 'Percent' in unit or '%' in unit:
                formatted_value = f"{latest:.1f}%"
            elif 'Thousand' in unit:
                if latest >= 1000:
                    formatted_value = f"{latest / 1000:.1f}M"
                else:
                    formatted_value = f"{latest:.0f}K"
            elif latest > 1000000:
                formatted_value = f"{latest / 1000000:.1f}M"
            elif latest > 1000:
                formatted_value = f"{latest / 1000:.0f}K"
            else:
                formatted_value = f"{latest:.1f}"

            metric = {
                'label': chart.get('name', chart.get('series_id', 'Unknown')),
                'value': formatted_value if latest else 'N/A',
                'description': series_info.short_description if series_info and series_info.short_description else None,
            }
            if chart.get('yoy_change') is not None:
                yoy = chart['yoy_change']
                if chart.get('yoy_type') == 'pp':
                    metric['change'] = f"{yoy:+.1f} pp"
                elif chart.get('yoy_type') == 'jobs':
                    if chart.get('is_job_change'):
                        # 12-month average monthly change (already divided by 12 in formatter)
                        metric['change'] = f"{yoy:+.0f}K/mo avg"
                    else:
                        metric['change'] = f"{yoy/1000:+.0f}K"
                else:
                    metric['change'] = f"{yoy:+.1f}%"
                metric['changeType'] = 'positive' if yoy > 0 else 'negative' if yoy < 0 else 'neutral'
            metrics.append(metric)

        # === SEND CHARTS + METRICS (first visible content for user) ===
        yield f"data: {json.dumps({'type': 'charts', 'data': charts, 'metrics': metrics, 'temporal_context': temporal.get('explanation') if temporal else None})}\n\n"

        # 6. Build and send special HTML boxes
        special_data = {}
        if routing_result.fed_sep_html:
            special_data['fed_sep_html'] = routing_result.fed_sep_html

        # Build live recession scorecard from fetched data
        recession_html = routing_result.recession_html
        if RECESSION_SCORECARD_AVAILABLE and is_recession_query(query):
            live_scorecard = _build_live_recession_scorecard(series_data)
            if live_scorecard:
                recession_html = live_scorecard
        if recession_html:
            special_data['recession_html'] = recession_html

        if routing_result.cape_html:
            special_data['cape_html'] = routing_result.cape_html

        polymarket_html = query_router.get_polymarket_html(query)
        if polymarket_html:
            special_data['polymarket_html'] = polymarket_html

        if special_data:
            yield f"data: {json.dumps({'type': 'special', **special_data})}\n\n"

        # 7. Build and send source citations
        sources = []
        for sid, dates, values, info in series_data:
            sources.append({
                'series_id': sid,
                'name': info.get('title', info.get('name', sid)),
                'url': f"https://fred.stlouisfed.org/series/{sid}"
            })
        yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"

        # 8. Stream AI summary token-by-token
        # Build conversation history from request history for context
        conversation_history = [{"query": q} for q in history] if history else None
        async for chunk in stream_summary(query, series_data, conversation_history=conversation_history):
            yield f"data: {json.dumps({'type': 'summary_chunk', 'text': chunk})}\n\n"

        # 9. Send suggestions (use static generation to avoid a second LLM call)
        suggestions = generate_suggestions(query, routing_result.series)

        yield f"data: {json.dumps({'type': 'done', 'suggestions': suggestions})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


# =============================================================================
# HTML ENDPOINTS (legacy - for Jinja templates)
# =============================================================================

@search_router.post("/search", response_class=HTMLResponse)
async def search_html(
    request: Request,
    query: str = Form(...),
    history: str = Form(default="[]")
):
    """
    Legacy HTML endpoint - returns Jinja template partials.

    Kept for backward compatibility with HTMX-based frontend.
    """
    templates = request.app.state.templates

    # Parse conversation history (format: [{"query": "...", "summary": "..."}])
    try:
        conv_history = json.loads(history) if history else []
    except json.JSONDecodeError:
        conv_history = []

    # 1. Route the query
    routing_result = query_router.route(query)

    if not routing_result.series:
        return templates.TemplateResponse("partials/no_results.html", {
            "request": request,
            "query": query,
            "message": "No matching economic data found for your query. Try rephrasing or asking about specific topics like inflation, jobs, or GDP."
        })

    # 2. Extract temporal context
    temporal = extract_temporal_filter(query)
    years = get_smart_date_range(query, config.default_years)
    if temporal and temporal.get('years_override'):
        years = temporal['years_override']

    # 3. Fetch data for all series IN PARALLEL
    results = await source_manager.fetch_many(routing_result.series, years)

    series_data = []
    for result in results:
        if result.is_valid:
            dates = result.dates
            values = result.values

            # Apply temporal filtering if specified
            if temporal:
                start_date = temporal.get('filter_start_date')
                end_date = temporal.get('filter_end_date')
                if start_date or end_date:
                    dates, values = filter_data_by_dates(dates, values, start_date, end_date)

            if dates and values:
                series_data.append((result.id, dates, values, result.info))

    if not series_data:
        return templates.TemplateResponse("partials/no_results.html", {
            "request": request,
            "query": query,
            "message": "Unable to fetch data for the requested series. Please try again."
        })

    # 4. Format chart data using auto-grouping
    charts = []
    groups = auto_group_series(series_data, routing_result)

    for group in groups:
        if len(group.series_data) > 1:
            # Multi-series group → combined chart with multiple traces
            combined = format_combined_chart(
                group.series_data,
                show_yoy=group.show_yoy,
                user_query=query,
                chart_title=group.title,
            )
            if combined:
                # Generate AI bullets for each series in the combined chart
                combined_bullets = []
                for sid, d, v, inf in group.series_data:
                    b = get_bullets(sid, d, v, inf, user_query=query)
                    if b:
                        combined_bullets.append(b[0])  # 1 bullet per series
                combined['bullets'] = combined_bullets[:3]  # Max 3 for combined
                charts.append(combined)
            else:
                # Combination refused by chart crime prevention → separate charts
                for sid, d, v, inf in group.series_data:
                    chart = format_chart_data(sid, d, v, inf, show_yoy=group.show_yoy, user_query=query)
                    chart['bullets'] = get_bullets(sid, d, v, inf, user_query=query)
                    charts.append(chart)
        else:
            # Single series → individual chart
            sid, d, v, inf = group.series_data[0]
            chart = format_chart_data(sid, d, v, inf, show_yoy=group.show_yoy, user_query=query)
            chart['bullets'] = get_bullets(sid, d, v, inf, user_query=query)
            charts.append(chart)

    # 4b. Gemini Flash review of chart bullets
    if GEMINI_AUDIT_AVAILABLE and config.enable_gemini_audit and audit_bullets:
        try:
            charts = audit_bullets(query, charts, series_data)
        except Exception as e:
            print(f"[Search] Bullet audit error: {e}")

    # 5. Generate AI summary (with conversation history for context)
    summary_result = generate_summary(query, series_data, conversation_history=conv_history)
    summary = get_summary_text(summary_result) if isinstance(summary_result, dict) else str(summary_result)

    # Extract AI-generated suggestions and chart descriptions
    ai_suggestions = summary_result.get('suggestions', []) if isinstance(summary_result, dict) else []
    chart_descriptions = summary_result.get('chart_descriptions', {}) if isinstance(summary_result, dict) else {}

    # 5b. Judgment layer for interpretive queries (adds expert quotes, thresholds, web search)
    if JUDGMENT_AVAILABLE and is_judgment_query(query):
        try:
            judgment_result, was_judgment = process_judgment_query(
                query=query,
                series_data=series_data,
                original_explanation=summary
            )
            if judgment_result and was_judgment:
                summary = judgment_result
                print(f"[Search] Enhanced with judgment layer")
        except Exception as e:
            print(f"[Search] Judgment error: {e}")

    # Apply economist reviewer if enabled
    if config.enable_economist_reviewer:
        summary = review_summary(query, series_data, summary)

    # 6. Get Polymarket predictions if relevant
    polymarket_html = query_router.get_polymarket_html(query)

    # 7. Use AI suggestions if available, otherwise generate static ones
    suggestions = ai_suggestions if ai_suggestions else generate_suggestions(query, routing_result.series)

    # 8. Apply AI-generated chart descriptions to charts
    for chart in charts:
        series_id = chart.get('series_id', '')
        if series_id in chart_descriptions:
            chart['description'] = chart_descriptions[series_id]

    # 9. Update conversation history for next request (keep last 5 exchanges)
    new_history = conv_history + [{"query": query, "summary": summary}]
    new_history = new_history[-5:]

    # 10. Build live recession scorecard from fetched data if applicable
    recession_html = routing_result.recession_html
    if RECESSION_SCORECARD_AVAILABLE and is_recession_query(query):
        live_scorecard = _build_live_recession_scorecard(series_data)
        if live_scorecard:
            recession_html = live_scorecard

    # Build context for template
    context = {
        "request": request,
        "query": query,
        "summary": summary,
        "charts": charts,
        "suggestions": suggestions,
        "history": json.dumps(new_history),
        "temporal_context": temporal.get('explanation') if temporal else None,
        # Special HTML boxes
        "fed_sep_html": routing_result.fed_sep_html,
        "recession_html": recession_html,
        "cape_html": routing_result.cape_html,
        "polymarket_html": polymarket_html,
    }

    return templates.TemplateResponse("partials/results.html", context)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_suggestions(query: str, series: List[str]) -> List[str]:
    """Generate follow-up query suggestions based on topic."""
    q = query.lower()

    # Base suggestions by topic
    if any(w in q for w in ['inflation', 'cpi', 'pce', 'prices']):
        return [
            "Core inflation trend",
            "Fed's inflation target",
            "Rent inflation",
        ]
    elif any(w in q for w in ['job', 'employment', 'unemployment', 'labor']):
        return [
            "Job openings vs hires",
            "Wage growth",
            "Part-time employment",
        ]
    elif any(w in q for w in ['gdp', 'growth', 'economy']):
        return [
            "Consumer spending",
            "Business investment",
            "GDP components",
        ]
    elif any(w in q for w in ['rate', 'fed', 'treasury', 'yield']):
        return [
            "Yield curve",
            "Mortgage rates",
            "Fed projections",
        ]
    elif any(w in q for w in ['housing', 'home', 'mortgage']):
        return [
            "Home price trends",
            "Housing affordability",
            "New home sales",
        ]
    elif any(w in q for w in ['trade', 'import', 'export', 'tariff']):
        return [
            "Trade with China",
            "Trade deficit trend",
            "US trading partners",
        ]
    elif any(w in q for w in ['recession', 'downturn', 'slowdown']):
        return [
            "Yield curve signal",
            "Sahm rule indicator",
            "Leading indicators",
        ]

    # Default suggestions
    return [
        "How is inflation?",
        "Job market health",
        "GDP growth",
    ]
