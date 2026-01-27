"""
Fed Policy Analysis: Is the Fed Too Tight or Too Loose?

The Federal Reserve controls short-term interest rates to achieve two goals:
1. Keep unemployment low (people should be able to find jobs)
2. Keep inflation near 2% (your money shouldn't lose value too fast)

This module answers three questions:

1. WHERE SHOULD RATES BE? - Based on inflation and unemployment, what interest rate
   makes sense? (Uses a formula called the "Taylor Rule" - but you don't need to
   remember that name, just understand it's math that balances inflation vs jobs.)

2. ARE FINANCIAL CONDITIONS ACTUALLY TIGHT? - The Fed sets one rate, but what matters
   is whether borrowing actually feels expensive. Stock prices, credit availability,
   and the dollar all affect this. Sometimes the Fed is "tight" but markets are loose.

3. WHAT IS THE FED FOCUSED ON? - Based on current data, is the Fed more worried about
   inflation (hawkish) or jobs (dovish)? This helps predict their next move.
"""

from dataclasses import dataclass
from typing import Optional
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.data_fetcher import DataFetcher


# =============================================================================
# TAYLOR RULE FRAMEWORK
# =============================================================================

@dataclass
class TaylorRuleResult:
    """Result of Taylor Rule calculation."""

    implied_rate: float  # What the rule says the rate should be
    actual_rate: float   # Current fed funds rate
    gap: float           # Implied - Actual (positive = Fed is loose)

    # Components
    r_star: float        # Neutral real rate assumption
    inflation: float     # Current inflation
    inflation_gap: float # Inflation - 2% target
    output_gap: float    # Output gap estimate

    # Metadata
    calculation_date: str
    inflation_source: str  # Which inflation measure used


def calculate_taylor_rule(
    inflation: float = None,
    output_gap: float = None,
    r_star: float = 2.5,
    inflation_target: float = 2.0,
    inflation_weight: float = 0.5,
    output_weight: float = 0.5,
    fetcher: DataFetcher = None
) -> TaylorRuleResult:
    """
    Calculate the Taylor Rule implied policy rate.

    The Taylor Rule (1993) is a monetary policy guideline suggesting how central
    banks should set interest rates based on economic conditions. It captures the
    intuition that the Fed should:
    - Raise rates when inflation exceeds target
    - Lower rates when the economy is underperforming

    Classic Formula:
        i = r* + pi + 0.5*(pi - pi*) + 0.5*(y - y*)

    Where:
        i   = nominal federal funds rate
        r*  = real neutral rate (long-run equilibrium rate)
        pi  = current inflation
        pi* = inflation target (2%)
        y   = actual output (GDP)
        y*  = potential output

    Economic Reasoning:
    - When inflation > target: Rule suggests higher rates to cool economy
    - When output < potential: Rule suggests lower rates to stimulate growth
    - The weights (0.5, 0.5) reflect Fed's dual mandate balance

    Args:
        inflation: Current inflation rate (%). If None, fetches Core PCE.
        output_gap: Output gap (%). If None, estimates from unemployment.
        r_star: Neutral real rate assumption. Default 2.5% (Fed's SEP longer-run).
        inflation_target: Fed's inflation target. Default 2.0%.
        inflation_weight: Weight on inflation gap. Default 0.5 (Taylor original).
        output_weight: Weight on output gap. Default 0.5 (Taylor original).
        fetcher: DataFetcher instance. Created if None.

    Returns:
        TaylorRuleResult with implied rate and components.

    Example:
        >>> result = calculate_taylor_rule()
        >>> print(f"Implied rate: {result.implied_rate:.2f}%")
        >>> print(f"Fed is {abs(result.gap)*100:.0f} bps {'loose' if result.gap > 0 else 'tight'}")
    """
    if fetcher is None:
        fetcher = DataFetcher()

    # Fetch current fed funds rate
    fed_funds_data = fetcher.fetch("FEDFUNDS", years=1)
    actual_rate = fed_funds_data.latest_value if fed_funds_data.latest_value else 5.25
    calc_date = fed_funds_data.latest_date or "unknown"

    # Get inflation if not provided (use Core PCE - Fed's preferred measure)
    inflation_source = "provided"
    if inflation is None:
        # Core PCE YoY - PCEPILFE is the index, need to calculate YoY
        pce_data = fetcher.fetch("PCEPILFE", years=2)
        if not pce_data.is_empty and len(pce_data.values) >= 12:
            # Calculate YoY change
            current = pce_data.values[-1]
            year_ago = pce_data.values[-12] if len(pce_data.values) >= 12 else pce_data.values[0]
            inflation = ((current / year_ago) - 1) * 100
            inflation_source = "Core PCE YoY"
        else:
            inflation = 2.8  # Fallback estimate
            inflation_source = "fallback estimate"

    # Estimate output gap if not provided
    # Use Okun's Law approximation: output gap ~ -2 * (unemployment - NAIRU)
    if output_gap is None:
        unemp_data = fetcher.fetch("UNRATE", years=1)
        if not unemp_data.is_empty:
            unemployment = unemp_data.latest_value
            nairu = 4.2  # Fed's current estimate of natural rate
            # Okun's Law: 1% above NAIRU ~ -2% output gap
            output_gap = -2.0 * (unemployment - nairu)
        else:
            output_gap = 0.0  # Assume at potential

    # Calculate inflation gap
    inflation_gap = inflation - inflation_target

    # Taylor Rule calculation
    implied_rate = (
        r_star
        + inflation
        + inflation_weight * inflation_gap
        + output_weight * output_gap
    )

    # Calculate gap (positive = Fed is running loose relative to rule)
    gap = implied_rate - actual_rate

    return TaylorRuleResult(
        implied_rate=implied_rate,
        actual_rate=actual_rate,
        gap=gap,
        r_star=r_star,
        inflation=inflation,
        inflation_gap=inflation_gap,
        output_gap=output_gap,
        calculation_date=calc_date,
        inflation_source=inflation_source
    )


