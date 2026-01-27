"""
Query-Type Narrative Templates

Provides structured narrative templates for different types of economic queries.
Each template knows what elements to include and in what order.

The Problem:
All queries get the same generic treatment. A trend question ("Is inflation coming down?")
needs different structure than a comparison ("Black vs overall unemployment") or a
state question ("What is unemployment?").

The Solution:
Different questions need different narrative structures:
- A comparison needs to show both values and explain the gap
- A trend question needs to answer yes/no and explain the trajectory
- A recession question needs to weigh conflicting signals and assess probability
- A demographic question needs to contextualize gaps and structural factors

Usage:
    from core.narrative_templates import (
        generate_narrative,
        select_template,
        NARRATIVE_TEMPLATES,
    )

    # Generate a complete narrative
    narrative = generate_narrative(
        query="Is inflation coming down?",
        query_type="trend",
        data_context={...},
        insights=[...],
    )

    # Or work with templates directly
    template = select_template(query, "trend")
    narrative = fill_template(template, data_context, insights)

Design Principles:
1. Lead with the insight, not the number
2. Structure matches question type (comparison, trend, state, etc.)
3. Weave data into natural prose, not bullet points
4. Always end with forward-looking statement
5. Explain the "why" and "what it means", not just the "what"
"""

from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
import random
import re


@dataclass
class NarrativeTemplate:
    """
    A template for structuring a narrative response.

    Each template defines:
    - What elements are required vs optional
    - The order in which elements should appear
    - Opening and closing pattern options for natural variety
    - Transition phrases between sections

    Attributes:
        query_type: The type of query this template handles
        required_elements: Elements that must be present for a complete narrative
        optional_elements: Elements that enhance the narrative if available
        structure: Ordered list of element names defining the narrative flow
        opening_patterns: Templates for starting the narrative
        closing_patterns: Templates for ending with forward-looking statements
        transitions: Phrases to connect sections smoothly
    """
    query_type: str
    required_elements: List[str]
    optional_elements: List[str]
    structure: List[str]
    opening_patterns: List[str]
    closing_patterns: List[str]
    transitions: Dict[str, List[str]] = field(default_factory=dict)


# =============================================================================
# NARRATIVE TEMPLATES FOR EACH QUERY TYPE
# =============================================================================

