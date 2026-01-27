"""
Premium Economist Analysis Module

This module generates economist-quality analysis by:
1. Looking at data values and trends across multiple indicators
2. Applying economic reasoning to interpret what they mean
3. Connecting multiple indicators into a coherent narrative
4. Highlighting key risks or opportunities

This is what differentiates EconStats from raw data tools - we don't just show
numbers, we explain what they mean and why they matter.

Example output:
    "The labor market remains solid with unemployment at 4.1% and strong job
    gains of 200K. However, inflation at 3.2% remains above the Fed's 2% target,
    suggesting monetary policy will stay restrictive. GDP growth of 2.5% indicates
    resilient expansion despite higher rates. Key watch: whether labor market
    strength can persist as restrictive policy continues."
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from urllib.request import urlopen, Request


# =============================================================================
# OPTIONAL MODULE IMPORTS
# These modules enhance fallback analysis but are not required
# =============================================================================

# Data narrator - provides contextual value descriptions
try:
    from core.data_narrator import (
        build_narrative as build_data_narrative,
        describe_value_with_context,
        BENCHMARKS as DATA_BENCHMARKS,
    )
    HAS_DATA_NARRATOR = True
except ImportError:
    HAS_DATA_NARRATOR = False

# Causal reasoning - provides WHY explanations
try:
    from core.causal_reasoning import (
        build_causal_narrative,
        hedge_causal_claim,
        get_hedging_phrase,
    )
    HAS_CAUSAL_REASONING = True
except ImportError:
    HAS_CAUSAL_REASONING = False

# Historical context - provides benchmark comparisons
try:
    from core.historical_context import (
        get_historical_context,
        describe_historical_context,
        HISTORICAL_BENCHMARKS,
    )
    HAS_HISTORICAL_CONTEXT = True
except ImportError:
    HAS_HISTORICAL_CONTEXT = False

# Narrative templates - provides query-type-specific structure
try:
    from core.narrative_templates import (
        generate_narrative as generate_template_narrative,
        select_template,
        NARRATIVE_TEMPLATES,
    )
    HAS_NARRATIVE_TEMPLATES = True
except ImportError:
    HAS_NARRATIVE_TEMPLATES = False

# Analysis gaps - provides query type detection
try:
    from core.analysis_gaps import detect_query_type
    HAS_ANALYSIS_GAPS = True
except ImportError:
    HAS_ANALYSIS_GAPS = False

# Series context - provides interpretive templates and relationship data
try:
    from core.series_context import (
        get_context as get_series_context,
        interpret_value,
        get_recession_status,
        get_forward_implications,
        SERIES_CONTEXT,
    )
    HAS_SERIES_CONTEXT = True
except ImportError:
    HAS_SERIES_CONTEXT = False


# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class IndicatorSnapshot:
    """
    A snapshot of a single economic indicator with context.

    Attributes:
        series_id: FRED series ID or custom identifier
        name: Human-readable name
        value: Current value
        unit: Unit of measurement (%, thousands, index, etc.)
        date: Date of the latest reading
        yoy_change: Year-over-year change (if available)
        yoy_direction: Pre-computed direction string (e.g., "UP 2.5% from year ago")
        mom_change: Month-over-month change (if available)
        mom_direction: Pre-computed direction string
        position_in_range: Where this sits in its 5-year range
        trend_3mo: Recent 3-month trend direction
        category: Economic category (labor, inflation, growth, housing, etc.)
    """
    series_id: str
    name: str
    value: float
    unit: str
    date: str
    yoy_change: Optional[float] = None
    yoy_direction: Optional[str] = None
    mom_change: Optional[float] = None
    mom_direction: Optional[str] = None
    position_in_range: Optional[str] = None
    trend_3mo: Optional[str] = None
    category: Optional[str] = None


@dataclass
class EconomicContext:
    """
    Contextual information that informs the analysis.

    Attributes:
        fed_rate: Current Fed funds rate
        fed_stance: Fed's current stance (tightening, easing, holding)
        inflation_target: Fed's inflation target (2%)
        natural_unemployment: NAIRU estimate (~4.2%)
        recent_fed_action: Most recent Fed decision
        key_events: Recent economic events that matter
    """
    fed_rate: float = 5.25
    fed_stance: str = "restrictive"
    inflation_target: float = 2.0
    natural_unemployment: float = 4.2
    recent_fed_action: Optional[str] = None
    key_events: Optional[List[str]] = None


@dataclass
class EconomistAnalysis:
    """
    The final economist analysis output.

    Attributes:
        headline: One-sentence summary answering the user's question
        narrative: 3-5 bullet points connecting the indicators
        key_insight: The most important takeaway
        sources: Sources for any claims made (data sources, expert citations)
        confidence: How confident we are in this assessment (low/medium/high)
    """
    headline: str
    narrative: List[str]
    key_insight: str
    sources: List[str] = None  # Sources for claims
    confidence: str = "medium"
    # Deprecated - kept for backwards compatibility but not displayed
    risks: List[str] = None
    opportunities: List[str] = None
    watch_items: List[str] = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = []
        if self.risks is None:
            self.risks = []
        if self.opportunities is None:
            self.opportunities = []
        if self.watch_items is None:
            self.watch_items = []


# =============================================================================
# INDICATOR CATEGORIZATION
# =============================================================================

# Map series IDs to economic categories
SERIES_CATEGORIES = {
    # Labor Market
    'UNRATE': 'labor',
    'PAYEMS': 'labor',
    'ICSA': 'labor',
    'JTSJOL': 'labor',
    'JTSQUR': 'labor',
    'LNS12300060': 'labor',
    'U6RATE': 'labor',
    'CES0500000003': 'labor',  # Average hourly earnings
    'AHETPI': 'labor',

    # Inflation
    'CPIAUCSL': 'inflation',
    'CPILFESL': 'inflation',
    'PCEPI': 'inflation',
    'PCEPILFE': 'inflation',
    'CUSR0000SAH1': 'inflation',  # Shelter CPI
    'CUSR0000SEHA': 'inflation',  # Rent CPI
    'CPIUFDNS': 'inflation',  # Food CPI

    # Growth/Output
    'GDPC1': 'growth',
    'A191RO1Q156NBEA': 'growth',  # GDP YoY
    'A191RL1Q225SBEA': 'growth',  # GDP quarterly
    'INDPRO': 'growth',  # Industrial production
    'RSXFS': 'growth',  # Retail sales
    'PCE': 'growth',  # Personal consumption

    # Interest Rates / Fed
    'FEDFUNDS': 'rates',
    'DFF': 'rates',  # Daily Fed Funds effective rate
    'DGS10': 'rates',
    'DGS2': 'rates',
    'T10Y2Y': 'rates',
    'MORTGAGE30US': 'rates',

    # Recession Indicators
    'SAHMREALTIME': 'recession',  # Sahm Rule Recession Indicator

    # Housing
    'CSUSHPINSA': 'housing',
    'HOUST': 'housing',
    'PERMIT': 'housing',
    'EXHOSLUSM495S': 'housing',
    'HSN1F': 'housing',
    'MSPUS': 'housing',

    # Consumer
    'UMCSENT': 'consumer',
    'PSAVERT': 'consumer',
    'PI': 'consumer',
    'DSPIC96': 'consumer',

    # Financial
    'SP500': 'financial',
    'VIXCLS': 'financial',
    'BAA10Y': 'financial',
    'NFCI': 'financial',
}


def categorize_indicator(series_id: str, name: str = "") -> str:
    """
    Determine the economic category of an indicator.

    Args:
        series_id: The FRED series ID or custom identifier
        name: The human-readable name (used for fuzzy matching)

    Returns:
        Category string: 'labor', 'inflation', 'growth', 'rates', 'housing',
        'consumer', 'financial', or 'other'
    """
    # Direct lookup
    if series_id in SERIES_CATEGORIES:
        return SERIES_CATEGORIES[series_id]

    # Fuzzy matching by name
    name_lower = name.lower()

    if any(term in name_lower for term in ['unemployment', 'payroll', 'job', 'employ', 'labor', 'wage', 'earnings']):
        return 'labor'
    elif any(term in name_lower for term in ['inflation', 'cpi', 'pce', 'price', 'cost']):
        return 'inflation'
    elif any(term in name_lower for term in ['gdp', 'growth', 'output', 'production', 'retail', 'sales']):
        return 'growth'
    elif any(term in name_lower for term in ['rate', 'treasury', 'yield', 'mortgage', 'fed fund']):
        return 'rates'
    elif any(term in name_lower for term in ['home', 'house', 'housing', 'rent', 'shelter']):
        return 'housing'
    elif any(term in name_lower for term in ['consumer', 'sentiment', 'confidence', 'saving', 'income']):
        return 'consumer'
    elif any(term in name_lower for term in ['stock', 's&p', 'nasdaq', 'dow', 'vix', 'credit', 'spread']):
        return 'financial'

    return 'other'


# =============================================================================
# ECONOMIC REASONING RULES
# =============================================================================

# These rules encode economic relationships for coherent narratives.
# CRITICAL: Each rule must check that required keys EXIST before comparing values.
# Using .get() with defaults like 0 or 10 causes false positives when data is missing.
# For example: data.get('core_inflation', 0) <= 2.5 returns True when core_inflation
# is missing, incorrectly triggering "inflation at target" when no data exists.
# Pattern: 'key' in data and data['key'] <comparison>
ECONOMIC_RELATIONSHIPS = {
    # Labor market - describe the data pattern
    'labor_tight': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] < 4.5 and
            'job_openings_per_unemployed' in data and data['job_openings_per_unemployed'] > 1.0
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% with {data['job_openings_per_unemployed']:.1f} job openings per unemployed worker",
        'implication': "more openings than job seekers",
    },
    'labor_cooling': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] > 4.0 and
            'unemployment_trend' in data and data['unemployment_trend'] == 'rising'
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% and rising",
        'implication': "up from recent lows",
    },
    'labor_soft': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] > 5.0
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% - above the 4-5% range of recent years",
        'implication': "elevated relative to pre-pandemic levels",
    },

    # Inflation - describe the data pattern
    'inflation_hot': {
        'conditions': lambda data: (
            'core_inflation' in data and data['core_inflation'] > 3.5
        ),
        'interpretation': lambda data: f"core inflation at {data['core_inflation']:.1f}% - {data['core_inflation'] - 2:.1f}pp above the Fed's 2% target",
        'implication': "more than 1.5x the target rate",
    },
    'inflation_progress': {
        'conditions': lambda data: (
            'core_inflation' in data and 2.5 < data['core_inflation'] <= 3.5 and
            'inflation_trend' in data and data['inflation_trend'] == 'falling'
        ),
        'interpretation': lambda data: f"core inflation at {data['core_inflation']:.1f}% and falling - down from higher levels",
        'implication': f"still above the 2% target but trending down",
    },
    'inflation_target': {
        'conditions': lambda data: (
            'core_inflation' in data and data['core_inflation'] <= 2.5
        ),
        'interpretation': lambda data: f"core inflation at {data['core_inflation']:.1f}% - within 0.5pp of the Fed's 2% target",
        'implication': "near the Fed's goal",
    },

    # Growth - describe the data pattern
    'growth_strong': {
        'conditions': lambda data: (
            'gdp_growth' in data and data['gdp_growth'] > 2.5
        ),
        'interpretation': lambda data: f"GDP growth at {data['gdp_growth']:.1f}% - above the ~2% long-run trend",
        'implication': "faster than typical",
    },
    'growth_moderate': {
        'conditions': lambda data: (
            'gdp_growth' in data and 1.0 < data['gdp_growth'] <= 2.5
        ),
        'interpretation': lambda data: f"GDP growth at {data['gdp_growth']:.1f}% - near the ~2% long-run trend",
        'implication': "around typical growth rates",
    },
    'growth_weak': {
        'conditions': lambda data: (
            'gdp_growth' in data and data['gdp_growth'] <= 1.0
        ),
        'interpretation': lambda data: f"GDP growth at {data['gdp_growth']:.1f}% - below the ~2% long-run trend",
        'implication': "slower than typical",
    },

    # Combined patterns - describe what the data shows together
    'goldilocks': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] < 4.5 and
            'core_inflation' in data and data['core_inflation'] < 3.0 and
            'gdp_growth' in data and data['gdp_growth'] > 1.5
        ),
        'interpretation': lambda data: f"unemployment {data['unemployment']:.1f}%, inflation {data['core_inflation']:.1f}%, GDP {data['gdp_growth']:.1f}%",
        'implication': "low unemployment + moderating inflation + positive growth",
    },
    'stagflation_risk': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] > 4.5 and
            'core_inflation' in data and data['core_inflation'] > 3.5
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% while inflation at {data['core_inflation']:.1f}%",
        'implication': "both elevated simultaneously",
    },

    # Yield curve inversion - state the fact
    'yield_curve_inverted': {
        'conditions': lambda data: 't10y2y' in data and data['t10y2y'] < 0,
        'interpretation': lambda data: f"yield curve spread at {data['t10y2y']:.2f}% (10Y minus 2Y Treasury)",
        'implication': "inverted - short rates above long rates",
    },

    # Sahm Rule trigger - state the indicator value
    'sahm_rule_triggered': {
        'conditions': lambda data: 'sahm_indicator' in data and data['sahm_indicator'] >= 0.5,
        'interpretation': lambda data: f"Sahm Rule indicator at {data['sahm_indicator']:.2f} (threshold: 0.50)",
        'implication': "triggered - has preceded past recessions",
    },

    # Fed policy stance - state the numbers
    'fed_restrictive': {
        'conditions': lambda data: (
            'fed_rate' in data and
            'core_inflation' in data and
            data['fed_rate'] > data['core_inflation'] + 0.5
        ),
        'interpretation': lambda data: f"Fed funds at {data['fed_rate']:.2f}% vs {data['core_inflation']:.1f}% inflation = {data['fed_rate'] - data['core_inflation']:.1f}% real rate",
        'implication': "positive real rate (Fed rate above inflation)",
    },

    # Consumer sentiment - state the reading
    'consumer_pessimism': {
        'conditions': lambda data: 'consumer_sentiment' in data and data['consumer_sentiment'] < 70,
        'interpretation': lambda data: f"consumer sentiment at {data['consumer_sentiment']:.1f} (below 70 is historically low)",
        'implication': "below historical average",
    },

    # Economic pattern - describe what data shows
    'soft_landing': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] < 4.5 and
            'unemployment_trend' in data and data['unemployment_trend'] == 'rising' and
            'core_inflation' in data and data['core_inflation'] < 3.0 and
            'gdp_growth' in data and data['gdp_growth'] > 1.0
        ),
        'interpretation': lambda data: f"unemployment {data['unemployment']:.1f}% (rising), inflation {data['core_inflation']:.1f}%, GDP {data['gdp_growth']:.1f}%",
        'implication': "cooling labor market + falling inflation + positive growth",
    },

    # =========================================================================
    # COMPARISON-SPECIFIC RULES (for 2-series comparisons)
    # =========================================================================

    # Unemployment disparity - Black unemployment significantly exceeds overall
    'unemployment_disparity': {
        'conditions': lambda data: (
            'black_unemployment' in data and
            'unemployment' in data and
            data['black_unemployment'] > data['unemployment'] * 1.3
        ),
        'interpretation': lambda data: f"Black unemployment at {data['black_unemployment']:.1f}% vs overall at {data['unemployment']:.1f}%",
        'implication': lambda data: f"a gap of {data['black_unemployment'] - data['unemployment']:.1f} percentage points ({data['black_unemployment']/data['unemployment']:.1f}x ratio)",
    },

    # Hispanic unemployment disparity
    'hispanic_unemployment_disparity': {
        'conditions': lambda data: (
            'hispanic_unemployment' in data and
            'unemployment' in data and
            data['hispanic_unemployment'] > data['unemployment'] * 1.2
        ),
        'interpretation': lambda data: f"Hispanic unemployment at {data['hispanic_unemployment']:.1f}% vs overall at {data['unemployment']:.1f}%",
        'implication': lambda data: f"a gap of {data['hispanic_unemployment'] - data['unemployment']:.1f} percentage points",
    },

    # Real wage erosion - wages not keeping pace with inflation
    'real_wage_erosion': {
        'conditions': lambda data: (
            'wage_growth' in data and
            'headline_inflation' in data and
            data['wage_growth'] < data['headline_inflation']
        ),
        'interpretation': lambda data: f"wage growth at {data['wage_growth']:.1f}% vs inflation at {data['headline_inflation']:.1f}%",
        'implication': lambda data: f"real wages down {data['headline_inflation'] - data['wage_growth']:.1f}% year-over-year",
    },

    # Real wage gains - wages outpacing inflation
    'real_wage_gains': {
        'conditions': lambda data: (
            'wage_growth' in data and
            'headline_inflation' in data and
            data['wage_growth'] > data['headline_inflation'] + 0.5
        ),
        'interpretation': lambda data: f"wage growth at {data['wage_growth']:.1f}% vs inflation at {data['headline_inflation']:.1f}%",
        'implication': lambda data: f"real wages up {data['wage_growth'] - data['headline_inflation']:.1f}% year-over-year",
    },

    # Core vs headline inflation divergence
    'inflation_divergence': {
        'conditions': lambda data: (
            'core_inflation' in data and
            'headline_inflation' in data and
            abs(data['headline_inflation'] - data['core_inflation']) > 1.0
        ),
        'interpretation': lambda data: f"headline inflation at {data['headline_inflation']:.1f}% vs core at {data['core_inflation']:.1f}%",
        'implication': lambda data: f"a {abs(data['headline_inflation'] - data['core_inflation']):.1f}pp gap driven by food and energy",
    },
}


def apply_economic_reasoning(indicators: Dict[str, float]) -> List[Dict[str, str]]:
    """
    Apply economic reasoning rules to interpret the data.

    Args:
        indicators: Dictionary mapping indicator names to values

    Returns:
        List of applicable interpretations with their implications
    """
    applicable_rules = []

    for rule_name, rule_def in ECONOMIC_RELATIONSHIPS.items():
        try:
            if rule_def['conditions'](indicators):
                # Handle both lambda and string interpretations/implications
                interpretation = rule_def['interpretation']
                if callable(interpretation):
                    interpretation = interpretation(indicators)

                implication = rule_def['implication']
                if callable(implication):
                    implication = implication(indicators)

                applicable_rules.append({
                    'rule': rule_name,
                    'interpretation': interpretation,
                    'implication': implication,
                })
        except (KeyError, TypeError):
            # Rule conditions not met due to missing data
            continue

    return applicable_rules


# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================

def build_data_context(series_data: List[Tuple]) -> Dict[str, Any]:
    """
    Build a context dictionary from series data for economic reasoning.

    This function extracts standardized economic metrics from raw series data,
    and also detects comparison scenarios when exactly two series are present.

    Args:
        series_data: List of (series_id, dates, values, info) tuples

    Returns:
        Dictionary with standardized economic metrics, including comparison
        metrics when applicable (comparison_gap, comparison_ratio, comparison_names,
        comparison_series_keys)
    """
    context = {}

    # Track series for comparison detection
    series_keys = []  # List of (standardized_key, name, latest_value) tuples

    for series_id, dates, values, info in series_data:
        if not values:
            continue

        latest = values[-1]
        name = info.get('name', info.get('title', series_id)).lower()
        display_name = info.get('name', info.get('title', series_id))

        # Track the standardized key for comparison detection
        standardized_key = None

        # Extract key metrics into standardized names
        # Overall unemployment rate (excludes demographic-specific rates)
        if series_id == 'UNRATE' or ('unemployment rate' in name and 'black' not in name and 'hispanic' not in name and 'women' not in name):
            context['unemployment'] = latest
            if len(values) >= 3:
                context['unemployment_trend'] = 'rising' if values[-1] > values[-3] else 'falling'
            standardized_key = 'unemployment'

        # Black unemployment rate
        elif series_id == 'LNS14000006' or ('black' in name and 'unemploy' in name):
            context['black_unemployment'] = latest
            if len(values) >= 3:
                context['black_unemployment_trend'] = 'rising' if values[-1] > values[-3] else 'falling'
            standardized_key = 'black_unemployment'

        # Hispanic unemployment rate
        elif series_id == 'LNS14000009' or ('hispanic' in name and 'unemploy' in name):
            context['hispanic_unemployment'] = latest
            standardized_key = 'hispanic_unemployment'

        # Women's unemployment rate
        elif series_id == 'LNS14000002' or ('women' in name and 'unemploy' in name):
            context['women_unemployment'] = latest
            standardized_key = 'women_unemployment'

        # Wage growth (average hourly earnings)
        elif series_id in ['CES0500000003', 'AHETPI'] or ('wage' in name or 'earnings' in name or 'hourly' in name):
            # Calculate YoY wage growth if we have enough data
            if len(values) >= 12:
                yoy_wage = ((values[-1] / values[-12]) - 1) * 100
                context['wage_growth'] = yoy_wage
                standardized_key = 'wage_growth'
            else:
                context['wage_level'] = latest
                standardized_key = 'wage_level'

        # Headline inflation (CPI All Items)
        elif series_id == 'CPIAUCSL' or ('cpi' in name and 'core' not in name and ('all' in name or 'urban' in name)):
            if len(values) >= 12:
                yoy = ((values[-1] / values[-12]) - 1) * 100
                context['headline_inflation'] = yoy
                if len(values) >= 15:
                    prev_yoy = ((values[-3] / values[-15]) - 1) * 100
                    context['headline_inflation_trend'] = 'falling' if yoy < prev_yoy else 'rising'
                standardized_key = 'headline_inflation'

        # Core inflation (CPI or PCE)
        elif series_id in ['CPILFESL', 'PCEPILFE'] or ('core' in name and ('cpi' in name or 'pce' in name)):
            # Calculate YoY inflation if we have index values
            if len(values) >= 12:
                yoy = ((values[-1] / values[-12]) - 1) * 100
                context['core_inflation'] = yoy
                if len(values) >= 15:
                    prev_yoy = ((values[-3] / values[-15]) - 1) * 100
                    context['inflation_trend'] = 'falling' if yoy < prev_yoy else 'rising'
                standardized_key = 'core_inflation'

        elif series_id == 'GDPC1':
            # GDPC1 is Real GDP level (in billions) - NOT a growth rate
            # Must calculate YoY growth from the level data
            # Quarterly data: need 4 observations for 1 year
            if len(values) >= 4:
                year_ago = values[-4]
                if year_ago > 0:
                    context['gdp_growth'] = ((latest / year_ago) - 1) * 100
            standardized_key = 'gdp_growth'

        elif series_id in ['A191RO1Q156NBEA', 'A191RL1Q225SBEA'] or 'gdp' in name:
            # These are already GDP growth rates, use the value directly
            # A191RO1Q156NBEA = GDP YoY growth rate
            # A191RL1Q225SBEA = GDP quarterly annualized growth rate
            if 'yoy' in name.lower() or 'growth' in name.lower():
                context['gdp_growth'] = latest
            elif info.get('is_yoy'):
                context['gdp_growth'] = latest
            else:
                context['gdp_growth'] = latest
            standardized_key = 'gdp_growth'

        elif series_id == 'JTSJOL' or 'job opening' in name:
            context['job_openings'] = latest
            standardized_key = 'job_openings'

        elif series_id == 'PAYEMS' or 'payroll' in name:
            if info.get('is_payroll_change'):
                context['monthly_job_change'] = latest
                standardized_key = 'monthly_job_change'
            else:
                context['total_payrolls'] = latest
                standardized_key = 'total_payrolls'

        elif series_id in ['FEDFUNDS', 'DFF'] or 'fed funds' in name:
            # Federal funds rate - effective or target rate
            context['fed_rate'] = latest
            standardized_key = 'fed_rate'

        elif series_id == 'T10Y2Y' or '10-year' in name and '2-year' in name:
            # Yield curve spread (10-year minus 2-year Treasury)
            # Negative values indicate inversion, a recession signal
            context['t10y2y'] = latest
            standardized_key = 't10y2y'

        elif series_id == 'SAHMREALTIME' or 'sahm' in name:
            # Sahm Rule Recession Indicator
            # Values >= 0.5 indicate recession has likely begun
            context['sahm_indicator'] = latest
            standardized_key = 'sahm_indicator'

        elif series_id == 'UMCSENT' or 'consumer sentiment' in name or 'michigan' in name:
            # University of Michigan Consumer Sentiment Index
            # Values below 70 indicate depressed consumer confidence
            context['consumer_sentiment'] = latest
            standardized_key = 'consumer_sentiment'

        # Track all series for comparison detection
        # Use standardized key if we recognized the series, otherwise use series_id
        series_keys.append((
            standardized_key if standardized_key else series_id.lower(),
            display_name,
            latest
        ))

    # Calculate derived metrics
    if 'job_openings' in context and 'unemployment' in context:
        # Rough estimate of openings per unemployed
        # Job openings in thousands, labor force ~165M
        labor_force = 165000  # thousands
        unemployed = (context['unemployment'] / 100) * labor_force
        if unemployed > 0:
            context['job_openings_per_unemployed'] = context['job_openings'] / unemployed

    # =========================================================================
    # COMPARISON DETECTION: When exactly 2 series, compute comparison metrics
    # =========================================================================
    if len(series_keys) == 2:
        key1, name1, val1 = series_keys[0]
        key2, name2, val2 = series_keys[1]

        # Store comparison metadata
        context['comparison_names'] = [name1, name2]
        context['comparison_series_keys'] = [key1, key2]
        context['comparison_values'] = [val1, val2]

        # Compute comparison gap (series1 - series2)
        context['comparison_gap'] = val1 - val2

        # Compute comparison ratio (series1 / series2), avoiding division by zero
        if val2 != 0:
            context['comparison_ratio'] = val1 / val2
        else:
            context['comparison_ratio'] = None

        # Determine which series is higher
        if val1 > val2:
            context['comparison_higher'] = name1
            context['comparison_lower'] = name2
        else:
            context['comparison_higher'] = name2
            context['comparison_lower'] = name1

    return context


def generate_economist_analysis(
    query: str,
    series_data: List[Tuple],
    existing_explanation: str = "",
    news_context: str = ""
) -> EconomistAnalysis:
    """
    Generate premium economist-quality analysis of economic data.

    This function:
    1. Extracts key metrics from the data
    2. Applies economic reasoning rules
    3. Calls an LLM to synthesize into coherent narrative
    4. Returns structured analysis with headline, narrative, risks, and opportunities

    Args:
        query: The user's original question
        series_data: List of (series_id, dates, values, info) tuples
        existing_explanation: Any existing explanation to build on
        news_context: Recent news context if available

    Returns:
        EconomistAnalysis dataclass with structured analysis
    """
    # Build data context for reasoning
    data_context = build_data_context(series_data)

    # Apply rule-based economic reasoning
    applicable_rules = apply_economic_reasoning(data_context)

    # Build data summary for LLM
    data_summary = _build_analysis_summary(series_data)

    # Generate analysis via LLM
    analysis = _call_llm_for_analysis(
        query=query,
        data_summary=data_summary,
        data_context=data_context,
        applicable_rules=applicable_rules,
        news_context=news_context,
        series_data=series_data,
    )

    return analysis


def _build_analysis_summary(series_data: List[Tuple]) -> List[Dict]:
    """
    Build a summary of series data for the LLM.

    Args:
        series_data: List of (series_id, dates, values, info) tuples

    Returns:
        List of dictionaries with key data points
    """
    summary = []

    for series_id, dates, values, info in series_data:
        if not values:
            continue

        name = info.get('name', info.get('title', series_id))
        unit = info.get('unit', info.get('units', ''))
        latest = values[-1]
        latest_date = dates[-1] if dates else 'unknown'

        entry = {
            'series_id': series_id,
            'name': name,
            'unit': unit,
            'latest_value': round(latest, 2),
            'latest_date': latest_date,
            'category': categorize_indicator(series_id, name),
        }

        # Add YoY change if available
        if len(values) >= 12:
            year_ago = values[-12]
            if year_ago != 0:
                yoy_change = latest - year_ago
                yoy_pct = (yoy_change / abs(year_ago)) * 100
                entry['yoy_change'] = round(yoy_change, 2)
                entry['yoy_pct_change'] = round(yoy_pct, 1)
                entry['yoy_direction'] = 'UP' if yoy_change > 0 else 'DOWN' if yoy_change < 0 else 'UNCHANGED'

        # Add month-over-month change
        if len(values) >= 2:
            mom_change = values[-1] - values[-2]
            entry['mom_change'] = round(mom_change, 2)
            entry['mom_direction'] = 'UP' if mom_change > 0.01 else 'DOWN' if mom_change < -0.01 else 'FLAT'

        # Add position in range
        recent_vals = values[-60:] if len(values) >= 60 else values
        if recent_vals:
            recent_min = min(recent_vals)
            recent_max = max(recent_vals)
            if recent_max > recent_min:
                position = (latest - recent_min) / (recent_max - recent_min)
                if position > 0.9:
                    entry['position_in_range'] = 'NEAR 5-YEAR HIGH'
                elif position < 0.1:
                    entry['position_in_range'] = 'NEAR 5-YEAR LOW'
                elif position > 0.5:
                    entry['position_in_range'] = 'ABOVE MIDDLE OF RANGE'
                else:
                    entry['position_in_range'] = 'BELOW MIDDLE OF RANGE'

        # Add payroll-specific data
        if info.get('is_payroll_change') and info.get('original_values'):
            orig_values = info['original_values']
            if len(orig_values) >= 2:
                monthly_change = orig_values[-1] - orig_values[-2]
                entry['monthly_job_change'] = round(monthly_change, 1)
            if len(orig_values) >= 13:
                changes_12mo = [orig_values[i] - orig_values[i-1] for i in range(-12, 0)]
                entry['avg_monthly_change_12mo'] = round(sum(changes_12mo) / 12, 1)

        summary.append(entry)

    return summary


def _call_llm_for_analysis(
    query: str,
    data_summary: List[Dict],
    data_context: Dict[str, Any],
    applicable_rules: List[Dict[str, str]],
    news_context: str = "",
    series_data: List[Tuple] = None,
) -> EconomistAnalysis:
    """
    Call Claude to generate the economist analysis.

    Args:
        query: User's question
        data_summary: Summarized data points
        data_context: Extracted economic metrics
        applicable_rules: Economic reasoning rules that apply
        news_context: Recent news if available
        series_data: Raw series data for enhanced fallback analysis

    Returns:
        EconomistAnalysis dataclass
    """
    if not ANTHROPIC_API_KEY:
        return _generate_fallback_analysis(
            query=query,
            data_summary=data_summary,
            data_context=data_context,
            applicable_rules=applicable_rules,
            series_data=series_data or [],
        )

    # Build the rules context
    rules_text = ""
    if applicable_rules:
        rules_text = "\n\nECONOMIC REASONING (pre-computed):\n"
        for rule in applicable_rules:
            rules_text += f"- {rule['interpretation']}. Implication: {rule['implication']}\n"

    # Build series context section (benchmarks, thresholds, forward implications)
    series_context_text = ""
    if HAS_SERIES_CONTEXT and series_data:
        context_items = []
        for series_id, dates, values, info in series_data:
            if values:
                current_value = values[-1]
                # Get the interpretive context
                interpretation = interpret_value(series_id, current_value)
                if interpretation:
                    context_items.append(interpretation)
                # Check for recession warnings
                recession_status = get_recession_status(series_id, current_value)
                if recession_status:
                    context_items.insert(0, f"⚠️ {recession_status}")
                # Get what this series leads
                implications = get_forward_implications(series_id)
                if implications:
                    ctx = get_series_context(series_id)
                    if ctx:
                        context_items.append(f"{ctx.name} leads: {', '.join(implications[:2])}")
        if context_items:
            series_context_text = "\n\nBENCHMARKS & INTERPRETIVE CONTEXT:\n" + "\n".join(f"- {item}" for item in context_items[:6])

    # Build news context section
    news_section = ""
    if news_context:
        news_section = f"\n\nRECENT NEWS CONTEXT:\n{news_context}"

    prompt = f"""You are a sharp economic analyst at a top research firm, writing insights for intelligent non-economists. Your job is to EXPLAIN WHAT THE DATA MEANS and WHY IT MATTERS - not just describe numbers.

