"""
Historical Context Provider for EconStats.

Provides historical comparisons and percentile rankings for economic data.
Numbers mean nothing without context - "4.1% unemployment" needs to be compared
to something: pre-pandemic levels, long-term averages, past recessions.

This module provides:
1. Pre-computed benchmarks for key economic series (avoiding repeated API calls)
2. Functions to generate historical context for any data point
3. Prose generation for explaining what values mean historically
4. Similar period matching to find when we've seen similar conditions

Usage:
    from core.historical_context import (
        get_historical_context,
        describe_historical_context,
        compare_to_benchmark,
        HISTORICAL_BENCHMARKS,
    )

    # Get structured historical context
    context = get_historical_context('UNRATE', 4.1)

    # Generate prose description
    description = describe_historical_context(context, 'Unemployment Rate')
    # Returns: "Unemployment at 4.1% is 0.6pp above the pre-pandemic level of 3.5%
    #          but well below the 50-year average of 6.2%..."

Design principles:
1. Numbers need context - always compare to something meaningful
2. Pre-compute benchmarks to avoid slow API calls
3. Multiple comparison points: pre-pandemic, averages, extremes
4. Prose should explain significance, not just state facts
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class HistoricalContext:
    """
    Historical context for an economic data point.

    Provides multiple reference points to understand what a value means:
    - Pre-pandemic comparison (Feb 2020)
    - Short-term and long-term averages
    - Percentile rankings
    - Extremes (min/max with dates)
    - Notable similar historical periods

    Attributes:
        current_value: The value being contextualized
        series_id: FRED series identifier

        pre_pandemic: Value in Feb 2020
        pre_pandemic_change: Human-readable change description
        pre_pandemic_date: The reference date used

        avg_5yr: Average over past 5 years
        avg_10yr: Average over past 10 years
        avg_since_1970: Long-run average (or as far back as data goes)

        percentile_5yr: 0-100 percentile within past 5 years
        percentile_10yr: 0-100 percentile within past 10 years
        percentile_all: 0-100 percentile in all available history

        min_5yr: Minimum value in past 5 years
        max_5yr: Maximum value in past 5 years
        min_date_5yr: Date of 5-year minimum
        max_date_5yr: Date of 5-year maximum

        historical_low: All-time (or modern) low
        historical_low_date: Date of historical low
        historical_high: All-time (or modern) high
        historical_high_date: Date of historical high

        similar_periods: List of periods with similar values
        threshold_zone: What zone the current value falls in (e.g., "low", "elevated")
    """
    current_value: float
    series_id: str

    # Pre-pandemic comparison
    pre_pandemic: Optional[float] = None
    pre_pandemic_change: Optional[str] = None
    pre_pandemic_date: str = "2020-02"

    # Averages
    avg_5yr: Optional[float] = None
    avg_10yr: Optional[float] = None
    avg_since_1970: Optional[float] = None

    # Percentile rankings
    percentile_5yr: Optional[int] = None
    percentile_10yr: Optional[int] = None
    percentile_all: Optional[int] = None

    # 5-year extremes
    min_5yr: Optional[float] = None
    max_5yr: Optional[float] = None
    min_date_5yr: Optional[str] = None
    max_date_5yr: Optional[str] = None

    # All-time extremes
    historical_low: Optional[float] = None
    historical_low_date: Optional[str] = None
    historical_high: Optional[float] = None
    historical_high_date: Optional[str] = None

    # Similar periods and thresholds
    similar_periods: List[str] = field(default_factory=list)
    threshold_zone: Optional[str] = None


@dataclass
class SeriesBenchmark:
    """
    Pre-computed historical benchmarks for a series.

    These benchmarks are pre-computed to avoid needing to fetch historical
    data every time we want to provide context. They should be updated
    periodically as new data becomes available.

    Attributes:
        series_id: FRED series identifier
        name: Human-readable name
        unit: Unit of measurement (%, thousands, index, etc.)

        pre_pandemic: Value in Feb 2020
        pre_pandemic_date: Reference date

        avg_5yr: Approximate 5-year average
        avg_10yr: Approximate 10-year average
        avg_since_1970: Long-run average

        pandemic_peak: Peak/trough during pandemic (Mar 2020 - Dec 2021)
        pandemic_peak_date: Date of pandemic extreme
        pandemic_is_high: True if pandemic caused high, False if low

        great_recession_peak: Peak/trough during Great Recession (Dec 2007 - Jun 2009)
        great_recession_peak_date: Date of Great Recession extreme
        great_recession_is_high: True if recession caused high, False if low

        historical_low: All-time or modern-era low
        historical_low_date: Date of historical low
        historical_high: All-time or modern-era high
        historical_high_date: Date of historical high

        fed_target: Fed's target value if applicable

        thresholds: Dict mapping zone names to threshold values
        threshold_descriptions: Dict mapping zone names to descriptions

        higher_is_better: True if higher values are generally positive
        typical_range: Tuple of (low, high) for normal conditions
    """
    series_id: str
    name: str
    unit: str = "%"

    # Pre-pandemic reference
    pre_pandemic: Optional[float] = None
    pre_pandemic_date: str = "2020-02"

    # Averages
    avg_5yr: Optional[float] = None
    avg_10yr: Optional[float] = None
    avg_since_1970: Optional[float] = None

    # Pandemic extreme
    pandemic_peak: Optional[float] = None
    pandemic_peak_date: Optional[str] = None
    pandemic_is_high: bool = True

    # Great Recession extreme
    great_recession_peak: Optional[float] = None
    great_recession_peak_date: Optional[str] = None
    great_recession_is_high: bool = True

    # Historical extremes
    historical_low: Optional[float] = None
    historical_low_date: Optional[str] = None
    historical_high: Optional[float] = None
    historical_high_date: Optional[str] = None

    # Fed target
    fed_target: Optional[float] = None

    # Threshold zones
    thresholds: Dict[str, float] = field(default_factory=dict)
    threshold_descriptions: Dict[str, str] = field(default_factory=dict)

    # Interpretation guidance
    higher_is_better: bool = False
    typical_range: Tuple[float, float] = (0.0, 0.0)

    # Similar period matching
    similar_period_ranges: Dict[str, Tuple[float, float]] = field(default_factory=dict)


# =============================================================================
# HISTORICAL BENCHMARKS DATABASE
# Pre-computed benchmarks for 15+ key economic series
# =============================================================================

HISTORICAL_BENCHMARKS: Dict[str, SeriesBenchmark] = {

    # =========================================================================
    # EMPLOYMENT INDICATORS
    # =========================================================================

    'UNRATE': SeriesBenchmark(
        series_id='UNRATE',
        name='Unemployment Rate',
        unit='%',

        pre_pandemic=3.5,
        pre_pandemic_date='2020-02',

        avg_5yr=4.5,   # 2019-2024 (elevated by pandemic spike)
        avg_10yr=5.0,  # 2014-2024
        avg_since_1970=6.2,

        pandemic_peak=14.7,
        pandemic_peak_date='2020-04',
        pandemic_is_high=True,

        great_recession_peak=10.0,
        great_recession_peak_date='2009-10',
        great_recession_is_high=True,

        historical_low=2.5,
        historical_low_date='1953-05',
        historical_high=14.7,  # Also the pandemic peak
        historical_high_date='2020-04',

        thresholds={
            'very_low': 3.5,
            'low': 4.0,
            'natural_rate': 4.2,
            'moderate': 5.0,
            'elevated': 6.0,
            'high': 7.5,
            'recession': 10.0,
        },
        threshold_descriptions={
            'very_low': 'Historically tight labor market',
            'low': 'Tight labor market, employers competing for workers',
            'natural_rate': 'Near the Fed\'s estimate of full employment',
            'moderate': 'Some slack in the labor market',
            'elevated': 'Meaningful labor market weakness',
            'high': 'Significant unemployment, typical of recessions',
            'recession': 'Severe economic distress',
        },

        higher_is_better=False,
        typical_range=(4.0, 6.0),

        similar_period_ranges={
            'Late 2019 (pre-pandemic)': (3.4, 3.7),
            'Mid-2017 to 2018': (3.8, 4.4),
            'Late 1990s boom': (3.8, 4.5),
            '2015-2016': (4.7, 5.3),
            '2013-2014 (post-recession)': (6.2, 7.5),
            'Great Recession (2009-2010)': (9.0, 10.0),
        },
    ),

    'PAYEMS': SeriesBenchmark(
        series_id='PAYEMS',
        name='Monthly Payroll Change',
        unit='thousands',

        pre_pandemic=273,  # Feb 2020 monthly change
        pre_pandemic_date='2020-02',

        avg_5yr=180,   # Excludes pandemic swings
        avg_10yr=195,
        avg_since_1970=130,

        pandemic_peak=-20477,  # April 2020 - massive job losses
        pandemic_peak_date='2020-04',
        pandemic_is_high=False,  # Pandemic caused low (job losses)

        great_recession_peak=-800,  # Peak monthly job losses
        great_recession_peak_date='2009-01',
        great_recession_is_high=False,

        historical_low=-20477,
        historical_low_date='2020-04',
        historical_high=4493,  # May 2020 rebound
        historical_high_date='2020-05',

        thresholds={
            'job_loss': 0,
            'weak': 50,
            'breakeven': 100,
            'solid': 150,
            'strong': 200,
            'very_strong': 300,
            'boom': 400,
        },
        threshold_descriptions={
            'job_loss': 'Economy shedding jobs',
            'weak': 'Anemic job creation',
            'breakeven': 'Roughly keeping pace with population growth',
            'solid': 'Healthy labor market',
            'strong': 'Strong job creation',
            'very_strong': 'Robust expansion',
            'boom': 'Exceptional, potentially unsustainable',
        },

        higher_is_better=True,
        typical_range=(100, 250),
    ),

    'ICSA': SeriesBenchmark(
        series_id='ICSA',
        name='Initial Jobless Claims',
        unit='thousands',

        pre_pandemic=211,
        pre_pandemic_date='2020-02',

        avg_5yr=280,   # Elevated by pandemic
        avg_10yr=310,
        avg_since_1970=350,

        pandemic_peak=6137,  # March 28, 2020 week
        pandemic_peak_date='2020-03',
        pandemic_is_high=True,

        great_recession_peak=665,
        great_recession_peak_date='2009-03',
        great_recession_is_high=True,

        historical_low=162,
        historical_low_date='1968-11',
        historical_high=6137,
        historical_high_date='2020-03',

        thresholds={
            'very_low': 200,
            'low': 225,
            'normal': 275,
            'elevated': 350,
            'high': 450,
            'recession': 600,
        },
        threshold_descriptions={
            'very_low': 'Minimal layoffs, very strong labor market',
            'low': 'Low layoff activity',
            'normal': 'Typical range',
            'elevated': 'Rising layoffs, early warning sign',
            'high': 'Significant layoffs',
            'recession': 'Recession-level layoff activity',
        },

        higher_is_better=False,
        typical_range=(200, 300),
    ),

    'JTSJOL': SeriesBenchmark(
        series_id='JTSJOL',
        name='Job Openings',
        unit='thousands',

        pre_pandemic=7012,
        pre_pandemic_date='2020-02',

        avg_5yr=9500,
        avg_10yr=7200,
        avg_since_1970=5500,  # Data starts 2000

        pandemic_peak=12182,  # March 2022
        pandemic_peak_date='2022-03',
        pandemic_is_high=True,  # Post-pandemic labor shortage

        great_recession_peak=2199,  # Trough in openings
        great_recession_peak_date='2009-07',
        great_recession_is_high=False,  # Recession = few openings

        historical_low=2199,
        historical_low_date='2009-07',
        historical_high=12182,
        historical_high_date='2022-03',

        thresholds={
            'weak': 5000,
            'balanced': 7000,
            'tight': 9000,
            'very_tight': 11000,
        },
        threshold_descriptions={
            'weak': 'Fewer job opportunities, workers have less leverage',
            'balanced': 'Roughly balanced labor market',
            'tight': 'More openings than normal, workers have leverage',
            'very_tight': 'Extreme labor shortage',
        },

        higher_is_better=True,
        typical_range=(5000, 8000),
    ),

    'LNS14000006': SeriesBenchmark(
        series_id='LNS14000006',
        name='Black Unemployment Rate',
        unit='%',

        pre_pandemic=5.8,
        pre_pandemic_date='2020-02',

        avg_5yr=7.5,
        avg_10yr=8.2,
        avg_since_1970=11.6,

        pandemic_peak=16.8,
        pandemic_peak_date='2020-05',
        pandemic_is_high=True,

        great_recession_peak=16.8,  # Same as pandemic
        great_recession_peak_date='2010-03',
        great_recession_is_high=True,

        historical_low=4.7,
        historical_low_date='2023-04',
        historical_high=21.2,
        historical_high_date='1983-01',

        thresholds={
            'record_low': 5.5,
            'low': 6.5,
            'moderate': 8.0,
            'elevated': 10.0,
            'high': 13.0,
        },
        threshold_descriptions={
            'record_low': 'Near historic lows',
            'low': 'Strong labor market for Black workers',
            'moderate': 'Typical range',
            'elevated': 'Above typical, weakness showing',
            'high': 'Significant distress',
        },

        higher_is_better=False,
        typical_range=(6.0, 10.0),
    ),

    'LNS12300060': SeriesBenchmark(
        series_id='LNS12300060',
        name='Prime-Age Employment-Population Ratio',
        unit='%',

        pre_pandemic=80.5,
        pre_pandemic_date='2020-02',

        avg_5yr=79.5,
        avg_10yr=78.5,
        avg_since_1970=77.0,

        pandemic_peak=70.0,
        pandemic_peak_date='2020-04',
        pandemic_is_high=False,  # Pandemic = employment collapse

        great_recession_peak=74.8,
        great_recession_peak_date='2010-11',
        great_recession_is_high=False,

        historical_low=70.0,
        historical_low_date='2020-04',
        historical_high=81.9,
        historical_high_date='2000-04',

        thresholds={
            'depressed': 75.0,
            'below_normal': 78.0,
            'healthy': 80.0,
            'strong': 81.0,
        },
        threshold_descriptions={
            'depressed': 'Many prime-age workers not employed',
            'below_normal': 'Below pre-pandemic levels',
            'healthy': 'Near pre-pandemic peak',
            'strong': 'Near all-time records',
        },

        higher_is_better=True,
        typical_range=(78.0, 81.0),
    ),

    # =========================================================================
    # INFLATION INDICATORS
    # =========================================================================

    'CPIAUCSL_YOY': SeriesBenchmark(
        series_id='CPIAUCSL_YOY',
        name='CPI Inflation (Year-over-Year)',
        unit='%',

        pre_pandemic=2.3,
        pre_pandemic_date='2020-02',

        avg_5yr=4.5,   # Elevated by 2021-2023 inflation
        avg_10yr=3.2,
        avg_since_1970=4.0,

        pandemic_peak=9.1,
        pandemic_peak_date='2022-06',
        pandemic_is_high=True,

        great_recession_peak=-2.1,  # Deflation
        great_recession_peak_date='2009-07',
        great_recession_is_high=False,

        fed_target=2.0,

        historical_low=-2.1,
        historical_low_date='2009-07',
        historical_high=14.8,
        historical_high_date='1980-03',

        thresholds={
            'deflation': 0.0,
            'too_low': 1.5,
            'target': 2.0,
            'slightly_above': 2.5,
            'elevated': 3.5,
            'high': 5.0,
            'very_high': 7.0,
        },
        threshold_descriptions={
            'deflation': 'Prices falling - can signal weak demand',
            'too_low': 'Below Fed target, risk of deflation',
            'target': 'Fed\'s goal',
            'slightly_above': 'Modestly above target',
            'elevated': 'Fed likely to stay restrictive',
            'high': 'Eroding purchasing power significantly',
            'very_high': '1970s/80s-level inflation',
        },

        higher_is_better=False,  # Neither too high nor too low is good
        typical_range=(1.5, 3.0),
    ),

    'PCEPILFE_YOY': SeriesBenchmark(
        series_id='PCEPILFE_YOY',
        name='Core PCE Inflation (Fed\'s Target)',
        unit='%',

        pre_pandemic=1.9,
        pre_pandemic_date='2020-02',

        avg_5yr=3.5,
        avg_10yr=2.5,
        avg_since_1970=3.2,

        pandemic_peak=5.6,
        pandemic_peak_date='2022-02',
        pandemic_is_high=True,

        great_recession_peak=0.9,
        great_recession_peak_date='2010-12',
        great_recession_is_high=False,

        fed_target=2.0,

        historical_low=0.9,
        historical_low_date='2010-12',
        historical_high=10.2,
        historical_high_date='1975-02',

        thresholds={
            'too_low': 1.5,
            'at_target': 2.0,
            'above_target': 2.5,
            'elevated': 3.0,
            'high': 4.0,
        },
        threshold_descriptions={
            'too_low': 'Below target, Fed may ease',
            'at_target': 'Goldilocks - Fed\'s goal',
            'above_target': 'Fed likely to maintain restrictive stance',
            'elevated': 'Sticky inflation concerns',
            'high': 'Significant inflation problem',
        },

        higher_is_better=False,
        typical_range=(1.5, 2.5),
    ),

    'CPILFESL_YOY': SeriesBenchmark(
        series_id='CPILFESL_YOY',
        name='Core CPI Inflation',
        unit='%',

        pre_pandemic=2.4,
        pre_pandemic_date='2020-02',

        avg_5yr=4.2,
        avg_10yr=2.8,
        avg_since_1970=4.1,

        pandemic_peak=6.6,
        pandemic_peak_date='2022-09',
        pandemic_is_high=True,

        great_recession_peak=0.6,
        great_recession_peak_date='2010-10',
        great_recession_is_high=False,

        historical_low=0.6,
        historical_low_date='2010-10',
        historical_high=13.6,
        historical_high_date='1980-06',

        thresholds={
            'low': 2.0,
            'normal': 2.5,
            'elevated': 3.5,
            'high': 5.0,
        },

        higher_is_better=False,
        typical_range=(1.5, 3.0),
    ),

    # =========================================================================
    # INTEREST RATES & YIELD CURVE
    # =========================================================================

    'T10Y2Y': SeriesBenchmark(
        series_id='T10Y2Y',
        name='Yield Curve Spread (10Y-2Y)',
        unit='%',

        pre_pandemic=0.21,
        pre_pandemic_date='2020-02',

        avg_5yr=-0.2,   # Inverted during 2022-2023
        avg_10yr=0.5,
        avg_since_1970=0.9,

        pandemic_peak=1.60,  # Steep curve during recovery
        pandemic_peak_date='2021-03',
        pandemic_is_high=True,

        great_recession_peak=2.91,
        great_recession_peak_date='2010-02',
        great_recession_is_high=True,

        historical_low=-1.08,
        historical_low_date='2023-07',
        historical_high=2.91,
        historical_high_date='2010-02',

        thresholds={
            'deeply_inverted': -0.75,
            'inverted': -0.25,
            'flat': 0.25,
            'normal': 1.0,
            'steep': 2.0,
        },
        threshold_descriptions={
            'deeply_inverted': 'Strong recession warning',
            'inverted': 'Recession warning - has preceded every recession since 1970',
            'flat': 'Neither signaling growth nor recession',
            'normal': 'Healthy upward slope',
            'steep': 'Early recovery expectations',
        },

        higher_is_better=True,  # Generally, normal/steep is healthier
        typical_range=(0.5, 2.0),

        similar_period_ranges={
            '2023 deep inversion': (-1.1, -0.5),
            '2019 inversion': (-0.1, 0.1),
            '2006-2007 inversion': (-0.2, 0.1),
            '2010 steep curve': (2.5, 3.0),
            'Normal expansion': (0.75, 1.5),
        },
    ),

    'FEDFUNDS': SeriesBenchmark(
        series_id='FEDFUNDS',
        name='Federal Funds Rate',
        unit='%',

        pre_pandemic=1.58,
        pre_pandemic_date='2020-02',

        avg_5yr=2.8,
        avg_10yr=1.5,
        avg_since_1970=5.0,

        pandemic_peak=0.05,  # Zero lower bound
        pandemic_peak_date='2020-04',
        pandemic_is_high=False,

        great_recession_peak=0.12,
        great_recession_peak_date='2009-01',
        great_recession_is_high=False,

        historical_low=0.05,
        historical_low_date='2020-04',
        historical_high=20.0,
        historical_high_date='1981-06',

        thresholds={
            'zero_lower_bound': 0.5,
            'accommodative': 2.0,
            'neutral': 2.5,
            'modestly_restrictive': 4.0,
            'restrictive': 5.0,
            'highly_restrictive': 5.5,
        },
        threshold_descriptions={
            'zero_lower_bound': 'Maximum accommodation',
            'accommodative': 'Supporting growth',
            'neutral': 'Neither stimulating nor restraining',
            'modestly_restrictive': 'Slightly slowing the economy',
            'restrictive': 'Intentionally slowing demand',
            'highly_restrictive': 'Significant drag on economy',
        },

        typical_range=(2.0, 5.0),
    ),

    'DGS10': SeriesBenchmark(
        series_id='DGS10',
        name='10-Year Treasury Yield',
        unit='%',

        pre_pandemic=1.50,
        pre_pandemic_date='2020-02',

        avg_5yr=3.0,
        avg_10yr=2.3,
        avg_since_1970=6.0,

        pandemic_peak=0.52,
        pandemic_peak_date='2020-08',
        pandemic_is_high=False,

        great_recession_peak=2.04,
        great_recession_peak_date='2008-12',
        great_recession_is_high=False,

        historical_low=0.52,
        historical_low_date='2020-08',
        historical_high=15.84,
        historical_high_date='1981-09',

        thresholds={
            'very_low': 1.5,
            'low': 2.5,
            'normal': 3.5,
            'elevated': 4.5,
            'high': 5.0,
        },
        threshold_descriptions={
            'very_low': 'Flight to safety or deflation fears',
            'low': 'Accommodative financial conditions',
            'normal': 'Historical average range',
            'elevated': 'Tightening financial conditions',
            'high': 'Significant headwind for housing and stocks',
        },

        typical_range=(2.0, 4.0),
    ),

    # =========================================================================
    # GDP & GROWTH
    # =========================================================================

    'A191RL1Q225SBEA': SeriesBenchmark(
        series_id='A191RL1Q225SBEA',
        name='Real GDP Growth (Quarterly, SAAR)',
        unit='%',

        pre_pandemic=2.1,  # Q4 2019
        pre_pandemic_date='2019-Q4',

        avg_5yr=2.5,
        avg_10yr=2.3,
        avg_since_1970=2.7,

        pandemic_peak=-28.0,  # Q2 2020
        pandemic_peak_date='2020-Q2',
        pandemic_is_high=False,

        great_recession_peak=-8.5,  # Q4 2008
        great_recession_peak_date='2008-Q4',
        great_recession_is_high=False,

        historical_low=-28.0,
        historical_low_date='2020-Q2',
        historical_high=35.2,  # Q3 2020 rebound
        historical_high_date='2020-Q3',

        thresholds={
            'contraction': 0.0,
            'stall_speed': 1.0,
            'below_trend': 1.5,
            'trend': 2.5,
            'above_trend': 3.5,
            'strong': 4.5,
        },
        threshold_descriptions={
            'contraction': 'Economy shrinking',
            'stall_speed': 'Barely growing, recession risk',
            'below_trend': 'Below potential growth',
            'trend': 'Sustainable pace',
            'above_trend': 'Strong, potentially inflationary',
            'strong': 'Very strong, typically unsustainable',
        },

        higher_is_better=True,
        typical_range=(1.5, 3.5),
    ),

    # =========================================================================
    # CONSUMER INDICATORS
    # =========================================================================

    'UMCSENT': SeriesBenchmark(
        series_id='UMCSENT',
        name='Consumer Sentiment (U of Michigan)',
        unit='index',

        pre_pandemic=101.0,
        pre_pandemic_date='2020-02',

        avg_5yr=70.0,   # Depressed by pandemic and inflation
        avg_10yr=85.0,
        avg_since_1970=85.0,

        pandemic_peak=50.0,
        pandemic_peak_date='2022-06',
        pandemic_is_high=False,  # Inflation shock

        great_recession_peak=55.3,
        great_recession_peak_date='2008-11',
        great_recession_is_high=False,

        historical_low=50.0,
        historical_low_date='2022-06',
        historical_high=111.8,
        historical_high_date='2000-01',

        thresholds={
            'crisis': 55,
            'depressed': 65,
            'pessimistic': 75,
            'neutral': 85,
            'healthy': 95,
            'strong': 105,
        },
        threshold_descriptions={
            'crisis': 'Severe pessimism, typically during recessions or shocks',
            'depressed': 'Consumers very worried',
            'pessimistic': 'Below average confidence',
            'neutral': 'Average sentiment',
            'healthy': 'Good confidence',
            'strong': 'Consumers very optimistic',
        },

        higher_is_better=True,
        typical_range=(75, 100),
    ),

    # =========================================================================
    # HOUSING
    # =========================================================================

    'MORTGAGE30US': SeriesBenchmark(
        series_id='MORTGAGE30US',
        name='30-Year Mortgage Rate',
        unit='%',

        pre_pandemic=3.45,
        pre_pandemic_date='2020-02',

        avg_5yr=5.2,
        avg_10yr=4.3,
        avg_since_1970=7.8,

        pandemic_peak=2.65,
        pandemic_peak_date='2021-01',
        pandemic_is_high=False,  # All-time low

        great_recession_peak=4.71,
        great_recession_peak_date='2008-12',
        great_recession_is_high=False,  # Low in response to crisis

        historical_low=2.65,
        historical_low_date='2021-01',
        historical_high=18.63,
        historical_high_date='1981-10',

        thresholds={
            'very_low': 4.0,
            'low': 5.0,
            'moderate': 6.0,
            'elevated': 7.0,
            'high': 8.0,
        },
        threshold_descriptions={
            'very_low': 'Highly accommodative for housing',
            'low': 'Affordable for most buyers',
            'moderate': 'Stretching affordability',
            'elevated': 'Affordability constrained',
            'high': 'Significant headwind for housing',
        },

        higher_is_better=False,  # Lower rates = more affordable
        typical_range=(4.0, 6.5),
    ),

    'CSUSHPINSA_YOY': SeriesBenchmark(
        series_id='CSUSHPINSA_YOY',
        name='Case-Shiller Home Price Growth (YoY)',
        unit='%',

        pre_pandemic=3.9,
        pre_pandemic_date='2020-02',

        avg_5yr=10.0,  # Elevated by pandemic surge
        avg_10yr=7.0,
        avg_since_1970=4.5,  # Data starts 1987

        pandemic_peak=21.2,
        pandemic_peak_date='2022-03',
        pandemic_is_high=True,

        great_recession_peak=-18.0,
        great_recession_peak_date='2008-12',
        great_recession_is_high=False,

        historical_low=-18.0,
        historical_low_date='2008-12',
        historical_high=21.2,
        historical_high_date='2022-03',

        thresholds={
            'declining': 0.0,
            'stable': 3.0,
            'moderate': 5.0,
            'strong': 8.0,
            'unsustainable': 12.0,
        },
        threshold_descriptions={
            'declining': 'Prices falling',
            'stable': 'Roughly in line with inflation',
            'moderate': 'Healthy appreciation',
            'strong': 'Outpacing inflation and wages',
            'unsustainable': 'Boom conditions, affordability crisis',
        },

        higher_is_better=False,  # Mixed - too high = unaffordable
        typical_range=(2.0, 6.0),
    ),

    # =========================================================================
    # ADDITIONAL KEY SERIES
    # =========================================================================

    'RSAFS_YOY': SeriesBenchmark(
        series_id='RSAFS_YOY',
        name='Retail Sales Growth (YoY)',
        unit='%',

        pre_pandemic=4.5,
        pre_pandemic_date='2020-02',

        avg_5yr=6.0,
        avg_10yr=5.0,
        avg_since_1970=5.5,

        pandemic_peak=51.8,  # April 2021 base effects
        pandemic_peak_date='2021-04',
        pandemic_is_high=True,

        great_recession_peak=-11.5,
        great_recession_peak_date='2009-01',
        great_recession_is_high=False,

        historical_low=-21.6,
        historical_low_date='2020-04',
        historical_high=51.8,
        historical_high_date='2021-04',

        thresholds={
            'contracting': 0.0,
            'weak': 2.0,
            'moderate': 4.0,
            'solid': 6.0,
            'strong': 10.0,
        },

        higher_is_better=True,
        typical_range=(2.0, 7.0),
    ),

    'VIXCLS': SeriesBenchmark(
        series_id='VIXCLS',
        name='VIX (Volatility Index)',
        unit='index',

        pre_pandemic=14.4,
        pre_pandemic_date='2020-02',

        avg_5yr=20.0,
        avg_10yr=18.0,
        avg_since_1970=19.5,  # Data starts 1990

        pandemic_peak=82.69,
        pandemic_peak_date='2020-03',
        pandemic_is_high=True,

        great_recession_peak=80.86,
        great_recession_peak_date='2008-11',
        great_recession_is_high=True,

        historical_low=9.14,
        historical_low_date='2017-11',
        historical_high=82.69,
        historical_high_date='2020-03',

        thresholds={
            'complacent': 12,
            'calm': 15,
            'normal': 20,
            'elevated': 25,
            'high': 30,
            'fear': 40,
            'panic': 60,
        },
        threshold_descriptions={
            'complacent': 'Very low fear, potential complacency',
            'calm': 'Low volatility, stable markets',
            'normal': 'Typical volatility',
            'elevated': 'Some nervousness',
            'high': 'Significant uncertainty',
            'fear': 'High fear in markets',
            'panic': 'Extreme panic, crisis conditions',
        },

        higher_is_better=False,
        typical_range=(12, 25),
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _calculate_change_description(
    current: float,
    reference: float,
    unit: str = '%',
    is_percentage_point: bool = True
) -> str:
    """
    Generate a human-readable description of the change between values.

    Args:
        current: Current value
        reference: Reference value to compare against
        unit: Unit of measurement
        is_percentage_point: If True, use "pp" for percentage point changes

    Returns:
        String like "up 0.6pp from pre-pandemic" or "down 2.3% from pre-pandemic"
    """
    diff = current - reference

    if is_percentage_point and unit == '%':
        change_unit = 'pp'
    else:
        change_unit = unit

    if diff > 0:
        direction = 'up'
    elif diff < 0:
        direction = 'down'
        diff = abs(diff)
    else:
        return "unchanged from"

    # Format the difference appropriately
    if abs(diff) < 0.1:
        diff_str = f"{diff:.2f}"
    elif abs(diff) < 10:
        diff_str = f"{diff:.1f}"
    else:
        diff_str = f"{diff:.0f}"

    return f"{direction} {diff_str}{change_unit}"


def _get_threshold_zone(value: float, benchmark: SeriesBenchmark) -> Tuple[str, str]:
    """
    Determine which threshold zone a value falls into.

    Args:
        value: Current value
        benchmark: SeriesBenchmark with thresholds

    Returns:
        Tuple of (zone_name, zone_description)
    """
    if not benchmark.thresholds:
        return ("unknown", "")

    # Sort thresholds by value
    sorted_thresholds = sorted(benchmark.thresholds.items(), key=lambda x: x[1])

    # Find the appropriate zone
    for i, (zone_name, threshold_value) in enumerate(sorted_thresholds):
        if value < threshold_value:
            if i == 0:
                # Below the lowest threshold
                return (zone_name, benchmark.threshold_descriptions.get(zone_name, ""))
            else:
                # In the previous zone
                prev_zone, _ = sorted_thresholds[i - 1]
                return (prev_zone, benchmark.threshold_descriptions.get(prev_zone, ""))

    # Above all thresholds
    highest_zone, _ = sorted_thresholds[-1]
    return (highest_zone, benchmark.threshold_descriptions.get(highest_zone, ""))


def _find_similar_periods(value: float, benchmark: SeriesBenchmark) -> List[str]:
    """
    Find historical periods with similar values.

    Args:
        value: Current value
        benchmark: SeriesBenchmark with similar_period_ranges

    Returns:
        List of period descriptions that match
    """
    if not benchmark.similar_period_ranges:
        return []

    matches = []
    for period_name, (low, high) in benchmark.similar_period_ranges.items():
        if low <= value <= high:
            matches.append(period_name)

    return matches


def _estimate_percentile(
    value: float,
    benchmark: SeriesBenchmark,
    time_horizon: str = "all"
) -> int:
    """
    Estimate percentile ranking based on benchmarks.

    This is a rough estimate based on known benchmarks, not actual
    percentile calculation from historical data.

    Args:
        value: Current value
        benchmark: SeriesBenchmark
        time_horizon: "5yr", "10yr", or "all"

    Returns:
        Estimated percentile (0-100)
    """
    # Use appropriate average and extremes for the time horizon
    if time_horizon == "5yr" and benchmark.avg_5yr:
        avg = benchmark.avg_5yr
        low = benchmark.min_5yr if hasattr(benchmark, 'min_5yr') else benchmark.historical_low
        high = benchmark.max_5yr if hasattr(benchmark, 'max_5yr') else benchmark.historical_high
    elif time_horizon == "10yr" and benchmark.avg_10yr:
        avg = benchmark.avg_10yr
        low = benchmark.historical_low
        high = benchmark.historical_high
    else:
        avg = benchmark.avg_since_1970 or benchmark.avg_10yr or benchmark.avg_5yr
        low = benchmark.historical_low
        high = benchmark.historical_high

    if low is None or high is None:
        return 50  # Default to median

    # Handle case where low == high
    if low == high:
        return 50

    # For series where lower is better (unemployment, inflation)
    if not benchmark.higher_is_better:
        # Invert the percentile
        if value <= low:
            return 99
        elif value >= high:
            return 1
        else:
            # Linear interpolation, inverted
            pct = (high - value) / (high - low) * 100
            return max(1, min(99, int(pct)))
    else:
        # Higher is better
        if value >= high:
            return 99
        elif value <= low:
            return 1
        else:
            pct = (value - low) / (high - low) * 100
            return max(1, min(99, int(pct)))


# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

def get_historical_context(series_id: str, current_value: float) -> HistoricalContext:
    """
    Get comprehensive historical context for a current data point.

    This function looks up pre-computed benchmarks and generates a
    HistoricalContext object with comparisons to:
    - Pre-pandemic levels (Feb 2020)
    - 5-year, 10-year, and long-run averages
    - Percentile rankings
    - Historical extremes
    - Similar historical periods

    Args:
        series_id: FRED series identifier (e.g., 'UNRATE', 'CPIAUCSL_YOY')
        current_value: The current value to contextualize

    Returns:
        HistoricalContext object with all comparison data

    Example:
        >>> context = get_historical_context('UNRATE', 4.1)
        >>> print(context.pre_pandemic_change)
        "up 0.6pp"
    """
    # Look up benchmark
    benchmark = HISTORICAL_BENCHMARKS.get(series_id)

    if not benchmark:
        # Return minimal context if no benchmark found
        return HistoricalContext(
            current_value=current_value,
            series_id=series_id,
        )

    # Build change description for pre-pandemic comparison
    pre_pandemic_change = None
    if benchmark.pre_pandemic is not None:
        pre_pandemic_change = _calculate_change_description(
            current_value,
            benchmark.pre_pandemic,
            benchmark.unit,
        )

    # Get threshold zone
    zone_name, zone_desc = _get_threshold_zone(current_value, benchmark)

    # Find similar periods
    similar_periods = _find_similar_periods(current_value, benchmark)

    # Estimate percentiles
    percentile_5yr = _estimate_percentile(current_value, benchmark, "5yr")
    percentile_10yr = _estimate_percentile(current_value, benchmark, "10yr")
    percentile_all = _estimate_percentile(current_value, benchmark, "all")

    return HistoricalContext(
        current_value=current_value,
        series_id=series_id,

        pre_pandemic=benchmark.pre_pandemic,
        pre_pandemic_change=pre_pandemic_change,
        pre_pandemic_date=benchmark.pre_pandemic_date,

        avg_5yr=benchmark.avg_5yr,
        avg_10yr=benchmark.avg_10yr,
        avg_since_1970=benchmark.avg_since_1970,

        percentile_5yr=percentile_5yr,
        percentile_10yr=percentile_10yr,
        percentile_all=percentile_all,

        # 5-year extremes (approximate from historical extremes if not set)
        min_5yr=benchmark.historical_low,
        max_5yr=benchmark.historical_high,
        min_date_5yr=benchmark.historical_low_date,
        max_date_5yr=benchmark.historical_high_date,

        historical_low=benchmark.historical_low,
        historical_low_date=benchmark.historical_low_date,
        historical_high=benchmark.historical_high,
        historical_high_date=benchmark.historical_high_date,

        similar_periods=similar_periods,
        threshold_zone=zone_name,
    )


def describe_historical_context(context: HistoricalContext, series_name: str) -> str:
    """
    Convert HistoricalContext into readable prose.

    Generates a narrative description explaining what the current value
    means in historical context, including:
    - Comparison to pre-pandemic levels
    - Comparison to long-run averages
    - Percentile ranking interpretation
    - Similar historical periods

    Args:
        context: HistoricalContext object from get_historical_context()
        series_name: Human-readable name of the series (e.g., "Unemployment")

    Returns:
        Multi-sentence prose description

    Example:
        >>> context = get_historical_context('UNRATE', 4.1)
        >>> describe_historical_context(context, 'Unemployment')
        "Unemployment at 4.1% is up 0.6pp from the pre-pandemic level of 3.5%
        but well below the 50-year average of 6.2%. It's in the 25th percentile
        of the past 5 years, suggesting a relatively healthy labor market."
    """
    sentences = []
    value = context.current_value

    # Get benchmark for additional context
    benchmark = HISTORICAL_BENCHMARKS.get(context.series_id)
    unit = benchmark.unit if benchmark else '%'

    # Format value string
    if unit == 'thousands':
        value_str = f"{value:,.0f}K"
    elif unit == 'index':
        value_str = f"{value:.1f}"
    else:
        value_str = f"{value:.1f}{unit}"

    # Opening statement with pre-pandemic comparison
    if context.pre_pandemic is not None and context.pre_pandemic_change:
        if unit == 'thousands':
            pre_str = f"{context.pre_pandemic:,.0f}K"
        elif unit == 'index':
            pre_str = f"{context.pre_pandemic:.1f}"
        else:
            pre_str = f"{context.pre_pandemic:.1f}{unit}"

        sentences.append(
            f"{series_name} at {value_str} is {context.pre_pandemic_change} "
            f"from the pre-pandemic level of {pre_str}."
        )
    else:
        sentences.append(f"{series_name} is currently at {value_str}.")

    # Long-run average comparison
    if context.avg_since_1970:
        if unit == 'thousands':
            avg_str = f"{context.avg_since_1970:,.0f}K"
        elif unit == 'index':
            avg_str = f"{context.avg_since_1970:.1f}"
        else:
            avg_str = f"{context.avg_since_1970:.1f}{unit}"

        if value < context.avg_since_1970:
            comparison = "below"
            distance = context.avg_since_1970 - value
        else:
            comparison = "above"
            distance = value - context.avg_since_1970

        # Qualify the magnitude
        ratio = distance / context.avg_since_1970 if context.avg_since_1970 != 0 else 0
        if ratio < 0.1:
            magnitude = "slightly"
        elif ratio < 0.3:
            magnitude = "moderately"
        else:
            magnitude = "well"

        sentences.append(
            f"This is {magnitude} {comparison} the 50-year average of {avg_str}."
        )

    # Percentile interpretation
    if context.percentile_5yr is not None:
        pct = context.percentile_5yr
        if benchmark and not benchmark.higher_is_better:
            # For series where lower is better (unemployment, inflation)
            if pct >= 75:
                interpretation = "very favorable relative to recent history"
            elif pct >= 50:
                interpretation = "better than the recent average"
            elif pct >= 25:
                interpretation = "somewhat elevated compared to recent years"
            else:
                interpretation = "high compared to the past 5 years"
        else:
            # For series where higher is better (sentiment, GDP)
            if pct >= 75:
                interpretation = "strong by recent standards"
            elif pct >= 50:
                interpretation = "above the recent median"
            elif pct >= 25:
                interpretation = "below the recent average"
            else:
                interpretation = "weak compared to the past 5 years"

        sentences.append(
            f"At the {pct}th percentile of the past 5 years, "
            f"this is {interpretation}."
        )

    # Notable extremes
    if benchmark:
        # Check if near pandemic extreme
        if benchmark.pandemic_peak is not None:
            dist_to_pandemic = abs(value - benchmark.pandemic_peak)
            pandemic_range = abs(benchmark.pandemic_peak - (benchmark.pre_pandemic or 0))
            if pandemic_range > 0 and dist_to_pandemic / pandemic_range < 0.1:
                sentences.append(
                    f"This is near the pandemic extreme of {benchmark.pandemic_peak} "
                    f"({benchmark.pandemic_peak_date})."
                )

        # Check if near Great Recession extreme
        if benchmark.great_recession_peak is not None:
            dist_to_gr = abs(value - benchmark.great_recession_peak)
            if benchmark.pre_pandemic and benchmark.pre_pandemic > 0:
                if dist_to_gr / benchmark.pre_pandemic < 0.15:
                    sentences.append(
                        f"For comparison, the Great Recession peak was "
                        f"{benchmark.great_recession_peak} ({benchmark.great_recession_peak_date})."
                    )

    # Similar historical periods
    if context.similar_periods:
        periods_str = ", ".join(context.similar_periods[:2])
        sentences.append(f"This level is similar to {periods_str}.")

    # Threshold zone interpretation
    if context.threshold_zone and benchmark and benchmark.threshold_descriptions:
        zone_desc = benchmark.threshold_descriptions.get(context.threshold_zone, "")
        if zone_desc:
            sentences.append(zone_desc + ".")

    return " ".join(sentences)


def find_similar_periods(series_id: str, current_value: float) -> List[str]:
    """
    Find historical periods with similar values.

    Searches the benchmark database for periods when the series
    had values in a similar range to the current value.

    Args:
        series_id: FRED series identifier
        current_value: Current value to match

    Returns:
        List of period descriptions (e.g., ["Late 2019", "Mid-2017 to 2018"])

    Example:
        >>> find_similar_periods('UNRATE', 4.1)
        ["Late 2019 (pre-pandemic)", "Mid-2017 to 2018"]
    """
    benchmark = HISTORICAL_BENCHMARKS.get(series_id)
    if not benchmark:
        return []

    return _find_similar_periods(current_value, benchmark)


def compare_to_benchmark(
    series_id: str,
    current_value: float,
    benchmark_name: str
) -> str:
    """
    Compare current value to a specific named benchmark.

    Generates a sentence comparing the current value to a specific
    reference point like pre-pandemic, great recession, or fed target.

    Args:
        series_id: FRED series identifier
        current_value: Current value
        benchmark_name: Name of benchmark to compare to:
            - 'pre_pandemic': Feb 2020 value
            - 'pandemic_peak': Pandemic extreme
            - 'great_recession': Great Recession extreme
            - 'fed_target': Fed's target (if applicable)
            - 'avg_10yr': 10-year average
            - 'avg_since_1970': Long-run average

    Returns:
        Comparison sentence

    Example:
        >>> compare_to_benchmark('UNRATE', 4.1, 'pre_pandemic')
        "Current unemployment of 4.1% is 0.6pp higher than the pre-pandemic
        level of 3.5% (Feb 2020)."
    """
    benchmark = HISTORICAL_BENCHMARKS.get(series_id)
    if not benchmark:
        return f"No benchmark data available for {series_id}."

    unit = benchmark.unit

    # Format current value
    if unit == 'thousands':
        current_str = f"{current_value:,.0f}K"
    elif unit == 'index':
        current_str = f"{current_value:.1f}"
    else:
        current_str = f"{current_value:.1f}{unit}"

    # Get the comparison value
    comparison_value: Optional[float] = None
    comparison_date: Optional[str] = None
    comparison_label: str = ""

    if benchmark_name == 'pre_pandemic':
        comparison_value = benchmark.pre_pandemic
        comparison_date = benchmark.pre_pandemic_date
        comparison_label = "pre-pandemic level"
    elif benchmark_name == 'pandemic_peak':
        comparison_value = benchmark.pandemic_peak
        comparison_date = benchmark.pandemic_peak_date
        comparison_label = "pandemic " + ("high" if benchmark.pandemic_is_high else "low")
    elif benchmark_name == 'great_recession':
        comparison_value = benchmark.great_recession_peak
        comparison_date = benchmark.great_recession_peak_date
        comparison_label = "Great Recession " + ("peak" if benchmark.great_recession_is_high else "trough")
    elif benchmark_name == 'fed_target':
        comparison_value = benchmark.fed_target
        comparison_label = "Fed's target"
    elif benchmark_name == 'avg_10yr':
        comparison_value = benchmark.avg_10yr
        comparison_label = "10-year average"
    elif benchmark_name == 'avg_since_1970':
        comparison_value = benchmark.avg_since_1970
        comparison_label = "50-year average"
    else:
        return f"Unknown benchmark '{benchmark_name}'."

    if comparison_value is None:
        return f"No {comparison_label} data available for {benchmark.name}."

    # Format comparison value
    if unit == 'thousands':
        comp_str = f"{comparison_value:,.0f}K"
    elif unit == 'index':
        comp_str = f"{comparison_value:.1f}"
    else:
        comp_str = f"{comparison_value:.1f}{unit}"

    # Calculate difference
    diff = current_value - comparison_value

    if abs(diff) < 0.01:
        relation = "at"
    elif diff > 0:
        relation = "higher than" if unit != 'thousands' else "above"
    else:
        relation = "lower than" if unit != 'thousands' else "below"

    # Format difference
    diff_str = _calculate_change_description(current_value, comparison_value, unit)

    # Build sentence
    date_str = f" ({comparison_date})" if comparison_date else ""

    return (
        f"Current {benchmark.name.lower()} of {current_str} is {diff_str.split()[0]} "
        f"{diff_str.split()[1] if len(diff_str.split()) > 1 else ''} "
        f"{relation} the {comparison_label} of {comp_str}{date_str}."
    ).replace("  ", " ")


def get_benchmark(series_id: str) -> Optional[SeriesBenchmark]:
    """
    Get the raw benchmark data for a series.

    Args:
        series_id: FRED series identifier

    Returns:
        SeriesBenchmark object or None if not found
    """
    return HISTORICAL_BENCHMARKS.get(series_id)


def list_available_benchmarks() -> List[str]:
    """
    List all series with available benchmarks.

    Returns:
        List of series IDs that have benchmark data
    """
    return list(HISTORICAL_BENCHMARKS.keys())


def get_context_summary(series_id: str, current_value: float) -> Dict[str, Any]:
    """
    Get a summary dict suitable for display/JSON output.

    Provides a structured summary of historical context including
    all key comparisons and interpretations.

    Args:
        series_id: FRED series identifier
        current_value: Current value

    Returns:
        Dictionary with context summary including:
            - current_value
            - pre_pandemic comparison
            - averages
            - percentiles
            - threshold_zone
            - similar_periods
            - narrative (prose description)
    """
    context = get_historical_context(series_id, current_value)
    benchmark = HISTORICAL_BENCHMARKS.get(series_id)
    series_name = benchmark.name if benchmark else series_id

    return {
        'series_id': series_id,
        'series_name': series_name,
        'current_value': current_value,
        'unit': benchmark.unit if benchmark else '%',

        'pre_pandemic': {
            'value': context.pre_pandemic,
            'date': context.pre_pandemic_date,
            'change': context.pre_pandemic_change,
        },

        'averages': {
            '5yr': context.avg_5yr,
            '10yr': context.avg_10yr,
            'since_1970': context.avg_since_1970,
        },

        'percentiles': {
            '5yr': context.percentile_5yr,
            '10yr': context.percentile_10yr,
            'all': context.percentile_all,
        },

        'extremes': {
            'historical_low': context.historical_low,
            'historical_low_date': context.historical_low_date,
            'historical_high': context.historical_high,
            'historical_high_date': context.historical_high_date,
        },

        'threshold_zone': context.threshold_zone,
        'similar_periods': context.similar_periods,

        'narrative': describe_historical_context(context, series_name),
    }


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("HISTORICAL CONTEXT PROVIDER")
    print("=" * 70)

    # Test unemployment context
    print("\n--- Unemployment Rate at 4.1% ---")
    context = get_historical_context('UNRATE', 4.1)
    narrative = describe_historical_context(context, 'Unemployment')
    print(narrative)

    print("\n--- Specific comparisons ---")
    print(compare_to_benchmark('UNRATE', 4.1, 'pre_pandemic'))
    print(compare_to_benchmark('UNRATE', 4.1, 'avg_since_1970'))
    print(compare_to_benchmark('UNRATE', 4.1, 'great_recession'))

    # Test inflation context
    print("\n--- CPI Inflation at 2.8% ---")
    context = get_historical_context('CPIAUCSL_YOY', 2.8)
    narrative = describe_historical_context(context, 'CPI Inflation')
    print(narrative)

    # Test yield curve context
    print("\n--- Yield Curve at -0.5% (inverted) ---")
    context = get_historical_context('T10Y2Y', -0.5)
    narrative = describe_historical_context(context, 'Yield Curve')
    print(narrative)

    print("\nSimilar periods:", find_similar_periods('T10Y2Y', -0.5))

    # Test mortgage rate context
    print("\n--- 30-Year Mortgage at 6.8% ---")
    context = get_historical_context('MORTGAGE30US', 6.8)
    narrative = describe_historical_context(context, '30-Year Mortgage Rate')
    print(narrative)

    # Test consumer sentiment context
    print("\n--- Consumer Sentiment at 72 ---")
    context = get_historical_context('UMCSENT', 72)
    narrative = describe_historical_context(context, 'Consumer Sentiment')
    print(narrative)

    # Show summary for GDP growth
    print("\n--- GDP Growth Summary at 2.5% ---")
    summary = get_context_summary('A191RL1Q225SBEA', 2.5)
    print(f"Series: {summary['series_name']}")
    print(f"Current: {summary['current_value']}{summary['unit']}")
    print(f"Pre-pandemic: {summary['pre_pandemic']['value']} ({summary['pre_pandemic']['change']})")
    print(f"50-year avg: {summary['averages']['since_1970']}")
    print(f"5yr percentile: {summary['percentiles']['5yr']}th")
    print(f"Zone: {summary['threshold_zone']}")
    print(f"\nNarrative: {summary['narrative']}")

    # List all available benchmarks
    print("\n--- Available Benchmarks ---")
    for series_id in list_available_benchmarks():
        benchmark = get_benchmark(series_id)
        print(f"  {series_id}: {benchmark.name}")
