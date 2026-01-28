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
    resilient expansion despite higher rates."
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class IndicatorSnapshot:
    """
    A snapshot of a single economic indicator with context.
    """
    series_id: str
    name: str
    value: float
    unit: str
    date: str
    yoy_change: Optional[float] = None
    mom_change: Optional[float] = None
    trend: Optional[str] = None  # 'rising', 'falling', 'stable'
    category: Optional[str] = None  # 'labor', 'inflation', 'growth', etc.


@dataclass
class EconomistAnalysis:
    """
    The final economist analysis output.
    """
    headline: str
    narrative: List[str]
    key_insight: str
    confidence: str = "medium"  # low, medium, high
    risks: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)


# =============================================================================
# INDICATOR CATEGORIZATION
# =============================================================================

SERIES_CATEGORIES = {
    # Labor Market
    'UNRATE': 'labor', 'PAYEMS': 'labor', 'ICSA': 'labor',
    'JTSJOL': 'labor', 'JTSQUR': 'labor', 'CES0500000003': 'labor',
    'LNS12300060': 'labor', 'CIVPART': 'labor',

    # Inflation
    'CPIAUCSL': 'inflation', 'CPILFESL': 'inflation',
    'PCEPI': 'inflation', 'PCEPILFE': 'inflation',
    'CUSR0000SEHA': 'inflation', 'GASREGW': 'inflation',

    # Growth
    'GDPC1': 'growth', 'A191RL1Q225SBEA': 'growth',
    'INDPRO': 'growth', 'RSXFS': 'growth', 'PCE': 'growth',

    # Interest Rates
    'FEDFUNDS': 'rates', 'DGS10': 'rates', 'DGS2': 'rates',
    'T10Y2Y': 'rates', 'MORTGAGE30US': 'rates',

    # Housing
    'CSUSHPINSA': 'housing', 'HOUST': 'housing',
    'PERMIT': 'housing', 'EXHOSLUSM495S': 'housing',

    # Consumer
    'UMCSENT': 'consumer', 'PSAVERT': 'consumer',
    'DSPIC96': 'consumer',
}


def categorize_indicator(series_id: str, name: str = "") -> str:
    """Determine the economic category of an indicator."""
    if series_id in SERIES_CATEGORIES:
        return SERIES_CATEGORIES[series_id]

    name_lower = name.lower()
    if any(t in name_lower for t in ['unemploy', 'payroll', 'job', 'employ', 'labor', 'wage']):
        return 'labor'
    elif any(t in name_lower for t in ['inflation', 'cpi', 'pce', 'price']):
        return 'inflation'
    elif any(t in name_lower for t in ['gdp', 'growth', 'output', 'production']):
        return 'growth'
    elif any(t in name_lower for t in ['rate', 'treasury', 'yield', 'mortgage']):
        return 'rates'
    elif any(t in name_lower for t in ['home', 'house', 'housing', 'rent']):
        return 'housing'
    elif any(t in name_lower for t in ['consumer', 'sentiment', 'saving']):
        return 'consumer'

    return 'other'


# =============================================================================
# ECONOMIC REASONING RULES
# =============================================================================

# These rules encode economic relationships for coherent narratives.
# Pattern: Check that required keys EXIST before comparing values.

