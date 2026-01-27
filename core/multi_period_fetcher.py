"""
Multi-Period Data Fetcher

Handles fetching data for multiple time periods when a query involves temporal
comparisons (e.g., "Compare unemployment to pre-pandemic").

For COMPARE intents:
- Fetches FULL data range (no filtering)
- Extracts values from both primary (current) and reference (historical) periods
- Computes comparison metrics (absolute change, percent change, direction)

This ensures queries like "since pre-pandemic" get CURRENT data compared AGAINST
the pre-pandemic baseline, NOT filtered TO pre-pandemic only.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import statistics

from .temporal_intent import TemporalIntent, get_comparison_baseline_date
from .data_fetcher import DataFetcher, SeriesData


@dataclass
class ComparisonMetric:
    """
    Computed comparison between two time periods for a single series.

    Example: For unemployment comparing current (4.1%) vs pre-pandemic (3.5%):
    - primary_value: 4.1
    - reference_value: 3.5
    - absolute_change: 0.6
    - percent_change: 17.1 (percent increase)
    - direction: "up"
    """
    series_id: str
    series_name: str

    # Values from each period
    primary_value: float
    reference_value: float
    primary_date: str
    reference_date: str

    # Computed changes
    absolute_change: float
    percent_change: float  # (new - old) / old * 100
    direction: str  # "up", "down", "flat"

    # For context
    units: str = ""
    period_label: str = ""  # e.g., "vs Pre-pandemic (Feb 2020)"

    def __str__(self) -> str:
        """Human-readable summary."""
        sign = "+" if self.absolute_change >= 0 else ""
        return (
            f"{self.series_name}: {self.primary_value:.2f} "
            f"({sign}{self.absolute_change:.2f}, {sign}{self.percent_change:.1f}%) "
            f"{self.period_label}"
        )


@dataclass
class MultiPeriodData:
    """
    Data fetched for a temporal comparison query.

    Contains:
    - full_data: Complete time series (for charting)
    - primary_data: Data from the primary/current period
    - reference_data: Data from the reference/historical period
    - comparison_metrics: Computed comparisons for each series
    """
    # Full data for charting (no filtering applied)
    full_data: dict[str, SeriesData] = field(default_factory=dict)

    # Extracted period data
    primary_data: dict[str, list] = field(default_factory=dict)  # {series_id: [(date, value), ...]}
    reference_data: dict[str, list] = field(default_factory=dict)

    # Comparison results
    comparison_metrics: dict[str, ComparisonMetric] = field(default_factory=dict)

    # Metadata
    primary_label: str = "Current"
    reference_label: str = "Reference"
    intent: Optional[TemporalIntent] = None

    @property
    def has_comparison_data(self) -> bool:
        """Check if we have data from both periods for comparison."""
        return bool(self.comparison_metrics)

    def get_metric(self, series_id: str) -> Optional[ComparisonMetric]:
        """Get comparison metric for a specific series."""
        return self.comparison_metrics.get(series_id)


def fetch_multi_period_data(
    series_ids: list[str],
    intent: TemporalIntent,
    years: int = None
) -> MultiPeriodData:
    """
    Fetch data for multiple time periods based on temporal intent.

    For COMPARE intents:
    - Fetches full data (no date filtering)
    - Extracts values from primary and reference periods
    - Computes comparison metrics

    For FILTER intents:
    - Fetches full data but marks filter bounds
    - Does NOT compute comparisons (single period)

    For CURRENT intents:
    - Just fetches recent data normally

    Args:
        series_ids: List of series IDs to fetch
        intent: The detected temporal intent
        years: Optional limit to last N years (None = all available)

    Returns:
        MultiPeriodData with full data and computed comparisons
    """
    fetcher = DataFetcher()

    # Always fetch full data (no date filtering for comparisons)
    full_data = fetcher.fetch_multiple(series_ids, years=years)

    result = MultiPeriodData(
        full_data=full_data,
        intent=intent,
        primary_label=intent.primary_period.get("label", "Current") if intent.primary_period else "Current",
        reference_label=intent.reference_label or "Reference"
    )

    # For comparison intents, extract period data and compute metrics
    if intent.is_comparison and intent.reference_period:
        for series_id, data in full_data.items():
            if data.is_empty or data.error:
                continue

            # Extract data for each period
            primary_values = _extract_period_data(
                data,
                intent.primary_period.get("start") if intent.primary_period else None,
                intent.primary_period.get("end") if intent.primary_period else None
            )

            reference_values = _extract_period_data(
                data,
                intent.reference_period.get("start"),
                intent.reference_period.get("end")
            )

            result.primary_data[series_id] = primary_values
            result.reference_data[series_id] = reference_values

            # Compute comparison metric if we have data from both periods
            metric = _compute_metric(
                series_id=series_id,
                series_data=data,
                primary_values=primary_values,
                reference_values=reference_values,
                reference_label=intent.reference_label
            )

            if metric:
                result.comparison_metrics[series_id] = metric

    return result


def _extract_period_data(
    data: SeriesData,
    start_date: Optional[str],
    end_date: Optional[str]
) -> list[tuple[str, float]]:
    """
    Extract data points within a date range.

    Args:
        data: The full series data
        start_date: Start of period (ISO format) or None for beginning
        end_date: End of period (ISO format) or None for present

    Returns:
        List of (date, value) tuples within the period
    """
    result = []

    for date_str, value in zip(data.dates, data.values):
        # Check if date is within range
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        result.append((date_str, value))

    return result


def _compute_metric(
    series_id: str,
    series_data: SeriesData,
    primary_values: list[tuple[str, float]],
    reference_values: list[tuple[str, float]],
    reference_label: str
) -> Optional[ComparisonMetric]:
    """
    Compute comparison metric between two periods.

    Uses the most recent value from each period for point comparison.
    For quarterly/annual data, uses the latest observation in each period.

    Args:
        series_id: The series identifier
        series_data: Full series data for metadata
        primary_values: Data from primary period
        reference_values: Data from reference period
        reference_label: Human-readable label for reference period

    Returns:
        ComparisonMetric or None if insufficient data
    """
    if not primary_values or not reference_values:
        return None

    # Get the most recent value from each period
    primary_date, primary_value = primary_values[-1]
    reference_date, reference_value = reference_values[-1]

    # Avoid division by zero
    if reference_value == 0:
        percent_change = 0.0
    else:
        percent_change = ((primary_value - reference_value) / abs(reference_value)) * 100

    absolute_change = primary_value - reference_value

    # Determine direction
    threshold = 0.01  # 0.01 units or 0.01% is considered "flat"
    if abs(absolute_change) < threshold:
        direction = "flat"
    elif absolute_change > 0:
        direction = "up"
    else:
        direction = "down"

    return ComparisonMetric(
        series_id=series_id,
        series_name=series_data.name,
        primary_value=primary_value,
        reference_value=reference_value,
        primary_date=primary_date,
        reference_date=reference_date,
        absolute_change=absolute_change,
        percent_change=percent_change,
        direction=direction,
        units=series_data.units,
        period_label=f"vs {reference_label}" if reference_label else ""
    )


def compute_comparison_metrics(
    series_data: dict[str, SeriesData],
    intent: TemporalIntent
) -> dict[str, ComparisonMetric]:
    """
    Standalone function to compute comparison metrics from existing data.

    Useful when data has already been fetched and we need to compute
    comparisons without re-fetching.

    Args:
        series_data: Dict of series_id -> SeriesData
        intent: The temporal intent with period information

    Returns:
        Dict of series_id -> ComparisonMetric
    """
    if not intent.is_comparison or not intent.reference_period:
        return {}

    metrics = {}

    for series_id, data in series_data.items():
        if data.is_empty or data.error:
            continue

        primary_values = _extract_period_data(
            data,
            intent.primary_period.get("start") if intent.primary_period else None,
            intent.primary_period.get("end") if intent.primary_period else None
        )

        reference_values = _extract_period_data(
            data,
            intent.reference_period.get("start"),
            intent.reference_period.get("end")
        )

        metric = _compute_metric(
            series_id=series_id,
            series_data=data,
            primary_values=primary_values,
            reference_values=reference_values,
            reference_label=intent.reference_label
        )

        if metric:
            metrics[series_id] = metric

    return metrics


def get_period_summary(
    values: list[tuple[str, float]],
    method: str = "latest"
) -> tuple[float, str]:
    """
    Summarize values from a period.

    Args:
        values: List of (date, value) tuples
        method: "latest" (most recent), "average", "first", "min", "max"

    Returns:
        (summary_value, date) tuple
    """
    if not values:
        return (0.0, "")

    if method == "latest":
        return values[-1][1], values[-1][0]
    elif method == "first":
        return values[0][1], values[0][0]
    elif method == "average":
        avg = statistics.mean(v for _, v in values)
        return avg, f"{values[0][0]} to {values[-1][0]}"
    elif method == "min":
        min_val = min(values, key=lambda x: x[1])
        return min_val[1], min_val[0]
    elif method == "max":
        max_val = max(values, key=lambda x: x[1])
        return max_val[1], max_val[0]
    else:
        return values[-1][1], values[-1][0]


# Quick test
if __name__ == "__main__":
    from .temporal_intent import detect_temporal_intent

    print("Testing Multi-Period Fetcher\n" + "=" * 50)

    # Test comparison query
    query = "How has unemployment changed since pre-pandemic?"
    intent = detect_temporal_intent(query)

    print(f"\nQuery: {query}")
    print(f"Intent type: {intent.intent_type}")
    print(f"Reference period: {intent.reference_period}")

    if intent.is_comparison:
        print("\nFetching multi-period data...")
        result = fetch_multi_period_data(["UNRATE"], intent)

        print(f"\nFull data points: {len(result.full_data.get('UNRATE', []).dates)}")
        print(f"Reference period data points: {len(result.reference_data.get('UNRATE', []))}")
        print(f"Primary period data points: {len(result.primary_data.get('UNRATE', []))}")

        if result.has_comparison_data:
            metric = result.get_metric("UNRATE")
            if metric:
                print(f"\nComparison: {metric}")
                print(f"  Direction: {metric.direction}")
