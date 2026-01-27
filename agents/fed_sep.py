"""
Federal Reserve Summary of Economic Projections (SEP) Integration.

Fetches and parses FOMC economic projections from the Fed's website.
SEP is released quarterly (March, June, September, December meetings).

Data includes median and range projections for:
- Real GDP growth
- Unemployment rate
- PCE inflation
- Core PCE inflation
- Federal funds rate
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser

# =============================================================================
# SEP MEETING DATES (updated quarterly)
# =============================================================================

# FOMC meetings with SEP releases (month/day format)
# SEP is released at March, June, September, December meetings
SEP_MEETINGS = [
    (3, 19),   # March
    (6, 18),   # June
    (9, 17),   # September
    (12, 18),  # December
]

# Cache for SEP data (refreshed daily max)
_sep_cache: Dict = {}
_sep_cache_time: Optional[datetime] = None
SEP_CACHE_TTL = timedelta(hours=24)


# =============================================================================
# FOMC STATEMENT SUMMARIES (hardcoded for recent meetings)
# =============================================================================

# Key quotes and summaries from recent FOMC statements
# Updated after each FOMC meeting - these provide context beyond just projections
FOMC_STATEMENT_SUMMARIES = {
    'December 2024': {
        'date': 'December 18, 2024',
        'rate_decision': 'Cut 25 bps to 4.25-4.50%',
        'key_quote': 'The Committee judges that the risks to achieving its employment and inflation goals are roughly in balance.',
        'highlights': [
            'Third consecutive rate cut (total 100 bps since September)',
            'Signaled slower pace of cuts in 2025 due to sticky inflation',
            'Revised inflation projections higher; fewer cuts expected in 2025',
            'Labor market conditions have "generally eased"',
        ],
        'tone': 'hawkish',  # Relative to expectations
    },
    'November 2024': {
        'date': 'November 7, 2024',
        'rate_decision': 'Cut 25 bps to 4.50-4.75%',
        'key_quote': 'Inflation has made progress toward the Committee\'s 2 percent objective but remains somewhat elevated.',
        'highlights': [
            'Second rate cut following September\'s 50 bps move',
            'Removed reference to "further progress" on inflation',
            'Labor market remains solid despite slower payroll gains',
        ],
        'tone': 'neutral',
    },
    'September 2024': {
        'date': 'September 18, 2024',
        'rate_decision': 'Cut 50 bps to 4.75-5.00%',
        'key_quote': 'The Committee has gained greater confidence that inflation is moving sustainably toward 2 percent.',
        'highlights': [
            'First rate cut since March 2020 - began easing cycle',
            'Larger-than-usual 50 bps cut to "recalibrate" policy',
            'Shift in focus from inflation to dual mandate balance',
            'Powell emphasized this is not about recession fears',
        ],
        'tone': 'dovish',
    },
}

# Current Fed funds rate target (update after each FOMC meeting)
CURRENT_FED_FUNDS_RATE = {
    'target_low': 4.25,
    'target_high': 4.50,
    'effective_rate': 4.33,  # Typically near midpoint
    'last_change': 'December 18, 2024',
    'last_change_direction': 'cut',
    'last_change_size': 25,  # basis points
}


def get_current_fed_funds_rate() -> Dict:
    """
    Get the current Fed funds rate target.

    Returns:
        Dict with target_low, target_high, effective_rate, and last change info
    """
    return CURRENT_FED_FUNDS_RATE.copy()


def get_recent_fomc_summary(meeting_date: Optional[str] = None) -> Optional[Dict]:
    """
    Get summary of a recent FOMC statement.

    Args:
        meeting_date: Specific meeting (e.g., 'December 2024'). If None, returns most recent.

    Returns:
        Dict with rate_decision, key_quote, highlights, tone
    """
    if meeting_date and meeting_date in FOMC_STATEMENT_SUMMARIES:
        return FOMC_STATEMENT_SUMMARIES[meeting_date].copy()

    # Return most recent if no specific meeting requested
    if FOMC_STATEMENT_SUMMARIES:
        # Keys are in chronological order, last one is most recent
        recent_key = list(FOMC_STATEMENT_SUMMARIES.keys())[0]
        return FOMC_STATEMENT_SUMMARIES[recent_key].copy()

    return None


# =============================================================================
# HTML PARSER FOR SEP TABLES
# =============================================================================

class SEPTableParser(HTMLParser):
    """Parse SEP projection tables from Fed HTML."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.tables = []
        self.current_table = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.current_table = []
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ('td', 'th') and self.in_row:
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag == 'table':
            if self.current_table:
                self.tables.append(self.current_table)
            self.in_table = False
            self.current_table = []
        elif tag == 'tr':
            if self.current_row:
                self.current_table.append(self.current_row)
            self.in_row = False
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            text = data.strip()
            if text:
                self.current_row.append(text)


# =============================================================================
# SEP DATA FETCHING
# =============================================================================

def get_latest_sep_url() -> Tuple[str, str]:
    """
    Get URL for most recent SEP release.

    Returns:
        (url, meeting_date) tuple
    """
    now = datetime.now()

    # Build list of candidate dates going back 2 years
    candidates = []
    for year in [now.year, now.year - 1, now.year - 2]:
        for month, day in SEP_MEETINGS:
            meeting_date = datetime(year, month, day)
            if meeting_date <= now:
                candidates.append(meeting_date)

    # Sort by most recent first
    candidates.sort(reverse=True)

    # Try each candidate URL until one works
    for meeting_date in candidates[:4]:  # Only try last 4 meetings
        date_str = meeting_date.strftime('%Y%m%d')
        url = f"https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{date_str}.htm"

        # Quick check if URL exists
        try:
            req = Request(url, method='HEAD', headers={
                'User-Agent': 'Mozilla/5.0 (compatible; EconStats/1.0)',
            })
            with urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return url, meeting_date.strftime('%B %Y')
        except:
            continue

    # Fallback to known good URL (December 2024)
    return "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20241218.htm", "December 2024"


def fetch_sep_html(url: str) -> Optional[str]:
    """Fetch SEP HTML from Fed website."""
    try:
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; EconStats/1.0)',
            'Accept': 'text/html',
        })
        with urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except (HTTPError, URLError) as e:
        print(f"[SEP] Error fetching {url}: {e}")
        return None


