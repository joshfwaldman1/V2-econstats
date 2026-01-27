"""
Data Transforms - YoY calculation, normalization, type safety.

Handles the "Iron Laws" of charting:
- Never apply YoY to rates (already meaningful)
- Always apply YoY to indexes (raw value meaningless)
- Respect data_type for each series
"""

from typing import List, Tuple, Optional
from registry import registry


def calculate_yoy(dates: List[str], values: List[float], periods: int = 12) -> Tuple[List[str], List[float]]:
    """
    Calculate year-over-year percent change.

    Args:
        dates: List of date strings
        values: List of values
        periods: Number of periods for YoY (12 for monthly, 4 for quarterly)

    Returns:
        Tuple of (yoy_dates, yoy_values)
    """
    if len(values) <= periods:
        return [], []

    yoy_dates = []
    yoy_values = []

    for i in range(periods, len(values)):
        if values[i - periods] != 0:  # Avoid division by zero
            yoy_pct = ((values[i] - values[i - periods]) / abs(values[i - periods])) * 100
            yoy_dates.append(dates[i])
            yoy_values.append(yoy_pct)

    return yoy_dates, yoy_values


def calculate_absolute_change(dates: List[str], values: List[float], periods: int = 12) -> Tuple[List[str], List[float]]:
    """
    Calculate absolute change over a period.

    Used for employment levels where YoY% is misleading.

    Args:
        dates: List of date strings
        values: List of values
        periods: Number of periods

    Returns:
        Tuple of (change_dates, change_values)
    """
    if len(values) <= periods:
        return [], []

    change_dates = []
    change_values = []

    for i in range(periods, len(values)):
        change = values[i] - values[i - periods]
        change_dates.append(dates[i])
        change_values.append(change)

    return change_dates, change_values


def should_apply_yoy(series_id: str, explicit_show_yoy: Optional[bool] = None) -> bool:
    """
    Determine if YoY transformation should be applied.

    Uses type-safe logic based on data_type:
    - rate: Never apply YoY (already meaningful)
    - index: Always apply YoY (raw value meaningless)
    - growth_rate: Never apply YoY (already a rate)
    - spread: Never apply YoY (already meaningful)
    - level: Use explicit_show_yoy or series default

    Args:
        series_id: The series identifier
        explicit_show_yoy: Explicit override from query plan

    Returns:
        True if YoY should be applied
    """
    # Get series info from registry
    series_info = registry.get_series(series_id)

    if series_info:
        data_type = series_info.data_type

        # Type-safe rules
        if data_type in ('rate', 'growth_rate', 'spread'):
            return False  # Never apply YoY
        if data_type == 'index':
            return True  # Always apply YoY

        # For 'level' type, use explicit or series default
        if explicit_show_yoy is not None:
            return explicit_show_yoy
        return series_info.show_yoy

    # Fallback if series not in registry
    if explicit_show_yoy is not None:
        return explicit_show_yoy
    return False


def apply_transforms(
    series_id: str,
    dates: List[str],
    values: List[float],
    info: dict,
    show_yoy: Optional[bool] = None,
    frequency: str = 'monthly'
) -> Tuple[List[str], List[float], dict]:
    """
    Apply appropriate transforms to series data.

    Args:
        series_id: The series identifier
        dates: Raw dates
        values: Raw values
        info: Series metadata
        show_yoy: Explicit YoY override
        frequency: Data frequency for period calculation

    Returns:
        Tuple of (transformed_dates, transformed_values, updated_info)
    """
    # Check if YoY should be applied
    if should_apply_yoy(series_id, show_yoy):
        # Determine periods based on frequency
        periods = 12 if frequency.lower() == 'monthly' else 4 if frequency.lower() == 'quarterly' else 1

        yoy_dates, yoy_values = calculate_yoy(dates, values, periods)

        if yoy_dates and yoy_values:
            # Update info for YoY display
            series_info = registry.get_series(series_id)
            if series_info and series_info.yoy_name:
                info = dict(info)  # Copy
                info['name'] = series_info.yoy_name
                info['unit'] = series_info.yoy_unit or '% Change YoY'

            return yoy_dates, yoy_values, info

    # No transform - return original
    return dates, values, info


def get_yoy_type(series_id: str) -> Optional[str]:
    """
    Get the appropriate YoY display type for a series.

    Returns:
        'pp' for percentage point change
        'percent' for percent change
        'jobs' for employment absolute change
        None if no YoY display
    """
    series_info = registry.get_series(series_id)
    if not series_info:
        return None

    data_type = series_info.data_type

    if data_type == 'rate':
        return 'pp'  # Percentage point change for rates
    elif data_type in ('level', 'index'):
        if series_id in ('PAYEMS', 'MANEMP') or 'employment' in series_info.name.lower():
            return 'jobs'  # Absolute job change
        return 'percent'  # Percent change

    return None


def calculate_yoy_change(values: List[float], data_type: str) -> Optional[float]:
    """
    Calculate the YoY change value for display.

    Args:
        values: List of values (at least 13 for monthly)
        data_type: The series data type

    Returns:
        The YoY change value or None
    """
    if len(values) < 13:
        return None

    latest = values[-1]
    year_ago = values[-13]

    if data_type == 'rate':
        # Percentage point change
        return latest - year_ago
    else:
        # Percent change
        if year_ago != 0:
            return ((latest - year_ago) / abs(year_ago)) * 100

    return None