ECONOMIC_RELATIONSHIPS = {
    # Labor market conditions
    'labor_tight': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] < 4.5 and
            'job_openings_per_unemployed' in data and data['job_openings_per_unemployed'] > 1.0
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% with {data['job_openings_per_unemployed']:.1f} job openings per unemployed worker",
        'implication': "tight labor market with more openings than job seekers",
    },
    'labor_cooling': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] > 4.0 and
            'unemployment_trend' in data and data['unemployment_trend'] == 'rising'
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% and rising",
        'implication': "labor market showing signs of cooling",
    },
    'labor_soft': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] > 5.0
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% - above the 4-5% range of recent years",
        'implication': "elevated unemployment indicates slack in the labor market",
    },

    # Inflation conditions
    'inflation_hot': {
        'conditions': lambda data: (
            'core_inflation' in data and data['core_inflation'] > 3.5
        ),
        'interpretation': lambda data: f"core inflation at {data['core_inflation']:.1f}% - {data['core_inflation'] - 2:.1f}pp above the Fed's 2% target",
        'implication': "inflation running hot, likely keeping Fed restrictive",
    },
    'inflation_progress': {
        'conditions': lambda data: (
            'core_inflation' in data and 2.5 < data['core_inflation'] <= 3.5 and
            'inflation_trend' in data and data['inflation_trend'] == 'falling'
        ),
        'interpretation': lambda data: f"core inflation at {data['core_inflation']:.1f}% and falling",
        'implication': "inflation making progress toward the 2% target",
    },
    'inflation_target': {
        'conditions': lambda data: (
            'core_inflation' in data and data['core_inflation'] <= 2.5
        ),
        'interpretation': lambda data: f"core inflation at {data['core_inflation']:.1f}% - near the Fed's 2% target",
        'implication': "inflation at or near target, giving Fed room to ease",
    },

    # Growth conditions
    'growth_strong': {
        'conditions': lambda data: (
            'gdp_growth' in data and data['gdp_growth'] > 2.5
        ),
        'interpretation': lambda data: f"GDP growth at {data['gdp_growth']:.1f}% - above the ~2% long-run trend",
        'implication': "economy expanding faster than typical",
    },
    'growth_moderate': {
        'conditions': lambda data: (
            'gdp_growth' in data and 1.0 < data['gdp_growth'] <= 2.5
        ),
        'interpretation': lambda data: f"GDP growth at {data['gdp_growth']:.1f}% - near the ~2% long-run trend",
        'implication': "sustainable growth pace",
    },
    'growth_weak': {
        'conditions': lambda data: (
            'gdp_growth' in data and data['gdp_growth'] <= 1.0
        ),
        'interpretation': lambda data: f"GDP growth at {data['gdp_growth']:.1f}% - below the ~2% long-run trend",
        'implication': "growth slower than typical, potential recession risk",
    },

    # Combined patterns
    'goldilocks': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] < 4.5 and
            'core_inflation' in data and data['core_inflation'] < 3.0 and
            'gdp_growth' in data and data['gdp_growth'] > 1.5
        ),
        'interpretation': lambda data: f"unemployment {data['unemployment']:.1f}%, inflation {data['core_inflation']:.1f}%, GDP {data['gdp_growth']:.1f}%",
        'implication': "goldilocks scenario: low unemployment + moderating inflation + positive growth",
    },
    'stagflation_risk': {
        'conditions': lambda data: (
            'unemployment' in data and data['unemployment'] > 4.5 and
            'core_inflation' in data and data['core_inflation'] > 3.5
        ),
        'interpretation': lambda data: f"unemployment at {data['unemployment']:.1f}% while inflation at {data['core_inflation']:.1f}%",
        'implication': "stagflation risk: both unemployment and inflation elevated",
    },

    # Yield curve
    'yield_curve_inverted': {
        'conditions': lambda data: (
            'yield_spread_10y2y' in data and data['yield_spread_10y2y'] < 0
        ),
        'interpretation': lambda data: f"10Y-2Y yield spread at {data['yield_spread_10y2y']:.2f}%",
        'implication': "inverted yield curve - historically a recession warning signal",
    },
    'yield_curve_normalizing': {
        'conditions': lambda data: (
            'yield_spread_10y2y' in data and 0 < data['yield_spread_10y2y'] < 0.5 and
            'yield_trend' in data and data['yield_trend'] == 'rising'
        ),
        'interpretation': lambda data: f"yield curve normalizing with {data['yield_spread_10y2y']:.2f}% spread",
        'implication': "yield curve un-inverting - sometimes precedes recession",
    },
}


def extract_data_context(series_data: List[dict]) -> Dict[str, Any]:
    """
    Extract key values from series data for economic reasoning.

    Args:
        series_data: List of dicts with 'series_id', 'values', 'info', 'analytics'

    Returns:
        Dict with normalized key values for ECONOMIC_RELATIONSHIPS checks
    """
    context = {}

    for data in series_data:
        series_id = data.get('series_id', '')
        analytics = data.get('analytics', {})
        latest = analytics.get('latest_value')
        yoy = analytics.get('yoy', {})

        if series_id == 'UNRATE':
            context['unemployment'] = latest
            if yoy.get('change', 0) > 0.2:
                context['unemployment_trend'] = 'rising'
            elif yoy.get('change', 0) < -0.2:
                context['unemployment_trend'] = 'falling'
            else:
                context['unemployment_trend'] = 'stable'

        elif series_id in ['CPILFESL', 'PCEPILFE']:
            if yoy.get('change_pct') is not None:
                context['core_inflation'] = yoy['change_pct']
                if yoy['change_pct'] < yoy.get('prior_pct', yoy['change_pct']):
                    context['inflation_trend'] = 'falling'
                else:
                    context['inflation_trend'] = 'rising'

        elif series_id in ['CPIAUCSL', 'PCEPI']:
            if yoy.get('change_pct') is not None and 'core_inflation' not in context:
                context['headline_inflation'] = yoy['change_pct']

        elif series_id == 'A191RL1Q225SBEA':
            context['gdp_growth'] = latest

        elif series_id == 'GDPC1':
            if yoy.get('change_pct') is not None:
                context['gdp_growth'] = yoy['change_pct']

        elif series_id == 'JTSJOL':
            context['job_openings'] = latest
            # Calculate openings per unemployed if we have unemployment
            if 'unemployment' in context and context['unemployment'] > 0:
                unemployed_count = 6.0  # Approximate millions
                context['job_openings_per_unemployed'] = latest / 1000 / unemployed_count

        elif series_id == 'T10Y2Y':
            context['yield_spread_10y2y'] = latest
            if yoy.get('change', 0) > 0:
                context['yield_trend'] = 'rising'
            else:
                context['yield_trend'] = 'falling'

    return context