def interpret_taylor_rule(result: TaylorRuleResult) -> str:
    """
    Explain in plain English: Is the Fed's rate too high, too low, or about right?

    Uses a formula that balances inflation (higher rates to cool it) against
    unemployment (lower rates to boost jobs). Tells you if the Fed is being
    aggressive on inflation, supportive of growth, or balanced.

    Args:
        result: TaylorRuleResult from calculate_taylor_rule()

    Returns:
        Human-readable explanation anyone can understand.
    """
    gap_bps = result.gap * 100
    gap_pct = abs(result.gap)

    # Determine stance with plain English explanations
    if abs(gap_bps) < 25:
        stance = "about right"
        stance_detail = (
            f"The Fed's current rate of {result.actual_rate:.2f}% is close to where the math says "
            f"it should be ({result.implied_rate:.2f}%). Policy looks balanced."
        )
    elif gap_bps > 0:
        stance = "lower than expected"
        stance_detail = (
            f"The formula says rates should be {result.implied_rate:.2f}%, but the Fed has them at "
            f"{result.actual_rate:.2f}%. That's {gap_pct:.1f} percentage points lower. "
            f"Either the Fed is being patient about inflation, or they're worried about growth."
        )
    else:
        stance = "higher than expected"
        stance_detail = (
            f"The formula says rates should be {result.implied_rate:.2f}%, but the Fed has them at "
            f"{result.actual_rate:.2f}%. That's {gap_pct:.1f} percentage points higher. "
            f"The Fed appears to be taking a hard line against inflation."
        )

    # Build interpretation - conversational, not a report
    lines = [
        f"WHERE SHOULD INTEREST RATES BE?",
        "",
        f"The Fed's rate: {result.actual_rate:.2f}%",
        f"Formula suggests: {result.implied_rate:.2f}%",
        f"Verdict: Rates are {stance}",
        "",
        stance_detail,
        "",
        "Why the formula says what it says:",
    ]

    # Explain inflation impact
    if result.inflation_gap > 0.5:
        lines.append(f"  - Inflation is {result.inflation:.1f}%, which is {result.inflation_gap:.1f} points above ")
        lines.append(f"    the Fed's 2% target. That pushes for higher rates.")
    elif result.inflation_gap < -0.3:
        lines.append(f"  - Inflation at {result.inflation:.1f}% is actually below the Fed's 2% target.")
        lines.append(f"    That argues for lower rates.")
    else:
        lines.append(f"  - Inflation at {result.inflation:.1f}% is close to the Fed's 2% target. Neutral impact.")

    # Explain output gap impact
    if result.output_gap > 0.5:
        lines.append(f"  - The economy is running hot (output gap: +{result.output_gap:.1f}%). ")
        lines.append(f"    That calls for higher rates to cool things down.")
    elif result.output_gap < -0.5:
        lines.append(f"  - The economy has slack (output gap: {result.output_gap:.1f}%). ")
        lines.append(f"    That argues for lower rates to stimulate growth.")
    else:
        lines.append(f"  - The economy is running close to its potential. Neutral impact.")

    lines.extend([
        "",
        "Keep in mind: This formula is a useful benchmark, not a commandment. The Fed also",
        "considers things like financial stability, global risks, and their own guidance."
    ])

    return "\n".join(lines)