def parse_sep_tables(html: str) -> Dict:
    """
    Parse SEP HTML into structured data.

    Returns dict with projections for each variable.
    """
    parser = SEPTableParser()
    parser.feed(html)

    projections = {
        'gdp': {},
        'unemployment': {},
        'pce_inflation': {},
        'core_pce': {},
        'fed_funds': {},
    }

    # Map table headers to our keys
    variable_map = {
        'change in real gdp': 'gdp',
        'real gdp': 'gdp',
        'unemployment rate': 'unemployment',
        'pce inflation': 'pce_inflation',
        'core pce inflation': 'core_pce',
        'core pce': 'core_pce',
        'federal funds rate': 'fed_funds',
    }

    for table in parser.tables:
        if not table:
            continue

        # Try to identify which variable this table is for
        current_var = None
        years = []

        for row in table:
            row_text = ' '.join(row).lower()

            # Check if this row identifies the variable
            for key_phrase, var_name in variable_map.items():
                if key_phrase in row_text:
                    current_var = var_name
                    break

            # Look for year headers
            year_pattern = re.findall(r'\b(202\d|longer\s*run)\b', row_text, re.IGNORECASE)
            if year_pattern and len(year_pattern) >= 3:
                years = [y.lower().replace(' ', '_') for y in year_pattern]

            # Look for median projections
            if current_var and years and 'median' in row_text:
                # Extract numeric values
                values = []
                for cell in row:
                    # Match numbers like 2.5, 4.2, etc.
                    match = re.search(r'(\d+\.?\d*)', cell)
                    if match:
                        values.append(float(match.group(1)))

                # Map values to years
                if values:
                    for i, year in enumerate(years):
                        if i < len(values):
                            projections[current_var][year] = {
                                'median': values[i],
                            }

    return projections


def get_sep_data(force_refresh: bool = False) -> Dict:
    """
    Get current SEP projections.

    Returns structured projection data with caching.
    """
    global _sep_cache, _sep_cache_time

    # Check cache
    if not force_refresh and _sep_cache and _sep_cache_time:
        if datetime.now() - _sep_cache_time < SEP_CACHE_TTL:
            return _sep_cache

    url, meeting_date = get_latest_sep_url()
    html = fetch_sep_html(url)

    if not html:
        # Return hardcoded fallback (December 2024 SEP)
        return get_fallback_sep()

    projections = parse_sep_tables(html)

    # If parsing failed, use fallback
    if not any(projections[k] for k in projections):
        return get_fallback_sep()

    result = {
        'meeting_date': meeting_date,
        'source_url': url,
        'projections': projections,
        'fetched_at': datetime.now().isoformat(),
    }

    # Cache it
    _sep_cache = result
    _sep_cache_time = datetime.now()

    return result


def get_fallback_sep() -> Dict:
    """
    Hardcoded SEP data as fallback when scraping fails.
    Updated from December 2024 FOMC meeting.
    """
    return {
        'meeting_date': 'December 2024',
        'source_url': 'https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20241218.htm',
        'projections': {
            'gdp': {
                '2024': {'median': 2.5, 'range': (2.3, 2.7)},
                '2025': {'median': 2.1, 'range': (1.6, 2.5)},
                '2026': {'median': 2.0, 'range': (1.4, 2.5)},
                '2027': {'median': 1.9, 'range': (1.5, 2.5)},
                'longer_run': {'median': 1.8, 'range': (1.7, 2.5)},
            },
            'unemployment': {
                '2024': {'median': 4.2, 'range': (4.2, 4.2)},
                '2025': {'median': 4.3, 'range': (4.2, 4.5)},
                '2026': {'median': 4.3, 'range': (3.9, 4.6)},
                '2027': {'median': 4.3, 'range': (3.8, 4.5)},
                'longer_run': {'median': 4.2, 'range': (3.5, 4.5)},
            },
            'pce_inflation': {
                '2024': {'median': 2.4, 'range': (2.4, 2.7)},
                '2025': {'median': 2.5, 'range': (2.1, 2.9)},
                '2026': {'median': 2.1, 'range': (2.0, 2.6)},
                '2027': {'median': 2.0, 'range': (2.0, 2.4)},
                'longer_run': {'median': 2.0, 'range': (2.0, 2.0)},
            },
            'core_pce': {
                '2024': {'median': 2.8, 'range': (2.8, 2.9)},
                '2025': {'median': 2.5, 'range': (2.1, 3.2)},
                '2026': {'median': 2.2, 'range': (2.0, 2.7)},
                '2027': {'median': 2.0, 'range': (2.0, 2.6)},
            },
            'fed_funds': {
                '2024': {'median': 4.4, 'range': (4.4, 4.6)},
                '2025': {'median': 3.9, 'range': (3.1, 4.4)},
                '2026': {'median': 3.4, 'range': (2.4, 3.9)},
                '2027': {'median': 3.1, 'range': (2.4, 3.9)},
                'longer_run': {'median': 3.0, 'range': (2.4, 3.9)},
            },
        },
        'is_fallback': True,
    }


# =============================================================================
# QUERY INTERFACE
# =============================================================================

def is_sep_query(query: str) -> bool:
    """Check if query is asking about Fed projections/SEP."""
    query_lower = query.lower()

    sep_keywords = [
        'fed project', 'fed forecast', 'fed expect', 'fed predict',
        'fomc project', 'fomc forecast', 'fomc expect',
        'sep', 'summary of economic projections',
        'dot plot', 'rate path', 'rate projection',
        'where does the fed see', 'what does the fed expect',
        'fed outlook', 'fed\'s outlook', 'fed median',
        'how many rate cuts', 'how many cuts',
        'terminal rate', 'neutral rate',
        'inflation outlook', 'gdp outlook', 'economic outlook',
        'rate outlook', 'unemployment outlook',
    ]

    return any(kw in query_lower for kw in sep_keywords)


