# Core modules for EconStats
#
# This package contains the streamlined core components:
# - query_parser: Single LLM call for query understanding
# - series_catalog: Unified series metadata and query plans
# - data_fetcher: Unified data fetching interface (FRED + DBnomics)

from .series_catalog import (
    SERIES_CATALOG,
    QUERY_PLANS,
    SeriesMetadata,
    get_series_metadata,
    find_series_by_keyword,
    find_series_by_category,
    find_plan_for_query,
)

from .query_parser import (
    QueryIntent,
    parse_query,
)

from .data_fetcher import (
    DataFetcher,
    SeriesData,
    get_observations,
)

from .summary_generator import (
    generate_analytical_summary,
    generate_inflation_summary,
    generate_jobs_summary,
    generate_recession_summary,
    generate_fed_summary,
    ECONOMIC_FRAMEWORKS,
    TOPIC_PROMPTS,
)

from .temporal_intent import (
    TemporalIntent,
    detect_temporal_intent,
    get_reference_period_bounds,
    get_comparison_baseline_date,
    NAMED_PERIODS,
    COMPARISON_PATTERNS,
)

from .multi_period_fetcher import (
    MultiPeriodData,
    ComparisonMetric,
    fetch_multi_period_data,
    compute_comparison_metrics,
)

from .comparison_narrative import (
    generate_comparison_narrative,
    format_metric_narrative,
    format_comparison_insight,
)

from .intent_validator import (
    ValidationResult,
    ValidationIssue,
    validate_data_matches_intent,
    self_correct_if_needed,
)

from .indicator_context import (
    INDICATOR_CONTEXT,
    IndicatorContext,
    get_indicator_context,
    interpret_indicator,
    get_threshold_assessment,
    get_related_indicators,
    get_historical_context,
    get_caveats,
    format_indicator_explanation,
    # Quick access lists
    EMPLOYMENT_SERIES,
    INFLATION_SERIES,
    GDP_SERIES,
    FED_RATES_SERIES,
    CONSUMER_SERIES,
    HOUSING_SERIES,
    MARKET_SERIES,
)

from .causal_reasoning import (
    # Hedging phrase dictionaries
    HEDGING_PHRASES,
    UNCERTAINTY_PHRASES,
    OVERCONFIDENT_PHRASES,
    FORWARD_LOOKING_REPLACEMENTS,
    # Core functions
    hedge_causal_claim,
    get_hedging_phrase,
    get_uncertainty_phrase,
    transform_overconfident_language,
    # Narrative builders
    build_causal_narrative,
    describe_transmission_mechanism,
    # Confidence helpers
    get_confidence_for_claim,
)

from .historical_context import (
    # Data classes
    HistoricalContext,
    SeriesBenchmark,
    # Pre-computed benchmarks database
    HISTORICAL_BENCHMARKS,
    # Core functions - aliased to avoid conflict with indicator_context version
    get_historical_context as get_historical_context_detailed,
    describe_historical_context,
    find_similar_periods,
    compare_to_benchmark,
    # Utility functions
    get_benchmark,
    list_available_benchmarks,
    get_context_summary,
)

from .citations import (
    # Data classes
    Citation,
    ExpertView,
    TopicViews,
    # Expert views database
    EXPERT_VIEWS,
    # Source tier utilities
    get_source_tier,
    get_tier_label,
    ALL_SOURCE_TIERS,
    # Claim detection
    should_cite,
    detect_claim_type,
    # Expert view retrieval
    get_expert_views,
    get_topic_consensus,
    get_topic_disagreement,
    list_available_topics,
    find_topic_for_query,
    # Formatting functions
    format_with_attribution,
    format_competing_views,
    format_single_view,
    format_citation_footer,
    format_inline_citation,
    # Analysis enhancement
    add_citations_to_analysis,
    # Convenience functions
    get_view_for_topic_and_source,
    get_official_view,
    get_wall_street_consensus,
    # Fresh view fetching
    fetch_fresh_views,
)

from .data_revisions import (
    # Data classes
    RevisionInfo,
    # Metadata databases
    REVISION_METADATA,
    RECENT_REVISIONS,
    BENCHMARK_HISTORY,
    # Core API functions
    get_revision_context,
    is_preliminary,
    get_release_type,
    format_with_revision_warning,
    get_benchmark_context,
    compare_initial_vs_revised,
    get_data_quality_summary,
    # Helper functions
    get_revision_metadata,
    list_tracked_series,
    get_confidence_interval,
    # Convenience functions
    should_show_revision_warning,
    get_revision_warning_short,
    format_value_with_uncertainty,
)
