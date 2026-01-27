"""
Chart Data Formatter - Prepare data for frontend display.

Handles formatting of chart data for Plotly.js rendering.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from registry import registry
from config import RECESSIONS
from .transforms import apply_transforms, get_yoy_type, calculate_yoy_change


def format_chart_data(
    series_id: str,
    dates: List[str],
    values: List[float],
    info: dict,
    show_yoy: Optional[bool] = None,
    user_query: str = ''
) -> Dict[str, Any]:
    """
    Format series data for chart display.

    Args:
        series_id: The series identifier
        dates: List of date strings
        values: List of values
        info: Series metadata from API
        show_yoy: Whether to show YoY transformation
        user_query: Original user query for context

    Returns:
        Dict with all data needed for Plotly chart rendering
    """
    # Get series info from registry
    series_info = registry.get_series(series_id)

    # Apply transforms if needed
    frequency = info.get('frequency', 'monthly').lower()
    transformed_dates, transformed_values, transformed_info = apply_transforms(
        series_id, dates, values, info, show_yoy, frequency
    )

    # Get display properties
    name = transformed_info.get('name', info.get('title', series_id))
    unit = transformed_info.get('unit', info.get('units', ''))
    source = info.get('source', 'FRED')

    # Check for special display flags
    is_job_change = series_id == 'PAYEMS' and not show_yoy
    is_payems_level = series_id == 'PAYEMS'

    # PAYEMS special handling: compute monthly job changes with 3-month averaging
    three_mo_avg = None
    if is_job_change and len(transformed_values) >= 4:
        # Compute month-over-month changes (in thousands of jobs)
        job_changes = []
        for i in range(1, len(transformed_values)):
            change = transformed_values[i] - transformed_values[i - 1]
            job_changes.append(change)

        # Apply 3-month moving average for stability
        smoothed_changes = []
        for i in range(len(job_changes)):
            if i < 2:
                # Not enough data for 3-month average, use raw
                smoothed_changes.append(job_changes[i])
            else:
                # 3-month average
                avg = (job_changes[i] + job_changes[i-1] + job_changes[i-2]) / 3
                smoothed_changes.append(avg)

        # Update chart data with job changes
        transformed_dates = transformed_dates[1:]  # Remove first date (no change for it)
        transformed_values = smoothed_changes

        # Update name and unit for job changes display
        name = 'Monthly Job Gains/Losses (3-Mo Avg)'
        unit = 'Thousands'

        # Store latest 3-month average
        three_mo_avg = smoothed_changes[-1] if smoothed_changes else None

    # Get latest value
    latest = transformed_values[-1] if transformed_values else None
    latest_date = transformed_dates[-1] if transformed_dates else None

    # Format latest date for display
    latest_date_formatted = ''
    if latest_date:
        try:
            dt = datetime.strptime(latest_date, '%Y-%m-%d')
            if 'quarterly' in frequency:
                quarter = (dt.month - 1) // 3 + 1
                latest_date_formatted = f"Q{quarter} {dt.year}"
            else:
                latest_date_formatted = dt.strftime('%b %Y')
        except:
            latest_date_formatted = latest_date

    # Calculate YoY change for display
    yoy_change = None
    yoy_type = None
    if series_info and len(values) >= 13:
        yoy_type = get_yoy_type(series_id)
        if yoy_type:
            if yoy_type == 'jobs':
                # Absolute change in thousands
                yoy_change = values[-1] - values[-13]
            elif yoy_type == 'pp':
                # Percentage point change
                yoy_change = values[-1] - values[-13]
            else:
                # Percent change
                if values[-13] != 0:
                    yoy_change = ((values[-1] - values[-13]) / abs(values[-13])) * 100

    # Get bullets from registry
    bullets = []
    if series_info:
        bullets = series_info.bullets[:2]  # Max 2 bullets

    # Seasonally adjusted flag
    sa = False
    if series_info:
        sa = series_info.sa
    elif info.get('seasonal_adjustment', '').upper() in ('SA', 'NSA'):
        sa = info.get('seasonal_adjustment', '').upper() == 'SA'

    # Get recessions for chart shading
    recessions_in_range = get_recessions_in_range(transformed_dates)

    return {
        'series_id': series_id,
        'name': name,
        'unit': unit,
        'source': source,
        'dates': transformed_dates,
        'values': transformed_values,
        'latest': latest,
        'latest_date': latest_date_formatted,
        'is_job_change': is_job_change,
        'is_payems_level': is_payems_level,
        'three_mo_avg': three_mo_avg,
        'yoy_change': yoy_change,
        'yoy_type': yoy_type,
        'bullets': bullets,
        'sa': sa,
        'recessions': recessions_in_range,
        'description': '',  # Can be filled by AI later
    }


def get_recessions_in_range(dates: List[str]) -> List[Dict[str, str]]:
    """
    Get NBER recessions that overlap with the data range.

    Args:
        dates: List of date strings

    Returns:
        List of {'start': ..., 'end': ...} dicts
    """
    if not dates:
        return []

    data_start = dates[0]
    data_end = dates[-1]

    recessions_in_range = []
    for start, end in RECESSIONS:
        # Check if recession overlaps with data range
        if end >= data_start and start <= data_end:
            recessions_in_range.append({
                'start': max(start, data_start),
                'end': min(end, data_end)
            })

    return recessions_in_range


def format_multiple_charts(
    series_data: List[tuple],
    show_yoy: bool = False,
    user_query: str = ''
) -> List[Dict[str, Any]]:
    """
    Format multiple series for chart display.

    Args:
        series_data: List of (series_id, dates, values, info) tuples
        show_yoy: Whether to show YoY transformation
        user_query: Original user query

    Returns:
        List of formatted chart data dicts
    """
    charts = []
    for series_id, dates, values, info in series_data:
        if dates and values:
            chart = format_chart_data(
                series_id, dates, values, info,
                show_yoy=show_yoy,
                user_query=user_query
            )
            charts.append(chart)
    return charts
