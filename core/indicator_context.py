"""
Indicator Context Knowledge Base for EconStats.

This module provides rich interpretive context for economic indicators, enabling
more insightful explanations of economic data. For each indicator, we capture:
- What it measures (technical definition)
- Why it matters (economic significance)
- Key thresholds (levels that signal different conditions)
- Historical context (notable events and ranges)
- Interpretation functions (dynamic explanations based on current values)

Usage:
    from core.indicator_context import (
        INDICATOR_CONTEXT,
        get_indicator_context,
        interpret_indicator,
        get_threshold_assessment,
    )

    # Get full context for an indicator
    context = get_indicator_context('UNRATE')

    # Get a dynamic interpretation for a specific value
    interpretation = interpret_indicator('UNRATE', 4.2)
    # Returns: "At 4.2%, unemployment is near the natural rate, suggesting a
    #           balanced labor market"

Design principles:
1. Lead with insight, not just numbers
2. Provide historical context to frame current values
3. Explain what the indicator signals for the broader economy
4. Note when values reach significant thresholds
"""

from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field


@dataclass
class IndicatorContext:
    """
    Rich context for interpreting an economic indicator.

    Attributes:
        series_id: The FRED (or other source) series identifier
        name: Human-readable name of the indicator
        category: Economic category (employment, inflation, gdp, etc.)
        measures: What this indicator technically measures
        why_it_matters: Economic significance and what it tells us
        thresholds: Dict of named thresholds with explanations
        historical_highs: Notable historical high points
        historical_lows: Notable historical low points
        typical_range: Normal range for this indicator
        leading_or_lagging: Whether this is a leading, coincident, or lagging indicator
        update_frequency: How often the data is released
        related_series: Other series that should be considered together
        caveats: Important limitations or nuances to keep in mind
        interpretation_fn: Function that generates dynamic interpretation from value
    """
    series_id: str
    name: str
    category: str
    measures: str
    why_it_matters: str
    thresholds: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    historical_highs: List[Dict[str, Any]] = field(default_factory=list)
    historical_lows: List[Dict[str, Any]] = field(default_factory=list)
    typical_range: Dict[str, float] = field(default_factory=dict)
    leading_or_lagging: str = "coincident"
    update_frequency: str = "monthly"
    related_series: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    interpretation_fn: Optional[Callable[[float], str]] = None


# =============================================================================
# INTERPRETATION FUNCTIONS
# These generate dynamic context based on current values
# =============================================================================

def _interpret_unemployment_rate(value: float) -> str:
    """Generate interpretation for unemployment rate (UNRATE)."""
    if value < 3.5:
        return (f"At {value}%, unemployment is historically low, indicating an extremely "
                f"tight labor market. This level of tightness often leads to wage pressures "
                f"and can be inflationary. The last time unemployment was this low for an "
                f"extended period was the late 1960s.")
    elif value < 4.0:
        return (f"At {value}%, unemployment is below the natural rate (~4%), suggesting "
                f"a tight labor market where employers may struggle to find workers. "
                f"Wage growth typically accelerates at these levels.")
    elif value < 4.5:
        return (f"At {value}%, unemployment is near the natural rate, suggesting a "
                f"balanced labor market. This is roughly where the Fed believes "
                f"unemployment can settle without generating inflation.")
    elif value < 5.5:
        return (f"At {value}%, unemployment is modestly elevated above the natural rate. "
                f"This suggests some slack in the labor market, which typically eases "
                f"wage pressures.")
    elif value < 7.0:
        return (f"At {value}%, unemployment is elevated, indicating meaningful weakness "
                f"in the labor market. Workers face more difficulty finding jobs, "
                f"and wage growth typically slows at these levels.")
    elif value < 10.0:
        return (f"At {value}%, unemployment is at recession levels. This indicates "
                f"significant economic distress, with many workers displaced. "
                f"The Fed typically responds with aggressive rate cuts at these levels.")
    else:
        return (f"At {value}%, unemployment is at crisis levels, comparable to the "
                f"Great Recession (10% in 2009) or COVID shock (14.7% in April 2020). "
                f"This signals severe economic contraction.")


def _interpret_u6_rate(value: float) -> str:
    """Generate interpretation for U-6 underemployment rate."""
    if value < 7.0:
        return (f"At {value}%, the broadest measure of underemployment is historically "
                f"low, indicating not just low unemployment but also few workers stuck "
                f"in part-time jobs who want full-time work.")
    elif value < 8.5:
        return (f"At {value}%, underemployment is healthy. The gap between U-6 and the "
                f"headline rate suggests the 'hidden' labor market slack is minimal.")
    elif value < 10.0:
        return (f"At {value}%, underemployment is modestly elevated. Some workers who "
                f"want full-time work are stuck in part-time positions.")
    elif value < 12.0:
        return (f"At {value}%, underemployment is elevated, indicating broader labor "
                f"market weakness than the headline unemployment rate suggests.")
    else:
        return (f"At {value}%, underemployment signals significant labor market distress, "
                f"with many workers either unemployed or underemployed.")


def _interpret_payrolls(value: float) -> str:
    """Generate interpretation for payroll changes (PAYEMS monthly change in thousands)."""
    if value < 0:
        return (f"The economy lost {abs(value):,.0f}K jobs, indicating contraction. "
                f"Job losses typically occur during recessions or economic shocks.")
    elif value < 50:
        return (f"The economy added just {value:,.0f}K jobs, below the ~100K needed "
                f"to keep pace with population growth. This suggests a softening "
                f"labor market.")
    elif value < 100:
        return (f"Job gains of {value:,.0f}K are modest, roughly keeping pace with "
                f"labor force growth but not reducing unemployment.")
    elif value < 150:
        return (f"Job gains of {value:,.0f}K are solid, suggesting healthy but not "
                f"overheating job growth.")
    elif value < 250:
        return (f"Job gains of {value:,.0f}K are strong, indicating robust labor "
                f"demand. This pace, if sustained, typically puts upward pressure "
                f"on wages.")
    elif value < 400:
        return (f"Job gains of {value:,.0f}K are very strong, suggesting an economy "
                f"expanding rapidly. This pace is typically unsustainable and can "
                f"be inflationary.")
    else:
        return (f"Job gains of {value:,.0f}K are exceptionally strong, often seen "
                f"during recoveries from recessions. This pace indicates rapid "
                f"economic expansion.")


def _interpret_initial_claims(value: float) -> str:
    """Generate interpretation for initial jobless claims (ICSA)."""
    # Value is in thousands
    if value < 200:
        return (f"At {value:,.0f}K, initial claims are historically low, indicating "
                f"very few layoffs. Employers are holding onto workers tightly.")
    elif value < 250:
        return (f"At {value:,.0f}K, initial claims are low, consistent with a healthy "
                f"labor market where layoffs remain contained.")
    elif value < 300:
        return (f"At {value:,.0f}K, initial claims are in normal territory, suggesting "
                f"the labor market is stable without significant layoff activity.")
    elif value < 400:
        return (f"At {value:,.0f}K, initial claims are elevated, suggesting layoffs "
                f"are increasing. This often precedes a rise in the unemployment rate.")
    elif value < 600:
        return (f"At {value:,.0f}K, initial claims signal significant labor market "
                f"weakness. This level is typically associated with recessions.")
    else:
        return (f"At {value:,.0f}K, initial claims are at crisis levels, indicating "
                f"widespread layoffs. The COVID shock saw claims spike to 6.9 million "
                f"in March 2020.")