# =============================================================================
# FINANCIAL CONDITIONS FRAMEWORK
# =============================================================================

@dataclass
class FinancialConditionsResult:
    """Result of financial conditions assessment."""

    composite_score: float  # Standardized score (-2 to +2 typical range)
    stance: str             # "tight", "neutral", "loose"

    # Components (all normalized: positive = tighter conditions)
    real_rate: float        # Real fed funds rate
    credit_spread: float    # Corporate credit spreads
    equity_return: float    # Stock market YoY return (inverted)
    dollar_strength: float  # Trade-weighted dollar

    # Raw values
    raw_real_rate: float
    raw_credit_spread: float
    raw_equity_yoy: float
    raw_dollar_level: float

    calculation_date: str
    nfci_available: bool    # Whether we got actual NFCI


def calculate_financial_conditions(
    fetcher: DataFetcher = None,
    use_nfci: bool = True
) -> FinancialConditionsResult:
    """
    Assess overall financial conditions tightness.

    Financial conditions matter because monetary policy works through financial
    markets. Even if the Fed holds rates steady, conditions can tighten if:
    - Credit spreads widen (borrowing becomes harder)
    - Stock prices fall (wealth effect, cost of equity capital rises)
    - Dollar strengthens (exports become less competitive)

    This framework either uses the Chicago Fed's NFCI (if available) or
    constructs a proxy from available market data.

    Components (our proxy):
    1. Real Fed Funds Rate = FEDFUNDS - Core PCE inflation
       - Higher real rates = tighter policy
    2. Credit Spreads = BAA10Y or high yield spread
       - Wider spreads = tighter credit conditions
    3. Stock Market = S&P 500 YoY return
       - Lower returns = tighter conditions (inverted in score)
    4. Dollar Strength = Trade-weighted dollar index
       - Stronger dollar = tighter conditions

    Economic Reasoning:
    - The Fed controls short-term rates but financial conditions reflect
      the full transmission of policy to the real economy
    - Conditions can be tight even with low rates (2008) or loose even
      with high rates (strong risk appetite)
    - This helps assess whether policy is actually restrictive or accommodative

    Args:
        fetcher: DataFetcher instance. Created if None.
        use_nfci: Try to use Chicago Fed NFCI first. Default True.

    Returns:
        FinancialConditionsResult with composite score and components.
    """
    if fetcher is None:
        fetcher = DataFetcher()

    # Try to get Chicago Fed NFCI first
    nfci_available = False
    if use_nfci:
        nfci_data = fetcher.fetch("NFCI", years=1)
        if not nfci_data.is_empty:
            nfci_available = True
            # NFCI is already a composite - positive = tighter
            composite = nfci_data.latest_value
            calc_date = nfci_data.latest_date

            # Still fetch components for context
            # (we'll use rough estimates for the component breakdown)

    # Fetch component data
    fed_funds = fetcher.fetch("FEDFUNDS", years=2)
    pce = fetcher.fetch("PCEPILFE", years=2)

    # Credit spread - try BAA10Y (Moody's BAA - 10yr Treasury)
    credit_spread = fetcher.fetch("BAA10Y", years=2)
    if credit_spread.is_empty:
        # Fallback to high yield spread
        credit_spread = fetcher.fetch("BAMLH0A0HYM2", years=2)

    # S&P 500
    sp500 = fetcher.fetch("SP500", years=2)

    # Trade-weighted dollar
    dollar = fetcher.fetch("DTWEXBGS", years=2)

    # Calculate real rate
    if not fed_funds.is_empty and not pce.is_empty and len(pce.values) >= 12:
        current_pce = pce.values[-1]
        year_ago_pce = pce.values[-12] if len(pce.values) >= 12 else pce.values[0]
        inflation_yoy = ((current_pce / year_ago_pce) - 1) * 100
        raw_real_rate = fed_funds.latest_value - inflation_yoy
    else:
        raw_real_rate = 2.0  # Fallback estimate
        inflation_yoy = 2.8

    # Get credit spread
    raw_credit_spread = credit_spread.latest_value if not credit_spread.is_empty else 2.0

    # Calculate equity YoY
    if not sp500.is_empty and len(sp500.values) >= 252:  # ~1 year of daily data
        current_sp = sp500.values[-1]
        year_ago_sp = sp500.values[-252] if len(sp500.values) >= 252 else sp500.values[0]
        raw_equity_yoy = ((current_sp / year_ago_sp) - 1) * 100
    elif not sp500.is_empty and len(sp500.values) >= 12:
        # Monthly data
        current_sp = sp500.values[-1]
        year_ago_sp = sp500.values[-12]
        raw_equity_yoy = ((current_sp / year_ago_sp) - 1) * 100
    else:
        raw_equity_yoy = 10.0  # Fallback

    # Dollar level
    raw_dollar_level = dollar.latest_value if not dollar.is_empty else 100.0

    calc_date = fed_funds.latest_date or "unknown"

    # If we don't have NFCI, construct composite
    if not nfci_available:
        # Normalize each component to roughly -2 to +2 scale
        # Real rate: historical average ~1%, std ~2%
        real_rate_norm = (raw_real_rate - 1.0) / 2.0

        # Credit spread: historical average ~2%, std ~1%
        # Wider = tighter, so positive contribution
        credit_norm = (raw_credit_spread - 2.0) / 1.0

        # Equity return: higher returns = looser, so invert
        # Average ~10%, std ~15%
        equity_norm = -(raw_equity_yoy - 10.0) / 15.0

        # Dollar: average ~100, std ~10
        # Stronger = tighter
        dollar_norm = (raw_dollar_level - 100.0) / 10.0

        # Equal weight composite
        composite = (real_rate_norm + credit_norm + equity_norm + dollar_norm) / 4
    else:
        # Use NFCI as composite, estimate component contributions
        real_rate_norm = (raw_real_rate - 1.0) / 2.0
        credit_norm = (raw_credit_spread - 2.0) / 1.0
        equity_norm = -(raw_equity_yoy - 10.0) / 15.0
        dollar_norm = (raw_dollar_level - 100.0) / 10.0

    # Determine stance
    if composite > 0.5:
        stance = "tight"
    elif composite < -0.5:
        stance = "loose"
    else:
        stance = "neutral"

    return FinancialConditionsResult(
        composite_score=composite,
        stance=stance,
        real_rate=real_rate_norm,
        credit_spread=credit_norm,
        equity_return=equity_norm,
        dollar_strength=dollar_norm,
        raw_real_rate=raw_real_rate,
        raw_credit_spread=raw_credit_spread,
        raw_equity_yoy=raw_equity_yoy,
        raw_dollar_level=raw_dollar_level,
        calculation_date=calc_date,
        nfci_available=nfci_available
    )


