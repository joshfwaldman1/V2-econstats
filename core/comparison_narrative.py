"""
Comparison Narrative Generator

Generates human-readable narratives for temporal comparison queries.

For "How has unemployment changed since pre-pandemic?":
→ "Unemployment has risen 0.6 percentage points from 3.5% (Feb 2020) to 4.1% today.
   This represents a 17% increase from pre-pandemic levels."

NOT: "Showing pre-COVID data through February 2020."

The key insight: Comparison narratives should emphasize the CHANGE between periods,
not just describe what data is being shown.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from .temporal_intent import TemporalIntent
from .multi_period_fetcher import MultiPeriodData, ComparisonMetric


def generate_comparison_narrative(
    intent: TemporalIntent,
    data: MultiPeriodData,
    query: str = ""
) -> str:
    """
    Generate a narrative that directly answers a comparison query.

    Args:
        intent: The detected temporal intent
        data: MultiPeriodData with comparison metrics
        query: Original query for context

    Returns:
        Human-readable comparison narrative
    """
    if not data.has_comparison_data:
        return _generate_no_comparison_fallback(intent, data)

    # Build narrative from comparison metrics
    narratives = []

    for series_id, metric in data.comparison_metrics.items():
        narrative = format_metric_narrative(metric)
        if narrative:
            narratives.append(narrative)

    if not narratives:
        return _generate_no_comparison_fallback(intent, data)

    # Combine narratives
    if len(narratives) == 1:
        return narratives[0]
    else:
        # Multiple series: lead with summary, then details
        return _combine_multiple_narratives(narratives, intent)


def format_metric_narrative(metric: ComparisonMetric) -> str:
    """
    Format a single comparison metric as natural language.

    Adapts formatting based on:
    - Units (percent, percentage points, index, thousands)
    - Direction (up, down, flat)
    - Magnitude (small vs large changes)

    Args:
        metric: The computed comparison metric

    Returns:
        Human-readable string describing the change
    """
    name = _simplify_series_name(metric.series_name)
    direction_word = _get_direction_word(metric)

    # Format values based on units
    if _is_rate_series(metric):
        return _format_rate_change(metric, name, direction_word)
    elif _is_index_series(metric):
        return _format_index_change(metric, name, direction_word)
    elif _is_jobs_series(metric):
        return _format_jobs_change(metric, name, direction_word)
    else:
        return _format_generic_change(metric, name, direction_word)


def _format_rate_change(metric: ComparisonMetric, name: str, direction: str) -> str:
    """
    Format change in a rate/percentage (like unemployment, inflation).

    Uses percentage points for the absolute change.
    """
    pp_change = metric.absolute_change
    ref_date = _format_date(metric.reference_date)
    primary_date = _format_date(metric.primary_date)

    # Build the narrative
    if metric.direction == "flat":
        return (
            f"{name} has remained essentially unchanged at {metric.primary_value:.1f}%, "
            f"compared to {metric.reference_value:.1f}% in {ref_date}."
        )

    sign = "+" if pp_change > 0 else ""

    return (
        f"{name} has {direction} {abs(pp_change):.1f} percentage points, "
        f"from {metric.reference_value:.1f}% ({ref_date}) to {metric.primary_value:.1f}% ({primary_date}). "
        f"This represents a {abs(metric.percent_change):.0f}% "
        f"{'increase' if metric.percent_change > 0 else 'decrease'} from {metric.period_label.replace('vs ', '')} levels."
    )


def _format_index_change(metric: ComparisonMetric, name: str, direction: str) -> str:
    """Format change in an index (like CPI, GDP deflator)."""
    ref_date = _format_date(metric.reference_date)
    primary_date = _format_date(metric.primary_date)

    if metric.direction == "flat":
        return (
            f"{name} has remained stable at {metric.primary_value:.1f}, "
            f"compared to {metric.reference_value:.1f} in {ref_date}."
        )

    return (
        f"{name} has {direction} {metric.percent_change:.1f}% "
        f"from {metric.reference_value:.1f} ({ref_date}) to {metric.primary_value:.1f} ({primary_date})."
    )


def _format_jobs_change(metric: ComparisonMetric, name: str, direction: str) -> str:
    """Format change in employment (payrolls, jobs)."""
    ref_date = _format_date(metric.reference_date)
    primary_date = _format_date(metric.primary_date)

    # Convert to millions if large
    if abs(metric.primary_value) > 10000:
        primary_fmt = f"{metric.primary_value / 1000:.1f} million"
        ref_fmt = f"{metric.reference_value / 1000:.1f} million"
        change_fmt = f"{abs(metric.absolute_change) / 1000:.1f} million"
    else:
        primary_fmt = f"{metric.primary_value:,.0f}K"
        ref_fmt = f"{metric.reference_value:,.0f}K"
        change_fmt = f"{abs(metric.absolute_change):,.0f}K"

    if metric.direction == "flat":
        return (
            f"{name} has remained essentially unchanged at {primary_fmt}, "
            f"similar to {ref_date} levels."
        )

    return (
        f"The economy has {'added' if direction == 'risen' else 'lost'} {change_fmt} jobs "
        f"since {ref_date}, with {name} {'rising' if direction == 'risen' else 'falling'} "
        f"from {ref_fmt} to {primary_fmt} ({primary_date})."
    )


def _format_generic_change(metric: ComparisonMetric, name: str, direction: str) -> str:
    """Format change for generic series."""
    ref_date = _format_date(metric.reference_date)
    primary_date = _format_date(metric.primary_date)

    if metric.direction == "flat":
        return (
            f"{name} has remained stable at {metric.primary_value:.2f}, "
            f"compared to {metric.reference_value:.2f} in {ref_date}."
        )

    return (
        f"{name} has {direction} {abs(metric.percent_change):.1f}%, "
        f"from {metric.reference_value:.2f} ({ref_date}) to {metric.primary_value:.2f} ({primary_date})."
    )


def _combine_multiple_narratives(narratives: list[str], intent: TemporalIntent) -> str:
    """
    Combine multiple series narratives into a cohesive summary.

    For job market comparisons, provides an overall assessment.
    """
    reference_label = intent.reference_label or "the reference period"

    # Lead with overall framing
    intro = f"Compared to {reference_label}:\n\n"

    # Add individual narratives as bullet points
    bullet_points = [f"- {n}" for n in narratives]

    return intro + "\n".join(bullet_points)


def _generate_no_comparison_fallback(intent: TemporalIntent, data: MultiPeriodData) -> str:
    """
    Generate fallback narrative when comparison data is unavailable.

    This happens when:
    - Reference period has no data
    - Series doesn't extend back far enough
    """
    if intent.reference_period:
        ref_label = intent.reference_period.get("label", "the reference period")
        return (
            f"Unable to generate a comparison with {ref_label}. "
            f"The requested data may not extend back far enough, or may not be available for that period. "
            f"Showing all available data instead."
        )

    return "Showing available data."


def _simplify_series_name(name: str) -> str:
    """
    Simplify verbose FRED series names for readability.

    "Unemployment Rate" → "The unemployment rate"
    "All Employees, Total Nonfarm" → "Total nonfarm employment"
    """
    # Common simplifications
    simplifications = {
        "Unemployment Rate": "The unemployment rate",
        "All Employees, Total Nonfarm": "Total nonfarm employment",
        "All Employees: Total Nonfarm": "Total nonfarm employment",
        "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average": "Consumer prices (CPI)",
        "Gross Domestic Product": "Real GDP",
        "Real Gross Domestic Product": "Real GDP",
        "Personal Consumption Expenditures: Chain-type Price Index": "PCE inflation",
        "Federal Funds Effective Rate": "The federal funds rate",
        "Initial Claims": "Initial unemployment claims",
    }

    for verbose, simple in simplifications.items():
        if verbose.lower() in name.lower():
            return simple

    # Default: add "The" if it's a rate, otherwise return as-is
    if "rate" in name.lower() and not name.lower().startswith("the "):
        return f"The {name.lower()}"

    return name


def _get_direction_word(metric: ComparisonMetric) -> str:
    """Get appropriate direction word based on context."""
    if metric.direction == "up":
        return "risen"
    elif metric.direction == "down":
        return "fallen"
    else:
        return "remained stable"


def _is_rate_series(metric: ComparisonMetric) -> bool:
    """Check if series is a rate/percentage."""
    units_lower = metric.units.lower() if metric.units else ""
    name_lower = metric.series_name.lower()

    return (
        "percent" in units_lower or
        "rate" in name_lower or
        "%" in metric.units or
        "unemployment" in name_lower or
        "inflation" in name_lower
    )


def _is_index_series(metric: ComparisonMetric) -> bool:
    """Check if series is an index."""
    units_lower = metric.units.lower() if metric.units else ""
    name_lower = metric.series_name.lower()

    return (
        "index" in units_lower or
        "index" in name_lower or
        "cpi" in name_lower.replace(" ", "")
    )


def _is_jobs_series(metric: ComparisonMetric) -> bool:
    """Check if series is employment/jobs related."""
    name_lower = metric.series_name.lower()

    return (
        "employees" in name_lower or
        "employment" in name_lower or
        "payroll" in name_lower or
        "jobs" in name_lower or
        "nonfarm" in name_lower
    )


def _format_date(date_str: str) -> str:
    """
    Format ISO date string to human-readable.

    "2020-02-01" → "February 2020"
    "2024-11-01" → "November 2024"
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%B %Y")
    except (ValueError, TypeError):
        return date_str or "unknown date"