USER QUESTION: {query}

DATA:
{json.dumps(data_summary, indent=2)}

KEY METRICS EXTRACTED:
{json.dumps(data_context, indent=2)}
{rules_text}
{series_context_text}
{news_section}

Write an insightful analysis in this exact JSON format:
{{
    "headline": "One punchy sentence answering the user's question with the key insight",
    "narrative": [
        "First, state the most important number with context (vs last year, vs historical average)",
        "Then explain WHY this matters or what's driving it",
        "Connect to a related indicator that confirms or complicates the story",
        "End with the forward-looking implication: what this means for the next 3-6 months"
    ],
    "key_insight": "The one thing a smart person should take away from this data",
    "confidence": "high" | "medium" | "low"
}}

YOUR ANALYSIS SHOULD:
1. ANSWER THE QUESTION - If they asked "is rent inflation coming down?", your headline should say yes or no, not "here's the data"
2. CONNECT THE DOTS - Link multiple indicators into a coherent story (e.g., "Zillow rents fell 6 months ago, and now CPI rent is finally following")
3. PROVIDE CONTEXT - Is this number high or low historically? What's normal? (e.g., "4.4% unemployment is still below the 5.7% long-term average")
4. EXPLAIN CAUSATION - Why is this happening? (e.g., "Shelter inflation is sticky because CPI measures existing leases, not new market rents")
5. LOOK FORWARD - What does this mean for the future? (e.g., "This suggests the Fed will have room to cut by mid-year")
6. BE SPECIFIC - Always include the actual numbers, dates, and YoY changes

