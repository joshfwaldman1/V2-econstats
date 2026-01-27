"""
Analysis Gaps Detection and Filling Module.

This is the "what are we missing?" layer that runs AFTER the main analysis.
It identifies gaps in the analysis based on query type and required context,
then generates additional context to fill those gaps.

The key insight is that different types of economic queries require different
sets of data to be properly answered. For example:
- A labor market query needs unemployment, job gains, and trend data at minimum
- An inflation query needs headline/core levels and year-over-year trends
- A recession query needs leading indicators like yield curve and Sahm Rule

This module:
1. detect_query_type() - Figures out what kind of analysis this is
2. identify_gaps() - Checks what's missing based on REQUIRED_CONTEXT
3. fill_gaps() - Generates text to add the missing context
4. fact_check_analysis() - Verifies numbers match data
5. tone_check_analysis() - Ensures tone matches the data sentiment

Usage:
    from core.analysis_gaps import identify_gaps, fill_gaps, fact_check_analysis

    # After generating main analysis
    gaps = identify_gaps(query, series_data, current_analysis)
    if gaps['gap_severity'] != 'minor':
        filled = fill_gaps(gaps, series_data, query)
        analysis_text += filled['additional_context']
"""

import json
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from urllib.request import urlopen, Request


# =============================================================================
# API KEYS
# =============================================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")


# =============================================================================
# REQUIRED CONTEXT BY QUERY TYPE
#
# These define what data elements should be present for a complete analysis.
# - must_have: Critical elements - analysis is incomplete without these
# - should_have: Important elements - analysis is weak without these
# - nice_to_have: Additional context - enriches the analysis
# =============================================================================

REQUIRED_CONTEXT = {
    'labor_market': {
        'must_have': ['unemployment_level', 'job_gains', 'unemployment_trend'],
        'should_have': ['prime_age_epop', 'initial_claims', 'quits_rate', 'job_openings'],
        'nice_to_have': ['wage_growth', 'hours_worked'],
    },
    'inflation': {
        'must_have': ['headline_or_core_level', 'yoy_trend'],
        'should_have': ['shelter_component', 'core_vs_headline_gap', 'fed_target_distance'],
        'nice_to_have': ['services_vs_goods', 'real_wages'],
    },
    'recession': {
        'must_have': ['sahm_rule', 'yield_curve', 'unemployment_trend'],
        'should_have': ['consumer_sentiment', 'initial_claims', 'leading_indicators'],
        'nice_to_have': ['polymarket_odds', 'credit_spreads'],
    },
    'fed_policy': {
        'must_have': ['current_rate', 'inflation_vs_target'],
        'should_have': ['real_rate', 'dot_plot_path', 'labor_market_conditions'],
        'nice_to_have': ['market_expectations', 'financial_conditions'],
    },
    'comparison': {
        'must_have': ['both_values', 'gap_or_ratio'],
        'should_have': ['historical_gap', 'trend_of_gap'],
        'nice_to_have': ['explanation_of_gap'],
    },
    'demographic': {
        'must_have': ['demographic_value', 'overall_value', 'gap'],
        'should_have': ['historical_context', 'lfpr'],
        'nice_to_have': ['structural_factors'],
    },
    'housing': {
        'must_have': ['price_trend', 'mortgage_rate'],
        'should_have': ['affordability', 'inventory', 'sales_volume'],
        'nice_to_have': ['regional_variation', 'rent_vs_buy'],
    },
    'gdp': {
        'must_have': ['growth_rate', 'growth_direction'],
        'should_have': ['consumer_component', 'business_investment', 'trend_vs_potential'],
        'nice_to_have': ['inventory_effects', 'trade_contribution'],
    },
    'general': {
        'must_have': ['primary_value', 'trend_direction'],
        'should_have': ['historical_context', 'related_indicators'],
        'nice_to_have': ['forward_outlook'],
    },
}


# =============================================================================
# SERIES TO CONTEXT ELEMENT MAPPINGS
#
# Maps FRED series IDs to the context elements they provide
# =============================================================================

SERIES_TO_CONTEXT = {
    # Labor market indicators
    'UNRATE': ['unemployment_level', 'unemployment_trend', 'labor_market_conditions'],
    'U6RATE': ['unemployment_level', 'broader_unemployment'],
    'PAYEMS': ['job_gains', 'employment_level'],
    'ICSA': ['initial_claims', 'layoff_indicator', 'leading_indicators'],
    'JTSJOL': ['job_openings', 'labor_demand'],
    'JTSQUR': ['quits_rate', 'labor_confidence'],
    'LNS12300060': ['prime_age_epop', 'employment_rate'],
    'CES0500000003': ['wage_growth', 'earnings'],
    'AHETPI': ['wage_growth', 'hourly_earnings'],
    'CIVPART': ['lfpr', 'labor_force_participation'],

    # Inflation indicators
    'CPIAUCSL': ['headline_or_core_level', 'yoy_trend', 'inflation_vs_target'],
    'CPILFESL': ['headline_or_core_level', 'core_inflation', 'yoy_trend'],
    'PCEPILFE': ['headline_or_core_level', 'core_inflation', 'fed_target_distance'],
    'PCEPI': ['headline_or_core_level', 'headline_inflation'],
    'CUSR0000SAH1': ['shelter_component', 'housing_inflation'],
    'CUSR0000SEHA': ['shelter_component', 'rent_inflation'],

    # GDP and growth
    'GDPC1': ['growth_rate', 'gdp_level'],
    'A191RO1Q156NBEA': ['growth_rate', 'yoy_growth'],
    'A191RL1Q225SBEA': ['growth_rate', 'quarterly_growth'],
    'PCE': ['consumer_component', 'consumer_spending'],
    'PNFI': ['business_investment', 'nonresidential_investment'],

    # Fed and rates
    'FEDFUNDS': ['current_rate', 'policy_rate'],
    'DGS10': ['long_rate', 'treasury_yield'],
    'DGS2': ['short_rate', 'treasury_yield'],
    'T10Y2Y': ['yield_curve', 'recession_signal'],
    'MORTGAGE30US': ['mortgage_rate', 'housing_costs'],

    # Recession indicators
    'SAHMREALTIME': ['sahm_rule', 'recession_signal'],
    'UMCSENT': ['consumer_sentiment', 'consumer_confidence'],
    'USSLIND': ['leading_indicators', 'lei'],
    'BAA10Y': ['credit_spreads', 'financial_stress'],
    'NFCI': ['financial_conditions', 'credit_conditions'],

    # Housing
    'CSUSHPINSA': ['price_trend', 'home_prices'],
    'HOUST': ['inventory', 'housing_starts'],
    'EXHOSLUSM495S': ['sales_volume', 'existing_home_sales'],
    'HSN1F': ['sales_volume', 'new_home_sales'],
    'MSPUS': ['price_trend', 'median_price'],

    # Demographics
    'LNS14000006': ['demographic_value', 'black_unemployment'],
    'LNS14000009': ['demographic_value', 'hispanic_unemployment'],
    'LNS14000002': ['demographic_value', 'women_unemployment'],
    'LNS14000003': ['overall_value', 'white_unemployment'],
}