def _interpret_job_openings(value: float) -> str:
    """Generate interpretation for job openings (JTSJOL) in thousands."""
    # Convert to millions for interpretation
    value_millions = value / 1000
    if value_millions > 11:
        return (f"At {value_millions:.1f} million openings, job demand is historically "
                f"elevated. The post-COVID peak of 12 million reflected extreme labor "
                f"shortages that drove wage inflation.")
    elif value_millions > 9:
        return (f"At {value_millions:.1f} million openings, labor demand remains strong. "
                f"There are roughly 1.5 openings per unemployed worker, giving workers "
                f"significant bargaining power.")
    elif value_millions > 7:
        return (f"At {value_millions:.1f} million openings, the labor market is healthy "
                f"but normalizing. The ratio of openings to unemployed workers is moving "
                f"toward balance.")
    elif value_millions > 5:
        return (f"At {value_millions:.1f} million openings, labor demand is moderate. "
                f"This is closer to pre-pandemic levels and suggests a balanced market.")
    else:
        return (f"At {value_millions:.1f} million openings, labor demand is weak. "
                f"Fewer openings typically leads to slower wage growth and rising "
                f"unemployment.")


def _interpret_prime_age_epop(value: float) -> str:
    """Generate interpretation for prime-age employment-population ratio (LNS12300060)."""
    if value > 81:
        return (f"At {value}%, prime-age employment is at or near record highs. "
                f"This is a more complete picture of labor market health than "
                f"unemployment, as it captures people who've left the labor force.")
    elif value > 80:
        return (f"At {value}%, prime-age employment is very strong, approaching "
                f"the late-1990s peak. This suggests the labor market is drawing "
                f"people back to work.")
    elif value > 78:
        return (f"At {value}%, prime-age employment is healthy, though below the "
                f"pre-pandemic high of 80.5%. Some workers have not returned.")
    elif value > 75:
        return (f"At {value}%, prime-age employment is below normal. A meaningful "
                f"share of working-age adults are not employed, suggesting untapped "
                f"labor supply.")
    else:
        return (f"At {value}%, prime-age employment is depressed, indicating "
                f"significant labor market weakness or structural issues keeping "
                f"people out of work.")


def _interpret_cpi(value: float) -> str:
    """Generate interpretation for CPI year-over-year inflation (CPIAUCSL yoy)."""
    if value < 0:
        return (f"At {value}%, prices are falling (deflation). While this may seem "
                f"good for consumers, persistent deflation can be economically "
                f"damaging as it discourages spending and investment.")
    elif value < 1.5:
        return (f"At {value}%, inflation is below the Fed's 2% target. This 'lowflation' "
                f"can signal weak demand and typically leads to easier monetary policy.")
    elif value < 2.5:
        return (f"At {value}%, inflation is near the Fed's 2% target, indicating "
                f"price stability. This is the goldilocks zone the Fed aims for.")
    elif value < 3.5:
        return (f"At {value}%, inflation is modestly above target. The Fed may tolerate "
                f"this temporarily but will watch for persistence.")
    elif value < 5.0:
        return (f"At {value}%, inflation is elevated. The Fed typically responds with "
                f"rate hikes at these levels to prevent inflation expectations from "
                f"becoming unanchored.")
    elif value < 7.0:
        return (f"At {value}%, inflation is high, eroding purchasing power significantly. "
                f"This level typically triggers aggressive Fed tightening.")
    else:
        return (f"At {value}%, inflation is at levels not seen since the 1980s. "
                f"This represents a serious policy challenge and significant burden "
                f"on households.")


def _interpret_core_pce(value: float) -> str:
    """Generate interpretation for Core PCE (PCEPILFE yoy) - the Fed's preferred measure."""
    if value < 1.5:
        return (f"At {value}%, core PCE is below the Fed's 2% target. The Fed may "
                f"become concerned about inflation being too low and could ease policy.")
    elif value < 2.3:
        return (f"At {value}%, core PCE is near the Fed's 2% target. This is where "
                f"the Fed wants inflation to be - close to but not persistently above 2%.")
    elif value < 3.0:
        return (f"At {value}%, core PCE is modestly elevated above target. The Fed "
                f"will watch whether this is transitory or becoming entrenched.")
    elif value < 4.0:
        return (f"At {value}%, core PCE signals underlying inflation pressure. "
                f"The Fed typically maintains restrictive policy at these levels.")
    elif value < 5.0:
        return (f"At {value}%, core PCE indicates significant inflation. The last "
                f"mile to 2% is often the hardest, requiring sustained tight policy.")
    else:
        return (f"At {value}%, core PCE is very elevated, stripping out food and "
                f"energy reveals broad-based price pressures. This typically requires "
                f"aggressive Fed action.")


def _interpret_shelter_cpi(value: float) -> str:
    """Generate interpretation for shelter/rent inflation (CUSR0000SEHA yoy)."""
    if value < 2.0:
        return (f"At {value}%, rent inflation is low, taking pressure off the overall "
                f"CPI. Shelter is about 1/3 of CPI, so low rent inflation helps a lot.")
    elif value < 4.0:
        return (f"At {value}%, rent inflation is moderate. This is roughly in line "
                f"with historical norms before the pandemic housing surge.")
    elif value < 6.0:
        return (f"At {value}%, rent inflation is elevated. Importantly, CPI rent lags "
                f"actual market rents by 12-18 months - check Zillow data for where "
                f"rents are heading.")
    elif value < 8.0:
        return (f"At {value}%, rent inflation is high, contributing significantly to "
                f"overall inflation. The good news: market rents have already cooled, "
                f"so this should follow with a lag.")
    else:
        return (f"At {value}%, rent inflation is very high. This is a lagging indicator - "
                f"actual market rents peaked months ago, and CPI rent should follow down.")


def _interpret_gdp_growth(value: float) -> str:
    """Generate interpretation for real GDP growth (A191RL1Q225SBEA quarterly SAAR)."""
    if value < -2.0:
        return (f"At {value}%, GDP is contracting significantly. Two consecutive "
                f"quarters of contraction is a common (though not official) recession "
                f"definition.")
    elif value < 0:
        return (f"At {value}%, GDP is contracting. A single negative quarter doesn't "
                f"necessarily mean recession, but it's a warning sign.")
    elif value < 1.0:
        return (f"At {value}%, GDP growth is sluggish, below the ~2% trend growth rate. "
                f"The economy is barely expanding.")
    elif value < 2.0:
        return (f"At {value}%, GDP growth is modest, roughly in line with potential "
                f"growth. This is sustainable but not robust.")
    elif value < 3.0:
        return (f"At {value}%, GDP growth is solid, above trend. The economy is "
                f"expanding at a healthy pace.")
    elif value < 4.0:
        return (f"At {value}%, GDP growth is strong. If sustained, this pace could "
                f"put upward pressure on inflation.")
    else:
        return (f"At {value}%, GDP growth is very strong, often seen during recoveries "
                f"or stimulus-fueled expansions. This pace is typically not sustainable.")


def _interpret_real_gdp_yoy(value: float) -> str:
    """Generate interpretation for real GDP year-over-year growth."""
    if value < -2.0:
        return (f"At {value}% year-over-year, the economy is in significant contraction. "
                f"This magnitude of decline typically indicates a recession.")
    elif value < 0:
        return (f"At {value}% year-over-year, the economy is shrinking. This suggests "
                f"either recession or a significant slowdown.")
    elif value < 1.5:
        return (f"At {value}% year-over-year, growth is below trend. The economy is "
                f"growing but not fast enough to significantly reduce unemployment.")
    elif value < 2.5:
        return (f"At {value}% year-over-year, growth is near the long-run trend of ~2%. "
                f"This represents sustainable expansion.")
    elif value < 3.5:
        return (f"At {value}% year-over-year, growth is above trend, indicating "
                f"a strengthening economy.")
    else:
        return (f"At {value}% year-over-year, growth is strong. This typically occurs "
                f"during recoveries or periods of fiscal/monetary stimulus.")


