"""
Leading Indicators Dashboard for EconStats.

Provides a comprehensive economic dashboard that displays key leading and
coincident indicators for recession risk and economic outlook assessment.
This is the go-to tool for "is a recession coming?" and "economic outlook" questions.

Indicators tracked:
1. Sahm Rule (SAHMREALTIME) - Triggered when 3-month avg unemployment rises 0.5% above 12-month low
2. Yield Curve (T10Y2Y) - Inverted = warning (historically precedes recessions by 12-18 months)
3. Consumer Sentiment (UMCSENT) - Sharp drops precede recessions
4. Initial Jobless Claims (ICSA) - Rising trend = warning
5. Leading Economic Index (USSLIND) - Conference Board's 10-component leading index
6. ISM Manufacturing PMI (NAPM) - Above 50 = expansion, below 50 = contraction
7. Credit Spreads (BAMLH0A0HYM2) - High yield spread widens before recessions
8. Polymarket Recession Odds - Forward-looking market sentiment
"""

from typing import Optional
from datetime import datetime, timedelta


# Status thresholds for each indicator
INDICATOR_CONFIG = {
    'SAHMREALTIME': {
        'name': 'Sahm Rule',
        'description': '3-mo avg unemployment rise above 12-mo low',
        'thresholds': {
            'red': 0.50,      # >= 0.50 = recession likely started
            'yellow': 0.30,   # >= 0.30 = elevated risk
            # < 0.30 = green
        },
        'direction': 'higher_is_worse',
        'unit': 'pp',
        'red_label': 'TRIGGERED',
        'yellow_label': 'Elevated',
        'green_label': 'Normal',
    },
    'T10Y2Y': {
        'name': 'Yield Curve (10Y-2Y)',
        'description': 'Spread between 10-year and 2-year Treasury yields',
        'thresholds': {
            'red': 0.0,       # <= 0 = inverted (warning)
            'yellow': 0.25,   # <= 0.25 = nearly flat
            # > 0.25 = green (normal upward slope)
        },
        'direction': 'lower_is_worse',
        'unit': '%',
        'red_label': 'Inverted',
        'yellow_label': 'Flat',
        'green_label': 'Normal',
    },
    'UMCSENT': {
        'name': 'Consumer Sentiment',
        'description': 'University of Michigan Consumer Sentiment Index',
        'thresholds': {
            'red': 60.0,      # <= 60 = very pessimistic (recession territory)
            'yellow': 75.0,   # <= 75 = subdued
            # > 75 = green (healthy sentiment)
        },
        'direction': 'lower_is_worse',
        'unit': 'index',
        'red_label': 'Weak',
        'yellow_label': 'Subdued',
        'green_label': 'Healthy',
    },
    'ICSA': {
        'name': 'Initial Claims',
        'description': 'Weekly initial unemployment claims (4-week avg)',
        'thresholds': {
            'red': 300000,     # >= 300K = recession-level claims
            'yellow': 250000,  # >= 250K = elevated
            # < 250K = green (healthy labor market)
        },
        'direction': 'higher_is_worse',
        'unit': 'K',
        'red_label': 'Elevated',
        'yellow_label': 'Rising',
        'green_label': 'Low',
    },
    'USSLIND': {
        'name': 'Leading Economic Index',
        'description': 'Conference Board LEI (10 components, % change)',
        'thresholds': {
            'red': -0.4,       # <= -0.4% = contraction signal
            'yellow': 0.0,    # <= 0% = stagnation warning
            # > 0% = green (expansion)
        },
        'direction': 'lower_is_worse',
        'unit': '%',
        'red_label': 'Contracting',
        'yellow_label': 'Flat',
        'green_label': 'Expanding',
    },
    'NAPM': {
        'name': 'ISM Manufacturing PMI',
        'description': 'Purchasing Managers Index (50 = neutral)',
        'thresholds': {
            'red': 47.0,       # <= 47 = significant contraction
            'yellow': 50.0,    # <= 50 = contraction
            # > 50 = green (expansion)
        },
        'direction': 'lower_is_worse',
        'unit': 'index',
        'red_label': 'Contracting',
        'yellow_label': 'Stalling',
        'green_label': 'Expanding',
    },
    'BAMLH0A0HYM2': {
        'name': 'Credit Spreads',
        'description': 'High yield bond spread over Treasuries',
        'thresholds': {
            'red': 5.0,        # >= 5% = stress in credit markets
            'yellow': 4.0,     # >= 4% = elevated risk aversion
            # < 4% = green (normal credit conditions)
        },
        'direction': 'higher_is_worse',
        'unit': '%',
        'red_label': 'Stressed',
        'yellow_label': 'Elevated',
        'green_label': 'Normal',
    },
}


