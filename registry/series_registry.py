"""
Unified Series Registry - Single Source of Truth

Consolidates:
- SERIES_DB (series metadata)
- QUERY_MAP (keyword -> series mappings)
- QUERY_PLANS (608 pre-built plans from JSON)

Provides O(1) lookup for query -> plan matching.
"""

import os
import json
import re
import difflib
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


@dataclass
class SeriesInfo:
    """Complete metadata for a single economic data series."""

    id: str
    name: str
    unit: str
    source: str = 'FRED'
    data_type: str = 'level'  # 'rate', 'index', 'level', 'growth_rate', 'spread'
    show_yoy: bool = False
    show_absolute_change: bool = False
    sa: bool = True  # Seasonally adjusted
    frequency: str = 'monthly'
    bullets: List[str] = field(default_factory=list)
    yoy_name: Optional[str] = None
    yoy_unit: Optional[str] = None
    benchmark: Optional[float] = None  # For threshold indicators like Sahm Rule


@dataclass
class QueryPlan:
    """Pre-computed plan for a query."""

    series: List[str]
    show_yoy: bool = False
    combine_chart: bool = False
    explanation: str = ''
    chart_groups: Optional[List[dict]] = None
    is_comparison: bool = False


# =============================================================================
# SERIES DATABASE - Metadata for all known series
# =============================================================================

