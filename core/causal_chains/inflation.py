"""
Causal Chain Models for Inflation Dynamics.

This module provides structured representations of how inflation transmits through
the economy. Each chain models a different inflation driver with:
- Defined stages with typical lags
- Relevant economic series for each stage
- Detection functions to identify current position
- Interpretation functions to explain the dynamics

Key insight: Inflation is not monolithic. Understanding WHICH type of inflation
is occurring (demand-pull vs cost-push) is crucial for policy response and forecasting.

Current context (as of early 2026):
- Headline inflation falling toward 2% target
- Shelter inflation sticky but should decline (market rents already fell)
- Goods in outright deflation
- Services ex-shelter normalizing
- Labor market cooling but not collapsing
"""

from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum


# =============================================================================
# CHAIN STAGE DEFINITIONS
# =============================================================================

class ChainStatus(Enum):
    """Status of a causal chain stage."""
    NOT_TRIGGERED = "not_triggered"
    EARLY = "early"
    ACTIVE = "active"
    PEAK = "peak"
    REVERSING = "reversing"
    NORMALIZED = "normalized"


@dataclass
class ChainStage:
    """A single stage in a causal chain."""
    name: str
    description: str
    series: list[str]  # FRED series IDs to monitor
    lag_months: tuple[int, int]  # (min_lag, max_lag) from previous stage
    threshold_rising: Optional[float] = None  # Threshold for "triggered"
    threshold_falling: Optional[float] = None  # Threshold for "reversing"

    def __post_init__(self):
        if self.series is None:
            self.series = []


@dataclass
class CausalChain:
    """A complete causal chain with stages and detection logic."""
    name: str
    description: str
    stages: list[ChainStage]
    key_insight: str
    policy_relevance: str

    def get_stage_names(self) -> list[str]:
        """Get list of stage names in order."""
        return [stage.name for stage in self.stages]

    def get_all_series(self) -> list[str]:
        """Get all series IDs used across all stages."""
        all_series = []
        for stage in self.stages:
            all_series.extend(stage.series)
        return list(set(all_series))


# =============================================================================
# DEMAND-PULL INFLATION CHAIN
# =============================================================================

DEMAND_PULL = CausalChain(
    name="DEMAND_PULL",
    description="""
    When people want to buy more stuff than the economy can produce, prices go up.
    That's demand-pull inflation - too much money chasing too few goods.

    How it works: People spend more -> Businesses run at full tilt -> They raise prices
    because they can -> Workers demand higher wages -> Those wages get passed on as higher prices

    When has this happened?
    - The 1960s: Government spent big on Vietnam AND social programs (guns + butter)
    - 2021-2022: Everyone got stimulus checks and spent them while factories were still recovering from COVID
    """,
    stages=[
        ChainStage(
            name="Spending takes off",
            description="People and businesses are spending faster than the economy can keep up",
            series=[
                "GDPC1",           # Real GDP
                "PCEC96",          # Real Personal Consumption
                "RSXFS",           # Retail Sales (ex food services)
                "UMCSENT",         # Consumer Sentiment
            ],
            lag_months=(0, 0),
            threshold_rising=3.0,  # GDP growth > 3% signals strong demand
        ),
        ChainStage(
            name="Economy running hot",
            description="Factories are near capacity, employers can't find enough workers",
            series=[
                "TCU",             # Total Capacity Utilization
                "UNRATE",          # Unemployment Rate (inverse of labor slack)
                "JTSJOL",          # Job Openings (labor demand)
            ],
            lag_months=(0, 3),
            threshold_rising=80.0,  # Capacity util > 80% is tight
            threshold_falling=75.0,
        ),
        ChainStage(
            name="Businesses raise prices",
            description="With customers lined up, businesses can charge more and people will still pay",
            series=[
                "PPIFIS",          # PPI Final Demand
                "CPIAUCSL",        # CPI All Items
                "CUSR0000SAC",     # CPI Commodities
            ],
            lag_months=(1, 4),
            threshold_rising=3.0,  # YoY > 3%
        ),
        ChainStage(
            name="Workers demand higher pay",
            description="With jobs plentiful and prices rising, workers push for raises - and get them",
            series=[
                "CES0500000003",   # Avg Hourly Earnings (Private)
                "ECIWAG",          # ECI Wages and Salaries
                "AHETPI",          # Avg Hourly Earnings (Production)
            ],
            lag_months=(3, 6),
            threshold_rising=4.0,  # Wage growth > 4% with 1-2% productivity
        ),
        ChainStage(
            name="It costs more to make things",
            description="If wages rise 5% but productivity only rises 1%, businesses pay 4% more per widget. That gets passed on.",
            series=[
                "ULCNFB",          # Unit Labor Cost (Nonfarm Business)
                "OPHNFB",          # Output per Hour (Nonfarm Business)
                "COMPNFB",         # Compensation per Hour
            ],
            lag_months=(0, 2),
            threshold_rising=3.0,  # ULC > 3% is concerning
        ),
        ChainStage(
            name="Services get expensive",
            description="Haircuts, doctor visits, restaurants - services are labor-heavy, so wage increases hit them hardest",
            series=[
                "CUSR0000SAS",     # CPI Services
                "CUSR0000SASLE",   # CPI Services Less Energy
                "PCEPILFE",        # Core PCE (Fed's target)
            ],
            lag_months=(3, 6),
            threshold_rising=3.5,  # Services > 3.5% is above target
        ),
    ],
    key_insight="""
    A little demand-pull inflation is actually fine - it means the economy is strong.
    The danger is letting it run too hot. Once people expect high inflation, they act
    on those expectations (demanding bigger raises, raising prices preemptively), and
    it becomes self-fulfilling. That's when you need a painful recession to break the cycle.
    """,
    policy_relevance="""
    The Fed's job: Raise rates to cool things down before expectations get out of hand.
    The government's job: Don't pour gasoline on the fire with stimulus when things are already hot.
    The challenge: Cool the economy just enough without causing a recession. That's the "soft landing."
    """,
)