def is_fed_related_query(query: str) -> bool:
    """
    Check if query is related to the Fed, interest rates, or monetary policy.

    This is a BROADER check than is_sep_query - it catches any Fed-related
    query where we should show Fed guidance prominently.

    Keywords that trigger Fed guidance:
    - "fed", "fomc", "federal reserve", "powell"
    - "rate cut", "rate hike", "monetary policy"
    - "dot plot", "rate path", "terminal rate"

    Returns:
        True if the query is Fed-related and should display Fed guidance
    """
    query_lower = query.lower()

    # Core Fed-related terms
    fed_core_keywords = [
        'fed', 'fomc', 'federal reserve', 'powell', 'jerome powell',
    ]

    # Rate-related terms
    rate_keywords = [
        'rate cut', 'rate hike', 'rate increase', 'rate decrease',
        'cutting rates', 'raising rates', 'hiking rates',
        'rate decision', 'rate announcement',
        'fed funds', 'federal funds rate', 'policy rate',
        'interest rate', 'benchmark rate',
    ]

    # Monetary policy terms
    policy_keywords = [
        'monetary policy', 'policy stance', 'tightening', 'easing',
        'hawkish', 'dovish', 'pivot',
        'quantitative tightening', 'qt', 'balance sheet',
    ]

    # Forward guidance terms (also triggers SEP)
    guidance_keywords = [
        'dot plot', 'rate path', 'terminal rate', 'neutral rate',
        'rate outlook', 'where rates are going', 'future rates',
        'how many cuts', 'how many hikes',
    ]

    all_keywords = fed_core_keywords + rate_keywords + policy_keywords + guidance_keywords

    return any(kw in query_lower for kw in all_keywords)


def get_fed_guidance_for_query(query: str) -> Optional[Dict]:
    """
    Get Fed guidance (SEP projections + FOMC statement summary) for Fed-related queries.

    This is the MAIN function to call for Fed-related queries. It provides:
    1. Current Fed funds rate
    2. FOMC's projected path (from the dot plot)
    3. Key quotes/highlights from recent FOMC statements

    Args:
        query: User's query string

    Returns:
        Dict with current_rate, projections, and fomc_summary, or None if not Fed-related
    """
    # Use the broader check - show Fed guidance for any Fed-related query
    if not is_fed_related_query(query):
        return None

    query_lower = query.lower()

    # Get current rate info
    current_rate = get_current_fed_funds_rate()

    # Get SEP projections (always include for Fed queries - the dot plot is key)
    sep_data = get_sep_data()

    # Determine which projections are relevant based on query
    relevant_vars = []

    if any(w in query_lower for w in ['gdp', 'growth', 'economy', 'output']):
        relevant_vars.append('gdp')
    if any(w in query_lower for w in ['unemployment', 'jobs', 'labor']):
        relevant_vars.append('unemployment')
    if any(w in query_lower for w in ['inflation', 'pce', 'prices', 'cpi']):
        relevant_vars.extend(['pce_inflation', 'core_pce'])

    # Always include fed_funds for any Fed-related query (the key metric)
    relevant_vars.append('fed_funds')

    # Remove duplicates while preserving order
    relevant_vars = list(dict.fromkeys(relevant_vars))

    # Get recent FOMC statement summary
    fomc_summary = get_recent_fomc_summary()

    return {
        'current_rate': current_rate,
        'meeting_date': sep_data['meeting_date'],
        'source_url': sep_data.get('source_url', ''),
        'projections': {k: sep_data['projections'].get(k, {}) for k in relevant_vars},
        'is_fallback': sep_data.get('is_fallback', False),
        'fomc_summary': fomc_summary,
    }


def get_sep_for_query(query: str) -> Optional[Dict]:
    """
    Get relevant SEP data based on query.

    NOTE: For broader Fed-related queries, use get_fed_guidance_for_query() instead.
    This function is kept for backward compatibility and SEP-specific queries.

    Returns formatted data for display.
    """
    # First try the broader Fed check - this ensures Fed guidance shows for more queries
    fed_guidance = get_fed_guidance_for_query(query)
    if fed_guidance:
        return fed_guidance

    # Fallback to original SEP-only check (for backward compatibility)
    if not is_sep_query(query):
        return None

    sep_data = get_sep_data()
    query_lower = query.lower()

    # Determine which projections are relevant
    relevant_vars = []

    if any(w in query_lower for w in ['gdp', 'growth', 'economy', 'output']):
        relevant_vars.append('gdp')
    if any(w in query_lower for w in ['unemployment', 'jobs', 'labor']):
        relevant_vars.append('unemployment')
    if any(w in query_lower for w in ['inflation', 'pce', 'prices', 'cpi']):
        relevant_vars.extend(['pce_inflation', 'core_pce'])
    if any(w in query_lower for w in ['rate', 'fed funds', 'interest', 'cut', 'hike', 'dot plot', 'terminal', 'neutral']):
        relevant_vars.append('fed_funds')

    # If no specific variable mentioned, return all
    if not relevant_vars:
        relevant_vars = ['gdp', 'unemployment', 'pce_inflation', 'fed_funds']

    # Remove duplicates while preserving order
    relevant_vars = list(dict.fromkeys(relevant_vars))

    return {
        'meeting_date': sep_data['meeting_date'],
        'source_url': sep_data.get('source_url', ''),
        'projections': {k: sep_data['projections'].get(k, {}) for k in relevant_vars},
        'is_fallback': sep_data.get('is_fallback', False),
    }


# =============================================================================
# REAL RATE CALCULATION
# =============================================================================

