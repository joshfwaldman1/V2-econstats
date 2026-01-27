"""
Data Revision Context Module for EconStats.

This module provides comprehensive context about data revisions and preliminary
estimates for economic indicators. Economic data is not "truth" - it's estimates
with uncertainty and revisions. A +200K payroll print might be revised to +170K
or +230K over the following months.

Key concepts covered:
1. Whether data is preliminary or final
2. Typical revision patterns by series
3. Recent revision history tracking
4. Benchmark revision timing and magnitude
5. Confidence intervals and uncertainty ranges

Source: BLS Technical Notes, BEA methodology, Census Bureau
https://www.bls.gov/bls/empsitquickguide.htm
https://www.bea.gov/system/files/methodologies/0417_how_bea_measures_gdp.pdf

Usage:
    from core.data_revisions import (
        REVISION_METADATA,
        get_revision_context,
        is_preliminary,
        get_data_quality_summary,
        format_with_revision_warning,
    )

    # Get plain-language revision context
    context = get_revision_context('PAYEMS')

    # Check if a data point is preliminary
    is_prelim, explanation = is_preliminary('PAYEMS', '2025-12')

    # Format a value with appropriate warnings
    formatted = format_with_revision_warning('PAYEMS', 256.0, '2025-12')

Design principle: Help users understand that economic data has uncertainty.
A healthy skepticism about precise point estimates leads to better decisions.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re


@dataclass
class RevisionInfo:
    """
    Information about revisions for a data series.

    Attributes:
        series_id: FRED series identifier
        release_schedule: How often data is released (e.g., "monthly", "quarterly")
        revision_schedule: Description of when and how revisions occur
        avg_revision_magnitude: Typical size of revision (in native units)
        avg_revision_direction: Typical direction of revisions ("up", "down", or None)
        benchmark_month: Month when annual benchmark occurs
        confidence_interval_90: 90% confidence interval width (in native units)
        is_current_preliminary: Whether the most recent data point is preliminary
        next_revision_date: ISO date string of expected next revision
        notes: Additional context about data quality
    """
    series_id: str
    release_schedule: str
    revision_schedule: str
    avg_revision_magnitude: float
    avg_revision_direction: Optional[str]
    benchmark_month: str
    confidence_interval_90: float
    is_current_preliminary: bool
    next_revision_date: Optional[str]
    notes: str


# =============================================================================
# REVISION METADATA DATABASE
# Comprehensive metadata for major economic series
# =============================================================================

REVISION_METADATA: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # EMPLOYMENT SERIES (BLS Current Employment Statistics)
    # Source: https://www.bls.gov/ces/publications/benchmark/ces-benchmark-revision.htm
    # =========================================================================
    'PAYEMS': {
        'name': 'Total Nonfarm Payrolls',
        'source': 'BLS Current Employment Statistics (Establishment Survey)',
        'release_schedule': 'Monthly, first Friday after reference week',
        'release_lag_days': 7,  # About 1 week after month end
        'revision_schedule': 'Revised in the 2 subsequent months; annual benchmark in February',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 26},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 30},
            {'round': 'benchmark', 'timing': 'February (for prior March)', 'avg_revision': 100},
        ],
        'avg_revision_1mo': 26,  # thousands
        'avg_revision_2mo': 30,  # thousands
        'avg_benchmark_revision': 100,  # Can be 100-500K for full year
        'direction_bias': None,  # No systematic bias
        'confidence_interval_90': 136,  # thousands, from BLS
        'standard_error': 84,  # thousands
        'benchmark_month': 'February',
        'sample_coverage': 'Initial estimate: ~40% of sample; final: ~80%',
        'survey_size': '~670,000 worksites, covering ~40% of all payroll jobs',
        'notes': (
            'Initial estimate based on ~40% of survey responses. '
            'The birth-death model adds estimated jobs from new businesses, '
            'which can introduce significant error in turning points. '
            'The 2024 benchmark revision was -818K, the largest downward revision since 2009.'
        ),
        'recent_benchmarks': [
            {'year': 2024, 'revision': -818, 'note': 'Largest downward revision since 2009'},
            {'year': 2023, 'revision': +358, 'note': 'Standard upward revision'},
            {'year': 2022, 'revision': -187, 'note': 'Modest downward revision'},
        ],
    },

    'UNRATE': {
        'name': 'Unemployment Rate',
        'source': 'BLS Current Population Survey (Household Survey)',
        'release_schedule': 'Monthly, first Friday after reference week',
        'release_lag_days': 7,
        'revision_schedule': 'Levels not revised; seasonal factors revised annually in January',
        'revision_rounds': [],  # No standard revisions
        'avg_revision': 0.0,  # Levels not revised
        'direction_bias': None,
        'confidence_interval_90': 0.2,  # percentage points
        'standard_error': 0.12,  # percentage points
        'benchmark_month': 'January',  # Seasonal factor revision
        'sample_coverage': '~60,000 households',
        'survey_size': '~60,000 households, representing 110,000+ individuals',
        'notes': (
            'Based on household survey, not establishment survey. '
            'The unemployment rate is not revised after release, but seasonal '
            'adjustment factors are updated annually which can change historical SA values. '
            'Margin of error means a 4.0% reading could be 3.8% to 4.2%.'
        ),
    },

    'U6RATE': {
        'name': 'U-6 Unemployment Rate (Underemployment)',
        'source': 'BLS Current Population Survey',
        'release_schedule': 'Monthly, first Friday',
        'release_lag_days': 7,
        'revision_schedule': 'Levels not revised; seasonal factors revised annually',
        'avg_revision': 0.0,
        'confidence_interval_90': 0.3,  # percentage points
        'notes': (
            'Broader measure including marginally attached and part-time for economic reasons. '
            'Higher sampling variability than headline unemployment.'
        ),
    },

    'ICSA': {
        'name': 'Initial Jobless Claims',
        'source': 'Department of Labor',
        'release_schedule': 'Weekly, Thursday morning',
        'release_lag_days': 5,  # Thursday for week ending Saturday
        'revision_schedule': 'Revised the following week',
        'revision_rounds': [
            {'round': 1, 'timing': '1 week later', 'avg_revision': 3},
        ],
        'avg_revision': 3,  # thousands
        'direction_bias': 'up',  # Usually revised slightly higher
        'confidence_interval_90': 10,  # thousands
        'benchmark_month': None,  # No annual benchmark
        'notes': (
            'State data sometimes delayed; revisions usually small but consistently upward. '
            'Holiday weeks can cause significant distortions. '
            '4-week moving average smooths week-to-week volatility.'
        ),
    },

    'CCSA': {
        'name': 'Continued (Ongoing) Jobless Claims',
        'source': 'Department of Labor',
        'release_schedule': 'Weekly, Thursday (1 week lag)',
        'release_lag_days': 12,
        'revision_schedule': 'Revised the following week',
        'avg_revision': 10,  # thousands
        'notes': 'Lags initial claims by one week; subject to similar revisions.',
    },

    'JTSJOL': {
        'name': 'Job Openings (JOLTS)',
        'source': 'BLS Job Openings and Labor Turnover Survey',
        'release_schedule': 'Monthly, ~40 days after reference month',
        'release_lag_days': 40,
        'revision_schedule': 'Revised in subsequent 2 months; annual benchmark',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 50},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 40},
        ],
        'avg_revision': 50,  # thousands
        'direction_bias': None,
        'confidence_interval_90': 200,  # thousands (high variability)
        'sample_coverage': '~21,000 establishments',
        'notes': (
            'Survey-based with significant sampling variability. '
            'Job openings data has wider confidence intervals than payrolls. '
            'The ratio of openings to unemployed is a key labor market tightness metric.'
        ),
    },

    'JTSQUR': {
        'name': 'Quits Rate (JOLTS)',
        'source': 'BLS JOLTS',
        'release_schedule': 'Monthly, ~40 days lag',
        'release_lag_days': 40,
        'revision_schedule': 'Revised in subsequent months',
        'avg_revision': 0.1,  # percentage points
        'notes': 'High quits rate signals worker confidence; low rate suggests labor market weakness.',
    },

    'CIVPART': {
        'name': 'Labor Force Participation Rate',
        'source': 'BLS Current Population Survey',
        'release_schedule': 'Monthly, first Friday',
        'release_lag_days': 7,
        'revision_schedule': 'Seasonal factors revised annually',
        'avg_revision': 0.0,
        'confidence_interval_90': 0.2,  # percentage points
        'notes': 'Not revised after release; watch for demographic composition effects.',
    },

    'LNS12300060': {
        'name': 'Prime-Age Employment-Population Ratio',
        'source': 'BLS Current Population Survey',
        'release_schedule': 'Monthly, first Friday',
        'release_lag_days': 7,
        'revision_schedule': 'Seasonal factors revised annually',
        'avg_revision': 0.0,
        'confidence_interval_90': 0.2,
        'notes': 'Ages 25-54; less affected by aging demographics than overall LFPR.',
    },

    'CES0500000003': {
        'name': 'Average Hourly Earnings (Private)',
        'source': 'BLS Current Employment Statistics',
        'release_schedule': 'Monthly, first Friday',
        'release_lag_days': 7,
        'revision_schedule': 'Revised in subsequent 2 months',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 0.01},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 0.01},
        ],
        'avg_revision': 0.01,  # dollars
        'confidence_interval_90': 0.06,  # dollars
        'notes': (
            'Composition effects can distort month-to-month changes. '
            'If low-wage workers lose jobs, average hourly earnings rise even with no raises.'
        ),
    },

    # =========================================================================
    # GDP SERIES (BEA National Income and Product Accounts)
    # Source: https://www.bea.gov/news/schedule
    # =========================================================================
    'GDPC1': {
        'name': 'Real Gross Domestic Product',
        'source': 'BEA National Income and Product Accounts',
        'release_schedule': 'Quarterly (advance ~30 days, second ~60 days, third ~90 days)',
        'release_lag_days': 30,  # Advance estimate
        'revision_schedule': 'Advance -> Second (1mo) -> Third (2mo) -> Annual (July) -> Comprehensive (every 5 years)',
        'revision_rounds': [
            {'round': 'advance', 'timing': '~30 days after quarter end', 'avg_revision': 0.0},
            {'round': 'second', 'timing': '~60 days (1 month after advance)', 'avg_revision': 0.5},
            {'round': 'third', 'timing': '~90 days (2 months after advance)', 'avg_revision': 0.6},
            {'round': 'annual', 'timing': 'July (for past 3 years)', 'avg_revision': 1.0},
            {'round': 'comprehensive', 'timing': 'Every 5 years', 'avg_revision': 2.0},
        ],
        'avg_revision_advance_to_second': 0.5,  # percentage points
        'avg_revision_advance_to_third': 0.6,
        'avg_revision_advance_to_annual': 1.0,
        'direction_bias': None,
        'confidence_interval_90': 1.0,  # percentage points
        'benchmark_month': 'July',  # Annual revision
        'release_names': {
            'advance': 'Advance Estimate (~30 days)',
            'second': 'Second Estimate (~60 days)',
            'third': 'Third Estimate (~90 days)',
            'annual': 'Annual Revision (July)',
            'comprehensive': 'Comprehensive Revision (every 5 years)',
        },
        'notes': (
            'Advance estimate uses incomplete data (especially services and inventories). '
            'The average absolute revision from advance to third is 0.6pp. '
            'Annual revisions in July can change the economic narrative significantly. '
            'The Q3 2024 advance was 2.8%, later revised to 3.1%.'
        ),
    },

    'A191RL1Q225SBEA': {
        'name': 'Real GDP Growth Rate (SAAR)',
        'source': 'BEA',
        'release_schedule': 'Quarterly with 3 releases',
        'release_lag_days': 30,
        'revision_schedule': 'Same as GDPC1',
        'avg_revision_advance_to_third': 0.6,
        'confidence_interval_90': 1.0,
        'notes': 'Seasonally adjusted annual rate; this is the "headline" GDP growth number.',
    },

    'PCE': {
        'name': 'Personal Consumption Expenditures',
        'source': 'BEA',
        'release_schedule': 'Monthly, ~1 month lag',
        'release_lag_days': 30,
        'revision_schedule': 'Revised monthly as source data improves; annual revision in July',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 0.1},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 0.1},
            {'round': 'annual', 'timing': 'July', 'avg_revision': 0.2},
        ],
        'avg_revision': 0.1,  # percentage points for MoM growth
        'confidence_interval_90': 0.2,
        'benchmark_month': 'July',
        'notes': (
            'Initial estimate uses partial retail sales and other data. '
            'PCE is more comprehensive than retail sales (includes services).'
        ),
    },

    'PCEC96': {
        'name': 'Real Personal Consumption Expenditures',
        'source': 'BEA',
        'release_schedule': 'Monthly',
        'release_lag_days': 30,
        'revision_schedule': 'Same as nominal PCE',
        'avg_revision': 0.1,
        'notes': 'Inflation-adjusted PCE; accounts for ~70% of GDP.',
    },

    'PCEPI': {
        'name': 'PCE Price Index',
        'source': 'BEA',
        'release_schedule': 'Monthly, ~1 month lag',
        'release_lag_days': 30,
        'revision_schedule': 'Revised monthly; annual revision in July',
        'avg_revision': 0.1,  # percentage points YoY
        'confidence_interval_90': 0.1,
        'notes': "The Fed's preferred inflation measure. More comprehensive than CPI.",
    },

    'PCEPILFE': {
        'name': 'Core PCE Price Index (Ex Food & Energy)',
        'source': 'BEA',
        'release_schedule': 'Monthly',
        'release_lag_days': 30,
        'revision_schedule': 'Revised monthly; annual revision in July',
        'avg_revision': 0.1,
        'confidence_interval_90': 0.1,
        'notes': "Core PCE is the Fed's primary inflation target (2%). Watch the 3-month and 6-month annualized rates.",
    },

    'INDPRO': {
        'name': 'Industrial Production Index',
        'source': 'Federal Reserve Board',
        'release_schedule': 'Monthly, ~15 days after month end',
        'release_lag_days': 15,
        'revision_schedule': 'Revised in subsequent months; annual benchmark',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 0.2},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 0.1},
        ],
        'avg_revision': 0.2,  # percentage points MoM
        'confidence_interval_90': 0.3,
        'benchmark_month': 'March',
        'notes': 'Covers manufacturing, mining, and utilities. Can be volatile month-to-month.',
    },

    # =========================================================================
    # INFLATION SERIES
    # =========================================================================
    'CPIAUCSL': {
        'name': 'Consumer Price Index (All Urban Consumers)',
        'source': 'BLS',
        'release_schedule': 'Monthly, ~2 weeks after month end',
        'release_lag_days': 14,
        'revision_schedule': 'NOT REVISED after initial release (except seasonal factors annually)',
        'revision_rounds': [],
        'avg_revision': 0.0,
        'direction_bias': None,
        'confidence_interval_90': 0.1,  # percentage points for YoY
        'standard_error': 0.06,
        'benchmark_month': 'February',  # Seasonal factor update
        'notes': (
            'CPI is NOT revised after initial release (unlike GDP or payrolls). '
            'Seasonal adjustment factors are updated annually in February. '
            'The CPI basket is updated every 2 years based on Consumer Expenditure Survey.'
        ),
    },

    'CPILFESL': {
        'name': 'Core CPI (Ex Food & Energy)',
        'source': 'BLS',
        'release_schedule': 'Monthly, ~2 weeks after month end',
        'release_lag_days': 14,
        'revision_schedule': 'Not revised; seasonal factors updated annually',
        'avg_revision': 0.0,
        'confidence_interval_90': 0.1,
        'notes': 'Core CPI excludes volatile food and energy; better signal of underlying inflation.',
    },

    'CUSR0000SAF1': {
        'name': 'CPI: Food at Home',
        'source': 'BLS',
        'release_schedule': 'Monthly',
        'release_lag_days': 14,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Grocery prices; can be volatile due to weather, supply shocks.',
    },

    'CUSR0000SETB01': {
        'name': 'CPI: Gasoline',
        'source': 'BLS',
        'release_schedule': 'Monthly',
        'release_lag_days': 14,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Very volatile; driven by crude oil prices and refining capacity.',
    },

    'CUSR0000SEHA': {
        'name': 'CPI: Rent of Primary Residence',
        'source': 'BLS',
        'release_schedule': 'Monthly',
        'release_lag_days': 14,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': (
            'CPI rent lags actual market rents by 12-18 months due to how BLS surveys. '
            'Market rents (Zillow, Apartment List) are more timely but different scope.'
        ),
    },

    # =========================================================================
    # HOUSING SERIES
    # =========================================================================
    'CSUSHPINSA': {
        'name': 'Case-Shiller Home Price Index',
        'source': 'S&P CoreLogic Case-Shiller',
        'release_schedule': 'Monthly, ~2 month lag (released last Tuesday)',
        'release_lag_days': 60,
        'revision_schedule': 'Revised for prior months as sales data is updated',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 0.1},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 0.05},
        ],
        'avg_revision': 0.1,  # percentage points
        'confidence_interval_90': 0.2,
        'notes': (
            'Based on repeat-sales methodology; 2-month lag means it reflects prices from 2-3 months ago. '
            'Covers 20 major metro areas for composite index.'
        ),
    },

    'HOUST': {
        'name': 'Housing Starts',
        'source': 'Census Bureau',
        'release_schedule': 'Monthly, ~18 days after month end',
        'release_lag_days': 18,
        'revision_schedule': 'Revised in subsequent month',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 30},
        ],
        'avg_revision': 30,  # thousands (SAAR)
        'confidence_interval_90': 100,  # thousands
        'standard_error': 60,
        'notes': (
            'Subject to significant sampling error. '
            '90% confidence interval is about +-10% of the level. '
            'Weather can cause large month-to-month swings.'
        ),
    },

    'PERMIT': {
        'name': 'Building Permits',
        'source': 'Census Bureau',
        'release_schedule': 'Monthly, ~18 days after month end',
        'release_lag_days': 18,
        'revision_schedule': 'Revised in subsequent month',
        'avg_revision': 25,  # thousands
        'confidence_interval_90': 80,
        'notes': 'Permits are a leading indicator for starts; less volatile than starts.',
    },

    'MORTGAGE30US': {
        'name': '30-Year Mortgage Rate',
        'source': 'Freddie Mac Primary Mortgage Market Survey',
        'release_schedule': 'Weekly, Thursday',
        'release_lag_days': 2,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Survey-based; may differ from actual rates offered. Rates vary by credit score and down payment.',
    },

    # =========================================================================
    # CONSUMER SERIES
    # =========================================================================
    'RSXFS': {
        'name': 'Retail Sales (Ex Food Services)',
        'source': 'Census Bureau',
        'release_schedule': 'Monthly, ~2 weeks after month end',
        'release_lag_days': 14,
        'revision_schedule': 'Revised in subsequent months; annual benchmark',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 0.2},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 0.1},
            {'round': 'annual', 'timing': 'March', 'avg_revision': 0.3},
        ],
        'avg_revision': 0.2,  # percentage points MoM
        'confidence_interval_90': 0.4,
        'benchmark_month': 'March',
        'notes': (
            'Volatile indicator; revisions can be large. '
            'Watch the "control group" (ex autos, gas, building materials, food services) '
            'which feeds directly into GDP calculations.'
        ),
    },

    'UMCSENT': {
        'name': 'Consumer Sentiment (U of Michigan)',
        'source': 'University of Michigan Survey of Consumers',
        'release_schedule': 'Monthly, preliminary mid-month, final end-of-month',
        'release_lag_days': 14,  # Preliminary
        'revision_schedule': 'Preliminary revised to final at month end',
        'revision_rounds': [
            {'round': 'final', 'timing': 'End of month', 'avg_revision': 1.0},
        ],
        'avg_revision': 1.0,  # index points
        'confidence_interval_90': 2.5,
        'release_names': {
            'preliminary': 'Preliminary (mid-month, ~500 surveys)',
            'final': 'Final (end of month, ~500 more surveys)',
        },
        'notes': (
            'Preliminary based on ~500 surveys; final adds ~500 more. '
            'Sentiment can diverge from actual spending behavior. '
            'The 1-year inflation expectations component is closely watched by the Fed.'
        ),
    },

    'PSAVERT': {
        'name': 'Personal Saving Rate',
        'source': 'BEA',
        'release_schedule': 'Monthly',
        'release_lag_days': 30,
        'revision_schedule': 'Revised monthly; large annual revisions possible',
        'avg_revision': 0.3,  # percentage points
        'notes': 'Residual calculation (income - outlays); subject to large revisions.',
    },

    # =========================================================================
    # MANUFACTURING/BUSINESS SERIES
    # =========================================================================
    'ISM-MFG': {
        'name': 'ISM Manufacturing PMI',
        'source': 'Institute for Supply Management',
        'release_schedule': 'Monthly, first business day',
        'release_lag_days': 1,
        'revision_schedule': 'Not revised after release',
        'avg_revision': 0.0,
        'confidence_interval_90': 1.5,  # index points
        'notes': (
            'Diffusion index: 50 = neutral. Survey-based, not revised. '
            'New orders and employment sub-indices are leading indicators.'
        ),
    },

    'ISM-NMI': {
        'name': 'ISM Services PMI',
        'source': 'Institute for Supply Management',
        'release_schedule': 'Monthly, third business day',
        'release_lag_days': 3,
        'revision_schedule': 'Not revised after release',
        'avg_revision': 0.0,
        'confidence_interval_90': 1.5,
        'notes': 'Services account for ~70% of economy; this is a key indicator.',
    },

    'DGORDER': {
        'name': 'Durable Goods Orders',
        'source': 'Census Bureau',
        'release_schedule': 'Monthly, ~3 weeks after month end',
        'release_lag_days': 21,
        'revision_schedule': 'Revised in subsequent month',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 0.3},
        ],
        'avg_revision': 0.3,  # percentage points MoM
        'confidence_interval_90': 1.0,
        'notes': (
            'Very volatile due to aircraft orders; watch "core" (ex defense, ex aircraft). '
            'Core capital goods orders are a key business investment indicator.'
        ),
    },

    'NEWORDER': {
        'name': "Manufacturers' New Orders",
        'source': 'Census Bureau',
        'release_schedule': 'Monthly',
        'release_lag_days': 35,
        'revision_schedule': 'Revised in subsequent months',
        'avg_revision': 0.2,
        'notes': 'Broader than durable goods; includes nondurable goods.',
    },

    # =========================================================================
    # INTEREST RATES (Generally not revised)
    # =========================================================================
    'FEDFUNDS': {
        'name': 'Effective Federal Funds Rate',
        'source': 'Federal Reserve',
        'release_schedule': 'Daily',
        'release_lag_days': 1,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Actual transaction-weighted rate; not revised. Target range set by FOMC.',
    },

    'DGS10': {
        'name': '10-Year Treasury Yield',
        'source': 'Federal Reserve H.15',
        'release_schedule': 'Daily',
        'release_lag_days': 1,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Market-determined; reflects inflation expectations and term premium.',
    },

    'DGS2': {
        'name': '2-Year Treasury Yield',
        'source': 'Federal Reserve H.15',
        'release_schedule': 'Daily',
        'release_lag_days': 1,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Closely tracks Fed funds expectations.',
    },

    'T10Y2Y': {
        'name': 'Treasury Yield Spread (10Y-2Y)',
        'source': 'Federal Reserve',
        'release_schedule': 'Daily',
        'release_lag_days': 1,
        'revision_schedule': 'Not revised',
        'avg_revision': 0.0,
        'notes': 'Yield curve inversion (negative spread) has preceded every recession since 1970.',
    },

    # =========================================================================
    # TRADE SERIES
    # =========================================================================
    'BOPGSTB': {
        'name': 'Trade Balance (Goods and Services)',
        'source': 'Census Bureau / BEA',
        'release_schedule': 'Monthly, ~5 weeks after month end',
        'release_lag_days': 35,
        'revision_schedule': 'Revised in subsequent months',
        'revision_rounds': [
            {'round': 1, 'timing': '1 month later', 'avg_revision': 2},
            {'round': 2, 'timing': '2 months later', 'avg_revision': 1},
        ],
        'avg_revision': 2,  # billions
        'confidence_interval_90': 5,
        'notes': 'Goods data from Census; services from BEA. Revisions can be significant.',
    },

    'IMPGS': {
        'name': 'Imports of Goods and Services',
        'source': 'BEA',
        'release_schedule': 'Monthly',
        'release_lag_days': 35,
        'revision_schedule': 'Revised monthly',
        'avg_revision': 1,  # billions
        'notes': 'Rising imports can subtract from GDP but signal strong domestic demand.',
    },

    'EXPGS': {
        'name': 'Exports of Goods and Services',
        'source': 'BEA',
        'release_schedule': 'Monthly',
        'release_lag_days': 35,
        'revision_schedule': 'Revised monthly',
        'avg_revision': 1,  # billions
        'notes': 'Export strength depends on global growth and dollar value.',
    },
}


# =============================================================================
# RECENT REVISION HISTORY TRACKING
# Updated periodically with actual revision history
# =============================================================================

RECENT_REVISIONS: Dict[str, Dict[str, Dict[str, Any]]] = {
    'PAYEMS': {
        # Format: 'YYYY-MM': {'initial': X, 'current': Y, 'revision': Z, 'is_final': bool}
        '2025-12': {'initial': 256, 'current': 256, 'revision': 0, 'is_final': False},
        '2025-11': {'initial': 212, 'current': 227, 'revision': 15, 'is_final': False},
        '2025-10': {'initial': 12, 'current': 36, 'revision': 24, 'is_final': True},
        '2025-09': {'initial': 223, 'current': 254, 'revision': 31, 'is_final': True},
        '2025-08': {'initial': 142, 'current': 159, 'revision': 17, 'is_final': True},
        '2025-07': {'initial': 114, 'current': 118, 'revision': 4, 'is_final': True},
        # Note: 2024 benchmark revised down 818K total (-68K/month average)
    },
    'GDPC1': {
        '2025-Q4': {'advance': None, 'second': None, 'third': None, 'current': None, 'is_final': False},
        '2025-Q3': {'advance': 2.8, 'second': 2.8, 'third': 3.1, 'current': 3.1, 'is_final': False},
        '2025-Q2': {'advance': 2.8, 'second': 3.0, 'third': 3.0, 'current': 3.0, 'is_final': True},
        '2025-Q1': {'advance': 1.6, 'second': 1.3, 'third': 1.4, 'current': 1.6, 'is_final': True},
    },
    'UMCSENT': {
        '2025-12': {'preliminary': 74.0, 'final': 74.0, 'revision': 0.0},
        '2025-11': {'preliminary': 73.0, 'final': 71.8, 'revision': -1.2},
        '2025-10': {'preliminary': 68.9, 'final': 70.5, 'revision': 1.6},
    },
}


# =============================================================================
# BENCHMARK REVISION HISTORY
# Major annual benchmark revisions that changed the narrative
# =============================================================================

BENCHMARK_HISTORY: Dict[str, List[Dict[str, Any]]] = {
    'PAYEMS': [
        {
            'year': 2024,
            'revision': -818,
            'revision_per_month': -68,
            'benchmark_period': 'March 2023 to March 2024',
            'note': (
                'Largest downward revision since 2009. Birth-death model overestimated '
                'new business job creation. Initial estimates showed strong hiring; '
                'revised data showed much weaker job growth.'
            ),
        },
        {
            'year': 2023,
            'revision': +358,
            'revision_per_month': +30,
            'benchmark_period': 'March 2022 to March 2023',
            'note': 'Standard upward revision; labor market stronger than initially reported.',
        },
        {
            'year': 2022,
            'revision': -187,
            'revision_per_month': -16,
            'benchmark_period': 'March 2021 to March 2022',
            'note': 'Modest downward revision during volatile pandemic recovery period.',
        },
        {
            'year': 2019,
            'revision': -514,
            'revision_per_month': -43,
            'benchmark_period': 'March 2018 to March 2019',
            'note': 'Large downward revision; job growth was notably weaker than initially thought.',
        },
    ],
    'GDPC1': [
        {
            'year': 2024,
            'revision': None,  # Comprehensive revision
            'note': (
                'July 2024 annual revision updated 2021-2023 data. '
                'Showed slightly stronger growth than initially estimated.'
            ),
        },
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_current_period() -> str:
    """Get the current reference period in YYYY-MM format."""
    now = datetime.now()
    return now.strftime('%Y-%m')


def _get_previous_period(periods_back: int = 1) -> str:
    """Get a previous reference period."""
    now = datetime.now()
    previous = now - relativedelta(months=periods_back)
    return previous.strftime('%Y-%m')


def _get_current_quarter() -> str:
    """Get the current quarter in YYYY-QN format."""
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{quarter}"


def _parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string in various formats.

    Supports: 'YYYY-MM', 'YYYY-MM-DD', 'YYYY-QN'
    """
    # Try YYYY-MM format
    if re.match(r'^\d{4}-\d{2}$', date_str):
        return datetime.strptime(date_str, '%Y-%m')

    # Try YYYY-MM-DD format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return datetime.strptime(date_str, '%Y-%m-%d')

    # Try YYYY-QN format
    match = re.match(r'^(\d{4})-Q(\d)$', date_str)
    if match:
        year = int(match.group(1))
        quarter = int(match.group(2))
        month = (quarter - 1) * 3 + 1
        return datetime(year, month, 1)

    return None