# =============================================================================
# COST-PUSH INFLATION CHAIN
# =============================================================================

COST_PUSH = CausalChain(
    name="COST_PUSH",
    description="""
    When something disrupts supply - oil shock, shipping crisis, war - it costs more
    to make things, and those costs get passed on to you. This is cost-push inflation.

    The nasty part: Unlike demand-pull, this can happen even when the economy is weak.
    Higher prices AND less output. Economists call this "stagflation."

    When has this happened?
    - 1973-74: Arab oil embargo quadrupled oil prices almost overnight
    - 2021-22: Ships stuck at ports, factories closed, everything in short supply
    - 2022: Russia invaded Ukraine, energy prices spiked across Europe
    """,
    stages=[
        ChainStage(
            name="Something breaks",
            description="Oil spikes, shipping freezes, a war disrupts trade - something outside our control",
            series=[
                "DCOILWTICO",      # WTI Crude Oil
                "DCOILBRENTEU",    # Brent Crude
                "PPIACO",          # PPI All Commodities
                "WPU101",          # PPI Metals
            ],
            lag_months=(0, 0),
            threshold_rising=20.0,  # Oil +20% YoY is a shock
        ),
        ChainStage(
            name="Raw materials get expensive",
            description="Steel, chemicals, components - everything businesses need to make stuff costs more",
            series=[
                "PPIITM",          # PPI Intermediate Materials
                "PCUOMFGOMFG",     # PPI Manufacturing
                "WPU0561",         # PPI Industrial Chemicals
            ],
            lag_months=(0, 2),
            threshold_rising=5.0,
        ),
        ChainStage(
            name="Businesses raise wholesale prices",
            description="Manufacturers can't eat the cost forever - they raise prices to retailers",
            series=[
                "PPIFIS",          # PPI Final Demand
                "PPIFGS",          # PPI Finished Goods
                "WPSFD4111",       # PPI Finished Consumer Goods
            ],
            lag_months=(1, 3),
            threshold_rising=4.0,
        ),
        ChainStage(
            name="You see it at the store",
            description="Retailers pass on some (not all) of the cost increase to consumers, usually 3-6 months later",
            series=[
                "CPIAUCSL",        # CPI All Items
                "CUSR0000SAC",     # CPI Commodities
                "CUSR0000SETA02",  # CPI Used Vehicles
            ],
            lag_months=(3, 6),
            threshold_rising=3.0,
        ),
        ChainStage(
            name="The danger zone",
            description="If people start expecting high inflation to stick around, they change their behavior - and it becomes permanent",
            series=[
                "MICH",            # Michigan Inflation Expectations (1yr)
                "T5YIFR",          # 5yr 5yr Forward Inflation Expectations
                "EXPINF1YR",       # Cleveland Fed 1yr Inflation Expectations
            ],
            lag_months=(3, 12),
            threshold_rising=3.5,  # Expectations above target
        ),
    ],
    key_insight="""
    Here's the key question: Is this temporary or permanent?

    If people believe it's a one-time shock (oil will come back down, supply chains
    will unclog), they don't change their behavior much. Inflation spikes and fades.

    But if people think "this is the new normal," they demand higher wages, businesses
    raise prices preemptively, and it feeds on itself. That's what happened in the 1970s.

    The difference? Whether people trust the Fed to bring it back under control.
    """,
    policy_relevance="""
    The Fed's dilemma: If they raise rates during a supply shock, they're slowing an
    economy that's already hurting. But if they don't, and expectations slip, it gets worse.

    Usually they "look through" temporary shocks and wait. But if expectations start rising,
    they have to act - even if it means a recession. That's what Volcker did in 1979.
    """,
)


# =============================================================================
# SHELTER INFLATION CHAIN (Critical for Current Environment)
# =============================================================================