def compute_real_rate(nominal_rate: float, inflation_rate: float) -> Dict:
    """
    Calculate the real Fed funds rate (nominal - inflation).

    The real rate is what matters for economic impact. A 5% nominal rate with
    3% inflation is only 2% in real terms - much less restrictive than it appears.

    Args:
        nominal_rate: Current effective Fed funds rate (e.g., 4.33%)
        inflation_rate: Core PCE or CPI inflation rate (e.g., 2.8%)

    Returns:
        Dict with:
            - real_rate: The real Fed funds rate
            - nominal_rate: The nominal rate used
            - inflation_rate: The inflation rate used
            - neutral_real_rate: Estimated neutral real rate (0.5-1.0%)
            - stance: "restrictive", "neutral", or "accommodative"
            - stance_degree: "mildly", "moderately", or "significantly"
    """
    real_rate = nominal_rate - inflation_rate

    # Neutral real rate estimates (from FOMC longer-run projections minus 2% inflation target)
    # Fed's longer-run neutral nominal rate is ~3.0%, minus 2% inflation = ~1.0% real neutral
    neutral_real_rate_low = 0.5
    neutral_real_rate_high = 1.0
    neutral_midpoint = (neutral_real_rate_low + neutral_real_rate_high) / 2

    # Determine policy stance based on distance from neutral
    distance_from_neutral = real_rate - neutral_midpoint

    if distance_from_neutral > 1.5:
        stance = "restrictive"
        stance_degree = "significantly"
    elif distance_from_neutral > 0.75:
        stance = "restrictive"
        stance_degree = "moderately"
    elif distance_from_neutral > 0.25:
        stance = "restrictive"
        stance_degree = "mildly"
    elif distance_from_neutral >= -0.25:
        stance = "neutral"
        stance_degree = ""
    elif distance_from_neutral >= -0.75:
        stance = "accommodative"
        stance_degree = "mildly"
    elif distance_from_neutral >= -1.5:
        stance = "accommodative"
        stance_degree = "moderately"
    else:
        stance = "accommodative"
        stance_degree = "significantly"

    return {
        'real_rate': real_rate,
        'nominal_rate': nominal_rate,
        'inflation_rate': inflation_rate,
        'neutral_real_rate_low': neutral_real_rate_low,
        'neutral_real_rate_high': neutral_real_rate_high,
        'stance': stance,
        'stance_degree': stance_degree,
    }


# =============================================================================
# QUERY-SPECIFIC FORMATTERS
# =============================================================================

def _format_dot_plot_response(guidance: Dict) -> str:
    """
    Format response for DOT PLOT / projection queries.

    Shows:
    - Full range of projections (not just median)
    - Distribution of participants at each year
    - Comparison context
    """
    sentences = []
    projections = guidance.get('projections', {})
    meeting = guidance.get('meeting_date', 'recent')
    current_rate = guidance.get('current_rate', {})
    ff = projections.get('fed_funds', {})

    # Current rate context
    if current_rate:
        target_low = current_rate.get('target_low')
        target_high = current_rate.get('target_high')
        if target_low and target_high:
            sentences.append(f"**Current Fed Funds Rate: {target_low:.2f}%-{target_high:.2f}%**")

    # Dot plot title
    sentences.append(f"**Dot Plot Summary ({meeting} SEP):**")

    # Show projections for each year with ranges
    years_to_show = ['2025', '2026', '2027', 'longer_run']
    dot_lines = []

    for year in years_to_show:
        if year in ff:
            data = ff[year]
            median = data.get('median')
            range_data = data.get('range', (None, None))

            if median:
                year_label = "Long Run" if year == "longer_run" else year
                if range_data and range_data[0] and range_data[1]:
                    range_low, range_high = range_data
                    spread = range_high - range_low
                    # Calculate implied cuts from current
                    if current_rate and year != 'longer_run':
                        current_midpoint = (current_rate.get('target_low', 4.25) + current_rate.get('target_high', 4.50)) / 2
                        if year == '2025':
                            implied_cuts = round((current_midpoint - median) / 0.25)
                            cuts_str = f" ({int(implied_cuts)} cuts implied)" if implied_cuts > 0 else ""
                        else:
                            cuts_str = ""
                    else:
                        cuts_str = ""
                    dot_lines.append(f"- **{year_label}:** Median {median:.1f}%, Range {range_low:.1f}%-{range_high:.1f}%{cuts_str}")
                else:
                    dot_lines.append(f"- **{year_label}:** Median {median:.1f}%")

    if dot_lines:
        sentences.append("\n".join(dot_lines))

    # Add interpretation
    ff_2025 = ff.get('2025', {}).get('median')
    ff_lr = ff.get('longer_run', {}).get('median')
    if ff_2025 and ff_lr:
        if ff_2025 > ff_lr:
            sentences.append(f"The dots show rates remaining above the {ff_lr}% neutral rate through 2025, indicating a gradual normalization path.")

    # Add range context
    range_2025 = ff.get('2025', {}).get('range')
    if range_2025 and range_2025[0] and range_2025[1]:
        spread = range_2025[1] - range_2025[0]
        if spread > 1.0:
            sentences.append(f"Note the wide spread in 2025 projections ({spread:.1f}pp) - participants have significant disagreement about the rate path.")

    # Source
    sentences.append(f"*Source: {meeting} FOMC Summary of Economic Projections*")

    return "\n\n".join(sentences)


def _format_policy_stance_response(guidance: Dict) -> str:
    """
    Format response for POLICY STANCE queries ("too tight?", "restrictive?").

    Shows:
    - Real Fed funds rate calculation
    - Comparison to neutral rate
    - Conclusion about stance
    """
    sentences = []
    projections = guidance.get('projections', {})
    meeting = guidance.get('meeting_date', 'recent')
    current_rate = guidance.get('current_rate', {})
    fomc_summary = guidance.get('fomc_summary', {})

    # Get current effective rate
    effective_rate = current_rate.get('effective_rate', 4.33) if current_rate else 4.33

    # Get current inflation (core PCE from projections, or use 2024 value)
    core_pce = projections.get('core_pce', {})
    # Use 2024 actual or latest estimate
    current_inflation = core_pce.get('2024', {}).get('median', 2.8)

    # Compute real rate
    real_rate_info = compute_real_rate(effective_rate, current_inflation)

    # Build response
    sentences.append("**Policy Stance Analysis:**")

    # Show calculation
    sentences.append(f"- **Nominal Fed Funds Rate:** {effective_rate:.2f}%")
    sentences.append(f"- **Core PCE Inflation:** {current_inflation:.1f}%")
    sentences.append(f"- **Real Fed Funds Rate:** {real_rate_info['real_rate']:.2f}% (nominal - inflation)")

    # Neutral rate context
    sentences.append(f"- **Estimated Neutral Real Rate:** {real_rate_info['neutral_real_rate_low']:.1f}%-{real_rate_info['neutral_real_rate_high']:.1f}%")

    # Stance conclusion
    stance = real_rate_info['stance']
    degree = real_rate_info['stance_degree']
    real_rate = real_rate_info['real_rate']
    neutral_mid = (real_rate_info['neutral_real_rate_low'] + real_rate_info['neutral_real_rate_high']) / 2

    if stance == "restrictive":
        diff = real_rate - neutral_mid
        conclusion = f"**Conclusion:** Policy is **{degree} {stance}**. The real Fed funds rate ({real_rate:.2f}%) is {diff:.1f}pp above the neutral range, which should slow economic activity and reduce inflation."
    elif stance == "accommodative":
        diff = neutral_mid - real_rate
        conclusion = f"**Conclusion:** Policy is **{degree} {stance}**. The real Fed funds rate ({real_rate:.2f}%) is {diff:.1f}pp below the neutral range, which should stimulate economic activity."
    else:
        conclusion = f"**Conclusion:** Policy is **roughly neutral**. The real Fed funds rate ({real_rate:.2f}%) is close to the estimated neutral range."

    sentences.append(conclusion)

    # Add FOMC's own assessment if available
    if fomc_summary:
        key_quote = fomc_summary.get('key_quote')
        if key_quote:
            sentences.append(f'*FOMC Assessment: "{key_quote}"*')

    # Inflation outlook
    core_2025 = core_pce.get('2025', {}).get('median')
    if core_2025 and current_inflation:
        if core_2025 < current_inflation:
            sentences.append(f"With core PCE projected to fall to {core_2025}% in 2025, the real rate would rise further (become more restrictive) unless the Fed cuts nominal rates.")

    sentences.append(f"*({meeting} FOMC)*")

    return "\n\n".join(sentences)