SERIES_DB: Dict[str, SeriesInfo] = {
    'PAYEMS': SeriesInfo(
        id='PAYEMS',
        name='Nonfarm Payrolls',
        unit='Thousands of Persons',
        source='U.S. Bureau of Labor Statistics',
        data_type='level',
        show_absolute_change=True,
        bullets=[
            'The single most important monthly indicator of labor market health—this is the "jobs number" that moves markets on the first Friday of each month.',
            'Context: The economy now needs only 50-75K new jobs/month to keep pace with slowing population growth. Gains above 150K signal robust hiring; below 50K suggests softening.'
        ]
    ),
    'UNRATE': SeriesInfo(
        id='UNRATE',
        name='Unemployment Rate',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        bullets=[
            'The headline unemployment rate—the share of Americans actively looking for work but unable to find it.',
            'Rates below 4% are historically rare and signal a tight labor market. The rate peaked at 10% in 2009 and briefly hit 14.7% in April 2020.'
        ]
    ),
    'A191RO1Q156NBEA': SeriesInfo(
        id='A191RO1Q156NBEA',
        name='Real GDP Growth',
        unit='Percent Change',
        source='U.S. Bureau of Economic Analysis',
        data_type='growth_rate',
        bullets=[
            'The broadest measure of economic output—real GDP growth shows how fast the economy is expanding or contracting.',
            'Healthy growth is typically 2-3% annually. Two consecutive quarters of negative growth is one common definition of recession.'
        ]
    ),
    'CPIAUCSL': SeriesInfo(
        id='CPIAUCSL',
        name='Consumer Price Index',
        unit='Index 1982-84=100',
        source='U.S. Bureau of Labor Statistics',
        data_type='index',
        show_yoy=True,
        yoy_name='CPI Inflation Rate (Headline)',
        yoy_unit='% Change YoY',
        bullets=[
            'CPI measures the average change in prices paid by urban consumers for a basket of goods and services.',
            'The Fed targets 2% annual inflation. Above 3% raises concerns; sustained rates above 5% typically prompt aggressive Fed action.'
        ]
    ),
    'CPILFESL': SeriesInfo(
        id='CPILFESL',
        name='Core CPI',
        unit='Index 1982-84=100',
        source='U.S. Bureau of Labor Statistics',
        data_type='index',
        show_yoy=True,
        yoy_name='Core CPI Inflation Rate',
        yoy_unit='% Change YoY',
        bullets=[
            'CPI excluding food and energy—shows underlying inflation trends without volatile components.',
            'Markets and policymakers watch core inflation to gauge persistent price pressures.'
        ]
    ),
    'FEDFUNDS': SeriesInfo(
        id='FEDFUNDS',
        name='Federal Funds Rate',
        unit='Percent',
        source='Board of Governors of the Federal Reserve System',
        data_type='rate',
        sa=False,
        bullets=[
            'The Fed\'s primary tool for monetary policy—the rate banks charge each other for overnight loans.',
            'When the Fed raises rates, borrowing becomes more expensive throughout the economy, slowing growth and inflation.'
        ]
    ),
    'DGS10': SeriesInfo(
        id='DGS10',
        name='10-Year Treasury Rate',
        unit='Percent',
        source='Board of Governors of the Federal Reserve System',
        data_type='rate',
        sa=False,
        bullets=[
            'The benchmark "risk-free" rate that influences mortgages, corporate bonds, and stock valuations.',
            'Higher 10-year yields mean higher borrowing costs across the economy and typically pressure stock prices.'
        ]
    ),
    'DGS2': SeriesInfo(
        id='DGS2',
        name='2-Year Treasury Rate',
        unit='Percent',
        source='Board of Governors of the Federal Reserve System',
        data_type='rate',
        sa=False,
        bullets=[
            'Reflects market expectations for Fed policy over the next two years.',
            'When the 2-year exceeds the 10-year (yield curve inversion), it has historically preceded recessions.'
        ]
    ),
    'MORTGAGE30US': SeriesInfo(
        id='MORTGAGE30US',
        name='30-Year Mortgage Rate',
        unit='Percent',
        source='Freddie Mac',
        data_type='rate',
        sa=False,
        bullets=[
            'The rate on a conventional 30-year fixed mortgage—the primary driver of housing affordability.',
            'Each 1% increase in rates reduces buying power by roughly 10%. Rates below 4% are historically low; above 7% is restrictive.'
        ]
    ),
    'T10Y2Y': SeriesInfo(
        id='T10Y2Y',
        name='Treasury Yield Spread (10Y-2Y)',
        unit='Percent',
        source='Federal Reserve Bank of St. Louis',
        data_type='spread',
        sa=False,
        bullets=[
            'WHY IT MATTERS: When short-term rates exceed long-term rates (inversion), it signals markets expect tight policy will slow growth—historically a reliable recession warning.',
            'The 2022-2024 inversion was the longest since the 1980s, yet no recession followed—possibly due to post-COVID resilience and strong labor markets.',
            'Preceded every recession since 1970, but the recent "false signal" raises questions about whether structural changes have weakened its predictive power.'
        ]
    ),
    'SAHMREALTIME': SeriesInfo(
        id='SAHMREALTIME',
        name='Sahm Rule Recession Indicator',
        unit='Percentage Points',
        source='Federal Reserve Bank of St. Louis',
        data_type='spread',
        benchmark=0.5,
        bullets=[
            'Created by economist Claudia Sahm—signals recession when the 3-month average unemployment rate rises 0.5 points above its 12-month low.',
            'Has correctly identified every U.S. recession since 1970 with no false positives.'
        ]
    ),
    'ICSA': SeriesInfo(
        id='ICSA',
        name='Initial Jobless Claims',
        unit='Number',
        source='U.S. Employment and Training Administration',
        data_type='level',
        frequency='weekly',
        bullets=[
            'Weekly count of new unemployment insurance filings—the most timely indicator of labor market stress.',
            'Claims below 250K indicate a healthy labor market. Sustained readings above 300K suggest deterioration.'
        ]
    ),
    'CIVPART': SeriesInfo(
        id='CIVPART',
        name='Labor Force Participation Rate',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        bullets=[
            'Share of the adult population either working or actively seeking work.',
            'Has declined from 67% in 2000 due to aging demographics, rising disability, and more students pursuing education.'
        ]
    ),
    'LNS12300060': SeriesInfo(
        id='LNS12300060',
        name='Prime-Age Employment-Population Ratio',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        bullets=[
            'Share of Americans aged 25-54 who are employed—avoids distortions from retiring boomers and students.',
            'Many economists consider this the single best measure of labor market health.'
        ]
    ),
    'PCEPILFE': SeriesInfo(
        id='PCEPILFE',
        name='Core PCE Inflation',
        unit='Index',
        source='U.S. Bureau of Economic Analysis',
        data_type='index',
        show_yoy=True,
        yoy_name='Core PCE Inflation Rate',
        yoy_unit='% Change YoY',
        bullets=[
            'The Federal Reserve\'s preferred inflation measure—excludes volatile food and energy prices.',
            'The Fed explicitly targets 2% core PCE inflation over time.'
        ]
    ),
    'PCEPI': SeriesInfo(
        id='PCEPI',
        name='PCE Inflation',
        unit='Index',
        source='U.S. Bureau of Economic Analysis',
        data_type='index',
        show_yoy=True,
        yoy_name='PCE Inflation Rate',
        yoy_unit='% Change YoY',
        bullets=[
            'Personal Consumption Expenditures price index—broader than CPI and the Fed\'s official inflation gauge.',
            'Tends to run slightly lower than CPI because it accounts for consumers substituting cheaper goods.'
        ]
    ),
    'UMCSENT': SeriesInfo(
        id='UMCSENT',
        name='Consumer Sentiment',
        unit='Index 1966:Q1=100',
        source='University of Michigan',
        data_type='index',
        sa=False,
        bullets=[
            'Survey-based measure of how consumers feel about their finances and the economy.',
            'Readings above 90 indicate optimism; below 70 suggests pessimism. Can lead changes in spending behavior.'
        ]
    ),
    'RSAFS': SeriesInfo(
        id='RSAFS',
        name='Retail Sales',
        unit='Millions of Dollars',
        source='U.S. Census Bureau',
        data_type='level',
        show_yoy=True,
        bullets=[
            'Total receipts at retail stores—a direct measure of consumer spending, which drives ~70% of GDP.',
            'Closely watched for signs of consumer strength or pullback.'
        ]
    ),
    'PSAVERT': SeriesInfo(
        id='PSAVERT',
        name='Personal Savings Rate',
        unit='Percent',
        source='U.S. Bureau of Economic Analysis',
        data_type='rate',
        bullets=[
            'The share of disposable income that households save rather than spend.',
            'Spiked to 33% during COVID stimulus; rates below 4% suggest consumers may be stretched.'
        ]
    ),
    'GDPNOW': SeriesInfo(
        id='GDPNOW',
        name='GDPNow Estimate',
        unit='Percent',
        source='Federal Reserve Bank of Atlanta',
        data_type='growth_rate',
        bullets=[
            'Real-time estimate of current-quarter GDP growth based on incoming economic data.',
            'Updates frequently as new data releases and provides the most current read on economic momentum.'
        ]
    ),
    'CSUSHPINSA': SeriesInfo(
        id='CSUSHPINSA',
        name='Case-Shiller Home Price Index',
        unit='Index',
        source='S&P Dow Jones Indices',
        data_type='index',
        show_yoy=True,
        sa=False,
        bullets=[
            'Tracks home prices across 20 major U.S. metro areas.',
            'A key measure of housing market health and household wealth.'
        ]
    ),
    'HOUST': SeriesInfo(
        id='HOUST',
        name='Housing Starts',
        unit='Thousands of Units',
        source='U.S. Census Bureau',
        data_type='level',
        bullets=[
            'New residential construction starts—a leading indicator of housing supply and economic activity.',
            'Sensitive to mortgage rates and builder confidence.'
        ]
    ),
}