def get_indicator_status(
    series_id: str,
    current_value: float,
    previous_value: Optional[float] = None
) -> dict:
    """
    Determine the status (green/yellow/red) for a given indicator value.

    Args:
        series_id: FRED series ID (e.g., 'SAHMREALTIME')
        current_value: Current value of the indicator
        previous_value: Previous value for trend calculation (optional)

    Returns:
        dict with status info: {
            'name': str,
            'value': float,
            'status': 'green' | 'yellow' | 'red',
            'label': str,
            'description': str,
            'trend': 'rising' | 'falling' | 'stable' | None
        }
    """
    config = INDICATOR_CONFIG.get(series_id)
    if not config:
        return None

    thresholds = config['thresholds']
    direction = config['direction']

    # Determine status based on thresholds and direction
    if direction == 'higher_is_worse':
        if current_value >= thresholds['red']:
            status = 'red'
            label = config['red_label']
        elif current_value >= thresholds['yellow']:
            status = 'yellow'
            label = config['yellow_label']
        else:
            status = 'green'
            label = config['green_label']
    else:  # lower_is_worse
        if current_value <= thresholds['red']:
            status = 'red'
            label = config['red_label']
        elif current_value <= thresholds['yellow']:
            status = 'yellow'
            label = config['yellow_label']
        else:
            status = 'green'
            label = config['green_label']

    # Calculate trend if previous value provided
    trend = None
    if previous_value is not None:
        change_pct = ((current_value - previous_value) / abs(previous_value)) * 100 if previous_value != 0 else 0
        if abs(change_pct) < 1:
            trend = 'stable'
        elif change_pct > 0:
            trend = 'rising'
        else:
            trend = 'falling'

    # Format value for display
    if series_id == 'ICSA':
        formatted_value = f"{current_value/1000:.0f}K"
    elif series_id == 'UMCSENT':
        formatted_value = f"{current_value:.1f}"
    elif series_id == 'NAPM':
        formatted_value = f"{current_value:.1f}"
    elif series_id == 'USSLIND':
        formatted_value = f"{current_value:+.1f}%"
    elif series_id == 'BAMLH0A0HYM2':
        formatted_value = f"{current_value:.2f}%"
    else:
        formatted_value = f"{current_value:.2f}"

    return {
        'series_id': series_id,
        'name': config['name'],
        'value': current_value,
        'formatted_value': formatted_value,
        'unit': config['unit'],
        'status': status,
        'label': label,
        'description': config['description'],
        'trend': trend,
    }