def _format_rate_outlook_response(guidance: Dict) -> str:
    """
    Format response for RATE OUTLOOK queries ("will Fed cut?", "rate path?").

    Shows:
    - Next meeting expectations
    - Dot plot path
    - Key data dependencies
    """
    sentences = []
    projections = guidance.get('projections', {})
    meeting = guidance.get('meeting_date', 'recent')
    current_rate = guidance.get('current_rate', {})
    fomc_summary = guidance.get('fomc_summary', {})
    ff = projections.get('fed_funds', {})

    # Current rate
    if current_rate:
        target_low = current_rate.get('target_low')
        target_high = current_rate.get('target_high')
        last_change = current_rate.get('last_change')
        direction = current_rate.get('last_change_direction', '')
        size = current_rate.get('last_change_size', 0)

        if target_low and target_high:
            rate_str = f"**Current Fed Funds Rate: {target_low:.2f}%-{target_high:.2f}%**"
            if last_change and direction and size:
                rate_str += f"\nLast action: {direction} {size} bps on {last_change}"
            sentences.append(rate_str)

    # Rate path from dot plot
    sentences.append("**Rate Path (Dot Plot Median):**")

    ff_2025 = ff.get('2025', {}).get('median')
    ff_2026 = ff.get('2026', {}).get('median')
    ff_2027 = ff.get('2027', {}).get('median')
    ff_lr = ff.get('longer_run', {}).get('median')

    if current_rate:
        current_midpoint = (current_rate.get('target_low', 4.25) + current_rate.get('target_high', 4.50)) / 2
    else:
        current_midpoint = 4.375

    # Calculate implied cuts
    if ff_2025:
        cuts_2025 = round((current_midpoint - ff_2025) / 0.25)
        sentences.append(f"- **2025:** {ff_2025:.2f}% ({int(cuts_2025)} cuts from current)")
    if ff_2026:
        cuts_2026 = round((ff_2025 - ff_2026) / 0.25) if ff_2025 else 0
        sentences.append(f"- **2026:** {ff_2026:.2f}% ({int(cuts_2026)} additional cuts)")
    if ff_2027:
        sentences.append(f"- **2027:** {ff_2027:.2f}%")
    if ff_lr:
        sentences.append(f"- **Long Run (Neutral):** {ff_lr:.2f}%")

    # FOMC tone and statement highlights
    if fomc_summary:
        tone = fomc_summary.get('tone', '')
        highlights = fomc_summary.get('highlights', [])
        key_quote = fomc_summary.get('key_quote')

        if tone:
            tone_display = tone.capitalize()
            sentences.append(f"**Recent FOMC Tone:** {tone_display}")

        if key_quote:
            sentences.append(f'*"{key_quote}"*')

        if highlights:
            sentences.append("**Key Takeaways:**")
            for h in highlights[:3]:  # Show top 3
                sentences.append(f"- {h}")

    # Data dependencies
    sentences.append("**What the Fed is Watching:**")
    sentences.append("- Inflation progress (core PCE toward 2%)")
    sentences.append("- Labor market conditions (unemployment, payrolls)")
    sentences.append("- Financial conditions and economic data")

    sentences.append(f"*({meeting} FOMC)*")

    return "\n\n".join(sentences)