def interpret_financial_conditions(result: FinancialConditionsResult) -> str:
    """
    Explain in plain English: Is money actually hard to come by?

    The Fed sets one interest rate, but that doesn't tell the whole story.
    What matters is whether borrowing FEELS expensive across the economy.
    This looks at interest rates, credit availability, stock prices, and the dollar.

    Args:
        result: FinancialConditionsResult from calculate_financial_conditions()

    Returns:
        Human-readable explanation anyone can understand.
    """
    # Main assessment - conversational
    if result.stance == "tight":
        main_assessment = (
            "Money is hard to come by right now. Borrowing costs are high, lenders are "
            "cautious, and/or markets are nervous. This puts the brakes on spending and "
            "investment - which is probably what the Fed wants if they're fighting inflation."
        )
    elif result.stance == "loose":
        main_assessment = (
            "Despite the Fed's rate hikes, financial conditions feel pretty easy. Credit is "
            "flowing, stocks are up, and businesses can still borrow without much trouble. "
            "This means the Fed's tightening isn't fully biting yet - the economy is shrugging it off."
        )
    else:
        main_assessment = (
            "Financial conditions are neither tight nor loose - roughly what you'd expect "
            "given where the Fed has rates. The Fed's policy is working as intended."
        )

    # Component contributions - explain what each means
    details = []

    # Real rates (interest rate minus inflation)
    if result.real_rate > 0.5:
        details.append(
            f"Interest rates after inflation (real rate: {result.raw_real_rate:+.1f}%) are meaningfully "
            f"positive. Savers are rewarded, but borrowers pay a real cost. This restrains spending."
        )
    elif result.real_rate < -0.5:
        details.append(
            f"Real interest rates are actually negative ({result.raw_real_rate:+.1f}%). "
            f"Inflation is higher than the rate you earn, so money in the bank loses value. "
            f"This encourages spending over saving."
        )

    # Credit spreads
    if result.credit_spread > 0.5:
        details.append(
            f"Companies are paying a {result.raw_credit_spread:.1f}% premium over Treasury rates to borrow. "
            f"That's elevated - lenders are nervous about getting paid back."
        )
    elif result.credit_spread < -0.5:
        details.append(
            f"Credit spreads are tight ({result.raw_credit_spread:.1f}%) - investors are happy to lend "
            f"to companies without demanding much extra yield. Risk appetite is strong."
        )

    # Stock market
    if result.equity_return > 0.5:
        details.append(
            f"Stocks are down {abs(result.raw_equity_yoy):.0f}% over the past year. That makes people "
            f"feel poorer and tightens conditions through the 'wealth effect.'"
        )
    elif result.equity_return < -0.5:
        details.append(
            f"Stocks are up {result.raw_equity_yoy:.0f}% over the past year. Rising portfolios make "
            f"people feel wealthier and more willing to spend - that loosens conditions."
        )

    # Dollar strength
    if result.dollar_strength > 0.5:
        details.append(
            f"The dollar is strong (index: {result.raw_dollar_level:.0f}). Good for importers and travelers, "
            f"but it makes US exports more expensive abroad and tightens conditions for multinationals."
        )
    elif result.dollar_strength < -0.5:
        details.append(
            f"The dollar is weak (index: {result.raw_dollar_level:.0f}). That helps US exporters compete "
            f"globally and effectively loosens financial conditions."
        )

    # Build output
    lines = [
        f"IS MONEY ACTUALLY TIGHT?",
        "",
        f"Overall: Financial conditions are {result.stance.upper()}",
        "",
        main_assessment,
    ]

    if details:
        lines.extend([
            "",
            "What's driving this:",
        ])
        for detail in details:
            lines.append(f"  - {detail}")

    if not details:
        lines.extend([
            "",
            "All major factors (rates, credit, stocks, dollar) are near normal ranges.",
        ])

    return "\n".join(lines)