def _interpret_fed_funds(value: float) -> str:
    """Generate interpretation for Federal Funds Rate (FEDFUNDS)."""
    if value < 0.5:
        return (f"At {value}%, the Fed funds rate is near zero, indicating maximum "
                f"monetary stimulus. The Fed uses near-zero rates to combat recessions "
                f"or deflation.")
    elif value < 2.0:
        return (f"At {value}%, monetary policy is accommodative, with rates below "
                f"the neutral rate. This supports economic growth and borrowing.")
    elif value < 3.0:
        return (f"At {value}%, the Fed funds rate is near the neutral rate, neither "
                f"stimulating nor restraining the economy.")
    elif value < 4.0:
        return (f"At {value}%, policy is modestly restrictive. The Fed is trying to "
                f"slow the economy to bring down inflation.")
    elif value < 5.5:
        return (f"At {value}%, policy is restrictive. Higher rates are designed to "
                f"cool demand and bring inflation back to 2%.")
    else:
        return (f"At {value}%, the Fed funds rate is highly restrictive, comparable "
                f"to levels seen when fighting high inflation. Borrowing costs are "
                f"significantly elevated.")


def _interpret_10y_treasury(value: float) -> str:
    """Generate interpretation for 10-Year Treasury Yield (DGS10)."""
    if value < 1.5:
        return (f"At {value}%, the 10-year yield is very low, often signaling growth "
                f"concerns or flight to safety. Mortgage rates and corporate borrowing "
                f"costs benefit.")
    elif value < 2.5:
        return (f"At {value}%, the 10-year yield is low by historical standards. "
                f"This keeps mortgage rates manageable and supports housing.")
    elif value < 3.5:
        return (f"At {value}%, the 10-year yield is in a normal historical range. "
                f"Bond markets expect moderate growth and inflation.")
    elif value < 4.5:
        return (f"At {value}%, the 10-year yield is elevated. Higher long-term rates "
                f"increase mortgage costs and can weigh on housing and stocks.")
    else:
        return (f"At {value}%, the 10-year yield is high by post-2008 standards. "
                f"This level pushes mortgage rates above 7% and can significantly "
                f"slow housing and investment.")


def _interpret_2y_treasury(value: float) -> str:
    """Generate interpretation for 2-Year Treasury Yield (DGS2)."""
    if value < 1.0:
        return (f"At {value}%, the 2-year yield reflects expectations of very low "
                f"Fed rates ahead, typically during or after recessions.")
    elif value < 2.5:
        return (f"At {value}%, the 2-year yield suggests markets expect accommodative "
                f"Fed policy.")
    elif value < 4.0:
        return (f"At {value}%, the 2-year yield reflects expectations of restrictive "
                f"Fed policy. The 2-year tracks expected Fed moves closely.")
    elif value < 5.0:
        return (f"At {value}%, the 2-year yield indicates markets expect the Fed to "
                f"maintain high rates for some time.")
    else:
        return (f"At {value}%, the 2-year yield is very elevated, pricing in "
                f"sustained restrictive Fed policy to fight inflation.")


def _interpret_yield_curve(value: float) -> str:
    """Generate interpretation for 10Y-2Y Treasury Spread (T10Y2Y)."""
    if value < -1.0:
        return (f"At {value}%, the yield curve is deeply inverted - a strong recession "
                f"signal. Every recession since 1970 has been preceded by inversion, "
                f"though timing varies (typically 12-18 months before recession).")
    elif value < -0.5:
        return (f"At {value}%, the yield curve is inverted, a classic recession warning. "
                f"Short-term rates exceeding long-term rates signals markets expect "
                f"Fed cuts ahead due to economic weakness.")
    elif value < 0:
        return (f"At {value}%, the yield curve is slightly inverted. This is a caution "
                f"sign, though shallow inversions can be false signals.")
    elif value < 0.5:
        return (f"At {value}%, the yield curve is flat, neither signaling strong growth "
                f"expectations nor recession risk.")
    elif value < 1.5:
        return (f"At {value}%, the yield curve has a normal upward slope, suggesting "
                f"markets expect stable growth without imminent recession.")
    else:
        return (f"At {value}%, the yield curve is steeply positive, often seen in "
                f"early recoveries when markets expect growth to accelerate.")


def _interpret_mortgage_rate(value: float) -> str:
    """Generate interpretation for 30-Year Mortgage Rate (MORTGAGE30US)."""
    if value < 4.0:
        return (f"At {value}%, mortgage rates are historically low. The sub-4% rates "
                f"of 2020-2021 fueled a housing boom and left many homeowners with "
                f"cheap mortgages they don't want to give up.")
    elif value < 5.0:
        return (f"At {value}%, mortgage rates are low by historical standards, though "
                f"above the pandemic lows. Housing remains relatively affordable.")
    elif value < 6.0:
        return (f"At {value}%, mortgage rates are moderate. Monthly payments are "
                f"meaningfully higher than during the low-rate era.")
    elif value < 7.0:
        return (f"At {value}%, mortgage rates are elevated. Affordability is strained, "
                f"especially for first-time buyers. Homeowners with 3% mortgages are "
                f"reluctant to sell, limiting supply.")
    elif value < 8.0:
        return (f"At {value}%, mortgage rates significantly impact affordability. "
                f"Monthly payments on a median home are at historic highs relative "
                f"to incomes.")
    else:
        return (f"At {value}%, mortgage rates are at levels not seen since the early "
                f"2000s or 1990s. Housing activity typically slows sharply at these "
                f"rates.")


def _interpret_consumer_sentiment(value: float) -> str:
    """Generate interpretation for U of Michigan Consumer Sentiment (UMCSENT)."""
    if value < 60:
        return (f"At {value}, consumer sentiment is very depressed. Historically, "
                f"readings this low occur during recessions or economic crises. "
                f"However, sentiment and spending don't always align.")
    elif value < 70:
        return (f"At {value}, consumer sentiment is pessimistic. Consumers are worried "
                f"about the economy, though actual spending often holds up better than "
                f"sentiment suggests.")
    elif value < 80:
        return (f"At {value}, consumer sentiment is below average but not dire. "
                f"Consumers have concerns but aren't panicking.")
    elif value < 90:
        return (f"At {value}, consumer sentiment is decent, near the long-run average. "
                f"Consumers feel okay about the economy.")
    elif value < 100:
        return (f"At {value}, consumer sentiment is healthy, suggesting consumers are "
                f"confident about jobs and finances.")
    else:
        return (f"At {value}, consumer sentiment is strong, typically seen during "
                f"economic expansions with low unemployment and rising incomes.")


def _interpret_retail_sales(value: float) -> str:
    """Generate interpretation for retail sales year-over-year growth (RSXFS yoy)."""
    if value < -5:
        return (f"At {value}% year-over-year, retail sales are falling sharply. "
                f"This indicates consumers are pulling back significantly, often "
                f"during recessions.")
    elif value < 0:
        return (f"At {value}% year-over-year, retail sales are contracting. "
                f"Consumer spending, 70% of GDP, is weakening.")
    elif value < 3:
        return (f"At {value}% year-over-year, retail sales growth is modest. "
                f"Adjusted for inflation, real spending may be flat or slightly negative.")
    elif value < 6:
        return (f"At {value}% year-over-year, retail sales growth is solid. "
                f"Consumers continue to spend, supporting economic growth.")
    elif value < 10:
        return (f"At {value}% year-over-year, retail sales growth is strong, "
                f"indicating robust consumer demand.")
    else:
        return (f"At {value}% year-over-year, retail sales growth is very strong, "
                f"often seen during post-recession recoveries or stimulus periods.")


def _interpret_sp500(value: float) -> str:
    """Generate interpretation for S&P 500 level."""
    # This is a level, so context depends heavily on recent history
    return (f"The S&P 500 at {value:,.0f} reflects market expectations for corporate "
            f"earnings and economic growth. Stock prices are forward-looking, often "
            f"moving 6-12 months ahead of the economy.")