# =============================================================================
# QUERY TYPE DETECTION
# =============================================================================

# Keywords that indicate query type
QUERY_TYPE_KEYWORDS = {
    'labor_market': [
        'job', 'jobs', 'employment', 'unemployment', 'payroll', 'payrolls',
        'hiring', 'layoff', 'layoffs', 'workers', 'labor', 'labour', 'workforce',
        'claims', 'openings', 'wage', 'wages', 'earnings', 'quits', 'lfpr'
    ],
    'inflation': [
        'inflation', 'cpi', 'pce', 'prices', 'price', 'deflation',
        'shelter', 'rent', 'rents', 'core inflation', 'headline'
    ],
    'recession': [
        'recession', 'downturn', 'contraction', 'soft landing', 'hard landing',
        'sahm', 'yield curve', 'inverted', 'slowdown', 'are we in'
    ],
    'fed_policy': [
        'fed', 'federal reserve', 'fomc', 'rate cut', 'rate hike', 'powell',
        'monetary policy', 'dot plot', 'tightening', 'easing', 'hawkish', 'dovish'
    ],
    'housing': [
        'housing', 'home prices', 'house prices', 'mortgage', 'real estate',
        'housing market', 'affordability', 'rent vs buy', 'homeowner'
    ],
    'gdp': [
        'gdp', 'growth', 'economic growth', 'output', 'economy growing',
        'expansion', 'gross domestic'
    ],
    'comparison': [
        'vs', 'versus', 'compared to', 'compare', 'than', 'against',
        'relative to', 'between', 'and'  # Note: 'and' only with context
    ],
    'demographic': [
        'black', 'african american', 'hispanic', 'latino', 'latina',
        'women', 'men', 'female', 'male', 'youth', 'older workers',
        'immigrant', 'asian', 'veteran'
    ],
}


def detect_query_type(query: str, series_ids: List[str]) -> str:
    """
    Detect what type of analysis this is based on the query and series.

    This function examines both the query text and the series IDs to determine
    the primary analytical focus. The query type determines what context
    elements are required for a complete analysis.

    Args:
        query: The user's original query string
        series_ids: List of FRED series IDs being analyzed

    Returns:
        Query type string: 'labor_market', 'inflation', 'recession', 'fed_policy',
        'housing', 'gdp', 'comparison', 'demographic', or 'general'

    Examples:
        >>> detect_query_type("How is the job market?", ["UNRATE", "PAYEMS"])
        'labor_market'
        >>> detect_query_type("US vs Eurozone GDP", ["GDPC1"])
        'comparison'
        >>> detect_query_type("Black unemployment rate", ["LNS14000006"])
        'demographic'
    """
    query_lower = query.lower()

    # Check for comparison queries first (they can overlap with other types)
    comparison_keywords = ['vs', 'versus', 'compared to', 'compare ']
    if any(kw in query_lower for kw in comparison_keywords):
        return 'comparison'

    # Check for demographic queries (specific groups)
    demographic_indicators = [
        'LNS14000006', 'LNS14000009', 'LNS14000002', 'LNS14000003',
        'LNS14000012', 'LNS14000004'  # Black, Hispanic, Women, White, Youth, Asian
    ]
    if any(s in series_ids for s in demographic_indicators):
        return 'demographic'

    for demographic_term in QUERY_TYPE_KEYWORDS['demographic']:
        if demographic_term in query_lower:
            return 'demographic'

    # Score each query type based on keyword matches
    type_scores: Dict[str, int] = {}

    for query_type, keywords in QUERY_TYPE_KEYWORDS.items():
        if query_type in ['comparison', 'demographic']:
            continue  # Already checked above

        score = 0
        for keyword in keywords:
            # Use word boundary matching for single words, substring for phrases
            if ' ' in keyword:
                if keyword in query_lower:
                    score += 2  # Phrases get higher weight
            else:
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, query_lower):
                    score += 1

        type_scores[query_type] = score

    # Also score based on series IDs
    series_type_indicators = {
        'labor_market': ['UNRATE', 'PAYEMS', 'ICSA', 'JTSJOL', 'U6RATE', 'LNS12300060'],
        'inflation': ['CPIAUCSL', 'CPILFESL', 'PCEPILFE', 'PCEPI', 'CUSR0000SAH1'],
        'recession': ['SAHMREALTIME', 'T10Y2Y', 'UMCSENT', 'USSLIND'],
        'fed_policy': ['FEDFUNDS', 'DGS10', 'DGS2', 'DFEDTARU'],
        'housing': ['CSUSHPINSA', 'HOUST', 'MORTGAGE30US', 'MSPUS', 'EXHOSLUSM495S'],
        'gdp': ['GDPC1', 'A191RO1Q156NBEA', 'A191RL1Q225SBEA'],
    }

    for query_type, indicators in series_type_indicators.items():
        matches = sum(1 for s in series_ids if s in indicators)
        type_scores[query_type] = type_scores.get(query_type, 0) + (matches * 2)

    # Return the highest scoring type, or 'general' if no clear winner
    if type_scores:
        max_score = max(type_scores.values())
        if max_score >= 2:
            return max(type_scores, key=type_scores.get)

    return 'general'


# =============================================================================
# GAP IDENTIFICATION
# =============================================================================

def _extract_context_elements(series_data: Dict) -> List[str]:
    """
    Extract what context elements are provided by the current series data.

    Args:
        series_data: Dictionary mapping series IDs to their data

    Returns:
        List of context element names that are covered
    """
    covered_elements = []

    for series_id in series_data.keys():
        if series_id in SERIES_TO_CONTEXT:
            covered_elements.extend(SERIES_TO_CONTEXT[series_id])

    return list(set(covered_elements))