SHELTER_INFLATION = CausalChain(
    name="SHELTER_INFLATION",
    description="""
    This is THE most important thing to understand about 2023-2026 inflation.

    The government's rent number is always behind reality - by a year or more. Why?
    Because they measure what people are actually paying, and most renters are locked
    into leases signed 6-12 months ago.

    So when Zillow shows rents dropping, the official number keeps rising for another
    year while old expensive leases roll off. It's maddening if you don't know why.

    Right now (2026): Market rents cooled a while ago. The official shelter number is
    still high but falling. This is why inflation has been slow to come down.
    """,
    stages=[
        ChainStage(
            name="The Fed moves",
            description="When mortgage rates jump, everything downstream changes",
            series=[
                "FEDFUNDS",        # Fed Funds Rate
                "MORTGAGE30US",    # 30-Year Mortgage Rate
                "MORTGAGE15US",    # 15-Year Mortgage Rate
            ],
            lag_months=(0, 0),
            threshold_rising=5.0,  # Mortgage rates > 5% slow housing
            threshold_falling=4.0,
        ),
        ChainStage(
            name="Home buying slows (or surges)",
            description="When monthly payments change by hundreds of dollars, people notice",
            series=[
                "EXHOSLUSM495S",   # Existing Home Sales
                "HSN1F",           # New Single Family Homes Sold
                "HOUST1F",         # Single Family Housing Starts
            ],
            lag_months=(1, 3),
        ),
        ChainStage(
            name="Home prices follow",
            description="With more or fewer buyers competing, prices adjust over 6-12 months",
            series=[
                "CSUSHPINSA",      # Case-Shiller US National
                "MSPUS",           # Median Sales Price
                "ASPUS",           # Average Sales Price
                "zillow_zhvi_national",  # Zillow Home Value Index
            ],
            lag_months=(3, 9),
            threshold_rising=5.0,  # YoY > 5% is strong appreciation
        ),
        ChainStage(
            name="New lease rents adjust",
            description="What landlords charge on NEW leases (Zillow tracks this in real-time)",
            series=[
                "zillow_zori_national",  # Zillow Observed Rent Index (LEADING)
                "zillow_rent_yoy",       # Zillow Rent YoY Change
            ],
            lag_months=(3, 12),
            threshold_rising=5.0,
        ),
        ChainStage(
            name="Official rent numbers catch up (slowly)",
            description="Takes 12-18 months because most renters are on year-long leases at old prices",
            series=[
                "CUSR0000SAH1",    # CPI Shelter (headline)
                "CUSR0000SEHA",    # CPI Rent of Primary Residence
                "CUSR0000SEHC",    # CPI Owner's Equivalent Rent
            ],
            lag_months=(12, 18),
            threshold_rising=4.0,  # Above 3% is elevated
        ),
        ChainStage(
            name="Full cycle complete",
            description="When the official number finally reflects reality, usually 1-2 years later",
            series=[
                "MORTGAGE30US",    # Mortgage rates
                "CUSR0000SAH1",    # CPI Shelter (will eventually fall)
            ],
            lag_months=(12, 24),
        ),
    ],
    key_insight="""
    The story of 2021-2026 in one sentence: Rent inflation was baked in when people
    signed expensive leases in 2021-2022, and it took years to work through the system.

    Timeline:
    - 2021-22: Super low rates -> buying frenzy -> home prices spike 40% -> rents follow
    - 2023-24: Fed hikes -> market rents cool (Zillow shows it) -> but official CPI stuck
    - 2025-26: Old leases finally roll off -> official shelter CPI comes down

    Shelter is 1/3 of the whole CPI. This lag is why "inflation is falling" took so long
    even though the Fed started hiking in 2022.
    """,
    policy_relevance="""
    The Fed knows shelter is lagged. But they can't ignore 1/3 of the CPI.

    Their workaround: "Supercore" inflation (services minus housing). This tells them
    what's happening with demand-driven inflation without the shelter noise.

    For you: If you want to know where rent inflation is GOING, look at Zillow, not the CPI.
    """,
)


# =============================================================================
# WAGE-PRICE SPIRAL CHAIN
# =============================================================================