def _interpret_home_prices(value: float) -> str:
    """Generate interpretation for Case-Shiller Home Price Index year-over-year change."""
    if value < -5:
        return (f"At {value}% year-over-year, home prices are falling significantly. "
                f"This magnitude of decline was last seen during the 2008 housing crash.")
    elif value < 0:
        return (f"At {value}% year-over-year, home prices are declining. While this "
                f"improves affordability, it can create negative equity for recent buyers.")
    elif value < 3:
        return (f"At {value}% year-over-year, home price growth is modest, roughly "
                f"in line with inflation. This represents a healthy, sustainable pace.")
    elif value < 7:
        return (f"At {value}% year-over-year, home prices are rising solidly. "
                f"Homeowners are building equity, but affordability is being stretched.")
    elif value < 12:
        return (f"At {value}% year-over-year, home price growth is strong. "
                f"This pace outstrips wage growth, worsening affordability.")
    elif value < 20:
        return (f"At {value}% year-over-year, home prices are surging. "
                f"This level of appreciation, seen in 2021-2022, rapidly prices out "
                f"first-time buyers.")
    else:
        return (f"At {value}% year-over-year, home price growth is at boom levels. "
                f"Such rapid appreciation is typically unsustainable.")


# =============================================================================
# INDICATOR CONTEXT DATABASE
# Comprehensive context for major economic indicators
# =============================================================================