def _check_analysis_content(current_analysis: Dict) -> List[str]:
    """
    Check what context elements are mentioned in the analysis text.

    This parses the analysis narrative and key insight to determine
    what concepts have been addressed.

    Args:
        current_analysis: Dict with 'narrative', 'headline', 'key_insight', etc.

    Returns:
        List of context element names that appear to be addressed
    """
    addressed = []

    # Combine all text from the analysis
    text_parts = []
    text_parts.append(current_analysis.get('headline', ''))
    text_parts.append(current_analysis.get('key_insight', ''))
    text_parts.extend(current_analysis.get('narrative', []))
    text_parts.extend(current_analysis.get('risks', []))

    full_text = ' '.join(text_parts).lower()

    # Map keywords to context elements
    keyword_to_element = {
        'unemployment': ['unemployment_level', 'unemployment_trend'],
        'jobless': ['unemployment_level'],
        'job gains': ['job_gains'],
        'payrolls': ['job_gains'],
        'added jobs': ['job_gains'],
        'claims': ['initial_claims'],
        'layoffs': ['initial_claims'],
        'openings': ['job_openings'],
        'quits': ['quits_rate'],
        'prime age': ['prime_age_epop'],
        'inflation': ['headline_or_core_level', 'yoy_trend'],
        'cpi': ['headline_or_core_level'],
        'pce': ['headline_or_core_level'],
        'shelter': ['shelter_component'],
        'rent': ['shelter_component'],
        '2%': ['fed_target_distance'],
        'target': ['fed_target_distance'],
        'core': ['core_vs_headline_gap'],
        'headline': ['core_vs_headline_gap'],
        'yield curve': ['yield_curve'],
        'inverted': ['yield_curve'],
        'sahm': ['sahm_rule'],
        'sentiment': ['consumer_sentiment'],
        'confidence': ['consumer_sentiment'],
        'fed funds': ['current_rate'],
        'rate': ['current_rate'],
        'growth': ['growth_rate', 'growth_direction'],
        'gdp': ['growth_rate'],
        'expanding': ['growth_direction'],
        'contracting': ['growth_direction'],
        'mortgage': ['mortgage_rate'],
        'home price': ['price_trend'],
        'housing': ['price_trend'],
        'affordability': ['affordability'],
    }

    for keyword, elements in keyword_to_element.items():
        if keyword in full_text:
            addressed.extend(elements)

    return list(set(addressed))


def identify_gaps(
    query: str,
    series_data: Dict,
    current_analysis: Dict,
) -> Dict:
    """
    Identify what's missing from the current analysis.

    This function compares the required context for the query type against
    what's actually present in the data and analysis, then identifies gaps.

    Args:
        query: The user's original query string
        series_data: Dictionary mapping series IDs to their data (dates, values, info)
        current_analysis: Dict with current analysis content:
            - headline: str
            - narrative: List[str]
            - key_insight: str
            - risks: List[str]
            - opportunities: List[str]

    Returns:
        Dictionary with gap information:
        {
            'query_type': str,
            'missing_must_have': List[str],
            'missing_should_have': List[str],
            'missing_nice_to_have': List[str],
            'gap_severity': 'critical' | 'moderate' | 'minor',
            'suggested_additions': List[str],  # Human-readable suggestions
            'covered_elements': List[str],  # What's already covered
        }

    Example:
        >>> gaps = identify_gaps(
        ...     "How is the job market?",
        ...     {"UNRATE": {...}},  # Only unemployment data
        ...     {"headline": "...", "narrative": [...]}
        ... )
        >>> gaps['gap_severity']
        'moderate'
        >>> gaps['missing_must_have']
        ['job_gains']  # Missing payrolls data
    """
    # Determine query type
    series_ids = list(series_data.keys())
    query_type = detect_query_type(query, series_ids)

    # Get required context for this query type
    requirements = REQUIRED_CONTEXT.get(query_type, REQUIRED_CONTEXT['general'])

    # Extract what's covered by the data
    data_coverage = _extract_context_elements(series_data)

    # Check what's addressed in the analysis text
    analysis_coverage = _check_analysis_content(current_analysis)

    # Combine coverage
    all_covered = list(set(data_coverage + analysis_coverage))

    # Identify missing elements
    missing_must_have = [
        elem for elem in requirements['must_have']
        if elem not in all_covered
    ]

    missing_should_have = [
        elem for elem in requirements['should_have']
        if elem not in all_covered
    ]

    missing_nice_to_have = [
        elem for elem in requirements.get('nice_to_have', [])
        if elem not in all_covered
    ]

    # Determine severity
    if missing_must_have:
        gap_severity = 'critical'
    elif len(missing_should_have) >= 2:
        gap_severity = 'moderate'
    elif missing_should_have:
        gap_severity = 'minor'
    else:
        gap_severity = 'minor'

    # Generate human-readable suggestions
    suggested_additions = _generate_suggestions(
        query_type, missing_must_have, missing_should_have
    )

    return {
        'query_type': query_type,
        'missing_must_have': missing_must_have,
        'missing_should_have': missing_should_have,
        'missing_nice_to_have': missing_nice_to_have,
        'gap_severity': gap_severity,
        'suggested_additions': suggested_additions,
        'covered_elements': all_covered,
    }


