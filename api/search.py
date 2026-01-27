"""
Search API Endpoint

The main endpoint for economic data queries.
"""

import json
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from routing import router as query_router
from sources import source_manager
from processing import format_chart_data, extract_temporal_filter, get_smart_date_range
from ai import generate_summary
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
    2. Fetch data for each series (with caching)
    3. Apply transforms (YoY, temporal filtering)
    4. Generate AI summary
    5. Return formatted HTML partial
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
        # No matching series found
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
            series_data.append((series_id, result.dates, result.values, result.info))

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
        charts.append(chart)

    # 5. Generate AI summary
    summary = generate_summary(query, series_data)

    # 6. Generate follow-up suggestions
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
    }

    return templates.TemplateResponse("partials/results.html", context)


def generate_suggestions(query: str, series: list) -> list:
    """Generate follow-up query suggestions."""
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

    # Default suggestions
    return [
        "How is inflation?",
        "Job market health",
        "GDP growth",
    ]