INDICATOR_CONTEXT: Dict[str, IndicatorContext] = {
    # =========================================================================
    # EMPLOYMENT INDICATORS
    # =========================================================================
    'UNRATE': IndicatorContext(
        series_id='UNRATE',
        name='Unemployment Rate',
        category='employment',
        measures=(
            'Percentage of the labor force (people working or actively seeking work) '
            'who are unemployed. Based on the household survey of ~60,000 households.'
        ),
        why_it_matters=(
            'The most-watched labor market indicator. Key input to Fed policy - the Fed '
            'has a dual mandate to pursue maximum employment and price stability. Rising '
            'unemployment signals economic weakness and can trigger rate cuts.'
        ),
        thresholds={
            'very_tight': {'value': 3.5, 'meaning': 'Historically tight, wage pressures likely'},
            'tight': {'value': 4.0, 'meaning': 'Below natural rate, employers competing for workers'},
            'natural_rate': {'value': 4.0, 'meaning': 'Fed estimates of long-run sustainable rate'},
            'elevated': {'value': 5.5, 'meaning': 'Above natural rate, some slack in labor market'},
            'recession': {'value': 7.0, 'meaning': 'Typically seen during recessions'},
            'crisis': {'value': 10.0, 'meaning': 'Severe economic distress'},
        },
        historical_highs=[
            {'value': 14.7, 'date': 'April 2020', 'event': 'COVID-19 pandemic'},
            {'value': 10.0, 'date': 'October 2009', 'event': 'Great Recession'},
            {'value': 10.8, 'date': 'November 1982', 'event': 'Volcker recession'},
        ],
        historical_lows=[
            {'value': 3.4, 'date': 'January 2023', 'event': '50-year low'},
            {'value': 3.5, 'date': 'September 2019', 'event': 'Pre-pandemic low'},
            {'value': 3.4, 'date': 'May 1969', 'event': 'Post-WWII expansion'},
        ],
        typical_range={'low': 4.0, 'high': 6.0},
        leading_or_lagging='lagging',
        update_frequency='monthly (first Friday)',
        related_series=['U6RATE', 'PAYEMS', 'ICSA', 'LNS12300060'],
        caveats=[
            'Lagging indicator - rises after other signals show weakness',
            "Doesn't count discouraged workers who've stopped looking",
            "Doesn't capture underemployment (part-time wanting full-time)",
            'Sahm Rule: 0.5% rise from 12-month low signals recession',
        ],
        interpretation_fn=_interpret_unemployment_rate,
    ),

    'U6RATE': IndicatorContext(
        series_id='U6RATE',
        name='U-6 Underemployment Rate',
        category='employment',
        measures=(
            'Broadest measure of labor underutilization: includes unemployed, marginally '
            'attached workers (want a job but stopped looking), and part-time workers '
            'who want full-time work.'
        ),
        why_it_matters=(
            "Shows the 'hidden' slack in the labor market that headline unemployment misses. "
            "A large gap between U-6 and U-3 (headline) suggests many workers aren't getting "
            "the hours or opportunities they want."
        ),
        thresholds={
            'very_tight': {'value': 7.0, 'meaning': 'Very little underutilization'},
            'healthy': {'value': 8.0, 'meaning': 'Minimal hidden slack'},
            'moderate_slack': {'value': 10.0, 'meaning': 'Some underemployment'},
            'elevated': {'value': 12.0, 'meaning': 'Significant underemployment'},
        },
        typical_range={'low': 7.0, 'high': 10.0},
        leading_or_lagging='lagging',
        update_frequency='monthly',
        related_series=['UNRATE', 'LNS12300060', 'CIVPART'],
        caveats=[
            'Gap between U-6 and U-3 shows underemployment beyond unemployment',
            'Can remain elevated even as headline unemployment falls',
        ],
        interpretation_fn=_interpret_u6_rate,
    ),

    'PAYEMS': IndicatorContext(
        series_id='PAYEMS',
        name='Total Nonfarm Payrolls',
        category='employment',
        measures=(
            'Total number of paid workers in the US economy excluding farm workers, '
            'private household employees, and non-profit employees. Based on establishment '
            'survey of ~670,000 worksites.'
        ),
        why_it_matters=(
            "The monthly jobs number that moves markets. Shows actual hiring/firing activity. "
            "More reliable than household survey for employment trends due to larger sample size."
        ),
        thresholds={
            'job_loss': {'value': 0, 'meaning': 'Economy shedding jobs'},
            'breakeven': {'value': 100, 'meaning': 'Roughly keeps pace with population growth'},
            'solid': {'value': 150, 'meaning': 'Healthy job creation'},
            'strong': {'value': 250, 'meaning': 'Robust labor demand'},
            'very_strong': {'value': 400, 'meaning': 'Hot labor market, potential wage pressure'},
        },
        typical_range={'low': 100, 'high': 250},
        leading_or_lagging='coincident',
        update_frequency='monthly (first Friday)',
        related_series=['UNRATE', 'CES0500000003', 'ICSA'],
        caveats=[
            'Focus on monthly CHANGE, not level (159M employed)',
            '3-month average smooths out monthly noise',
            'Revisions can be significant - first print often revised',
            'Seasonal adjustments can be tricky around holidays',
        ],
        interpretation_fn=_interpret_payrolls,
    ),

    'ICSA': IndicatorContext(
        series_id='ICSA',
        name='Initial Jobless Claims',
        category='employment',
        measures=(
            'Number of people filing for unemployment insurance for the first time. '
            'Released weekly, making it the timeliest labor market indicator.'
        ),
        why_it_matters=(
            "Earliest warning signal for labor market weakness. Rising claims indicate "
            "increasing layoffs, often preceding rises in the unemployment rate by several months."
        ),
        thresholds={
            'very_low': {'value': 200, 'meaning': 'Minimal layoffs, very healthy labor market'},
            'low': {'value': 250, 'meaning': 'Low layoff activity'},
            'normal': {'value': 300, 'meaning': 'Typical range'},
            'elevated': {'value': 400, 'meaning': 'Rising layoffs, warning sign'},
            'recession': {'value': 600, 'meaning': 'Recession-level layoffs'},
        },
        typical_range={'low': 200, 'high': 300},
        leading_or_lagging='leading',
        update_frequency='weekly (Thursday)',
        related_series=['CCSA', 'UNRATE', 'PAYEMS'],
        caveats=[
            'Weekly data is noisy - use 4-week moving average',
            "Doesn't capture all layoffs (some workers don't file)",
            'Continuing claims (CCSA) shows duration of unemployment',
        ],
        interpretation_fn=_interpret_initial_claims,
    ),

    'JTSJOL': IndicatorContext(
        series_id='JTSJOL',
        name='Job Openings (JOLTS)',
        category='employment',
        measures=(
            'Total number of job openings on the last business day of the month. '
            'Part of the Job Openings and Labor Turnover Survey (JOLTS).'
        ),
        why_it_matters=(
            "Leading indicator of labor demand. The ratio of job openings to unemployed workers "
            "shows labor market tightness. High openings = workers have bargaining power. "
            "Falling openings often precede rising unemployment."
        ),
        thresholds={
            'excess_demand': {'value': 11000, 'meaning': 'Extreme labor shortage (in thousands)'},
            'tight': {'value': 9000, 'meaning': 'More openings than normal'},
            'balanced': {'value': 7000, 'meaning': 'Roughly 1 opening per unemployed'},
            'slack': {'value': 5000, 'meaning': 'Fewer opportunities for workers'},
        },
        typical_range={'low': 5000, 'high': 8000},
        leading_or_lagging='leading',
        update_frequency='monthly (released with ~6 week lag)',
        related_series=['UNRATE', 'JTSQUR', 'PAYEMS'],
        caveats=[
            'Released with significant lag (~6 weeks)',
            'Openings-to-unemployed ratio is key metric',
            'Post-COVID, the ratio reached 2:1 (historic)',
            'Watch quits rate (JTSQUR) alongside openings',
        ],
        interpretation_fn=_interpret_job_openings,
    ),

    'LNS12300060': IndicatorContext(
        series_id='LNS12300060',
        name='Prime-Age Employment-Population Ratio',
        category='employment',
        measures=(
            'Percentage of people ages 25-54 (prime working age) who are employed. '
            'Unlike unemployment rate, this captures people who left the labor force.'
        ),
        why_it_matters=(
            "Better measure of labor market health than unemployment rate because it counts "
            "everyone, not just those actively seeking work. High prime-age employment means "
            "the economy is drawing people into the workforce."
        ),
        thresholds={
            'record': {'value': 81, 'meaning': 'Near all-time highs'},
            'strong': {'value': 80, 'meaning': 'Very healthy employment'},
            'healthy': {'value': 78, 'meaning': 'Good but below peak'},
            'depressed': {'value': 75, 'meaning': 'Many prime-age adults not working'},
        },
        historical_highs=[
            {'value': 81.9, 'date': 'April 2000', 'event': 'Dot-com boom'},
            {'value': 80.5, 'date': 'January 2020', 'event': 'Pre-pandemic'},
        ],
        typical_range={'low': 78, 'high': 81},
        leading_or_lagging='coincident',
        update_frequency='monthly',
        related_series=['UNRATE', 'CIVPART', 'PAYEMS'],
        caveats=[
            'Prime-age (25-54) avoids distortions from aging, school, retirement',
            'Includes people who stopped looking (unemployment rate misses them)',
        ],
        interpretation_fn=_interpret_prime_age_epop,
    ),

    # =========================================================================
    # INFLATION INDICATORS
    # =========================================================================
    'CPIAUCSL': IndicatorContext(
        series_id='CPIAUCSL',
        name='Consumer Price Index (CPI)',
        category='inflation',
        measures=(
            'Average change in prices paid by urban consumers for a basket of goods '
            'and services. Covers ~93% of the US population.'
        ),
        why_it_matters=(
            "The most widely followed inflation measure. Affects everything from Fed policy "
            "to Social Security adjustments. High CPI erodes purchasing power and can force "
            "the Fed to raise rates."
        ),
        thresholds={
            'deflation': {'value': 0, 'meaning': 'Prices falling - can signal weak demand'},
            'lowflation': {'value': 1.5, 'meaning': 'Below Fed target'},
            'target': {'value': 2.0, 'meaning': 'Fed target (though Fed prefers PCE)'},
            'above_target': {'value': 3.0, 'meaning': 'Modestly elevated'},
            'elevated': {'value': 5.0, 'meaning': 'High, eroding purchasing power'},
            'crisis': {'value': 7.0, 'meaning': 'Very high, 1980s-level'},
        },
        historical_highs=[
            {'value': 9.1, 'date': 'June 2022', 'event': 'Post-pandemic inflation spike'},
            {'value': 14.8, 'date': 'March 1980', 'event': 'Volcker-era inflation'},
        ],
        typical_range={'low': 1.5, 'high': 3.0},
        leading_or_lagging='coincident',
        update_frequency='monthly',
        related_series=['PCEPILFE', 'CPILFESL', 'CUSR0000SEHA'],
        caveats=[
            'Fed prefers Core PCE, but CPI gets more attention',
            'Show as year-over-year change, not index level',
            'Shelter (1/3 of CPI) lags actual rents by 12-18 months',
            'Headline includes volatile food and energy',
        ],
        interpretation_fn=_interpret_cpi,
    ),

    'PCEPILFE': IndicatorContext(
        series_id='PCEPILFE',
        name='Core PCE (Fed\'s Target Measure)',
        category='inflation',
        measures=(
            'Personal Consumption Expenditures price index excluding food and energy. '
            "This is the Fed's preferred inflation measure for policy decisions."
        ),
        why_it_matters=(
            "The Fed explicitly targets 2% Core PCE inflation. Unlike CPI, PCE adjusts for "
            "substitution effects (people buying chicken when beef gets expensive) and has "
            "broader coverage. Fed policy hinges on this number."
        ),
        thresholds={
            'below_target': {'value': 1.5, 'meaning': 'Fed may ease policy'},
            'at_target': {'value': 2.0, 'meaning': 'Goldilocks zone'},
            'above_target': {'value': 2.5, 'meaning': 'Fed likely to stay restrictive'},
            'elevated': {'value': 3.5, 'meaning': 'Fed likely hiking/holding high'},
            'high': {'value': 5.0, 'meaning': 'Significant inflation problem'},
        },
        typical_range={'low': 1.5, 'high': 2.5},
        leading_or_lagging='coincident',
        update_frequency='monthly',
        related_series=['CPIAUCSL', 'PCEPI', 'CPILFESL'],
        caveats=[
            "Fed's actual target - more important than CPI for policy",
            'Core excludes food and energy for underlying trend',
            'Supercore (services ex-housing) is new focus',
        ],
        interpretation_fn=_interpret_core_pce,
    ),

    'CUSR0000SEHA': IndicatorContext(
        series_id='CUSR0000SEHA',
        name='CPI: Rent of Primary Residence',
        category='inflation',
        measures=(
            'Year-over-year change in the rent component of CPI, measuring what '
            'tenants pay for housing.'
        ),
        why_it_matters=(
            "Shelter is ~1/3 of CPI, making it crucial for overall inflation. CPI rent lags "
            "actual market rents by 12-18 months because BLS measures existing leases, not "
            "new leases. When market rents fall, CPI rent follows with a delay."
        ),
        thresholds={
            'low': {'value': 2.0, 'meaning': 'Taking pressure off headline CPI'},
            'normal': {'value': 4.0, 'meaning': 'Historical norm'},
            'elevated': {'value': 6.0, 'meaning': 'Contributing to inflation'},
            'high': {'value': 8.0, 'meaning': 'Major inflation driver'},
        },
        typical_range={'low': 2.0, 'high': 5.0},
        leading_or_lagging='lagging',
        update_frequency='monthly',
        related_series=['CPIAUCSL', 'CUSR0000SAH1'],
        caveats=[
            'LAGS market rents by 12-18 months',
            'Check Zillow ZORI for where rents are heading',
            'Owners Equivalent Rent (OER) has similar lag',
            'Together, shelter is ~1/3 of CPI',
        ],
        interpretation_fn=_interpret_shelter_cpi,
    ),

    # =========================================================================
    # GDP AND GROWTH INDICATORS
    # =========================================================================
    'A191RL1Q225SBEA': IndicatorContext(
        series_id='A191RL1Q225SBEA',
        name='Real GDP Growth (Quarterly, SAAR)',
        category='gdp',
        measures=(
            'Quarter-over-quarter growth in real (inflation-adjusted) GDP, expressed '
            'as a seasonally adjusted annual rate (SAAR). This is the headline "GDP growth" '
            'number reported each quarter.'
        ),
        why_it_matters=(
            "The broadest measure of economic output. Two consecutive negative quarters is "
            "commonly (though not officially) considered a recession. Strong GDP growth "
            "supports employment; weak growth raises recession concerns."
        ),
        thresholds={
            'contraction': {'value': 0, 'meaning': 'Economy shrinking'},
            'stall_speed': {'value': 1.0, 'meaning': 'Barely growing'},
            'trend': {'value': 2.0, 'meaning': 'Long-run sustainable pace'},
            'above_trend': {'value': 3.0, 'meaning': 'Strong growth'},
            'hot': {'value': 4.0, 'meaning': 'Potentially inflationary'},
        },
        typical_range={'low': 1.5, 'high': 3.0},
        leading_or_lagging='coincident',
        update_frequency='quarterly (advance, second, third estimates)',
        related_series=['GDPC1', 'A191RO1Q156NBEA', 'PCE'],
        caveats=[
            'SAAR extrapolates quarterly growth to annual pace',
            'Volatile quarter-to-quarter; YoY is smoother',
            'Three estimates: advance (1 month), second, final',
            'Watch contributions from consumer, investment, trade',
        ],
        interpretation_fn=_interpret_gdp_growth,
    ),

    'GDPC1': IndicatorContext(
        series_id='GDPC1',
        name='Real GDP (Level)',
        category='gdp',
        measures=(
            'Total value of goods and services produced, adjusted for inflation. '
            'Expressed in billions of chained 2017 dollars.'
        ),
        why_it_matters=(
            "The total size of the US economy. While the level itself is less informative "
            "than growth rates, comparing to pre-crisis levels shows recovery progress."
        ),
        typical_range={'low': 0, 'high': 0},  # Level, not rate
        leading_or_lagging='coincident',
        update_frequency='quarterly',
        related_series=['A191RL1Q225SBEA', 'A191RO1Q156NBEA'],
        caveats=[
            'Show as YoY % change, not level',
            'Quarterly data - can be volatile',
        ],
        interpretation_fn=_interpret_real_gdp_yoy,
    ),

    # =========================================================================
    # INTEREST RATES AND FED POLICY
    # =========================================================================
    'FEDFUNDS': IndicatorContext(
        series_id='FEDFUNDS',
        name='Federal Funds Rate',
        category='fed_rates',
        measures=(
            'Interest rate at which banks lend reserves to each other overnight. '
            'The Fed sets a target range and uses open market operations to maintain it.'
        ),
        why_it_matters=(
            "The Fed's primary policy tool. Changes ripple through the entire economy: "
            "mortgages, car loans, credit cards, business investment, and stock prices "
            "all respond to Fed funds rate changes."
        ),
        thresholds={
            'zero_lower_bound': {'value': 0.25, 'meaning': 'Maximum accommodation'},
            'accommodative': {'value': 2.0, 'meaning': 'Below neutral, supporting growth'},
            'neutral': {'value': 2.5, 'meaning': 'Neither stimulating nor restraining'},
            'restrictive': {'value': 4.0, 'meaning': 'Slowing economy intentionally'},
            'highly_restrictive': {'value': 5.5, 'meaning': 'Significant economic drag'},
        },
        historical_highs=[
            {'value': 20.0, 'date': 'June 1981', 'event': 'Volcker inflation fight'},
            {'value': 6.5, 'date': 'July 2000', 'event': 'Pre-dot-com crash'},
            {'value': 5.33, 'date': 'July 2023', 'event': 'Post-COVID inflation fight'},
        ],
        typical_range={'low': 1.0, 'high': 4.0},
        leading_or_lagging='leading',
        update_frequency='daily (target changes 8x per year at FOMC)',
        related_series=['DGS2', 'DGS10', 'MORTGAGE30US'],
        caveats=[
            'Fed sets target range, market determines effective rate',
            'Policy lags: takes 12-18 months to fully impact economy',
            'Watch Fed dots and futures for rate path expectations',
        ],
        interpretation_fn=_interpret_fed_funds,
    ),

    'DGS10': IndicatorContext(
        series_id='DGS10',
        name='10-Year Treasury Yield',
        category='fed_rates',
        measures=(
            'Market yield on US Treasury securities with 10-year maturity. '
            'Set by market forces (supply and demand for bonds), not the Fed.'
        ),
        why_it_matters=(
            "The benchmark for long-term rates. Mortgage rates track the 10-year closely. "
            "Also reflects market expectations for growth and inflation over the next decade. "
            "Rising yields can weigh on stocks and housing."
        ),
        thresholds={
            'very_low': {'value': 1.5, 'meaning': 'Recession fears or deflation'},
            'low': {'value': 2.5, 'meaning': 'Accommodative financial conditions'},
            'normal': {'value': 3.5, 'meaning': 'Historical average range'},
            'elevated': {'value': 4.5, 'meaning': 'Tightening financial conditions'},
            'high': {'value': 5.0, 'meaning': 'Significant headwind for economy'},
        },
        typical_range={'low': 2.0, 'high': 4.0},
        leading_or_lagging='leading',
        update_frequency='daily',
        related_series=['DGS2', 'T10Y2Y', 'MORTGAGE30US'],
        caveats=[
            'Market-determined, not Fed-controlled',
            'Reflects growth + inflation expectations + term premium',
            'Key driver of mortgage rates',
        ],
        interpretation_fn=_interpret_10y_treasury,
    ),

    'DGS2': IndicatorContext(
        series_id='DGS2',
        name='2-Year Treasury Yield',
        category='fed_rates',
        measures=(
            'Market yield on US Treasury securities with 2-year maturity. '
            'Closely tracks expected Fed policy over the next two years.'
        ),
        why_it_matters=(
            "Best market indicator of expected Fed policy. The 2-year moves in anticipation "
            "of Fed rate changes. When 2-year exceeds 10-year (inversion), it signals markets "
            "expect the Fed to cut rates eventually."
        ),
        thresholds={
            'very_low': {'value': 1.0, 'meaning': 'Expecting very low Fed rates'},
            'low': {'value': 2.5, 'meaning': 'Expecting accommodative policy'},
            'restrictive': {'value': 4.0, 'meaning': 'Expecting tight policy'},
            'very_restrictive': {'value': 5.0, 'meaning': 'Expecting sustained tight policy'},
        },
        typical_range={'low': 1.5, 'high': 4.0},
        leading_or_lagging='leading',
        update_frequency='daily',
        related_series=['DGS10', 'T10Y2Y', 'FEDFUNDS'],
        caveats=[
            'Tracks expected Fed policy closely',
            'Compare to 10-year for yield curve signal',
        ],
        interpretation_fn=_interpret_2y_treasury,
    ),

    'T10Y2Y': IndicatorContext(
        series_id='T10Y2Y',
        name='10Y-2Y Treasury Spread (Yield Curve)',
        category='fed_rates',
        measures=(
            'Difference between 10-year and 2-year Treasury yields. '
            'Positive = normal (long rates higher), Negative = inverted.'
        ),
        why_it_matters=(
            "The classic recession predictor. An inverted yield curve (negative spread) has "
            "preceded every recession since 1970, typically by 12-18 months. Reflects market "
            "expectations that the Fed will need to cut rates due to weakness."
        ),
        thresholds={
            'deeply_inverted': {'value': -1.0, 'meaning': 'Strong recession signal'},
            'inverted': {'value': -0.5, 'meaning': 'Recession warning'},
            'slightly_inverted': {'value': 0, 'meaning': 'Caution flag'},
            'flat': {'value': 0.5, 'meaning': 'Neutral'},
            'normal': {'value': 1.5, 'meaning': 'Healthy upward slope'},
            'steep': {'value': 2.5, 'meaning': 'Recovery expectations'},
        },
        historical_lows=[
            {'value': -1.08, 'date': 'July 2023', 'event': 'Deepest inversion since 1980s'},
        ],
        typical_range={'low': 0.5, 'high': 2.0},
        leading_or_lagging='leading',
        update_frequency='daily',
        related_series=['DGS10', 'DGS2', 'FEDFUNDS'],
        caveats=[
            'Inverted = recession signal, but timing is uncertain (6-24 months)',
            '2023 inversion deepest since 1980s',
            'Un-inversion can also signal imminent recession',
            "Some argue 'this time is different' - it never is",
        ],
        interpretation_fn=_interpret_yield_curve,
    ),

    'MORTGAGE30US': IndicatorContext(
        series_id='MORTGAGE30US',
        name='30-Year Fixed Mortgage Rate',
        category='housing',
        measures=(
            'Average interest rate on a 30-year fixed-rate mortgage, '
            'based on Freddie Mac survey of lenders.'
        ),
        why_it_matters=(
            "Determines affordability for homebuyers. Mortgage rates roughly track the 10-year "
            "Treasury plus a spread. Low rates in 2020-2021 (sub-3%) created a 'lock-in effect' - "
            "homeowners won't sell and give up cheap mortgages, limiting supply."
        ),
        thresholds={
            'very_low': {'value': 4.0, 'meaning': 'Highly accommodative, fuels housing'},
            'low': {'value': 5.0, 'meaning': 'Affordable for most'},
            'moderate': {'value': 6.0, 'meaning': 'Stretching affordability'},
            'elevated': {'value': 7.0, 'meaning': 'Affordability strained'},
            'high': {'value': 8.0, 'meaning': 'Significant headwind for housing'},
        },
        historical_highs=[
            {'value': 18.6, 'date': 'October 1981', 'event': 'Volcker-era rates'},
            {'value': 7.8, 'date': 'October 2023', 'event': 'Post-pandemic high'},
        ],
        historical_lows=[
            {'value': 2.65, 'date': 'January 2021', 'event': 'All-time low'},
        ],
        typical_range={'low': 4.0, 'high': 6.0},
        leading_or_lagging='coincident',
        update_frequency='weekly (Thursday)',
        related_series=['DGS10', 'CSUSHPINSA', 'HOUST'],
        caveats=[
            'Roughly = 10-year Treasury + 1.5-2% spread',
            "Millions locked in at 3% won't sell",
            'Affects both demand (buyers) and supply (sellers)',
        ],
        interpretation_fn=_interpret_mortgage_rate,
    ),

    # =========================================================================
    # CONSUMER INDICATORS
    # =========================================================================
    'UMCSENT': IndicatorContext(
        series_id='UMCSENT',
        name='Consumer Sentiment (U of Michigan)',
        category='consumer',
        measures=(
            "University of Michigan's index of consumer confidence based on surveys "
            "about personal finances, business conditions, and buying conditions. "
            "Index where 1966 = 100."
        ),
        why_it_matters=(
            "Leading indicator of consumer spending, which is 70% of GDP. Sentiment often "
            "moves ahead of actual spending changes. However, there can be a disconnect - "
            "people sometimes feel bad about the economy but keep spending."
        ),
        thresholds={
            'very_depressed': {'value': 60, 'meaning': 'Crisis-level pessimism'},
            'depressed': {'value': 70, 'meaning': 'Consumers worried'},
            'below_average': {'value': 80, 'meaning': 'Subdued confidence'},
            'average': {'value': 90, 'meaning': 'Normal range'},
            'healthy': {'value': 100, 'meaning': 'Confident consumers'},
        },
        historical_highs=[
            {'value': 111.8, 'date': 'January 2000', 'event': 'Dot-com peak'},
        ],
        historical_lows=[
            {'value': 50.0, 'date': 'June 2022', 'event': 'Inflation shock'},
            {'value': 51.7, 'date': 'May 1980', 'event': 'Stagflation'},
        ],
        typical_range={'low': 75, 'high': 100},
        leading_or_lagging='leading',
        update_frequency='monthly (preliminary and final)',
        related_series=['PCE', 'RSXFS', 'PSAVERT'],
        caveats=[
            'Sentiment and spending often diverge',
            "Consumers say they feel bad but keep spending",
            'Inflation expectations component closely watched by Fed',
        ],
        interpretation_fn=_interpret_consumer_sentiment,
    ),

    'RSXFS': IndicatorContext(
        series_id='RSXFS',
        name='Retail Sales (Excluding Food Services)',
        category='consumer',
        measures=(
            'Monthly retail sales excluding restaurants and bars. '
            'Measures goods purchases by consumers.'
        ),
        why_it_matters=(
            "Consumer spending is 70% of GDP, so retail sales directly impact growth. "
            "Shows whether consumers are opening their wallets. Nominal measure - need "
            "to adjust for inflation to see 'real' spending."
        ),
        thresholds={
            'contraction': {'value': -5, 'meaning': 'Consumers pulling back sharply'},
            'weak': {'value': 0, 'meaning': 'Flat or declining'},
            'modest': {'value': 3, 'meaning': 'Barely keeping pace with inflation'},
            'solid': {'value': 6, 'meaning': 'Healthy growth'},
            'strong': {'value': 10, 'meaning': 'Robust consumer spending'},
        },
        typical_range={'low': 2, 'high': 6},
        leading_or_lagging='coincident',
        update_frequency='monthly',
        related_series=['PCE', 'UMCSENT', 'PSAVERT'],
        caveats=[
            'Nominal - must adjust for inflation',
            'Excludes services (most of spending)',
            'Monthly data noisy, watch 3-month trend',
        ],
        interpretation_fn=_interpret_retail_sales,
    ),

    # =========================================================================
    # HOUSING INDICATORS
    # =========================================================================
    'CSUSHPINSA': IndicatorContext(
        series_id='CSUSHPINSA',
        name='Case-Shiller US National Home Price Index',
        category='housing',
        measures=(
            "S&P CoreLogic Case-Shiller index tracking repeat sales of single-family homes. "
            "The gold standard for measuring home price changes."
        ),
        why_it_matters=(
            "Home equity is the largest asset for most Americans. Rising prices increase "
            "wealth effect (people spend more when they feel rich). Falling prices can "
            "cause financial distress, especially for recent buyers."
        ),
        thresholds={
            'falling': {'value': 0, 'meaning': 'Prices declining'},
            'modest': {'value': 3, 'meaning': 'In line with inflation'},
            'solid': {'value': 6, 'meaning': 'Outpacing inflation'},
            'strong': {'value': 10, 'meaning': 'Significant appreciation'},
            'unsustainable': {'value': 15, 'meaning': 'Boom conditions'},
        },
        historical_highs=[
            {'value': 21.2, 'date': 'March 2022', 'event': 'Post-COVID surge'},
        ],
        historical_lows=[
            {'value': -18.0, 'date': 'December 2008', 'event': 'Housing crisis'},
        ],
        typical_range={'low': 3, 'high': 7},
        leading_or_lagging='lagging',
        update_frequency='monthly (2-month lag)',
        related_series=['MORTGAGE30US', 'HOUST', 'PERMIT'],
        caveats=[
            '2-month lag in data',
            'Show as YoY change, not index level',
            'Repeat-sales method avoids mix bias',
            'Regional indices can differ significantly',
        ],
        interpretation_fn=_interpret_home_prices,
    ),

    # =========================================================================
    # MARKET INDICATORS
    # =========================================================================
    'SP500': IndicatorContext(
        series_id='SP500',
        name='S&P 500 Index',
        category='markets',
        measures=(
            'Market-cap weighted index of 500 large US companies. '
            "Represents roughly 80% of US stock market value."
        ),
        why_it_matters=(
            "The primary benchmark for US stocks and a leading economic indicator. "
            "Stock prices reflect expectations for future earnings and economic growth. "
            "Affects consumer wealth effect and business investment decisions."
        ),
        typical_range={'low': 0, 'high': 0},  # Level changes over time
        leading_or_lagging='leading',
        update_frequency='daily',
        related_series=['VIXCLS', 'DGS10', 'UMCSENT'],
        caveats=[
            'Forward-looking - often moves 6-12 months ahead of economy',
            "Cap-weighted = dominated by largest companies (the 'Magnificent 7')",
            'Short-term volatility vs long-term trends',
        ],
        interpretation_fn=_interpret_sp500,
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_indicator_context(series_id: str) -> Optional[IndicatorContext]:
    """
    Retrieve the full context for an indicator.

    Args:
        series_id: The FRED (or other source) series identifier

    Returns:
        IndicatorContext object or None if not found

    Example:
        >>> context = get_indicator_context('UNRATE')
        >>> print(context.why_it_matters)
        "The most-watched labor market indicator..."
    """
    return INDICATOR_CONTEXT.get(series_id)


def interpret_indicator(series_id: str, value: float) -> str:
    """
    Generate a dynamic interpretation for a specific indicator value.

    Args:
        series_id: The FRED (or other source) series identifier
        value: The current value to interpret

    Returns:
        String interpretation of what this value means

    Example:
        >>> interpret_indicator('UNRATE', 4.2)
        "At 4.2%, unemployment is near the natural rate..."
    """
    context = INDICATOR_CONTEXT.get(series_id)
    if context and context.interpretation_fn:
        return context.interpretation_fn(value)
    return f"{series_id} is at {value}"


def get_threshold_assessment(
    series_id: str,
    value: float
) -> Optional[Dict[str, Any]]:
    """
    Determine which threshold bracket a value falls into.

    Args:
        series_id: The FRED (or other source) series identifier
        value: The current value to assess

    Returns:
        Dict with threshold name, value, and meaning, or None

    Example:
        >>> get_threshold_assessment('UNRATE', 3.8)
        {'name': 'tight', 'threshold': 4.0,
         'meaning': 'Below natural rate, employers competing for workers'}
    """
    context = INDICATOR_CONTEXT.get(series_id)
    if not context or not context.thresholds:
        return None

    # Sort thresholds by value
    sorted_thresholds = sorted(
        context.thresholds.items(),
        key=lambda x: x[1]['value']
    )

    # Find the appropriate bracket
    for i, (name, threshold_data) in enumerate(sorted_thresholds):
        threshold_value = threshold_data['value']
        if value < threshold_value:
            if i == 0:
                return {
                    'name': name,
                    'threshold': threshold_value,
                    'meaning': threshold_data['meaning'],
                    'position': 'below_first',
                }
            else:
                prev_name, prev_data = sorted_thresholds[i - 1]
                return {
                    'name': prev_name,
                    'threshold': prev_data['value'],
                    'meaning': prev_data['meaning'],
                    'position': 'between',
                }

    # Above all thresholds
    last_name, last_data = sorted_thresholds[-1]
    return {
        'name': last_name,
        'threshold': last_data['value'],
        'meaning': last_data['meaning'],
        'position': 'above_last',
    }


def get_related_indicators(series_id: str) -> List[str]:
    """
    Get series IDs that should be considered alongside this indicator.

    Args:
        series_id: The FRED (or other source) series identifier

    Returns:
        List of related series IDs

    Example:
        >>> get_related_indicators('UNRATE')
        ['U6RATE', 'PAYEMS', 'ICSA', 'LNS12300060']
    """
    context = INDICATOR_CONTEXT.get(series_id)
    if context:
        return context.related_series
    return []


def get_historical_context(series_id: str, value: float) -> str:
    """
    Generate historical context for a value.

    Args:
        series_id: The FRED (or other source) series identifier
        value: The current value

    Returns:
        String describing how this value compares historically
    """
    context = INDICATOR_CONTEXT.get(series_id)
    if not context:
        return ""

    comparisons = []

    # Compare to historical highs
    for high in context.historical_highs:
        if value >= high['value'] * 0.9:  # Within 10% of high
            comparisons.append(
                f"approaching the {high['event']} high of {high['value']} "
                f"({high['date']})"
            )
            break

    # Compare to historical lows
    for low in context.historical_lows:
        if value <= low['value'] * 1.1:  # Within 10% of low
            comparisons.append(
                f"near the {low['event']} low of {low['value']} "
                f"({low['date']})"
            )
            break

    # Compare to typical range
    if context.typical_range:
        low_typical = context.typical_range.get('low', 0)
        high_typical = context.typical_range.get('high', 0)
        if low_typical and high_typical:
            if value < low_typical:
                comparisons.append(f"below the typical range of {low_typical}-{high_typical}")
            elif value > high_typical:
                comparisons.append(f"above the typical range of {low_typical}-{high_typical}")
            else:
                comparisons.append(f"within the typical range of {low_typical}-{high_typical}")

    if comparisons:
        return f"Currently {', '.join(comparisons)}."
    return ""


def get_caveats(series_id: str) -> List[str]:
    """
    Get important caveats and limitations for an indicator.

    Args:
        series_id: The FRED (or other source) series identifier

    Returns:
        List of caveat strings
    """
    context = INDICATOR_CONTEXT.get(series_id)
    if context:
        return context.caveats
    return []


def format_indicator_explanation(
    series_id: str,
    value: float,
    include_thresholds: bool = True,
    include_historical: bool = True,
    include_caveats: bool = False,
) -> str:
    """
    Generate a comprehensive explanation for an indicator value.

    Args:
        series_id: The FRED (or other source) series identifier
        value: The current value
        include_thresholds: Whether to include threshold assessment
        include_historical: Whether to include historical comparisons
        include_caveats: Whether to include caveats

    Returns:
        Multi-paragraph explanation string
    """
    context = INDICATOR_CONTEXT.get(series_id)
    if not context:
        return f"{series_id} is at {value}."

    parts = []

    # Primary interpretation
    if context.interpretation_fn:
        parts.append(context.interpretation_fn(value))

    # Historical context
    if include_historical:
        hist_context = get_historical_context(series_id, value)
        if hist_context:
            parts.append(hist_context)

    # Why it matters
    if context.why_it_matters:
        parts.append(f"Why this matters: {context.why_it_matters}")

    # Caveats
    if include_caveats and context.caveats:
        caveats_text = "Keep in mind: " + "; ".join(context.caveats[:2])
        parts.append(caveats_text)

    return " ".join(parts)


# =============================================================================
# QUICK ACCESS LISTS
# =============================================================================

# Series by category for quick lookup
EMPLOYMENT_SERIES = ['UNRATE', 'U6RATE', 'PAYEMS', 'ICSA', 'JTSJOL', 'LNS12300060']
INFLATION_SERIES = ['CPIAUCSL', 'PCEPILFE', 'CUSR0000SEHA']
GDP_SERIES = ['A191RL1Q225SBEA', 'GDPC1']
FED_RATES_SERIES = ['FEDFUNDS', 'DGS10', 'DGS2', 'T10Y2Y', 'MORTGAGE30US']
CONSUMER_SERIES = ['UMCSENT', 'RSXFS']
HOUSING_SERIES = ['CSUSHPINSA', 'MORTGAGE30US']
MARKET_SERIES = ['SP500']


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("INDICATOR CONTEXT KNOWLEDGE BASE")
    print("=" * 70)

    # Test unemployment interpretation
    print("\n--- Unemployment Rate (UNRATE) ---")
    for test_value in [3.4, 4.0, 5.5, 8.0]:
        print(f"\nValue: {test_value}%")
        print(f"Interpretation: {interpret_indicator('UNRATE', test_value)}")

    # Test yield curve interpretation
    print("\n--- Yield Curve (T10Y2Y) ---")
    for test_value in [-1.0, -0.3, 0.5, 1.5]:
        print(f"\nValue: {test_value}%")
        print(f"Interpretation: {interpret_indicator('T10Y2Y', test_value)}")

    # Test full explanation
    print("\n--- Full Explanation: Fed Funds at 5.25% ---")
    print(format_indicator_explanation('FEDFUNDS', 5.25, include_caveats=True))

    # Show coverage
    print(f"\n--- Coverage: {len(INDICATOR_CONTEXT)} indicators ---")
    for series_id, context in INDICATOR_CONTEXT.items():
        print(f"  {series_id}: {context.name}")