# =============================================================================
# FED REACTION FUNCTION FRAMEWORK
# =============================================================================

@dataclass
class FedReactionResult:
    """Result of Fed reaction function analysis."""

    likely_stance: str      # "hawkish", "dovish", "balanced"
    urgency: str            # "high", "moderate", "low"
    primary_concern: str    # What the Fed is most focused on

    # Key indicators
    core_pce: float         # Core PCE YoY
    core_pce_gap: float     # Distance from 2% target
    unemployment: float
    unemployment_gap: float # Distance from NAIRU
    inflation_expectations: float  # 5Y5Y breakeven
    expectations_anchored: bool

    # Assessment
    inflation_assessment: str
    employment_assessment: str
    expectations_assessment: str

    calculation_date: str


def calculate_fed_reaction(
    nairu: float = 4.2,
    inflation_target: float = 2.0,
    fetcher: DataFetcher = None
) -> FedReactionResult:
    """
    Analyze what the Fed is likely watching and their probable policy stance.

    The Fed's "reaction function" describes how they respond to economic data.
    While the Taylor Rule is mechanical, this framework tries to capture the
    Fed's actual decision-making process based on their communications.

    Key Inputs (What the Fed Watches):
    1. Core PCE Inflation - The Fed's official target measure
       - Target: 2% (since 2012)
       - Above 2%: Hawkish pressure
       - Below 2%: Dovish pressure

    2. Unemployment vs NAIRU - Labor market slack
       - NAIRU (Non-Accelerating Inflation Rate of Unemployment) ~ 4.2%
       - Below NAIRU: Economy running hot, inflation pressure
       - Above NAIRU: Labor market slack, room for accommodation

    3. Inflation Expectations (T5YIFR) - Are expectations anchored?
       - 5-Year, 5-Year Forward Inflation Expectation Rate
       - Should be ~2% if credibility is maintained
       - De-anchoring would be very concerning for the Fed

    Economic Reasoning:
    - Fed follows "flexible average inflation targeting" (FAIT)
    - They consider both current readings AND trajectory
    - Employment gets more weight when inflation is near target
    - Inflation expectations are a critical anchor

    Args:
        nairu: Non-accelerating inflation rate of unemployment. Default 4.2%.
        inflation_target: Fed's inflation target. Default 2.0%.
        fetcher: DataFetcher instance. Created if None.

    Returns:
        FedReactionResult with likely stance and key indicators.
    """
    if fetcher is None:
        fetcher = DataFetcher()

    # Fetch Core PCE (index, need to calculate YoY)
    pce_data = fetcher.fetch("PCEPILFE", years=2)
    if not pce_data.is_empty and len(pce_data.values) >= 12:
        current_pce = pce_data.values[-1]
        year_ago_pce = pce_data.values[-12]
        core_pce = ((current_pce / year_ago_pce) - 1) * 100
        calc_date = pce_data.latest_date
    else:
        core_pce = 2.8  # Fallback
        calc_date = "unknown"

    core_pce_gap = core_pce - inflation_target

    # Fetch unemployment
    unemp_data = fetcher.fetch("UNRATE", years=1)
    unemployment = unemp_data.latest_value if not unemp_data.is_empty else 4.0
    unemployment_gap = unemployment - nairu

    # Fetch inflation expectations (5Y5Y forward)
    expectations_data = fetcher.fetch("T5YIFR", years=1)
    inflation_expectations = expectations_data.latest_value if not expectations_data.is_empty else 2.3

    # Assess each dimension
    # Inflation assessment
    if core_pce_gap > 1.0:
        inflation_assessment = "significantly_above_target"
        inflation_concern = "high"
    elif core_pce_gap > 0.3:
        inflation_assessment = "moderately_above_target"
        inflation_concern = "moderate"
    elif core_pce_gap > -0.3:
        inflation_assessment = "near_target"
        inflation_concern = "low"
    else:
        inflation_assessment = "below_target"
        inflation_concern = "low"

    # Employment assessment
    if unemployment_gap < -0.5:
        employment_assessment = "tight_labor_market"
        employment_concern = "hawkish"  # Could add to inflation
    elif unemployment_gap < 0.3:
        employment_assessment = "near_full_employment"
        employment_concern = "neutral"
    elif unemployment_gap < 1.0:
        employment_assessment = "some_slack"
        employment_concern = "dovish"
    else:
        employment_assessment = "significant_slack"
        employment_concern = "dovish"

    # Expectations assessment
    if 1.8 <= inflation_expectations <= 2.5:
        expectations_anchored = True
        expectations_assessment = "well_anchored"
    elif inflation_expectations > 2.5:
        expectations_anchored = False
        expectations_assessment = "drifting_higher"
    else:
        expectations_anchored = True  # Low is okay
        expectations_assessment = "anchored_low"

    # Determine overall stance
    # Inflation is typically dominant when above target
    if core_pce_gap > 0.5:
        if employment_concern == "hawkish":
            likely_stance = "hawkish"
            urgency = "high"
            primary_concern = "Inflation above target with tight labor market"
        else:
            likely_stance = "hawkish"
            urgency = "moderate"
            primary_concern = "Inflation above target"
    elif core_pce_gap < -0.3:
        if employment_concern == "dovish":
            likely_stance = "dovish"
            urgency = "moderate"
            primary_concern = "Below-target inflation with labor slack"
        else:
            likely_stance = "balanced"
            urgency = "low"
            primary_concern = "Near mandate on both fronts"
    else:
        # Near target - employment becomes more important
        if employment_concern == "hawkish":
            likely_stance = "balanced"  # But watching inflation
            urgency = "low"
            primary_concern = "Monitoring tight labor market for inflation pressure"
        elif employment_concern == "dovish":
            likely_stance = "dovish"
            urgency = "moderate"
            primary_concern = "Supporting employment with inflation near target"
        else:
            likely_stance = "balanced"
            urgency = "low"
            primary_concern = "Both mandates near target"

    # Override for de-anchored expectations
    if not expectations_anchored and inflation_expectations > 2.5:
        likely_stance = "hawkish"
        urgency = "high"
        primary_concern = "Inflation expectations de-anchoring - credibility at risk"

    return FedReactionResult(
        likely_stance=likely_stance,
        urgency=urgency,
        primary_concern=primary_concern,
        core_pce=core_pce,
        core_pce_gap=core_pce_gap,
        unemployment=unemployment,
        unemployment_gap=unemployment_gap,
        inflation_expectations=inflation_expectations,
        expectations_anchored=expectations_anchored,
        inflation_assessment=inflation_assessment,
        employment_assessment=employment_assessment,
        expectations_assessment=expectations_assessment,
        calculation_date=calc_date
    )


