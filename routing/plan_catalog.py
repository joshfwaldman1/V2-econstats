"""
Plan Catalog - Compact plan index for LLM routing.

Builds a ~3,500 token text representation of all curated plans,
organized by topic bucket. This is sent to Gemini so it can pick
the best plan for any query in a single call.

Topic buckets group plans by subject area:
  EMPLOYMENT, INFLATION, GDP, HOUSING, FED_RATES, ...

Each bucket lists its plan keys comma-separated so the LLM can
scan them quickly and pick the closest match.
"""

import re
from typing import Dict, List, Tuple, Optional


# =============================================================================
# TOPIC BUCKET DEFINITIONS
# =============================================================================
# Each bucket has:
#   - keywords: Words that classify a plan key into this bucket
#   - priority: Higher priority buckets are checked first (avoids
#     "unemployment" matching EMPLOYMENT before EMPLOYMENT_DEMOGRAPHICS)

TOPIC_BUCKETS = {
    'EMPLOYMENT_DEMOGRAPHICS': {
        'keywords': [
            'black unemployment', 'black workers', 'black employment', 'black labor',
            'hispanic unemployment', 'hispanic workers', 'hispanic employment',
            'latino', 'latina', 'women unemployment', 'women employment',
            'women labor', 'women workers', 'men unemployment', 'men employment',
            'youth unemployment', 'teen unemployment', 'young workers',
            'asian unemployment', 'asian workers', 'asian employment',
            'veteran', 'veterans', 'immigrant', 'foreign born', 'native born',
            'white unemployment', 'white workers', 'white employment',
            'by race', 'by gender', 'gender gap', 'racial gap',
            'unemployment by', 'employment by',
        ],
        'priority': 10,
    },
    'EMPLOYMENT_SECTORS': {
        'keywords': [
            'manufacturing employment', 'manufacturing jobs', 'factory jobs',
            'construction jobs', 'construction employment', 'construction workers',
            'tech employment', 'tech jobs', 'tech sector',
            'healthcare jobs', 'healthcare employment', 'hospital',
            'restaurant', 'food service', 'hospitality',
            'government employment', 'government jobs', 'federal jobs',
            'retail employment', 'retail jobs', 'retail workers',
            'finance jobs', 'banking jobs', 'financial sector employment',
            'education jobs', 'education employment',
            'transportation', 'mining', 'professional services',
            'leisure and hospitality', 'information sector',
        ],
        'priority': 9,
    },
    'EMPLOYMENT': {
        'keywords': [
            'job', 'jobs', 'employment', 'labor', 'unemployment', 'hiring',
            'payroll', 'workforce', 'jobless', 'claims', 'jolts', 'openings',
            'participation', 'prime age', 'underemployment', 'sahm',
            'labor force', 'nonfarm', 'beveridge', 'quits', 'hires',
            'layoffs', 'employed', 'epop',
        ],
        'priority': 5,
    },
    'INFLATION': {
        'keywords': [
            'inflation', 'cpi', 'pce', 'prices', 'price', 'cost of living',
            'food price', 'shelter', 'rent inflation', 'energy price',
            'gas price', 'gasoline', 'deflation', 'disinflation',
            'core inflation', 'headline inflation', 'breakeven',
            'inflation expectations', 'inflation target', 'sticky',
        ],
        'priority': 5,
    },
    'GDP': {
        'keywords': [
            'gdp', 'economic growth', 'output', 'productivity',
            'industrial production', 'durable goods', 'gdpnow',
            'real gdp', 'nominal gdp', 'potential gdp', 'gdp components',
            'gdp quarterly', 'private demand', 'final sales',
        ],
        'priority': 5,
    },
    'HOUSING': {
        'keywords': [
            'housing', 'home price', 'mortgage', 'housing starts',
            'building permits', 'affordability', 'rent', 'rents',
            'rental', 'new home sales', 'existing home sales',
            'case-shiller', 'case shiller', 'home value', 'zillow',
            'homebuilder', 'housing supply', 'housing market',
        ],
        'priority': 5,
    },
    'FED_RATES': {
        'keywords': [
            'fed', 'federal reserve', 'interest rate', 'rates',
            'yield curve', 'treasury', 'dot plot', 'fomc',
            'monetary policy', 'rate cut', 'rate hike', 'fed funds',
            'powell', 'tightening', 'easing', 'quantitative',
            'balance sheet', 'spread', '10 year', '2 year',
        ],
        'priority': 5,
    },
    'CONSUMER': {
        'keywords': [
            'consumer', 'spending', 'retail sales', 'sentiment',
            'confidence', 'savings', 'personal income', 'disposable',
            'credit', 'debt', 'household', 'consumption',
        ],
        'priority': 5,
    },
    'WAGES_INCOME': {
        'keywords': [
            'wage', 'wages', 'earnings', 'income', 'pay',
            'compensation', 'real wages', 'wage growth',
            'wages vs inflation', 'employment cost',
            'minimum wage', 'median income',
        ],
        'priority': 6,
    },
    'TRADE_MARKETS': {
        'keywords': [
            'trade', 'export', 'import', 'tariff', 'deficit',
            'surplus', 'balance', 'stock market', 'stocks', 's&p',
            'nasdaq', 'dow', 'gold', 'oil', 'commodity',
            'dollar', 'forex', 'exchange rate', 'vix',
            'trading partner',
        ],
        'priority': 5,
    },
    'RECESSION': {
        'keywords': [
            'recession', 'downturn', 'contraction', 'leading indicator',
            'recession risk', 'recession probability', 'headed for',
            'slowdown', 'soft landing', 'hard landing',
        ],
        'priority': 7,
    },
    'SOCIAL': {
        'keywords': [
            'poverty', 'inequality', 'gini', 'food insecurity',
            'bankruptcy', 'homelessness', 'welfare', 'snap',
            'social security', 'disability',
        ],
        'priority': 5,
    },
    'ECONOMY_OVERVIEW': {
        'keywords': [
            'economy', 'economic', 'overview', 'how is', 'outlook',
            'forecast', 'state of', 'what\'s happening',
        ],
        'priority': 3,  # Low priority — catch-all
    },
    'INTERNATIONAL': {
        'keywords': [
            'eurozone', 'europe', 'uk', 'china', 'japan', 'germany',
            'canada', 'india', 'brazil', 'mexico', 'korea', 'australia',
            'us vs', 'us compared', 'compared to',
        ],
        'priority': 6,
    },
    'STATES': {
        'keywords': [],  # Matched by state name/code patterns
        'priority': 8,
    },
}

