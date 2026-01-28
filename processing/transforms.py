"""
Data Transforms - YoY calculation, normalization, type safety.

Handles the "Iron Laws" of charting:
- Never apply YoY to rates (already meaningful)
- Always apply YoY to indexes (raw value meaningless)
- Respect data_type for each series
"""

from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Tuple, Optional
from registry import registry


def calculate_yoy(dates: List[str], values: List[float], periods: int = 12) -> Tuple[List[str], List[float]]:
    """
    Calculate year-over-year percent change using DATE-BASED matching.

    Instead of blindly using values[i - periods] (position-based, which breaks
    when data has gaps or irregular spacing), this matches each date to the
    observation closest to exactly 12 months prior.

    This ensures our YoY matches FRED's computation.

    Args:
        dates: List of date strings (YYYY-MM-DD)
        values: List of values
        periods: Number of periods for YoY (12 for monthly, 4 for quarterly)

    Returns:
        Tuple of (yoy_dates, yoy_values)
    """
    if len(values) <= periods:
        return [], []

    # Parse dates once for efficient lookup
    parsed_dates = [datetime.strptime(d, '%Y-%m-%d') if isinstance(d, str) else d for d in dates]

    # Build a date→value mapping for efficient lookup
    date_value_map = {}
    for d, v in zip(parsed_dates, values):
        date_value_map[d] = v

    # Sort dates for binary search
    sorted_dates = sorted(date_value_map.keys())
    sorted_values = [date_value_map[d] for d in sorted_dates]

    yoy_dates = []
    yoy_values = []

    # Determine lookback delta based on periods
    if periods <= 4:
        # Quarterly: look back exactly 1 year
        delta = relativedelta(years=1)
    elif periods <= 12:
        # Monthly: look back exactly 1 year
        delta = relativedelta(years=1)
    elif periods <= 52:
        # Weekly: look back exactly 1 year
        delta = relativedelta(years=1)
    else:
        # Daily (252 trading days): look back exactly 1 year
        delta = relativedelta(years=1)

    for i, (current_date, current_value) in enumerate(zip(sorted_dates, sorted_values)):
        target_date = current_date - delta

        # Find the observation closest to target_date
        prior_value = _find_closest_value(sorted_dates, sorted_values, target_date)

        if prior_value is not None and prior_value != 0:
            yoy_pct = ((current_value - prior_value) / abs(prior_value)) * 100
            date_str = current_date.strftime('%Y-%m-%d')
            yoy_dates.append(date_str)
            yoy_values.append(yoy_pct)

    return yoy_dates, yoy_values


def _find_closest_value(sorted_dates: List[datetime], sorted_values: List[float],
                        target: datetime, max_gap_days: int = 45) -> Optional[float]:
    """
    Find the value of the observation closest to target date.

    Uses binary search for efficiency. Returns None if no observation
    is within max_gap_days of the target.
    """
    import bisect
    idx = bisect.bisect_left(sorted_dates, target)

    best_value = None
    best_gap = None

    for candidate_idx in [idx - 1, idx]:
        if 0 <= candidate_idx < len(sorted_dates):
            gap = abs((sorted_dates[candidate_idx] - target).days)
            if best_gap is None or gap < best_gap:
                best_gap = gap
                best_value = sorted_values[candidate_idx]

    if best_gap is not None and best_gap <= max_gap_days:
        return best_value

    return None


def calculate_absolute_change(dates: List[str], values: List[float], periods: int = 12) -> Tuple[List[str], List[float]]:
    """
    Calculate absolute change over a period using DATE-BASED matching.

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

    # Parse dates for date-based matching
    parsed_dates = [datetime.strptime(d, '%Y-%m-%d') if isinstance(d, str) else d for d in dates]
    sorted_pairs = sorted(zip(parsed_dates, values), key=lambda x: x[0])
    sorted_dates = [p[0] for p in sorted_pairs]
    sorted_values = [p[1] for p in sorted_pairs]

    delta = relativedelta(years=1)

    change_dates = []
    change_values = []

    for current_date, current_value in zip(sorted_dates, sorted_values):
        target_date = current_date - delta
        prior_value = _find_closest_value(sorted_dates, sorted_values, target_date)

        if prior_value is not None:
            change = current_value - prior_value
            change_dates.append(current_date.strftime('%Y-%m-%d'))
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


def calculate_yoy_change(
    values: List[float],
    data_type: str,
    dates: Optional[List[str]] = None,
) -> Optional[float]:
    """
    Calculate the YoY change value for display.

    Uses date-based matching when dates are provided for accuracy.
    Falls back to position-based (values[-13]) when dates are not available.

    Args:
        values: List of values (at least 13 for monthly)
        data_type: The series data type
        dates: Optional list of date strings for date-based matching

    Returns:
        The YoY change value or None
    """
    if len(values) < 13:
        return None

    latest = values[-1]

    # Use date-based matching when dates are available
    if dates and len(dates) == len(values):
        parsed_dates = [datetime.strptime(d, '%Y-%m-%d') if isinstance(d, str) else d for d in dates]
        sorted_pairs = sorted(zip(parsed_dates, values), key=lambda x: x[0])
        s_dates = [p[0] for p in sorted_pairs]
        s_values = [p[1] for p in sorted_pairs]

        latest = s_values[-1]
        target = s_dates[-1] - relativedelta(years=1)
        year_ago = _find_closest_value(s_dates, s_values, target)

        if year_ago is None:
            return None
    else:
        # Fallback to position-based
        year_ago = values[-13]

    if data_type == 'rate':
        # Percentage point change
        return latest - year_ago
    else:
        # Percent change
        if year_ago != 0:
            return ((latest - year_ago) / abs(year_ago)) * 100

    return None