def interpret_fed_reaction(result: FedReactionResult) -> str:
    """
    Explain in plain English: What is the Fed focused on, and what will they do next?

    Is the Fed more worried about inflation (hawkish - likely to raise rates or keep them high)?
    Or more worried about jobs (dovish - likely to cut rates)? Or watching and waiting?

    Args:
        result: FedReactionResult from calculate_fed_reaction()

    Returns:
        Human-readable explanation anyone can understand.
    """
    # Stance description - conversational
    if result.likely_stance == "hawkish":
        stance_desc = (
            "The Fed is in inflation-fighting mode. They're likely to keep rates high, "
            "and don't expect cuts anytime soon. If inflation stays stubborn, they might "
            "even hike again. Their message: we'll tolerate economic pain to beat inflation."
        )
    elif result.likely_stance == "dovish":
        stance_desc = (
            "The Fed is shifting toward supporting growth. They're likely looking for "
            "reasons to cut rates - or at least signal that cuts are coming. Inflation "
            "is less of a worry right now than the job market."
        )
    else:
        stance_desc = (
            "The Fed is in wait-and-see mode. They're not rushing to hike OR cut. "
            "Each new jobs report and inflation reading will matter a lot. Expect them "
            "to talk about being 'data dependent' a lot."
        )

    # Urgency context - make it clear
    urgency_desc = {
        "high": "They may act soon - watch the next meeting closely.",
        "moderate": "No rush, but they're paying close attention to the data.",
        "low": "Expect them to sit tight for a while unless something big changes."
    }

    lines = [
        f"WHAT IS THE FED THINKING?",
        "",
        f"Current stance: {result.likely_stance.upper()}",
        "",
        stance_desc,
        "",
        urgency_desc.get(result.urgency, ""),
        "",
        f"Their biggest concern right now: {result.primary_concern}",
        "",
        "THE THREE THINGS THEY'RE WATCHING:",
        "",
    ]

    # Inflation explanation
    if result.inflation_assessment == "significantly_above_target":
        lines.append(f"1. INFLATION: {result.core_pce:.1f}% - way above their 2% target")
        lines.append(f"   This is the Fed's top priority right now. Until this comes down,")
        lines.append(f"   don't expect them to ease up.")
    elif result.inflation_assessment == "moderately_above_target":
        lines.append(f"1. INFLATION: {result.core_pce:.1f}% - still above the 2% target")
        lines.append(f"   Getting better, but not done yet. The Fed wants to see more progress.")
    elif result.inflation_assessment == "near_target":
        lines.append(f"1. INFLATION: {result.core_pce:.1f}% - close to the 2% target")
        lines.append(f"   Mission nearly accomplished on inflation. This gives the Fed flexibility.")
    else:
        lines.append(f"1. INFLATION: {result.core_pce:.1f}% - actually below the 2% target")
        lines.append(f"   If anything, the Fed might want inflation a bit HIGHER. Unusual situation.")

    lines.append("")

    # Employment explanation
    if result.employment_assessment == "tight_labor_market":
        lines.append(f"2. JOBS: Unemployment at {result.unemployment:.1f}% - very low")
        lines.append(f"   The job market is strong, maybe too strong. Workers have leverage,")
        lines.append(f"   which can push wages and prices up. The Fed isn't worried about jobs.")
    elif result.employment_assessment == "near_full_employment":
        lines.append(f"2. JOBS: Unemployment at {result.unemployment:.1f}% - healthy")
        lines.append(f"   The job market is solid. Not too hot, not too cold. The Fed can")
        lines.append(f"   focus on other things.")
    elif result.employment_assessment == "some_slack":
        lines.append(f"2. JOBS: Unemployment at {result.unemployment:.1f}% - showing some weakness")
        lines.append(f"   The job market is softening. The Fed is starting to worry about")
        lines.append(f"   their other mandate: keeping people employed.")
    else:
        lines.append(f"2. JOBS: Unemployment at {result.unemployment:.1f}% - concerning")
        lines.append(f"   Jobs are the Fed's big worry now. High unemployment means real pain")
        lines.append(f"   for real people. Expect them to prioritize growth over inflation.")

    lines.append("")

    # Expectations explanation
    if result.expectations_assessment == "well_anchored":
        lines.append(f"3. INFLATION EXPECTATIONS: {result.inflation_expectations:.1f}% - stable")
        lines.append(f"   People still believe the Fed will keep inflation around 2% long-term.")
        lines.append(f"   This is crucial - it means the Fed hasn't lost credibility.")
    elif result.expectations_assessment == "drifting_higher":
        lines.append(f"3. INFLATION EXPECTATIONS: {result.inflation_expectations:.1f}% - WARNING")
        lines.append(f"   People are starting to expect higher inflation permanently. This is")
        lines.append(f"   the Fed's nightmare - it can become a self-fulfilling prophecy.")
        lines.append(f"   Expect aggressive action to restore credibility.")
    else:
        lines.append(f"3. INFLATION EXPECTATIONS: {result.inflation_expectations:.1f}% - on the low side")
        lines.append(f"   If anything, people expect less inflation than the Fed wants.")
        lines.append(f"   Not a big concern, but worth noting.")

    lines.extend([
        "",
        "Bottom line: Watch the Fed's next statement and press conference for clues.",
        "Their words often signal moves before they actually happen."
    ])

    return "\n".join(lines)


