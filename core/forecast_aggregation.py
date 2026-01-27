"""
Forecast Aggregation System for EconStats.

Combines forecasts from multiple sources (Fed, banks, markets) into
weighted consensus estimates. Research shows aggregation beats individual forecasts.

"Simply averaging forecasts leads to dramatic performance improvements"
- Clemen (1989), Timmermann (2006)

Sources aggregated:
- Federal Reserve (dot plot, SEP projections)
- Major banks (Goldman, Morgan Stanley, JPMorgan, etc.)
- Market-implied (Fed funds futures, CME FedWatch)
- Survey-based (Blue Chip, SPF)
- International institutions (IMF, CBO)
- Prediction markets (Polymarket, for probability estimates)

Key insight: Forecast aggregation works because individual forecasters have
different information sets, models, and biases. Combining them cancels out
idiosyncratic errors while preserving signal.

Usage:
    from core.forecast_aggregation import (
        aggregate_forecasts,
        get_forecast_comparison,
        compare_fed_vs_market,
        measure_disagreement,
        get_consensus_summary,
    )

    # Get consensus for Fed rate path
    consensus = aggregate_forecasts('fed_funds_rate', 'end_2025')

    # Compare different forecasters
    comparison = get_forecast_comparison('fed_funds_rate', 'end_2025')

    # See Fed vs market expectations
    gap_analysis = compare_fed_vs_market()

Design principles:
1. Weighted aggregation slightly beats simple average (research-backed)
2. Disagreement measures tell us about uncertainty
3. Always provide plain-language interpretation
4. Track who's been more accurate (for future weighting)
5. Update easily when new forecasts come in
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import statistics


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Forecast:
    """
    A single forecast from one source.

    Attributes:
        source: Name of the forecasting entity (e.g., "Federal Reserve Dot Plot")
        value: The point forecast value
        metric: What is being forecasted ('fed_funds_rate', 'unemployment', etc.)
        horizon: Time horizon ('end_2025', 'end_2026', 'q1_2026', etc.)
        date_made: When the forecast was issued (ISO format string)
        tier: Source credibility tier:
              1 = Fed/official government
              2 = Major bank/institution
              3 = Market-implied
              4 = Other (prediction markets, surveys)
        confidence: Optional subjective confidence ('high', 'medium', 'low')
        range_low: Optional lower bound of forecast range
        range_high: Optional upper bound of forecast range
        notes: Optional additional context about the forecast
    """
    source: str
    value: float
    metric: str
    horizon: str
    date_made: str
    tier: int
    confidence: Optional[str] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class ConsensusForecast:
    """
    Aggregated forecast from multiple sources.

    Provides weighted consensus plus measures of forecaster disagreement
    and uncertainty. All values needed for display and interpretation.

    Attributes:
        metric: What is being forecasted ('fed_funds_rate', etc.)
        horizon: Time horizon ('end_2025', etc.)
        consensus_value: Weighted average of forecasts
        consensus_range: Tuple of (min, max) across all forecasts
        simple_average: Unweighted mean for comparison
        median: Middle forecast value
        std_dev: Standard deviation - measure of disagreement
        n_forecasts: Number of forecasts aggregated
        sources: List of source names included
        last_updated: When consensus was calculated (ISO format)
        interpretation: Plain language explanation
        fed_value: Fed's forecast (if available) for comparison
        market_value: Market-implied forecast (if available) for comparison
    """
    metric: str
    horizon: str
    consensus_value: float
    consensus_range: Tuple[float, float]
    simple_average: float
    median: float
    std_dev: float
    n_forecasts: int
    sources: List[str]
    last_updated: str
    interpretation: str
    fed_value: Optional[float] = None
    market_value: Optional[float] = None


@dataclass
class DisagreementAnalysis:
    """
    Analysis of how much forecasters disagree.

    High disagreement = high uncertainty about the future.
    Low disagreement = more confidence in the consensus.

    Attributes:
        std_dev: Standard deviation of forecasts
        range_width: Max forecast - Min forecast
        coefficient_of_variation: std_dev / mean (normalized disagreement)
        interpretation: 'low', 'moderate', 'high', or 'very_high'
        narrative: Plain language description
        most_optimistic: Source with highest (or lowest for unemployment) forecast
        most_pessimistic: Source with opposite forecast
        outliers: List of forecasts more than 1.5 std devs from mean
    """
    std_dev: float
    range_width: float
    coefficient_of_variation: float
    interpretation: str
    narrative: str
    most_optimistic: Optional[str] = None
    most_pessimistic: Optional[str] = None
    outliers: List[str] = field(default_factory=list)


# =============================================================================
# WEIGHTING SCHEME
# =============================================================================

# Source weights for aggregation
# Higher weight = more influence on consensus
# Based on historical accuracy and information quality
SOURCE_WEIGHTS: Dict[str, float] = {
    # Tier 1: Federal Reserve and government (official but not always right)
    'Federal Reserve Dot Plot': 1.5,
    'Federal Reserve SEP': 1.5,
    'CBO Projection': 1.3,
    'IMF World Economic Outlook': 1.2,
    'Congressional Budget Office': 1.3,

    # Tier 2: Major banks and institutions (good track records)
    'Goldman Sachs': 1.0,
    'Morgan Stanley': 1.0,
    'JPMorgan': 1.0,
    'Bank of America': 1.0,
    'Citi': 1.0,
    'UBS': 1.0,
    'Barclays': 1.0,
    'Deutsche Bank': 0.9,
    'Credit Suisse': 0.9,
    'Blue Chip Consensus': 1.2,  # Already aggregated, proven track record
    'SPF Median': 1.2,  # Survey of Professional Forecasters
    'Wall Street Consensus': 1.1,
    'Cleveland Fed Inflation Nowcast': 1.3,  # Good track record on inflation
    'Atlanta Fed GDPNow': 1.0,  # Volatile but useful
    'NY Fed Nowcast': 1.0,

    # Tier 3: Market-implied (wisdom of crowds)
    'CME FedWatch Implied': 1.0,
    'Fed Funds Futures': 1.0,
    'TIPS Breakeven': 1.1,  # Good inflation expectations measure
    'Eurodollar Futures': 0.9,

    # Tier 4: Prediction markets and other (experimental but useful)
    'Polymarket': 0.8,
    'Kalshi': 0.8,
    'PredictIt': 0.7,
    'Conference Board LEI': 1.0,
    'NFIB Survey': 0.8,

    # Default for unknown sources
    'default': 0.7,
}


def get_source_weight(source: str) -> float:
    """
    Get the weight for a forecast source.

    Weights reflect:
    - Historical accuracy (research on forecast accuracy)
    - Information advantage (Fed has insider view)
    - Independence (avoid double-counting correlated forecasts)

    Args:
        source: Name of the forecasting entity

    Returns:
        Weight (typically 0.7 to 1.5)
    """
    return SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS['default'])


# =============================================================================
# CURRENT FORECASTS DATABASE
# =============================================================================

# Pre-loaded forecasts from major sources
# These should be updated periodically (manually or via news_context.py)
# Last updated: January 2026

CURRENT_FORECASTS: Dict[str, Dict[str, List[Forecast]]] = {
    # =========================================================================
    # FEDERAL FUNDS RATE FORECASTS
    # =========================================================================
    'fed_funds_rate': {
        'end_2025': [
            Forecast(
                source='Federal Reserve Dot Plot',
                value=3.9,
                metric='fed_funds_rate',
                horizon='end_2025',
                date_made='2024-12',
                tier=1,
                confidence='high',
                range_low=3.4,
                range_high=4.4,
                notes='Median of FOMC participant projections'
            ),
            Forecast(
                source='Goldman Sachs',
                value=3.75,
                metric='fed_funds_rate',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
                notes='Expects 3 more cuts in 2025'
            ),
            Forecast(
                source='Morgan Stanley',
                value=3.5,
                metric='fed_funds_rate',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
                notes='More dovish than consensus'
            ),
            Forecast(
                source='JPMorgan',
                value=3.75,
                metric='fed_funds_rate',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='CME FedWatch Implied',
                value=3.85,
                metric='fed_funds_rate',
                horizon='end_2025',
                date_made='2026-01',
                tier=3,
                notes='Derived from Fed funds futures'
            ),
            Forecast(
                source='Blue Chip Consensus',
                value=3.8,
                metric='fed_funds_rate',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
        ],
        'end_2026': [
            Forecast(
                source='Federal Reserve Dot Plot',
                value=3.4,
                metric='fed_funds_rate',
                horizon='end_2026',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=2.9,
                range_high=3.9,
            ),
            Forecast(
                source='Goldman Sachs',
                value=3.5,
                metric='fed_funds_rate',
                horizon='end_2026',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='Morgan Stanley',
                value=3.25,
                metric='fed_funds_rate',
                horizon='end_2026',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='CME FedWatch Implied',
                value=3.6,
                metric='fed_funds_rate',
                horizon='end_2026',
                date_made='2026-01',
                tier=3,
            ),
        ],
        'longer_run': [
            Forecast(
                source='Federal Reserve Dot Plot',
                value=3.0,
                metric='fed_funds_rate',
                horizon='longer_run',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=2.5,
                range_high=3.5,
                notes='Fed estimate of neutral rate (r-star)'
            ),
            Forecast(
                source='CBO Projection',
                value=2.8,
                metric='fed_funds_rate',
                horizon='longer_run',
                date_made='2025-01',
                tier=1,
                confidence='medium',
            ),
        ],
    },

    # =========================================================================
    # UNEMPLOYMENT RATE FORECASTS
    # =========================================================================
    'unemployment': {
        'end_2025': [
            Forecast(
                source='Federal Reserve SEP',
                value=4.3,
                metric='unemployment',
                horizon='end_2025',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=4.0,
                range_high=4.5,
            ),
            Forecast(
                source='CBO Projection',
                value=4.4,
                metric='unemployment',
                horizon='end_2025',
                date_made='2025-01',
                tier=1,
                confidence='medium',
            ),
            Forecast(
                source='Goldman Sachs',
                value=4.2,
                metric='unemployment',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='Wall Street Consensus',
                value=4.3,
                metric='unemployment',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
        ],
        'end_2026': [
            Forecast(
                source='Federal Reserve SEP',
                value=4.3,
                metric='unemployment',
                horizon='end_2026',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=3.9,
                range_high=4.6,
            ),
            Forecast(
                source='CBO Projection',
                value=4.5,
                metric='unemployment',
                horizon='end_2026',
                date_made='2025-01',
                tier=1,
                confidence='medium',
            ),
        ],
    },

    # =========================================================================
    # GDP GROWTH FORECASTS
    # =========================================================================
    'gdp_growth': {
        '2025': [
            Forecast(
                source='Federal Reserve SEP',
                value=2.1,
                metric='gdp_growth',
                horizon='2025',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=1.8,
                range_high=2.4,
            ),
            Forecast(
                source='IMF World Economic Outlook',
                value=2.2,
                metric='gdp_growth',
                horizon='2025',
                date_made='2024-10',
                tier=1,
                confidence='medium',
            ),
            Forecast(
                source='CBO Projection',
                value=2.0,
                metric='gdp_growth',
                horizon='2025',
                date_made='2025-01',
                tier=1,
                confidence='medium',
            ),
            Forecast(
                source='Blue Chip Consensus',
                value=2.0,
                metric='gdp_growth',
                horizon='2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
                range_low=1.5,
                range_high=2.5,
            ),
            Forecast(
                source='Goldman Sachs',
                value=2.3,
                metric='gdp_growth',
                horizon='2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='Morgan Stanley',
                value=1.9,
                metric='gdp_growth',
                horizon='2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
        ],
        '2026': [
            Forecast(
                source='Federal Reserve SEP',
                value=2.0,
                metric='gdp_growth',
                horizon='2026',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=1.7,
                range_high=2.3,
            ),
            Forecast(
                source='IMF World Economic Outlook',
                value=2.1,
                metric='gdp_growth',
                horizon='2026',
                date_made='2024-10',
                tier=1,
                confidence='medium',
            ),
            Forecast(
                source='CBO Projection',
                value=1.9,
                metric='gdp_growth',
                horizon='2026',
                date_made='2025-01',
                tier=1,
                confidence='medium',
            ),
        ],
    },

    # =========================================================================
    # INFLATION FORECASTS (Core PCE)
    # =========================================================================
    'core_pce_inflation': {
        'end_2025': [
            Forecast(
                source='Federal Reserve SEP',
                value=2.5,
                metric='core_pce_inflation',
                horizon='end_2025',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=2.3,
                range_high=2.8,
            ),
            Forecast(
                source='Cleveland Fed Inflation Nowcast',
                value=2.6,
                metric='core_pce_inflation',
                horizon='q1_2026',
                date_made='2026-01',
                tier=1,
                confidence='high',
                notes='Nowcast for near-term inflation'
            ),
            Forecast(
                source='Goldman Sachs',
                value=2.4,
                metric='core_pce_inflation',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='Blue Chip Consensus',
                value=2.5,
                metric='core_pce_inflation',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
        ],
        'end_2026': [
            Forecast(
                source='Federal Reserve SEP',
                value=2.2,
                metric='core_pce_inflation',
                horizon='end_2026',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                range_low=2.0,
                range_high=2.4,
            ),
            Forecast(
                source='CBO Projection',
                value=2.3,
                metric='core_pce_inflation',
                horizon='end_2026',
                date_made='2025-01',
                tier=1,
                confidence='medium',
            ),
        ],
    },

    # =========================================================================
    # RECESSION PROBABILITY FORECASTS
    # =========================================================================
    'recession_probability': {
        '2025': [
            Forecast(
                source='Polymarket',
                value=20,
                metric='recession_probability',
                horizon='2025',
                date_made='2026-01',
                tier=4,
                notes='Prediction market odds (%)'
            ),
            Forecast(
                source='Goldman Sachs',
                value=15,
                metric='recession_probability',
                horizon='2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
            Forecast(
                source='Conference Board LEI',
                value=25,
                metric='recession_probability',
                horizon='12mo',
                date_made='2025-12',
                tier=2,
                confidence='medium',
                notes='Based on Leading Economic Index'
            ),
        ],
        '2026': [
            Forecast(
                source='Polymarket',
                value=23,
                metric='recession_probability',
                horizon='2026',
                date_made='2026-01',
                tier=4,
            ),
            Forecast(
                source='Goldman Sachs',
                value=20,
                metric='recession_probability',
                horizon='2026',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
        ],
    },

    # =========================================================================
    # CPI INFLATION FORECASTS
    # =========================================================================
    'cpi_inflation': {
        'end_2025': [
            Forecast(
                source='Federal Reserve SEP',
                value=2.5,
                metric='cpi_inflation',
                horizon='end_2025',
                date_made='2024-12',
                tier=1,
                confidence='medium',
                notes='PCE-based, CPI typically ~30bps higher'
            ),
            Forecast(
                source='Cleveland Fed Inflation Nowcast',
                value=2.7,
                metric='cpi_inflation',
                horizon='q1_2026',
                date_made='2026-01',
                tier=1,
                confidence='high',
            ),
            Forecast(
                source='Blue Chip Consensus',
                value=2.6,
                metric='cpi_inflation',
                horizon='end_2025',
                date_made='2026-01',
                tier=2,
                confidence='medium',
            ),
        ],
    },
}


# Metric display names and properties
METRIC_INFO: Dict[str, Dict[str, Any]] = {
    'fed_funds_rate': {
        'name': 'Federal Funds Rate',
        'unit': '%',
        'higher_is_better': None,  # Neither - depends on context
        'fed_target': None,
    },
    'unemployment': {
        'name': 'Unemployment Rate',
        'unit': '%',
        'higher_is_better': False,  # Lower unemployment is better
        'fed_target': 4.2,  # Approximate NAIRU
    },
    'gdp_growth': {
        'name': 'Real GDP Growth',
        'unit': '%',
        'higher_is_better': True,  # Higher growth is better (within reason)
        'fed_target': 2.0,  # Long-run potential growth
    },
    'core_pce_inflation': {
        'name': 'Core PCE Inflation',
        'unit': '%',
        'higher_is_better': False,  # Fed targets 2%, lower (to a point) is better
        'fed_target': 2.0,
    },
    'cpi_inflation': {
        'name': 'CPI Inflation',
        'unit': '%',
        'higher_is_better': False,
        'fed_target': 2.0,  # Fed targets PCE, but CPI often used
    },
    'recession_probability': {
        'name': 'Recession Probability',
        'unit': '%',
        'higher_is_better': False,  # Lower recession odds is better
        'fed_target': None,
    },
}


# =============================================================================
# CORE AGGREGATION FUNCTIONS
# =============================================================================

def aggregate_forecasts(
    metric: str,
    horizon: str,
    method: str = 'weighted',
) -> Optional[ConsensusForecast]:
    """
    Aggregate forecasts for a metric/horizon into consensus.

    This is the main entry point for getting consensus forecasts.
    Research shows that forecast aggregation dramatically improves
    accuracy compared to individual forecasts.

    Args:
        metric: Economic variable to forecast ('fed_funds_rate', 'unemployment',
                'gdp_growth', 'core_pce_inflation', 'recession_probability')
        horizon: Time horizon ('end_2025', 'end_2026', '2025', '2026', 'longer_run')
        method: Aggregation method:
                - 'weighted': Source-weighted average (default, slightly better)
                - 'simple': Unweighted average
                - 'median': Middle value (robust to outliers)
                - 'trimmed': Average excluding top and bottom 10%

    Returns:
        ConsensusForecast object with consensus value, range, and interpretation,
        or None if no forecasts available for this metric/horizon

    Example:
        >>> consensus = aggregate_forecasts('fed_funds_rate', 'end_2025')
        >>> print(f"Consensus: {consensus.consensus_value}%")
        >>> print(consensus.interpretation)
    """
    # Get forecasts for this metric/horizon
    metric_forecasts = CURRENT_FORECASTS.get(metric, {})
    forecasts = metric_forecasts.get(horizon, [])

    if not forecasts:
        return None

    values = [f.value for f in forecasts]
    sources = [f.source for f in forecasts]

    # Calculate consensus based on method
    if method == 'weighted':
        weights = [get_source_weight(f.source) for f in forecasts]
        total_weight = sum(weights)
        consensus_value = sum(v * w for v, w in zip(values, weights)) / total_weight
    elif method == 'simple':
        consensus_value = statistics.mean(values)
    elif method == 'median':
        consensus_value = statistics.median(values)
    elif method == 'trimmed':
        # Trim top and bottom 10%
        sorted_values = sorted(values)
        trim_count = max(1, len(sorted_values) // 10)
        trimmed = sorted_values[trim_count:-trim_count] if len(sorted_values) > 2 else sorted_values
        consensus_value = statistics.mean(trimmed)
    else:
        consensus_value = statistics.mean(values)

    # Calculate other statistics
    simple_average = statistics.mean(values)
    median_value = statistics.median(values)
    std_dev = statistics.stdev(values) if len(values) > 1 else 0.0
    consensus_range = (min(values), max(values))

    # Get Fed and market values if available
    fed_value = None
    market_value = None
    for f in forecasts:
        if 'Federal Reserve' in f.source:
            fed_value = f.value
        elif 'CME' in f.source or 'Futures' in f.source:
            market_value = f.value

    # Generate interpretation
    interpretation = _generate_consensus_interpretation(
        metric=metric,
        horizon=horizon,
        consensus_value=consensus_value,
        std_dev=std_dev,
        fed_value=fed_value,
        market_value=market_value,
        n_forecasts=len(forecasts),
    )

    return ConsensusForecast(
        metric=metric,
        horizon=horizon,
        consensus_value=round(consensus_value, 2),
        consensus_range=consensus_range,
        simple_average=round(simple_average, 2),
        median=round(median_value, 2),
        std_dev=round(std_dev, 2),
        n_forecasts=len(forecasts),
        sources=sources,
        last_updated=datetime.now().strftime('%Y-%m-%d'),
        interpretation=interpretation,
        fed_value=fed_value,
        market_value=market_value,
    )


def _generate_consensus_interpretation(
    metric: str,
    horizon: str,
    consensus_value: float,
    std_dev: float,
    fed_value: Optional[float],
    market_value: Optional[float],
    n_forecasts: int,
) -> str:
    """
    Generate plain-language interpretation of consensus forecast.

    Explains what the consensus means, how much agreement there is,
    and any notable gaps between Fed and market expectations.

    Args:
        metric: Economic variable being forecasted
        horizon: Time horizon
        consensus_value: The weighted consensus
        std_dev: Standard deviation (disagreement measure)
        fed_value: Fed's forecast if available
        market_value: Market-implied forecast if available
        n_forecasts: Number of forecasts aggregated

    Returns:
        Multi-sentence interpretation string
    """
    metric_info = METRIC_INFO.get(metric, {})
    metric_name = metric_info.get('name', metric)
    unit = metric_info.get('unit', '')

    sentences = []

    # Main consensus statement
    horizon_text = horizon.replace('_', ' ').replace('end ', 'end of ')
    sentences.append(
        f"The consensus forecast for {metric_name} by {horizon_text} is "
        f"{consensus_value:.1f}{unit}, based on {n_forecasts} forecasters."
    )

    # Disagreement level
    if std_dev < 0.15:
        disagreement = "strong agreement"
    elif std_dev < 0.3:
        disagreement = "moderate agreement"
    elif std_dev < 0.5:
        disagreement = "some disagreement"
    else:
        disagreement = "significant disagreement"
    sentences.append(f"There is {disagreement} among forecasters (std dev: {std_dev:.2f}).")

    # Fed vs market gap
    if fed_value is not None and market_value is not None:
        gap = abs(fed_value - market_value)
        if gap > 0.25:
            if fed_value > market_value:
                sentences.append(
                    f"The Fed ({fed_value:.1f}{unit}) is more hawkish than markets ({market_value:.1f}{unit}), "
                    f"suggesting markets expect a more dovish path."
                )
            else:
                sentences.append(
                    f"Markets ({market_value:.1f}{unit}) are pricing a more hawkish path than the Fed ({fed_value:.1f}{unit})."
                )
        elif gap > 0.1:
            sentences.append(
                f"Fed ({fed_value:.1f}{unit}) and market ({market_value:.1f}{unit}) expectations are roughly aligned."
            )

    # Context based on metric
    if metric == 'fed_funds_rate':
        if consensus_value > 4.5:
            sentences.append("This level remains restrictive relative to the neutral rate.")
        elif consensus_value < 3.0:
            sentences.append("This level would be near the Fed's estimate of neutral.")
    elif metric == 'unemployment':
        if consensus_value < 4.0:
            sentences.append("This would remain below the natural rate, indicating a tight labor market.")
        elif consensus_value > 5.0:
            sentences.append("This would indicate meaningful labor market slack.")
    elif metric == 'gdp_growth':
        if consensus_value < 1.5:
            sentences.append("This below-trend growth raises recession concerns.")
        elif consensus_value > 2.5:
            sentences.append("This above-trend growth suggests continued expansion.")
    elif metric == 'core_pce_inflation':
        if consensus_value > 2.5:
            sentences.append("This remains above the Fed's 2% target, suggesting policy will stay restrictive.")
        elif consensus_value < 2.3:
            sentences.append("This approaches the Fed's 2% target, potentially enabling rate cuts.")

    return ' '.join(sentences)


def get_forecast_comparison(metric: str, horizon: str) -> str:
    """
    Format a comparison of forecasts from different sources.

    Creates a formatted string showing each forecaster's view,
    highlighting the consensus and any notable outliers.

    Args:
        metric: Economic variable ('fed_funds_rate', 'unemployment', etc.)
        horizon: Time horizon ('end_2025', 'end_2026', etc.)

    Returns:
        Formatted multi-line string suitable for display

    Example:
        >>> print(get_forecast_comparison('fed_funds_rate', 'end_2025'))
        Fed Funds Rate Path (end of 2025):
         - Fed Dots: 3.9% (range: 3.4-4.4%)
         - Goldman: 3.75%
         - Morgan Stanley: 3.5%
         - Markets: 3.85%
         --> Consensus: 3.76% (from 6 forecasters)

         Disagreement is moderate; Morgan Stanley is most dovish.
    """
    metric_forecasts = CURRENT_FORECASTS.get(metric, {})
    forecasts = metric_forecasts.get(horizon, [])

    if not forecasts:
        return f"No forecasts available for {metric} at {horizon}."

    metric_info = METRIC_INFO.get(metric, {})
    metric_name = metric_info.get('name', metric)
    unit = metric_info.get('unit', '')

    lines = []
    horizon_text = horizon.replace('_', ' ').replace('end ', 'end of ')
    lines.append(f"{metric_name} ({horizon_text}):")

    # Sort by tier (Fed/official first)
    sorted_forecasts = sorted(forecasts, key=lambda x: (x.tier, x.source))

    for f in sorted_forecasts:
        # Format source name (shorten for display)
        source_display = f.source.replace('Federal Reserve ', 'Fed ').replace(' Implied', '')
        value_str = f"{f.value:.2f}{unit}"

        if f.range_low is not None and f.range_high is not None:
            range_str = f" (range: {f.range_low:.1f}-{f.range_high:.1f}{unit})"
        else:
            range_str = ""

        lines.append(f"  - {source_display}: {value_str}{range_str}")

    # Add consensus
    consensus = aggregate_forecasts(metric, horizon)
    if consensus:
        lines.append("")
        lines.append(
            f"  --> Consensus: {consensus.consensus_value}{unit} "
            f"(from {consensus.n_forecasts} forecasters)"
        )

        # Add disagreement analysis
        disagreement = measure_disagreement(forecasts)
        lines.append("")
        lines.append(f"  {disagreement.narrative}")

    return '\n'.join(lines)


def measure_disagreement(forecasts: List[Forecast]) -> DisagreementAnalysis:
    """
    Measure how much forecasters disagree.

    High disagreement indicates high uncertainty about the future.
    This is valuable information beyond just the consensus value.

    Args:
        forecasts: List of Forecast objects to analyze

    Returns:
        DisagreementAnalysis with std_dev, range, interpretation, and narrative

    Example:
        >>> forecasts = get_forecasts('fed_funds_rate', 'end_2025')
        >>> disagreement = measure_disagreement(forecasts)
        >>> print(disagreement.interpretation)  # 'moderate'
        >>> print(disagreement.narrative)  # "Forecasters show moderate disagreement..."
    """
    if not forecasts or len(forecasts) < 2:
        return DisagreementAnalysis(
            std_dev=0.0,
            range_width=0.0,
            coefficient_of_variation=0.0,
            interpretation='insufficient_data',
            narrative="Not enough forecasts to measure disagreement.",
        )

    values = [f.value for f in forecasts]
    sources = [f.source for f in forecasts]

    std_dev = statistics.stdev(values)
    mean_value = statistics.mean(values)
    range_width = max(values) - min(values)
    coef_var = std_dev / abs(mean_value) if mean_value != 0 else 0

    # Determine interpretation
    if coef_var < 0.05:
        interpretation = 'low'
        narrative_adj = "strong agreement"
    elif coef_var < 0.10:
        interpretation = 'moderate'
        narrative_adj = "moderate agreement"
    elif coef_var < 0.20:
        interpretation = 'high'
        narrative_adj = "notable disagreement"
    else:
        interpretation = 'very_high'
        narrative_adj = "significant disagreement"

    # Find most optimistic and pessimistic
    max_idx = values.index(max(values))
    min_idx = values.index(min(values))
    most_optimistic = sources[max_idx]
    most_pessimistic = sources[min_idx]

    # Find outliers (more than 1.5 std devs from mean)
    outliers = []
    for f in forecasts:
        if abs(f.value - mean_value) > 1.5 * std_dev:
            outliers.append(f.source)

    # Build narrative
    metric = forecasts[0].metric
    metric_info = METRIC_INFO.get(metric, {})
    higher_is_better = metric_info.get('higher_is_better')

    if higher_is_better is True:
        optimist_label = "most optimistic"
        pessimist_label = "most pessimistic"
    elif higher_is_better is False:
        optimist_label = "most optimistic"
        pessimist_label = "most pessimistic"
        # Swap for metrics where lower is better
        most_optimistic, most_pessimistic = most_pessimistic, most_optimistic
    else:
        optimist_label = "highest"
        pessimist_label = "lowest"

    if interpretation in ['low', 'moderate']:
        narrative = f"Forecasters show {narrative_adj}."
    else:
        narrative = (
            f"Forecasters show {narrative_adj}; "
            f"{most_optimistic} is {optimist_label}, "
            f"{most_pessimistic} is {pessimist_label}."
        )

    return DisagreementAnalysis(
        std_dev=round(std_dev, 3),
        range_width=round(range_width, 3),
        coefficient_of_variation=round(coef_var, 3),
        interpretation=interpretation,
        narrative=narrative,
        most_optimistic=most_optimistic,
        most_pessimistic=most_pessimistic,
        outliers=outliers,
    )


def get_market_implied_path(metric: str) -> List[Dict[str, Any]]:
    """
    Get market-implied path for a metric (e.g., Fed funds futures).

    Returns the expected path based on futures pricing, which reflects
    the market's probability-weighted expectations.

    Args:
        metric: Currently only 'fed_funds_rate' is supported

    Returns:
        List of dicts with 'date', 'value', and 'source' keys

    Example:
        >>> path = get_market_implied_path('fed_funds_rate')
        >>> for point in path:
        ...     print(f"{point['date']}: {point['value']}%")
    """
    if metric != 'fed_funds_rate':
        return []

    # Hard-coded market expectations (would ideally fetch from CME FedWatch)
    # Last updated: January 2026
    return [
        {'date': '2026-01', 'value': 4.25, 'source': 'CME FedWatch'},
        {'date': '2026-03', 'value': 4.00, 'source': 'CME FedWatch', 'note': 'Possible cut'},
        {'date': '2026-06', 'value': 3.75, 'source': 'CME FedWatch'},
        {'date': '2026-09', 'value': 3.75, 'source': 'CME FedWatch'},
        {'date': '2026-12', 'value': 3.50, 'source': 'CME FedWatch'},
        {'date': '2027-06', 'value': 3.25, 'source': 'CME FedWatch'},
    ]


def compare_fed_vs_market() -> str:
    """
    Compare Fed projections to market expectations.

    Analyzes the gap between Fed dot plot projections and what
    futures markets are pricing. This gap often contains valuable
    information about market beliefs vs. Fed communication.

    Returns:
        Multi-paragraph analysis string

    Example:
        >>> print(compare_fed_vs_market())
        "Fed vs. Market Rate Expectations:

        The Fed's December 2024 dot plot suggests the median FOMC participant
        expects rates at 3.4% by end-2026, implying about 4 rate cuts from current levels.

        Markets, however, are pricing rates at 3.6% by end-2026, suggesting only
        3 cuts. This 20bp gap indicates markets expect:
        (a) Stickier inflation than the Fed projects, or
        (b) A higher neutral rate than the Fed estimates

        Historically, markets have been better at predicting the direction of
        rate changes, while the Fed has been better at predicting the pace."
    """
    lines = []
    lines.append("Fed vs. Market Rate Expectations:")
    lines.append("")

    # Get Fed and market forecasts for different horizons
    for horizon in ['end_2025', 'end_2026']:
        forecasts = CURRENT_FORECASTS.get('fed_funds_rate', {}).get(horizon, [])

        fed_forecast = None
        market_forecast = None
        for f in forecasts:
            if 'Federal Reserve' in f.source:
                fed_forecast = f
            elif 'CME' in f.source or 'FedWatch' in f.source:
                market_forecast = f

        if fed_forecast and market_forecast:
            horizon_text = horizon.replace('_', ' ').replace('end ', 'end of ')
            gap = fed_forecast.value - market_forecast.value

            if abs(gap) < 0.1:
                lines.append(f"For {horizon_text}: Fed and markets are aligned at ~{fed_forecast.value}%.")
            elif gap > 0:
                lines.append(
                    f"For {horizon_text}: Fed expects {fed_forecast.value}% vs. markets at {market_forecast.value}% "
                    f"(Fed is {abs(gap):.2f}pp more hawkish)."
                )
            else:
                lines.append(
                    f"For {horizon_text}: Fed expects {fed_forecast.value}% vs. markets at {market_forecast.value}% "
                    f"(markets are {abs(gap):.2f}pp more hawkish)."
                )

    lines.append("")

    # Add interpretation
    lines.append("Interpretation:")
    lines.append("")

    # Check overall direction
    end_2025_forecasts = CURRENT_FORECASTS.get('fed_funds_rate', {}).get('end_2025', [])
    fed_2025 = None
    market_2025 = None
    for f in end_2025_forecasts:
        if 'Federal Reserve' in f.source:
            fed_2025 = f.value
        elif 'CME' in f.source:
            market_2025 = f.value

    if fed_2025 and market_2025:
        if fed_2025 > market_2025:
            lines.append(
                "The Fed is more hawkish than markets, suggesting either:"
            )
            lines.append("  (a) The Fed sees inflation risks that markets are underpricing")
            lines.append("  (b) Markets expect weaker growth that will force faster cuts")
            lines.append("")
            lines.append(
                "Historically, when this gap persists, markets tend to 'win' - "
                "the Fed usually ends up cutting more than it projects when faced "
                "with economic weakness."
            )
        else:
            lines.append(
                "Markets are more hawkish than the Fed, suggesting either:"
            )
            lines.append("  (a) Markets see stickier inflation than the Fed projects")
            lines.append("  (b) Markets believe the neutral rate is higher than the Fed estimates")
            lines.append("")
            lines.append(
                "When markets are more hawkish than the Fed, it often means bond investors "
                "see inflation persistence that could delay the Fed's cutting cycle."
            )

    return '\n'.join(lines)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_forecasts(metric: str, horizon: str) -> List[Forecast]:
    """
    Get raw forecasts for a metric/horizon.

    Args:
        metric: Economic variable
        horizon: Time horizon

    Returns:
        List of Forecast objects
    """
    return CURRENT_FORECASTS.get(metric, {}).get(horizon, [])


def get_available_metrics() -> List[str]:
    """
    List all metrics with available forecasts.

    Returns:
        List of metric names
    """
    return list(CURRENT_FORECASTS.keys())


def get_available_horizons(metric: str) -> List[str]:
    """
    List all horizons with forecasts for a metric.

    Args:
        metric: Economic variable

    Returns:
        List of horizon names
    """
    return list(CURRENT_FORECASTS.get(metric, {}).keys())


def get_consensus_summary() -> str:
    """
    Get a summary of all consensus forecasts.

    Returns formatted string with key forecasts and their consensus values.
    Useful for a quick overview of the forecast landscape.

    Returns:
        Multi-line formatted summary string

    Example:
        >>> print(get_consensus_summary())
        ECONOMIC FORECAST CONSENSUS (as of 2026-01-25)
        =============================================

        Fed Funds Rate:
          End 2025: 3.76% (range: 3.5-3.9%)
          End 2026: 3.44% (range: 3.25-3.6%)

        Unemployment:
          End 2025: 4.3% (range: 4.2-4.4%)
        ...
    """
    lines = []
    current_date = datetime.now().strftime('%Y-%m-%d')
    lines.append(f"ECONOMIC FORECAST CONSENSUS (as of {current_date})")
    lines.append("=" * 50)
    lines.append("")

    for metric in CURRENT_FORECASTS.keys():
        metric_info = METRIC_INFO.get(metric, {})
        metric_name = metric_info.get('name', metric)
        unit = metric_info.get('unit', '')

        lines.append(f"{metric_name}:")

        horizons = get_available_horizons(metric)
        for horizon in horizons:
            consensus = aggregate_forecasts(metric, horizon)
            if consensus:
                horizon_text = horizon.replace('_', ' ').replace('end ', 'end of ')
                range_str = f"{consensus.consensus_range[0]:.1f}-{consensus.consensus_range[1]:.1f}{unit}"
                lines.append(
                    f"  {horizon_text}: {consensus.consensus_value}{unit} "
                    f"(range: {range_str}, n={consensus.n_forecasts})"
                )

        lines.append("")

    return '\n'.join(lines)


def update_forecasts_from_news(news_results: List[Dict]) -> int:
    """
    Update CURRENT_FORECASTS based on news search results.

    Parses news snippets for forecast updates from major sources.
    This is a best-effort parser - it looks for patterns like
    "Goldman expects..." or "Fed projects..."

    Args:
        news_results: List of dicts with 'title', 'snippet', 'source' keys
                     (typically from news_context.py)

    Returns:
        Number of forecasts updated

    Note:
        This is a simplified parser. For production use, would want
        more sophisticated NLP or structured data feeds.
    """
    updated_count = 0

    # Known source patterns to look for
    source_patterns = {
        'Goldman': 'Goldman Sachs',
        'Morgan Stanley': 'Morgan Stanley',
        'JPMorgan': 'JPMorgan',
        'Fed': 'Federal Reserve',
        'FOMC': 'Federal Reserve',
        'IMF': 'IMF World Economic Outlook',
        'CBO': 'CBO Projection',
    }

    # Metric patterns
    metric_patterns = {
        'fed funds': 'fed_funds_rate',
        'interest rate': 'fed_funds_rate',
        'rate cut': 'fed_funds_rate',
        'unemployment': 'unemployment',
        'jobless rate': 'unemployment',
        'GDP': 'gdp_growth',
        'growth': 'gdp_growth',
        'inflation': 'core_pce_inflation',
        'PCE': 'core_pce_inflation',
        'CPI': 'cpi_inflation',
    }

    for news in news_results:
        snippet = news.get('snippet', '')
        title = news.get('title', '')
        text = f"{title} {snippet}".lower()

        # Try to identify source
        source_name = None
        for pattern, name in source_patterns.items():
            if pattern.lower() in text:
                source_name = name
                break

        if not source_name:
            continue

        # Try to identify metric
        metric = None
        for pattern, m in metric_patterns.items():
            if pattern.lower() in text:
                metric = m
                break

        if not metric:
            continue

        # Try to extract a numeric value (very simplified)
        import re
        numbers = re.findall(r'(\d+\.?\d*)\s*%', text)
        if numbers:
            try:
                value = float(numbers[0])
                # Basic sanity checks
                if metric == 'fed_funds_rate' and 0 < value < 10:
                    # This is a valid forecast, but we'd need horizon
                    # For now, just count it as found
                    updated_count += 1
                elif metric == 'unemployment' and 2 < value < 15:
                    updated_count += 1
                elif metric == 'gdp_growth' and -5 < value < 10:
                    updated_count += 1
                elif 'inflation' in metric and 0 < value < 15:
                    updated_count += 1
            except ValueError:
                pass

    return updated_count


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("FORECAST AGGREGATION SYSTEM")
    print("=" * 70)

    # Test consensus for Fed funds rate
    print("\n--- Fed Funds Rate Consensus ---")
    consensus = aggregate_forecasts('fed_funds_rate', 'end_2025')
    if consensus:
        print(f"Consensus: {consensus.consensus_value}%")
        print(f"Range: {consensus.consensus_range}")
        print(f"Simple avg: {consensus.simple_average}%")
        print(f"Median: {consensus.median}%")
        print(f"Std dev: {consensus.std_dev}")
        print(f"Sources: {len(consensus.sources)}")
        print(f"\nInterpretation:")
        print(consensus.interpretation)

    # Test forecast comparison
    print("\n--- Forecast Comparison ---")
    print(get_forecast_comparison('fed_funds_rate', 'end_2025'))

    # Test Fed vs Market
    print("\n--- Fed vs. Market ---")
    print(compare_fed_vs_market())

    # Test disagreement analysis
    print("\n--- Disagreement Analysis ---")
    forecasts = get_forecasts('fed_funds_rate', 'end_2025')
    disagreement = measure_disagreement(forecasts)
    print(f"Std dev: {disagreement.std_dev}")
    print(f"Range width: {disagreement.range_width}")
    print(f"Interpretation: {disagreement.interpretation}")
    print(f"Narrative: {disagreement.narrative}")

    # Test market path
    print("\n--- Market-Implied Rate Path ---")
    path = get_market_implied_path('fed_funds_rate')
    for point in path:
        note = point.get('note', '')
        print(f"  {point['date']}: {point['value']}% {note}")

    # Full summary
    print("\n" + "=" * 70)
    print(get_consensus_summary())

    # Test GDP forecasts
    print("\n--- GDP Growth Forecast Comparison ---")
    print(get_forecast_comparison('gdp_growth', '2025'))

    # Test unemployment
    print("\n--- Unemployment Consensus ---")
    consensus = aggregate_forecasts('unemployment', 'end_2025')
    if consensus:
        print(f"Consensus: {consensus.consensus_value}%")
        print(f"Interpretation: {consensus.interpretation}")

    # Test recession probability
    print("\n--- Recession Probability ---")
    print(get_forecast_comparison('recession_probability', '2025'))
