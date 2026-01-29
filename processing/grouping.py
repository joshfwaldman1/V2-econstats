"""
Chart Auto-Grouping - Decide which series to overlay on the same chart.

When a query returns multiple series (e.g., "New York economy" → NYUR, NYNA, UNRATE, PAYEMS),
this module determines which series should be overlaid on the same chart vs rendered separately.

Grouping rules:
- Series with different frequencies NEVER share a chart (chart crime prevention)
- Series with incompatible units NEVER share a chart
- Series with vastly different scales (>10x) get separate charts
- Semantic pairs (state+national, headline+core) are grouped together
- Max 4 traces per chart for readability

Honors explicit chart_groups from query plans when available.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set
from collections import defaultdict

from registry import registry


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ChartGroup:
    """A group of series to render on one chart."""

    series_data: List[tuple]  # [(series_id, dates, values, info), ...]
    title: str = ''           # Auto-generated or from plan
    show_yoy: bool = False    # Override per group


@dataclass
class _ClassifiedSeries:
    """Internal: a series with extracted metadata for grouping decisions."""

    series_id: str
    data: tuple               # (series_id, dates, values, info)
    frequency: str            # monthly, quarterly, annual, daily, weekly
    unit_category: str        # percent, dollars, index, count, other
    data_type: str            # rate, index, level, growth_rate, spread
    max_value: float          # max(abs(values)) for scale comparison
    region: str               # 2-letter state code or 'national'
    semantic_tags: Set[str]   # e.g., {'unemployment', 'rate'}
    name: str                 # Display name for title generation


# =============================================================================
# KNOWN SEMANTIC PAIRS
# =============================================================================

# Explicit pairs: series that should be overlaid when both are present
EXPLICIT_PAIRS: Dict[str, str] = {
    # Headline + Core inflation
    'CPIAUCSL': 'CPILFESL',
    'CPILFESL': 'CPIAUCSL',
    'PCEPI': 'PCEPILFE',
    'PCEPILFE': 'PCEPI',

    # Fed Funds + 10-Year Treasury
    'FEDFUNDS': 'DGS10',
    'DGS10': 'FEDFUNDS',

    # U-3 + U-6 unemployment
    'UNRATE': 'U6RATE',
    'U6RATE': 'UNRATE',
}

# National counterparts for state series
NATIONAL_COUNTERPARTS: Dict[str, str] = {
    'UR': 'UNRATE',    # State unemployment rate → national unemployment rate
    'NA': 'PAYEMS',    # State nonfarm payrolls → national nonfarm payrolls
}

# Patterns for state series IDs
# {2-letter state}UR = state unemployment rate (e.g., NYUR, CAUR, TXUR)
# {2-letter state}NA = state nonfarm payrolls (e.g., NYNA, CANA, TXNA)
STATE_UR_PATTERN = re.compile(r'^([A-Z]{2})UR$')
STATE_NA_PATTERN = re.compile(r'^([A-Z]{2})NA$')

# Max traces per chart
MAX_TRACES = 4

# Scale compatibility threshold: series with max_value ratio > this get separate charts
SCALE_THRESHOLD = 10.0


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def auto_group_series(
    series_data: List[tuple],
    routing_result
) -> List[ChartGroup]:
    """
    Decide which series should be overlaid on the same chart.

    This is the single entry point called by api/search.py. It handles:
    1. Explicit chart_groups from query plans (curated groupings)
    2. combine_chart flag (all series on one chart)
    3. Auto-grouping based on frequency, units, scale, and semantic similarity

    Args:
        series_data: List of (series_id, dates, values, info) tuples
        routing_result: RoutingResult with chart_groups, combine_chart, show_yoy

    Returns:
        List of ChartGroup objects, each containing series to render together
    """
    if not series_data:
        return []

    # ------------------------------------------------------------------
    # Phase 0a: Honor explicit chart_groups from the query plan
    # ------------------------------------------------------------------
    if routing_result.chart_groups:
        groups = _apply_explicit_groups(series_data, routing_result)
        if groups:
            return groups

    # ------------------------------------------------------------------
    # Phase 0b: Honor combine_chart flag (all series on one chart)
    # ------------------------------------------------------------------
    if routing_result.combine_chart and len(series_data) > 1:
        return [ChartGroup(
            series_data=series_data,
            title='',
            show_yoy=routing_result.show_yoy,
        )]

    # ------------------------------------------------------------------
    # Phase 0c: Single series → no grouping needed
    # ------------------------------------------------------------------
    if len(series_data) <= 1:
        return [ChartGroup(
            series_data=[s],
            title='',
            show_yoy=routing_result.show_yoy,
        ) for s in series_data]

    # ------------------------------------------------------------------
    # Phase 1: Classify each series
    # ------------------------------------------------------------------
    classified = []
    for item in series_data:
        series_id, dates, values, info = item
        classified.append(_classify_series(series_id, dates, values, info))

    # ------------------------------------------------------------------
    # Phase 2: Group by frequency (hard constraint)
    # ------------------------------------------------------------------
    freq_buckets: Dict[str, List[_ClassifiedSeries]] = defaultdict(list)
    for c in classified:
        freq_buckets[c.frequency].append(c)

    # ------------------------------------------------------------------
    # Phase 3-6: Within each frequency bucket, apply unit/scale/semantic grouping
    # ------------------------------------------------------------------
    result_groups: List[ChartGroup] = []
    for freq, items in freq_buckets.items():
        groups = _group_within_frequency(items, routing_result.show_yoy)
        result_groups.extend(groups)

    # ------------------------------------------------------------------
    # Phase 7: Generate titles for multi-series groups
    # ------------------------------------------------------------------
    for group in result_groups:
        if len(group.series_data) > 1 and not group.title:
            group.title = _generate_title(group.series_data)

    return result_groups


# =============================================================================
# PHASE 0a: EXPLICIT CHART GROUPS FROM PLAN
# =============================================================================

def _apply_explicit_groups(
    series_data: List[tuple],
    routing_result
) -> List[ChartGroup]:
    """
    Map curated chart_groups from query plan to fetched series_data.

    Plans define chart_groups like:
        [{"series": ["CPIAUCSL", "PCEPI"], "show_yoy": true, "title": "Headline CPI vs PCE"}]

    We match these series IDs against the fetched data and build ChartGroup objects.
    Any series not in a group gets its own chart.
    """
    # Build lookup: series_id → data tuple
    data_lookup: Dict[str, tuple] = {}
    for item in series_data:
        data_lookup[item[0]] = item

    groups: List[ChartGroup] = []
    assigned_ids: Set[str] = set()

    for group_spec in routing_result.chart_groups:
        group_series_ids = group_spec.get('series', [])
        group_data = []

        for sid in group_series_ids:
            if sid in data_lookup:
                group_data.append(data_lookup[sid])
                assigned_ids.add(sid)

        if group_data:
            groups.append(ChartGroup(
                series_data=group_data,
                title=group_spec.get('title', ''),
                show_yoy=group_spec.get('show_yoy', routing_result.show_yoy),
            ))

    # Any unassigned series get their own charts
    for item in series_data:
        if item[0] not in assigned_ids:
            groups.append(ChartGroup(
                series_data=[item],
                title='',
                show_yoy=routing_result.show_yoy,
            ))

    return groups


# =============================================================================
# PHASE 1: CLASSIFY SERIES
# =============================================================================

def _classify_series(
    series_id: str,
    dates: List[str],
    values: List[float],
    info: dict
) -> _ClassifiedSeries:
    """
    Extract metadata from a series for grouping decisions.

    Uses both the registry (SeriesInfo) and the API response (info dict).
    """
    series_info = registry.get_series(series_id)

    # Frequency
    frequency = _get_frequency(info, series_info)

    # Unit category
    unit_category = _get_unit_category(info, series_info)

    # Data type
    data_type = series_info.data_type if series_info else 'level'

    # Max absolute value for scale comparison
    max_value = max(abs(v) for v in values) if values else 0

    # Region (state code or 'national')
    region = _extract_region(series_id, series_info)

    # Semantic tags from name
    name = ''
    if series_info:
        name = series_info.name
    else:
        name = info.get('title', info.get('name', series_id))
    semantic_tags = _get_semantic_tags(series_id, name)

    return _ClassifiedSeries(
        series_id=series_id,
        data=(series_id, dates, values, info),
        frequency=frequency,
        unit_category=unit_category,
        data_type=data_type,
        max_value=max_value,
        region=region,
        semantic_tags=semantic_tags,
        name=name,
    )


def _get_frequency(info: dict, series_info=None) -> str:
    """Normalize frequency to one of: monthly, quarterly, annual, daily, weekly."""
    freq = ''
    if series_info and series_info.frequency:
        freq = series_info.frequency.lower()
    else:
        freq = info.get('frequency', 'monthly').lower()

    if 'quarter' in freq:
        return 'quarterly'
    elif 'annual' in freq or 'year' in freq:
        return 'annual'
    elif 'week' in freq:
        return 'weekly'
    elif 'daily' in freq or 'day' in freq:
        return 'daily'
    return 'monthly'


def _get_unit_category(info: dict, series_info=None) -> str:
    """
    Categorize series unit into: percent, dollars, index, count, other.

    Uses the same logic as formatter.py's chart crime prevention.
    """
    unit = ''
    if series_info:
        unit = series_info.unit.lower() if series_info.unit else ''
    if not unit:
        unit = info.get('units', '').lower()

    if 'percent' in unit or 'rate' in unit or '%' in unit:
        return 'percent'
    elif 'dollar' in unit or '$' in unit or 'usd' in unit:
        return 'dollars'
    elif 'index' in unit:
        return 'index'
    elif 'thousand' in unit or 'million' in unit or 'billion' in unit:
        return 'count'
    return 'other'


def _extract_region(series_id: str, series_info=None) -> str:
    """
    Extract region from series ID.

    State series follow FRED patterns:
    - {ST}UR: state unemployment rate (e.g., NYUR, CAUR)
    - {ST}NA: state nonfarm payrolls (e.g., NYNA, CANA)

    Returns 2-letter state code or 'national'.
    """
    # Check state unemployment rate pattern
    match = STATE_UR_PATTERN.match(series_id)
    if match:
        return match.group(1)

    # Check state nonfarm payrolls pattern
    match = STATE_NA_PATTERN.match(series_id)
    if match:
        return match.group(1)

    return 'national'


def _get_semantic_tags(series_id: str, name: str) -> Set[str]:
    """
    Extract semantic tags from series ID and name for pairing logic.

    Tags represent the concept measured (e.g., 'unemployment', 'employment', 'inflation').
    """
    tags: Set[str] = set()
    name_lower = name.lower()
    sid_lower = series_id.lower()

    # Unemployment
    if 'unemploy' in name_lower or sid_lower.endswith('ur') or series_id in ('UNRATE', 'U6RATE'):
        tags.add('unemployment')

    # Employment / payrolls — exclude 'unemployment' names to avoid false pairing
    # ('employ' is a substring of 'unemployment', which would cause UNRATE and EPOP
    # to share a tag and get combined on the same chart despite different scales)
    if (('employ' in name_lower and 'unemploy' not in name_lower)
            or 'payroll' in name_lower or 'nonfarm' in name_lower):
        tags.add('employment')
    if sid_lower.endswith('na') or series_id == 'PAYEMS':
        tags.add('employment')

    # Inflation
    if 'cpi' in sid_lower or 'pce' in sid_lower or 'inflation' in name_lower or 'price' in name_lower:
        tags.add('inflation')

    # Interest rates
    if 'rate' in name_lower and ('fed' in name_lower or 'treasury' in name_lower or 'dgs' in sid_lower):
        tags.add('interest_rate')
    if series_id in ('FEDFUNDS', 'DGS10', 'DGS2', 'DGS30'):
        tags.add('interest_rate')

    # GDP
    if 'gdp' in sid_lower or 'gdp' in name_lower:
        tags.add('gdp')

    # Housing
    if 'hous' in name_lower or 'home' in name_lower or 'mortgage' in name_lower:
        tags.add('housing')

    return tags


# =============================================================================
# PHASES 3-6: GROUP WITHIN FREQUENCY BUCKET
# =============================================================================

def _group_within_frequency(
    items: List[_ClassifiedSeries],
    default_show_yoy: bool
) -> List[ChartGroup]:
    """
    Within a single frequency bucket, apply unit grouping, scale checks,
    and semantic pairing to produce final chart groups.
    """
    # Phase 3: Group by unit category
    unit_buckets: Dict[str, List[_ClassifiedSeries]] = defaultdict(list)
    for item in items:
        unit_buckets[item.unit_category].append(item)

    result: List[ChartGroup] = []

    for unit_cat, unit_items in unit_buckets.items():
        # Phase 4 + 5: Scale check + semantic pairing
        groups = _apply_semantic_pairing(unit_items, default_show_yoy)
        result.extend(groups)

    return result


def _apply_semantic_pairing(
    items: List[_ClassifiedSeries],
    default_show_yoy: bool
) -> List[ChartGroup]:
    """
    Within a unit-compatible group, find semantic pairs and check scale compatibility.

    Pairing priority:
    1. Explicit pairs (CPIAUCSL↔CPILFESL, FEDFUNDS↔DGS10)
    2. State + national counterpart (NYUR + UNRATE, NYNA + PAYEMS)
    3. Same semantic tags (both tagged 'unemployment')

    Series that don't pair with anything become solo charts.
    """
    if len(items) <= 1:
        return [_make_group(items, default_show_yoy)]

    # Track which items have been assigned to a group
    assigned: Set[str] = set()
    groups: List[List[_ClassifiedSeries]] = []

    # Build quick lookup
    items_by_id: Dict[str, _ClassifiedSeries] = {item.series_id: item for item in items}

    # ------------------------------------------------------------------
    # Pass 1: Explicit pairs
    # ------------------------------------------------------------------
    for item in items:
        if item.series_id in assigned:
            continue
        partner_id = EXPLICIT_PAIRS.get(item.series_id)
        if partner_id and partner_id in items_by_id and partner_id not in assigned:
            pair = [item, items_by_id[partner_id]]
            if _scale_compatible(pair):
                groups.append(pair)
                assigned.add(item.series_id)
                assigned.add(partner_id)

    # ------------------------------------------------------------------
    # Pass 2: State + national counterpart
    # ------------------------------------------------------------------
    for item in items:
        if item.series_id in assigned:
            continue

        national_id = _get_national_counterpart(item.series_id)
        if national_id and national_id in items_by_id and national_id not in assigned:
            pair = [item, items_by_id[national_id]]
            if _scale_compatible(pair):
                groups.append(pair)
                assigned.add(item.series_id)
                assigned.add(national_id)

    # ------------------------------------------------------------------
    # Pass 3: Same semantic tags (group unassigned items that share a concept)
    # ------------------------------------------------------------------
    unassigned = [item for item in items if item.series_id not in assigned]

    if len(unassigned) > 1:
        tag_groups = _group_by_shared_tags(unassigned)
        for tag_group in tag_groups:
            if len(tag_group) > 1 and _scale_compatible(tag_group):
                # Cap at MAX_TRACES
                for chunk in _chunk_list(tag_group, MAX_TRACES):
                    groups.append(chunk)
                    for item in chunk:
                        assigned.add(item.series_id)

    # ------------------------------------------------------------------
    # Remaining unassigned items → solo charts
    # ------------------------------------------------------------------
    for item in items:
        if item.series_id not in assigned:
            groups.append([item])

    # Convert to ChartGroup objects with appropriate show_yoy
    return [_make_group(g, default_show_yoy) for g in groups]


def _get_national_counterpart(series_id: str) -> Optional[str]:
    """
    For a state series ID, return the national counterpart.

    NYUR → UNRATE (state unemployment → national unemployment)
    NYNA → PAYEMS (state payrolls → national payrolls)
    """
    match = STATE_UR_PATTERN.match(series_id)
    if match:
        return NATIONAL_COUNTERPARTS.get('UR')

    match = STATE_NA_PATTERN.match(series_id)
    if match:
        return NATIONAL_COUNTERPARTS.get('NA')

    return None


def _scale_compatible(items: List[_ClassifiedSeries]) -> bool:
    """
    Check if series have compatible scales (max values within SCALE_THRESHOLD of each other).

    This prevents putting PAYEMS (150,000+) on the same axis as a small series (500).
    """
    if len(items) <= 1:
        return True

    max_vals = [item.max_value for item in items if item.max_value > 0]
    if len(max_vals) <= 1:
        return True

    highest = max(max_vals)
    lowest = min(max_vals)

    if lowest == 0:
        return False

    return (highest / lowest) <= SCALE_THRESHOLD


def _group_by_shared_tags(items: List[_ClassifiedSeries]) -> List[List[_ClassifiedSeries]]:
    """
    Group items by shared semantic tags.

    Items that share at least one semantic tag are grouped together.
    Items with no tags or no shared tags remain ungrouped.
    """
    if not items:
        return []

    # Simple greedy approach: for each unassigned item, find others that share a tag
    assigned: Set[str] = set()
    groups: List[List[_ClassifiedSeries]] = []

    for item in items:
        if item.series_id in assigned or not item.semantic_tags:
            continue

        # Find all items sharing at least one tag with this item
        group = [item]
        assigned.add(item.series_id)

        for other in items:
            if other.series_id in assigned:
                continue
            if item.semantic_tags & other.semantic_tags:  # Set intersection
                group.append(other)
                assigned.add(other.series_id)

        if len(group) > 1:
            groups.append(group)

    return groups


def _chunk_list(items: list, max_size: int) -> List[list]:
    """Split a list into chunks of max_size."""
    return [items[i:i + max_size] for i in range(0, len(items), max_size)]


# =============================================================================
# PHASE 7: GENERATE TITLES
# =============================================================================

def _generate_title(series_data: List[tuple]) -> str:
    """
    Generate a descriptive title for a multi-series chart.

    Examples:
    - NYUR + UNRATE → "New York vs National Unemployment Rate"
    - CPIAUCSL + CPILFESL → "Headline vs Core CPI"
    - FEDFUNDS + DGS10 → "Fed Funds Rate vs 10-Year Treasury"
    """
    if len(series_data) == 0:
        return ''

    if len(series_data) == 1:
        return ''  # Single series uses its own name

    series_ids = [s[0] for s in series_data]

    # Check for known title patterns
    title = _known_pair_title(series_ids)
    if title:
        return title

    # Check for state + national pattern
    title = _state_national_title(series_ids, series_data)
    if title:
        return title

    # Fallback: "Series A vs Series B"
    names = []
    for series_id, dates, values, info in series_data[:2]:
        si = registry.get_series(series_id)
        name = si.name if si else info.get('title', series_id)
        # Shorten long names
        if len(name) > 40:
            name = name[:37] + '...'
        names.append(name)

    if len(series_data) > 2:
        return f"{names[0]} vs {names[1]} (+{len(series_data) - 2} more)"
    return ' vs '.join(names)


# Known pair titles for common combinations
_PAIR_TITLES: Dict[frozenset, str] = {
    frozenset({'CPIAUCSL', 'CPILFESL'}): 'Headline vs Core CPI',
    frozenset({'PCEPI', 'PCEPILFE'}): 'Headline vs Core PCE',
    frozenset({'CPIAUCSL', 'PCEPI'}): 'CPI vs PCE Inflation',
    frozenset({'CPILFESL', 'PCEPILFE'}): 'Core CPI vs Core PCE',
    frozenset({'FEDFUNDS', 'DGS10'}): 'Fed Funds Rate vs 10-Year Treasury',
    frozenset({'FEDFUNDS', 'DGS2'}): 'Fed Funds Rate vs 2-Year Treasury',
    frozenset({'DGS2', 'DGS10'}): '2-Year vs 10-Year Treasury',
    frozenset({'UNRATE', 'U6RATE'}): 'U-3 vs U-6 Unemployment Rate',
}


def _known_pair_title(series_ids: List[str]) -> Optional[str]:
    """Check if the series IDs match a known pair with a predefined title."""
    if len(series_ids) == 2:
        key = frozenset(series_ids)
        return _PAIR_TITLES.get(key)
    return None


# US state name lookup for title generation
_STATE_NAMES: Dict[str, str] = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
    'PR': 'Puerto Rico',
}


def _state_national_title(series_ids: List[str], series_data: List[tuple]) -> Optional[str]:
    """
    Generate title for state + national pairs.

    NYUR + UNRATE → "New York vs National Unemployment Rate"
    NYNA + PAYEMS → "New York vs National Nonfarm Payrolls"
    """
    if len(series_ids) != 2:
        return None

    for sid in series_ids:
        ur_match = STATE_UR_PATTERN.match(sid)
        if ur_match:
            state_code = ur_match.group(1)
            other = [s for s in series_ids if s != sid][0]
            if other == 'UNRATE':
                state_name = _STATE_NAMES.get(state_code, state_code)
                return f"{state_name} vs National Unemployment Rate"

        na_match = STATE_NA_PATTERN.match(sid)
        if na_match:
            state_code = na_match.group(1)
            other = [s for s in series_ids if s != sid][0]
            if other == 'PAYEMS':
                state_name = _STATE_NAMES.get(state_code, state_code)
                return f"{state_name} vs National Nonfarm Payrolls"

    return None


# =============================================================================
# PHASE 8: DETERMINE show_yoy PER GROUP
# =============================================================================

def _determine_show_yoy(items: List[_ClassifiedSeries], default: bool) -> bool:
    """
    Determine whether a group should display YoY transformation.

    - Rate data_type → never show YoY (already meaningful as levels)
    - Index data_type → always show YoY (raw index values meaningless)
    - Otherwise → use the routing result's default
    """
    if not items:
        return default

    data_types = {item.data_type for item in items}

    # If ALL series are rates, never show YoY
    if data_types == {'rate'}:
        return False

    # If ALL series are indexes, always show YoY
    if data_types == {'index'}:
        return True

    # If any are growth_rate or spread, don't apply YoY
    if data_types & {'growth_rate', 'spread'}:
        return False

    return default


def _make_group(items: List[_ClassifiedSeries], default_show_yoy: bool) -> ChartGroup:
    """Convert a list of classified series into a ChartGroup with appropriate show_yoy."""
    return ChartGroup(
        series_data=[item.data for item in items],
        title='',
        show_yoy=_determine_show_yoy(items, default_show_yoy),
    )