WAGE_PRICE_SPIRAL = CausalChain(
    name="WAGE_PRICE_SPIRAL",
    description="""
    The nightmare scenario: prices go up, so workers demand raises, so businesses
    raise prices to cover wages, so workers demand more raises... and it never stops.

    BUT HERE'S THE KEY: This only happens if people EXPECT it to continue.
    If everyone thinks "inflation will come back down," they don't panic. They accept
    one-time wage bumps and wait. The spiral never starts.

    That's what happened in 2021-2023: inflation hit 9%, but people still expected
    it to fall back to 2-3%. So wages rose once to catch up, then stabilized.
    No spiral. The 1970s were different - expectations got unmoored and it took
    Volcker's brutal recession to break the cycle.
    """,
    stages=[
        ChainStage(
            name="Workers have leverage",
            description="Unemployment is low, jobs are plentiful, people quit for better offers",
            series=[
                "UNRATE",          # Unemployment Rate
                "JTSJOL",          # Job Openings
                "JTSQUR",          # Quits Rate (confidence to quit)
                "LNS12300060",     # Prime-Age EPOP
            ],
            lag_months=(0, 0),
            threshold_rising=0.0,  # UNRATE < 4% is tight
        ),
        ChainStage(
            name="Wages outpace productivity",
            description="If wages rise 5% but each worker only produces 1% more, that's 4% added cost",
            series=[
                "CES0500000003",   # Avg Hourly Earnings
                "ECIWAG",          # ECI Wages
                "OPHNFB",          # Productivity (to compare)
            ],
            lag_months=(3, 6),
            threshold_rising=4.0,  # Wages > 4% with ~1% productivity = trouble
        ),
        ChainStage(
            name="Making stuff costs more",
            description="Businesses pay more for the same output - their margins shrink",
            series=[
                "ULCNFB",          # Unit Labor Cost (Nonfarm Business)
            ],
            lag_months=(0, 2),
            threshold_rising=3.0,
        ),
        ChainStage(
            name="Businesses raise prices",
            description="To protect margins, businesses raise prices - especially in services where labor is the main cost",
            series=[
                "CUSR0000SAS",     # CPI Services (labor-intensive)
                "CUSR0000SASLE",   # CPI Services Less Energy
                "PCEPILFE",        # Core PCE
            ],
            lag_months=(2, 4),
            threshold_rising=3.5,
        ),
        ChainStage(
            name="THE CRITICAL QUESTION: Do expectations shift?",
            description="If people think 'this is temporary,' it ends here. If they think 'inflation is the new normal,' it spirals.",
            series=[
                "MICH",            # Michigan 1yr Expectations
                "T5YIFR",          # 5yr 5yr Forward
                "EXPINF1YR",       # Cleveland Fed Expectations
            ],
            lag_months=(0, 6),
            threshold_rising=3.5,  # Expectations above 3% signals de-anchoring
        ),
        ChainStage(
            name="Spiral or stop?",
            description="With anchored expectations: one-time catch-up, then back to normal. Unanchored: round two of demands, and we're stuck.",
            series=[
                "CES0500000003",   # Wage growth (does it accelerate?)
                "PCEPILFE",        # Core inflation (does it persist?)
            ],
            lag_months=(6, 12),
        ),
    ],
    key_insight="""
    The spiral is NOT automatic. It requires people to lose faith that inflation will
    come back down.

    2021-2023 proved this: 9% inflation, but the 5-year expectation stayed near 2%.
    People trusted the Fed would fix it. So workers got catch-up raises and stopped there.
    No accelerating demands, no spiral.

    That trust took 40 years to build. The 1970s Fed didn't have it.
    """,
    policy_relevance="""
    The Fed's real job isn't just setting rates - it's maintaining credibility.
    If people believe the Fed will do "whatever it takes," inflation expectations
    stay anchored even when prices spike.

    That's why they talk so much about being "data-dependent" and "committed to 2%."
    The words matter as much as the rate hikes.
    """,
)


# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================

@dataclass
class ChainPosition:
    """Current position within a causal chain."""
    chain_name: str
    current_stage: Optional[str]
    stage_status: ChainStatus
    confidence: float  # 0-1
    evidence: list[str]
    next_expected: Optional[str]
    estimated_lag: Optional[tuple[int, int]]


def detect_chain_position(
    chain: CausalChain,
    data: dict[str, dict],
) -> ChainPosition:
    """
    Detect current position in a causal chain based on economic data.

    Args:
        chain: The causal chain to analyze
        data: Dict of series_id -> {value, yoy_change, mom_change, trend}

    Returns:
        ChainPosition with current stage and status
    """
    evidence = []
    active_stage = None
    stage_status = ChainStatus.NOT_TRIGGERED

    # Walk through stages looking for activity
    for i, stage in enumerate(chain.stages):
        stage_active = False
        stage_evidence = []

        for series_id in stage.series:
            if series_id not in data:
                continue

            series_data = data[series_id]
            yoy = series_data.get("yoy_change")
            trend = series_data.get("trend", "stable")

            if yoy is None:
                continue

            # Check thresholds
            if stage.threshold_rising and yoy > stage.threshold_rising:
                stage_active = True
                stage_evidence.append(
                    f"{series_id} at {yoy:.1f}% YoY (above {stage.threshold_rising}% threshold)"
                )
            elif stage.threshold_falling and yoy < stage.threshold_falling:
                stage_evidence.append(
                    f"{series_id} at {yoy:.1f}% YoY (below {stage.threshold_falling}%, reversing)"
                )
                if active_stage == stage.name:
                    stage_status = ChainStatus.REVERSING

        if stage_active:
            active_stage = stage.name
            evidence.extend(stage_evidence)

            # Determine status based on trend
            if series_data.get("trend") == "accelerating":
                stage_status = ChainStatus.EARLY
            elif series_data.get("trend") == "decelerating":
                stage_status = ChainStatus.PEAK
            else:
                stage_status = ChainStatus.ACTIVE

    # Determine next expected stage
    next_stage = None
    estimated_lag = None
    if active_stage:
        stage_names = chain.get_stage_names()
        try:
            current_idx = stage_names.index(active_stage)
            if current_idx < len(chain.stages) - 1:
                next_stage_obj = chain.stages[current_idx + 1]
                next_stage = next_stage_obj.name
                estimated_lag = next_stage_obj.lag_months
        except ValueError:
            pass

    return ChainPosition(
        chain_name=chain.name,
        current_stage=active_stage,
        stage_status=stage_status,
        confidence=min(len(evidence) * 0.2, 0.9),  # More evidence = higher confidence
        evidence=evidence,
        next_expected=next_stage,
        estimated_lag=estimated_lag,
    )


