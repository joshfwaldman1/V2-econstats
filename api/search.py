"""
Search API Endpoint

The main endpoint for economic data queries.
Integrates all features: routing, data fetching, AI summary, special boxes.
"""

import json
from typing import Optional, List

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from routing import router as query_router
from sources import source_manager
from processing import format_chart_data, extract_temporal_filter, get_smart_date_range
from processing.temporal import filter_data_by_dates
from ai import generate_summary, get_bullets, review_summary
from config import config

search_router = APIRouter()


@search_router.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    query: str = Form(...),
    history: str = Form(default="[]")
):
    """
    Main search endpoint - processes user queries and returns chart data.

    Flow:
    1. Route query to series (via registry/LLM)
    2. Handle special routes (Fed SEP, recession, CAPE)
    3. Fetch data for each series (with caching)
    4. Apply transforms (YoY, temporal filtering)
    5. Generate AI summary (with optional reviewer)
    6. Get Polymarket predictions if relevant
    7. Return formatted HTML partial
    """
    templates = request.app.state.templates

    # Parse conversation history
    try:
        conv_history = json.loads(history) if history else []
    except json.JSONDecodeError:
        conv_history = []

    # Add current query to history
    conv_history.append({"role": "user", "content": query})

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

    # 3. Fetch data for each series
    series_data = []
    for series_id in routing_result.series:
        result = source_manager.fetch_sync(series_id, years)
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
                series_data.append((series_id, dates, values, result.info))

    if not series_data:
        return templates.TemplateResponse("partials/no_results.html", {
            "request": request,
            "query": query,
            "message": "Unable to fetch data for the requested series. Please try again."
        })

    # 4. Format chart data
    charts = []
    for series_id, dates, values, info in series_data:
        chart = format_chart_data(
            series_id, dates, values, info,
            show_yoy=routing_result.show_yoy,
            user_query=query
        )

        # Get bullets (AI or static)
        chart['bullets'] = get_bullets(
            series_id, dates, values, info,
            user_query=query
        )

        charts.append(chart)

    # 5. Generate AI summary
    summary = generate_summary(query, series_data)

    # Apply economist reviewer if enabled
    if config.enable_economist_reviewer:
        summary = review_summary(query, series_data, summary)

    # 6. Get Polymarket predictions if relevant
    polymarket_html = query_router.get_polymarket_html(query)

    # 7. Generate follow-up suggestions
    suggestions = generate_suggestions(query, routing_result.series)

    # Build context for template
    context = {
        "request": request,
        "query": query,
        "summary": summary,
        "charts": charts,
        "suggestions": suggestions,
        "history": json.dumps(conv_history),
        "temporal_context": temporal.get('explanation') if temporal else None,
        # Special HTML boxes
        "fed_sep_html": routing_result.fed_sep_html,
        "recession_html": routing_result.recession_html,
        "cape_html": routing_result.cape_html,
        "polymarket_html": polymarket_html,
    }

    return templates.TemplateResponse("partials/results.html", context)


@search_router.post("/search/stream")
async def search_stream(
    request: Request,
    query: str = Form(...),
):
    """
    Streaming search endpoint using Server-Sent Events.

    Streams results as they become available:
    1. Routing result
    2. Chart data
    3. AI summary (token by token)
    """
    from fastapi.responses import StreamingResponse
    from ai import stream_summary

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