GREAT ANALYSIS EXAMPLES:
- "Rent inflation is finally cracking. CPI rent rose 4.8% YoY in December, but that's down from 8% a year ago—and Zillow market rents are already falling 2% YoY. Since CPI rent lags market rents by 12 months, this means shelter inflation should drop sharply by summer 2026."
- "The labor market is cooling but not collapsing. Unemployment rose to 4.4% (up 0.5pp from the low), but initial claims at 220K/week are nowhere near recession levels of 350K+. This looks like normalization, not deterioration."
- "The yield curve has been inverted for 18 months—the longest inversion since the 1970s. Historically, recession follows 12-18 months after inversion. But Polymarket puts recession odds at just 25%, suggesting markets see a soft landing."

AVOID:
- Mere data recitation without insight ("Inflation was 2.65% in December")
- Weasel words ("appears to be", "may suggest", "could potentially")
- Clichés ("threading the needle", "remains to be seen", "time will tell")
- Being wishy-washy when the data is clear

The confidence level should be:
- "high" if data clearly answers the question
- "medium" if data is mixed or requires interpretation
- "low" if data is stale, conflicting, or doesn't directly answer the question

Return ONLY valid JSON, no markdown or explanation."""

    url = 'https://api.anthropic.com/v1/messages'
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 1200,
        'messages': [{'role': 'user', 'content': prompt}]
    }
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
    }

    try:
        req = Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
            content = result['content'][0]['text'].strip()

            # Parse JSON response
            analysis_dict = _extract_json(content)

            if analysis_dict:
                # Add data sources
                sources = analysis_dict.get('sources', [])
                if not sources:
                    sources = ["Data: BLS, BEA, Federal Reserve via FRED"]
                return EconomistAnalysis(
                    headline=analysis_dict.get('headline', 'Analysis unavailable'),
                    narrative=analysis_dict.get('narrative', []),
                    key_insight=analysis_dict.get('key_insight', ''),
                    sources=sources,
                    confidence=analysis_dict.get('confidence', 'medium'),
                )
    except Exception as e:
        print(f"[EconomistAnalysis] LLM error: {e}")

    return _generate_fallback_analysis(
        query=query,
        data_summary=data_summary,
        data_context=data_context,
        applicable_rules=applicable_rules,
        series_data=series_data or [],
    )


def _extract_json(text: str) -> Optional[Dict]:
    """Extract JSON from LLM response."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0]
    elif '```' in text:
        text = text.split('```')[1].split('```')[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _generate_fallback_analysis(
    query: str = "",
    data_summary: List[Dict] = None,
    data_context: Dict[str, Any] = None,
    applicable_rules: List[Dict[str, str]] = None,
    series_data: List[Tuple] = None,
) -> EconomistAnalysis:
    """
    Generate enhanced analysis when LLM is unavailable.

    This function integrates multiple analysis modules to produce high-quality
    output even without an LLM:
    - data_narrator: Provides contextual value descriptions with benchmarks
    - causal_reasoning: Explains WHY things are happening
    - historical_context: Compares to pre-pandemic, long-term averages, etc.
    - narrative_templates: Structures responses for different query types

    Args:
        query: The user's original question
        data_summary: Summarized data points
        data_context: Extracted economic metrics
        applicable_rules: Economic reasoning rules that apply
        series_data: Raw series data for detailed context

    Returns:
        EconomistAnalysis with rich, contextual content
    """
    data_summary = data_summary or []
    data_context = data_context or {}
    applicable_rules = applicable_rules or []
    series_data = series_data or []

    # Check if this is a comparison query (exactly 2 series)
    is_comparison = 'comparison_gap' in data_context

    if is_comparison:
        # Generate comparison-specific analysis (use existing specialized function)
        return _generate_comparison_fallback(data_summary, data_context, applicable_rules)

    # =========================================================================
    # STEP 1: Detect query type for appropriate narrative structure
    # =========================================================================
    query_type = 'general'
    series_ids = [s[0] for s in series_data] if series_data else []

    if HAS_ANALYSIS_GAPS:
        query_type = detect_query_type(query, series_ids)

    # =========================================================================
    # STEP 2: Build series_dict for data narrator (series_id -> data dict)
    # =========================================================================
    series_dict = {}
    for item in series_data:
        if len(item) >= 4:
            series_id, dates, values, info = item[0], item[1], item[2], item[3]
            if values:
                series_dict[series_id] = {
                    'values': values,
                    'dates': dates,
                    'info': info,
                }

    # =========================================================================
    # STEP 3: Get historical context for each series
    # =========================================================================
    historical_contexts = {}
    historical_descriptions = []

    if HAS_HISTORICAL_CONTEXT:
        for series_id, data in series_dict.items():
            if data.get('values'):
                current_value = data['values'][-1]
                ctx = get_historical_context(series_id, current_value)
                historical_contexts[series_id] = ctx

                # Generate prose description
                info = data.get('info', {})
                series_name = info.get('name', info.get('title', series_id))
                description = describe_historical_context(ctx, series_name)
                if description:
                    historical_descriptions.append(description)

    # =========================================================================
    # STEP 3b: Get series context for interpretive insights
    # =========================================================================
    series_interpretations = []
    recession_warnings = []
    forward_implications = []

    if HAS_SERIES_CONTEXT:
        for series_id, data in series_dict.items():
            if data.get('values'):
                current_value = data['values'][-1]

                # Get interpretation with benchmarks
                interpretation = interpret_value(series_id, current_value)
                if interpretation:
                    series_interpretations.append(interpretation)

                # Check for recession warnings
                recession_status = get_recession_status(series_id, current_value)
                if recession_status:
                    recession_warnings.append(recession_status)

                # Get forward implications
                implications = get_forward_implications(series_id)
                if implications:
                    forward_implications.extend(implications[:2])  # Max 2 per series

    # =========================================================================
    # STEP 4: Generate data-driven insights using narrator
    # =========================================================================
    data_insights = []

    if HAS_DATA_NARRATOR:
        for series_id, data in series_dict.items():
            if data.get('values'):
                current_value = data['values'][-1]
                insight = describe_value_with_context(
                    series_id, current_value, data, include_trend=True
                )
                if insight:
                    data_insights.append(insight)

    # =========================================================================
    # STEP 5: Build rich headline with context
    # =========================================================================
    headline_parts = []
    headline_context_parts = []

    if 'unemployment' in data_context:
        unemp = data_context['unemployment']
        headline_parts.append(f"unemployment at {unemp:.1f}%")

        # Add context if available
        if HAS_HISTORICAL_CONTEXT and 'UNRATE' in historical_contexts:
            ctx = historical_contexts['UNRATE']
            if ctx.pre_pandemic and ctx.pre_pandemic_change:
                headline_context_parts.append(
                    f"{ctx.pre_pandemic_change} from the pre-pandemic {ctx.pre_pandemic:.1f}%"
                )

    if 'core_inflation' in data_context:
        inflation = data_context['core_inflation']
        headline_parts.append(f"core inflation at {inflation:.1f}%")

        # Add Fed target context
        if inflation > 2.5:
            headline_context_parts.append("still above the Fed's 2% target")
        elif inflation <= 2.2:
            headline_context_parts.append("near the Fed's 2% target")

    if 'gdp_growth' in data_context:
        gdp = data_context['gdp_growth']
        headline_parts.append(f"GDP growing {gdp:.1f}%")

        # Add trend context
        if gdp > 2.5:
            headline_context_parts.append("above trend growth")
        elif gdp < 1.0:
            headline_context_parts.append("below trend, suggesting slowdown")

    # Build the headline
    if headline_parts:
        headline = f"Economic snapshot: {', '.join(headline_parts)}"
        if headline_context_parts:
            headline += f" - {headline_context_parts[0]}"
        headline += "."
    else:
        headline = "Economic data overview."

    # =========================================================================
    # STEP 6: Build narrative with causal reasoning
    # =========================================================================
    narrative = []

    # First, add series interpretations (from series_context - the "so what")
    for interp in series_interpretations[:2]:  # Max 2 interpretations
        if len(interp) > 200:
            interp = interp[:197] + "..."
        narrative.append(interp)

    # Add recession warnings prominently if any
    for warning in recession_warnings[:1]:  # Max 1 recession warning
        narrative.insert(0, warning)  # Put at start - most important

    # Add data insights (from narrator)
    for insight in data_insights[:2]:  # Max 2 data insights
        if insight not in ' '.join(narrative):  # Avoid duplicates
            if len(insight) > 200:
                insight = insight[:197] + "..."
            narrative.append(insight)

    # Add causal explanations for applicable rules
    for rule in applicable_rules[:2]:  # Max 2 rules
        interpretation = rule['interpretation']
        implication = rule['implication']

        # Build the rule text - hedging is already applied in the rule definitions
        # so we just need to format it properly
        rule_text = f"{interpretation.capitalize()}. {implication.capitalize()}."
        if rule_text not in ' '.join(narrative):  # Avoid duplicates
            narrative.append(rule_text)

    # Add historical context summary if we have it
    if historical_descriptions and len(narrative) < 4:
        # Find the most informative historical description
        for desc in historical_descriptions[:1]:
            if len(desc) > 50 and desc not in ' '.join(narrative):
                # Truncate if needed
                if len(desc) > 180:
                    desc = desc[:177] + "..."
                narrative.append(desc)

    # Add forward implications if we have room
    if forward_implications and len(narrative) < 5:
        unique_implications = list(set(forward_implications))[:2]
        if unique_implications:
            implications_text = f"This data tends to lead: {', '.join(unique_implications)}."
            narrative.append(implications_text)

    # Ensure we have at least one narrative point
    if not narrative:
        narrative = ["Economic data shows mixed signals across key indicators."]

    # =========================================================================
    # STEP 7: Generate key insight based on query type and data
    # =========================================================================
    key_insight = _generate_key_insight(query_type, data_context, applicable_rules)

    # =========================================================================
    # STEP 8: Generate risks and opportunities based on data
    # =========================================================================
    risks = _generate_risks(data_context, applicable_rules)
    opportunities = _generate_opportunities(data_context, applicable_rules)
    watch_items = _generate_watch_items(query_type, data_context)

    # =========================================================================
    # STEP 9: Determine confidence level
    # =========================================================================
    confidence = "medium"  # Enhanced fallback gets medium confidence

    # Lower confidence if we're missing key modules
    if not (HAS_HISTORICAL_CONTEXT and HAS_DATA_NARRATOR):
        confidence = "low"

    # Higher confidence if we have multiple data points and rules
    if len(series_data) >= 3 and len(applicable_rules) >= 2:
        confidence = "medium"

    # =========================================================================
    # STEP 10: Generate sources for data used
    # =========================================================================
    sources = []
    series_sources = set()
    for series_id, info in series_dict.items():
        # Identify data source
        if series_id.startswith(('LNS', 'CES', 'PAYEMS', 'UNRATE')):
            series_sources.add("BLS")
        elif series_id.startswith(('GDP', 'A191', 'PCE')):
            series_sources.add("BEA")
        elif series_id.startswith(('DGS', 'T10Y', 'FEDFUNDS', 'DFF')):
            series_sources.add("Federal Reserve")
        elif series_id.startswith('CPI'):
            series_sources.add("BLS")
        else:
            series_sources.add("FRED")

    if series_sources:
        sources.append(f"Data: {', '.join(sorted(series_sources))} via FRED")

    return EconomistAnalysis(
        headline=headline,
        narrative=narrative[:5],  # Cap at 5 bullets
        key_insight=key_insight,
        sources=sources,
        confidence=confidence,
    )


def _generate_key_insight(
    query_type: str,
    data_context: Dict[str, Any],
    applicable_rules: List[Dict[str, str]]
) -> str:
    """
    Generate the key insight based on query type and data.

    Focus on describing the data pattern clearly, not making predictions.
    """
    # Build data-focused insights that state what the numbers show

    # Labor market insights - describe the data
    if query_type == 'labor_market' or 'unemployment' in data_context:
        unemp = data_context.get('unemployment', 0)
        trend = data_context.get('unemployment_trend', '')
        if unemp < 4.0:
            return f"Unemployment at {unemp:.1f}% is below the 4% level typically considered full employment."
        elif unemp < 4.5:
            trend_text = f" and {trend}" if trend else ""
            return f"Unemployment at {unemp:.1f}%{trend_text} - near the Fed's estimate of full employment (~4.2%)."
        elif unemp < 5.5:
            return f"Unemployment at {unemp:.1f}% is above full employment levels, indicating labor market slack."
        else:
            return f"Unemployment at {unemp:.1f}% is elevated - well above the 4-5% range seen in healthy economies."

    # Inflation insights - describe the data
    if query_type == 'inflation' or 'core_inflation' in data_context:
        inflation = data_context.get('core_inflation', 0)
        trend = data_context.get('inflation_trend', '')
        target = 2.0
        if inflation < 2.3:
            return f"Core inflation at {inflation:.1f}% is near the Fed's 2% target."
        elif inflation < 3.0:
            trend_text = f" and {trend}" if trend else ""
            return f"Core inflation at {inflation:.1f}%{trend_text} - still {inflation - target:.1f}pp above the Fed's 2% target."
        elif inflation < 4.0:
            return f"Core inflation at {inflation:.1f}% remains {inflation - target:.1f} percentage points above the Fed's 2% target."
        else:
            return f"Core inflation at {inflation:.1f}% is {inflation - target:.1f}pp above target - more than double the Fed's goal."

    # GDP/growth insights - describe the data
    if query_type == 'gdp' or 'gdp_growth' in data_context:
        gdp = data_context.get('gdp_growth', 0)
        # Long-run trend growth is about 2%
        if gdp > 3.0:
            return f"GDP growth at {gdp:.1f}% is above the ~2% long-run trend."
        elif gdp > 2.0:
            return f"GDP growth at {gdp:.1f}% is near the ~2% long-run trend."
        elif gdp > 0:
            return f"GDP growth at {gdp:.1f}% is below the ~2% long-run trend."
        else:
            return f"GDP at {gdp:.1f}% indicates the economy is contracting."

    # Fed policy insights - describe the data
    if query_type == 'fed_policy' or 'fed_rate' in data_context:
        fed_rate = data_context.get('fed_rate', 0)
        inflation = data_context.get('core_inflation')
        if fed_rate and inflation:
            real_rate = fed_rate - inflation
            return f"Fed funds at {fed_rate:.2f}% minus {inflation:.1f}% inflation = {real_rate:.1f}% real rate."
        elif fed_rate:
            return f"Fed funds rate at {fed_rate:.2f}%."
        return "Fed funds rate data unavailable."

    # Recession insights - describe the indicators
    if query_type == 'recession':
        sahm = data_context.get('sahm_indicator')
        yield_curve = data_context.get('t10y2y')
        parts = []
        if sahm is not None:
            status = "triggered (≥0.5)" if sahm >= 0.5 else "not triggered (<0.5)"
            parts.append(f"Sahm Rule at {sahm:.2f} is {status}")
        if yield_curve is not None:
            status = "inverted" if yield_curve < 0 else "positive"
            parts.append(f"yield curve spread at {yield_curve:.2f}% is {status}")
        if parts:
            return "; ".join(parts) + "."
        return "Recession indicator data unavailable."

    # Default insight - summarize what we have
    summaries = []
    if 'unemployment' in data_context:
        summaries.append(f"unemployment {data_context['unemployment']:.1f}%")
    if 'gdp_growth' in data_context:
        summaries.append(f"GDP growth {data_context['gdp_growth']:.1f}%")
    if 'core_inflation' in data_context:
        summaries.append(f"core inflation {data_context['core_inflation']:.1f}%")

    if summaries:
        return f"Current readings: {', '.join(summaries)}."

    return "See charts below for detailed data."


def _generate_risks(
    data_context: Dict[str, Any],
    applicable_rules: List[Dict[str, str]]
) -> List[str]:
    """Generate contextual risk statements based on the data."""
    risks = []

    # Inflation risks
    if data_context.get('core_inflation', 0) > 2.5:
        risks.append("Sticky inflation could keep policy restrictive longer than expected.")

    # Labor market risks
    if data_context.get('unemployment', 0) > 4.5:
        risks.append("Rising unemployment could accelerate, tipping the economy into recession.")
    elif data_context.get('unemployment', 0) < 4.0:
        risks.append("Tight labor market could fuel wage-price spiral, complicating the Fed's task.")

    # Yield curve risks
    if data_context.get('t10y2y', 1) < 0:
        risks.append("Inverted yield curve historically precedes recessions by 12-18 months.")

    # GDP risks
    if data_context.get('gdp_growth', 2) < 1.5:
        risks.append("Below-trend growth raises recession probability.")

    # Default risks
    if not risks:
        risks = [
            "Policy uncertainty could affect economic outlook.",
            "Global economic conditions remain a source of risk.",
        ]

    return risks


def _generate_opportunities(
    data_context: Dict[str, Any],
    applicable_rules: List[Dict[str, str]]
) -> List[str]:
    """Generate contextual opportunity statements based on the data."""
    opportunities = []

    # Inflation progress
    if data_context.get('core_inflation', 5) < 3.0:
        opportunities.append("Progress on inflation opens the door for eventual policy easing.")

    # Strong labor market
    if data_context.get('unemployment', 6) < 4.5:
        opportunities.append("Solid job market supports consumer spending and economic resilience.")

    # GDP strength
    if data_context.get('gdp_growth', 0) > 2.0:
        opportunities.append("Above-trend growth suggests economy can weather restrictive policy.")

    # Soft landing
    if any('soft landing' in str(r.get('interpretation', '')).lower() for r in applicable_rules):
        opportunities.append("Soft landing scenario remains achievable based on current data.")

    # Default opportunities
    if not opportunities:
        opportunities = [
            "Economic resilience creates opportunities for sustained expansion.",
            "Data transparency enables better-informed decision-making.",
        ]

    return opportunities


def _generate_watch_items(query_type: str, data_context: Dict[str, Any]) -> List[str]:
    """Generate contextual watch items based on query type."""
    watch_items = []

    if query_type == 'labor_market':
        watch_items = [
            "Monthly payroll gains and initial jobless claims",
            "Wage growth vs productivity trends",
            "Labor force participation, especially prime-age workers",
        ]
    elif query_type == 'inflation':
        watch_items = [
            "Core PCE inflation (Fed's preferred measure)",
            "Shelter and services inflation stickiness",
            "Wage growth relative to productivity",
        ]
    elif query_type == 'fed_policy':
        watch_items = [
            "FOMC statements and dot plot projections",
            "Inflation data releases (CPI, PCE)",
            "Employment reports for signs of labor market cooling",
        ]
    elif query_type == 'recession':
        watch_items = [
            "Sahm Rule indicator (triggered at 0.5)",
            "Initial jobless claims trend",
            "Yield curve normalization vs further inversion",
        ]
    elif query_type == 'gdp':
        watch_items = [
            "Consumer spending and retail sales",
            "Business investment trends",
            "Trade balance and inventory changes",
        ]
    else:
        watch_items = [
            "Federal Reserve policy decisions",
            "Employment and inflation data releases",
            "Consumer spending and confidence indicators",
        ]

    return watch_items


def _generate_comparison_fallback(
    data_summary: List[Dict],
    data_context: Dict[str, Any],
    applicable_rules: List[Dict[str, str]]
) -> EconomistAnalysis:
    """
    Generate analysis specifically for comparison queries (2 series).

    This function creates meaningful narratives about the gap between two
    economic indicators, such as:
    - "Black unemployment at X% is Y percentage points above the overall rate of Z%"
    - "Wage growth at X% is trailing inflation at Y%, meaning real wages fell Z%"

    Args:
        data_summary: Summarized data points
        data_context: Extracted economic metrics with comparison data
        applicable_rules: Economic reasoning rules that apply

    Returns:
        EconomistAnalysis with comparison-focused content
    """
    # Extract comparison data
    names = data_context.get('comparison_names', ['Series 1', 'Series 2'])
    keys = data_context.get('comparison_series_keys', ['unknown', 'unknown'])
    values = data_context.get('comparison_values', [0, 0])
    gap = data_context.get('comparison_gap', 0)
    ratio = data_context.get('comparison_ratio')
    higher = data_context.get('comparison_higher', names[0])
    lower = data_context.get('comparison_lower', names[1])

    val1, val2 = values[0], values[1]
    name1, name2 = names[0], names[1]
    key1, key2 = keys[0], keys[1]

    # Determine the type of comparison for specialized narratives
    headline = ""
    narrative = []
    key_insight = ""
    risks = []
    opportunities = []
    watch_items = []

    # =========================================================================
    # UNEMPLOYMENT DISPARITY COMPARISONS
    # =========================================================================
    if key1 == 'black_unemployment' and key2 == 'unemployment':
        # Black unemployment vs overall
        gap_pp = val1 - val2
        headline = f"Black unemployment at {val1:.1f}% is {abs(gap_pp):.1f} percentage points {'above' if gap_pp > 0 else 'below'} the overall rate of {val2:.1f}%."
        narrative = [
            f"Black unemployment stands at {val1:.1f}%, compared to the overall unemployment rate of {val2:.1f}%.",
            f"This {abs(gap_pp):.1f} percentage point gap reflects persistent structural disparities in the labor market.",
            f"Black workers historically experience unemployment rates roughly 1.5-2x the overall rate.",
            f"The current ratio of {ratio:.2f}x {'indicates a typical disparity' if ratio and ratio > 1.4 else 'shows some narrowing of the gap'}." if ratio else "Gap analysis requires additional context."
        ]
        key_insight = f"Black workers face unemployment rates {ratio:.1f}x the national average, highlighting ongoing labor market inequality." if ratio else "Demographic unemployment disparities require policy attention."

    elif key1 == 'unemployment' and key2 == 'black_unemployment':
        # Overall vs Black unemployment (reversed order)
        gap_pp = val2 - val1
        headline = f"Black unemployment at {val2:.1f}% is {abs(gap_pp):.1f} percentage points above the overall rate of {val1:.1f}%."
        narrative = [
            f"The overall unemployment rate stands at {val1:.1f}%, while Black unemployment is {val2:.1f}%.",
            f"This {abs(gap_pp):.1f} percentage point gap reflects persistent structural disparities in the labor market.",
            f"Black workers historically experience unemployment rates roughly 1.5-2x the overall rate.",
            f"The current ratio of {1/ratio:.2f}x {'indicates a typical disparity' if ratio and 1/ratio > 1.4 else 'shows some narrowing of the gap'}." if ratio else "Gap analysis requires additional context."
        ]
        key_insight = f"Black workers face unemployment rates {1/ratio:.1f}x the national average, highlighting ongoing labor market inequality." if ratio else "Demographic unemployment disparities require policy attention."

    # =========================================================================
    # WAGE VS INFLATION COMPARISONS
    # =========================================================================
    elif (key1 == 'wage_growth' and key2 == 'headline_inflation') or (key1 == 'headline_inflation' and key2 == 'wage_growth'):
        # Wage growth vs inflation - use the COMPUTED growth rates from context, not raw values
        # The raw comparison_values are index/dollar levels; we need the YoY % growth rates
        # which were computed in build_data_context()
        wage_val = data_context.get('wage_growth', 0)
        inflation_val = data_context.get('headline_inflation', 0)

        real_wage_change = wage_val - inflation_val

        if real_wage_change < 0:
            headline = f"Wage growth at {wage_val:.1f}% is trailing inflation at {inflation_val:.1f}%, meaning real wages fell {abs(real_wage_change):.1f}%."
            narrative = [
                f"Nominal wages grew {wage_val:.1f}% year-over-year, but inflation ran at {inflation_val:.1f}%.",
                f"This means workers experienced a {abs(real_wage_change):.1f}% decline in real purchasing power.",
                "Wage growth lagging inflation erodes living standards and consumer spending power.",
                "This dynamic often leads to increased pressure for wage negotiations and potential labor unrest."
            ]
            key_insight = f"Workers' purchasing power declined by {abs(real_wage_change):.1f}% in real terms, putting pressure on household budgets."
        else:
            headline = f"Wage growth at {wage_val:.1f}% is outpacing inflation at {inflation_val:.1f}%, delivering {real_wage_change:.1f}% real wage gains."
            narrative = [
                f"Nominal wages grew {wage_val:.1f}% year-over-year, exceeding inflation of {inflation_val:.1f}%.",
                f"This translates to {real_wage_change:.1f}% growth in real purchasing power for workers.",
                "Positive real wage growth supports consumer spending and living standards.",
                "Sustained real wage gains without sparking inflation indicate healthy productivity growth."
            ]
            key_insight = f"Workers gained {real_wage_change:.1f}% in real purchasing power, supporting consumer spending and living standards."

    # =========================================================================
    # GENERIC COMPARISON (when no specific pattern matches)
    # =========================================================================
    else:
        # Generic comparison narrative
        if gap > 0:
            headline = f"{name1} at {val1:.1f} exceeds {name2} at {val2:.1f} by {abs(gap):.1f}."
        else:
            headline = f"{name2} at {val2:.1f} exceeds {name1} at {val1:.1f} by {abs(gap):.1f}."

        narrative = [
            f"{name1} currently stands at {val1:.1f}.",
            f"{name2} currently stands at {val2:.1f}.",
            f"The gap between these indicators is {abs(gap):.1f}.",
        ]

        if ratio and ratio != 1:
            ratio_display = ratio if ratio > 1 else 1/ratio
            higher_name = name1 if ratio > 1 else name2
            lower_name = name2 if ratio > 1 else name1
            narrative.append(f"{higher_name} is {ratio_display:.2f}x {lower_name}.")

        key_insight = f"The relationship between these indicators warrants monitoring as economic conditions evolve."

    # Add applicable rules to narrative
    for rule in applicable_rules[:2]:  # Add up to 2 rule-based insights
        rule_text = f"{rule['interpretation'].capitalize()}. {rule['implication'].capitalize()}."
        if rule_text not in narrative:
            narrative.append(rule_text)

    # Generate sources
    sources = ["Data: BLS via FRED"]

    return EconomistAnalysis(
        headline=headline,
        narrative=narrative[:5],  # Cap at 5 bullets
        key_insight=key_insight,
        sources=sources,
        confidence="medium",  # Higher confidence for comparison analysis since we have specific data
    )


# =============================================================================
# FORMATTED OUTPUT
# =============================================================================

def format_analysis_for_display(analysis: EconomistAnalysis) -> str:
    """
    Format the economist analysis for display.

    Args:
        analysis: EconomistAnalysis dataclass

    Returns:
        Formatted string for display
    """
    lines = []

    # Headline
    lines.append(analysis.headline)
    lines.append("")

    # Narrative bullets
    for point in analysis.narrative:
        lines.append(f"- {point}")

    lines.append("")

    # Key insight
    if analysis.key_insight:
        lines.append(f"KEY TAKEAWAY: {analysis.key_insight}")
        lines.append("")

    # Risks
    if analysis.risks:
        lines.append("RISKS TO WATCH:")
        for risk in analysis.risks:
            lines.append(f"  - {risk}")
        lines.append("")

    # Opportunities
    if analysis.opportunities:
        lines.append("OPPORTUNITIES:")
        for opp in analysis.opportunities:
            lines.append(f"  - {opp}")
        lines.append("")

    # Watch items
    if analysis.watch_items:
        lines.append("WHAT TO MONITOR:")
        for item in analysis.watch_items:
            lines.append(f"  - {item}")

    return "\n".join(lines)


def format_analysis_as_html(analysis: EconomistAnalysis) -> str:
    """
    Format the economist analysis as HTML for Streamlit display.

    Args:
        analysis: EconomistAnalysis dataclass

    Returns:
        HTML string for display
    """
    html_parts = []

    # Headline
    html_parts.append(f"<p style='font-size: 1.1em; font-weight: 600; margin-bottom: 12px;'>{analysis.headline}</p>")

    # Narrative bullets
    html_parts.append("<ul style='margin: 0 0 12px 0; padding-left: 20px;'>")
    for point in analysis.narrative:
        html_parts.append(f"<li style='margin-bottom: 6px;'>{point}</li>")
    html_parts.append("</ul>")

    # Key insight box - use single line to avoid whitespace issues in Streamlit
    if analysis.key_insight:
        html_parts.append(f"<div style='background: #FEF3C7; border-left: 4px solid #F59E0B; padding: 12px; margin: 12px 0; border-radius: 4px;'><strong>Key Takeaway:</strong> {analysis.key_insight}</div>")

    # Sources footer (if any claims need attribution)
    if analysis.sources:
        sources_text = ", ".join(analysis.sources)
        html_parts.append(f"<p style='margin-top: 12px; font-size: 0.8em; color: #6B7280; border-top: 1px solid #E5E7EB; padding-top: 8px;'><strong>Sources:</strong> {sources_text}</p>")

    # Join without newlines to avoid Streamlit rendering issues
    return "".join(html_parts)


# =============================================================================
# CONVENIENCE FUNCTION FOR APP INTEGRATION
# =============================================================================

def get_premium_analysis(
    query: str,
    series_data: List[Tuple],
    news_context: str = ""
) -> Tuple[EconomistAnalysis, str, str]:
    """
    Main entry point for premium economist analysis.

    Args:
        query: User's question
        series_data: List of (series_id, dates, values, info) tuples
        news_context: Optional news context

    Returns:
        Tuple of (EconomistAnalysis, plain_text_format, html_format)
    """
    analysis = generate_economist_analysis(
        query=query,
        series_data=series_data,
        news_context=news_context,
    )

    plain_text = format_analysis_for_display(analysis)
    html = format_analysis_as_html(analysis)

    return analysis, plain_text, html


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("PREMIUM ECONOMIST ANALYSIS - TEST")
    print("=" * 70)

    # Sample data mimicking what app.py provides
    sample_series_data = [
        ('UNRATE', ['2024-09-01', '2024-10-01', '2024-11-01', '2024-12-01'],
         [4.1, 4.0, 4.2, 4.1], {'name': 'Unemployment Rate', 'unit': '%'}),
        ('PAYEMS', ['2024-09-01', '2024-10-01', '2024-11-01', '2024-12-01'],
         [158000, 158200, 158400, 158600],
         {'name': 'Monthly Job Change', 'unit': 'Thousands', 'is_payroll_change': True,
          'original_values': [157000, 157500, 158000, 158200, 158400, 158600]}),
        ('A191RO1Q156NBEA', ['2024-03-01', '2024-06-01', '2024-09-01', '2024-12-01'],
         [2.2, 2.4, 2.5, 2.3], {'name': 'Real GDP (YoY)', 'unit': '%', 'is_yoy': True}),
        ('PCEPILFE', ['2024-01-01', '2024-02-01', '2024-03-01', '2024-04-01', '2024-05-01',
                      '2024-06-01', '2024-07-01', '2024-08-01', '2024-09-01', '2024-10-01',
                      '2024-11-01', '2024-12-01'],
         [120.0, 120.3, 120.6, 120.9, 121.2, 121.5, 121.8, 122.1, 122.4, 122.7, 123.0, 123.3],
         {'name': 'Core PCE Price Index', 'unit': 'Index'}),
    ]

    print("\n1. Testing data context extraction...")
    context = build_data_context(sample_series_data)
    print(f"Extracted context: {json.dumps(context, indent=2)}")

    print("\n2. Testing economic reasoning...")
    rules = apply_economic_reasoning(context)
    print(f"Applicable rules: {json.dumps(rules, indent=2)}")

    print("\n3. Testing full analysis generation...")
    analysis = generate_economist_analysis(
        query="How is the economy doing?",
        series_data=sample_series_data,
    )
    print(f"\nHeadline: {analysis.headline}")
    print(f"Confidence: {analysis.confidence}")
    print(f"\nNarrative:")
    for point in analysis.narrative:
        print(f"  - {point}")
    print(f"\nKey Insight: {analysis.key_insight}")
    print(f"\nRisks: {analysis.risks}")
    print(f"Opportunities: {analysis.opportunities}")

    print("\n4. Testing formatted output...")
    plain = format_analysis_for_display(analysis)
    print("\nPlain text format:")
    print(plain)

    # =========================================================================
    # COMPARISON TESTS
    # =========================================================================
    print("\n" + "=" * 70)
    print("COMPARISON ANALYSIS TESTS")
    print("=" * 70)

    # Test 5: Black unemployment vs overall unemployment
    print("\n5. Testing: Black unemployment vs overall unemployment...")
    comparison_data_unemployment = [
        ('LNS14000006', ['2024-09-01', '2024-10-01', '2024-11-01', '2024-12-01'],
         [5.8, 5.7, 5.9, 5.8], {'name': 'Black Unemployment Rate', 'unit': '%'}),
        ('UNRATE', ['2024-09-01', '2024-10-01', '2024-11-01', '2024-12-01'],
         [4.1, 4.0, 4.2, 4.1], {'name': 'Unemployment Rate', 'unit': '%'}),
    ]

    context_unemp = build_data_context(comparison_data_unemployment)
    print(f"Comparison context: {json.dumps(context_unemp, indent=2)}")

    # Check comparison metrics are present
    assert 'comparison_gap' in context_unemp, "comparison_gap should be present"
    assert 'comparison_ratio' in context_unemp, "comparison_ratio should be present"
    assert 'comparison_names' in context_unemp, "comparison_names should be present"
    print(f"  Gap: {context_unemp['comparison_gap']:.2f} pp")
    print(f"  Ratio: {context_unemp['comparison_ratio']:.2f}x")

    # Test the rules
    rules_unemp = apply_economic_reasoning(context_unemp)
    print(f"Applicable rules: {[r['rule'] for r in rules_unemp]}")
    assert any(r['rule'] == 'unemployment_disparity' for r in rules_unemp), "unemployment_disparity rule should trigger"

    # Test fallback analysis for this comparison
    analysis_unemp = _generate_fallback_analysis(data_summary=[], data_context=context_unemp, applicable_rules=rules_unemp)
    print(f"\nHeadline: {analysis_unemp.headline}")
    print(f"Key insight: {analysis_unemp.key_insight}")
    assert 'percentage point' in analysis_unemp.headline.lower(), "Headline should mention percentage points"

    # Test 6: Wage growth vs inflation (real wage erosion)
    print("\n6. Testing: Wage growth vs inflation (real wage erosion)...")
    # 12 months of data needed for YoY calculation
    dates_12mo = [f'2024-{m:02d}-01' for m in range(1, 13)]
    # CPI index rising 3.5% over the year
    cpi_values = [300.0 + (i * 0.875) for i in range(12)]  # ~3.5% YoY
    # Wages rising only 2.5% over the year
    wage_values = [30.0 + (i * 0.0625) for i in range(12)]  # ~2.5% YoY

    comparison_data_wages = [
        ('CES0500000003', dates_12mo, wage_values,
         {'name': 'Average Hourly Earnings', 'unit': 'Dollars'}),
        ('CPIAUCSL', dates_12mo, cpi_values,
         {'name': 'Consumer Price Index for All Urban Consumers', 'unit': 'Index'}),
    ]

    context_wages = build_data_context(comparison_data_wages)
    print(f"  Wage growth: {context_wages.get('wage_growth', 'N/A'):.2f}%")
    print(f"  Headline inflation: {context_wages.get('headline_inflation', 'N/A'):.2f}%")
    print(f"  Comparison gap: {context_wages.get('comparison_gap', 'N/A')}")

    # Test the rules
    rules_wages = apply_economic_reasoning(context_wages)
    print(f"Applicable rules: {[r['rule'] for r in rules_wages]}")
    assert any(r['rule'] == 'real_wage_erosion' for r in rules_wages), "real_wage_erosion rule should trigger"

    # Test fallback analysis
    analysis_wages = _generate_fallback_analysis(data_summary=[], data_context=context_wages, applicable_rules=rules_wages)
    print(f"\nHeadline: {analysis_wages.headline}")
    print(f"Key insight: {analysis_wages.key_insight}")
    assert 'trailing' in analysis_wages.headline.lower() or 'fell' in analysis_wages.headline.lower() or 'declined' in analysis_wages.headline.lower(), "Headline should indicate wage erosion"

    # Test 7: Wage growth vs inflation (real wage gains)
    print("\n7. Testing: Wage growth vs inflation (real wage gains)...")
    # CPI index rising 2.0% over the year
    cpi_values_low = [300.0 + (i * 0.5) for i in range(12)]  # ~2.0% YoY
    # Wages rising 4.0% over the year
    wage_values_high = [30.0 + (i * 0.1) for i in range(12)]  # ~4.0% YoY

    comparison_data_gains = [
        ('CES0500000003', dates_12mo, wage_values_high,
         {'name': 'Average Hourly Earnings', 'unit': 'Dollars'}),
        ('CPIAUCSL', dates_12mo, cpi_values_low,
         {'name': 'Consumer Price Index for All Urban Consumers', 'unit': 'Index'}),
    ]

    context_gains = build_data_context(comparison_data_gains)
    print(f"  Wage growth: {context_gains.get('wage_growth', 'N/A'):.2f}%")
    print(f"  Headline inflation: {context_gains.get('headline_inflation', 'N/A'):.2f}%")

    rules_gains = apply_economic_reasoning(context_gains)
    print(f"Applicable rules: {[r['rule'] for r in rules_gains]}")
    assert any(r['rule'] == 'real_wage_gains' for r in rules_gains), "real_wage_gains rule should trigger"

    analysis_gains = _generate_fallback_analysis(data_summary=[], data_context=context_gains, applicable_rules=rules_gains)
    print(f"\nHeadline: {analysis_gains.headline}")
    assert 'outpacing' in analysis_gains.headline.lower() or 'gains' in analysis_gains.headline.lower(), "Headline should indicate wage gains"

    # Test 8: Generic comparison (unknown series)
    print("\n8. Testing: Generic comparison (unknown series)...")
    comparison_data_generic = [
        ('CUSTOM1', ['2024-12-01'], [100.5], {'name': 'Custom Indicator A', 'unit': 'Index'}),
        ('CUSTOM2', ['2024-12-01'], [85.2], {'name': 'Custom Indicator B', 'unit': 'Index'}),
    ]

    context_generic = build_data_context(comparison_data_generic)
    print(f"  Comparison gap: {context_generic.get('comparison_gap', 'N/A'):.2f}")
    print(f"  Comparison ratio: {context_generic.get('comparison_ratio', 'N/A'):.2f}")

    analysis_generic = _generate_fallback_analysis(data_summary=[], data_context=context_generic, applicable_rules=[])
    print(f"\nHeadline: {analysis_generic.headline}")
    assert 'Custom Indicator' in analysis_generic.headline, "Headline should use series names"

    # =========================================================================
    # MISSING DATA TESTS - Rules should NOT fire when data is missing
    # =========================================================================
    print("\n" + "=" * 70)
    print("MISSING DATA TESTS")
    print("=" * 70)

    # Test 9: Empty data should trigger NO rules
    print("\n9. Testing: Empty data should trigger NO rules...")
    empty_context = {}
    empty_rules = apply_economic_reasoning(empty_context)
    print(f"   Rules triggered with empty data: {[r['rule'] for r in empty_rules]}")
    assert len(empty_rules) == 0, "No rules should fire with empty data"
    print("   PASSED: No rules fired with empty data")

    # Test 10: Partial data should only trigger relevant rules, not defaults
    print("\n10. Testing: Partial data should not trigger default-based rules...")

    # Only unemployment present - should NOT trigger inflation_target
    # (which would fire if core_inflation defaulted to 0)
    partial_context = {'unemployment': 4.0}
    partial_rules = apply_economic_reasoning(partial_context)
    rule_names = [r['rule'] for r in partial_rules]
    print(f"    Rules with only unemployment={partial_context['unemployment']}: {rule_names}")

    # inflation_target should NOT fire (no core_inflation data)
    assert 'inflation_target' not in rule_names, "inflation_target should NOT fire without core_inflation data"
    # growth_weak should NOT fire (no gdp_growth data)
    assert 'growth_weak' not in rule_names, "growth_weak should NOT fire without gdp_growth data"
    print("    PASSED: No false positive rules fired")

    # Test 11: Verify specific rule does NOT fire with missing data
    print("\n11. Testing: inflation_target should NOT fire when core_inflation is missing...")

    # Old buggy behavior: data.get('core_inflation', 0) <= 2.5 returns True because 0 <= 2.5
    # Fixed behavior: 'core_inflation' in data and data['core_inflation'] <= 2.5 returns False
    no_inflation_context = {'unemployment': 4.0, 'gdp_growth': 2.0}  # No core_inflation
    no_inflation_rules = apply_economic_reasoning(no_inflation_context)
    rule_names = [r['rule'] for r in no_inflation_rules]
    print(f"    Rules without core_inflation: {rule_names}")
    assert 'inflation_target' not in rule_names, "inflation_target should NOT fire without core_inflation"
    assert 'growth_weak' not in rule_names, "growth_weak should NOT fire (gdp_growth=2.0 > 1.0)"
    print("    PASSED: inflation_target did not fire without data")

    # Test 12: Verify rules DO fire when data IS present
    print("\n12. Testing: Rules should fire when correct data IS present...")

    full_context = {
        'unemployment': 4.0,
        'core_inflation': 2.3,  # Below 2.5 threshold
        'gdp_growth': 2.8,      # Above 2.5 threshold
    }
    full_rules = apply_economic_reasoning(full_context)
    rule_names = [r['rule'] for r in full_rules]
    print(f"    Rules with full context: {rule_names}")
    assert 'inflation_target' in rule_names, "inflation_target SHOULD fire (core_inflation=2.3 <= 2.5)"
    assert 'growth_strong' in rule_names, "growth_strong SHOULD fire (gdp_growth=2.8 > 2.5)"
    print("    PASSED: Rules correctly fired when data present")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETE - MISSING DATA BUG FIX VERIFIED")
    print("=" * 70)