# =============================================================================
# INTERPRETATION FUNCTIONS
# =============================================================================

def interpret_demand_pull(position: ChainPosition, data: dict) -> str:
    """Interpret demand-pull inflation position."""
    if position.stage_status == ChainStatus.NOT_TRIGGERED:
        return """
        No signs of demand-driven inflation right now.

        The economy isn't overheating. Factories have spare capacity, there's no
        spending frenzy, and businesses don't have unusual pricing power. This is
        what a balanced economy looks like.
        """

    if position.current_stage == "Spending takes off":
        return f"""
        Demand is heating up.

        {chr(10).join('- ' + e for e in position.evidence)}

        What happens next: If this continues, factories will start running at capacity
        and employers will struggle to find workers. That's when businesses can start
        raising prices without losing customers. Watch for that in 1-3 months.
        """

    if position.current_stage == "Services get expensive":
        if position.stage_status == ChainStatus.REVERSING:
            return """
            Good news: demand-driven inflation is cooling off.

            Services inflation has peaked and is coming down. This means:
            - The Fed's rate hikes are working
            - The job market is rebalancing (fewer quits, slower wage growth)
            - It's costing less to produce each unit of output

            If this continues, we should see inflation keep falling.
            """
        else:
            return f"""
            Demand-pull inflation has worked through the whole system.

            {chr(10).join('- ' + e for e in position.evidence)}

            Services are labor-heavy, so this is where wage pressures show up last.
            The Fed will keep rates high until this comes down convincingly.
            That usually requires the job market to cool off more.
            """

    if position.estimated_lag:
        return f"""
        We're in the "{position.current_stage}" stage of demand-pull inflation.

        {chr(10).join('- ' + e for e in position.evidence)}

        What's coming next: "{position.next_expected or 'End of the chain'}"
        Expected timing: {position.estimated_lag[0]}-{position.estimated_lag[1]} months from now
        """
    return ""


def interpret_cost_push(position: ChainPosition, data: dict) -> str:
    """Interpret cost-push inflation position."""
    if position.stage_status == ChainStatus.NOT_TRIGGERED:
        return """
        No supply shocks driving prices up right now.

        Oil prices are stable, supply chains are working, raw materials aren't spiking.
        That's good news - there's no outside force pushing prices higher. Makes it
        easier for inflation to come down.
        """

    if "danger zone" in str(position.current_stage).lower():
        return f"""
        This is the critical moment.

        {chr(10).join('- ' + e for e in position.evidence)}

        The big question: Do people think this is temporary, or the new normal?

        If long-term expectations (the 5-year forward rate) stay near 2%: The shock
        will pass. People will grumble about prices but not change their behavior.

        If expectations rise above 3%: Danger. People start demanding raises to keep
        up, businesses raise prices in anticipation, and it feeds on itself. That's
        what happened in the 1970s - a temporary oil shock became permanent inflation.

        Watch the expectation surveys closely.
        """

    if position.stage_status == ChainStatus.REVERSING:
        return """
        The cost shock is fading.

        Input costs are falling. This is showing up as:
        - Wholesale prices (PPI) dropping faster than retail prices (CPI)
        - Goods getting cheaper
        - Energy stabilizing

        When this happens, headline inflation falls faster than core inflation
        because energy and goods are such a big part of the headline number.
        """

    return f"""
    We're seeing cost-push inflation at the "{position.current_stage}" stage.

    {chr(10).join('- ' + e for e in position.evidence)}

    The key thing to watch: Are people's inflation expectations staying put?
    If the 5-year expectation is still near 2%, this will pass. If it's rising,
    we could have a bigger problem.
    """