def _format_general_fed_response(guidance: Dict) -> str:
    """
    Format general Fed response (default case).

    Shows balanced overview of rate, projections, and FOMC statement.
    """
    # This is essentially the original format_sep_for_display logic
    if not guidance:
        return ""

    projections = guidance.get('projections', {})
    meeting = guidance.get('meeting_date', 'recent')
    current_rate = guidance.get('current_rate', {})
    fomc_summary = guidance.get('fomc_summary', {})

    sentences = []

    # Current Fed funds rate
    if current_rate:
        target_low = current_rate.get('target_low')
        target_high = current_rate.get('target_high')
        last_change = current_rate.get('last_change')
        direction = current_rate.get('last_change_direction', '')
        size = current_rate.get('last_change_size', 0)

        if target_low and target_high:
            rate_str = f"**Current Fed Funds Rate: {target_low:.2f}%-{target_high:.2f}%**"
            if last_change and direction and size:
                rate_str += f" (last {direction}: {size} bps on {last_change})"
            sentences.append(rate_str)

    # FOMC key quote
    if fomc_summary:
        key_quote = fomc_summary.get('key_quote')
        if key_quote:
            sentences.append(f'*"{key_quote}"*')

    # Fed funds rate path (dot plot)
    if 'fed_funds' in projections:
        ff = projections['fed_funds']
        ff_2025 = ff.get('2025', {}).get('median')
        ff_2026 = ff.get('2026', {}).get('median')
        ff_lr = ff.get('longer_run', {}).get('median')

        current_midpoint = 4.4
        if current_rate:
            target_low = current_rate.get('target_low', 4.25)
            target_high = current_rate.get('target_high', 4.50)
            current_midpoint = (target_low + target_high) / 2

        if ff_2025 and ff_2026:
            cuts_2025 = round((current_midpoint - ff_2025) / 0.25)
            cuts_2026 = round((ff_2025 - ff_2026) / 0.25)

            if cuts_2025 > 0 and cuts_2026 > 0:
                sentences.append(f"**Dot Plot Path:** The median projection shows the fed funds rate falling to {ff_2025}% by end of 2025 and {ff_2026}% by end of 2026, implying roughly {int(cuts_2025 + cuts_2026)} quarter-point cuts over two years.")
            elif cuts_2025 > 0:
                sentences.append(f"**Dot Plot Path:** The median projection shows the fed funds rate at {ff_2025}% by end of 2025 ({int(cuts_2025)} cuts from current levels).")
            elif ff_lr:
                sentences.append(f"**Dot Plot Path:** The median fed funds rate projection is {ff_2025}% for 2025, with a long-run neutral rate of {ff_lr}%.")

    # FOMC highlights
    if fomc_summary:
        highlights = fomc_summary.get('highlights', [])
        tone = fomc_summary.get('tone', '')
        if highlights and len(highlights) > 0:
            tone_str = ""
            if tone == 'hawkish':
                tone_str = " (hawkish)"
            elif tone == 'dovish':
                tone_str = " (dovish)"
            sentences.append(f"**Key Takeaways{tone_str}:** {highlights[0]}")

    if not sentences:
        return ""

    narrative = " ".join(sentences)

    if guidance.get('is_fallback'):
        narrative += f" *(Based on {meeting} FOMC projections; more recent data may be available.)*"
    else:
        narrative += f" *({meeting} FOMC)*"

    return narrative


def format_fed_guidance_for_query(query: str, guidance: Dict) -> str:
    """
    Format Fed guidance based on query type.

    Routes to appropriate formatter based on what the user is asking:
    - DOT PLOT queries: Show full range of projections, participant distribution
    - POLICY STANCE queries: Compute real rate, compare to neutral
    - RATE OUTLOOK queries: Focus on next meeting expectations, data dependencies
    - GENERAL queries: Balanced overview

    Args:
        query: The user's query string
        guidance: Dict from get_fed_guidance_for_query()

    Returns:
        Formatted string tailored to the query type
    """
    if not guidance:
        return ""

    query_lower = query.lower()

    # Route to appropriate formatter based on query type
    if 'dot plot' in query_lower or 'projection' in query_lower or 'dots' in query_lower:
        return _format_dot_plot_response(guidance)
    elif any(term in query_lower for term in ['too tight', 'too loose', 'restrictive', 'accommodative', 'stance', 'real rate']):
        return _format_policy_stance_response(guidance)
    elif any(term in query_lower for term in ['cut', 'hike', 'raise', 'lower', 'next meeting', 'rate path', 'when will']):
        return _format_rate_outlook_response(guidance)
    else:
        return _format_general_fed_response(guidance)


