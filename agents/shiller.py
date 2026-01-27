"""
Shiller CAPE (Cyclically Adjusted P/E) Data Integration

Source: Robert Shiller's "Irrational Exuberance" dataset
URL: http://www.econ.yale.edu/~shiller/data.htm

The CAPE ratio divides the S&P 500 price by the 10-year average of inflation-adjusted
earnings. It's the gold standard for long-term market valuation.

Historical context:
- Long-term average (1881-present): ~17
- Dot-com peak (2000): 44.2
- 2008 financial crisis low: 13.3
- Current (2025): ~38-40
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Path to the Shiller data file
SHILLER_DATA_PATH = Path(__file__).parent.parent / "data" / "shiller_pe.xls"

# Historical CAPE benchmarks for context
CAPE_BENCHMARKS = {
    "long_term_average": 17.0,
    "median": 16.0,
    "dot_com_peak": 44.2,
    "dot_com_peak_date": "2000.01",
    "2008_crisis_low": 13.3,
    "2008_crisis_date": "2009.03",
    "black_monday_1987": 18.3,
    "1929_peak": 32.6,
}


def load_shiller_data() -> pd.DataFrame:
    """
    Load and parse the Shiller CAPE dataset.

    Returns:
        DataFrame with columns: date, sp_price, earnings, cape, real_price
    """
    if not SHILLER_DATA_PATH.exists():
        logger.error(f"Shiller data file not found at {SHILLER_DATA_PATH}")
        raise FileNotFoundError(f"Shiller data not found. Expected at: {SHILLER_DATA_PATH}")

    # Read Excel, skip header rows
    df = pd.read_excel(SHILLER_DATA_PATH, sheet_name='Data', header=None, skiprows=8)

    # Assign column names based on Shiller's format
    df.columns = ['date_raw', 'sp_price', 'dividend', 'earnings', 'cpi', 'date_fraction',
                  'gs10', 'real_price', 'real_dividend', 'real_tr_price', 'real_earnings',
                  'real_scaled_earnings', 'cape', 'col13', 'tr_cape', 'col15', 'excess_cape_yield',
                  'monthly_bond_return', 'real_bond_return', 'ann_stock_return',
                  'ann_bond_return', 'excess_ann_return']

    # Filter to valid rows (date is numeric)
    df = df[pd.to_numeric(df['date_raw'], errors='coerce').notna()].copy()

    # Convert date format (1871.01 = January 1871)
    def parse_shiller_date(date_val):
        try:
            year = int(date_val)
            month = int(round((date_val - year) * 100))
            if month == 0:
                month = 1
            return datetime(year, month, 1)
        except:
            return None

    df['date'] = df['date_raw'].apply(parse_shiller_date)
    df = df[df['date'].notna()]

    # Select and clean columns
    result = df[['date', 'sp_price', 'earnings', 'cape', 'real_price']].copy()
    result = result.sort_values('date').reset_index(drop=True)

    return result


def get_cape_series() -> Dict:
    """
    Get CAPE data in the standard series format used by the app.

    Returns:
        Dict with 'dates', 'values', 'info' keys matching FRED format
    """
    df = load_shiller_data()
    df = df[df['cape'].notna()]

    return {
        'dates': df['date'].dt.strftime('%Y-%m-%d').tolist(),
        'values': df['cape'].tolist(),
        'info': {
            'id': 'shiller_cape',
            'title': 'Shiller CAPE Ratio (Cyclically Adjusted P/E)',
            'units': 'Ratio',
            'frequency': 'Monthly',
            'source': 'Robert Shiller, Yale University',
            'notes': 'S&P 500 price divided by 10-year average of inflation-adjusted earnings'
        }
    }


def get_current_cape() -> Dict:
    """
    Get the most recent CAPE value with historical context.

    Returns:
        Dict with current value, percentile, and historical comparisons
    """
    df = load_shiller_data()
    df = df[df['cape'].notna()]

    current = df.iloc[-1]
    current_cape = current['cape']
    current_date = current['date']

    # Calculate percentile (what % of historical readings are below current)
    percentile = (df['cape'] < current_cape).mean() * 100

    # Find historical comparisons
    avg = df['cape'].mean()
    median = df['cape'].median()
    max_cape = df['cape'].max()
    max_date = df.loc[df['cape'].idxmax(), 'date']
    min_cape = df['cape'].min()
    min_date = df.loc[df['cape'].idxmin(), 'date']

    # Get values at key historical moments
    dot_com = df[df['date'].dt.year == 2000]['cape'].max()
    crisis_2008 = df[(df['date'].dt.year >= 2008) & (df['date'].dt.year <= 2009)]['cape'].min()

    return {
        'current_value': round(current_cape, 1),
        'current_date': current_date.strftime('%Y-%m'),
        'percentile': round(percentile, 1),
        'vs_average': {
            'long_term_avg': round(avg, 1),
            'median': round(median, 1),
            'premium_pct': round((current_cape / avg - 1) * 100, 1)
        },
        'historical_range': {
            'max': round(max_cape, 1),
            'max_date': max_date.strftime('%Y-%m'),
            'min': round(min_cape, 1),
            'min_date': min_date.strftime('%Y-%m')
        },
        'comparisons': {
            'dot_com_peak': round(dot_com, 1) if dot_com else None,
            'crisis_2008_low': round(crisis_2008, 1) if crisis_2008 else None,
            'vs_dot_com_pct': round((current_cape / dot_com - 1) * 100, 1) if dot_com else None
        },
        'interpretation': _interpret_cape(current_cape, percentile)
    }


def _interpret_cape(cape_value: float, percentile: float) -> str:
    """
    Provide a plain-English interpretation of the CAPE level.
    """
    if percentile >= 95:
        return f"Extremely elevated - in the top 5% of historical readings. Only exceeded during dot-com bubble."
    elif percentile >= 85:
        return f"Very high - in the top 15% historically. Suggests lower expected long-term returns."
    elif percentile >= 70:
        return f"Above average - higher than ~{int(percentile)}% of historical readings."
    elif percentile >= 30:
        return f"Near historical average - typical valuation range."
    elif percentile >= 15:
        return f"Below average - historically associated with above-average future returns."
    else:
        return f"Very low - in the bottom 15% historically. Rare buying opportunity if fundamentals intact."


def get_cape_for_period(start_year: int = None, end_year: int = None) -> Dict:
    """
    Get CAPE data for a specific time period.

    Args:
        start_year: Start year (default: 1881)
        end_year: End year (default: current)

    Returns:
        Dict with filtered series data
    """
    df = load_shiller_data()
    df = df[df['cape'].notna()]

    if start_year:
        df = df[df['date'].dt.year >= start_year]
    if end_year:
        df = df[df['date'].dt.year <= end_year]

    return {
        'dates': df['date'].dt.strftime('%Y-%m-%d').tolist(),
        'values': df['cape'].tolist(),
        'info': {
            'id': 'shiller_cape',
            'title': f'Shiller CAPE Ratio ({start_year or 1881}-{end_year or "present"})',
            'units': 'Ratio',
            'frequency': 'Monthly',
            'source': 'Robert Shiller, Yale University'
        }
    }


def get_bubble_comparison_data() -> Dict:
    """
    Get data specifically useful for "are we in a bubble?" analysis.

    Returns:
        Dict with current CAPE, dot-com comparison, and key statistics
    """
    df = load_shiller_data()
    df = df[df['cape'].notna()]

    current = get_current_cape()

    # Get dot-com era data (1998-2002)
    dot_com_era = df[(df['date'].dt.year >= 1998) & (df['date'].dt.year <= 2002)]

    # Get recent data (last 5 years)
    five_years_ago = df['date'].max() - pd.DateOffset(years=5)
    recent = df[df['date'] >= five_years_ago]

    # Calculate how long we've been above various thresholds
    above_30 = df[df['cape'] > 30]
    current_streak_above_30 = 0
    for _, row in df.iloc[::-1].iterrows():
        if row['cape'] > 30:
            current_streak_above_30 += 1
        else:
            break

    return {
        'current': current,
        'dot_com_comparison': {
            'peak_cape': round(dot_com_era['cape'].max(), 1),
            'peak_date': dot_com_era.loc[dot_com_era['cape'].idxmax(), 'date'].strftime('%Y-%m'),
            'current_vs_peak_pct': round((current['current_value'] / dot_com_era['cape'].max() - 1) * 100, 1),
            'months_above_30_in_dot_com': len(dot_com_era[dot_com_era['cape'] > 30])
        },
        'recent_trend': {
            'avg_last_5_years': round(recent['cape'].mean(), 1),
            'min_last_5_years': round(recent['cape'].min(), 1),
            'max_last_5_years': round(recent['cape'].max(), 1)
        },
        'streak_analysis': {
            'months_above_30': current_streak_above_30,
            'total_months_ever_above_30': len(above_30),
            'pct_of_history_above_30': round(len(above_30) / len(df) * 100, 1)
        },
        'summary': _generate_bubble_summary(current, dot_com_era['cape'].max())
    }


def _generate_bubble_summary(current: Dict, dot_com_peak: float) -> str:
    """
    Generate a summary statement for bubble analysis.
    """
    cape = current['current_value']
    percentile = current['percentile']

    if cape > dot_com_peak:
        return f"CAPE at {cape} exceeds the dot-com peak ({dot_com_peak:.1f}). Historically unprecedented outside of that era."
    elif cape > 35:
        return f"CAPE at {cape} is extremely elevated ({percentile:.0f}th percentile) but below dot-com peak. Valuations stretched but not at bubble extremes."
    elif cape > 30:
        return f"CAPE at {cape} is high ({percentile:.0f}th percentile). Above long-term average of 17, suggesting modest expected returns."
    elif cape > 25:
        return f"CAPE at {cape} is above average but not extreme. Market fairly valued to slightly expensive."
    else:
        return f"CAPE at {cape} is near or below historical average. Valuations reasonable."


# Convenience function for app.py integration
def is_valuation_query(query: str) -> bool:
    """
    Check if a query is about market valuation / CAPE / bubbles.
    """
    valuation_keywords = [
        'cape', 'shiller', 'p/e', 'pe ratio', 'price to earnings',
        'valuation', 'overvalued', 'undervalued', 'bubble',
        'expensive', 'cheap', 'fairly valued', 'stretched'
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in valuation_keywords)


if __name__ == "__main__":
    # Test the module
    print("Loading Shiller data...")
    df = load_shiller_data()
    print(f"Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}")
    print()

    print("Current CAPE:")
    current = get_current_cape()
    for k, v in current.items():
        print(f"  {k}: {v}")
    print()

    print("Bubble comparison:")
    bubble = get_bubble_comparison_data()
    print(f"  Summary: {bubble['summary']}")