def interpret_shelter(position: ChainPosition, data: dict) -> str:
    """Interpret shelter inflation dynamics."""

    # Get key data points if available
    cpi_shelter_yoy = data.get("CUSR0000SAH1", {}).get("yoy_change")
    market_rent_yoy = data.get("zillow_rent_yoy", {}).get("value")
    mortgage_rate = data.get("MORTGAGE30US", {}).get("value")

    if position.stage_status == ChainStatus.NOT_TRIGGERED:
        return """
        Nothing unusual happening with housing costs right now.

        The official rent numbers are moving at a normal pace. No big shocks from
        mortgage rates or housing market swings.
        """

    # The critical case: market rents leading CPI shelter down
    if market_rent_yoy is not None and cpi_shelter_yoy is not None:
        if market_rent_yoy < cpi_shelter_yoy:
            gap = cpi_shelter_yoy - market_rent_yoy
            return f"""
            Here's the good news most people miss:

            The official rent number ({cpi_shelter_yoy:.1f}%) looks scary, but it's
            looking in the rear-view mirror. Market rents (what new tenants actually
            pay) are only up {market_rent_yoy:.1f}%.

            That's a {gap:.1f} percentage point gap that will close over time.

            Why the gap? The government measures what ALL renters pay, not just new
            leases. Most people are locked into year-long leases signed when rents
            were higher. As those leases renew at lower rates, the official number
            will come down.

            Timeline: Expect official shelter inflation to fall toward market rents
            over the next 6-12 months. Since housing is a third of the whole CPI,
            this will pull overall inflation down with it.
            """

    if position.current_stage == "Official rent numbers catch up (slowly)":
        base_msg = f"""
        The official shelter number is finally catching up to reality.

        {chr(10).join('- ' + e for e in position.evidence)}

        Remember: This number is always 12-18 months behind what's happening in
        the market. To see where it's heading, look at Zillow or Apartment List.
        """
        if mortgage_rate:
            base_msg += f"""

        Current mortgage rates: {mortgage_rate:.1f}%. That affects how many people
        buy vs rent, which eventually affects rents themselves.
        """
        return base_msg

    return f"""
    We're at the "{position.current_stage}" stage of the housing cycle.

    {chr(10).join('- ' + e for e in position.evidence)}

    The key thing to remember: Official rent inflation runs 12-18 months behind
    market reality. If you want to know where it's going, look at Zillow ZORI -
    that shows what NEW leases are actually being signed for.
    """


def interpret_wage_spiral(position: ChainPosition, data: dict) -> str:
    """Interpret wage-price spiral risk."""

    # Get expectations data
    mich_1yr = data.get("MICH", {}).get("value")
    t5yifr = data.get("T5YIFR", {}).get("value")
    wage_growth = data.get("CES0500000003", {}).get("yoy_change")

    if position.stage_status == ChainStatus.NOT_TRIGGERED:
        if t5yifr and t5yifr < 2.5:
            return f"""
            No wage-price spiral. Here's why:

            People still expect inflation to come back down. The 5-year forward
            expectation is at {t5yifr:.2f}% - basically where the Fed wants it.

            This is the crucial test. Even if inflation spikes temporarily, as long
            as people believe it's temporary, they don't demand perpetually higher
            wages, and businesses don't raise prices preemptively. The spiral
            never starts.

            Workers got catch-up raises to make up for lost purchasing power, but
            they're not demanding more every year. That's not a spiral - it's
            a one-time adjustment.
            """
        return """
            No signs of a wage-price spiral.

            Wages and prices are moving normally. No self-reinforcing loop where
            higher prices lead to higher wages lead to higher prices.
            """

    if "CRITICAL" in str(position.current_stage).upper() or "expectations" in str(position.current_stage).lower():
        if t5yifr and t5yifr > 3.0:
            return f"""
            Watch out - expectations are getting wobbly.

            The 5-year forward rate is at {t5yifr:.2f}%, which is above the comfort zone.
            {"The 1-year expectation is at " + f"{mich_1yr:.1f}%." if mich_1yr else ""}

            This is the danger point. If people stop believing inflation will come
            back down:
            - Workers start demanding bigger raises to "stay ahead"
            - Businesses raise prices now, expecting costs to rise later
            - It becomes a self-fulfilling prophecy

            The Fed needs to get on top of this fast - either with tough talk or
            more rate hikes. The 1970s spiral only broke when Volcker convinced
            people he'd do whatever it took.
            """
        else:
            msg = """
            There's some wage-price activity, but no spiral forming.
            """
            if t5yifr:
                msg += f"""

            The key number: Long-term inflation expectations at {t5yifr:.2f}%.
            Still close to 2%. That means people trust the Fed to fix this.
            """
            if wage_growth:
                msg += f"""

            Wages are up {wage_growth:.1f}%, which is high, but it's not accelerating.
            These look like catch-up raises, not the start of an endless cycle.
            """
            msg += """

            This is what 2021-2023 looked like: 9% inflation but no spiral, because
            expectations stayed put. The Fed's 40 years of credibility paid off.
            """
            return msg

    return f"""
    Looking at wage-price dynamics: we're at "{position.current_stage}"

    {chr(10).join('- ' + e for e in position.evidence)}

    The one number that matters most: Are long-term expectations near 2%?
    If yes, this won't spiral. If they're rising above 3%, we could have a problem.
    """


