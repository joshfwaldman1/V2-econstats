"""
Analytics Layer - All math computed with pandas, not LLMs.

This module provides robust statistical calculations for economic data.
LLMs receive pre-computed results, never raw data to calculate.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dateutil.relativedelta import relativedelta


def compute_series_analytics(
    dates: List[str],
    values: List[float],
    series_id: str = '',
    frequency: str = 'monthly',
    data_type: str = ''
) -> Dict:
    """
    Compute comprehensive analytics for a data series using pandas.

    Returns a dict of pre-computed values that can be safely passed to LLMs.
    The LLM should NEVER do math - just interpret these computed results.

    Args:
        dates: List of date strings (YYYY-MM-DD)
        values: List of numeric values
        series_id: Optional series identifier
        frequency: 'monthly', 'quarterly', 'daily', 'weekly'
        data_type: 'rate', 'index', 'level', 'growth_rate', 'spread'

    Returns:
        Dict with all computed analytics
    """
    if not dates or not values or len(values) < 2:
        return {'error': 'Insufficient data'}

    # Create pandas series with datetime index
    df = pd.DataFrame({
        'date': pd.to_datetime(dates),
        'value': pd.to_numeric(values, errors='coerce')
    }).set_index('date').sort_index()

    # Drop NaN values
    df = df.dropna()

    if len(df) < 2:
        return {'error': 'Insufficient valid data'}

    latest = df['value'].iloc[-1]
    latest_date = df.index[-1]

    # Determine lookback periods based on frequency
    if frequency == 'quarterly':
        yoy_periods = 4
        short_term_periods = 2  # 2 quarters = 6 months
    elif frequency == 'daily':
        yoy_periods = 252  # Trading days
        short_term_periods = 63  # ~3 months
    elif frequency == 'weekly':
        yoy_periods = 52
        short_term_periods = 13  # ~3 months
    else:  # monthly (default)
        yoy_periods = 12
        short_term_periods = 3

    analytics = {
        'series_id': series_id,
        'latest_value': round(latest, 4),
        'latest_date': latest_date.strftime('%Y-%m-%d'),
        'latest_date_formatted': _format_date(latest_date, frequency),
        'data_points': len(df),
        'frequency': frequency,
        'data_type': data_type,
    }

    # Year-over-year change — DATE-BASED lookup, not position-based.
    # Position-based (iloc[-13]) breaks when data has gaps, missing months,
    # or irregular frequency. Date-based ensures we compare Dec 2025 to Dec 2024.
    yoy_target_date = latest_date - relativedelta(years=1)
    yoy_row = _find_nearest_observation(df, yoy_target_date)
    if yoy_row is not None:
        year_ago = yoy_row['value']
        year_ago_date = yoy_row.name
        yoy_change = latest - year_ago
        yoy_pct = (yoy_change / abs(year_ago) * 100) if year_ago != 0 else None
        analytics['yoy'] = {
            'change': round(yoy_change, 4),
            'change_pct': round(yoy_pct, 2) if yoy_pct else None,
            'prior_value': round(year_ago, 4),
            'prior_date': year_ago_date.strftime('%Y-%m-%d'),
        }

    # Short-term trend — also DATE-BASED.
    # For monthly: 3 months back. For quarterly: 6 months. For daily: ~3 months.
    if frequency == 'quarterly':
        short_term_delta = relativedelta(months=6)
    elif frequency == 'daily':
        short_term_delta = relativedelta(months=3)
    elif frequency == 'weekly':
        short_term_delta = relativedelta(months=3)
    else:  # monthly
        short_term_delta = relativedelta(months=3)

    short_target_date = latest_date - short_term_delta
    short_row = _find_nearest_observation(df, short_target_date)
    if short_row is not None:
        short_ago = short_row['value']
        short_change = latest - short_ago
        short_pct = (short_change / abs(short_ago) * 100) if short_ago != 0 else None

        # Classify trend
        if short_pct is not None:
            if short_pct > 2:
                trend_direction = 'rising'
            elif short_pct < -2:
                trend_direction = 'falling'
            else:
                trend_direction = 'flat'
        else:
            trend_direction = 'unknown'

        analytics['short_term'] = {
            'periods': short_term_periods,
            'change': round(short_change, 4),
            'change_pct': round(short_pct, 2) if short_pct else None,
            'direction': trend_direction,
        }

    # 52-week / 1-year high and low
    one_year_periods = min(yoy_periods, len(df) - 1)
    if one_year_periods > 0:
        recent = df['value'].iloc[-one_year_periods:]
        high_52 = recent.max()
        low_52 = recent.min()
        high_date = recent.idxmax()
        low_date = recent.idxmin()

        pct_from_high = ((latest - high_52) / abs(high_52) * 100) if high_52 != 0 else 0
        pct_from_low = ((latest - low_52) / abs(low_52) * 100) if low_52 != 0 else 0

        analytics['range_1y'] = {
            'high': round(high_52, 4),
            'high_date': high_date.strftime('%Y-%m-%d'),
            'low': round(low_52, 4),
            'low_date': low_date.strftime('%Y-%m-%d'),
            'pct_from_high': round(pct_from_high, 2),
            'pct_from_low': round(pct_from_low, 2),
            'at_high': abs(pct_from_high) < 0.5,
            'at_low': abs(pct_from_low) < 0.5,
        }

    # 5-year high and low (if enough data)
    five_year_periods = yoy_periods * 5
    if len(df) > five_year_periods:
        recent_5y = df['value'].iloc[-five_year_periods:]
        analytics['range_5y'] = {
            'high': round(recent_5y.max(), 4),
            'low': round(recent_5y.min(), 4),
            'mean': round(recent_5y.mean(), 4),
            'median': round(recent_5y.median(), 4),
            'std': round(recent_5y.std(), 4),
        }

    # All-time statistics
    analytics['all_time'] = {
        'high': round(df['value'].max(), 4),
        'high_date': df['value'].idxmax().strftime('%Y-%m-%d'),
        'low': round(df['value'].min(), 4),
        'low_date': df['value'].idxmin().strftime('%Y-%m-%d'),
        'mean': round(df['value'].mean(), 4),
        'median': round(df['value'].median(), 4),
    }

    # Recent momentum (is it accelerating or decelerating?)
    # Use date-based lookups for consistency
    mid_target = latest_date - short_term_delta
    far_target = latest_date - short_term_delta - short_term_delta
    mid_row = _find_nearest_observation(df, mid_target)
    far_row = _find_nearest_observation(df, far_target)
    if mid_row is not None and far_row is not None:
        recent_change = latest - mid_row['value']
        prior_change = mid_row['value'] - far_row['value']

        if prior_change != 0:
            momentum = 'accelerating' if recent_change > prior_change else 'decelerating'
        else:
            momentum = 'stable'

        analytics['momentum'] = {
            'recent_change': round(recent_change, 4),
            'prior_change': round(prior_change, 4),
            'direction': momentum,
        }

    return analytics


def _find_nearest_observation(df: pd.DataFrame, target_date) -> Optional[pd.Series]:
    """
    Find the observation closest to target_date in the DataFrame.

    Uses date-based lookup instead of position-based indexing.
    This ensures YoY compares Dec 2025 to Dec 2024, even if data has
    gaps, missing months, or irregular frequency.

    Args:
        df: DataFrame with DatetimeIndex and 'value' column
        target_date: The target date to find

    Returns:
        The row (as pd.Series) closest to target_date, or None if no data
        is within a reasonable range (45 days for monthly, 120 days for quarterly).
    """
    if len(df) == 0:
        return None

    # Convert target to pandas Timestamp for comparison
    target = pd.Timestamp(target_date)

    # Find closest date using searchsorted
    idx = df.index.searchsorted(target, side='left')

    # Check both the date before and after the target
    candidates = []
    if idx > 0:
        candidates.append(idx - 1)
    if idx < len(df):
        candidates.append(idx)

    if not candidates:
        return None

    # Pick the closest
    best_idx = min(candidates, key=lambda i: abs(df.index[i] - target))
    best_date = df.index[best_idx]

    # Sanity check: don't use an observation more than 45 days away
    # (handles missing months gracefully but rejects wild mismatches)
    max_gap = pd.Timedelta(days=45)
    if abs(best_date - target) > max_gap:
        return None

    return df.iloc[best_idx]


def _format_date(dt: datetime, frequency: str) -> str:
    """Format date based on data frequency."""
    if frequency == 'quarterly':
        quarter = (dt.month - 1) // 3 + 1
        return f"Q{quarter} {dt.year}"
    elif frequency == 'daily' or frequency == 'weekly':
        return dt.strftime('%b %d, %Y')
    else:
        return dt.strftime('%B %Y')


def analytics_to_text(analytics: Dict) -> str:
    """
    Convert computed analytics to plain text for LLM context.

    The LLM receives this text - no raw numbers to calculate.

    CRITICAL: Output must be unambiguous. LLMs will misread numbers if
    the text is unclear about units. For example, "YoY: +9.04 (+3.0%)"
    causes the LLM to cite "9.04% inflation" when the actual rate is 3.0%.

    Rules by data_type:
    - index: Suppress raw point changes (meaningless). Only show YoY %.
    - rate: Show point changes as "X.XX percentage points" (explicit units).
    - growth_rate: Show the value directly (it IS the rate).
    - level/other: Show both raw change and percentage.
    """
    if 'error' in analytics:
        return f"Data error: {analytics['error']}"

    data_type = analytics.get('data_type', '')
    lines = []

    # Latest value — context-dependent
    if data_type == 'index':
        # For indexes, the raw value is meaningless to users.
        # Lead with YoY % if available, mention index value only for reference.
        if 'yoy' in analytics and analytics['yoy'].get('change_pct') is not None:
            yoy_pct = analytics['yoy']['change_pct']
            lines.append(
                f"Latest YoY change: {yoy_pct:+.1f}% as of {analytics['latest_date_formatted']}"
                f" (index level: {analytics['latest_value']:.1f})"
            )
        else:
            lines.append(f"Latest: {analytics['latest_value']} as of {analytics['latest_date_formatted']}")
    elif data_type == 'rate':
        lines.append(f"Latest: {analytics['latest_value']:.1f}% as of {analytics['latest_date_formatted']}")
    elif data_type == 'growth_rate':
        lines.append(f"Latest: {analytics['latest_value']:.1f}% as of {analytics['latest_date_formatted']}")
    else:
        lines.append(f"Latest: {analytics['latest_value']} as of {analytics['latest_date_formatted']}")

    # YoY — format depends on data_type
    if 'yoy' in analytics:
        yoy = analytics['yoy']
        if data_type == 'index':
            # For indexes: ONLY show percentage change, NEVER raw point change.
            # Raw point change (e.g., +9.04 index points) is meaningless and
            # causes LLMs to hallucinate "9.04% inflation".
            if yoy.get('change_pct') is not None:
                lines.append(f"YoY: {yoy['change_pct']:+.1f}%")
            # Don't append anything if no percentage available
        elif data_type == 'rate':
            # For rates: show change in percentage POINTS (explicit unit).
            # "Up 0.5 percentage points" not "up 0.5" (which LLMs read as 0.5%).
            lines.append(f"YoY change: {yoy['change']:+.2f} percentage points")
        else:
            # For levels/other: show both
            if yoy.get('change_pct') is not None:
                lines.append(f"YoY: {yoy['change']:+.2f} ({yoy['change_pct']:+.1f}%)")
            else:
                lines.append(f"YoY: {yoy['change']:+.2f}")

    # Short-term trend
    if 'short_term' in analytics:
        st = analytics['short_term']
        if data_type == 'index':
            # For indexes: only show percentage, not raw point change
            if st.get('change_pct') is not None:
                lines.append(f"Recent trend: {st['direction']} ({st['change_pct']:+.1f}% over {st['periods']} periods)")
            else:
                lines.append(f"Recent trend: {st['direction']}")
        elif data_type == 'rate':
            lines.append(f"Recent trend: {st['direction']} ({st['change']:+.2f} percentage points over {st['periods']} periods)")
        else:
            if st.get('change_pct') is not None:
                lines.append(f"Recent trend: {st['direction']} ({st['change_pct']:+.1f}% over {st['periods']} periods)")
            else:
                lines.append(f"Recent trend: {st['direction']}")

    # Range
    if 'range_1y' in analytics:
        r = analytics['range_1y']
        if data_type == 'rate':
            lines.append(f"1Y range: {r['low']:.1f}% - {r['high']:.1f}%")
        elif data_type == 'index':
            # For indexes: suppress raw index range (e.g., "306-315") — meaningless to users
            # and confusing to LLMs which may misinterpret raw values as rates.
            # Only show position relative to high/low as percentages.
            lines.append(f"1Y position: {r['pct_from_high']:+.1f}% from high, {r['pct_from_low']:+.1f}% from low")
        else:
            lines.append(f"1Y range: {r['low']:.2f} - {r['high']:.2f} (currently {r['pct_from_high']:+.1f}% from high)")

    # 5Y stats
    if 'range_5y' in analytics:
        r5 = analytics['range_5y']
        if data_type == 'rate':
            lines.append(f"5Y avg: {r5['mean']:.1f}%, median: {r5['median']:.1f}%")
        else:
            lines.append(f"5Y avg: {r5['mean']:.2f}, median: {r5['median']:.2f}")

    # Momentum
    if 'momentum' in analytics:
        m = analytics['momentum']
        lines.append(f"Momentum: {m['direction']}")

    return " | ".join(lines)


def compute_comparison_analytics(
    series_list: List[Tuple[str, List[str], List[float], Dict]]
) -> Dict:
    """
    Compute analytics for comparing multiple series.

    Useful for queries like "compare US vs Japan inflation".
    """
    results = {}

    for series_id, dates, values, info in series_list:
        freq = info.get('frequency', 'monthly').lower()
        if 'quarter' in freq:
            freq = 'quarterly'
        elif 'daily' in freq or 'day' in freq:
            freq = 'daily'
        elif 'week' in freq:
            freq = 'weekly'
        else:
            freq = 'monthly'

        data_type = info.get('data_type', '')
        results[series_id] = compute_series_analytics(dates, values, series_id, freq, data_type)

    return results