def build_recession_scorecard(
    sahm_value: Optional[float] = None,
    yield_curve_value: Optional[float] = None,
    sentiment_value: Optional[float] = None,
    claims_value: Optional[float] = None,
    lei_value: Optional[float] = None,
    pmi_value: Optional[float] = None,
    credit_spread_value: Optional[float] = None,
    polymarket_odds: Optional[float] = None,
    sahm_prev: Optional[float] = None,
    yield_curve_prev: Optional[float] = None,
    sentiment_prev: Optional[float] = None,
    claims_prev: Optional[float] = None,
    lei_prev: Optional[float] = None,
    pmi_prev: Optional[float] = None,
    credit_spread_prev: Optional[float] = None,
) -> dict:
    """
    Build a comprehensive recession/economic outlook scorecard from indicator values.

    Args:
        sahm_value: Current Sahm Rule value (SAHMREALTIME)
        yield_curve_value: Current 10Y-2Y spread (T10Y2Y)
        sentiment_value: Current consumer sentiment (UMCSENT)
        claims_value: Current initial claims 4-week avg (ICSA)
        lei_value: Conference Board Leading Economic Index MoM % change (USSLIND)
        pmi_value: ISM Manufacturing PMI (NAPM)
        credit_spread_value: High yield credit spread (BAMLH0A0HYM2)
        polymarket_odds: Polymarket recession probability (0-100%)
        *_prev: Previous values for trend calculation

    Returns:
        dict with scorecard data: {
            'indicators': [...],
            'overall_risk': 'low' | 'moderate' | 'elevated' | 'high',
            'red_count': int,
            'yellow_count': int,
            'green_count': int,
            'polymarket_odds': float or None,
            'narrative': str,
        }
    """
    indicators = []
    red_count = 0
    yellow_count = 0
    green_count = 0

    # Process each indicator (order matters for display)
    indicator_data = [
        ('SAHMREALTIME', sahm_value, sahm_prev),
        ('T10Y2Y', yield_curve_value, yield_curve_prev),
        ('USSLIND', lei_value, lei_prev),
        ('NAPM', pmi_value, pmi_prev),
        ('UMCSENT', sentiment_value, sentiment_prev),
        ('ICSA', claims_value, claims_prev),
        ('BAMLH0A0HYM2', credit_spread_value, credit_spread_prev),
    ]

    for series_id, value, prev_value in indicator_data:
        if value is not None:
            status_info = get_indicator_status(series_id, value, prev_value)
            if status_info:
                indicators.append(status_info)
                if status_info['status'] == 'red':
                    red_count += 1
                elif status_info['status'] == 'yellow':
                    yellow_count += 1
                else:
                    green_count += 1

    # Determine overall risk level
    total_indicators = len(indicators)
    if total_indicators == 0:
        overall_risk = 'unknown'
    elif red_count >= 2 or (red_count >= 1 and yellow_count >= 2):
        overall_risk = 'high'
    elif red_count >= 1 or yellow_count >= 2:
        overall_risk = 'elevated'
    elif yellow_count >= 1:
        overall_risk = 'moderate'
    else:
        overall_risk = 'low'

    # Boost risk level if Polymarket odds are high
    if polymarket_odds is not None and polymarket_odds >= 40:
        if overall_risk == 'low':
            overall_risk = 'moderate'
        elif overall_risk == 'moderate':
            overall_risk = 'elevated'

    # Build narrative
    narrative = _build_narrative(indicators, overall_risk, polymarket_odds)

    return {
        'indicators': indicators,
        'overall_risk': overall_risk,
        'red_count': red_count,
        'yellow_count': yellow_count,
        'green_count': green_count,
        'polymarket_odds': polymarket_odds,
        'narrative': narrative,
    }