# US state codes → names (for state pattern detection)
STATE_CODES = {
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
}
STATE_NAMES_LOWER = {name.lower(): code for code, name in STATE_CODES.items()}


class PlanCatalog:
    """
    Builds a compact plan catalog for the LLM routing prompt.

    At startup, classifies all ~1,375 curated plans into topic buckets
    and generates a compact text (~3,500 tokens) that Gemini can scan
    to pick the best plan for any query.
    """

    def __init__(self):
        self._catalog_text: Optional[str] = None
        self._buckets: Dict[str, List[str]] = {}
        self._plan_keys: List[str] = []

    def build(self, registry) -> str:
        """
        Build the full catalog text at startup.

        Args:
            registry: The SeriesRegistry instance with all loaded plans.

        Returns:
            Compact text catalog for the LLM prompt.
        """
        all_plans = registry.get_all_plans()
        self._plan_keys = list(all_plans.keys())
        self._buckets = self._classify_plans(all_plans)
        self._catalog_text = self._format_catalog(self._buckets)
        print(f"[PlanCatalog] Built catalog: {len(self._plan_keys)} plans → {len(self._buckets)} buckets")
        return self._catalog_text

    @property
    def catalog_text(self) -> str:
        """Get the built catalog text."""
        if self._catalog_text is None:
            return ''
        return self._catalog_text

    def _classify_plans(self, all_plans: Dict[str, dict]) -> Dict[str, List[str]]:
        """
        Classify all plan keys into topic buckets.

        Uses keyword matching with priority ordering to assign each
        plan key to exactly one bucket. Higher-priority buckets
        (like EMPLOYMENT_DEMOGRAPHICS) are checked before lower-priority
        ones (like EMPLOYMENT) to avoid incorrect classification.
        """
        buckets: Dict[str, List[str]] = {name: [] for name in TOPIC_BUCKETS}
        unclassified: List[str] = []

        # Sort bucket definitions by priority (highest first)
        sorted_buckets = sorted(
            TOPIC_BUCKETS.items(),
            key=lambda x: x[1]['priority'],
            reverse=True
        )

        for plan_key in all_plans.keys():
            key_lower = plan_key.lower()

            # Check if it's a state plan
            if self._is_state_plan(key_lower):
                buckets['STATES'].append(plan_key)
                continue

            # Try each bucket in priority order
            matched = False
            for bucket_name, bucket_def in sorted_buckets:
                if bucket_name == 'STATES':
                    continue  # Already handled
                for keyword in bucket_def['keywords']:
                    if keyword in key_lower:
                        buckets[bucket_name].append(plan_key)
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                unclassified.append(plan_key)

        # Put unclassified plans in ECONOMY_OVERVIEW as catch-all
        if unclassified:
            buckets['ECONOMY_OVERVIEW'].extend(unclassified)

        # Remove empty buckets
        return {k: v for k, v in buckets.items() if v}

    def _is_state_plan(self, key_lower: str) -> bool:
        """Check if a plan key is a state-specific plan."""
        # Match patterns like "california economy", "new york unemployment", "TX jobs"
        for state_name in STATE_NAMES_LOWER:
            if state_name in key_lower:
                return True
        # Also check 2-letter state codes at word boundaries
        words = key_lower.split()
        for word in words:
            if word.upper() in STATE_CODES and len(word) == 2:
                return True
        return False

    def _format_catalog(self, buckets: Dict[str, List[str]]) -> str:
        """
        Format the classified plans into compact text for the LLM prompt.

        Each bucket shows its plan keys comma-separated. States are
        summarized as a pattern rather than listing all 520 plans.
        """
        lines = []

        # Define display order for buckets
        display_order = [
            'EMPLOYMENT', 'EMPLOYMENT_DEMOGRAPHICS', 'EMPLOYMENT_SECTORS',
            'INFLATION', 'GDP', 'HOUSING', 'FED_RATES', 'CONSUMER',
            'WAGES_INCOME', 'TRADE_MARKETS', 'RECESSION', 'SOCIAL',
            'ECONOMY_OVERVIEW', 'INTERNATIONAL', 'STATES',
        ]

        for bucket_name in display_order:
            if bucket_name not in buckets:
                continue

            plan_keys = buckets[bucket_name]

            if bucket_name == 'STATES':
                # Summarize states as a pattern
                lines.append(f'\nSTATES ({len(plan_keys)} plans):')
                lines.append('  For any US state: "{state} economy", "{state} unemployment", "{state} jobs"')
                lines.append('  Examples: california economy, new york unemployment, texas jobs, florida housing')
                lines.append('  All 50 states + DC covered.')
                continue

            # Deduplicate plan keys (some are very similar)
            unique_keys = self._deduplicate_keys(plan_keys)

            lines.append(f'\n{bucket_name} ({len(plan_keys)} plans):')
            # Format as comma-separated, wrapped at reasonable line length
            key_str = ', '.join(unique_keys)
            lines.append(f'  {key_str}')

        return '\n'.join(lines)

    def _deduplicate_keys(self, plan_keys: List[str]) -> List[str]:
        """
        Remove near-duplicate plan keys for compact display.

        When plan keys are very similar (e.g., "how is the economy" and
        "how is the economy doing"), keep only the shortest canonical form.
        """
        # Sort by length (shortest first) so canonical forms come first
        sorted_keys = sorted(set(plan_keys), key=len)
        seen_roots = set()
        unique = []

        for key in sorted_keys:
            # Create a simplified root for dedup
            root = key.lower().strip()
            # Remove trailing filler words
            for suffix in [' doing', ' looking', ' trending', ' changed',
                           ' right now', ' today', ' currently', ' these days']:
                root = root.removesuffix(suffix)

            if root not in seen_roots:
                seen_roots.add(root)
                unique.append(key)

        return unique

    def pre_filter(self, query: str) -> List[str]:
        """
        Quick keyword check to guess 1-3 likely topic buckets.

        Used to give the LLM a hint about which section of the catalog
        is most relevant. Not used for exclusion — the LLM can pick
        from any bucket.

        Args:
            query: The user's query string.

        Returns:
            List of bucket names that likely match.
        """
        q = query.lower()
        matches = []

        # Sort by priority (highest first)
        sorted_buckets = sorted(
            TOPIC_BUCKETS.items(),
            key=lambda x: x[1]['priority'],
            reverse=True
        )

        for bucket_name, bucket_def in sorted_buckets:
            if bucket_name == 'STATES':
                # Check state names
                if self._is_state_plan(q):
                    matches.append(bucket_name)
                continue

            for keyword in bucket_def['keywords']:
                if keyword in q:
                    matches.append(bucket_name)
                    break

        return matches[:3]  # Return top 3 likely buckets


# Global instance
plan_catalog = PlanCatalog()
