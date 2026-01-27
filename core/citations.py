"""
Citation and Attribution System for EconStats.

Provides source attribution for economic claims beyond raw data.
Supports expert opinions, competing views, and forecast attribution.

The Problem:
    Economic analysis often goes beyond raw data to include interpretations,
    forecasts, and expert opinions. Without proper attribution:
    - Opinions can be mistaken for facts
    - Forecast sources are unclear
    - Competing expert views are hidden
    - Intellectual dishonesty creeps in

    BAD (unsourced opinion):
        "The Fed will likely cut rates twice in 2026"

    GOOD (attributed):
        "Goldman Sachs expects two rate cuts in 2026, while Morgan Stanley sees only one"

    BAD (asserted as fact):
        "Inflation will continue to moderate"

    GOOD (with competing views):
        "Most forecasters expect inflation to continue moderating, though some
        analysts warn about persistent services inflation"

Key Principles:
    1. Raw data doesn't need citation - "Unemployment is 4.1%" is a fact
    2. Interpretations need attribution - "This suggests cooling" should note who says this
    3. Forecasts always need sources - "Rates will fall" -> "Goldman expects rates to fall"
    4. Competing views are valuable - Show when experts disagree
    5. Tier sources by authority - Fed > Academic > Finance > Press

Usage:
    from core.citations import (
        Citation,
        EXPERT_VIEWS,
        get_expert_views,
        format_with_attribution,
        format_competing_views,
        should_cite,
        add_citations_to_analysis,
        format_citation_footer,
    )

    # Check if a claim needs citation
    if should_cite("forecast"):
        views = get_expert_views("fed_rate_path")
        attributed_text = format_with_attribution(claim, views)

    # Get competing views formatted for display
    competing = format_competing_views("recession_risk")

    # Add a citation footer to analysis
    footer = format_citation_footer(citations_used)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Citation:
    """
    A citation for a claim about economic conditions or forecasts.

    Attributes:
        source: The organization or individual making the claim
                (e.g., "Goldman Sachs", "Federal Reserve", "BLS")
        claim: What they said (the actual claim or forecast)
        date: When they said it (e.g., "January 2026", "December 2024")
        url: Optional link to the source material
        tier: Source credibility tier (1=Fed/Govt highest, 4=Press lowest)
        category: Optional category like 'forecast', 'opinion', 'research'

    Tier System:
        1 = Federal Reserve and Government (highest authority)
        2 = Academic/Research institutions
        3 = Financial institutions (banks, asset managers)
        4 = Press and media outlets
    """
    source: str
    claim: str
    date: Optional[str] = None
    url: Optional[str] = None
    tier: int = 3
    category: Optional[str] = None

    def __str__(self) -> str:
        """Format citation as a readable string."""
        date_part = f" ({self.date})" if self.date else ""
        return f"{self.source}{date_part}: {self.claim}"

    def as_dict(self) -> Dict[str, Any]:
        """Convert citation to dictionary for JSON serialization."""
        return {
            'source': self.source,
            'claim': self.claim,
            'date': self.date,
            'url': self.url,
            'tier': self.tier,
            'category': self.category,
        }


@dataclass
class ExpertView:
    """
    A single expert's view on an economic topic.

    This is a lighter-weight structure than Citation, used for storing
    expert opinions in the EXPERT_VIEWS database.

    IMPORTANT: Views must be SPECIFIC with numbers, dates, or concrete predictions.

    BAD (vague - rejected):
        - "Goldman sees the labor market as resilient"
        - "Analysts expect inflation to moderate"
        - "Experts are divided on recession risk"

    GOOD (specific - required):
        - "Goldman expects unemployment to stay below 4.5% through 2026"
        - "Morgan Stanley projects rate cuts in June and September 2026"
        - "Cleveland Fed Nowcast projects January CPI at 2.9% YoY"
        - "Polymarket shows 23% recession probability for 2026"

    Attributes:
        source: Who holds this view (e.g., "Goldman Sachs", "Federal Reserve Dot Plot")
        specific_claim: The actual prediction with numbers/dates - MUST be specific!
                       (e.g., "expects two 25bp cuts in 2026, in March and June")
        metric: What specifically they're predicting (e.g., "fed_funds_rate",
                "unemployment_rate", "rate_cuts", "gdp_growth", "core_pce")
        timeframe: When this applies (e.g., "2026", "Q1 2026", "end-2025",
                   "next 6 months", "through 2027")
        date: When this view was expressed (e.g., "January 2026")
        tier: Source credibility tier (1=Fed/Govt, 2=Academic, 3=Finance, 4=Press)
        rationale: Optional explanation for why they hold this view

        # Deprecated - use specific_claim instead
        view: Legacy field, mapped to specific_claim for backward compatibility
    """
    source: str
    specific_claim: str = ""
    metric: str = ""
    timeframe: str = ""
    date: Optional[str] = None
    tier: int = 3
    rationale: Optional[str] = None
    url: Optional[str] = None  # Link to source material
    # Legacy field for backward compatibility - will be deprecated
    view: str = ""

    def __post_init__(self):
        """Handle backward compatibility with legacy 'view' field."""
        # If specific_claim is empty but view is provided, use view as specific_claim
        if not self.specific_claim and self.view:
            self.specific_claim = self.view
        # If specific_claim is provided but view is empty, copy to view for compatibility
        elif self.specific_claim and not self.view:
            self.view = self.specific_claim

    def to_citation(self, topic: str = "") -> Citation:
        """Convert to a full Citation object."""
        return Citation(
            source=self.source,
            claim=self.specific_claim,
            date=self.date,
            url=self.url,
            tier=self.tier,
            category='expert_view',
        )

    def format_specific(self) -> str:
        """
        Format this view as a specific, attributable statement.

        Returns a string like:
            "Goldman expects two rate cuts in 2026 (March and June)"

        NOT vague like:
            "Goldman expects rate cuts"
        """
        return f"{self.source} {self.specific_claim}"


@dataclass
class TopicViews:
    """
    Collection of expert views on a specific economic topic.

    Attributes:
        topic: The economic topic (e.g., "Federal Reserve rate path")
        views: List of expert views on this topic
        last_updated: When this collection was last updated
        consensus: Optional description of the consensus view
        key_disagreement: Optional description of main points of disagreement
    """
    topic: str
    views: List[ExpertView] = field(default_factory=list)
    last_updated: Optional[str] = None
    consensus: Optional[str] = None
    key_disagreement: Optional[str] = None


# =============================================================================
# SOURCE TIER DEFINITIONS
# =============================================================================

# Tier 1: Federal Reserve and Government (highest authority)
# These sources have primary data and official policy positions
TIER_1_FED_GOVT = {
    'Federal Reserve': 1,
    'Federal Reserve (Dot Plot)': 1,
    'FOMC': 1,
    'Fed Chair Powell': 1,
    'Bureau of Labor Statistics': 1,
    'Bureau of Economic Analysis': 1,
    'Treasury Department': 1,
    'Congressional Budget Office': 1,
    'Cleveland Fed': 1,
    'Atlanta Fed': 1,
    'New York Fed': 1,
    'St. Louis Fed': 1,
    'San Francisco Fed': 1,
    'BLS': 1,
    'BEA': 1,
    'Census Bureau': 1,
}

# Tier 2: Academic and Research institutions
# Credible research with peer review and methodological rigor
TIER_2_ACADEMIC = {
    'National Bureau of Economic Research': 2,
    'NBER': 2,
    'Brookings Institution': 2,
    'Peterson Institute': 2,
    'Conference Board': 2,
    'University of Michigan': 2,
    'MIT': 2,
    'Harvard': 2,
    'Princeton': 2,
    'IMF': 2,
    'World Bank': 2,
    'OECD': 2,
    'Federal Reserve Bank Research': 2,
}

# Tier 3: Financial institutions
# Have skin in the game, motivated to be accurate, but potential conflicts
TIER_3_FINANCE = {
    'Goldman Sachs': 3,
    'Morgan Stanley': 3,
    'JP Morgan': 3,
    'JPMorgan': 3,
    'Bank of America': 3,
    'Citigroup': 3,
    'Wells Fargo': 3,
    'BlackRock': 3,
    'Bridgewater': 3,
    'PIMCO': 3,
    'Vanguard': 3,
    'Deutsche Bank': 3,
    'UBS': 3,
    'Credit Suisse': 3,
    'Barclays': 3,
    'Nomura': 3,
    'CME FedWatch': 3,
    'Polymarket': 3,
}

# Tier 4: Press and media
# Good for news, less reliable for analysis/forecasts
TIER_4_PRESS = {
    'Wall Street Journal': 4,
    'Financial Times': 4,
    'Bloomberg': 4,
    'Reuters': 4,
    'The Economist': 4,
    'CNBC': 4,
    'MarketWatch': 4,
    "Barron's": 4,
    'New York Times': 4,
    'Washington Post': 4,
}

# Combined lookup for tier assignment
ALL_SOURCE_TIERS = {
    **TIER_1_FED_GOVT,
    **TIER_2_ACADEMIC,
    **TIER_3_FINANCE,
    **TIER_4_PRESS,
}


def get_source_tier(source: str) -> int:
    """
    Get the tier for a source, defaulting to 4 if unknown.

    Args:
        source: The source name to look up

    Returns:
        Tier number (1=highest authority, 4=press/unknown)
    """
    # Try exact match first
    if source in ALL_SOURCE_TIERS:
        return ALL_SOURCE_TIERS[source]

    # Try partial match (source name might be part of a longer string)
    source_lower = source.lower()
    for known_source, tier in ALL_SOURCE_TIERS.items():
        if known_source.lower() in source_lower or source_lower in known_source.lower():
            return tier

    return 4  # Default to press tier for unknown sources


def get_tier_label(tier: int) -> str:
    """
    Get a human-readable label for a source tier.

    Args:
        tier: The tier number (1-4)

    Returns:
        Human-readable tier description
    """
    tier_labels = {
        1: 'Official (Fed/Govt)',
        2: 'Research/Academic',
        3: 'Financial Institution',
        4: 'Press/Media',
    }
    return tier_labels.get(tier, 'Unknown')


# =============================================================================
# EXPERT VIEWS DATABASE
# =============================================================================

# Pre-loaded expert views on key economic topics.
# These are updated periodically from news searches and Fed communications.
# The views dictionary maps topic keys to TopicViews objects.

EXPERT_VIEWS: Dict[str, TopicViews] = {
    # =========================================================================
    # MONETARY POLICY
    # =========================================================================
    'fed_rate_path': TopicViews(
        topic='Federal Reserve rate path',
        last_updated='January 2026',
        consensus='Fed dot plot shows rates at 3.4% by end-2026; Wall Street expects 50-75bp of cuts',
        key_disagreement='Number of cuts: Fed projects 100bp vs Wall Street 50-75bp',
        views=[
            ExpertView(
                source='Federal Reserve Dot Plot',
                specific_claim='median shows rates at 3.9% by end-2025, 3.4% by end-2026',
                metric='fed_funds_rate',
                timeframe='2025-2026',
                date='December 2024',
                tier=1,
                rationale='Official FOMC projections based on committee median',
                url='https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20241218.htm',
            ),
            ExpertView(
                source='CME FedWatch Tool',
                specific_claim='futures imply 65% probability of at least two cuts by December 2026',
                metric='rate_cut_probability',
                timeframe='through December 2026',
                date='January 2026',
                tier=3,
                rationale='Fed funds futures implied probabilities',
                url='https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html',
            ),
            ExpertView(
                source='Atlanta Fed GDPNow',
                specific_claim='Q1 2026 GDP tracking at 2.3% annualized, suggesting no urgency to cut',
                metric='gdp_nowcast',
                timeframe='Q1 2026',
                date='January 2026',
                tier=1,
                rationale='Real-time GDP tracking model',
                url='https://www.atlantafed.org/cqer/research/gdpnow',
            ),
            ExpertView(
                source='Fed Chair Powell (FOMC Press Conference)',
                specific_claim='stated rates are "well into restrictive territory" but more progress on inflation needed',
                metric='policy_stance',
                timeframe='current',
                date='December 2024',
                tier=1,
                rationale='Direct statement from Fed Chair',
                url='https://www.federalreserve.gov/newsevents/pressreleases.htm',
            ),
        ],
    ),

    'fed_terminal_rate': TopicViews(
        topic='Fed terminal/neutral rate',
        last_updated='January 2026',
        consensus='Fed estimates neutral rate at 2.5-3.0%; some argue it has risen post-pandemic',
        key_disagreement='Whether neutral is 2.5-3.0% (pre-pandemic) or 3.0-3.5% (higher structural)',
        views=[
            ExpertView(
                source='Federal Reserve SEP',
                specific_claim='projects longer-run neutral rate at 3.0% (median, up from 2.5% in 2023)',
                metric='neutral_rate',
                timeframe='long-run',
                date='December 2024',
                tier=1,
                rationale='From Summary of Economic Projections',
            ),
            ExpertView(
                source='PIMCO',
                specific_claim='estimates neutral rate has risen to 3.0-3.5% post-pandemic',
                metric='neutral_rate',
                timeframe='structural estimate',
                date='January 2026',
                tier=3,
                rationale='Structural factors like fiscal deficits and deglobalization',
            ),
            ExpertView(
                source='Bridgewater',
                specific_claim='estimates neutral rate at 3.5% or higher, above pre-pandemic 2.5%',
                metric='neutral_rate',
                timeframe='structural estimate',
                date='January 2026',
                tier=3,
                rationale='Productivity growth and investment demand shifts',
            ),
        ],
    ),

    # =========================================================================
    # INFLATION OUTLOOK
    # =========================================================================
    'inflation_outlook': TopicViews(
        topic='Inflation trajectory',
        last_updated='January 2026',
        consensus='Fed projects core PCE at 2.2% by end-2026; Cleveland Fed nowcasts 2.6% currently',
        key_disagreement='Whether core PCE reaches 2.2% (Fed) or stays sticky at 2.4-2.6% (Wall Street)',
        views=[
            ExpertView(
                source='Cleveland Fed Inflation Nowcast',
                specific_claim='projects January 2026 CPI at 2.9% YoY, core PCE at 2.6%',
                metric='core_pce',
                timeframe='January 2026',
                date='January 2026',
                tier=1,
                rationale='Real-time inflation tracking model',
                url='https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting',
            ),
            ExpertView(
                source='Federal Reserve SEP',
                specific_claim='projects core PCE at 2.5% by end-2025, falling to 2.2% by end-2026',
                metric='core_pce',
                timeframe='2025-2026',
                date='December 2024',
                tier=1,
                rationale='FOMC Summary of Economic Projections',
                url='https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20241218.htm',
            ),
            ExpertView(
                source='SF Fed Economic Letter',
                specific_claim='estimates services inflation persistence will keep core PCE above 2.5% through Q2 2026',
                metric='core_pce',
                timeframe='Q2 2026',
                date='December 2024',
                tier=1,
                rationale='Research on inflation persistence in services sector',
                url='https://www.frbsf.org/research-and-insights/publications/economic-letter/',
            ),
            ExpertView(
                source='NY Fed Underlying Inflation Gauge',
                specific_claim='UIG full data set shows underlying inflation at 2.8% as of November 2025',
                metric='underlying_inflation',
                timeframe='November 2025',
                date='January 2026',
                tier=1,
                rationale='Alternative measure filtering noise from CPI',
                url='https://www.newyorkfed.org/research/policy/underlying-inflation-gauge',
            ),
            ExpertView(
                source='Peterson Institute (Jason Furman)',
                specific_claim='projects shelter inflation will drop from 5.5% to 3.5% by end-2026 as market rents flow through',
                metric='shelter_inflation',
                timeframe='2026',
                date='January 2026',
                tier=2,
                rationale='CPI shelter lags market rents by 12-18 months',
                url='https://www.piie.com/blogs/realtime-economics',
            ),
        ],
    ),

    'shelter_inflation': TopicViews(
        topic='Shelter/housing inflation',
        last_updated='January 2026',
        consensus='CPI shelter at 5.5% will decline to 3.5-4% by end-2026 as market rents flow through',
        key_disagreement='Speed of decline: some see 4% by mid-2026, others not until end-2026',
        views=[
            ExpertView(
                source='Fed Chair Powell',
                specific_claim='expects CPI shelter to fall to 3-4% range in 2026 as lagged rent data catches up',
                metric='cpi_shelter',
                timeframe='2026',
                date='December 2024',
                tier=1,
                rationale='Fed Chair Powell commentary on housing inflation',
            ),
            ExpertView(
                source='Zillow',
                specific_claim='Observed Rent Index shows market rents up only 3.5% YoY as of December 2025',
                metric='market_rents',
                timeframe='December 2025',
                date='January 2026',
                tier=3,
                rationale='Zillow Observed Rent Index shows 3.5% annual growth',
            ),
            ExpertView(
                source='Goldman Sachs',
                specific_claim='forecasts CPI shelter dropping from 5.5% to 4.0% by end-2026',
                metric='cpi_shelter',
                timeframe='end-2026',
                date='January 2026',
                tier=3,
                rationale='Market rent deceleration with 12-month lag to CPI',
            ),
        ],
    ),

    # =========================================================================
    # RECESSION RISK
    # =========================================================================
    'recession_risk': TopicViews(
        topic='Recession probability',
        last_updated='January 2026',
        consensus='Recession probability at 15-20% for 2026; soft landing remains base case',
        key_disagreement='Goldman at 15% vs Morgan Stanley at 20%; consumer strength uncertain',
        views=[
            ExpertView(
                source='NY Fed Recession Probability',
                specific_claim='model shows 25% probability of recession in next 12 months based on yield curve',
                metric='recession_probability',
                timeframe='next 12 months',
                date='January 2026',
                tier=1,
                rationale='Probit model based on Treasury spread',
                url='https://www.newyorkfed.org/research/capital_markets/ycfaq.html',
            ),
            ExpertView(
                source='Conference Board LEI',
                specific_claim='Leading Economic Index rose 0.2% in December after 6 months of declines; no longer signaling recession',
                metric='lei_change',
                timeframe='December 2025',
                date='January 2026',
                tier=2,
                rationale='LEI has stopped declining after prior deterioration',
                url='https://www.conference-board.org/topics/us-leading-indicators',
            ),
            ExpertView(
                source='Polymarket',
                specific_claim='shows 18% probability of US recession in 2026 (defined as two consecutive quarters of negative GDP)',
                metric='recession_probability',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Aggregated market-based probability estimate',
                url='https://polymarket.com/event/us-recession-before-2027',
            ),
            ExpertView(
                source='Claudia Sahm (Sahm Rule)',
                specific_claim='Sahm Rule indicator at 0.43 in December 2025, below 0.5 trigger threshold',
                metric='sahm_indicator',
                timeframe='December 2025',
                date='January 2026',
                tier=2,
                rationale='Real-time recession indicator based on unemployment rate dynamics',
                url='https://fred.stlouisfed.org/series/SAHMREALTIME',
            ),
            ExpertView(
                source='NBER Business Cycle Dating',
                specific_claim='has not declared a recession; current expansion began April 2020 (now 57 months old)',
                metric='recession_dating',
                timeframe='as of December 2025',
                date='December 2025',
                tier=2,
                rationale='Official business cycle dating committee',
                url='https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions',
            ),
        ],
    ),

    'soft_landing': TopicViews(
        topic='Soft landing scenario',
        last_updated='January 2026',
        consensus='Soft landing probability at 60-65%; inflation falling while unemployment stays below 4.5%',
        key_disagreement='Whether unemployment can stay below 4.5% as inflation reaches 2%',
        views=[
            ExpertView(
                source='Fed Chair Powell',
                specific_claim='stated Fed is not in a hurry to cut rates; data-dependent approach with unemployment at 4.1%',
                metric='policy_stance',
                timeframe='December 2024',
                date='December 2024',
                tier=1,
                rationale='Powell press conference remarks',
            ),
            ExpertView(
                source='JP Morgan',
                specific_claim='assigns 60% probability to soft landing (inflation to 2.2%, unemployment stays below 4.5%)',
                metric='soft_landing_probability',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Inflation declining while employment holds up',
            ),
            ExpertView(
                source='Bridgewater',
                specific_claim='sees 55% soft landing probability, 25% no landing (reacceleration), 20% hard landing',
                metric='scenario_probabilities',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Balanced upside and downside scenarios',
            ),
        ],
    ),

    # =========================================================================
    # LABOR MARKET
    # =========================================================================
    'labor_market_outlook': TopicViews(
        topic='Labor market trajectory',
        last_updated='January 2026',
        consensus='Unemployment at 4.1%, job gains at 150-200K/month; Fed projects 4.3% by end-2025',
        key_disagreement='Whether unemployment rises to 4.3% (Fed) or stays near 4.1% (Goldman)',
        views=[
            ExpertView(
                source='Federal Reserve SEP',
                specific_claim='projects unemployment at 4.3% by end-2025, remaining at 4.3% through 2026',
                metric='unemployment_rate',
                timeframe='2025-2026',
                date='December 2024',
                tier=1,
                rationale='FOMC Summary of Economic Projections',
            ),
            ExpertView(
                source='BLS',
                specific_claim='unemployment at 4.1% in December 2025; payroll gains averaged 186K/month in Q4 2025',
                metric='unemployment_rate',
                timeframe='December 2025',
                date='January 2026',
                tier=1,
                rationale='Official employment statistics',
            ),
            ExpertView(
                source='Goldman Sachs',
                specific_claim='expects unemployment to stay below 4.3% through 2026 as job gains remain at 150K+/month',
                metric='unemployment_rate',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Job openings declining, quits rate normalizing',
            ),
            ExpertView(
                source='Bank of America',
                specific_claim='sees unemployment risk rising to 4.5% by mid-2026 if consumer spending slows',
                metric='unemployment_rate',
                timeframe='mid-2026',
                date='January 2026',
                tier=3,
                rationale='Initial claims trending higher',
            ),
        ],
    ),

    'wage_growth': TopicViews(
        topic='Wage growth outlook',
        last_updated='January 2026',
        consensus='Wage growth at 4.5% (Atlanta Fed), down from 6%+ peak; needs to reach 3.5% for 2% inflation',
        key_disagreement='Whether 4.5% wage growth is inflationary or sustainable with productivity',
        views=[
            ExpertView(
                source='Atlanta Fed Wage Tracker',
                specific_claim='median wage growth at 4.5% YoY in December 2025, down from 6.7% peak in mid-2022',
                metric='wage_growth',
                timeframe='December 2025',
                date='January 2026',
                tier=1,
                rationale='Official wage tracking from Fed district',
            ),
            ExpertView(
                source='Goldman Sachs',
                specific_claim='estimates wage growth needs to fall to 3.5% YoY to be consistent with 2% inflation target',
                metric='wage_growth_target',
                timeframe='target level',
                date='January 2026',
                tier=3,
                rationale='Based on productivity growth assumptions',
            ),
            ExpertView(
                source='Peterson Institute',
                specific_claim='argues 4.5% wage growth is sustainable if productivity growth stays at 2% (implying 2.5% unit labor costs)',
                metric='wage_sustainability',
                timeframe='ongoing',
                date='January 2026',
                tier=2,
                rationale='Recent productivity gains creating room for higher wages',
            ),
        ],
    ),

    # =========================================================================
    # GDP AND GROWTH
    # =========================================================================
    'gdp_outlook': TopicViews(
        topic='GDP growth outlook',
        last_updated='January 2026',
        consensus='Fed projects 2.0% GDP growth for 2026; Wall Street ranges from 1.8% (MS) to 2.3% (GS)',
        key_disagreement='Goldman at 2.3% vs Morgan Stanley at 1.8%; consumer strength is key variable',
        views=[
            ExpertView(
                source='Federal Reserve SEP',
                specific_claim='projects real GDP growth of 2.1% for 2025, slowing to 2.0% for 2026',
                metric='gdp_growth',
                timeframe='2025-2026',
                date='December 2024',
                tier=1,
                rationale='FOMC Summary of Economic Projections',
            ),
            ExpertView(
                source='Atlanta Fed GDPNow',
                specific_claim='nowcasts Q1 2026 GDP growth at 2.5% annualized (as of January 20, 2026)',
                metric='gdp_growth',
                timeframe='Q1 2026',
                date='January 2026',
                tier=1,
                rationale='Nowcast model incorporating latest data',
            ),
            ExpertView(
                source='Goldman Sachs',
                specific_claim='forecasts 2026 GDP growth at 2.3%, above consensus of 2.0%',
                metric='gdp_growth',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Consumer and investment spending remain solid',
            ),
            ExpertView(
                source='Morgan Stanley',
                specific_claim='forecasts 2026 GDP growth at 1.8%, below consensus, with downside risks',
                metric='gdp_growth',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Consumer spending expected to slow as savings deplete',
            ),
        ],
    ),

    # =========================================================================
    # HOUSING MARKET
    # =========================================================================
    'housing_outlook': TopicViews(
        topic='Housing market outlook',
        last_updated='January 2026',
        consensus='Home prices up 3-4% YoY; existing sales at 4.0M pace (near 30-year low); rates at 6.9%',
        key_disagreement='Goldman sees 3% price gains in 2026 vs Moodys warning of 10-20% overvaluation in some markets',
        views=[
            ExpertView(
                source='National Association of Realtors',
                specific_claim='existing home sales at 4.0M annualized pace in December 2025, near lowest since 1995',
                metric='existing_home_sales',
                timeframe='December 2025',
                date='January 2026',
                tier=3,
                rationale='Existing home sales near multi-decade lows',
            ),
            ExpertView(
                source='Zillow',
                specific_claim='Zillow Home Value Index up 3.8% YoY in December 2025; typical home worth $362,000',
                metric='home_values',
                timeframe='December 2025',
                date='January 2026',
                tier=3,
                rationale='Zillow Home Value Index tracking',
            ),
            ExpertView(
                source='Goldman Sachs',
                specific_claim='forecasts home prices rising 3% in 2026 despite 30-year mortgage rates near 7%',
                metric='home_price_growth',
                timeframe='2026',
                date='January 2026',
                tier=3,
                rationale='Low inventory keeping prices elevated',
            ),
            ExpertView(
                source='Moodys Analytics',
                specific_claim='estimates 15-20% of metro areas are overvalued by 20%+; risk of 5-10% price declines if rates stay above 7%',
                metric='overvaluation_risk',
                timeframe='2026 risk scenario',
                date='January 2026',
                tier=3,
                rationale='Affordability at worst levels since 1980s',
            ),
        ],
    ),

    # =========================================================================
    # FINANCIAL CONDITIONS
    # =========================================================================
    'financial_conditions': TopicViews(
        topic='Financial conditions',
        last_updated='January 2026',
        consensus='Chicago Fed NFCI at -0.45 (loose); Goldman FCI eased 50bp since October despite Fed holding rates',
        key_disagreement='Whether loose conditions support soft landing or undermine inflation fight',
        views=[
            ExpertView(
                source='Chicago Fed NFCI',
                specific_claim='reads -0.45 in January 2026 (negative = loose), 0.2 standard deviations looser than pre-pandemic average',
                metric='nfci_level',
                timeframe='January 2026',
                date='January 2026',
                tier=1,
                rationale='National Financial Conditions Index tracking',
            ),
            ExpertView(
                source='Goldman Sachs FCI',
                specific_claim='eased 50bp since October 2025 on 8% equity gains and 30bp credit spread tightening',
                metric='fci_change',
                timeframe='October 2025 - January 2026',
                date='January 2026',
                tier=3,
                rationale='Stock gains and credit spread tightening',
            ),
            ExpertView(
                source='FOMC Minutes',
                specific_claim='noted financial conditions have eased 75bp equivalent since September 2024 FOMC',
                metric='policy_concern',
                timeframe='September 2024 - December 2024',
                date='December 2024',
                tier=1,
                rationale='FOMC minutes discussion',
            ),
        ],
    ),
}


# =============================================================================
# CLAIM TYPE DETECTION
# =============================================================================

# Keywords indicating different types of claims that need citation
FORECAST_KEYWORDS = [
    'forecast', 'prediction', 'expect', 'project', 'anticipate',
    'outlook', 'estimate for', 'will be', 'will likely', 'will probably',
    'going forward', 'by end of', 'by year-end', 'next year',
    'will cut', 'will raise', 'will hike', 'will hold', 'will pause',
    'will fall', 'will rise', 'will increase', 'will decrease',
    'will continue', 'will remain', 'will stay', 'will moderate',
]

OPINION_KEYWORDS = [
    'interpretation', 'opinion', 'view', 'assessment', 'belief',
    'argues', 'contends', 'believes', 'thinks', 'suggests',
    'indicates', 'implies', 'signals',
]

PROBABILITY_KEYWORDS = [
    'likely', 'probably', 'expected to', 'may', 'could', 'might',
    'should', 'appears to', 'seems to', 'looks like',
    'odds of', 'probability', 'chance of', 'risk of',
]

COMPARISON_KEYWORDS = [
    'compared to consensus', 'relative to expectations', 'versus forecasts',
    'better than expected', 'worse than expected', 'ahead of estimates',
    'behind expectations', 'surprised to the',
]

# Claims that do NOT need citation (factual statements)
NO_CITATION_KEYWORDS = [
    'is', 'was', 'stands at', 'came in at', 'reported', 'released',
    'rose to', 'fell to', 'increased to', 'decreased to',
    'the data shows', 'according to BLS', 'according to BEA',
]


def should_cite(claim_type: str = '', claim_text: str = '') -> bool:
    """
    Determine if a claim type or text needs citation.

    This function analyzes either a claim type label or the actual claim text
    to determine if it should be attributed to a source.

    Needs citation:
        - Forecasts and predictions
        - Opinions and interpretations
        - Probabilistic statements
        - Comparisons to consensus

    No citation needed:
        - Raw data values
        - Simple math/calculations
        - Definitions
        - Official statistics cited with source

    Args:
        claim_type: A label for the type of claim (e.g., 'forecast', 'opinion')
        claim_text: The actual text of the claim to analyze

    Returns:
        True if the claim should be cited, False otherwise.

    Examples:
        >>> should_cite(claim_type='forecast')
        True
        >>> should_cite(claim_text='The Fed will likely cut rates twice')
        True
        >>> should_cite(claim_text='Unemployment is 4.1%')
        False
    """
    # Check claim type
    claim_type_lower = claim_type.lower()
    if any(keyword in claim_type_lower for keyword in FORECAST_KEYWORDS):
        return True
    if any(keyword in claim_type_lower for keyword in OPINION_KEYWORDS):
        return True

    # Check claim text
    claim_text_lower = claim_text.lower()

    # Check for forecast keywords
    if any(keyword in claim_text_lower for keyword in FORECAST_KEYWORDS):
        return True

    # Check for opinion keywords
    if any(keyword in claim_text_lower for keyword in OPINION_KEYWORDS):
        return True

    # Check for probability keywords
    if any(keyword in claim_text_lower for keyword in PROBABILITY_KEYWORDS):
        return True

    # Check for comparison keywords
    if any(keyword in claim_text_lower for keyword in COMPARISON_KEYWORDS):
        return True

    return False


def detect_claim_type(text: str) -> str:
    """
    Detect what type of claim a piece of text represents.

    Args:
        text: The text to analyze

    Returns:
        Claim type string: 'forecast', 'opinion', 'probability',
        'comparison', or 'factual'
    """
    text_lower = text.lower()

    if any(keyword in text_lower for keyword in FORECAST_KEYWORDS):
        return 'forecast'

    if any(keyword in text_lower for keyword in OPINION_KEYWORDS):
        return 'opinion'

    if any(keyword in text_lower for keyword in PROBABILITY_KEYWORDS):
        return 'probability'

    if any(keyword in text_lower for keyword in COMPARISON_KEYWORDS):
        return 'comparison'

    return 'factual'


# =============================================================================
# EXPERT VIEW RETRIEVAL
# =============================================================================

def get_expert_views(topic: str) -> List[ExpertView]:
    """
    Get expert views on a topic for citation.

    This function looks up pre-loaded expert views on economic topics.
    Views are sorted by tier (highest authority first).

    Args:
        topic: The topic key (e.g., 'fed_rate_path', 'inflation_outlook')

    Returns:
        List of ExpertView objects, sorted by tier (highest first)

    Example:
        >>> views = get_expert_views('fed_rate_path')
        >>> for v in views[:3]:
        ...     print(f"{v.source}: {v.view}")
        Federal Reserve (Dot Plot): Median projection shows rates falling to 3.4%...
        Goldman Sachs: Expects two 25bp rate cuts in 2026...
    """
    if topic not in EXPERT_VIEWS:
        return []

    topic_views = EXPERT_VIEWS[topic]
    # Sort by tier (lowest tier number = highest authority)
    return sorted(topic_views.views, key=lambda v: v.tier)


def get_topic_consensus(topic: str) -> Optional[str]:
    """
    Get the consensus view on a topic, if available.

    Args:
        topic: The topic key

    Returns:
        Consensus description or None if not available
    """
    if topic not in EXPERT_VIEWS:
        return None
    return EXPERT_VIEWS[topic].consensus


def get_topic_disagreement(topic: str) -> Optional[str]:
    """
    Get the key point of disagreement on a topic, if available.

    Args:
        topic: The topic key

    Returns:
        Key disagreement description or None if not available
    """
    if topic not in EXPERT_VIEWS:
        return None
    return EXPERT_VIEWS[topic].key_disagreement


def list_available_topics() -> List[str]:
    """
    List all topics with available expert views.

    Returns:
        List of topic keys
    """
    return list(EXPERT_VIEWS.keys())


def find_topic_for_query(query: str) -> Optional[str]:
    """
    Find the most relevant topic for a user query.

    Args:
        query: The user's query text

    Returns:
        Most relevant topic key, or None if no match
    """
    query_lower = query.lower()

    # Topic keyword mappings
    topic_keywords = {
        'fed_rate_path': [
            'fed rate', 'rate cut', 'rate hike', 'fed funds', 'fomc', 'rate path',
            'interest rate', 'federal reserve', 'the fed', 'what will the fed',
            'fed do', 'fed going to', 'monetary policy', 'powell',
        ],
        'fed_terminal_rate': ['terminal rate', 'neutral rate', 'long-run rate', 'r-star'],
        'inflation_outlook': ['inflation', 'cpi', 'pce', 'prices', 'price level'],
        'shelter_inflation': ['shelter', 'rent inflation', 'housing cost', 'housing inflation'],
        'recession_risk': ['recession', 'downturn', 'economic contraction', 'is a recession'],
        'soft_landing': ['soft landing', 'hard landing', 'avoid recession'],
        'labor_market_outlook': [
            'labor market', 'jobs', 'employment', 'unemployment', 'hiring',
            'job market', 'layoffs', 'workforce',
        ],
        'wage_growth': ['wage', 'earnings', 'pay', 'compensation', 'salary'],
        'gdp_outlook': ['gdp', 'economic growth', 'expansion', 'output growth'],
        'housing_outlook': ['housing', 'home prices', 'real estate', 'mortgage', 'home values'],
        'financial_conditions': ['financial conditions', 'credit', 'lending', 'credit spreads'],
    }

    for topic, keywords in topic_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            return topic

    return None


# =============================================================================
# FORMATTING FUNCTIONS
# =============================================================================

def format_with_attribution(
    claim: str,
    sources: List[Citation],
    include_dates: bool = True,
    use_specific_claims: bool = True,
) -> str:
    """
    Format a claim with proper attribution using SPECIFIC claims from sources.

    This transforms an unsourced claim into an attributed statement
    that cites the SPECIFIC predictions from each source.

    IMPORTANT: This function now uses specific claims with numbers and dates,
    NOT vague summaries.

    Args:
        claim: The generic claim topic (e.g., "Rate cuts expected in 2026")
               - Used as fallback if sources lack specific claims
        sources: List of Citation objects supporting the claim
        include_dates: Whether to include dates in the attribution
        use_specific_claims: If True, use the specific claim text from sources
                            instead of the generic claim (default: True)

    Returns:
        Attributed version with SPECIFIC claims

    Examples:
        BAD (old behavior - vague):
            "Goldman and the Fed both expect rate cuts in 2026."

        GOOD (new behavior - specific):
            "Goldman expects two rate cuts in 2026 (March and June), while the
            Fed's dot plot shows rates falling to 3.4% by end-2026."

        Input with specific sources:
            claim = "Rate cuts expected in 2026"
            sources = [
                Citation(source='Fed Dot Plot', claim='rates at 3.4% by end-2026'),
                Citation(source='Goldman', claim='two 25bp cuts in March and June'),
            ]
        Output:
            "The Fed Dot Plot shows rates at 3.4% by end-2026, while Goldman
            expects two 25bp cuts in March and June."
    """
    if not sources:
        return claim

    # Sort by tier (highest authority first)
    sorted_sources = sorted(sources, key=lambda s: s.tier)

    if len(sorted_sources) == 1:
        # Single source: use specific claim if available
        source = sorted_sources[0]
        date_part = f" ({source.date})" if include_dates and source.date else ""

        if use_specific_claims and source.claim and source.claim != claim:
            # Use the specific claim from the source
            return f"{source.source}{date_part} {source.claim}"
        else:
            return f"{source.source}{date_part} {claim.lower()}"

    # Multiple sources: show SPECIFIC claims from each, highlighting differences
    tier_1_sources = [s for s in sorted_sources if s.tier == 1]
    other_sources = [s for s in sorted_sources if s.tier > 1]

    parts = []

    if tier_1_sources:
        # Lead with official source's SPECIFIC claim
        lead = tier_1_sources[0]
        lead_date = f" ({lead.date})" if include_dates and lead.date else ""

        if use_specific_claims and lead.claim:
            parts.append(f"{lead.source}{lead_date} {lead.claim}")
        else:
            parts.append(f"{lead.source}{lead_date} {claim.lower()}")

        # Add contrasting views from other sources with THEIR specific claims
        if other_sources:
            for other in other_sources[:2]:  # Limit to top 2 non-official sources
                if use_specific_claims and other.claim:
                    parts.append(f"{other.source} {other.claim}")
                else:
                    parts.append(f"{other.source} holds a similar view")

    else:
        # No official source - show competing Wall Street views with specifics
        for i, source in enumerate(sorted_sources[:3]):
            if use_specific_claims and source.claim:
                parts.append(f"{source.source} {source.claim}")
            else:
                parts.append(f"{source.source} {claim.lower()}")

    # Join with appropriate conjunctions to show comparison/contrast
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]}, while {parts[1]}"
    else:
        # Three or more: "A says X, B says Y, and C says Z"
        return f"{parts[0]}; {parts[1]}; and {parts[2]}"


def format_competing_views(
    topic: str,
    max_views: int = 4,
    include_rationale: bool = False,
    include_metrics: bool = True,
) -> str:
    """
    Format competing expert views on a topic using SPECIFIC claims.

    This creates a balanced presentation of different expert opinions,
    highlighting SPECIFIC predictions with numbers and dates.

    IMPORTANT: Uses specific_claim field for detailed, actionable information.

    Args:
        topic: The topic key (e.g., 'fed_rate_path')
        max_views: Maximum number of views to include
        include_rationale: Whether to include the reasoning behind each view
        include_metrics: Whether to include the metric being predicted

    Returns:
        Formatted text showing competing views with SPECIFIC claims

    Example:
        BAD (vague - old behavior):
            "Views on the Fed's rate path vary: Goldman sees cuts, Morgan sees cuts."

        GOOD (specific - new behavior):
            "Views on the Fed's rate path:
            - Fed Dot Plot (Dec 2024): rates at 3.9% by end-2025, 3.4% by end-2026
            - Goldman Sachs (Jan 2026): two 25bp cuts in 2026, in March and June
            - Morgan Stanley (Jan 2026): rate cuts in June and September 2026"
    """
    if topic not in EXPERT_VIEWS:
        return f"No expert views available for topic: {topic}"

    topic_data = EXPERT_VIEWS[topic]
    views = sorted(topic_data.views, key=lambda v: v.tier)[:max_views]

    if not views:
        return f"No expert views available for topic: {topic}"

    # Build narrative
    parts = []

    # Add consensus if available (should now be SPECIFIC)
    if topic_data.consensus:
        parts.append(f"Current picture: {topic_data.consensus}")

    # Add key disagreement if available (should now be SPECIFIC)
    if topic_data.key_disagreement:
        parts.append(f"Key disagreement: {topic_data.key_disagreement}")

    # Add individual views with SPECIFIC claims
    parts.append("")
    parts.append("Specific forecasts:")

    for view in views:
        tier_label = get_tier_label(view.tier)
        date_part = f" ({view.date})" if view.date else ""

        # Use specific_claim instead of generic view
        claim_text = view.specific_claim if view.specific_claim else view.view

        # Build the view line with specifics
        view_line = f"- {view.source}{date_part} [{tier_label}]: {claim_text}"

        # Add metric and timeframe if available and requested
        if include_metrics and (view.metric or view.timeframe):
            metric_info = []
            if view.metric:
                metric_info.append(f"metric: {view.metric}")
            if view.timeframe:
                metric_info.append(f"timeframe: {view.timeframe}")
            if metric_info:
                view_line += f" [{', '.join(metric_info)}]"

        if include_rationale and view.rationale:
            view_line += f" (Rationale: {view.rationale})"

        parts.append(view_line)

    return '\n'.join(parts)


def format_single_view(
    view: ExpertView,
    include_tier: bool = True,
    include_timeframe: bool = True,
    include_url: bool = False,
) -> str:
    """
    Format a single expert view for display using SPECIFIC claim.

    IMPORTANT: Uses specific_claim for detailed, actionable information.

    Args:
        view: The ExpertView to format
        include_tier: Whether to include the tier label
        include_timeframe: Whether to include the timeframe
        include_url: Whether to include URL if available

    Returns:
        Formatted string with SPECIFIC claim

    Example:
        "Goldman Sachs (Jan 2026) [Finance]: expects two 25bp cuts in 2026, in March and June [timeframe: 2026]"
    """
    tier_part = f" [{get_tier_label(view.tier)}]" if include_tier else ""
    date_part = f" ({view.date})" if view.date else ""

    # Use specific_claim instead of generic view
    claim_text = view.specific_claim if view.specific_claim else view.view

    result = f"{view.source}{date_part}{tier_part}: {claim_text}"

    # Add timeframe if available and requested
    if include_timeframe and view.timeframe:
        result += f" [timeframe: {view.timeframe}]"

    # Add URL if available and requested
    if include_url and view.url:
        result += f" ({view.url})"

    return result


def format_view_as_html(
    view: ExpertView,
    include_url: bool = True,
) -> str:
    """
    Format a single expert view as HTML with clickable link.

    Args:
        view: The ExpertView to format
        include_url: Whether to make source a clickable link

    Returns:
        HTML formatted string

    Example:
        '<a href="https://...">Cleveland Fed</a> (Jan 2026): projects CPI at 2.9%'
    """
    date_part = f" ({view.date})" if view.date else ""
    claim_text = view.specific_claim if view.specific_claim else view.view

    if include_url and view.url:
        source_html = f'<a href="{view.url}" target="_blank" style="color: #2563eb; text-decoration: underline;">{view.source}</a>'
    else:
        source_html = f'<strong>{view.source}</strong>'

    return f'{source_html}{date_part}: {claim_text}'


def format_views_as_html_list(
    views: List[ExpertView],
    max_views: int = 3,
    include_urls: bool = True,
) -> str:
    """
    Format multiple expert views as an HTML bullet list.

    Args:
        views: List of ExpertView objects
        max_views: Maximum number of views to include
        include_urls: Whether to make sources clickable links

    Returns:
        HTML formatted bullet list
    """
    if not views:
        return ""

    # Sort by tier (most authoritative first) and take top N
    sorted_views = sorted(views, key=lambda v: v.tier)[:max_views]

    items = []
    for view in sorted_views:
        item_html = format_view_as_html(view, include_url=include_urls)
        items.append(f'<li style="margin-bottom: 8px;">{item_html}</li>')

    return f'<ul style="margin: 0; padding-left: 20px;">{"".join(items)}</ul>'


def format_citation_footer(
    citations_used: List[Citation],
    include_urls: bool = True,
) -> str:
    """
    Format a footer with all sources cited.

    This creates a proper source attribution section for the end of an analysis,
    sorted by tier (most authoritative first).

    Args:
        citations_used: List of Citation objects used in the analysis
        include_urls: Whether to include URLs when available

    Returns:
        Formatted footer text

    Example:
        Output:
        ---
        Sources:
        - Federal Reserve Dot Plot (December 2024)
        - Goldman Sachs Research (January 2026)
        - Morgan Stanley Economics (January 2026)
    """
    if not citations_used:
        return ""

    # Deduplicate by source name
    seen_sources = set()
    unique_citations = []
    for citation in citations_used:
        if citation.source not in seen_sources:
            seen_sources.add(citation.source)
            unique_citations.append(citation)

    # Sort by tier
    sorted_citations = sorted(unique_citations, key=lambda c: c.tier)

    lines = ["---", "Sources:"]

    for citation in sorted_citations:
        date_part = f" ({citation.date})" if citation.date else ""
        line = f"- {citation.source}{date_part}"

        if include_urls and citation.url:
            line += f" - {citation.url}"

        lines.append(line)

    return '\n'.join(lines)


def format_inline_citation(citation: Citation) -> str:
    """
    Format a citation for inline use in text.

    Args:
        citation: The Citation to format

    Returns:
        Inline citation text (e.g., "(Goldman Sachs, Jan 2026)")
    """
    date_part = f", {citation.date}" if citation.date else ""
    return f"({citation.source}{date_part})"


# =============================================================================
# ANALYSIS ENHANCEMENT
# =============================================================================

def add_citations_to_analysis(
    analysis_text: str,
    available_topics: Optional[List[str]] = None,
) -> Tuple[str, List[Citation]]:
    """
    Enhance analysis text with appropriate citations.

    This function scans the analysis for claims that need attribution
    and adds source references where appropriate. It also returns a list
    of citations used for creating a footer.

    Args:
        analysis_text: The analysis text to enhance
        available_topics: Topics to check for relevant views (defaults to all)

    Returns:
        Tuple of (enhanced_text, citations_used)
    """
    if available_topics is None:
        available_topics = list(EXPERT_VIEWS.keys())

    citations_used: List[Citation] = []
    enhanced_text = analysis_text

    # Find sentences that need citation
    sentences = re.split(r'(?<=[.!?])\s+', analysis_text)
    enhanced_sentences = []

    for sentence in sentences:
        if not sentence.strip():
            enhanced_sentences.append(sentence)
            continue

        # Check if this sentence needs citation
        if should_cite(claim_text=sentence):
            # Find relevant topic
            relevant_topic = None
            for topic in available_topics:
                if _sentence_matches_topic(sentence, topic):
                    relevant_topic = topic
                    break

            if relevant_topic:
                views = get_expert_views(relevant_topic)
                if views:
                    # Add inline attribution
                    top_view = views[0]  # Highest tier
                    citation = top_view.to_citation(relevant_topic)
                    citations_used.append(citation)

                    # Add attribution if not already present
                    source_lower = top_view.source.lower()
                    if source_lower not in sentence.lower():
                        inline_cite = format_inline_citation(citation)
                        enhanced_sentences.append(f"{sentence.rstrip('.')} {inline_cite}.")
                    else:
                        enhanced_sentences.append(sentence)
                else:
                    enhanced_sentences.append(sentence)
            else:
                enhanced_sentences.append(sentence)
        else:
            enhanced_sentences.append(sentence)

    enhanced_text = ' '.join(enhanced_sentences)
    return enhanced_text, citations_used


def _sentence_matches_topic(sentence: str, topic: str) -> bool:
    """Check if a sentence is related to a topic."""
    sentence_lower = sentence.lower()
    topic_lower = topic.lower()

    # Topic keyword mappings (simplified)
    topic_keywords = {
        'fed_rate_path': ['rate cut', 'rate hike', 'fed rate', 'rate path'],
        'inflation_outlook': ['inflation', 'cpi', 'pce', 'prices'],
        'recession_risk': ['recession', 'downturn'],
        'labor_market_outlook': ['unemployment', 'jobs', 'labor'],
        'gdp_outlook': ['gdp', 'growth'],
        'housing_outlook': ['housing', 'home prices'],
    }

    keywords = topic_keywords.get(topic, [topic.replace('_', ' ')])
    return any(keyword in sentence_lower for keyword in keywords)


# =============================================================================
# FRESH VIEW FETCHING (INTEGRATION WITH news_context.py)
# =============================================================================

def fetch_fresh_views(topic: str) -> List[ExpertView]:
    """
    Fetch fresh expert views using news_context.py search.

    This updates expert views with current information from trusted news sources.
    Falls back to cached views if search fails.

    Args:
        topic: The topic to search for (e.g., 'fed_rate_path')

    Returns:
        List of ExpertView objects from recent news

    Note:
        Requires news_context.py and SERPAPI_KEY environment variable.
    """
    try:
        from core.news_context import search_news, get_source_tier as news_tier
    except ImportError:
        # news_context not available, return cached views
        return get_expert_views(topic)

    # Map topic to search query
    topic_queries = {
        'fed_rate_path': 'Federal Reserve rate path forecast 2026',
        'inflation_outlook': 'inflation forecast outlook 2026',
        'recession_risk': 'recession probability forecast 2026',
        'labor_market_outlook': 'labor market employment outlook 2026',
        'gdp_outlook': 'GDP growth forecast 2026',
        'housing_outlook': 'housing market forecast 2026',
    }

    query = topic_queries.get(topic, f'{topic.replace("_", " ")} forecast')

    try:
        results = search_news(query, num_results=5)

        fresh_views = []
        for result in results:
            # Convert search result to ExpertView
            view = ExpertView(
                source=result.get('source', 'Unknown'),
                view=result.get('snippet', '')[:200],  # Truncate long snippets
                date=result.get('date'),
                tier=result.get('tier', 4),
            )
            fresh_views.append(view)

        return fresh_views

    except Exception as e:
        # Search failed, return cached views
        print(f"[Citations] Fresh view fetch failed for {topic}: {e}")
        return get_expert_views(topic)


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

# Patterns that indicate a VAGUE (bad) claim - these should be rejected
VAGUE_CLAIM_PATTERNS = [
    r'^[A-Za-z\s]+ see[s]? the .+ as',  # "Goldman sees the labor market as resilient"
    r'^[A-Za-z\s]+ expect[s]? .+ to (moderate|improve|weaken|strengthen)$',  # "Analysts expect inflation to moderate"
    r'^experts are divided',  # "Experts are divided on recession risk"
    r'^[A-Za-z\s]+ (is|are) (bullish|bearish|optimistic|pessimistic)',  # "Goldman is bullish"
    r'^[A-Za-z\s]+ has a (positive|negative|cautious) (view|outlook)',  # "Fed has a cautious outlook"
]

# Patterns that indicate a SPECIFIC (good) claim - should contain numbers/dates
SPECIFIC_CLAIM_INDICATORS = [
    r'\d+(\.\d+)?%',  # Contains a percentage (4.5%, 2.2%)
    r'\d+ ?bp',  # Contains basis points (25bp, 50 bp)
    r'(Q[1-4]|January|February|March|April|May|June|July|August|September|October|November|December) \d{4}',  # Quarter or month with year
    r'(end|mid|early|late)[- ]?\d{4}',  # Timeframe with year (end-2026)
    r'(by|through|until) \d{4}',  # By/through year
    r'\$[\d,]+',  # Dollar amounts
    r'\d+ (cuts?|hikes?|months?)',  # Numeric counts
    r'(at|to|from) \d+(\.\d+)?',  # Numeric targets
]


def is_vague_claim(claim: str) -> bool:
    """
    Check if a claim is too vague (lacks specific numbers/dates/predictions).

    Vague claims should be rejected and replaced with specific ones.

    Args:
        claim: The claim text to check

    Returns:
        True if the claim is vague and should be rejected

    Examples:
        is_vague_claim("Goldman sees the labor market as resilient") -> True (BAD)
        is_vague_claim("expects unemployment to stay below 4.5% through 2026") -> False (GOOD)
    """
    claim_lower = claim.lower()

    # Check for vague patterns
    for pattern in VAGUE_CLAIM_PATTERNS:
        if re.search(pattern, claim_lower, re.IGNORECASE):
            return True

    return False


def is_specific_claim(claim: str) -> bool:
    """
    Check if a claim is specific enough (has numbers, dates, or concrete predictions).

    Specific claims are required for all expert views.

    Args:
        claim: The claim text to check

    Returns:
        True if the claim is specific enough

    Examples:
        is_specific_claim("Goldman expects two rate cuts in 2026") -> True (GOOD)
        is_specific_claim("Goldman is optimistic about rates") -> False (BAD)
    """
    # Check for specific indicators
    for pattern in SPECIFIC_CLAIM_INDICATORS:
        if re.search(pattern, claim, re.IGNORECASE):
            return True

    return False


def validate_expert_view(view: ExpertView) -> Tuple[bool, str]:
    """
    Validate that an ExpertView has a specific claim with numbers/dates.

    Returns (is_valid, reason).

    Args:
        view: The ExpertView to validate

    Returns:
        Tuple of (is_valid, validation_message)

    Examples:
        Good view:
            source='Goldman Sachs'
            specific_claim='expects unemployment to stay below 4.5% through 2026'
            -> (True, "Valid: contains percentage and timeframe")

        Bad view:
            source='Goldman Sachs'
            specific_claim='sees the labor market as resilient'
            -> (False, "Vague: lacks specific numbers, dates, or predictions")
    """
    claim = view.specific_claim or view.view

    if not claim:
        return False, "Missing: no claim provided"

    if is_vague_claim(claim):
        return False, f"Vague: '{claim}' lacks specific numbers, dates, or predictions"

    if not is_specific_claim(claim):
        return False, f"Needs specifics: '{claim}' should include numbers, percentages, or dates"

    # Check for required fields on new-style views
    if not view.metric:
        return False, f"Missing metric field (what is being predicted?)"

    if not view.timeframe:
        return False, f"Missing timeframe field (when does this apply?)"

    return True, "Valid: contains specific prediction with metric and timeframe"


def validate_all_expert_views() -> Dict[str, List[Tuple[str, bool, str]]]:
    """
    Validate all expert views in EXPERT_VIEWS and return validation results.

    Returns:
        Dict mapping topic -> list of (source, is_valid, message) tuples

    Usage:
        results = validate_all_expert_views()
        for topic, validations in results.items():
            for source, is_valid, msg in validations:
                if not is_valid:
                    print(f"[{topic}] {source}: {msg}")
    """
    results = {}

    for topic, topic_views in EXPERT_VIEWS.items():
        topic_results = []
        for view in topic_views.views:
            is_valid, message = validate_expert_view(view)
            topic_results.append((view.source, is_valid, message))
        results[topic] = topic_results

    return results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_view_for_topic_and_source(topic: str, source: str) -> Optional[ExpertView]:
    """
    Get a specific source's view on a topic.

    Args:
        topic: The topic key
        source: The source name to look for

    Returns:
        The ExpertView if found, None otherwise
    """
    views = get_expert_views(topic)
    source_lower = source.lower()

    for view in views:
        if source_lower in view.source.lower():
            return view

    return None


def get_official_view(topic: str) -> Optional[ExpertView]:
    """
    Get the official (Tier 1) view on a topic.

    Args:
        topic: The topic key

    Returns:
        The highest-authority ExpertView if available
    """
    views = get_expert_views(topic)

    for view in views:
        if view.tier == 1:
            return view

    return None


def get_wall_street_consensus(topic: str) -> Optional[str]:
    """
    Get a summary of Wall Street (Tier 3) views on a topic.

    Args:
        topic: The topic key

    Returns:
        Summary text of financial institution views
    """
    views = get_expert_views(topic)
    tier_3_views = [v for v in views if v.tier == 3]

    if not tier_3_views:
        return None

    sources = [v.source for v in tier_3_views]
    if len(sources) == 1:
        return f"{sources[0]}: {tier_3_views[0].view}"

    # Summarize multiple views
    source_list = ', '.join(sources)
    return f"Major forecasters ({source_list}) broadly expect similar outcomes, with some variation in timing."


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("CITATION AND ATTRIBUTION SYSTEM - TESTS")
    print("=" * 70)

    # Test 1: Check if claims need citation
    print("\n1. CLAIM TYPE DETECTION")
    print("-" * 40)

    test_claims = [
        "Unemployment is 4.1%",
        "The Fed will likely cut rates twice in 2026",
        "Inflation will continue to moderate",
        "GDP grew 2.5% in Q3",
        "Most forecasters expect inflation to decline",
        "This suggests labor market cooling",
    ]

    for claim in test_claims:
        needs_cite = should_cite(claim_text=claim)
        claim_type = detect_claim_type(claim)
        status = "NEEDS CITATION" if needs_cite else "OK (factual)"
        print(f"  [{status}] ({claim_type}): {claim}")

    # Test 2: Get expert views
    print("\n\n2. EXPERT VIEWS RETRIEVAL")
    print("-" * 40)

    for topic in ['fed_rate_path', 'inflation_outlook', 'recession_risk']:
        print(f"\nTopic: {topic}")
        views = get_expert_views(topic)
        for v in views[:3]:
            print(f"  - {format_single_view(v)}")

    # Test 3: Format competing views
    print("\n\n3. COMPETING VIEWS FORMAT")
    print("-" * 40)

    print(format_competing_views('fed_rate_path', max_views=4))

    # Test 4: Format with attribution - NOW WITH SPECIFIC CLAIMS
    print("\n\n4. ATTRIBUTION FORMATTING (SPECIFIC CLAIMS)")
    print("-" * 40)

    # BAD example - vague claims (should not use)
    print("\nBAD (vague - what we're avoiding):")
    print("  'Goldman and the Fed both expect rate cuts in 2026.'")

    # GOOD example - specific claims
    print("\nGOOD (specific - what we now produce):")
    citations = [
        Citation(
            source='Federal Reserve Dot Plot',
            claim='median shows rates at 3.9% by end-2025, 3.4% by end-2026',
            date='December 2024',
            tier=1
        ),
        Citation(
            source='Goldman Sachs',
            claim='expects two 25bp cuts in 2026, in March and June',
            date='January 2026',
            tier=3
        ),
        Citation(
            source='Morgan Stanley',
            claim='projects rate cuts in June and September 2026',
            date='January 2026',
            tier=3
        ),
    ]

    claim = "Rate cuts expected in 2026"
    attributed = format_with_attribution(claim, citations)
    print(f"  Original generic claim: {claim}")
    print(f"  With specific attribution: {attributed}")

    # Test 5: Citation footer
    print("\n\n5. CITATION FOOTER")
    print("-" * 40)

    footer = format_citation_footer(citations)
    print(footer)

    # Test 6: Topic finding
    print("\n\n6. TOPIC FINDING FOR QUERIES")
    print("-" * 40)

    test_queries = [
        "What is the Fed going to do with rates?",
        "Is a recession coming?",
        "How will inflation evolve?",
        "What's the labor market outlook?",
    ]

    for query in test_queries:
        topic = find_topic_for_query(query)
        print(f"  Query: '{query}'")
        print(f"  Matched topic: {topic}")
        print()

    # Test 7: Get official view
    print("\n7. OFFICIAL VIEWS")
    print("-" * 40)

    for topic in ['fed_rate_path', 'inflation_outlook']:
        official = get_official_view(topic)
        if official:
            print(f"  {topic}: {official.source} - {official.view}")
        else:
            print(f"  {topic}: No official view available")

    # Test 8: Tier detection
    print("\n\n8. SOURCE TIER DETECTION")
    print("-" * 40)

    test_sources = [
        'Federal Reserve',
        'Goldman Sachs',
        'Wall Street Journal',
        'NBER',
        'Random Blog',
    ]

    for source in test_sources:
        tier = get_source_tier(source)
        label = get_tier_label(tier)
        print(f"  {source}: Tier {tier} ({label})")

    # Test 9: Claim specificity validation
    print("\n\n9. CLAIM SPECIFICITY VALIDATION")
    print("-" * 40)

    # Test vague vs specific claims
    test_claims_specificity = [
        # BAD - vague claims
        ("Goldman sees the labor market as resilient", "VAGUE"),
        ("Analysts expect inflation to moderate", "VAGUE"),
        ("Experts are divided on recession risk", "VAGUE"),
        ("Fed is optimistic about growth", "VAGUE"),
        # GOOD - specific claims
        ("expects unemployment to stay below 4.5% through 2026", "SPECIFIC"),
        ("projects rate cuts in June and September 2026", "SPECIFIC"),
        ("shows 18% probability of US recession in 2026", "SPECIFIC"),
        ("forecasts core PCE at 2.2% by end-2026", "SPECIFIC"),
        ("median shows rates at 3.9% by end-2025, 3.4% by end-2026", "SPECIFIC"),
    ]

    print("\nVague vs Specific Claim Detection:")
    for claim_text, expected in test_claims_specificity:
        is_vague = is_vague_claim(claim_text)
        is_spec = is_specific_claim(claim_text)

        if expected == "VAGUE":
            result = "VAGUE" if is_vague or not is_spec else "SPECIFIC"
        else:
            result = "SPECIFIC" if is_spec and not is_vague else "VAGUE"

        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] {result}: {claim_text[:50]}...")

    # Test 10: Validate all expert views
    print("\n\n10. EXPERT VIEW VALIDATION (All views should be specific)")
    print("-" * 40)

    validation_results = validate_all_expert_views()
    all_valid = True
    for topic, validations in validation_results.items():
        invalid_views = [(src, msg) for src, is_valid, msg in validations if not is_valid]
        if invalid_views:
            all_valid = False
            print(f"\n  [{topic}] - {len(invalid_views)} invalid views:")
            for src, msg in invalid_views:
                print(f"    - {src}: {msg}")
        else:
            print(f"  [{topic}] - All {len(validations)} views are specific")

    if all_valid:
        print("\n  ALL EXPERT VIEWS ARE PROPERLY SPECIFIC!")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