def _months_since_date(date_str: str) -> int:
    """Calculate months elapsed since a date string."""
    parsed = _parse_date(date_str)
    if not parsed:
        return 0

    now = datetime.now()
    months = (now.year - parsed.year) * 12 + (now.month - parsed.month)
    return max(0, months)


def _is_quarterly_series(series_id: str) -> bool:
    """Check if a series is quarterly (GDP-related)."""
    quarterly_series = {'GDPC1', 'A191RL1Q225SBEA', 'GDP'}
    return series_id in quarterly_series


# =============================================================================
# MAIN API FUNCTIONS
# =============================================================================

def get_revision_context(series_id: str) -> str:
    """
    Get plain-language context about revisions for a series.

    This is the primary function for getting user-friendly revision information.
    It explains what revisions mean, typical magnitudes, and recent history.

    Args:
        series_id: FRED series identifier (e.g., 'PAYEMS', 'GDPC1')

    Returns:
        A multi-paragraph string explaining revision context.

    Example output for PAYEMS:
        "Note: This is the initial estimate for December payrolls.
         BLS typically revises by +/-30K over the next two months.
         The 90% confidence interval is +/-136K, meaning the true
         value could reasonably be anywhere from +64K to +336K.

         Recent revision history:
         - November: +212K initially -> +227K (+15K revision)
         - October: +12K initially -> +36K (+24K revision)

         Annual benchmark note: The February 2025 benchmark revised
         2024 payrolls down by 818K (-68K/month average)."
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return f"No revision metadata available for {series_id}."

    lines = []
    name = metadata.get('name', series_id)

    # Add header with key warning
    lines.append(f"Data Quality Context for {name}:")
    lines.append("")

    # Revision schedule
    revision_schedule = metadata.get('revision_schedule', 'Unknown revision schedule')
    lines.append(f"Revision schedule: {revision_schedule}")
    lines.append("")

    # Confidence interval / uncertainty
    ci = metadata.get('confidence_interval_90')
    if ci:
        unit = _get_unit_for_series(series_id)
        lines.append(
            f"Uncertainty: The 90% confidence interval is +/-{ci}{unit}. "
            f"This means the true value could reasonably differ from the reported "
            f"number by this amount."
        )
        lines.append("")

    # Recent revision history
    recent = RECENT_REVISIONS.get(series_id, {})
    if recent:
        lines.append("Recent revision history:")
        for period, data in list(recent.items())[:4]:  # Last 4 periods
            if 'initial' in data and 'current' in data:
                initial = data['initial']
                current = data['current']
                revision = data.get('revision', current - initial if initial and current else 0)
                status = "(final)" if data.get('is_final') else "(preliminary)"
                if initial is not None and current is not None:
                    sign = "+" if revision >= 0 else ""
                    lines.append(
                        f"  - {period}: {initial:,.0f} initially -> {current:,.0f} "
                        f"({sign}{revision:,.0f} revision) {status}"
                    )
            elif 'advance' in data:  # GDP format
                advance = data.get('advance')
                current = data.get('current')
                if advance and current:
                    revision = current - advance
                    sign = "+" if revision >= 0 else ""
                    lines.append(
                        f"  - {period}: {advance:.1f}% advance -> {current:.1f}% "
                        f"({sign}{revision:.1f}pp revision)"
                    )
        lines.append("")

    # Benchmark revision context
    benchmark_history = BENCHMARK_HISTORY.get(series_id, [])
    if benchmark_history:
        recent_benchmark = benchmark_history[0]
        year = recent_benchmark.get('year')
        revision = recent_benchmark.get('revision')
        note = recent_benchmark.get('note', '')

        if revision is not None:
            direction = "down" if revision < 0 else "up"
            lines.append(
                f"Annual benchmark note: The {year} benchmark revised data {direction} "
                f"by {abs(revision):,.0f}K."
            )
            if note:
                lines.append(f"  Context: {note}")
            lines.append("")

    # Additional notes
    notes = metadata.get('notes', '')
    if notes:
        lines.append(f"Additional context: {notes}")

    return "\n".join(lines)


def is_preliminary(series_id: str, date: str) -> Tuple[bool, str]:
    """
    Check if a data point is preliminary.

    Args:
        series_id: FRED series identifier
        date: Date string in 'YYYY-MM' or 'YYYY-QN' format

    Returns:
        Tuple of (is_preliminary: bool, explanation: str)

    Example:
        >>> is_preliminary('PAYEMS', '2025-12')
        (True, "This is the initial estimate for December 2025 payrolls.
                Expect revisions of +/-30K over the next two months.")

        >>> is_preliminary('GDPC1', '2025-Q3')
        (True, "This is the third estimate for Q3 2025 GDP. Final annual
                revision will occur in July 2026.")
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return (False, f"No metadata available for {series_id}")

    # Check recent revisions to see if this date is marked as final
    recent = RECENT_REVISIONS.get(series_id, {})
    if date in recent:
        data = recent[date]
        if data.get('is_final', False):
            return (False, f"This is the final revised estimate for {date}.")

    # Calculate months since the reference period
    months_elapsed = _months_since_date(date)

    # Series-specific logic
    name = metadata.get('name', series_id)

    # CPI and similar series that are not revised
    if metadata.get('avg_revision') == 0.0 and not metadata.get('revision_rounds'):
        return (False, f"{name} is not revised after initial release.")

    # GDP has specific release rounds
    if _is_quarterly_series(series_id):
        if months_elapsed < 1:
            return (True, f"This is the advance estimate for {date}. Expect revisions of ~0.5pp when the second estimate releases next month.")
        elif months_elapsed < 2:
            return (True, f"This is the second estimate for {date}. Expect potential revisions of ~0.1pp when the third estimate releases.")
        elif months_elapsed < 3:
            return (True, f"This is the third estimate for {date}. Annual revision occurs in July.")
        elif months_elapsed < 15:  # Before annual revision
            return (True, f"This estimate may be revised in the annual July revision.")
        else:
            return (False, f"This estimate has been through annual revision and is considered final.")

    # Employment and other monthly series
    revision_rounds = metadata.get('revision_rounds', [])
    if revision_rounds:
        if months_elapsed < 1:
            avg_rev = metadata.get('avg_revision_1mo', metadata.get('avg_revision', 0))
            unit = _get_unit_for_series(series_id)
            return (True, f"This is the initial estimate for {date}. Typical revision: +/-{avg_rev}{unit}.")
        elif months_elapsed < 2:
            return (True, f"This has been revised once. One more revision expected.")
        elif months_elapsed < 12:
            benchmark_month = metadata.get('benchmark_month')
            if benchmark_month:
                return (True, f"This may be revised in the annual benchmark ({benchmark_month}).")
            return (False, f"This estimate has been through standard revisions.")
        else:
            return (False, f"This is the final revised estimate.")

    # Default: recent data is preliminary
    if months_elapsed < 3:
        return (True, f"Recent data for {series_id} may be subject to revision.")

    return (False, f"This estimate is considered final.")


def get_release_type(series_id: str, date: str) -> str:
    """
    Get the release type for a data point.

    Args:
        series_id: FRED series identifier
        date: Date string in 'YYYY-MM' or 'YYYY-QN' format

    Returns:
        One of: 'advance', 'preliminary', 'second', 'third', 'final', 'revised', 'not_revised'
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return 'unknown'

    # Check if series is not revised
    if metadata.get('avg_revision') == 0.0 and not metadata.get('revision_rounds'):
        return 'not_revised'

    # Check if marked as final in recent revisions
    recent = RECENT_REVISIONS.get(series_id, {})
    if date in recent and recent[date].get('is_final', False):
        return 'final'

    months_elapsed = _months_since_date(date)

    # GDP-specific release types
    if _is_quarterly_series(series_id):
        if months_elapsed < 1:
            return 'advance'
        elif months_elapsed < 2:
            return 'second'
        elif months_elapsed < 3:
            return 'third'
        elif months_elapsed < 15:
            return 'revised'
        else:
            return 'final'

    # Standard monthly series
    if months_elapsed < 1:
        return 'preliminary'
    elif months_elapsed < 2:
        return 'revised'
    elif months_elapsed < 12:
        return 'revised'
    else:
        return 'final'


def format_with_revision_warning(
    series_id: str,
    value: float,
    date: str,
    include_confidence: bool = True,
) -> str:
    """
    Format a value with appropriate revision warnings.

    This function is designed to be used in data displays to remind users
    that economic data has uncertainty.

    Args:
        series_id: FRED series identifier
        value: The data value
        date: Date string for the observation
        include_confidence: Whether to include confidence interval info

    Returns:
        Formatted string with value and warnings.

    Example:
        >>> format_with_revision_warning('PAYEMS', 256.0, '2025-12')
        "Payrolls: +256K in December 2025 (preliminary)
         Note: This is the initial estimate. Typical revision: +/-30K.
         90% confidence interval: +120K to +392K"

        >>> format_with_revision_warning('GDPC1', 2.8, '2025-Q3')
        "GDP grew 2.8% in Q3 2025 (advance estimate).
         Note: Will be revised twice over the next 2 months.
         Typical revision from advance to third: +/-0.6pp"
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return f"{series_id}: {value}"

    name = metadata.get('name', series_id)
    release_type = get_release_type(series_id, date)
    is_prelim, explanation = is_preliminary(series_id, date)

    lines = []

    # Format the main value
    unit = _get_unit_for_series(series_id)
    if _is_quarterly_series(series_id):
        lines.append(f"{name}: {value:.1f}% in {date} ({release_type} estimate)")
    elif series_id == 'PAYEMS':
        sign = "+" if value >= 0 else ""
        lines.append(f"{name}: {sign}{value:,.0f}K in {date} ({release_type})")
    else:
        lines.append(f"{name}: {value:,.1f}{unit} in {date} ({release_type})")

    # Add revision warning if preliminary
    if is_prelim:
        lines.append(f"  Note: {explanation}")

    # Add confidence interval if requested
    if include_confidence:
        ci = metadata.get('confidence_interval_90')
        if ci:
            lower = value - ci
            upper = value + ci
            if _is_quarterly_series(series_id):
                lines.append(f"  90% confidence interval: {lower:.1f}% to {upper:.1f}%")
            elif series_id == 'PAYEMS':
                lines.append(f"  90% confidence interval: {lower:+,.0f}K to {upper:+,.0f}K")
            else:
                lines.append(f"  90% confidence interval: {lower:,.1f}{unit} to {upper:,.1f}{unit}")

    return "\n".join(lines)


def get_benchmark_context(series_id: str) -> Optional[str]:
    """
    Get context about recent or upcoming benchmark revisions.

    Benchmark revisions occur annually and can significantly change the
    economic narrative. This function provides context about recent
    benchmarks and when the next one is expected.

    Args:
        series_id: FRED series identifier

    Returns:
        Context string about benchmarks, or None if no benchmark info available.

    Example:
        >>> get_benchmark_context('PAYEMS')
        "Note: The February 2025 benchmark revision adjusted 2024
         payrolls down by 818K (-68K/month on average). This was
         the largest downward revision since 2009, attributed to
         the birth-death model overestimating new business formation."
    """
    benchmark_history = BENCHMARK_HISTORY.get(series_id)
    if not benchmark_history:
        return None

    recent = benchmark_history[0]
    lines = []

    year = recent.get('year')
    revision = recent.get('revision')
    per_month = recent.get('revision_per_month')
    note = recent.get('note', '')

    metadata = REVISION_METADATA.get(series_id, {})
    benchmark_month = metadata.get('benchmark_month', 'Unknown')

    if revision is not None:
        direction = "down" if revision < 0 else "up"
        lines.append(
            f"The {benchmark_month} {year} benchmark revision adjusted data {direction} "
            f"by {abs(revision):,.0f}K total"
        )
        if per_month:
            lines.append(f"({per_month:+,.0f}K per month on average).")
        else:
            lines.append(".")

    if note:
        lines.append(f"\nContext: {note}")

    # Add next benchmark timing
    now = datetime.now()
    next_benchmark_year = now.year if now.month < _month_to_int(benchmark_month) else now.year + 1
    lines.append(f"\nNext benchmark: {benchmark_month} {next_benchmark_year}")

    return " ".join(lines)


def compare_initial_vs_revised(series_id: str, n_months: int = 6) -> str:
    """
    Show how initial estimates compared to revised values.

    This helps users understand whether recent data tends to be revised
    up or down, and by how much.

    Args:
        series_id: FRED series identifier
        n_months: Number of months to analyze

    Returns:
        Analysis of revision patterns.

    Example:
        >>> compare_initial_vs_revised('PAYEMS', 6)
        "Recent revision track record for payrolls:
         - Average revision: +17K (slight upward bias recently)
         - Largest revision: +31K (September 2025)
         - All 6 months revised higher"
    """
    recent = RECENT_REVISIONS.get(series_id, {})
    if not recent:
        return f"No revision history available for {series_id}"

    # Filter to items with both initial and current values
    revisions = []
    for period, data in list(recent.items())[:n_months]:
        if 'initial' in data and 'current' in data:
            initial = data['initial']
            current = data['current']
            if initial is not None and current is not None:
                revision = current - initial
                revisions.append({
                    'period': period,
                    'initial': initial,
                    'current': current,
                    'revision': revision,
                })

    if not revisions:
        return f"No revision data available for {series_id}"

    metadata = REVISION_METADATA.get(series_id, {})
    name = metadata.get('name', series_id)

    lines = [f"Recent revision track record for {name}:"]

    # Calculate statistics
    revision_values = [r['revision'] for r in revisions]
    avg_revision = sum(revision_values) / len(revision_values)
    max_revision = max(revisions, key=lambda x: abs(x['revision']))
    up_count = sum(1 for r in revision_values if r > 0)
    down_count = sum(1 for r in revision_values if r < 0)
    unchanged_count = sum(1 for r in revision_values if r == 0)

    # Average revision with direction bias assessment
    if avg_revision > 5:
        bias_note = "(upward bias recently)"
    elif avg_revision < -5:
        bias_note = "(downward bias recently)"
    else:
        bias_note = "(no consistent direction)"

    lines.append(f"  - Average revision: {avg_revision:+,.0f}K {bias_note}")
    lines.append(
        f"  - Largest revision: {max_revision['revision']:+,.0f}K "
        f"({max_revision['period']})"
    )

    # Direction summary
    if up_count == len(revisions):
        lines.append(f"  - All {len(revisions)} periods revised higher")
    elif down_count == len(revisions):
        lines.append(f"  - All {len(revisions)} periods revised lower")
    else:
        lines.append(f"  - {up_count} revised up, {down_count} revised down, {unchanged_count} unchanged")

    return "\n".join(lines)


def get_data_quality_summary(series_id: str) -> str:
    """
    Provide an overall data quality summary for a series.

    This is the comprehensive summary suitable for display in tooltips
    or help sections.

    Args:
        series_id: FRED series identifier

    Returns:
        Multi-line data quality summary.

    Example:
        >>> get_data_quality_summary('PAYEMS')
        "Data Quality for Nonfarm Payrolls:
         - Source: BLS establishment survey (~670K worksites)
         - Timeliness: Released first Friday, ~1 week after month end
         - Reliability: 90% CI of +/-136K; revised twice then benchmarked
         - Recent accuracy: Initial estimates have been revised up
           on average by 17K over the past 6 months
         - Caveat: Annual benchmark can move full-year totals by 500K+"
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return f"No data quality information available for {series_id}"

    name = metadata.get('name', series_id)
    source = metadata.get('source', 'Unknown source')
    release_schedule = metadata.get('release_schedule', 'Unknown schedule')
    release_lag = metadata.get('release_lag_days', 'Unknown')
    ci = metadata.get('confidence_interval_90')
    revision_schedule = metadata.get('revision_schedule', 'Unknown')
    survey_size = metadata.get('survey_size', metadata.get('sample_coverage', ''))
    notes = metadata.get('notes', '')

    lines = [f"Data Quality for {name}:"]

    # Source and survey info
    source_line = f"  - Source: {source}"
    if survey_size:
        source_line += f" ({survey_size})"
    lines.append(source_line)

    # Timeliness
    lines.append(f"  - Timeliness: {release_schedule}")
    if isinstance(release_lag, int):
        lines.append(f"    (~{release_lag} days after reference period)")

    # Reliability
    reliability_parts = []
    if ci:
        unit = _get_unit_for_series(series_id)
        reliability_parts.append(f"90% CI of +/-{ci}{unit}")
    reliability_parts.append(revision_schedule.split(';')[0])  # First part of revision schedule
    lines.append(f"  - Reliability: {'; '.join(reliability_parts)}")

    # Recent accuracy
    recent_accuracy = compare_initial_vs_revised(series_id, 6)
    if "No revision" not in recent_accuracy:
        # Extract just the average revision line
        for line in recent_accuracy.split('\n'):
            if 'Average revision' in line:
                lines.append(f"  - Recent accuracy: {line.strip().replace('- ', '')}")
                break

    # Key caveat
    if notes:
        # Extract first sentence as main caveat
        first_sentence = notes.split('.')[0] + '.'
        lines.append(f"  - Key caveat: {first_sentence}")

    return "\n".join(lines)


def get_revision_metadata(series_id: str) -> Optional[Dict[str, Any]]:
    """
    Get raw revision metadata for a series.

    Args:
        series_id: FRED series identifier

    Returns:
        Dictionary of metadata or None if not found.
    """
    return REVISION_METADATA.get(series_id)


def list_tracked_series() -> List[str]:
    """
    List all series with revision metadata.

    Returns:
        List of series IDs.
    """
    return list(REVISION_METADATA.keys())


def get_confidence_interval(series_id: str) -> Optional[Tuple[float, str]]:
    """
    Get the 90% confidence interval for a series.

    Args:
        series_id: FRED series identifier

    Returns:
        Tuple of (ci_value, unit_description) or None if not available.

    Example:
        >>> get_confidence_interval('PAYEMS')
        (136, 'thousands')
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return None

    ci = metadata.get('confidence_interval_90')
    if ci is None:
        return None

    unit = _get_unit_description_for_series(series_id)
    return (ci, unit)


# =============================================================================
# INTERNAL HELPER FUNCTIONS
# =============================================================================

def _get_unit_for_series(series_id: str) -> str:
    """Get the display unit suffix for a series."""
    rate_series = {'UNRATE', 'U6RATE', 'CIVPART', 'LNS12300060', 'PSAVERT', 'MORTGAGE30US'}
    pct_point_series = {'GDPC1', 'A191RL1Q225SBEA', 'CPIAUCSL', 'CPILFESL', 'PCEPI', 'PCEPILFE'}

    if series_id in rate_series:
        return '%'
    elif series_id in pct_point_series:
        return 'pp'
    elif series_id in {'PAYEMS', 'ICSA', 'CCSA', 'JTSJOL', 'HOUST', 'PERMIT'}:
        return 'K'
    elif series_id in {'BOPGSTB', 'IMPGS', 'EXPGS'}:
        return 'B'
    else:
        return ''


def _get_unit_description_for_series(series_id: str) -> str:
    """Get the full unit description for a series."""
    unit_map = {
        'PAYEMS': 'thousands of jobs',
        'ICSA': 'thousands of claims',
        'CCSA': 'thousands of claims',
        'JTSJOL': 'thousands of openings',
        'UNRATE': 'percentage points',
        'U6RATE': 'percentage points',
        'GDPC1': 'percentage points',
        'A191RL1Q225SBEA': 'percentage points',
        'CPIAUCSL': 'percentage points (YoY)',
        'HOUST': 'thousands of units (SAAR)',
        'BOPGSTB': 'billions of dollars',
    }
    return unit_map.get(series_id, 'units')


def _month_to_int(month_name: str) -> int:
    """Convert month name to integer (1-12)."""
    months = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4,
        'May': 5, 'June': 6, 'July': 7, 'August': 8,
        'September': 9, 'October': 10, 'November': 11, 'December': 12
    }
    return months.get(month_name, 1)


# =============================================================================
# CONVENIENCE FUNCTIONS FOR COMMON USE CASES
# =============================================================================

def should_show_revision_warning(series_id: str, date: str) -> bool:
    """
    Quick check if a revision warning should be displayed.

    Args:
        series_id: FRED series identifier
        date: Date string

    Returns:
        True if the data point warrants a revision warning.
    """
    is_prelim, _ = is_preliminary(series_id, date)
    return is_prelim


def get_revision_warning_short(series_id: str) -> str:
    """
    Get a short one-line revision warning for a series.

    Suitable for footnotes or compact displays.

    Args:
        series_id: FRED series identifier

    Returns:
        Short warning string.

    Example:
        >>> get_revision_warning_short('PAYEMS')
        "Preliminary; typical revision +/-30K"
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return ""

    # Not revised series
    if metadata.get('avg_revision') == 0.0 and not metadata.get('revision_rounds'):
        return "Not revised after release"

    # Build short warning
    avg_rev = metadata.get('avg_revision_1mo', metadata.get('avg_revision', 0))
    ci = metadata.get('confidence_interval_90')

    if avg_rev > 0:
        unit = _get_unit_for_series(series_id)
        return f"Preliminary; typical revision +/-{avg_rev:.0f}{unit}"
    elif ci:
        unit = _get_unit_for_series(series_id)
        return f"90% CI: +/-{ci}{unit}"
    else:
        return "Subject to revision"


def format_value_with_uncertainty(
    series_id: str,
    value: float,
    format_spec: str = '.1f'
) -> str:
    """
    Format a value with its uncertainty range inline.

    Args:
        series_id: FRED series identifier
        value: The data value
        format_spec: Python format specification for the value

    Returns:
        Formatted string like "256K (+/-136K)" or "2.8% (+/-1.0pp)"
    """
    metadata = REVISION_METADATA.get(series_id)
    if not metadata:
        return f"{value:{format_spec}}"

    ci = metadata.get('confidence_interval_90')
    unit = _get_unit_for_series(series_id)

    if ci:
        return f"{value:{format_spec}}{unit} (+/-{ci}{unit})"
    else:
        return f"{value:{format_spec}}{unit}"


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Data Revisions Module Test")
    print("=" * 60)

    # Test series
    test_series = ['PAYEMS', 'GDPC1', 'CPIAUCSL', 'UNRATE', 'JTSJOL']

    for sid in test_series:
        print(f"\n{'='*60}")
        print(f"Series: {sid}")
        print(f"{'='*60}")

        # Get full context
        print("\n--- Full Revision Context ---")
        print(get_revision_context(sid))

        # Check if preliminary
        print("\n--- Preliminary Check ---")
        date = _get_current_period() if not _is_quarterly_series(sid) else _get_current_quarter()
        is_prelim, explanation = is_preliminary(sid, date)
        print(f"Date: {date}")
        print(f"Is preliminary: {is_prelim}")
        print(f"Explanation: {explanation}")

        # Get data quality summary
        print("\n--- Data Quality Summary ---")
        print(get_data_quality_summary(sid))

        # Get short warning
        print(f"\n--- Short Warning ---")
        print(get_revision_warning_short(sid))

    print(f"\n{'='*60}")
    print(f"Total tracked series: {len(list_tracked_series())}")
    print(f"{'='*60}")
