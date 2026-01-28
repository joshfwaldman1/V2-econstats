"""
Analytics Layer - All math computed with pandas, not LLMs.

This module provides robust statistical calculations for economic data.
LLMs receive pre-computed results, never raw data to calculate.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime


def compute_series_analytics(
    dates: List[str],
    values: List[float],
    series_id: str = '',
    frequency: str = 'monthly'
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
    }

    # Year-over-year change
    if len(df) > yoy_periods:
        year_ago = df['value'].iloc[-(yoy_periods + 1)]
        yoy_change = latest - year_ago
        yoy_pct = (yoy_change / abs(year_ago) * 100) if year_ago != 0 else None
        analytics['yoy'] = {
            'change': round(yoy_change, 4),
            'change_pct': round(yoy_pct, 2) if yoy_pct else None,
            'prior_value': round(year_ago, 4),
            'prior_date': df.index[-(yoy_periods + 1)].strftime('%Y-%m-%d'),
        }

    # Short-term trend (3 months or equivalent)
    if len(df) > short_term_periods:
        short_ago = df['value'].iloc[-(short_term_periods + 1)]
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
    if len(df) > short_term_periods * 2:
        recent_change = df['value'].iloc[-1] - df['value'].iloc[-(short_term_periods + 1)]
        prior_change = df['value'].iloc[-(short_term_periods + 1)] - df['value'].iloc[-(short_term_periods * 2 + 1)]

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
    """
    if 'error' in analytics:
        return f"Data error: {analytics['error']}"

    lines = []

    # Latest value
    lines.append(f"Latest: {analytics['latest_value']} as of {analytics['latest_date_formatted']}")

    # YoY
    if 'yoy' in analytics:
        yoy = analytics['yoy']
        if yoy.get('change_pct') is not None:
            lines.append(f"YoY: {yoy['change']:+.2f} ({yoy['change_pct']:+.1f}%)")
        else:
            lines.append(f"YoY: {yoy['change']:+.2f}")

    # Short-term trend
    if 'short_term' in analytics:
        st = analytics['short_term']
        if st.get('change_pct') is not None:
            lines.append(f"Recent trend: {st['direction']} ({st['change_pct']:+.1f}% over {st['periods']} periods)")
        else:
            lines.append(f"Recent trend: {st['direction']}")

    # Range
    if 'range_1y' in analytics:
        r = analytics['range_1y']
        lines.append(f"1Y range: {r['low']:.2f} - {r['high']:.2f} (currently {r['pct_from_high']:+.1f}% from high)")

    # 5Y stats
    if 'range_5y' in analytics:
        r5 = analytics['range_5y']
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

        results[series_id] = compute_series_analytics(dates, values, series_id, freq)

    return results