def _generate_suggestions(
    query_type: str,
    missing_must_have: List[str],
    missing_should_have: List[str]
) -> List[str]:
    """
    Generate human-readable suggestions for filling gaps.

    Args:
        query_type: The detected query type
        missing_must_have: List of missing critical elements
        missing_should_have: List of missing important elements

    Returns:
        List of suggestion strings
    """
    suggestions = []

    # Suggestion templates by element
    element_suggestions = {
        'unemployment_level': "Add the current unemployment rate level",
        'unemployment_trend': "Note whether unemployment is rising or falling",
        'job_gains': "Include recent job gains/losses (nonfarm payrolls)",
        'prime_age_epop': "Consider prime-age employment-population ratio for fuller picture",
        'initial_claims': "Mention initial jobless claims for early warning signs",
        'quits_rate': "Quits rate shows worker confidence (high = workers confident)",
        'job_openings': "Job openings vs unemployed ratio shows labor market tightness",
        'wage_growth': "Add wage growth to show worker bargaining power",
        'headline_or_core_level': "State the current inflation level",
        'yoy_trend': "Note the year-over-year inflation trend",
        'shelter_component': "Shelter/rent is ~1/3 of CPI - critical to mention",
        'core_vs_headline_gap': "Compare core vs headline inflation",
        'fed_target_distance': "How far is inflation from the Fed's 2% target?",
        'sahm_rule': "Sahm Rule is key recession indicator - has it triggered?",
        'yield_curve': "Yield curve inversion status (recession predictor)",
        'consumer_sentiment': "Consumer sentiment often leads spending",
        'leading_indicators': "Leading economic indicators predict turning points",
        'current_rate': "State the current Fed funds rate",
        'inflation_vs_target': "Compare current inflation to Fed's 2% target",
        'real_rate': "Real rate = fed funds - inflation (shows true tightness)",
        'dot_plot_path': "Fed's dot plot shows projected rate path",
        'labor_market_conditions': "Labor market affects Fed decisions",
        'price_trend': "Note home price trend (rising/falling)",
        'mortgage_rate': "Current mortgage rates affect affordability",
        'affordability': "Housing affordability metric or payment-to-income",
        'inventory': "Housing inventory affects price dynamics",
        'growth_rate': "State the GDP growth rate",
        'growth_direction': "Note whether economy is expanding or contracting",
        'both_values': "Show both values being compared",
        'gap_or_ratio': "Quantify the gap or ratio between compared items",
        'demographic_value': "State the demographic-specific value",
        'overall_value': "Include overall/national value for comparison",
        'gap': "Note the gap between demographic and overall values",
    }

    # Add suggestions for critical missing elements
    for elem in missing_must_have:
        if elem in element_suggestions:
            suggestions.append(f"CRITICAL: {element_suggestions[elem]}")

    # Add suggestions for important missing elements (limit to 3)
    for elem in missing_should_have[:3]:
        if elem in element_suggestions:
            suggestions.append(element_suggestions[elem])

    return suggestions


# =============================================================================
# GAP FILLING
# =============================================================================

def fill_gaps(
    gaps: Dict,
    series_data: Dict,
    query: str,
) -> Dict:
    """
    Generate additional analysis to fill identified gaps.

    This function examines the available data and generates additional
    context text to address the missing elements identified by identify_gaps().

    Args:
        gaps: Output from identify_gaps() containing gap information
        series_data: Dictionary mapping series IDs to their data tuples
            Each value is (series_id, dates, values, info)
        query: The user's original query

    Returns:
        Dictionary with filled content:
        {
            'additional_context': str,  # Text to append to analysis
            'additional_bullets': List[str],  # Bullet points to add
            'warnings': List[str],  # Caveats about filled data
            'filled_elements': List[str],  # What elements we addressed
        }

    Example:
        >>> gaps = identify_gaps(query, series_data, analysis)
        >>> filled = fill_gaps(gaps, series_data, query)
        >>> print(filled['additional_context'])
        "Looking at additional context: Initial jobless claims at 218K
        remain historically low, suggesting limited layoff activity..."
    """
    additional_bullets = []
    warnings = []
    filled_elements = []

    query_type = gaps.get('query_type', 'general')
    missing_must = gaps.get('missing_must_have', [])
    missing_should = gaps.get('missing_should_have', [])

    # Try to fill gaps from available data
    data_context = _build_data_context_from_series(series_data)

    # Generate content for missing must-have elements
    for element in missing_must:
        filled_text = _fill_element(element, data_context, query_type)
        if filled_text:
            additional_bullets.append(filled_text)
            filled_elements.append(element)

    # Generate content for missing should-have elements (limit to 2)
    for element in missing_should[:2]:
        filled_text = _fill_element(element, data_context, query_type)
        if filled_text:
            additional_bullets.append(filled_text)
            filled_elements.append(element)

    # If we couldn't fill from data, add generic context
    if not additional_bullets and gaps.get('gap_severity') == 'critical':
        generic_context = _generate_generic_context(query_type, missing_must)
        if generic_context:
            additional_bullets.append(generic_context)
            warnings.append("Some context is general (specific data not available)")

    # Build additional context paragraph
    if additional_bullets:
        additional_context = "Additional context: " + " ".join(additional_bullets)
    else:
        additional_context = ""

    return {
        'additional_context': additional_context,
        'additional_bullets': additional_bullets,
        'warnings': warnings,
        'filled_elements': filled_elements,
    }


def _build_data_context_from_series(series_data: Dict) -> Dict[str, Any]:
    """
    Build a context dictionary from series data for gap filling.

    Args:
        series_data: Dictionary mapping series IDs to data tuples

    Returns:
        Dictionary with extracted values keyed by concept names
    """
    context = {}

    for series_id, data in series_data.items():
        # Handle both tuple format (series_id, dates, values, info) and dict format
        if isinstance(data, tuple) and len(data) >= 4:
            _, dates, values, info = data
        elif isinstance(data, dict):
            dates = data.get('dates', [])
            values = data.get('values', [])
            info = data.get('info', {})
        else:
            continue

        if not values:
            continue

        latest_value = values[-1]
        latest_date = dates[-1] if dates else 'unknown'

        # Map to context keys based on series
        if series_id == 'UNRATE':
            context['unemployment_rate'] = latest_value
            context['unemployment_date'] = latest_date
            if len(values) >= 3:
                context['unemployment_trend'] = 'rising' if values[-1] > values[-3] else 'falling'

        elif series_id == 'PAYEMS':
            if len(values) >= 2:
                change = values[-1] - values[-2]
                context['payroll_change'] = change
                context['payroll_date'] = latest_date

        elif series_id == 'ICSA':
            context['initial_claims'] = latest_value
            context['claims_date'] = latest_date

        elif series_id == 'JTSJOL':
            context['job_openings'] = latest_value
            context['openings_date'] = latest_date

        elif series_id == 'JTSQUR':
            context['quits_rate'] = latest_value

        elif series_id in ['CPIAUCSL', 'CPILFESL', 'PCEPILFE']:
            # Calculate YoY if we have enough data
            if len(values) >= 12:
                yoy = ((values[-1] / values[-12]) - 1) * 100
                context['inflation_yoy'] = round(yoy, 1)
            context['inflation_level'] = latest_value

        elif series_id == 'T10Y2Y':
            context['yield_curve_spread'] = latest_value
            context['yield_curve_inverted'] = latest_value < 0

        elif series_id == 'SAHMREALTIME':
            context['sahm_rule_value'] = latest_value
            context['sahm_triggered'] = latest_value >= 0.5

        elif series_id == 'UMCSENT':
            context['consumer_sentiment'] = latest_value

        elif series_id == 'FEDFUNDS':
            context['fed_funds_rate'] = latest_value

        elif series_id in ['A191RO1Q156NBEA', 'A191RL1Q225SBEA']:
            context['gdp_growth'] = latest_value

    return context