def format_comparison_insight(metric: ComparisonMetric) -> str:
    """
    Generate a single-line insight for a comparison metric.

    Useful for metric cards and quick summaries.

    Returns text like:
    - "↑ 0.6 pp since Feb 2020"
    - "↓ 2.3M jobs vs pre-pandemic"
    """
    if metric.direction == "up":
        arrow = "↑"
    elif metric.direction == "down":
        arrow = "↓"
    else:
        arrow = "→"

    if _is_rate_series(metric):
        return f"{arrow} {abs(metric.absolute_change):.1f} pp {metric.period_label}"
    elif _is_jobs_series(metric) and abs(metric.absolute_change) > 1000:
        change_m = abs(metric.absolute_change) / 1000
        return f"{arrow} {change_m:.1f}M jobs {metric.period_label}"
    else:
        return f"{arrow} {abs(metric.percent_change):.1f}% {metric.period_label}"


# Quick test
if __name__ == "__main__":
    # Create mock metric for testing
    mock_metric = ComparisonMetric(
        series_id="UNRATE",
        series_name="Unemployment Rate",
        primary_value=4.1,
        reference_value=3.5,
        primary_date="2024-11-01",
        reference_date="2020-02-01",
        absolute_change=0.6,
        percent_change=17.14,
        direction="up",
        units="Percent",
        period_label="vs Pre-pandemic (Feb 2020)"
    )

    print("Testing Comparison Narrative Generator\n" + "=" * 50)

    print("\nRate series (unemployment):")
    print(format_metric_narrative(mock_metric))

    print("\nShort insight:")
    print(format_comparison_insight(mock_metric))

    # Test jobs series
    jobs_metric = ComparisonMetric(
        series_id="PAYEMS",
        series_name="All Employees, Total Nonfarm",
        primary_value=159000,
        reference_value=152000,
        primary_date="2024-11-01",
        reference_date="2020-02-01",
        absolute_change=7000,
        percent_change=4.6,
        direction="up",
        units="Thousands of Persons",
        period_label="vs Pre-pandemic (Feb 2020)"
    )

    print("\nJobs series (payrolls):")
    print(format_metric_narrative(jobs_metric))