def format_sep_for_display(sep_data: Dict) -> str:
    """
    Format SEP data for display in the UI.

    Returns a narrative explanation of Fed projections including:
    - Current Fed funds rate
    - FOMC's projected rate path (dot plot)
    - Key quotes from recent FOMC statements

    NOTE: For query-specific formatting, use format_fed_guidance_for_query() instead.
    This function is kept for backward compatibility and returns general formatting.

    Args:
        sep_data: Dict from get_sep_for_query() or get_fed_guidance_for_query()

    Returns:
        Formatted narrative string for display
    """
    if not sep_data:
        return ""

    projections = sep_data.get('projections', {})
    meeting = sep_data.get('meeting_date', 'recent')
    current_rate = sep_data.get('current_rate', {})
    fomc_summary = sep_data.get('fomc_summary', {})

    sentences = []

    # ==========================================================================
    # CURRENT FED FUNDS RATE (always show first for Fed queries)
    # ==========================================================================
    if current_rate:
        target_low = current_rate.get('target_low')
        target_high = current_rate.get('target_high')
        last_change = current_rate.get('last_change')
        direction = current_rate.get('last_change_direction', '')
        size = current_rate.get('last_change_size', 0)

        if target_low and target_high:
            rate_str = f"**Current Fed Funds Rate: {target_low:.2f}%-{target_high:.2f}%**"
            if last_change and direction and size:
                rate_str += f" (last {direction}: {size} bps on {last_change})"
            sentences.append(rate_str)

    # ==========================================================================
    # FOMC STATEMENT KEY QUOTE (if available)
    # ==========================================================================
    if fomc_summary:
        key_quote = fomc_summary.get('key_quote')
        if key_quote:
            sentences.append(f'*"{key_quote}"*')

    # ==========================================================================
    # GDP PROJECTION
    # ==========================================================================
    if 'gdp' in projections:
        gdp = projections['gdp']
        gdp_2025 = gdp.get('2025', {}).get('median')
        gdp_lr = gdp.get('longer_run', {}).get('median')
        if gdp_2025:
            if gdp_lr and gdp_2025 > gdp_lr:
                sentences.append(f"FOMC participants expect GDP growth of {gdp_2025}% in 2025, gradually slowing toward the {gdp_lr}% long-run trend.")
            else:
                sentences.append(f"FOMC participants expect GDP growth of {gdp_2025}% in 2025.")

    # ==========================================================================
    # UNEMPLOYMENT PROJECTION
    # ==========================================================================
    if 'unemployment' in projections:
        unemp = projections['unemployment']
        unemp_2025 = unemp.get('2025', {}).get('median')
        unemp_lr = unemp.get('longer_run', {}).get('median')
        if unemp_2025:
            if unemp_lr:
                diff = unemp_2025 - unemp_lr
                if abs(diff) < 0.2:
                    sentences.append(f"Unemployment is projected to hold steady around {unemp_2025}%, near the {unemp_lr}% long-run level.")
                elif diff > 0:
                    sentences.append(f"Unemployment is projected at {unemp_2025}% in 2025, slightly above the {unemp_lr}% long-run estimate.")
                else:
                    sentences.append(f"Unemployment is projected at {unemp_2025}% in 2025.")

    # ==========================================================================
    # INFLATION PROJECTION
    # ==========================================================================
    if 'pce_inflation' in projections or 'core_pce' in projections:
        pce = projections.get('pce_inflation', {})
        core = projections.get('core_pce', {})
        pce_2025 = pce.get('2025', {}).get('median')
        pce_2027 = pce.get('2027', {}).get('median')
        core_2025 = core.get('2025', {}).get('median')

        if pce_2025 and pce_2027:
            if pce_2025 > 2.0 and pce_2027 <= 2.0:
                sentences.append(f"Inflation is expected to remain elevated at {pce_2025}% in 2025 before returning to the 2% target by 2027.")
            elif pce_2025 > 2.0:
                sentences.append(f"Inflation is projected at {pce_2025}% in 2025, still above the 2% target.")
            else:
                sentences.append(f"Inflation is projected at {pce_2025}% in 2025.")
        elif core_2025:
            sentences.append(f"Core PCE inflation is projected at {core_2025}% in 2025.")

    # ==========================================================================
    # FED FUNDS RATE PATH (DOT PLOT) - most important for Fed queries
    # ==========================================================================
    if 'fed_funds' in projections:
        ff = projections['fed_funds']
        ff_2025 = ff.get('2025', {}).get('median')
        ff_2026 = ff.get('2026', {}).get('median')
        ff_lr = ff.get('longer_run', {}).get('median')

        # Use current rate if available, otherwise fallback to 4.4%
        current_midpoint = 4.4
        if current_rate:
            target_low = current_rate.get('target_low', 4.25)
            target_high = current_rate.get('target_high', 4.50)
            current_midpoint = (target_low + target_high) / 2

        if ff_2025 and ff_2026:
            cuts_2025 = round((current_midpoint - ff_2025) / 0.25)
            cuts_2026 = round((ff_2025 - ff_2026) / 0.25)

            if cuts_2025 > 0 and cuts_2026 > 0:
                sentences.append(f"**Dot Plot Path:** The median projection shows the fed funds rate falling to {ff_2025}% by end of 2025 and {ff_2026}% by end of 2026, implying roughly {int(cuts_2025 + cuts_2026)} quarter-point cuts over two years.")
            elif cuts_2025 > 0:
                sentences.append(f"**Dot Plot Path:** The median projection shows the fed funds rate at {ff_2025}% by end of 2025 ({int(cuts_2025)} cuts from current levels).")
            elif ff_lr:
                sentences.append(f"**Dot Plot Path:** The median fed funds rate projection is {ff_2025}% for 2025, with a long-run neutral rate of {ff_lr}%.")
            else:
                sentences.append(f"**Dot Plot Path:** The median fed funds rate projection is {ff_2025}% for 2025.")
        elif ff_lr:
            sentences.append(f"**Long-Run Neutral Rate:** {ff_lr}% (FOMC median estimate).")

    # ==========================================================================
    # FOMC STATEMENT HIGHLIGHTS (key takeaways)
    # ==========================================================================
    if fomc_summary:
        highlights = fomc_summary.get('highlights', [])
        tone = fomc_summary.get('tone', '')
        if highlights and len(highlights) > 0:
            # Add tone indicator
            tone_str = ""
            if tone == 'hawkish':
                tone_str = " (hawkish)"
            elif tone == 'dovish':
                tone_str = " (dovish)"
            sentences.append(f"**Key Takeaways{tone_str}:** {highlights[0]}")

    if not sentences:
        return ""

    # Combine into narrative
    narrative = " ".join(sentences)

    # Add source note
    if sep_data.get('is_fallback'):
        narrative += f" *(Based on {meeting} FOMC projections; more recent data may be available.)*"
    else:
        narrative += f" *({meeting} FOMC)*"

    return narrative


def get_sep_series_data(variable: str) -> Tuple[List[str], List[float], Dict]:
    """
    Get SEP projection as time series data (for charting).

    Args:
        variable: One of 'gdp', 'unemployment', 'pce_inflation', 'core_pce', 'fed_funds'

    Returns:
        (dates, values, info) tuple compatible with chart builder
    """
    sep_data = get_sep_data()
    projections = sep_data['projections'].get(variable, {})

    if not projections:
        return [], [], {'error': f'No SEP data for {variable}'}

    var_names = {
        'gdp': 'Real GDP Growth',
        'unemployment': 'Unemployment Rate',
        'pce_inflation': 'PCE Inflation',
        'core_pce': 'Core PCE Inflation',
        'fed_funds': 'Federal Funds Rate',
    }

    dates = []
    values = []

    # Convert year keys to dates (use Q4 of each year)
    year_order = ['2024', '2025', '2026', '2027', 'longer_run']

    for year in year_order:
        if year in projections:
            median = projections[year].get('median')
            if median is not None:
                if year == 'longer_run':
                    # Use 2030 as proxy for long run
                    dates.append('2030-12-31')
                else:
                    dates.append(f'{year}-12-31')
                values.append(median)

    info = {
        'id': f'sep_{variable}',
        'title': f'FOMC Projection: {var_names.get(variable, variable)}',
        'description': f'Median FOMC participant projection for {var_names.get(variable, variable).lower()}',
        'units': 'percent',
        'frequency': 'annual',
        'source': 'Federal Reserve',
        'source_url': sep_data.get('source_url', ''),
        'meeting_date': sep_data.get('meeting_date', ''),
        'is_projection': True,
    }

    return dates, values, info


# =============================================================================
# SERIES CATALOG ENTRIES
# =============================================================================

SEP_SERIES = {
    'sep_gdp': {
        'name': 'FOMC GDP Growth Projection',
        'variable': 'gdp',
        'description': 'Median FOMC projection for real GDP growth',
        'keywords': ['gdp projection', 'fed gdp forecast', 'growth outlook'],
    },
    'sep_unemployment': {
        'name': 'FOMC Unemployment Projection',
        'variable': 'unemployment',
        'description': 'Median FOMC projection for unemployment rate',
        'keywords': ['unemployment projection', 'fed jobs forecast'],
    },
    'sep_pce_inflation': {
        'name': 'FOMC PCE Inflation Projection',
        'variable': 'pce_inflation',
        'description': 'Median FOMC projection for PCE inflation',
        'keywords': ['inflation projection', 'fed inflation forecast'],
    },
    'sep_core_pce': {
        'name': 'FOMC Core PCE Projection',
        'variable': 'core_pce',
        'description': 'Median FOMC projection for core PCE inflation',
        'keywords': ['core inflation projection', 'fed core pce forecast'],
    },
    'sep_fed_funds': {
        'name': 'FOMC Fed Funds Rate Projection',
        'variable': 'fed_funds',
        'description': 'Median FOMC projection for federal funds rate (dot plot)',
        'keywords': ['dot plot', 'rate path', 'fed funds projection', 'terminal rate'],
    },
}