NARRATIVE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # CURRENT STATE QUERIES
    # "What is unemployment?" / "What is inflation?"
    # -------------------------------------------------------------------------
    'current_state': {
        'description': 'For questions asking about the current level of an indicator',
        'required_elements': ['current_value', 'historical_context'],
        'optional_elements': ['recent_trend', 'fed_implications', 'forward_outlook', 'related_indicators'],
        'structure': [
            'direct_answer',      # "Unemployment is 4.1%"
            'historical_context', # "up from 3.5% pre-pandemic but below the 6.2% long-term average"
            'recent_trend',       # "and has been gradually rising over the past 6 months"
            'implication',        # "suggesting the Fed's rate hikes are filtering through"
            'forward_outlook',    # "Watch for whether this stabilizes or accelerates"
        ],
        'opening_patterns': [
            "{indicator} currently stands at {value}{units}",
            "The latest {indicator} reading is {value}{units}",
            "{indicator} is at {value}{units}",
            "As of {date}, {indicator} sits at {value}{units}",
        ],
        'closing_patterns': [
            "Going forward, watch for {forward_signal}.",
            "The key question is whether {uncertainty}.",
            "This suggests {assessment}, with implications for {implication_target}.",
            "Looking ahead, {forward_outlook}.",
        ],
        'transitions': {
            'historical_context': [
                "This compares to",
                "For context,",
                "Historically,",
                "To put this in perspective,",
            ],
            'recent_trend': [
                "Over recent months,",
                "The trend shows",
                "Recently,",
                "Looking at the trajectory,",
            ],
            'implication': [
                "This suggests",
                "The implication is that",
                "This points to",
                "This indicates",
            ],
        },
        'element_templates': {
            'direct_answer': "{indicator} currently stands at {value}{units}",
            'historical_context': "{historical_context}",
            'recent_trend': "{recent_trend}",
            'implication': "{economic_interpretation}",
            'forward_outlook': "{forward_outlook}",
        },
    },

    # -------------------------------------------------------------------------
    # TREND QUERIES
    # "Is inflation coming down?" / "Is unemployment rising?"
    # -------------------------------------------------------------------------
    'trend': {
        'description': 'For questions asking about the direction and trajectory of change',
        'required_elements': ['trend_direction', 'trend_magnitude', 'trend_duration'],
        'optional_elements': ['acceleration', 'causal_explanation', 'comparison_to_target', 'inflection_points'],
        'structure': [
            'trend_answer',        # "Yes, inflation is coming down"
            'magnitude',           # "from 9.1% in June 2022 to 3.2% now"
            'pace',                # "though the pace of decline has slowed in recent months"
            'causal_explanation',  # "as goods disinflation runs its course and services remain sticky"
            'distance_to_target',  # "Still 1.2pp above the Fed's 2% target"
            'forward_outlook',     # "The last mile to 2% may be the hardest"
        ],
        'opening_patterns': [
            "Yes, {indicator} is {trend_direction}",
            "Indeed, {indicator} has been {trend_direction}",
            "{indicator} is {trend_direction}, though {caveat}",
            "No, {indicator} is not {expected_direction} - it has been {actual_direction}",
            "The data confirms {indicator} is {trend_direction}",
        ],
        'closing_patterns': [
            "The {target_or_threshold} remains {distance_description} away.",
            "At this pace, {projection_statement}.",
            "Key to watch: {watch_items}.",
            "The trajectory suggests {forward_assessment}.",
        ],
        'transitions': {
            'magnitude': [
                "It has moved from",
                "The change has been substantial, from",
                "Specifically,",
            ],
            'pace': [
                "However,",
                "That said,",
                "Notably,",
                "The pace has",
            ],
            'causal_explanation': [
                "This reflects",
                "The main drivers are",
                "Behind this trend,",
                "Contributing factors include",
            ],
            'distance_to_target': [
                "Despite this progress,",
                "Even so,",
                "This still leaves",
                "That still puts us",
            ],
        },
        'element_templates': {
            'trend_answer': "{affirmation}, {indicator} is {trend_direction}",
            'magnitude': "from {start_value}{units} ({start_date}) to {end_value}{units} today, a {change_magnitude}{units} {change_direction}",
            'pace': "the pace of {change_noun} has {pace_description}",
            'causal_explanation': "{causal_factors}",
            'distance_to_target': "still {distance_value}{units} {distance_direction} {target_name}",
            'forward_outlook': "{forward_statement}",
        },
    },

    # -------------------------------------------------------------------------
    # COMPARISON QUERIES
    # "Black unemployment vs overall" / "Inflation vs wages"
    # -------------------------------------------------------------------------
    'comparison': {
        'description': 'For questions comparing two economic measures or groups',
        'required_elements': ['both_values', 'gap', 'gap_interpretation'],
        'optional_elements': ['historical_gap', 'trend_of_gap', 'explanation', 'convergence_divergence'],
        'structure': [
            'both_values',        # "Black unemployment is 7.5% vs 4.4% overall"
            'gap_quantified',     # "a gap of 3.1 percentage points, or 70% higher"
            'historical_context', # "This ratio has been persistent, typically 1.5-2x"
            'explanation',        # "reflecting structural barriers in education, geography, and hiring"
            'trend_of_gap',       # "The gap has narrowed slightly from its pandemic peak"
            'forward_outlook',    # "Tight labor markets historically help narrow this gap"
        ],
        'opening_patterns': [
            "{indicator_a} stands at {value_a}{units} compared to {value_b}{units} for {indicator_b}",
            "There's a notable gap: {indicator_a} is {value_a}{units} versus {value_b}{units} for {indicator_b}",
            "{indicator_a} ({value_a}{units}) {comparison_word} {indicator_b} ({value_b}{units})",
            "Comparing the two: {indicator_a} at {value_a}{units} and {indicator_b} at {value_b}{units}",
        ],
        'closing_patterns': [
            "The gap is {gap_trend_direction}, suggesting {gap_implication}.",
            "{condition_statement}, the gap tends to {gap_behavior}.",
            "Watch for {convergence_signal}.",
            "Historical patterns suggest {historical_pattern_implication}.",
        ],
        'transitions': {
            'gap_quantified': [
                "That's a difference of",
                "The gap amounts to",
                "This represents",
            ],
            'historical_context': [
                "Historically,",
                "This gap has been persistent -",
                "For context,",
                "Over time,",
            ],
            'explanation': [
                "This disparity reflects",
                "Behind this gap are",
                "The drivers include",
                "This can be attributed to",
            ],
            'trend_of_gap': [
                "Recently,",
                "Over the past year,",
                "The trend shows",
                "Notably,",
            ],
        },
        'element_templates': {
            'both_values': "{indicator_a} stands at {value_a}{units} compared to {value_b}{units} for {indicator_b}",
            'gap_quantified': "a {gap_description} of {gap_value} {gap_units}, or {gap_percent}% higher",
            'historical_context': "this {historical_gap_statement}",
            'explanation': "{explanation_factors}",
            'trend_of_gap': "the gap has {gap_trend_direction} from {gap_previous} to {gap_current}",
            'forward_outlook': "{forward_statement}",
        },
    },

    # -------------------------------------------------------------------------
    # DEMOGRAPHIC QUERIES
    # "How are Black workers doing?" / "Women's employment"
    # -------------------------------------------------------------------------
    'demographic': {
        'description': 'For questions about specific demographic groups in the economy',
        'required_elements': ['demographic_value', 'comparison_to_overall', 'gap'],
        'optional_elements': ['lfpr', 'historical_context', 'structural_factors', 'recent_progress', 'sector_concentration'],
        'structure': [
            'demographic_value',     # "Black unemployment is 7.5%"
            'vs_overall',            # "compared to 4.4% overall"
            'gap_context',           # "This 3.1pp gap is typical historically"
            'lfpr_context',          # "Labor force participation for Black workers is 64%"
            'structural_explanation', # "Structural factors including..."
            'recent_progress',       # "The gap has narrowed in tight labor markets"
            'forward_outlook',       # "Continued labor market strength would help"
        ],
        'opening_patterns': [
            "For {demographic_group}, {indicator} stands at {value}{units}",
            "{demographic_group} {indicator} is currently {value}{units}",
            "Looking at {demographic_group}: {indicator} is {value}{units}",
            "The {indicator} for {demographic_group} is {value}{units}",
        ],
        'closing_patterns': [
            "Continued {favorable_condition} would help {gap_impact}.",
            "Historical patterns show {historical_pattern}.",
            "Key factors to watch include {watch_factors}.",
            "Progress depends on {progress_factors}.",
        ],
        'transitions': {
            'vs_overall': [
                "This compares to",
                "Versus the overall rate of",
                "The national average is",
                "For comparison, the overall figure is",
            ],
            'gap_context': [
                "This gap of",
                "The disparity -",
                "This differential",
                "Such a gap",
            ],
            'lfpr_context': [
                "Beyond unemployment,",
                "Labor force participation also matters:",
                "Looking more broadly,",
                "Another key metric:",
            ],
            'structural_explanation': [
                "Several factors drive this gap:",
                "The underlying causes include",
                "This reflects",
                "Structural factors at play include",
            ],
            'recent_progress': [
                "On a positive note,",
                "The good news:",
                "Progress has been made:",
                "Encouragingly,",
            ],
        },
        'element_templates': {
            'demographic_value': "For {demographic_group}, {indicator} stands at {value}{units}",
            'vs_overall': "{overall_value}{units} for the overall population",
            'gap_context': "this gap of {gap_value} {gap_units} {gap_historical_comparison}",
            'lfpr_context': "labor force participation for {demographic_group} is {lfpr_value}%, {lfpr_comparison}",
            'structural_explanation': "{structural_factors}",
            'recent_progress': "{progress_statement}",
            'forward_outlook': "{forward_statement}",
        },
    },

    # -------------------------------------------------------------------------
    # RECESSION QUERIES
    # "Is a recession coming?" / "Recession risk"
    # -------------------------------------------------------------------------
    'recession': {
        'description': 'For questions about recession risk and economic downturn',
        'required_elements': ['key_signals', 'signal_status', 'probability_assessment'],
        'optional_elements': ['leading_indicators', 'comparison_to_past', 'timing', 'offsetting_factors', 'market_expectations'],
        'structure': [
            'bottom_line',         # "Recession risk is elevated but a soft landing remains possible"
            'key_signals',         # "The yield curve has been inverted for X months; Sahm rule at Y"
            'signal_context',      # "Historically, yield curve inversion has preceded every recession"
            'offsetting_factors',  # "However, the labor market remains resilient"
            'probability',         # "Polymarket puts recession odds at X%"
            'what_to_watch',       # "Key indicators to monitor: initial claims, payroll gains"
        ],
        'opening_patterns': [
            "Recession risk is {risk_level}: {summary_assessment}",
            "The signals are {signal_summary}: {key_insight}",
            "{bottom_line_assessment}",
            "On balance, {probability_assessment}",
        ],
        'closing_patterns': [
            "Key indicators to monitor: {watch_items}.",
            "The next few months will be crucial, particularly {crucial_factors}.",
            "The path from here depends on {key_dependencies}.",
            "History suggests {historical_lesson}.",
        ],
        'transitions': {
            'key_signals': [
                "The warning signs:",
                "Looking at the classic recession indicators:",
                "The data shows:",
                "Key signals include:",
            ],
            'signal_context': [
                "Historically,",
                "For context,",
                "These indicators have",
                "The track record:",
            ],
            'offsetting_factors': [
                "However,",
                "On the other hand,",
                "Pushing back against recession fears:",
                "But not everything points to recession:",
            ],
            'probability': [
                "Markets currently price",
                "Forecasters estimate",
                "The probability assessment:",
                "Prediction markets show",
            ],
        },
        'element_templates': {
            'bottom_line': "{bottom_line_assessment}",
            'key_signals': "{signal_list}",
            'signal_context': "{historical_context}",
            'offsetting_factors': "{positive_factors}",
            'probability': "{probability_statement}",
            'what_to_watch': "Key indicators to monitor: {watch_indicators}",
        },
    },

    # -------------------------------------------------------------------------
    # FED POLICY QUERIES
    # "Will the Fed cut rates?" / "Is policy too tight?"
    # -------------------------------------------------------------------------
    'fed_policy': {
        'description': 'For questions about Federal Reserve policy and interest rates',
        'required_elements': ['current_stance', 'key_data_points', 'likely_path'],
        'optional_elements': ['real_rate', 'dot_plot', 'market_expectations', 'data_dependencies', 'risks'],
        'structure': [
            'current_stance',      # "The Fed is currently at 4.25-4.50%"
            'real_rate',           # "With core inflation at 2.8%, the real rate is about 1.5%"
            'stance_assessment',   # "This is moderately restrictive by historical standards"
            'data_dependencies',   # "The Fed is watching inflation progress and labor cooling"
            'likely_path',         # "The dot plot suggests 2 cuts in 2025"
            'risks',               # "But sticky services inflation could delay cuts"
        ],
        'opening_patterns': [
            "The Fed currently holds rates at {rate_range}",
            "Monetary policy stands at {rate_range}, {stance_description}",
            "With the fed funds rate at {rate_range}, policy is {stance_label}",
            "The Fed's current {rate_range} stance is {stance_description}",
        ],
        'closing_patterns': [
            "Watch for {data_points} to signal the next move.",
            "The risk to this outlook is {risk_factor}.",
            "Markets are pricing {market_expectation}, but {fed_may_diverge}.",
            "The Fed has emphasized {fed_guidance}.",
        ],
        'transitions': {
            'real_rate': [
                "Adjusting for inflation,",
                "In real terms,",
                "After accounting for inflation,",
                "The real rate -",
            ],
            'stance_assessment': [
                "This represents",
                "By historical standards,",
                "This is",
                "Such a level is",
            ],
            'data_dependencies': [
                "The Fed is focused on",
                "Key data they're watching:",
                "The path forward depends on",
                "Powell has emphasized",
            ],
            'likely_path': [
                "Looking ahead,",
                "The Fed's projections suggest",
                "Markets expect",
                "The likely path:",
            ],
            'risks': [
                "The main risk:",
                "However,",
                "What could change this:",
                "Risks to this outlook include",
            ],
        },
        'element_templates': {
            'current_stance': "The Fed currently holds rates at {rate_range}",
            'real_rate': "the real fed funds rate is approximately {real_rate}%",
            'stance_assessment': "this is {stance_description}",
            'data_dependencies': "the Fed is focused on {data_dependencies}",
            'likely_path': "{rate_path_projection}",
            'risks': "{risk_factors}",
        },
    },

    # -------------------------------------------------------------------------
    # FORECAST QUERIES
    # "Where is inflation heading?" / "GDP outlook"
    # -------------------------------------------------------------------------
    'forecast': {
        'description': 'For questions asking about future expectations and projections',
        'required_elements': ['current_level', 'direction', 'drivers'],
        'optional_elements': ['consensus_forecast', 'model_projection', 'scenario_analysis', 'confidence_level'],
        'structure': [
            'current_baseline',    # "Inflation currently stands at 2.7%"
            'expected_direction',  # "and is expected to continue declining"
            'key_drivers',         # "driven by shelter disinflation and stable goods prices"
            'forecast_timeline',   # "reaching 2.5% by mid-2025 and 2.2% by year-end"
            'upside_risks',        # "Risks to the upside include service sector stickiness"
            'downside_risks',      # "while downside risks center on faster demand cooling"
            'confidence',          # "Confidence in this outlook is moderate given uncertainty"
        ],
        'opening_patterns': [
            "Looking ahead, {indicator} is expected to {expected_direction}",
            "The outlook for {indicator}: {direction_summary}",
            "{indicator}, currently at {current_value}{units}, is projected to {projection}",
            "Forecasters expect {indicator} to {expected_change}",
        ],
        'closing_patterns': [
            "The main uncertainty is {key_uncertainty}.",
            "This outlook assumes {key_assumption}.",
            "Confidence in this projection is {confidence_level}.",
            "Key variables to watch: {key_variables}.",
        ],
        'transitions': {
            'expected_direction': [
                "Going forward,",
                "The expectation is for",
                "Models project",
                "The trajectory points toward",
            ],
            'key_drivers': [
                "The main drivers will be",
                "This is based on",
                "Contributing factors include",
                "Behind this forecast:",
            ],
            'forecast_timeline': [
                "On the timeline:",
                "The path forward:",
                "Expectations by period:",
                "Looking at specific dates:",
            ],
            'upside_risks': [
                "Risks to the upside:",
                "The forecast could be too low if",
                "Upside risk factors:",
                "What could push it higher:",
            ],
            'downside_risks': [
                "On the downside,",
                "Conversely,",
                "Downside risks include",
                "What could push it lower:",
            ],
        },
        'element_templates': {
            'current_baseline': "{indicator} currently stands at {current_value}{units}",
            'expected_direction': "expected to {direction_verb} toward {target_value}{units}",
            'key_drivers': "{driver_list}",
            'forecast_timeline': "{timeline_statement}",
            'upside_risks': "{upside_risk_factors}",
            'downside_risks': "{downside_risk_factors}",
            'confidence': "{confidence_statement}",
        },
    },

    # -------------------------------------------------------------------------
    # CAUSAL QUERIES
    # "Why is inflation sticky?" / "What's driving unemployment higher?"
    # -------------------------------------------------------------------------
    'causal': {
        'description': 'For questions asking about causes and explanations',
        'required_elements': ['phenomenon', 'primary_cause', 'mechanism'],
        'optional_elements': ['secondary_causes', 'historical_precedent', 'timeline', 'policy_response'],
        'structure': [
            'phenomenon_stated',   # "Inflation has proven sticky at current levels"
            'primary_cause',       # "The main driver is shelter costs"
            'mechanism',           # "which lag actual rents by 12-18 months in the CPI"
            'secondary_causes',    # "Services more broadly remain elevated due to wage growth"
            'why_it_matters',      # "This matters because the Fed needs sustained progress"
            'outlook',             # "The good news: market rents have already fallen"
        ],
        'opening_patterns': [
            "The main reason {phenomenon} is {primary_cause}",
            "{phenomenon} primarily because {primary_cause}",
            "Behind {phenomenon}: {primary_cause}",
            "The answer lies in {primary_cause}",
        ],
        'closing_patterns': [
            "The implication: {implication}.",
            "This suggests {forward_implication}.",
            "As these factors evolve, expect {expected_change}.",
            "The timeline for resolution: {resolution_timeline}.",
        ],
        'transitions': {
            'primary_cause': [
                "The primary driver is",
                "The main factor is",
                "At the core:",
                "The leading cause:",
            ],
            'mechanism': [
                "This works through",
                "The mechanism:",
                "Here's how it works:",
                "The transmission channel:",
            ],
            'secondary_causes': [
                "Additional factors include",
                "Also contributing:",
                "Secondary drivers:",
                "Other causes:",
            ],
            'why_it_matters': [
                "This matters because",
                "The significance:",
                "Why this is important:",
                "The implication:",
            ],
        },
        'element_templates': {
            'phenomenon_stated': "{phenomenon_description}",
            'primary_cause': "{primary_cause_description}",
            'mechanism': "{mechanism_description}",
            'secondary_causes': "{secondary_causes_list}",
            'why_it_matters': "{significance_statement}",
            'outlook': "{outlook_statement}",
        },
    },

    # -------------------------------------------------------------------------
    # SECTOR QUERIES
    # "How is manufacturing doing?" / "Tech employment"
    # -------------------------------------------------------------------------
    'sector': {
        'description': 'For questions about specific economic sectors',
        'required_elements': ['sector_metric', 'recent_performance', 'drivers'],
        'optional_elements': ['comparison_to_overall', 'leading_indicators', 'employment_impact', 'outlook'],
        'structure': [
            'sector_current_state', # "Manufacturing output declined 0.5% last month"
            'performance_context',  # "This extends a three-month streak of weakness"
            'key_drivers',          # "driven by weak demand and inventory destocking"
            'comparison',           # "while services continue to expand"
            'employment_impact',    # "The sector has shed 15K jobs this year"
            'forward_outlook',      # "Leading indicators suggest stabilization ahead"
        ],
        'opening_patterns': [
            "{sector} is {performance_summary}",
            "The {sector} sector shows {performance_description}",
            "Looking at {sector}: {key_metric}",
            "{sector} {metric} came in at {value}, {interpretation}",
        ],
        'closing_patterns': [
            "Leading indicators suggest {forward_signal}.",
            "The outlook for {sector} depends on {key_factors}.",
            "Watch for {leading_indicator} as an early signal.",
            "The sector's trajectory points toward {direction}.",
        ],
        'transitions': {
            'performance_context': [
                "This continues",
                "Building on",
                "This marks",
                "The trend shows",
            ],
            'key_drivers': [
                "The drivers:",
                "This reflects",
                "Behind this:",
                "Contributing factors:",
            ],
            'comparison': [
                "In contrast,",
                "Meanwhile,",
                "By comparison,",
                "Whereas",
            ],
            'employment_impact': [
                "On the jobs front,",
                "For employment,",
                "Labor market impact:",
                "Job-wise,",
            ],
        },
        'element_templates': {
            'sector_current_state': "{sector} {metric} {recent_change}",
            'performance_context': "{performance_trend}",
            'key_drivers': "{driver_list}",
            'comparison': "{comparison_statement}",
            'employment_impact': "{employment_statement}",
            'forward_outlook': "{outlook_statement}",
        },
    },

    # -------------------------------------------------------------------------
    # HOLISTIC QUERIES
    # "How is the economy doing?" / "Economic health"
    # -------------------------------------------------------------------------
    'holistic': {
        'description': 'For broad questions about overall economic health',
        'required_elements': ['overall_assessment', 'key_indicators', 'main_dynamics'],
        'optional_elements': ['strengths', 'weaknesses', 'risks', 'opportunities', 'historical_comparison'],
        'structure': [
            'overall_assessment',  # "The economy is in a decent place, though showing signs of cooling"
            'growth_status',       # "GDP grew 2.8% last quarter, above trend"
            'labor_status',        # "The job market remains solid with 4.1% unemployment"
            'inflation_status',    # "Inflation has come down but remains above the Fed's 2% target"
            'key_tension',         # "The main tension: can inflation fall without a recession?"
            'forward_outlook',     # "Most indicators point to continued expansion with gradual cooling"
        ],
        'opening_patterns': [
            "The economy is {overall_assessment}",
            "On balance, the economic picture shows {summary_description}",
            "Economic conditions are {conditions_description}",
            "The US economy is currently {state_description}",
        ],
        'closing_patterns': [
            "The key question ahead: {key_question}",
            "Most indicators point toward {forward_direction}.",
            "The balance of risks is tilted toward {risk_tilt}.",
            "Watch for {key_factors} to signal the next phase.",
        ],
        'transitions': {
            'growth_status': [
                "On growth,",
                "Starting with output:",
                "GDP growth",
                "Looking at growth:",
            ],
            'labor_status': [
                "The labor market",
                "On jobs,",
                "Employment-wise,",
                "For workers,",
            ],
            'inflation_status': [
                "On prices,",
                "Inflation",
                "Price pressures",
                "For inflation,",
            ],
            'key_tension': [
                "The central tension:",
                "The key question:",
                "The main dynamic:",
                "What's driving uncertainty:",
            ],
        },
        'element_templates': {
            'overall_assessment': "{overall_state}",
            'growth_status': "GDP {growth_description}",
            'labor_status': "the labor market {labor_description}",
            'inflation_status': "{inflation_description}",
            'key_tension': "{tension_statement}",
            'forward_outlook': "{outlook_statement}",
        },
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_random_pattern(patterns: List[str]) -> str:
    """Select a random pattern from a list for natural variety."""
    return random.choice(patterns) if patterns else ""


def _fill_pattern(pattern: str, context: Dict[str, Any]) -> str:
    """
    Fill a pattern template with values from context.

    Handles missing values gracefully by returning empty string if critical
    placeholders are missing.

    Args:
        pattern: Template string with {placeholder} markers
        context: Dictionary of values to substitute

    Returns:
        Filled string with placeholders replaced, or empty if critical values missing
    """
    if not pattern:
        return ""

    # Find all placeholders in the pattern
    placeholders = re.findall(r'\{(\w+)\}', pattern)

    # Check if we have the essential values
    missing_critical = []
    for placeholder in placeholders:
        value = context.get(placeholder)
        if value is None or (isinstance(value, str) and not value.strip()):
            # Some placeholders are optional
            if placeholder not in ['units', 'date', 'caveat', 'assessment', 'implication_target',
                                   'forward_signal', 'uncertainty', 'implication']:
                missing_critical.append(placeholder)

    # If more than half the placeholders are missing, skip this element
    if missing_critical and len(missing_critical) > len(placeholders) / 2:
        return ""

    filled = pattern
    for placeholder in placeholders:
        value = context.get(placeholder, '')
        if value is None:
            value = ''
        filled = filled.replace(f'{{{placeholder}}}', str(value))

    # Clean up any leftover empty placeholders that look bad
    filled = re.sub(r'\s*\{\w+\}\s*', ' ', filled)
    filled = re.sub(r'\s+', ' ', filled)
    filled = re.sub(r'\s+([.,!?])', r'\1', filled)

    return filled.strip()


def _clean_narrative(text: str) -> str:
    """
    Clean up a narrative by fixing common issues.

    - Remove double spaces
    - Fix punctuation spacing
    - Ensure proper sentence capitalization
    - Remove redundant phrases
    - Fix awkward repeated patterns
    """
    if not text:
        return ""

    # Remove double spaces
    text = re.sub(r' +', ' ', text)

    # Fix common punctuation issues
    text = re.sub(r' +\.', '.', text)
    text = re.sub(r' +,', ',', text)
    text = re.sub(r'\.\.+', '.', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'\.\s*\.', '.', text)

    # Fix redundant transition patterns like "However, however" or "The X - the X"
    text = re.sub(r'([Hh]owever,?\s*)+however', 'However', text, flags=re.IGNORECASE)
    text = re.sub(r'([Tt]he\s+\w+\s*-?\s*)+the\s+', 'The ', text, flags=re.IGNORECASE)

    # Fix patterns like "Prediction markets show Prediction markets"
    text = re.sub(r'([A-Z][a-z]+\s+[a-z]+\s+[a-z]+)\s+\1', r'\1', text)

    # Fix patterns like "The Fed is focused on the Fed is focused on"
    text = re.sub(r'([Tt]he Fed is focused on)\s+\1', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'(this is)\s+\1', r'\1', text, flags=re.IGNORECASE)

    # Fix patterns like "in recent months in recent months"
    words = text.split()
    cleaned_words = []
    skip_until = -1
    for i, word in enumerate(words):
        if i < skip_until:
            continue
        # Check for 3-6 word repetition
        found_repeat = False
        for length in [6, 5, 4, 3]:
            if i + length * 2 <= len(words):
                phrase1 = ' '.join(words[i:i+length]).lower()
                phrase2 = ' '.join(words[i+length:i+length*2]).lower()
                if phrase1 == phrase2:
                    cleaned_words.extend(words[i:i+length])
                    skip_until = i + length * 2
                    found_repeat = True
                    break
        if not found_repeat:
            cleaned_words.append(word)
    text = ' '.join(cleaned_words)

    # Fix redundant phrases like "a gap of 3.1percentage points" (missing space)
    text = re.sub(r'(\d+\.?\d*)([a-zA-Z])', r'\1 \2', text)

    # Fix period followed by lowercase
    def fix_sentence_start(match):
        return match.group(1) + ' ' + match.group(2).upper()
    text = re.sub(r'(\.)[ ]+([a-z])', fix_sentence_start, text)

    # Fix redundant closing patterns (remove duplicate watch statements)
    text = re.sub(r'(The .{20,60}away\.)\s*The .{20,60}away\.', r'\1', text)

    # Fix redundant gap statements
    text = re.sub(r'(The gap is .{10,40}\.)\s*The gap is .{10,40}\.', r'\1', text)

    # Ensure starts with capital
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Ensure ends with period
    text = text.strip()
    if text and text[-1] not in '.!?':
        text += '.'

    return text


def _join_sentences(sentences: List[str], transitions: Dict[str, List[str]] = None) -> str:
    """
    Join sentences into a coherent paragraph with optional transitions.

    Args:
        sentences: List of sentence strings
        transitions: Optional dict mapping element names to transition phrases

    Returns:
        Joined paragraph string
    """
    if not sentences:
        return ""

    # Filter out empty sentences
    sentences = [s.strip() for s in sentences if s and s.strip()]

    if not sentences:
        return ""

    # Join with proper spacing
    result = sentences[0]
    for sentence in sentences[1:]:
        # Ensure previous ends with punctuation
        if result and result[-1] not in '.!?':
            result += '.'
        result += ' ' + sentence

    return result


def _format_value_with_units(value: Any, units: str = '') -> str:
    """
    Format a numeric value with appropriate units.

    Args:
        value: The numeric value
        units: Unit string (e.g., '%', 'pp', 'K')

    Returns:
        Formatted string like "4.1%" or "156K"
    """
    if value is None:
        return ""

    if isinstance(value, float):
        if abs(value) < 10:
            formatted = f"{value:.1f}"
        else:
            formatted = f"{value:.0f}"
    else:
        formatted = str(value)

    # Add units
    if units:
        if units == '%':
            return f"{formatted}%"
        elif units == 'pp':
            return f"{formatted} percentage points"
        elif units == 'K':
            return f"{formatted}K"
        elif units == 'M':
            return f"{formatted} million"
        elif units == 'B':
            return f"{formatted} billion"
        else:
            return f"{formatted} {units}"

    return formatted


def _get_trend_word(direction: str, intensity: str = 'moderate') -> str:
    """
    Get appropriate trend vocabulary based on direction and intensity.

    Args:
        direction: 'up', 'down', or 'flat'
        intensity: 'slight', 'moderate', or 'strong'

    Returns:
        Trend description word
    """
    trend_vocab = {
        'up': {
            'slight': ['edging up', 'inching higher', 'nudging up'],
            'moderate': ['rising', 'increasing', 'climbing'],
            'strong': ['surging', 'spiking', 'jumping'],
        },
        'down': {
            'slight': ['edging down', 'drifting lower', 'easing'],
            'moderate': ['falling', 'declining', 'dropping'],
            'strong': ['plunging', 'tumbling', 'collapsing'],
        },
        'flat': {
            'slight': ['holding steady', 'stable', 'unchanged'],
            'moderate': ['flat', 'stable', 'steady'],
            'strong': ['stubbornly flat', 'persistently unchanged', 'stuck'],
        },
    }

    vocab_list = trend_vocab.get(direction, {}).get(intensity, ['changing'])
    return random.choice(vocab_list)


def _interpret_gap(gap_value: float, gap_type: str = 'absolute') -> str:
    """
    Generate interpretation language for a gap between two values.

    Args:
        gap_value: The size of the gap
        gap_type: 'absolute', 'ratio', or 'percent'

    Returns:
        Descriptive phrase for the gap
    """
    if gap_type == 'ratio':
        if gap_value >= 2.0:
            return "more than double"
        elif gap_value >= 1.5:
            return "about 50% higher"
        elif gap_value >= 1.25:
            return "notably higher"
        elif gap_value >= 1.1:
            return "slightly higher"
        elif gap_value >= 0.9:
            return "roughly comparable"
        elif gap_value >= 0.75:
            return "somewhat lower"
        else:
            return "significantly lower"
    elif gap_type == 'percent':
        if abs(gap_value) >= 50:
            return "dramatically different"
        elif abs(gap_value) >= 25:
            return "substantially different"
        elif abs(gap_value) >= 10:
            return "notably different"
        elif abs(gap_value) >= 5:
            return "modestly different"
        else:
            return "roughly similar"
    else:  # absolute
        if abs(gap_value) >= 3:
            return "a substantial gap"
        elif abs(gap_value) >= 1.5:
            return "a meaningful gap"
        elif abs(gap_value) >= 0.5:
            return "a modest gap"
        else:
            return "a small difference"


# =============================================================================
# MAIN PUBLIC FUNCTIONS
# =============================================================================

def select_template(query: str, query_type: str) -> NarrativeTemplate:
    """
    Select the appropriate template for a query.

    Uses both the explicit query_type and analyzes the query text to
    determine the best template structure.

    Args:
        query: The original user query text
        query_type: The detected query type (e.g., 'trend', 'comparison')

    Returns:
        NarrativeTemplate object configured for this query type

    Example:
        >>> template = select_template("Is inflation coming down?", "trend")
        >>> template.query_type
        'trend'
    """
    # Get the template definition
    template_def = NARRATIVE_TEMPLATES.get(query_type)

    # Fall back to current_state if query type not found
    if not template_def:
        template_def = NARRATIVE_TEMPLATES['current_state']
        query_type = 'current_state'

    # Build the NarrativeTemplate object
    return NarrativeTemplate(
        query_type=query_type,
        required_elements=template_def.get('required_elements', []),
        optional_elements=template_def.get('optional_elements', []),
        structure=template_def.get('structure', []),
        opening_patterns=template_def.get('opening_patterns', []),
        closing_patterns=template_def.get('closing_patterns', []),
        transitions=template_def.get('transitions', {}),
    )


def fill_template(
    template: NarrativeTemplate,
    data_context: Dict[str, Any],
    insights: List[Dict[str, Any]],
) -> str:
    """
    Fill a template with actual data and insights.

    This is where the magic happens - taking structured elements
    and weaving them into coherent prose.

    Args:
        template: The NarrativeTemplate to fill
        data_context: Dictionary with data values and metadata, including:
            - indicator: Name of the indicator
            - value: Current value
            - units: Unit of measurement
            - date: Date of the reading
            - trend_direction: 'up', 'down', or 'flat'
            - trend_magnitude: Size of recent change
            - comparison_value: Value to compare against
            - target_value: Target or threshold value
            - And other template-specific fields
        insights: List of insight dictionaries with interpretations

    Returns:
        Natural language narrative string

    Example:
        >>> template = select_template("What is unemployment?", "current_state")
        >>> narrative = fill_template(template, {
        ...     'indicator': 'The unemployment rate',
        ...     'value': 4.1,
        ...     'units': '%',
        ...     'date': 'December 2024',
        ...     'historical_context': 'up from 3.5% a year ago',
        ...     'forward_outlook': 'watch for further cooling',
        ... }, [])
        >>> print(narrative)
        "The unemployment rate currently stands at 4.1%. This compares to..."
    """
    template_def = NARRATIVE_TEMPLATES.get(template.query_type, NARRATIVE_TEMPLATES['current_state'])

    # Build the narrative following the structure
    sections = []
    used_keys = set()

    # Opening - select the best pattern based on available context
    if template.opening_patterns:
        best_opening = None
        best_score = -1
        for pattern in template.opening_patterns:
            placeholders = re.findall(r'\{(\w+)\}', pattern)
            available = sum(1 for p in placeholders if data_context.get(p))
            if available > best_score:
                best_score = available
                best_opening = pattern
        if best_opening:
            opening = _fill_pattern(best_opening, data_context)
            if opening and len(opening) > 10:  # Only add if substantial
                sections.append(opening)
                # Track which data we've used
                for p in re.findall(r'\{(\w+)\}', best_opening):
                    used_keys.add(p)

    # Process each element in the structure
    for element in template.structure:
        # Skip if we already handled this in opening
        if element == 'direct_answer' and sections:
            continue

        # Get element template
        element_templates = template_def.get('element_templates', {})
        element_template = element_templates.get(element, '')

        # Fill the template
        filled_element = _fill_pattern(element_template, data_context)

        # If no template, try to get the value directly from context
        if not filled_element and element in data_context:
            value = data_context[element]
            if value and str(value).strip():
                filled_element = str(value)

        # Skip if nothing meaningful to add or it duplicates existing content
        if not filled_element or len(filled_element) < 5:
            continue

        # Check for duplication with existing sections
        normalized_filled = filled_element.lower()[:50]
        is_duplicate = any(normalized_filled in s.lower() for s in sections)
        if is_duplicate:
            continue

        # Add transition if available and we have previous sections
        transitions = template.transitions.get(element, [])
        if transitions and sections:
            transition = _get_random_pattern(transitions)
            if transition:
                filled_element = f"{transition} {filled_element}"

        sections.append(filled_element)

    # Add insights if provided (and not already covered)
    if insights:
        existing_text = ' '.join(sections).lower()
        for insight in insights[:2]:
            insight_text = insight.get('text', '') or insight.get('insight', '')
            if insight_text:
                # Only add if it contains new information
                insight_normalized = insight_text.lower()[:30]
                if insight_normalized not in existing_text:
                    sections.append(insight_text)

    # Closing - only if we have meaningful closing context
    if template.closing_patterns:
        best_closing = None
        best_score = -1
        for pattern in template.closing_patterns:
            placeholders = re.findall(r'\{(\w+)\}', pattern)
            available = sum(1 for p in placeholders if data_context.get(p))
            if available > best_score and available > 0:
                best_score = available
                best_closing = pattern

        if best_closing:
            closing = _fill_pattern(best_closing, data_context)
            if closing and len(closing) > 15:  # Only add if substantial
                existing_text = ' '.join(sections).lower()
                if closing.lower()[:30] not in existing_text:
                    sections.append(closing)

    # Join and clean
    narrative = _join_sentences(sections)
    narrative = _clean_narrative(narrative)

    return narrative


def generate_narrative(
    query: str,
    query_type: str,
    data_context: Dict[str, Any],
    insights: List[Dict[str, Any]] = None,
) -> str:
    """
    Main entry point - generate a complete narrative for a query.

    This function orchestrates the entire narrative generation process:
    1. Selects the appropriate template based on query type
    2. Fills the template with data and insights
    3. Returns polished, natural prose

    Args:
        query: The original user query text
        query_type: The detected query type. One of:
            - 'current_state': "What is X?"
            - 'trend': "Is X going up/down?"
            - 'comparison': "X vs Y"
            - 'demographic': "How is group X doing?"
            - 'recession': "Is a recession coming?"
            - 'fed_policy': "What will the Fed do?"
            - 'forecast': "Where is X heading?"
            - 'causal': "Why is X happening?"
            - 'sector': "How is sector X doing?"
            - 'holistic': "How is the economy doing?"
        data_context: Dictionary with all data values and metadata
        insights: Optional list of insight dictionaries

    Returns:
        Complete narrative string

    Example:
        >>> narrative = generate_narrative(
        ...     query="Is inflation coming down?",
        ...     query_type="trend",
        ...     data_context={
        ...         'indicator': 'CPI inflation',
        ...         'value': 3.2,
        ...         'units': '%',
        ...         'trend_direction': 'down',
        ...         'start_value': 9.1,
        ...         'start_date': 'June 2022',
        ...         'target_value': 2.0,
        ...         'target_name': "Fed's target",
        ...     },
        ...     insights=[],
        ... )
        >>> print(narrative)
        "Yes, CPI inflation is falling - from 9.1% (June 2022) to 3.2% today..."
    """
    insights = insights or []

    # Select the appropriate template
    template = select_template(query, query_type)

    # Fill the template
    narrative = fill_template(template, data_context, insights)

    # If we got an empty or very short narrative, provide a fallback
    if not narrative or len(narrative) < 20:
        # Build a simple fallback narrative
        indicator = data_context.get('indicator', 'The indicator')
        value = data_context.get('value', '')
        units = data_context.get('units', '')

        if value:
            narrative = f"{indicator} is currently at {_format_value_with_units(value, units)}."
        else:
            narrative = f"Data for {indicator} is being analyzed."

    return narrative


# =============================================================================
# CONVENIENCE FUNCTIONS FOR SPECIFIC QUERY TYPES
# =============================================================================

def generate_current_state_narrative(
    indicator: str,
    value: float,
    units: str = '%',
    date: str = '',
    historical_context: str = '',
    recent_trend: str = '',
    forward_outlook: str = '',
    economic_interpretation: str = '',
) -> str:
    """
    Generate a narrative for a current state query.

    Args:
        indicator: Name of the indicator (e.g., "The unemployment rate")
        value: Current value
        units: Unit of measurement
        date: Date of the reading
        historical_context: Context about historical levels (e.g., "up from 3.5% a year ago")
        recent_trend: Description of recent trend (e.g., "gradually rising")
        forward_outlook: Forward-looking statement
        economic_interpretation: What this level means economically

    Returns:
        Narrative string

    Example:
        >>> narrative = generate_current_state_narrative(
        ...     indicator='The unemployment rate',
        ...     value=4.1,
        ...     units='%',
        ...     date='December 2024',
        ...     historical_context='up from 3.5% a year ago but below the 5.7% long-term average',
        ...     recent_trend='gradually rising over the past six months',
        ...     forward_outlook='whether this stabilizes around 4% or continues climbing',
        ...     economic_interpretation='the labor market is cooling but remains solid',
        ... )
    """
    # Build a rich context for the template
    data_context = {
        'indicator': indicator,
        'value': value,
        'units': units,
        'date': date,
    }

    # Add optional context if provided
    if historical_context:
        data_context['historical_context'] = historical_context

    if recent_trend:
        data_context['recent_trend'] = recent_trend
        # Extract trend direction for templates
        if 'rising' in recent_trend.lower() or 'up' in recent_trend.lower():
            data_context['trend_direction'] = 'rising'
        elif 'falling' in recent_trend.lower() or 'down' in recent_trend.lower():
            data_context['trend_direction'] = 'falling'
        else:
            data_context['trend_direction'] = 'stable'

    if forward_outlook:
        data_context['forward_outlook'] = forward_outlook
        data_context['forward_signal'] = forward_outlook
        data_context['uncertainty'] = forward_outlook

    if economic_interpretation:
        data_context['economic_interpretation'] = economic_interpretation
        data_context['assessment'] = economic_interpretation

    return generate_narrative(
        query=f"What is {indicator}?",
        query_type='current_state',
        data_context=data_context,
    )


def generate_trend_narrative(
    indicator: str,
    trend_direction: str,
    start_value: float,
    end_value: float,
    start_date: str,
    units: str = '%',
    target_value: float = None,
    target_name: str = '',
    causal_factors: str = '',
    forward_statement: str = '',
    pace_description: str = '',
) -> str:
    """
    Generate a narrative for a trend query.

    Args:
        indicator: Name of the indicator
        trend_direction: 'rising', 'falling', or 'stable'
        start_value: Value at start of trend
        end_value: Current value
        start_date: Date when trend started
        units: Unit of measurement
        target_value: Target or threshold value
        target_name: Name of target (e.g., "Fed's 2% target")
        causal_factors: Description of factors driving the trend
        forward_statement: Forward-looking statement
        pace_description: How the pace has changed (e.g., "slowed", "accelerated")

    Returns:
        Narrative string

    Example:
        >>> narrative = generate_trend_narrative(
        ...     indicator='CPI inflation',
        ...     trend_direction='falling',
        ...     start_value=9.1,
        ...     end_value=3.2,
        ...     start_date='June 2022',
        ...     units='%',
        ...     target_value=2.0,
        ...     target_name="the Fed's 2% target",
        ...     causal_factors='goods disinflation and improving supply chains',
        ...     forward_statement='The last mile to 2% may prove the hardest',
        ...     pace_description='slowed in recent months as services remain sticky',
        ... )
    """
    # Calculate change metrics
    change_magnitude = abs(end_value - start_value)
    change_direction = 'increase' if end_value > start_value else 'decrease'
    change_noun = 'decline' if end_value < start_value else 'increase'

    # Determine affirmation based on trend
    affirmation = 'Yes' if trend_direction in ['rising', 'falling'] else 'No'

    data_context = {
        'indicator': indicator,
        'trend_direction': trend_direction,
        'start_value': start_value,
        'end_value': end_value,
        'start_date': start_date,
        'units': units,
        'change_magnitude': f"{change_magnitude:.1f}",
        'change_direction': change_direction,
        'change_noun': change_noun,
        'affirmation': affirmation,
        'value': end_value,
    }

    # Add target/distance context if provided
    if target_value is not None:
        distance = abs(end_value - target_value)
        distance_direction = 'above' if end_value > target_value else 'below'
        data_context.update({
            'target_value': target_value,
            'target_name': target_name or 'the target',
            'distance_value': f"{distance:.1f}",
            'distance_direction': distance_direction,
            'target_or_threshold': target_name or 'the target',
            'distance_description': f"{distance:.1f}{units}",
        })

    # Add causal factors
    if causal_factors:
        data_context['causal_factors'] = causal_factors

    # Add pace description
    if pace_description:
        data_context['pace_description'] = pace_description

    # Add forward statement with multiple keys for template flexibility
    if forward_statement:
        data_context['forward_statement'] = forward_statement
        data_context['forward_outlook'] = forward_statement
        data_context['forward_assessment'] = forward_statement
        data_context['projection_statement'] = forward_statement

    return generate_narrative(
        query=f"Is {indicator} {trend_direction}?",
        query_type='trend',
        data_context=data_context,
    )


def generate_comparison_narrative(
    indicator_a: str,
    value_a: float,
    indicator_b: str,
    value_b: float,
    units: str = '%',
    historical_gap_statement: str = '',
    explanation_factors: str = '',
    gap_trend_direction: str = '',
    forward_statement: str = '',
    gap_previous: str = '',
    gap_current: str = '',
) -> str:
    """
    Generate a narrative for a comparison query.

    Args:
        indicator_a: Name of first indicator (e.g., "Black unemployment")
        value_a: Value of first indicator
        indicator_b: Name of second indicator (e.g., "overall unemployment")
        value_b: Value of second indicator
        units: Unit of measurement
        historical_gap_statement: Historical context for the gap
        explanation_factors: Factors explaining the gap
        gap_trend_direction: How the gap is changing (e.g., "narrowed", "widened")
        forward_statement: Forward-looking statement
        gap_previous: Previous gap value for trend context
        gap_current: Current gap value for trend context

    Returns:
        Narrative string

    Example:
        >>> narrative = generate_comparison_narrative(
        ...     indicator_a='Black unemployment',
        ...     value_a=7.5,
        ...     indicator_b='overall unemployment',
        ...     value_b=4.4,
        ...     units='%',
        ...     historical_gap_statement='has persisted historically at 1.5-2x the overall rate',
        ...     explanation_factors='structural barriers including education access and geographic concentration',
        ...     gap_trend_direction='narrowed',
        ...     forward_statement='Tight labor markets tend to compress this gap',
        ... )
    """
    # Calculate gap metrics
    gap_value = value_a - value_b
    gap_ratio = value_a / value_b if value_b != 0 else 0
    gap_percent = ((value_a / value_b) - 1) * 100 if value_b != 0 else 0

    gap_description = 'gap' if gap_value > 0 else 'deficit'
    comparison_word = 'exceeds' if gap_value > 0 else 'trails'

    # Build context
    data_context = {
        'indicator_a': indicator_a,
        'value_a': value_a,
        'indicator_b': indicator_b,
        'value_b': value_b,
        'units': units,
        'gap_value': f"{abs(gap_value):.1f}",
        'gap_percent': f"{abs(gap_percent):.0f}",
        'gap_description': gap_description,
        'gap_units': 'percentage points' if units == '%' else units,
        'comparison_word': comparison_word,
    }

    # Add gap ratio interpretation
    if gap_ratio >= 1.5:
        data_context['gap_interpretation'] = f"roughly {gap_ratio:.1f}x higher"
    elif gap_ratio >= 1.1:
        data_context['gap_interpretation'] = f"about {abs(gap_percent):.0f}% higher"
    elif gap_ratio <= 0.67:
        data_context['gap_interpretation'] = f"roughly {1/gap_ratio:.1f}x lower"

    # Add optional context
    if historical_gap_statement:
        data_context['historical_gap_statement'] = historical_gap_statement

    if explanation_factors:
        data_context['explanation_factors'] = explanation_factors

    if gap_trend_direction:
        data_context['gap_trend_direction'] = gap_trend_direction
        data_context['gap_implication'] = f"the disparity is {gap_trend_direction.replace('ing', 'ing')}"

    if gap_previous:
        data_context['gap_previous'] = gap_previous

    if gap_current:
        data_context['gap_current'] = gap_current

    if forward_statement:
        data_context['forward_statement'] = forward_statement
        data_context['gap_behavior'] = forward_statement

    return generate_narrative(
        query=f"{indicator_a} vs {indicator_b}",
        query_type='comparison',
        data_context=data_context,
    )


def get_available_query_types() -> List[str]:
    """
    Get list of all available query types.

    Returns:
        List of query type strings
    """
    return list(NARRATIVE_TEMPLATES.keys())


def get_template_description(query_type: str) -> str:
    """
    Get a description of what a template is for.

    Args:
        query_type: The query type

    Returns:
        Description string
    """
    template_def = NARRATIVE_TEMPLATES.get(query_type, {})
    return template_def.get('description', f'Template for {query_type} queries')


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("NARRATIVE TEMPLATES - TEST SUITE")
    print("=" * 70)

    # Test 1: Current State
    print("\n--- Test 1: Current State Query ---")
    print("Query: 'What is unemployment?'\n")

    narrative = generate_current_state_narrative(
        indicator='The unemployment rate',
        value=4.1,
        units='%',
        date='December 2024',
        historical_context='up from 3.5% a year ago but below the 5.7% long-term average',
        recent_trend='gradually rising over the past six months',
        forward_outlook='whether this stabilizes around 4% or continues climbing toward 4.5%',
        economic_interpretation='the labor market is cooling but remains solid',
    )
    print(f"Narrative:\n{narrative}")

    # Test 2: Trend
    print("\n--- Test 2: Trend Query ---")
    print("Query: 'Is inflation coming down?'\n")

    narrative = generate_trend_narrative(
        indicator='CPI inflation',
        trend_direction='falling',
        start_value=9.1,
        end_value=3.2,
        start_date='June 2022',
        units='%',
        target_value=2.0,
        target_name="the Fed's 2% target",
        causal_factors='goods disinflation and improving supply chains, though services remain sticky',
        forward_statement='The last mile to 2% may prove the hardest as shelter inflation lags',
        pace_description='slowed in recent months',
    )
    print(f"Narrative:\n{narrative}")

    # Test 3: Comparison
    print("\n--- Test 3: Comparison Query ---")
    print("Query: 'Black unemployment vs overall'\n")

    narrative = generate_comparison_narrative(
        indicator_a='Black unemployment',
        value_a=7.5,
        indicator_b='overall unemployment',
        value_b=4.4,
        units='%',
        historical_gap_statement='has persisted historically, typically running 1.5-2x the overall rate',
        explanation_factors='structural barriers including disparities in education access, geographic concentration in areas with fewer jobs, and hiring practices',
        gap_trend_direction='narrowed slightly',
        gap_previous='3.8 percentage points at pandemic peak',
        gap_current='3.1 percentage points today',
        forward_statement='Tight labor markets historically help compress this gap as employers expand their hiring pools',
    )
    print(f"Narrative:\n{narrative}")

    # Test 4: Recession
    print("\n--- Test 4: Recession Query ---")
    print("Query: 'Is a recession coming?'\n")

    narrative = generate_narrative(
        query="Is a recession coming?",
        query_type='recession',
        data_context={
            'risk_level': 'elevated',
            'summary_assessment': 'a soft landing remains the base case, though risks persist',
            'bottom_line_assessment': 'Recession risk is elevated but not imminent - the classic signals are mixed',
            'signal_list': 'the yield curve has been inverted for 18 months (a reliable historical signal), while the Sahm Rule indicator sits at 0.4 (just below the 0.5 trigger)',
            'historical_context': 'yield curve inversion has preceded every recession since 1970, though the timing varies from 6 to 24 months',
            'positive_factors': 'the labor market remains resilient with solid job gains, low initial claims, and consumers continuing to spend',
            'probability_statement': 'Prediction markets put 12-month recession odds at 25%, down from 35% earlier this year',
            'watch_indicators': 'initial jobless claims, monthly payroll gains, and consumer spending trends',
            'crucial_factors': 'whether unemployment rises above the Sahm threshold',
        },
    )
    print(f"Narrative:\n{narrative}")

    # Test 5: Fed Policy
    print("\n--- Test 5: Fed Policy Query ---")
    print("Query: 'Will the Fed cut rates?'\n")

    narrative = generate_narrative(
        query="Will the Fed cut rates?",
        query_type='fed_policy',
        data_context={
            'rate_range': '4.25-4.50%',
            'stance_description': 'moderately restrictive by historical standards',
            'stance_label': 'restrictive',
            'real_rate': '1.5',
            'data_dependencies': 'continued progress on inflation (especially services) and gradual labor market cooling',
            'rate_path_projection': 'the December dot plot suggests 2 cuts in 2025, though markets are pricing a bit more easing',
            'risk_factors': 'sticky services inflation or a reacceleration in the labor market could delay cuts',
            'data_points': 'core PCE inflation and monthly payroll data',
            'fed_guidance': 'data-dependent approach with no preset path for rate cuts',
        },
    )
    print(f"Narrative:\n{narrative}")

    # Test 6: Demographic Query
    print("\n--- Test 6: Demographic Query ---")
    print("Query: 'How are women doing in the labor market?'\n")

    narrative = generate_narrative(
        query="How are women doing in the labor market?",
        query_type='demographic',
        data_context={
            'demographic_group': 'women',
            'indicator': 'unemployment',
            'value': 3.9,
            'units': '%',
            'overall_value': 4.1,
            'gap_value': 0.2,
            'gap_units': 'percentage points',
            'gap_historical_comparison': 'is typical - women have had slightly lower unemployment for the past two decades',
            'lfpr_value': 57.7,
            'lfpr_comparison': 'up from 56.1% pre-pandemic but still below the 60% peak from the early 2000s',
            'structural_factors': 'childcare availability and costs continue to affect participation, particularly for mothers of young children',
            'progress_statement': 'the gender gap in employment has narrowed considerably over the past 50 years',
            'forward_statement': 'Childcare policies and remote work flexibility could further boost participation',
        },
    )
    print(f"Narrative:\n{narrative}")

    # Test 7: Holistic Query
    print("\n--- Test 7: Holistic Query ---")
    print("Query: 'How is the economy doing?'\n")

    narrative = generate_narrative(
        query="How is the economy doing?",
        query_type='holistic',
        data_context={
            'overall_assessment': 'in a surprisingly strong position despite headwinds',
            'overall_state': 'performing above expectations, with resilient growth despite high interest rates',
            'growth_description': 'came in at 2.8% in Q3, above the 2% trend pace',
            'labor_description': 'remains solid with 4.1% unemployment and steady job gains',
            'inflation_description': 'has fallen sharply but remains above the Fed\'s 2% target at 3.2%',
            'tension_statement': 'Can inflation return to 2% without a recession? The soft landing scenario remains in play',
            'outlook_statement': 'Most indicators point to continued expansion with gradual cooling - a soft landing remains the base case',
            'key_question': 'whether the Fed can stick the landing as it navigates the last mile on inflation',
        },
    )
    print(f"Narrative:\n{narrative}")

    # Print available query types
    print("\n--- Available Query Types ---")
    for qt in get_available_query_types():
        print(f"  - {qt}: {get_template_description(qt)}")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
