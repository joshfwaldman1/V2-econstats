"""
Data Narrator - Converts economic data into insightful prose.

This module is the solution to a critical problem: the system calculates YoY changes,
MoM changes, trends, and positions in 5-year ranges but NEVER USES THEM in the narrative.
The fallback just outputs generic rules.

Instead of generic rule matching, this module LOOKS AT THE ACTUAL DATA VALUES
and generates specific, meaningful narratives.

Example:
    Instead of: "The labor market remains tight"
    We generate: "Unemployment at 4.1% is 0.4pp higher than the 3.7% reading a year ago,
                 suggesting gradual cooling. However, this remains near historically
                 healthy levels (typical range: 4.0-6.0%)."

Key principles:
1. ALWAYS cite specific numbers from the data
2. ALWAYS compare to historical context (year ago, 5-year range, historical highs/lows)
3. ALWAYS explain what the level means economically
4. ALWAYS note the direction and magnitude of change
5. ALWAYS provide forward-looking implications

Usage:
    from core.data_narrator import build_narrative, narrate_level, DataInsight

    # Single series narration
    insight = narrate_level('UNRATE', 4.1, 'Unemployment Rate')
    print(insight.text)  # "Unemployment at 4.1% is healthy - near the natural rate..."

    # Full narrative from multiple series
    narrative = build_narrative(
        query="How is the labor market?",
        series_data={'UNRATE': {...}, 'PAYEMS': {...}},
        query_type='labor'
    )
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DataInsight:
    """
    A single insight derived from data.

    This represents one piece of meaningful prose about economic data,
    along with metadata about what data it's based on.

    Attributes:
        text: The prose description (the actual narrative)
        importance: 'high', 'medium', or 'low' - used for ranking insights
        data_points: List of strings describing what data this is based on
        series_id: The FRED series ID this insight is about
        category: Economic category (labor, inflation, growth, etc.)
    """
    text: str
    importance: str  # 'high', 'medium', 'low'
    data_points: List[str] = field(default_factory=list)
    series_id: Optional[str] = None
    category: Optional[str] = None


# =============================================================================
# LEVEL CONTEXT - Historical thresholds for key series
# =============================================================================

# Rich context for interpreting current levels
# Format: series_id -> dict of threshold ranges with (min, max, description)
LEVEL_CONTEXT: Dict[str, Dict[str, Tuple[float, float, str]]] = {
    # =========================================================================
    # UNEMPLOYMENT RATES
    # =========================================================================
    'UNRATE': {
        'very_low': (0, 3.5, "historically tight - this level typically causes wage pressures"),
        'low': (3.5, 4.0, "very healthy - below the natural rate of ~4%"),
        'healthy': (4.0, 4.5, "healthy - near the natural rate, labor market in balance"),
        'moderate': (4.5, 5.5, "softening - some slack developing in the labor market"),
        'elevated': (5.5, 7.0, "concerning - meaningful labor market weakness"),
        'high': (7.0, 10.0, "recessionary - significant economic distress"),
        'crisis': (10.0, 100, "crisis levels - severe economic contraction"),
    },
    'LNS14000006': {  # Black unemployment
        'very_low': (0, 5.5, "historically low for Black workers - near record territory"),
        'low': (5.5, 6.5, "strong - below typical levels, reflects tight labor market"),
        'typical': (6.5, 8.0, "typical range historically - structural gap persists"),
        'elevated': (8.0, 10.0, "elevated - above historical norms, weakness apparent"),
        'high': (10.0, 15.0, "high - significant job market weakness for this demographic"),
        'crisis': (15.0, 100, "crisis levels - severe economic stress"),
    },
    'LNS14000009': {  # Hispanic unemployment
        'very_low': (0, 4.0, "historically low for Hispanic workers"),
        'low': (4.0, 5.0, "strong - below typical levels"),
        'typical': (5.0, 6.5, "typical range historically"),
        'elevated': (6.5, 8.0, "elevated - above historical norms"),
        'high': (8.0, 12.0, "high - significant job market weakness"),
        'crisis': (12.0, 100, "crisis levels"),
    },

    # =========================================================================
    # INFLATION MEASURES
    # =========================================================================
    'CPIAUCSL_YOY': {  # CPI YoY (computed)
        'deflation': (-100, 0, "deflationary - prices falling, can signal weak demand"),
        'very_low': (0, 1.5, "below the Fed's 2% target - lowflation risk"),
        'target': (1.5, 2.5, "near the Fed's 2% target - price stability achieved"),
        'above_target': (2.5, 3.5, "above the Fed's comfort zone - sticky inflation"),
        'elevated': (3.5, 5.0, "elevated - eroding purchasing power, Fed concerned"),
        'high': (5.0, 7.0, "high - significant inflation problem requiring action"),
        'very_high': (7.0, 100, "very high - not seen since the 1980s, urgent"),
    },
    'CPILFESL_YOY': {  # Core CPI YoY (computed)
        'very_low': (0, 1.5, "well below the Fed's implicit target - unusual"),
        'target': (1.5, 2.5, "in the Fed's comfort zone"),
        'above_target': (2.5, 3.5, "above target - Fed watching closely, sticky services"),
        'elevated': (3.5, 4.5, "elevated - underlying inflation pressure, restrictive policy"),
        'high': (4.5, 100, "high - sticky core inflation, Fed's main concern"),
    },
    'PCEPILFE_YOY': {  # Core PCE YoY - Fed's preferred measure (computed)
        'below_target': (0, 1.5, "below the Fed's 2% target - may prompt easing"),
        'at_target': (1.5, 2.3, "at or near the Fed's 2% target - goldilocks zone"),
        'above_target': (2.3, 3.0, "above target - Fed patient but vigilant"),
        'elevated': (3.0, 4.0, "elevated - Fed maintaining restrictive policy"),
        'high': (4.0, 100, "high - Fed firmly in inflation-fighting mode"),
    },

    # =========================================================================
    # GDP GROWTH
    # =========================================================================
    'GDPC1_YOY': {  # Real GDP YoY (computed)
        'contraction': (-100, 0, "contracting - economy shrinking, recession risk"),
        'stagnant': (0, 1.0, "stagnant - barely growing, watch for weakness"),
        'below_trend': (1.0, 2.0, "below trend - modest expansion"),
        'trend': (2.0, 2.5, "at trend - sustainable ~2% pace"),
        'above_trend': (2.5, 3.5, "above trend - solid expansion"),
        'strong': (3.5, 100, "strong - could be inflationary if sustained"),
    },
    'A191RL1Q225SBEA': {  # GDP quarterly annualized
        'deep_contraction': (-100, -2.0, "deep contraction - recession territory"),
        'contraction': (-2.0, 0, "contracting - negative growth this quarter"),
        'stall_speed': (0, 1.0, "stall speed - barely growing, vulnerable"),
        'moderate': (1.0, 2.5, "moderate - sustainable pace"),
        'solid': (2.5, 4.0, "solid - healthy expansion"),
        'hot': (4.0, 100, "hot - strong but watch for overheating"),
    },

    # =========================================================================
    # YIELD CURVE
    # =========================================================================
    'T10Y2Y': {
        'deeply_inverted': (-100, -0.5, "deeply inverted - strong recession signal, historically reliable"),
        'inverted': (-0.5, 0, "inverted - classic recession warning, every recession since 1970"),
        'flat': (0, 0.5, "flat - caution, growth concerns mounting"),
        'normal': (0.5, 1.5, "normal - healthy yield curve, no recession signal"),
        'steep': (1.5, 100, "steep - often seen in early recovery or easing expectations"),
    },

    # =========================================================================
    # INITIAL CLAIMS
    # =========================================================================
    'ICSA': {  # In thousands
        'very_low': (0, 200, "very low - minimal layoffs, extremely tight labor market"),
        'low': (200, 250, "low - healthy labor market, contained layoffs"),
        'normal': (250, 300, "normal - typical range, stable job market"),
        'elevated': (300, 400, "elevated - layoffs increasing, early warning"),
        'high': (400, 600, "high - recession-level layoffs"),
        'crisis': (600, 10000, "crisis - severe labor market distress (COVID peak: 6.9M)"),
    },

    # =========================================================================
    # CONSUMER SENTIMENT
    # =========================================================================
    'UMCSENT': {
        'very_depressed': (0, 55, "very depressed - crisis-level pessimism (COVID/inflation shock territory)"),
        'depressed': (55, 65, "depressed - consumers very worried"),
        'pessimistic': (65, 75, "pessimistic - below average confidence"),
        'neutral': (75, 85, "neutral - near long-run average of ~85"),
        'optimistic': (85, 95, "optimistic - consumers feeling good"),
        'very_optimistic': (95, 150, "very optimistic - strong confidence, expansion mode"),
    },

    # =========================================================================
    # JOB OPENINGS (JOLTS)
    # =========================================================================
    'JTSJOL': {  # In thousands
        'weak': (0, 5000, "weak - few opportunities, employers not hiring (recession levels)"),
        'moderate': (5000, 7000, "moderate - near pre-pandemic levels (~7M)"),
        'healthy': (7000, 9000, "healthy - good labor demand, balanced market"),
        'strong': (9000, 11000, "strong - lots of opportunities, workers have leverage"),
        'extreme': (11000, 20000, "extreme - historic labor shortage (post-COVID peak: 12M)"),
    },

    # =========================================================================
    # QUITS RATE (JOLTS)
    # =========================================================================
    'JTSQUR': {  # Percent
        'very_low': (0, 1.5, "very low - workers afraid to quit, job insecurity"),
        'low': (1.5, 2.0, "low - workers cautious, less confident"),
        'normal': (2.0, 2.5, "normal - typical job mobility, healthy churn"),
        'elevated': (2.5, 3.0, "elevated - workers confident, seeking better opportunities"),
        'high': (3.0, 100, "high - Great Resignation territory, extreme worker leverage"),
    },
}


# =============================================================================
# PAYROLL CHANGE CONTEXT
# =============================================================================

# Thresholds for monthly payroll changes (in thousands)
PAYROLL_THRESHOLDS = {
    'job_loss': (-10000, 0, "economy shedding jobs - contraction signal"),
    'minimal': (0, 50, "minimal - below ~100K needed for population growth"),
    'break_even': (50, 100, "break-even - keeping pace with labor force growth"),
    'moderate': (100, 150, "moderate - healthy but not hot job creation"),
    'solid': (150, 200, "solid - strong labor demand"),
    'strong': (200, 300, "strong - robust hiring"),
    'very_strong': (300, 500, "very strong - hot labor market, wage pressure risk"),
    'exceptional': (500, 10000, "exceptional - recovery/stimulus-driven (rare)"),
}


# =============================================================================
# HISTORICAL CONTEXT
# =============================================================================

# Notable historical reference points for context
HISTORICAL_CONTEXT = {
    'UNRATE': {
        'covid_peak': (14.7, 'April 2020'),
        'great_recession': (10.0, 'October 2009'),
        'pre_pandemic_low': (3.5, 'September 2019'),
        'fifty_year_low': (3.4, 'January 2023'),
        'long_term_avg': (5.7, '1948-present'),
        'natural_rate': (4.2, 'CBO estimate'),
    },
    'LNS14000006': {  # Black unemployment
        'record_low': (4.8, 'April 2023'),
        'pre_pandemic': (5.8, 'August 2019'),
        'long_term_avg': (10.8, '1972-present'),
    },
    'LNS14000009': {  # Hispanic unemployment
        'record_low': (3.9, 'September 2019'),
        'pre_pandemic': (4.3, 'December 2019'),
    },
    'CPIAUCSL_YOY': {
        'covid_peak': (9.1, 'June 2022'),
        'volcker_era': (14.8, 'March 1980'),
        'fed_target': (2.0, 'ongoing'),
        'pre_pandemic': (2.3, '2019 average'),
    },
    'PCEPILFE_YOY': {
        'covid_peak': (5.6, 'February 2022'),
        'fed_target': (2.0, 'ongoing'),
    },
    'ICSA': {
        'covid_peak': (6900, 'March 2020'),
        'great_recession': (665, 'March 2009'),
        'pre_pandemic': (215, 'February 2020'),
    },
    'T10Y2Y': {
        'deepest_inversion': (-1.08, 'July 2023'),
        'pre_2008': (0.0, '2006-2007'),
    },
    'JTSJOL': {
        'post_covid_peak': (12000, 'March 2022'),
        'pre_pandemic': (7000, 'February 2020'),
    },
    'UMCSENT': {
        'covid_low': (50.0, 'June 2022'),
        'pre_pandemic': (101.0, 'February 2020'),
        'long_term_avg': (86.0, '1978-present'),
    },
    'GDPC1_YOY': {
        'trend_growth': (2.0, 'long-run average'),
        'covid_trough': (-8.4, 'Q2 2020'),
    },
    'A191RL1Q225SBEA': {
        'covid_trough': (-28.1, 'Q2 2020'),
        'covid_rebound': (35.2, 'Q3 2020'),
        'trend': (2.0, 'long-run potential'),
    },
}


# =============================================================================
# NARRATION FUNCTIONS
# =============================================================================

def narrate_level(
    series_id: str,
    value: float,
    name: str,
    unit: str = '%'
) -> DataInsight:
    """
    Narrate a level value with historical context and economic meaning.

    This function takes a current value and generates prose that explains:
    - What the level is
    - Where it falls in historical context (thresholds)
    - What this means economically

    Args:
        series_id: The FRED series ID (or a derived ID like 'CPIAUCSL_YOY')
        value: The current value
        name: Human-readable name for the series
        unit: Unit of measurement (defaults to '%')

    Returns:
        DataInsight with the narrative and metadata

    Example:
        >>> insight = narrate_level('UNRATE', 4.1, 'Unemployment Rate')
        >>> print(insight.text)
        "Unemployment at 4.1% is healthy - near the natural rate, labor market in balance."
    """
    # Get thresholds for this series
    thresholds = LEVEL_CONTEXT.get(series_id, {})

    if not thresholds:
        # No specific context - generate generic insight
        return DataInsight(
            text=f"{name} is at {value:.1f}{unit}.",
            importance='low',
            data_points=[f"{name}: {value:.1f}{unit}"],
            series_id=series_id,
        )

    # Find which threshold bracket the value falls into
    bracket_name = None
    bracket_desc = None
    for name_key, (low, high, desc) in thresholds.items():
        if low <= value < high:
            bracket_name = name_key
            bracket_desc = desc
            break

    if not bracket_name:
        # Value outside all defined brackets
        return DataInsight(
            text=f"{name} at {value:.1f}{unit} is outside typical ranges.",
            importance='medium',
            data_points=[f"{name}: {value:.1f}{unit}"],
            series_id=series_id,
        )

    # Build the narrative with proper value formatting
    if unit == '%':
        value_str = f"{value:.1f}%"
    elif unit == 'K' or unit == 'thousands':
        if value >= 1000:
            value_str = f"{value/1000:.1f} million"
        else:
            value_str = f"{value:.0f}K"
    elif unit == 'index':
        value_str = f"{value:.1f}"
    else:
        value_str = f"{value:.2f}{unit}"

    # Determine importance based on bracket
    importance = 'medium'
    if bracket_name in ['very_low', 'very_high', 'crisis', 'deeply_inverted', 'exceptional', 'extreme']:
        importance = 'high'
    elif bracket_name in ['target', 'healthy', 'normal', 'moderate', 'at_target']:
        importance = 'low'

    text = f"{name} at {value_str} is {bracket_desc}."

    return DataInsight(
        text=text,
        importance=importance,
        data_points=[f"{name}: {value_str}"],
        series_id=series_id,
        category=_categorize_series(series_id),
    )


def narrate_trend(
    series_id: str,
    values: List[float],
    name: str,
    periods: int = 6,
    unit: str = '%'
) -> DataInsight:
    """
    Narrate a trend (rising, falling, flat, accelerating, decelerating).

    This function analyzes recent values to determine the trend direction
    and magnitude, then generates prose describing the movement.

    Args:
        series_id: The FRED series ID
        values: List of values (most recent last)
        name: Human-readable name
        periods: Number of periods to analyze (default 6)
        unit: Unit of measurement

    Returns:
        DataInsight describing the trend

    Example:
        >>> values = [4.0, 4.1, 4.2, 4.3, 4.4, 4.5]
        >>> insight = narrate_trend('UNRATE', values, 'Unemployment')
        >>> print(insight.text)
        "Unemployment has risen by 0.5pp over the past 6 months, a steady increase..."
    """
    if len(values) < 2:
        return DataInsight(
            text=f"Insufficient data to determine trend for {name}.",
            importance='low',
            data_points=[],
            series_id=series_id,
        )

    # Use available data up to 'periods'
    recent = values[-min(periods, len(values)):]
    start_val = recent[0]
    end_val = recent[-1]
    change = end_val - start_val
    num_periods = len(recent)

    # Determine trend direction with context-appropriate thresholds
    flat_threshold = 0.1 if unit == '%' else 0.05 if unit == 'index' else 50 if unit in ['K', 'thousands'] else 0.05

    if abs(change) < flat_threshold:
        trend = "essentially flat"
        direction = "unchanged"
    elif change > 0:
        if abs(change) > abs(start_val) * 0.2 if start_val != 0 else abs(change) > 1:
            trend = "risen sharply"
            direction = "up significantly"
        elif abs(change) > abs(start_val) * 0.1 if start_val != 0 else abs(change) > 0.5:
            trend = "risen notably"
            direction = "up"
        else:
            trend = "edged higher"
            direction = "up slightly"
    else:
        if abs(change) > abs(start_val) * 0.2 if start_val != 0 else abs(change) > 1:
            trend = "fallen sharply"
            direction = "down significantly"
        elif abs(change) > abs(start_val) * 0.1 if start_val != 0 else abs(change) > 0.5:
            trend = "fallen notably"
            direction = "down"
        else:
            trend = "edged lower"
            direction = "down slightly"

    # Check for acceleration/deceleration
    acceleration_text = ""
    if len(recent) >= 4:
        mid_point = len(recent) // 2
        first_half = recent[:mid_point]
        second_half = recent[mid_point:]
        first_change = first_half[-1] - first_half[0] if len(first_half) > 1 else 0
        second_change = second_half[-1] - second_half[0] if len(second_half) > 1 else 0

        if first_change != 0:
            if change > 0 and second_change > first_change * 1.5:
                acceleration_text = " and the pace of increase is accelerating"
            elif change > 0 and second_change < first_change * 0.5:
                acceleration_text = " though the pace of increase is slowing"
            elif change < 0 and abs(second_change) > abs(first_change) * 1.5:
                acceleration_text = " and the pace of decline is accelerating"
            elif change < 0 and abs(second_change) < abs(first_change) * 0.5:
                acceleration_text = " though the pace of decline is slowing"

    # Format the change value
    if unit == '%':
        change_str = f"{abs(change):.1f}pp"
    elif unit in ['K', 'thousands']:
        if abs(change) >= 1000:
            change_str = f"{abs(change)/1000:.1f}M"
        else:
            change_str = f"{abs(change):.0f}K"
    else:
        change_str = f"{abs(change):.2f}"

    # Build text
    period_label = f"{num_periods} months" if num_periods > 1 else "month"
    text = f"{name} has {trend} by {change_str} over the past {period_label}{acceleration_text}."

    # Importance based on magnitude
    importance = 'medium'
    if 'sharply' in trend:
        importance = 'high'
    elif 'flat' in trend or 'slightly' in direction:
        importance = 'low'

    return DataInsight(
        text=text,
        importance=importance,
        data_points=[f"Start: {start_val:.1f}", f"End: {end_val:.1f}", f"Change: {change_str}"],
        series_id=series_id,
        category=_categorize_series(series_id),
    )


def narrate_yoy_change(
    series_id: str,
    current: float,
    year_ago: float,
    name: str,
    unit: str = '%',
    is_payroll: bool = False
) -> DataInsight:
    """
    Narrate a year-over-year change with context.

    This function compares the current value to the year-ago value and
    generates prose describing the change, including what it might mean.

    Args:
        series_id: The FRED series ID
        current: Current value
        year_ago: Value from one year ago
        name: Human-readable name
        unit: Unit of measurement
        is_payroll: If True, interpret as payroll changes in thousands

    Returns:
        DataInsight describing the YoY change

    Example:
        >>> insight = narrate_yoy_change('UNRATE', 4.1, 3.7, 'Unemployment')
        >>> print(insight.text)
        "Unemployment at 4.1% is 0.4pp higher than the 3.7% reading a year ago,
         indicating gradual labor market cooling."
    """
    change = current - year_ago
    pct_change = ((current - year_ago) / abs(year_ago)) * 100 if year_ago != 0 else 0

    # Format values based on unit
    if unit == '%':
        current_str = f"{current:.1f}%"
        year_ago_str = f"{year_ago:.1f}%"
        change_str = f"{abs(change):.1f}pp"
    elif unit in ['K', 'thousands']:
        if abs(current) >= 1000:
            current_str = f"{current/1000:.1f}M"
        else:
            current_str = f"{current:.0f}K"
        if abs(year_ago) >= 1000:
            year_ago_str = f"{year_ago/1000:.1f}M"
        else:
            year_ago_str = f"{year_ago:.0f}K"
        if abs(change) >= 1000:
            change_str = f"{abs(change)/1000:.1f}M"
        else:
            change_str = f"{abs(change):.0f}K"
    else:
        current_str = f"{current:.2f}"
        year_ago_str = f"{year_ago:.2f}"
        change_str = f"{abs(change):.2f}"

    # Determine direction language
    if change > 0:
        direction = "higher"
        movement = "up"
    elif change < 0:
        direction = "lower"
        movement = "down"
    else:
        direction = "unchanged"
        movement = "flat"

    # Generate context-specific interpretation
    interpretation = ""
    if is_payroll:
        # Payroll-specific interpretation
        if current > 200 and year_ago > 200:
            interpretation = "Both readings show robust hiring."
        elif current < 100 and year_ago > 200:
            interpretation = "Hiring has slowed notably from the strong pace a year ago."
        elif current > year_ago * 1.2:
            interpretation = "Hiring has accelerated compared to a year ago."
        elif current < year_ago * 0.8:
            interpretation = "Hiring has cooled compared to a year ago."
    else:
        # Series-specific interpretation
        if series_id == 'UNRATE':
            if change > 0.5:
                interpretation = "This meaningful rise suggests notable labor market cooling."
            elif change > 0.2:
                interpretation = "This rise suggests gradual labor market normalization."
            elif change > 0:
                interpretation = "This slight increase indicates minor softening."
            elif change < -0.5:
                interpretation = "This meaningful drop shows the labor market has tightened significantly."
            elif change < 0:
                interpretation = "The decline indicates continued labor market strength."
            else:
                interpretation = "The labor market remains stable year-over-year."
        elif series_id in ['LNS14000006', 'LNS14000009']:
            if change > 0:
                interpretation = "This demographic group is experiencing relative weakness."
            else:
                interpretation = "This demographic group has seen improving conditions."
        elif 'CPI' in series_id or 'PCE' in series_id:
            if change > 0.5:
                interpretation = "Inflation pressures have intensified over the past year."
            elif change > 0:
                interpretation = "Inflation has edged higher year-over-year."
            elif change < -1:
                interpretation = "Significant disinflation progress is evident."
            elif change < 0:
                interpretation = "Inflation is cooling, making progress toward the Fed's target."
            else:
                interpretation = "Inflation is relatively stable year-over-year."
        elif series_id == 'T10Y2Y':
            if current < 0 and year_ago < 0:
                if change > 0:
                    interpretation = "The curve remains inverted but is normalizing."
                else:
                    interpretation = "The inversion has deepened, strengthening the recession signal."
            elif current < 0 and year_ago >= 0:
                interpretation = "The curve has inverted over the past year - a warning sign."
            elif current >= 0 and year_ago < 0:
                interpretation = "The curve has un-inverted - historically this can precede recession."
        elif series_id in ['JTSJOL', 'JTSQUR']:
            if change > 0:
                interpretation = "Labor demand remains strong relative to a year ago."
            else:
                interpretation = "Labor demand is normalizing from elevated levels."
        elif series_id == 'ICSA':
            if change > 50:
                interpretation = "Layoffs have increased notably, a potential warning sign."
            elif change > 0:
                interpretation = "Claims have edged higher but remain contained."
            else:
                interpretation = "Claims remain low, indicating a healthy labor market."
        elif series_id == 'UMCSENT':
            if change > 10:
                interpretation = "Consumer confidence has improved substantially."
            elif change > 0:
                interpretation = "Sentiment is recovering."
            elif change < -10:
                interpretation = "Confidence has deteriorated notably."
            else:
                interpretation = "Sentiment has weakened year-over-year."

    # Build the text
    if change == 0:
        text = f"{name} at {current_str} is unchanged from a year ago."
    else:
        text = f"{name} at {current_str} is {change_str} {direction} than the {year_ago_str} reading a year ago"
        if pct_change != 0 and unit != '%':
            text += f" ({movement} {abs(pct_change):.1f}%)"
        text += "."
        if interpretation:
            text += f" {interpretation}"

    # Importance based on magnitude
    importance = 'medium'
    if abs(pct_change) > 20 or (unit == '%' and abs(change) > 1):
        importance = 'high'
    elif abs(pct_change) < 5 and abs(change) < 0.3:
        importance = 'low'

    return DataInsight(
        text=text,
        importance=importance,
        data_points=[
            f"Current: {current_str}",
            f"Year ago: {year_ago_str}",
            f"Change: {'+' if change > 0 else ''}{change_str}",
        ],
        series_id=series_id,
        category=_categorize_series(series_id),
    )


def narrate_comparison(
    series1_id: str,
    series1_name: str,
    series1_value: float,
    series2_id: str,
    series2_name: str,
    series2_value: float,
    unit: str = '%'
) -> DataInsight:
    """
    Narrate the relationship between two series.

    This is especially useful for demographic comparisons (Black unemployment
    vs overall) or related metrics (core vs headline inflation).

    Args:
        series1_id: First series ID
        series1_name: First series name
        series1_value: First series value
        series2_id: Second series ID
        series2_name: Second series name
        series2_value: Second series value
        unit: Unit of measurement

    Returns:
        DataInsight describing the relationship

    Example:
        >>> insight = narrate_comparison(
        ...     'LNS14000006', 'Black unemployment', 7.5,
        ...     'UNRATE', 'Overall unemployment', 4.4
        ... )
        >>> print(insight.text)
        "Black unemployment at 7.5% is 3.1pp higher than the overall rate of 4.4%,
         a ratio of 1.7x that reflects persistent structural disparities."
    """
    gap = series1_value - series2_value
    ratio = series1_value / series2_value if series2_value != 0 else 0

    # Format values
    if unit == '%':
        val1_str = f"{series1_value:.1f}%"
        val2_str = f"{series2_value:.1f}%"
        gap_str = f"{abs(gap):.1f}pp"
    else:
        val1_str = f"{series1_value:.1f}"
        val2_str = f"{series2_value:.1f}"
        gap_str = f"{abs(gap):.1f}"

    # Determine relationship
    if gap > 0:
        direction = "higher than"
    elif gap < 0:
        direction = "lower than"
    else:
        direction = "equal to"

    # Build text based on the type of comparison
    text = f"{series1_name} at {val1_str} is {gap_str} {direction} {series2_name.lower()} at {val2_str}"

    # Add ratio context for unemployment comparisons
    if 'unemploy' in series1_name.lower() and 'unemploy' in series2_name.lower():
        if ratio > 1.1:
            text += f", a ratio of {ratio:.1f}x"
            if ratio > 1.7:
                text += " - wider than the typical 1.5-1.7x historical gap, indicating disproportionate impact"
            elif ratio > 1.5:
                text += " that reflects persistent structural disparities in the labor market"
            else:
                text += ", which is narrower than historical averages"
            text += "."
        elif ratio < 0.9:
            text += f", a ratio of {ratio:.2f}x - unusually narrow by historical standards."
        else:
            text += ", roughly in line with each other."
    elif 'inflation' in series1_name.lower() or 'cpi' in series1_name.lower().replace(' ', ''):
        if gap > 0.5:
            text += f". The {gap_str} gap suggests {'food and energy' if 'core' in series2_name.lower() else 'underlying'} factors are driving prices."
        elif gap < -0.5:
            text += f". Core running below headline suggests food and energy are adding to inflation pressures."
        else:
            text += f". The small gap indicates broad-based price pressures."
    else:
        text += "."

    importance = 'high' if abs(gap) > 1 or (ratio > 1.5 or ratio < 0.67) else 'medium'

    return DataInsight(
        text=text,
        importance=importance,
        data_points=[
            f"{series1_name}: {val1_str}",
            f"{series2_name}: {val2_str}",
            f"Gap: {'+' if gap > 0 else ''}{gap_str}",
            f"Ratio: {ratio:.2f}x" if ratio != 0 else "",
        ],
        series_id=series1_id,
        category=_categorize_series(series1_id),
    )


def narrate_position_in_range(
    series_id: str,
    value: float,
    min_5yr: float,
    max_5yr: float,
    name: str,
    unit: str = '%'
) -> DataInsight:
    """
    Narrate where the current value sits within its 5-year historical range.

    This provides important context about whether a reading is high or low
    relative to recent history.

    Args:
        series_id: The FRED series ID
        value: Current value
        min_5yr: Minimum value over past 5 years
        max_5yr: Maximum value over past 5 years
        name: Human-readable name
        unit: Unit of measurement

    Returns:
        DataInsight describing position in range

    Example:
        >>> insight = narrate_position_in_range('CPIAUCSL_YOY', 3.2, 0.1, 9.1, 'CPI Inflation')
        >>> print(insight.text)
        "Current inflation of 3.2% is in the 34th percentile of the past 5 years
         (range: 0.1% to 9.1%), below the midpoint but well off pandemic lows."
    """
    if max_5yr == min_5yr:
        return DataInsight(
            text=f"{name} at {value:.1f}{unit} has been stable over the past 5 years.",
            importance='low',
            data_points=[f"{name}: {value:.1f}{unit}"],
            series_id=series_id,
        )

    # Calculate percentile position
    percentile = ((value - min_5yr) / (max_5yr - min_5yr)) * 100

    # Format values
    if unit == '%':
        value_str = f"{value:.1f}%"
        min_str = f"{min_5yr:.1f}%"
        max_str = f"{max_5yr:.1f}%"
    elif unit in ['K', 'thousands']:
        value_str = f"{value/1000:.1f}M" if value >= 1000 else f"{value:.0f}K"
        min_str = f"{min_5yr/1000:.1f}M" if min_5yr >= 1000 else f"{min_5yr:.0f}K"
        max_str = f"{max_5yr/1000:.1f}M" if max_5yr >= 1000 else f"{max_5yr:.0f}K"
    else:
        value_str = f"{value:.1f}"
        min_str = f"{min_5yr:.1f}"
        max_str = f"{max_5yr:.1f}"

    # Generate position description
    if percentile > 90:
        position_desc = f"near the top of its 5-year range (in the {percentile:.0f}th percentile)"
        context = "at or near recent highs"
    elif percentile > 75:
        position_desc = f"in the upper quartile of its 5-year range ({percentile:.0f}th percentile)"
        context = "elevated by recent standards"
    elif percentile > 50:
        position_desc = f"above the midpoint of its 5-year range ({percentile:.0f}th percentile)"
        context = "moderately elevated"
    elif percentile > 25:
        position_desc = f"below the midpoint of its 5-year range ({percentile:.0f}th percentile)"
        context = "moderate by recent standards"
    elif percentile > 10:
        position_desc = f"in the lower quartile of its 5-year range ({percentile:.0f}th percentile)"
        context = "low by recent standards"
    else:
        position_desc = f"near the bottom of its 5-year range ({percentile:.0f}th percentile)"
        context = "at or near recent lows"

    text = f"{name} at {value_str} is {position_desc}. The 5-year range spans {min_str} to {max_str}, making the current reading {context}."

    importance = 'high' if percentile > 90 or percentile < 10 else 'medium'

    return DataInsight(
        text=text,
        importance=importance,
        data_points=[
            f"Current: {value_str}",
            f"5yr min: {min_str}",
            f"5yr max: {max_str}",
            f"Percentile: {percentile:.0f}%",
        ],
        series_id=series_id,
        category=_categorize_series(series_id),
    )


def narrate_payroll_change(
    value: float,
    avg_3mo: Optional[float] = None,
    avg_12mo: Optional[float] = None
) -> DataInsight:
    """
    Narrate a monthly payroll change with context.

    Payrolls require special handling because:
    - The value represents monthly job gains/losses in thousands
    - Context requires comparison to ~100K needed for population growth
    - 3-month and 12-month averages smooth out monthly noise

    Args:
        value: Monthly payroll change in thousands
        avg_3mo: 3-month average change (optional)
        avg_12mo: 12-month average change (optional)

    Returns:
        DataInsight describing the payroll change

    Example:
        >>> insight = narrate_payroll_change(256, 180, 200)
        >>> print(insight.text)
        "The economy added 256K jobs, a strong reading well above the ~100K needed
         for population growth. The 3-month average of 180K suggests solid
         underlying momentum."
    """
    # Find threshold bracket
    bracket_name = None
    bracket_desc = None
    for name_key, (low, high, desc) in PAYROLL_THRESHOLDS.items():
        if low <= value < high:
            bracket_name = name_key
            bracket_desc = desc
            break

    # Format the value
    if value < 0:
        value_str = f"lost {abs(value):.0f}K jobs"
    else:
        value_str = f"added {value:.0f}K jobs"

    # Build the text
    text = f"The economy {value_str}"
    if bracket_desc:
        bracket_label = bracket_desc.split(' - ')[0]
        text += f", a {bracket_label} reading"

    # Add context about population growth threshold
    if value > 150:
        text += " well above the ~100K needed for population growth"
    elif value > 100:
        text += ", modestly above the ~100K breakeven for population growth"
    elif value >= 50:
        text += ", near the ~100K needed to keep pace with population growth"
    elif value >= 0:
        text += ", below the ~100K needed to keep pace with population growth"
    text += "."

    # Add averaging context if available
    if avg_3mo is not None:
        avg_text = f" The 3-month average of {avg_3mo:.0f}K suggests "
        if avg_3mo > 200:
            avg_text += "strong underlying momentum."
        elif avg_3mo > 150:
            avg_text += "solid underlying job creation."
        elif avg_3mo > 100:
            avg_text += "moderate underlying hiring."
        elif avg_3mo > 50:
            avg_text += "modest underlying job growth."
        else:
            avg_text += "weak underlying job growth."
        text += avg_text

    if avg_12mo is not None and avg_3mo is not None:
        if avg_3mo < avg_12mo * 0.7:
            text += f" This is notably below the 12-month average of {avg_12mo:.0f}K, indicating slowing momentum."
        elif avg_3mo > avg_12mo * 1.3:
            text += f" This exceeds the 12-month average of {avg_12mo:.0f}K, showing accelerating hiring."

    importance = 'high' if value < 0 or value > 300 else ('medium' if value < 100 or value > 200 else 'low')

    return DataInsight(
        text=text,
        importance=importance,
        data_points=[
            f"Monthly change: {value:.0f}K",
            f"3mo avg: {avg_3mo:.0f}K" if avg_3mo else "",
            f"12mo avg: {avg_12mo:.0f}K" if avg_12mo else "",
        ],
        series_id='PAYEMS',
        category='labor',
    )


# =============================================================================
# MAIN NARRATIVE BUILDER
# =============================================================================

def build_narrative(
    query: str,
    series_data: Dict[str, Dict[str, Any]],
    query_type: str,
) -> str:
    """
    Build a complete narrative from multiple data insights.

    This is the main entry point. It:
    1. Extracts insights from each series
    2. Ranks insights by importance
    3. Combines into coherent prose
    4. Adds forward-looking implications

    Args:
        query: The user's original question
        series_data: Dictionary mapping series_id to data dict containing:
            - 'values': List of values
            - 'dates': List of dates
            - 'name': Human-readable name
            - 'unit': Unit of measurement
            - 'latest_value': Most recent value (optional, will compute if not provided)
            - 'yoy_value': Year-ago value (optional)
            - 'min_5yr': 5-year minimum (optional)
            - 'max_5yr': 5-year maximum (optional)
        query_type: Type of query ('labor', 'inflation', 'growth', 'recession', 'fed', 'general')

    Returns:
        Coherent narrative string combining all insights

    Example:
        >>> narrative = build_narrative(
        ...     query="How is the labor market?",
        ...     series_data={
        ...         'UNRATE': {'values': [...], 'name': 'Unemployment Rate', ...},
        ...         'PAYEMS': {'values': [...], 'name': 'Payrolls', ...},
        ...     },
        ...     query_type='labor'
        ... )
    """
    insights: List[DataInsight] = []

    # Process each series
    for series_id, data in series_data.items():
        if not data or not data.get('values'):
            continue

        values = data['values']
        name = data.get('name', series_id)
        unit = data.get('unit', '%')
        latest = data.get('latest_value', values[-1] if values else None)

        if latest is None:
            continue

        # Generate level insight
        level_insight = narrate_level(series_id, latest, name, unit)
        if level_insight.text:
            insights.append(level_insight)

        # Generate trend insight if we have enough data
        if len(values) >= 3:
            trend_insight = narrate_trend(series_id, values, name, periods=6, unit=unit)
            if trend_insight.text and 'flat' not in trend_insight.text.lower():
                insights.append(trend_insight)

        # Generate YoY insight if we have year-ago data
        yoy_value = data.get('yoy_value')
        if yoy_value is None and len(values) >= 12:
            yoy_value = values[-12]
        if yoy_value is not None:
            is_payroll = series_id == 'PAYEMS' and data.get('is_payroll_change', False)
            yoy_insight = narrate_yoy_change(series_id, latest, yoy_value, name, unit, is_payroll)
            insights.append(yoy_insight)

        # Generate position-in-range insight if we have 5-year data
        min_5yr = data.get('min_5yr')
        max_5yr = data.get('max_5yr')
        if min_5yr is None and len(values) >= 60:
            min_5yr = min(values[-60:])
            max_5yr = max(values[-60:])
        if min_5yr is not None and max_5yr is not None:
            range_insight = narrate_position_in_range(series_id, latest, min_5yr, max_5yr, name, unit)
            insights.append(range_insight)

    # Handle payroll special case
    payroll_data = series_data.get('PAYEMS', {})
    if payroll_data.get('monthly_change') is not None:
        payroll_insight = narrate_payroll_change(
            payroll_data['monthly_change'],
            payroll_data.get('avg_3mo'),
            payroll_data.get('avg_12mo'),
        )
        insights.append(payroll_insight)

    # Generate comparison insights for related series
    insights.extend(_generate_comparison_insights(series_data))

    # Rank insights by importance
    high_insights = [i for i in insights if i.importance == 'high']
    medium_insights = [i for i in insights if i.importance == 'medium']
    low_insights = [i for i in insights if i.importance == 'low']

    # Build the narrative
    narrative_parts = []

    # Lead with high-importance insights
    for insight in high_insights[:2]:  # Max 2 high-importance
        narrative_parts.append(insight.text)

    # Add medium-importance insights
    for insight in medium_insights[:3]:  # Max 3 medium
        if insight.text not in narrative_parts:
            narrative_parts.append(insight.text)

    # Add one low-importance insight for context if we have room
    if len(narrative_parts) < 4 and low_insights:
        narrative_parts.append(low_insights[0].text)

    # Add forward-looking implications based on query type
    implication = _generate_implication(query_type, insights)
    if implication:
        narrative_parts.append(implication)

    # Combine into prose
    if not narrative_parts:
        return "Insufficient data to generate a narrative."

    return " ".join(narrative_parts)


def _generate_comparison_insights(series_data: Dict[str, Dict]) -> List[DataInsight]:
    """Generate insights comparing related series."""
    insights = []

    # Unemployment comparisons
    if 'LNS14000006' in series_data and 'UNRATE' in series_data:
        black_data = series_data['LNS14000006']
        overall_data = series_data['UNRATE']
        if black_data.get('values') and overall_data.get('values'):
            insight = narrate_comparison(
                'LNS14000006', 'Black unemployment', black_data['values'][-1],
                'UNRATE', 'overall unemployment', overall_data['values'][-1],
            )
            insights.append(insight)

    if 'LNS14000009' in series_data and 'UNRATE' in series_data:
        hispanic_data = series_data['LNS14000009']
        overall_data = series_data['UNRATE']
        if hispanic_data.get('values') and overall_data.get('values'):
            insight = narrate_comparison(
                'LNS14000009', 'Hispanic unemployment', hispanic_data['values'][-1],
                'UNRATE', 'overall unemployment', overall_data['values'][-1],
            )
            insights.append(insight)

    # Inflation comparisons
    if 'CPILFESL' in series_data and 'CPIAUCSL' in series_data:
        core_data = series_data['CPILFESL']
        headline_data = series_data['CPIAUCSL']
        if core_data.get('yoy_pct') and headline_data.get('yoy_pct'):
            insight = narrate_comparison(
                'CPILFESL', 'Core CPI', core_data['yoy_pct'],
                'CPIAUCSL', 'headline CPI', headline_data['yoy_pct'],
            )
            insights.append(insight)

    return insights


def _generate_implication(query_type: str, insights: List[DataInsight]) -> str:
    """Generate forward-looking implication based on insights."""
    implications = {
        'labor': "These labor market conditions inform Fed policy decisions on interest rates.",
        'inflation': "Inflation trajectory will be key for Fed rate path decisions.",
        'growth': "Growth momentum will shape both market expectations and Fed policy.",
        'recession': "These indicators bear watching for signs of economic turning points.",
        'fed': "Market expectations for Fed policy will adjust as these data evolve.",
        'general': "Economic conditions remain dynamic; upcoming data releases will provide clarity.",
    }

    base = implications.get(query_type, implications['general'])

    # Modify based on what we found in the data
    has_concerning = any('concerning' in i.text.lower() or 'crisis' in i.text.lower() or
                        'recessionary' in i.text.lower() or 'inverted' in i.text.lower()
                        for i in insights)
    has_strong = any('strong' in i.text.lower() or 'healthy' in i.text.lower() or
                    'solid' in i.text.lower() or 'target' in i.text.lower()
                    for i in insights)

    if has_concerning and not has_strong:
        return f"These readings warrant close monitoring. {base}"
    elif has_strong and not has_concerning:
        return f"Overall conditions appear solid. {base}"
    elif has_concerning and has_strong:
        return f"The data shows mixed signals - some strength alongside warning signs. {base}"

    return base


def _categorize_series(series_id: str) -> str:
    """Categorize a series by economic domain."""
    labor_series = {'UNRATE', 'LNS14000006', 'LNS14000009', 'PAYEMS', 'ICSA', 'JTSJOL', 'JTSQUR'}
    inflation_series = {'CPIAUCSL', 'CPILFESL', 'PCEPILFE', 'CPIAUCSL_YOY', 'CPILFESL_YOY', 'PCEPILFE_YOY'}
    growth_series = {'GDPC1', 'A191RL1Q225SBEA', 'GDPC1_YOY'}
    rates_series = {'T10Y2Y', 'FEDFUNDS', 'DGS10', 'DGS2'}
    consumer_series = {'UMCSENT', 'PCE', 'RSXFS'}

    if series_id in labor_series:
        return 'labor'
    elif series_id in inflation_series:
        return 'inflation'
    elif series_id in growth_series:
        return 'growth'
    elif series_id in rates_series:
        return 'rates'
    elif series_id in consumer_series:
        return 'consumer'
    return 'other'


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def quick_narrate(
    series_id: str,
    value: float,
    name: str,
    yoy_value: Optional[float] = None,
    unit: str = '%'
) -> str:
    """
    Quick narration for a single data point.

    Generates a simple narrative about a single value with optional YoY comparison.

    Args:
        series_id: The FRED series ID
        value: Current value
        name: Human-readable name
        yoy_value: Year-ago value (optional)
        unit: Unit of measurement

    Returns:
        Narrative string

    Example:
        >>> print(quick_narrate('UNRATE', 4.1, 'Unemployment', 3.7))
        "Unemployment at 4.1% is healthy - near the natural rate. It has risen
         0.4pp from 3.7% a year ago, indicating gradual labor market cooling."
    """
    parts = []

    # Level context
    level = narrate_level(series_id, value, name, unit)
    parts.append(level.text)

    # YoY context if available
    if yoy_value is not None:
        yoy = narrate_yoy_change(series_id, value, yoy_value, name, unit)
        # Extract just the change part, not the repetitive current value
        yoy_text = yoy.text.split('. ', 1)
        if len(yoy_text) > 1:
            parts.append(yoy_text[1])

    return " ".join(parts)


def get_historical_reference(series_id: str) -> Optional[Dict[str, Tuple[float, str]]]:
    """
    Get historical reference points for a series.

    Args:
        series_id: The FRED series ID

    Returns:
        Dictionary of reference points or None
    """
    return HISTORICAL_CONTEXT.get(series_id)


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("DATA NARRATOR MODULE TEST")
    print("=" * 70)

    # Test 1: narrate_level
    print("\n1. Testing narrate_level:")
    test_cases = [
        ('UNRATE', 4.1, 'Unemployment'),
        ('UNRATE', 3.4, 'Unemployment'),
        ('UNRATE', 7.5, 'Unemployment'),
        ('LNS14000006', 5.8, 'Black unemployment'),
        ('LNS14000009', 4.5, 'Hispanic unemployment'),
        ('T10Y2Y', -0.3, 'Yield curve spread'),
        ('T10Y2Y', 0.8, 'Yield curve spread'),
        ('UMCSENT', 62.5, 'Consumer sentiment'),
        ('UMCSENT', 95.0, 'Consumer sentiment'),
        ('ICSA', 220, 'Initial claims'),
        ('ICSA', 450, 'Initial claims'),
        ('JTSJOL', 8500, 'Job openings'),
        ('JTSQUR', 2.3, 'Quits rate'),
    ]
    for series_id, value, name in test_cases:
        insight = narrate_level(series_id, value, name)
        print(f"  {series_id} at {value}: [{insight.importance}]")
        print(f"    {insight.text}")

    # Test 2: narrate_trend
    print("\n2. Testing narrate_trend:")
    values_rising = [4.0, 4.1, 4.2, 4.3, 4.4, 4.5]
    values_falling = [4.5, 4.4, 4.3, 4.2, 4.1, 4.0]
    values_flat = [4.1, 4.1, 4.0, 4.1, 4.1, 4.1]
    values_accelerating = [4.0, 4.05, 4.1, 4.2, 4.35, 4.55]

    for desc, vals in [
        ('Rising unemployment', values_rising),
        ('Falling unemployment', values_falling),
        ('Flat unemployment', values_flat),
        ('Accelerating rise', values_accelerating),
    ]:
        insight = narrate_trend('UNRATE', vals, 'Unemployment')
        print(f"  {desc}: [{insight.importance}]")
        print(f"    {insight.text}")

    # Test 3: narrate_yoy_change
    print("\n3. Testing narrate_yoy_change:")
    yoy_tests = [
        ('UNRATE', 4.1, 3.7, 'Unemployment'),
        ('UNRATE', 4.1, 4.5, 'Unemployment'),
        ('LNS14000006', 7.5, 6.0, 'Black unemployment'),
        ('T10Y2Y', -0.3, 0.5, 'Yield curve'),
        ('ICSA', 280, 210, 'Initial claims'),
    ]
    for series_id, current, year_ago, name in yoy_tests:
        insight = narrate_yoy_change(series_id, current, year_ago, name)
        print(f"  {name} {current} vs {year_ago}: [{insight.importance}]")
        print(f"    {insight.text}")

    # Test 4: narrate_comparison
    print("\n4. Testing narrate_comparison:")
    insight = narrate_comparison(
        'LNS14000006', 'Black unemployment', 7.5,
        'UNRATE', 'overall unemployment', 4.4
    )
    print(f"  Black vs Overall: [{insight.importance}]")
    print(f"    {insight.text}")

    insight = narrate_comparison(
        'CPILFESL_YOY', 'Core CPI', 3.2,
        'CPIAUCSL_YOY', 'Headline CPI', 2.9
    )
    print(f"  Core vs Headline CPI: [{insight.importance}]")
    print(f"    {insight.text}")

    # Test 5: narrate_position_in_range
    print("\n5. Testing narrate_position_in_range:")
    insight = narrate_position_in_range('CPIAUCSL_YOY', 3.2, 0.1, 9.1, 'CPI Inflation')
    print(f"  CPI in range: [{insight.importance}]")
    print(f"    {insight.text}")

    insight = narrate_position_in_range('UNRATE', 4.1, 3.4, 14.7, 'Unemployment')
    print(f"  Unemployment in range: [{insight.importance}]")
    print(f"    {insight.text}")

    # Test 6: narrate_payroll_change
    print("\n6. Testing narrate_payroll_change:")
    payroll_tests = [
        (256, 180, 200),
        (75, 100, 180),
        (-50, 50, 150),
        (350, 280, 200),
    ]
    for value, avg_3mo, avg_12mo in payroll_tests:
        insight = narrate_payroll_change(value, avg_3mo, avg_12mo)
        print(f"  Payrolls {value:+}K: [{insight.importance}]")
        print(f"    {insight.text}")

    # Test 7: quick_narrate
    print("\n7. Testing quick_narrate:")
    text = quick_narrate('UNRATE', 4.1, 'Unemployment', 3.7)
    print(f"    {text}")

    # Test 8: Full build_narrative
    print("\n8. Testing build_narrative:")
    test_data = {
        'UNRATE': {
            'values': [3.7, 3.8, 3.9, 4.0, 4.0, 4.1, 4.1, 4.0, 4.2, 4.1, 4.1, 4.1],
            'name': 'Unemployment Rate',
            'unit': '%',
        },
        'PAYEMS': {
            'values': [157000, 157200, 157400, 157600, 157800, 158000,
                      158200, 158400, 158600, 158800, 159000, 159200],
            'name': 'Total Nonfarm Payrolls',
            'unit': 'K',
            'monthly_change': 200,
            'avg_3mo': 180,
            'avg_12mo': 200,
        },
        'ICSA': {
            'values': [210, 215, 220, 225, 230, 235, 240, 245, 250, 255, 260, 265],
            'name': 'Initial Jobless Claims',
            'unit': 'K',
        },
    }
    narrative = build_narrative("How is the labor market?", test_data, 'labor')
    print(f"  Full narrative:")
    print(f"    {narrative}")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETE")
    print("=" * 70)
