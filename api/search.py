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

# Judgment layer for interpretive queries (adds expert quotes, thresholds, web search)
try:
    from agents.judgment_layer import is_judgment_query, process_judgment_query
    JUDGMENT_AVAILABLE = True
except ImportError:
    JUDGMENT_AVAILABLE = False
    print("[Search] Judgment layer not available")

search_router = APIRouter()


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


class SearchResponse(BaseModel):
    """JSON search response."""
    query: str
    summary: str
    suggestions: List[str]
    chart_descriptions: dict
    charts: List[dict]
    metrics: List[MetricResponse]
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
            error="Unable to fetch data for the requested series. Please try again."
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

    # 7. Build metrics from chart data
    metrics = []
    for chart in charts[:4]:  # Max 4 metrics
        series_id = chart.get('series_id', '')
        series_info = registry.get_series(series_id)

        metric = MetricResponse(
            label=chart.get('name', chart.get('series_id', 'Unknown')),
            value=f"{chart.get('latest', 0):.1f}" if chart.get('latest') else 'N/A',
            description=series_info.short_description if series_info and series_info.short_description else None,
        )
        if chart.get('yoy_change') is not None:
            yoy = chart['yoy_change']
            if chart.get('yoy_type') == 'pp':
                metric.change = f"{yoy:+.1f} pp"
            elif chart.get('yoy_type') == 'jobs':
                metric.change = f"{yoy/1000:+.0f}K"
            else:
                metric.change = f"{yoy:+.1f}%"
            metric.changeType = 'positive' if yoy > 0 else 'negative' if yoy < 0 else 'neutral'
        metrics.append(metric)

    # Use AI suggestions if available, otherwise generate static ones
    suggestions = ai_suggestions if ai_suggestions else generate_suggestions(query, routing_result.series)

    return SearchResponse(
        query=query,
        summary=summary_text,
        suggestions=suggestions,
        chart_descriptions=chart_descriptions,
        charts=charts,
        metrics=metrics,
        temporal_context=temporal.get('explanation') if temporal else None,
        fed_sep_html=routing_result.fed_sep_html,
        recession_html=routing_result.recession_html,
        cape_html=routing_result.cape_html,
        polymarket_html=polymarket_html,
        error=None
    )


@search_router.post("/api/search/stream")
async def api_search_stream(body: SearchRequest):
    """
    Streaming search endpoint using Server-Sent Events.

    Streams results as they become available for React frontend.
    """
    from fastapi.responses import StreamingResponse
    from ai import stream_summary

    query = body.query

    async def event_generator():
        # 1. Route query
        routing_result = query_router.route(query)

        if not routing_result.series:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No matching data found'})}\n\n"
            return

        # Send routing info
        yield f"data: {json.dumps({'type': 'routing', 'series': routing_result.series})}\n\n"

        # 2. Fetch data
        years = get_smart_date_range(query, config.default_years)
        series_data = []

        for series_id in routing_result.series:
            result = source_manager.fetch_sync(series_id, years)
            if result.is_valid:
                series_data.append((series_id, result.dates, result.values, result.info))

        # Send chart data
        charts = []
        for series_id, dates, values, info in series_data:
            chart = format_chart_data(series_id, dates, values, info, show_yoy=routing_result.show_yoy)
            charts.append(chart)

        yield f"data: {json.dumps({'type': 'charts', 'data': charts})}\n\n"

        # 3. Stream AI summary
        yield f"data: {json.dumps({'type': 'summary_start'})}\n\n"

        async for chunk in stream_summary(query, series_data):
            yield f"data: {json.dumps({'type': 'summary_chunk', 'text': chunk})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

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
        "recession_html": routing_result.recession_html,
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