def _fill_element(element: str, data_context: Dict, query_type: str) -> Optional[str]:
    """
    Generate text to fill a specific missing element.

    Args:
        element: The context element name to fill
        data_context: Available data context
        query_type: The query type for context-appropriate language

    Returns:
        Text string if we can fill this element, None otherwise
    """
    # Templates for filling different elements
    fill_templates = {
        'unemployment_trend': lambda ctx: (
            f"Unemployment is {ctx.get('unemployment_trend', 'stable')} "
            f"from {ctx.get('unemployment_rate', 'N/A')}%"
            if 'unemployment_trend' in ctx else None
        ),
        'job_gains': lambda ctx: (
            f"The economy added {ctx['payroll_change']:.0f}K jobs "
            f"in the latest month"
            if 'payroll_change' in ctx else None
        ),
        'initial_claims': lambda ctx: (
            f"Initial jobless claims at {ctx['initial_claims']:.0f}K "
            f"{'remain historically low' if ctx['initial_claims'] < 250 else 'show elevated layoffs'}"
            if 'initial_claims' in ctx else None
        ),
        'job_openings': lambda ctx: (
            f"Job openings at {ctx['job_openings']/1000:.1f} million"
            if 'job_openings' in ctx else None
        ),
        'quits_rate': lambda ctx: (
            f"The quits rate at {ctx['quits_rate']:.1f}% "
            f"{'suggests workers are confident' if ctx['quits_rate'] > 2.3 else 'shows workers are cautious'}"
            if 'quits_rate' in ctx else None
        ),
        'yoy_trend': lambda ctx: (
            f"Year-over-year inflation is at {ctx['inflation_yoy']:.1f}%"
            if 'inflation_yoy' in ctx else None
        ),
        'fed_target_distance': lambda ctx: (
            f"Inflation remains {abs(ctx['inflation_yoy'] - 2):.1f}pp "
            f"{'above' if ctx['inflation_yoy'] > 2 else 'below'} the Fed's 2% target"
            if 'inflation_yoy' in ctx else None
        ),
        'yield_curve': lambda ctx: (
            f"The yield curve is {'inverted at ' + str(ctx['yield_curve_spread']) + 'bp' if ctx.get('yield_curve_inverted') else 'positive'}"
            if 'yield_curve_spread' in ctx else None
        ),
        'sahm_rule': lambda ctx: (
            f"The Sahm Rule {'has triggered' if ctx.get('sahm_triggered') else 'has not triggered'} "
            f"(currently {ctx['sahm_rule_value']:.2f})"
            if 'sahm_rule_value' in ctx else None
        ),
        'consumer_sentiment': lambda ctx: (
            f"Consumer sentiment at {ctx['consumer_sentiment']:.0f} "
            f"{'is depressed' if ctx['consumer_sentiment'] < 70 else 'is healthy'}"
            if 'consumer_sentiment' in ctx else None
        ),
        'current_rate': lambda ctx: (
            f"The Fed funds rate is at {ctx['fed_funds_rate']:.2f}%"
            if 'fed_funds_rate' in ctx else None
        ),
        'growth_rate': lambda ctx: (
            f"GDP growth is at {ctx['gdp_growth']:.1f}%"
            if 'gdp_growth' in ctx else None
        ),
    }

    if element in fill_templates:
        return fill_templates[element](data_context)

    return None


def _generate_generic_context(query_type: str, missing_elements: List[str]) -> Optional[str]:
    """
    Generate generic context when specific data isn't available.

    Args:
        query_type: The detected query type
        missing_elements: List of missing critical elements

    Returns:
        Generic context string or None
    """
    generic_templates = {
        'labor_market': (
            "For a complete labor market assessment, consider also checking "
            "job openings (JOLTS), initial claims, and the quits rate."
        ),
        'inflation': (
            "Shelter inflation (about 1/3 of CPI) typically lags market rents "
            "by 12-18 months, which can affect the path back to 2%."
        ),
        'recession': (
            "Key recession indicators include the Sahm Rule, yield curve, "
            "leading economic indicators, and initial claims trends."
        ),
        'fed_policy': (
            "Fed decisions depend on progress toward 2% inflation, "
            "labor market conditions, and financial stability considerations."
        ),
    }

    return generic_templates.get(query_type)


# =============================================================================
# FACT CHECKING
# =============================================================================

def fact_check_analysis(
    analysis_text: str,
    series_data: Dict,
) -> Dict:
    """
    Verify claims in the analysis against actual data.

    This function parses the analysis text for numerical claims and
    verifies them against the provided series data.

    Args:
        analysis_text: The full analysis text to verify
        series_data: Dictionary mapping series IDs to data tuples

    Returns:
        Dictionary with verification results:
        {
            'verified': bool,  # True if no issues found
            'issues': List[str],  # Any factual problems found
            'corrections': List[str],  # Suggested fixes
            'claims_checked': int,  # Number of claims verified
        }

    Example:
        >>> result = fact_check_analysis(
        ...     "Unemployment at 4.1% is rising",
        ...     {"UNRATE": (_, _, [3.9, 4.0, 4.1], _)}
        ... )
        >>> result['verified']
        True
    """
    issues = []
    corrections = []
    claims_checked = 0

    # Build reference data
    data_context = _build_data_context_from_series(series_data)

    # Extract numerical claims from text
    claims = _extract_numerical_claims(analysis_text)

    for claim in claims:
        claims_checked += 1
        issue, correction = _verify_claim(claim, data_context)
        if issue:
            issues.append(issue)
            if correction:
                corrections.append(correction)

    # Check directional claims (rising/falling)
    directional_issues = _check_directional_claims(analysis_text, data_context)
    issues.extend(directional_issues)

    return {
        'verified': len(issues) == 0,
        'issues': issues,
        'corrections': corrections,
        'claims_checked': claims_checked,
    }