def _build_narrative(
    indicators: list,
    overall_risk: str,
    polymarket_odds: Optional[float]
) -> str:
    """
    Build a narrative description of the recession scorecard.

    Provides an economist-style interpretation of the indicators.
    """
    parts = []

    # Overall assessment
    if overall_risk == 'high':
        parts.append("Multiple recession warning signals are flashing.")
    elif overall_risk == 'elevated':
        parts.append("Some recession indicators are showing warning signs.")
    elif overall_risk == 'moderate':
        parts.append("Recession risk appears modest, though some indicators bear watching.")
    else:
        parts.append("Recession indicators are not signaling imminent concern.")

    # Highlight specific concerning indicators
    red_indicators = [ind for ind in indicators if ind['status'] == 'red']
    if red_indicators:
        red_names = [ind['name'] for ind in red_indicators]
        if len(red_names) == 1:
            parts.append(f"The {red_names[0]} is at a concerning level.")
        else:
            parts.append(f"Concerning signals from: {', '.join(red_names)}.")

    # Highlight specific indicators at caution level
    yellow_indicators = [ind for ind in indicators if ind['status'] == 'yellow']
    if yellow_indicators and not red_indicators:
        yellow_names = [ind['name'] for ind in yellow_indicators]
        if len(yellow_names) == 1:
            parts.append(f"The {yellow_names[0]} warrants monitoring.")
        else:
            parts.append(f"Indicators to watch: {', '.join(yellow_names)}.")

    # Add Polymarket context
    if polymarket_odds is not None:
        if polymarket_odds >= 40:
            parts.append(f"Prediction markets put recession odds at {polymarket_odds:.0f}%—a meaningful risk.")
        elif polymarket_odds >= 25:
            parts.append(f"Prediction markets price in {polymarket_odds:.0f}% recession odds—notable but not dominant.")
        else:
            parts.append(f"Prediction markets see recession as unlikely ({polymarket_odds:.0f}% odds).")

    return " ".join(parts)