# =============================================================================
# QUERY MAP - Fast keyword -> series mappings
# =============================================================================

QUERY_MAP: Dict[str, dict] = {
    # Economy overview
    'economy': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'CPIAUCSL'], 'combine': False},
    'how is the economy': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'CPIAUCSL'], 'combine': False},
    'economic overview': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'CPIAUCSL'], 'combine': False},
    'recession': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'T10Y2Y'], 'combine': False},

    # Jobs
    'job market': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'jobs': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'employment': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'labor market': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'unemployment': {'series': ['UNRATE'], 'combine': False},

    # Inflation
    'inflation': {'series': ['CPIAUCSL', 'CPILFESL'], 'combine': True, 'show_yoy': True},
    'cpi': {'series': ['CPIAUCSL'], 'combine': False, 'show_yoy': True},
    'core inflation': {'series': ['CPILFESL'], 'combine': False, 'show_yoy': True},
    'pce': {'series': ['PCEPI', 'PCEPILFE'], 'combine': True, 'show_yoy': True},

    # Interest rates
    'interest rates': {'series': ['FEDFUNDS', 'DGS10'], 'combine': True},
    'rates': {'series': ['FEDFUNDS', 'DGS10'], 'combine': True},
    'fed': {'series': ['FEDFUNDS'], 'combine': False},
    'fed funds': {'series': ['FEDFUNDS'], 'combine': False},
    'treasury': {'series': ['DGS10', 'DGS2'], 'combine': True},
    'yield curve': {'series': ['T10Y2Y'], 'combine': False},
    'mortgage': {'series': ['MORTGAGE30US'], 'combine': False},

    # Housing
    'housing': {'series': ['CSUSHPINSA', 'HOUST'], 'combine': False},
    'home prices': {'series': ['CSUSHPINSA'], 'combine': False, 'show_yoy': True},
    'housing market': {'series': ['CSUSHPINSA', 'MORTGAGE30US'], 'combine': False},

    # Consumer
    'consumer': {'series': ['RSAFS', 'UMCSENT'], 'combine': False},
    'consumer sentiment': {'series': ['UMCSENT'], 'combine': False},
    'retail sales': {'series': ['RSAFS'], 'combine': False, 'show_yoy': True},

    # GDP
    'gdp': {'series': ['A191RO1Q156NBEA', 'GDPNOW'], 'combine': False},
    'gdp growth': {'series': ['A191RO1Q156NBEA', 'GDPNOW'], 'combine': False},
    'economic growth': {'series': ['A191RO1Q156NBEA', 'GDPNOW'], 'combine': False},

    # Trade
    'trade': {'series': ['BOPGSTB', 'IMPGS', 'EXPGS'], 'combine': False, 'show_yoy': False},
    'trade balance': {'series': ['BOPGSTB', 'IMPGS', 'EXPGS'], 'combine': False},
    'imports': {'series': ['IMPGS', 'BOPGSTB'], 'combine': False},
    'exports': {'series': ['EXPGS', 'BOPGSTB'], 'combine': False},
}