def _extract_numerical_claims(text: str) -> List[Dict]:
    """
    Extract numerical claims from analysis text.

    Args:
        text: Analysis text to parse

    Returns:
        List of claim dictionaries with 'value', 'context', 'unit'
    """
    claims = []

    # Pattern for percentage claims: "X.X%" or "X%"
    pct_pattern = r'(\d+\.?\d*)\s*%'
    for match in re.finditer(pct_pattern, text):
        value = float(match.group(1))
        # Get surrounding context (20 chars before and after)
        start = max(0, match.start() - 30)
        end = min(len(text), match.end() + 20)
        context = text[start:end].lower()

        claims.append({
            'value': value,
            'context': context,
            'unit': 'percent',
            'position': match.start(),
        })

    # Pattern for thousands (e.g., "200K jobs", "218K claims")
    k_pattern = r'(\d+\.?\d*)\s*[Kk]'
    for match in re.finditer(k_pattern, text):
        value = float(match.group(1))
        start = max(0, match.start() - 30)
        end = min(len(text), match.end() + 20)
        context = text[start:end].lower()

        claims.append({
            'value': value,
            'context': context,
            'unit': 'thousands',
            'position': match.start(),
        })

    return claims


def _verify_claim(claim: Dict, data_context: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Verify a single numerical claim against data.

    Args:
        claim: Dictionary with 'value', 'context', 'unit'
        data_context: Reference data

    Returns:
        Tuple of (issue_string, correction_string) or (None, None) if verified
    """
    value = claim['value']
    context = claim['context']
    unit = claim['unit']

    # Check unemployment claims
    if 'unemployment' in context and unit == 'percent':
        actual = data_context.get('unemployment_rate')
        if actual is not None:
            # Allow for rounding differences
            if abs(value - actual) > 0.2:
                return (
                    f"Unemployment claimed as {value}% but data shows {actual}%",
                    f"Correct to {actual}%"
                )

    # Check inflation claims
    if any(word in context for word in ['inflation', 'cpi', 'pce']) and unit == 'percent':
        actual = data_context.get('inflation_yoy')
        if actual is not None:
            if abs(value - actual) > 0.3:
                return (
                    f"Inflation claimed as {value}% but calculated YoY is {actual}%",
                    f"Correct to {actual}%"
                )

    # Check job gains claims
    if any(word in context for word in ['job', 'payroll', 'added']) and unit == 'thousands':
        actual = data_context.get('payroll_change')
        if actual is not None:
            if abs(value - actual) > 20:
                return (
                    f"Job gains claimed as {value}K but data shows {actual:.0f}K",
                    f"Correct to {actual:.0f}K"
                )

    # Check claims claims (initial jobless)
    if 'claims' in context and unit == 'thousands':
        actual = data_context.get('initial_claims')
        if actual is not None:
            if abs(value - actual) > 10:
                return (
                    f"Initial claims claimed as {value}K but data shows {actual:.0f}K",
                    f"Correct to {actual:.0f}K"
                )

    return (None, None)


def _check_directional_claims(text: str, data_context: Dict) -> List[str]:
    """
    Check directional claims (rising/falling) against data trends.

    Args:
        text: Analysis text
        data_context: Reference data with trend information

    Returns:
        List of issues found
    """
    issues = []
    text_lower = text.lower()

    # Check unemployment direction claims
    if data_context.get('unemployment_trend'):
        actual_trend = data_context['unemployment_trend']

        if 'unemployment' in text_lower:
            if 'rising' in text_lower and actual_trend == 'falling':
                issues.append(
                    "Claims unemployment is rising but data shows it falling"
                )
            elif 'falling' in text_lower and actual_trend == 'rising':
                issues.append(
                    "Claims unemployment is falling but data shows it rising"
                )

    # Check yield curve claims
    if 'yield_curve_inverted' in data_context:
        is_inverted = data_context['yield_curve_inverted']

        if 'yield curve' in text_lower:
            if 'inverted' in text_lower and not is_inverted:
                issues.append(
                    "Claims yield curve is inverted but spread is positive"
                )
            elif 'positive' in text_lower and is_inverted:
                issues.append(
                    "Claims yield curve is positive but it's inverted"
                )

    return issues


# =============================================================================
# TONE CHECKING
# =============================================================================

def tone_check_analysis(
    analysis_text: str,
    data_context: Dict,
) -> Dict:
    """
    Check if the tone matches the data.

    This function assesses whether the analysis tone (optimistic, neutral,
    pessimistic) is appropriate given the underlying data.

    Args:
        analysis_text: The full analysis text to check
        data_context: Dictionary with extracted data values

    Returns:
        Dictionary with tone assessment:
        {
            'tone': 'optimistic' | 'neutral' | 'pessimistic',
            'appropriate': bool,
            'data_sentiment': 'positive' | 'neutral' | 'negative',
            'suggestions': List[str],  # Tone adjustment suggestions
        }

    Example:
        >>> result = tone_check_analysis(
        ...     "The economy is booming with strong job gains!",
        ...     {"unemployment_rate": 6.5, "unemployment_trend": "rising"}
        ... )
        >>> result['appropriate']
        False  # Optimistic tone doesn't match rising unemployment
    """
    # Assess tone of analysis text
    analysis_tone = _assess_text_tone(analysis_text)

    # Assess what the data suggests
    data_sentiment = _assess_data_sentiment(data_context)

    # Check if tone matches data
    tone_matches = _check_tone_match(analysis_tone, data_sentiment)

    # Generate suggestions if mismatch
    suggestions = []
    if not tone_matches:
        suggestions = _generate_tone_suggestions(analysis_tone, data_sentiment, data_context)

    return {
        'tone': analysis_tone,
        'appropriate': tone_matches,
        'data_sentiment': data_sentiment,
        'suggestions': suggestions,
    }


def _assess_text_tone(text: str) -> str:
    """
    Assess the tone of analysis text.

    Args:
        text: Analysis text to assess

    Returns:
        'optimistic', 'neutral', or 'pessimistic'
    """
    text_lower = text.lower()

    # Optimistic indicators
    optimistic_words = [
        'strong', 'robust', 'healthy', 'solid', 'excellent', 'booming',
        'surging', 'accelerating', 'improving', 'resilient', 'gains',
        'recovery', 'expansion', 'growing', 'positive', 'encouraging'
    ]

    # Pessimistic indicators
    pessimistic_words = [
        'weak', 'weakening', 'declining', 'falling', 'slowing', 'contraction',
        'recession', 'crisis', 'concerning', 'troubling', 'deteriorating',
        'collapse', 'crash', 'plunging', 'struggling', 'risk', 'warning'
    ]

    # Neutral indicators
    neutral_words = [
        'stable', 'moderate', 'steady', 'mixed', 'unchanged', 'flat',
        'balanced', 'modest', 'gradual'
    ]

    opt_count = sum(1 for word in optimistic_words if word in text_lower)
    pess_count = sum(1 for word in pessimistic_words if word in text_lower)
    neutral_count = sum(1 for word in neutral_words if word in text_lower)

    # Determine predominant tone
    if opt_count > pess_count + 1 and opt_count > neutral_count:
        return 'optimistic'
    elif pess_count > opt_count + 1 and pess_count > neutral_count:
        return 'pessimistic'
    else:
        return 'neutral'


def _assess_data_sentiment(data_context: Dict) -> str:
    """
    Assess what sentiment the data supports.

    Args:
        data_context: Dictionary with data values

    Returns:
        'positive', 'neutral', or 'negative'
    """
    positive_signals = 0
    negative_signals = 0

    # Unemployment assessment
    if 'unemployment_rate' in data_context:
        rate = data_context['unemployment_rate']
        if rate < 4.0:
            positive_signals += 2
        elif rate < 5.0:
            positive_signals += 1
        elif rate > 6.0:
            negative_signals += 2
        elif rate > 5.0:
            negative_signals += 1

    # Unemployment trend
    if data_context.get('unemployment_trend') == 'falling':
        positive_signals += 1
    elif data_context.get('unemployment_trend') == 'rising':
        negative_signals += 1

    # Job gains
    if 'payroll_change' in data_context:
        change = data_context['payroll_change']
        if change > 200:
            positive_signals += 2
        elif change > 100:
            positive_signals += 1
        elif change < 0:
            negative_signals += 2
        elif change < 50:
            negative_signals += 1

    # Inflation distance from target
    if 'inflation_yoy' in data_context:
        inflation = data_context['inflation_yoy']
        distance_from_target = abs(inflation - 2.0)
        if distance_from_target < 0.5:
            positive_signals += 1
        elif distance_from_target > 2.0:
            negative_signals += 1

    # Yield curve
    if data_context.get('yield_curve_inverted'):
        negative_signals += 2

    # Sahm rule
    if data_context.get('sahm_triggered'):
        negative_signals += 3

    # Consumer sentiment
    if 'consumer_sentiment' in data_context:
        sentiment = data_context['consumer_sentiment']
        if sentiment > 90:
            positive_signals += 1
        elif sentiment < 60:
            negative_signals += 1

    # Determine overall sentiment
    if positive_signals > negative_signals + 2:
        return 'positive'
    elif negative_signals > positive_signals + 2:
        return 'negative'
    else:
        return 'neutral'


def _check_tone_match(analysis_tone: str, data_sentiment: str) -> bool:
    """
    Check if analysis tone matches data sentiment.

    Args:
        analysis_tone: 'optimistic', 'neutral', or 'pessimistic'
        data_sentiment: 'positive', 'neutral', or 'negative'

    Returns:
        True if tones are compatible, False otherwise
    """
    # Direct matches
    if analysis_tone == 'optimistic' and data_sentiment == 'positive':
        return True
    if analysis_tone == 'pessimistic' and data_sentiment == 'negative':
        return True
    if analysis_tone == 'neutral' and data_sentiment == 'neutral':
        return True

    # Neutral analysis is acceptable for any data
    if analysis_tone == 'neutral':
        return True

    # Mismatches
    if analysis_tone == 'optimistic' and data_sentiment == 'negative':
        return False
    if analysis_tone == 'pessimistic' and data_sentiment == 'positive':
        return False

    # Close enough matches
    return True


def _generate_tone_suggestions(
    analysis_tone: str,
    data_sentiment: str,
    data_context: Dict
) -> List[str]:
    """
    Generate suggestions for adjusting tone.

    Args:
        analysis_tone: Current analysis tone
        data_sentiment: What data supports
        data_context: The underlying data

    Returns:
        List of suggestion strings
    """
    suggestions = []

    if analysis_tone == 'optimistic' and data_sentiment == 'negative':
        suggestions.append(
            "Consider tempering optimistic language given mixed/negative data signals"
        )

        if data_context.get('sahm_triggered'):
            suggestions.append(
                "The Sahm Rule has triggered - this typically signals recession"
            )

        if data_context.get('yield_curve_inverted'):
            suggestions.append(
                "Yield curve inversion is a recession warning sign"
            )

        if data_context.get('unemployment_trend') == 'rising':
            suggestions.append(
                "Rising unemployment warrants cautious language"
            )

    elif analysis_tone == 'pessimistic' and data_sentiment == 'positive':
        suggestions.append(
            "Consider more balanced language - data shows some positive signals"
        )

        if 'unemployment_rate' in data_context and data_context['unemployment_rate'] < 4.5:
            suggestions.append(
                f"Unemployment at {data_context['unemployment_rate']}% is historically low"
            )

        if 'payroll_change' in data_context and data_context['payroll_change'] > 150:
            suggestions.append(
                f"Job gains of {data_context['payroll_change']:.0f}K are solid"
            )

    return suggestions


# =============================================================================
# CONVENIENCE FUNCTION FOR FULL ANALYSIS REVIEW
# =============================================================================

def review_analysis(
    query: str,
    series_data: Dict,
    current_analysis: Dict,
) -> Dict:
    """
    Comprehensive review of an analysis - gaps, facts, and tone.

    This is the main entry point that runs all checks and returns
    a complete review.

    Args:
        query: The user's original query
        series_data: Dictionary mapping series IDs to data
        current_analysis: The current analysis content

    Returns:
        Dictionary with complete review:
        {
            'gaps': {...},  # Output from identify_gaps
            'filled': {...},  # Output from fill_gaps
            'fact_check': {...},  # Output from fact_check_analysis
            'tone_check': {...},  # Output from tone_check_analysis
            'overall_quality': 'good' | 'needs_improvement' | 'critical_issues',
            'summary': str,  # Human-readable summary
        }
    """
    # Identify gaps
    gaps = identify_gaps(query, series_data, current_analysis)

    # Fill gaps
    filled = fill_gaps(gaps, series_data, query)

    # Build full analysis text for fact/tone checking
    analysis_text = _build_analysis_text(current_analysis)

    # Fact check
    fact_check = fact_check_analysis(analysis_text, series_data)

    # Tone check
    data_context = _build_data_context_from_series(series_data)
    tone_check = tone_check_analysis(analysis_text, data_context)

    # Determine overall quality
    if gaps['gap_severity'] == 'critical' or not fact_check['verified']:
        overall_quality = 'critical_issues'
    elif gaps['gap_severity'] == 'moderate' or not tone_check['appropriate']:
        overall_quality = 'needs_improvement'
    else:
        overall_quality = 'good'

    # Build summary
    summary_parts = []
    if gaps['gap_severity'] != 'minor':
        summary_parts.append(
            f"Gap severity: {gaps['gap_severity']} "
            f"(missing: {', '.join(gaps['missing_must_have'][:2])})"
        )
    if not fact_check['verified']:
        summary_parts.append(f"Fact issues: {len(fact_check['issues'])}")
    if not tone_check['appropriate']:
        summary_parts.append(
            f"Tone mismatch: {tone_check['tone']} analysis vs {tone_check['data_sentiment']} data"
        )
    if not summary_parts:
        summary_parts.append("Analysis quality is good")

    return {
        'gaps': gaps,
        'filled': filled,
        'fact_check': fact_check,
        'tone_check': tone_check,
        'overall_quality': overall_quality,
        'summary': "; ".join(summary_parts),
    }


def _build_analysis_text(current_analysis: Dict) -> str:
    """
    Build full text from analysis components.

    Args:
        current_analysis: Dictionary with analysis components

    Returns:
        Combined text string
    """
    parts = []

    if current_analysis.get('headline'):
        parts.append(current_analysis['headline'])

    if current_analysis.get('narrative'):
        parts.extend(current_analysis['narrative'])

    if current_analysis.get('key_insight'):
        parts.append(current_analysis['key_insight'])

    if current_analysis.get('risks'):
        parts.extend(current_analysis['risks'])

    if current_analysis.get('opportunities'):
        parts.extend(current_analysis['opportunities'])

    return ' '.join(parts)


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("ANALYSIS GAPS MODULE - TEST")
    print("=" * 70)

    # Test 1: Query type detection
    print("\n1. Testing query type detection...")

    test_cases = [
        ("How is the job market?", ["UNRATE", "PAYEMS"], "labor_market"),
        ("What's happening with inflation?", ["CPIAUCSL"], "inflation"),
        ("Is a recession coming?", ["T10Y2Y", "SAHMREALTIME"], "recession"),
        ("US vs Eurozone GDP", ["GDPC1"], "comparison"),
        ("Black unemployment rate", ["LNS14000006"], "demographic"),
        ("What will the Fed do?", ["FEDFUNDS"], "fed_policy"),
    ]

    for query, series, expected in test_cases:
        result = detect_query_type(query, series)
        status = "PASS" if result == expected else "FAIL"
        print(f"  {status}: '{query}' -> {result} (expected {expected})")

    # Test 2: Gap identification
    print("\n2. Testing gap identification...")

    sample_series_data = {
        "UNRATE": ("UNRATE", ["2024-10-01", "2024-11-01", "2024-12-01"], [4.0, 4.1, 4.1], {"name": "Unemployment Rate"}),
    }

    sample_analysis = {
        "headline": "Unemployment is stable at 4.1%",
        "narrative": ["Labor market remains resilient"],
        "key_insight": "Job market is healthy",
        "risks": [],
        "opportunities": [],
    }

    gaps = identify_gaps(
        "How is the job market?",
        sample_series_data,
        sample_analysis
    )

    print(f"  Query type: {gaps['query_type']}")
    print(f"  Gap severity: {gaps['gap_severity']}")
    print(f"  Missing must-have: {gaps['missing_must_have']}")
    print(f"  Missing should-have: {gaps['missing_should_have']}")
    print(f"  Suggestions: {gaps['suggested_additions'][:2]}")

    # Test 3: Gap filling
    print("\n3. Testing gap filling...")

    # Add more data for filling
    extended_series_data = {
        "UNRATE": ("UNRATE", ["2024-10-01", "2024-11-01", "2024-12-01"], [4.0, 4.1, 4.1], {"name": "Unemployment Rate"}),
        "PAYEMS": ("PAYEMS", ["2024-10-01", "2024-11-01", "2024-12-01"], [158000, 158200, 158400], {"name": "Nonfarm Payrolls"}),
        "ICSA": ("ICSA", ["2024-12-01"], [218], {"name": "Initial Claims"}),
    }

    filled = fill_gaps(gaps, extended_series_data, "How is the job market?")

    print(f"  Additional context: {filled['additional_context'][:100]}...")
    print(f"  Bullets added: {len(filled['additional_bullets'])}")
    print(f"  Elements filled: {filled['filled_elements']}")

    # Test 4: Fact checking
    print("\n4. Testing fact checking...")

    test_analysis_text = "Unemployment at 4.1% is stable. Job gains of 200K are solid."

    fact_result = fact_check_analysis(test_analysis_text, extended_series_data)

    print(f"  Verified: {fact_result['verified']}")
    print(f"  Claims checked: {fact_result['claims_checked']}")
    print(f"  Issues: {fact_result['issues']}")

    # Test 5: Tone checking
    print("\n5. Testing tone checking...")

    data_context = _build_data_context_from_series(extended_series_data)

    optimistic_text = "The economy is booming with robust job gains and strong growth!"
    tone_result = tone_check_analysis(optimistic_text, data_context)

    print(f"  Detected tone: {tone_result['tone']}")
    print(f"  Data sentiment: {tone_result['data_sentiment']}")
    print(f"  Appropriate: {tone_result['appropriate']}")
    print(f"  Suggestions: {tone_result['suggestions']}")

    # Test 6: Full review
    print("\n6. Testing full review...")

    review = review_analysis(
        "How is the job market?",
        extended_series_data,
        sample_analysis
    )

    print(f"  Overall quality: {review['overall_quality']}")
    print(f"  Summary: {review['summary']}")

    print("\n" + "=" * 70)
    print("TESTS COMPLETE")
    print("=" * 70)