# =============================================================================
# COMBINED ANALYSIS
# =============================================================================

def full_fed_policy_analysis(fetcher: DataFetcher = None) -> str:
    """
    The big picture: Is Fed policy too tight, too loose, or about right?

    Synthesizes three different ways of looking at the same question:
    1. Where SHOULD rates be based on inflation and unemployment?
    2. Does money FEEL tight or loose in the real economy?
    3. What is the Fed FOCUSED on, and what will they do next?

    Args:
        fetcher: DataFetcher instance. Created if None.

    Returns:
        A synthesized assessment that non-economists can understand.
    """
    if fetcher is None:
        fetcher = DataFetcher()

    # Run all frameworks
    taylor = calculate_taylor_rule(fetcher=fetcher)
    conditions = calculate_financial_conditions(fetcher=fetcher)
    reaction = calculate_fed_reaction(fetcher=fetcher)

    # Build the big picture summary
    taylor_stance = "loose" if taylor.gap > 0.25 else "tight" if taylor.gap < -0.25 else "neutral"

    lines = [
        "THE BIG PICTURE ON FED POLICY",
        "=" * 60,
        "",
    ]

    # Synthesize into ONE clear takeaway
    if taylor_stance == "loose" and conditions.stance == "loose":
        big_picture = (
            "Policy is on the easy side. The Fed's rates are lower than textbook math "
            "suggests, and financial conditions feel loose too. If inflation stays sticky, "
            "expect the Fed to either stay higher for longer or even consider more hikes. "
            "Markets might be underestimating how serious the Fed is about inflation."
        )
    elif taylor_stance == "tight" and conditions.stance == "tight":
        big_picture = (
            "Policy is genuinely restrictive. The Fed's rates are higher than the textbook "
            "level, and financial conditions feel tight across the board. This should be "
            "working to slow inflation - and the economy. The risk now is overdoing it "
            "and tipping into recession."
        )
    elif conditions.stance == "tight" and taylor_stance != "tight":
        big_picture = (
            "An interesting split: The Fed's rate itself isn't that restrictive, but "
            "financial conditions feel tight anyway. Credit spreads, stock weakness, or "
            "a strong dollar are doing some of the Fed's work for them. The Fed might "
            "not need to be as aggressive as they otherwise would."
        )
    elif conditions.stance == "loose" and taylor_stance != "loose":
        big_picture = (
            "Markets are shrugging off the Fed. Despite rate hikes, financial conditions "
            "feel easy - stocks are up, credit is flowing, risk appetite is strong. "
            "The Fed's tightening isn't biting as hard as they'd like. They may need to "
            "do more, or at least stay tight longer, to actually cool things down."
        )
    else:
        big_picture = (
            "Policy looks balanced. The Fed's rate is roughly where the math says it "
            "should be, and financial conditions are neither too tight nor too loose. "
            "The Fed has flexibility here - they can wait and see how the data evolve "
            "before making their next move."
        )

    lines.extend([
        big_picture,
        "",
        f"The Fed's likely next move: {reaction.likely_stance.upper()}",
        f"How urgently: {reaction.urgency.upper()}",
        f"Their main focus: {reaction.primary_concern}",
        "",
        "=" * 60,
        "",
    ])

    # Add individual reports
    lines.append(interpret_taylor_rule(taylor))
    lines.append("")
    lines.append("-" * 60)
    lines.append("")
    lines.append(interpret_financial_conditions(conditions))
    lines.append("")
    lines.append("-" * 60)
    lines.append("")
    lines.append(interpret_fed_reaction(reaction))

    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing Fed Policy Analysis Frameworks")
    print("=" * 60)

    # Initialize fetcher
    fetcher = DataFetcher()

    # Test Taylor Rule
    print("\n1. TAYLOR RULE")
    print("-" * 40)
    taylor_result = calculate_taylor_rule(fetcher=fetcher)
    print(interpret_taylor_rule(taylor_result))

    # Test Financial Conditions
    print("\n\n2. FINANCIAL CONDITIONS")
    print("-" * 40)
    fc_result = calculate_financial_conditions(fetcher=fetcher)
    print(interpret_financial_conditions(fc_result))

    # Test Fed Reaction Function
    print("\n\n3. FED REACTION FUNCTION")
    print("-" * 40)
    reaction_result = calculate_fed_reaction(fetcher=fetcher)
    print(interpret_fed_reaction(reaction_result))

    # Test Full Analysis
    print("\n\n4. FULL COMBINED ANALYSIS")
    print("-" * 40)
    full_analysis = full_fed_policy_analysis(fetcher=fetcher)
    print(full_analysis)