class SeriesRegistry:
    """
    Unified registry for all series metadata and query plans.

    Provides fast O(1) lookup for most queries via exact match,
    with fuzzy matching as fallback.
    """

    def __init__(self):
        self._series: Dict[str, SeriesInfo] = dict(SERIES_DB)
        self._plans: Dict[str, dict] = dict(QUERY_MAP)
        self._keyword_index: Dict[str, List[str]] = {}
        self._loaded = False

    def load(self, plans_dir: str = 'agents') -> None:
        """Load all query plans from JSON files and build indexes."""
        if self._loaded:
            return

        # Load JSON plan files
        plan_files = [
            'plans_economy_overview.json',
            'plans_inflation.json',
            'plans_employment.json',
            'plans_gdp.json',
            'plans_housing.json',
            'plans_fed_rates.json',
            'plans_consumer.json',
            'plans_demographics.json',
            'plans_trade_markets.json',
        ]

        for filename in plan_files:
            path = os.path.join(plans_dir, filename)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        plans = json.load(f)
                        self._plans.update(plans)
                        print(f"[Registry] Loaded {len(plans)} plans from {filename}")
                except Exception as e:
                    print(f"[Registry] Error loading {filename}: {e}")

        # Build keyword index
        self._build_keyword_index()
        self._loaded = True
        print(f"[Registry] Total plans: {len(self._plans)}, Series: {len(self._series)}")

    def _build_keyword_index(self) -> None:
        """Build inverted index from keywords to plan keys."""
        for key in self._plans.keys():
            words = key.lower().split()
            for word in words:
                if len(word) >= 3:  # Skip short words
                    if word not in self._keyword_index:
                        self._keyword_index[word] = []
                    self._keyword_index[word].append(key)

    def get_series(self, series_id: str) -> Optional[SeriesInfo]:
        """Get metadata for a series by ID."""
        return self._series.get(series_id)

    def get_plan(self, query: str) -> Optional[dict]:
        """Get a query plan by exact match."""
        normalized = self._normalize(query)
        return self._plans.get(normalized) or self._plans.get(query.lower())

    def fuzzy_match(self, query: str, threshold: float = 0.7) -> Optional[dict]:
        """Find best matching plan using fuzzy string matching."""
        normalized = self._normalize(query)
        all_keys = list(self._plans.keys())

        matches = difflib.get_close_matches(normalized, all_keys, n=1, cutoff=threshold)
        if matches:
            return self._plans[matches[0]]

        # Try keyword-based matching
        words = normalized.split()
        candidate_keys = set()
        for word in words:
            if word in self._keyword_index:
                candidate_keys.update(self._keyword_index[word])

        if candidate_keys:
            matches = difflib.get_close_matches(normalized, list(candidate_keys), n=1, cutoff=0.6)
            if matches:
                return self._plans[matches[0]]

        return None

    def all_plan_keys(self) -> List[str]:
        """Get all available plan keys for LLM classification."""
        return list(self._plans.keys())

    def _normalize(self, query: str) -> str:
        """Normalize query for matching."""
        q = query.lower().strip()

        # Normalize "v." and "versus" to "vs"
        q = re.sub(r'\bv\.?\s+', 'vs ', q)
        q = re.sub(r'\bversus\b', 'vs', q)

        # Remove filler words
        fillers = [
            r'^what is\s+', r'^what are\s+', r'^show me\s+', r'^show\s+',
            r'^tell me about\s+', r'^how is\s+', r'^how are\s+',
            r'^what\'s\s+', r'^whats\s+', r'^give me\s+',
            r'\s+changed\s*$', r'\s+doing\s*$', r'\s+looking\s*$', r'\s+trending\s*$',
            r'\?$', r'\.+$', r'\s+the\s+', r'^the\s+'
        ]
        for filler in fillers:
            q = re.sub(filler, ' ', q)

        return ' '.join(q.split()).strip()


# Global registry instance
registry = SeriesRegistry()
