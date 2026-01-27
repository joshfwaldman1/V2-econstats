"""
Causal chain models for economic dynamics.

This module provides structured representations of economic transmission mechanisms,
helping analysts understand how shocks propagate through the economy.

Modules:
    monetary: Federal Reserve policy transmission chains (rate -> housing, consumption, labor)
    inflation: Inflation dynamics chains (demand-pull, cost-push, shelter, wage-price spiral)
"""

# Monetary policy transmission chains
from .monetary import (
    # Chain definitions
    RATE_TO_HOUSING,
    RATE_TO_CONSUMPTION,
    RATE_TO_LABOR,
    CHAINS as MONETARY_CHAINS,

    # Detection and explanation
    detect_chain_position,
    explain_chain_position,

    # Utilities
    get_chain_series,
    get_all_chain_series,
    summarize_all_chains,
)

# Inflation dynamics chains
from .inflation import (
    # Chain definitions
    DEMAND_PULL,
    COST_PUSH,
    SHELTER_INFLATION,
    WAGE_PRICE_SPIRAL,

    # Detection and interpretation
    detect_chain_position as detect_inflation_chain_position,
    interpret_inflation_dynamics,
    get_current_inflation_narrative,

    # Data structures
    CausalChain,
    ChainStage,
    ChainPosition,
    ChainStatus,
)

__all__ = [
    # Monetary chains
    "RATE_TO_HOUSING",
    "RATE_TO_CONSUMPTION",
    "RATE_TO_LABOR",
    "MONETARY_CHAINS",
    "detect_chain_position",
    "explain_chain_position",
    "get_chain_series",
    "get_all_chain_series",
    "summarize_all_chains",

    # Inflation chains
    "DEMAND_PULL",
    "COST_PUSH",
    "SHELTER_INFLATION",
    "WAGE_PRICE_SPIRAL",
    "detect_inflation_chain_position",
    "interpret_inflation_dynamics",
    "get_current_inflation_narrative",

    # Shared data structures
    "CausalChain",
    "ChainStage",
    "ChainPosition",
    "ChainStatus",
]
