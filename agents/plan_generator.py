#!/usr/bin/env python3
"""
Unified Plan Generator for EconStats.

This replaces the 9 individual agent_*.py files with a single generator
that reads configs from plan_configs/ directory.

Usage:
    python plan_generator.py                 # Generate all plans
    python plan_generator.py employment      # Generate only employment plans
    python plan_generator.py employment inflation  # Generate specific domains
"""

import sys
import importlib
import os

# Add the agents directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_base import process_prompts

# Domain configurations - maps domain name to output file and category display name
DOMAINS = {
    "employment": {
        "output": "plans_employment.json",
        "category": "Employment & Labor",
    },
    "inflation": {
        "output": "plans_inflation.json",
        "category": "Inflation & Prices",
    },
    "gdp": {
        "output": "plans_gdp.json",
        "category": "GDP & Growth",
    },
    "housing": {
        "output": "plans_housing.json",
        "category": "Housing",
    },
    "fed_rates": {
        "output": "plans_fed_rates.json",
        "category": "Fed & Interest Rates",
    },
    "consumer": {
        "output": "plans_consumer.json",
        "category": "Consumer & Sentiment",
    },
    "demographics": {
        "output": "plans_demographics.json",
        "category": "Demographics",
    },
    "economy_overview": {
        "output": "plans_economy_overview.json",
        "category": "Economy Overview",
    },
    "trade_markets": {
        "output": "plans_trade_markets.json",
        "category": "Trade & Markets",
    },
}


def generate_plans(domain: str) -> dict:
    """
    Generate plans for a single domain.

    Args:
        domain: Domain name (e.g., "employment", "inflation")

    Returns:
        Generated plans dict
    """
    if domain not in DOMAINS:
        print(f"Unknown domain: {domain}")
        print(f"Available domains: {', '.join(DOMAINS.keys())}")
        return {}

    config = DOMAINS[domain]

    # Import the domain config module
    try:
        config_module = importlib.import_module(f"plan_configs.{domain}")
    except ImportError as e:
        print(f"Could not import plan_configs.{domain}: {e}")
        return {}

    # Get EXPERT_PROMPT and PROMPTS from the config
    expert_prompt = getattr(config_module, "EXPERT_PROMPT", None)
    prompts = getattr(config_module, "PROMPTS", None)

    if not expert_prompt or not prompts:
        print(f"Config for {domain} missing EXPERT_PROMPT or PROMPTS")
        return {}

    # Generate the output path
    agents_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(agents_dir, config["output"])

    # Run the plan generation
    return process_prompts(
        prompts,
        expert_prompt,
        output_path,
        config["category"]
    )


def generate_all_plans():
    """Generate plans for all domains."""
    results = {}
    for domain in DOMAINS:
        print(f"\n{'#' * 60}")
        print(f"# Generating: {domain.upper()}")
        print(f"{'#' * 60}")
        results[domain] = generate_plans(domain)
    return results


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Generate specific domains
        domains = sys.argv[1:]
        for domain in domains:
            generate_plans(domain)
    else:
        # Generate all domains
        generate_all_plans()


if __name__ == "__main__":
    main()