def format_scorecard_for_display(scorecard: dict) -> str:
    """
    Format the scorecard as HTML for display in Streamlit.

    Creates a visual dashboard with colored status indicators.
    """
    indicators = scorecard.get('indicators', [])
    overall_risk = scorecard.get('overall_risk', 'unknown')
    polymarket_odds = scorecard.get('polymarket_odds')
    narrative = scorecard.get('narrative', '')

    # Status colors
    status_colors = {
        'red': '#ef4444',
        'yellow': '#f59e0b',
        'green': '#22c55e',
    }

    # Risk level colors and labels
    risk_config = {
        'high': {'color': '#ef4444', 'bg': '#fef2f2', 'label': 'HIGH RISK'},
        'elevated': {'color': '#f59e0b', 'bg': '#fefce8', 'label': 'ELEVATED'},
        'moderate': {'color': '#3b82f6', 'bg': '#eff6ff', 'label': 'MODERATE'},
        'low': {'color': '#22c55e', 'bg': '#f0fdf4', 'label': 'LOW RISK'},
        'unknown': {'color': '#6b7280', 'bg': '#f9fafb', 'label': 'UNKNOWN'},
    }

    risk = risk_config.get(overall_risk, risk_config['unknown'])

    # Build indicator rows HTML
    indicator_rows = ""
    for ind in indicators:
        status_color = status_colors.get(ind['status'], '#6b7280')
        trend_icon = ""
        if ind.get('trend') == 'rising':
            trend_icon = '<span style="color: #ef4444;">&#9650;</span>'  # Up arrow
        elif ind.get('trend') == 'falling':
            trend_icon = '<span style="color: #22c55e;">&#9660;</span>'  # Down arrow

        indicator_rows += f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1.5rem; border-bottom: 1px solid #f1f5f9;">
            <div>
                <div style="font-weight: 500; color: #0f172a; font-size: 0.875rem;">{ind['name']}</div>
                <div style="color: #64748b; font-size: 0.75rem;">{ind['description']}</div>
            </div>
            <div style="text-align: right; display: flex; align-items: center; gap: 0.5rem;">
                <div style="font-weight: 600; color: #0f172a; font-size: 0.875rem;">{ind['formatted_value']} {trend_icon}</div>
                <div style="background: {status_color}; color: white; padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; font-weight: 600;">
                    {ind['label']}
                </div>
            </div>
        </div>
        """

    # Add Polymarket row if available
    polymarket_row = ""
    if polymarket_odds is not None:
        pm_status = 'red' if polymarket_odds >= 40 else ('yellow' if polymarket_odds >= 25 else 'green')
        pm_color = status_colors[pm_status]
        pm_label = 'High' if polymarket_odds >= 40 else ('Moderate' if polymarket_odds >= 25 else 'Low')
        polymarket_row = f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1.5rem; background: #f8fafc;">
            <div>
                <div style="font-weight: 500; color: #0f172a; font-size: 0.875rem;">Polymarket Odds</div>
                <div style="color: #64748b; font-size: 0.75rem;">Prediction market recession probability</div>
            </div>
            <div style="text-align: right; display: flex; align-items: center; gap: 0.5rem;">
                <div style="font-weight: 600; color: #0f172a; font-size: 0.875rem;">{polymarket_odds:.0f}%</div>
                <div style="background: {pm_color}; color: white; padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; font-weight: 600;">
                    {pm_label}
                </div>
            </div>
        </div>
        """

    # FastAPI UI style - clean white card matching chart cards
    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 1rem; margin: 0 0 1.5rem 0; overflow: hidden; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);">
        <div style="padding: 1rem 1.5rem; border-bottom: 1px solid #f1f5f9;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3 style="font-weight: 600; color: #0f172a; font-size: 1rem; margin: 0;">Leading Indicators Dashboard</h3>
                    <p style="color: #64748b; font-size: 0.875rem; margin: 0.25rem 0 0 0;">Key recession warning signals</p>
                </div>
                <div style="background: {risk['color']}; color: white; padding: 0.25rem 0.75rem; border-radius: 0.375rem; font-weight: 600; font-size: 0.75rem;">
                    {risk['label']}
                </div>
            </div>
        </div>
        <div style="padding: 0.5rem 0;">
            {indicator_rows}
            {polymarket_row}
        </div>
        <div style="padding: 0.75rem 1.5rem; background: #f8fafc; border-top: 1px solid #f1f5f9;">
            <p style="color: #94a3b8; font-size: 0.75rem; margin: 0; line-height: 1.5;">{narrative}</p>
        </div>
        <div style="padding: 0.5rem 1.5rem; background: #f8fafc;">
            <p style="color: #94a3b8; font-size: 0.7rem; margin: 0;">Sources: FRED (Federal Reserve), Polymarket. Sahm Rule threshold: 0.5.</p>
        </div>
    </div>
    """

    return html


def is_recession_query(query: str) -> bool:
    """
    Detect if a query is asking about recession risk or economic outlook.

    Returns True if the query should trigger the leading indicators dashboard.
    """
    query_lower = query.lower()

    # Recession-related keywords
    recession_keywords = [
        'recession',
        'are we in a recession',
        'is a recession coming',
        'recession risk',
        'recession odds',
        'recession probability',
        'economic downturn',
        'downturn coming',
        'hard landing',
        'soft landing',
        'sahm rule',
        'yield curve inversion',
        'inverted yield curve',
        'recession indicator',
        'recession warning',
        'recession signal',
    ]

    # Economic outlook keywords (also show dashboard)
    outlook_keywords = [
        'economic outlook',
        'leading indicators',
        'economic forecast',
        'where is the economy headed',
        'economic health',
        'economy dashboard',
        'lei ',
        'leading index',
    ]

    all_keywords = recession_keywords + outlook_keywords
    for keyword in all_keywords:
        if keyword in query_lower:
            return True

    return False


def is_leading_indicators_query(query: str) -> bool:
    """Alias for is_recession_query - both show the same dashboard."""
    return is_recession_query(query)


# For testing
if __name__ == "__main__":
    # Test with sample data
    scorecard = build_recession_scorecard(
        sahm_value=0.23,
        yield_curve_value=0.15,
        sentiment_value=68.0,
        claims_value=215000,
        polymarket_odds=22.0,
    )

    print("Scorecard:")
    print(f"  Overall Risk: {scorecard['overall_risk']}")
    print(f"  Red: {scorecard['red_count']}, Yellow: {scorecard['yellow_count']}, Green: {scorecard['green_count']}")
    print(f"  Narrative: {scorecard['narrative']}")
    print()

    for ind in scorecard['indicators']:
        print(f"  {ind['name']}: {ind['formatted_value']} [{ind['status'].upper()}] - {ind['label']}")