def apply_economic_reasoning(context: Dict[str, Any]) -> List[Dict]:
    """
    Apply economic reasoning rules to the data context.

    Returns list of triggered rules with their interpretations.
    """
    triggered = []

    for rule_name, rule in ECONOMIC_RELATIONSHIPS.items():
        try:
            if rule['conditions'](context):
                triggered.append({
                    'rule': rule_name,
                    'interpretation': rule['interpretation'](context),
                    'implication': rule['implication'],
                })
        except Exception:
            continue

    return triggered


def generate_economist_analysis(
    query: str,
    series_data: List[dict],
    summary: str = ""
) -> Optional[EconomistAnalysis]:
    """
    Generate economist-quality analysis connecting multiple indicators.

    Args:
        query: The user's question
        series_data: List of data dicts with analytics
        summary: Optional AI-generated summary to enhance

    Returns:
        EconomistAnalysis with headline, narrative, insights
    """
    # Extract data context for reasoning
    context = extract_data_context(series_data)

    if not context:
        return None

    # Apply economic reasoning rules
    triggered_rules = apply_economic_reasoning(context)

    if not triggered_rules:
        return None

    # Build narrative from triggered rules
    narrative = []
    for rule in triggered_rules:
        narrative.append(f"{rule['interpretation']} - {rule['implication']}")

    # Generate headline from primary rule
    primary = triggered_rules[0]
    headline = primary['interpretation']

    # Extract key insight
    key_insight = triggered_rules[-1]['implication'] if len(triggered_rules) > 1 else primary['implication']

    # Determine risks and opportunities based on triggered rules
    risks = []
    opportunities = []

    rule_names = [r['rule'] for r in triggered_rules]

    if 'stagflation_risk' in rule_names:
        risks.append("Stagflation risk if both unemployment and inflation remain elevated")
    if 'yield_curve_inverted' in rule_names:
        risks.append("Inverted yield curve has historically preceded recessions")
    if 'inflation_hot' in rule_names:
        risks.append("Elevated inflation may keep Fed restrictive longer")
    if 'growth_weak' in rule_names:
        risks.append("Weak growth increases recession probability")

    if 'goldilocks' in rule_names:
        opportunities.append("Favorable conditions for continued expansion")
    if 'inflation_progress' in rule_names:
        opportunities.append("Falling inflation may allow Fed to ease")
    if 'growth_strong' in rule_names:
        opportunities.append("Strong growth supports earnings and employment")
    if 'yield_curve_normalizing' in rule_names:
        opportunities.append("Normalizing yield curve may signal easing ahead")

    # Determine confidence level
    if len(triggered_rules) >= 3:
        confidence = 'high'
    elif len(triggered_rules) >= 2:
        confidence = 'medium'
    else:
        confidence = 'low'

    return EconomistAnalysis(
        headline=headline,
        narrative=narrative,
        key_insight=key_insight,
        confidence=confidence,
        risks=risks,
        opportunities=opportunities,
    )


# Quick test
if __name__ == "__main__":
    # Test with sample data
    test_data = [
        {
            'series_id': 'UNRATE',
            'analytics': {'latest_value': 4.1, 'yoy': {'change': -0.3}},
        },
        {
            'series_id': 'CPILFESL',
            'analytics': {'latest_value': 315, 'yoy': {'change_pct': 3.2}},
        },
        {
            'series_id': 'A191RL1Q225SBEA',
            'analytics': {'latest_value': 2.8},
        },
    ]

    context = extract_data_context(test_data)
    print(f"Context: {context}")

    rules = apply_economic_reasoning(context)
    print(f"\nTriggered rules: {rules}")

    analysis = generate_economist_analysis("How is the economy?", test_data)
    if analysis:
        print(f"\nHeadline: {analysis.headline}")
        print(f"Narrative: {analysis.narrative}")
        print(f"Key insight: {analysis.key_insight}")
        print(f"Risks: {analysis.risks}")
        print(f"Opportunities: {analysis.opportunities}")