def interpret_inflation_dynamics(
    chain: CausalChain,
    position: ChainPosition,
    data: dict,
) -> str:
    """
    Route to appropriate interpretation function based on chain.
    """
    interpreters = {
        "DEMAND_PULL": interpret_demand_pull,
        "COST_PUSH": interpret_cost_push,
        "SHELTER_INFLATION": interpret_shelter,
        "WAGE_PRICE_SPIRAL": interpret_wage_spiral,
    }

    interpreter = interpreters.get(chain.name)
    if interpreter:
        return interpreter(position, data)

    return f"""
    Chain: {chain.name}
    Current stage: {position.current_stage}
    Status: {position.stage_status.value}
    Evidence: {position.evidence}
    """


# =============================================================================
# UNIFIED NARRATIVE FUNCTION
# =============================================================================

def get_current_inflation_narrative(data: dict) -> str:
    """
    Generate a complete narrative of current inflation dynamics.

    This function analyzes all four causal chains and synthesizes
    a coherent explanation of where we are and where we're headed.

    Args:
        data: Dict of series_id -> {value, yoy_change, mom_change, trend}

    Returns:
        Comprehensive narrative string
    """
    chains = [DEMAND_PULL, COST_PUSH, SHELTER_INFLATION, WAGE_PRICE_SPIRAL]
    positions = []
    interpretations = []

    for chain in chains:
        position = detect_chain_position(chain, data)
        positions.append((chain.name, position))
        interpretation = interpret_inflation_dynamics(chain, position, data)
        interpretations.append((chain.name, interpretation))

    # Check key indicators for the summary
    core_pce = data.get("PCEPILFE", {}).get("yoy_change")
    cpi_shelter = data.get("CUSR0000SAH1", {}).get("yoy_change")
    cpi_goods = data.get("CUSR0000SAC", {}).get("yoy_change")
    t5yifr = data.get("T5YIFR", {}).get("value")

    # Start with the bottom line - what does this mean for me?
    narrative = """
================================================================================
THE INFLATION PICTURE: Where We Are and What's Coming
================================================================================

"""

    # Lead with the synthesis - the story, not the data
    if core_pce is not None:
        if core_pce < 2.5:
            narrative += f"""BOTTOM LINE: Inflation is basically back to normal.

Core inflation is at {core_pce:.1f}%, close to the Fed's 2% target. The hard part
is mostly behind us.

"""
        elif core_pce < 3.0:
            narrative += f"""BOTTOM LINE: We're almost there.

Core inflation at {core_pce:.1f}% is within striking distance of the 2% target.
The Fed can see the finish line.

"""
        elif core_pce < 4.0:
            narrative += f"""BOTTOM LINE: Progress, but not done yet.

Core inflation at {core_pce:.1f}% has come down a lot, but there's still work to do.
The Fed will stay cautious until it's clearly below 3%.

"""
        else:
            narrative += f"""BOTTOM LINE: Inflation is still a problem.

At {core_pce:.1f}%, core inflation remains stubbornly high. The Fed will keep rates
elevated until this comes down convincingly.

"""

    # Explain the story of what's happening
    if cpi_shelter and cpi_goods:
        if cpi_goods < 0 and cpi_shelter > 3:
            narrative += f"""
WHAT'S HAPPENING: It's all about housing vs everything else.

Two forces are pulling in opposite directions:
- Stuff you buy (goods): prices FALLING at {abs(cpi_goods):.1f}%
- Housing costs: still UP {cpi_shelter:.1f}%

Why is housing so stubborn? The official rent number is backward-looking.
It measures what ALL renters pay, including those on old leases. Market rents
for NEW leases have already cooled, but it takes 12-18 months for that to show
up in the official numbers as old leases roll over.

This is actually good news in disguise: that high shelter number is going to
come down over the next year as reality catches up.
"""

    # The confidence check
    if t5yifr:
        if t5yifr < 2.5:
            narrative += f"""

THE MOST IMPORTANT NUMBER: {t5yifr:.2f}%

That's what markets expect inflation to be, on average, 5-10 years from now.
Near 2% means people trust the Fed to keep inflation under control.

Why does this matter so much? As long as people expect low inflation:
- Workers don't demand ever-bigger raises to "keep up"
- Businesses don't raise prices preemptively
- One-time shocks stay one-time instead of becoming permanent

The 1970s spiral happened because this expectation got unmoored. Today? Still anchored.
"""
        elif t5yifr > 3.0:
            narrative += f"""

WATCH THIS NUMBER: {t5yifr:.2f}%

That's where markets expect inflation to be in the long run. At {t5yifr:.2f}%,
it's starting to drift up from the Fed's 2% target.

If this keeps rising, it could become a self-fulfilling prophecy - people
expect inflation, so they act in ways that cause it. The Fed will be watching
this closely.
"""

    # Add the detailed analysis for those who want to dig deeper
    narrative += """

================================================================================
DETAILED ANALYSIS: The Four Drivers of Inflation
================================================================================

"""

    # Rename the chains for readability
    friendly_names = {
        "DEMAND_PULL": "Demand-Pull (too much spending)",
        "COST_PUSH": "Cost-Push (supply shocks)",
        "SHELTER_INFLATION": "Housing Costs",
        "WAGE_PRICE_SPIRAL": "Wage-Price Spiral Risk"
    }

    for chain_name, interp in interpretations:
        friendly_name = friendly_names.get(chain_name, chain_name)
        narrative += f"""
--- {friendly_name} ---
{interp}
"""

    return narrative