def search_sep_series(query: str) -> List[str]:
    """
    Search for SEP series matching a query.

    Returns list of matching series keys.
    """
    query_lower = query.lower()
    matches = []

    for key, info in SEP_SERIES.items():
        # Check keywords
        if any(kw in query_lower for kw in info['keywords']):
            matches.append(key)
            continue
        # Check name
        if any(word in info['name'].lower() for word in query_lower.split()):
            matches.append(key)

    return matches


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    print("Testing Fed SEP integration...\n")

    # Test fetching data
    sep = get_sep_data()
    print(f"Meeting: {sep['meeting_date']}")
    print(f"Source: {sep.get('source_url', 'fallback')}")
    print(f"Is fallback: {sep.get('is_fallback', False)}")
    print()

    # Print projections
    for var, data in sep['projections'].items():
        if data:
            print(f"{var}:")
            for year, proj in sorted(data.items()):
                median = proj.get('median', 'N/A')
                print(f"  {year}: {median}%")
            print()

    # Test current rate
    print("Current Fed Funds Rate:")
    rate = get_current_fed_funds_rate()
    print(f"  Target: {rate['target_low']:.2f}%-{rate['target_high']:.2f}%")
    print(f"  Last change: {rate['last_change']} ({rate['last_change_direction']} {rate['last_change_size']} bps)")
    print()

    # Test FOMC summary
    print("Recent FOMC Statement Summary:")
    summary = get_recent_fomc_summary()
    if summary:
        print(f"  Date: {summary['date']}")
        print(f"  Decision: {summary['rate_decision']}")
        print(f"  Tone: {summary['tone']}")
        print(f"  Key quote: \"{summary['key_quote']}\"")
        print(f"  Highlights:")
        for h in summary.get('highlights', []):
            print(f"    - {h}")
    print()

    # Test SEP-specific query matching
    sep_test_queries = [
        "what does the fed expect for gdp",
        "dot plot",
        "fed rate projections",
        "how many rate cuts in 2025",
        "inflation outlook",
    ]

    print("SEP-specific query matching (is_sep_query):")
    for q in sep_test_queries:
        result = is_sep_query(q)
        print(f"  '{q}' -> {result}")
    print()

    # Test BROADER Fed-related query matching (NEW)
    fed_test_queries = [
        "fed",  # Core keyword
        "fomc",  # Core keyword
        "federal reserve",  # Core keyword
        "powell",  # Powell
        "rate cut",  # Rate action
        "rate hike",  # Rate action
        "monetary policy",  # Policy
        "what is the fed doing",  # Natural question
        "when will the fed cut rates",  # Natural question
        "hawkish or dovish",  # Tone
        "interest rates",  # General rates
        "fed funds rate",  # Specific rate
        "terminal rate",  # Forward guidance
        "neutral rate",  # Forward guidance
        "dot plot",  # Projections
        "rate path",  # Projections
        "quantitative tightening",  # Policy detail
        "balance sheet",  # Policy detail
        "unemployment rate",  # Should NOT match (not Fed-specific)
        "GDP growth",  # Should NOT match (not Fed-specific)
    ]

    print("Broader Fed-related query matching (is_fed_related_query):")
    for q in fed_test_queries:
        result = is_fed_related_query(q)
        status = "MATCH" if result else "no match"
        print(f"  '{q}' -> {status}")
    print()

    # Test compute_real_rate function
    print("=" * 60)
    print("Testing compute_real_rate():")
    print("=" * 60)
    test_cases = [
        (4.33, 2.8),  # Current situation
        (5.0, 3.0),   # More restrictive
        (3.0, 2.0),   # Near neutral
        (1.0, 3.0),   # Accommodative (negative real)
    ]
    for nominal, inflation in test_cases:
        result = compute_real_rate(nominal, inflation)
        print(f"  Nominal: {nominal}%, Inflation: {inflation}%")
        print(f"    Real Rate: {result['real_rate']:.2f}%")
        print(f"    Stance: {result['stance_degree']} {result['stance']}")
        print()

    # Test query-specific formatters (THE FIX - different queries get different output)
    query_specific_tests = [
        ("What is the dot plot showing?", "DOT PLOT"),
        ("Is monetary policy too tight?", "POLICY STANCE"),
        ("Will the Fed cut rates?", "RATE OUTLOOK"),
        ("What is the Fed doing?", "GENERAL"),
    ]

    print("=" * 60)
    print("QUERY-SPECIFIC FORMATTING (the fix!)")
    print("=" * 60)
    print()

    for query, query_type in query_specific_tests:
        print("=" * 60)
        print(f"Query: '{query}' ({query_type})")
        print("=" * 60)
        guidance = get_fed_guidance_for_query(query)
        formatted = format_fed_guidance_for_query(query, guidance)
        print(formatted)
        print()
        print()

    # Show that the outputs are DIFFERENT (not identical)
    print("=" * 60)
    print("VERIFICATION: Different queries produce different outputs")
    print("=" * 60)

    queries = [
        "What is the dot plot showing?",
        "Is monetary policy too tight?",
        "Will the Fed cut rates?",
    ]

    outputs = []
    for q in queries:
        guidance = get_fed_guidance_for_query(q)
        formatted = format_fed_guidance_for_query(q, guidance)
        outputs.append((q, len(formatted), formatted[:100] + "..."))

    for q, length, preview in outputs:
        print(f"  '{q}'")
        print(f"    Length: {length} chars, Preview: {preview}")
        print()

    # Check they're different
    all_different = len(set(o[1] for o in outputs)) == len(outputs)
    print(f"  All outputs different lengths? {all_different}")
