"""
Economic Analysis Frameworks

This package provides frameworks for analyzing economic data
from FRED and other sources.

Available Frameworks:
- labor_market: Beveridge Curve, Sahm Rule, Labor Market Heat
- fed_policy: Taylor Rule, Financial Conditions, Fed Reaction Function
- recession: Recession indicators and probability models
"""

from .labor_market import (
    # Beveridge Curve
    calculate_beveridge_curve,
    interpret_beveridge_curve,
    BEVERIDGE_CURVE_SERIES,
    BeveridgePosition,

    # Sahm Rule
    calculate_sahm_rule,
    interpret_sahm_rule,
    SAHM_RULE_SERIES,
    SAHM_THRESHOLD,

    # Labor Market Heat
    calculate_labor_market_heat,
    interpret_labor_market_heat,
    LABOR_MARKET_HEAT_SERIES,
    HEAT_BENCHMARKS,

    # Convenience functions
    get_all_required_series,
    analyze_labor_market,
)

from .fed_policy import (
    # Taylor Rule
    TaylorRuleResult,
    calculate_taylor_rule,
    interpret_taylor_rule,

    # Financial Conditions
    FinancialConditionsResult,
    calculate_financial_conditions,
    interpret_financial_conditions,

    # Fed Reaction Function
    FedReactionResult,
    calculate_fed_reaction,
    interpret_fed_reaction,

    # Combined Analysis
    full_fed_policy_analysis,
)

from .recession import (
    # Data classes
    YieldCurveSignal,
    LeadingIndicator,
    LeadingIndicatorsComposite,
    RecessionProbability,
    ExpansionAge,
    # Analysis functions
    analyze_yield_curve,
    analyze_leading_indicators,
    calculate_recession_probability,
    calculate_expansion_age,
    get_recession_dashboard,
    # Constants
    NBER_RECESSION_DATES,
    HISTORICAL_EXPANSIONS,
    AVERAGE_EXPANSION_MONTHS,
    MEDIAN_EXPANSION_MONTHS,
    LAST_RECESSION_END,
)

__all__ = [
    # Beveridge Curve
    "calculate_beveridge_curve",
    "interpret_beveridge_curve",
    "BEVERIDGE_CURVE_SERIES",
    "BeveridgePosition",

    # Sahm Rule
    "calculate_sahm_rule",
    "interpret_sahm_rule",
    "SAHM_RULE_SERIES",
    "SAHM_THRESHOLD",

    # Labor Market Heat
    "calculate_labor_market_heat",
    "interpret_labor_market_heat",
    "LABOR_MARKET_HEAT_SERIES",
    "HEAT_BENCHMARKS",

    # Convenience
    "get_all_required_series",
    "analyze_labor_market",

    # Fed Policy - Taylor Rule
    "TaylorRuleResult",
    "calculate_taylor_rule",
    "interpret_taylor_rule",

    # Fed Policy - Financial Conditions
    "FinancialConditionsResult",
    "calculate_financial_conditions",
    "interpret_financial_conditions",

    # Fed Policy - Reaction Function
    "FedReactionResult",
    "calculate_fed_reaction",
    "interpret_fed_reaction",

    # Fed Policy - Combined
    "full_fed_policy_analysis",

    # Recession Framework - Data Classes
    "YieldCurveSignal",
    "LeadingIndicator",
    "LeadingIndicatorsComposite",
    "RecessionProbability",
    "ExpansionAge",

    # Recession Framework - Functions
    "analyze_yield_curve",
    "analyze_leading_indicators",
    "calculate_recession_probability",
    "calculate_expansion_age",
    "get_recession_dashboard",

    # Recession Framework - Constants
    "NBER_RECESSION_DATES",
    "HISTORICAL_EXPANSIONS",
    "AVERAGE_EXPANSION_MONTHS",
    "MEDIAN_EXPANSION_MONTHS",
    "LAST_RECESSION_END",
]