# =============================================================================
# TEST WITH SIMULATED CURRENT CONDITIONS
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("TESTING INFLATION CAUSAL CHAINS")
    print("=" * 80)

    # Simulate current conditions (early 2026):
    # - Inflation falling, approaching target
    # - Shelter sticky but should decline
    # - Goods deflating
    # - Expectations anchored

    simulated_data = {
        # Core inflation measures
        "PCEPILFE": {"value": 2.6, "yoy_change": 2.6, "trend": "decelerating"},
        "CPILFESL": {"value": None, "yoy_change": 2.8, "trend": "decelerating"},

        # Shelter - still elevated but should fall
        "CUSR0000SAH1": {"value": None, "yoy_change": 4.2, "trend": "decelerating"},
        "CUSR0000SEHA": {"value": None, "yoy_change": 4.0, "trend": "stable"},

        # Market rents - leading indicator, already cooled
        "zillow_rent_yoy": {"value": 2.5, "yoy_change": None, "trend": "stable"},

        # Goods - deflating
        "CUSR0000SAC": {"value": None, "yoy_change": -1.5, "trend": "stable"},

        # Labor market - cooling but solid
        "UNRATE": {"value": 4.2, "yoy_change": None, "trend": "rising"},
        "CES0500000003": {"value": None, "yoy_change": 3.8, "trend": "decelerating"},
        "JTSJOL": {"value": 7.5, "yoy_change": -15.0, "trend": "falling"},

        # Capacity
        "TCU": {"value": 77.5, "yoy_change": -1.2, "trend": "stable"},

        # Expectations - well anchored
        "T5YIFR": {"value": 2.25, "yoy_change": None, "trend": "stable"},
        "MICH": {"value": 2.9, "yoy_change": None, "trend": "stable"},

        # Energy - stable
        "DCOILWTICO": {"value": 72, "yoy_change": -5.0, "trend": "stable"},

        # Mortgage rates
        "MORTGAGE30US": {"value": 6.5, "yoy_change": None, "trend": "stable"},
    }

    print("\n" + "=" * 80)
    print("SIMULATED CONDITIONS (Early 2026)")
    print("=" * 80)
    print("""
    Core PCE: 2.6% (approaching target)
    CPI Shelter: 4.2% (elevated but lagging)
    Market Rents (Zillow): 2.5% (already cooled)
    Goods CPI: -1.5% (deflating)
    Unemployment: 4.2% (normalized)
    5yr5yr Forward: 2.25% (anchored)
    """)

    # Generate full narrative
    narrative = get_current_inflation_narrative(simulated_data)
    print(narrative)

    # Test individual chain detection
    print("\n" + "=" * 80)
    print("INDIVIDUAL CHAIN ANALYSIS")
    print("=" * 80)

    for chain in [DEMAND_PULL, COST_PUSH, SHELTER_INFLATION, WAGE_PRICE_SPIRAL]:
        print(f"\n--- {chain.name} ---")
        position = detect_chain_position(chain, simulated_data)
        print(f"Stage: {position.current_stage}")
        print(f"Status: {position.stage_status.value}")
        print(f"Confidence: {position.confidence:.1%}")
        if position.evidence:
            print("Evidence:")
            for e in position.evidence:
                print(f"  - {e}")
        if position.next_expected:
            print(f"Next: {position.next_expected} ({position.estimated_lag[0]}-{position.estimated_lag[1]}mo)")

    print("\n" + "=" * 80)
    print("CHAIN METADATA")
    print("=" * 80)

    for chain in [DEMAND_PULL, COST_PUSH, SHELTER_INFLATION, WAGE_PRICE_SPIRAL]:
        print(f"\n{chain.name}:")
        print(f"  Stages: {' -> '.join(chain.get_stage_names())}")
        print(f"  Series count: {len(chain.get_all_series())}")
        print(f"  Key insight: {chain.key_insight.strip()[:100]}...")
